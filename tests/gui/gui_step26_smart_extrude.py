"""In a real UI: Shift+drag the Move gizmo on a face = Smart Extrude (new faces,
the extruded face moves, nothing else); Shift+click without dragging changes nothing;
an object Shift+drag cancelled with RMB leaves no copy; W hold menu check boxes."""

import os
import sys

import bmesh
import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, step, setup, screenshot, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def v3d_override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def counts():
    ob = bpy.data.objects["Cube"]
    bm = bmesh.from_edit_mesh(ob.data)
    return len(bm.verts), len(bm.edges), len(bm.faces)


def top_z():
    bm = bmesh.from_edit_mesh(bpy.data.objects["Cube"].data)
    return max(v.co.z for v in bm.verts)


def arrow(origin, axis):
    area, region = view3d()
    o = location_3d_to_region_2d(region, region.data, origin)
    a = location_3d_to_region_2d(region, region.data, origin + axis * 0.1)
    d = (a - o).normalized()
    size = bpy.context.preferences.view.gizmo_size * bpy.context.preferences.system.ui_scale
    p = o + d * size * 0.75
    return int(region.x + p.x), int(region.y + p.y), d


def hover(x, y):
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y)


def shift_down():
    # A simulated keyboard event's modifiers reach the window event state (mouse events' don't):
    # pressing LEFT_SHIFT first makes the LMB press and its CLICK_DRAG real Shift events.
    ev('LEFT_SHIFT', 'PRESS', shift=True)


def shift_up():
    ev('LEFT_SHIFT', 'RELEASE')


def press_drag(x, y, d, dist):
    shift_down()
    ev('LEFTMOUSE', 'PRESS', x=x, y=y, shift=True)
    for i in range(1, 9):
        ev('MOUSEMOVE', 'NOTHING', x=int(x + d.x * dist * i / 8), y=int(y + d.y * dist * i / 8), shift=True)


@step
def s_setup():
    C["x"], C["y"] = setup()
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
def s_extrude_press():
    x, y, d = C["g"]
    press_drag(x, y, d, 70)


@step
def s_extrude_shot():
    shot("gui_step26_smart_extrude.png")
    x, y, d = C["g"]
    ev('LEFTMOUSE', 'RELEASE', x=int(x + d.x * 70), y=int(y + d.y * 70), shift=True)
    shift_up()


@step
def s_extrude_wait():
    pass   # the watch timer runs (0.05 s ticks)


@step
def s_extruded():
    c = counts()
    check(f"Shift+drag on the face = Smart Extrude ({C['before']} -> {c})", c == (12, 20, 10))
    check(f"the extruded face moved up, the old top stayed (top z {top_z():.3f})", top_z() > 1.05)
    C["before"] = c
    ob = bpy.data.objects["Cube"]
    bm = bmesh.from_edit_mesh(ob.data)
    top = max((f for f in bm.faces if f.select), key=lambda f: f.calc_center_median().z)
    C["g"] = arrow(top.calc_center_median(), Vector((0, 0, 1)))
    hover(*C["g"][:2])


@step
def s_click_press():
    x, y, _d = C["g"]
    shift_down()
    ev('LEFTMOUSE', 'PRESS', x=x, y=y, shift=True)


@step
def s_click_release():
    x, y, _d = C["g"]
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y, shift=True)
    shift_up()


@step
def s_click_wait():
    pass


@step
def s_clicked():
    check(f"Shift+click without dragging changes nothing ({C['before']} -> {counts()})",
          counts() == C["before"])
    tap('F8')


@step
def s_object_mode():
    check(f"F8 -> object mode ({bpy.context.mode})", bpy.context.mode == 'OBJECT')
    C["n"] = len(bpy.data.objects)
    with v3d_override():
        bpy.ops.wm.tool_set_by_id(name="builtin.move")   # tools are per mode
    cube = bpy.data.objects["Cube"]
    C["g"] = arrow(cube.matrix_world.translation, Vector((1, 0, 0)))
    hover(*C["g"][:2])


@step
def s_dup_press():
    x, y, d = C["g"]
    press_drag(x, y, d, 60)


@step
def s_dup_cancel():
    check(f"Shift+drag on the object made a copy ({C['n']} -> {len(bpy.data.objects)})",
          len(bpy.data.objects) == C["n"] + 1)
    x, y, d = C["g"]
    ev('RIGHTMOUSE', 'PRESS', x=int(x + d.x * 60), y=int(y + d.y * 60), shift=True)
    ev('RIGHTMOUSE', 'RELEASE', x=int(x + d.x * 60), y=int(y + d.y * 60), shift=True)
    ev('LEFTMOUSE', 'RELEASE', x=int(x + d.x * 60), y=int(y + d.y * 60))
    shift_up()


@step
def s_cancel_wait():
    pass


@step
def s_cancelled():
    cube = bpy.data.objects["Cube"]
    check(f"RMB cancel takes the copy back ({sorted(o.name for o in bpy.data.objects)})",
          len(bpy.data.objects) == C["n"])
    check("the original is selected and active again",
          cube.select_get() and bpy.context.view_layer.objects.active is cube)
    ev('MOUSEMOVE', 'NOTHING', x=C["x"] - 200, y=C["y"])
    ev('W', 'PRESS', x=C["x"] - 200, y=C["y"])
    ev('LEFTMOUSE', 'PRESS', x=C["x"] - 200, y=C["y"])


@step
def s_menu_wait():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_menu_shot():
    shot("gui_step26_w_menu_checks.png")
    ev('LEFTMOUSE', 'RELEASE', x=C["x"] - 200, y=C["y"])
    ev('W', 'RELEASE', x=C["x"] - 200, y=C["y"])
    tap('ESC')
    check("W hold menu opened (screenshot)", True)


run()
