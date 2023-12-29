"use strict";

class TransportWebSocket {
    constructor(addr) {
        this.addr = addr;
        this.ws = null;
        this.server = null;
        this.serverProxies = {};
    }

    start(server) {
        this.server = server;
        this.ws = new WebSocket(this.addr);

        this.ws.onopen = async (event) => {
            this.send({
                destination: null,
                method: "__register__",
                params: [server.name]
            });
        };
        
        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('<--', data);
            if (data.result !== undefined) {
                const proxy = this.serverProxies[data.source];
                proxy.onReceive(data);
            } else {
                this.server.onReceive(data);
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
        data.dynbus = "0.1";
        this.ws.send(JSON.stringify(data));
    }
}

class Server {
    constructor(name, transport) {
        this.name = name;
        this.transport = transport;
        this.nextObjectId = 0;
        this.liveObjects = {};
        this.global = { window: window };
    }

    serve() {
        this.transport.start(this);
    }

    onReceive(data) {
        const params = this.unmarshalParams(data.params);
        let result;
        if (data.method === "__getter__") {
            let target = params[0] == null ? this.global : params[0];
            let name = params[1];
            result = target[name];
        } else {
            const target = params.shift();
            result = target[data.method].apply(target, params);
        }
        this.transport.send({
            id: data.id,
            destination: data.source,
            result: this.marshalResult(result)
        });
    }

    unmarshalParams(params) {
        return params.map((value) => {
            if (value !== null && typeof(value) === "object") {
                return this.liveObjects[value.id];
            } else {
                return value;
            }
        });
    }

    marshalResult(result) {
        if (result === undefined || result == null) {
            return null;
        }
        if (typeof(result) !== "object") {
            return result;
        }
        if (result._objectId === undefined) {
            const objectId = this.nextObjectId++;
            this.liveObjects[objectId] = result;
            result._objectId = objectId;
        }
        return {
            id: result._objectId,
            class: Object.getPrototypeOf(result).constructor.name
        };
    }
}

class ServerProxy {
    constructor(name, transport) {
        this.transport = transport;
        this.name = name;
        this.nextRequestId = 0;
        this.liveObjects = {};
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
        let resolve = this.pendingRequests[data.id];
        delete this.pendingRequests[data.id];
        resolve(this.unmarshalResult(data.result));
    }

    unmarshalResult(result) {
        if (result !== null && typeof(result) === 'object') {
            return new ObjectProxy(this, result.id);
        }
        return result;
    }

    marshalParams(params) {
        return params.map((value) => {
            if (value instanceof ObjectProxy) {
                return { id: value.objectId };
            }
            return value;
        });
    }
}

class ObjectProxy {
    constructor(proxy, objectId) {
        this.proxy = proxy;
        this.objectId = objectId;
    }

    async invoke(method, ...args) {
        args.unshift(this.objectId === null ? null : this);
        return await this.proxy.request(method, args);
    }
}

window.addEventListener("load", async () => {
    console.log(window.location.search);
    const name = window.location.search.replace('?name=', '');
    const remote = name == 'server_a' ? 'server_b' : 'server_a';
    const addr = `ws://${window.location.host}/ws`;
    const transport = new TransportWebSocket(addr);
    const server = new Server(name, transport);
    const proxy1 = new ServerProxy(remote, transport);
    const proxy2 = new ServerProxy('server_c', transport);
    server.serve();

    const test1Elem = document.getElementById("test1");
    test1Elem.addEventListener("click", async (event) => {
        event.preventDefault();
        let g = new ObjectProxy(proxy1, null);
        let win = await g.invoke("__getter__", "window");
        let doc = await win.invoke("__getter__", "document");
        let body = await doc.invoke("__getter__", "body");
        //let res = await win.invokeMethod("alert", ["Hi!"]);
        let x = await body.invoke("__getter__", "innerHTML");
        console.log(x);
    });

    const test2Elem = document.getElementById("test2");
    test2Elem.addEventListener("click", async (event) => {
        event.preventDefault();
        let g = new ObjectProxy(proxy2, null);
        await g.invoke("start");
    });
});
