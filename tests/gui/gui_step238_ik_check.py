"""Issue #146: Key > IK/FK Keys > Enable IK Solver draws Maya's check mark (on after the first
click). Shot with ``--shots``: the submenu opened mid-viewport."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, screenshot, setup, step, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")


def mod(name):
    return import_module(MODULE + name)


def v3d():
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


@step
def s_setup():
    setup()
    load_maya_layout()
    bpy.context.preferences.view.show_tooltips = False


@step
def s_state():
    mod(".operators.ik_fk")._STATE["on"] = True            # = Enable IK Solver clicked once (Maya: check on)
    check("the menu check reads the state", bpy.context.window_manager.allset_ik_solver)
    area, region = v3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)


@step
def s_open():
    ms = mod(".ui.menu_sets")
    sub = ms.SUBMENU_IDS.get("Key/IK/FK Keys")
    check(f"IK/FK Keys submenu class ({sub})", sub is not None)
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.call_menu(name=sub)


step(lambda: None)


@step
def s_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step238_ik_check.png"))
    area, region = v3d()
    ev('ESC', 'PRESS', x=region.x + region.width // 2, y=region.y + region.height // 2)
    ev('ESC', 'RELEASE', x=region.x + region.width // 2, y=region.y + region.height // 2)
    mod(".operators.ik_fk")._STATE["on"] = False


run()
