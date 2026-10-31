"""#81: in a real UI: every Maya workspace of the template through Windows > Workspaces (one shot each,
read by eye), then Reset Current Workspace puts a changed layout back."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
os.environ["ALLSET_FIT_WARP"] = "1"
GUI_TIMEOUT = 240
C = {}


def wsm():
    return import_module(MODULE + ".ui.workspaces")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def types():
    return sorted(a.ui_type for a in win().screen.areas)


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, f"gui_step160_{name}.png"))


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_keymap():
    bpy.ops.allset.keymap_activate()
    ev('MOUSEMOVE', 'NOTHING', x=800, y=450)
    redraw()


def _visit(name):
    def go():
        with bpy.context.temp_override(window=win()):
            bpy.ops.allset.maya_workspace(name=name)
        redraw()

    def wait():
        redraw()

    def look():
        ws = win().workspace
        prefs = import_module(MODULE + ".preferences").get()
        check(f"Windows > Workspaces > {wsm().LABELS[name]}: shown ({ws.name}, areas {types()}, menu set "
              f"{prefs.menu_set})", import_module(MODULE + ".switch").template_of(ws) == name)
        shot(name.replace(" ", "_"))
    return go, wait, wait, look


for _name in ("General", "Modeling - Standard", "Modeling - Expert", "Sculpting", "UV Editing", "Rigging", "Animation",
              "Rendering - Standard"):
    for _fn in _visit(_name):
        step(_fn)


@step
def s_change():
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.maya_workspace(name="Animation")
    C["factory"] = None


@step
def s_change2():
    C["factory"] = types()
    for area in win().screen.areas:
        if area.type == 'OUTLINER':
            area.type = 'INFO'
    redraw()


@step
def s_changed():
    check(f"the user changed the Animation layout ({types()})", types() != C["factory"])
    with bpy.context.temp_override(window=win()):
        res = bpy.ops.allset.reset_workspace()
    C["res"] = res
    redraw()


@step
def s_reset_wait():
    redraw()


@step
def s_reset_wait2():
    redraw()


@step
def s_reset():
    names = [w.name for w in bpy.data.workspaces]
    check(f"Reset Current Workspace puts Animation back ({C['res']}, {types()})",
          C["res"] == {'FINISHED'} and types() == C["factory"] and win().workspace.name == "Animation")
    check(f"one Animation workspace left ({names})", names.count("Animation") == 1 and not
          any(n.endswith("(old)") for n in names))
    shot("Animation_reset")


run()
