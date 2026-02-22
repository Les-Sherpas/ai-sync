# AI Research Doc

A single canonical repository for AI agent configuration across **Codex**, **Cursor**, and **Gemini CLI**. Define agents, skills, MCP servers, and client settings once; sync them to every client with one command.

## Overview

This repo provides:

- **Agents** – Sub-agents derived from prompts with per-client metadata
- **Skills** – Agent Skills (SKILL.md) mirrored to all clients
- **MCP servers** – Model Context Protocol servers with centralized config and secrets
- **Client configuration** – Generic settings (subagents, mode) derived into client-specific configs
- **OAuth token portability** – Manual copy of client OAuth caches across machines (automated capture/restore planned)

All syncing is **idempotent**: identical targets cause no writes; changed targets are backed up (`tar.gz`) before overwrite.

---

## Quick start

```bash
pip install -r scripts/requirements.txt
sync-ai-configs
```

### Auto-sync (LaunchAgent + notifications)

Use the installer to set up a LaunchAgent that watches changes and syncs automatically with notifications:

```bash
./scripts/auto-sync/install_auto_sync.sh --op-account NAME
```

Requires `--op-account` (or `OP_ACCOUNT` env). Notes:
- Creates a venv at `scripts/.venv/` and runs syncs inside it.
- Enforces the repo-owned `scripts/.client-versions.json` (major/minor must match installed clients).
- Auto-sync is blocked and a notification is shown if client major/minor versions differ.

### Prerequisites

- Python 3.10+
- [Codex](https://developers.openai.com/codex), [Cursor](https://cursor.com), and/or [Gemini CLI](https://geminicli.com) installed
- For MCP stdio servers: Node.js (`npx`), [uv](https://docs.astral.sh/uv/) (`uvx` for workspace-mcp), `pip install mcp-server-fetch` for fetch

---

## Repository structure

```
.
├── config/
│   ├── prompts/               # Agent prompts (source of truth)
│   ├── senior_software_engineer.md
│   ├── senior_software_engineer.metadata.yaml
│   └── ...
│   ├── skills/                # Agent Skills
│   │   ├── create-skill/
│   │   │   └── SKILL.md
│   │   └── ...
│   ├── mcp-servers/
│   │   ├── servers.example.yaml  # Template – copy to servers.yaml
│   │   └── servers.yaml         # Gitignored – your MCP manifest
│   └── client-settings/
│       ├── settings.example.yaml  # Template (tracked)
│       └── settings.yaml          # Local overrides (gitignored; copy from example)
├── scripts/
│   ├── auto-sync/             # LaunchAgent + notifications
│   │   ├── install_auto_sync.sh
│   │   ├── watch_sync.py
│   │   ├── run_sync_once.sh
│   │   └── notify_sync.sh
│   ├── client-sync/           # Python: sync-ai-configs
│   │   ├── pyproject.toml
│   │   ├── sync_ai_configs/
│   │   ├── tests/
│   │   └── ...
│   └── shared/                # Shared helpers (summaries)
│       └── sync_summary.py
├── scripts/requirements.txt
├── scripts/.client-versions.json
├── scripts/.venv/
├── .env.tpl                     # MCP secrets (op:// refs resolved via 1Password)
└── .sync_backups/               # Tar.gz backups before overwrite
```

---

## Sync script

### Usage

```bash
sync-ai-configs
```

Run from the **repository root** so the script finds `config/prompts/`, `config/skills/`, `config/mcp-servers/`, `config/client-settings/`.

### Options

| Option | Description |
|--------|--------------|
| (none) | Full sync: agents → skills → MCP servers → client config |
| `--force` | Update `scripts/.client-versions.json` with local client versions, then sync |
| `--no-interactive` | Skip interactive prompts |
| `--plain` | Plain output (implies `--no-interactive`) |
| `--override` / `--override-json` | Override manifest leaf values (e.g. `/servers/context7/enabled=false`) |
| `--op-account` | 1Password account name for desktop auth (install export in shell rc) |

### Sync order

1. **Agents** – From `config/prompts/*.md` → `~/.codex/agents/`, `~/.cursor/agents/`, `~/.gemini/agents/`
2. **Skills** – From `config/skills/*/` → `~/.codex/skills/`, `~/.cursor/skills/`, `~/.gemini/skills/`
3. **MCP servers** – From `config/mcp-servers/servers.yaml` → client MCP configs, MCP instructions
4. **Client config** – From `config/client-settings/settings.yaml` → approval policy, sandbox, features

### Sync strategy

- **Agents, skills, client config**: Files overwritten if they exist. Untracked agents/skills (not in config/prompts/ or config/skills/) are left alone.
- **Client config**: Deep-merge with existing; ai-tools keys overwrite on conflict.
- **MCP servers**: Merged with existing; managed servers updated, user-added servers preserved.

---

## Agents

### Source structure

Each agent lives in `config/prompts/`:

```
config/prompts/
├── <agent_name>.md           # Prompt content (required)
└── <agent_name>.metadata.yaml   # Optional metadata
```

### Metadata schema (`config/prompts/<name>.metadata.yaml`)

Metadata is **generic** (client-agnostic). The sync script adapts it per client.

| Key | Description | Default |
|-----|-------------|---------|
| `slug` | Agent ID (kebab-case) | Derived from filename |
| `name` | Display name | From filename |
| `description` | Short description | Extracted from prompt |

Untracked agents (in client but not in `config/prompts/`) are left alone.

### Target layout per client

| Client | Target |
|--------|--------|
| Codex | `~/.codex/agents/<slug>/prompt.md` + `config.toml` |
| Cursor | `~/.cursor/agents/<slug>.md` (frontmatter) |
| Gemini | `~/.gemini/agents/<slug>.md` (frontmatter) |

---

## Skills

Skills are directories under `config/skills/` with a `SKILL.md` file. The sync script mirrors each skill to all three clients.

### Structure

```
config/skills/
└── <skill-name>/
    ├── SKILL.md          # Required
    ├── reference.md      # Optional
    ├── examples.md       # Optional
    └── scripts/          # Optional; copied if present
```

Paths containing `.venv`, `node_modules`, `__pycache__`, `.git`, or `.DS_Store` are skipped. Untracked skills (in client but not in `config/skills/`) are left alone.

### Targets

- `~/.codex/skills/<skill-name>/`
- `~/.cursor/skills/<skill-name>/`
- `~/.gemini/skills/<skill-name>/`

---

## MCP servers

### Manifest (`config/mcp-servers/servers.yaml`)

```yaml
servers:
  <server_id>:
    method: stdio | http | sse
    command: npx
    args: ["-y", "@modelcontextprotocol/server-xxx"]
    enabled: true
    clients: [codex, cursor, gemini]   # Optional; default: all
    timeout: 60s                       # Optional; startup/tool timeout
    trust: true                        # Optional; Cursor/Gemini: auto-approve tools
```

**STDIO servers** – `command`, `args`; env vars use `"${VAR}"` refs resolved from `.env.tpl`.

**HTTP/SSE servers** – `url`, `httpUrl`; optional `bearer_token_env_var` for Codex.

**HTTP with OAuth** – `httpUrl` + `oauth.enabled: true`; `clientId`/`clientSecret` from `.env.tpl` via `"${VAR}"`:

```yaml
  google-maps-grounding-lite:
    method: http
    httpUrl: https://mapstools.googleapis.com/mcp
    oauth:
      enabled: true
      clientId: "${GOOGLE_MAPS_GROUNDING_LITE_CLIENT_ID}"
      clientSecret: "${GOOGLE_MAPS_GROUNDING_LITE_CLIENT_SECRET}"
```

### Configured servers

| Server | Method | Description |
|--------|--------|-------------|
| context7 | stdio | Documentation lookup (`@upstash/context7-mcp`) |
| fetch | stdio | URL fetch → markdown (`python -m mcp_server_fetch`) |
| playwright | stdio | Browser control (`@playwright/mcp`) |
| exa | http | Search API |
| google-workspace-perso | stdio | Gmail, Calendar, Drive (personal @gmail.com, separate OAuth) |
| google-workspace-pro | stdio | Gmail, Calendar, Drive (work @sherpas.com, separate OAuth) |
| google-maps-grounding-lite | http | Maps grounding (OAuth) |

### Secrets (`.env.tpl`)

All MCP secrets live in `.env.tpl` at the repo root. Use `op://` references for 1Password:

```
CONTEXT7_API_KEY=op://Private/AI Tools Secrets/CONTEXT7_API_KEY
EXA_API_KEY=op://Private/AI Tools Secrets/EXA_API_KEY
GOOGLE_OAUTH_CLIENT_ID_PERSO=op://Private/AI Tools Secrets/GOOGLE_OAUTH_CLIENT_ID_PERSO
...
```

In `servers.yaml`, reference them with `"${VAR_NAME}"` in each server's `env` or `oauth` block. The sync script resolves these at runtime via 1Password (requires `OP_ACCOUNT` or `OP_SERVICE_ACCOUNT_TOKEN`).

**Requirements**: [1Password CLI](https://developer.1password.com/docs/cli) and either `OP_ACCOUNT` (desktop app) or `OP_SERVICE_ACCOUNT_TOKEN` (service account).

### Client targets

| Client | Target | Strategy |
|--------|--------|----------|
| Codex | `~/.codex/config.toml` `[mcp_servers.<id>]` | Merge |
| Codex | `~/.codex/mcp.env` | Bearer token exports (source before running Codex) |
| Cursor | `~/.cursor/mcp.json` | Overwrite `mcpServers` |
| Gemini | `~/.gemini/settings.json` `mcpServers` | Deep-merge |

### OAuth token portability

OAuth tokens are stored per client (e.g. `~/.gemini/mcp-oauth-tokens.json`). To move them between machines, copy the client token files manually via a secure channel (rsync, 1Password, etc.). Automated capture/restore is planned.

---

## Client configuration

Single YAML definition → derived into Codex, Gemini, and Cursor.

### Schema (`config/client-settings/settings.yaml`)

Copy from `settings.example.yaml`. See that file for full schema.

| Key | Values | Description |
|-----|--------|-------------|
| `subagents` | `true` \| `false` | Enable multi-agents, sub-agents, child-prompts, AGENTS.md |
| `mode` | `ask` \| `ask-once` \| `full-access` | Approval / restriction mode |
| `suppress_unstable_features_warning` | `true` \| `false` | Codex only. Suppress "Under-development features" warning |
| `tools.sandbox` | `true` \| `false` | Gemini only. When false, allow MCP tools filesystem access (uvx, etc.) |

### Mode semantics

| Mode | Meaning |
|------|---------|
| `ask` | Prompt for approval every time before acting |
| `ask-once` | Auto-approve safe ops, prompt for risky ones (where supported) |
| `full-access` | No approval prompts, no restrictions (YOLO) |

### Client mapping (from official docs)

| Generic | Codex | Gemini | Cursor |
|----------|-------|--------|--------|
| **subagents: true** | `features.multi_agent`, `features.child_agents_md` | `experimental.enableAgents` | — |
| **suppress_unstable_features_warning** | `suppress_unstable_features_warning` | — | — |
| **tools.sandbox: false** | — | `tools.sandbox` | — |
| **mode: ask** | `approval_policy=on-request`, `sandbox_mode=workspace-write` | `general.defaultApprovalMode=default` | `permissions: {allow:[], deny:[]}` |
| **mode: ask-once** | `approval_policy=untrusted`, `sandbox_mode=workspace-write` | `general.defaultApprovalMode=auto_edit` | same as `ask` |
| **mode: full-access** | `approval_policy=never`, `sandbox_mode=danger-full-access` | `general.defaultApprovalMode=yolo` | `allow: [Shell(*), Read(*), Write(*), WebFetch(*), Mcp(*:*)]` |

### Client targets

| Client | Target | Strategy |
|--------|--------|----------|
| Codex | `~/.codex/config.toml` | Deep-merge with existing; ai-tools keys overwrite. No backup. |
| Gemini | `~/.gemini/settings.json` | Deep-merge with existing; ai-tools keys overwrite. No backup. |
| Cursor | `~/.cursor/cli-config.json` | Deep-merge with existing; ai-tools keys overwrite. No backup. |

---

## Dependencies

The sync tool lives in `scripts/client-sync/` as a Python project:

```bash
pip install -e scripts/client-sync/
```

Dependencies: `pyyaml>=6.0`, `tomli>=2.0`, `tomli-w>=1.0`, `watchfiles>=0.21`, and others (see `pyproject.toml`).

### Testing

```bash
pip install -e "scripts/client-sync[dev]"
pytest scripts/client-sync/tests/
```

---

## .gitignore

- `config/mcp-servers/servers.yaml` (copy from `servers.example.yaml`)
- `config/client-settings/settings.yaml` (copy from `settings.example.yaml`)
- `knowledge-base/*`
- `.sync_backups/`
- `.env`, Python bytecode, virtual envs, `.pytest_cache/`, `node_modules/`, `.DS_Store`, etc.

---

## Workflow summary

### New machine setup

1. Clone repo
2. `pip install -r scripts/requirements.txt`
3. Copy `config/mcp-servers/servers.example.yaml` to `config/mcp-servers/servers.yaml`
4. Ensure `.env.tpl` has correct 1Password refs; set `OP_ACCOUNT` or `OP_SERVICE_ACCOUNT_TOKEN`
5. Copy `config/client-settings/settings.example.yaml` to `config/client-settings/settings.yaml` and edit if needed
6. `sync-ai-configs`
7. For Codex HTTP MCP servers: `source ~/.codex/mcp.env` in shell profile

### Adding an MCP server

1. Edit `config/mcp-servers/servers.yaml`
2. Add required vars to `.env.tpl` (use `op://` refs for secrets)
3. Run `sync-ai-configs`

### Adding an agent

1. Add `config/prompts/<name>.md`
2. (Optional) Add `config/prompts/<name>.metadata.yaml`
3. Run `sync-ai-configs`

### Adding a skill

1. Create `config/skills/<skill-name>/SKILL.md`
2. Run `sync-ai-configs`

### Changing client mode

1. Edit `config/client-settings/settings.yaml` (`subagents`, `mode`)
2. Run `sync-ai-configs`

---

## References

- [Codex config reference](https://developers.openai.com/codex/config-reference/)
- [Codex security & sandbox](https://developers.openai.com/codex/security)
- [Gemini CLI configuration](https://geminicli.com/docs/reference/configuration)
- [Cursor CLI permissions](https://docs.cursor.com/cli/reference/permissions)
- [Agent Skills standard](https://github.com/anthropics/anthropic-cookbook/blob/main/agent-skills/README.md)
