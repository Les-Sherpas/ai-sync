"""Service for resolving 1Password refs via SDK fallback."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

from onepassword.client import Client

from ai_sync.services.one_password_auth_service import OnePasswordAuthService
from ai_sync.services.one_password_cli_service import OnePasswordCliService


class OnePasswordSdkService:
    """Resolve refs via 1Password SDK fallback."""

    def __init__(self, *, auth_resolver: OnePasswordAuthService) -> None:
        self._auth_resolver = auth_resolver

    def resolve_refs(
        self,
        *,
        refs: list[str],
        lines: list[str],
        line_to_ref: dict[int, str],
        config_root: Path | None,
        environ: Mapping[str, str],
    ) -> dict[str, str]:
        return asyncio.run(
            self._resolve_refs_async(
                refs=refs,
                lines=lines,
                line_to_ref=line_to_ref,
                config_root=config_root,
                environ=environ,
            )
        )

    async def _resolve_refs_async(
        self,
        *,
        refs: list[str],
        lines: list[str],
        line_to_ref: dict[int, str],
        config_root: Path | None,
        environ: Mapping[str, str],
    ) -> dict[str, str]:
        auth = self._auth_resolver.resolve_auth(config_root, environ)
        client = await Client.authenticate(
            auth=auth,
            integration_name="ai-sync",
            integration_version="0.1.0",
        )
        response = await client.secrets.resolve_all(refs)
        failures: list[tuple[str, object]] = []
        resolved: dict[str, str] = {}
        for ref, resp in response.individual_responses.items():
            if resp.error is not None:
                failures.append((ref, resp.error))
            elif resp.content:
                resolved[ref] = resp.content.secret
        if failures:
            raise RuntimeError(self._format_sdk_failures(failures))
        injected = self._inject_resolved(lines, line_to_ref, resolved)
        return OnePasswordCliService.parse_injected_env(injected)

    @staticmethod
    def _inject_resolved(
        lines: list[str], line_to_ref: dict[int, str], resolved: dict[str, str]
    ) -> str:
        out: list[str] = []
        for idx, line in enumerate(lines):
            if idx in line_to_ref:
                ref = line_to_ref[idx]
                name = line.split("=", 1)[0].strip()
                out.append(f"{name}={resolved.get(ref, ref)}")
            else:
                out.append(line)
        return "\n".join(out)

    @staticmethod
    def _format_sdk_failures(failures: list[tuple[str, object]]) -> str:
        vault_not_found: set[str] = set()
        other: list[str] = []

        for ref, error in failures:
            err_str = str(error)
            if "vaultNotFound" in err_str:
                parts = ref.removeprefix("op://").split("/", 2)
                vault_not_found.add(parts[0])
            else:
                other.append(f"  {ref}: {error}")

        msgs: list[str] = []
        if vault_not_found:
            names = ", ".join(f"'{vault}'" for vault in sorted(vault_not_found))
            msgs.append(
                f"Vault not found: {names}. "
                "Run `op vault list` to verify the name and check your OP_ACCOUNT."
            )
        if other:
            msgs.append("Failed to resolve references:\n" + "\n".join(other))
        return "\n".join(msgs)
