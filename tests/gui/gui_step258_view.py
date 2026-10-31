"""Issue #155: in the Maya layout: after a Move (a Blender transform, like a manipulator drag) no "Move"
redo panel shows (Maya has none; the Maya layout views keep the HUD region off); F frames pCube1 with Maya's margin; the
Status Line Symmetry box is a drop-down. Screenshots: gui_step258_after_move.png, gui_step258_framed.png."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def centre():
    _a, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)


def hud_shown():
    area, _r = view3d()
    return area.spaces.active.show_region_hud


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_cube():
    bpy.ops.allset.keymap_activate()
    with override():
        bpy.ops.allset.create(kind='CUBE')
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    C["hud0"] = hud_shown()
    with override():
        bpy.ops.transform.translate('EXEC_DEFAULT', True, value=(0.0, 0.0, 0.5))
    centre()


@step
def s_wait():
    pass


@step
def s_after_move():
    check(f"Maya layout view has no HUD region (Maya: no redo panel) ({C['hud0']})", not C["hud0"])
    area, _r = view3d()
    hud = [r for r in area.regions if r.type == 'HUD' and r.width > 1 and r.height > 1]
    check(f"no redo panel after a Move ({[(r.width, r.height) for r in hud]})", not hud or not hud_shown())
    shot("gui_step258_after_move.png")
    centre()
    ev('F', 'PRESS')
    ev('F', 'RELEASE')


@step
def s_wait3():
    pass


@step
def s_framed():
    shot("gui_step258_framed.png")
    area, region = view3d()
    rv3d = region.data
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    ob = bpy.context.view_layer.objects.active
    pts = [location_3d_to_region_2d(region, rv3d, ob.matrix_world @ v.co) for v in ob.data.vertices]
    ys = [p.y for p in pts if p is not None]
    top, bottom = max(ys), min(ys)
    margin = min(region.height - top, bottom) / region.height
    print("framed margin", margin, flush=True)
    check(f"F leaves Maya's margin around pCube1 ({margin:.3f} of the view height top / bottom)", margin > 0.05)


run()
