"""B1-B4: the Joint Tool ends on the top of the branch it made (Maya 2026), the branch hit area is the
drawn joint sphere, and a skeleton picked with no bone selected shows its root joint.
Maya 2026: Joint Tool finish, hit area, root joint in the Channel Box.
GUI: tests/gui/gui_pr125_joint_tool.py (Enter -> Select tool, W after a branch), gui_step217_joint_hit.py."""

from importlib import import_module

import bpy
from mathutils import Vector

import kit

joints = import_module(kit.MODULE + ".operators.joints")
joint_selection = import_module(kit.MODULE + ".operators.joint_selection")
cb = import_module(kit.MODULE + ".ui.channel_box")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for arm in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm)


def _chain(points, parent=None, ob=None):
    ob = ob or joints.new_skeleton(bpy.context)
    if ob.mode != 'EDIT':
        bpy.ops.object.mode_set(mode='EDIT')
    names = []
    for p in points:
        name = joints.add_joint(ob, Vector(p), parent, up=Vector((0, 0, 1)), length=1.0)
        if name != parent:
            names.append(name)
        parent = name
    return ob, names


def _selected(ob):
    return [pb.name for pb in ob.pose.bones if cb.bone_selected(pb)]


def test_finish_selects_the_new_root():
    """3 clicks + Enter -> [joint1] (Maya: the new chain's root), active, only selection."""
    _clear()
    ob, names = _chain([(0, 0, 0), (0, 0, 2), (0, 0, 4)])
    joints.finish(bpy.context, ob, names)
    assert names == ["joint1", "joint2", "joint3"]
    assert _selected(ob) == ["joint1"] and ob.data.bones.active.name == "joint1"
    assert cb.lead() == ob.pose.bones["joint1"]


def test_finish_after_a_branch_selects_the_branch_parent():
    """First click on existing joint2 + one click + Enter -> joint4 under joint2, selection [joint2] (Maya joint8 case)."""
    _clear()
    ob, names = _chain([(0, 0, 0), (0, 0, 2), (0, 0, 4)])
    bpy.ops.object.mode_set(mode='POSE')
    _ob, new = _chain([(2, 0, 2)], parent="joint2", ob=ob)
    joints.finish(bpy.context, ob, new, "joint2")
    assert new == ["joint4"] and ob.data.bones["joint4"].parent.name == "joint2"
    assert _selected(ob) == ["joint2"] and ob.data.bones.active.name == "joint2"


def test_operator_points_select_the_root():
    _clear()
    res = bpy.ops.allset.joint_tool('EXEC_DEFAULT', points="[[0, 0, 0], [0, 0, 3], [0, 0, 6]]")
    assert res == {'FINISHED'}
    ob = bpy.context.active_object
    assert _selected(ob) == ["joint1"], _selected(ob)


def test_joint_sphere_radius():
    """Blender's octahedral joint point = 0.05 x bone length; a connected head uses the incoming bone."""
    _clear()
    ob, names = _chain([(0, 0, 0), (0, 0, 4), (0, 0, 6)])
    bpy.ops.object.mode_set(mode='OBJECT')
    bones = ob.data.bones
    assert abs(joints.joint_sphere_radius(ob, bones["joint1"]) - 0.05 * 4.0) < 1e-6
    # joint2's head = joint1's tail (connected): the sphere is drawn with joint1's length
    assert bones["joint2"].use_connect
    assert abs(joints.joint_sphere_radius(ob, bones["joint2"]) - 0.05 * 4.0) < 1e-6
    ob.scale = (2, 2, 2)
    bpy.context.view_layer.update()
    assert abs(joints.joint_sphere_radius(ob, bones["joint1"]) - 0.4) < 1e-6
    ob.data.display_type = 'STICK'
    assert joints.joint_sphere_radius(ob, bones["joint1"]) == 0.0      # no sphere: the click-box floor only


def test_root_joint_selected_when_nothing_is():
    """B4: a skeleton picked with no shown bone selected -> its root joint (Channel Box = root channels)."""
    _clear()
    ob, names = _chain([(0, 0, 0), (0, 0, 2), (0, 0, 4)])
    bpy.ops.object.mode_set(mode='POSE')
    for pb in ob.pose.bones:
        cb.set_bone_selected(pb, False)
    ob.data.bones.active = None
    assert cb.lead() is None
    assert joint_selection.select_roots_if_empty(ob)
    assert _selected(ob) == ["joint1"] and cb.lead() == ob.pose.bones["joint1"]
    # a selection the user made stays
    cb.set_bone_selected(ob.pose.bones["joint1"], False)
    cb.set_bone_selected(ob.pose.bones["joint3"], True)
    ob.data.bones.active = ob.data.bones["joint3"]
    assert not joint_selection.select_roots_if_empty(ob)
    assert _selected(ob) == ["joint3"]
    bpy.ops.object.mode_set(mode='OBJECT')


def test_root_joints_skip_hidden_collections_and_take_every_root():
    """Two root chains: both roots selected, the last one leads (Maya Select > All lead = last root); a root in a
    hidden bone collection gives way to its first shown descendants."""
    _clear()
    ob, a = _chain([(0, 0, 0), (0, 0, 2)])
    _ob, b = _chain([(3, 0, 0), (3, 0, 2)], ob=ob)
    bpy.ops.object.mode_set(mode='POSE')
    for pb in ob.pose.bones:
        cb.set_bone_selected(pb, False)
    assert joint_selection.select_roots_if_empty(ob)
    assert sorted(_selected(ob)) == sorted([a[0], b[0]]) and ob.data.bones.active.name == b[0]
    for pb in ob.pose.bones:
        cb.set_bone_selected(pb, False)
    mch = ob.data.collections.new("MCH")
    mch.assign(ob.data.bones[a[0]])
    mch.is_visible = False
    assert [pb.name for pb in joint_selection.root_joints(ob)] == [a[1], b[0]]
    bpy.ops.object.mode_set(mode='OBJECT')
