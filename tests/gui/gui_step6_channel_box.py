"""In a real UI: Channel Box MMB virtual slider (and pass-through), screenshot."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, dock_area, ev, run, step, setup, screenshot, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def cube():
    return bpy.data.objects["Cube"]


def ui_region():
    area = view3d()[0]
    return next(r for r in area.regions if r.type == 'UI')


def mmb_drag(dx, cancel=False):
    x, y = C["x"], C["y"]
    ev('MIDDLEMOUSE', 'PRESS', x=x, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x + dx // 2, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x + dx, y=y)
    if cancel:
        ev('ESC', 'PRESS')
        ev('ESC', 'RELEASE')
    ev('MIDDLEMOUSE', 'RELEASE', x=x + dx, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_setup():
    C["x"], C["y"] = setup()
    C["cb"] = import_module(MODULE + ".ui.channel_box")
    area, _r = view3d()
    dock_area('CHANNEL_BOX')    # Maya's tab stack right of the viewport (was the 3D View sidebar)
    for o in bpy.context.view_layer.objects:
        o.select_set(o.name == "Cube")
    bpy.context.view_layer.objects.active = cube()
    with bpy.context.temp_override(window=win(), area=area):
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    C["cb"].set_selected_channels(["tx"])
    C["x0"] = cube().location.x
    mmb_drag(100)


@step
def s_slider():
    dx = cube().location.x - C["x0"]
    check(f"MMB drag 100 px with Translate X selected -> +1.0 (got {dx:.3f})", abs(dx - 1.0) < 0.05)
    check("other channels untouched", abs(cube().location.y) < 1e-6 and abs(cube().location.z) < 1e-6)
    C["x1"] = cube().location.x
    mmb_drag(150, cancel=True)


@step
def s_cancel():
    check("Esc during the slider restores the value", abs(cube().location.x - C["x1"]) < 1e-6)
    C["cb"].set_selected_channels([])
    C["loc"] = tuple(cube().location)
    mmb_drag(120)


@step
def s_pass_through():
    moved = any(abs(a - b) > 1e-4 for a, b in zip(cube().location, C["loc"]))
    check("no channel selected -> MMB drag is the Move tool's drag", moved)
    C["tries"] = 0


@step
def s_tab():
    md = import_module(MODULE + ".ui.maya_dock")
    check("the dock shows the Channel Box tab", md.role(dock_area()) == 'STACK' and md.current_tab() == 'CHANNEL_BOX')
    ob = cube()
    ob.keyframe_insert("location", index=0)
    ob.lock_location[1] = True
    ob["speed"] = 2.5
    ob.modifiers.new("Smooth", 'SUBSURF')
    C["cb"].set_selected_channels(["tx", "rz"])
    bpy.ops.allset.layer_new(selected=True)


@step
def s_shot():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_shot2():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step6_channel_box.png"))


run()
