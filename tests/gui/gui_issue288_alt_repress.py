"""#288: pressing Alt again during an Alt+LMB tumble doesn't snap the persp view to an orthographic side view (Maya's
tumble never snaps), so the view keeps tumbling afterwards instead of staying locked like a top / front / side view."""

import os
import sys
from importlib import import_module

import bpy
from mathutils import Euler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, setup, step, win  # noqa: E402

C = {}


def view():
    return import_module(MODULE + ".ui.status_line").main_view3d(win().screen)


def at(fx, fy=0.5):
    _a, r = view()
    return int(r.x + r.width * fx), int(r.y + r.height * fy)


def move(f, alt=True):
    def fn():
        x, y = at(f)
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y, alt=alt)
    return fn


def key(type, value, alt, f=0.5):
    def fn():
        x, y = at(f)
        ev(type, value, x=x, y=y, alt=alt)
    return fn


def idle():
    pass


def rotating():
    return any(o.bl_idname == 'VIEW3D_OT_rotate' for o in win().modal_operators)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_near_front():
    bpy.ops.allset.keymap_activate()
    rv3d = view()[1].data
    rv3d.view_perspective = 'PERSP'
    # a few degrees off Blender's front view: close enough for an axis snap
    rv3d.view_rotation = Euler((1.50, 0.0, 0.08)).to_quaternion()


for _f in (move(0.45), key('LEFT_ALT', 'PRESS', True, 0.45), key('LEFTMOUSE', 'PRESS', True, 0.45),
           move(0.47), move(0.49)):
    step(_f)


@step
def s_dragging():
    check("Alt+LMB starts a tumble", rotating())


# Alt let go and pressed again while the left button is still down
for _f in (key('LEFT_ALT', 'RELEASE', False), move(0.495, False), key('LEFT_ALT', 'PRESS', True),
           move(0.5), move(0.5)):
    step(_f)


@step
def s_no_snap():
    rv3d = view()[1].data
    check(f"pressing Alt again mid-tumble keeps the view perspective ({rv3d.view_perspective})",
          rv3d.view_perspective == 'PERSP')


for _f in (key('LEFTMOUSE', 'RELEASE', True), key('LEFT_ALT', 'RELEASE', False), idle, idle, idle):
    step(_f)


@step
def s_after():
    rv3d = view()[1].data
    check(f"after the tumble the view is still perspective ({rv3d.view_perspective})",
          rv3d.view_perspective == 'PERSP')
    C["rot"] = rv3d.view_rotation.copy()


for _f in (move(0.4), key('LEFT_ALT', 'PRESS', True, 0.4), key('LEFTMOUSE', 'PRESS', True, 0.4),
           move(0.44), move(0.48), move(0.55)):
    step(_f)


@step
def s_again():
    check("a second Alt+LMB drag tumbles again", rotating())


for _f in (key('LEFTMOUSE', 'RELEASE', True, 0.55), key('LEFT_ALT', 'RELEASE', False, 0.55), idle):
    step(_f)


@step
def s_turned():
    rot = view()[1].data.view_rotation
    check("the second tumble turned the view", max(abs(a - b) for a, b in zip(rot, C["rot"])) > 1e-3)


run()
