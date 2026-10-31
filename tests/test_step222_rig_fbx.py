"""Issue #132: rig FBX like Maya — joint orient as PreRotation (rotate 0 at rest), joint
translations in cm, no armature Null; the joint world positions the file describes (T . Pre . R . S) equal
Blender's at every frame.
"""

import math
import os
from importlib import import_module

import bpy
from mathutils import Vector

import kit

fbx_rig = import_module(kit.MODULE + ".operators.fbx_rig")
units = import_module(kit.MODULE + ".operators.units")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tmp", "test_step222")

# the spec's rig: root (0,0,0) -> spine (0,5,2) -> head (0,10,0) in Maya cm, Y up
JOINTS = (("root", (0, 0, 0)), ("spine", (0, 5, 2)), ("head", (0, 10, 0)))


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _bl(p, k):
    return Vector((p[0], -p[2], p[1])) * k            # Maya (x, y, z) -> Blender (x, -z, y)


def _rig(control_bone=True):
    _clear()
    scene = bpy.context.scene
    scene.unit_settings.system, scene.unit_settings.length_unit = 'METRIC', 'CENTIMETERS'   # the kit template
    k = units.maya_unit(scene)
    assert abs(k - 0.01) < 1e-9
    arm = bpy.data.armatures.new("skeleton1")
    rig = bpy.data.objects.new("skeleton1", arm)
    scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    prev = None
    for i, (name, p) in enumerate(JOINTS):
        eb = arm.edit_bones.new(name)
        eb.head = _bl(p, k)
        eb.tail = _bl(JOINTS[i + 1][1], k) if i + 1 < len(JOINTS) else _bl(p, k) + Vector((0, 0, 2 * k))
        if prev is not None:
            eb.parent, eb.use_connect = prev, True
        prev = eb
    if control_bone:                              # a kit / Rigify-style control: not a joint in Maya's file
        ctl = arm.edit_bones.new("spine_ctrl")
        ctl.head, ctl.tail = _bl((0, 5, 4), k), _bl((0, 5, 6), k)
        ctl.use_deform = False
    bpy.ops.object.mode_set(mode='POSE')
    for name, frames in (("root", ((1, 0.0), (10, 90.0))), ("spine", ((1, 0.0), (10, -30.0)))):
        pb = rig.pose.bones[name]
        pb.rotation_mode = 'XYZ'
        for f, deg in frames:
            pb.rotation_euler = (math.radians(deg) * 0.3, math.radians(deg), 0.0)
            pb.keyframe_insert("rotation_euler", frame=f)
    bpy.ops.object.mode_set(mode='OBJECT')
    # a mesh skinned to the joints (Armature modifier + vertex groups)
    bpy.ops.mesh.primitive_cylinder_add(radius=1 * k, depth=10 * k, location=_bl((0, 5, 0), k))
    body = bpy.context.active_object
    body.name = "body"
    for name in ("root", "spine", "head"):
        body.vertex_groups.new(name=name)
    for v in body.data.vertices:
        z = (body.matrix_world @ v.co).z / k
        body.vertex_groups["root" if z < 3 else "spine" if z < 7 else "head"].add([v.index], 1.0, 'REPLACE')
    body.modifiers.new("skinCluster1", 'ARMATURE').object = rig
    scene.frame_start, scene.frame_end = 1, 10
    scene.frame_set(5)                            # not the rest frame: the writer's Lcl values are this pose
    return rig, body, k


def _truth(rig, k, frame):
    bpy.context.scene.frame_set(frame)
    out = {}
    for pb in rig.pose.bones:
        p = (rig.matrix_world @ pb.matrix).to_translation() / k
        out[pb.name] = Vector((p.x, p.z, -p.y))       # Blender -> Maya axes, cm
    return out


def _export(path):
    os.makedirs(OUT, exist_ok=True)
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    res = bpy.ops.allset.file_export_all('EXEC_DEFAULT', filepath=path, export_type='FBX')
    assert res == {'FINISHED'}, res
    assert not os.path.exists(os.path.splitext(path)[0] + ".rest_pose.tmp.fbx")


def test_rig_fbx_matches_maya_layout():
    rig, body, k = _rig()
    path = os.path.join(OUT, "rig222.fbx")
    _export(path)
    tree, _v = fbx_rig.load(path)
    index = fbx_rig.Index(tree)
    kinds = [m.props[2] for m in index.models.values()]
    assert b"Null" not in kinds, kinds                                      # no armature Null node
    limbs = {fbx_rig.name_of(m): m for m in index.limbs().values()}
    assert sorted(limbs) == ["head", "root", "spine"], sorted(limbs)          # control bone not written
    # PreRotation = the rest orientation (Maya jointOrient); translations in cm along the joint's X
    spine = limbs["spine"]
    t = fbx_rig.get_vec(spine, b"Lcl Translation")
    assert abs(t.length - math.sqrt(5 ** 2 + 2 ** 2)) < 1e-3 and abs(t.x - t.length) < 1e-3, t   # 5.385 cm on X
    assert fbx_rig.get_vec(spine, b"PreRotation").length > 1.0
    # roots hang from the scene root
    for uid, m in index.limbs().items():
        if fbx_rig.name_of(m) == "root":
            assert index.parent.get(uid) == 0
    # rotate 0 at the rest pose: frame 1 keys (rest pose there) are ~0 for every joint
    for uid, m in index.limbs().items():
        keys = fbx_rig.channel_keys(index, uid, b"Lcl Rotation", fbx_rig.get_vec(m, b"Lcl Rotation"))
        if keys is not None:
            assert keys[1][0].length < 1e-3, (fbx_rig.name_of(m), tuple(keys[1][0]))


def test_world_positions_every_frame_equal_blender():
    rig, body, k = _rig()
    path = os.path.join(OUT, "rig222_world.fbx")
    _export(path)
    index = fbx_rig.Index(fbx_rig.load(path)[0])
    worst = 0.0
    for i, frame in enumerate(range(1, 11)):
        truth = _truth(rig, k, frame)
        got = fbx_rig.world_matrices(index, sample=i)
        for name, w in got.items():
            worst = max(worst, (w.to_translation() - truth[name]).length)
    print(f"step222 max joint world position error {worst:.2e} cm")
    # Blender truth for the cross-check
    import json
    dg = bpy.context.evaluated_depsgraph_get()
    truth = {}
    for frame in range(1, 11):
        joints = {n: list(v) for n, v in _truth(rig, k, frame).items()}
        ev = body.evaluated_get(dg)
        verts = [list(ev.matrix_world @ v.co / k) for v in list(ev.data.vertices)[::8]]
        truth[frame] = {"joints": joints, "verts": [[v[0], v[2], -v[1]] for v in verts]}
    with open(os.path.join(OUT, "rig222_world_truth.json"), "w") as fh:
        json.dump(truth, fh)
    assert worst < 1e-4 * 100, worst            # 1e-4 m = 0.01 cm


def test_skin_clusters_follow_the_fold():
    """Cluster TransformLink = the joint's world matrix without the Null's scale (unit columns)."""
    rig, body, k = _rig()
    path = os.path.join(OUT, "rig222_skin.fbx")
    _export(path)
    index = fbx_rig.Index(fbx_rig.load(path)[0])
    clusters = [d for d in index.objects.find(b"Deformer") if d.props[2] == b"Cluster"]
    assert clusters
    for d in clusters:
        m = fbx_rig._mat(d.first(b"TransformLink").props[0])
        for col in range(3):
            assert abs(m.col[col].to_3d().length - 1.0) < 1e-4, (col, m)


def test_rest_rotations_ignore_the_current_frame():
    """The trap: the PreRotation must not depend on the frame the export ran at."""
    rig, body, k = _rig()
    pres = []
    for frame in (1, 7):
        bpy.context.scene.frame_set(frame)
        path = os.path.join(OUT, f"rig222_f{frame}.fbx")
        _export(path)
        index = fbx_rig.Index(fbx_rig.load(path)[0])
        pres.append({fbx_rig.name_of(m): fbx_rig.get_vec(m, b"PreRotation") for m in index.limbs().values()})
    for name in pres[0]:
        assert (pres[0][name] - pres[1][name]).length < 1e-4, name
