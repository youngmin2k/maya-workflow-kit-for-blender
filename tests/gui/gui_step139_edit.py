"""In a real UI: the Maya menu items Edit Mesh > Connect / Merge / Symmetrize and Mesh > Smooth run in
component mode through allset.menu_item (the kit menus' own operator) give Maya's counts;
Symmetrize waits for an edge click (Esc leaves the mesh alone, a click on the
seam edge mirrors the selected side)."""

import os
import sys

import bmesh
import bpy
from bpy_extras import view3d_utils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def ob():
    return bpy.data.objects["Cube"]


def ctx():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def counts():
    if bpy.context.mode == 'EDIT_MESH':
        bm = bmesh.from_edit_mesh(ob().data)
        return (len(bm.verts), len(bm.edges), len(bm.faces))
    me = ob().data
    return (len(me.vertices), len(me.edges), len(me.polygons))


def fresh(sym=False):
    """Object mode, the Cube = a 1 x 1 x 1 cube (Maya polyCube); ``sym`` = polyCube -sx 2 with the +X side moved."""
    with ctx():
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    if sym:
        edges = [e for e in bm.edges if abs(e.verts[0].co.x - e.verts[1].co.x) > .5]
        bmesh.ops.subdivide_edges(bm, edges=edges, cuts=1, use_grid_fill=True)
        for v in bm.verts:
            if v.co.x > .4:
                v.co.x += .3
                if v.co.z > 0:
                    v.co.z += .2
    bm.to_mesh(ob().data)
    bm.free()
    ob().data.update()
    ob().location = (0, 0, 0)
    ob().rotation_euler = (0, 0, 0)
    ob().scale = (1, 1, 1)


def edit(mode, pick):
    with ctx():
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type=mode)
        bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(ob().data)
    for el in pick(bm):
        el.select = True
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob().data)


def menu(path):
    with ctx():
        return bpy.ops.allset.menu_item('INVOKE_DEFAULT', item=path)


def top_face(bm):
    return max(bm.faces, key=lambda f: f.calc_center_median().z)


@step
def s_setup():
    setup()
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob().select_set(True)
    bpy.context.view_layer.objects.active = ob()


@step
def s_connect():
    fresh()

    def pick(bm):
        f = top_face(bm)
        es = [lp.edge for lp in f.loops]
        return [es[0], es[2]]
    edit('EDGE', pick)
    menu("Edit Mesh/Connect")
    check(f"Edit Mesh > Connect, two opposite edges: Maya 10/15/7 ({counts()})", counts() == (10, 15, 7))


@step
def s_merge():
    fresh()

    def pick(bm):
        bm.verts.ensure_lookup_table()
        v = bm.verts[0]
        return [v, v.link_edges[0].other_vert(v)]
    edit('VERT', pick)
    menu("Edit Mesh/Merge")
    check(f"Edit Mesh > Merge, two neighbour vertices (always merge two): Maya 7/11/6 ({counts()})",
          counts() == (7, 11, 6))


@step
def s_smooth_faces():
    fresh()
    edit('FACE', lambda bm: [top_face(bm)])
    menu("Mesh/Smooth")
    check(f"Mesh > Smooth, one face: Maya 13/20/9 ({counts()})", counts() == (13, 20, 9))


@step
def s_smooth_object():
    fresh()
    menu("Mesh/Smooth")
    check(f"Mesh > Smooth, object mode: Maya 26/48/24, no modifier ({counts()}, {[m.type for m in ob().modifiers]})",
          counts() == (26, 48, 24) and not ob().modifiers)


def positions():
    bm = bmesh.from_edit_mesh(ob().data)
    return sorted(tuple(round(c, 4) for c in v.co) for v in bm.verts)


@step
def s_sym_enter():
    fresh(sym=True)
    edit('VERT', lambda bm: [v for v in bm.verts if v.co.x < -.1])
    C["before"] = positions()
    C["res"] = menu("Edit Mesh/Symmetrize")


@step
def s_sym_waiting():
    ops = [o.bl_idname for o in win().modal_operators]
    check(f"Symmetrize waits for an edge click, mesh unchanged ({C['res']}, {ops})",
          "ALLSET_OT_symmetrize" in ops and positions() == C["before"])
    area, region = view3d()
    x, y = region.x + region.width // 2, region.y + region.height // 2
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('ESC', 'PRESS', x=x, y=y)
    ev('ESC', 'RELEASE', x=x, y=y)


@step
def s_sym_cancelled():
    ops = [o.bl_idname for o in win().modal_operators]
    check(f"Esc leaves the pick tool and the mesh alone ({ops})",
          "ALLSET_OT_symmetrize" not in ops and positions() == C["before"])
    C["res"] = menu("Edit Mesh/Symmetrize")


@step
def s_sym_click():
    bm = bmesh.from_edit_mesh(ob().data)
    seam = next(e for e in bm.edges if all(abs(v.co.x) < 1e-6 and v.co.z > .4 for v in e.verts))
    mid = ob().matrix_world @ ((seam.verts[0].co + seam.verts[1].co) / 2)
    area, region = view3d()
    p = view3d_utils.location_3d_to_region_2d(region, area.spaces.active.region_3d, mid)
    x, y = region.x + int(p.x), region.y + int(p.y)
    C["click"] = (x, y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


@step
def s_sym_result():
    x, y = C["click"]
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)
    plus = sorted(p for p in positions() if p[0] > .1)
    want = sorted((.5, y, z) for y in (-.5, .5) for z in (-.5, .5))
    check(f"a click on the seam edge mirrors the selected -X side onto +X (Maya topo_minus: {plus})", plus == want)
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step139_symmetrize.png"))


run()
