"""In a real UI: Move tool, Ctrl+LMB drag on the X arrow moves along X with grid snapping and makes X the
active handle,
Ctrl+click on the centre frees it, Shift+MMB drag in the front view picks X (sideways) / Z (up), Scale tool Ctrl+X
arrow scales Y and Z."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_location_3d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win, scale, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
STEPS = 8


def mod(name):
    return import_module(f"{MODULE}.{name}")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def ob1():
    return bpy.data.objects["pCube1"]


def screen(world):
    _area, region = view3d()
    p = location_3d_to_region_2d(region, region.data, world)
    return Vector((region.x + p.x, region.y + p.y))


def px_world(at):
    _area, region = view3d()
    p = location_3d_to_region_2d(region, region.data, at)
    w = region_2d_to_location_3d(region, region.data, p + Vector((1, 0)), at)
    return (w - at).length


def handle_point(axis, frac):
    c = ob1().matrix_world.translation
    n = mod("ui.manipulator").ARROW_PX * bpy.context.preferences.view.gizmo_size / 75.0 * scale()
    return screen(c + Vector(axis) * n * frac * px_world(c))


def hover(p):
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x), y=int(p.y))
    ev('MOUSEMOVE', 'NOTHING', x=int(p.x) + 1, y=int(p.y))


def set_tool(name):
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name=name)
    redraw()


def drag(button, mods, start, end):
    """Steps: hover, modifier + press, moves (own step), release + modifier up."""
    keys = {"ctrl": "LEFT_CTRL", "shift": "LEFT_SHIFT"}

    def s1():
        hover(start())

    def s2():
        for m in mods:
            ev(keys[m], 'PRESS', **{m: True})       # a real modifier key: mouse-only modifiers reach no window state
        C["a"], C["b"] = start(), end()
        ev(button, 'PRESS', x=int(C["a"].x), y=int(C["a"].y), **{m: True for m in mods})

    def s3():
        # first stretch alone: a transform the press (or its first movement) starts sees later ticks only
        a, b = C["a"], C["b"]
        q = a + (b - a) * (2 / STEPS)
        ev('MOUSEMOVE', 'NOTHING', x=int(q.x), y=int(q.y), **{m: True for m in mods})

    def s3b():
        a, b = C["a"], C["b"]
        for i in range(3, STEPS + 1):
            q = a + (b - a) * (i / STEPS)
            ev('MOUSEMOVE', 'NOTHING', x=int(q.x), y=int(q.y), **{m: True for m in mods})

    def s4():
        ev(button, 'RELEASE', x=int(C["b"].x), y=int(C["b"].y), **{m: True for m in mods})
        for m in mods:
            ev(keys[m], 'RELEASE')

    def s5():
        running = [op.bl_idname for op in win().modal_operators]
        C.setdefault("modal_after", []).append(running)
        print("STEP85 modal after release", running)
    for s in (s1, s2, s3, s3b, s4, s5):
        step(s)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_cube():
    bpy.ops.allset.keymap_activate()
    view3d()[1].data.view_distance *= 2.0          # the sizes the manipulator test uses
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    set_tool("builtin.move")
    C["start"] = ob1().location.copy()


# Ctrl+LMB drag on the X arrow: up and to the left on screen
drag('LEFTMOUSE', ("ctrl",), lambda: handle_point((1, 0, 0), 0.6),
     lambda: handle_point((1, 0, 0), 0.6) + Vector((-60, 70)))


@step
def s_ctrl_check():
    d = ob1().location - C["start"]
    k = mod("operators.units").maya_unit()
    h = mod("operators.manip").HANDLES.get('TRANSLATE')
    cm = d.x / k
    check(f"Ctrl+X arrow drag: X only, whole cm ({d.x / k:.3f}, {d.y / k:.3f}, {d.z / k:.3f} cm)",
          abs(cm) > 0.5 and abs(cm - round(cm)) < 1e-3 and abs(d.y) < 1e-6 and abs(d.z) < 1e-6)
    check(f"X is the active handle ({h})", h is not None and tuple(h["constraint_axis"]) == (True, False, False))
    C["d"] = d
    redraw()


@step
def s_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step85_active_x.png"))
    hover(screen(ob1().matrix_world.translation))


@step
def s_center_ctrl():
    ev('LEFT_CTRL', 'PRESS', ctrl=True)
    p = screen(ob1().matrix_world.translation)
    ev('LEFTMOUSE', 'PRESS', x=int(p.x), y=int(p.y), ctrl=True)


@step
def s_center_ctrl_up():
    p = screen(ob1().matrix_world.translation)
    ev('LEFTMOUSE', 'RELEASE', x=int(p.x), y=int(p.y), ctrl=True)
    ev('LEFT_CTRL', 'RELEASE')


@step
def s_center_check():
    h = mod("operators.manip").HANDLES.get('TRANSLATE')
    check(f"Ctrl+click on the centre frees the active handle ({h})", h is None)
    check("and doesn't move the cube", (ob1().location - C["start"] - C["d"]).length < 1e-6)
    check("and keeps the selection", ob1().select_get())
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.view3d.view_axis(type='FRONT')
    redraw()


def mid():
    _a, r = view3d()
    return Vector((r.x + r.width * 0.3, r.y + r.height * 0.3))


@step
def s_before_side():
    C["l1"] = ob1().location.copy()


drag('MIDDLEMOUSE', ("shift",), mid, lambda: mid() + Vector((80, 12)))


@step
def s_side_check():
    d = ob1().location - C["l1"]
    check(f"Shift+MMB sideways in the front view = X only ({d.x:.4f}, {d.y:.4f}, {d.z:.4f})",
          abs(d.x) > 1e-4 and abs(d.y) < 1e-6 and abs(d.z) < 1e-6)
    C["l2"] = ob1().location.copy()


drag('MIDDLEMOUSE', ("shift",), mid, lambda: mid() + Vector((10, 80)))


@step
def s_up_check():
    d = ob1().location - C["l2"]
    check(f"Shift+MMB up = Z only ({d.x:.4f}, {d.y:.4f}, {d.z:.4f})",
          abs(d.z) > 1e-4 and abs(d.x) < 1e-6 and abs(d.y) < 1e-6)
    set_tool("builtin.scale")
    C["s0"] = ob1().scale.copy()


drag('LEFTMOUSE', ("ctrl",), lambda: handle_point((1, 0, 0), 0.8),
     lambda: handle_point((1, 0, 0), 0.8) + Vector((60, 60)))


@step
def s_scale_check():
    s = ob1().scale
    check(f"Scale tool Ctrl+X: X kept, Y and Z scaled ({s.x:.3f}, {s.y:.3f}, {s.z:.3f})",
          abs(s.x - C["s0"].x) < 1e-6 and abs(s.y - C["s0"].y) > 1e-3 and abs(s.y - s.z) < 1e-6)


run()
