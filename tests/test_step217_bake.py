"""Key > Bake Simulation like Maya's ``bakeResults`` (menu default flags).

Expected results: a constrained box (cases default / dic_off / pok_off / step2)
and an IK chain (Disable implicit control on / off).

Scene = the Maya scene in Blender axes (Maya (x, y, z) -> Blender (x, -z, y), 1 Maya unit = 1 m in this factory
scene): locator ``ctrl`` keyed tx 0 -> 3 and ry 0 -> 350 (linear, frames 1 / 10), cube ``box`` at Maya (0, 5, 2)
parent-constrained to it with offset (Child Of, identity inverse = ctrl at the origin on frame 1), box sx key at 20,
sz keys at 2.5 and 6; Time Slider 1-10. Compared: key frames of every channel, the constraint-driven values (tx, tz,
ry) within 1e-3, world positions before / after / after moving the driver. The sz values between its two keys are
not compared: Maya's and Blender's default tangents differ (not part of the bake).
"""

import math
from importlib import import_module

import bpy
from mathutils import Vector

import kit

ow = import_module(kit.MODULE + ".operators.option_windows")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
cb = import_module(kit.MODULE + ".ui.channel_box")      # bone selection shim (5.x has no Bone.select)
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")

F1_10 = [float(f) for f in range(1, 11)]
# <case>: key frames per Maya channel
MAYA_KEYS = {
    "default": {**{a: F1_10 for a in ("tx", "ty", "tz", "rx", "ry", "rz", "sy", "sz")}, "sx": F1_10 + [20.0]},
    "dic_off": {**{a: F1_10 for a in ("tx", "ty", "tz", "rx", "ry", "rz", "sy", "sz")}, "sx": F1_10 + [20.0]},
    "pok_off": {a: F1_10 for a in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz")},
    "step2": {**{a: [1.0, 3.0, 5.0, 7.0, 9.0] for a in ("tx", "ty", "tz", "rx", "ry", "rz", "sy", "sz")},
              "sx": [1.0, 3.0, 5.0, 7.0, 9.0, 20.0]},
}
# default case: {tx, tz, ry} values (frames 1..10)
MAYA_TX = [0.0, 1.589, 2.6213, 2.7873, 2.161, 1.1678, 0.3958, 0.3348, 1.1598, 2.6527]
MAYA_TZ = [2.0, 1.5567, 0.4234, -0.8976, -1.8207, -1.9368, -1.1943, 0.0776, 1.315, 1.9696]
MAYA_RY = [0.0, 38.8889, 77.7778, 116.6667, 155.5556, 194.4444, 233.3333, 272.2222, 311.1111, 350.0]
# default case: before == baked == after the driver moved (Maya world positions)
MAYA_POS = {1: (0.0, 5.0, 2.0), 5: (2.161, 5.0, -1.8207), 10: (2.6527, 5.0, 1.9696)}
# Maya channel -> (Blender path, index, sign)
CHANNELS = {"tx": ("location", 0, 1), "ty": ("location", 2, 1), "tz": ("location", 1, -1),
            "rx": ("rotation_euler", 0, 1), "ry": ("rotation_euler", 2, 1), "rz": ("rotation_euler", 1, -1),
            "sx": ("scale", 0, 1), "sy": ("scale", 2, 1), "sz": ("scale", 1, 1)}
# IK case: end joint c world position (Maya) before / after; after moving the handle key to tx -3 at 10
IK_C = {1: (0.0, 10.0, 0.0), 10: (2.9304, 9.7679, 0.0)}
IK_C_HANDLE_MOVED_DRIVES = (-2.9304, 9.7679, 0.0)       # joints_dic_off.after_handle_moved


def bl(p):
    return Vector((p[0], -p[2], p[1]))


def _clear():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for data in (bpy.data.actions, bpy.data.armatures):
        for d in list(data):
            data.remove(d)
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end, sc.use_preview_range = 1, 10, False
    us = sc.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'METERS', 1.0


def _key(ob, path, index, frame, value, linear=False):
    getattr(ob, path)[index] = value
    ob.keyframe_insert(path, index=index, frame=frame)
    if linear:
        for fc in kit.fcurves(ob):
            if fc.data_path == path and fc.array_index == index:
                for kp in fc.keyframe_points:
                    kp.interpolation = 'LINEAR'


def _select(*obs):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1]


def _scene():
    _clear()
    sc = bpy.context.scene
    ctrl = bpy.data.objects.new("ctrl", None)
    box = bpy.data.objects.new("box", None)
    for o in (ctrl, box):
        sc.collection.objects.link(o)
    _key(ctrl, "location", 0, 1, 0.0, True)
    _key(ctrl, "location", 0, 10, 3.0, True)
    _key(ctrl, "rotation_euler", 2, 1, 0.0, True)
    _key(ctrl, "rotation_euler", 2, 10, math.radians(350.0), True)
    box.location = bl((0.0, 5.0, 2.0))
    _key(box, "scale", 0, 20, 2.0)          # Maya sx key at 20 (outside the range)
    _key(box, "scale", 1, 2.5, 1.5)         # Maya sz keys at 2.5 / 6 (inside, 2.5 off every sample grid)
    _key(box, "scale", 1, 6, 1.0)
    con = box.constraints.new('CHILD_OF')    # Maya parentConstraint -mo (ctrl at the origin on frame 1)
    con.target = ctrl
    con.inverse_matrix.identity()
    sc.frame_set(1)
    return box, ctrl, con


def _pos(ob, frames):
    sc = bpy.context.scene
    out = {}
    for f in frames:
        sc.frame_set(f)
        out[f] = ob.matrix_world.translation.copy()
    return out


def _curve(ob, path, index):
    for fc in kit.fcurves(ob):
        if fc.data_path == path and fc.array_index == index:
            return fc
    return None


def _check_keys(box, case):
    curves = {(fc.data_path, fc.array_index) for fc in kit.fcurves(box)}
    want = {(p, i) for p, i, _s in CHANNELS.values()}
    assert curves == want, (case, sorted(curves))          # no kit-internal / quaternion curves left
    for attr, frames in MAYA_KEYS[case].items():
        path, index, _sign = CHANNELS[attr]
        got = [round(kp.co.x, 4) for kp in _curve(box, path, index).keyframe_points]
        assert got == frames, (case, attr, got, frames)


def _bake(**kw):
    return bpy.ops.allset.bake_simulation('EXEC_DEFAULT', True, **kw)


def test_bake_default_matches_maya():
    box, ctrl, con = _scene()
    before = _pos(box, (1, 5, 10))
    for f, p in MAYA_POS.items():
        assert (before[f] - bl(p)).length < 1e-3, (f, before[f], p)
    _select(box)
    bpy.context.scene.frame_set(4)
    assert _bake() == {'FINISHED'}
    assert bpy.context.scene.frame_current == 4                # the current time stays
    con = box.constraints.get(con.name)
    assert con is not None and con.mute, "rule 5: the constraint stays and stops driving the box"
    _check_keys(box, "default")
    for attr, maya, scale in (("tx", MAYA_TX, 1.0), ("tz", MAYA_TZ, 1.0), ("ry", MAYA_RY, 180.0 / math.pi)):
        path, index, sign = CHANNELS[attr]
        got = [sign * kp.co.y * scale for kp in _curve(box, path, index).keyframe_points]
        assert all(abs(a - b) < 1e-3 for a, b in zip(got, maya)), (attr, got)
    after = _pos(box, (1, 5, 10))
    for f in (1, 5, 10):
        assert (after[f] - before[f]).length < 1e-3, (f, after[f], before[f])
    # moving the driver no longer moves the baked box (default case, like Maya)
    for kp in _curve(ctrl, "location", 0).keyframe_points:
        if abs(kp.co.x - 10.0) < 1e-6:
            kp.co.y = kp.handle_left.y = kp.handle_right.y = 6.0
    moved = _pos(box, (5, 10))
    for f in (5, 10):
        assert (moved[f] - bl(MAYA_POS[f])).length < 1e-3, (f, moved[f])


def test_disable_implicit_off_still_disconnects_constraints():
    box, ctrl, con = _scene()
    _select(box)
    assert _bake(disable_implicit=False) == {'FINISHED'}
    assert box.constraints[0].mute                       # dic_off: same as default
    _check_keys(box, "dic_off")


def test_keep_unbaked_off_removes_outside_keys_not_constraints():
    box, ctrl, con = _scene()
    _select(box)
    assert _bake(keep_unbaked=False) == {'FINISHED'}
    assert len(box.constraints) == 1 and box.constraints[0].type == 'CHILD_OF', "constraints are never deleted"
    assert box.constraints[0].mute
    _check_keys(box, "pok_off")


def test_sample_by_two():
    box, ctrl, con = _scene()
    _select(box)
    assert _bake(sample_by=2) == {'FINISHED'}
    _check_keys(box, "step2")


def test_one_undo_step():
    box, ctrl, con = _scene()
    _select(box)
    bpy.ops.ed.undo_push(message="before bake")
    assert _bake() == {'FINISHED'}
    assert len(_curve(box, "location", 0).keyframe_points) == 10
    bpy.ops.ed.undo()
    box = bpy.data.objects["box"]
    assert not box.constraints[0].mute
    assert _curve(box, "location", 0) is None
    assert [kp.co.x for kp in _curve(box, "scale", 1).keyframe_points] == [2.5, 6.0]


def test_option_window_and_menu_rows():
    w = ow.find_path("Key/Bake Simulation")
    assert w is not None and w.key == "bake_simulation"
    assert ow.find_path("Edit/Keys/Bake Simulation") is w
    assert w.defaults()["keep_unbaked"] is True and w.defaults()["disable_implicit"] is True
    assert menu_map.MAP["Key/Bake Simulation"] == "allset.bake_simulation"
    assert menu_map.MAP["Edit/Keys/Bake Simulation"] == "allset.bake_simulation"
    assert shelf_map.BY_COMMAND["BakeSimulation"][0] == "allset.bake_simulation"
    box, ctrl, con = _scene()
    _select(box)
    res = ow.run(w, bpy.context, {"keep_unbaked": False})
    assert not isinstance(res, str), res
    assert len(box.constraints) == 1 and box.constraints[0].mute     # the old window deleted the constraint
    _check_keys(box, "pok_off")


# --- IK ------------------------------------------------------------------------------------------------------

def _rig():
    _clear()
    sc = bpy.context.scene
    arm = bpy.data.objects.new("skeleton1", bpy.data.armatures.new("skeleton1"))
    sc.collection.objects.link(arm)
    _select(arm)
    bpy.ops.object.mode_set(mode='EDIT')
    a = arm.data.edit_bones.new("a")
    a.head, a.tail = bl((0, 0, 0)), bl((0, 5, 1))
    b = arm.data.edit_bones.new("b")
    b.head, b.tail = bl((0, 5, 1)), bl((0, 10, 0))
    b.parent, b.use_connect = a, True
    bpy.ops.object.mode_set(mode='OBJECT')
    handle = bpy.data.objects.new("ik1", None)
    sc.collection.objects.link(handle)
    handle.location = bl((0, 10, 0))
    _key(handle, "location", 0, 1, 0.0)
    _key(handle, "location", 0, 10, 3.0)
    con = arm.pose.bones["b"].constraints.new('IK')     # kit IK handle (operators/skin.py create_ik)
    con.target, con.chain_count, con.use_tail = handle, 2, True
    sc.frame_set(1)
    return arm, handle, con


def _c(arm, frames):
    sc = bpy.context.scene
    out = {}
    for f in frames:
        sc.frame_set(f)
        out[f] = arm.matrix_world @ arm.pose.bones["b"].tail
    return out


def _pose_bake(arm, bones, **kw):
    _select(arm)
    bpy.ops.object.mode_set(mode='POSE')
    for pb in arm.pose.bones:
        cb.set_bone_selected(pb, pb.name in bones)
    res = _bake(**kw)
    bpy.ops.object.mode_set(mode='OBJECT')
    return res


def _move_handle(handle):
    for kp in _curve(handle, "location", 0).keyframe_points:
        if abs(kp.co.x - 10.0) < 1e-6:
            kp.co.y = kp.handle_left.y = kp.handle_right.y = -3.0


def test_ik_disable_implicit_on():
    arm, handle, con = _rig()
    before = _c(arm, (1, 10))
    for f, p in IK_C.items():
        assert (before[f] - bl(p)).length < 2e-3, (f, before[f], p)
    assert _pose_bake(arm, {"a", "b"}) == {'FINISHED'}
    con = arm.pose.bones["b"].constraints[0]
    assert con.influence == 0.0 and not con.mute        # Maya ikBlend 0 (joints_dic_on)
    keys = [kp.co.x for kp in _curve(arm, 'pose.bones["a"].rotation_quaternion', 0).keyframe_points]
    assert keys == F1_10, keys                          # joints_dic_on.a_rx_keys
    after = _c(arm, (1, 10))
    for f in (1, 10):
        assert (after[f] - before[f]).length < 1e-3, (f, after[f], before[f])
    _move_handle(handle)
    assert (_c(arm, (10,))[10] - before[10]).length < 1e-3       # joints_dic_on.after_handle_moved


def test_ik_disable_implicit_off_keeps_the_handle_driving():
    arm, handle, con = _rig()
    before = _c(arm, (1, 10))
    assert _pose_bake(arm, {"a", "b"}, disable_implicit=False) == {'FINISHED'}
    assert arm.pose.bones["b"].constraints[0].influence == 1.0   # joints_dic_off.ikBlend 1
    after = _c(arm, (1, 10))
    for f in (1, 10):
        assert (after[f] - before[f]).length < 2e-3, (f, after[f], before[f])
    _move_handle(handle)
    moved = _c(arm, (10,))[10]
    assert (moved - bl(IK_C_HANDLE_MOVED_DRIVES)).length < 2e-3, moved


def test_ik_hierarchy_below_from_the_root_joint():
    arm, handle, con = _rig()
    assert _pose_bake(arm, {"a"}, hierarchy_below=True) == {'FINISHED'}
    assert arm.pose.bones["b"].constraints[0].influence == 0.0
    assert _curve(arm, 'pose.bones["b"].rotation_quaternion', 0) is not None
    assert not cb.bone_selected(arm.pose.bones["b"])          # the temporary selection is put back
