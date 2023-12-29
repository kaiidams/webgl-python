class TransportWebsocket {
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
            let e = await sendRequest(null, "register", [node]);
            console.log(e);
        };
        
        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('<--', data);
            if (data.result !== undefined) {
                const proxy = this.serverProxies[data.sender];
                proxy.onReceived(data);
            } else {
                this.server.onReceive(data);
            }
        };
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
        this.global = {};
    }

    serve() {
        this.transport.start(this);
    }

    onReceived(data) {
        const params = this.unmarshalParams(data.params);
        let result;
        if (data.method === "__getter__") {
            let target = params[0] == null ? this.global : params[0];
            let name = params[1];
            result = target[name];
        } else {
            const target = params.shift();
            result = target[data.name].apply(target, params);
        }
        this.transport.send({
            id: data.id,
            receiver: data.sender,
            result: marshalResult(result)
        });
    }

    unmarshalParams(params) {
        return params.map((value) => {
            if (typeof(value) === "object") {
                return this.liveObjects[value.id];
            } else {
                return value;
            }
        });
    }

    marshalResult(result) {
        if (typeof(result) !== "object") {
            return result;
        }
        if (result._objectId === undefined) {
            const objectId = this.nextObjectId++;
            this.liveObjects[objectId] = result;
            result._objectId = target;
        }
        return {
            id: result._objectId
        };
    }
}

class ServerProxy {
    constructor(ws, name) {
        this.ws = ws;
        this.name = name;
        this.nextRequestId = 0;
        this.liveObjects = {};
        this.pendingRequests = {};
    }

    sendRequest(receiver, method, params) {
        const requestId = this.nextRequestId++;
        data = {
            id: requestId,
            receiver: receiver,
            method: method,
            params: this.marshalParams(params),
        };
        this.transport.send(data);
        return new Promise(resolve => {
            this.pendingRequests[requestId] = resolve;
        });
    }

    onReceived(data) {
        let resolve = this.pendingRequests[data.id];
        delete this.pendingRequests[data.id];
        resolve(this.unmarshalResult(data.result));
    }

    unmarshalResult(result) {
        if (typeof(result) === 'object') {
            return new ProxyObject(this, result.id);
        }
        return result;
    }

    marshalParams(params) {
        return params.map((value) => {
            if (typeof(value) === 'object') {
                return { id: value.id };
            }
            return value;
        });
    }
}

class ProxyObject
{
    constructor(server, objectId) {
        this.server = server;
        this.objectId = objectId;
    }

    async getProperty(propertyName) {
        let result = await sendRequest(this.node, this.target, "get", propertyName, []);
        return unmarshalObject(result.value);
    }

    async invokeMethod(methodName, params) {
        let unmarshaledparams = marshalArray(params);
        let result = await sendRequest(this.node, this.target, "invoke", methodName, unmarshaledparams);
        return unmarshalObject(result.value);
    }
}

window.addEventListener("load", async () => {
    console.log(window.location.search);
    const name = window.location.search.replace('?name=', '');
    const addr = "ws://192.168.10.109:8000/ws";
    const transport = new TransportWebsocket(addr);
    const server = new Server(ws, name);
    server.serve();

    const startElement = document.getElementById("start");
    startElement.addEventListener("click", async (event) => {
        event.preventDefault();
        let g = new ProxyObject(node == 'a' ? 'b' : 'a', null);
        let win = await g.getProperty("window");
        let doc = await win.getProperty("document");
        let body = await doc.getProperty("body");
        //let res = await win.invokeMethod("alert", ["Hi!"]);
        let x = await body.getProperty("innerHTML");
        console.log(x);
    });
});
