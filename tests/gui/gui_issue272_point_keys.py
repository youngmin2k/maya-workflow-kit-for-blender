"""Issue #272 in a real UI: in the Maya layout, a cube's vertex selected in edit mode, the S key over the viewport
keys that vertex's X / Y / Z at the current frame; after a move at frame 10 and another S, going back to frame 1
puts the vertex back — still in edit mode, like Maya's component keys. A lattice point is keyed the same way."""

import os
import sys
from importlib import import_module

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, tap, view3d, load_maya_layout  # noqa: E402

C = {}


def compat():
    return import_module(MODULE + ".compat")


def curves(idd):
    return sorted((fc.data_path, fc.array_index) for fc in compat().id_fcurves(idd))


def hover():
    _area, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)


def select_only(ob):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_cube():
    bpy.ops.allset.keymap_activate()
    me = bpy.data.meshes.new("pCubeShape1")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("pCube1", me)
    bpy.context.scene.collection.objects.link(ob)
    select_only(ob)
    bpy.context.scene.frame_set(1)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.tool_settings.mesh_select_mode = (True, False, False)
    bm = bmesh.from_edit_mesh(me)
    for v in bm.verts:
        v.select = v.index == 2
    bm.select_flush_mode()
    bm.verts.ensure_lookup_table()
    C["z0"] = bm.verts[2].co.z
    bmesh.update_edit_mesh(me)
    C["ob"] = ob.name
    hover()


@step
def s_key1():
    tap('S')


@step
def s_keyed1():
    ob = bpy.data.objects[C["ob"]]
    got = curves(ob.data)
    check(f"S in vertex mode keys the vertex's X / Y / Z ({got})", got == [("vertices[2].co", a) for a in range(3)])
    check(f"... and stays in edit mode ({bpy.context.mode})", bpy.context.mode == 'EDIT_MESH')
    bpy.context.scene.frame_set(10)
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    bm.verts[2].co.z = C["z0"] + 2.0
    bmesh.update_edit_mesh(ob.data)
    hover()


@step
def s_key2():
    tap('S')


@step
def s_back():
    ob = bpy.data.objects[C["ob"]]
    fc = next(f for f in compat().id_fcurves(ob.data) if f.data_path == "vertices[2].co" and f.array_index == 2)
    check(f"second S keys the moved position ({len(fc.keyframe_points)} keys)", len(fc.keyframe_points) == 2)
    bpy.context.scene.frame_set(1)
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    check(f"frame 1 in edit mode: the vertex is back ({bm.verts[2].co.z:.3f})", abs(bm.verts[2].co.z - C["z0"]) < 1e-4)


@step
def s_lattice():
    bpy.ops.object.mode_set(mode='OBJECT')
    lat = bpy.data.objects.new("ffd1Lattice", bpy.data.lattices.new("ffd1LatticeShape"))
    bpy.context.scene.collection.objects.link(lat)
    select_only(lat)
    bpy.ops.object.mode_set(mode='EDIT')
    for i, p in enumerate(lat.data.points):
        p.select = i == 1
    C["lat"] = lat.name
    hover()


@step
def s_key_lattice():
    tap('S')


@step
def s_lattice_keyed():
    lat = bpy.data.objects[C["lat"]]
    got = curves(lat.data)
    check(f"S on a lattice point keys it ({got})", got == [("points[1].co_deform", a) for a in range(3)])


run()
