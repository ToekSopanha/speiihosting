# Quick Start/Stop Reference

**SpeiiHosting System Control Commands**

---

## ⚡ Quick Commands

```bash
# Start everything
speiihos service start

# Stop everything  
speiihos service stop

# Check status
speiihos list
```

---

## 🎯 System Control

### Start the Supervisor

```bash
speiihos service start
```

**What happens:**
- ✅ Background supervisor daemon starts
- ✅ All previously running services auto-restart
- ✅ Nginx and Cloudflare Tunnel reconnect
- ✅ Sites become accessible at their URLs

**When to use:**
- After system reboot (if autostart disabled)
- After running `service stop`
- When you want to bring all services online

---

### Stop Everything

```bash
speiihos service stop
```

**What happens:**
- 🛑 All hosted apps stop gracefully
- 🛑 Nginx stops
- 🛑 Cloudflare Tunnel disconnects
- 🛑 Supervisor daemon stops
- ✅ Sites no longer accessible (clean shutdown)

**When to use:**
- Before system shutdown (optional, handled automatically)
- To save resources when not needed
- Troubleshooting system issues
- Before major system updates

---

### Check Status

```bash
speiihos list
```

**Example output (running):**
```
Name       Type       Target              Status   Health   Restarts  CPU    RAM
portfolio  frontend   /path/to/live       active   healthy  0         0.2%   45.3 MB
api        backend    127.0.0.1:8000      active   healthy  0         1.5%   128.7 MB
bot        bot        outbound            active   healthy  0         0.8%   89.2 MB
```

**Example output (stopped):**
```
Name       Type       Target              Status    Health    Restarts  CPU   RAM
portfolio  frontend   /path/to/live       stopped   unknown   0         0%    0 MB
api        backend    127.0.0.1:8000      stopped   unknown   0         0%    0 MB
```

**What to look for:**
- `Status: active` = Service running
- `Status: stopped` = Service offline
- `Health: healthy` = App responding correctly
- `Restarts: 0` = Stable (high number = crashes)

---

## 🔄 Individual Service Control

### Start One Service

```bash
# By name
speiihos start portfolio

# By port
speiihos start 8000
```

### Stop One Service

```bash
# By name
speiihos stop api

# By port
speiihos stop 3000
```

### Restart One Service

```bash
# Hard restart (brief downtime)
speiihos restart bot

# Zero-downtime restart (if supported)
speiihos reload api
```

**When to control individual services:**
- Testing one service without affecting others
- Applying config changes to specific app
- Debugging a problematic service
- Temporary disable without full removal

---

## 🚀 Autostart Configuration

### Enable Autostart (Default)

```bash
speiihos config set autostart on
```

**What this does:**
- Services automatically start when you log in
- Your sites stay online 24/7 after reboot
- No manual intervention needed
- **Creates system startup entry:**
  - **macOS:** `~/Library/LaunchAgents/io.speiihosting.daemon.plist`
  - **Linux:** `~/.config/systemd/user/speiihos.service`
  - **Windows:** Task Scheduler entry

**Recommended for:**
- Home servers
- Production deployments
- Always-on services
- Public-facing websites

---

### Disable Autostart

```bash
speiihos config set autostart off
```

**What this does:**
- Services will NOT start after reboot
- You must manually run `speiihos service start`
- Saves resources when not needed
- Good for development/testing

**Recommended for:**
- Laptops (save battery)
- Development machines
- Temporary testing setups
- Shared computers

---

### Check Autostart Status

```bash
# View autostart setting
speiihos config get autostart

# View all settings
speiihos config list
```

---

## 📋 Common Workflows

### For Always-On Server (Recommended)

```bash
# Initial setup (once)
speiihos init
speiihos config set autostart on  # Already default
speiihos host-front --subdomain mysite --dir dist

# That's it! Site stays online 24/7
# After reboot: services start automatically
```

---

### For Development Machine

```bash
# Disable autostart
speiihos config set autostart off

# Start when working
speiihos service start

# Stop when done for the day
speiihos service stop
```

---

### After System Reboot

**With autostart enabled (default):**
1. Log in to your computer
2. Wait ~30 seconds
3. Run `speiihos list` to verify
4. All services should show `active` ✅

**Without autostart:**
```bash
# Manually start after reboot
speiihos service start
```

---

### Emergency Stop

```bash
# Quick stop everything
speiihos service stop

# If that hangs, force kill (last resort)
pkill -9 -f speiihosting.daemon  # macOS/Linux
taskkill /F /IM python.exe       # Windows (stops all Python)
```

---

## 🔍 Troubleshooting

### Services Won't Start

```bash
# Check supervisor logs
speiihos logs speii-daemon

# Check specific service
speiihos logs myservice -n 200

# Try manual start with verbose output
speiihos start myservice
```

---

### Autostart Not Working After Reboot

```bash
# Re-register autostart
speiihos config set autostart off
speiihos config set autostart on

# Verify registration (macOS)
ls ~/Library/LaunchAgents/io.speiihosting.daemon.plist

# Verify registration (Linux)
systemctl --user status speiihos.service

# Verify registration (Windows)
schtasks /Query /TN io.speiihosting.daemon
```

---

### Check if Supervisor is Running

```bash
# Method 1: List services
speiihos list
# If you see CPU/RAM stats, supervisor is running

# Method 2: Check daemon directly
speiihos inspect speii-daemon

# Method 3: Check process (macOS/Linux)
ps aux | grep speiihosting.daemon

# Method 3: Check process (Windows)
tasklist | findstr python
```

---

## 💡 Pro Tips

1. **Always use `service stop` instead of killing processes**
   - Graceful shutdown prevents data corruption
   - Properly closes connections

2. **Enable autostart for production**
   - Your sites survive power outages
   - Automatic recovery after system updates

3. **Use `speiihos list` to monitor health**
   - Check daily or set up monitoring alerts
   - High restart count = investigate logs

4. **Individual service control is faster**
   - Don't restart everything to update one app
   - `speiihos restart myapp` is quicker

5. **Check logs after start/stop**
   ```bash
   speiihos service start
   speiihos logs speii-daemon -n 50
   ```

---

## 🆘 Need Help?

- Full guide: `USERGUIDE.md` (Section 3)
- Troubleshooting: `USERGUIDE.md` (Section 11)
- Quick help: `speiihos --help`
- Service help: `speiihos service --help`

---

**Last Updated:** 2026-10-20  
**Version:** 0.3.0
