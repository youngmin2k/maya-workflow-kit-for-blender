"""In a real UI: Maya shelf row (tabs + 32 px kit icons as gizmos: click = command, second click =
options), shelf tab switch, Maya menu option box; screenshots."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, scale, step, setup, screenshot, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
shelf = import_module(MODULE + ".ui.shelf")


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


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


def slot_of(label):
    _cur, buttons = shelf.icon_buttons(bpy.context)
    return next(k for k, b in enumerate(buttons) if b[1] == label)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    bpy.ops.allset.shelf_select(shelf="Polygons")
    redraw()


@step
def s_rows():
    area = shelf_area()
    regions = {r.type: r for r in area.regions}
    win_r = regions['WINDOW']
    _x, _y, size = shelf.icon_rect(win_r, 0, scale())
    if abs(scale() - 1.0) < 0.01:   # the Maya density: the template's sizes are Maya pixels
        check(f"Shelf row = tab row + icon row ({area.height} px; Maya 64)", abs(area.height - 64) <= 2)
        check(f"icons {size:.0f} px (Maya 32)", abs(size - 32) < 0.5)
    else:   # other scales: the row is resized when Blender lets the kit move the edge (best effort)
        check(f"Shelf row shows tabs and icons at scale {scale():.2f} ({area.height} px, icons {size:.0f})",
              not area.spaces.active.show_region_header and size >= 16)
    C["n0"] = len(bpy.data.objects)
    x, y = icon_centre(slot_of("Polygon Cube"))
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_hover():
    redraw()


@step
def s_click():
    shot("gui_step51_shelf_hover.png")
    ev('LEFTMOUSE', 'PRESS')
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_clicked():
    names = [o.name for o in bpy.data.objects]
    check(f"Polygon Cube icon creates pCube1 ({names})", "pCube1" in names)


@step
def s_tab():
    # switch shelves with the tab row: Rigging
    bpy.ops.allset.shelf_select(shelf="Rigging")
    redraw()


@step
def s_tab_check():
    _cur, buttons = shelf.icon_buttons(bpy.context)
    check(f"Rigging shelf icons ({len(buttons)})", buttons and buttons[0][1] == "Create Locator")
    shot("gui_step51_rigging.png")
    bpy.ops.allset.shelf_select(shelf="Polygons")
    redraw()


@step
def s_menu_hover():
    # Create in the menu bar (x 121, y 13 from the top at effective scale 1.0): hover, then click
    C["create"] = (round(121 * scale()), win().height - round(13 * scale()))
    ev('MOUSEMOVE', 'NOTHING', x=C["create"][0], y=C["create"][1])


@step
def s_menu():
    ev('LEFTMOUSE', 'PRESS')
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_menu_shot():
    shot("gui_step51_create_menu.png")
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


status_line = import_module(MODULE + ".ui.status_line")


def file_handle():
    # the File group's collapse arrow (after the menu set combo and the five file / undo icons;
    # at x 296 in a scale 1.25 shot of the Maya Workflow Kit layout)
    strip = next(a for a in win().screen.areas if a.type == 'IMAGE_EDITOR' and shelf.is_strip(a.spaces.active))
    hdr = next(r for r in strip.regions if r.type == 'HEADER')
    return hdr.x + round(237 * scale()), hdr.y + hdr.height // 2


@step
def s_handle_hover():
    x, y = file_handle()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y + 40)   # leave the menu bar first
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_handle_click():
    ev('LEFTMOUSE', 'PRESS')
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_handle_check():
    check(f"Status Line File handle hides the group ({sorted(status_line._collapsed)})",
          status_line._collapsed == {"FILE"} | set(status_line.DEFAULT_COLLAPSED))
    shot("gui_step51_status_collapsed.png")
    # Maya: a collapsed group keeps only its bar and a filled arrow, right after the menu set combo (x 166 at 1.25)
    x, y = file_handle()
    C["again"] = (x - round(237 * scale()) + round(133 * scale()), y)
    ev('MOUSEMOVE', 'NOTHING', x=C["again"][0], y=y)


@step
def s_handle_click_again():   # hover in one tick, press in the next
    x, y = C["again"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_handle_again():
    check("... and its arrow shows it again", status_line._collapsed == set(status_line.DEFAULT_COLLAPSED))


run()
