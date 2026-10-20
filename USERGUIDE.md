# SpeiiHosting User Guide

**Complete Step-by-Step Tutorial for Self-Hosting**

Version 0.3.0 • Last Updated: 2026-10-20

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Initial Setup](#2-initial-setup)
3. [Hosting Static Websites](#3-hosting-static-websites)
4. [Hosting Dynamic Web Apps](#4-hosting-dynamic-web-apps)
5. [Hosting Private APIs](#5-hosting-private-apis)
6. [Hosting 24/7 Bots](#6-hosting-247-bots)
7. [Deployment & Updates](#7-deployment--updates)
8. [Monitoring & Logs](#8-monitoring--logs)
9. [Advanced Configuration](#9-advanced-configuration)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Getting Started

### What You'll Need

**Hardware:**
- Any PC, Mac, or old laptop
- At least 2 GB RAM (4 GB recommended)
- 10 GB free disk space
- Stable internet connection

**Software:**
- Python 3.10 or higher
- (Optional) Node.js 18+ for npm installation

**Cloud Setup:**
- Free Cloudflare account: [dash.cloudflare.com](https://dash.cloudflare.com)
- A domain added to Cloudflare (can be free or paid)
- Cloudflare API token (we'll create this together)

### Installation Methods

#### Method 1: Python (Recommended)

```bash
# Clone or download the repository
cd /path/to/speiihosting

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate

# Install SpeiiHosting
pip install .

# Verify installation
speiihos --version
```

#### Method 2: NPM

```bash
# Install globally
npm install -g .

# Verify installation
speiihos --version
```

#### Method 3: Standalone Scripts

```bash
# On macOS/Linux:
sh scripts/install.sh

# On Windows (PowerShell):
powershell -File scripts/install.ps1
```

---

## 2. Initial Setup

### Step 1: Create Cloudflare API Token

1. **Login to Cloudflare Dashboard**
   - Go to https://dash.cloudflare.com
   - Navigate to: My Profile → API Tokens

2. **Create Custom Token**
   - Click "Create Token"
   - Click "Create Custom Token"

3. **Configure Permissions**
   ```
   Account Permissions:
   ✓ Cloudflare Tunnel - Edit
   
   Zone Permissions:
   ✓ DNS - Edit
   ✓ Zone - Read
   ✓ Cache Purge - Purge (optional, for cache invalidation)
   ```

4. **Set Zone Resources**
   ```
   Include → Specific zone → yourdomain.com
   ```

5. **Create and Copy Token**
   - Click "Continue to summary"
   - Click "Create Token"
   - **Copy the token immediately** (shown only once!)

### Step 2: Run Initial Setup

```bash
# Start interactive setup
speiihos init
```

**What happens during setup:**

```
🔍 Checking system dependencies...
   [✓] Python 3.12 found
   [✗] Nginx not found → Installing...
   [✗] cloudflared not found → Installing...

🌐 Cloudflare Configuration
   Enter your API token: [paste token here]
   
   Available domains:
   1. example.com
   2. mydomain.net
   
   Select domain [1]: 1
   
✓ Created tunnel: speiihosting-home-server
✓ Started Cloudflare tunnel
✓ Configured Nginx on 127.0.0.1:8080

🚀 Setup complete! Ready to host.
```

### Step 3: Verify Setup

```bash
# Check system status
speiihos list

# Should show:
# No services hosted yet
```

---

## 3. Hosting Static Websites

### Use Case
Host React, Vue, Angular, plain HTML/CSS/JS, or any static build output.

### Step-by-Step: React Portfolio Site

#### Step 1: Build Your Site

```bash
# Navigate to your project
cd ~/projects/my-portfolio

# Build for production
npm run build

# Verify build output exists
ls dist/
# Should show: index.html, assets/, favicon.ico, etc.
```

#### Step 2: Host the Site

```bash
# Host with subdomain
speiihos host-front --subdomain portfolio --dir dist
```

**Output:**
```
🌐 Hosting Frontend Site
   Source: /Users/mac/projects/my-portfolio
   Build dir: dist
   Subdomain: portfolio.example.com

📦 Staging to: ~/.speiihosting/sites/portfolio/live/
   Copied 124 files (2.4 MB)

🌍 Configuring Cloudflare
   ✓ Created DNS: portfolio.example.com
   ✓ Tunnel route configured

🔧 Configuring Nginx
   ✓ Generated vhost config
   ✓ Nginx reload successful

✅ Site is LIVE!
   URL: https://portfolio.example.com
   Status: Running
```

#### Step 3: Test Your Site

```bash
# Verify public HTTPS
speiihos verify portfolio

# Check status
speiihos list

# View in browser
# https://portfolio.example.com
```

### Advanced Frontend Options

#### Custom Build Command

```bash
# Use custom build tool
speiihos host-front --subdomain mysite \
  --build "pnpm build" \
  --dir dist
```

#### Multiple Build Outputs

```bash
# Next.js static export
speiihos host-front --subdomain nextsite --dir out

# Create React App
speiihos host-front --subdomain reactapp --dir build

# Plain HTML
speiihos host-front --subdomain landing --dir public
```

#### Using Project Manifest

```bash
# Create project config
speiihos project init --type frontend

# Edit speiihosting.toml
cat > speiihosting.toml << 'EOF'
schema_version = 1
type = "frontend"
name = "portfolio"
subdomain = "portfolio"
dir = "dist"
build = "npm run build"
EOF

# Host using config
speiihos host-front
```

---

## 4. Hosting Dynamic Web Apps

### Use Case
Server-rendered applications: Next.js, Nuxt, Django, Flask, Laravel, etc.

### Step-by-Step: Next.js Application

#### Step 1: Prepare Your App

```bash
cd ~/projects/my-nextjs-app

# Ensure your app listens to PORT environment variable
# In your Next.js config or server.js:
```

```javascript
// server.js or next.config.js
const port = process.env.PORT || 3000;
```

#### Step 2: Host the Application

```bash
# Host with auto-detection
speiihos host-dynamic --subdomain myapp --port 3000
```

**What SpeiiHosting detects:**
- ✓ Found `package.json` with `"next"` dependency
- ✓ Will run: `npm install && npm run build && npm start`
- ✓ Expects server on port 3000

**Output:**
```
🚀 Hosting Dynamic Web App
   Framework: Next.js (detected)
   Port: 3000
   Subdomain: myapp.example.com

📦 Installing dependencies...
   Running: npm install
   ✓ 1,234 packages installed

🔨 Building application...
   Running: npm run build
   ✓ Build completed (45s)

🔧 Starting application server...
   ✓ Process started (PID: 12345)
   ✓ Health check passed: http://127.0.0.1:3000

🌍 Configuring public access...
   ✓ DNS: myapp.example.com
   ✓ Nginx reverse proxy configured
   ✓ Tunnel route active

✅ Application is LIVE!
   URL: https://myapp.example.com
   Local: http://127.0.0.1:3000
   PID: 12345
   Auto-restart: Enabled
```

#### Step 3: Verify and Monitor

```bash
# Check application status
speiihos inspect myapp

# Output shows:
# - Process health: Running
# - CPU/Memory usage
# - Restart count: 0
# - Public URL: Verified

# Test public access
speiihos verify myapp

# Stream live logs
speiihos logs myapp -f
```

### Step-by-Step: Django Application

#### Step 1: Prepare Django Project

```bash
cd ~/projects/my-django-app

# Create requirements.txt if not exists
cat > requirements.txt << 'EOF'
Django>=4.2
gunicorn>=21.0
psycopg2-binary>=2.9
python-dotenv>=1.0
EOF

# Ensure WSGI configuration
# File: myproject/wsgi.py should exist
```

#### Step 2: Host with Custom Command

```bash
# Host Django with Gunicorn
speiihos host-dynamic --subdomain djangoapp --port 8000 \
  --run "gunicorn myproject.wsgi:application --bind 0.0.0.0:8000"
```

**Alternative: Let SpeiiHosting Auto-detect**

```bash
# SpeiiHosting detects manage.py and wsgi.py
speiihos host-dynamic --subdomain djangoapp --port 8000
```

#### Step 3: Configure Health Check

```bash
# Create project manifest
speiihos project init --type dynamic

# Edit speiihosting.toml
cat >> speiihosting.toml << 'EOF'
[health]
path = "/health/"
expected_status = 200
timeout = 5
interval = 10
failures = 3
startup_timeout = 30
EOF

# Deploy with health checks
speiihos host-dynamic
```

### Other Frameworks

#### Laravel (PHP)

```bash
speiihos host-dynamic --subdomain laravelapp --port 8000 \
  --run "php artisan serve --host=127.0.0.1 --port=8000"
```

#### Flask (Python)

```bash
speiihos host-dynamic --subdomain flaskapp --port 5000 \
  --run "gunicorn --bind 0.0.0.0:5000 app:app"
```

#### Nuxt (Vue SSR)

```bash
speiihos host-dynamic --subdomain nuxtapp --port 3000
# Auto-detects Nuxt, runs: node .output/server/index.mjs
```

---

## 5. Hosting Private APIs

### Core Concept

**APIs are PRIVATE by default!**
- No public domain assigned
- No Cloudflare DNS record created
- Runs only on `127.0.0.1:<port>`
- Requires explicit linking to expose publicly

### Step-by-Step: FastAPI Backend

#### Step 1: Create API Project

```bash
cd ~/projects/my-api

# Create requirements.txt
cat > requirements.txt << 'EOF'
fastapi>=0.104
uvicorn[standard]>=0.24
pydantic>=2.0
EOF

# Create main.py
cat > main.py << 'EOF'
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "ok"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/users")
def get_users():
    return {"users": ["Alice", "Bob"]}
EOF
```

#### Step 2: Host as Private Service

```bash
speiihos host-back --port 8000 --health-path /health --health-status 200
```

**Output:**
```
🔒 Hosting Private Backend Service
   Port: 8000
   Mode: Private (No public domain)

📦 Setting up Python environment...
   ✓ Created virtualenv
   ✓ Installed dependencies

🔧 Starting service...
   ✓ Process started (PID: 23456)
   ✓ Health check: http://127.0.0.1:8000/health → 200 OK

✅ Backend Service is ACTIVE!
   Endpoint: http://127.0.0.1:8000
   Public URL: None (private service)
   Health: Healthy
   Auto-restart: Enabled

💡 To expose publicly: speiihos link <frontend> api --prefix /api
```

#### Step 3: Link to Frontend (Optional)

```bash
# Make API accessible via your frontend domain
speiihos link portfolio api --prefix /api
```

**Now:**
```
https://portfolio.example.com/api/users
  → proxies to → http://127.0.0.1:8000/users
```

**Benefits:**
- ✓ Same origin (no CORS issues)
- ✓ Shared frontend HTTPS certificate
- ✓ Backend stays on private loopback
- ✓ Can unlink anytime: `speiihos unlink portfolio`

#### Step 4: Inspect Routes

```bash
speiihos inspect api

# Shows:
# Routes:
#   - Linked to: portfolio
#   - Public path: /api/*
#   - Backend: http://127.0.0.1:8000
```

### API Security Best Practices

#### 1. Always Implement Authorization

```python
# main.py - Add authentication
from fastapi import FastAPI, Header, HTTPException

app = FastAPI()

API_KEY = "your-secret-key"  # Use env var in production!

@app.get("/users")
def get_users(x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"users": ["Alice", "Bob"]}
```

#### 2. Use Environment Variables

```bash
# Create .env file (never commit this!)
cat > .env << 'EOF'
API_KEY=your-secret-key-here
DATABASE_URL=postgresql://user:pass@localhost/db
EOF

# Add to env_allow in speiihosting.toml
cat > speiihosting.toml << 'EOF'
schema_version = 1
type = "backend"
name = "api"
port = 8000
env_allow = ["DATABASE_URL"]

[health]
path = "/health"
expected_status = 200
EOF
```

#### 3. For Admin Dashboards: Use Cloudflare Access

```bash
# Host admin panel separately
speiihos host-dynamic --subdomain admin --port 9000

# Then configure in Cloudflare Dashboard:
# Access → Applications → Add an application
# Require email domain: @yourcompany.com
```

### Step-by-Step: Express.js API

```bash
cd ~/projects/node-api

# Create package.json
npm init -y
npm install express dotenv

# Create server.js
cat > server.js << 'EOF'
const express = require('express');
const app = express();
const port = process.env.PORT || 3001;

app.get('/health', (req, res) => {
  res.json({ status: 'healthy' });
});

app.get('/api/data', (req, res) => {
  res.json({ data: 'Hello World' });
});

app.listen(port, '127.0.0.1', () => {
  console.log(`API running on port ${port}`);
});
EOF

# Host privately
speiihos host-back --port 3001 --health-path /health
```

---

## 6. Hosting 24/7 Bots

### Use Case
Telegram bots, Discord bots, cron jobs, monitoring scripts.

### Step-by-Step: Telegram Bot

#### Step 1: Create Bot with BotFather

1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Follow prompts to name your bot
4. **Copy the bot token** (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

#### Step 2: Create Bot Code

```bash
cd ~/projects/telegram-bot

# Create requirements.txt
cat > requirements.txt << 'EOF'
python-telegram-bot>=20.0
python-dotenv>=1.0
EOF

# Create .env file (NEVER commit this!)
cat > .env << 'EOF'
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
EOF

# Create bot.py
cat > bot.py << 'EOF'
import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Hello! I am alive 24/7!')

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Pong!')

def main():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not found!")
    
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    
    print("Bot starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
EOF
```

#### Step 3: Host the Bot

```bash
# No port needed - bot polls Telegram servers
speiihos host-bot
```

**Output:**
```
🤖 Hosting Bot Service
   Detected: Python bot (bot.py)
   Mode: Long-polling (outbound only)

📦 Setting up environment...
   ✓ Created virtualenv
   ✓ Installed dependencies
   ✓ Loaded .env variables

🚀 Starting bot...
   ✓ Process started (PID: 34567)
   ✓ Running for 5 seconds - stable

✅ Bot is RUNNING 24/7!
   Service: telegram-bot
   PID: 34567
   Mode: Outbound (no port needed)
   Auto-restart: Enabled
   Survives: Terminal close, PC reboot

💡 Close this terminal safely - bot keeps running!
```

#### Step 4: Test Your Bot

1. Open Telegram
2. Find your bot by username
3. Send `/start` → Should reply "Hello! I am alive 24/7!"
4. Send `/ping` → Should reply "Pong!"

#### Step 5: Monitor Bot

```bash
# View live logs
speiihos logs telegram-bot -f

# Check bot status
speiihos list

# Inspect details
speiihos inspect telegram-bot
```

### Step-by-Step: Discord Bot

```bash
cd ~/projects/discord-bot

# Install dependencies
npm init -y
npm install discord.js dotenv

# Create .env
cat > .env << 'EOF'
DISCORD_BOT_TOKEN=your-discord-bot-token-here
EOF

# Create bot.js
cat > bot.js << 'EOF'
require('dotenv').config();
const { Client, GatewayIntentBits } = require('discord.js');

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent
  ]
});

client.on('ready', () => {
  console.log(`Logged in as ${client.user.tag}!`);
});

client.on('messageCreate', async (message) => {
  if (message.content === '!ping') {
    message.reply('Pong!');
  }
});

client.login(process.env.DISCORD_BOT_TOKEN);
EOF

# Host the bot
speiihos host-bot
```

### Webhook Mode (Optional)

If your bot needs to receive incoming HTTP webhooks:

```bash
# Host with webhook support
speiihos host-bot --webhook --port 8443 --subdomain mybot

# Now accessible at: https://mybot.example.com
```

---

## 7. Deployment & Updates

### Understanding the Deployment Model

**Key Concept: Isolated Staging**

```
Your working directory:
~/projects/myapp/          ← Edit code freely here
                             Auto-save, experiments, broken code OK!

SpeiiHosting live staging:
~/.speiihosting/sites/myapp/
  ├── live/                ← Production runs from here
  ├── previous/            ← Last working version (for rollback)
  ├── candidate/           ← New version during deployment
  └── data/                ← Persistent files (uploads, DBs)
```

### Step-by-Step: Deploying Updates

#### Step 1: Edit Your Code

```bash
cd ~/projects/my-portfolio

# Make changes in your editor
# VS Code auto-save? No problem!
# Test locally: npm run dev

# When ready, build
npm run build
```

#### Step 2: Preview Deployment

```bash
# See what will happen WITHOUT making changes
speiihos deploy --dry-run

# Output shows:
# - Files to copy
# - Build commands to run
# - Services to restart
# - Estimated downtime
```

#### Step 3: Deploy

```bash
# Deploy to live
speiihos deploy
```

**Deployment Process:**
```
📦 Preparing Deployment
   Service: portfolio
   Source: /Users/mac/projects/my-portfolio
   Target: ~/.speiihosting/sites/portfolio/

🔄 Backing up current release...
   ✓ live/ → previous/

🔨 Building in candidate directory...
   ✓ Copied source files
   ✓ Running: npm run build
   ✓ Build completed (12s)

🏥 Health Check (before promotion)...
   ✓ Staged build verified

🚀 Promoting to live...
   ✓ candidate/ → live/
   ✓ Nginx reloaded
   ✓ Health check: Passed

🌐 Purging Cloudflare cache...
   ✓ Edge cache cleared

✅ Deployment Successful!
   Version: live
   Rollback available: Yes (previous/)
   Health: Healthy
   URL: https://portfolio.example.com
```

#### Step 4: Verify Deployment

```bash
# Explicit HTTPS verification
speiihos verify portfolio

# Check in browser
# https://portfolio.example.com
```

### Rollback

#### Instant Rollback to Previous Version

```bash
# Something wrong? Rollback immediately
speiihos rollback portfolio
```

**Rollback Process:**
```
⏪ Rolling Back Service
   Service: portfolio
   Strategy: Offline rollback (no rebuild)

📋 Loading previous release metadata...
   ✓ Found: previous/ with complete dependencies

🔄 Swapping releases...
   ✓ live/ → .obsolete/
   ✓ previous/ → live/
   ✓ Restored runtime configuration

🚀 Starting restored version...
   ✓ No package installation needed
   ✓ Process started
   ✓ Health check: Passed

✅ Rollback Complete! (3 seconds)
   Now running: previous release
   Failed version: quarantined
```

**Key Benefits:**
- ✓ No package downloads
- ✓ No build commands
- ✓ Complete dependency snapshot
- ✓ Usually completes in <5 seconds

### Recovery from Interrupted Deploys

If deployment was interrupted (power loss, Ctrl+C, crash):

```bash
# Automatic recovery on next command
speiihos list
# → Detects interrupted deploy, auto-recovers

# Or manually:
speiihos recover

# Shows:
# - Services with pending recovery
# - Recovery actions taken
# - Final state
```

### Deployment Best Practices

#### 1. Always Test Locally First

```bash
# Test before deploying
cd ~/projects/myapp
npm run dev
# Test in browser at localhost

# Then deploy
speiihos deploy
```

#### 2. Use Health Checks

```toml
# speiihosting.toml
[health]
path = "/health"
expected_status = 200
expected_body = "ok"
```

Health checks prevent bad deploys from going live!

#### 3. Monitor Logs During Deploy

```bash
# In one terminal: deploy
speiihos deploy

# In another: watch logs
speiihos logs myapp -f
```

#### 4. Check Disk Space

```bash
# View disk usage
speiihos inspect myapp

# Shows:
# - Release size
# - Disk budget (default 4096 MB)
# - Data directory size
```

---

## 8. Monitoring & Logs

### Viewing Service Status

#### List All Services

```bash
speiihos list
```

**Output:**
```
NAME         TYPE      PORT    URL                              STATUS    HEALTH
portfolio    frontend  -       https://portfolio.example.com    Running   ✓
myapp        dynamic   3000    https://myapp.example.com        Running   ✓
api          backend   8000    (private)                        Running   ✓
telegram-bot bot       -       (outbound)                       Running   ✓
```

#### Detailed Inspection

```bash
speiihos inspect api --json
```

**Output:**
```json
{
  "name": "api",
  "type": "backend",
  "status": "running",
  "health": "healthy",
  "process": {
    "pid": 12345,
    "running": true,
    "uptime_seconds": 86400,
    "restart_count": 0
  },
  "resources": {
    "cpu_percent": 2.5,
    "memory_mb": 145,
    "memory_limit_mb": null
  },
  "routes": {
    "linked_to": "portfolio",
    "public_prefix": "/api",
    "target": "http://127.0.0.1:8000"
  },
  "disk": {
    "live_mb": 42,
    "previous_mb": 38,
    "data_mb": 256,
    "budget_mb": 4096
  },
  "health_config": {
    "path": "/health",
    "expected_status": 200,
    "interval_seconds": 5,
    "last_check": "2026-10-20T10:30:45Z",
    "consecutive_failures": 0
  }
}
```

### Working with Logs

#### View Recent Logs

```bash
# Last 100 lines (default)
speiihos logs api

# Last 500 lines
speiihos logs api -n 500

# All available logs
speiihos logs api -n 99999
```

#### Stream Live Logs

```bash
# Follow logs in real-time (like tail -f)
speiihos logs api -f

# Press Ctrl+C to stop (service keeps running!)
```

#### Build Logs vs Runtime Logs

```bash
# Runtime logs (stdout/stderr)
speiihos logs api

# Build logs (npm install, pip install, build commands)
speiihos logs api --build
```

#### Infrastructure Logs

```bash
# Nginx access logs (all HTTP requests)
speiihos logs nginx

# Nginx error logs
speiihos logs nginx -f

# Supervisor daemon
speiihos logs speii-daemon
```

### Log Management

#### Check Log Sizes

```bash
speiihos logs size
```

**Output:**
```
LOG FILE              TYPE                SIZE       LINES
portfolio.log         Frontend            1.2 MB     14,200
myapp.log             Dynamic Web         3.8 MB     42,100
api.log               Backend             0.8 MB      9,400
telegram-bot.log      Bot                 0.5 MB      6,300
nginx_access.log      Infrastructure      2.1 MB     22,000
nginx_error.log       Infrastructure      0.1 MB        450
speii-daemon.log      Supervisor          0.2 MB      1,800
────────────────────────────────────────────────────────
Total                                     8.7 MB

Note: Logs auto-rotate at 5 MB per file (10 MB total per service)
```

#### Clear Logs

```bash
# Clear specific service logs
speiihos logs clear api

# Clear nginx logs
speiihos logs clear nginx

# Clear all logs
speiihos logs clear --all
```

### Health Monitoring

#### Verify Public HTTPS

```bash
speiihos verify portfolio
```

**Output:**
```
🌐 Verifying Public Access
   URL: https://portfolio.example.com

✓ DNS Resolution: 104.21.12.34 (Cloudflare)
✓ HTTPS Connection: TLS 1.3
✓ HTTP Response: 200 OK
✓ Response Time: 245ms
✓ Content-Type: text/html

Last Verified: 2026-10-20 10:45:23 UTC

✅ Public URL is accessible!
```

#### Monitor Health Status

```bash
# Health checks run automatically every 5 seconds (configurable)

# View current health
speiihos inspect api | grep health

# Health failures trigger auto-restart after threshold (default: 3)
```

### Performance Monitoring

```bash
# CPU and Memory usage
speiihos list

# Detailed per-service
speiihos inspect myapp

# Watch for high restart counts (indicates crashes)
# Restart count: 0 = stable
# Restart count: >5 = investigate logs
```

---

## 9. Advanced Configuration

### Project Manifests

#### Creating a Manifest

```bash
cd ~/projects/myapp

speiihos project init --type backend
# Creates: speiihosting.toml
```

#### Complete Manifest Example

```toml
# speiihosting.toml
schema_version = 1

# Service identity
type = "backend"
name = "api"
port = 8000

# Build and runtime
run = "uvicorn main:app --host 0.0.0.0 --port 8000"
# build = "npm run build"  # For frontends

# Environment
env_allow = [
  "DATABASE_URL",
  "REDIS_URL",
  "SMTP_HOST"
]

# Dependencies
strict_dependencies = false  # true = require lockfiles with hashes

# Health monitoring
[health]
path = "/health"
expected_status = 200
expected_body = "ok"
timeout = 2
interval = 5
failures = 3
startup_timeout = 30

# Container isolation (Linux + Podman)
# [isolation]
# mode = "podman"
# image = "registry.io/myapp@sha256:abc123..."
# memory_mb = 512
# cpus = 1
# pids = 128

# Linking
# frontend = "portfolio"  # Auto-link to this frontend
# backend = "api"         # Or link this backend to me
```

#### Validating Manifest

```bash
speiihos project validate

# Checks:
# - Schema version supported
# - Required fields present
# - Port numbers valid
# - No reserved environment variables
# - Health check configuration valid
```

### Container Isolation (Linux + Podman)

#### Prerequisites

```bash
# Install Podman (Ubuntu/Debian)
sudo apt install podman

# Enable rootless mode
sudo sysctl kernel.unprivileged_userns_clone=1

# Configure cgroup v2
sudo mkdir -p /etc/systemd/system/user@.service.d
cat | sudo tee /etc/systemd/system/user@.service.d/delegate.conf << 'EOF'
[Service]
Delegate=cpu memory pids
EOF
sudo systemctl daemon-reload
```

#### Build and Push Image

```bash
# Build your app image
cd ~/projects/myapp

cat > Dockerfile << 'EOF'
FROM python:3.12-slim
WORKDIR /app
# Install dependencies at build time
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Note: app code will be mounted at runtime
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

# Build with digest
podman build -t registry.io/myapp:v1 .
podman push registry.io/myapp:v1

# Get digest (SHA256)
podman inspect registry.io/myapp:v1 | grep Digest
# Example: sha256:abc123def456...
```

#### Host with Container

```bash
speiihos host-back --port 8000 \
  --isolation podman \
  --image 'registry.io/myapp@sha256:abc123def456...' \
  --memory-mb 512 \
  --cpus 1 \
  --pids 128 \
  --health-path /health
```

**Container Benefits:**
- ✓ Read-only filesystem (except /data and /tmp)
- ✓ No capabilities (no privileged operations)
- ✓ CPU/memory/PID limits enforced
- ✓ Process isolation from host
- ✓ Predictable resource usage

### Global Configuration

#### View Current Config

```bash
speiihos config show
```

#### Change Settings

```bash
# Nginx port (default: 8080)
speiihos config set nginx_port 8080

# Release disk budget per site (default: 4096 MB)
speiihos config set release_budget_mb 8192

# Metrics write interval (default: 2 seconds, range: 1-60)
speiihos config set metrics_interval 5

# Credential storage (default: file)
pip install '.[secrets]'
speiihos config set credential_store keyring

# Auto-start on boot (default: true)
speiihos config set autostart on

# Sleep prevention (default: off)
speiihos config set sleep_prevent on
```

### Sleep Prevention (Laptop Hosting)

#### Enable Sleep Prevention

```bash
speiihos config set sleep_prevent on
```

**What this does per platform:**

- **Linux**: Configures systemd logind to ignore lid close
  ```bash
  # /etc/systemd/logind.conf
  HandleLidSwitch=ignore
  HandleLidSwitchExternalPower=ignore
  ```

- **macOS**: Runs caffeinate (hardware-dependent)
  ```bash
  # Keeps system awake, but closed-lid networking varies by model
  ```

- **Windows**: Sets power policy to do nothing on lid close
  ```powershell
  powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
  ```

**Caveats:**
- Battery drain on laptops
- Overheating if poorly ventilated
- macOS closed-lid Ethernet may not work on all models

### Strict Dependency Mode

#### Enable Strict Mode

```toml
# speiihosting.toml
strict_dependencies = true
```

**Requirements when strict mode is ON:**

**For Node.js:**
- Must have `package-lock.json`
- Uses `npm ci` (exact versions)

**For Python:**
- Must have `requirements.lock` or hashed `requirements.txt`
- Example requirements.txt:
  ```
  fastapi==0.104.1 \
      --hash=sha256:abc123...
  uvicorn[standard]==0.24.0 \
      --hash=sha256:def456...
  ```
- Uses `pip install --require-hashes --only-binary=:all:`

#### Generate Locked Requirements

```bash
# Python with pip-tools
pip install pip-tools
pip-compile --generate-hashes requirements.in

# Or use uv
uv pip compile requirements.in --generate-hashes > requirements.txt

# Node.js
npm install  # Generates package-lock.json automatically
```

---

## 10. Troubleshooting

### Common Issues

#### Issue: "Invalid input. Check names, domains, ports..." during setup

**Symptoms:**
```
Root domain on Cloudflare: CNAME
Invalid input. Check names, domains, ports and setting values.
```

**Cause:**
You entered "CNAME" (a DNS record type) instead of an actual domain name.

**Solution:**
```bash
# Run setup again
speiihos setup

# When prompted "Root domain on Cloudflare:", enter a real domain:
# ✅ CORRECT: example.com
# ✅ CORRECT: mydomain.net
# ❌ WRONG: CNAME
# ❌ WRONG: www.example.com (enter root domain, not subdomain)
# ❌ WRONG: https://example.com (no protocol)
```

**Requirements for the domain:**
1. You must own it
2. It must be added to your Cloudflare account (at https://dash.cloudflare.com)
3. DNS must be managed by Cloudflare (nameservers pointing to Cloudflare)

**Alternative:** Skip the prompt by providing domain directly:
```bash
speiihos setup --domain yourdomain.com
```

**Don't have a domain on Cloudflare?**
1. Go to https://dash.cloudflare.com
2. Click "Add a Site"
3. Enter your domain
4. Follow nameserver setup instructions
5. Wait 5-10 minutes for DNS propagation
6. Then run `speiihos setup` again

---

#### Issue: "Port already in use"

**Symptoms:**
```
Error: Port 8000 is already in use
```

**Solutions:**
```bash
# Find what's using the port
# Linux/macOS:
lsof -i :8000

# Windows:
netstat -ano | findstr :8000

# Use a different port
speiihos host-back --port 8001

# Or stop the conflicting process
speiihos stop <name-on-that-port>
```

#### Issue: "Health check failed"

**Symptoms:**
```
Health check timeout: http://127.0.0.1:8000/health
```

**Solutions:**
```bash
# 1. Check if app is actually running
speiihos inspect api

# 2. Test health endpoint manually
curl http://127.0.0.1:8000/health

# 3. View application logs
speiihos logs api -n 200

# 4. Increase startup timeout
cat >> speiihosting.toml << 'EOF'
[health]
startup_timeout = 60
EOF

# 5. Disable health check temporarily (not recommended for production)
speiihos host-back --port 8000 --no-health
```

#### Issue: "Public URL not accessible"

**Symptoms:**
- Site works on `http://127.0.0.1:port`
- But `https://mysite.example.com` shows error

**Solutions:**
```bash
# 1. Check tunnel status
speiihos inspect mysite

# 2. Check Cloudflare dashboard
# - DNS record exists?
# - Proxy enabled (orange cloud)?

# 3. Verify explicitly
speiihos verify mysite

# 4. Check Nginx config
speiihos logs nginx

# 5. Restart tunnel
speiihos service restart
```

#### Issue: "Service keeps restarting"

**Symptoms:**
```
speiihos list
# Shows: Restart count: 15 (and climbing)
```

**Solutions:**
```bash
# 1. Check logs for crash reason
speiihos logs myservice -n 500

# 2. Check build logs
speiihos logs myservice --build

# 3. Test manually
cd ~/.speiihosting/sites/myservice/live
source .venv/bin/activate
# Run the command manually to see errors

# 4. Check dependencies installed
ls ~/.speiihosting/sites/myservice/live/node_modules
# or
ls ~/.speiihosting/sites/myservice/environments/*/lib/python*/site-packages

# 5. Common causes:
# - Missing environment variables
# - Port conflict
# - Database not accessible
# - Syntax error in code
```

#### Issue: "Out of disk space"

**Symptoms:**
```
Error: Release budget exceeded (4096 MB)
# or
Error: Less than 128 MB free space
```

**Solutions:**
```bash
# 1. Check current usage
speiihos inspect --all

# 2. Clean previous releases
speiihos clean --all

# 3. Clear logs
speiihos logs clear --all

# 4. Increase budget
speiihos config set release_budget_mb 8192

# 5. Remove unused services
speiihos remove old-service
```

### Getting Help

#### Collect Diagnostic Info

```bash
# Service status
speiihos list --json > status.json

# Detailed inspection
speiihos inspect myservice --json > myservice.json

# Recent logs
speiihos logs myservice -n 500 > myservice.log
speiihos logs nginx -n 200 > nginx.log

# System info
speiihos --version
python --version
nginx -v
cloudflared --version
```

#### Check Configuration

```bash
# View all settings
cat ~/.speiihosting/config.json
cat ~/.speiihosting/services.json

# Check project manifest
cat speiihosting.toml
```

#### Common Log Patterns

**Application started successfully:**
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

**Health check passed:**
```
[speiihos] Health check: http://127.0.0.1:8000/health → 200 OK
```

**Common error patterns:**
```
ModuleNotFoundError: No module named 'fastapi'
→ Dependencies not installed

Error: EADDRINUSE: address already in use :::3000
→ Port conflict

django.db.utils.OperationalError: could not connect to server
→ Database not accessible
```

---

## Quick Reference

### Essential Commands

```bash
# Setup
speiihos init                          # First-time setup

# Hosting
speiihos host-front --subdomain NAME   # Static site
speiihos host-dynamic --subdomain NAME --port PORT  # Web app
speiihos host-back --port PORT         # Private API
speiihos host-bot                      # Bot/worker

# Management
speiihos list                          # List all services
speiihos inspect NAME                  # Detailed info
speiihos start/stop/restart NAME       # Control services
speiihos verify NAME                   # Test public URL

# Deployment
speiihos deploy                        # Deploy updates
speiihos rollback NAME                 # Undo deployment
speiihos recover                       # Fix interrupted deploy

# Monitoring
speiihos logs NAME -f                  # Stream logs
speiihos logs NAME --build             # Build logs
speiihos logs size                     # Check log sizes

# Maintenance
speiihos clean NAME                    # Remove old releases
speiihos remove NAME                   # Delete service
speiihos logs clear --all              # Clear all logs

# Configuration
speiihos project init --type TYPE      # Create manifest
speiihos config set KEY VALUE          # Change settings
```

### File Locations

```
~/.speiihosting/
├── config.json              # Global settings
├── credentials.json         # API tokens (private)
├── services.json            # Service registry
├── sites/
│   └── <name>/
│       ├── live/            # Running code
│       ├── previous/        # Rollback snapshot
│       ├── candidate/       # Staging during deploy
│       └── data/            # Persistent storage
└── logs/
    ├── <name>.log           # Runtime logs
    ├── <name>.build.log     # Build logs
    ├── nginx_access.log     # HTTP requests
    └── nginx_error.log      # Proxy errors
```

---

## Next Steps

1. **Join the Community** (when available)
   - GitHub Discussions
   - Discord Server
   - Issue Tracker

2. **Explore Advanced Topics**
   - [Technical Documentation](documentation.md)
   - [Implementation Plan](plan.txt)
   - [Changelog](CHANGELOG.md)

3. **Contribute**
   - Report bugs
   - Suggest features
   - Submit pull requests

---

**Happy Self-Hosting! 🚀**

*For questions or issues, check [documentation.md](documentation.md) or open a GitHub issue.*
