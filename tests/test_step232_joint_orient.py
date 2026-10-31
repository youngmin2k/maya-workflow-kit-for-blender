"""Issue #141: Orient Joint runs on a plain click, and the FBX jointOrient equals Maya's.

Maya 2026: the same three joints
(cm, Maya Y-up), ``joint -e -oj xyz -sao yup -ch -zso`` (Joint Tool finish, then Skeleton > Orient Joint factory),
then ``mirrorJoint -mirrorYZ -mirrorBehavior``. The kit file is read back with its own FBX reader (PreRotation =
Maya jointOrient); audit 0.5.0 ③-15 had the root at (-90, 7, 0) and the end joint at (0, 0, 0).
"""

import math
import os
from importlib import import_module

import bpy
from mathutils import Euler, Matrix, Vector

import kit

joints = import_module(kit.MODULE + ".operators.joints")
fbx_rig = import_module(kit.MODULE + ".operators.fbx_rig")
units = import_module(kit.MODULE + ".operators.units")

OUT = os.path.join(os.environ.get("ALLSET_TEST_OUT", bpy.app.tempdir), "step232")
MAYA_POS = {"joint1": (4.99104, 0.0, -0.03606), "joint2": (12.98916, 0.0, -1.01919),
            "joint3": (20.98985, 0.0, 0.00757)}


def _bl(p, k):
    return Vector((p[0], -p[2], p[1])) * k


def _rot(deg):
    return Euler([math.radians(a) for a in deg], 'XYZ').to_matrix()


def _scene():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for a in list(bpy.data.armatures):
        bpy.data.armatures.remove(a)
    sc = bpy.context.scene
    sc.unit_settings.system, sc.unit_settings.length_unit = 'METRIC', 'CENTIMETERS'
    return sc, units.maya_unit(sc)


def _arm(mirror=True, orient_menu=True):
    sc, k = _scene()
    ob = joints.new_skeleton(bpy.context)
    parent, names = None, []
    for name in ("joint1", "joint2", "joint3"):
        parent = joints.add_joint(ob, _bl(MAYA_POS[name], k), parent, up=Vector((0, 0, 1)), length=2 * k)
        names.append(parent)
    assert names == ["joint1", "joint2", "joint3"], names
    # Maya's chain was made with `joint -e -oj xyz -sao yup -ch -zso` — no -aos (aos=False here)
    joints.orient_new(ob, names, aos=False)                       # Joint Tool finish (Y, world +Y)
    joints.finish(bpy.context, ob, names)
    if orient_menu:
        joints.orient(ob, ["joint1"], "Y+", True, aos=False)      # Skeleton > Orient Joint, no -aos
    if mirror:
        joints.mirror(ob, ["joint1"], "YZ", True)                 # Mirror Joints YZ, Behavior
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob, k


def _export(name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    assert bpy.ops.allset.file_export_all('EXEC_DEFAULT', filepath=path, export_type='FBX') == {'FINISHED'}
    return fbx_rig.Index(fbx_rig.load(path)[0])


def _angle(a, b):
    return math.degrees((a.transposed() @ b).to_quaternion().angle)


def test_world_positions_unchanged():
    ob, k = _arm()
    index = _export("pos232.fbx")
    for name, w in fbx_rig.world_matrices(index).items():
        p = (ob.matrix_world @ ob.data.bones[name].head_local) / k
        assert (w.to_translation() - Vector((p.x, p.z, -p.y))).length < 1e-4, (name, w.to_translation(), p)


def test_end_joint_frame_turns_its_skin_cluster():
    """The end joint's turned frame keeps the skin: its cluster TransformLink = the joint's world matrix at bind."""
    ob, k = _arm(mirror=False)
    bpy.ops.mesh.primitive_cube_add(size=2 * k, location=_bl((20, 0, 0), k))
    body = bpy.context.active_object
    for name in ("joint1", "joint2", "joint3"):
        body.vertex_groups.new(name=name)
    body.vertex_groups["joint3"].add([v.index for v in body.data.vertices], 1.0, 'REPLACE')
    body.modifiers.new("skinCluster1", 'ARMATURE').object = ob
    index = _export("skin232.fbx")
    world = fbx_rig.world_matrices(index)
    uid = next(u for u, m in index.limbs().items() if fbx_rig.name_of(m) == "joint3")
    clusters = {d.props[0]: d for d in index.objects.find(b"Deformer") if d.props[2] == b"Cluster"}
    cid = next(c.props[2] for c in index.conns.elems if c.props[0] == b"OO" and c.props[1] == uid
               and c.props[2] in clusters)
    tl = fbx_rig._mat(clusters[cid].first(b"TransformLink").props[0])
    assert _angle(tl.to_3x3().normalized(), world["joint3"].to_3x3().normalized()) < 1e-3
    assert (tl.to_translation() - world["joint3"].to_translation()).length < 1e-3
    assert _angle(world["joint3"].to_3x3(), _rot((0, 0, 0))) < 1e-3          # Maya: the end joint lines up with the world


def test_end_orient_cleared_when_the_joint_gets_a_child():
    ob, k = _arm(mirror=False)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    joints.add_joint(ob, _bl((26, 0, 2), k), "joint3")
    joints.orient_new(ob, ["joint3", "joint4"], aos=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    assert joints.MAYA_FRAME not in ob.data.bones["joint3"]
    assert joints.MAYA_FRAME in ob.data.bones["joint4"]


def test_plain_click_runs_with_the_last_options():
    """Maya: the menu item runs with the saved options (no window); only the option box opens it. In -b an INVOKE
    call goes straight to execute, so the saved values and the load are checked directly (the click itself: GUI,
    audit230 sessions/chain3.py — Orient Joint, then Alt+F / Q)."""
    ob, k = _arm(mirror=False, orient_menu=False)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='POSE')
    cb = import_module(kit.MODULE + ".ui.channel_box")
    for pb in ob.pose.bones:
        cb.set_bone_selected(pb, pb.name == "joint1")
    ow = import_module(kit.MODULE + ".operators.option_windows")
    assert bpy.ops.allset.orient_joint('EXEC_DEFAULT', world="Z+", children=False) == {'FINISHED'}
    assert ow.saved("op_orient_joint")["world"] == "Z+" and ow.saved("op_orient_joint")["children"] is False

    class Op:
        primary, secondary, world, children = "X", "Y", "Y+", True
    op = Op()
    joints._load_options(op, "orient_joint", ("primary", "secondary", "world", "children"))
    assert (op.world, op.children) == ("Z+", False)
    assert bpy.ops.allset.orient_joint('EXEC_DEFAULT', world="Y+", children=True) == {'FINISHED'}   # back
    for cls in ("ALLSET_OT_orient_joint", "ALLSET_OT_mirror_joints"):
        rna = getattr(bpy.types, cls)
        assert 'REGISTER' not in rna.bl_options, cls                         # Maya has no redo panel
    for op in (bpy.ops.allset.orient_joint, bpy.ops.allset.mirror_joints):
        assert "option_box" in op.get_rna_type().properties                  # the option box opens the window


def test_turned_joints_keep_the_animation():
    """Keys on Behavior-mirrored and end joints: every frame's joint world positions equal the scene's."""
    ob, k = _arm()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 10
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='POSE')
    for name, deg in (("joint4", 30.0), ("joint5", -45.0), ("joint6", 20.0), ("joint2", 25.0)):
        pb = ob.pose.bones[name]
        pb.rotation_mode = 'XYZ'
        for f, a in ((1, 0.0), (10, deg)):
            pb.rotation_euler = (math.radians(a) * 0.5, math.radians(a) * 0.3, math.radians(a))
            pb.keyframe_insert("rotation_euler", frame=f)
    bpy.ops.object.mode_set(mode='OBJECT')
    index = _export("anim232.fbx")
    turns = joints.maya_frames(ob)
    assert sorted(turns) == ["joint3", "joint4", "joint5", "joint6"], sorted(turns)
    worst = rot_worst = 0.0
    for i, f in enumerate(range(1, 11)):
        sc.frame_set(f)
        got = fbx_rig.world_matrices(index, sample=i)
        for pb in ob.pose.bones:
            p = (ob.matrix_world @ pb.head) / k
            worst = max(worst, (got[pb.name].to_translation() - Vector((p.x, p.z, -p.y))).length)
            # and its axes = the bone's joint frame turned by its Maya frame (Maya coordinates)
            want = joints.MAYA_WORLD.inverted() @ ((ob.matrix_world @ pb.matrix).to_3x3().normalized()
                                                   @ joints.JOINT_AXES @ turns.get(pb.name, Matrix.Identity(3)))
            rot_worst = max(rot_worst, _angle(got[pb.name].to_3x3().normalized(), want))
    print(f"step232 animated turned joints max error {worst:.2e} cm, {rot_worst:.2e} deg")
    assert worst < 1e-3 and rot_worst < 1e-3, (worst, rot_worst)
