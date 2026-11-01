"""In a real UI: a Shift+drag on the Move manipulator shows what it does as an in-view message —
"Shift Extrude" on faces, "Shift Duplicate" on objects; a Shift+click shows nothing, and the
In-View Messages preference turns it off."""

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


def vm():
    from bl_ext.user_default.allset.ui import view_message
    return view_message


def prefs():
    from bl_ext.user_default.allset import preferences
    return preferences.get(bpy.context)


def clear_message():
    vm()._state.update(text="")


def v3d_override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


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


def press_drag(x, y, d, dist):
    # A keyboard Shift press first: its modifier reaches the window state, so the drag is a real Shift drag
    ev('LEFT_SHIFT', 'PRESS', shift=True)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y, shift=True)
    for i in range(1, 9):
        ev('MOUSEMOVE', 'NOTHING', x=int(x + d.x * dist * i / 8), y=int(y + d.y * dist * i / 8), shift=True)


def release(x, y, d, dist):
    ev('LEFTMOUSE', 'RELEASE', x=int(x + d.x * dist), y=int(y + d.y * dist), shift=True)
    ev('LEFT_SHIFT', 'RELEASE')


@step
def s_setup():
    C["x"], C["y"] = setup()
    cube = bpy.data.objects["Cube"]
    for o in bpy.context.view_layer.objects:
        o.select_set(o is cube)
    bpy.context.view_layer.objects.active = cube
    prefs().in_view_messages = True
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
    C["g"] = arrow(Vector((0, 0, 1)), Vector((0, 0, 1)))
    hover(*C["g"][:2])
    clear_message()


@step
def s_click_press():
    x, y, _d = C["g"]
    ev('LEFT_SHIFT', 'PRESS', shift=True)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y, shift=True)


@step
def s_click_release():
    x, y, _d = C["g"]
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y, shift=True)
    ev('LEFT_SHIFT', 'RELEASE')


@step
def s_click_wait():
    pass


@step
def s_clicked():
    check(f"a Shift+click shows no label ({vm().current()})", vm().current() is None)
    hover(*C["g"][:2])


@step
def s_extrude_press():
    x, y, d = C["g"]
    press_drag(x, y, d, 70)


@step
def s_extrude_wait():
    pass   # the watch timer sees the transform (0.05 s ticks)


@step
def s_extrude_label():
    cur = vm().current()
    check(f"Shift+drag on a face shows 'Shift Extrude' ({cur})",
          cur == ("<hl>Shift Extrude</hl>", 'TOP_CENTER'))
    shot("gui_issue277_shift_extrude.png")
    release(*C["g"], 70)


@step
def s_extrude_done():
    pass


@step
def s_object_mode():
    tap('F8')


@step
def s_object_ready():
    check(f"F8 -> object mode ({bpy.context.mode})", bpy.context.mode == 'OBJECT')
    with v3d_override():
        bpy.ops.wm.tool_set_by_id(name="builtin.move")   # tools are per mode
    cube = bpy.data.objects["Cube"]
    C["n"] = len(bpy.data.objects)
    C["g"] = arrow(cube.matrix_world.translation, Vector((1, 0, 0)))
    hover(*C["g"][:2])
    clear_message()


@step
def s_dup_press():
    x, y, d = C["g"]
    press_drag(x, y, d, 60)


@step
def s_dup_wait():
    pass


@step
def s_dup_label():
    cur = vm().current()
    check(f"Shift+drag on an object shows 'Shift Duplicate' ({cur})",
          cur == ("<hl>Shift Duplicate</hl>", 'TOP_CENTER'))
    shot("gui_issue277_shift_duplicate.png")
    release(*C["g"], 60)


@step
def s_dup_done():
    check(f"the drag made a copy ({C['n']} -> {len(bpy.data.objects)})", len(bpy.data.objects) == C["n"] + 1)
    cube = bpy.data.objects["Cube"]
    for o in bpy.context.view_layer.objects:
        o.select_set(o is cube)
    bpy.context.view_layer.objects.active = cube
    C["g"] = arrow(cube.matrix_world.translation, Vector((1, 0, 0)))
    hover(*C["g"][:2])
    prefs().in_view_messages = False
    clear_message()


@step
def s_off_press():
    x, y, d = C["g"]
    press_drag(x, y, d, 60)


@step
def s_off_wait():
    pass


@step
def s_off_label():
    check(f"In-View Messages off: no label ({vm().current()})", vm().current() is None)
    release(*C["g"], 60)


@step
def s_off_done():
    prefs().in_view_messages = True


run()
