"""#121: in a real UI: Windows > Settings/Preferences > Preferences opens the kit's Maya Preferences window
(Categories list, page "<Category>: <description>", Save / Cancel); picking Time Slider shows the scene's framerate /
ranges; a change there is put back by Cancel; the Undo page shows Blender's Undo Steps read-only with the button
that opens Blender's Preferences. Shots: the Interface page, the Time Slider page."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, setup, step, view3d, win  # noqa: E402

GUI_TIMEOUT = 200
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(MODULE + name)


def prefs_window():
    return mod(".ui.marked_window").find_window(bpy.context, "PREFERENCES")


def shot(name):
    w = prefs_window()
    if SHOTS and w is not None:
        with bpy.context.temp_override(window=w):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def redraw():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_open():
    area, region = view3d()
    C["fps"] = bpy.context.scene.render.fps
    with bpy.context.temp_override(window=win(), area=area, region=region):
        C["open"] = bpy.ops.allset.menu_item(item="Windows/Settings/Preferences/Preferences")


@step
def s_opened():
    redraw()


@step
def s_check_open():
    w = prefs_window()
    check(f"Windows > Settings/Preferences > Preferences opens the kit window ({C['open']})", w is not None)
    if w is None:
        return
    area = w.screen.areas[0]
    check("one area, no Blender header (Maya window)",
          len(w.screen.areas) == 1 and not area.spaces.active.show_region_header)
    bpy.context.window_manager.allset_prefs_category = 'INTERFACE'
    redraw()


@step
def s_wait1():
    redraw()


@step
def s_shot_interface():
    shot("gui_step215_prefs_interface.png")
    bpy.context.window_manager.allset_prefs_category = 'TIME_SLIDER'
    bpy.context.scene.render.fps = 30          # a change made in the window
    redraw()


@step
def s_wait2():
    redraw()


@step
def s_shot_time():
    shot("gui_step215_prefs_time_slider.png")
    w = prefs_window()
    with bpy.context.temp_override(window=w, area=w.screen.areas[0]):
        bpy.ops.allset.prefs_cancel()


@step
def s_cancelled():
    check(f"Cancel puts the framerate back ({bpy.context.scene.render.fps} == {C['fps']})",
          bpy.context.scene.render.fps == C["fps"])


@step
def s_closed():
    check("Cancel closes the window", prefs_window() is None)


run()
