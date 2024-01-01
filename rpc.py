from websockets.sync.client import connect
import json
from functools import partial
import logging

logger = logging.getLogger(__name__)


class ProxyException(Exception):
    pass


class TransportWebsocket:
    def __init__(self, uri):
        self.uri = uri
        self.ws = None
        self.server = None
        self.serverProxies = {}

    def __enter__(self):
        self.ws = connect(self.uri).__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.ws.__exit__(exc_type, exc_val, exc_tb)

    def run(self, server):
        self.server = server
        with connect(self.uri) as self.ws:
            self.send({
                "destination": None,
                "method": "__register__",
                "params": [server.name]
            })

            while True:
                self.wait_until(None, None)

    def wait_until(self, source, request_id):
        while True:
            data = self.ws.recv()
            data = json.loads(data)
            logger.info('<-- %s', data)
            assert data["jsonrpc"] == "pywebgl-0.1"
            if "error" in data:
                if source and data["source"] == source and data["id"] == request_id:
                    return data
            elif "result" in data:
                if source and data["source"] == source and data["id"] == request_id:
                    return data
                proxy = self.serverProxies[data["source"]]
                proxy.onReceive(data)
            elif self.server is not None:
                self.server.onReceive(data)

    def send(self, data):
        logger.info('--> %s', data)
        data["jsonrpc"] = "pywebgl-0.1"
        self.ws.send(json.dumps(data))


class Server:
    def __init__(self, name, transport):
        self.name = name
        self.transport = transport
        self.nextobject_id = 0
        self.liveObjects = {}
        self.global_ = None

    def serve(self, app):
        self.global_ = app
        self.transport.run(self)

    def onReceive(self, data):
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

        self.transport.send({
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

        if not hasattr(result, "_object_id"):
            object_id = self.nextobject_id
            self.nextobject_id += 1
            self.liveObjects[object_id] = result
            result._object_id = object_id

        return {
            "id": result._object_id,
            "class": "object",
        }


class ServerProxy:
    def __init__(self, name, transport):
        self.transport = transport
        self.name = name
        self.next_request_id = 0
        self.liveObjects = {}
        self.pendingRequests = {}
        self.transport.serverProxies[self.name] = self
        self.constructors = {}

    def register_constructor(self, name: str, func) -> None:
        self.constructors[name] = func

    def invoke(self, method, *params):
        request_id = self.next_request_id
        self.next_request_id += 1
        self.transport.send({
            "id": request_id,
            "destination": self.name,
            "method": method,
            "params": self.marshalParams(params),
        })
        data = self.transport.wait_until(self.name, request_id)
        if "error" in data:
            error = data["error"]
            raise ProxyException(error["code"], error["message"])
        return self.unmarshalResult(data["result"])

    def onReceive(self, data):
        fut = self.pendingRequests[data["id"]]
        del self.pendingRequests[data["id"]]
        fut.set_result()

    def unmarshalResult(self, result):
        if result is None or type(result) in (int, float, str, bool):
            return result
        assert isinstance(result, dict)
        if "__jsonclass__" not in result:
            return result
        jsonclass = result['__jsonclass__']
        constructor = jsonclass[0]
        object_id = jsonclass[1]
        print("Class:", constructor)
        print("object_id:", object_id)
        return self.constructors[constructor](self, constructor, object_id)

    def marshalParams(self, params):
        def f(value):
            if isinstance(value, ObjectProxy):
                return {"__jsonclass__": [value.constructor, value.object_id]}
            return value
        return [f(value) for value in params]


class ObjectProxy:
    def __init__(self, proxy, constructor, object_id):
        self.proxy = proxy
        self.constructor = constructor
        self.object_id = object_id

    def _invoke_function(self, name, *args):
        args = list(args)
        args.insert(0, None if self.object_id is None else self)
        return self.proxy.invoke(name, *args)

    def _invoke_procedure(self, name, *args):
        args = list(args)
        args.insert(0, None if self.object_id is None else self)
        return self.proxy.invoke(name, *args)

    def _get_attribute(self, name):
        constructor = self.constructor
        while constructor:
            spec = self.proxy.constructors[constructor]
            print(spec)
            if name in spec["properties"]:
                return self.invoke("__getter__", name)
            if name in spec["methods"]:
                return partial(self.invoke, name)
            constructor = spec["parent"]

    def _set_attribute(self, name, value):
        pass

    def __str__(self):
        return f"<ObjectProxy object; proxy={self.proxy.name}, constructor={self.constructor}, object_id={self.object_id}>"
