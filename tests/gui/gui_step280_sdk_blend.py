"""#186: in a real UI: two Set Driven Key drivers summed on pCube1 Rotate Z (Maya blendWeighted).
ctrl.curl (0, 0) (10, 90) + ctrl.spread (0, 0) (10, -30) through the Set Driven Key window -> 10 / 10 = 60,
Ctrl+Z / Ctrl+Shift+Z over the last Key, then Save As + Open: the hidden inputs stay on their own data-block."""

import math
import os
import sys
import tempfile
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, dock_area, ev, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
PATH = os.path.join(tempfile.mkdtemp(), "sdk_blend.blend")


def dk():
    return import_module(MODULE + ".operators.driven_key")


def cb():
    return import_module(MODULE + ".ui.channel_box")


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def rz():
    bpy.context.view_layer.update()
    return math.degrees(bpy.data.objects["pCube1"].rotation_euler[2])


def select(name):
    for o in bpy.context.view_layer.objects:
        o.select_set(o.name == name)
    bpy.context.view_layer.objects.active = bpy.data.objects[name]


def pose(curl, spread, cube_rz=None):
    ctrl = bpy.data.objects["ctrl"]
    cb().set_value(ctrl, "cp:curl", float(curl))
    cb().set_value(ctrl, "cp:spread", float(spread))
    bpy.context.view_layer.update()
    if cube_rz is not None:
        select("pCube1")
        cb().apply_entry("rz", str(cube_rz))      # typed in the Channel Box: held while the window is open


def load(which, attr):
    select("ctrl" if which == 'DRIVER' else "pCube1")
    cb().set_selected_channels([attr])
    bpy.ops.allset.sdk_load(which=which)


def key(undo=False):
    bpy.ops.allset.sdk_key('EXEC_DEFAULT', undo)


def over_view():
    _area, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)


@step
def s_setup():
    setup()
    bpy.data.objects["Cube"].name = "pCube1"
    ctrl = bpy.data.objects.new("ctrl", None)
    ctrl.empty_display_type = 'PLAIN_AXES'
    ctrl.location = (0, -3, 0)
    ctrl["curl"] = 0.0
    ctrl["spread"] = 0.0
    bpy.context.scene.collection.objects.link(ctrl)
    dock_area('CHANNEL_BOX')
    bpy.ops.allset.sdk_window()
    redraw()


@step
def s_curl():
    load('DRIVER', "cp:curl")
    load('DRIVEN', "rz")
    pose(0, 0)
    key()
    pose(10, 0, 90)
    key()
    pose(0, 0)
    check(f"curl alone: 0 -> pCube1 Rotate Z 0 (got {rz():.3f})", abs(rz()) < 1e-3)


@step
def s_spread():
    load('DRIVER', "cp:spread")
    load('DRIVEN', "rz")
    pose(0, 0)
    key()
    pose(0, 10, -30)
    bpy.ops.ed.undo_push(message="posed")  # the scripted setup above made no undo steps of its own
    key(undo=True)                        # the last Key is one undo step (a button press)
    blend = dk().sdk_fcurve(bpy.data.objects["pCube1"], "rz")
    tex = dk().helper(create=False)
    check("two drivers = a summed channel whose inputs sit on the hidden helper",
          dk().is_blend(blend) and tex is not None and all(v.targets[0].id == tex for v in blend.driver.variables))
    pose(10, 10)
    check(f"curl 10 + spread 10 -> Rotate Z 60 like Maya (got {rz():.3f})", abs(rz() - 60) < 1e-3)
    select("pCube1")
    redraw()


@step
def s_shot_sum():
    shot("gui_step280_sum60.png")
    over_view()


@step
def s_undo():
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def s_check_undo():
    fc = dk().driver_curve(bpy.data.objects["pCube1"], "rz", bpy.data.objects["ctrl"], "cp:spread")
    check(f"Ctrl+Z takes back the last Key (spread keys {fc and len(fc.keyframe_points)})",
          fc is not None and len(fc.keyframe_points) == 1)
    over_view()
    ev('Z', 'PRESS', ctrl=True, shift=True)
    ev('Z', 'RELEASE', ctrl=True, shift=True)


@step
def s_check_redo():
    fc = dk().driver_curve(bpy.data.objects["pCube1"], "rz", bpy.data.objects["ctrl"], "cp:spread")
    check(f"Ctrl+Shift+Z brings it back (spread keys {fc and len(fc.keyframe_points)})",
          fc is not None and len(fc.keyframe_points) == 2)
    bpy.ops.allset.sdk_close()
    pose(10, 10)
    check(f"after redo 10 / 10 -> 60 (got {rz():.3f})", abs(rz() - 60) < 1e-3)
    bpy.ops.wm.save_as_mainfile(filepath=PATH)


@step
def s_open():
    bpy.ops.wm.open_mainfile(filepath=PATH)


@step
def s_check_open():
    check(f"one helper after Open (got {[t.name for t in dk().helpers()]})", len(dk().helpers()) == 1)
    for curl, spread, want in ((10, 0, 90), (0, 10, -30), (10, 10, 60), (5, 0, 45)):
        pose(curl, spread)
        check(f"reopened: curl {curl} spread {spread} -> {want} (got {rz():.3f})", abs(rz() - want) < 1e-3)
    pose(10, 10)
    select("pCube1")
    redraw()


@step
def s_shot_open():
    shot("gui_step280_reopened.png")


run()
