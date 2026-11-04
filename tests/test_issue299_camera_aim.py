"""#299: Create > Cameras > Camera and Aim / Camera, Aim and Up.

Like Maya: camera1 and camera1_aim (and camera1_up) under camera1_group; the camera looks at the aim with world up,
the up node rolls it; each node moves on its own and moving the group moves the whole rig."""

import math
from importlib import import_module

import bpy
from mathutils import Vector

import kit

menu_map = import_module(kit.MODULE + ".ui.menu_map")


def _clean():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _make(kind):
    _clean()
    assert bpy.ops.allset.create(kind=kind) == {'FINISHED'}
    bpy.context.view_layer.update()
    return {ob.name: ob for ob in bpy.data.objects}


def _view_dir(cam):
    # a Blender camera looks along its local -Z
    return (cam.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()


def _up_dir(cam):
    return (cam.matrix_world.to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()


def test_menu_items_reach_the_rigs():
    assert menu_map.MAP["Create/Cameras/Camera"] == ("allset.create", {"kind": 'CAMERA'})
    assert menu_map.MAP["Create/Cameras/Camera and Aim"] == ("allset.create", {"kind": 'CAMERA_AIM'})
    assert menu_map.MAP["Create/Cameras/Camera, Aim and Up"] == ("allset.create", {"kind": 'CAMERA_AIM_UP'})
    assert "Create/Cameras" not in menu_map.MAP, "Cameras must open its submenu"


def test_camera_and_aim():
    obs = _make('CAMERA_AIM')
    assert set(obs) == {"camera1", "camera1_aim", "camera1_group"}, set(obs)
    cam, aim, group = obs["camera1"], obs["camera1_aim"], obs["camera1_group"]
    assert cam.type == 'CAMERA' and aim.type == 'EMPTY' and group.type == 'EMPTY'
    assert cam.parent == group and aim.parent == group and group.parent is None
    # looks at the aim, 5 units ahead
    to_aim = (aim.matrix_world.translation - cam.matrix_world.translation)
    assert abs(to_aim.length - 5.0) < 1e-4, to_aim.length
    assert _view_dir(cam).angle(to_aim.normalized()) < 1e-4
    # the aim moves on its own; the camera follows it and stays level (world up)
    aim.location = Vector((3.0, 5.0, 2.0))
    bpy.context.view_layer.update()
    to_aim = (aim.matrix_world.translation - cam.matrix_world.translation).normalized()
    assert _view_dir(cam).angle(to_aim) < 1e-4
    right = (cam.matrix_world.to_3x3() @ Vector((1.0, 0.0, 0.0)))
    assert abs(right.z) < 1e-4, "no roll without an up node"
    # moving the group moves the whole rig
    group.location = Vector((10.0, 0.0, 0.0))
    bpy.context.view_layer.update()
    assert abs(cam.matrix_world.translation.x - 10.0) < 1e-4
    assert abs(aim.matrix_world.translation.x - 13.0) < 1e-4


def test_camera_aim_and_up():
    obs = _make('CAMERA_AIM_UP')
    assert set(obs) == {"camera1", "camera1_aim", "camera1_up", "camera1_group"}, set(obs)
    cam, up = obs["camera1"], obs["camera1_up"]
    assert up.parent == obs["camera1_group"]
    assert _up_dir(cam).z > 0.99, "camera starts upright"
    # the up node to the side rolls the camera towards it
    up.location = Vector((5.0, 0.0, 0.0))
    bpy.context.view_layer.update()
    to_aim = (obs["camera1_aim"].matrix_world.translation - cam.matrix_world.translation).normalized()
    assert _view_dir(cam).angle(to_aim) < 1e-3
    roll = _up_dir(cam)
    assert roll.x > 0.5, roll
    assert math.degrees(roll.angle(Vector((0.0, 0.0, 1.0)))) > 30.0


def test_plain_camera_unchanged():
    obs = _make('CAMERA')
    assert set(obs) == {"camera1"}, set(obs)
    assert not obs["camera1"].constraints
