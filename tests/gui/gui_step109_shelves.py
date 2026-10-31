"""In a real UI: every Maya shelf tab shows all of Maya's buttons (greyed slots for the unmapped ones),
a click on a greyed icon shows its notice, a Sculpting icon picks the Blender brush; one shot per tab."""

import json
import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, scale, step, setup, screenshot, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {"rects": {}}
shelf = import_module(MODULE + ".ui.shelf")
shelf_data = import_module(MODULE + ".ui.shelf_data")
notices = import_module(MODULE + ".ui.notices")
MAYA_COUNTS = {"Curves": 14, "Surfaces": 24, "Polygons": 37, "Sculpting": 26, "UVEditing": 12, "Rigging": 18,
               "Animation": 18, "Rendering": 26, "FX": 29, "FXCaching": 10}     # Maya 2026
TABS = [s[0] for s in shelf_data.SHELVES]


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def shelf_area():
    return shelf.shelf_row_area(win().screen)


def icon_centre(slot):
    area = shelf_area()
    r = next(r for r in area.regions if r.type == 'WINDOW')
    x, y, size = shelf.icon_rect(r, slot, scale())
    return round(r.x + x + size / 2), round(r.y + y + size / 2)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    bpy.ops.allset.make_maya(open_layout=False)     # Maya theme (dogfood note)
    bpy.ops.allset.shelf_select(shelf=TABS[0])
    redraw()


def _tab_steps(name):
    def select():
        bpy.ops.allset.shelf_select(shelf=name)
        ev('MOUSEMOVE', 'NOTHING', x=win().width // 2, y=win().height // 2)
        redraw()

    def check_and_shoot():
        cur, buttons = shelf.icon_buttons(bpy.context)
        greyed = sum(1 for b in buttons if not b[3])
        check(f"{name}: {len(buttons)} slots = Maya {MAYA_COUNTS[name]} ({greyed} greyed)",
              cur == name and len(buttons) == MAYA_COUNTS[name])
        area = shelf_area()
        C["rects"][name] = [area.x, area.y, area.width, area.height]

    def shoot():
        if SHOTS:
            screenshot(os.path.join(SHOTS, f"gui_step109_{name}.png"))
    step(select)
    step(check_and_shoot)
    step(shoot)


for _name in TABS:
    _tab_steps(_name)


@step
def s_greyed_hover():
    bpy.ops.allset.shelf_select(shelf="Surfaces")
    redraw()
    _cur, buttons = shelf.icon_buttons(bpy.context)
    C["trim"] = next(k for k, b in enumerate(buttons) if b[1] == "Trim Tool")
    x, y = icon_centre(C["trim"])
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_greyed_click():
    redraw()
    ev('LEFTMOUSE', 'PRESS')
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_greyed_check():
    check(f"greyed Trim Tool click shows its notice ({notices.current()!r})",
          notices.current().startswith("Trim Tool: "))
    C["n0"] = len(bpy.data.objects)
    bpy.ops.allset.shelf_select(shelf="Sculpting")
    redraw()
    bpy.ops.allset.create(kind='SPHERE')
    _cur, buttons = shelf.icon_buttons(bpy.context)
    x, y = icon_centre(next(k for k, b in enumerate(buttons) if b[1] == "Grab Tool"))
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_sculpt_hover():
    redraw()
    ev('LEFTMOUSE', 'PRESS')
    ev('LEFTMOUSE', 'RELEASE')


for _k in range(8):      # the first brush use loads the essentials asset library in the background
    step(lambda: None)


@step
def s_sculpt_check():
    brush = bpy.context.tool_settings.sculpt.brush
    check(f"Sculpting Grab Tool icon -> Sculpt mode, Grab brush ({bpy.context.mode}, "
          f"{brush.name if brush else None})", bpy.context.mode == 'SCULPT' and brush and brush.name == "Grab")
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step109_sculpt_grab.png"))
        with open(os.path.join(SHOTS, "gui_step109_rects.json"), "w", encoding="utf-8") as fh:
            json.dump({"scale": scale(), "window": [win().width, win().height], "rects": C["rects"]}, fh)


run()
