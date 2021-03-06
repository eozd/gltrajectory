from PyQt5.QtWidgets import QOpenGLWidget
from PyQt5.QtCore import (QTimer, QTime, Qt, QPoint)
from PyQt5.QtGui import QCursor
from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GLUT import *
import json
import numpy as np

from gl_object import GLObject
import loader
import matrix_utils as mu


class GLTrajectoryWidget(QOpenGLWidget):
    """
    Animate a trajectory in 3D using OpenGL.
    """

    def __init__(self, width, height, dataQueue, configFilepath):
        """
        width: Width of the widget.

        height: Height of the widget.

        dataQueue: Synchronized queue object that gives the data of the
        trajectory. At each frame, all the points in the queue will be painted.

        configFilepath: Path to configuration file.
        """
        super().__init__()
        self.configure(configFilepath)
        self.setMinimumSize(width, height)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setMouseTracking(True)
        self.lastPos = QPoint(width/2, height/2)  # last cursor pos
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
        self.dataQueue = dataQueue
        self.dataPoints = []
        self.paintCounter = 0
        self.totalElapsedTime = 0

    def initializeGL(self):
        """
        Called once when the GL widget is initialized.
        """
        glClearColor(*self.backgroundColor)
        # enable Z-buffer
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LESS)
        # enable blending for transparency
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        # enable culling for better performance
        glEnable(GL_CULL_FACE)
        self.programID = loader.loadShaders("shaders/vertex_shader.glsl", "shaders/fragment_shader.glsl")
        self.initUniforms(self.programID)
        GLObject.initUniforms(self.programID)
        GLObject.initModelVertexDic(
            {
                'box'   : self.boxObjFile,
                'ball'  : self.ballObjFile,
                'arrow' : self.arrowObjFile
            }
        )
        self.ballGLObject = GLObject('ball')
        self.boxGLObject = GLObject('box')
        self.arrowGLObject = GLObject('arrow')

    def paintGL(self):
        """
        Painting of each frame happens in this method.
        """
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self.getMouseInputs()
        V, P = self.computeMVPFromInputs()
        self.resetMouseInputs()
        glUseProgram(self.programID)
        self.setConstUniform()
        glUniformMatrix4fv(self.VID, 1, False, V)
        self.setDataPoints()
        for pos in self.dataPoints:
            # all the x,y,z coords are shifted to right by 2 for upwards height
            # and better visualization.
            pos = np.roll(pos, 2)
            M = mu.reverse_mul(mu.translate(*pos), mu.scale(*self.ballXYZLength))
            self.ballGLObject.paint(M, V, P, self.ballDiffuseColor)
        # draw the origin
        M = mu.reverse_mul(mu.translate(0, 0, 0), mu.scale(*self.ballXYZLength))
        self.ballGLObject.paint(M, V, P, self.originDiffuseColor)
        # x axis
        M = mu.reverse_mul(mu.translate(0, 0, 1), mu.scale(.05, .05, 1))
        self.boxGLObject.paint(M, V, P, self.xAxisColor)
        # y axis
        M = mu.reverse_mul(mu.translate(1, 0, 0), mu.scale(1, .05, .05))
        self.boxGLObject.paint(M, V, P, self.yAxisColor)
        # z axis
        M = mu.reverse_mul(mu.translate(0, 1, 0), mu.scale(.05, 1, .05))
        self.boxGLObject.paint(M, V, P, self.zAxisColor)
        # bounding box
        x, y, z = self.boxXYZLength
        # rotate and translate the box so that its left bottom corner sits at origin
        M = mu.reverse_mul(mu.translate(x, z, y), mu.reverse_mul(mu.rotate([1, 0, 0], 90), mu.scale(*self.boxXYZLength)))
        self.boxGLObject.paint(M, V, P, self.boxDiffuseColor)

    def configure(self, configFilepath):
        """
        Configure the GL widget with options in the given configuration file
        in JSON format.
        """
        # don't catch any possible error. If no correct config, just crash.
        with open(configFilepath, 'r') as f:
            configTXT = f.read()
            confDic = json.loads(configTXT)
        # Frames per second
        self.FPS = confDic['FPS']
        # print FPS?
        self.fpsCounter = confDic['fpsCounter']
        # Trail length. This many spheres are drawn per trail at each frame.
        self.trailLength = confDic['trailLength']
        # x, y, z coordinates of light source in world coordinates
        self.lightPosWorld = np.array(confDic['lightPosWorld'], dtype='float32')
        # color of light in r, g, b
        self.lightColor = np.array(confDic['lightColor'], dtype='float32')
        # power of light source
        self.lightPower = confDic['lightPower']
        # background color in r, g, b, a
        self.backgroundColor = confDic['backgroundColor']
        # color of the ball in r, g, b, a
        self.ballDiffuseColor = np.array(
            confDic['ballDiffuseColor'],
            dtype='float32'
        )
        # color of the origin
        self.originDiffuseColor = np.array(
            confDic['originDiffuseColor'],
            dtype='float32'
        )
        # color of x axis
        self.xAxisColor = np.array(
            confDic['xAxisColor'],
            dtype='float32'
        )
        # color of y axis
        self.yAxisColor = np.array(
            confDic['yAxisColor'],
            dtype='float32'
        )
        # color of z axis
        self.zAxisColor = np.array(
            confDic['zAxisColor'],
            dtype='float32'
        )
        # x, y, z edge lengths of the bounding box in meters
        self.ballXYZLength = np.array(
            confDic['ballXYZLength'],
            dtype='float32'
        )
        # color of the box in r, g, b, a
        self.boxDiffuseColor = np.array(
            confDic['boxDiffuseColor'],
            dtype='float32'
        )
        # x, y, z axis lengths of the point ball in meters
        self.boxXYZLength = np.array(
            confDic['boxXYZLength'],
            dtype='float32'
        )
        # ambient color coefficients coeff_r, coeff_g, coeff_b.
        # Multiplied with color to determine the power of ambient lighting
        self.materialAmbientColorCoeffs = np.array(
            confDic['materialAmbientColorCoeffs'],
            dtype='float32'
        )
        # Specular color in r, g, b.
        self.materialSpecularColor = np.array(
            confDic['materialSpecularColor'],
            dtype='float32'
        )
        # Initiali position of camera in x, y, z
        self.position = confDic['initialCameraPosition']
        # Initial horizontal angle of camera in degrees
        self.horzAngle = np.radians(confDic['initialHorzAngle'])
        # Initial vertical angle of camera in degrees
        self.vertAngle = np.radians(confDic['initialVertAngle'])
        # Field of view
        self.fov = confDic['fov']
        # Speed of camera
        self.speed = confDic['speed']
        # Mouse speed (used to determine how fast user can chnage his view)
        self.mouseSpeed = confDic['mouseSpeed']
        # Mouse wheel speed (used to elevate up/down)
        self.mouseWheelSpeed = confDic['mouseWheelSpeed']
        # Obj file for ball model
        self.ballObjFile = confDic['ballObjFile']
        # Obj file for box model
        self.boxObjFile = confDic['boxObjFile']
        # Obj file for arrow model
        self.arrowObjFile = confDic['arrowObjFile']

    def setConstUniform(self):
        """
        Sets uniform values which is constant for the whole frame.
        """
        glUniform3fv(self.lightPosWorldID, 1, self.lightPosWorld)
        glUniform3fv(self.lightColorID, 1, self.lightColor)
        glUniform1f(self.lightPowerID, self.lightPower)
        glUniform3fv(self.materialAmbientColorCoeffsID, 1, self.materialAmbientColorCoeffs)
        glUniform3fv(self.materialSpecularColorID, 1, self.materialSpecularColor)

    def setDataPoints(self):
        """
        Gets a single point from self.dataQueue and puts it into self.dataPoints.
        If self.dataPoints contains less points self.trailLength, then no point
        is removed from it. When it reaches self.trailLength, for each point
        put into self.dataPoints a point is popped out of it in a FIFO fashion.
        """
        if not self.dataQueue.empty():
            newPoint = self.dataQueue.get()
            self.dataPoints.append(newPoint)
            if len(self.dataPoints) == self.trailLength:
                self.dataPoints.pop(0)

    def initUniforms(self, programID):
        """
        Creates locations for uniform variables used in the shader program.

        programID: Shader program ID.
        """
        self.VID = glGetUniformLocation(self.programID, "V")
        self.lightPosWorldID = glGetUniformLocation(self.programID, "LightPosition_worldspace")
        self.lightColorID = glGetUniformLocation(self.programID, "LightColor")
        self.lightPowerID = glGetUniformLocation(self.programID, "LightPower")
        self.materialAmbientColorCoeffsID = glGetUniformLocation(self.programID, "MaterialAmbientColorCoeffs")
        self.materialSpecularColorID = glGetUniformLocation(self.programID, "MaterialSpecularColor")

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
        # TODO: merge elapsed with timer
        self.elapsed = self.time.elapsed()/1000

        if self.fpsCounter:
            self.totalElapsedTime += self.elapsed
            self.paintCounter += 1
            if self.totalElapsedTime >= 1:
                print('FPS : {:2d}'.format(self.paintCounter), file=sys.stderr)
                self.totalElapsedTime = 0
                self.paintCounter = 0

        self.time.restart()
        self.update()

    def mousePressEvent(self, event):
        self.lastPos = QCursor.pos()
        self.setCursor(Qt.BlankCursor)
        self.resetMouseInputs()

    def getMouseInputs(self):
        """
        Manually grabs mouse inputs.

        Since we can get cursor information directly from QCursor class, we
        don't need Qt signals and events for mouse inputs.
        """
        if self.hasFocus():
            pos = QCursor.pos()
            self.inputs['mouseXDelta'] = pos.x() - self.width()/2
            self.inputs['mouseYDelta'] = pos.y() - self.height()/2

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
        up = mu.cross(right, direction)
        if self.inputs['up']:
            self.position += direction*deltaTime*self.speed
        if self.inputs['down']:
            self.position -= direction*deltaTime*self.speed
        if self.inputs['right']:
            self.position += right*deltaTime*self.speed
        if self.inputs['left']:
            self.position -= right*deltaTime*self.speed
        self.position += up*deltaTime*self.speed*self.inputs['wheelDelta']
        projection = mu.perspective(
            self.fov,                    # fov
            self.width()/self.height(),  # aspect ratio
            0.1,                         # distance to near clipping plane
            200,                         # distance to far clipping plane
        )
        view = mu.lookAt(
            self.position,               # camera position in world coordinates
            self.position + direction,   # where the camera looks at in world coordinates
            up,                          # up vector for camera. Used for orientation
        )
        return view, projection
