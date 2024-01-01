from typing import Any
import math
import time
import logging
from rpc import TransportWebsocket, ObjectProxy, ServerProxy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# arrays

def make_array(n, v):
    return {
        "__jsonclass__": [n, v]
    }


def Uint16Array(v):
    return make_array("Uint16Array", v)


def Float32Array(v):
    return make_array("Float32Array", v)


# glmatrix.js stub

class mat4:
    @staticmethod
    def create():
        out = [0] * 16
        out[0] = out[5] = out[10] = out[15] = 1
        return out

    @staticmethod
    def perspective(out, fovy, aspect, near, far):
        t = 1 / math.tan(fovy / 2)
        out[:] = [0] * 16
        out[0] = t / aspect
        out[5] = t
        out[10] = 2 / (near - far)
        out[11] = -1
        out[14] = -1
        return out

    @staticmethod
    def translate(out, a, v):
        out[:] = a
        out[12] += v[0]
        out[13] += v[1]
        out[14] += v[2]
        return out

    @staticmethod
    def rotate(out, a, rad, axis):
        out[:] = a
        c = math.cos(rad)
        s = math.sin(rad)
        o1 = a[0] * c - a[4] * s
        o2 = a[1] * c + a[5] * s
        o3 = -a[0] * s + a[4] * c
        o4 = -a[1] * s + a[5] * c
        out[0] = o1
        out[1] = o2
        out[4] = o3
        out[5] = o4
        return out

    @staticmethod
    def rotate2(out, a, rad, axis):
        out[:] = a
        c = math.cos(rad)
        s = math.sin(rad)
        o1 = a[0] * c - a[8] * s
        o2 = a[2] * c + a[10] * s
        o3 = -a[0] * s + a[8] * c
        o4 = -a[2] * s + a[10] * c
        out[0] = o1
        out[2] = o2
        out[8] = o3
        out[10] = o4
        return out


# WebGL Test

vsSource = """
    attribute vec4 aVertexPosition;
    attribute vec4 aVertexColor;

    uniform mat4 uModelViewMatrix;
    uniform mat4 uProjectionMatrix;

    varying lowp vec4 vColor;

    void main(void) {
      gl_Position = uProjectionMatrix * uModelViewMatrix * aVertexPosition;
      vColor = aVertexColor;
    }
"""

fsSource = """
    varying lowp vec4 vColor;

    void main(void) {
      gl_FragColor = vColor;
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


def initBuffers(gl):
    positionBuffer = initPositionBuffer(gl)
    colorBuffer = initColorBuffer(gl)
    indexBuffer = initIndexBuffer(gl)

    return {
        "position": positionBuffer,
        "color": colorBuffer,
        "indices": indexBuffer,
    }


def initPositionBuffer(gl):
    # Create a buffer for the square's positions.
    positionBuffer = gl.createBuffer()

    # Select the positionBuffer as the one to apply buffer
    # operations to from here out.
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer)

    # Now create an array of positions for the square.
    positions = [
        # Front face
        -1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0, 1.0, 1.0, -1.0, 1.0, 1.0,

        # Back face
        -1.0, -1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, -1.0, -1.0,

        # Top face
        -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0,

        # Bottom face
        -1.0, -1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, -1.0, -1.0, 1.0,

        # Right face
        1.0, -1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0, 1.0, 1.0, -1.0, 1.0,

        # Left face
        -1.0, -1.0, -1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, -1.0,
    ]
  
    # Now pass the list of positions into WebGL to build the
    # shape. We do this by creating a Float32Array from the
    # JavaScript array, then use it to fill the current buffer.
    gl.bufferData(gl.ARRAY_BUFFER, Float32Array(positions), gl.STATIC_DRAW)

    return positionBuffer


def initColorBuffer(gl):
    faceColors = [
        [1.0, 1.0, 1.0, 1.0],  # Front face: white
        [1.0, 0.0, 0.0, 1.0],  # Back face: red
        [0.0, 1.0, 0.0, 1.0],  # Top face: green
        [0.0, 0.0, 1.0, 1.0],  # Bottom face: blue
        [1.0, 1.0, 0.0, 1.0],  # Right face: yellow
        [1.0, 0.0, 1.0, 1.0],  # Left face: purple
    ]

    # Convert the array of colors into a table for all the vertices.

    colors = []

    for j in range(len(faceColors)):
        c = faceColors[j]
        # Repeat each color four times for the four vertices of the face
        colors.extend(c)
        colors.extend(c)
        colors.extend(c)
        colors.extend(c)

    colorBuffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, colorBuffer)
    gl.bufferData(gl.ARRAY_BUFFER, Float32Array(colors), gl.STATIC_DRAW)

    return colorBuffer


def initIndexBuffer(gl):
    indexBuffer = gl.createBuffer()
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indexBuffer)

    # This array defines each face as two triangles, using the
    # indices into the vertex array to specify each triangle's
    # position.

    indices = [
        0,
        1,
        2,
        0,
        2,
        3,  # front
        4,
        5,
        6,
        4,
        6,
        7,  # back
        8,
        9,
        10,
        8,
        10,
        11,  # top
        12,
        13,
        14,
        12,
        14,
        15,  # bottom
        16,
        17,
        18,
        16,
        18,
        19,  # right
        20,
        21,
        22,
        20,
        22,
        23,  # left
    ]

    # Now send the element array to GL

    gl.bufferData(
        gl.ELEMENT_ARRAY_BUFFER,
        Uint16Array(indices),
        gl.STATIC_DRAW,
    )

    return indexBuffer


# Tell WebGL how to pull out the colors from the color buffer
# into the vertexColor attribute.
def setColorAttribute(gl, buffers, programInfo):
    numComponents = 4
    type = gl.FLOAT
    normalize = False
    stride = 0
    offset = 0
    gl.bindBuffer(gl.ARRAY_BUFFER, buffers["color"])
    gl.vertexAttribPointer(
        programInfo["attribLocations"]["vertexColor"],
        numComponents,
        type,
        normalize,
        stride,
        offset,
    )
    gl.enableVertexAttribArray(programInfo["attribLocations"]["vertexColor"])


def drawScene(gl, programInfo, buffers, cubeRotation):
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
    # aspect = gl.canvas.clientWidth / gl.canvas.clientHeight
    aspect = 640 / 480
    zNear = 0.1
    zFar = 100.0

    if True:
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

        mat4.rotate(
            modelViewMatrix,  # destination matrix
            modelViewMatrix,  # matrix to rotate
            cubeRotation,  # amount to rotate in radians
            [0, 0, 1],
        )  # axis to rotate around

        mat4.rotate2(
            modelViewMatrix,  # destination matrix
            modelViewMatrix,  # matrix to rotate
            cubeRotation * 0.7,  # amount to rotate in radians
            [0, 1, 0],
        );  # axis to rotate around (Y)
    else:
        projectionMatrix = Float32Array([
            1.8106601238250732, 0, 0, 0,
            0, 2.4142136573791504, 0, 0,
            0, 0, -1.0020020008087158, -1,
            0, 0, -0.20020020008087158, 0,
        ])
        modelViewMatrix = Float32Array([
            1, 0, 0, 0,
            0, 1, 0, 0,
            0, 0, 1, 0,
            0, 0, -6, 1,
        ])

    # Tell WebGL how to pull out the positions from the position
    # buffer into the vertexPosition attribute.
    setPositionAttribute(gl, buffers, programInfo)
    setColorAttribute(gl, buffers, programInfo)

    # Tell WebGL which indices to use to index the vertices
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, buffers["indices"])

    # Tell WebGL to use our program when drawing
    gl.useProgram(programInfo["program"])

    # Set the shader uniforms
    gl.uniformMatrix4fv(
        programInfo["uniformLocations"]["projectionMatrix"],
        False,
        Float32Array(projectionMatrix),
    )
    gl.uniformMatrix4fv(
        programInfo["uniformLocations"]["modelViewMatrix"],
        False,
        Float32Array(modelViewMatrix),
    )

    vertexCount = 36
    type = gl.UNSIGNED_SHORT
    offset = 0
    gl.drawElements(gl.TRIANGLES, vertexCount, type, offset)


# Tell WebGL how to pull out the positions from the position
# buffer into the vertexPosition attribute.
def setPositionAttribute(gl, buffers, programInfo):
    numComponents = 3  # pull out 2 values per iteration
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


def test(proxy):
    canvas = proxy.get_root_object()
    gl = canvas.getContext("webgl")
    gl.clearColor(0.0, 0.0, 1.0, 1.0)
    gl.clear(gl.COLOR_BUFFER_BIT)

    shaderProgram = initShaderProgram(gl, vsSource, fsSource)

    # Collect all the info needed to use the shader program.
    # Look up which attribute our shader program is using
    # for aVertexPosition and look up uniform locations.
    programInfo = {
        "program": shaderProgram,
        "attribLocations": {
            "vertexPosition": gl.getAttribLocation(shaderProgram, "aVertexPosition"),
            "vertexColor": gl.getAttribLocation(shaderProgram, "aVertexColor"),
        },
        "uniformLocations": {
            "projectionMatrix": gl.getUniformLocation(shaderProgram, "uProjectionMatrix"),
            "modelViewMatrix": gl.getUniformLocation(shaderProgram, "uModelViewMatrix"),
        },
    }

    # Here's where we call the routine that builds all the
    # objects we'll be drawing.
    buffers = initBuffers(gl)

    squareRotation = 0
    then = time.time()
    while True:
        now = time.time()

        deltaTime = now - then
        then = now

        # Draw the scene
        drawScene(gl, programInfo, buffers, squareRotation)

        squareRotation += deltaTime
        proxy.flush()
        time.sleep(0.01)


# main

def main():
    import webgl

    uri = "ws://localhost:8000/ws"
    with TransportWebsocket(uri) as transport:
        proxy = ServerProxy("browser", transport)
        for k, v in webgl.INTERFACES.items():
            class _Class(ObjectProxy, v):
                pass
            proxy.register_constructor(k, _Class)

        class WebGLContext(
            ObjectProxy,
            webgl.WebGLRenderingContextBase,
            webgl.WebGLRenderingContextOverloads
        ):
            pass

        proxy.register_constructor("WebGLContext", WebGLContext)
        proxy.register_constructor("WebGLRenderingContext", WebGLContext)

        class CanvasObject(ObjectProxy, webgl.ProxyInterfaceBase):
            def getContext(self, *args) -> Any:
                return self._invoke_function("getContext", *args)

        proxy.register_constructor("CanvasObject", CanvasObject)

        test(proxy)


if __name__ == "__main__":
    main()
