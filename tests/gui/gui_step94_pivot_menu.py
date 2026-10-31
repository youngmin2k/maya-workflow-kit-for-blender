"""In a real UI (Maya Workflow Kit layout): with a custom pivot on pCube1, hold D, hold RMB = the pivot menu (Maya
RMB_EMPTY edit-mode branch), drag south + release = Reset Pivot (delta_location back to 0), release D =
pivot edit off."""

import os
import sys
from importlib import import_module

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
DRAG = 120


def cube():
    return bpy.data.objects["pCube1"]


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    import_module(MODULE + ".operators.freeze").shift_pivot(cube(), Vector((1.0, 0.0, 0.0)))   # custom pivot
    for o in bpy.context.scene.objects:
        o.select_set(o.name == "pCube1")
    bpy.context.view_layer.objects.active = cube()
    bpy.context.view_layer.update()
    C["delta0"] = Vector(cube().delta_location).length
    C["x"], C["y"] = region.x + region.width // 2, region.y + region.height // 2
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('D', 'PRESS', x=C["x"], y=C["y"])


@step
def s_rmb():
    ts = bpy.context.scene.tool_settings
    check(f"D held = pivot edit ({ts.use_transform_data_origin}), custom pivot offset {C['delta0']:.4f}",
          ts.use_transform_data_origin and C["delta0"] > 1e-4)
    ev('RIGHTMOUSE', 'PRESS', x=C["x"], y=C["y"])


@step
def s_menu_wait():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_menu_shot():
    d = import_module(MODULE + ".marking.draw")
    s = d.ACTIVE.get("session")
    labels = sorted(it.label for it in s.layout.items) if s else []
    check(f"RMB shows the pivot menu ({labels})", "Reset Pivot" in labels and "Pin Component Pivot" in labels)
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step94_pivot_menu.png"))
    # release on the S box: the list starts 87 px x scale under the press point, so a longer
    # drag south ends on the list's first row
    r = s.layout.radial["S"].rect if s and "S" in s.layout.radial else (0, -DRAG, 0, -DRAG)
    C["dy"] = int(round((r[1] + r[3]) / 2))
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"] + C["dy"] // 2)
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"] + C["dy"])


@step
def s_release_rmb():
    ev('RIGHTMOUSE', 'RELEASE', x=C["x"], y=C["y"] + C["dy"])


@step
def s_release_d():
    bpy.context.view_layer.update()
    C["delta1"] = Vector(cube().delta_location).length
    ev('D', 'RELEASE', x=C["x"], y=C["y"] + C["dy"])


@step
def s_check():
    check(f"drag south = Reset Pivot: delta_location {C['delta0']:.4f} -> {C['delta1']:.6f}", C["delta1"] < 1e-6)
    ts = bpy.context.scene.tool_settings
    check(f"releasing D ends pivot edit ({ts.use_transform_data_origin})", not ts.use_transform_data_origin)


run()
