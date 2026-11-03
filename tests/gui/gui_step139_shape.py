"""In a real UI (#70 M4, #16): component mode, Ctrl+B on an edge -> polyBevel1 exists at once
(no modal), Esc keeps it -> the In-View Editor's Segments row dragged to 2 -> Ctrl+Z = Segments 1, Ctrl+Z = no bevel
(one undo step each) -> Ctrl+E on two edges = polyExtrudeEdge1 at once (12/18/8, Maya) -> Ctrl+E on a vertex =
polyExtrudeVertex1 at once (11/18/9)."""

import os
import sys
from importlib import import_module

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, px, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def mod(name):
    return import_module(sys.modules["sim"].MODULE + name)


def cube():
    return bpy.data.objects["Cube"]


def counts():
    bm = bmesh.from_edit_mesh(cube().data)
    return len(bm.verts), len(bm.edges), len(bm.faces)


def rec():
    return mod(".operators.extrude").active(bpy.context)[1]


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def v3d_ctx():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active)


def in_view_rows():
    area, region = view3d()
    with v3d_ctx():
        _r, lay = mod(".ui.in_view").current_layout(bpy.context)
    if lay is None:
        return None
    return {f: (region.x + round((x0 + x1) / 2), region.y + round((y0 + y1) / 2)) for f, x0, y0, x1, y1 in lay["rows"]}


def select(mode, pick):
    """Select the elements ``pick(bm)`` returns in select mode ``mode`` (VERT / EDGE)."""
    bpy.context.scene.tool_settings.mesh_select_mode = (mode == 'VERT', mode == 'EDGE', False)
    bm = bmesh.from_edit_mesh(cube().data)
    for seq in (bm.faces, bm.edges, bm.verts):
        for el in seq:
            el.select = False
    for el in pick(bm):
        el.select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(cube().data)


def front_edges(bm, n):
    """The front face's horizontal edges (-Y side): bottom first."""
    edges = [e for e in bm.edges if all(v.co.y < -0.9 for v in e.verts) and abs(e.verts[0].co.z - e.verts[1].co.z) < 1e-6]
    return sorted(edges, key=lambda e: e.verts[0].co.z)[:n]


def mouse_mid():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"] - px(200), y=C["y"] - px(150))


def combo(key, **mods):
    ev(key, 'PRESS', **mods)
    ev(key, 'RELEASE', **mods)


# PR #125's always-running window watchers are not a user modal
WATCHERS = {'ALLSET_OT_joint_outliner_select', 'ALLSET_OT_pose_empty_click'}


@step
def s_setup():
    C["x"], C["y"] = setup()
    bpy.context.view_layer.objects.active = cube()
    cube().select_set(True)
    with v3d_ctx():
        bpy.ops.object.mode_set('EXEC_DEFAULT', True, mode='EDIT')     # an undo step, like Tab
    select('EDGE', lambda bm: front_edges(bm, 1))
    C["base"] = counts()
    mouse_mid()
    redraw()


@step
def s_ctrl_b():
    combo('B', ctrl=True)


@step
def s_beveled():
    r = rec()
    mods = [op.bl_idname for op in win().modal_operators
            if op.bl_idname not in WATCHERS]
    check(f"Ctrl+B on an edge = polyBevel1 at once, no modal (got {r and r.name}, {counts()}, modal {mods})",
          r is not None and r.name == "polyBevel1" and counts() == (10, 15, 7) and not mods)
    combo('ESC')


@step
def s_esc_keeps():
    r = rec()
    check(f"Esc keeps the bevel (Maya; got {counts()}, {r and r.name})", counts() == (10, 15, 7) and r is not None)
    with v3d_ctx():
        check("the In-View Editor shows polyBevel1", mod(".ui.in_view").manip_visible(bpy.context))
    redraw()


@step
def s_shot_bevel():
    shot("gui_step139_bevel.png")
    C["rows"] = in_view_rows()
    check(f"In-View rows = Maya polyBevel names ({C['rows'] and list(C['rows'])})",
          C["rows"] is not None and list(C["rows"]) == ["fraction", "offset_as_fraction", "offset", "segments", "depth",
                                                           "chamfer"])
    if C["rows"]:
        x, y = C["rows"]["segments"]
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_press_segments():
    redraw()
    x, y = C["rows"]["segments"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


@step
def s_drag_segments():
    x, y = C["rows"]["segments"]
    d = px(24)                       # 20 px per segment at scale 1
    C["d"] = d
    for i in range(1, 7):
        ev('MOUSEMOVE', 'NOTHING', x=x + d * i // 6, y=y)


@step
def s_release_segments():
    x, y = C["rows"]["segments"]
    ev('LEFTMOUSE', 'RELEASE', x=x + C["d"], y=y)


@step
def s_segments():
    r = rec()
    check(f"In-View Segments drag -> 2: 12/18/8 like Maya seg2 (got {counts()}, {r and r.params.get('segments')})",
          r is not None and r.params["segments"] == 2 and counts() == (12, 18, 8))
    redraw()


@step
def s_shot_segments():
    shot("gui_step139_bevel_seg2.png")
    mouse_mid()
    combo('Z', ctrl=True)


@step
def s_undo_one():
    r = rec()
    check(f"Ctrl+Z: Segments 1 again (one step; got {counts()}, {r and r.params.get('segments')})",
          counts() == (10, 15, 7) and r is not None and r.params["segments"] == 1)
    combo('Z', ctrl=True)


@step
def s_undo_two():
    check(f"Ctrl+Z again: no bevel (the bevel was one step; got {counts()})", counts() == C["base"])
    select('EDGE', lambda bm: front_edges(bm, 2))
    mouse_mid()
    redraw()


@step
def s_ctrl_e_edges():
    combo('E', ctrl=True)


@step
def s_edges_extruded():
    r = rec()
    mods = [op.bl_idname for op in win().modal_operators
            if op.bl_idname not in WATCHERS]
    check(f"Ctrl+E on 2 edges = polyExtrudeEdge1 at once, 12/18/8 (got {r and r.name}, {counts()}, modal {mods})",
          r is not None and r.name == "polyExtrudeEdge1" and counts() == (12, 18, 8) and not mods)
    C["rows"] = in_view_rows()
    check(f"In-View rows = polyExtrudeEdge names ({C['rows'] and list(C['rows'])})",
          C["rows"] is not None and list(C["rows"]) == ["thickness", "local_translate_z", "offset", "divisions"])
    if C["rows"]:
        x, y = C["rows"]["thickness"]
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    redraw()


@step
def s_press_thickness():
    redraw()
    x, y = C["rows"]["thickness"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


@step
def s_drag_thickness():
    x, y = C["rows"]["thickness"]
    d = round(50 * bpy.context.preferences.system.ui_scale)     # 0.01 Maya unit per px at scale 1 -> 0.5
    C["d"] = d
    for i in range(1, 9):
        ev('MOUSEMOVE', 'NOTHING', x=x + d * i // 8, y=y)


@step
def s_release_thickness():
    x, y = C["rows"]["thickness"]
    ev('LEFTMOUSE', 'RELEASE', x=x + C["d"], y=y)


@step
def s_thickness():
    r = rec()
    t = r.params["thickness"] if r else None
    bm = bmesh.from_edit_mesh(cube().data)
    low = min(v.co.y for v in bm.verts)
    check(f"In-View Thickness drag -> about 0.5, edges move out (thickness {t}, min y {low:.3f})",
          r is not None and abs(t - 0.5) < 0.05 and low < -1.2)
    redraw()


@step
def s_shot_edges():
    shot("gui_step139_extrude_edges.png")
    select("VERT", lambda bm: [max(bm.verts, key=lambda v: (v.co.y, v.co.z, -v.co.x))])   # back top left corner
    mouse_mid()
    redraw()


@step
def s_ctrl_e_vertex():
    C["before_v"] = counts()
    combo('E', ctrl=True)


@step
def s_vertex_extruded():
    r = rec()
    nv, ne, nf = C["before_v"]
    check(f"Ctrl+E on a vertex = polyExtrudeVertex1 at once, +3/+6/+3 like Maya 11/18/9 (got {r and r.name}, "
          f"{C['before_v']} -> {counts()})",
          r is not None and r.name == "polyExtrudeVertex1" and counts() == (nv + 3, ne + 6, nf + 3))
    redraw()


@step
def s_end():
    shot("gui_step139_extrude_vertex.png")


run()
