"""Service for resolving 1Password secret references."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

from ai_sync.services.one_password_cli_service import OnePasswordCliService
from ai_sync.services.one_password_sdk_service import OnePasswordSdkService

OP_REF_PREFIX = "op://"


class OnePasswordSecretService:
    """Resolve op:// refs using CLI-first then SDK fallback."""

    def __init__(
        self,
        *,
        cli_injector: OnePasswordCliService,
        sdk_resolver: OnePasswordSdkService,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._cli_injector = cli_injector
        self._sdk_resolver = sdk_resolver
        self._environ = environ if environ is not None else os.environ

    def resolve(
        self, values: dict[str, str], config_root: Path | None = None
    ) -> dict[str, str]:
        op_entries = {k: v for k, v in values.items() if v.startswith("op://")}
        plain_entries = {k: v for k, v in values.items() if not v.startswith("op://")}

        if not op_entries:
            return dict(values)

        lines = [f"{name}={ref}" for name, ref in op_entries.items()]
        content = "\n".join(lines)
        refs, line_to_ref = self._extract_op_refs(lines)

        cli_error_msg: str | None = None
        try:
            resolved_op = self._cli_injector.inject(
                content, config_root=config_root, environ=self._environ
            )
            return {**plain_entries, **resolved_op}
        except subprocess.CalledProcessError as exc:
            cli_error_msg = self._format_cli_error(exc.stderr or "")
        except Exception as exc:
            cli_error_msg = str(exc)

        try:
            resolved_op = self._sdk_resolver.resolve_refs(
                refs=refs,
                lines=lines,
                line_to_ref=line_to_ref,
                config_root=config_root,
                environ=self._environ,
            )
            return {**plain_entries, **resolved_op}
        except Exception as sdk_error:
            raise RuntimeError(
                f"Failed to resolve 1Password references.\nCLI: {cli_error_msg}\nSDK: {sdk_error}"
            ) from sdk_error

    @staticmethod
    def _extract_op_refs(lines: list[str]) -> tuple[list[str], dict[int, str]]:
        refs: list[str] = []
        seen: set[str] = set()
        line_to_ref: dict[int, str] = {}
        for idx, line in enumerate(lines):
            if "=" not in line or line.strip().startswith("#"):
                continue
            _, value = line.split("=", 1)
            ref = value.strip()
            if ref.startswith(OP_REF_PREFIX):
                line_to_ref[idx] = ref
                if ref not in seen:
                    seen.add(ref)
                    refs.append(ref)
        return refs, line_to_ref

    @staticmethod
    def _format_cli_error(message: str) -> str:
        lowered = message.lower()
        if "multiple accounts found" in lowered:
            return (
                "1Password CLI could not choose an account. Set OP_ACCOUNT to the sign-in address "
                "or user ID from `op account list`, or rerun "
                "`ai-sync install --op-account-identifier example.1password.com`."
            )
        if "found no accounts for filter" in lowered:
            return (
                "Configured OP_ACCOUNT does not match a 1Password CLI sign-in address or user ID. "
                "Use `op account list` to find the correct value."
            )
        return message.strip() or "1Password CLI failed to resolve secret references."
