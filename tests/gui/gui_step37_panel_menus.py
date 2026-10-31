"""In a real UI: the 3D View header shows Maya's panel menus; click Shading and pick
Wireframe, open Show (screenshots), Blender ▸ still has Blender's menus."""

import os
import sys


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, px, run, screenshot, setup, step, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def header():
    area, _r = view3d()
    return next(r for r in area.regions if r.type == 'HEADER')


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    C["x"], C["y"] = setup()
    h = header()
    C["hy"] = h.y + h.height // 2
    C["hx"] = h.x
    ev('MOUSEMOVE', 'NOTHING', x=h.x + px(200), y=C["hy"])
    redraw()


@step
def s_header_shot():
    shot("gui_step37_header.png")
    check("3D View header redrawn (screenshot)", True)
    click(286)  # "Shading" (x read from gui_step37_header.png, 1600 px window)


def click(x, y=None):
    x, y = C["hx"] + px(x), C["hy"] if y is None else y
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_shading_wait():
    redraw()


@step
def s_shading_shot():
    shot("gui_step37_shading_menu.png")
    click(326, C["hy"] - px(29))  # "Wireframe", first row under the header


@step
def s_wireframe():
    shading = view3d()[0].spaces.active.shading
    check(f"Shading > Wireframe from the header menu ({shading.type})", shading.type == 'WIREFRAME')
    click(622)  # "Blender"


@step
def s_blender_wait():
    redraw()


@step
def s_blender_shot():
    shot("gui_step37_blender_menu.png")
    tap('ESC')
    check("Blender submenu opened (screenshot)", True)


@step
def s_after_blender():
    # Event simulation: after ESC closes a header menu the cursor has to leave the header
    # once, or the next click on another header menu opens nothing.
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    redraw()


@step
def s_show():
    click(419)  # "Show"


@step
def s_show_wait():
    redraw()


@step
def s_show_shot():
    shot("gui_step37_show_menu.png")
    tap('ESC')
    check("Show menu opened (screenshot)", True)


@step
def s_after_show():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    redraw()


@step
def s_panels():
    click(556)  # "Panels"


@step
def s_panels_wait():
    redraw()


@step
def s_panels_wait2():
    redraw()


@step
def s_panels_shot():
    shot("gui_step37_panels_menu.png")
    tap('ESC')
    check("Panels menu opened (screenshot)", True)


run()
