# Changelog

All notable changes to SpeiiHosting will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.3.1] - 2026-10-20

**Major security, reliability, and usability revision**

This release supersedes conflicting behavior from v0.1 architecture. Existing installations should run `speiihos migrate` and review public API routes.

### 🔐 Security Enhancements

#### Added
- **Private-by-default APIs**: New backend services no longer auto-link to frontends
  - Explicit linking required: `speiihos link frontend api --prefix /api`
  - Added `unlink` command to remove public API mappings
  - Inspect shows all current route mappings

- **Credential Isolation**
  - Hosting credentials moved to separate `credentials.json`
  - Optional secure OS keyring support via `credential_store=keyring`
  - Hosting tokens excluded from app/build process environments
  - Migration command moves legacy credentials safely

- **Container Isolation** (Linux + rootless Podman)
  - Read-only `/app` code mount
  - Writable `/data` for persistent storage only
  - Dropped capabilities and no-new-privileges
  - CPU/memory/PID resource limits enforced
  - Secrets via private env file, never command args

- **Environment Sanitization**
  - Apps inherit only platform allowlist + explicit `env_allow`
  - Reserved: `CLOUDFLARE_API_TOKEN`, `SPEIIHOSTING_*` names
  - App `.env` files parsed without shell evaluation

### 🚑 Reliability Improvements

#### Added
- **HTTP Health Monitoring**
  - Configurable path, expected status, body substring matching
  - Per-request timeout, interval, consecutive failure threshold
  - Startup timeout with health gate before promotion
  - Ongoing background checks with auto-restart

- **Durable Deployment Recovery**
  - Journaled promotion phases: `prepared` → `promoting` → `committed`
  - Automatic recovery on next supervisor/CLI pass
  - `speiihos recover` for manual intervention
  - Failed health checks trigger automatic rollback

- **Complete Offline Rollback**
  - Previous release retained with installed dependencies
  - `speiihos rollback` needs no registry downloads or rebuilds
  - Separate Python environments reused across releases

- **Persistent Data Storage**
  - `SPEII_DATA_DIR` (or `/data` in containers) survives deploys
  - `--purge-data` required to delete uploads/databases
  - `--reuse-data` attaches existing data to rehosted service

- **Release Disk Budget**
  - Default 4096 MiB per site (configurable)
  - Includes candidate/live/previous/environments
  - Promotion blocked when budget exceeded or <128 MB free

### 🎯 Usability Features

#### Added
- **Project Manifests** (`speiihosting.toml`)
  - `speiihos project init --type frontend|dynamic|backend|bot`
  - `speiihos project validate` checks schema and sensitive names
  - CLI flags override manifest values explicitly
  - Schema version 1 for projects, version 2 for state

- **Dry-Run Previews**
  - `--dry-run` and `--json` output for all hosting commands
  - Shows commands, ports, routes, health config, isolation
  - No state changes or package installs during preview

- **Inspection and Verification**
  - `speiihos inspect <name>` shows full service details
  - CPU/memory metrics, restart counts, disk usage
  - Recovery state, enforced limits, public routes
  - `speiihos verify <name>` explicitly tests public HTTPS

- **Migration Command**
  - `speiihos migrate` upgrades v1 → v2 state
  - Moves credentials out of `config.json`
  - Preserves existing API links (review with `inspect`)

- **Separate Build Logs**
  - Build output isolated from runtime logs
  - `speiihos logs <name> --build` shows install/build history
  - Both streams rotate at 5 MB with 1 backup

### ⚡ Performance Optimizations

#### Changed
- **Configuration Caching**
  - Cached by file mtime/size/inode
  - Reduces repeated JSON parsing in supervisor loop

- **Metrics Writes**
  - Lifecycle transitions publish immediately
  - Disposable metrics coalesced (default 2s, configurable 1-60s)
  - No fsync for reconstructible runtime state

- **Nginx Improvements**
  - Upstream keepalive for backend connections
  - Conservative immutable caching for hashed assets
  - HTML revalidates with `no-cache`
  - Streaming mode disables proxy buffering (SSE/streaming)
  - Bounded request body size and timeouts

- **Dependency Handling**
  - Package download caches reused safely
  - Writable installed dirs never shared between releases
  - Strict mode requires lockfiles with hashes

### 🏗️ Infrastructure Changes

#### Added
- **Supply Chain Hardening**
  - `binaries.json` requires SHA-256 for direct downloads
  - CI actions pinned to full commit SHAs
  - `uv.lock` and `requirements-dev.lock` with hashes
  - `pip-audit` checks pinned dependencies

- **Test Coverage**
  - 82 tests (up from 78) on Python 3.10/3.12/3.14
  - Real temporary Nginx in integration tests
  - HTTP health failure/auto-restart scenarios
  - Interrupted promotion at each phase boundary
  - Offline rollback with dependency snapshots
  - Secret filtering in real child processes

#### Changed
- **Default Nginx Port**
  - New installations: `127.0.0.1:8080` (unprivileged)
  - Existing ports preserved during migration
  - System Nginx config untouched

- **State Structure**
  - `credentials.json` separate from `config.json`
  - `sites/<name>/candidate/` during deployment
  - `sites/<name>/transaction.json` promotion journal
  - `sites/<name>/previous.json` runtime metadata
  - `sites/<name>/data/` persistent app storage

### 🐛 Bug Fixes

#### Fixed
- **Windows Logging** (2026-10-20 follow-up)
  - Log reader now decodes UTF-8 incrementally
  - Complete lines assembled across pipe reads
  - CRLF normalized, incomplete tail flushed at EOF
  - Long lines segmented at 8192 chars to bound buffers

- **Node Dependencies on Windows**
  - npm rollback fixture uses versioned `.tgz` packages
  - Tests verify physical directories, not junctions
  - Directory links unsafe after release rename on Windows

- **CI Startup Timeouts** (2026-10-20 follow-up)
  - HTTP readiness uses HTTP response directly
  - Concurrent test backends bypass reverse DNS
  - Health tests allow 10s startup, 25s transitions
  - Failed tests include bounded runtime/service logs

### ⚠️ Breaking Changes

#### Changed
- **API Exposure Behavior**
  - Old: Backends auto-linked to frontends
  - New: Explicit `speiihos link` required
  - **Action**: Run `speiihos inspect` on each site after migration

- **Credential Storage**
  - Old: API tokens in `config.json`
  - New: Separate `credentials.json` (or keyring)
  - **Action**: `speiihos migrate` handles this automatically

- **Deployment Semantics**
  - Old: Undefined promotion recovery
  - New: Journals prevent inconsistent state
  - **Action**: Interrupted deploys auto-recover on next command

### 📋 Migration Checklist

If upgrading from v0.1:

1. **Run migration**: `speiihos migrate`
2. **Review API routes**: `speiihos inspect <name>` for each service
3. **Remove unwanted links**: `speiihos unlink <frontend>` if needed
4. **Move persistent data**: Store uploads/DBs in `SPEII_DATA_DIR`
5. **Configure health checks**: Add `[health]` section to manifests
6. **Test public URLs**: `speiihos verify <name>` for HTTPS verification

### 🔮 Known Limitations

- **Platform Verification Incomplete**
  - OS startup/power behavior not tested on all targets
  - Podman cgroup enforcement tested via mocks only
  - Keyring integration needs per-platform validation

- **Operational Constraints**
  - Fixed-port restarts have brief interruptions
  - Database migrations/external APIs not auto-rolled back
  - macOS closed-lid operation hardware-dependent
  - Container image storage outside release budget

See [documentation.md](documentation.md#verification-and-release-limits) for complete list.

---

## [0.1.0] - 2026-XX-XX (Historical Reference)

**Initial implementation** - Original v1 architecture

### Added
- Four hosting modes: frontend, dynamic, backend, bot
- Cloudflare Tunnel integration for HTTPS
- Private Nginx instance on port 80
- Process supervision with auto-restart
- Cross-platform support (Windows, macOS, Linux)
- Deployment from isolated staging directories
- Basic rollback support
- Log rotation at 5 MB per service

### Architecture Notes
- Backends auto-linked to frontends (changed in v0.2)
- Credentials in main `config.json` (changed in v0.2)
- No deployment recovery (added in v0.2)
- Basic process health only (enhanced in v0.2)

---

## Release Schedule

### [released]

#### Planned for 0.3.0
- Registry publication (npm, PyPI)
- Hosted installer URLs
- Complete target-environment validation
- Performance benchmarks
- Multi-tenant scenarios
- Extended framework detection

#### Under Consideration
- Web dashboard UI
- Database backup integration
- Multi-machine clustering
- Let's Encrypt direct integration
- GitHub Actions deployment workflow

---

## Version History Quick Reference

| Version | Date | Key Feature | Status |
|---------|------|-------------|--------|
| **0.2.0** | 2026-10-20 | Security & reliability overhaul | ✅ Local validation |
| 0.1.0 | 2026-XX-XX | Initial implementation | 📚 Historical |

---

## Compatibility Matrix

### v0.2.0 Requirements

| Component | Minimum Version | Tested Versions |
|-----------|----------------|-----------------|
| Python | 3.10 | 3.10, 3.12, 3.14 |
| Nginx | 1.18+ | Latest stable |
| cloudflared | 2024+ | Latest official |
| Podman (optional) | 4.0+ | Rootless mode |
| Node.js (apps) | 18+ | 18 LTS, 20 LTS |

### Platform Support

| OS | Architecture | Status | Notes |
|----|-------------|--------|-------|
| **Linux** | x64, ARM64 | ✅ Tested | CI validated |
| **macOS** | x64, ARM64 | ✅ Tested | CI validated |
| **Windows** | x64 | ✅ Tested | CI validated |
| Windows | ARM64 | ⚠️ Untested | Should work |

---

## Upgrade Paths

### From 0.1.0 → 0.2.0

**Automatic**:
- State schema upgrade on first command
- `speiihos migrate` for explicit upgrade

**Manual Review**:
- Check `speiihos inspect` for each service
- Verify API routes still desired
- Update health checks in manifests

**Breaking Changes**:
- APIs no longer auto-expose
- Credentials storage location changed

### From 0.2.0 → 0.3.0 (future)

**Expected**:
- No breaking changes planned
- Optional new features
- Registry package updates

---

## Support & Resources

- **Documentation**: [USERGUIDE.md](USERGUIDE.md)
- **Architecture**: [documentation.md](documentation.md)
- **Development**: [plan.txt](plan.txt)
- **Issues**: GitHub Issues (when published)
- **License**: MIT

---

*For detailed technical changes, see commit history and [documentation.md](documentation.md)*
