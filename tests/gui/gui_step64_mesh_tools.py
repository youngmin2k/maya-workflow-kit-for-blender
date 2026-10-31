"""In a real UI (Maya modeling workflow): Shift+RMB N = Target Weld Tool ->
F9 vertex mode -> drag a vertex onto its neighbour -> 8 -> 7 vertices at the target; Ctrl+Z; Ctrl+Shift+X Multi-Cut ->
Ctrl+click on an edge -> an edge loop where clicked; Shift+click -> the cut starts at the Snap Step point; Crease
Tool -> MMB drag right -> creased edges, 3 = smooth preview (screenshots)."""

import os
import sys
from importlib import import_module

import bmesh
import bpy
from bpy_extras import view3d_utils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, px, run, screenshot, setup, step, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
DRAG = 120


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def mt():
    return import_module(sys.modules["sim"].MODULE + ".operators.mesh_tools")


def cube():
    return bpy.data.objects["Cube"]


def bm():
    b = bmesh.from_edit_mesh(cube().data)
    b.verts.ensure_lookup_table()
    b.edges.ensure_lookup_table()
    return b


def to_window(co):
    """Window position of an object-space point of the cube."""
    area, region = view3d()
    rv3d = area.spaces.active.region_3d
    p = view3d_utils.location_3d_to_region_2d(region, rv3d, cube().matrix_world @ co)
    return region.x + round(p.x), region.y + round(p.y)


def depth(co):
    area, _region = view3d()
    return -(area.spaces.active.region_3d.view_matrix @ (cube().matrix_world @ co)).z


def tool_id():
    return bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=False).idname


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    C["x"], C["y"] = setup()
    check("Maya keymap active", sys.modules["sim"].maya_keys())
    bpy.context.view_layer.objects.active = cube()
    cube().select_set(True)
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('RIGHTMOUSE', 'PRESS', x=C["x"], y=C["y"], shift=True)


@step
def s_mm_north():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"] + DRAG // 2, shift=True)
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"] + DRAG, shift=True)


@step
def s_mm_release():
    ev('RIGHTMOUSE', 'RELEASE', x=C["x"], y=C["y"] + DRAG, shift=True)


@step
def s_weld_tool():
    check(f"Shift+RMB N (Target Weld Tool) -> edit mode + Target Weld (got {bpy.context.mode}, {tool_id()})",
          bpy.context.mode == 'EDIT_MESH' and tool_id() == "allset.target_weld_tool")
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    tap('F9')


@step
def s_vertex_mode():
    ts = bpy.context.scene.tool_settings
    check(f"F9 = vertex mode (got {tuple(ts.mesh_select_mode)})", tuple(ts.mesh_select_mode) == (True, False, False))
    b = bm()
    for v in b.verts:
        v.select = False
    b.select_flush(False)
    bmesh.update_edit_mesh(cube().data)
    # the vertex nearest to the camera and one of its neighbours (both in front)
    src = min(b.verts, key=lambda v: depth(v.co))
    dst = min((e.other_vert(src) for e in src.link_edges), key=lambda v: depth(v.co))
    C["src"], C["dst"] = src.co.copy(), dst.co.copy()
    C["p0"], C["p1"] = to_window(src.co), to_window(dst.co)
    C["n0"] = len(b.verts)
    ev('MOUSEMOVE', 'NOTHING', x=C["p0"][0], y=C["p0"][1])
    redraw()


@step
def s_press():
    shot("gui_step64_weld_hover.png")
    ev('LEFTMOUSE', 'PRESS', x=C["p0"][0], y=C["p0"][1])


@step
def s_drag():
    (x0, y0), (x1, y1) = C["p0"], C["p1"]
    for i in range(1, 9):
        ev('MOUSEMOVE', 'NOTHING', x=x0 + (x1 - x0) * i // 8, y=y0 + (y1 - y0) * i // 8)


@step
def s_drag_wait():
    redraw()


@step
def s_release():
    shot("gui_step64_weld_drag.png")
    ev('LEFTMOUSE', 'RELEASE', x=C["p1"][0], y=C["p1"][1])


@step
def s_welded():
    b = bm()
    n = len(b.verts)
    at_target = any((v.co - C["dst"]).length < 1e-5 for v in b.verts)
    gone = not any((v.co - C["src"]).length < 1e-5 for v in b.verts)
    check(f"Target Weld drag: {C['n0']} -> {n} vertices, merged at the target", n == C["n0"] - 1 and at_target and gone)
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def s_undone():
    n = len(bm().verts)
    check(f"Ctrl+Z after the weld: back to {n} vertices", n == C["n0"])
    ev('X', 'PRESS', ctrl=True, shift=True)
    ev('X', 'RELEASE', ctrl=True, shift=True)


def _visible_edge():
    """A front edge (both ends near the camera): (edge index, end 0, end 1)."""
    b = bm()
    e = min(b.edges, key=lambda e: depth(e.verts[0].co) + depth(e.verts[1].co))
    return e.index, e.verts[0].co.copy(), e.verts[1].co.copy()


@step
def s_multicut():
    check(f"Ctrl+Shift+X = Multi-Cut (got {tool_id()})", tool_id() == "allset.multi_cut_tool")
    i, a, b = _visible_edge()
    C["edge"] = (a, b)
    C["n1"] = len(bm().verts)
    x, y = to_window(a.lerp(b, 0.3))
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y, ctrl=True)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y, ctrl=True)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y, ctrl=True)


@step
def s_loop():
    b = bm()
    n = len(b.verts)
    a, e1 = C["edge"]
    on_edge = [v for v in b.verts if abs((v.co - a).length + (v.co - e1).length - (a - e1).length) < 1e-4
               and (v.co - a).length > 1e-4 and (v.co - e1).length > 1e-4]
    t = (on_edge[0].co - a).length / (e1 - a).length if on_edge else -1
    check(f"Multi-Cut Ctrl+click on an edge: an edge loop ({C['n1']} -> {n} vertices)", n == C["n1"] + 4)
    check(f"... cut where clicked: {t:.3f} along the edge (clicked 0.3)", abs(t - 0.3) < 0.03)
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def s_snap_press():
    bpy.context.scene.allset_mesh_tools.snap_step = 25
    i, a, b = _visible_edge()
    C["edge"] = (a, b)
    C["n2"] = len(bm().verts)
    x, y = to_window(a.lerp(b, 0.33))      # snaps to 25 %
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y, shift=True)
    ev('LEFT_SHIFT', 'PRESS', x=x, y=y, shift=True)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y, shift=True)


@step
def s_snap_release():
    ev('LEFTMOUSE', 'RELEASE', shift=True)
    ev('LEFT_SHIFT', 'RELEASE')


@step
def s_second_point():
    # a second cut point: the middle of another edge of a face that has the first edge
    b = bm()
    a, e1 = C["edge"]
    first = next(e for e in b.edges if {tuple(v.co) for v in e.verts} == {tuple(a), tuple(e1)})
    face = max(first.link_faces, key=lambda f: -sum(depth(v.co) for v in f.verts))
    other = next(e for e in face.edges if not (set(e.verts) & set(first.verts)))
    x, y = to_window(other.verts[0].co.lerp(other.verts[1].co, 0.5))
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_confirm():
    shot("gui_step64_multicut_snap.png")
    tap('RET')


@step
def s_snapped():
    b = bm()
    a, e1 = C["edge"]
    on_edge = [v for v in b.verts if abs((v.co - a).length + (v.co - e1).length - (a - e1).length) < 1e-4
               and (v.co - a).length > 1e-4 and (v.co - e1).length > 1e-4]
    ts = sorted(round((v.co - a).length / (e1 - a).length, 4) for v in on_edge)
    check(f"Multi-Cut Shift+click: the cut starts on the 25 % Snap Step (got {ts}, {C['n2']} -> {len(b.verts)} vertices)",
          ts == [0.25] or ts == [0.75])
    bpy.context.scene.allset_mesh_tools.snap_step = 10
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def s_crease_setup():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name="allset.crease_tool", space_type='VIEW_3D')
    bpy.context.scene.tool_settings.mesh_select_mode = (False, True, False)
    b = bm()
    for e in b.edges:
        e.select = all(v.co.z > 0.5 for v in e.verts)     # the four top edges
    for v in b.verts:
        v.select = any(e.select for e in v.link_edges)
    bmesh.update_edit_mesh(cube().data)
    C["x0"] = C["x"] - px(100)
    ev('MOUSEMOVE', 'NOTHING', x=C["x0"], y=C["y"])
    ev('MIDDLEMOUSE', 'PRESS', x=C["x0"], y=C["y"])


@step
def s_crease_drag():
    d = round(100 * bpy.context.preferences.system.ui_scale)    # 100 px at UI scale 1 = Maya 2.0
    C["d"] = d
    for i in range(1, 9):
        ev('MOUSEMOVE', 'NOTHING', x=C["x0"] + d * i // 8, y=C["y"])


@step
def s_crease_wait():
    shot("gui_step64_crease_drag.png")


@step
def s_crease_release():
    ev('MIDDLEMOUSE', 'RELEASE', x=C["x0"] + C["d"], y=C["y"])


@step
def s_creased():
    check(f"Crease Tool active (got {tool_id()})", tool_id() == "allset.crease_tool")
    b = bm()
    layer = b.edges.layers.float.get("crease_edge")
    top = [e[layer] for e in b.edges if e.select] if layer else []
    rest = [e[layer] for e in b.edges if not e.select] if layer else []
    want = mt().maya_to_blender_crease(2.0)
    check(f"MMB drag right 100 px = Maya crease 2 on the top edges (Blender {top}, want {want:.3f})",
          len(top) == 4 and all(abs(c - want) < 0.03 for c in top) and not any(rest))
    tap('THREE')


@step
def s_preview():
    redraw()


@step
def s_end():
    shot("gui_step64_crease_preview.png")
    mods = [m.name for m in cube().modifiers]
    check(f"3 = smooth preview with the creases (modifiers {mods})", any("Smooth Preview" in m for m in mods))


run()
