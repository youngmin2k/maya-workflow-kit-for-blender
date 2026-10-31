"""#169: rig QA fixes: Set IK/FK Key keys the RP handle's Twist and Pole Vector — or the pole object when a
Pole Vector constraint drives it (Maya 2026) — and the Skeleton menu /
P see only the joints the user picked while the Move tool keeps the skeleton in Edit mode."""

import bpy
from mathutils import Vector

import test_step223_ik_fk as T
from bl_ext.user_default.allset import compat
from bl_ext.user_default.allset.operators import ik_rp, joint_selection, joints


def _paths(ob):
    return {fc.data_path for fc in compat.id_fcurves(ob)} if ob.animation_data else set()


def test_set_ik_fk_key_keys_twist_and_pole_vector():
    arm, handle, con = T._arm()
    assert ik_rp.HELPER in handle.keys()
    T._select(handle)
    assert bpy.ops.allset.ik_fk_key() == {'FINISHED'}
    paths = _paths(handle)
    assert {'["twist"]', '["poleVectorX"]', '["poleVectorY"]', '["poleVectorZ"]'} <= paths, paths


def test_set_ik_fk_key_keys_the_pole_object_not_the_driven_vector():
    arm, handle, con = T._arm()
    loc = bpy.data.objects.new("poleLocator", None)
    bpy.context.scene.collection.objects.link(loc)
    loc.location = T.bl((4, 0, -6))
    ik_rp.set_pole_object(handle, loc)
    T._update()
    T._select(handle)
    assert bpy.ops.allset.ik_fk_key() == {'FINISHED'}
    paths = _paths(handle)
    assert '["twist"]' in paths and not any("poleVector" in p for p in paths), paths
    assert "location" in _paths(loc)        # Maya keys the constraint's target (pv locator translate)


def test_edit_mode_pick_is_the_clicked_joint_not_its_subtree():
    arm, handle, con = T._arm()
    T._select(arm)
    bpy.ops.object.mode_set(mode='EDIT')
    joint_selection.select_edit(bpy.context, arm, "shoulder")
    # W carries the subtree (every bone selected), the Skeleton menu sees the pick
    assert all(eb.select for eb in arm.data.edit_bones)
    assert joints.selected_joint_names(arm) == ["shoulder"]
    joint_selection.select_edit(bpy.context, arm, "wrist", shift=True)
    assert joints.selected_joint_names(arm) == ["shoulder"]     # wrist is inside shoulder's subtree: still one pick
    joint_selection.select_edit(bpy.context, arm, "elbow")
    assert joints.selected_joint_names(arm) == ["elbow"]
    # a plain Blender selection (bone bodies only) still counts
    for eb in arm.data.edit_bones:
        eb.select = eb.select_head = eb.select_tail = False
    arm.data.edit_bones["wrist"].select = True
    assert joints.selected_joint_names(arm) == ["wrist"]
    bpy.ops.object.mode_set(mode='OBJECT')
    assert (Vector(arm.location) - Vector()).length < 1e-9
