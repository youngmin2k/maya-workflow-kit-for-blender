"""Issue #153: in a real UI: Move Absolute, Rotate Relative; switching tools (W / E) and pressing the
manipulator put that tool's own mode into Blender's shared Absolute Grid Snap flag before its transform starts, and a
Move drag lands on whole grid units."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, tap, view3d, win  # noqa: E402

C = {}


def ts():
    return bpy.context.scene.tool_settings


def ov():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


@step
def s_setup():
    C["x"], C["y"] = setup()
    snap = import_module(MODULE + ".operators.snap_align")
    with ov():
        bpy.ops.allset.step_snap('EXEC_DEFAULT', True, kind='TRANSLATE', mode='ABSOLUTE')
        bpy.ops.allset.step_snap('EXEC_DEFAULT', True, kind='ROTATE', mode='RELATIVE')
    check("the last click (Rotate Relative) left Blender's flag relative", ts().use_snap_grid_absolute is False)
    check("Move still shows Absolute", snap.step_snap_mode(ts(), 'TRANSLATE') == 'ABSOLUTE')
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    tap('E')                     # Rotate tool


@step
def s_wait_e():
    pass


@step
def s_wait_e2():
    pass


@step
def s_rotate():
    check(f"E: the Rotate tool's Relative is in Blender's flag ({ts().use_snap_grid_absolute})",
          ts().use_snap_grid_absolute is False)
    tap('W')                     # Move tool


@step
def s_wait_w():
    pass


@step
def s_wait_w2():
    pass


@step
def s_move():
    check(f"W: the Move tool's Absolute is in Blender's flag ({ts().use_snap_grid_absolute})",
          ts().use_snap_grid_absolute is True)
    ts().use_snap_grid_absolute = False          # something else flipped it; a manipulator press puts it back
    with ov():
        bpy.ops.allset.manip_press('INVOKE_DEFAULT')
    check("a press on the Move manipulator applies Move's Absolute", ts().use_snap_grid_absolute is True)


run()
