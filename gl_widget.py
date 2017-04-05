import sys
import json
import numpy as np
import ctypes
import math
from PyQt5.QtGui import (QSurfaceFormat, QPainter, QCursor, QKeyEvent)
from PyQt5.QtCore import (QTimer, QTime, Qt, QPoint)
from PyQt5.QtWidgets import (QApplication, QHBoxLayout, QOpenGLWidget, QWidget, QMainWindow)
from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GLUT import *

from matrix_utils import (mul, lookAt, perspective, translate, rotate, cross)
from loader import (loadOBJ, loadShaders, indexVBO)


class GLTrajectoryWidget(QOpenGLWidget):
    """
    Animate a trajectory in 3D using OpenGL.
    """
    # TODO: Create OpenGL object class (combination of vertices and methods, etc.)
    # to have multiple, independent objects in the same scene
    def __init__(self, width, height, data, configFilepath):
        """
        width: Width of the widget.

        height: Height of the widget.

        data: Data of the trajectory. Must be an Nx3 numpy array where columns
        are x, y, z coordinates.

        configFilepath: Path to configuration file.
        """
        super(QOpenGLWidget, self).__init__()
        self.configure(configFilepath)
        self.setMinimumSize(width, height)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setMouseTracking(True)
        self.lastPos = QPoint(width/2, height/2)
        self.cursorType = self.cursor()
        self.clearFocus()
        self.resetInputs()
        timer = QTimer(self)
        timer.timeout.connect(self.animate)
        timer.start(1000/self.FPS)
        # TODO: synchronize these with the timer
        self.elapsed = 0
        self.time = QTime()
        self.time.start()
        self.data = data
        self.dataIndices = np.arange(1)

    def initializeGL(self):
        """
        Called once when the GL widget is initialized.
        """
        glClearColor(*self.backgroundColor)
        # enable Z-buffer
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LESS)
        # enable culling for better performance
        glEnable(GL_CULL_FACE)
        self.programID = loadShaders("shaders/vertex_shader.glsl", "shaders/fragment_shader.glsl")
        self.indices, vertices, _, normals = indexVBO(*loadOBJ(self.objFile))
        self.initUniforms(self.programID)
        self.initBuffers(vertices, normals)

    def paintGL(self):
        """
        Painting of each frame happens in this method.
        """
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        V, P = self.computeMVPFromInputs()
        glUseProgram(self.programID)
        self.setConstUniform()
        glUniformMatrix4fv(self.VID, 1, False, V)
        for i in self.dataIndices:
            M = translate(*(self.data[i]*10))
            MVP = mul(P, mul(V, M))
            glUniformMatrix4fv(self.matrixID, 1, False, MVP)
            glUniformMatrix4fv(self.MID, 1, False, M)
            # vertex attribute array
            glEnableVertexAttribArray(0)
            glBindBuffer(GL_ARRAY_BUFFER, self.vertexBuffer)
            glVertexAttribPointer(
                0,                   # must match the layout id in the shader
                3,                   # size
                GL_FLOAT,            # data type
                GL_FALSE,            # normalized?
                0,                   # stride. offset in between
                ctypes.c_void_p(0),  # offset to the beginning
            )
            # normal coordinates attribute array
            glEnableVertexAttribArray(1)
            glBindBuffer(GL_ARRAY_BUFFER, self.normalBuffer)
            glVertexAttribPointer(
                1,
                3,
                GL_FLOAT,
                GL_FALSE,
                0,
                ctypes.c_void_p(0),
            )
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.elementBuffer)
            glDrawElements(
                GL_TRIANGLES,
                len(self.indices),
                GL_UNSIGNED_SHORT,
                ctypes.c_void_p(0),
            )
        glDisableVertexAttribArray(0)
        glDisableVertexAttribArray(1)
        self.resetMouseInputs()
        self.dataIndices += 1

    def configure(self, configFilepath):
        """
        Configure the GL widget with options in the given configuration file
        in JSON format.
        """
        # don't catch any possible error. If no correct config, just crash.
        with open(configFilepath, 'r') as f:
            configTXT = f.read()
            confDic = json.loads(configTXT)
        self.FPS = confDic['FPS']
        self.lightPosWorld = np.array(confDic['lightPosWorld'], dtype='float32')
        self.lightColor = np.array(confDic['lightColor'], dtype='float32')
        self.lightPower = confDic['lightPower']
        self.backgroundColor = confDic['backgroundColor']
        self.materialDiffuseColor = np.array(
            confDic['materialDiffuseColor'],
            dtype='float32'
        )
        self.materialAmbientColorCoeffs = np.array(
            confDic['materialAmbientColorCoeffs'],
            dtype='float32'
        )
        self.materialSpecularColor = np.array(
            confDic['materialSpecularColor'],
            dtype='float32'
        )
        self.position = confDic['initialCameraPosition']
        self.horzAngle = np.radians(confDic['initialHorzAngle'])
        self.vertAngle = np.radians(confDic['initialVertAngle'])
        self.fov = confDic['fov']
        self.speed = confDic['speed']
        self.mouseSpeed = confDic['mouseSpeed']
        self.mouseWheelSpeed = confDic['mouseWheelSpeed']
        self.objFile = confDic['objFile']

    def setConstUniform(self):
        """
        Sets uniform values which is constant for the whole frame.
        """
        glUniform3fv(self.lightPosWorldID, 1, self.lightPosWorld)
        glUniform3fv(self.lightColorID, 1, self.lightColor)
        glUniform1f(self.lightPowerID, self.lightPower)
        glUniform3fv(self.materialDiffuseColorID, 1, self.materialDiffuseColor)
        glUniform3fv(self.materialAmbientColorCoeffsID, 1, self.materialAmbientColorCoeffs)
        glUniform3fv(self.materialSpecularColorID, 1, self.materialSpecularColor)

    def initUniforms(self, programID):
        """
        Creates locations for uniform variables used in the shader program.

        programID: Shader program ID.
        """
        self.matrixID = glGetUniformLocation(programID, "MVP")
        self.MID = glGetUniformLocation(programID, "M")
        self.VID = glGetUniformLocation(programID, "V")
        self.lightPosWorldID = glGetUniformLocation(programID, "LightPosition_worldspace")
        self.lightColorID = glGetUniformLocation(programID, "LightColor")
        self.lightPowerID = glGetUniformLocation(programID, "LightPower")
        self.materialDiffuseColorID = glGetUniformLocation(programID, "MaterialDiffuseColor")
        self.materialAmbientColorCoeffsID = glGetUniformLocation(programID, "MaterialAmbientColorCoeffs")
        self.materialSpecularColorID = glGetUniformLocation(programID, "MaterialSpecularColor")

    def initBuffers(self, vertices, normals):
        """
        Creates OpenGL buffers for storing vertex data.
        """
        glBindVertexArray(glGenVertexArrays(1))
        # vertex array (positions)
        self.vertexBuffer = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vertexBuffer)
        glBufferData(GL_ARRAY_BUFFER, vertices, GL_STATIC_DRAW)
        # normal array (normal vector of each triangle)
        self.normalBuffer = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.normalBuffer)
        glBufferData(GL_ARRAY_BUFFER, normals, GL_STATIC_DRAW)
        # index array (to be used for VBO indexing)
        self.elementBuffer = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.elementBuffer)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, self.indices, GL_STATIC_DRAW)

    def resetInputs(self):
        """
        Reset user inputs to their initial values.
        """
        self.inputs = {
            'left'        : False,
            'right'       : False,
            'up'          : False,
            'down'        : False,
            'mouseXDelta' : 0.0,
            'mouseYDelta' : 0.0,
            'wheelDelta'  : 0.0,
        }

    def resetMouseInputs(self):
        """
        Resets mouse inputs and if the widget has focus, centers the cursor
        on the center of the widget frame.

        Centering mouse behaviour is needed for FPS-style mouse navigation.
        Otherwise, cursor goes out of the screen.
        """
        self.inputs['mouseXDelta'] = 0.0
        self.inputs['mouseYDelta'] = 0.0
        self.inputs['wheelDelta']  = 0.0
        if self.hasFocus():
            QCursor.setPos(self.width()/2, self.height()/2)

    def animate(self):
        """
        Animate the scene with delta time intervals.

        Needs to be connected to a timer to be called in equal, small intervals.
        """
        # need to manually grab mouse position since I couldn't synchronize qt
        # mouse signals with openGL frames and we don't need qt signals for
        # this task
        if self.hasFocus():
            pos = QCursor.pos()
            self.inputs['mouseXDelta'] = pos.x() - self.width()/2
            self.inputs['mouseYDelta'] = pos.y() - self.height()/2
        # TODO: merge elapsed with timer
        self.elapsed = self.time.elapsed()/1000
        self.time.restart()
        self.update()

    def mousePressEvent(self, event):
        self.setCursor(Qt.BlankCursor)
        self.lastPos = QCursor.pos()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.resetInputs()
            self.clearFocus()
            QCursor.setPos(self.lastPos)
            self.setCursor(self.cursorType)
        else:
            # we already press the key OR it is pressed in this event
            self.inputs['up']    |= (event.key() == Qt.Key_Up)
            self.inputs['down']  |= (event.key() == Qt.Key_Down)
            self.inputs['left']  |= (event.key() == Qt.Key_Left)
            self.inputs['right'] |= (event.key() == Qt.Key_Right)

    def keyReleaseEvent(self, event):
        # key remains pressed
        # if it is already pressed AND it is NOT released in this event
        self.inputs['up']    &= (event.key() != Qt.Key_Up)
        self.inputs['down']  &= (event.key() != Qt.Key_Down)
        self.inputs['left']  &= (event.key() != Qt.Key_Left)
        self.inputs['right'] &= (event.key() != Qt.Key_Right)

    def wheelEvent(self, event):
        # 160 is just random magic number. Wheel speed "felt" best with it.
        self.inputs['wheelDelta'] = self.mouseWheelSpeed*event.angleDelta().y()/160

    def computeMVPFromInputs(self):
        """
        Compute and return the Model-View-Projection (MVP) matrix using the user
        input data and accumulator values for position, view angles, etc.
        """
        deltaTime = self.elapsed
        self.horzAngle += self.mouseSpeed*deltaTime*(-self.inputs['mouseXDelta'])
        vertAnglePossible = self.vertAngle + self.mouseSpeed*deltaTime*(-self.inputs['mouseYDelta'])
        # bound vertical angle by [-90, 90]
        self.vertAngle = max(-np.pi/2, min(vertAnglePossible, np.pi/2))
        direction = np.array([
            np.cos(self.vertAngle)*np.sin(self.horzAngle),
            np.sin(self.vertAngle),
            np.cos(self.vertAngle)*np.cos(self.horzAngle),
        ])
        right = np.array([
            np.sin(self.horzAngle - np.pi/2),
            0,
            np.cos(self.horzAngle - np.pi/2),
        ])
        up = cross(right, direction)
        if self.inputs['up']:
            self.position += direction*deltaTime*self.speed
        if self.inputs['down']:
            self.position -= direction*deltaTime*self.speed
        if self.inputs['right']:
            self.position += right*deltaTime*self.speed
        if self.inputs['left']:
            self.position -= right*deltaTime*self.speed
        self.position += up*deltaTime*self.speed*self.inputs['wheelDelta']
        projection = perspective(
            self.fov,                    # fov
            self.width()/self.height(),  # aspect ratio
            0.1,                         # distance to near clipping plane
            100,                         # distance to far clipping plane
        )
        view = lookAt(
            self.position,               # camera position in world coordinates
            self.position + direction,   # where the camera looks at in world coordinates
            up,                          # up vector for camera. Used for orientation
        )
        return view, projection


if __name__ == '__main__':
    fmt = QSurfaceFormat()
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    fmt.setMajorVersion(3)
    fmt.setMinorVersion(3)
    fmt.setRenderableType(QSurfaceFormat.OpenGL)
    fmt.setDepthBufferSize(24)
    fmt.setAlphaBufferSize(24)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)

    # read data file
    dataFile = sys.argv[1]
    configFile = sys.argv[2]
    data = np.genfromtxt(dataFile, delimiter=',', dtype=str)
    data = np.char.replace(data, '[', '')
    data = np.char.replace(data, ']', '')
    data = data.astype(float)

    app = QApplication(sys.argv)
    window = QWidget()
    layout = QHBoxLayout()
    layout.addWidget(GLTrajectoryWidget(1368, 768, data[:, 1:4], configFile))
    window.setLayout(layout)

    window.show()
    sys.exit(app.exec_())
