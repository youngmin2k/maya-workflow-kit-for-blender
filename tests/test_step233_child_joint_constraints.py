"""Issue #142: constraints on a CHILD joint move it like Maya.

Expected: joints (0, 10, 0) ->
(6, 10, 0) -> (12, 10, 0) (cmds.joint), transforms ctrlA t (12, 10, 0) r (0, 0, 30) and ctrlB t (12, 14, 0)
r (10, -20, 0); ctrlA, ctrlB, then joint3 selected -> Constrain > Point / Parent / Orient / Aim; W1 = 3; then
ctrlB moved to (14, 15, 1). Audit 0.5.0 ①-7: the kit's Point constraint left joint3 at (12, 10, 0) (Blender ignores
location constraints on a connected bone).
"""

import math
from importlib import import_module

import bpy
from mathutils import Euler, Matrix, Vector

import kit

joints = import_module(kit.MODULE + ".operators.joints")
multi = import_module(kit.MODULE + ".operators.constrain_multi")
units = import_module(kit.MODULE + ".operators.units")
cb = import_module(kit.MODULE + ".ui.channel_box")

C3 = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))      # Maya axes -> Blender axes
MAYA = {   # Maya joint3 world translation (cm)
    "point": {"w11": (12.0, 12.0, 0.0), "w13": (12.0, 13.0, 0.0), "moved": (13.5, 13.75, 0.75)},
    "parent_nomo": {"w11": (12.0, 12.0, 0.0), "w13": (12.0, 13.0, 0.0), "moved": (13.5, 13.75, 0.75)},
    "parent_mo": {"w11": (12.0, 10.0, 0.0), "w13": (12.0, 10.0, 0.0), "moved": (13.5, 10.75, 0.75)},
    "orient": {"w11": (12.0, 10.0, 0.0)},
    "aim": {"w11": (12.0, 10.0, 0.0)},
}
# joint3 world axes (rows of Maya's xform -ws -m, rotation part) per state
I3 = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
PARENT_R = {"w11": ((0.946209, 0.265705, 0.184632), (-0.280921, 0.957768, 0.061347), (-0.160534, -0.109915, 0.980891)),
            "w13": ((0.953929, 0.134393, 0.268251), (-0.168419, 0.979776, 0.10805), (-0.248304, -0.14825, 0.95727))}
MAYA_R = {"point": {"w11": I3, "w13": I3, "moved": I3},
          "parent_nomo": {**PARENT_R, "moved": PARENT_R["w13"]},
          "parent_mo": {"w11": I3, "w13": I3, "moved": I3},
          "orient": PARENT_R,
          # aim: position only — two aim targets are not a weighted target average in the kit (out of scope;
          # Maya aims at (12, 12, 0) here), and its up vector is parallel to the aim (degenerate)
          "aim": {}}
# kit - expected axis differences (deg) allowed where the kit's blend isn't Maya's (orient = Blender's
# weighted rotation mix, not Maya's)
ROT_TOL = {"orient": 1.0}


def _bl(p, k):
    return Vector((p[0], -p[2], p[1])) * k


def _scene():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for a in list(bpy.data.armatures):
        bpy.data.armatures.remove(a)
    sc = bpy.context.scene
    sc.unit_settings.system, sc.unit_settings.length_unit = 'METRIC', 'CENTIMETERS'
    k = units.maya_unit(sc)
    ob = joints.new_skeleton(bpy.context)
    parent = None
    for p in ((0, 10, 0), (6, 10, 0), (12, 10, 0)):
        parent = joints.add_joint(ob, _bl(p, k), parent, up=Vector((0, 0, 1)), length=2 * k)
    joints.orient_new(ob, ["joint1", "joint2", "joint3"])
    joints.finish(bpy.context, ob, ["joint1", "joint2", "joint3"])
    bpy.ops.object.mode_set(mode='OBJECT')
    assert ob.data.bones["joint3"].use_connect
    ctrls = []
    for name, t, r in (("ctrlA", (12, 10, 0), (0, 0, 30)), ("ctrlB", (12, 14, 0), (10, -20, 0))):
        e = bpy.data.objects.new(name, None)
        sc.collection.objects.link(e)
        rm = C3 @ Euler([math.radians(a) for a in r], 'XYZ').to_matrix() @ C3.transposed()
        m = rm.to_4x4()
        m.translation = _bl(t, k)
        e.matrix_world = m
        ctrls.append(e)
    bpy.context.view_layer.update()
    return ob, ctrls, k


def _constrain(ob, ctrls, ctype, maintain='DEFAULT'):
    for c in ctrls:
        c.select_set(True)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='POSE')
    for pb in ob.pose.bones:
        cb.set_bone_selected(pb, pb.name == "joint3")
    ob.data.bones.active = ob.data.bones["joint3"]
    res = bpy.ops.allset.constrain('EXEC_DEFAULT', type=ctype, maintain_offset=maintain)
    assert res == {'FINISHED'}, res
    bpy.context.view_layer.update()


def _pos(ob, k):
    p = (ob.matrix_world @ ob.pose.bones["joint3"].matrix).to_translation() / k
    return Vector((p.x, p.z, -p.y))


def _axes(ob):
    """joint3's Maya world axes (columns), Maya coordinates."""
    m = (ob.matrix_world @ ob.pose.bones["joint3"].matrix).to_3x3().normalized() @ joints.JOINT_AXES
    return C3.transposed() @ m


def _set_w1(ob, value):
    pb = ob.pose.bones["joint3"]
    key = next(k for k in pb.keys() if k.startswith(multi.WEIGHT) and ":1:" in k)
    pb[key] = value
    ob.update_tag()
    bpy.context.view_layer.update()


def _run(case, ctype, maintain='DEFAULT'):
    ob, ctrls, k = _scene()
    _constrain(ob, ctrls, ctype, maintain)
    want = MAYA[case]
    got = {"w11": _pos(ob, k)}
    axes = {"w11": _axes(ob)}
    if "w13" in want:
        _set_w1(ob, 3.0)
        got["w13"], axes["w13"] = _pos(ob, k), _axes(ob)
        ctrls[1].matrix_world.translation = _bl((14, 15, 1), k)
        bpy.context.view_layer.update()
        got["moved"], axes["moved"] = _pos(ob, k), _axes(ob)
    for key, rows in MAYA_R[case].items():
        if key not in axes:
            continue
        maya = Matrix(rows).transposed()
        deg = math.degrees((axes[key].transposed() @ maya).to_quaternion().angle)
        print(f"step233 {case} {key}: axes off Maya {deg:.4f} deg")
        assert deg < ROT_TOL.get(case, 0.01), (case, key, deg)
    for key, w in want.items():
        d = (got[key] - Vector(w)).length
        print(f"step233 {case} {key}: kit {tuple(round(x, 4) for x in got[key])} maya {w} d {d:.2e}")
        assert d < 1e-3, (case, key, tuple(got[key]), w)
    return ob


def test_point_on_a_child_joint():
    ob = _run("point", 'COPY_LOCATION')
    assert not ob.data.bones["joint3"].use_connect and ob.data.bones["joint3"].get(joints.FREED)
    assert ob.data.bones["joint2"].use_connect                   # only the constrained joint lets go


def test_parent_without_offset_on_a_child_joint():
    _run("parent_nomo", 'CHILD_OF', 'OFF')


def test_parent_menu_default_keeps_the_offset():
    _run("parent_mo", 'CHILD_OF')


def test_orient_and_aim_leave_the_joint_in_place():
    for case, ctype in (("orient", 'COPY_ROTATION'), ("aim", 'TRACK_TO')):
        ob = _run(case, ctype)
        assert ob.data.bones["joint3"].use_connect, case         # rotation only: nothing to free


def test_undo_brings_the_connection_back():
    ob, ctrls, k = _scene()
    name = ob.name
    bpy.ops.ed.undo_push(message="before")
    for c in ctrls:
        c.select_set(True)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='POSE')
    for pb in ob.pose.bones:
        cb.set_bone_selected(pb, pb.name == "joint3")
    ob.data.bones.active = ob.data.bones["joint3"]
    assert bpy.ops.allset.constrain('EXEC_DEFAULT', True, type='COPY_LOCATION') == {'FINISHED'}
    ob = bpy.data.objects[name]
    assert not ob.data.bones["joint3"].use_connect
    bpy.ops.ed.undo()
    ob = bpy.data.objects[name]
    assert ob.data.bones["joint3"].use_connect
    assert not ob.pose.bones["joint3"].constraints
