"""In a real UI: drag the Move gizmo's X arrow, then MMB drag anywhere moves along X
only (Maya active handle); tap W again (centre handle) and MMB drag moves freely."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, tap, view3d, win  # noqa: E402

C = {}


def v3d_override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def arrow(ob, axis):
    area, region = view3d()
    o = location_3d_to_region_2d(region, region.data, ob.matrix_world.translation)
    a = location_3d_to_region_2d(region, region.data, ob.matrix_world.translation + axis * 0.1)
    d = (a - o).normalized()
    size = bpy.context.preferences.view.gizmo_size * bpy.context.preferences.system.ui_scale
    p = o + d * size * 0.75
    return int(region.x + p.x), int(region.y + p.y), d


def drag(button, x, y, dx, dy):
    ev(button, 'PRESS', x=x, y=y)
    for i in range(1, 9):
        ev('MOUSEMOVE', 'NOTHING', x=x + dx * i // 8, y=y + dy * i // 8)
    ev(button, 'RELEASE', x=x + dx, y=y + dy)


def cube():
    return bpy.data.objects["Cube"]


@step
def s_setup():
    C["x"], C["y"] = setup()
    for o in bpy.context.view_layer.objects:
        o.select_set(o is cube())
    bpy.context.view_layer.objects.active = cube()
    with v3d_override():
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    manip = import_module(MODULE + ".operators.manip")
    manip.HANDLES.clear()
    x, y, d = arrow(cube(), Vector((1, 0, 0)))
    C["g"] = (x, y, d)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y)


@step
def s_x_drag():
    x, y, d = C["g"]
    drag('LEFTMOUSE', x, y, int(d.x * 60), int(d.y * 60))


@step
def s_wait():
    pass    # the press watcher reads the registered transform


@step
def s_remembered():
    handles = import_module(MODULE + ".operators.manip").HANDLES
    h = handles.get('TRANSLATE')
    check(f"the X arrow drag is remembered ({h})", h is not None and h["constraint_axis"] == (True, False, False))
    C["loc"] = cube().location.copy()
    # MMB drag far from the gizmo, diagonally (a free move would change Y/Z too)
    x, y = C["x"] - 250, C["y"] + 150
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('MIDDLEMOUSE', 'PRESS', x=x, y=y)


# The nested transform modal (started by allset.manip_mmb on the press) needs a tick
# before it sees mouse moves in event simulation: press, moves and release in separate steps.
@step
def s_mmb_move():
    x, y = C["x"] - 250, C["y"] + 150
    for i in range(1, 9):
        ev('MOUSEMOVE', 'NOTHING', x=x + 80 * i // 8, y=y - 70 * i // 8)


@step
def s_mmb_release():
    x, y = C["x"] - 250, C["y"] + 150
    ev('MIDDLEMOUSE', 'RELEASE', x=x + 80, y=y - 70)


@step
def s_mmb_x():
    moved = cube().location - C["loc"]
    check(f"MMB drag anywhere moves along X only ({tuple(round(v, 3) for v in moved)})",
          abs(moved.x) > 0.05 and abs(moved.y) < 1e-5 and abs(moved.z) < 1e-5)
    C["loc"] = cube().location.copy()
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    tap('W')


@step
def s_reset():
    handles = import_module(MODULE + ".operators.manip").HANDLES
    check(f"tapping W on the Move tool resets to the centre handle ({handles.get('TRANSLATE')})",
          handles.get('TRANSLATE') is None)
    x, y = C["x"] - 250, C["y"] + 150
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('MIDDLEMOUSE', 'PRESS', x=x, y=y)


@step
def s_free_move():
    s_mmb_move()


@step
def s_free_release():
    s_mmb_release()


@step
def s_mmb_free():
    moved = cube().location - C["loc"]
    check(f"after the reset MMB drag moves freely ({tuple(round(v, 3) for v in moved)})",
          (abs(moved.y) > 1e-3 or abs(moved.z) > 1e-3) and moved.length > 0.05)


run()
