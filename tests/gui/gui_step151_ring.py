"""Lane A (#99) in a real UI: RMB on pCube1 and Shift+RMB with nothing selected draw Maya 2022's compact ring
(radius 55 x UI scale, boxes text + 2 x 25 px, UV with a submenu arrow, the list 21 px under the ring).
Screenshots of the object marking menu and the Shift+RMB menu:
gui_step151_rmb.png, gui_step151_shift_rmb.png (run with ALLSET_GUI_UI_SCALE=0.8 on a 125 % display = scale 1.0)."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, screenshot, step, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def draw():
    return import_module(MODULE + ".marking.draw")


def engine():
    return import_module(MODULE + ".marking.engine")


def main_view():
    status_line = import_module(MODULE + ".ui.status_line")
    return status_line.main_view3d(win().screen)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, region = main_view()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    bpy.ops.object.select_all(action='DESELECT')
    redraw()


@step
def s_rmb_press():
    _area, region = main_view()
    ob = bpy.data.objects["pCube1"]
    p = location_3d_to_region_2d(region, region.data, ob.location)
    x, y = region.x + int(p.x), region.y + int(p.y)
    C["rmb"] = (x, y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('RIGHTMOUSE', 'PRESS', x=x, y=y)


@step
def s_rmb_wait():
    redraw()


def _ring_checks(s, what):
    k = draw().ui_scale()
    r = s.layout.radial
    p = s.params
    check(f"{what}: radius {p.radius:.2f} = 55 x UI scale {k:.2f}", abs(p.radius - 55 * k) < 1e-3)
    if "N" in r:
        n = r["N"].rect
        check(f"{what}: N box centre 55 px above the press point x scale ({(n[1] + n[3]) / 2:.1f})",
              abs((n[1] + n[3]) / 2 - 55 * k) < 0.5)
    if "E" in r:
        check(f"{what}: E box near side 55 px right x scale ({r['E'].rect[0]:.1f})", abs(r["E"].rect[0] - 55 * k) < 0.5)
    heights = {round(it.rect[3] - it.rect[1], 2) for it in r.values()}
    check(f"{what}: boxes 21 px high x scale ({heights})", heights == {round(21 * k, 2)})


@step
def s_rmb():
    s = draw().ACTIVE.get("session")
    check("RMB on pCube1 opens the object marking menu", s is not None)
    if s is None:
        return
    _ring_checks(s, "RMB")
    uv = s.layout.radial.get("E")
    check("E = UV with a submenu arrow", uv is not None and uv.label == "UV" and engine().Layout.has_arrow(uv.action))
    rows = [it for it in s.layout.items if it.kind == "list"]
    # the list goes under the ring when it fits (gap 21 px), else one column beside it
    gap = s.layout.radial["S"].rect[1] - max(it.rect[3] for it in rows)
    boxes = [b.rect for b in s.layout.radial.values()]
    beside = (min(it.rect[0] for it in rows) >= max(b[2] for b in boxes)
              or max(it.rect[2] for it in rows) <= min(b[0] for b in boxes))
    check(f"list 21 px x scale under the S box ({gap:.1f}), or one column beside the ring ({beside})",
          abs(gap - 21 * draw().ui_scale()) < 0.5 or (beside and len({it.rect[0] for it in rows}) == 1))


@step
def s_rmb_shot():
    shot("gui_step151_rmb.png")
    x, y = C["rmb"]
    ev('RIGHTMOUSE', 'RELEASE', x=x, y=y)
    ev('ESC', 'PRESS', x=x, y=y)
    ev('ESC', 'RELEASE', x=x, y=y)


@step
def s_shift_press():
    bpy.ops.object.select_all(action='DESELECT')
    x, y = C["rmb"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('RIGHTMOUSE', 'PRESS', x=x, y=y, shift=True)


@step
def s_shift_wait():
    redraw()


@step
def s_shift():
    s = draw().ACTIVE.get("session")
    check("Shift+RMB opens a marking menu", s is not None)
    if s is None:
        return
    check(f"all 8 directions ({sorted(s.layout.radial)})", len(s.layout.radial) == 8)
    _ring_checks(s, "Shift+RMB")


@step
def s_shift_shot():
    shot("gui_step151_shift_rmb.png")
    x, y = C["rmb"]
    ev('RIGHTMOUSE', 'RELEASE', x=x, y=y, shift=True)
    ev('ESC', 'PRESS', x=x, y=y)
    ev('ESC', 'RELEASE', x=x, y=y)


run()
