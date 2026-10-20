<div align="center">

<!-- version:0.3.3 -->

# 🚀 SpeiiHosting

**Transform Any Computer Into a Professional Web Server**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Cross Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

*Zero port forwarding • Free HTTPS • Production-grade deployments*

[Quick Start](#-quick-start) • [Features](#-features) • [Documentation](USERGUIDE.md) • [Changelog](CHANGELOG.md)

</div>

---

## 🎯 What is SpeiiHosting?

SpeiiHosting (`speiihos`) is a professional CLI tool that turns any PC, Mac, or old laptop into a full-featured web hosting server. Host static sites, dynamic web apps, REST APIs, and 24/7 bots—all without router configuration or exposing ports.

**Perfect for:**
- 💼 **Developers** hosting personal projects and portfolios
- 🏢 **Small teams** running internal tools and dashboards  
- 🎓 **Students** learning deployment and DevOps practices
- 💰 **Cost savers** repurposing old hardware instead of cloud bills

## ✨ Features

### 🌐 **4 Hosting Modes, One Command**

| Mode | Use Case | Command | Public URL |
|------|----------|---------|------------|
| **Frontend** | React, Vue, Static Sites | `speiihos host-front` | ✅ HTTPS |
| **Dynamic** | Next.js, Django, Full-Stack | `speiihos host-dynamic` | ✅ HTTPS |
| **Backend** | REST APIs, Microservices | `speiihos host-back` | 🔒 Private |
| **Bot** | Telegram, Discord, Workers | `speiihos host-bot` | 🔒 Outbound |

### 🔐 **Enterprise-Grade Security**

- **Private by Default**: APIs never auto-expose; explicit linking required
- **Credential Isolation**: Hosting tokens separated from app environments
- **Container Support**: Optional rootless Podman with CPU/memory/PID limits
- **Environment Control**: Allowlist-based variable inheritance

### 🚑 **Bulletproof Deployments**

- **Atomic Rollbacks**: Complete offline rollback with preserved dependencies
- **Health Monitoring**: HTTP checks with auto-restart for unhealthy services
- **Crash Recovery**: Durable journals repair interrupted deployments
- **Zero Downtime***: Smart process management with graceful restarts

### 🛠️ **Developer-Friendly Workflow**

```sh
# Preview before applying
speiihos host-back --dry-run --json

# Save project configuration  
speiihos project init --type backend

# Deploy safely from source
speiihos deploy

# Instant rollback if needed
speiihos rollback api
```

### 📊 **Production Monitoring**

- Live log streaming with auto-rotation (5MB cap per service)
- CPU, memory, and health status tracking
- Separate build and runtime logs
- Explicit public HTTPS verification

---

## 🚀 Quick Start

### Installation

**Python (Recommended)**
```sh
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install .
```

**NPM Alternative**
```sh
npm install -g .
```

### First-Time Setup

```sh
# Interactive setup: installs Nginx, cloudflared, configures Cloudflare
speiihos init
```

You'll need:
- A Cloudflare account with a domain
- API token with: `Account Cloudflare Tunnel Edit`, `Zone Read`, `DNS Edit`

### Host Your First Site

**Static Website (React, Vue, HTML)**
```sh
cd ~/my-portfolio
npm run build
speiihos host-front --subdomain portfolio --dir dist
# ✅ Live at https://portfolio.yourdomain.com
```

**Full-Stack App (Next.js, Django)**
```sh
cd ~/my-nextjs-app  
speiihos host-dynamic --subdomain myapp --port 3000
# ✅ Live at https://myapp.yourdomain.com
```

**Private API (FastAPI, Express)**
```sh
cd ~/my-api
speiihos host-back --port 8000 --health-path /health
# 🔒 Runs on http://127.0.0.1:8000 (no public domain)

# Link to frontend when ready
speiihos link portfolio api --prefix /api
# ✅ https://portfolio.yourdomain.com/api → 127.0.0.1:8000
```

**24/7 Bot (Telegram, Discord)**
```sh
cd ~/my-telegram-bot
speiihos host-bot
# 🤖 Runs 24/7, auto-restarts on crash
```

---

## 📦 How It Works

```
┌─────────────────────────────────────────────────┐
│          Cloudflare Edge (Free HTTPS)           │
│     Global CDN • DDoS Protection • SSL          │
└─────────────────┬───────────────────────────────┘
                  │ Encrypted Tunnel (No port forwarding!)
                  ▼
┌─────────────────────────────────────────────────┐
│            Your PC / Old Laptop                 │
│                                                  │
│  ┌──────────────────────────────────────────┐  │
│  │  Nginx (127.0.0.1:8080)                  │  │
│  │  • Virtual hosting for all sites         │  │
│  │  • Asset caching & gzip                  │  │
│  │  • WebSocket support                     │  │
│  └──────────────────────────────────────────┘  │
│           │                    │                 │
│           ▼                    ▼                 │
│  ┌─────────────────┐  ┌─────────────────┐      │
│  │  Frontend       │  │  Backend API    │      │
│  │  (Static)       │  │  (Port 8000)    │      │
│  └─────────────────┘  └─────────────────┘      │
└─────────────────────────────────────────────────┘
```

**Key Principles:**
1. **Cloudflare Tunnels** provide public HTTPS without router changes
2. **Nginx** handles routing, caching, and proxying on loopback
3. **Process Supervision** keeps services running 24/7 with auto-restart
4. **Isolated Staging** prevents code edits from affecting live services

---

## 🎓 Core Concepts

### API Privacy Model

**Default: Private** → New APIs never auto-expose  
**Explicit Linking** → `speiihos link frontend api --prefix /api`  
**Same-Origin Routing** → No CORS issues, backend stays on 127.0.0.1  
**Authorization Required** → Public routes need app-level auth

### Deployment Architecture

```sh
~/.speiihosting/sites/myapp/
  ├── live/          # Current running release
  ├── previous/      # Complete backup with dependencies
  ├── candidate/     # Prepared deployment (during promote)
  ├── data/          # Persistent uploads/databases
  └── environments/  # Python venvs (reused across releases)
```

- **Atomic Deploys**: Builds complete before switching
- **Durable Journals**: Interrupted deploys auto-recover
- **Health Gates**: Failed health checks auto-rollback
- **Offline Rollback**: No registry downloads needed

### Resource Management

- **Release Budget**: Default 4096 MB per site (configurable)
- **Log Rotation**: 5 MB cap with 1 backup per service
- **Dependency Isolation**: Each release has its own installed packages
- **Data Persistence**: `SPEII_DATA_DIR` survives deploys and rollbacks

---

## 📋 Common Commands

```sh
# System Control
speiihos service start           # Start supervisor + all services
speiihos service stop            # Stop everything gracefully
speiihos list                    # Show all hosted services status

# Lifecycle Management
speiihos inspect api --json      # Detailed service info
speiihos start / stop / restart api
speiihos config set autostart on # Auto-start on boot (default)

# Deployment
speiihos deploy                  # Deploy from current directory
speiihos rollback api            # Restore previous release
speiihos recover                 # Repair interrupted deploy

# Monitoring
speiihos logs api -f             # Stream live logs
speiihos logs api --build        # View dependency install logs
speiihos verify portfolio        # Test public HTTPS URL
speiihos logs size               # Check log disk usage

# Configuration
speiihos project init --type backend
speiihos project validate
speiihos config set release_budget_mb 8192

# Cleanup
speiihos clean api               # Remove previous release
speiihos remove api              # Delete service entirely
speiihos logs clear --all        # Truncate all logs
```

---

## 🔧 Advanced Features

### Health Checks

```toml
# speiihosting.toml
[health]
path = "/health"
expected_status = 200
expected_body = "ok"
timeout = 2
interval = 5
failures = 3
startup_timeout = 30
```

### Container Isolation (Linux + Podman)

```sh
speiihos host-back --port 8000 --isolation podman \
  --image 'registry.io/app@sha256:abc123...' \
  --memory-mb 512 --cpus 1 --pids 128
```

### Strict Dependency Mode

```toml
strict_dependencies = true  # Requires lockfiles with hashes
```

### Custom Builds

```sh
speiihos host-front --build "pnpm build" --dir ./dist
speiihos host-dynamic --run "deno run --allow-net server.ts"
```

---

## 🆚 Comparison

| Feature | SpeiiHosting | PM2 | Dokku | Cloud Hosting |
|---------|-------------|-----|-------|---------------|
| **No Router Config** | ✅ | ❌ | ❌ | ✅ |
| **Free HTTPS** | ✅ | ❌ | ❌ | 💰 |
| **Atomic Rollback** | ✅ | ❌ | ✅ | ✅ |
| **Multi-Language** | ✅ | Node only | ✅ | ✅ |
| **Old Hardware** | ✅ | ✅ | ✅ | ❌ |
| **Cost** | $0 | $0 | $0 | $$$$ |

---

## 📚 Documentation

- **[User Guide](USERGUIDE.md)**: Step-by-step tutorials and examples
- **[Changelog](CHANGELOG.md)**: Version history and migration guides  
- **[Technical Docs](documentation.md)**: Architecture and operational limits
- **[Implementation Plan](plan.txt)**: Development roadmap and design decisions

---

## 🤝 Contributing

SpeiiHosting is currently in active development (v0.2.0). Contributions, bug reports, and feature requests are welcome!

### Version Management

This project uses centralized version management. To update the version:

```bash
# Simple: just update the VERSION file
echo "0.3.0" > VERSION
python3 scripts/update_version.py

# Or use Make
make release VERSION=0.3.0

# Check consistency
make version-check
```

See [VERSION_MANAGEMENT.md](VERSION_MANAGEMENT.md) for complete details.

### Development Setup

```sh
# Development setup
uv sync --locked --all-extras
uv run --locked python -m pytest -q
uv run --locked ruff check src tests
```

**Testing Requirements:**
- Python 3.10 / 3.12 / 3.14
- Nginx on PATH (for integration tests)
- 82 tests passing on all platforms

---

## ⚠️ Current Limitations

- **Startup Power**: OS-specific boot behavior needs per-platform verification
- **Container Enforcement**: Podman limits tested via mocks, not live cgroups
- **Sleep Prevention**: macOS closed-lid operation has hardware-specific limits
- **Zero Downtime**: Fixed-port restarts have brief interruptions

See [documentation.md](documentation.md#verification-and-release-limits) for complete operational limits.

---

## 📜 License

MIT License - see [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

Built with:
- **Typer** & **Rich** - Beautiful CLI experience
- **Cloudflare Tunnels** - Secure public access without port forwarding
- **Nginx** - High-performance reverse proxy and caching
- **Podman** - Optional rootless container isolation

---

<div align="center">

**Made for developers who want control without complexity**

[Get Started](USERGUIDE.md) • [Report Bug](https://github.com/ToekSopanha/speiihosting/issues) • [Request Feature](https://github.com/ToekSopanha/speiihosting/issues)

</div>
