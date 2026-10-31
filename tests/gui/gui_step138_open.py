"""Lane CARRY (#63, #64) in a real UI: File > Open of a file saved in Blender's own layout shows the Maya
layout (Status Line strip, shelf row, Tool Box column, Maya dock) with Maya mode on and "Keep Maya Layout When Opening
Files" on; with the option off the file's own layout stays. A file that holds a Maya workspace in the background gets
that one back (no second copy). Tool settings set in the Maya scene survive the Open."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, step, setup, screenshot, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP = os.path.join(ROOT, "tmp", "gui_step138_open")
FACTORY = os.path.join(TMP, "factory_layout.blend")
WITH_MAYA = os.path.join(TMP, "maya_ws_in_background.blend")


def _m(name):
    return import_module(MODULE + "." + name)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def layout_parts():
    screen = win().screen
    shelf, toolbox, maya_dock = _m("ui.shelf"), _m("ui.toolbox"), _m("ui.maya_dock")
    return {"strip": shelf.strip_area(screen) is not None,
            "shelf": shelf.shelf_row_area(screen) is not None,
            "toolbox": any(a.type == 'VIEW_3D' and toolbox.is_toolbox(a.spaces.active) for a in screen.areas),
            "dock": maya_dock.find_stack(screen) is not None}


def maya_workspaces():
    switch = _m("switch")
    return [ws.name for ws in bpy.data.workspaces if switch.is_maya_workspace(ws)]


@step
def s_setup():
    setup()
    os.makedirs(TMP, exist_ok=True)
    # a file saved in Blender's own layout (factory startup: Layout workspace, no Maya areas)
    bpy.ops.wm.save_as_mainfile(filepath=FACTORY, copy=True)
    load_maya_layout()


@step
def s_settings():
    sc = bpy.context.scene
    check("New Scene is the Maya layout", _m("switch").is_maya_workspace(win().workspace))
    sc.transform_orientation_slots[1].type = 'NORMAL'              # Move axis: Component (Normal)
    _m("operators.snap_align").set_step_snap(sc.tool_settings, 'TRANSLATE', 'RELATIVE')
    sc.allset_symmetry.on = True
    bpy.ops.wm.open_mainfile(filepath=FACTORY)


@step
def s_wait_open():
    redraw()


@step
def s_opened():
    sc = bpy.context.scene
    parts = layout_parts()
    check(f"opened file shows the Maya layout ({win().workspace.name}, {parts})",
          _m("switch").is_maya_workspace(win().workspace) and all(parts.values()))
    check(f"the file's own workspaces stay ({len(bpy.data.workspaces)})", "Layout" in bpy.data.workspaces)
    check(f"Move axis carried ({sc.transform_orientation_slots[1].type})",
          sc.transform_orientation_slots[1].type == 'NORMAL')
    check("step snap carried", _m("operators.snap_align").step_snap_mode(sc.tool_settings, 'TRANSLATE') == 'RELATIVE')
    check("symmetry carried", sc.allset_symmetry.on)
    print("step138: is_dirty after Open + Maya layout =", bpy.data.is_dirty)
    redraw()


@step
def s_shot_open():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step138_open_maya.png"))
    # the file now holds the appended Maya workspace; saved while Blender's Layout workspace is shown
    win().workspace = bpy.data.workspaces["Layout"]


@step
def s_save_background():
    check("Layout workspace shown before saving", win().workspace.name == "Layout")
    bpy.ops.wm.save_as_mainfile(filepath=WITH_MAYA, copy=True)
    bpy.ops.wm.open_mainfile(filepath=WITH_MAYA)


@step
def s_wait_bg():
    redraw()


@step
def s_reopened_bg():
    names = maya_workspaces()
    check(f"the file's Maya workspace is shown again, not a second copy ({win().workspace.name}, {names})",
          _m("switch").is_maya_workspace(win().workspace) and len(names) == 1)
    _m("preferences").get().maya_layout_on_open = False
    bpy.ops.wm.open_mainfile(filepath=FACTORY)


@step
def s_wait_off():
    redraw()


@step
def s_option_off():
    parts = layout_parts()
    check(f"option off: the file's own layout ({win().workspace.name}, {parts})",
          win().workspace.name == "Layout" and not any(parts.values()))
    check("option off: tool settings still carried",
          bpy.context.scene.transform_orientation_slots[1].type == 'NORMAL')
    redraw()


@step
def s_shot_off():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step138_open_option_off.png"))
    _m("preferences").get().maya_layout_on_open = True
    # Blender mode: no layout entry
    _m("switch").set_mode(False, layout=False)
    bpy.ops.wm.open_mainfile(filepath=FACTORY)


@step
def s_wait_blender():
    redraw()


@step
def s_blender_mode():
    check(f"Blender mode: the file's own layout ({win().workspace.name})", win().workspace.name == "Layout")
    _m("switch").set_mode(True, layout=False)


run()
