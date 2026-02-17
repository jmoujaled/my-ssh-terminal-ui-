import json
import uuid
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ssh_manager import SSHManager

app = FastAPI()
executor = ThreadPoolExecutor(max_workers=8)

COMMANDS_FILE = Path(__file__).parent / "saved_commands.json"


# --- Static file serving ---

@app.get("/")
async def root():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


# --- WebSocket SSH endpoint ---

@app.websocket("/ws/ssh")
async def ssh_websocket(websocket: WebSocket):
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
            cols=int(connect_msg.get("cols", 120)),
            rows=int(connect_msg.get("rows", 30)),
        )

        if not success:
            await websocket.send_json({"type": "error", "data": error})
            return

        await websocket.send_json({"type": "connected"})

        # Now switch to raw bidirectional streaming.
        # Two concurrent tasks:
        #   1. Read from SSH channel → send to WebSocket (as binary text)
        #   2. Read from WebSocket → write to SSH channel

        async def ssh_to_ws():
            """Read SSH channel output and forward to WebSocket."""
            while manager.is_active():
                data = await loop.run_in_executor(executor, manager.read)
                if data:
                    # Send as text (xterm.js expects text)
                    await websocket.send_text(data.decode("utf-8", errors="replace"))
                else:
                    await asyncio.sleep(0.02)

        async def ws_to_ssh():
            """Read WebSocket messages and forward to SSH channel."""
            while True:
                msg = await websocket.receive()

                if msg.get("type") == "websocket.disconnect":
                    break

                # Text messages: could be raw keystrokes or JSON control messages
                text = msg.get("text", "")
                if text:
                    # Try to parse as JSON (for control messages like resize/disconnect)
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
                                # Explicit input message
                                manager.write(parsed["data"].encode("utf-8"))
                                continue
                    except (json.JSONDecodeError, ValueError):
                        pass

                    # If not a JSON control message, treat as raw terminal input
                    manager.write(text.encode("utf-8"))

                # Binary messages: forward directly
                bdata = msg.get("bytes")
                if bdata:
                    manager.write(bdata)

        # Run both tasks concurrently; when either finishes, cancel the other
        ssh_task = asyncio.create_task(ssh_to_ws())
        ws_task = asyncio.create_task(ws_to_ssh())

        done, pending = await asyncio.wait(
            [ssh_task, ws_task],
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
