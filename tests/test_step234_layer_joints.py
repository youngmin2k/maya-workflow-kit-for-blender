"""Issue #143: animation layers on joints — key, bake, membership.

Expected (chain and bake results):
Create Layer from Selected on a joint, Rotate X +20 at frame 12, S -> Rotate X 20 on every frame (one
key on the layer, BaseAnimation has none); Bake Simulation leaves the pose unchanged (0.0 cm) and keeps the layers.
Audit 0.5.0 ⑤-5 / ⑤-14: S on a layer joint keyed nothing; ⑤-8: the bake doubled the base animation (35.2 cm).
"""

import math
from importlib import import_module

import bpy
from mathutils import Quaternion

import kit

al = import_module(kit.MODULE + ".operators.anim_layers")
bake_maya = import_module(kit.MODULE + ".operators.bake_maya")
cb = import_module(kit.MODULE + ".ui.channel_box")

BONES = (("root", (0, 0, 0), (0, 0, 1)), ("spine", (0, 0, 1), (0, 0, 2)), ("shoulder", (0, 0, 2), (1, 0, 2)),
         ("elbow", (1, 0, 2), (2, 0, 2)), ("wrist", (2, 0, 2), (2.5, 0, 2)))


def _scene(quaternion=False):
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 24
    ls = getattr(sc, "allset_anim_layers", None)
    if ls is not None:
        ls.clear()
    arm = bpy.data.objects.new("skeleton1", bpy.data.armatures.new("skeleton1"))
    sc.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    prev = None
    for name, h, t in BONES:
        eb = arm.data.edit_bones.new(name)
        eb.head, eb.tail = h, t
        if prev is not None:
            eb.parent, eb.use_connect = prev, (prev.tail - eb.head).length < 1e-6
        prev = eb
    bpy.ops.object.mode_set(mode='POSE')
    for pb in arm.pose.bones:
        pb.rotation_mode = 'QUATERNION' if quaternion and pb.name == "shoulder" else 'XYZ'
    el = arm.pose.bones["elbow"]
    for f, deg in ((1, 0.0), (6, -30.0), (12, -60.0), (24, 0.0)):
        el.rotation_euler = (0.0, math.radians(deg), 0.0)
        el.keyframe_insert("rotation_euler", frame=f)
    sh = arm.pose.bones["shoulder"]
    for f, deg in ((1, 0.0), (18, 15.0)):
        if quaternion:
            sh.rotation_quaternion = Quaternion((0, 0, 1), math.radians(deg))
            sh.keyframe_insert("rotation_quaternion", frame=f)
        else:
            sh.rotation_euler = (0.0, 0.0, math.radians(deg))
            sh.keyframe_insert("rotation_euler", frame=f)
    return sc, arm


def _pick(arm, *names):
    for pb in arm.pose.bones:
        cb.set_bone_selected(pb, pb.name in names)
    arm.data.bones.active = arm.data.bones[names[-1]]


def _layer_on_shoulder(sc, arm):
    _pick(arm, "shoulder")
    assert bpy.ops.allset.anim_layer_create(from_selected=True) == {'FINISHED'}
    assert [e.name for e in al.layers(sc)] == [al.BASE, "AnimLayer1"]
    return "AnimLayer1"


def _world(arm):
    return {pb.name: (arm.matrix_world @ pb.head).copy() for pb in arm.pose.bones}


def _sample(sc, arm):
    out = {}
    for f in range(1, 25):
        sc.frame_set(f)
        out[f] = _world(arm)
    return out


def test_layer_members_are_the_selected_joints():
    sc, arm = _scene()
    layer = _layer_on_shoulder(sc, arm)
    assert al.member_bones(arm, layer) == ["shoulder"]
    assert al.is_member(arm, layer, 'pose.bones["shoulder"].rotation_euler', 0)
    assert not al.is_member(arm, layer, 'pose.bones["elbow"].rotation_euler', 1)
    assert cb.channel_state(arm.pose.bones["shoulder"], "rx") == 'LAYERED'    # Maya teal
    assert cb.channel_state(arm.pose.bones["elbow"], "ry") != 'LAYERED'


def test_s_keys_a_joint_on_the_layer_like_maya():
    sc, arm = _scene()
    layer = _layer_on_shoulder(sc, arm)
    sc.frame_set(12)
    sh = arm.pose.bones["shoulder"]
    before = math.degrees(sh.rotation_euler[0])
    sh.rotation_euler[0] = math.radians(before + 20.0)
    assert bpy.ops.allset.set_key() == {'FINISHED'}
    curves = {(fc.data_path, fc.array_index) for fc in al.layer_curves(arm, layer)}
    assert ('pose.bones["shoulder"].rotation_euler', 0) in curves, curves
    for f in (1, 6, 12, 18, 24):                           # Maya: rx 20 on every frame
        sc.frame_set(f)
        assert abs(math.degrees(sh.rotation_euler[0]) - 20.0) < 1e-4, (f, math.degrees(sh.rotation_euler[0]))
    sc.frame_set(18)
    assert abs(math.degrees(sh.rotation_euler[2]) - 15.0) < 1e-4       # the base animation still plays


def test_non_member_joint_keys_on_base_animation():
    sc, arm = _scene()
    layer = _layer_on_shoulder(sc, arm)
    sc.frame_set(9)
    _pick(arm, "elbow")
    el = arm.pose.bones["elbow"]
    el.rotation_euler[1] = math.radians(-10.0)
    assert bpy.ops.allset.set_key() == {'FINISHED'}
    assert not any(al.bone_of(fc.data_path) == "elbow" for fc in al.layer_curves(arm, layer))
    base = al.base_curve(arm, 'pose.bones["elbow"].rotation_euler', 1)
    assert any(abs(kp.co[0] - 9) < 1e-6 for kp in base.keyframe_points)
    sc.frame_set(9)
    assert abs(math.degrees(el.rotation_euler[1]) + 10.0) < 1e-4


def test_quaternion_joint_keys_on_the_layer():
    sc, arm = _scene(quaternion=True)
    layer = _layer_on_shoulder(sc, arm)
    sh = arm.pose.bones["shoulder"]
    sc.frame_set(12)
    target = Quaternion((1, 0, 0), math.radians(20.0)) @ sh.rotation_quaternion.copy()
    sh.rotation_quaternion = target
    assert bpy.ops.allset.set_key() == {'FINISHED'}
    assert sum(1 for fc in al.layer_curves(arm, layer) if fc.data_path.endswith("rotation_quaternion")) == 4
    sc.frame_set(12)
    got = sh.rotation_quaternion.normalized()
    assert got.rotation_difference(target.normalized()).angle < 1e-4, (tuple(got), tuple(target))
    # override layer: the key still makes the result the shown rotation
    e = next(x for x in al.layers(sc) if x.name == layer)
    e.override = True
    al.sync(sc)
    sc.frame_set(6)
    t2 = Quaternion((0, 1, 0), math.radians(35.0))
    sh.rotation_quaternion = t2
    assert bpy.ops.allset.set_key() == {'FINISHED'}
    sc.frame_set(6)
    assert sh.rotation_quaternion.normalized().rotation_difference(t2).angle < 1e-4


def test_bake_with_a_layer_keeps_the_pose_like_maya():
    sc, arm = _scene()
    layer = _layer_on_shoulder(sc, arm)
    sc.frame_set(12)
    sh = arm.pose.bones["shoulder"]
    sh.rotation_euler[0] = math.radians(20.0)
    assert bpy.ops.allset.set_key() == {'FINISHED'}
    pre = _sample(sc, arm)
    names = [pb.name for pb in arm.pose.bones]
    _pick(arm, *names)
    assert bake_maya.bake(bpy.context, bones=list(arm.pose.bones), start=1, end=24) is not None
    post = _sample(sc, arm)
    worst = max((post[f][n] - pre[f][n]).length for f in pre for n in pre[f])
    print(f"step234 bake with a layer: pose change {worst:.2e}")
    assert worst < 1e-4, worst                               # expected 0.0 cm (audit ⑤-8 had 35.2 cm)
    assert layer in al.tracks(arm) and al.BASE in al.tracks(arm)    # the layers stay
    for path, i in (('pose.bones["elbow"].rotation_euler', 1), ('pose.bones["shoulder"].rotation_euler', 0)):
        fc = al.base_curve(arm, path, i)                     # really baked: a key on every frame of BaseAnimation
        assert fc is not None and len(fc.keyframe_points) == 24, (path, fc and len(fc.keyframe_points))
    sc.frame_set(12)
    assert abs(math.degrees(sh.rotation_euler[0]) - 20.0) < 1e-4
    assert abs(math.degrees(arm.pose.bones["elbow"].rotation_euler[1]) + 60.0) < 1e-4    # not -120


def test_quaternion_bake_with_a_layer():
    sc, arm = _scene(quaternion=True)
    _layer_on_shoulder(sc, arm)
    sc.frame_set(12)
    sh = arm.pose.bones["shoulder"]
    sh.rotation_quaternion = Quaternion((1, 0, 0), math.radians(20.0)) @ sh.rotation_quaternion
    assert bpy.ops.allset.set_key() == {'FINISHED'}
    pre = _sample(sc, arm)
    _pick(arm, *[pb.name for pb in arm.pose.bones])
    assert bake_maya.bake(bpy.context, bones=list(arm.pose.bones), start=1, end=24) is not None
    post = _sample(sc, arm)
    worst = max((post[f][n] - pre[f][n]).length for f in pre for n in pre[f])
    assert worst < 1e-4, worst
