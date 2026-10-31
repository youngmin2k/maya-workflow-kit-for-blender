"""Issue #144: kit FBX back into the kit, blend shapes next to other deformers.

Audit 0.5.0 (③-17): File > Import of a file the kit wrote brought the
skinned mesh in at 1/100 size turned 90 deg and the Time Slider at 0-24 instead of the file's 1-20. ④-8: a mesh with a
blend shape and a non-skin deformer (cluster = Hook) lost every blend shape in the FBX (Blender's writer exports the
evaluated mesh when a non-Armature modifier is on: $S/addons_core/io_scene_fbx/export_fbx_bin.py:2645-2657, 2773).
"""

import math
import os
from importlib import import_module

import bpy
from mathutils import Vector

import kit

units = import_module(kit.MODULE + ".operators.units")
fbx_rig = import_module(kit.MODULE + ".operators.fbx_rig")
joints = import_module(kit.MODULE + ".operators.joints")

OUT = os.path.join(os.environ.get("ALLSET_TEST_OUT", bpy.app.tempdir), "step235")


def _bl(p, k):
    return Vector((p[0], -p[2], p[1])) * k


def _clear():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.armatures, bpy.data.actions):
        for d in list(coll):
            coll.remove(d)
    sc = bpy.context.scene
    sc.unit_settings.system, sc.unit_settings.length_unit = 'METRIC', 'CENTIMETERS'
    sc.frame_start, sc.frame_end = 1, 20
    return sc, units.maya_unit(sc)


def _rig():
    sc, k = _clear()
    ob = joints.new_skeleton(bpy.context)
    parent = None
    for p in ((5, 10, 0), (12, 10, -1), (19, 10, 0)):
        parent = joints.add_joint(ob, _bl(p, k), parent, up=Vector((0, 0, 1)), length=2 * k)
    joints.orient_new(ob, ["joint1", "joint2", "joint3"])
    joints.finish(bpy.context, ob, ["joint1", "joint2", "joint3"])
    for f, deg in ((1, 0.0), (10, 40.0), (20, -20.0)):
        pb = ob.pose.bones["joint2"]
        pb.rotation_euler = (0.0, 0.0, math.radians(deg))
        pb.keyframe_insert("rotation_euler", frame=f)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.mesh.primitive_cylinder_add(radius=2 * k, depth=16 * k, location=_bl((12, 10, 0), k),
                                        rotation=(0, math.radians(90), 0))
    body = bpy.context.active_object
    body.name = "pCylinder1"
    for name in ("joint1", "joint2", "joint3"):
        body.vertex_groups.new(name=name)
    for v in body.data.vertices:
        x = (body.matrix_world @ v.co).x / k
        body.vertex_groups["joint1" if x < 12 else "joint2"].add([v.index], 1.0, 'REPLACE')
    body.modifiers.new("skinCluster1", 'ARMATURE').object = ob
    return sc, k, ob, body


def _verts(ob, k):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    return [(ev.matrix_world @ v.co) / k for v in ev.data.vertices]


def _export(path, selection=False):
    os.makedirs(OUT, exist_ok=True)
    op = bpy.ops.allset.file_export_selection if selection else bpy.ops.allset.file_export_all
    assert op('EXEC_DEFAULT', filepath=path, export_type='FBX') == {'FINISHED'}


def test_kit_fbx_back_into_the_kit():
    sc, k, arm, body = _rig()
    truth = {}
    for f in (1, 7, 10, 20):
        sc.frame_set(f)
        truth[f] = (_verts(body, k), {pb.name: (arm.matrix_world @ pb.head) / k for pb in arm.pose.bones})
    path = os.path.join(OUT, "round235.fbx")
    for o in bpy.context.selected_objects:
        o.select_set(False)
    _export(path)
    sc, k = _clear()
    sc.frame_start, sc.frame_end = 0, 250                # the scene's own range before the import
    assert bpy.ops.allset.file_import('EXEC_DEFAULT', filepath=path) == {'FINISHED'}
    rng = (sc.frame_start, sc.frame_end)
    mesh = next(o for o in bpy.data.objects if o.type == 'MESH')
    arm2 = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    worst_v = worst_j = 0.0
    for f, (verts, js) in truth.items():
        sc.frame_set(f)
        got = _verts(mesh, k)
        assert len(got) == len(verts)
        worst_v = max(worst_v, max((a - b).length for a, b in zip(got, verts)))
        for pb in arm2.pose.bones:
            worst_j = max(worst_j, ((arm2.matrix_world @ pb.head) / k - js[pb.name]).length)
    print(f"step235 kit -> FBX -> kit: vertices {worst_v:.2e} cm, joints {worst_j:.2e} cm")
    assert rng == (1, 20), rng                       # the file's range (Maya), not Blender's 0..24 default
    assert worst_j < 1e-3, worst_j
    assert worst_v < 1e-3, worst_v


def _blend_mesh(deformer):
    sc, k = _clear()
    bpy.ops.mesh.primitive_cube_add(size=4 * k)
    ob = bpy.context.active_object
    ob.name = "arm"
    ob.shape_key_add(name="Basis")
    sk = ob.shape_key_add(name="bulge")
    for p in sk.data:
        p.co *= 1.5
    if deformer == 'HOOK':
        e = bpy.data.objects.new("cluster1Handle", None)
        sc.collection.objects.link(e)
        md = ob.modifiers.new("cluster1", 'HOOK')
        md.object = e
        md.vertex_indices_set([0, 1])
    elif deformer == 'LATTICE':
        lat = bpy.data.objects.new("ffd1Lattice", bpy.data.lattices.new("ffd1Lattice"))
        sc.collection.objects.link(lat)
        ob.modifiers.new("ffd1", 'LATTICE').object = lat
    return ob


def _blend_channels(path):
    tree, _v = fbx_rig.load(path)
    objs = tree.first(b"Objects")
    return [fbx_rig.name_of(d) for d in objs.find(b"Deformer") if d.props[2] == b"BlendShapeChannel"]


def test_blend_shapes_survive_a_hook_and_a_lattice():
    for deformer in ('HOOK', 'LATTICE'):
        ob = _blend_mesh(deformer)
        for o in bpy.context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        path = os.path.join(OUT, f"blend235_{deformer.lower()}.fbx")
        _export(path, selection=True)
        chans = _blend_channels(path)
        assert chans == ["bulge"], (deformer, chans)
        assert all(m.show_viewport for m in ob.modifiers), "the deformers come back on"


