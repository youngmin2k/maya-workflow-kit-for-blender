"""In a real UI (#298): a 4 x 4 grid -> UV > UV Editor -> one edge inside the UV shell selected -> Shift+RMB opens
the UV Editor's UV editing marking menu (edges: the UV menu, ring Snap / Straighten / Optimize / Align / Rotate /
Layout / Unfold / Normalize) -> release on Cut UVs in its list -> the cut edge is drawn as a border at once, though
the shell stays one piece; faces -> Shift+RMB opens the face menu (screenshots)."""

import os
import sys
from importlib import import_module

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, run, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
N = 4


def mod(name):
    return import_module(sys.modules["sim"].MODULE + name)


def grid():
    return bpy.data.objects[C["grid"]]


def uv_window():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.ui_type == 'UV':
                return w, a, next(r for r in a.regions if r.type == 'WINDOW')
    return None, None, None


def shot(name, window=None):
    if SHOTS:
        with bpy.context.temp_override(window=window or win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def uv_ev(type, value, x=None, y=None, **kw):
    """sim.ev for the UV Editor window (keeps sim's simulated key state: the menu engine reads it)."""
    down = sys.modules["sim"]._down
    if value == 'PRESS':
        down.add(type)
    elif value == 'RELEASE':
        down.discard(type)
    w, _a, _r = uv_window()
    if x is None:
        x, y = C["uvpos"]
    C["uvpos"] = (x, y)
    w.event_simulate(type=type, value=value, x=x, y=y, **kw)


def centre():
    _w, _a, r = uv_window()
    return r.x + r.width // 2, r.y + r.height // 2


def redraw_all():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


def session():
    return mod(".marking.draw").ACTIVE.get("session")


def open_menu_name():
    s = session()
    return getattr(s.stack[0][0].sub, "name", None) if s is not None else None


def borders():
    return len(mod(".ui.uv_display").segments_of(grid(), bpy.context.scene.tool_settings.use_uv_select_sync)) // 2


def middle_edge(b):
    for e in b.edges:
        if sorted((round(v.co.x, 3), round(v.co.y, 3)) for v in e.verts) == [(0.0, -0.5), (0.0, 0.0)]:
            return e
    return None


@step
def s_setup():
    C["x"], C["y"] = setup()
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for ob in list(bpy.data.objects):
            ob.select_set(False)
        bpy.ops.mesh.primitive_grid_add(x_subdivisions=N, y_subdivisions=N, size=2.0)
        C["grid"] = bpy.context.active_object.name
        C["open"] = mod(".marking.modal").run_action(bpy.context, mod(".ui.menu_map").MAP["UV/UV Editor"])


@step
def s_wait_uv_window():
    import sim
    C.setdefault("wait_uv", 0)
    if uv_window()[1] is None and C["wait_uv"] < 15:
        C["wait_uv"] += 1
        sim._steps.insert(0, s_wait_uv_window)


@step
def s_opened():
    w, a, r = uv_window()
    ts = bpy.context.scene.tool_settings
    check(f"UV > UV Editor: a UV Editor window, grid in edit mode, UV Sync ({C['open']}, {a is not None}, "
          f"{grid().mode}, {ts.use_uv_select_sync})", a is not None and grid().mode == 'EDIT')
    if a is None:
        return
    with bpy.context.temp_override(window=w, area=a, region=r):
        bpy.ops.image.view_all(fit_view=True)
    ts.use_uv_select_sync = True
    ts.mesh_select_mode = (False, True, False)
    b = bmesh.from_edit_mesh(grid().data)
    for el in (*b.verts, *b.edges, *b.faces):
        el.select = False
    e = middle_edge(b)
    check("an edge inside the grid", e is not None)
    if e is None:
        return
    e.select_set(True)
    bmesh.update_edit_mesh(grid().data)
    C["borders0"] = borders()
    check(f"before the cut only the grid's outline is a border ({C['borders0']})", C["borders0"] == 4 * N)
    C["uvpos"] = centre()
    uv_ev('MOUSEMOVE', 'NOTHING', *centre())
    redraw_all()


@step
def s_press():
    x, y = C["c"] = centre()
    uv_ev('MOUSEMOVE', 'NOTHING', x, y)
    uv_ev('LEFT_SHIFT', 'PRESS', x, y)
    uv_ev('RIGHTMOUSE', 'PRESS', x, y, shift=True)


@step
def s_menu_open():
    name = open_menu_name()
    check(f"Shift+RMB with an edge selected opens the UV menu (got {name})", name == "SHIFT_UV")
    s = session()
    if s is None:
        return
    ring = {k: it.label for k, it in s.layout.radial.items()}
    check(f"ring: N Snap, NE Straighten, E Optimize, SE Align UVs, S Rotate UVs, SW Layout, W Unfold, NW Normalize "
          f"({ring})", ring == {"N": "Snap", "NE": "Straighten", "E": "Optimize", "SE": "Align UVs",
                                "S": "Rotate UVs", "SW": "Layout", "W": "Unfold", "NW": "Normalize"})
    item = next((it for it in s.layout.items if it.label == "Cut UVs"), None)
    check("the list has Cut UVs", item is not None)
    w, _a, _r = uv_window()
    shot("gui_issue298_uv_menu.png", w)
    if item is None:
        return
    box = item.rect
    x = C["c"][0] + int(s.center[0] - s.press[0] + (box[0] + box[2]) / 2)
    y = C["c"][1] + int(s.center[1] - s.press[1] + (box[1] + box[3]) / 2)
    C["release"] = (x, y)
    uv_ev('MOUSEMOVE', 'NOTHING', x, y, shift=True)


@step
def s_release():
    x, y = C["release"]
    uv_ev('RIGHTMOUSE', 'RELEASE', x, y, shift=True)
    uv_ev('LEFT_SHIFT', 'RELEASE', x, y)
    redraw_all()


@step
def s_cut_drawn():
    b = bmesh.from_edit_mesh(grid().data)
    uv = b.loops.layers.uv.active
    e = middle_edge(b)
    n = borders()
    shells = len(mod(".operators.uv_tools").islands(b, uv))
    check(f"Cut UVs ran: the edge is cut ({e is not None and e.seam}), one shell still ({shells})",
          e is not None and e.seam and shells == 1)
    check(f"the cut edge is drawn as a border right away ({C['borders0']} -> {n} sides)", n == C["borders0"] + 2)
    check("menu closed", not mod(".marking.draw").ACTIVE)
    w, _a, _r = uv_window()
    shot("gui_issue298_cut_border.png", w)
    ts = bpy.context.scene.tool_settings
    ts.mesh_select_mode = (False, False, True)
    for f in b.faces:
        f.select_set(True)
    bmesh.update_edit_mesh(grid().data)
    redraw_all()


@step
def s_face_press():
    x, y = C["c"]
    uv_ev('MOUSEMOVE', 'NOTHING', x, y)
    uv_ev('LEFT_SHIFT', 'PRESS', x, y)
    uv_ev('RIGHTMOUSE', 'PRESS', x, y, shift=True)


@step
def s_face_menu():
    name = open_menu_name()
    check(f"Shift+RMB in face mode opens the face menu (got {name})", name == "SHIFT_UV_FACE")
    w, _a, _r = uv_window()
    shot("gui_issue298_face_menu.png", w)
    x, y = C["c"]
    uv_ev('ESC', 'PRESS', x, y)
    uv_ev('ESC', 'RELEASE', x, y)
    uv_ev('RIGHTMOUSE', 'RELEASE', x, y, shift=True)
    uv_ev('LEFT_SHIFT', 'RELEASE', x, y)


@step
def s_end():
    check("menu closed at the end", not mod(".marking.draw").ACTIVE)


run()
