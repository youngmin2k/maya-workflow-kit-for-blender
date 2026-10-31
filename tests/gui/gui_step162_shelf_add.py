"""Ctrl+Shift+click on a Maya menu item adds it to the current shelf.

Ctrl and Shift are held (the add-on reads the OS key state, ``keystate.is_down``, which the simulation replaces) while
Display > Grid is clicked: the item does not run and doesn't open its option box; a "Grid" button is appended to the
Animation shelf after its 15 Maya slots (Poly Modeling has 37). In the Maya layout the shelf
draws it (shot ``162_shelf.png``) and a click on it runs Display > Grid through ``allset.menu_item``. Menu buttons
with a kit picture (Cube: a shelf drawing, Move Tool: a Tool Box glyph) are drawn too (``162_icons.png``). The
sandbox's shelves.json is restored at the end.
"""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402
from sim import (MODULE, check, ev, load_maya_layout, px, run, scale, screenshot, setup, step, tap,  # noqa: E402
                 view3d, win)

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
PATH = "Display/Grid"
C = {"calls": []}


def mod(name):
    return import_module(MODULE + name)


def _spy(cls, tag):
    orig = cls.execute

    def execute(self, context):
        C["calls"].append((tag, getattr(self, "item", "")))
        return orig(self, context)
    cls.execute = execute
    C.setdefault("restore", []).append((cls, orig))


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


@step
def s_setup():
    C["x"], C["y"] = setup()
    bpy.ops.allset.keymap_activate()
    bpy.context.preferences.view.show_tooltips = False
    shelf = mod(".ui.shelf")
    path = shelf.store_path()
    C["backup"] = open(path, encoding="utf-8").read() if os.path.isfile(path) else None
    shelf.reload_user()
    bpy.ops.allset.shelf_select(shelf="Animation")
    C["before"] = list(shelf.icon_buttons(bpy.context)[1])
    ms = mod(".ui.menu_sets")
    _spy(ms.ALLSET_OT_menu_option_box, "box")
    _spy(ms.ALLSET_OT_menu_item, "item")


@step
def s_open():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active):
        bpy.ops.wm.call_menu(name=mod(".ui.menu_sets").menu_idname("mainDisplayMenu"))


@step
def s_hover():
    # Display opens mid-viewport with Grid 34 px above the mouse (gui_step146_option_box.first_row)
    C["row"] = (C["x"], C["y"] + px(9))   # Maya 2026 Display menu
    ev('MOUSEMOVE', 'NOTHING', x=C["row"][0] - 4, y=C["row"][1])


@step
def s_hover2():
    ev('MOUSEMOVE', 'NOTHING', x=C["row"][0], y=C["row"][1])


@step
def s_settle():
    shot("162_menu.png")


@step
def s_click():
    # Ctrl + Shift physically held: only the OS key state (simulated modifier clicks run nothing)
    sim._down.update({'LEFT_CTRL', 'LEFT_SHIFT'})
    del C["calls"][:]
    ev('LEFTMOUSE', 'PRESS', x=C["row"][0], y=C["row"][1])
    ev('LEFTMOUSE', 'RELEASE', x=C["row"][0], y=C["row"][1])


@step
def s_added():
    sim._down.difference_update({'LEFT_CTRL', 'LEFT_SHIFT'})
    shelf = mod(".ui.shelf")
    extras = shelf.factory_extras("Animation") or []
    print("GUI162 calls", C["calls"], "extras", extras, flush=True)
    check(f"Ctrl+Shift+click on Display > Grid: the item ran (no option box) only to add itself ({C['calls']})",
          C["calls"] == [("item", PATH)])
    check(f"a Grid button was added to Animation ({extras})",
          bool(extras) and extras[-1]["menu"] == PATH and extras[-1]["label"] == "Grid")
    after = shelf.icon_buttons(bpy.context)[1]
    check(f"factory slots unchanged, the button after them ({len(C['before'])} -> {len(after)})",
          after[:len(C["before"])] == C["before"] and len(after) == len(C["before"]) + 1)
    on_disk = open(shelf.store_path(), encoding="utf-8").read()
    check("stored in shelves.json", '"Display/Grid"' in on_disk)
    tap('ESC')


@step
def s_layout():
    load_maya_layout()


@step
def s_layout2():
    bpy.ops.allset.keymap_activate()
    bpy.ops.allset.shelf_select(shelf="Animation")
    for a in win().screen.areas:
        a.tag_redraw()
    ev('MOUSEMOVE', 'NOTHING', x=win().width // 2, y=win().height // 2)


@step
def s_hover_icon():
    shelf = mod(".ui.shelf")
    area = shelf.shelf_row_area(win().screen)
    check("the Maya layout has a shelf row", area is not None)
    r = next(r for r in area.regions if r.type == 'WINDOW')
    slot = len(C["before"])
    x, y, size = shelf.icon_rect(r, slot, scale())
    C["icon"] = (round(r.x + x + size / 2), round(r.y + y + size / 2))
    C["shelf_rect"] = (area.x, area.y, area.width, area.height)
    check(f"the added button's slot is inside the shelf row ({x:.0f} + {size:.0f} <= {r.width})", x + size <= r.width)
    ev('MOUSEMOVE', 'NOTHING', x=C["icon"][0], y=C["icon"][1])


@step
def s_shot():
    shot("162_shelf.png")
    del C["calls"][:]


@step
def s_click_icon():
    ev('LEFTMOUSE', 'PRESS', x=C["icon"][0], y=C["icon"][1])
    ev('LEFTMOUSE', 'RELEASE', x=C["icon"][0], y=C["icon"][1])


@step
def s_ran():
    print("GUI162 shelf click calls", C["calls"], "shelf", C["shelf_rect"], "icon", C["icon"], flush=True)
    check(f"a click on the new shelf button runs Display > Grid like the menu ({C['calls']})",
          C["calls"] == [("item", PATH)])
    shot("162_after_click.png")
    shelf = mod(".ui.shelf")
    for path in ("Create/Polygon Primitives/Cube", "Modify/Transformation Tools/Move Tool"):
        shelf.add_menu_item(bpy.context, path)
    ev('MOUSEMOVE', 'NOTHING', x=win().width // 2, y=win().height // 2)


@step
def s_redraw():
    pass             # screen.screenshot shows the previous frame


@step
def s_icons():
    shot("162_icons.png")
    shelf = mod(".ui.shelf")
    textures = shelf.shelf_icons._textures
    check(f"the Cube button uses the Polygon Cube shelf drawing, Move Tool a picture texture ({len(textures)} cached)",
          any(k[:2] == ("Polygon Cube", "Polygons") for k in textures)
          and any(k[0] == "picture" for k in textures))


@step
def s_cleanup():
    for cls, orig in C.get("restore", ()):
        cls.execute = orig
    shelf = mod(".ui.shelf")
    path = shelf.store_path()
    if C["backup"] is None:
        if os.path.isfile(path):
            os.remove(path)
    else:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(C["backup"])
    shelf.reload_user()


run()
