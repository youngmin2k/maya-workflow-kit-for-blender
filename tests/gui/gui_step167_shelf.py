"""In the Maya Workflow Kit layout (1600 px window): the Poly Modeling shelf wraps into a second row at UI
scale 1.25, the wheel over the icons / the scroll bar's arrow shows it (the last button is reachable and runs), and a
double-click on Polygon Cube makes one cube and opens Polygon Cube Options. Shots with ``--shots``."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, scale, screenshot, setup, step, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
shelf = import_module(f"{MODULE}.ui.shelf")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def row_region():
    area = shelf.shelf_row_area(win().screen)
    return next(r for r in area.regions if r.type == 'WINDOW')


def icon_centre(slot):
    r = row_region()
    x, y, size = shelf.icon_rect(r, slot, scale())
    return round(r.x + x + size / 2), round(r.y + y + size / 2)


def shot(name):
    screenshot(os.path.join(SHOTS or bpy.app.tempdir, f"gui_step167_{name}_{scale():.2f}.png".replace(".", "", 1)))


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    cls = import_module(f"{MODULE}.ui.menu_sets").ALLSET_OT_menu_option_box
    orig = cls.execute
    C["calls"] = []

    def execute(self, context):
        C["calls"].append(self.item)
        return orig(self, context)
    cls.execute = execute
    sc = shelf.ALLSET_OT_shelf_scroll
    o_inv = sc.invoke

    def inv(self, context, event):
        res = o_inv(self, context, event)
        print("SCROLL invoke", self.delta, event.type, event.value, res, flush=True)
        return res
    sc.invoke = inv
    bpy.ops.allset.shelf_select(shelf="Polygons")
    shelf._row.clear()
    redraw()


step(redraw)


@step
def s_rows():
    r = row_region()
    rows, first = shelf.rows_of(r, scale())
    _cur, buttons = shelf.icon_buttons(bpy.context)
    C["last"] = len(buttons) - 1
    C["last_label"] = buttons[-1][1]
    x, _y, _s = shelf.icon_rect(r, C["last"], scale())
    check(f"window {win().width} px, UI {scale():.2f}: Poly Modeling has {rows} rows, row {first} shown", rows >= 2)
    check("the last button is not on the shown row", x > r.width)
    check("the scroll bar is drawn", len(shelf.scroll_rects(r, scale())) == 2)
    shot("row0")
    rx, ry = icon_centre(3)
    ev('MOUSEMOVE', 'NOTHING', x=rx, y=ry)


@step
def s_wheel():
    ev('WHEELDOWNMOUSE', 'PRESS')
    redraw()


step(redraw)


@step
def s_after_wheel():
    r = row_region()
    rows, first = shelf.rows_of(r, scale())
    x, _y, _s = shelf.icon_rect(r, C["last"], scale())
    check(f"the wheel over the icons shows the next row (row {first} of {rows})", first == 1)
    check(f"the last button ({C['last_label']}) is now on screen", 0 <= x <= r.width)
    shot("row1")
    C["n"] = len(bpy.data.objects)
    lx, ly = icon_centre(C["last"])
    ev('MOUSEMOVE', 'NOTHING', x=lx, y=ly)


@step
def s_hover_last():
    redraw()
    check("hovering the last button highlights it", shelf._hover.get(row_region().as_pointer()) == C["last"])


@step
def s_up_arrow():
    r = row_region()
    up = shelf.scroll_rects(r, scale())[0]
    x, y = r.x + (up[0] + up[2]) // 2, r.y + (up[1] + up[3]) // 2
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_up_press():
    r = row_region()
    up = shelf.scroll_rects(r, scale())[0]
    x, y = r.x + (up[0] + up[2]) // 2, r.y + (up[1] + up[3]) // 2
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y + 1)       # the gizmo highlight follows this move, then the press
    ev('LEFTMOUSE', 'PRESS', x=x, y=y + 1)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y + 1)


step(redraw)


@step
def s_after_arrow():
    rows, first = shelf.rows_of(row_region(), scale())
    check(f"the scroll bar's up arrow shows row 0 again (row {first})", first == 0)
    shelf._last_click.clear()
    for o in list(bpy.data.objects):
        if o.type == 'MESH':
            bpy.data.objects.remove(o)
    i = next(k for k, b in enumerate(shelf.icon_buttons(bpy.context)[1]) if b[1] == "Polygon Cube")
    C["cube"] = icon_centre(i)
    ev('MOUSEMOVE', 'NOTHING', x=C["cube"][0], y=C["cube"][1])


@step
def s_cube_click1():
    redraw()
    for _k in range(2):        # two clicks in one tick: within the double-click time (Blender: a DOUBLE_CLICK)
        ev('LEFTMOUSE', 'PRESS', x=C["cube"][0], y=C["cube"][1])
        ev('LEFTMOUSE', 'RELEASE', x=C["cube"][0], y=C["cube"][1])


step(redraw)
step(redraw)


@step
def s_dialog():
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    check(f"double-click on Polygon Cube makes one cube ({len(meshes)})", len(meshes) == 1)
    shot("dclick")
    check(f"... and opens Polygon Cube Options ({C['calls']})", C["calls"] == ["Create/Polygon Primitives/Cube"])
    ev('ESC', 'PRESS', x=win().width // 2, y=win().height // 2)
    ev('ESC', 'RELEASE', x=win().width // 2, y=win().height // 2)


run()
