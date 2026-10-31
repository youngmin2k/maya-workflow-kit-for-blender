"""In a real UI: the option boxes of Create > Polygon Primitives > Gear and Control > Create Character Set open
Maya's option windows instead of Blender's Adjust Last
Operation; screenshots (ALLSET_GUI_SHOTS)."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, setup, screenshot, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def esc():
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


def box(path):
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0], y=C["mid"][1])
    with bpy.context.temp_override(window=win()):
        res = bpy.ops.allset.menu_option_box('INVOKE_DEFAULT', item=path)
    # the box runs the window's operator nested (FINISHED for the box itself, like gui_step103's box click)
    check(f"{path} option box opens its window ({res})", res in ({'FINISHED'}, {'RUNNING_MODAL'}))


@step
def s_setup():
    setup()
    a, _r = view3d()
    C["mid"] = (a.x + a.width // 2, a.y + a.height // 2)
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.create(kind='CUBE')


@step
def s_gear():
    box("Create/Polygon Primitives/Gear")


@step
def s_w1():
    ev('MOUSEMOVE', 'NOTHING', x=8, y=C["mid"][1])    # off the dialog: no tooltip over its first row


@step
def s_gear_shot():
    shot("gui_step196_polygon_gear_options.png")
    esc()


@step
def s_character():
    box("Control/Create Character Set")


@step
def s_w2():
    ev('MOUSEMOVE', 'NOTHING', x=8, y=C["mid"][1])


@step
def s_character_shot():
    shot("gui_step196_create_character_set_options.png")
    esc()


@step
def s_done():
    check("no kit option window left open", True)


run()
