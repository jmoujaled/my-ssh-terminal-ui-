# SSH Terminal UI — Runbook

Operations guide for managing the SSH Terminal UI service running as a macOS LaunchAgent.

---

## Service Details

| Property | Value |
|----------|-------|
| **Service name** | `com.user.ssh-terminal-ui` |
| **Port** | `2222` |
| **URL** | `http://localhost:2222` |
| **Plist location** | `~/Library/LaunchAgents/com.user.ssh-terminal-ui.plist` |
| **Working directory** | `/Users/user/Dev/simple ssh ui` |
| **Stdout log** | `/Users/user/Dev/simple ssh ui/logs/stdout.log` |
| **Stderr log** | `/Users/user/Dev/simple ssh ui/logs/stderr.log` |
| **Auto-start** | Yes (runs on login) |
| **Auto-restart** | Yes (restarts if process dies) |

---

## Common Commands

### Check if the service is running

```bash
launchctl list | grep ssh-terminal
```

If running, you'll see output like:

```
56326   0   com.user.ssh-terminal-ui
```

- First column = PID (process ID)
- Second column = exit code (0 = healthy)
- Third column = service label

### Start the service

```bash
launchctl load ~/Library/LaunchAgents/com.user.ssh-terminal-ui.plist
```

### Stop the service

```bash
launchctl unload ~/Library/LaunchAgents/com.user.ssh-terminal-ui.plist
```

### Restart the service

```bash
launchctl kickstart -k gui/$(id -u)/com.user.ssh-terminal-ui
```

Or stop and start:

```bash
launchctl unload ~/Library/LaunchAgents/com.user.ssh-terminal-ui.plist
launchctl load ~/Library/LaunchAgents/com.user.ssh-terminal-ui.plist
```

### Check if the web server is responding

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:2222/
```

Should return `200`.

---

## Logs

### View recent logs

```bash
# Stderr (uvicorn access logs + errors)
tail -20 "/Users/user/Dev/simple ssh ui/logs/stderr.log"

# Stdout
tail -20 "/Users/user/Dev/simple ssh ui/logs/stdout.log"
```

### Watch logs in real-time

```bash
tail -f "/Users/user/Dev/simple ssh ui/logs/stderr.log"
```

### Clear logs

```bash
> "/Users/user/Dev/simple ssh ui/logs/stdout.log"
> "/Users/user/Dev/simple ssh ui/logs/stderr.log"
```

---

## Installation

### First-time setup

```bash
cd "/Users/user/Dev/simple ssh ui"

# Install Python dependencies
pip install -r requirements.txt

# Create logs directory
mkdir -p logs

# Copy plist to LaunchAgents
cp com.user.ssh-terminal-ui.plist ~/Library/LaunchAgents/

# Load the service (starts immediately)
launchctl load ~/Library/LaunchAgents/com.user.ssh-terminal-ui.plist
```

### Uninstall

```bash
# Stop and remove the LaunchAgent
launchctl unload ~/Library/LaunchAgents/com.user.ssh-terminal-ui.plist
rm ~/Library/LaunchAgents/com.user.ssh-terminal-ui.plist
```

### Update the plist after editing

If you modify `com.user.ssh-terminal-ui.plist`, reload it:

```bash
launchctl unload ~/Library/LaunchAgents/com.user.ssh-terminal-ui.plist
cp com.user.ssh-terminal-ui.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.user.ssh-terminal-ui.plist
```

---

## Troubleshooting

### Service won't start

1. **Check the plist is valid:**
   ```bash
   plutil -lint ~/Library/LaunchAgents/com.user.ssh-terminal-ui.plist
   ```

2. **Check if port 2222 is already in use:**
   ```bash
   lsof -i :2222
   ```

3. **Check Python/uvicorn is available:**
   ```bash
   python3 -m uvicorn --version
   ```

4. **Check the error log:**
   ```bash
   cat "/Users/user/Dev/simple ssh ui/logs/stderr.log"
   ```

### Service keeps restarting

The `KeepAlive` flag means macOS will restart the process if it exits. Check the error log for crash reasons:

```bash
tail -50 "/Users/user/Dev/simple ssh ui/logs/stderr.log"
```

Common causes:
- Missing Python dependencies → run `pip install -r requirements.txt`
- Port conflict → check `lsof -i :2222`
- File permission issues → check the working directory is accessible

### Can't connect to SSH from the terminal

- Verify SSH is enabled: **System Settings > General > Sharing > Remote Login**
- Test SSH directly: `ssh username@host`
- Check the target server is reachable: `ping host`
- Check Tailscale is running: `tailscale status`

### Browser shows WebSocket error

- Make sure the backend is running: `curl http://localhost:2222/`
- Check the browser console for errors (F12 > Console)
- Try refreshing the page

---

## Port Reference

Ports intentionally avoided to prevent conflicts:

| Port | Used by |
|------|---------|
| `2222` | **SSH Terminal UI (this app)** |
| `3000` | React / Next.js dev servers |
| `5173` / `5174` | Vite dev servers |
| `8000` | FastAPI / Django dev servers |
| `8080` | General dev / manual run mode |
| `18789` | OpenClaw gateway |
