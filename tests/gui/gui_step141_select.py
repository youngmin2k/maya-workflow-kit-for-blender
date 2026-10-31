"""In a real UI: Ctrl+RMB (CTRL_CONVERT) on a cube in component mode runs the new conversions
through marking-menu gestures — vertex mode: Grow Selection > Grow Along Loop (an isolated vertex grows to its three
neighbours); face mode: To Vertices > To Vertex Perimeter (the face's 4 vertices); then the list row To Face Path
(the rings of the touched edges = all 6 faces). Screenshot: gui_step141_convert_menu.png."""

import math
import os
import sys
from importlib import import_module

import bmesh
import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, px, run, setup, screenshot, step, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
DIRS = {"N": (0, 1), "NE": (1, 1), "E": (1, 0), "SE": (1, -1), "S": (0, -1), "SW": (-1, -1), "W": (-1, 0),
        "NW": (-1, 1)}


def draw():
    return import_module(MODULE + ".marking.draw")


def main_view():
    status_line = import_module(MODULE + ".ui.status_line")
    return status_line.main_view3d(win().screen)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def session():
    return draw().ACTIVE.get("session")


def _bm():
    bm = bmesh.from_edit_mesh(bpy.data.objects["pCube1"].data)
    for seq in (bm.verts, bm.edges, bm.faces):
        seq.ensure_lookup_table()
    return bm


def _select(kind, index):
    area, region = main_view()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.mesh.select_mode(type=kind)
        bpy.ops.mesh.select_all(action='DESELECT')
    bm = _bm()
    {'VERT': bm.verts, 'FACE': bm.faces}[kind][index].select_set(True)
    bmesh.update_edit_mesh(bpy.data.objects["pCube1"].data)
    redraw()


def _press():
    bm = _bm()
    print("GUI-DBG press mode", bpy.context.mode, tuple(bpy.context.scene.tool_settings.mesh_select_mode),
          [v.index for v in bm.verts if v.select], [f.index for f in bm.faces if f.select], flush=True)
    _area, region = main_view()
    p = location_3d_to_region_2d(region, region.data, bpy.data.objects["pCube1"].location)
    x, y = region.x + int(p.x), region.y + int(p.y)
    C["origin"] = (x, y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('RIGHTMOUSE', 'PRESS', x=x, y=y, ctrl=True)


def _drag(direction, dist=130):
    """Move from the last point ``dist`` px (scaled) towards a radial direction."""
    x, y = C.get("pos", C["origin"])
    dx, dy = DIRS[direction]
    n = math.hypot(dx, dy)
    x, y = x + int(px(dist) * dx / n), y + int(px(dist) * dy / n)
    C["pos"] = (x, y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y, ctrl=True)


def _release():
    s = session()
    if s is not None:
        print("GUI-DBG release hover", s.hover[0].label if s.hover[0] else None, len(s.stack), flush=True)
    x, y = C.pop("pos", C["origin"])
    ev('RIGHTMOUSE', 'RELEASE', x=x, y=y, ctrl=True)


def _hover_row(label):
    s = session()
    it = next((i for i in s.layout.items if i.kind == "list" and i.label == label), None)
    if it is None:
        return False
    _area, region = main_view()
    x = region.x + int(s.center[0] + (it.rect[0] + it.rect[2]) / 2)
    y = region.y + int(s.center[1] + (it.rect[1] + it.rect[3]) / 2)
    C["pos"] = (x, y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y, ctrl=True)
    return it.enabled


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
        if bpy.context.mode != 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='EDIT')
    _select('VERT', 0)
    bm = _bm()
    C["neighbours"] = {bm.verts[0].index} | {e.other_vert(bm.verts[0]).index for e in bm.verts[0].link_edges}


# --- 1. vertex mode: Grow Selection (NE) > Grow Along Loop (N) ------------------------------------------

@step
def s_grow_press():
    _press()


@step
def s_grow_drag1():
    s = session()
    check("Ctrl+RMB in vertex mode opens the convert menu",
          s is not None and getattr(s.layout.sub, "name", "") == "CTRL_CONVERT")
    _drag("NE")


@step
def s_grow_drag2():
    s = session()
    labels = {d: it.label for d, it in s.layout.radial.items()} if s is not None else {}
    check(f"dragging NE opens Grow Selection ({labels.get('NE')}, {labels.get('N')})",
          labels.get("N") == "Grow Along Loop")
    if s is not None and "N" in s.layout.radial:
        check("Grow Along Loop is enabled", s.layout.radial["N"].enabled)
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step141_convert_menu.png"))
    _drag("N")


@step
def s_grow_release():
    _release()


@step
def s_grow_wait():
    redraw()


@step
def s_grow_result():
    bm = _bm()
    got = {v.index for v in bm.verts if v.select}
    check(f"Grow Along Loop: the isolated vertex grew to its neighbours ({sorted(got)})", got == C["neighbours"])
    check("still vertex mode", tuple(bpy.context.scene.tool_settings.mesh_select_mode) == (True, False, False))
    _select('FACE', 0)
    C["face_verts"] = {v.index for v in _bm().faces[0].verts}


# --- 2. face mode: To Vertices (W) > To Vertex Perimeter (NW) ----------------------------------------------

@step
def s_perim_press():
    _press()


@step
def s_perim_drag1():
    _drag("W")


@step
def s_perim_drag2():
    s = session()
    labels = {d: it.label for d, it in s.layout.radial.items()} if s is not None else {}
    check(f"dragging W opens To Vertices ({labels.get('NW')})", labels.get("NW") == "To Vertex Perimeter")
    _drag("NW")


@step
def s_perim_release():
    _release()


@step
def s_perim_wait():
    redraw()


@step
def s_perim_result():
    bm = _bm()
    got = {v.index for v in bm.verts if v.select}
    check(f"To Vertex Perimeter: the face's 4 vertices ({sorted(got)})", got == C["face_verts"])
    check("vertex mode", tuple(bpy.context.scene.tool_settings.mesh_select_mode) == (True, False, False))


# --- 3. list row To Face Path ---------------------------------------------------------------------------------

@step
def s_path_press():
    _press()


@step
def s_path_hover():
    check("To Face Path row is enabled", _hover_row("To Face Path"))


@step
def s_path_release():
    _release()


@step
def s_path_wait():
    redraw()


@step
def s_path_result():
    bm = _bm()
    n = sum(f.select for f in bm.faces)
    check(f"To Face Path: the rings of the 8 touched edges = all 6 faces ({n})", n == 6)
    check("face mode", tuple(bpy.context.scene.tool_settings.mesh_select_mode) == (False, False, True))
    area, region = main_view()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.object.mode_set(mode='OBJECT')


run()
