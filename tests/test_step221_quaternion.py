"""Issue #131: quaternion bones of a received rig show Maya's Rotate X / Y / Z in the Channel
Box, typed values come back as typed (compat conversion, <= 0.002 deg), S keys the rotation (rotation_quaternion
curves), the Graph Editor names the keyed curves; undo. The rig keeps its QUATERNION mode."""

import math
import random
from importlib import import_module

import addon_utils
import bpy
from mathutils import Euler, Quaternion

import kit

cb = import_module(kit.MODULE + ".ui.channel_box")
rd = import_module(kit.MODULE + ".rotation_display")
time_keys = import_module(kit.MODULE + ".operators.time_keys")
editor_chrome = import_module(kit.MODULE + ".ui.editor_chrome")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    rd.forget()


def _visible(bone):
    return not bone.hide and (not bone.collections or any(c.is_visible_effectively for c in bone.collections))


def _rigify():
    _clear()
    addon_utils.enable("rigify", default_set=True)
    bpy.ops.object.armature_human_metarig_add()
    meta = bpy.context.object
    bpy.ops.pose.rigify_generate()
    rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE' and o is not meta)
    bpy.context.view_layer.objects.active = rig
    for o in bpy.context.selected_objects:
        o.select_set(False)
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='POSE')
    return rig


def _select_only(rig, pb):
    for other in rig.pose.bones:
        cb.set_bone_selected(other, False)
    cb.set_bone_selected(pb, True)
    rig.data.bones.active = pb.bone


def test_pure_round_trip():
    """2000 random typed Euler triples (-360..360) through the quaternion and back: <= 0.005 deg (mathutils is
    float32; 0.002 with another sample — the Channel Box keeps typed values exactly, below)."""
    random.seed(221)
    worst = 0.0
    for _ in range(2000):
        typed = Euler([math.radians(random.uniform(-360, 360)) for _ in range(3)], 'XYZ')
        shown = rd.euler_from(typed.to_quaternion(), typed)
        worst = max(worst, max(abs(a - b) for a, b in zip(shown, typed)))
    assert math.degrees(worst) <= 0.005, math.degrees(worst)
    # a slerped 0 -> 170 deg animation shows no jump (euler_curve, shared with the FBX export step)
    qa, qb = Euler((0, 0, 0)).to_quaternion(), Euler((0, 0, math.radians(170))).to_quaternion()
    curve = rd.euler_curve([qa.slerp(qb, i / 100) for i in range(101)])
    assert max(abs(b.z - a.z) for a, b in zip(curve, curve[1:])) < math.radians(10)
    assert abs(math.degrees(curve[-1].z) - 170) < 1e-3


def test_rigify_channel_box_keys_and_graph_editor():
    try:
        rig = _rigify()
        controls = [pb for pb in rig.pose.bones if _visible(pb.bone)]
        quats = [pb for pb in controls if pb.rotation_mode == 'QUATERNION']
        print(f"step221 rigify: {len(controls)} visible controls, {len(quats)} quaternion")
        assert len(quats) > 100
        # every visible control shows Rotate X / Y / Z (Euler, quaternion and axis-angle alike)
        missing = [pb.name for pb in controls if not all(k in cb._visible_channels(pb) for k in ("rx", "ry", "rz"))
                   and not all(pb.lock_rotation)]
        assert not missing, missing[:10]
        pb = next(p for p in quats if p.name == "chest") if "chest" in rig.pose.bones else quats[0]
        _select_only(rig, pb)
        assert cb.lead() == pb
        # typed values come back exactly; the bone stays quaternion
        for key, deg in (("rx", 30.0), ("ry", 270.0), ("rz", -45.0)):
            cb.set_value(pb, key, math.radians(deg))
        shown = [math.degrees(cb.get_value(pb, k)) for k in ("rx", "ry", "rz")]
        assert max(abs(a - b) for a, b in zip(shown, (30.0, 270.0, -45.0))) <= 0.002, shown
        assert pb.rotation_mode == 'QUATERNION'
        want = Euler([math.radians(d) for d in (30.0, 270.0, -45.0)], 'XYZ').to_quaternion()
        assert abs(abs(Quaternion(pb.rotation_quaternion).dot(want)) - 1.0) < 1e-6     # float32 storage
        # S at frame 1 and frame 10 (another value): rotation_quaternion curves with the right values
        scene = bpy.context.scene
        scene.frame_set(1)
        path = pb.path_from_id("rotation_quaternion")
        # undo: S (the kit operator, one undo step) and Ctrl+Z leave no rotation curves
        rig_name, pb_name = rig.name, pb.name
        bpy.ops.ed.undo_push(message="before keys")
        assert bpy.ops.allset.set_key('EXEC_DEFAULT', True) == {'FINISHED'}
        assert [fc for fc in kit.fcurves(rig) if fc.data_path == path]
        bpy.ops.ed.undo()
        rig = bpy.data.objects[rig_name]
        fcs0 = kit.fcurves(rig)
        assert fcs0 is None or not [fc for fc in fcs0 if fc.data_path == path]
        pb = rig.pose.bones[pb_name]
        scene = bpy.context.scene
        assert time_keys.set_key(bpy.context) > 0
        scene.frame_set(10)
        cb.set_value(pb, "ry", math.radians(90.0))
        q10 = Quaternion(pb.rotation_quaternion)
        time_keys.set_key(bpy.context)
        fcs = [fc for fc in kit.fcurves(rig) if fc.data_path == path]
        assert sorted(fc.array_index for fc in fcs) == [0, 1, 2, 3], [fc.array_index for fc in fcs]
        for fc in fcs:
            assert abs(fc.evaluate(10) - q10[fc.array_index]) < 1e-6
            assert sorted(round(k.co.x) for k in fc.keyframe_points) == [1, 10]
        q1 = Quaternion([fc.evaluate(1) for fc in sorted(fcs, key=lambda f: f.array_index)])
        assert abs(abs(q1.dot(want)) - 1.0) < 1e-6
        # the Channel Box sees the channel as keyed; the Graph Editor names the curves Maya-style
        assert cb.fcurve(pb, "rx") is not None and len(cb.channel_fcurves(pb, "ry")) == 4
        labels = sorted(editor_chrome.attr_label(fc) for fc in fcs)
        assert all(lab.startswith("Rotate") for lab in labels), labels
    finally:
        addon_utils.disable("rigify", default_set=True)


def test_axis_angle_and_object_quaternion():
    _clear()
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    ob.rotation_mode = 'AXIS_ANGLE'
    cb.set_value(ob, "rz", math.radians(120.0))
    assert abs(math.degrees(cb.get_value(ob, "rz")) - 120.0) < 0.002
    assert ob.rotation_mode == 'AXIS_ANGLE' and abs(math.degrees(ob.rotation_axis_angle[0]) - 120.0) < 1e-4
    ob.rotation_mode = 'QUATERNION'
    rd.forget()
    cb.set_value(ob, "rx", math.radians(-200.0))
    assert abs(math.degrees(cb.get_value(ob, "rx")) + 200.0) < 0.002
    assert cb.keyframe(ob, "rx")
    assert sorted(fc.array_index for fc in kit.fcurves(ob) if fc.data_path == "rotation_quaternion") == [0, 1, 2, 3]
