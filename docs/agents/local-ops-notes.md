# Local Ops Notes (deployment, config, session files)

> audience: developers running the stack locally
> status: current
> canonical-path: `docs/agents/local-ops-notes.md`

## Deployment

Nginx is the single public entry: it proxies `/api/*` to the Gateway (rewriting `/api/langgraph/*` onto the Gateway's native routes) and serves the frontend, compressing HTML and configured textual assets while deliberately leaving SSE, fonts, images, audio, and video uncompressed at the proxy layer. The main compose file publishes that entry as `"${BIND_HOST:-127.0.0.1}:${PORT:-2026}:2026"` — **loopback by default**; a bare `"${PORT}:2026"` binds `0.0.0.0`, which does not. Nginx listening `default_server` on IPv4+IPv6 and the Gateway binding `0.0.0.0:8001` are container-internal on purpose: the published nginx port is the entire external surface, so any new published port needs an explicit bind address.

## Security & configuration

Do not commit local secrets. Start from `config.example.yaml`, `.env.example`, or `extensions_config.example.json`, then keep local values in untracked config files. Use `make doctor` to validate configuration and system requirements before reporting environment issues. For production-mode local startup, `scripts/start-local.sh` validates required commands, `config.yaml`, and configured model-key environment variable names before invoking `make start`; `START_TARGET` and `REQUIRED_ENV_VARS` accept only simple targets and identifiers.

## Session / working files (dev-log)

Developer session artifacts (`task_plan.md`, `progress.md`, `findings.md`, and any scratch notes produced during a working session) must live in `dev-log/`, not the repo root. `dev-log/`, coverage outputs, qodo cover config, `pr-build/`, `.opencode/`, `.agents/`, and `.mimocode/` are git-ignored and guarded by a pre-commit hook — never `git add -f` them, and delete them when the session ends.
