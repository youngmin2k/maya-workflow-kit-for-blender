"""#307 in a real UI, the reporter's steps: a Blender file -> Maya mode -> File > New Scene in Maya mode -> Blender mode.
Blender mode shows Blender's tabs only (no Maya workspace mixed in) and the workspace the user had before Maya mode;
a second round trip leaves the same tabs."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, screenshot, setup, step, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def sw():
    return import_module(MODULE + ".switch")


def maya_names():
    return sorted(w.name for w in bpy.data.workspaces if sw().is_maya_workspace(w))


def blender_names():
    return sorted(w.name for w in bpy.data.workspaces if not sw().is_maya_workspace(w))


@step
def s_setup():
    setup()
    check(f"no user startup file in the sandbox ({sw().user_startup_file()})", sw().user_startup_file() is None)
    win().workspace = bpy.data.workspaces["Modeling"]


@step
def s_maya():
    check(f"Blender file on Modeling ({win().workspace.name})", win().workspace.name == "Modeling")
    sw().set_mode(True)


@step
def s_maya_shown():
    check(f"Maya mode shows the Maya layout ({win().workspace.name})", sw().is_maya_workspace(win().workspace))
    load_maya_layout()                     # File > New Scene in Maya mode


@step
def s_new_scene():
    check(f"a new scene in the Maya layout ({win().workspace.name}, {maya_names()})",
          sw().is_maya_workspace(win().workspace) and len(maya_names()) > 1)
    sw().set_mode(False)


@step
def s_wait():
    pass


@step
def s_blender():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_issue307_blender_tabs.png"))
    check(f"Blender mode shows the workspace from before Maya mode ({win().workspace.name})",
          win().workspace.name == "Modeling")
    check(f"no Maya workspace left among the tabs ({maya_names()})", not maya_names())
    check(f"Blender's own tabs ({blender_names()})", blender_names() == sorted(sw().BLENDER_WORKSPACES))
    C["names"] = blender_names()
    sw().set_mode(True)


@step
def s_maya_again():
    check(f"Maya mode shows the Maya layout again ({win().workspace.name})", sw().is_maya_workspace(win().workspace))
    sw().set_mode(False)


@step
def s_wait_again():
    pass


@step
def s_blender_again():
    check(f"and back: the same Blender tabs, no Maya one ({win().workspace.name}, {maya_names()}, "
          f"{blender_names()})",
          win().workspace.name == "Modeling" and not maya_names() and blender_names() == C["names"])


run()
