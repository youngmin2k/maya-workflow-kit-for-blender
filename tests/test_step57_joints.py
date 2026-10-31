"""Joint Tool (click -> joints, Enter), Orient Joint, Mirror Joints, pose-mode pick-walk, P / Shift+P on
joints. GUI: tests/gui/gui_step57_joints.py."""

import math
import types
from importlib import import_module

import bpy
from mathutils import Matrix, Vector

import kit

joints = import_module(kit.MODULE + ".operators.joints")
cb = import_module(kit.MODULE + ".ui.channel_box")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")
ic_data = import_module(kit.MODULE + ".keymap.ic_data")
maya_patches = import_module(kit.MODULE + ".keymap.maya_patches")
patch = import_module(kit.MODULE + ".keymap.patch")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for arm in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm)


POINTS = (Vector((1.0, 0.0, 3.0)), Vector((2.0, 0.0, 2.0)), Vector((3.0, 0.0, 2.0)))


def _skeleton(points=POINTS):
    ob = joints.new_skeleton(bpy.context)
    names, parent = [], None
    for p in points:
        parent = joints.add_joint(ob, p, parent, up=Vector((0, 0, 1)), length=0.5)
        names.append(parent)
    return ob, names


def test_joint_tool_chain():
    _clear()
    ob, names = _skeleton()
    assert ob.name == "skeleton1" and ob.data.name == "skeleton1" and ob.mode == 'EDIT'
    assert names == ["joint1", "joint2", "joint3"], names
    ebs = ob.data.edit_bones
    assert ebs["joint2"].parent == ebs["joint1"] and ebs["joint3"].parent == ebs["joint2"]
    assert ebs["joint2"].use_connect and ebs["joint3"].use_connect
    assert (ebs["joint1"].head - POINTS[0]).length < 1e-6 and (ebs["joint1"].tail - POINTS[1]).length < 1e-6
    # the end joint: half the last segment along it
    assert (ebs["joint3"].tail - Vector((3.5, 0.0, 2.0))).length < 1e-6, tuple(ebs["joint3"].tail)
    # a click on the last joint again adds nothing
    assert joints.add_joint(ob, POINTS[2], "joint3") == "joint3" and len(ebs) == 3
    joints.finish(bpy.context, ob, names)
    assert ob.mode == 'POSE'
    assert all(pb.rotation_mode == 'XYZ' for pb in ob.pose.bones)
    # Maya 2026: the new chain's root is the selection
    assert cb.lead() == ob.pose.bones["joint1"] and cb.targets() == [ob.pose.bones["joint1"]]
    # a second skeleton keeps counting joints scene-wide (Maya)
    bpy.ops.object.mode_set(mode='OBJECT')
    ob2, names2 = _skeleton(POINTS[:2])
    assert ob2.name == "skeleton2" and names2 == ["joint4", "joint5"], (ob2.name, names2)
    bpy.ops.object.mode_set(mode='OBJECT')


def test_single_click_joint_has_a_length():
    _clear()
    ob, names = _skeleton(POINTS[:1])
    eb = ob.data.edit_bones["joint1"]
    assert abs(eb.length - 0.5) < 1e-6 and (eb.tail - eb.head).normalized().dot(Vector((0, 0, 1))) > 0.999
    bpy.ops.object.mode_set(mode='OBJECT')


def test_click_point_orthographic_front():
    """Front view (looks along +Y): a click lands on the view plane through the origin (y = 0)."""
    view = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, -10), (0, 0, 0, 1)))
    proj = Matrix(((0.1, 0, 0, 0), (0, 0.1 * 2, 0, 0), (0, 0, -0.01, 0), (0, 0, 0, 1)))
    rv3d = types.SimpleNamespace(is_perspective=False, view_perspective='ORTHO', view_matrix=view,
                                 perspective_matrix=proj @ view)
    region = types.SimpleNamespace(width=200, height=100)
    p = joints.click_point(region, rv3d, (150, 75))       # right of and above the centre
    assert abs(p.y) < 1e-6 and p.x > 0 and p.z > 0, tuple(p)
    assert abs(p.x - 5.0) < 1e-4 and abs(p.z - 2.5) < 1e-4, tuple(p)


def test_orient_joint():
    _clear()
    ob, names = _skeleton((Vector((0, 0, 0)), Vector((1, 0, 0)), Vector((2, 0, 0))))
    for eb in ob.data.edit_bones:
        eb.roll = 1.0
    bpy.ops.object.mode_set(mode='POSE')
    for pb in ob.pose.bones:
        cb.set_bone_selected(pb, pb.name == "joint1")
    assert bpy.ops.allset.orient_joint(world="Y+", children=False) == {'FINISHED'}
    bones = ob.data.bones
    z = lambda b: b.matrix_local.to_3x3().col[2]
    assert z(bones["joint1"]).dot(Vector((0, 0, 1))) > 0.999, "Maya world up Y+ = Blender +Z"
    assert z(bones["joint2"]).dot(Vector((0, 0, 1))) < 0.99, "children untouched without the option"
    bpy.ops.allset.orient_joint(world="Z+", children=True)
    for b in bones:
        assert z(b).dot(Vector((0, -1, 0))) > 0.999, (b.name, tuple(z(b)))   # Maya Z = Blender -Y
    assert ob.mode == 'POSE'
    assert joints.SAO_ROLL["Y+"] == 'GLOBAL_POS_Z'


def test_mirror_joints_yz():
    _clear()
    ob, names = _skeleton()
    ebs = ob.data.edit_bones
    ebs["joint1"].roll = 0.4
    bpy.ops.object.mode_set(mode='POSE')
    for pb in ob.pose.bones:
        cb.set_bone_selected(pb, pb.name == "joint1")
    assert bpy.ops.allset.mirror_joints(plane="YZ") == {'FINISHED'}
    bones = ob.data.bones
    assert len(bones) == 6 and {"joint4", "joint5", "joint6"} <= set(bones.keys()), bones.keys()
    for src, dst in (("joint1", "joint4"), ("joint2", "joint5"), ("joint3", "joint6")):
        a, b = bones[src], bones[dst]
        assert (b.head_local - Vector((-a.head_local.x, a.head_local.y, a.head_local.z))).length < 1e-5, dst
        assert (b.tail_local - Vector((-a.tail_local.x, a.tail_local.y, a.tail_local.z))).length < 1e-5, dst
        ra, rb = a.matrix_local.to_3x3(), b.matrix_local.to_3x3()
        r = Matrix.Diagonal((-1, 1, 1))
        assert abs(rb.determinant() - 1) < 1e-5
        assert ((r @ ra.col[1]) - rb.col[1]).length < 1e-5, "the bone points the mirrored way"
        assert ((r @ ra.col[0]) + rb.col[0]).length < 1e-5, "Behavior: X flips (Blender symmetrize)"
    assert bones["joint5"].parent == bones["joint4"] and bones["joint4"].parent is None
    assert ob.pose.bones["joint6"].rotation_mode == 'XYZ'


def test_mirror_search_replace():
    _clear()
    ob, _names = _skeleton()
    for old, new in (("joint1", "l_hip"), ("joint2", "l_knee"), ("joint3", "l_ankle")):
        ob.data.edit_bones[old].name = new
    for eb in ob.data.edit_bones:
        eb.select = eb.name == "l_hip"
    new = joints.mirror(ob, ["l_hip"], "YZ", True, "l_", "r_")
    assert new == ["r_hip", "r_knee", "r_ankle"], new
    new = joints.mirror(ob, ["l_hip"], "XY", False, "l_", "r_")      # r_* taken: numbered
    assert all(n.startswith("r_") and n not in ("r_hip", "r_knee", "r_ankle") for n in new), new
    eb, src = ob.data.edit_bones[new[0]], ob.data.edit_bones["l_hip"]
    assert abs(eb.head.y + src.head.y) < 1e-6 and abs(eb.head.x - src.head.x) < 1e-6, "Maya XY = Blender -y"
    bpy.ops.object.mode_set(mode='OBJECT')


def test_pick_walk_joints():
    _clear()
    ob, names = _skeleton()
    joints.add_joint(ob, Vector((2.0, 1.0, 1.0)), "joint1")     # joint4: a second child of joint1
    joints.finish(bpy.context, ob, ["joint2"])                  # joint2 selected
    walk = lambda d: (bpy.ops.allset.pick_walk_joint(direction=d), cb.lead().name)[1]
    assert walk("UP") == "joint1"
    assert walk("UP") == "joint1", "the root stays"
    assert walk("DOWN") == "joint2", "first child by name"
    assert walk("RIGHT") == "joint4" and walk("RIGHT") == "joint2", "siblings wrap"
    assert walk("LEFT") == "joint4"
    assert [pb.name for pb in cb.targets()] == ["joint4"]


def test_parent_and_unparent_joints():
    _clear()
    ob, names = _skeleton()
    joints.add_joint(ob, Vector((5.0, 0.0, 0.0)), None)          # joint4: a second root
    bpy.ops.object.mode_set(mode='POSE')
    head = ob.data.bones["joint4"].head_local.copy()
    for pb in ob.pose.bones:
        cb.set_bone_selected(pb, pb.name in ("joint4", "joint2"))
    ob.data.bones.active = ob.data.bones["joint2"]              # Maya: the parent is selected last
    assert bpy.ops.allset.parent_joint() == {'FINISHED'}
    assert ob.data.bones["joint4"].parent.name == "joint2" and ob.mode == 'POSE'
    assert (ob.data.bones["joint4"].head_local - head).length < 1e-6, "kept its place"
    for pb in ob.pose.bones:
        cb.set_bone_selected(pb, pb.name == "joint4")
    assert bpy.ops.allset.unparent_joint() == {'FINISHED'}
    assert ob.data.bones["joint4"].parent is None
    # no loops: a joint can't become the child of its own child
    for pb in ob.pose.bones:
        cb.set_bone_selected(pb, pb.name in ("joint1", "joint3"))
    ob.data.bones.active = ob.data.bones["joint3"]
    bpy.ops.allset.parent_joint()
    assert ob.data.bones["joint1"].parent is None


def test_menus_shelf_keymaps():
    assert menu_map.MAP["Skeleton/Create Joints"] == "allset.joint_tool"
    assert menu_map.MAP["Skeleton/Mirror Joints"] == "allset.mirror_joints"
    assert menu_map.MAP["Skeleton/Orient Joint"] == "allset.orient_joint"
    assert shelf_map.BY_COMMAND["JointTool"][0] == "allset.joint_tool"
    kd = patch.KeyconfigData(maya_patches.apply(ic_data.generate()))
    for key, d in (("UP_ARROW", "UP"), ("DOWN_ARROW", "DOWN"), ("LEFT_ARROW", "LEFT"), ("RIGHT_ARROW", "RIGHT")):
        found = kd.find("Pose", "allset.pick_walk_joint", type=key, repeat=True)
        assert found and dict(found[0][2]["properties"])["direction"] == d, key
    assert not kd.find("Pose", "pose.select_hierarchy", type="UP_ARROW", repeat=True)
    for km in ("Pose", "Armature"):
        assert kd.find(km, "allset.parent_joint", type="P")
        assert kd.find(km, "allset.unparent_joint", type="P", shift=True)
    assert not kd.find("Armature", "armature.parent_set", type="P")
    # the option box dialogs say why there is no primary axis choice
    assert "Y axis" in joints.AXIS_NOTE and math.isclose(1.0, 1.0)
