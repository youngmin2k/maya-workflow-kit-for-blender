"""#290: the Outliner toggle never opens a new window while it can dock. In a layout without the Tool Box column
(Blender's own Layout workspace, Modeling - Expert) a click hides the Outliner and the next click docks one back
left of the main viewport."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, setup, step, win  # noqa: E402

C = {}


def mod(name):
    return import_module(MODULE + name)


def toggle():
    with bpy.context.temp_override(window=win()):
        return bpy.ops.allset.toggle_outliner()


def counts():
    tb = mod(".ui.toolbox")
    return len(bpy.context.window_manager.windows), len(tb.outliner_areas(win().screen))


def make(tag, prepare):
    def first():
        prepare()

    def hide():
        tb = mod(".ui.toolbox")
        cols = [a for a in win().screen.areas if a.type == 'VIEW_3D' and tb.is_toolbox(a.spaces.active)]
        check(f"{tag}: no Tool Box column in this layout", not cols)
        if counts()[1] == 0:
            toggle()            # a layout without an Outliner: the first click docks one
        check(f"{tag}: an Outliner is docked {counts()}", counts() == (1, 1))
        toggle()

    def show():
        check(f"{tag}: the click hid the Outliner, no new window {counts()}", counts() == (1, 0))
        toggle()

    def shown():
        check(f"{tag}: the next click docked one back, no new window {counts()}", counts() == (1, 1))
        view, _r = mod(".ui.status_line").main_view3d(win().screen)
        out = mod(".ui.toolbox").outliner_areas(win().screen)[0]
        check(f"{tag}: it sits left of the main viewport ({out.x}+{out.width} vs {view.x})",
              abs(out.x + out.width - view.x) <= 8)
    return first, hide, show, shown


def blender_layout():
    print("workspace", win().workspace.name)


def expert():
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.maya_workspace(name="Modeling - Expert")


@step
def s_setup():
    setup()


for _tag, _prep in (("Blender Layout", blender_layout), ("Modeling - Expert", expert)):
    for _fn in make(_tag, _prep):
        step(_fn)


run()
