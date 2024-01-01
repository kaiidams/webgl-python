# The code is translated from the tutorial code from MDN. See
# https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API/Tutorial/Using_textures_in_WebGL
# for the original JavaScript code.

from typing import Any
import math
import time
import logging
from PIL import Image
from rpc import TransportWebsocket, ObjectProxy, ServerProxy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# arrays

def make_array(n, v):
    return {
        "__jsonclass__": [n, v]
    }


def Uint8Array(v):
    return make_array("Uint8Array", v)


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
        f = 1 / math.tan(fovy / 2)
        out[:] = [0] * 16
        out[0] = f / aspect
        out[5] = f
        out[10] = (near + far) / (near - far)
        out[11] = -1
        out[14] = 2 * far * near / (near - far)
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
        a = a[:]
        x, y, z = axis
        c = math.cos(rad)
        s = math.sin(rad)
        a11 = x * x * (1 - c) + c
        a21 = y * x * (1 - c) + z * s
        a31 = x * z * (1 - c) - y * s
        a12 = x * y * (1 - c) - z * s
        a22 = y * y * (1 - c) + c
        a32 = y * z * (1 - c) + x * s
        a13 = x * z * (1 - c) + y * s
        a23 = y * z * (1 - c) - x * s
        a33 = z * z * (1 - c) + c
        out[0] = a11 * a[0] + a21 * a[4] + a31 * a[8]
        out[1] = a12 * a[0] + a22 * a[4] + a32 * a[8]
        out[2] = a13 * a[0] + a23 * a[4] + a33 * a[8]
        out[4] = a11 * a[1] + a21 * a[5] + a31 * a[9]
        out[5] = a12 * a[1] + a22 * a[5] + a32 * a[9]
        out[6] = a13 * a[1] + a23 * a[5] + a33 * a[9]
        out[8] = a11 * a[2] + a21 * a[6] + a31 * a[10]
        out[9] = a12 * a[2] + a22 * a[6] + a32 * a[10]
        out[10] = a13 * a[2] + a23 * a[6] + a33 * a[10]
        out[15] = a[15]
        return out


# WebGL Test

vsSource = """
    attribute vec4 aVertexPosition;
    attribute vec2 aTextureCoord;

    uniform mat4 uModelViewMatrix;
    uniform mat4 uProjectionMatrix;

    varying highp vec2 vTextureCoord;

    void main(void) {
      gl_Position = uProjectionMatrix * uModelViewMatrix * aVertexPosition;
      vTextureCoord = aTextureCoord;
    }
"""

fsSource = """
  varying highp vec2 vTextureCoord;

  uniform sampler2D uSampler;

  void main(void) {
    gl_FragColor = texture2D(uSampler, vTextureCoord);
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
    textureCoordBuffer = initTextureBuffer(gl)
    indexBuffer = initIndexBuffer(gl)

    return {
        "position": positionBuffer,
        "color": colorBuffer,
        "textureCoord": textureCoordBuffer,
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


def initTextureBuffer(gl):
    textureCoordBuffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, textureCoordBuffer)

    textureCoordinates = [
        # Front
        0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0,
        # Back
        0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0,
        # Top
        0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0,
        # Bottom
        0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0,
        # Right
        0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0,
        # Left
        0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0,
    ]

    gl.bufferData(
        gl.ARRAY_BUFFER,
        Float32Array(textureCoordinates),
        gl.STATIC_DRAW,
    )

    return textureCoordBuffer


#
# Initialize a texture and load an image.
# When the image finished loading copy it into the texture.
#
def loadTexture(gl, url):
    texture = gl.createTexture()
    gl.bindTexture(gl.TEXTURE_2D, texture)

    # Because images have to be downloaded over the internet
    # they might take a moment until they are ready.
    # Until then put a single pixel in the texture so we can
    # use it immediately. When the image has finished downloading
    # we'll update the texture with the contents of the image.
    level = 0
    internalFormat = gl.RGBA
    border = 0
    srcFormat = gl.RGBA
    srcType = gl.UNSIGNED_BYTE
    with Image.open(url) as im:
        # im = im.resize(size=(64, 64))
        pixel = [y for x in im.getdata() for y in x]
        width, height = im.size
    gl.texImage2D(
        gl.TEXTURE_2D,
        level,
        internalFormat,
        width,
        height,
        border,
        srcFormat,
        srcType,
        Uint8Array(pixel),
    )

    # WebGL1 has different requirements for power of 2 images
    # vs. non power of 2 images so check if the image is a
    # power of 2 in both dimensions.
    if isPowerOf2(width) and isPowerOf2(height):
        # Yes, it's a power of 2. Generate mips.
        gl.generateMipmap(gl.TEXTURE_2D)
    else:
        # No, it's not a power of 2. Turn off mips and set
        # wrapping to clamp to edge
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)

    return texture


def isPowerOf2(value):
    return (value & (value - 1)) == 0


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


def drawScene(gl, programInfo, buffers, texture, cubeRotation):
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

    mat4.rotate(
        modelViewMatrix,  # destination matrix
        modelViewMatrix,  # matrix to rotate
        cubeRotation * 0.7,  # amount to rotate in radians
        [0, 1, 0],
    )  # axis to rotate around (Y)

    # Tell WebGL how to pull out the positions from the position
    # buffer into the vertexPosition attribute.
    setPositionAttribute(gl, buffers, programInfo)
    # setColorAttribute(gl, buffers, programInfo)
    setTextureAttribute(gl, buffers, programInfo)

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

    # Tell WebGL we want to affect texture unit 0
    gl.activeTexture(gl.TEXTURE0)

    # Bind the texture to texture unit 0
    gl.bindTexture(gl.TEXTURE_2D, texture)

    # Tell the shader we bound the texture to texture unit 0
    gl.uniform1i(programInfo["uniformLocations"]["uSampler"], 0)

    vertexCount = 36
    type = gl.UNSIGNED_SHORT
    offset = 0
    gl.drawElements(gl.TRIANGLES, vertexCount, type, offset)


# tell webgl how to pull out the texture coordinates from buffer
def setTextureAttribute(gl, buffers, programInfo):
    num = 2  # every coordinate composed of 2 values
    type = gl.FLOAT  # the data in the buffer is 32-bit float
    normalize = False  # don't normalize
    stride = 0  # how many bytes to get from one set to the next
    offset = 0  # how many bytes inside the buffer to start from
    gl.bindBuffer(gl.ARRAY_BUFFER, buffers["textureCoord"])
    gl.vertexAttribPointer(
        programInfo["attribLocations"]["textureCoord"],
        num,
        type,
        normalize,
        stride,
        offset,
    )
    gl.enableVertexAttribArray(programInfo["attribLocations"]["textureCoord"])


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
            # "vertexColor": gl.getAttribLocation(shaderProgram, "aVertexColor"),
            "textureCoord": gl.getAttribLocation(shaderProgram, "aTextureCoord"),
        },
        "uniformLocations": {
            "projectionMatrix": gl.getUniformLocation(shaderProgram, "uProjectionMatrix"),
            "modelViewMatrix": gl.getUniformLocation(shaderProgram, "uModelViewMatrix"),
            "uSampler": gl.getUniformLocation(shaderProgram, "uSampler"),
        },
    }

    # Here's where we call the routine that builds all the
    # objects we'll be drawing.
    buffers = initBuffers(gl)

    # Load texture
    texture = loadTexture(gl, "debian-logo.png")
    # Flip image pixels into the bottom-to-top order that WebGL expects.
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, True)

    squareRotation = 0
    then = time.time()
    while True:
        now = time.time()

        deltaTime = now - then
        then = now

        # Draw the scene
        drawScene(gl, programInfo, buffers, texture, squareRotation)

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
