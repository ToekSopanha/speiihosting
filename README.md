# 🚀 SpeiiHosting (`speiihos`)

<p align="center">
  <b>Turn any old PC, laptop, or Mac into a 24/7 production-grade web hosting powerhouse.</b><br>
  Automated free HTTPS • Zero port forwarding • CGNAT-proof • $0 cloud hosting fees.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License">
  <img src="https://img.shields.io/badge/python-3.10+-brightgreen.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg" alt="Platform">
  <img src="https://img.shields.io/badge/tunnel-Cloudflare%20Tunnels-orange.svg" alt="Cloudflare">
  <img src="https://img.shields.io/badge/storage-Zero--Waste%20Capped-success.svg" alt="Zero-Waste Storage">
</p>

---

## 💡 Why SpeiiHosting?

Why pay **$20 to $100+/month** for cloud hosting (Vercel, AWS, Heroku, DigitalOcean) when you have an old laptop or desktop sitting in a closet or drawer?

Self-hosting traditionally required painful networking setups: router port forwarding, dynamic DNS, complex Nginx configurations, and handling SSL certificates. **SpeiiHosting completely automates all of this:**

* 🌐 **Zero Port Forwarding & CGNAT-Proof:** Powered by Cloudflare Tunnels (`cloudflared`). Works out of the box on apartment Wi-Fi, home networks, and mobile hotspots.
* 🔒 **Automated Free SSL:** Every subdomain receives valid, trusted HTTPS certificates automatically.
* 🛡️ **Auto-Save Safe (Isolated Live Staging):** Edit code in VS Code freely with auto-save enabled without breaking your live server. Changes only publish when you run `speiihos deploy`.
* 🔄 **1-Second Instant Rollback:** Deployed a bug? Run `speiihos rollback <name>` to restore the previous stable version in 1 second.
* 💾 **Zero Disk Exhaustion:** Strict 1-version backup limit (excluding `node_modules` and `.venv`) and smart 5 MB rotating log caps prevent hard drives from ever filling up.
* 💻 **Close Your Laptop Lid:** Run your laptop 24/7 with the screen off and lid closed using built-in sleep prevention.
* ⚡ **Terminal Independence:** Closing Command Prompt, PowerShell, Terminal, or VS Code **never** terminates your running sites.

---

## 🧩 4 Dedicated Hosting Engines

SpeiiHosting provides a tailored hosting engine for every project type:

| Engine | Command | Best For | Domain / Port Rules |
| :--- | :--- | :--- | :--- |
| **Static Frontend** | `speiihos host-front` | React, Vue, Vite, Svelte, HTML | Subdomain + HTTPS (Shared Port 80) |
| **Dynamic SSR Web** | `speiihos host-dynamic` | Next.js, Django, Laravel, Nuxt | Subdomain + Background SSR Port |
| **Internal Backend** | `speiihos host-back` | FastAPI, Express.js, Flask, Go | **Local Port ONLY (NO domain needed!)** |
| **24/7 Bot Runner** | `speiihos host-bot` | Telegram, Discord, Slack bots | **NO Domain, NO Port Needed!** |

---

## ⚡ Quickstart in 60 Seconds

### 1. Install SpeiiHosting

Choose your preferred installation method:

```bash
# via Python PIP (Recommended)
pip install speiihosting

# or via Standalone Installer (macOS & Linux)
curl -fsSL https://get.speiihosting.io | bash

# or via Standalone Installer (Windows PowerShell)
irm https://get.speiihosting.io.ps1 | iex
```

### 2. Initialize (`speiihos init`)

Run the first-time setup wizard:
```bash
speiihos init
```
* Checks dependencies (Nginx & `cloudflared`) and auto-installs missing tools.
* Connects your free Cloudflare account and selects your domain.
* Provisions your permanent home server tunnel.

---

## 🚀 How to Host Your Projects

### 1. Host a Frontend Website (React, Vue, HTML)
```bash
cd ~/projects/my-portfolio
npm run build
speiihos host-front --subdomain portfolio
```
🎉 **Live at:** `https://portfolio.yourdomain.com` (with free HTTPS!).

---

### 2. Host a Dynamic Full-Stack SSR Web App (Next.js, Django)
```bash
cd ~/projects/my-nextjs-app
npm run build
speiihos host-dynamic --subdomain app --port 3000 --run "npm start"
```
🎉 **Live at:** `https://app.yourdomain.com` with Nginx asset caching and reverse proxying!

---

### 3. Host an Internal Backend Service (FastAPI, Express)
> **Note:** Backends run purely as internal background services on `127.0.0.1`. **No public domain or subdomain needed!**
```bash
cd ~/projects/my-fastapi-api
speiihos host-back --port 8000
```
🚀 **Running locally at:** `http://127.0.0.1:8000`. Frontends communicate directly with it internally with **zero CORS headaches!**

---

### 4. Host a 24/7 Bot (Telegram, Discord)
> **Note:** Bots use outbound polling or WebSockets. **No domain, no port needed!**
```bash
cd ~/projects/my-telegram-bot
speiihos host-bot
```
🤖 **Active 24/7!** Automatically detects `.env` secrets, runs detached in the background, and restarts instantly if your Wi-Fi drops.

---

## 🛠️ Daily Workflow & Maintenance

### 1. Safe Code Updates (`speiihos deploy`)
Edit your code freely in your workspace. When tested and ready to publish:
```bash
cd ~/projects/my-portfolio
speiihos deploy
```
* Compiles/syncs your updates into live production with zero downtime.
* Automatically purges Cloudflare CDN cache so visitors see updates immediately.

### 2. Instant Emergency Rollback (`speiihos rollback`)
Deployed a broken release? Restore the last stable version in 1 second:
```bash
speiihos rollback portfolio
```

### 3. View Logs (Apps + Nginx), Check Sizes & Self-Service Clear
```bash
# View app or Nginx HTTP logs
speiihos logs api             # View last 100 lines of API logs
speiihos logs api -n 500      # View last 500 lines of history
speiihos logs api -f          # Stream live output in real time (Ctrl+C to exit)
speiihos logs nginx           # View incoming Nginx HTTP web traffic & errors
speiihos logs nginx -f        # Stream live web visitor requests

# Inspect exact log file sizes on disk
speiihos logs size            # Shows table of all log files & exact disk usage

# Clear logs manually (Self-Service)
speiihos logs clear api       # Clear api logs back to 0 bytes
speiihos logs clear nginx     # Clear Nginx access & error logs
speiihos logs clear --all     # Clear all logs across all sites & Nginx
```
*Logs automatically rotate at 5 MB per file, giving you deep error history without risking disk bloat!*

### 4. Turn an Old Laptop into a 24/7 Server
Close the lid, turn off the screen, and let it run permanently on a shelf:
```bash
# Keep server running with laptop lid closed
speiihos config set sleep_prevent on

# Automatically restart all websites and bots when the PC reboots
speiihos config set autostart on
```

---

## 📋 Command Cheat Sheet

| Task | Command |
| :--- | :--- |
| **Setup & Health** | `speiihos init` • `speiihos doctor` • `speiihos config show` |
| **Host Frontend** | `speiihos host-front --subdomain <name>` |
| **Host SSR Web** | `speiihos host-dynamic --subdomain <name> --port <num>` |
| **Host Backend** | `speiihos host-back --port <num>` *(No domain needed)* |
| **Host Bot** | `speiihos host-bot` *(No domain/port needed)* |
| **Deploy Updates** | `speiihos deploy` *(Run inside project directory)* |
| **Instant Rollback**| `speiihos rollback <name>` |
| **View Logs** | `speiihos logs <name>` • `speiihos logs nginx` • `speiihos logs size` |
| **Clear Logs** | `speiihos logs clear <name>` • `speiihos logs clear nginx` • `speiihos logs clear --all` |
| **Clean Backups** | `speiihos clean <name>` • `speiihos clean --all` |
| **List Services** | `speiihos list` |
| **Lifecycle** | `speiihos start <name>` • `speiihos stop <name>` • `speiihos restart <name>` |
| **Remove Site** | `speiihos remove <name>` |

---

## 🏗️ System Architecture

```
                             +-------------------------------------+
                             |           CLOUDFLARE EDGE           |
                             |  - Free SSL (*.yourdomain.com)      |
                             |  - DDoS & Bot Protection            |
                             |  - Global Anycast CDN               |
                             +-------------------------------------+
                                                │
                                  Encrypted Cloudflare Tunnel
                                  (Outbound - Zero Open Ports!)
                                                │
                                                ▼
+───────────────────────────────────────────────────────────────────────────────────────────+
│                                  YOUR PC / OLD LAPTOP                                     │
│                                                                                           │
│   [ Speii CLI & Supervisor Daemon ]                                                       │
│     - Detached background execution (Closing terminal NEVER kills sites)                  │
│     - Auto-restores all services upon machine reboot                                      │
│                                                                                           │
│   [ Cloudflare Tunnel Daemon (cloudflared) ]                                              │
│     - Encrypted bridge passing incoming requests to localhost:80                          │
│                                                                                           │
│   [ Local Nginx Router (Port 80) ]                                                        │
│     ├── portfolio.domain.com   ──►  Static Staging: ~/.speiihosting/sites/portfolio/live/ │
│     ├── app.domain.com         ──►  SSR Process: http://127.0.0.1:3000                     │
│     └── /api                   ──►  Internal Backend: http://127.0.0.1:8000 (Zero CORS!)  │
│                                                                                           │
│   [ 24/7 Outbound Workers ]                                                               │
│     └── Telegram/Discord Bot   ──►  Polling Outbound (Zero ports, zero domains needed!)   │
+───────────────────────────────────────────────────────────────────────────────────────────+
```

---

## 📚 Complete Documentation

Looking for detailed architecture breakdowns, Nginx configurations, troubleshooting steps, and best practices?

👉 **Read the full [User Documentation & Operating Manual (documentation.md)](documentation.md)**

---

## 🤝 Contributing & License

Contributions, bug reports, and feature requests are welcome! Feel free to open an issue or submit a pull request.

This project is licensed under the **MIT License**.
