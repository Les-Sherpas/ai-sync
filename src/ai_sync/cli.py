"""CLI entrypoint."""

from __future__ import annotations

import argparse
import sys

from .di import bootstrap_runtime
from .services.error_handler_service import LOG_FILENAME
from .services.plain_display_service import PlainDisplayService
from .services.rich_display_service import RichDisplayService


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync AI configs (agents, skills, commands, rules, MCP servers) per-project.",
    )
    subparsers = parser.add_subparsers(dest="command")

    install_parser = subparsers.add_parser(
        "install", help="Initialize ~/.ai-sync bootstrap and store auth settings."
    )
    install_parser.add_argument(
        "--op-account-identifier",
        metavar="SIGNIN_ADDRESS_OR_USER_ID",
        help="1Password sign-in address or user ID for desktop app auth (example: example.1password.com).",
    )
    install_parser.add_argument(
        "--force", action="store_true", help="Overwrite existing config.toml."
    )

    plan_parser = subparsers.add_parser(
        "plan", help="Resolve sources, render a plan, and save a plan artifact."
    )
    plan_parser.add_argument(
        "--plain", action="store_true", help="Plain output mode (no interactive prompts)."
    )
    plan_parser.add_argument("--out", metavar="PATH", help="Write the plan artifact to PATH.")

    apply_parser = subparsers.add_parser(
        "apply", help="Apply ai-sync config to the current project."
    )
    apply_parser.add_argument(
        "--plain", action="store_true", help="Plain output mode (no interactive prompts)."
    )
    apply_parser.add_argument(
        "planfile", nargs="?", help="Optional saved plan file to validate and apply."
    )

    subparsers.add_parser("doctor", help="Check machine bootstrap and project planning health.")

    uninstall_parser = subparsers.add_parser(
        "uninstall", help="Remove ai-sync managed changes from current project."
    )
    uninstall_parser.add_argument(
        "--apply", action="store_true", help="Apply uninstall (default is dry-run)."
    )

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    if args.command is None:
        args.command = "apply"
        if not hasattr(args, "plain"):
            args.plain = False

    runtime = bootstrap_runtime()
    config_root = runtime.container.config_store_service().get_config_root()
    log_path = config_root / LOG_FILENAME
    display = (
        PlainDisplayService()
        if getattr(args, "plain", False)
        else RichDisplayService()
    )

    try:
        if args.command == "install":
            return runtime.install_service.run(
                display=display,
                op_account_identifier=args.op_account_identifier,
                force=bool(args.force),
            )
        if args.command == "plan":
            return runtime.plan_service.run(
                config_root=config_root, display=display, out=args.out
            )
        if args.command == "doctor":
            return runtime.doctor_service.run(config_root=config_root, display=display)
        if args.command == "uninstall":
            return runtime.uninstall_service.run(display=display, apply=bool(args.apply))
        if args.command == "apply":
            return runtime.apply_service.run(
                config_root=config_root, display=display, planfile=args.planfile
            )
    except Exception as exc:
        runtime.error_handler_service.handle_fatal(exc, display, log_path)
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
