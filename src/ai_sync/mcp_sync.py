"""MCP sync flow."""

from __future__ import annotations

from collections.abc import Sequence

from ai_sync.clients.base import Client
from ai_sync.display import Display
from ai_sync.state_store import StateStore


def resolve_servers_for_client(servers: dict, client_name: str) -> dict:
    resolved = {}
    for sid, srv in servers.items():
        base = {k: v for k, v in srv.items() if k != "client_overrides"}
        override = (srv.get("client_overrides") or {}).get(client_name, {})
        if override:
            merged = {**base}
            for key, val in override.items():
                # None means "not set by this override", not "clear the value".
                # ClientOverrideConfig fields default to None so every field is
                # always present in the dumped dict; skipping None here gives us
                # exclude_none=True semantics without requiring model_dump().
                if val is None:
                    continue
                if key in ("env", "headers", "auth") and isinstance(val, dict):
                    # Use `or {}` so that an explicit None base value doesn't cause TypeError.
                    merged[key] = {**(base.get(key) or {}), **val}
                elif key == "oauth" and isinstance(val, dict):
                    # Filter None values from the serialized OAuthConfig before
                    # merging so that unset optional fields don't overwrite base.
                    filtered_val = {k: v for k, v in val.items() if v is not None}
                    merged[key] = {**(base.get("oauth") or {}), **filtered_val}
                else:
                    merged[key] = val
            resolved[sid] = merged
        else:
            resolved[sid] = base
    return resolved


def sync_mcp_servers(
    servers: dict,
    clients: Sequence[Client],
    secrets: dict,
    store: StateStore,
    display: Display,
) -> None:
    if not servers:
        display.print("MCP Servers: skipping (no servers)", style="dim")
        return
    display.rule("Syncing MCP Servers")
    sync_errors: list[str] = []
    for client in clients:
        try:
            client_servers = resolve_servers_for_client(servers, client.name)
            client.sync_mcp(client_servers, secrets, store)
        except Exception as exc:
            sync_errors.append(f"{client.name}: {exc}")
            display.print(f"  Warning: MCP sync failed for {client.name}: {exc}", style="warning")
    if sync_errors:
        display.print(f"  {len(sync_errors)} client(s) had MCP sync errors (see above)", style="warning")

    server_ids = list(servers.keys())
    display.table(
        ("Item", "Value"),
        [("Servers", ", ".join(server_ids) if server_ids else "—"), ("Clients", ", ".join(c.name for c in clients))],
    )
