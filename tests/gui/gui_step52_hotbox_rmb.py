"""In a real UI (Maya Workflow Kit layout, Channel Box dock open): the hotbox shows Maya's rows (all menu sets,
"Maya" in the centre) and draws over the sidebar too; RMB on pCube1 shows the Maya 2022 list under the ring.
Screenshots: gui_step52_hotbox.png, gui_step52_rmb.png."""

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
def s_hotbox_press():
    area, region = main_view()
    ui = next(r for r in area.regions if r.type == 'UI')
    C["ui"] = (ui.x, ui.width)
    # near the sidebar, like the kit shot of 13_hotbox: the rows reach over the Channel Box dock
    x, y = ui.x - 120, region.y + region.height // 2
    C["hb"] = (x, y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('SPACE', 'PRESS', x=x, y=y)


@step
def s_hotbox_wait():
    redraw()


@step
def s_hotbox():
    lay = draw().ACTIVE.get("hotbox")
    check("Space hold opens the hotbox", lay is not None)
    if lay is None:
        return
    _area, region = main_view()
    rows = {}
    for r, _k, label in lay.labels:
        rows.setdefault(r[1], []).append(label)
    check(f"{len(rows)} rows (Maya: 2 above, the centre row, 5 menu sets)", len(rows) == 8)
    check("centre box says Maya Workflow Kit", lay.title == "Maya Workflow Kit")
    check("four zone lines", len(lay.zone_lines) == 4)
    ui_x = C["ui"][0] - region.x
    check("rows reach over the sidebar dock (drawn there too)", max(r[2] for r, _k, _l in lay.labels) > ui_x)
    b = draw().window_bounds(win(), region)
    check("rows inside the window", all(b[0] - 1 <= r[0] and r[2] <= b[2] + 1 for r, _k, _l in lay.labels))


@step
def s_hotbox_shot():
    shot("gui_step52_hotbox.png")
    x, y = C["hb"]
    ev('SPACE', 'RELEASE', x=x, y=y)


@step
def s_rmb_press():
    area, region = main_view()
    ob = bpy.data.objects["pCube1"]
    p = location_3d_to_region_2d(region, region.data, ob.location)
    x, y = region.x + int(p.x), region.y + int(p.y)
    C["rmb"] = (x, y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('RIGHTMOUSE', 'PRESS', x=x, y=y)


@step
def s_rmb_wait():
    redraw()


@step
def s_rmb():
    s = draw().ACTIVE.get("session")
    check("RMB on pCube1 opens the object marking menu", s is not None)
    if s is None:
        return
    rows = [it for it in s.layout.items if it.kind == "list"]
    check(f"first row is the object's name ({rows[0].label if rows else None})",
          bool(rows) and rows[0].label == "pCube1...")
    labels = [it.label for it in rows]
    want = ["Select", "Select All", "Deselect All", "Select Hierarchy", "Invert Selection", "Select Similar",
            "Make Live", "DG Traversal", "Inputs", "Outputs", "Paint"]
    check("Maya 2022 rows in order", labels[1:1 + len(want)] == want)
    # marking/engine.fit_ring: one column, under the ring when it fits, else beside it on the side
    # without a radial submenu (RMB on a mesh: E = UV, so the left side); never over the ring
    boxes = list(s.layout.radial.values())
    ring_bottom = min(it.rect[1] for it in boxes)
    under = all(it.rect[3] <= ring_bottom for it in rows)
    beside = max(it.rect[2] for it in rows) <= min(x.rect[0] for x in boxes)
    check(f"the list is under the ring or beside it (under {under}, left {beside})", under or beside)
    x0, x1 = min(it.rect[0] for it in rows), max(it.rect[2] for it in rows)
    b = draw().window_bounds(win(), main_view()[1])
    cx = s.center[0]
    check("one column; under the ring it is centred (or slid inside the window)",
          len({round(it.rect[0], 3) for it in rows}) == 1
          and (not under or abs((x0 + x1) / 2) < 1 or abs(x0 + cx - b[0]) < 1 or abs(x1 + cx - b[2]) < 1))


@step
def s_rmb_shot():
    shot("gui_step52_rmb.png")
    x, y = C["rmb"]
    ev('RIGHTMOUSE', 'RELEASE', x=x, y=y)
    ev('ESC', 'PRESS', x=x, y=y)
    ev('ESC', 'RELEASE', x=x, y=y)


run()
