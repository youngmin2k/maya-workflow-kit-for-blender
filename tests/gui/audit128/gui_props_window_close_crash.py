"""Audit 128 repro (crash): a Maya menu item that opens a Properties window on a tab (Display > Wireframe Color...,
Shape Editor, Color Set Editor, UV Set Editor, Light Linking ...) retries the tab from a timer for up to 2 s
(operators/menu_extras.properties_tab_later). Closing that window before the timer gives up crashed Blender 4.5
(EXCEPTION_ACCESS_VIOLATION in BKE_workspace_active_screen_get via Window.screen, during a menu sweep).
PASSes when Blender survives (the last check runs after the timer's 2 s)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sim import MODULE, check, run, setup, step, view3d, win  # noqa: E402

C = {}


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)


@step
def s_open():
    # nothing active: the OBJECT tab never becomes available, so the timer keeps retrying
    bpy.context.view_layer.objects.active = None
    for ob in bpy.context.scene.objects:
        ob.select_set(False)
    C["n"] = len(bpy.context.window_manager.windows)
    modal = import_module(MODULE + ".marking.modal")
    mm = import_module(MODULE + ".ui.menu_map")
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        modal.run_action(bpy.context, mm.MAP["Display/Wireframe Color..."], path="Display/Wireframe Color...")


@step
def s_close():
    wins = list(bpy.context.window_manager.windows)
    check(f"Display > Wireframe Color... opened a window ({C['n']} -> {len(wins)})", len(wins) > C["n"])
    for w in wins:
        if w != win():
            with bpy.context.temp_override(window=w):
                bpy.ops.wm.window_close()


for _ in range(8):       # 8 x 0.4 s > the timer's 40 x 0.05 s
    step(lambda: None)


@step
def s_alive():
    check("Blender still running 3 s after closing the window (no crash in properties_tab_later)", True)


run()
