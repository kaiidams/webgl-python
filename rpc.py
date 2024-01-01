from typing import Optional
from websockets.sync.client import connect
import json
from functools import partial
import logging

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2.0"


class ProxyException(Exception):
    pass


class TransportWebsocket:
    def __init__(self, uri: str) -> None:
        self.uri = uri
        self.ws = None
        self.server = None

    def __enter__(self):
        self.ws = connect(self.uri).__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.ws.__exit__(exc_type, exc_val, exc_tb)

    def connect(self, to_addr):
        self.send(None, {
            "jsonrpc": PROTOCOL_VERSION,
            "method": "__connect__",
            "params": [to_addr]
        })

    def listen(self, from_addr):
        self.send(None, {
            "jsonrpc": PROTOCOL_VERSION,
            "method": "__listen__",
            "params": [from_addr]
        })

    def run(self, server):
        self.server = server
        with connect(self.uri) as self.ws:
            self.listen(server.name)
            while True:
                self.wait_until(None)

    def recv(self):
        packet = self.ws.recv()
        packet = json.loads(packet)
        body = packet["body"]
        if isinstance(body, list):
            for data in body:
                logger.info('<-- %s', data)
        else:
            logger.info('<-- %s', body)
        return body

    def send(self, to_addr, body):
        if isinstance(body, list):
            for msg in body:
                logger.info("--> %s", msg)
        else:
            logger.info("--> %s", body)
        self.ws.send(json.dumps({
            "to": to_addr,
            "body": body
        }))


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

        self.transport.send(
            data["source"],
            {
                "id": data["id"],
                "result": self.marshalResult(result)
            }
        )

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
    def __init__(self, to_addr, transport):
        self.to_addr = to_addr
        self.transport = transport
        self.next_request_id = 0
        self.pendingRequests = {}
        self.constructors = {}
        self.buffers = []
        self.transport.connect(to_addr)

    def register_constructor(self, name: str, func) -> None:
        self.constructors[name] = func

    def get_root_object(self):
        return self._invoke(False, "__root__")

    def invoke_function(self, method, *params):
        return self._invoke(False, method, *params)

    def invoke_procedure(self, method, *params):
        self._invoke(True, method, *params)

    def flush(self):
        if not self.buffers:
            return

        body = self.buffers[0] if len(self.buffers) == 1 else self.buffers[:]
        self.buffers.clear()

        self.transport.send(self.to_addr, body)

    def _invoke(self, no_wait, method, *params):
        data = {
            "jsonrpc": PROTOCOL_VERSION,
            "method": method,
            "params": self.marshalParams(params),
        }
        self.buffers.append(data)
        if no_wait:
            return
        print(method)

        request_id = self.next_request_id
        self.next_request_id += 1
        data["id"] = request_id

        # Copy self.buffers
        body = self.buffers[0] if len(self.buffers) == 1 else self.buffers[:]
        self.buffers.clear()

        self.transport.send(self.to_addr, body)

        while True:
            body = self.transport.recv()
            if not isinstance(body, list):
                body = [body]
            error_data = None
            return_data = None
            for data in body:
                assert data["jsonrpc"] == PROTOCOL_VERSION
                if "error" in data:
                    error_data = data
                if request_id is not None and data["id"] == request_id:
                    return_data = data
            if error_data is not None:
                error = error_data["error"]
                raise ProxyException(error["code"], error["message"])
            if return_data is not None:
                return self.unmarshalResult(return_data["result"])

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
        return self.proxy.invoke_function(name, *args)

    def _invoke_procedure(self, name, *args):
        args = list(args)
        args.insert(0, None if self.object_id is None else self)
        self.proxy.invoke_procedure(name, *args)

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
