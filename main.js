"use strict";

const PROTOCOL_VERSION = "2.0";
const ERROR_INTERNAL = -32603;

class TransportWebSocket {
    constructor(uri) {
        this.uri = uri;
        this.ws = null;
        this.server = null;
    }

    start(server) {
        this.server = server;
        this.ws = new WebSocket(this.uri);

        this.ws.onopen = (event) => {
            this.send(null, {
                jsonrpc: PROTOCOL_VERSION,
                method: "__listen__",
                params: [server.name]    
            });
        };
        
        this.ws.onmessage = (event) => {
            const packet = JSON.parse(event.data);
            console.log('<--', packet.body);
            this.server.onReceive(packet.from, packet.body);
        };

        this.ws.onclose = (event) => {
            console.log(event);
        }

        this.ws.onerror = (event) => {
            console.log(event);
        }
    }

    send(to, body) {
        console.log('-->', body);
        const packet = {
            to: to,
            body: body
        };
        this.ws.send(JSON.stringify(packet));
    }
}

class Server {
    constructor(name, transport) {
        this.name = name;
        this.transport = transport;
        this.nextObjectId = 0;
        this.liveObjects = {};
        this.rootObject = {};
        this.methods = {}
    }

    registerDefaultMethods() {
        this.registerMethod(
            "__root__",
            () => {
                return this.rootObject;
            });
        this.registerMethod(
            "__getter__",
            (target, name) => {
                return target[name];
            });
    }

    registerMethod(name, method) {
        this.methods[name] = method;
    }

    registerRootObject(object) {
        this.rootObject = object;
    }

    serve() {
        this.transport.start(this);
    }

    onReceive(fromAddr, body) {
        if (!(body instanceof Array)) {
            body = [body];
        }
        for (const data of body) {
            try {
                const params = this.unmarshalParams(data.params);
                let result;
                if (this.methods.hasOwnProperty(data.method)) {
                    result = this.methods[data.method](...params);
                } else {
                    const target = params.shift();
                    result = target[data.method].apply(target, params);
                }
                if (data.id !== undefined)
                {
                    this.transport.send(fromAddr, {
                        jsonrpc: PROTOCOL_VERSION,
                        id: data.id,
                        result: this.marshalResult(result)
                    });
                }
            } catch (e) {
                console.error(e);
                if (data.id !== undefined)
                {
                    this.transport.send(fromAddr, {
                        id: data.id,
                        error: {
                            code: ERROR_INTERNAL,
                            message: e.message
                        }
                    });
                }
            }
        }
    }

    unmarshalParams(params) {
        return params.map((value) => {
            if (value instanceof Array) {
                return value;
            }
            if (value instanceof Object) {
                if (value.__jsonclass__ !== undefined) {
                    const constructor = value.__jsonclass__[0];
                    const objectId = value.__jsonclass__[1];
                    if (constructor == "Float32Array") {
                        return new Float32Array(objectId);
                    } else {
                        return this.liveObjects[objectId];
                    }
                }
                return value;
            }
            // number, string, null
            return value;
        });
    }

    marshalResult(value) {
        if (value === undefined || value == null) {
            return null;
        }
        if (typeof(value) !== "object") {
            return value;
        }
        if (Object.getPrototypeOf(value) === Object.prototype) {
            return value;
        }
        if (Object.getPrototypeOf(value) === Array.prototype) {
            return value;
        }
        if (value._objectId === undefined) {
            const objectId = this.nextObjectId++;
            this.liveObjects[objectId] = value;
            value._objectId = objectId;
        }
        const constructor = Object.getPrototypeOf(value).constructor.name;
        return {
            __jsonclass__: [constructor, value._objectId]
        };
    }
}
