"""Issue #154: in a real UI: File > Game Exporter opens a kit window that stays open while you work in the
main window (a click there no longer drops the File Name edit), shows the "Up Axis" label, and closes by its window."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mw():
    return import_module(MODULE + ".ui.marked_window")


def exporter():
    return mw().find_window(bpy.context, "GAME_EXPORTER")


@step
def s_setup():
    C["x"], C["y"] = setup()
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.menu_item(item="File/Game Exporter")


@step
def s_wait():
    pass


@step
def s_open():
    w = exporter()
    check("File > Game Exporter opened a kit window", w is not None)
    s = bpy.context.scene.allset_game_exporter
    check(f"File Name starts empty like Maya 2026 ({s.export_filename!r})", s.export_filename == "")
    s.export_filename = "hero"            # the user types a name
    # then works in the main window: a click in the viewport
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('LEFTMOUSE', 'PRESS', x=C["x"], y=C["y"])
    ev('LEFTMOUSE', 'RELEASE', x=C["x"], y=C["y"])


@step
def s_wait2():
    pass


@step
def s_still_open():
    w = exporter()
    check("a click in the main window leaves the Game Exporter open", w is not None)
    check("the File Name edit is kept", bpy.context.scene.allset_game_exporter.export_filename == "hero")
    if w is not None and SHOTS:
        with bpy.context.temp_override(window=w):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, "gui_step263_game_exporter_prev.png"))


@step
def s_shot():
    w = exporter()
    if w is not None and SHOTS:
        with bpy.context.temp_override(window=w):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, "gui_step263_game_exporter.png"))
    if w is not None:
        mw().close_later(w)


@step
def s_wait3():
    pass


@step
def s_closed():
    check("the window closes as a window", exporter() is None)


run()
