# 🚀 SpeiiHosting (`speiihos`) — Official User Documentation & Operating Manual

> **Turn any PC, old laptop, or Mac into a 24/7 production-grade web hosting server with automated HTTPS, zero port forwarding, and zero cloud hosting fees.**

---

## 📖 Table of Contents
1. [Introduction & Overview](#1-introduction--overview)
2. [Prerequisites & System Requirements](#2-prerequisites--system-requirements)
3. [Installation & First-Time Setup (`speiihos init`)](#3-installation--first-time-setup-speiihos-init)
4. [The 4 Core Hosting Engines (Step-by-Step)](#4-the-4-core-hosting-engines-step-by-step)
   - [Engine 1: Static Frontend (`host-front`)](#engine-1-static-frontend-hosting-speiihos-host-front)
   - [Engine 2: Dynamic Full-Stack SSR Web (`host-dynamic`)](#engine-2-dynamic-full-stack-ssr-web-speiihos-host-dynamic)
   - [Engine 3: Internal Backend Services (`host-back`) — No Domain Needed!](#engine-3-internal-backend-services-speiihos-host-back)
   - [Engine 4: 24/7 Bot Runner (`host-bot`) — No Domain / No Port Needed!](#engine-4-247-bot-runner-speiihos-host-bot)
5. [Safe Code Updates & Atomic Deployment (`speiihos deploy`)](#5-safe-code-updates--atomic-deployment-speiihos-deploy)
6. [Instant Emergency Rollback (`speiihos rollback`)](#6-instant-emergency-rollback-speiihos-rollback)
7. [Storage Safeguards & Resource Rules](#7-storage-safeguards--resource-rules)
   - [Rule 1: Strict Single-Version Rollback Storage](#rule-1-strict-single-version-rollback-storage)
   - [Rule 2: Smart Capped Log Rotation (5 MB Limit)](#rule-2-smart-capped-log-rotation-5-mb-limit)
8. [Process Supervision & Terminal Independence](#8-process-supervision--terminal-independence)
9. [Laptop Server & Power Settings (Lid-Close Hosting)](#9-laptop-server--power-settings-lid-close-hosting)
10. [Complete CLI Command Reference](#10-complete-cli-command-reference)
11. [Developer Rules & Step-by-Step Best Practices](#11-developer-rules--step-by-step-best-practices)
12. [Troubleshooting & Frequently Asked Questions (FAQ)](#12-troubleshooting--frequently-asked-questions-faq)

---

## 1. Introduction & Overview

**SpeiiHosting** (CLI executable: `speiihos`) is an open-source developer tool designed to eliminate cloud hosting costs by transforming your personal computer or old laptop into an always-on, high-performance web server.

### Why SpeiiHosting?
- **Zero Port Forwarding & CGNAT-Proof:** Utilizes Cloudflare Tunnels (`cloudflared`) to establish an encrypted outbound connection to Cloudflare's global edge network. It functions smoothly behind home Wi-Fi, apartment routers, firewalls, and mobile hotspots.
- **Automated Free SSL/TLS:** Every public subdomain automatically receives valid, trusted HTTPS certificates managed by Cloudflare.
- **Auto-Save Safe (Isolated Live Staging):** Edit code in VS Code with auto-save enabled without breaking your live server. The live website runs in an isolated directory and only updates when you explicitly run `speiihos deploy`.
- **Zero Blast Radius:** If one backend crashes, other websites and services remain 100% online.
- **Resilient Background Daemons:** Closing your terminal, Command Prompt (CMD), PowerShell, or IDE will **never** stop your running services.

---

## 2. Prerequisites & System Requirements

Before you begin, ensure you meet the following basic requirements:

### A. Hardware & Operating System
- **Computer:** Any desktop PC, laptop, mini PC, or Mac.
- **Operating Systems Supported:**
  - **Windows 10 & 11** (64-bit)
  - **macOS** (Intel & Apple Silicon M1/M2/M3/M4)
  - **Linux** (Ubuntu, Debian, Fedora, CentOS, Arch, Raspberry Pi OS)
- **Memory & Storage:** At least 2 GB RAM and 500 MB of free disk space.

### B. Network
- A standard home internet connection (Wi-Fi, Ethernet, or mobile hotspot).
- **No static public IP address required.**
- **No router admin access or port forwarding required.**

### C. Cloudflare Account & Domain
- A free account at [Cloudflare.com](https://dash.cloudflare.com).
- Any registered domain name (e.g. `yourdomain.com`) whose nameservers are pointed to Cloudflare.
- A Cloudflare **API Token** with permissions:
  - `Zone.Zone:Read`
  - `Zone.DNS:Edit`
  - `Account.Cloudflare Tunnel:Edit`

---

## 3. Installation & First-Time Setup (`speiihos init`)

### Step 3.1: Install SpeiiHosting

Choose the installation method that fits your environment:

#### Option A: via Python PIP (Recommended)
```bash
pip install speiihosting
# or using pipx (isolated environment)
pipx install speiihosting
```

#### Option B: Standalone One-Line Installer (No Python Required)
- **Windows (PowerShell as Administrator or User):**
  ```powershell
  irm https://get.speiihosting.io.ps1 | iex
  ```
- **macOS & Linux (Terminal):**
  ```bash
  curl -fsSL https://get.speiihosting.io | bash
  ```

---

### Step 3.2: First-Time Setup Wizard (`speiihos init`)

Run the initialization command:
```bash
speiihos init
```

The interactive wizard will guide you through the initial configuration:
1. **System Health Check (`Doctor Engine`):**
   - Automatically checks for Nginx and `cloudflared`. If missing, Speii auto-downloads and installs them.
2. **Cloudflare Authentication:**
   - Paste your Cloudflare API Token (or press Enter to authorize via browser).
3. **Select Default Domain:**
   - Speii queries your Cloudflare account, detects your domain (e.g., `mydevsite.com`), and sets it as the default.
4. **Provision Cloudflare Tunnel:**
   - Automatically creates a secure named tunnel (`speiihosting-server`) and configures ingress rules.
5. **Laptop Power Configuration:**
   - Prompts whether to keep the system awake when closing your laptop lid (ideal for 24/7 home servers).

### Step 3.3: Verify System Health (`speiihos doctor`)
You can verify that all components are functioning at any time:
```bash
speiihos doctor
```
```text
[✓] Nginx 1.24.0: Installed and operational
[✓] Cloudflared 2024.x: Connected to Cloudflare Edge
[✓] Cloudflare API Token: Valid (Domain: mydevsite.com)
[✓] Speii Master Supervisor Daemon: Active
[✓] Port 80 Listener: Configured (Zero conflicts)
System is 100% healthy and ready to host!
```

---

## 4. The 4 Core Hosting Engines (Step-by-Step)

SpeiiHosting provides 4 distinct hosting engines. Choose the engine that fits your project:

```
┌───────────────────────────────────────────────────────────────────────────┐
│                       SPEIIHOSTING ENGINE SELECTOR                        │
├──────────────────────┬────────────────────────┬───────────────────────────┤
│ Project Type         │ Command                │ Domain / Port Rules       │
├──────────────────────┼────────────────────────┼───────────────────────────┤
│ React, Vue, Vite, HTML│ speiihos host-front    │ Subdomain + HTTPS (Port 80)│
│ Next.js SSR, Django   │ speiihos host-dynamic  │ Subdomain + App Port (SSR)│
│ FastAPI, Express API │ speiihos host-back     │ Local Port ONLY (NO Domain)│
│ Telegram/Discord Bot │ speiihos host-bot      │ NO Domain, NO Port Needed │
└──────────────────────┴────────────────────────┴───────────────────────────┘
```

---

### Engine 1: Static Frontend Hosting (`speiihos host-front`)

Designed for client-side Single Page Applications (SPAs) and static websites: **React, Vue, Vite, Svelte, Angular, Astro, or plain HTML/CSS/JavaScript**.

#### Requirements:
- A build folder containing `index.html` (e.g., `./dist`, `./build`, or `./out`) or raw static files.
- A chosen subdomain (e.g., `portfolio` becomes `portfolio.mydevsite.com`).

#### How to Use:
```bash
# 1. Navigate to your frontend project
cd ~/projects/my-portfolio

# 2. Build your production assets
npm run build

# 3. Publish with speiihos
speiihos host-front --subdomain portfolio
```

#### What Speii Does Automatically:
1. Detects your `./dist` or `./build` directory and copies files to isolated live staging (`~/.speiihosting/sites/portfolio/live/`).
2. Configures Nginx SPA routing rules (redirects all paths to `index.html` to support React Router / Vue Router without 404s).
3. Connects `portfolio.mydevsite.com` on Cloudflare Tunnel to the local Nginx virtual host.
4. Auto-provisions DNS CNAME records and SSL on Cloudflare.
5. Serves over shared local Port 80 — **zero port conflicts**, allowing you to host 50+ frontends on the same machine!

---

### Engine 2: Dynamic Full-Stack SSR Web (`speiihos host-dynamic`)

Designed for full-stack Server-Side Rendered (SSR) web applications: **Next.js (Node server), Nuxt.js, Remix, Django (Python), Laravel (PHP), Ruby on Rails, or SvelteKit**.

#### Requirements:
- A dynamic backend process that renders HTML and runs on an internal port (e.g., Next.js on port 3000).
- Static assets (CSS, JS, images) that should be cached by Nginx.
- A chosen subdomain (e.g., `app.mydevsite.com`).

#### How to Use:
```bash
# Example: Next.js SSR Application
cd ~/projects/my-nextjs-app

# 1. Build the production application
npm run build

# 2. Host dynamically
speiihos host-dynamic --subdomain app --port 3000 --run "npm start"
```

#### What Speii Does Automatically:
1. Spawns your server process in the background on port `3000` with crash recovery.
2. Generates an Nginx reverse proxy configuration for `app.mydevsite.com`:
   - Directs `/_next/static/` to serve directly from disk with caching and gzip compression.
   - Proxies dynamic SSR page requests to `http://127.0.0.1:3000`.
   - Enables WebSocket upgrade headers (`Upgrade` / `Connection`) for real-time hydration.
3. Binds the public Cloudflare tunnel to `app.mydevsite.com` with HTTPS.

---

### Engine 3: Internal Backend Services (`speiihos host-back`)

Designed for API backends and microservices: **Python FastAPI, Flask, Node.js Express, Go Gin, Spring Boot, or Docker containers**.

> [!IMPORTANT]
> **NO DOMAIN OR SUBDOMAIN IS NEEDED FOR BACKENDS!**
> Modern frontends and backends hosted on Speii communicate internally via localhost loopback or through local Nginx proxy passes. The backend runs as a 24/7 background service on `127.0.0.1:<PORT>`. This eliminates CORS issues and keeps internal APIs secure.

#### Requirements:
- A local port number (e.g., `8000`).
- A project entrypoint or start command.

#### How to Use:
```bash
# Example 1: FastAPI Python Backend
cd ~/projects/my-fastapi-app
speiihos host-back --port 8000

# Example 2: Node.js Express API with custom name and command
cd ~/projects/my-express-api
speiihos host-back --port 5000 --name api-service --run "node server.js"
```

#### What Speii Does Automatically:
1. **Port Collision Guard:** Verifies port `8000` is available. If occupied by an unrelated app, Speii warns you and suggests the next free port.
2. **Process Staging:** Syncs code to isolated live storage (`~/.speiihosting/sites/api/live/`).
3. **Background Daemon:** Spawns the process as a decoupled background service. If it crashes, Speii restarts it automatically.
4. **Internal Routing:** Configures internal loopback routing so your frontend can call `/api/v1` seamlessly with zero CORS configuration!

---

### Engine 4: 24/7 Bot Runner (`speiihos host-bot`)

Designed for automation bots and long-running background workers: **Telegram bots, Discord bots, Slack bots, Twitter/X bots, background schedulers, and queue workers**.

> [!IMPORTANT]
> **NO DOMAIN, NO SUBDOMAIN, AND NO PORT NEEDED!**
> Standard bots communicate outbound with remote API servers (e.g. Telegram or Discord gateways) using Long-Polling or persistent WebSockets. They do not accept incoming web requests, so they require neither open ports nor public web addresses.

#### Requirements:
- A bot project directory with an entrypoint (`bot.py`, `main.py`, `bot.js`, or `index.js`).
- An environment file (`.env`) containing your bot secret token (e.g. `TELEGRAM_BOT_TOKEN=...` or `DISCORD_TOKEN=...`).

#### How to Use:
```bash
# Navigate to your bot folder and run:
cd ~/projects/my-telegram-bot
speiihos host-bot
```

#### What Speii Does Automatically:
1. Detects the language (Python or Node.js) and entrypoint file.
2. Automatically parses `.env` and securely injects secrets into the background environment.
3. Launches the bot as an independent detached daemon process.
4. **Network Drop & Crash Recovery:** If your Wi-Fi disconnects or the bot encounters an unhandled API error, Speii automatically restarts the bot in seconds.

---

## 5. Safe Code Updates & Atomic Deployment (`speiihos deploy`)

### The Problem with Direct Live Hosting
If you host directly out of your active coding directory (`~/projects/my-app`), every time you test unfinished code, hit auto-save in VS Code, or trigger an intermediate file write, **your live production site can break instantly**.

### The Speii Isolated Staging Solution
Speii strictly separates your local development workspace from the live production server:

```
[ Developer Workspace ]                 [ Speii Production Server ]
~/projects/my-portfolio/                 ~/.speiihosting/sites/portfolio/
├── src/                                 ├── live/      (Currently serving users)
├── package.json                         └── previous/  (Backup for 1-second rollback)
└── dist/ (Work freely, auto-save on!)
                  │
                  ▼ Run: "speiihos deploy"
           [ Atomic Sync & Cache Purge ]
```

### How to Update Your Live Application:
When you have finished testing your updates locally, simply run:
```bash
cd ~/projects/my-app
speiihos deploy
```

#### What Happens Behind the Scenes:
1. **Rollback Snapshot:** Speii backs up the current live version to `~/.speiihosting/sites/<name>/previous/`.
2. **Atomic Replacement:** Safely compiles/syncs the updated code into `live/`.
3. **Frontend CDN Purge:** If updating a frontend, Speii automatically calls the Cloudflare API to purge edge cache so visitors immediately see new changes worldwide.
4. **Backend Restart:** If updating a backend, Speii gracefully restarts the background service in milliseconds.
5. **Zero Downtime:** Visitors never experience broken screens or maintenance pages.

---

## 6. Instant Emergency Rollback (`speiihos rollback`)

Did you deploy new code that introduced a bug or runtime exception? You can recover instantly without needing to debug under pressure.

### How to Roll Back:
```bash
speiihos rollback <name>
```

#### Examples:
```bash
speiihos rollback portfolio     # Reverts frontend website
speiihos rollback api           # Reverts backend API
speiihos rollback telegram-bot  # Reverts bot service
```

### How It Works:
- In less than **1 second**, Speii swaps `previous/` back into `live/` and reloads the service.
- Your working, stable application is immediately restored.

---

## 7. Storage Safeguards & Resource Rules

SpeiiHosting is engineered to run on laptops and modest PCs with limited disk space. It enforces strict rules to prevent storage exhaustion:

### Rule 1: Strict Single-Version Rollback Storage
- **Max 1 Previous Release:** Speii **strictly stores only ONE previous version** in `previous/`. Each new deployment overwrites the old snapshot. Speii **never** accumulates chains of historical versions (`v1`, `v2`, `v3`...).
- **Heavy Directory Exclusions:** When backing up, Speii aggressively excludes dependencies and temporary caches:
  - Excludes: `node_modules/`, `.git/`, `.venv/`, `venv/`, `__pycache__/`, `.next/cache/`, `.turbo/`, `tmp/`.
  - Only source code and manifests (`package.json`, `requirements.txt`, `.env`) are preserved.
  - The rollback snapshot typically takes only a few **kilobytes to megabytes**, rather than gigabytes.
- **Manual Backup Cleanup:** If you want to delete the rollback backup to reclaim space:
  ```bash
  speiihos clean portfolio      # Deletes previous/ backup for portfolio
  speiihos clean --all          # Wipes all rollback backups across all sites
  ```

---

### Rule 2: Active Nginx & App Logging with Capped Rotation & Self-Service Size Control

Developers need full visibility into incoming web traffic, HTTP status codes, client IPs, and server errors. Speii keeps **Nginx access logs and application logs fully enabled**, while providing total transparency into file sizes and complete self-service control to clear them:

```
Web Requests & App stdout/stderr
           │
           ├──► ~/.speiihosting/logs/nginx_access.log  (HTTP traffic: IP, path, status 200/404/500)
           ├──► ~/.speiihosting/logs/nginx_error.log   (Nginx gateway errors & timeouts)
           └──► ~/.speiihosting/logs/<name>.log        (App/Bot console output & exceptions)
```

#### 1. Full Visibility into Nginx HTTP Web Traffic:
```bash
# View recent Nginx access and error logs
speiihos logs nginx

# Stream live web visitor traffic in real time
speiihos logs nginx -f
```

#### 2. Inspecting Exact Log File Sizes on Disk:
Users can check the exact disk space consumed by every log file at any time:
```bash
speiihos logs size
```
Example Output:
```text
========================================================================
LOG FILE                 TYPE              SIZE       LINES
========================================================================
portfolio.log            Frontend SPA      1.2 MB     14,200
api.log                  Backend Service   3.8 MB     42,100
telegram-bot.log         Bot Worker        0.5 MB      6,300
nginx_access.log         Nginx HTTP Access 2.1 MB     22,000
nginx_error.log          Nginx Gateway     0.1 MB        450
speii-daemon.log         Supervisor        0.2 MB      1,800
========================================================================
Total Disk Space Used by Logs: 7.9 MB (Safe - within 10 MB per-service limits)
========================================================================
```

#### 3. Self-Service Log Clearing:
Users have full manual control to clear any log file back to 0 bytes whenever they want:
```bash
# Clear a specific service's log file
speiihos logs clear api

# Clear Nginx HTTP access & error logs
speiihos logs clear nginx

# Clear all log files across all sites and Nginx
speiihos logs clear --all
```

#### 4. Automatic Safety Rotation:
- Every log file is automatically rotated when it reaches **5 MB** (max 1 backup archive = 10 MB maximum total per service). Even if you forget to clear logs, your hard drive will **never run out of space**.

---

## 8. Process Supervision & Terminal Independence

A common mistake with self-hosting scripts is that closing your terminal window terminates all child processes. **SpeiiHosting completely solves this.**

### How It Works:
- **On Windows 10 & 11:** Speii launches processes with `DETACHED_PROCESS` and `CREATE_NEW_PROCESS_GROUP` flags with `windowsHide: true`.
- **On macOS & Linux:** Speii launches processes using POSIX `setsid()`, double-forking, and decoupled I/O streams.

### Operating Rule:
> [!TIP]
> After running `speiihos host-front`, `host-back`, `host-dynamic`, or `host-bot`, **you can safely CLOSE Command Prompt, PowerShell, Terminal, or exit VS Code completely.**
> Your applications, websites, and bots will continue running 24/7 in the background!

---

## 9. Laptop Server & Power Settings (Lid-Close Hosting)

If you are using an old laptop as a dedicated home server, you want to close the lid and place it on a desk or shelf without it entering Sleep mode.

### 1. Enable Lid-Close Hosting:
```bash
speiihos config set sleep_prevent on
```
- **What happens:** The screen turns off to save power, but the CPU, Wi-Fi, Nginx, and your services remain active 24/7.
- **Cross-platform support:**
  - Windows: Configures `powercfg` lid-close actions.
  - macOS: Sets `pmset` sleep assertions.
  - Linux: Configures `systemd-logind` (`HandleLidSwitch=ignore`).

### 2. Enable Auto-Start on Machine Reboot:
```bash
speiihos config set autostart on
```
- When your computer reboots (e.g., after an OS update or power outage), the Speii supervisor daemon automatically starts up and restores all previously running websites, backends, and bots!

### 3. View Current Settings:
```bash
speiihos config show
```

---

## 10. Complete CLI Command Reference

### Setup & System Health
| Command | Description |
| :--- | :--- |
| `speiihos init` | Runs the first-time setup wizard (Doctor, Cloudflare login, domain binding). |
| `speiihos doctor` | Diagnostic scan of Nginx, Python, cloudflared, and port listeners. |
| `speiihos config show` | Displays all global configuration values. |
| `speiihos config set <key> <val>` | Updates a configuration setting (e.g., `sleep_prevent on`). |

### Hosting
| Command | Description |
| :--- | :--- |
| `speiihos host-front --subdomain <name>` | Hosts static frontend (React, Vue, HTML) on shared port 80 with HTTPS. |
| `speiihos host-dynamic --subdomain <name> --port <num> [--run "<cmd>"]` | Hosts dynamic SSR app (Next.js, Django, Laravel) with domain & reverse proxy. |
| `speiihos host-back --port <number> [--name <name>] [--run "<cmd>"]` | Hosts backend as 24/7 background service on 127.0.0.1 (No domain needed!). |
| `speiihos host-bot [--name <name>] [--run "<cmd>"]` | Runs Telegram/Discord bot 24/7 with auto-restart and `.env` loading (No domain/port needed!). |

### Deployment & Maintenance
| Command | Description |
| :--- | :--- |
| `speiihos deploy` | Publishes code updates from local directory to live production server. |
| `speiihos rollback <name>` | Restores the previous stable release in 1 second. |
| `speiihos clean <name>` | Deletes the rollback snapshot for a specific site to reclaim disk space. |
| `speiihos clean --all` | Deletes all rollback snapshots across all hosted sites. |
| `speiihos clean --logs` | Purges all log files across all sites. |
| `speiihos purge <name>` | Purges Cloudflare CDN edge cache for a frontend subdomain. |

### Service Lifecycle & Monitoring
| Command | Description |
| :--- | :--- |
| `speiihos list` | Displays all hosted sites, ports, URLs, and real-time status. |
| `speiihos start <name>` | Starts a stopped service. |
| `speiihos stop <name>` | Pauses/stops a running service. |
| `speiihos restart <name>` | Restarts a running service. |
| `speiihos logs <name>` | Displays recent logs (default 100 lines). |
| `speiihos logs <name> -n <num>` | Displays last N lines of log history (e.g. `-n 500`). |
| `speiihos logs <name> -f` | Streams live logs in real time (press `Ctrl+C` to exit). |
| `speiihos logs nginx` | Displays incoming Nginx HTTP access and error logs. |
| `speiihos logs size` | Displays formatted table of all log files and their exact disk sizes. |
| `speiihos logs clear <name>` | Empties that service's log file back to 0 bytes immediately. |
| `speiihos logs clear nginx` | Empties Nginx access & error logs to 0 bytes. |
| `speiihos logs clear --all` | Clears all log files across all sites and Nginx. |
| `speiihos remove <name>` | Permanently deletes a site, removes vhost, kills process, and unlinks files. |

### Master Service Controls
| Command | Description |
| :--- | :--- |
| `speiihos service start` | Starts master Cloudflare tunnel and Nginx daemon. |
| `speiihos service stop` | Stops all hosting services on this machine. |
| `speiihos service status` | Checks master tunnel connectivity, Nginx status, and uptime. |

---

## 11. Developer Rules & Step-by-Step Best Practices

Follow these golden rules to keep your self-hosted server secure, fast, and healthy:

1. **Rule of Clean Environments (`.env`):**
   - Keep your secrets (database passwords, bot tokens, API keys) in a local `.env` file.
   - Never commit `.env` to Git. Speii automatically reads `.env` and injects variables securely into background processes.
2. **Rule of Distinct Backend Ports:**
   - Every internal backend (`host-back`) must run on a unique port (e.g. `8000`, `8001`, `5000`). If unsure, Speii will automatically detect collisions and notify you.
3. **Rule of Static Frontends (Port 80):**
   - Do **NOT** assign custom ports to frontends. Frontends share local Port 80 via Nginx virtual host routing (`portfolio.domain.com`, `blog.domain.com`). This ensures zero port conflicts.
4. **Rule of Staged Deployments:**
   - Always run your build or tests locally before running `speiihos deploy`.
   - If an issue occurs after deployment, run `speiihos rollback <name>` immediately.
5. **Rule of Log Hygiene:**
   - If you want to keep your hard drive completely pristine, run `speiihos clean --logs` periodically or after large debugging sessions.

---

## 12. Troubleshooting & Frequently Asked Questions (FAQ)

### Q1: Can I host multiple websites and APIs on a single laptop?
**A:** Yes! You can host as many sites and APIs as your machine's CPU and RAM can handle. All frontends share Port 80, and backends run on individual internal ports.

### Q2: What happens if one of my websites crashes?
**A:** Speii utilizes **Service Fault Isolation (Zero Blast Radius)**. Each application runs with its own process ID (PID). If one backend crashes, Speii attempts to restart it, while all other sites remain 100% online.

### Q3: What happens when my computer turns off or restarts?
**A:** When your machine boots back up, the Speii supervisor daemon automatically starts and resurrects all websites and bots that were active before shutdown.

### Q4: Do I need a public static IP or router port forwarding?
**A:** No. Cloudflare Tunnel creates a secure outbound encrypted tunnel to Cloudflare's edge network. It works through CGNAT, firewalls, and home Wi-Fi without opening any inbound ports on your router.

### Q5: If I close Command Prompt (CMD) or Terminal, do my websites still run?
**A:** Yes, 100%! All services run as detached background daemons. You can close your terminal, shut down VS Code, and disconnect — your services will stay online 24/7.

### Q6: Will Speii fill up my hard drive with logs and rollback backups?
**A:** No. Speii balances complete developer visibility with strict disk safety:
1. **Nginx & App Logs Enabled:** Nginx HTTP access logs and application logs are fully active, so you can track all incoming web traffic, status codes (200, 404, 500), and errors.
2. **Inspect Sizes Anytime:** Run `speiihos logs size` to view the exact disk space used by every log file.
3. **Self-Service Clearing:** You can clear any log file at any time using `speiihos logs clear <name>`, `speiihos logs clear nginx`, or `speiihos logs clear --all`.
4. **Automatic Safety Cap:** Logs automatically rotate when they hit 5 MB (maximum 10 MB total per service), so they can never cause disk exhaustion even if left unattended.
5. **Rollback Backup Limit:** Rollback is strictly capped at 1 single previous version (excluding `node_modules` and `.venv`).

---

🎉 **You are now ready to host your web apps, APIs, and bots 24/7 with SpeiiHosting!**
