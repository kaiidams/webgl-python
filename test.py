import asyncio
import websockets
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TransportWebsocket:
    def __init__(self, uri):
        self.uri = uri
        self.ws = None
        self.server = None
        self.serverProxies = {}

    async def run(self, server):
        self.server = server
        async with websockets.connect(self.uri) as self.ws:
            await self.send({
                "destination": None,
                "method": "__register__",
                "params": [server.name]
            })
        
            while True:
                data = await self.ws.recv()
                data = json.loads(data)
                logger.info('<-- %s', data)
                if "result" in data:
                    proxy = self.serverProxies[data["source"]]
                    proxy.onReceive(data)
                else:
                    await self.server.onReceive(data)

    async def send(self, data):
        logger.info('--> %s', data)
        data["dynbus"] = "0.1"
        await self.ws.send(json.dumps(data))

class Server:
    def __init__(self, name, transport):
        self.name = name
        self.transport = transport
        self.nextObjectId = 0
        self.liveObjects = {}
        self.global_ = None

    async def serve(self, app):
        self.global_ = app
        await self.transport.run(self)

    async def onReceive(self, data):
        params = self.unmarshalParams(data["params"])
        target = params.pop(0)
        if target is None:
            target = self.global_

        if data["method"] == "__getter__":
            name = params[1]
            result = getattr(target, name)
        else:
            method = getattr(target, data["method"])
            result = method(*params)

        await self.transport.send({
            "id": data["id"],
            "destination": data["source"],
            "result": self.marshalResult(result)
        })

    def unmarshalParams(self, params):
        def f(value):
            if isinstance(value, dict):
                return self.liveObjects[value.id]
            else:
                return value
        return [f(value) for value in params]

    def marshalResult(self, result):
        if result is None or type(result) in (int, float, str, bool):
            return result

        if not hasattr(result, "_objectId"):
            objectId = self.nextObjectId
            self.nextObjectId += 1
            self.liveObjects[objectId] = result
            result._objectId = objectId

        return {
            "id": result._objectId,
            "class": "object",
        }

class ServerProxy:
    def __init__(self, name, transport):
        self.transport = transport
        self.name = name
        self.nextRequestId = 0
        self.liveObjects = {}
        self.pendingRequests = {}
        self.transport.serverProxies[self.name] = self


    async def request(self, method, params):
        requestId = self.nextRequestId
        self.nextRequestId += 1
        await self.transport.send({
            "id": requestId,
            "destination": self.name,
            "method": method,
            "params": self.marshalParams(params),
        })
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self.pendingRequests[requestId] = fut
        return await fut

    def onReceive(self, data):
        fut = self.pendingRequests[data["id"]]
        del self.pendingRequests[data["id"]]
        fut.set_result(self.unmarshalResult(data["result"]))

    def unmarshalResult(self, result):
        if result is None or type(result) in (int, float, str, bool):
            return result
        assert isinstance(result, dict)
        return ObjectProxy(self, result["id"])

    def marshalParams(self, params):
        def f(value):
            if isinstance(value, ObjectProxy):
                return { "id": value.objectId }
            return value
        return [f(value) for value in params]


class ObjectProxy:
    def __init__(self, proxy, objectId):
        self.proxy = proxy
        self.objectId = objectId

    async def invoke(self, method, *args):
        args = list(args)
        args.insert(0, None if self.objectId is None else self)
        return await self.proxy.request(method, args)


class App():
    def __init__(self, proxy):
        self.proxy = proxy

    def start(self):
        print('hello')
        loop = asyncio.get_event_loop()
        loop.create_task(self.run())
        return True

    async def run(self):
        g = ObjectProxy(self.proxy, None)
        win = await g.invoke("__getter__", "window")
        while True:
            await win.invoke("alert", "hello")
            await asyncio.sleep(3)
            print('hello')


async def main():
    uri = "ws://localhost:8000/ws"
    transport = TransportWebsocket(uri)
    proxy = ServerProxy("server_a", transport)
    server = Server("server_c", transport)
    app = App(proxy)
    await server.serve(app)

    async with websockets.connect(uri) as websocket:
        await websocket.send(json.dumps({
            'destination': None,
            'method': '__register__',
            'params': ['server_c']
        }))
        while True:
            data = await websocket.recv()
            print(data)


if __name__ == "__main__":
    asyncio.run(main())
