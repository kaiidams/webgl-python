from typing import Mapping, Any
import uuid
from pathlib import Path
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse

nodes: Mapping[str, WebSocket] = {}
app = FastAPI()


@app.get("/")
async def root():
    with open(Path(__file__).parent / 'main.html') as fp:
        html = fp.read()
    return HTMLResponse(html)


@app.get("/test")
async def test():
    with open(Path(__file__).parent / 'test.html') as fp:
        html = fp.read()
    return HTMLResponse(html)


@app.get("/main.js")
async def script():
    
    with open(Path(__file__).parent / 'main.js') as fp:
        js = fp.read()
    return HTMLResponse(js, media_type="text/javascript")


async def route_message(source: str, data: Any) -> None:
    destination = data['destination']
    data['source'] = source
    if destination is None:
        for k, v in nodes.items():
            if source != k:
                websocket = v
                break
    else:
        websocket = nodes[destination]
    await websocket.send_json(data)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    source = str(uuid.uuid1())
    nodes[source] = websocket

    while True:
        data = await websocket.receive_json()
        if data['destination'] is None:
            if data["method"] == "__register__":
                del nodes[source]
                source = data['params'][0]
                nodes[source] = websocket
        else:
            await route_message(source, data)
