"""Smart Extrude where the OS can't say whether the mouse button is held (Linux, macOS): Shift+press on the Move
manipulator, hold still for a while, then drag = the face extrudes and the new face moves; a Shift+click without a
drag changes nothing; a slow Shift+drag in Object Mode still duplicates."""

import os
import sys
from importlib import import_module

import bmesh
import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, tap, view3d, win  # noqa: E402

C = {}


def v3d_override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def counts():
    bm = bmesh.from_edit_mesh(bpy.data.objects["Cube"].data)
    return len(bm.verts), len(bm.edges), len(bm.faces)


def top_z():
    bm = bmesh.from_edit_mesh(bpy.data.objects["Cube"].data)
    return max(v.co.z for v in bm.verts)


def arrow(origin, axis):
    _area, region = view3d()
    o = location_3d_to_region_2d(region, region.data, origin)
    a = location_3d_to_region_2d(region, region.data, origin + axis * 0.1)
    d = (a - o).normalized()
    size = bpy.context.preferences.view.gizmo_size * bpy.context.preferences.system.ui_scale
    p = o + d * size * 0.75
    return int(region.x + p.x), int(region.y + p.y), d


def hover(x, y):
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y)


def shift_press():
    x, y, _d = C["g"]
    ev('LEFT_SHIFT', 'PRESS', shift=True)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y, shift=True)


def drag(dist):
    x, y, d = C["g"]
    for i in range(1, 9):
        ev('MOUSEMOVE', 'NOTHING', x=int(x + d.x * dist * i / 8), y=int(y + d.y * dist * i / 8), shift=True)


def release(dist):
    x, y, d = C["g"]
    ev('LEFTMOUSE', 'RELEASE', x=int(x + d.x * dist), y=int(y + d.y * dist), shift=True)
    ev('LEFT_SHIFT', 'RELEASE')


@step
def s_setup():
    C["x"], C["y"] = setup()
    import_module(MODULE + ".operators.keystate").is_down = lambda _t: None     # like Linux / macOS
    cube = bpy.data.objects["Cube"]
    for o in bpy.context.view_layer.objects:
        o.select_set(o is cube)
    bpy.context.view_layer.objects.active = cube
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    tap('F11')


@step
def s_face_selected():
    with v3d_override():
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    ob = bpy.data.objects["Cube"]
    bm = bmesh.from_edit_mesh(ob.data)
    top = max(bm.faces, key=lambda f: f.calc_center_median().z)
    top.select = True
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    C["before"] = counts()
    C["g"] = arrow(Vector((0, 0, 1)), Vector((0, 0, 1)))
    hover(*C["g"][:2])


@step
def s_press():
    shift_press()


@step
def s_hold_still():
    check(f"the press extruded at once and keeps it while the button is held ({counts()})", counts() == (12, 20, 10))


@step
def s_drag():
    drag(70)


@step
def s_release():
    release(70)


@step
def s_release_wait():
    pass


@step
def s_extruded():
    c = counts()
    check(f"a slow Shift+drag = Smart Extrude ({C['before']} -> {c})", c == (12, 20, 10))
    check(f"the extruded face moved up (top z {top_z():.3f})", top_z() > 1.05)
    C["before"] = c
    bm = bmesh.from_edit_mesh(bpy.data.objects["Cube"].data)
    top = max((f for f in bm.faces if f.select), key=lambda f: f.calc_center_median().z)
    C["g"] = arrow(top.calc_center_median(), Vector((0, 0, 1)))
    hover(*C["g"][:2])


@step
def s_click_press():
    shift_press()


@step
def s_click_hold():
    pass


@step
def s_click_release():
    release(0)


@step
def s_click_wait():
    pass


@step
def s_clicked():
    check(f"Shift+click without dragging changes nothing ({C['before']} -> {counts()})", counts() == C["before"])
    tap('F8')


@step
def s_object_mode():
    check(f"F8 -> object mode ({bpy.context.mode})", bpy.context.mode == 'OBJECT')
    C["n"] = len(bpy.data.objects)
    with v3d_override():
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    cube = bpy.data.objects["Cube"]
    C["g"] = arrow(cube.matrix_world.translation, Vector((1, 0, 0)))
    hover(*C["g"][:2])


@step
def s_dup_press():
    shift_press()


@step
def s_dup_hold():
    pass


@step
def s_dup_drag():
    drag(60)


@step
def s_dup_release():
    release(60)


@step
def s_dup_wait():
    pass


@step
def s_duplicated():
    n = len(bpy.data.objects)
    check(f"a slow Shift+drag on the object keeps its copy ({C['n']} -> {n})", n == C["n"] + 1)
    check("the original stays where it was", bpy.data.objects["Cube"].location.length < 1e-6)


run()
