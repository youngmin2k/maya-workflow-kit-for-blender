"""#98: resting the mouse on the Maya Move manipulator's X arrow shows no tooltip (Maya manipulators have
none; Blender showed "Move selected items"). The window right after the hover and ~1.6 s later must look the same
next to the cursor (a tooltip is a box of text there). Shots with ``--shots``."""

import os
import sys
from importlib import import_module

import bpy
import numpy as np
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_location_3d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, scale, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def shot(name):
    path = os.path.join(SHOTS or bpy.app.tempdir, f"gui_step151_{name}.png")
    screenshot(path)
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[..., :3]


def x_arrow_point(frac=0.7):
    """Window point ``frac`` along the Move manipulator's X arrow."""
    area, region = view3d()
    c = bpy.data.objects["pCube1"].matrix_world.translation
    p = location_3d_to_region_2d(region, region.data, c)
    one = (region_2d_to_location_3d(region, region.data, p + Vector((1, 0)), c) - c).length
    length = mod("ui.manipulator").ARROW_PX * bpy.context.preferences.view.gizmo_size / 75.0 * scale()
    q = location_3d_to_region_2d(region, region.data, c + Vector((1, 0, 0)) * length * frac * one)
    return int(region.x + q.x), int(region.y + q.y)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_cube():
    bpy.ops.allset.keymap_activate()
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    redraw()


step(redraw)


@step
def s_hover():
    x, y = x_arrow_point()
    C["at"] = (x, y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y)


step(redraw)


@step
def s_first():
    C["first"] = shot("move_hover_start")


for _i in range(4):          # ~1.6 s without moving: Blender's tooltip delay is ~0.5 s
    step(redraw)


@step
def s_late():
    late = shot("move_hover_late")
    x, y = C["at"]
    s = scale()
    h, w = late.shape[:2]
    # a tooltip opens under / beside the cursor: compare a box there between the two shots
    x0, x1 = max(0, x - int(40 * s)), min(w, x + int(320 * s))
    y0, y1 = max(0, y - int(110 * s)), min(h, y + int(10 * s))
    diff = np.abs(late[y0:y1, x0:x1] - C["first"][y0:y1, x0:x1]).max(axis=2) > 0.08
    changed = float(diff.mean())
    hi = late[max(0, y - 6):y + 7, max(0, x - 6):x + 7]
    yellow = bool(((hi[..., 0] > 0.8) & (hi[..., 1] > 0.8) & (hi[..., 2] < 0.4)).any())
    print("GUI151 tooltip", (x, y), "changed", round(changed, 4), "highlight", yellow, flush=True)
    check(f"the X arrow is under the mouse (highlight yellow: {yellow})", yellow)
    check(f"#98 no tooltip next to the Move manipulator after 1.6 s ({changed:.1%} of the box changed)",
          changed < 0.01)


run()
