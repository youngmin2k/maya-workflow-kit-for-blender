"""In a real UI: in the Maya Workflow Kit layout (m + cm display) the shelf cube and
``cmds.polyCube()`` are the same 1 cm cube, seen by Maya's persp view; Channel Box
and Attribute Editor show Maya's numbers (cm); screenshots."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {"tries": 0}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def main_view():
    return max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)


def ui_region():
    return next(r for r in main_view().regions if r.type == 'UI')


def goto_tab(category, then):
    """Ctrl+wheel over the sidebar tab strip until ``category`` shows (gui_step11)."""
    def s_tab():
        r = ui_region()
        if r.active_panel_category != category and C["tries"] < 12:
            C["tries"] += 1
            ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width - 8, y=r.y + r.height - 60)
            ev('WHEELDOWNMOUSE', 'PRESS', ctrl=True)
            sys.modules["sim"]._steps.insert(0, s_tab)
            return
        C["tries"] = 0
        check(f"sidebar shows the {category} tab", r.active_panel_category == category)
        then()
    return s_tab


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_loaded():
    bpy.ops.allset.keymap_activate()
    units = import_module(MODULE + ".operators.units")
    check(f"Maya Workflow Kit layout: 1 Maya unit = 0.01 BU (m + cm) ({units.maya_unit():.4f})",
          abs(units.maya_unit() - 0.01) < 1e-6)
    area = main_view()
    shelf_map = import_module(MODULE + ".ui.shelf_map")
    modal = import_module(MODULE + ".marking.modal")
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=win(), area=area, region=region):
        modal.run_action(bpy.context, shelf_map.BY_COMMAND["CreatePolygonCube"][0])
    cmds = import_module(MODULE + ".command_line.cmds_shim")
    C["cmds_cube"] = cmds.polyCube()[0]
    cmds.move(2, 0, 0, C["cmds_cube"])
    cmds.select("pCube1")
    bpy.context.window_manager.allset_dock = 'CHANNEL_BOX'   # the layout's tab stack
    redraw()


@step
def s_sizes():
    a, b = bpy.data.objects["pCube1"], bpy.data.objects[C["cmds_cube"]]
    check(f"shelf pCube1 and cmds {b.name} are the same size ({tuple(a.dimensions)}, {tuple(b.dimensions)})",
          all(abs(x - y) < 1e-6 for x, y in zip(a.dimensions, b.dimensions)))
    check(f"pCube1 is 1 cm ({a.dimensions.x:.4f} BU)", abs(a.dimensions.x - 0.01) < 1e-6)
    rv3d = main_view().spaces.active.region_3d
    check(f"Maya persp view distance 44.8 cm ({rv3d.view_distance:.4f} BU)",
          abs(rv3d.view_distance - 0.4482) < 1e-3)
    md = import_module(MODULE + ".ui.maya_dock")
    check("the tab stack shows the Channel Box", md.find_stack(win().screen) is not None and md.current_tab() == 'CHANNEL_BOX')
    s_cb_ready()


def s_cb_ready():
    bpy.context.view_layer.objects.active = bpy.data.objects[C["cmds_cube"]]
    for o in bpy.context.view_layer.objects:
        o.select_set(o.name == C["cmds_cube"])
    redraw()


@step
def s_cb_shot():
    shot("gui_step21_channel_box.png")
    bpy.context.window_manager.allset_dock = 'ATTRIBUTE_EDITOR'
    bpy.context.window_manager.allset_ae_tab = "T"    # transform node: Translate in cm
    redraw()


@step
def s_ae_redraw():
    redraw()


@step
def s_ae_shot():
    shot("gui_step21_attribute_editor.png")
    bpy.context.window_manager.allset_dock = 'CHANNEL_BOX'


@step
def s_back():
    bpy.ops.wm.read_homefile(app_template="")


run()
