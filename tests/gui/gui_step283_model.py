"""#182: modeling chain as a Maya user in the Maya layout: Create > Cylinder -> Ctrl+E on a side face ->
Ctrl+B on three top rim edges (Maya: 0.2212097 down the sides, 0.1564189 along the unbevelled rim neighbours) ->
Multi-Cut across another side face (Ctrl+Shift+X, two clicks, RMB) -> Edit Mesh > Merge two vertices -> UV > Automatic
-> Edit > Delete by Type > History -> Ctrl+Z -> save / open. Screenshots: gui_step283_bevel.png, gui_step283_end.png."""

import math
import os
import sys
import tempfile
from importlib import import_module

import bmesh
import bpy
from bpy_extras import view3d_utils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, screenshot, setup, step, view3d, win  # noqa: E402

GUI_TIMEOUT = 240
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
PATH = os.path.join(tempfile.mkdtemp(), "model283.blend")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def mod(name):
    return import_module(MODULE + "." + name)


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def centre():
    _a, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)


def key(type, **mods):
    centre()
    ev(type, 'PRESS', **mods)
    ev(type, 'RELEASE', **mods)


def ob():
    return bpy.data.objects[C["ob"]]


def bm():
    b = bmesh.from_edit_mesh(ob().data)
    for seq in (b.verts, b.edges, b.faces):
        seq.ensure_lookup_table()
    return b


def k():
    return mod("operators.units").maya_unit(bpy.context.scene)


def to_window(co):
    area, region = view3d()
    p = view3d_utils.location_3d_to_region_2d(region, area.spaces.active.region_3d, ob().matrix_world @ co)
    return region.x + round(p.x), region.y + round(p.y)


def angle(co):
    return math.degrees(math.atan2(co.y, co.x)) % 360.0


def side_face(deg):
    """The side quad whose centre is nearest the angle ``deg`` around the cylinder's axis."""
    b = C["bm"] = bm()       # keep the wrapper alive while its elements are used
    sides = [f for f in b.faces if abs(f.normal.z) < 1e-3]
    return min(sides, key=lambda f: abs((angle(f.calc_center_median()) - deg + 180.0) % 360.0 - 180.0))


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_cylinder():
    bpy.ops.allset.keymap_activate()
    with override():
        bpy.ops.allset.create(kind='CYLINDER')
        C["ob"] = bpy.context.view_layer.objects.active.name
        if bpy.context.mode != 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='FACE')
    b = bm()
    for f in b.faces:
        f.select_set(False)
    side_face(180.0).select_set(True)          # a side face away from the bevelled rim part
    bmesh.update_edit_mesh(ob().data)
    C["v0"] = len(b.verts)


@step
def s_extrude():
    key('E', ctrl=True)


@step
def s_extruded():
    ex = mod("operators.extrude")
    with override():
        check("Ctrl+E made polyExtrudeFace1", ex.active(bpy.context)[1] is not None)
        ex.set_params(bpy.context, local_translate_z=0.5)
        bpy.ops.mesh.select_mode(type='EDGE')
    b = bm()
    check(f"the extrusion adds 4 vertices ({C['v0']} -> {len(b.verts)})", len(b.verts) == C["v0"] + 4)
    top = max(v.co.z for v in b.verts)
    C["top"] = top
    # three neighbouring rim edges at the +X side (edges e[20:22] of Create > Cylinder)
    rim = [e for e in b.edges if all(abs(v.co.z - top) < 1e-6 and v.co.xy.length > 0.9 * k() for v in e.verts)]
    rim.sort(key=lambda e: (angle((e.verts[0].co + e.verts[1].co) / 2) - 9.0) % 360.0)
    for e in b.edges:
        e.select_set(False)
    for e in rim[:3]:
        e.select_set(True)
    C["ends"] = []
    sel = set(rim[:3])
    for v in {v for e in rim[:3] for v in e.verts}:
        if sum(1 for e in v.link_edges if e in sel) == 1:
            C["ends"].append(v.co.copy())
    bmesh.update_edit_mesh(ob().data)
    centre()


@step
def s_bevel():
    key('B', ctrl=True)


@step
def s_bevelled():
    b = bm()
    kk, top = k(), C["top"]
    drops = [v for v in b.verts if abs(v.co.xy.length - kk) < 1e-5 and abs(top - v.co.z - 0.2212097 * kk) < 1e-5]
    check(f"Ctrl+B on 3 rim edges: 4 new side vertices 0.2212097 down like Maya ({len(drops)})", len(drops) == 4)
    ends = 0
    for p in C["ends"]:
        for v in b.verts:
            d = (v.co - p).length / kk
            if abs(v.co.z - top) < 1e-6 and abs(d - 0.1564189) < 1e-5 and v.co.xy.length > 0.9 * kk:
                ends += 1
    check(f"the unbevelled rim neighbours get their vertex 0.1564189 in, like Maya ({ends} of 2)", ends == 2)
    C["after_bevel"] = len(b.verts)
    shot("gui_step283_bevel.png")


@step
def s_multicut():
    with override():
        bpy.ops.mesh.select_mode(type='VERT')
    face = side_face(270.0)
    e0 = next(e for e in face.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 1e-6)
    e1 = next(e for e in face.edges if e is not e0 and abs(e.verts[0].co.z - e.verts[1].co.z) > 1e-6)
    C["cut"] = [(e.verts[0].co.copy(), e.verts[1].co.copy()) for e in (e0, e1)]
    C["v_cut"] = len(bm().verts)
    key('X', ctrl=True, shift=True)


def _cut_point(i):
    a, b = C["cut"][i]
    return to_window(a.lerp(b, 0.5))


@step
def s_cut1():
    x, y = _cut_point(0)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


@step
def s_cut1_up():
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_cut2():
    x, y = _cut_point(1)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


@step
def s_cut2_up():
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_cut_done():
    ev('RIGHTMOUSE', 'PRESS')
    ev('RIGHTMOUSE', 'RELEASE')


@step
def s_cut_check():
    n = len(bm().verts)
    check(f"Multi-Cut across a side face adds 2 vertices ({C['v_cut']} -> {n})", n == C["v_cut"] + 2)
    key('ESC')


@step
def s_merge():
    b = bm()
    for v in b.verts:
        v.select_set(False)
    a, c = C["cut"][0]
    mid = a.lerp(c, 0.5)
    new = min(b.verts, key=lambda v: (v.co - mid).length)
    other = min((v for v in b.verts if v is not new), key=lambda v: (v.co - new.co).length)
    new.select_set(True)
    other.select_set(True)
    b.select_history.add(other)
    bmesh.update_edit_mesh(ob().data)
    C["v_merge"] = len(b.verts)
    with override():
        res = bpy.ops.allset.menu_item(item="Edit Mesh/Merge")
    check(f"Edit Mesh > Merge two vertices ({res}, {C['v_merge']} -> {len(bm().verts)})",
          res == {'FINISHED'} and len(bm().verts) == C["v_merge"] - 1)


@step
def s_uv():
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')
        res = bpy.ops.allset.menu_item(item="UV/Automatic")
    rec = mod("ui.in_view").cb_record(bpy.context, ob())
    check(f"UV > Automatic (polyAutoProj1: {rec.name if rec else None})", res == {'FINISHED'} and rec is not None)
    C["v_final"] = len(ob().data.vertices)
    bpy.ops.ed.undo_push(message="before history")


@step
def s_history():
    with override():
        res = bpy.ops.allset.menu_item(item="Edit/Delete by Type/History")
    rec = mod("ui.in_view").cb_record(bpy.context, ob())
    check(f"Delete by Type > History removes the history ({res}, record {rec})", res == {'FINISHED'} and rec is None)
    check(f"the mesh stays ({len(ob().data.vertices)} vertices)", len(ob().data.vertices) == C["v_final"])
    key('Z', ctrl=True)


@step
def s_undone():
    rec = mod("ui.in_view").cb_record(bpy.context, ob())
    check(f"Ctrl+Z brings the history back ({rec.name if rec else None})", rec is not None)
    bpy.ops.wm.save_as_mainfile(filepath=PATH)


@step
def s_open():
    bpy.ops.wm.open_mainfile(filepath=PATH)


@step
def s_reopened():
    o = bpy.data.objects.get(C["ob"])
    check(f"reopened: {C['ob']} with {len(o.data.vertices) if o else None} vertices",
          o is not None and len(o.data.vertices) == C["v_final"])
    shot("gui_step283_end.png")


run()
