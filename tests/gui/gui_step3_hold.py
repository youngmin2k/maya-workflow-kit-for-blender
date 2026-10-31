"""With real (simulated) key events: hold keys, tap/hold, pick-walk."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, step, tap, setup, screenshot, view3d  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def ts():
    return bpy.context.scene.tool_settings


def selected():
    return sorted(o.name for o in bpy.context.selected_objects)


def select_only(name):
    for o in bpy.context.view_layer.objects:
        o.select_set(o.name == name)
    bpy.context.view_layer.objects.active = bpy.data.objects[name]


@step
def s_setup():
    C["x"], C["y"] = setup()
    ts().use_snap, ts().snap_elements = False, {'INCREMENT'}
    ts().use_transform_data_origin = False
    ts().use_proportional_edit_objects, ts().proportional_size = False, 2.0   # a user radius (1.0 = Blender default becomes Maya 5)
    check("keymap active = Maya", sys.modules["sim"].maya_keys())
    ev('X', 'PRESS')


@step
def s_x():
    check("X held -> grid snap", ts().use_snap and set(ts().snap_elements) == {'GRID'})
    ev('V', 'PRESS')


@step
def s_xv():
    check("X+V held -> GRID+VERTEX", set(ts().snap_elements) == {'GRID', 'VERTEX'})
    ev('X', 'RELEASE')


@step
def s_v():
    check("X up, V held -> VERTEX", ts().use_snap and set(ts().snap_elements) == {'VERTEX'})
    ev('V', 'RELEASE')


@step
def s_restored():
    check("all up -> snap restored", not ts().use_snap and set(ts().snap_elements) == {'INCREMENT'})
    ev('D', 'PRESS')


@step
def s_d():
    check("D held -> affect only origins", ts().use_transform_data_origin)
    ev('D', 'RELEASE')


@step
def s_d_up():
    check("D up -> restored", not ts().use_transform_data_origin)
    tap('INSERT')


@step
def s_insert():
    check("Insert -> pivot edit toggled on", ts().use_transform_data_origin)
    ts().use_transform_data_origin = False
    tap('B')


@step
def s_b_tap():
    check("B tap -> soft select on", ts().use_proportional_edit_objects)
    ev('B', 'PRESS')
    ev('LEFTMOUSE', 'PRESS', x=C["x"], y=C["y"])


@step
def s_b_drag():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"] + 100, y=C["y"])


@step
def s_b_drag_check():
    check("B + LMB drag 100 px -> radius x2 (2 -> 4)", abs(ts().proportional_size - 4.0) < 1e-3)
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step3_bdrag.png"))
    ev('LEFTMOUSE', 'RELEASE', x=C["x"] + 100, y=C["y"])
    ev('B', 'RELEASE')


@step
def s_b_after():
    check("B release after drag does not toggle", ts().use_proportional_edit_objects)
    area, _r = view3d()
    rv3d = area.spaces.active.region_3d
    C["dist"] = rv3d.view_distance * 5
    rv3d.view_distance = C["dist"]
    tap('A')


@step
def s_a_wait():
    pass  # smooth-view animation


@step
def s_a_tap():
    rv3d = view3d()[0].spaces.active.region_3d
    check("A tap -> frame all", abs(rv3d.view_distance - C["dist"]) > 1e-3)
    select_only("Cube")
    ev('A', 'PRESS')
    ev('LEFTMOUSE', 'PRESS', x=C["x"], y=C["y"])
    ev('LEFTMOUSE', 'RELEASE', x=C["x"], y=C["y"])


@step
def s_a_menu():
    check("A hold + click -> menu, selection untouched", selected() == ["Cube"])
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step3_amenu.png"))
    tap('ESC')
    ev('A', 'RELEASE')


@step
def s_walk_down():
    select_only("Cube")
    kid = bpy.data.objects.new("kid", None)
    bpy.context.scene.collection.objects.link(kid)
    kid.parent = bpy.data.objects["Cube"]
    bpy.context.view_layer.update()
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    tap('DOWN_ARROW')


@step
def s_walk_up():
    check("Down arrow -> child", selected() == ["kid"])
    tap('UP_ARROW')


@step
def s_drag_start():
    check("Up arrow -> parent", selected() == ["Cube"])
    area, _r = view3d()
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0], area=area):
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    ev('X', 'PRESS')
    ev('LEFTMOUSE', 'PRESS', x=C["x"], y=C["y"])


@step
def s_drag1():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"] + 40, y=C["y"] + 10)


@step
def s_drag2():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"] + 80, y=C["y"] + 20)
    check("X held while dragging -> snap on", ts().use_snap)
    ev('X', 'RELEASE')  # eaten by the transform modal


@step
def s_drag_end():
    ev('LEFTMOUSE', 'RELEASE', x=C["x"] + 80, y=C["y"] + 20)


@step
def s_after_drag():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])


@step
def s_missed_release():
    check("X released during drag -> restored after drag (keystate fallback)", not ts().use_snap)


run()
