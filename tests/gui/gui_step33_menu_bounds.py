"""In a real UI: RMB on an object low in the view shows the whole marking menu list
(and its last row works), the hotbox opened near the top edge keeps its rows on screen;
screenshots."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_location_3d

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def draw():
    return import_module(MODULE + ".marking.draw")


def bounds():
    # menus draw over the whole window (its editors), like Maya's
    from sim import win
    area, region = view3d()
    return draw().window_bounds(win(), region)


def all_inside(rects):
    b = bounds()
    return all(b[0] - 1 <= r[0] and r[2] <= b[2] + 1 and b[1] - 1 <= r[1] and r[3] <= b[3] + 1 for r in rects)


@step
def s_setup():
    setup()
    cube = bpy.data.objects["Cube"]
    area, region = view3d()
    # Put the cube 70 px above the bottom of the view, half way across.
    target = location_3d_to_region_2d(region, region.data, cube.location)
    target.y = 70
    target.x = region.width / 2
    cube.location = region_2d_to_location_3d(region, region.data, target, cube.location)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    C["xy"] = (region.x + int(target.x), region.y + 70)


@step
def s_rmb():
    x, y = C["xy"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('RIGHTMOUSE', 'PRESS', x=x, y=y)
    ev('RIGHTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_rmb_open():
    s = draw().ACTIVE.get("session")
    check("RMB click on the low cube opens the object menu", s is not None and s.mode == "CLICK")
    if s is None:
        return
    cx, cy = s.center
    rects = [(it.rect[0] + cx, it.rect[1] + cy, it.rect[2] + cx, it.rect[3] + cy) for it in s.layout.items]
    labels = [it.label for it in s.layout.items]
    check("menu has the material rows", "Assign Existing Material" in labels)
    check("every radial box and list row is inside the window", all_inside(rects))
    last = next(it for it in s.layout.items if it.label == "Material Attributes...")
    _area, region = view3d()
    C["new"] = (region.x + int(cx + (last.rect[0] + last.rect[2]) / 2),
                region.y + int(cy + (last.rect[1] + last.rect[3]) / 2))


@step
def s_rmb_shot():
    shot("gui_step33_rmb_low.png")
    x, y = C["new"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_rmb_pick():
    x, y = C["new"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_search_open():
    check("the moved row still runs its item (menu closed)", not draw().ACTIVE)


@step
def s_search_shot():
    shot("gui_step33_assign_new_popup.png")
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')
    area, region = view3d()
    view = import_module(MODULE + ".operators.view")
    b = view.visible_bounds(area, region)
    C["top"] = (region.x + region.width // 2, region.y + int(b[3]) - 30)
    x, y = C["top"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('SPACE', 'PRESS', x=x, y=y)


@step
def s_hotbox_wait():
    pass


@step
def s_hotbox():
    hb = draw().ACTIVE.get("hotbox")
    check("Space hold near the top edge opens the hotbox", hb is not None)
    if hb is not None:
        check("hotbox menu rows inside the window", all_inside([r for r, _k, _l in hb.labels]))
        c = hb.center_rect
        check("rows clear of the centre box",
              not any(r[0] < c[2] and c[0] < r[2] and r[1] < c[3] and c[1] < r[3] for r, _k, _l in hb.labels))


@step
def s_hotbox_shot():
    shot("gui_step33_hotbox_top.png")
    x, y = C["top"]
    ev('SPACE', 'RELEASE', x=x, y=y)


run()
