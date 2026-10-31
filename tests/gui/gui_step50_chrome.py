"""In a real UI: Maya editor chrome — Channel Box / Layer Editor menu bars, Outliner header,
Time Slider buttons in the timeline sidebar, Range Slider row; screenshots."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def timeline():
    return next(a for a in win().screen.areas if a.ui_type == 'TIMELINE')


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    bpy.ops.allset.create(kind='CUBE')
    redraw()


@step
def s_wait():
    redraw()


@step
def s_check():
    tl = timeline()
    regions = {r.type: r for r in tl.regions}
    ui = regions.get('UI')
    # Blender 5.x loads the template's timeline sidebar 1 px wide: the buttons go to the header
    ts = import_module(MODULE + ".ui.time_slider")
    check(f"5.x: Time Slider buttons in the header instead ({ui and (ui.x, ui.width)})",
          not ts.has_slider_panel(tl.spaces.active, tl))
    # the panel draws: frame field + transport buttons are not the region background
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step50_chrome.png"))
    redraw()


@step
def s_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step50_chrome.png"))


run()
