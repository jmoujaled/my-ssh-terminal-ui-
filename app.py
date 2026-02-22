import json
import uuid
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ssh_manager import SSHManager
from config import settings
from auth import check_password, create_session, verify_session
from middleware import IPAllowlistMiddleware, AuthMiddleware

app = FastAPI()
executor = ThreadPoolExecutor(max_workers=8)

COMMANDS_FILE = Path(__file__).parent / "saved_commands.json"


# --- Middleware (opt-in, only active when env vars are set) ---

if settings.allowed_ips:
    app.add_middleware(
        IPAllowlistMiddleware,
        allowed_networks=settings.allowed_networks,
    )

if settings.auth_enabled:
    app.add_middleware(
        AuthMiddleware,
        secret_key=settings.secret_key,
        max_age_seconds=settings.session_timeout_minutes * 60,
    )


# --- Auth routes (only functional when SSH_TERMINAL_ADMIN_PASSWORD is set) ---

@app.get("/login")
async def login_page():
    if not settings.auth_enabled:
        return RedirectResponse("/")
    return FileResponse(Path(__file__).parent / "static" / "login.html")


@app.post("/api/auth/login")
async def login(request: Request):
    if not settings.auth_enabled:
        return JSONResponse({"detail": "Auth not enabled"}, status_code=400)

    body = await request.json()
    password = body.get("password", "")

    if not check_password(password):
        return JSONResponse({"detail": "Invalid password"}, status_code=401)

    token = create_session(settings.secret_key, settings.session_timeout_minutes)
    response = JSONResponse({"ok": True})
    response.set_cookie(
        key="ssh_terminal_session",
        value=token,
        httponly=True,
        samesite="strict",
        max_age=settings.session_timeout_minutes * 60,
        secure=request.url.scheme == "https",
    )
    return response


@app.post("/api/auth/logout")
async def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("ssh_terminal_session")
    return response


# --- Static file serving ---

@app.get("/")
async def root():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


# --- WebSocket SSH endpoint ---

@app.websocket("/ws/ssh")
async def ssh_websocket(websocket: WebSocket):
    # --- Auth check for WebSocket (middleware doesn't cover WS reliably) ---
    if settings.auth_enabled:
        cookie_value = websocket.cookies.get("ssh_terminal_session")
        max_age = settings.session_timeout_minutes * 60
        if not cookie_value or not verify_session(cookie_value, settings.secret_key, max_age):
            await websocket.close(code=4401, reason="Unauthorized")
            return

    # --- IP check for WebSocket ---
    if settings.allowed_ips and not settings.is_ip_allowed(websocket.client.host):
        await websocket.close(code=4403, reason="Forbidden")
        return

    await websocket.accept()
    manager = SSHManager()
    loop = asyncio.get_event_loop()

    try:
        # Wait for connection details (JSON message)
        connect_msg = await websocket.receive_json()

        if connect_msg.get("type") != "connect":
            await websocket.send_json({"type": "error", "data": "Expected connect message"})
            return

        success, error = manager.connect(
            host=connect_msg["host"],
            port=int(connect_msg.get("port", 22)),
            username=connect_msg["username"],
            password=connect_msg.get("password"),
            key_path=connect_msg.get("key_path"),
            key_data=connect_msg.get("key_data"),
            cols=int(connect_msg.get("cols", 120)),
            rows=int(connect_msg.get("rows", 30)),
        )

        if not success:
            await websocket.send_json({"type": "error", "data": error})
            return

        await websocket.send_json({"type": "connected"})

        # Track last activity for idle timeout
        last_activity = loop.time()

        # --- Concurrent streaming tasks ---

        async def ssh_to_ws():
            """Read SSH channel output and forward to WebSocket."""
            while manager.is_active():
                data = await loop.run_in_executor(executor, manager.read)
                if data:
                    await websocket.send_text(data.decode("utf-8", errors="replace"))
                else:
                    await asyncio.sleep(0.02)

        async def ws_to_ssh():
            """Read WebSocket messages and forward to SSH channel."""
            nonlocal last_activity
            while True:
                msg = await websocket.receive()
                last_activity = loop.time()

                if msg.get("type") == "websocket.disconnect":
                    break

                text = msg.get("text", "")
                if text:
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, dict):
                            if parsed.get("type") == "resize":
                                cols = int(parsed.get("cols", 120))
                                rows = int(parsed.get("rows", 30))
                                await loop.run_in_executor(
                                    executor,
                                    lambda: manager.resize(cols, rows)
                                )
                                continue
                            elif parsed.get("type") == "disconnect":
                                break
                            elif parsed.get("type") == "input":
                                manager.write(parsed["data"].encode("utf-8"))
                                continue
                    except (json.JSONDecodeError, ValueError):
                        pass

                    manager.write(text.encode("utf-8"))

                bdata = msg.get("bytes")
                if bdata:
                    manager.write(bdata)

        async def idle_watchdog():
            """Close connection if idle too long (only when auth is enabled)."""
            timeout_seconds = settings.session_timeout_minutes * 60
            while True:
                await asyncio.sleep(30)  # Check every 30 seconds
                elapsed = loop.time() - last_activity
                if elapsed > timeout_seconds:
                    try:
                        await websocket.send_json({
                            "type": "error",
                            "data": "Session expired due to inactivity"
                        })
                    except Exception:
                        pass
                    break

        # Build task list
        tasks = [
            asyncio.create_task(ssh_to_ws()),
            asyncio.create_task(ws_to_ssh()),
        ]
        if settings.auth_enabled:
            tasks.append(asyncio.create_task(idle_watchdog()))

        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "data": str(e)})
        except Exception:
            pass
    finally:
        manager.disconnect()


# --- Saved commands REST API ---

def _load_commands():
    try:
        with open(COMMANDS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_commands(commands):
    with open(COMMANDS_FILE, "w") as f:
        json.dump(commands, f, indent=2)


@app.get("/api/commands")
async def get_commands():
    return _load_commands()


class CommandCreate(BaseModel):
    label: str
    cmd: str
    category: str = "General"


@app.post("/api/commands")
async def add_command(command: CommandCreate):
    commands = _load_commands()
    new_cmd = {
        "id": str(uuid.uuid4())[:8],
        "label": command.label,
        "cmd": command.cmd,
        "category": command.category,
    }
    commands.append(new_cmd)
    _save_commands(commands)
    return new_cmd


@app.delete("/api/commands/{cmd_id}")
async def delete_command(cmd_id: str):
    commands = _load_commands()
    commands = [c for c in commands if c["id"] != cmd_id]
    _save_commands(commands)
    return {"ok": True}


# --- Entrypoint (supports built-in HTTPS/TLS via env vars) ---

if __name__ == "__main__":
    import uvicorn

    uvicorn_kwargs = {
        "app": "app:app",
        "host": settings.host,
        "port": settings.port,
    }

    if settings.ssl_certfile and settings.ssl_keyfile:
        uvicorn_kwargs["ssl_certfile"] = settings.ssl_certfile
        uvicorn_kwargs["ssl_keyfile"] = settings.ssl_keyfile
        print(f"Starting with HTTPS on port {settings.port}")
    else:
        print(f"Starting with HTTP on port {settings.port}")

    uvicorn.run(**uvicorn_kwargs)
