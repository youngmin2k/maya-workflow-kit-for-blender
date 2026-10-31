"""#36 crash class: the four view splits its top row from a timer one tick later
(ui/four_view.py ``_split_top_later``). A second window enters the four view and closes before that tick runs; the
tick must find the window gone (pointers + live_refs) instead of touching the freed window. PASSES when Blender is
still running afterwards."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, setup, step, view3d, win  # noqa: E402

C = {}


def second():
    return next((w for w in bpy.context.window_manager.windows if w.as_pointer() == C.get("ptr")), None)


@step
def s_setup():
    setup()


@step
def s_open():
    before = {w.as_pointer() for w in bpy.context.window_manager.windows}
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.window_new()
    new = [w for w in bpy.context.window_manager.windows if w.as_pointer() not in before]
    check("a second window opened", len(new) == 1)
    C["ptr"] = new[0].as_pointer() if new else None


step(lambda: None)


@step
def s_four_then_close():
    w = second()
    if w is None:
        return
    fv = import_module(MODULE + ".ui.four_view")
    area = max((a for a in w.screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    placed = fv.enter(bpy.context, area, w)
    check(f"the four view started in the second window ({len(placed)} panels now, the top row next tick)",
          len(placed) == 3)
    with bpy.context.temp_override(window=w):
        bpy.ops.wm.window_close()


@step
def s_closed():
    check("the second window closed", second() is None)


for _ in range(4):
    step(lambda: None)


@step
def s_alive():
    check("Blender still running after closing a window while its four view was being split", True)


run()
