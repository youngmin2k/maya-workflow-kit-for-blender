"""In a real UI: the Maya strip (Status Line + Shelf) of the Maya Workflow Kit layout,
tab switching, UI Elements > Shelf toggle in the factory layout; screenshots."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def regions(area):
    return {r.type: r for r in area.regions}


@step
def s_setup():
    setup()
    C["shelf"] = import_module(MODULE + ".ui.shelf")
    load_maya_layout()


@step
def s_loaded():
    bpy.ops.allset.keymap_activate()
    redraw()


@step
def s_strip():
    scr = win().screen
    strip = C["shelf"].strip_area(scr)
    check("Maya Workflow Kit layout has the Maya strip", strip is not None)
    if strip is None:
        return
    area3d = max((a for a in scr.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    rg = regions(strip)
    check(f"strip sits above the 3D View (strip y {strip.y}, 3D View top {area3d.y + area3d.height})",
          strip.y >= area3d.y + area3d.height - 2)
    # the template's Shelf is its own header-only row under the Status Line
    # (the shelf row has no header — tab strip + icons in its WINDOW region)
    row = C["shelf"].shelf_row_area(scr)
    shelf_h = regions(row)['WINDOW'].height if row else 0
    check(f"Status Line row and Shelf row both shown ({rg['HEADER'].height}, {shelf_h})",
          rg['HEADER'].height > 20 and shelf_h > 20 and row.y < strip.y)
    outliner = next(a for a in scr.areas if a.type == 'OUTLINER' and a.x < area3d.x)
    check("strip spans the Outliner and the viewport", strip.x <= outliner.x + 2
          and strip.x + strip.width >= area3d.x + area3d.width - 2)
    C["strip"] = strip


@step
def s_shot():
    shot("gui_step12_strip_poly.png")
    bpy.ops.allset.shelf_select(shelf="Rigging")
    redraw()


@step
def s_wait():
    pass


@step
def s_rigging_shot():
    shot("gui_step12_strip_rigging.png")
    bpy.ops.allset.shelf_select(shelf="Polygons")
    # Factory layout: UI Elements > Shelf adds the strip over the largest 3D View.
    bpy.ops.wm.read_homefile(app_template="")


@step
def s_factory():
    setup_view = view3d()[0]
    with bpy.context.temp_override(window=win(), screen=win().screen, area=setup_view):
        res = bpy.ops.allset.shelf_strip_toggle()
    check("Shelf toggle adds the strip in another layout", res == {'FINISHED'}
          and C["shelf"].strip_area(win().screen) is not None)
    redraw()


@step
def s_factory_wait():
    strip = C["shelf"].strip_area(win().screen)
    rg = regions(strip) if strip else {}
    check("added strip shows both rows", bool(rg) and rg['TOOL_HEADER'].height > 20)


@step
def s_factory_shot():
    shot("gui_step12_strip_factory.png")
    strip = C["shelf"].strip_area(win().screen)
    with bpy.context.temp_override(window=win(), screen=win().screen, area=strip):
        bpy.ops.allset.shelf_strip_toggle()


@step
def s_removed():
    check("Shelf toggle again removes the strip", C["shelf"].strip_area(win().screen) is None)


run()
