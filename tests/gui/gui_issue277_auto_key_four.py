"""Issue #277 items 1 and 4 in a real UI, in the Maya layout: the Time Slider's Auto Key button is shown and a click
turns Auto Key on; the Tool Box Four View button clicked twice keeps 4 panels and Single goes back to 1.
(Run it with other window sizes / UI scales too: ALLSET_GUI_GEOMETRY="0 0 1280 800", --ui-scale 0.8.)"""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, find_button, load_maya_layout, run, screenshot, setup, step, win  # noqa: E402

GUI_TIMEOUT = 300
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def timeline():
    for area in win().screen.areas:
        if area.type == 'DOPESHEET_EDITOR' and area.spaces.active.mode == 'TIMELINE':
            return area, next(r for r in area.regions if r.type == 'HEADER')
    raise LookupError("no Time Slider")


def toolbox():
    tb = mod("ui.toolbox")
    area = next(a for a in win().screen.areas if a.type == 'VIEW_3D' and tb.is_toolbox(a.spaces.active))
    return area, next(r for r in area.regions if r.type == 'TOOLS')


def panels():
    tb = mod("ui.toolbox")
    return [a for a in win().screen.areas if a.type == 'VIEW_3D' and not tb.is_toolbox(a.spaces.active)]


def click_at(key):
    def hover():
        pos = C.get(key)
        if pos:
            ev('MOUSEMOVE', 'NOTHING', x=pos[0], y=pos[1])

    def press():
        if C.get(key):
            ev('LEFTMOUSE', 'PRESS')
            ev('LEFTMOUSE', 'RELEASE')
    step(hover)
    step(press)
    for _i in range(12):           # a second press on the same button soon after would be a double-click
        step(lambda: None)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_size():
    print(f"GUI window {win().width} x {win().height}, UI scale {bpy.context.preferences.system.ui_scale:.2f}",
          flush=True)


# --- 1: Auto Key -----------------------------------------------------------------------------------------------------
step(find_button(timeline, lambda path, cmd: "allset_auto_key" in path, C, "auto", step_px=5))


@step
def s_auto_found():
    _a, header = timeline()
    pos = C.get("auto")
    check(f"#277-1: the Time Slider shows the Auto Key button ({pos}, header {header.x}..{header.x + header.width})",
          pos is not None and header.x <= pos[0] <= header.x + header.width)
    shot("issue277_time_slider.png")


click_at("auto")


@step
def s_auto_on():
    on = bpy.context.scene.allset_auto_key
    check("#277-1: a click on it turns Auto Key on", on)
    bpy.context.scene.allset_auto_key = False


# --- 4: Four View twice, then Single ---------------------------------------------------------------------------------
step(find_button(toolbox, lambda path, cmd: "quick_layout" in cmd and "FOUR" in cmd, C, "four", step_px=4,
                 x_frac=0.5))
click_at("four")


@step
def s_four_once():
    n = len(panels())
    check(f"#277-4: Four View = 4 panels ({n})", n == 4)


click_at("four")


@step
def s_four_twice():
    n = len(panels())
    check(f"#277-4: Four View again keeps 4 panels ({n})", n == 4)
    shot("issue277_four_twice.png")


step(find_button(toolbox, lambda path, cmd: "quick_layout" in cmd and "SINGLE" in cmd, C, "single", step_px=4,
                 x_frac=0.5))
click_at("single")


@step
def s_single():
    n = len(panels())
    check(f"#277-4: Single View = 1 panel ({n})", n == 1)


run()
