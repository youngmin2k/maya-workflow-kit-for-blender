"""Issue #165: Maya pick-walk order and joint display.

Maya pick-walk:
spine's children L_arm, R_arm, neck in creation order; Left / Right walk the siblings in that order and wrap; Down = the
first child; a leaf stays. Controller tags first, hidden bone collections skipped by default, as before.
Kit: operators/joints.py child_order_key / stamp_last, operators/joint_display.py.
"""

from importlib import import_module

import bpy
from mathutils import Vector

import kit

joints = import_module(kit.MODULE + ".operators.joints")
jd = import_module(kit.MODULE + ".operators.joint_display")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
cbm = import_module(kit.MODULE + ".ui.channel_box")

# the fixture skeleton (joint order = Maya creation order)
SKEL = [("root", (0, 10, 0), None), ("spine", (0, 13, 0), "root"), ("L_arm", (3, 15, 0), "spine"),
        ("L_hand", (6, 15, 0), "L_arm"), ("R_arm", (-3, 15, 0), "spine"), ("R_hand", (-6, 15, 0), "R_arm"),
        ("neck", (0, 17, 0), "spine"), ("L_leg", (2, 6, 0), "root")]


def _reset():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _build(order=SKEL):
    _reset()
    arm = bpy.data.armatures.new("skeleton1")
    ob = bpy.data.objects.new("skeleton1", arm)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    pos = {n: Vector((p[0], -p[2], p[1])) for n, p, _ in order}
    for n, _p, parent in order:
        eb = arm.edit_bones.new(n)
        eb.head = pos[n]
        eb.tail = pos[n] + Vector((0, 0, 1))
        if parent:
            eb.parent = arm.edit_bones[parent]
    bpy.ops.object.mode_set(mode='POSE')
    return ob


def _walk(ob, name, direction, skip=True):
    return joints.walk_bone(ob.data.bones[name], direction, skip).name


def test_creation_order_not_names():
    # created z_arm before a_arm: Maya walks in that order (the kit used to sort by name)
    ob = _build([("root", (0, 0, 0), None), ("z_arm", (2, 0, 0), "root"), ("a_arm", (-2, 0, 0), "root"),
                 ("m_arm", (0, 2, 0), "root")])
    assert _walk(ob, "root", "DOWN") == "z_arm"
    assert _walk(ob, "z_arm", "RIGHT") == "a_arm" and _walk(ob, "m_arm", "RIGHT") == "z_arm"   # wraps
    assert _walk(ob, "z_arm", "LEFT") == "m_arm"


def test_reparented_joint_goes_last():
    ob = _build()
    bpy.ops.object.mode_set(mode='EDIT')
    joints.parent_joints(ob, ["L_arm"], "root")          # P to root, then P back to spine
    joints.parent_joints(ob, ["L_arm"], "spine")
    bpy.ops.object.mode_set(mode='POSE')
    kids = [b.name for b in sorted(ob.data.bones["spine"].children, key=joints.child_order_key)]
    assert kids == ["R_arm", "neck", "L_arm"], kids
    assert _walk(ob, "spine", "DOWN") == "R_arm"


def test_new_joint_after_a_reparent_is_still_last():
    ob = _build()
    bpy.ops.object.mode_set(mode='EDIT')
    joints.parent_joints(ob, ["neck"], "spine")
    new = joints.add_joint(ob, ob.matrix_world @ Vector((1, 0, 18)), "spine")
    bpy.ops.object.mode_set(mode='POSE')
    kids = [b.name for b in sorted(ob.data.bones["spine"].children, key=joints.child_order_key)]
    assert kids == ["L_arm", "R_arm", "neck", new], kids


def test_hidden_joint_is_walked_into_collection_hidden_is_skipped():
    ob = _build()
    ob.data.bones["R_arm"].hide = True                   # h: Maya walks into hidden joints
    assert _walk(ob, "L_arm", "RIGHT") == "R_arm"
    coll = ob.data.collections.new("hidden_ctrls")       # a hidden bone collection is skipped (pref on)
    coll.assign(ob.data.bones["R_arm"])
    coll.is_visible = False
    assert _walk(ob, "L_arm", "RIGHT", skip=True) == "R_hand"
    assert _walk(ob, "L_arm", "RIGHT", skip=False) == "R_arm"
    prefs = import_module(kit.MODULE + ".preferences")
    assert prefs.get(bpy.context).pick_walk_skip_hidden_collections is True, "skip-hidden default kept"


def test_operator_walks_in_child_order():
    ob = _build()
    for pb in ob.pose.bones:
        cbm.set_bone_selected(pb, pb.name == "L_arm")
    ob.data.bones.active = ob.data.bones["L_arm"]
    assert bpy.ops.allset.pick_walk_joint(direction='LEFT') == {'FINISHED'}
    assert ob.data.bones.active.name == "neck"


def test_skeleton_menu_reparents_go_last():
    ob = _build()
    sm = import_module(kit.MODULE + ".operators.skeleton_menu")
    bpy.ops.object.mode_set(mode='EDIT')
    end, _f = sm.disconnect_joint(ob, "L_arm")           # the end joint left behind is spine's newest child
    bpy.ops.object.mode_set(mode='POSE')
    kids = [b.name for b in sorted(ob.data.bones["spine"].children, key=joints.child_order_key)]
    assert kids == ["R_arm", "neck", end], kids


# --- joint display -------------------------------------------------------------------------------------------

def test_menu_items():
    assert menu_map.MAP["Display/Transform Display/Local Rotation Axes"] == "allset.local_rotation_axes"
    assert menu_map.MAP["Display/Animation/Joint Size..."] == "allset.joint_size"


def test_radius_row_and_joint_size_scale_the_click_sphere():
    ob = _build()
    b = ob.data.bones["spine"]
    assert b.allset_joint_radius == 1.0, "Maya joint radius default"
    b.allset_joint_radius = 2.0
    r2 = joints.joint_sphere_radius(ob, b)
    bpy.context.scene.allset_joint_size = 0.5
    assert abs(joints.joint_sphere_radius(ob, b) - r2 * 0.5) < 1e-9
    bpy.context.scene.allset_joint_size = 1.0
    assert bpy.ops.allset.joint_size('EXEC_DEFAULT', size=3.0) == {'FINISHED'}
    assert abs(bpy.context.scene.allset_joint_size - 3.0) < 1e-9
    bpy.context.scene.allset_joint_size = 1.0


def test_local_rotation_axes_toggles():
    ob = _build()
    assert not ob.data.show_axes
    assert bpy.ops.allset.local_rotation_axes() == {'FINISHED'}
    assert ob.data.show_axes
    assert bpy.ops.allset.local_rotation_axes() == {'FINISHED'}
    assert not ob.data.show_axes
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    ob.select_set(True)
    assert bpy.ops.allset.local_rotation_axes() == {'FINISHED'}
    assert cube.show_axis and ob.show_axis, "every selected object (Maya: each selected node)"
