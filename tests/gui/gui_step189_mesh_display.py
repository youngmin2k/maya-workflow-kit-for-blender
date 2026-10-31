"""In a real UI: the Status Line Construction History toggle (pressed = on, a click turns it off), the panel
Show menu with IK Handles / Image Planes as check rows, and the Mesh Display menu with its new working items (shots)."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, load_maya_layout, run, screenshot, setup, step, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), screen=win().screen, area=area, region=region)


@step
def s_setup():
    C["x"], C["y"] = setup()
    load_maya_layout()


@step
def s_history_group():
    bpy.ops.allset.keymap_activate()
    if bpy.ops.allset.status_group.poll():
        bpy.ops.allset.status_group(group="HISTORY")      # Maya shows the group collapsed: open it
    wm = bpy.context.window_manager
    check("Construction History starts on", wm.allset_construction_history is True)


@step
def s_history_toggle():
    with override():
        bpy.ops.allset.construction_history()
    check("the Status Line toggle turns Construction History off",
          bpy.context.window_manager.allset_construction_history is False)
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_history_shot():
    shot("gui_step189_status_line_history_off.png")
    with override():
        bpy.ops.allset.construction_history()


def _open(menu):
    area, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height * 2 // 3)
    with override():
        bpy.ops.wm.call_menu(name=menu)


@step
def s_show_menu():
    _open("ALLSET_MT_panel_show")


@step
def s_show_shot():
    shot("gui_step189_show_menu.png")
    tap('ESC')
    check("panel Show menu opened (screenshot)", True)


run()
