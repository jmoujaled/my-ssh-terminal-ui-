# SSH Terminal Web UI

A browser-based SSH client for remotely managing any server with SSH enabled. Connect from any device with a browser — no native SSH client needed.

Works with any SSH target — macOS, Linux, cloud VPS (Hostinger, DigitalOcean, AWS, etc.), Raspberry Pi, or any machine running an SSH server. Built as a lightweight alternative to native SSH clients and tools like Apple Screen Sharing.

> **Warning:** This project is intended for **personal LAN or VPN use only**. It is not hardened for public internet exposure. Do not expose this application to the open internet without proper authentication, HTTPS, and network-level access controls. See [Security Considerations](#security-considerations) below.

---

## Purpose

Manage any server from anywhere through a real terminal experience in the browser. Designed for:

- **Local servers** — macOS/Linux machines over LAN (e.g. `192.x.x.x`) or Tailscale VPN (e.g. `100.x.x.x`)
- **Cloud VPS** — Hostinger, DigitalOcean, AWS EC2, Linode, Hetzner, or any provider with SSH access
- Running system administration commands (disk, memory, processes)
- Managing Docker containers and compose stacks
- Monitoring and controlling OpenClaw gateway services
- Quick access to frequently used commands via a sidebar

---

## Screenshots

The UI features a dark GitHub-inspired theme with:
- **Connection bar** at the top (host, port, username, password, connect/disconnect, status indicator)
- **Saved commands sidebar** on the left with collapsible categories
- **Full xterm.js terminal** taking up the main area

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend terminal** | [xterm.js](https://xtermjs.org/) v5.5.0 | Browser-based terminal emulator |
| **Terminal addons** | FitAddon v0.10.0, WebLinksAddon v0.11.0 | Auto-resize terminal, clickable URLs |
| **Backend server** | [FastAPI](https://fastapi.tiangolo.com/) | WebSocket + REST API server |
| **ASGI server** | [Uvicorn](https://www.uvicorn.org/) | Runs the FastAPI application |
| **SSH library** | [Paramiko](https://www.paramiko.org/) | Python SSH2 protocol implementation |
| **Transport** | WebSocket | Bidirectional real-time communication |
| **Styling** | Vanilla CSS | GitHub dark theme, no build tools needed |

---

## Architecture

The core design is a **raw PTY pipe** — no output parsing, no sentinels, no ANSI stripping. Raw bytes flow directly between the browser and the SSH shell:

```
xterm.js (browser)  <-->  WebSocket  <-->  FastAPI  <-->  Paramiko channel (SSH PTY)
```

### How it works

1. **User connects** — Frontend sends connection details (host, port, username, password) over WebSocket
2. **Backend opens SSH** — Paramiko connects to the server and opens an interactive shell via `invoke_shell()` with `xterm-256color` terminal type
3. **Two concurrent async tasks** stream data bidirectionally:
   - `ssh_to_ws`: Reads raw bytes from the SSH channel, sends as text to the WebSocket
   - `ws_to_ssh`: Reads WebSocket messages (keystrokes, resize events), writes to the SSH channel
4. **xterm.js renders everything** — All ANSI escape codes, colors, cursor movement, prompts, tab completion, etc. are handled natively by xterm.js

### WebSocket message protocol

| Direction | Type | Format | Purpose |
|-----------|------|--------|---------|
| Client -> Server | `connect` | JSON | Send connection credentials |
| Client -> Server | `input` | JSON `{type: 'input', data: '...'}` | Forward keystrokes |
| Client -> Server | `resize` | JSON `{type: 'resize', cols: N, rows: N}` | Resize PTY |
| Client -> Server | `disconnect` | JSON | Close SSH session |
| Server -> Client | `connected` | JSON | Connection success |
| Server -> Client | `error` | JSON `{type: 'error', data: '...'}` | Error message |
| Server -> Client | `disconnected` | JSON | Session ended |
| Server -> Client | raw text | Plain string | Terminal output (written directly to xterm.js) |

---

## Project Structure

```
simple ssh ui/
├── app.py                              # FastAPI server (WebSocket SSH proxy + REST API)
├── ssh_manager.py                      # Paramiko SSH wrapper (connect, read, write, resize)
├── config.py                           # Env-based configuration (loads .env, parses settings)
├── auth.py                             # Session token creation/verification, password checking
├── middleware.py                       # IP allowlist + auth middleware (opt-in)
├── saved_commands.json                 # Saved commands data (JSON)
├── requirements.txt                    # Python dependencies
├── .env.example                        # Template for security env vars (copy to .env)
├── com.user.ssh-terminal-ui.plist      # macOS LaunchAgent (auto-start on boot)
├── RUNBOOK.md                          # Operations runbook (start/stop/logs/troubleshooting)
├── static/
│   ├── index.html                      # Full UI (HTML + CSS + JavaScript, single file)
│   └── login.html                      # Login page (shown when auth is enabled)
├── logs/
│   ├── stdout.log                      # Application stdout (created at runtime)
│   └── stderr.log                      # Application stderr (created at runtime)
└── README.md
```

### File breakdown

**`ssh_manager.py`** (~115 lines)
Simple Paramiko wrapper class with no output parsing:
- `connect()` — Opens SSH connection + interactive shell with PTY
- `read()` — Non-blocking read from the shell channel (returns raw bytes)
- `write()` — Sends raw bytes to the shell channel (user keystrokes)
- `resize()` — Resizes the PTY to match frontend terminal dimensions
- `is_active()` — Checks if the SSH channel is still alive
- `disconnect()` — Closes channel and SSH client

**`app.py`** (~185 lines)
FastAPI application with two main components:
- **WebSocket endpoint** (`/ws/ssh`) — Bidirectional SSH streaming with two concurrent async tasks
- **REST API** — CRUD for saved commands (`GET/POST/DELETE /api/commands`)
- Uses `ThreadPoolExecutor` for running blocking Paramiko reads in async context

**`static/index.html`** (~895 lines, single file)
Complete frontend with no build step:
- xterm.js terminal with GitHub dark theme
- Connection bar with live status indicator (connecting/connected/disconnected)
- Saved commands sidebar with collapsible categories and command counts
- Add command modal with category combo-box (autocomplete from existing categories)
- ResizeObserver for automatic terminal fitting
- localStorage persistence for connection details and collapsed category state

**`saved_commands.json`**
JSON file with 34+ pre-configured commands across 7 categories.

---

## Saved Command Categories

| Category | Commands | Description |
|----------|----------|-------------|
| **System** | 6 | `whoami`, `uptime`, `df -h`, `vm_stat`, `ps aux`, `sw_vers` |
| **Docker** | 5 | `docker ps`, `docker ps -a`, `docker images`, `docker compose ps`, `docker compose up -d` |
| **Files** | 3 | `ls -la`, `pwd`, `du -sh *` |
| **Network** | 3 | `ifconfig`, `netstat`, `tailscale status` |
| **OpenClaw** | 14 | Gateway start/stop/restart, health, status, doctor, version, launchctl, curl health endpoint, log viewing |
| **OpenClaw Scripts** | 4 | Update script, help, list backups, rollback |

Commands are clicked in the sidebar to **type them into the terminal** without auto-executing — you press Enter to run them.

---

## Features

- **Real terminal experience** — Full xterm.js rendering with colors, prompts, tab completion, scrollback
- **Persistent shell session** — `cd` persists, environment variables work, login shell with full PATH
- **Saved commands sidebar** — Click to pre-fill commands, grouped by collapsible categories
- **Add new commands** — Modal with category autocomplete (type to filter existing categories or create new ones)
- **Connection persistence** — Host, port, and username saved to localStorage (never password)
- **Auto-resize** — Terminal automatically fits the browser window, PTY resizes to match
- **Clickable URLs** — URLs in terminal output are clickable via WebLinksAddon
- **Live connection status** — Visual indicator (green dot = connected, yellow pulse = connecting, grey = disconnected)
- **Dark theme** — GitHub-inspired dark color scheme throughout

---

## Setup & Installation

### Prerequisites

- **Python 3.8+** on the machine running the web server
- **SSH enabled** on the target macOS server (System Settings > General > Sharing > Remote Login)
- Network access to the server (Tailscale or LAN)

### Install

```bash
cd "simple ssh ui"
pip install -r requirements.txt
```

### Option 1: Run locally (manual)

Run it on demand from the terminal. Good for development or one-off use:

```bash
python3 -m uvicorn app:app --reload --host 0.0.0.0 --port 8080
```

Then open `http://localhost:8080` in your browser. The `--reload` flag auto-restarts the server when you edit code.

### Option 2: Install as a LaunchAgent (always running)

If you want the SSH Terminal UI to start automatically every time you log in and stay running in the background, install it as a macOS LaunchAgent. This runs on **port 2222** to avoid conflicts with dev servers (3000, 5173, 8000, 8080) and OpenClaw (18789).

```bash
# Create the logs directory
mkdir -p "/Users/user/Dev/simple ssh ui/logs"

# Copy the plist to LaunchAgents
cp com.user.ssh-terminal-ui.plist ~/Library/LaunchAgents/

# Load and start the service
launchctl load ~/Library/LaunchAgents/com.user.ssh-terminal-ui.plist
```

Then open `http://localhost:2222` in your browser — it's always available.

See **[RUNBOOK.md](RUNBOOK.md)** for all management commands (start, stop, restart, logs, troubleshooting).

### Connect

1. Enter your server's IP address or hostname
2. Enter port (default: `22`)
3. Enter your username and password
4. Click **Connect**

Works with any SSH target:

| Server type | Host example | Username |
|-------------|-------------|----------|
| Local Mac (LAN) | `192.168.1.249` | `jalel` |
| Local Mac (Tailscale) | `100.108.x.x` | `jalel` |
| Hostinger VPS | `154.41.x.x` | `root` |
| DigitalOcean Droplet | `167.99.x.x` | `root` |
| AWS EC2 | `ec2-xx-xx.compute.amazonaws.com` | `ubuntu` |
| Raspberry Pi | `192.168.1.x` | `pi` |

---

## API Reference

### WebSocket

- `ws://localhost:8000/ws/ssh` — SSH terminal session

### REST Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/commands` | List all saved commands |
| `POST` | `/api/commands` | Add a new command (`{label, cmd, category}`) |
| `DELETE` | `/api/commands/{id}` | Delete a saved command |

---

## Security Considerations

This tool provides **direct SSH access through a WebSocket proxy**. It includes built-in opt-in security features and should be deployed with proper precautions.

### Built-in security features (opt-in via environment variables)

All security features are **disabled by default** so the app works out of the box. Enable them by creating a `.env` file (see `.env.example`):

| Env Variable | Purpose | Default |
|-------------|---------|---------|
| `SSH_TERMINAL_ADMIN_PASSWORD` | Set a password to enable the login page. Users must authenticate before accessing the terminal. | Not set (open access) |
| `SSH_TERMINAL_SESSION_TIMEOUT` | Idle session timeout in minutes. After this period of inactivity, the session expires and the user is redirected to the login page. | `30` |
| `SSH_TERMINAL_SECRET_KEY` | Secret key for signing session cookies. Auto-generated on startup if not set (sessions won't survive restarts). | Auto-generated |
| `SSH_TERMINAL_ALLOWED_IPS` | Comma-separated IP/CIDR allowlist. Only listed IPs can access the app. Supports single IPs and subnets. | Not set (all IPs allowed) |

**Quick start — enable login with one env var:**

```bash
# Copy the template
cp .env.example .env

# Edit .env and uncomment:
SSH_TERMINAL_ADMIN_PASSWORD=your-strong-password-here
```

Restart the server and a login page will appear. No code changes needed.

### Recommended deployment

- Behind a **reverse proxy** (Nginx, Caddy) with HTTPS
- Accessible only via **VPN** (Tailscale, WireGuard) or trusted LAN
- **Admin password enabled** via `SSH_TERMINAL_ADMIN_PASSWORD`
- **IP allowlisting** via `SSH_TERMINAL_ALLOWED_IPS` and/or firewall rules
- **Rate limiting** enabled at the reverse proxy level

### What this application does NOT do

- **No command sandboxing** — Commands run with full privileges of the SSH user
- **No SSH host key verification** — Uses Paramiko's `AutoAddPolicy` (accepts any host key on first connect)
- **No credential storage** — SSH passwords are never saved to disk or localStorage (by design)
- **No session logging/audit** — SSH sessions are not recorded
- **No user management** — Single admin password, no individual user accounts

### Threat model

| Concern | Responsibility | Notes |
|---------|---------------|-------|
| Web UI authentication | **Built-in** (opt-in) | Set `SSH_TERMINAL_ADMIN_PASSWORD` to enable login page |
| IP-based access control | **Built-in** (opt-in) | Set `SSH_TERMINAL_ALLOWED_IPS` to restrict by IP/CIDR |
| Session idle timeout | **Built-in** (opt-in) | Set `SSH_TERMINAL_SESSION_TIMEOUT` (default: 30 min) |
| SSH credential security | **SSH protocol** | Credentials are handled by Paramiko over the SSH channel |
| Transport encryption | **You** (deployer) | Use HTTPS/WSS via reverse proxy with TLS certificates |
| Command authorization | **SSH server** | The remote server's user permissions govern what commands can run |
| Network access control | **You** (deployer) | Additionally restrict via firewall, VPN, or reverse proxy |
| Host key verification | **Not implemented** | Suitable for trusted networks; not safe for untrusted networks |

### Summary

This application is a **transparent SSH proxy** — it connects you to an SSH server and passes data through. Built-in security features (login page, session expiry, IP allowlist) protect access to the web UI. All command-level security (user permissions, command restrictions) is handled by the target SSH server.

---

## Deployment

### Local development

Run on demand — no configuration needed:

```bash
python3 -m uvicorn app:app --reload --host 0.0.0.0 --port 8080
```

### Behind Nginx (recommended for persistent use)

Example Nginx config with basic auth and HTTPS:

```nginx
server {
    listen 443 ssl;
    server_name ssh-terminal.local;

    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # Basic authentication
    auth_basic "SSH Terminal";
    auth_basic_user_file /etc/nginx/.htpasswd;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=ssh_terminal:10m rate=10r/s;
    limit_req zone=ssh_terminal burst=20 nodelay;

    location / {
        proxy_pass http://127.0.0.1:2222;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket support (required for terminal to work)
    location /ws/ {
        proxy_pass http://127.0.0.1:2222;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
```

Generate the `.htpasswd` file:

```bash
# Install htpasswd if needed (macOS)
brew install httpd

# Create password file
htpasswd -c /etc/nginx/.htpasswd yourusername
```

### Tailscale-only access (simplest secure option)

If you run this on a machine with Tailscale, bind to the Tailscale interface only:

```bash
python3 -m uvicorn app:app --host 100.108.208.57 --port 2222
```

This makes the UI accessible **only** from devices on your Tailscale network — no Nginx or HTTPS needed since Tailscale encrypts all traffic with WireGuard.

### IP allowlisting (macOS firewall)

Restrict access to specific IPs using the macOS packet filter:

```bash
# Allow only your LAN subnet and Tailscale
echo "block in on en0 proto tcp to port 2222
pass in on en0 proto tcp from 192.168.1.0/24 to port 2222
pass in on utun4 proto tcp to port 2222" | sudo pfctl -ef -
```

---

## Dependencies

```
fastapi          # Web framework with WebSocket support
uvicorn[standard] # ASGI server
paramiko         # SSH2 protocol library
```

Frontend dependencies loaded from CDN (no npm/build step):
- `@xterm/xterm@5.5.0`
- `@xterm/addon-fit@0.10.0`
- `@xterm/addon-web-links@0.11.0`
