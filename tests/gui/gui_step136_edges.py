"""#56: marking menus opened near every edge of the main viewport stay inside the window and off the area
borders Blender draws after every region. Maya Workflow Kit layout; RMB / Shift+RMB / Ctrl+RMB on pCube1 in object
mode and in vertex / edge / face mode (everything selected), pressed near the top, bottom, left and right edge of the
main 3D View. Each opened menu: every drawn rect (radial boxes, list rows) inside the window, no rect on a horizontal
area-border band, radial boxes on no band, list rows on a vertical border line only in the engine's fallback (more
columns than the free spans hold, tests/test_step136_bounds.py). With ``--shots DIR`` one picture per menu
(``<scale>_<mode>_<button>_<edge>.png``) — run at 1.25 and with ``--ui-scale 0.8`` (1.0)."""

GUI_TIMEOUT = 420

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_location_3d

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, win, load_maya_layout, screenshot, scale, px  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
MODES = ("object", "vertex", "edge", "face")
BUTTONS = (("rmb", {}), ("shift", {"shift": True}), ("ctrl", {"ctrl": True}))
EDGES = ("top", "bottom", "left", "right")
C = {"opened": 0, "problems": []}


def draw():
    return import_module(MODULE + ".marking.draw")


def main_view():
    return import_module(MODULE + ".ui.status_line").main_view3d(win().screen)


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _horizontal(b):
    return b[2] - b[0] >= b[3] - b[1]


def press_point(edge):
    """Region point near ``edge`` of the main view (~40 px in at 1.25)."""
    _area, region = main_view()
    m = px(40)
    return {"top": (region.width // 2, region.height - m), "bottom": (region.width // 2, m),
            "left": (m, region.height // 2), "right": (region.width - m, region.height // 2)}[edge]


def put_object_at(x, y):
    """Move pCube1 so its origin shows at region point (x, y)."""
    ob = bpy.data.objects["pCube1"]
    _area, region = main_view()
    target = location_3d_to_region_2d(region, region.data, ob.matrix_world.translation)
    target.x, target.y = x, y
    ob.location = region_2d_to_location_3d(region, region.data, target, ob.matrix_world.translation)


def set_mode(mode):
    ob = bpy.data.objects["pCube1"]
    area, region = main_view()
    with bpy.context.temp_override(window=win(), area=area, region=region, active_object=ob, object=ob):
        if mode == "object":
            if ob.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            ob.select_set(True)
            bpy.context.view_layer.objects.active = ob
            return
        if ob.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type={"vertex": 'VERT', "edge": 'EDGE', "face": 'FACE'}[mode])
        bpy.ops.mesh.select_all(action='SELECT')


def check_menu(what):
    s = draw().ACTIVE.get("session")
    if s is None:
        C["problems"].append((what, "no menu"))
        return
    C["opened"] += 1
    _area, region = main_view()
    bounds = draw().window_bounds(win(), region)
    bands = draw().window_edges(win(), region)
    for level, (lay, (cx, cy)) in enumerate(s.stack):
        rects = [(it, (it.rect[0] + cx, it.rect[1] + cy, it.rect[2] + cx, it.rect[3] + cy)) for it in lay.items]
        for it, r in rects:
            if not (bounds[0] - 0.5 <= r[0] and r[2] <= bounds[2] + 0.5 and bounds[1] - 0.5 <= r[1]
                    and r[3] <= bounds[3] + 0.5):
                C["problems"].append((what, level, it.label, "outside the window", r))
            for b in bands:
                if _overlap(r, b) and (_horizontal(b) or it.kind == "radial"):
                    C["problems"].append((what, level, it.label, "on an area border", r, b))
        crossed = {round(r[0]) for it, r in rects if it.kind == "list"
                   for b in bands if not _horizontal(b) and _overlap(r, b)}
        columns = {round(r[0]) for it, r in rects if it.kind == "list"}
        if crossed and not (len(columns) >= 3 and len(crossed) == 1):
            C["problems"].append((what, level, "list rows on a vertical border", sorted(crossed)))
        if crossed:
            C.setdefault("vertical", []).append(what)
    radial = {d: it.label for d, it in s.layout.radial.items()}
    rows = [it.label for it in s.layout.items if it.kind == "list"][:3]
    print("GUI-DBG menu", what, radial.get("N"), radial.get("S"), rows)


def make_case(mode, button, mods, edge):
    what = f"{mode}/{button}/{edge}"

    def place():
        set_mode(mode)
        x, y = press_point(edge)
        put_object_at(x, y)
        area, region = main_view()
        area.tag_redraw()
        C["at"] = (region.x + x, region.y + y)
        ev('MOUSEMOVE', 'NOTHING', x=C["at"][0], y=C["at"][1])

    def press():
        x, y = C["at"]
        ev('RIGHTMOUSE', 'PRESS', x=x, y=y, **mods)

    def look():
        check_menu(what)

    def shot():   # one tick later: screen.screenshot shows the previous frame
        if SHOTS and draw().ACTIVE:
            screenshot(os.path.join(SHOTS, f"{scale():.2f}_{mode}_{button}_{edge}.png"))

    def close():
        x, y = C["at"]
        ev('RIGHTMOUSE', 'RELEASE', x=x, y=y, **mods)
        ev('ESC', 'PRESS', x=x, y=y)
        ev('ESC', 'RELEASE', x=x, y=y)

    def closed():
        if draw().ACTIVE:
            C["problems"].append((what, "menu still open"))
            ev('ESC', 'PRESS')
            ev('ESC', 'RELEASE')

    for fn in (place, press, look, shot, close, closed):
        step(fn)


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
    tl = [a for a in win().screen.areas]
    print("GUI-DBG view", region.x, region.y, region.width, region.height, "scale", scale(),
          "areas", [(a.type, a.x, a.y, a.width, a.height) for a in tl])
    print("GUI-DBG bands", draw().window_edges(win(), region))


for _mode in MODES:
    for _button, _mods in BUTTONS:
        for _edge in EDGES:
            make_case(_mode, _button, _mods, _edge)


@step
def s_report():
    n = len(MODES) * len(BUTTONS) * len(EDGES)
    for p in C["problems"]:
        print("GUI-DBG problem", p)
    print("GUI-DBG vertical fallback", C.get("vertical", []))
    check(f"every menu opened ({C['opened']} / {n})", C["opened"] == n)
    check(f"menus inside the window and off the area borders ({len(C['problems'])} problems)", not C["problems"])


run()
