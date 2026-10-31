"""#168: Maya orient / parent constraint Interp Type and aim world up types against the expected
results."""

import math

import bpy
from mathutils import Matrix, Vector

from bl_ext.user_default.allset.operators import constrain_interp as ci
from bl_ext.user_default.allset.operators import constrain_multi as cm
from bl_ext.user_default.allset.operators.joints import MAYA_WORLD as K
from bl_ext.user_default.allset.ui import channel_box as cb

QK = K.to_quaternion()
TOL_KIT = 0.05      # end to end: Blender's float32 transforms (worst 0.04 deg)


def mq(rot, order='XYZ'):
    """Maya q_Euler of a rotate value in degrees (Maya axes)."""
    return ci.euler_quat([math.radians(a) for a in rot], order)


def ang(a, b):
    return math.degrees(2.0 * math.acos(min(1.0, abs(ci.qdot(ci.q_tuple(a), ci.q_tuple(b))))))


def _reset():
    if bpy.context.object is not None and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for arm in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm)


def _node(name, rot=(0, 0, 0), loc=(0, 0, 0), parent=None):
    ob = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(ob)
    if parent is not None:
        ob.parent = parent
        ob.matrix_parent_inverse = Matrix.Identity(4)
    ob.rotation_mode = 'QUATERNION'
    ob.rotation_quaternion = _blender_q(mq(rot))                 # own_maya(ob) == Maya q_Euler(rot), sign kept
    ob.location = K @ Vector(loc)
    return ob


def _blender_q(q_maya):
    qk = ci.q_tuple(QK)
    return ci.qmul(ci.qmul(qk, q_maya), ci.qinv(qk))


def _constrain(owner, targets, ctype, mo=None):
    for ob in bpy.context.scene.objects:
        ob.select_set(False)
    for t in targets:
        t.select_set(True)
    owner.select_set(True)
    bpy.context.view_layer.objects.active = owner
    bpy.context.view_layer.update()
    kw = {} if mo is None else {"maintain_offset": 'ON' if mo else 'OFF'}
    assert bpy.ops.allset.constrain('EXEC_DEFAULT', type=ctype, **kw) == {'FINISHED'}
    groups = list(cm._groups(owner))
    assert len(groups) == 1, groups
    return groups[0]


def _settle(owner, group):
    for _ in range(3):
        bpy.context.view_layer.update()
        if ci.blend_constraint(owner, group) is not None:
            ci.update(owner, group)
    bpy.context.view_layer.update()


# --- the maths -------------------------------------------------------------------------------------------------------


# --- the kit ----------------------------------------------------------------------------------------------------------


def test_blend_is_part_of_the_node_and_goes_with_it():
    _reset()
    a, b = _node("A", (0, 0, 30)), _node("B", (0, 0, 90))
    c = _node("C")
    group = _constrain(c, [a, b], 'COPY_ROTATION')
    blend = ci.blend_constraint(c, group)
    assert blend is not None and blend not in cb.constraints(c), "the blend is hidden in the Channel Box"
    assert len(cb.constraints(c)) == 2
    cm.set_enabled(c, group, False)
    assert not blend.enabled
    cm.set_enabled(c, group, True)
    helper = blend.target.name
    cm.remove_group(c, group)
    assert ci.blend_constraint(c, group) is None and helper not in bpy.data.objects
    assert not any(k.startswith(ci.INTERP) for k in c.keys())


def test_bone_owner_runs():
    _reset()
    arm = bpy.data.armatures.new("A")
    ob = bpy.data.objects.new("skeleton1", arm)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.edit_bones.new("joint1")
    eb.head, eb.tail = (0, 0, 0), (0, 1, 0)
    bpy.ops.object.mode_set(mode='OBJECT')
    t0, t1 = _node("T0", (0, 0, 20)), _node("T1", (0, 0, 120))
    pb = ob.pose.bones["joint1"]
    cm.build(bpy.context, pb, [(t0, ""), (t1, "")], 'COPY_ROTATION')
    group = next(iter(cm._groups(ob.pose.bones["joint1"])))
    pb = ob.pose.bones["joint1"]
    _settle(pb, group)
    # Average of two equal-weight targets 100 deg apart = the joint turned to their middle (Maya frames)
    cp_inv = ci.parent_frame(pb).inverted()
    want = ci.blend([ci.target_quat(cp_inv, t0), ci.target_quat(cp_inv, t1)], [1, 1], ci.AVERAGE)
    got = (cp_inv @ ci.frame(pb)).to_quaternion()
    assert ang(got, want) < TOL_KIT


# --- aim world up types ------------------------------------------------------------------------------------------------


def test_aim_object_up_helper_goes_with_the_aim():
    from bl_ext.user_default.allset.operators import rig_tools
    _reset()
    a, up, c = _node("A", loc=(3, 1, 0)), _node("UP", loc=(0, 4, 0)), _node("C")
    con = c.constraints.new('TRACK_TO')
    con.target = a
    con = rig_tools.aim(c.constraints, con, world_up="Object up", up_object=up)
    companion = c.constraints.get(con.name + rig_tools.UP_SUFFIX)
    assert companion is not None and companion not in cb.constraints(c) and con in cb.constraints(c)
    helper, companion = companion.target.name, companion.name
    c.constraints.remove(con)
    cm.cleanup()
    assert helper not in bpy.data.objects and c.constraints.get(companion) is None
