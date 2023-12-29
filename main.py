from typing import Mapping, Any
import uuid
from pathlib import Path
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse

nodes: Mapping[str, WebSocket] = {}
app = FastAPI()


@app.get("/")
async def root():
    with open('main.html') as fp:
        html = fp.read()
    return HTMLResponse(html)


@app.get("/test")
async def test():
    with open('test.html') as fp:
        html = fp.read()
    return HTMLResponse(html)


@app.get("/main.js")
async def script():
    __file__
    with open('main.js') as fp:
        js = fp.read()
    return HTMLResponse(js, media_type="text/javascript")


async def route_message(sender_node: str, data: Any) -> None:
    receiver_node = data['receiver']
    data['sender'] = sender_node
    if receiver_node is None:
        for k, v in nodes.items():
            if sender_node != k:
                websocket = v
                break
    else:
        websocket = nodes[receiver_node]
    await websocket.send_json(data)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    sender_node = str(uuid.uuid1())
    nodes[sender_node] = websocket

    while True:
        data = await websocket.receive_json()
        print(data)
        if data['type'] == "register":
            del nodes[sender_node]
            sender_node = data['name']
            nodes[sender_node] = websocket
            await websocket.send_json({
                "id": data['id'],
                "receiver": sender_node,
                "type": "return",
            })
        else:
            await route_message(sender_node, data)
