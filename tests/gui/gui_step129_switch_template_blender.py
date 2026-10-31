"""#19: , from the audit 128 repro: Maya -> Blender while the Maya Workflow Kit template file is open (what
"Make Blender feel like Maya" opens and what every Maya-mode start opens) must give a usable Blender
screen: no empty Status Line / Shelf image-editor strips, no Tool-tab-only Properties dock without
header, and File > New in Blender mode must not load the Maya template again.
PASSes when fixed."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, step, setup, screenshot, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def sw():
    return import_module(MODULE + ".switch")


def strips():
    out = []
    for a in win().screen.areas:
        sp = a.spaces.active
        if a.type == 'IMAGE_EDITOR' and getattr(sp, "mask", None) is not None and sp.mask.name.startswith(".Allset"):
            out.append(a)
    return out


def headerless_properties():
    return [a for a in win().screen.areas if a.type == 'PROPERTIES' and not a.spaces.active.show_region_header]


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_maya():
    sw().set_mode(True, layout=False)
    bpy.ops.allset.keymap_activate()
    check(f"Maya mode in the template file ({len(strips())} strips)", sw().is_on() and len(strips()) == 2)


@step
def s_to_blender():
    sw().set_mode(False)


@step
def s_check_blender():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_switch_template_blender.png"))
    check(f"Blender mode: no dead Maya Status Line / Shelf strips left ({len(strips())})", not strips())
    check(f"Blender mode: no header-less Properties dock left ({len(headerless_properties())})",
          not headerless_properties())
    C["n_ws"] = len(bpy.data.workspaces)
    sw().set_mode(True)


@step
def s_maya_again():
    check(f"Maya again in the same file: its own Maya layout is back ({len(strips())} strips, "
          f"{len(bpy.data.workspaces)} workspaces)", len(strips()) == 2 and len(bpy.data.workspaces) == C["n_ws"])
    sw().set_mode(False)


@step
def s_blender_again():
    check(f"Blender again: Blender's Layout reused ({len(strips())} strips, {len(bpy.data.workspaces)} workspaces)",
          not strips() and len(bpy.data.workspaces) == C["n_ws"])
    bpy.ops.wm.read_homefile()


@step
def s_new_file():
    check(f"Blender mode: File > New does not reload the Maya template "
          f"(app_template={bpy.context.preferences.app_template!r}, strips {len(strips())})",
          bpy.context.preferences.app_template != "Maya_Workflow_Kit" and not strips())


run()
