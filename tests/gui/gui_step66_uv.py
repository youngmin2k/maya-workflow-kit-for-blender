"""In a real UI (Maya UV workflow): cube -> UV > UV Editor -> a UV Editor window, edit mode,
UV Sync Selection, the UVs drawn -> the top face's edges selected -> Shift+X (Cut) -> two shells -> Ctrl+U (Unfold) ->
Ctrl+L (Layout) -> inside 0-1, no overlap -> RMB marking menu NW = UV Shell -> island mode; UV Toolkit tab (screenshots)."""

import os
import sys
from importlib import import_module

import bmesh
import bpy
from mathutils import geometry

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
DRAG = 120


def mod(name):
    return import_module(sys.modules["sim"].MODULE + name)


def cube():
    return bpy.data.objects["Cube"]


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
    w, _a, r = uv_window()
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


def bm():
    return bmesh.from_edit_mesh(cube().data)


def shells():
    b = bm()
    C["bm"] = b        # keep the wrapper alive: its faces die with it
    uv = b.loops.layers.uv.active
    return mod(".operators.uv_tools").islands(b, uv), uv


def overlapping(isls, uv):
    tris = []
    for i, isl in enumerate(isls):
        for f in isl:
            p = [l[uv].uv.copy() for l in f.loops]
            for k in range(1, len(p) - 1):
                tris.append((i, (p[0], p[k], p[k + 1])))
    for a in range(len(tris)):
        for b in range(a + 1, len(tris)):
            if tris[a][0] != tris[b][0] and geometry.intersect_tri_tri_2d(*tris[a][1], *tris[b][1]):
                return True
    return False


@step
def s_setup():
    C["x"], C["y"] = setup()
    bpy.context.view_layer.objects.active = cube()
    cube().select_set(True)
    area, region = view3d()
    menu_map = mod(".ui.menu_map")
    modal = mod(".marking.modal")
    with bpy.context.temp_override(window=win(), area=area, region=region):
        C["open"] = modal.run_action(bpy.context, menu_map.MAP["UV/UV Editor"])


@step
def s_wait_uv_window():
    # the window opens a few ticks later when it has a remembered place (window places)
    import sim
    C.setdefault("wait_uv", 0)
    if uv_window()[1] is None and C["wait_uv"] < 15:
        C["wait_uv"] += 1
        sim._steps.insert(0, s_wait_uv_window)


@step
def s_opened():
    w, a, r = uv_window()
    ts = bpy.context.scene.tool_settings
    check(f"UV > UV Editor: a UV Editor window, cube in edit mode, UV Sync Selection (got {C['open']}, "
          f"{a is not None}, {cube().mode}, {ts.use_uv_select_sync})",
          a is not None and cube().mode == 'EDIT' and ts.use_uv_select_sync)
    if a is None:
        return
    C["uvpos"] = centre()
    with bpy.context.temp_override(window=w, area=a, region=r):
        bpy.ops.image.view_all(fit_view=True)
    b = bm()
    for el in (*b.verts, *b.edges, *b.faces):
        el.select = False
    for e in b.edges:          # the top face's border: cuts it out of the cube's cross of UVs
        e.select = all(v.co.z > 0.5 for v in e.verts)
    for v in b.verts:
        v.select = any(e.select for e in v.link_edges)
    bpy.context.scene.tool_settings.mesh_select_mode = (False, True, False)
    bmesh.update_edit_mesh(cube().data)
    C["shells0"] = len(shells()[0])
    redraw_all()


@step
def s_shot_open():
    w, _a, _r = uv_window()
    shot("gui_step66_uv_editor.png", w)
    uv_ev('MOUSEMOVE', 'NOTHING', *centre())
    uv_ev('X', 'PRESS', shift=True)
    uv_ev('X', 'RELEASE', shift=True)


@step
def s_cut():
    isls, _uv = shells()
    seams = sum(e.seam for e in bm().edges)
    check(f"Shift+X in the UV Editor = Cut: 4 seams, {C['shells0']} -> {len(isls)} shells", seams == 4 and len(isls) == C["shells0"] + 1)
    uv_ev('U', 'PRESS', ctrl=True)
    uv_ev('U', 'RELEASE', ctrl=True)


@step
def s_unfold():
    isls, uv = shells()
    check(f"Ctrl+U = Unfold: shells kept ({len(isls)})", len(isls) == C["shells0"] + 1)
    b = bm()
    for el in (*b.verts, *b.edges, *b.faces):
        el.select = False
    bmesh.update_edit_mesh(cube().data)
    uv_ev('L', 'PRESS', ctrl=True)
    uv_ev('L', 'RELEASE', ctrl=True)


@step
def s_layout():
    isls, uv = shells()
    us = [l[uv].uv for isl in isls for f in isl for l in f.loops]
    inside = all(-1e-5 <= u.x <= 1 + 1e-5 and -1e-5 <= u.y <= 1 + 1e-5 for u in us)
    check(f"Ctrl+L = Layout: every UV inside 0-1, no overlapping shells ({len(isls)} shells)",
          inside and not overlapping(isls, uv))
    redraw_all()


@step
def s_shot_layout():
    w, _a, _r = uv_window()
    shot("gui_step66_layout.png", w)
    x, y = centre()
    C["c"] = (x, y)
    uv_ev('MOUSEMOVE', 'NOTHING', x, y)
    uv_ev('RIGHTMOUSE', 'PRESS', x, y)


@step
def s_rmb_open():
    w, _a, _r = uv_window()
    shot("gui_step66_rmb.png", w)
    x, y = C["c"]
    uv_ev('MOUSEMOVE', 'NOTHING', x - DRAG // 2, y + DRAG // 2)
    uv_ev('MOUSEMOVE', 'NOTHING', x - DRAG, y + DRAG)


@step
def s_rmb_release():
    x, y = C["c"]
    uv_ev('RIGHTMOUSE', 'RELEASE', x - DRAG, y + DRAG)


@step
def s_shell_mode():
    ts = bpy.context.scene.tool_settings
    # UV Shell = Maya's UV Shell mask (one selection with the 3D View: sync on, face mode)
    check(f"UV Editor RMB NW = UV Shell mask (sync {ts.use_uv_select_sync}, {tuple(ts.mesh_select_mode)})",
          bpy.context.window_manager.allset_uv_shell_mask and ts.use_uv_select_sync
          and tuple(ts.mesh_select_mode) == (False, False, True))
    _w, a, _r = uv_window()
    a.spaces.active.show_region_ui = True
    redraw_all()


@step
def s_tabs():
    """Ctrl+wheel over the sidebar until its UV Toolkit tab is on (the tab can't be set from Python)."""
    _w, a, _r = uv_window()
    ui = next(r for r in a.regions if r.type == 'UI')
    C.setdefault("tries", 0)
    if ui.active_panel_category != "UV Toolkit" and C["tries"] < 10:
        C["tries"] += 1
        uv_ev('MOUSEMOVE', 'NOTHING', ui.x + ui.width - 10, ui.y + ui.height - 60)
        uv_ev('WHEELDOWNMOUSE', 'PRESS', ctrl=True)
        redraw_all()
        sys.modules["sim"]._steps.insert(0, s_tabs)
        return
    check(f"UV Editor sidebar on the UV Toolkit tab (got {ui.active_panel_category})",
          ui.active_panel_category == "UV Toolkit")
    redraw_all()


@step
def s_end():
    w, _a, _r = uv_window()
    shot("gui_step66_toolkit.png", w)


run()
