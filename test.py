from websockets.sync.client import connect
import json
from functools import partial
import logging
import math

logging.basicConfig(level=logging.INFO)
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
        self.fetch_constructors(constructor)
        return ObjectProxy(self, constructor, object_id)

    def marshalParams(self, params):
        def f(value):
            if isinstance(value, ObjectProxy):
                return {"__jsonclass__": [value.constructor, value.object_id]}
            return value
        return [f(value) for value in params]

    def fetch_constructors(self, constructor):
        while constructor != "Object" and constructor != "TypedArray":
            if constructor in self.constructors:
                break
            spec = self.invoke("__inspect__", constructor)
            if spec is None:
                break
            self.constructors[constructor] = spec
            constructor = spec["parent"]


class ObjectProxy:
    def __init__(self, proxy, constructor, object_id):
        self.proxy = proxy
        self.constructor = constructor
        self.object_id = object_id

    def invoke(self, method, *args):
        args = list(args)
        args.insert(0, None if self.object_id is None else self)
        return self.proxy.invoke(method, *args)

    def __getattr__(self, name):
        constructor = self.constructor
        while constructor:
            spec = self.proxy.constructors[constructor]
            print(spec)
            if name in spec["properties"]:
                return self.invoke("__getter__", name)
            if name in spec["methods"]:
                return partial(self.invoke, name)
            constructor = spec["parent"]

    def __str__(self):
        return f"<ObjectProxy object; proxy={self.proxy.name}, constructor={self.constructor}, object_id={self.object_id}>"


# WebGL Test
vsSource = """
attribute vec4 aVertexPosition;
uniform mat4 uModelViewMatrix;
uniform mat4 uProjectionMatrix;
void main() {
    gl_Position = uProjectionMatrix * uModelViewMatrix * aVertexPosition;
}
"""

fsSource = """
void main() {
    gl_FragColor = vec4(1.0, 1.0, 1.0, 1.0);
}
"""


#
# Initialize a shader program, so WebGL knows how to draw our data
#
def initShaderProgram(gl, vsSource, fsSource):
    vertexShader = loadShader(gl, gl.VERTEX_SHADER, vsSource)
    fragmentShader = loadShader(gl, gl.FRAGMENT_SHADER, fsSource)

    # Create the shader program

    shaderProgram = gl.createProgram()

    gl.attachShader(shaderProgram, vertexShader)
    gl.attachShader(shaderProgram, fragmentShader)
    gl.linkProgram(shaderProgram)

    # If creating the shader program failed, alert

    if not gl.getProgramParameter(shaderProgram, gl.LINK_STATUS):
        assert False, f"""
            Unable to initialize the shader program: {gl.getProgramInfoLog(shaderProgram)}
        """
        return None

    return shaderProgram


#
# creates a shader of the given type, uploads the source and
# compiles it.
#
def loadShader(gl, type, source):
    shader = gl.createShader(type)

    # Send the source to the shader object

    gl.shaderSource(shader, source)

    # Compile the shader program

    gl.compileShader(shader)

    # See if it compiled successfully

    if not gl.getShaderParameter(shader, gl.COMPILE_STATUS):
        assert False, (
            f"An error occurred compiling the shaders: ${gl.getShaderInfoLog(shader)}"
        )
        gl.deleteShader(shader)
        return None

    return shader


def initBuffers(gl, proxy):
    positionBuffer = initPositionBuffer(gl, proxy)

    return {
        "position": positionBuffer,
    }


def initPositionBuffer(gl, proxy):
    # Create a buffer for the square's positions.
    positionBuffer = gl.createBuffer()

    # Select the positionBuffer as the one to apply buffer
    # operations to from here out.
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer)

    # Now create an array of positions for the square.
    positions = [1.0, 1.0, -1.0, 1.0, 1.0, -1.0, -1.0, -1.0]

    # Now pass the list of positions into WebGL to build the
    # shape. We do this by creating a Float32Array from the
    # JavaScript array, then use it to fill the current buffer.
    positionsArray = proxy.invoke("__new__", "Float32Array", positions)
    gl.bufferData(gl.ARRAY_BUFFER, positionsArray, gl.STATIC_DRAW)

    return positionBuffer


def drawScene(gl, programInfo, buffers, proxy):
    gl.clearColor(0.0, 0.0, 0.0, 1.0)  # Clear to black, fully opaque
    gl.clearDepth(1.0)  # Clear everything
    gl.enable(gl.DEPTH_TEST)  # Enable depth testing
    gl.depthFunc(gl.LEQUAL)  # Near things obscure far things

    # Clear the canvas before we start drawing on it.

    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT)

    # Create a perspective matrix, a special matrix that is
    # used to simulate the distortion of perspective in a camera.
    # Our field of view is 45 degrees, with a width/height
    # ratio that matches the display size of the canvas
    # and we only want to see objects between 0.1 units
    # and 100 units away from the camera.

    fieldOfView = (45 * math.pi) / 180  # in radians
    aspect = gl.canvas.clientWidth / gl.canvas.clientHeight
    zNear = 0.1
    zFar = 100.0

    if False:
        projectionMatrix = mat4.create()

        # note: glmatrix.js always has the first argument
        # as the destination to receive the result.
        mat4.perspective(projectionMatrix, fieldOfView, aspect, zNear, zFar)

        # Set the drawing position to the "identity" point, which is
        # the center of the scene.
        modelViewMatrix = mat4.create()

        # Now move the drawing position a bit to where we want to
        # start drawing the square.
        mat4.translate(
            modelViewMatrix,  # destination matrix
            modelViewMatrix,  # matrix to translate
            [-0.0, 0.0, -6.0],
        )  # amount to translate
    else:
        projectionMatrix = proxy.invoke("__new__", "Float32Array", [
            1.8106601238250732, 0, 0, 0,
            0, 2.4142136573791504, 0, 0,
            0, 0, -1.0020020008087158, -1,
            0, 0, -0.20020020008087158, 0,
        ])
        modelViewMatrix = proxy.invoke("__new__", "Float32Array", [
            1, 0, 0, 0,
            0, 1, 0, 0,
            0, 0, 1, 0,
            0, 0, -6, 1,
        ])

    # Tell WebGL how to pull out the positions from the position
    # buffer into the vertexPosition attribute.
    setPositionAttribute(gl, buffers, programInfo)

    # Tell WebGL to use our program when drawing
    gl.useProgram(programInfo["program"])

    # Set the shader uniforms
    gl.uniformMatrix4fv(
        programInfo["uniformLocations"]["projectionMatrix"],
        False,
        projectionMatrix,
    )
    gl.uniformMatrix4fv(
        programInfo["uniformLocations"]["modelViewMatrix"],
        False,
        modelViewMatrix,
    )

    offset = 0
    vertexCount = 4
    gl.drawArrays(gl.TRIANGLE_STRIP, offset, vertexCount)


# Tell WebGL how to pull out the positions from the position
# buffer into the vertexPosition attribute.
def setPositionAttribute(gl, buffers, programInfo):
    numComponents = 2  # pull out 2 values per iteration
    type = gl.FLOAT  # the data in the buffer is 32bit floats
    normalize = False  # don't normalize
    stride = 0  # how many bytes to get from one set of values to the next
    # 0 = use type and numComponents above
    offset = 0  # how many bytes inside the buffer to start from
    gl.bindBuffer(gl.ARRAY_BUFFER, buffers["position"])
    gl.vertexAttribPointer(
        programInfo["attribLocations"]["vertexPosition"],
        numComponents,
        type,
        normalize,
        stride,
        offset,
    )
    gl.enableVertexAttribArray(programInfo["attribLocations"]["vertexPosition"])


def test(proxy, document):
    print(document)
    elem = document.getElementById("glcanvas")
    if elem is None:
        elem = document.createElement("canvas")
        elem.setAttribute("id", "glcanvas")
        elem.setAttribute("width", "640")
        elem.setAttribute("height", "480")
        elem.setAttribute("style", "border: 2px solid blue; display: block")
        document.body.appendChild(elem)
    gl = elem.getContext("webgl")
    # gl.clearColor(0.0, 0.0, 1.0, 1.0)
    # gl.clear(gl.COLOR_BUFFER_BIT)

    shaderProgram = initShaderProgram(gl, vsSource, fsSource)

    # Collect all the info needed to use the shader program.
    # Look up which attribute our shader program is using
    # for aVertexPosition and look up uniform locations.
    programInfo = {
        "program": shaderProgram,
        "attribLocations": {
            "vertexPosition": gl.getAttribLocation(shaderProgram, "aVertexPosition"),
        },
        "uniformLocations": {
            "projectionMatrix": gl.getUniformLocation(shaderProgram, "uProjectionMatrix"),
            "modelViewMatrix": gl.getUniformLocation(shaderProgram, "uModelViewMatrix"),
        },
    }

    # Here's where we call the routine that builds all the
    # objects we'll be drawing.
    buffers = initBuffers(gl, proxy)

    # Draw the scene
    drawScene(gl, programInfo, buffers, proxy)


# main

def main():
    uri = "ws://localhost:8000/ws"
    with TransportWebsocket(uri) as transport:
        proxy = ServerProxy("server_a", transport)
        transport.server = Server("server_c", transport)

        window = proxy.invoke("__getter__", None, "window")
        document = proxy.invoke("__getter__", window, "document")
        test(proxy, document)


if __name__ == "__main__":
    main()
