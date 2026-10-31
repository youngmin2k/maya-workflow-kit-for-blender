"""In a real UI: Shift+drag on the Move gizmo's X arrow duplicates the cube and
moves the copy (Maya Smart Duplicate); a plain drag moves the original; Rotate gizmo too."""

import os
import sys

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, step, setup, screenshot, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
STEPS = 8


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def screen_pos(world):
    area, region = view3d()
    p = location_3d_to_region_2d(region, region.data, world)
    return int(region.x + p.x), int(region.y + p.y)


def arrow_point(ob, axis=Vector((1, 0, 0)), frac=0.75):
    """Window position on the gizmo arrow: ``frac`` of the gizmo size along the axis."""
    area, region = view3d()
    o = location_3d_to_region_2d(region, region.data, ob.matrix_world.translation)
    a = location_3d_to_region_2d(region, region.data, ob.matrix_world.translation + axis * 0.1)
    d = (a - o).normalized()
    size = bpy.context.preferences.view.gizmo_size * bpy.context.preferences.system.ui_scale
    p = o + d * size * frac
    return int(region.x + p.x), int(region.y + p.y), d


def drag(x, y, d, dist, shift):
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y)
    C["drag"] = (x, y, d, dist, shift)


def drag_press():
    x, y, d, dist, shift = C["drag"]
    if shift:
        # a real Shift drag: only a keyboard event's modifiers reach the window event state
        ev('LEFT_SHIFT', 'PRESS', shift=True)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y, shift=shift)
    for i in range(1, STEPS + 1):
        f = dist * i / STEPS
        ev('MOUSEMOVE', 'NOTHING', x=int(x + d.x * f), y=int(y + d.y * f), shift=shift)


def drag_release():
    x, y, d, dist, shift = C["drag"]
    ev('LEFTMOUSE', 'RELEASE', x=int(x + d.x * dist), y=int(y + d.y * dist), shift=shift)
    if shift:
        ev('LEFT_SHIFT', 'RELEASE')


def select_only(ob):
    for o in bpy.context.view_layer.objects:
        o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob


@step
def s_setup():
    C["x"], C["y"] = setup()
    cube = bpy.data.objects["Cube"]
    cube.name = "pCube1"
    cube.data.name = "pCubeShape1"
    select_only(cube)
    for name in ("Camera", "Light"):
        bpy.data.objects[name].hide_set(True)
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    redraw()


@step
def s_hover_plain():
    cube = bpy.data.objects["pCube1"]
    C["start"] = cube.location.copy()
    x, y, d = arrow_point(cube)
    drag(x, y, d, 80, shift=False)


@step
def s_press_plain():
    drag_press()


@step
def s_release_plain():
    drag_release()


@step
def s_plain_done():
    cube = bpy.data.objects["pCube1"]
    moved = cube.location - C["start"]
    check(f"plain drag on the X arrow moves the cube along X ({tuple(round(v, 3) for v in moved)})",
          len(bpy.data.objects) == 3 and moved.x > 0.1 and abs(moved.y) < 1e-4 and abs(moved.z) < 1e-4)
    C["plain_dx"] = moved.x
    C["start"] = cube.location.copy()
    redraw()


@step
def s_hover_shift():
    cube = bpy.data.objects["pCube1"]
    x, y, d = arrow_point(cube)
    drag(x, y, d, 80, shift=True)


@step
def s_press_shift():
    drag_press()


@step
def s_shot_shift():
    shot("gui_step22_shift_drag.png")
    drag_release()


@step
def s_shift_done():
    cube = bpy.data.objects["pCube1"]
    copy = bpy.data.objects.get("pCube2")
    check(f"Shift+drag duplicates: objects {[o.name for o in bpy.data.objects]}",
          copy is not None and len(bpy.data.objects) == 4)
    check(f"original stays ({tuple(round(v, 3) for v in cube.location)})",
          (cube.location - C["start"]).length < 1e-4)
    if copy is not None:
        moved = copy.location - C["start"]
        check(f"copy moved along X like a plain drag ({moved.x:.3f} vs {C['plain_dx']:.3f}, no precision)",
              moved.x > 0.5 * C["plain_dx"] and abs(moved.y) < 1e-4 and abs(moved.z) < 1e-4)
        check("copy has the Maya name and shape name", copy.data.name == "pCubeShape2")
        check("copy is selected and active, original not",
              copy.select_get() and not cube.select_get()
              and bpy.context.view_layer.objects.active is copy)
        C["copy"] = copy.name
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name="builtin.rotate")
    redraw()


@step
def s_hover_rotate():
    ob = bpy.data.objects[C.get("copy", "pCube1")]
    C["rot_before"] = ob.rotation_euler.copy()
    C["n"] = len(bpy.data.objects)
    # rotate gizmo: the Z dial (ring in the XY plane) at gizmo radius along +X
    x, y, d = arrow_point(ob, frac=0.9)
    side = Vector((-d.y, d.x))
    drag(x, y, side, 60, shift=True)


@step
def s_press_rotate():
    drag_press()


@step
def s_release_rotate():
    drag_release()


@step
def s_rotate_done():
    src = bpy.data.objects[C.get("copy", "pCube1")]
    new = [o for o in bpy.data.objects if o.name not in ("pCube1", "pCube2", "Camera", "Light")]
    check(f"Shift+drag on the rotate gizmo duplicates ({C['n']} -> {len(bpy.data.objects)})",
          len(bpy.data.objects) == C["n"] + 1)
    check("source of the rotate copy keeps its rotation",
          (Vector(src.rotation_euler) - Vector(C["rot_before"])).length < 1e-4)
    if new:
        check(f"rotate copy {new[0].name} is rotated ({tuple(round(v, 3) for v in new[0].rotation_euler)})",
              Vector(new[0].rotation_euler).length > 1e-3)
    C["n"] = len(bpy.data.objects)
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.ed.undo()


@step
def s_undone():
    check(f"one undo removes the copy and its rotation ({C['n']} -> {len(bpy.data.objects)})",
          len(bpy.data.objects) == C["n"] - 1 and "pCube3" not in bpy.data.objects)


run()
