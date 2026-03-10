"""CLI entrypoint."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config_store import DEFAULT_SECRET_PROVIDER, ensure_layout, get_config_root, load_config, write_config
from .display import PlainDisplay, RichDisplay
from .display.base import Display
from .error_handler import LOG_FILENAME, handle_fatal
from .gitignore import check_gitignore
from .planning import build_plan_context, default_plan_path, render_plan, save_plan, validate_saved_plan
from .project import find_project_root, resolve_project_manifest
from .sync_runner import run_apply
from .uninstall import run_uninstall
from .version_checks import check_client_versions, get_default_versions_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync AI configs (agents, skills, commands, rules, MCP servers) per-project.",
    )
    subparsers = parser.add_subparsers(dest="command")

    install_parser = subparsers.add_parser("install", help="Initialize ~/.ai-sync bootstrap and store auth settings.")
    install_parser.add_argument("--op-account", metavar="NAME", help="1Password account name (desktop app auth).")
    install_parser.add_argument("--force", action="store_true", help="Overwrite existing config.toml.")

    plan_parser = subparsers.add_parser("plan", help="Resolve sources, render a plan, and save a plan artifact.")
    plan_parser.add_argument("--plain", action="store_true", help="Plain output mode (no interactive prompts).")
    plan_parser.add_argument("--out", metavar="PATH", help="Write the plan artifact to PATH.")

    apply_parser = subparsers.add_parser("apply", help="Apply ai-sync config to the current project.")
    apply_parser.add_argument("--plain", action="store_true", help="Plain output mode (no interactive prompts).")
    apply_parser.add_argument("planfile", nargs="?", help="Optional saved plan file to validate and apply.")

    subparsers.add_parser("doctor", help="Check machine bootstrap and project planning health.")

    uninstall_parser = subparsers.add_parser("uninstall", help="Remove ai-sync managed changes from current project.")
    uninstall_parser.add_argument("--apply", action="store_true", help="Apply uninstall (default is dry-run).")

    return parser


def _run_install(args: argparse.Namespace, display: Display) -> int:
    root = ensure_layout()
    config_path = root / "config.toml"
    if config_path.exists() and not args.force:
        display.panel(
            f"Config already exists: {config_path}\nUse --force to overwrite.",
            title="Already installed",
            style="error",
        )
        return 1

    op_account = args.op_account or os.environ.get("OP_ACCOUNT")
    token = os.environ.get("OP_SERVICE_ACCOUNT_TOKEN")
    if not op_account and not token:
        if sys.stdin.isatty():
            op_account = input("1Password account name (as shown in app): ").strip() or None
        if not op_account:
            display.panel(
                "No 1Password account configured.\n"
                "Provide --op-account NAME, set OP_ACCOUNT, or set OP_SERVICE_ACCOUNT_TOKEN.",
                title="Missing account",
                style="error",
            )
            return 1

    config = {"secret_provider": DEFAULT_SECRET_PROVIDER}
    if op_account:
        config["op_account"] = op_account
    write_config(config, root)
    display.print(f"Wrote {config_path}", style="success")
    return 0


def _ensure_installed(config_root: Path, display: Display) -> bool:
    if config_root.exists() and (config_root / "config.toml").exists():
        return True
    display.panel("Run `ai-sync install` first.", title="Not set up", style="error")
    return False


def _run_plan(args: argparse.Namespace, config_root: Path, display: Display) -> int:
    if not _ensure_installed(config_root, display):
        return 1
    project_root = find_project_root()
    if project_root is None:
        display.panel("No .ai-sync.yaml found. Create one first.", title="No project", style="error")
        return 1

    uncovered = check_gitignore(project_root)
    if uncovered:
        display.panel(
            "The following ai-sync managed paths are not covered by .gitignore:\n"
            + "\n".join(f"  - {p}" for p in uncovered),
            title="Gitignore gate failed",
            style="error",
        )
        return 1

    versions_path = get_default_versions_path()
    ok, msg = check_client_versions(versions_path)
    if not ok or msg != "OK":
        display.print(f"Warning: {msg}", style="warning")

    context = build_plan_context(project_root, config_root, display)
    render_plan(context.plan, display)
    out_path = Path(args.out).expanduser() if getattr(args, "out", None) else default_plan_path(project_root)
    save_plan(context.plan, out_path)
    display.print(f"Saved plan to {out_path}", style="success")
    return 0


def _run_apply(args: argparse.Namespace, config_root: Path, display: Display) -> int:
    if not _ensure_installed(config_root, display):
        return 1
    project_root = find_project_root()
    if project_root is None:
        display.panel("No .ai-sync.yaml found. Create one first.", title="No project", style="error")
        return 1

    uncovered = check_gitignore(project_root)
    if uncovered:
        display.panel(
            "The following ai-sync managed paths are not covered by .gitignore:\n"
            + "\n".join(f"  - {p}" for p in uncovered)
            + "\n\nAdd them to .gitignore before applying.",
            title="Gitignore gate failed",
            style="error",
        )
        return 1

    versions_path = get_default_versions_path()
    ok, msg = check_client_versions(versions_path)
    if not ok or msg != "OK":
        display.print(f"Warning: {msg}", style="warning")

    context = build_plan_context(project_root, config_root, display)
    planfile = getattr(args, "planfile", None)
    if planfile:
        validate_saved_plan(Path(planfile).expanduser(), context.plan)
        display.print(f"Validated saved plan: {planfile}", style="success")
    else:
        display.print("Applying a fresh plan computed from the current project state.", style="info")
        render_plan(context.plan, display)

    return run_apply(
        project_root=project_root,
        source_roots={alias: source.root for alias, source in context.resolved_sources.items()},
        manifest=context.manifest,
        mcp_manifest=context.mcp_manifest,
        secrets=context.secrets,
        runtime_env=context.runtime_env,
        display=display,
    )


def _run_doctor(config_root: Path, display: Display) -> int:
    display.print(f"Config root: {config_root}")
    if not config_root.exists():
        display.print("  Missing config root. Run `ai-sync install`.", style="warning")
        return 1
    config_path = config_root / "config.toml"
    if not config_path.exists():
        display.print("  Missing config.toml. Run `ai-sync install`.", style="warning")
        return 1

    try:
        config = load_config(config_root)
    except RuntimeError as exc:
        display.print(f"  Failed to read config: {exc}", style="warning")
        return 1

    op_account = os.environ.get("OP_ACCOUNT") or config.get("op_account")
    token = os.environ.get("OP_SERVICE_ACCOUNT_TOKEN")
    if token:
        display.print("  1Password auth: OK (service account token)", style="success")
    elif op_account:
        display.print(f"  1Password auth: OK (OP_ACCOUNT={op_account})", style="success")
    else:
        display.print("  1Password auth: missing (set OP_SERVICE_ACCOUNT_TOKEN or OP_ACCOUNT)", style="warning")
        return 1

    project_root = find_project_root()
    if project_root:
        display.print(f"\nProject: {project_root}")
        try:
            manifest = resolve_project_manifest(project_root)
            display.print(f"  .ai-sync.yaml: OK ({len(manifest.sources)} sources declared)", style="success")
        except RuntimeError as exc:
            display.print(f"  .ai-sync.yaml: {exc}", style="warning")
            return 1

        uncovered = check_gitignore(project_root)
        if uncovered:
            display.print(f"  Gitignore: MISSING coverage for {', '.join(uncovered)}", style="warning")
        else:
            display.print("  Gitignore: OK", style="success")

        try:
            context = build_plan_context(project_root, config_root, display)
            display.print(
                f"  Planned: {len(context.plan.actions)} action(s) from {len(context.resolved_sources)} source(s)",
                style="success",
            )
        except RuntimeError as exc:
            display.print(f"  Plan check failed: {exc}", style="warning")
    else:
        display.print("\nNo project found (no .ai-sync.yaml in current directory tree)", style="dim")

    return 0


def _run_uninstall(args: argparse.Namespace, display: Display) -> int:
    project_root = find_project_root()
    if project_root is None:
        display.panel("No .ai-sync.yaml found. Nothing to uninstall.", title="No project", style="error")
        return 1
    return run_uninstall(project_root, apply=bool(args.apply))


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    if args.command is None:
        args.command = "apply"
        if not hasattr(args, "plain"):
            args.plain = False

    config_root = get_config_root()
    log_path = config_root / LOG_FILENAME
    display = PlainDisplay() if getattr(args, "plain", False) else RichDisplay()

    try:
        if args.command == "install":
            return _run_install(args, display)
        if args.command == "plan":
            return _run_plan(args, config_root, display)
        if args.command == "doctor":
            return _run_doctor(config_root, display)
        if args.command == "uninstall":
            return _run_uninstall(args, display)
        if args.command == "apply":
            return _run_apply(args, config_root, display)
    except Exception as exc:
        handle_fatal(exc, display, log_path)
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
