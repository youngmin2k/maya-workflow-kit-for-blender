"""#101: lane A in a real UI: Display > Grid ❒ opens Maya's Grid Options window, and applying other values
(length, lines every, subdivisions, colours) changes the grid the Maya layout view draws. Screenshots
(ALLSET_GUI_SHOTS) for the step doc, next to Maya's Grid Options window."""

import os
import sys
from importlib import import_module

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {"n": 0}
RED = (1.0, 0.0, 0.0)


def mod(name):
    return import_module(f"{MODULE}.{name}")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def grab(tag):
    """Screenshot of the window as an (h, w, 3) array (row 0 = bottom)."""
    C["n"] += 1
    path = os.path.join(SHOTS or bpy.app.tempdir, f"gui_step152_{C['n']}_{tag}.png")
    screenshot(path)
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    return a.reshape(h, w, 4)[:, :, :3]


def red_pixels(img):
    area, _r = view3d()
    sub = img[area.y:area.y + area.height, area.x:area.x + area.width]
    return int(((sub[:, :, 0] > 0.8) & (sub[:, :, 1] < 0.2) & (sub[:, :, 2] < 0.2)).sum())


def esc():
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_keys():
    bpy.ops.allset.keymap_activate()
    mod("operators.option_windows").store("grid_options", None)
    area, r = view3d()
    C["mid"] = (r.x + r.width // 2, r.y + r.height // 2)
    ev('MOUSEMOVE', 'NOTHING', x=r.x + 5, y=r.y + r.height - 5)
    redraw()


@step
def s_wait():
    redraw()


@step
def s_factory():
    img = grab("factory_grid")
    C["red0"] = red_pixels(img)
    check("Maya grid on in the main view", mod("ui.maya_grid").is_on(view3d()[0].spaces.active))


@step
def s_open():
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0], y=C["mid"][1])
    with bpy.context.temp_override(window=win()):
        res = bpy.ops.allset.menu_option_box('INVOKE_DEFAULT', item="Display/Grid")
    check(f"Display > Grid option box opens ({res})", res in ({'FINISHED'}, {'RUNNING_MODAL'}))
    check("Display > Grid option box = a Maya window", mod("ui.menu_sets").option_kind("Display/Grid") == "window")


@step
def s_open_wait():
    pass


@step
def s_window_shot():
    grab("grid_options_window")
    esc()


@step
def s_apply():
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0] + 400, y=C["mid"][1] + 200)
    with bpy.context.temp_override(window=win()):
        res = bpy.ops.allset.opt_grid_options('EXEC_DEFAULT', size=6.0, spacing=2.0, divisions=4, axis_color=RED,
                                              line_color=(0.1, 0.1, 0.1), division_color=(0.55, 0.55, 0.55))
    check(f"Grid Options Apply and Close ran ({res})", res == {'FINISHED'})
    redraw()


@step
def s_apply_wait():
    redraw()


@step
def s_applied():
    img = grab("applied_grid")
    red = red_pixels(img)
    check(f"red axes drawn after Apply ({C['red0']} -> {red} red px)", red > C["red0"] + 50)
    s = mod("ui.maya_grid").settings()
    check("applied values kept", (s["size"], s["spacing"], s["divisions"]) == (6.0, 2.0, 4))


@step
def s_reset():
    mod("operators.option_windows").store("grid_options", None)
    redraw()


@step
def s_reset_wait():
    redraw()


@step
def s_reset_shot():
    img = grab("reset_grid")
    check("factory grid back after Reset (no red)", red_pixels(img) <= C["red0"] + 5)


run()
