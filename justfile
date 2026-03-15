set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

venv := ".venv/bin"

default:
    @just --list

install:
    poetry sync --with dev
    {{venv}}/pre-commit install --hook-type pre-commit

build-ui:
    cd ui && npm ci && npm run build

verify-embedded-ui:
    just build-ui
    git diff --quiet -- src/ai_sync/web/static ui/package-lock.json || { echo "Embedded UI assets are stale. Run \`just build-ui\` and commit the changes before releasing." >&2; git diff -- src/ai_sync/web/static ui/package-lock.json; exit 1; }

ui-dev:
    @printf '%s\n' \
      'Run the web UI in two terminals for full hot reload:' \
      '  just ui-dev-api' \
      '  just ui-dev-web'

ui-dev-api host="127.0.0.1" port="8321":
    {{venv}}/uvicorn ai_sync.web.dev:create_dev_app --factory --reload --host {{host}} --port {{port}}

ui-dev-web host="127.0.0.1" port="5173":
    cd ui && npm install && npm run dev -- --host {{host}} --port {{port}}

build-ui-watch:
    cd ui && npm install && npm run build:watch

ui-typecheck:
    cd ui && npm install && npm run typecheck

ui-typecheck-watch:
    cd ui && npm install && npm run typecheck:watch

lock:
    poetry lock

test:
    {{venv}}/pytest

typecheck:
    {{venv}}/pyright

lint:
    {{venv}}/ruff check src/

fix:
    {{venv}}/ruff check --fix src/

release version:
    ./scripts/release_checks.sh {{version}}
    just verify-embedded-ui
    poetry lock
    poetry version {{version}}
    just install
    just test
    git add pyproject.toml poetry.lock
    git commit -m "release: v{{version}}"
    git tag -a v{{version}} -m "v{{version}}"
    git push --follow-tags
