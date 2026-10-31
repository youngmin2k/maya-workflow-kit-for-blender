"""#91 #93 #94: selection wire follows deformation per frame, Maya names restart after Delete, Bind Skin =
Maya closest distance.
GUI: tests/gui/gui_step149_wire.py (playback shot)."""

import math
from importlib import import_module

import bpy
from mathutils import Vector

import kit

skin = import_module(kit.MODULE + ".operators.skin")
joints = import_module(kit.MODULE + ".operators.joints")
wire = import_module(kit.MODULE + ".ui.selection_wire")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.armatures):
        for d in list(coll):
            coll.remove(d)
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'METERS', 1.0    # factory m scene: maya_unit() = 1


def _maya_chain():
    """Maya (0,8,0) (0,4,0) (0,0,0) Y-up = Blender (0,0,8) (0,0,4) (0,0,0)."""
    ob = joints.new_skeleton(bpy.context)
    parent = None
    for p in ((0, 0, 8), (0, 0, 4), (0, 0, 0)):
        parent = joints.add_joint(ob, Vector(p), parent, length=0.5)
    joints.finish(bpy.context, ob, ["joint1", "joint2", "joint3"])
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob


def _bind(arm, mesh):
    for o in bpy.context.scene.objects:
        o.select_set(o in (arm, mesh))
    bpy.context.view_layer.objects.active = mesh
    assert bpy.ops.allset.bind_skin() == {'FINISHED'}


# --- #94 Bind Skin --------------------------------------------------------------------------------------------------


def test_94_heat_map_still_available_and_option_window_field():
    _clear()
    arm = _maya_chain()
    bpy.ops.allset.create(kind='CYLINDER')
    cyl = bpy.context.active_object
    cyl.location = (0, 0, 4)
    cyl.scale = (1, 1, 4)
    for o in bpy.context.scene.objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = cyl
    assert bpy.ops.allset.bind_skin(bind_method='HEAT_MAP') == {'FINISHED'}
    assert skin.armature_modifier(cyl) is not None and cyl.parent is None
    ow = import_module(kit.MODULE + ".operators.option_windows_rig")
    spec = next(w for w in ow.WINDOWS if w.key == "bind_skin_maya")
    field = next(f for f in spec.fields if f.name == "bind_method")
    assert field.default == "Closest distance"


# --- #93 names ------------------------------------------------------------------------------------------------------

def test_93_cube_name_restarts_after_delete():
    _clear()
    bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.active_object
    assert (ob.name, ob.data.name) == ("pCube1", "pCubeShape1")
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    bpy.ops.object.delete()
    assert "pCubeShape1" in bpy.data.meshes and bpy.data.meshes["pCubeShape1"].users == 0   # Blender keeps the orphan
    bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.active_object
    assert (ob.name, ob.data.name) == ("pCube1", "pCubeShape1"), (ob.name, ob.data.name)
    # data still used (or kept with a fake user) stays taken
    keep = bpy.data.meshes.new("pCubeShape2")
    keep.use_fake_user = True
    bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.active_object
    assert (ob.name, ob.data.name) == ("pCube3", "pCubeShape3"), (ob.name, ob.data.name)


# --- #91 selection wire ---------------------------------------------------------------------------------------------

def test_91_wire_batch_dropped_on_frame_change_for_deforming_objects():
    _clear()
    arm = _maya_chain()
    bpy.ops.allset.create(kind='CYLINDER')
    cyl = bpy.context.active_object
    cyl.location = (0, 0, 4)
    cyl.scale = (0.5, 0.5, 4.0)
    _bind(arm, cyl)
    bpy.ops.allset.create(kind='CUBE')
    cube = bpy.context.active_object
    assert wire.time_dependent(cyl) and not wire.time_dependent(cube)
    pb = arm.pose.bones["joint2"]
    pb.rotation_mode = 'XYZ'
    scene = bpy.context.scene
    pb.rotation_euler = (0, 0, 0)
    pb.keyframe_insert("rotation_euler", frame=1)
    pb.rotation_euler = (math.radians(45), 0, 0)
    pb.keyframe_insert("rotation_euler", frame=10)
    scene.frame_set(1)
    dg = bpy.context.evaluated_depsgraph_get()
    co1, _ed = wire.edges_of(cyl, dg)
    wire._batches[cyl.session_uid] = (None, 0)
    wire._batches[cube.session_uid] = (None, 0)
    scene.frame_set(10)                       # frame_change_post: the cylinder's batch goes, the cube's stays
    assert cyl.session_uid not in wire._batches
    assert cube.session_uid in wire._batches
    co10, _ed = wire.edges_of(cyl, bpy.context.evaluated_depsgraph_get())
    moved = max((Vector(a) - Vector(b)).length for a, b in zip(co1, co10))
    assert moved > 0.5, moved                 # the bottom ring swings with joint2
    wire._batches.clear()


def test_lattice_gets_the_maya_selection_wire():
    # Maya: displayColor lattice -active 16 (white), lead 19 (green) like meshes
    _clear()
    lat = bpy.data.lattices.new("ffd1LatticeShape")
    lat.points_u, lat.points_v, lat.points_w = 2, 5, 2
    ob = bpy.data.objects.new("ffd1Lattice", lat)
    bpy.context.scene.collection.objects.link(ob)
    co, ed = wire.lattice_edges(lat)
    assert co.shape == (20, 3) and ed.shape == (10 + 16 + 10, 2), (co.shape, ed.shape)
    lengths = {round(float(((co[a] - co[b]) ** 2).sum()) ** 0.5, 4) for a, b in ed}
    assert lengths == {1.0}, lengths     # grid neighbours only (a fresh lattice spaces its points 1 unit apart)
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    assert ob in wire.wire_objects(bpy.context)
