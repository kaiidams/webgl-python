"use strict";

const PROTOCOL_VERSION = "pywebgl-0.1";
const ERROR_INTERNAL = -32603;

function inspectObject(obj) {
    const name = obj.constructor.name;
    if (window[name] !== undefined && window[name] !== obj.constructor) {
        throw new Exception();
    }
    let methods = [];
    let properties = [];
    let parent = Object.getPrototypeOf(obj).constructor.name;
    if (parent === "Object") {
        parent = null;
    }
    for (const key in obj) {
        if (obj.hasOwnProperty(key)) {
            const desc = Object.getOwnPropertyDescriptor(obj, key);
            if (desc.value instanceof Function) {
                methods.push(key);
            } else {
                properties.push(key);
            }
        }
    }
    return {
        name: name,
        parent: parent,
        methods: methods,
        properties: properties
    };
}

class TransportWebSocket {
    constructor(uri) {
        this.uri = uri;
        this.ws = null;
        this.server = null;
        this.serverProxies = {};
    }

    start(server) {
        this.server = server;
        this.ws = new WebSocket(this.uri);

        this.ws.onopen = (event) => {
            if (this.server != null) {
                this.send({
                    destination: null,
                    method: "__register__",
                    params: [server.name]
                });
            }
        };
        
        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log('<--', data);
                if (data.result !== undefined || data.error !== undefined) {
                    const proxy = this.serverProxies[data.source];
                    proxy.onReceive(data);
                } else {
                    this.server.onReceive(data);
                }
            } catch (e) {
                console.error(e);
            }
        };

        this.ws.onclose = (event) => {
            console.log(event);
        }

        this.ws.onerror = (event) => {
            console.log(event);
        }
    }

    send(data) {
        console.log('-->', data);
        data.jsonrpc = PROTOCOL_VERSION;
        this.ws.send(JSON.stringify(data));
    }
}

class Server {
    constructor(name, transport) {
        this.name = name;
        this.transport = transport;
        this.nextObjectId = 0;
        this.liveObjects = {};
        this.global = {};
        this.methods = {}
    }

    registerDefaultMethods() {
        this.registerMethod(
            "__getter__",
            (target, name) => {
                if (target == null) target = this.global;
                return target[name];
            });
        this.registerMethod(
            "__new__",
            (name, ...args) => {
                const f = window[name].bind(null, ...args);
                return new f();
            });
        this.registerMethod(
            "__inspect__",
            (name) => {
                if (window[name] === undefined) {
                    return null;
                }
                return inspectObject(window[name].prototype);
            });
    }

    registerMethod(name, method) {
        this.methods[name] = method;
    }

    registerObject(name, object) {
        this.global[name] = object;
    }

    serve() {
        this.transport.start(this);
    }

    onReceive(data) {
        try {
            const params = this.unmarshalParams(data.params);
            let result;
            if (this.methods.hasOwnProperty(data.method)) {
                result = this.methods[data.method](...params);
            } else {
                const target = params.shift();
                result = target[data.method].apply(target, params);
            }
            this.transport.send({
                id: data.id,
                destination: data.source,
                result: this.marshalResult(result)
            });
        } catch (e) {
            console.error(e);
            this.transport.send({
                id: data.id,
                destination: data.source,
                error: {
                    code: ERROR_INTERNAL,
                    message: e.message
                }
            });
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

class ServerProxy {
    constructor(name, transport) {
        this.transport = transport;
        this.name = name;
        this.nextRequestId = 0;
        this.pendingRequests = {};
        this.transport.serverProxies[this.name] = this;
    }

    request(method, params) {
        const requestId = this.nextRequestId++;
        this.transport.send({
            id: requestId,
            destination: this.name,
            method: method,
            params: this.marshalParams(params),
        });
        return new Promise(resolve => {
            this.pendingRequests[requestId] = resolve;
        });
    }

    onReceive(data) {
        const resolve = this.pendingRequests[data.id];
        delete this.pendingRequests[data.id];
        resolve(this.unmarshalResult(data.result));
    }

    unmarshalResult(value) {
        if (value instanceof Array) {
            return value;
        }
        if (value instanceof Object) {
            if (value.__jsonclass__ !== undefined) {
                const constructor = value.__jsonclass__[0];
                const objectId = value.__jsonclass__[1];
                return new ObjectProxy(this, constructor, objectId);
            }
            return value;
        }
        // number, string, null
        return value;
    }

    marshalParams(params) {
        return params.map((value) => {
            if (value instanceof ObjectProxy) {
                return {
                    __jsonclass__: [value.constructor, value.objectId]
                };
            }
            return value;
        });
    }
}

class ObjectProxy {
    constructor(proxy, constructor, objectId) {
        this.proxy = proxy;
        this.constructor = constructor;
        this.objectId = objectId;
    }

    async invoke(method, ...args) {
        args.unshift(this.objectId == null ? null : this);
        return await this.proxy.request(method, args);
    }
}
