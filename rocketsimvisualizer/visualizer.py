from rocketsimvisualizer.models import obj
import RocketSim

from pyqtgraph.Qt import QtCore
import pyqtgraph as pg
import pyqtgraph.opengl as gl

import numpy as np
import math

from controller import XboxController

from collections import defaultdict
import pathlib
import tomli

current_dir = pathlib.Path(__file__).parent

with open(current_dir / "rsvconfig-default.toml", "rb") as file:
    default_config_dict = tomli.load(file)

# Get key mappings from Qt namespace
qt_keys = (
    (getattr(QtCore.Qt, attr), attr[4:])
    for attr in dir(QtCore.Qt)
    if attr.startswith("Key_")
)
keys_mapping = defaultdict(lambda: "unknown", qt_keys)


class KeyPressWindow(gl.GLViewWidget):
    sigKeyPress = QtCore.pyqtSignal(object)
    sigKeyRelease = QtCore.pyqtSignal(object)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            return
        self.sigKeyPress.emit(event)

    def keyReleaseEvent(self, event):
        if event.isAutoRepeat():
            return
        self.sigKeyRelease.emit(event)


class Visualizer:
    def __init__(self, arena,
                 tick_rate=120, tick_skip=2,
                 step_arena=False, overwrite_controls=False,
                 config_dict=None, kbm=True):
        self.arena = arena
        self.tick_rate = tick_rate
        self.tick_skip = tick_skip
        self.step_arena = step_arena
        self.overwrite_controls = overwrite_controls
        self.kbm = kbm
        self.y_pressed = False
        self.start_pressed = False
        self.back_pressed = False
        if kbm == False:
            self.joy = XboxController()

        if config_dict is None:
            print("Using default configs")
            config_dict = default_config_dict

        self.input_dict = config_dict["INPUT"]
        self.cam_dict = config_dict["CAMERA"]

        self.app = pg.mkQApp()

        # window settings
        self.w = KeyPressWindow()
        self.w.setWindowTitle("pyqtgraph visualizer")
        self.w.setGeometry(0, 50, 1280, 720)

        # initial camera settings
        self.target_cam = False
        self.w.opts["fov"] = self.cam_dict["FOV"]
        self.w.opts["distance"] = self.cam_dict["DISTANCE"]
        self.w.show()

        # Add ground grid
        grid_item = gl.GLGridItem()
        grid_item.setSize(8192, 10240 + 880 * 2, 1)
        grid_item.setSpacing(100, 100, 100)
        self.w.addItem(grid_item)

        # text info
        self.text_item = gl.GLTextItem(pos=(0, 0, 60))

        self.default_edge_color = (1, 1, 1, 1)

        # Create stadium 3d model
        stadium_object = obj.OBJ(current_dir / "models/field_simplified.obj")
        stadium_md = gl.MeshData(vertexes=stadium_object.vertices, faces=stadium_object.faces)
        stadium_mi = gl.GLMeshItem(meshdata=stadium_md, smooth=False, drawFaces=False, drawEdges=True,
                                   edgeColor=self.default_edge_color)
        stadium_mi.rotate(90, 0, 0, 1)
        self.w.addItem(stadium_mi)

        # Create ball geometry
        ball_radius = self.arena.ball.get_radius() * 50
        ball_md = gl.MeshData.sphere(rows=8, cols=16, radius=ball_radius)
        self.ball_mi = gl.GLMeshItem(meshdata=ball_md, smooth=False, drawFaces=True, drawEdges=True,
                                     edgeColor=self.default_edge_color, color=(0.1, 0.1, 0.1, 1))
        self.w.addItem(self.ball_mi)

        # Create ground projection for the ball
        ball_proj_md = gl.MeshData.cylinder(rows=1, cols=16, length=0, radius=round(ball_radius))
        self.ball_proj = gl.GLMeshItem(meshdata=ball_proj_md, smooth=False, drawFaces=False,
                                       drawEdges=True, edgeColor=self.default_edge_color)
        self.w.addItem(self.ball_proj)

        # Create boost geometry
        big_pad_md = gl.MeshData.cylinder(rows=1, cols=4, length=64, radius=160)
        small_pad_md = gl.MeshData.cylinder(rows=1, cols=4, length=64, radius=144)

        self.pads_mi = []
        for pad in arena.get_boost_pads():
            pad_pos = pad.get_pos()
            pad_md = big_pad_md if pad.is_big else small_pad_md
            pad_mi = gl.GLMeshItem(meshdata=pad_md, drawFaces=False, drawEdges=True,
                                   edgeColor=self.default_edge_color)
            pad_mi.rotate(45, 0, 0, 1)
            pad_mi.translate(-pad_pos.x, pad_pos.y, pad_pos.z)
            self.pads_mi.append(pad_mi)
            self.w.addItem(pad_mi)

        # Create car geometry
        car_object = obj.OBJ(current_dir / "models/Octane_decimated.obj")
        car_md = gl.MeshData(vertexes=car_object.vertices, faces=car_object.faces)

        self.blue_color = (0, 0.4, 0.8, 1)
        self.orange_color = (1, 0.2, 0.1, 1)

        self.cars_mi = []
        for car in arena.get_cars():

            car_color = self.blue_color if car.team == 0 else self.orange_color

            car_mi = gl.GLMeshItem(meshdata=car_md, smooth=False,
                                   drawFaces=True, drawEdges=True,
                                   color=car_color, edgeColor=self.default_edge_color)

            self.cars_mi.append(car_mi)
            self.w.addItem(car_mi)

            # hitbox
            car_config = car.get_config()
            hitbox_size = car_config.hitbox_size
            dia_conv = 1 / math.sqrt(2)
            hitbox_offset = car_config.hitbox_pos_offset
            car_hitbox_md = gl.MeshData.cylinder(rows=1, cols=4, radius=(dia_conv, dia_conv))

            hitbox_mi = gl.GLMeshItem(meshdata=car_hitbox_md, smooth=False,
                                      drawFaces=False, drawEdges=True,
                                      edgeColor=self.default_edge_color)

            hitbox_mi.rotate(45, 0, 0, 1)
            hitbox_mi.translate(0, 0, -0.5)  # by default cylinder origin z loc is at 0.5 length
            hitbox_mi.scale(hitbox_size.x, hitbox_size.y, hitbox_size.z, local=False)
            hitbox_mi.translate(-hitbox_offset.x, hitbox_offset.y, hitbox_offset.z, local=False)
            hitbox_mi.setParentItem(car_mi)

        # index of the car we control/spectate
        self.car_index = 0

        # item to track with target cam
        self.target_index = -1

        # connect key press events to update our controls
        self.is_pressed_dict = {input_key: False for input_key in self.input_dict.values()}
        self.controls = RocketSim.CarControls()
        self.w.sigKeyPress.connect(self.update_controls)
        self.w.sigKeyRelease.connect(self.release_controls)
        self.app.focusChanged.connect(self.reset_controls)

        self.update()

    def get_cam_targets(self):
        if not self.cars_mi:
            return [self.ball_mi]
        targets = self.cars_mi + [self.ball_mi]
        targets.pop(self.car_index)
        return targets

    def get_cam_target(self):
        targets = self.get_cam_targets()
        self.target_index = self.target_index % len(targets)
        return targets[self.target_index]

    def reset_controls(self):
        for key in self.is_pressed_dict.keys():
            self.is_pressed_dict[key] = False
        self.controls = RocketSim.CarControls()

    def release_controls(self, event):
        self.update_controls(event, is_pressed=False)

    def update_controls(self, event, is_pressed=True):
        if self.kbm == True:
            key = keys_mapping[event.key()]
            if key in self.input_dict.keys():
                self.is_pressed_dict[self.input_dict[key]] = is_pressed

            if self.input_dict.get(key, None) == "SWITCH_CAR" and is_pressed:
                if self.overwrite_controls:  # reset car controls before switching cars
                    self.arena.get_cars()[self.car_index].set_controls(RocketSim.CarControls())
                self.car_index = (self.car_index + 1) % len(self.cars_mi)

            if self.input_dict.get(key, None) == "TARGET_CAM" and is_pressed:
                self.target_cam = not self.target_cam

            if self.input_dict.get(key, None) == "CYCLE_TARGETS" and is_pressed:
                self.target_index = (self.target_index + 1) % len(self.get_cam_targets())

            self.controls.throttle = self.is_pressed_dict["FORWARD"] - self.is_pressed_dict["BACKWARD"]
            self.controls.steer = self.is_pressed_dict["RIGHT"] - self.is_pressed_dict["LEFT"]
            self.controls.roll = self.is_pressed_dict["ROLL_RIGHT"] - self.is_pressed_dict["ROLL_LEFT"]
            self.controls.pitch = -self.controls.throttle
            self.controls.yaw = self.controls.steer
            self.controls.jump = self.is_pressed_dict["JUMP"]
            self.controls.handbrake = self.is_pressed_dict["POWERSLIDE"]
            self.controls.boost = self.is_pressed_dict["BOOST"]
        else:
            controls = self.joy.read()
            self.controls.throttle = controls['RT'] or -controls['LT']
            self.controls.steer = controls["leftX"]
            self.controls.roll = controls['RB'] or -controls['LB']
            self.controls.pitch = -controls["leftY"]
            self.controls.yaw = controls["leftX"]
            self.controls.jump = controls["A"]
            self.controls.handbrake = controls["X"]
            self.controls.boost = controls["B"]
            if controls['Y'] and self.y_pressed == False:
                self.target_cam = not self.target_cam
                self.y_pressed = True
            if controls['START'] and self.start_pressed == False:
                self.target_index = (self.target_index + 1) % len(self.get_cam_targets())
                self.start_pressed = True
            if controls['BACK'] and self.back_pressed == False:
                self.back_pressed = True
                if self.overwrite_controls:  # reset car controls before switching cars
                    self.arena.get_cars()[self.car_index].set_controls(RocketSim.CarControls())
                self.car_index = (self.car_index + 1) % len(self.cars_mi)
            
            if controls['START'] == False and self.start_pressed == True:
                self.start_pressed = False     
            if controls['BACK'] == False and self.back_pressed == True:
                self.back_pressed == False
            if controls['Y'] == False and self.y_pressed == True:
                self.y_pressed = False

    def update_boost_pad_data(self):
        for i, pad in enumerate(self.arena.get_boost_pads()):
            pad_state = pad.get_state()
            self.pads_mi[i].show() if pad_state.is_active else self.pads_mi[i].hide()

    def update_ball_data(self):

        # plot ball data
        ball_state = self.arena.ball.get_state()

        # approx ball spin
        ball_angvel_np = np.array([ball_state.ang_vel.x, -ball_state.ang_vel.y, ball_state.ang_vel.z])
        rot_angle = np.linalg.norm(ball_angvel_np)
        rot_axis = ball_angvel_np / max(1e-9, rot_angle)
        delta_rot_angle = rot_angle * self.tick_skip / self.tick_rate

        self.ball_mi.rotate(delta_rot_angle / math.pi * 180, *rot_axis, local=False)

        # location
        ball_transform = self.ball_mi.transform()
        ball_transform[0, 3] = -ball_state.pos.x
        ball_transform[1, 3] = ball_state.pos.y
        ball_transform[2, 3] = ball_state.pos.z
        self.ball_mi.setTransform(ball_transform)

        # ball ground projection
        self.ball_proj.resetTransform()
        self.ball_proj.translate(-ball_state.pos.x, ball_state.pos.y, 0)

    def update_cars_data(self):

        for i, car in enumerate(self.arena.get_cars()):

            car_state = car.get_state()
            car_angles = car_state.angles

            self.cars_mi[i].resetTransform()

            # location
            self.cars_mi[i].translate(-car_state.pos.x, car_state.pos.y, car_state.pos.z)

            # rotation
            self.cars_mi[i].rotate(car_angles.yaw / math.pi * 180, 0, 0, -1, local=True)
            self.cars_mi[i].rotate(car_angles.pitch / math.pi * 180, 0, 1, 0, local=True)
            self.cars_mi[i].rotate(car_angles.roll / math.pi * 180, -1, 0, 0, local=True)

            # visual indicator for going supersonic
            self.cars_mi[i].opts["edgeColor"] = (0, 0, 0, 1) if car_state.is_supersonic else self.default_edge_color

    def update_camera_data(self):

        # calculate target cam values
        if self.target_cam:
            cam_pos = self.w.cameraPosition()
            target_pos = self.get_cam_target().transform().matrix()[:3, 3]
            rel_target_pos = -target_pos[0] + cam_pos[0], target_pos[1] - cam_pos[1], target_pos[2] - cam_pos[2]
            rel_target_pos_norm = np.linalg.norm(rel_target_pos)

            target_azimuth = math.atan2(rel_target_pos[1], rel_target_pos[0])

            target_elevation = 0
            if rel_target_pos_norm != 0:
                target_elevation = math.asin(rel_target_pos[2] / rel_target_pos_norm)

            smaller_target_elevation = target_elevation * 2 / 3

            self.w.setCameraParams(azimuth=-target_azimuth / math.pi * 180,
                                   elevation=self.cam_dict["ANGLE"] - smaller_target_elevation / math.pi * 180)

        if self.cars_mi:

            car = self.arena.get_cars()[self.car_index]
            car_state = car.get_state()

            # center camera around the car
            self.w.opts["center"] = pg.Vector(-car_state.pos.x, car_state.pos.y, car_state.pos.z + self.cam_dict["HEIGHT"])

            if not self.target_cam:
                # non-target_cam cam
                car_vel_2d_norm = math.sqrt(car_state.vel.y ** 2 + car_state.vel.x ** 2)
                if car_vel_2d_norm > 50:  # don't be sensitive to near 0 vel dir changes
                    car_vel_azimuth = math.atan2(car_state.vel.y, car_state.vel.x)
                    self.w.setCameraParams(azimuth=-car_vel_azimuth / math.pi * 180,
                                           elevation=self.cam_dict["ANGLE"])

    def update_text_data(self):
        if self.cars_mi:
            car_state = self.arena.get_cars()[self.car_index].get_state()
            self.text_item.text = f"{car_state.boost=:.1f}"
            self.text_item.setParentItem(self.cars_mi[self.car_index])

    def update_plot_data(self):
        self.update_boost_pad_data()
        self.update_ball_data()
        self.update_cars_data()
        self.update_camera_data()
        self.update_text_data()

    def update(self):

        # only set car controls if overwrite_controls is true and there's at least one car
        if self.overwrite_controls and self.cars_mi:
            self.arena.get_cars()[self.car_index].set_controls(self.controls)

        # only call arena.step() if running in standalone mode
        if self.step_arena:
            self.arena.step(self.tick_skip)
        if self.kbm == False:
            self.update_controls(None)
        self.update_plot_data()

    def animation(self):
        timer = QtCore.QTimer()
        timer.timeout.connect(self.update)
        timer.start(16)
        self.app.exec()
