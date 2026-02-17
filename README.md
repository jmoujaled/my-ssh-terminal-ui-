# SSH Terminal Web UI

A browser-based SSH client for remotely managing a macOS home server. Connect from any device with a browser — no native SSH client needed.

Built as a lightweight alternative to tools like Apple Screen Sharing for running terminal commands remotely, whether over Tailscale VPN or local LAN.

---

## Purpose

Manage a macOS home server from anywhere through a real terminal experience in the browser. Designed for:

- Running system administration commands (disk, memory, processes)
- Managing Docker containers and compose stacks
- Monitoring and controlling OpenClaw gateway services
- Quick access to frequently used commands via a sidebar
- Accessing the server over Tailscale (e.g. `100.x.x.x`) or LAN (e.g. `192.x.x.x`)

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
├── app.py                  # FastAPI server (WebSocket SSH proxy + REST API)
├── ssh_manager.py          # Paramiko SSH wrapper (connect, read, write, resize)
├── saved_commands.json     # Saved commands data (JSON)
├── requirements.txt        # Python dependencies
├── static/
│   └── index.html          # Full UI (HTML + CSS + JavaScript, single file)
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

### Run

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000` in your browser.

### Connect

1. Enter your server's IP address (Tailscale or LAN)
2. Enter port (default: `22`)
3. Enter your username and password
4. Click **Connect**

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

## Security Notes

- This application is intended for **local/private network use** (LAN or Tailscale)
- Passwords are transmitted over WebSocket — use behind HTTPS in production
- Passwords are **never** saved to localStorage or disk
- The server accepts any SSH host key (`AutoAddPolicy`) — suitable for trusted networks
- No authentication on the web UI itself — anyone who can reach port 8000 can attempt SSH connections

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
