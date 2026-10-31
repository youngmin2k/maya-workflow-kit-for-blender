"""Skeleton > Joint Labelling (labels as bone ID properties, Rename Joints From Labels, Label Based
on Joint Names, Toggle / Show / Hide labels + viewport drawing), Mirror Skin Weights Label association, Enable /
Disable Selected IK Handles, following Maya."""

from importlib import import_module

import bpy
from mathutils import Vector

import kit

labels = import_module(kit.MODULE + ".operators.joint_labels")
joints = import_module(kit.MODULE + ".operators.joints")
skin = import_module(kit.MODULE + ".operators.skin")
rig_maya = import_module(kit.MODULE + ".operators.rig_maya")
cb = import_module(kit.MODULE + ".ui.channel_box")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.armatures, bpy.data.curves):
        for d in list(coll):
            coll.remove(d)
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'METERS', 1.0


def _skeleton(spec):
    """spec = [(point, parent index or None)] -> armature in pose mode, bone names in spec order."""
    ob = joints.new_skeleton(bpy.context)
    names = []
    for p, parent in spec:
        names.append(joints.add_joint(ob, Vector(p), names[parent] if parent is not None else None, length=0.5))
    joints.finish(bpy.context, ob, names)
    return ob, names


def _chain(n=3):
    return _skeleton([((0, 0, i), i - 1 if i else None) for i in range(n)])


def _select(ob, names):
    if ob.mode != 'POSE':
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='POSE')
    for pb in ob.pose.bones:
        cb.set_bone_selected(pb, pb.name in names)
    if names:
        ob.data.bones.active = ob.data.bones[names[-1]]


def _lab(ob, name):
    return labels.get_label(ob.data.bones[name])


# --- Add Joint Labels ---------------------------------------------------------------------------------------------

def test_factory_label_values():
    _clear()
    ob, n = _chain(1)
    assert _lab(ob, n[0]) == (0, 0, "jaw", False), _lab(ob, n[0])     # Maya: Center, None, "jaw", off
    assert len(labels.TYPES) == 30 and labels.TYPES[18] == "Other" and labels.TYPES[29] == "Foot Thumb"
    assert labels.SIDES == ("Center", "Left", "Right", "None")


def test_side_labels_follow_maya_scope():
    _clear()
    ob, n = _chain(3)
    _select(ob, [n[0]])
    assert bpy.ops.allset.joint_label(side='LEFT') == {'FINISHED'}
    assert [_lab(ob, x)[0] for x in n] == [1, 1, 1], "Left = the selection and every joint below it"
    assert bpy.ops.allset.joint_label(side='CENTER') == {'FINISHED'}
    assert [_lab(ob, x)[0] for x in n] == [0, 1, 1], "Center = the selected joints only (Maya)"
    assert bpy.ops.allset.joint_label(side='NONE') == {'FINISHED'}
    assert [_lab(ob, x)[0] for x in n] == [3, 3, 3]


def test_type_labels_follow_maya_scope():
    _clear()
    ob, n = _chain(3)
    _select(ob, [n[0]])
    bpy.ops.allset.joint_label(side='LEFT')
    _select(ob, [n[1]])
    assert bpy.ops.allset.joint_label(type='SPINE') == {'FINISHED'}
    assert _lab(ob, n[1])[:2] == (0, 6), "Spine also sets the selected joint's side to Center"
    assert _lab(ob, n[2])[:2] == (1, 0), "non-digit types touch only the selection"
    _select(ob, [n[0]])
    assert bpy.ops.allset.joint_label(type='THUMB') == {'FINISHED'}
    assert [_lab(ob, x)[1] for x in n] == [14, 14, 14], "digit types also label the joints below (Maya)"
    assert bpy.ops.allset.joint_label(type='NONE') == {'FINISHED'}
    assert _lab(ob, n[0])[:2] == (0, 0) and _lab(ob, n[1])[1] == 14, "Label None = type None + Center, selection only"
    _select(ob, [])
    try:
        bpy.ops.allset.joint_label(type='HIP')
    except RuntimeError:
        pass
    else:
        raise AssertionError("no joint selected must be an error like Maya's")


def test_labels_in_edit_mode_survive_leaving_it():
    _clear()
    ob, n = _chain(2)
    bpy.ops.object.mode_set(mode='EDIT')
    for eb in ob.data.edit_bones:
        eb.select = eb.name == n[1]
    assert bpy.ops.allset.joint_label(type='KNEE') == {'FINISHED'}
    bpy.ops.object.mode_set(mode='POSE')
    assert _lab(ob, n[1])[1] == 3 and _lab(ob, n[0])[1] == 0


def test_object_mode_skeleton_means_its_root_joints():
    _clear()
    ob, n = _chain(3)
    bpy.ops.object.mode_set(mode='OBJECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    assert bpy.ops.allset.joint_label(side='RIGHT') == {'FINISHED'}
    assert [_lab(ob, x)[0] for x in n] == [2, 2, 2]


# Maya (retargetingLimbLabel "Arm" / "Leg" on the top joint): names + child counts -> types
def test_limb_labels_match_maya():
    chain5 = [("s", 1), ("el", 1), ("wr", 1), ("f1", 1), ("f2", 0)]
    assert labels.limb_labels("ARM", chain5) == [10, 11, 12, 13, 13]
    assert labels.limb_labels("ARM", [("s", 1), ("el", 1), ("wr", 0)]) == [10, 11, 12]
    leg = [("hp", 1), ("kn", 1), ("ft", 1), ("toeA", 1), ("toeB", 0)]
    assert labels.limb_labels("LEG", leg) == [2, 3, 4, 5, 5]
    branch = [("s", 1), ("el", 1), ("wr", 2), ("fa1", 1), ("fa2", 0), ("fb1", 1), ("fb2", 0)]
    assert labels.limb_labels("ARM", branch) == [10, 11, 12, 13, 13, 13, 13]
    # operator on a real 5-joint chain
    _clear()
    ob, n = _chain(5)
    _select(ob, [n[0]])
    assert bpy.ops.allset.joint_label(type='ARM') == {'FINISHED'}
    assert [_lab(ob, x)[1] for x in n] == [10, 11, 12, 13, 13]
    assert bpy.ops.allset.joint_label(type='LEG') == {'FINISHED'}
    assert [_lab(ob, x)[1] for x in n] == [2, 3, 4, 5, 5]


# --- Label Based on Joint Names -----------------------------------------------------------------------------------


def test_label_from_joint_names_operator():
    _clear()
    ob, n = _chain(3)
    bpy.ops.object.mode_set(mode='OBJECT')
    for old, new in zip(n, ("L_arm", "leftForeArm", "Hip_R")):
        ob.data.bones[old].name = new
    _select(ob, ["L_arm"])
    assert bpy.ops.allset.label_from_joint_names() == {'FINISHED'}
    assert _lab(ob, "L_arm")[:2] == (1, 10) and _lab(ob, "leftForeArm")[:2] == (1, 11)
    assert _lab(ob, "Hip_R")[:2] == (0, 2), "Maya reads no side from a trailing _R"


# --- Rename Joints From Labels ------------------------------------------------------------------------------------

def test_rename_joints_from_labels_matches_maya():
    _clear()
    ob, n = _chain(5)
    for name, (side, typ, other) in zip(n, ((0, 1, None), (1, 2, None), (3, 3, None), (1, 18, "Tail"), (2, 19, None))):
        labels.set_label(ob.data.bones[name], side=side, type=typ, other_type=other)
    # a skinned mesh keeps its weights through the rename (Blender renames the vertex groups)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.mesh.primitive_plane_add(size=1)
    plane = bpy.context.active_object
    plane.modifiers.new("Armature", 'ARMATURE').object = ob
    plane.vertex_groups.new(name=n[1]).add([0], 1.0, 'REPLACE')
    _select(ob, [n[0]])
    assert bpy.ops.allset.rename_joints_from_labels() == {'FINISHED'}
    got = [b.name for b in ob.data.bones]
    # Maya: |CenterRoot|LeftHip|c|LeftOther|RightIndexFinger (None side keeps its name; Other = "Other")
    assert got == ["CenterRoot", "LeftHip", n[2], "LeftOther", "RightIndexFinger"], got
    assert plane.vertex_groups.get("LeftHip") is not None
    # a clash numbers the name like Maya's rename (LeftHip1)
    labels.set_label(ob.data.bones[n[2]], side=1, type=2)
    _select(ob, [n[2]])
    bpy.ops.allset.rename_joints_from_labels()
    assert ob.data.bones.get("LeftHip1") is not None and ob.data.bones.get("LeftHip") is not None


# --- Toggle / Show / Hide labels, drawing --------------------------------------------------------------------------

def test_toggle_show_hide_and_drawn_text():
    _clear()
    ob, n = _chain(3)
    labels.set_label(ob.data.bones[n[2]], draw=True)
    _select(ob, [n[1]])
    assert bpy.ops.allset.joint_label_toggle() == {'FINISHED'}
    # Maya displayJointLabels 2: the first joint decides (off -> on for all)
    assert [_lab(ob, x)[3] for x in n] == [False, True, True]
    bpy.ops.allset.joint_label_toggle()
    assert [_lab(ob, x)[3] for x in n] == [False, False, False]
    assert bpy.ops.allset.joint_label_show_all(show=True) == {'FINISHED'}
    assert all(_lab(ob, x)[3] for x in n)
    labels.set_label(ob.data.bones[n[0]], side=1, type=2)
    labels.set_label(ob.data.bones[n[1]], side=3, type=3)
    labels.set_label(ob.data.bones[n[2]], side=2, type=18, other_type="tail")
    texts = sorted(t for _p, t, _s in labels.label_points(bpy.context))
    assert texts == ["Hip (L)", "Knee (None)", "tail (R)"], texts          # Maya's labels
    assert labels.label_text(ob.data.bones[n[0]]) == "Hip (L)"
    labels.set_label(ob.data.bones[n[0]], side=0, type=6)
    assert labels.label_text(ob.data.bones[n[0]]) == "Spine"
    assert bpy.ops.allset.joint_label_show_all(show=False) == {'FINISHED'}
    assert labels.label_points(bpy.context) == []
    assert labels._handles, "the viewport draw handler is registered with the extension"


# --- Mirror Skin Weights: Label association -----------------------------------------------------------------------

def _two_sided():
    """root at the origin; left Hip / Knee at +x, right Hip / Knee at -x NOT mirrored; two fingers per side."""
    spec = [((0, 0, 0), None),
            ((2, 0, 0), 0), ((4, 0, 0), 1),                 # 1 aL, 2 bL
            ((-3, 0, 1), 0), ((-6, 0, 1), 3),               # 3 cR, 4 dR
            ((5, 1, 0), 2), ((5, -1, 0), 2),                # 5 fL1 (+y), 6 fL2 (-y)
            ((-7, -1, 1), 4), ((-7, 1, 1), 4)]              # 7 gR1 (-y), 8 gR2 (+y)
    ob, n = _skeleton(spec)
    lab = [(0, 1), (1, 2), (1, 3), (2, 2), (2, 3), (1, 13), (1, 13), (2, 13), (2, 13)]
    for name, (side, typ) in zip(n, lab):
        labels.set_label(ob.data.bones[name], side=side, type=typ)
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob, n


def test_mirror_label_association_pairs_unmirrored_joints():
    _clear()
    ob, n = _two_sided()
    by_label = skin.mirror_group_names(ob, 0, modes=("LABEL",))
    # Maya copySkinWeights -mirrorMode YZ -influenceAssociation label: aL->cR, bL->dR, fL1->gR2, fL2->gR1
    assert by_label[n[0]] == n[0] and by_label[n[1]] == n[3] and by_label[n[2]] == n[4], by_label
    assert by_label[n[5]] == n[8] and by_label[n[6]] == n[7], by_label
    assert by_label[n[3]] == n[1]
    closest = skin.mirror_group_names(ob, 0)
    # Maya closestJoint: the joint nearest the mirrored place, no tolerance (bL -> cR, fL1 -> dR)
    assert closest[n[1]] == n[3] and closest[n[2]] == n[3] and closest[n[5]] == n[4], closest
    # unlabelled joints: Label alone falls back to the closest joint and reports it
    labels.set_label(ob.data.bones[n[2]], type=0)
    missed = []
    pair = skin.mirror_group_names(ob, 0, modes=("LABEL",), unmatched=missed)
    # bL lost its type: it and Right Knee (no Left Knee left) are unmatched
    assert sorted(missed) == sorted([n[2], n[4]]) and pair[n[2]] == n[3], missed


def test_mirror_skin_weights_operator_label_mode():
    _clear()
    ob, n = _two_sided()
    bpy.ops.mesh.primitive_plane_add(size=1)
    plane = bpy.context.active_object
    bpy.ops.transform.resize(value=(16, 1, 1))
    bpy.ops.object.transform_apply(scale=True)
    plane.modifiers.new("Armature", 'ARMATURE').object = ob
    groups = {name: plane.vertex_groups.new(name=name) for name in n}
    pos = [v.index for v in plane.data.vertices if v.co.x > 0]
    neg = [v.index for v in plane.data.vertices if v.co.x < 0]
    groups[n[2]].add(pos, 1.0, 'REPLACE')                  # +x side all Left Knee
    groups[n[3]].add(neg, 1.0, 'REPLACE')                  # -x side wrong (Right Hip) before the mirror
    for o in bpy.context.scene.objects:
        o.select_set(o is plane)
    bpy.context.view_layer.objects.active = plane
    assert bpy.ops.allset.mirror_skin_weights(influence1='LABEL') == {'FINISHED'}
    for i in neg:
        ws = {plane.vertex_groups[g.group].name: round(g.weight, 6) for g in plane.data.vertices[i].groups
              if g.weight > 0}
        assert ws == {n[4]: 1.0}, ("Left Knee mirrors onto Right Knee", ws)
    # Closest joint (factory) sends Left Knee (4, 0, 0) to the joint nearest (-4, 0, 0) = Right Hip
    assert bpy.ops.allset.mirror_skin_weights() == {'FINISHED'}
    ws = {plane.vertex_groups[g.group].name for g in plane.data.vertices[neg[0]].groups if g.weight > 0}
    assert ws == {n[3]}, ws


def test_mirror_bound_mesh_label_mode():
    """bind_skin, then Label mode keeps the source side and gives the other side the paired joints."""
    _clear()
    ob, n = _two_sided()
    bpy.ops.mesh.primitive_plane_add(size=1)
    plane = bpy.context.active_object
    bpy.ops.transform.resize(value=(16, 1, 1))
    bpy.ops.object.transform_apply(scale=True)
    for o in bpy.context.scene.objects:
        o.select_set(o in (ob, plane))
    bpy.context.view_layer.objects.active = plane
    assert bpy.ops.allset.bind_skin() == {'FINISHED'}
    v = max(plane.data.vertices, key=lambda v: v.co.x)
    before = {plane.vertex_groups[g.group].name: g.weight for g in v.groups if g.weight > 1e-6}
    assert bpy.ops.allset.mirror_skin_weights(influence1='LABEL') == {'FINISHED'}
    mate = min(plane.data.vertices, key=lambda u: (u.co - Vector((-v.co.x, v.co.y, v.co.z))).length)
    after = {plane.vertex_groups[g.group].name: g.weight for g in mate.groups if g.weight > 1e-6}
    pair = skin.mirror_group_names(ob, 0, modes=("LABEL",))
    want = {}
    for name, w in before.items():
        want[pair[name]] = want.get(pair[name], 0.0) + w
    assert set(after) == set(want) and all(abs(after[k] - want[k]) < 1e-6 for k in want), (after, want)


# --- Enable / Disable Selected IK Handles -------------------------------------------------------------------------

def test_ik_handle_enable_disable():
    _clear()
    ob, n = _skeleton([((0, 0, 0), None), ((0, 0.3, 1), 0), ((0, 0, 2), 1)])
    bpy.ops.object.mode_set(mode='OBJECT')
    handle = skin.create_ik(bpy.context, ob, (n[0], 'HEAD'), (n[2], 'HEAD'))
    con = skin.ik_constraints_on(handle)[0][2]
    assert bpy.context.active_object is handle and handle.select_get()
    assert bpy.ops.allset.ik_handle_enable(enable=False) == {'FINISHED'}
    assert con.influence == 0.0, "Maya ikHandle -e -dh: ikBlend 0"
    assert bpy.ops.allset.ik_handle_enable(enable=True) == {'FINISHED'}
    assert con.influence == 1.0
    handle.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    try:
        bpy.ops.allset.ik_handle_enable(enable=False)
    except RuntimeError as ex:
        assert "No handle selected" in str(ex), ex
    else:
        raise AssertionError("a joint / skeleton is not a handle (Maya: 'No handle selected.')")
    assert con.influence == 1.0


def test_spline_ik_handle_disable_from_its_bone():
    _clear()
    ob, n = _chain(4)
    res = rig_maya.create_spline_ik(bpy.context, ob, (n[0], 'HEAD'), (n[3], 'HEAD'))
    assert res is not None
    con, _curve = res
    bone = con.id_data.pose.bones[[pb.name for pb in ob.pose.bones if con.name in pb.constraints][0]]
    _select(ob, [bone.name])
    assert bpy.ops.allset.ik_handle_enable(enable=False) == {'FINISHED'}
    assert con.influence == 0.0
