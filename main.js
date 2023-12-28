var ws = new WebSocket("ws://localhost:8000/ws");

var node = null;
var oid = 0;
var tid = 0;
var liveObjects = {};
var pendingMessages = {};

function sendMessage(receiver_node, target, type, name, args) {
    var transaction = `tid-${tid++}`;
    ws.send(JSON.stringify({
        transaction: transaction,
        receiver: receiver_node,
        target: target,
        type: type,
        name: name,
        args: args,
    }));
    return new Promise(resolve => {
        pendingMessages[transaction] = resolve;
    });
}

function unmarshal(value) {
    if (typeof(value) === 'object') {
        return new ProxyObject(value.node, value.target);
    }
    return value;
}

function marshal(args) {
    return args.map((value) => {
        if (typeof(value) === "object") {
            if (value._target !== undefined) {
                return {
                    node: node,
                    target: value._target
                };
            }
            let target = `oid-${oid++}`;
            liveObjects[target] = value;
            value._target = target;
            return {
                node: node,
                target: target
            };
        }
        return value; 
    })
}

class ProxyObject
{
    constructor(node, target) {
        this.node = node;
        this.target = target;
    }

    async getProperty(propertyName) {
        let result = await sendMessage(this.node, this.target, "get", propertyName, []);
        return unmarshal(result.value);
    }

    async invokeMethod(methodName, args) {
        let unmarshaledArgs = marshal(args);
        let result = await sendMessage(this.node, this.target, "invoke", methodName, unmarshaledArgs);
        return unmarshal(result.value);
    }
}

ws.onopen = async function(event) {
    node = window.location.search.replace('?node=', '');
    let e = await sendMessage(null, null, "register", node, []);
    console.log(e);
};

ws.onmessage = function(event) {
    var messages = document.getElementById('messages')
    var message = document.createElement('pre')
    var content = document.createTextNode(event.data)
    message.appendChild(content)
    messages.appendChild(message)
    let data = JSON.parse(event.data);
    if (data.type === "return") {
        console.log(data);
        let resolve = pendingMessages[data.transaction];
        delete pendingMessages[data.transaction];
        resolve(data);    
    } else {
        if (data.type === "get") {
            let target;
            if (data.target == null) {
                target = window;
            } else {
                target = liveObjects[data.target];
            }
            let args = [ target[data.name] ];
            let marshaledArgs = marshal(args);
            ws.send(JSON.stringify({
                transaction: data.transaction,
                receiver: data.sender,
                type: "return",
                value: marshaledArgs[0]
            }));
        } else if (data.type === "invoke") {
            target = liveObjects[data.target];
            let res = target[data.name].apply(target, data.args);
            ws.send(JSON.stringify({
                transaction: data.transaction,
                receiver: data.sender,
                type: "return",
                value: res
            }));
        }
    }
};

window.addEventListener("load", async () => {
    var startElement = document.getElementById("start");
    console.log(window.location.search);
    node = window.location.search.replace('?node=', '')

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

    // ws.send(JSON.stringify({
    //     "type": "get",
    //     "device": null,
    //     "target": null,
    //     "name": "window"
    // }));
});
