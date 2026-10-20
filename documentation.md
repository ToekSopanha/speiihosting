# SpeiiHosting 0.2 operating manual

## What changed in 0.2.0

Implementation record dated 2026-10-20. These features are implemented in this checkout; registry publication remains a separate release step.

| Area | Added or updated | Benefit for users |
| --- | --- | --- |
| API exposure | New backends stay private until explicitly linked; `unlink` and route inspection are available. | Users choose which APIs become public. |
| Credentials and environments | Hosting credentials are stored separately from settings, with an optional secure OS keyring; app/build environments exclude hosting tokens. | Reduces accidental credential exposure. |
| Health and status | Configurable HTTP checks, ongoing monitoring, restart thresholds and explicit public HTTPS verification. | Reports application readiness and helps recover unhealthy managed services. |
| Deployment recovery | Durable promotion journals, automatic recovery and one complete previous release with dependencies. | Interrupted deployments can recover; rollback needs no package downloads or rebuild. |
| Persistent storage | A separate application data directory and a configurable release disk budget. | Deployments retain uploads/databases and bound release storage. |
| CLI usability | Validated `speiihosting.toml`, `project init`/`validate`, dry-run previews, JSON output, `inspect`, `recover`, `migrate` and `verify`. | Makes setup repeatable and planned changes easier to review. |
| Performance | Cached configuration, less frequent metrics writes, upstream keepalive, conservative asset caching and streaming support. | Reduces repeated work while keeping HTML fresh and streams usable. |
| Runtime isolation | Optional Linux rootless Podman adapter with pinned images and CPU/memory/PID limits. | Provides stronger isolation than native processes for compatible projects. |
| Logs and dependencies | Separate build logs, strict dependency installation, locked development dependencies, checksum-verified binaries and hardened CI configuration. | Makes troubleshooting and dependency changes easier to review. |

### Existing installation migration

1. Run `speiihos migrate` to persist version 2 state and move hosting credentials out of general settings.
2. Review each site's public routes with `speiihos inspect NAME`; existing recorded links are preserved. Use `speiihos unlink FRONTEND` to remove an unwanted API mapping.
3. Store writable uploads/databases in `SPEII_DATA_DIR` (or `/data` with Podman). Existing application files are not automatically moved into persistent storage.
4. Configure a meaningful health endpoint in the project manifest or hosting options, then use `speiihos verify NAME` when public HTTPS should be checked.

New installations default to loopback Nginx port **8080**. Migration preserves an existing configured port. Native apps still share their OS user's file permissions; the optional container adapter requires an appropriate Linux runtime.

Recorded implementation validation: **78 tests passed**, including real temporary Nginx and native process workflows; lint, formatting, Python/npm packaging and the hashed dependency audit passed. The audit reported no known vulnerabilities in the checked dependency set. The pinned cloudflared download passed checksum and CLI flag checks without connecting an account. Live Cloudflare account/DNS operations, Podman resource enforcement, secure OS keyring integration, OS startup/power behavior and remote CI execution still require their target environments. See [Verification and release limits](#verification-and-release-limits).

## Contract and trust model

The version 2 amendment at the top of plan.txt supersedes the historical version 1 plan. The CLI supports frontend, dynamic, backend and bot services across Windows/macOS/Linux. Optional rootless Podman isolation currently targets Linux with cgroup v2; native process mode remains available for trusted projects on every platform.

A native application and the supervisor use the same OS account. A compromised native app can therefore access files permitted to that account. Detached processes, Python virtual environments, environment allowlists and directory permissions do not create a separate filesystem identity. Stronger isolation uses the Podman adapter or an independently administered OS account. Public `/api` routes still require authorization, including when their backend listens only on loopback. Cloudflare Access can protect private administrative applications.

## Setup, installation and supply chain

Install from source with pip, the npm launcher, or scripts/install.sh / install.ps1. The npm bundle includes the Python source and pinned binary manifest; the first invocation creates a private CLI environment if needed. Publishing registries and installer domains is a separate release activity.

`init` can install Nginx/cloudflared and configure either an API-token-managed tunnel or browser-authenticated local tunnel. New configurations use nginx_port=8080, autostart=true and sleep_prevent=false. Existing nginx_port values remain unchanged on migration. Setup uses a hidden API-token prompt or CLOUDFLARE_API_TOKEN. Noninteractive setup requires a token and an explicit domain when more than one zone is available.

Prefer OS package managers for system dependencies. Direct downloads use only pinned URLs and reviewed SHA-256 checksums in src/speiihosting/binaries.json. Missing platform entries or digests fail with an actionable package-manager alternative. A download is bounded to 128 MiB and checked before installation; unpacked archives are bounded and traversal paths rejected. Hashes protect integrity relative to the checked-in manifest; they do not establish that arbitrary publisher code is safe. Updating the manifest requires a reviewed release change.

Cloudflare token permissions are Account Cloudflare Tunnel Edit, Zone Read and DNS Edit, plus Cache Purge for cache invalidation. Scope tokens to the relevant account/zones and rotate them when exposure is suspected. Browser login cannot automatically delete DNS through the API or purge caches; use the dashboard or switch to token setup.

The repository has a universal uv.lock and a hashed requirements-dev.lock export. CI installs with `uv sync --locked --all-extras`, checks formatting/tests/builds and audits the pinned list. External GitHub Actions are pinned to full commit SHAs, workflow permissions are read-only, and Dependabot proposes uv/action updates. GitHub Actions cannot be tested end-to-end until the workflow runs remotely.

## State, migrations and credentials

`SPEIIHOSTING_HOME` defaults to ~/.speiihosting (also %USERPROFILE% on Windows).

```text
config.json                      version 2 public settings; no hosting tokens
credentials.json                 private file-backed hosting credentials
services.json                    versioned desired state and runner definitions
registry.json                    derived port index
runtime.json                     disposable observed status/metrics
state.lock / daemon.lock         OS-backed locks
bin/                             private dependency executables
nginx/nginx.conf                  private main configuration
nginx/speiihosting.d/             enabled and disabled per-site files
tunnel.yml                       JSON-compatible YAML tunnel ingress
pids/                            PID/creation-time/generation records
sites/<name>/live/               current immutable-by-workflow release
sites/<name>/previous/           complete runnable previous release
sites/<name>/previous.json       previous runtime metadata
sites/<name>/candidate/          prepared deployment candidate
sites/<name>/transaction.json    durable promotion/recovery journal
sites/<name>/environments/       referenced Python environments
sites/<name>/data/               persistent writable application data
logs/                            separate bounded worker/build/infrastructure logs
```

Settings and service models reject unknown fields/unsupported future versions. Version 1 files are upgraded in memory; `migrate` persists version 2 and separates credentials. Existing recorded API mappings remain intact because their original intent cannot be inferred; review with inspect and remove unwanted mappings with unlink. General configuration output redacts in-memory tokens, and saved config.json contains none.

The file credential backend uses the private root (POSIX 0700) and files (0600). Optional `credential_store=keyring` requires the secrets extra and a supported secure native keyring; plaintext or unavailable providers fail rather than silently weakening storage. Headless environments should keep the private-file provider when a keyring cannot unlock. Switching to keyring saves credentials and publishes the new provider before deleting the old file copy.

Critical writes use temporary files, file fsync, replacement, and a parent-directory fsync on POSIX. Disposable metrics use replacement without fsync. Configuration reads are cached by modification time, size and inode. services.json is authoritative; registry.json is derived. CLI mutations are serialized by an OS lock; runtime state is written independently by the supervisor.

## Project manifests and command semantics

`project init --type frontend|dynamic|backend|bot` generates speiihosting.toml. Existing files require --force to replace. `project validate` checks schema and sensitive names. The manifest supports name, type, subdomain/domain, port, dir, run/build, explicit backend/frontend links, install/auto_port/existing flags, webhook mode, env_allow, health, resources, streaming, strict_dependencies, isolation, image and reuse_data. Schema version is 1 for project files and 2 for persistent global/service state.

CLI flags override only values actually supplied. The --config option selects an alternate manifest. Deploy refreshes explicitly recorded runtime settings from the source's default manifest; service identity, ports and published routes remain registered management decisions. Use link/unlink to change API mappings.

Hosting commands support --dry-run and --json. Deploy and rollback also preview without mutating hosting state. A preview lists commands, intended builds/installations, requested ports, public routes, isolation and health. It does not claim that a port is free, an image is present, a dependency is installed or a public URL is reachable. Those checks occur when applying the command. `--non-interactive` before the subcommand prevents setup/config prompts. JSON is supported by host/deploy/rollback/list/inspect/recover/migrate/verify and by the global output option for structured commands.

Names, DNS labels/domains, API prefixes, ports, health paths, environment allowlists and pinned image references are validated. Source staging rejects escaping links and directory symlinks. Source control, caches, preexisting node_modules and virtual environments are excluded from source copies; dependencies needed by the candidate are installed independently. Complete previous releases retain their installed dependencies.

## Environments, secrets and builds

The supervisor inherits only a platform environment allowlist. Apps inherit that minimal environment plus explicit env_allow variables and their own .env, parsed without interpolation or shell execution. Hosting API/tunnel variables and SPEIIHOSTING_* names are reserved and are never injected into apps or build commands. Other shell credentials, preload flags, SSH agent sockets and Python paths are absent unless explicitly permitted as app inputs.

Native apps receive loopback HOST/HOSTNAME/NITRO_HOST, selected PORT/NITRO_PORT, PYTHONUNBUFFERED and SPEII_DATA_DIR. Custom applications must honor those values; the tool cannot rewrite a hard-coded listener. A project's own code can still print its secrets, so application logging must avoid credential output.

Node installation uses npm ci when package-lock.json exists and npm install otherwise. In strict mode a lockfile is required. Python uses requirements.lock when present, then requirements.txt, or a pyproject installation. Strict Python mode requires a complete pinned requirements file with hashes and uses pip --require-hashes --only-binary=:all:. Detected ASGI/WSGI server dependencies must already be included in that lock; strict mode does not add unpinned extras. Ordinary mode can install detected server runtimes. Python environments are kept at stable paths outside release directories and cleaned only when neither live nor previous metadata references them.

Next.js/Nuxt and generic dynamic Node build scripts run in the candidate when present. Static initial hosting publishes an existing build; later frontend deploys can rebuild in an isolated workspace. --run and --build are explicit shell commands and execute with the current user's authority in native mode. Trust their source and dependencies.

## Runtime adapters and resource controls

The native adapter runs detached subprocesses with independently drained output and PID creation-time checks. Hosting app processes as root is rejected. It provides a best-effort process-tree RSS ceiling; CPU and PID controls are reported as unenforced in inspect. Builds have a finite timeout. Native mode is intended for trusted projects.

The optional Podman adapter requires a non-root runtime, cgroup v2 and delegated CPU/memory/PID controllers. Images must be prebuilt and referenced by an immutable sha256 digest. It sets a non-root user with keep-id mapping, a read-only root filesystem, no capabilities, no-new-privileges, an init process, bounded tmpfs, memory/CPU/PID limits and loopback-only published ports. Only that service's staged project and data directory are mounted; hosting credentials, runtime sockets and the user's home are not mounted.

The image supplies its runtime/dependencies; host installs/builds are skipped. `/app` is a read-only code mount and `/data` is writable persistent storage. Image dependencies must remain available outside the mounted source tree. Application host/port variables use 0.0.0.0 inside the container. Secrets go through a private env file outside the code mount, never command argument values or the Podman client's environment. Multiline values require a separate data file. Container ownership labels and generation records are checked before cleanup. Outbound networking remains available; enforce API authorization and any required egress restrictions independently.

Contract tests verify the generated restrictions and rejection of rootful/unsupported configurations. Live container isolation/resource enforcement requires a Linux Podman environment and has not been established by mocked tests. It is not a multi-tenant security certification.

## Health, supervision and status

The daemon reconciles processes roughly every 250 ms. Configuration is cached; disposable metrics normally publish every two seconds or immediately on lifecycle transitions. `metrics_interval` is configurable between 1 and 60 seconds. Independent process trees and bounded health probes keep worker failures separate. Infrastructure failures are recorded without preventing unrelated native workers from being supervised.

HTTP health supports a local path, expected status, optional expected response substring, per-request timeout, interval, consecutive-failure threshold and startup timeout. Responses are bounded, redirects disabled and inherited proxy settings ignored. Without an explicit health configuration, newly managed HTTP services use a basic non-5xx response at `/`; configure a meaningful endpoint to validate application dependencies. Bots without a port use process startup checks.

A new app must stay running for at least one second and pass its readiness check before promotion commits. Failed candidates restore the original release. Ongoing health failures trigger restart of the managed app after the configured threshold; externally managed listeners are observed without being killed. Worker exits use exponential delay capped at ten seconds; more than five exits in sixty seconds stops the crash loop. Restart/start changes the generation and clears that worker's crash state.

`list` displays health, restart count, CPU and memory. Native metrics cover the process tree; container payload usage should be checked with podman stats (the local process snapshot covers its client). `inspect` adds routes, configured/enforced limits, disk use, data path, errors and pending recovery. Process startup, local health, cloudflared process startup, tunnel connection (cloudflared's connection PID file) and public HTTPS verification are distinct stages. `verify name` performs an explicit public request and records its result/time; deployments and lifecycle changes invalidate the verified flag. Access-protected sites may require external authenticated validation.

`service stop` preserves desired running states for service start. Closing a CLI terminal does not close managed output pipes or application sessions. Startup restores user-session services through LaunchAgents, systemd user units or Windows logon tasks; Linux before-login startup requires lingering. Native startup/power behavior still needs verification on each target OS.

## Nginx routing and caching

The private Nginx instance uses explicit -p/-c paths, binds loopback and shares one port across server_name vhosts. Unknown hosts return 404. New APIs have no public mapping until an explicit link. `/api/users` becomes `/users` at the backend. Stopping a backend returns 503 on its linked route. A bot gets public routing only in explicit webhook mode.

Changes are validated with nginx -t before reload and restore the previous managed files on failure. Stopped vhosts use .conf.disabled. Dotfiles are denied. HTTP settings disable server version output, bound request-body size/timeouts, enable sendfile/gzip, set nosniff/referrer headers and use upstream keepalive. WebSocket upgrade headers remain supported; streaming=true disables proxy buffering for SSE/streaming routes. API/application responses are not cached by a proxy cache.

HTML/SPA routes revalidate with no-cache. Common assets under assets/static get a short cache. Hexadecimal fingerprinted filenames get a one-year immutable cache; Next.js's versioned static namespace retains immutable caching. Conservative filename detection can leave other build hash formats on shorter caching. Missing assets return 404, not index.html.

Cloudflare API mode creates proxied CNAMEs without overwriting unrelated records. Matching reused records are not owned and are not deleted. Ingress retains unrelated hostnames and ends with a catch-all 404. Removing an owned record checks its current target first. DNS/API operations remain external side effects; a network failure or power loss between remote creation and saving its record ID can require dashboard reconciliation. The local filesystem journal does not claim a transaction across Cloudflare and the disk.

## Deployment state machine and storage

A deployment prepares a candidate and its dependencies/build output without changing live. It checks a per-site release/environment budget (default 4096 MiB) and at least 128 MiB free space before promotion. Data files and external container image storage are outside that release budget.

The journal records old desired state, the new runtime, prior metadata and whether live/previous existed. Its phases are:

1. prepared: candidate is ready; live is still original.
2. promoting: intent is durable before pausing and directory changes.
3. committed: new desired state, health and previous metadata are durable; obsolete backup cleanup may finish later.

During promotion, previous moves to .obsolete, live moves to previous, and candidate becomes live. Failures restore old files and runner state. A pending uncommitted journal is recovered on the next supervisor or management pass; a committed journal only finishes cleanup. Recovery is idempotent across interrupted restoration. Unknown/corrupt journals preserve evidence and quarantine affected processes; failures are shown as recovery_required. Public routing is disabled for affected sites when safely possible, and paused if safe quarantine cannot be validated. Other workers continue.

One complete previous release is retained. Rollback copies it as a candidate and reuses its recorded runner/environment; it does not call package registries or build commands. During a promotion the candidate/obsolete directories can temporarily increase disk use, so budget for staging as well as two retained releases. `clean` removes previous and unreferenced environments after pending recovery has been processed.

Fixed-port apps are stopped before the directory switch and restarted afterward. Brief interruptions are expected. Renames are recoverable steps, not a universal atomic directory exchange. Filesystem loss, unreadable original releases and external side effects can still require manual intervention. Journals remain when recovery cannot finish.

`SPEII_DATA_DIR` is the app's persistent upload/database location. It survives deployment, rollback and normal remove. Normal removal cleans releases/environments/logs while retaining nonempty data; --purge-data explicitly deletes it. Rehosting retained data requires --reuse-data. Database migrations and remote operations need their own backup/rollback plan.

## Logs and daily maintenance

Use logs name -n 500, logs name -f, logs name --build, logs nginx -f and logs speii-daemon. Builds use their own rotating file so concurrent deployment output cannot compete with the live process's rotation handler. `logs size` reports exact file sizes/line counts. Clear with logs clear name or logs clear --all; truncation preserves existing file descriptors. Application handlers rotate at 5,000,000 bytes with one backup. Output is consumed in bounded chunks. Nginx logs are periodically rotated, so brief overshoot is possible.

Configuration commands support domain, nginx_port, autostart, sleep_prevent, metrics_interval, release_budget_mb and credential_store. Sleep prevention is off by default. Linux writes a dedicated logind drop-in effective after reload/reboot; Windows saves/restores the AC lid policy; macOS runs caffeinate, with hardware-specific closed-lid limits. No laptop hardware/thermal or network availability guarantee is implied.

## Verification and release limits

Tests cover secret filtering in real child/build processes, credential migration, previews without side effects, schemas, caching/fsync policy, explicit API exposure, dependency retention, each promotion boundary, recovery retry, HTTP health failure/auto-restart, offline rollback, persistent data, isolation contracts, Nginx validation/routing and package behavior. Real Nginx runs when Nginx is on PATH or SPEII_TEST_NGINX is set.

Cloudflare calls, keyring failure modes and container ownership/restrictions can be tested with mocks. Account authentication/public DNS, native Podman cgroups/keyrings, startup/power changes and remote GitHub Actions require their respective target environments. CI configuration and a passing local suite are not evidence those external integrations have run.

References: [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/), [Nginx upstream keepalive](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#keepalive), [pip secure installs](https://pip.pypa.io/en/stable/topics/secure-installs/), [Podman run](https://docs.podman.io/en/stable/markdown/podman-run.1.html), [GitHub Actions security](https://docs.github.com/en/actions/reference/security/secure-use).
