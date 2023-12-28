from typing import Mapping, Any
import logging
import uuid
from pathlib import Path
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2.0"

nodes: Mapping[str, WebSocket] = {}
app = FastAPI()


@app.get("/")
async def root():
    with open(Path(__file__).parent / 'main.html') as fp:
        html = fp.read()
    return HTMLResponse(html)


@app.get("/main.js")
async def script():
    
    with open(Path(__file__).parent / 'main.js') as fp:
        js = fp.read()
    return HTMLResponse(js, media_type="text/javascript")


async def route_message(packet: Any) -> None:
    to_addr = packet['to']
    websocket = nodes.get(to_addr)
    if websocket is None:
        raise ValueError("Unknown address")
    await websocket.send_json(packet)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    from_addr = None
    to_addr = None

    try:
        while True:
            packet = await websocket.receive_json()
            if packet.get('to') is None:
                body = packet['body']
                if not isinstance(body, list):
                    body = [body]
                for data in body:
                    if data["jsonrpc"] != PROTOCOL_VERSION:
                        raise ValueError("Unknown protocol version")
                    if "id" in data:
                        raise ValueError("ID is not allowed")
                    if data["method"] == "__listen__":
                        from_addr, = data['params']
                        nodes[from_addr] = websocket
                    elif data["method"] == "__connect__":
                        from_addr = str(uuid.uuid1())
                        nodes[from_addr] = websocket
                        to_addr, = data['params']
                    else:
                        raise ValueError("Unknown method")
            else:
                if from_addr is None:
                    raise ValueError("Not connected yet")
                if to_addr is not None and packet["to"] != to_addr:
                    raise ValueError("Unexpected address")
                packet["from"] = from_addr
                await route_message(packet)
    finally:
        if from_addr:
            del nodes[from_addr]
