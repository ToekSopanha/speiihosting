# SpeiiHosting (`speiihos`)

A Python CLI for hosting static websites, dynamic web apps, local APIs and outbound bots on Windows, macOS and Linux. Public sites use a private Nginx instance and Cloudflare Tunnels for HTTPS without router port forwarding.

Version 0.2 adds explicit API exposure, separate hosting credentials, application health checks, recoverable deployments, complete offline rollback releases, project manifests and optional rootless containers.

See [what changed and migration steps](documentation.md#what-changed-in-020) for the full implementation record, user-visible defaults and verification limits. The [plan](plan.txt) records completed work and remaining release verification.

## Install

Requires Python 3.10+. From this checkout:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
# Windows: .venv\Scripts\python -m pip install .
```

Activate that environment before using `speiihos`, or call `.venv/bin/speiihos` directly. Alternative installers are `npm install -g .`, `sh scripts/install.sh`, and `powershell -File scripts/install.ps1`. The npm launcher requires Python and creates a private environment when needed; the standalone scripts can install Python through the platform package manager.

Nginx, cloudflared and a Cloudflare domain are needed only for public hosting. Registry publication and hosted installer URLs are separate release tasks.

## Host a project

```sh
# Static website: build first, then publish dist/build/out/public or index.html
cd ~/projects/portfolio
speiihos host-front --subdomain portfolio --dir dist

# Dynamic SSR application (host-app is an alias)
cd ~/projects/next-app
speiihos host-dynamic --subdomain app --port 3000

# Private API: no domain, Nginx or Cloudflare setup required
cd ~/projects/api
speiihos host-back --port 8000 --health-path /health --health-status 200

# Outbound bot: no domain or port required
cd ~/projects/bot
speiihos host-bot
```

For public hosting, run `speiihos init` first. Setup can install Nginx/cloudflared, configure a Cloudflare API token or browser login, and register user startup. New installations use **127.0.0.1:8080**; choose another port with `init --nginx-port`. Existing configured ports remain unchanged during migration. System Nginx configuration is left alone.

An API token needs Account Cloudflare Tunnel Edit, Zone Read and DNS Edit; cache purging additionally needs Cache Purge. Enter it through the hidden prompt or `CLOUDFLARE_API_TOKEN`. Apps and build commands do not inherit that token. `--no-install` and `--no-autostart` skip setup actions.

Detection supports Next.js, Nuxt, Django, Flask, FastAPI, Laravel and conventional Python/Node entrypoints. Use `--run` or `--build` for other layouts. Native custom applications must honor `HOST=127.0.0.1` and `PORT`. `--auto-port` selects the next available port; use `$PORT` in POSIX commands or `%PORT%` on Windows. `host-back --existing --port 8000` registers an independently managed listener without taking ownership of its process.

## Keep APIs private until explicitly linked

New services never auto-link to a frontend. Expose a route deliberately:

```sh
speiihos link portfolio api --prefix /api
# Or supply --backend api on host-front/host-dynamic,
# or --frontend portfolio on host-back.
speiihos unlink portfolio
```

`https://portfolio.example.com/api/users` then reaches `http://127.0.0.1:8000/users`. This strips the prefix and shares the frontend's origin. The route is publicly reachable: implement application authorization, and use Cloudflare Access for private dashboards. Stopping the linked backend makes its API route return 503. A polling bot remains outbound; `host-bot --webhook --port 8443 --subdomain hooks` explicitly enables public webhook routing.

## Save project settings and preview changes

```sh
speiihos project init --type backend
speiihos project validate
speiihos host-back --dry-run --json
speiihos host-back
```

A project file can contain:

```toml
schema_version = 1
type = "backend"
name = "api"
port = 8000
env_allow = ["APP_REGION"]
strict_dependencies = false

[health]
path = "/health"
expected_status = 200
expected_body = "ok"
timeout = 2
interval = 5
failures = 3
startup_timeout = 30
```

CLI options override explicitly supplied manifest values. `--config path.toml` selects another manifest. Previews show commands, requested ports, routes, health and isolation without installing packages, starting processes or creating hosting state. Availability and disk checks run when applying the command. Use `--non-interactive` before the subcommand for scripted setup; API-token setup then requires no prompts and needs `--domain` when several zones are available.

## Deploy, inspect and recover

```sh
speiihos deploy --dry-run --json
speiihos deploy                    # match the registered source directory
speiihos rollback api              # restore a complete previous release offline
speiihos recover                   # repair an interrupted promotion
speiihos list
speiihos list --json
speiihos inspect api --json
speiihos verify portfolio --json   # explicitly check the public HTTPS URL
speiihos stop 8000
speiihos start api
speiihos restart api
```

Code runs from `~/.speiihosting/sites/<name>/live/`; source edits do not change it. Candidate builds finish before promotion. A durable journal records promotion intent, and interrupted updates are recovered by the supervisor or the next management command. Failed startup/health checks restore the old release. One **complete runnable previous release**, including its installed dependencies, is retained. Rollback performs no package installation or build.

Runtime settings explicitly present in the default project manifest are refreshed on deploy. Registered names, ports and public routes remain explicit management choices. Fixed-port application restarts have a brief interruption; literal zero downtime is not guaranteed.

Keep uploads/databases in `SPEII_DATA_DIR`, which points to `sites/<name>/data` for native processes and `/data` in containers. This directory survives deploy, rollback, backup cleanup and normal removal. `remove api --purge-data` explicitly deletes it; `--reuse-data` attaches saved data when rehosting the same name. Database migrations and other external side effects are not rolled back.

The per-site release budget defaults to 4096 MiB and includes candidate/live/previous/environment files. Persistent data and Podman image storage have separate lifecycles. Change it with `config set release_budget_mb 8192`. Low free space or an exceeded budget prevents promotion.

Status separates process startup, application health, tunnel connection and explicit public URL verification. Without a custom health check, newly managed HTTP services accept a non-5xx response at `/` as basic HTTP readiness; configure a meaningful path/status/body for application health. Background checks restart repeatedly unhealthy managed apps. `inspect` includes current metrics, restart counts, routes, disk usage and recovery state.

## Application isolation and credentials

Native mode runs **trusted code under the current OS user**. Environment allowlisting and virtual environments do not isolate that user's filesystem. Shell variables are inherited only through a small platform allowlist or explicit `env_allow`; the app's own `.env` is loaded without shell evaluation. Hosting credential variables are reserved. Native process-tree memory limits are supervised on a best-effort basis; CPU/PID limits require the container adapter.

For stronger isolation, Linux with rootless Podman and delegated cgroup v2 CPU/memory/PID controllers can use:

```sh
speiihos host-back --port 8000 --isolation podman \
  --image 'registry.example.com/app@sha256:<your-64-digit-digest>' \
  --memory-mb 512 --cpus 1 --pids 128
```

Use a prebuilt image with its runtime/dependencies already installed. The adapter mounts the staged project at `/app` read-only, persistent data at `/data`, drops capabilities, prevents privilege escalation and gives the container a bounded writable `/tmp`. Image dependencies must remain available outside the mounted `/app` tree. Image mode skips host dependency installs/builds; applications listen on `0.0.0.0` inside the container while only loopback ports are published on the host. App secrets are passed through a private env file, without placing values in process arguments or the Podman client's environment. Container values must be single-line; store multiline certificates in an app data file.

Hosting credentials live in private `credentials.json`, separately from `config.json`. Optional OS credential storage:

```sh
python -m pip install '.[secrets]'
speiihos config set credential_store keyring
```

A supported secure OS keyring must be available and unlockable; plaintext fallback keyrings are rejected. The private-file provider remains suitable for headless setups. Containers retain outbound networking; internal APIs still need authorization. Native Podman/keyring integration must be verified on the target system.

## Logs, maintenance and migration

```sh
speiihos logs api -n 500
speiihos logs api --build      # separate dependency/build output
speiihos logs api -f
speiihos logs nginx -f
speiihos logs speii-daemon
speiihos logs size
speiihos logs clear --all
speiihos clean api
speiihos clean --all
speiihos remove api
speiihos migrate
```

Application and build logs are separate streams, each rotating at 5,000,000 bytes with one backup. Nginx logs may briefly exceed that threshold between supervisor checks. `clean` removes the previous release, never persistent data. Version 1 state is read compatibly; `migrate` persists schema version 2 and moves legacy tokens out of general configuration. Existing recorded links are preserved: inspect them and use `unlink` to remove any unwanted public mapping.

Autostart uses macOS LaunchAgents, Linux systemd user services and Windows logon tasks. Linux boot before login requires separately enabling lingering. Sleep prevention defaults off; `config set sleep_prevent on` enables platform-specific controls. macOS `caffeinate` does not guarantee closed-lid operation. Startup/power changes need target-machine verification. Browser-authenticated tunnels support hosting but require dashboard DNS cleanup and API-token authentication for cache purging.

## Development and verification

```sh
uv sync --locked --all-extras
uv run --locked python -m pytest -q
uv run --locked ruff check src tests
uv run --locked ruff format --check src tests
uv run --locked python -m build
uv run --locked pip-audit --strict --require-hashes -r requirements-dev.lock
npm test
npm pack --dry-run
```

`uv.lock` and `requirements-dev.lock` record pinned versions and hashes. Applications may opt into `strict_dependencies = true`: Node then requires package-lock.json; Python requires a complete pinned/hash-checked requirements.lock or requirements.txt, including its server runtime. Package download caches are reused; writable installed dependency directories are never shared across distinct releases.

CI runs several Python versions across Windows/macOS/Linux, uses actions pinned by commit SHA and audits dependencies. Direct executable downloads use the versioned checksums in `binaries.json` and fail closed on missing or mismatched hashes. The real Nginx test runs with Nginx on PATH or `SPEII_TEST_NGINX`. Cloudflare and container contract tests use mocks; they do not prove live account connectivity or native container enforcement.

The CI startup follow-up uses concurrent test HTTP servers without reverse DNS, allows more startup time on hosted runners, and prints bounded runtime/service logs when a test fails. HTTP readiness uses the HTTP response directly; timeout messages include the last process and health status. See the [CI startup notes](documentation.md#ci-startup-follow-up-2026-10-20) for validation and remaining remote checks.

The Windows follow-up preserves complete log lines and UTF-8 characters across pipe reads. For local Node dependencies on Windows, use packaged .tgz files inside the source project or registry packages, with the corresponding lockfile, to keep releases independent of directory links. See [Windows logging and local dependencies](documentation.md#windows-logging-and-local-node-dependencies-2026-10-20).

See [documentation.md](documentation.md) for architecture, recovery details and operational limits; [plan.txt](plan.txt) records the revised implementation plan. MIT license.
