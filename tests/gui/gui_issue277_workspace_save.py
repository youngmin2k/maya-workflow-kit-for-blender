"""#277: in a real UI: Windows > Workspaces > Save Current Workspace As saves a changed Maya layout (editor types and
area sizes), a new scene lists it after Maya's workspaces and brings it back unchanged (the column fit leaves its
sizes alone), Reset puts it back after a change, Delete removes it and shows Maya Classic."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
os.environ["ALLSET_FIT_WARP"] = "1"
GUI_TIMEOUT = 240
NAME = "My GUI Layout"
C = {}


def uw():
    return import_module(MODULE + ".ui.user_workspaces")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def layout():
    """(editor, width, height) of every area, left to right / top to bottom."""
    return sorted((a.ui_type, a.width, a.height) for a in win().screen.areas)


def same_sizes(a, b, tol=3):
    return len(a) == len(b) and all(x[0] == y[0] and abs(x[1] - y[1]) <= tol and abs(x[2] - y[2]) <= tol
                                    for x, y in zip(a, b))


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, f"gui_issue277_ws_{name}.png"))


def wait():
    redraw()


@step
def s_setup():
    setup()
    for f in uw().saved_names():
        os.remove(uw().path_of(f))
    load_maya_layout()


@step
def s_keymap():
    bpy.ops.allset.keymap_activate()
    ev('MOUSEMOVE', 'NOTHING', x=800, y=450)
    redraw()


for _ in range(10):         # past the column fit of a newly loaded layout
    step(wait)


@step
def s_change():
    C["factory"] = layout()
    for area in win().screen.areas:
        if area.type == 'OUTLINER':
            area.type = 'INFO'
    redraw()


@step
def s_save():
    C["mine"] = layout()
    check(f"the user changed the layout ({C['mine']})", C["mine"] != C["factory"])
    with bpy.context.temp_override(window=win()):
        C["res"] = bpy.ops.allset.save_workspace_as(name=NAME)
    redraw()


@step
def s_saved():
    ws = win().workspace
    check(f"Save Current Workspace As: saved ({C['res']}, {uw().saved_names()}, shown {ws.name})",
          C["res"] == {'FINISHED'} and uw().saved_names() == [NAME] and ws.name == NAME
          and uw().user_name(ws) == NAME)
    with bpy.context.temp_override(window=win()):
        bpy.ops.wm.call_menu(name="ALLSET_MT_maya_workspaces")


@step
def s_menu_shot():
    shot("menu")
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


@step
def s_new_scene():
    load_maya_layout()


@step
def s_new_scene_shown():
    check(f"a new scene starts in Maya Classic ({win().workspace.name})", uw().user_name(win().workspace) is None)
    ws_mod = import_module(MODULE + ".ui.workspaces")
    rows = [r[2] for r in ws_mod.entries()]
    check(f"the saved workspace is listed after Maya's ({rows})",
          NAME in rows and rows.index(NAME) == len(ws_mod.IN_TEMPLATE))
    C["objects"] = len(bpy.data.objects)
    with bpy.context.temp_override(window=win()):
        C["res"] = bpy.ops.allset.user_workspace(name=NAME)
    redraw()


for _ in range(10):
    step(wait)


@step
def s_loaded():
    got = layout()
    check(f"the saved workspace comes back with its editors and sizes ({C['res']}, {got} vs {C['mine']})",
          C["res"] == {'FINISHED'} and win().workspace.name == NAME and same_sizes(got, C["mine"]))
    check(f"loading it adds no objects ({len(bpy.data.objects)} vs {C['objects']})",
          len(bpy.data.objects) == C["objects"])
    shot("loaded")
    for area in win().screen.areas:
        if area.type == 'INFO':
            area.type = 'OUTLINER'
    redraw()


@step
def s_reset():
    check(f"changed again ({layout()})", not same_sizes(layout(), C["mine"]))
    with bpy.context.temp_override(window=win()):
        C["res"] = bpy.ops.allset.reset_workspace()
    redraw()


for _ in range(3):
    step(wait)


@step
def s_reset_done():
    names = [w.name for w in bpy.data.workspaces]
    check(f"Reset Current Workspace brings back the saved state ({C['res']}, {layout()})",
          C["res"] == {'FINISHED'} and win().workspace.name == NAME and same_sizes(layout(), C["mine"]))
    check(f"one copy left ({names})", names.count(NAME) == 1 and not any(n.endswith("(old)") for n in names))
    with bpy.context.temp_override(window=win()):
        C["res"] = bpy.ops.allset.delete_workspace('EXEC_DEFAULT')
    redraw()


for _ in range(3):
    step(wait)


@step
def s_deleted():
    names = [w.name for w in bpy.data.workspaces]
    sw = import_module(MODULE + ".switch")
    check(f"Delete Current Workspace: file gone, Maya Classic shown ({C['res']}, {uw().saved_names()}, "
          f"{win().workspace.name}, {names})",
          C["res"] == {'FINISHED'} and uw().saved_names() == [] and sw.template_of(win().workspace) == "General"
          and NAME not in names and not any(n.endswith("(old)") for n in names))


run()
