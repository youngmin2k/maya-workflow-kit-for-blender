"""In a real UI: the option boxes of Skeleton > Create Joints, Key > Delete Keys and Constrain > Aim open
their Maya option windows; screenshots (ALLSET_GUI_SHOTS)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
PATHS = (("create_joints", "Skeleton/Create Joints"), ("delete_keys", "Key/Delete Keys"), ("aim", "Constrain/Aim"))


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def esc():
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


@step
def s_setup():
    setup()
    a, _r = view3d()
    C["mid"] = (a.x + a.width // 2, a.y + a.height // 2)
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0], y=C["mid"][1])
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.create(kind='CUBE')
    menu_sets = import_module(MODULE + ".ui.menu_sets")
    for _name, path in PATHS:
        check(f"{path} option box = a Maya window", menu_sets.option_kind(path) == "window")


def _open(path):
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0], y=C["mid"][1])
    with bpy.context.temp_override(window=win()):
        res = bpy.ops.allset.menu_option_box('INVOKE_DEFAULT', item=path)
    check(f"{path} option box opens", res in ({'FINISHED'}, {'RUNNING_MODAL'}))
    ow = import_module(MODULE + ".operators.option_windows")
    w = ow.find_path(path)
    check(f"{path} window title", w is not None and w.title.endswith(("Options", "Tool")))


def _steps(name, path):
    @step
    def s_open():
        _open(path)

    @step
    def s_wait():
        pass

    @step
    def s_shot():
        shot(f"gui_step140_{name}.png")
        esc()
    s_open.__name__ = f"s_{name}_open"
    s_wait.__name__ = f"s_{name}_wait"
    s_shot.__name__ = f"s_{name}_shot"


for _n, _p in PATHS:
    _steps(_n, _p)

run()
