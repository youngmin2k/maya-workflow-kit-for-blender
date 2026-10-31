"""Set Driven Key, pose-mode Constrain, Add / Edit / Delete Attribute, Blend Shape, Quick Rig (Rigify).
GUI: tests/gui/gui_step62_sdk.py (rigging_06 hand order)."""

import math
from importlib import import_module

import bpy
from mathutils import Vector

import kit

sdk = import_module(kit.MODULE + ".operators.driven_key")
rig = import_module(kit.MODULE + ".operators.rig_tools")
joints = import_module(kit.MODULE + ".operators.joints")
cb = import_module(kit.MODULE + ".ui.channel_box")
multi = import_module(kit.MODULE + ".operators.constrain_multi")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_data = import_module(kit.MODULE + ".ui.menu_data")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")
notices = import_module(kit.MODULE + ".ui.notices")


def _clear():
    st = bpy.context.window_manager.allset_sdk
    st.open = False
    st.driven.clear()
    st.driver.object = None
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for arm in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)


def _select(*obs, active=None):
    for o in bpy.context.scene.objects:   # view_layer.objects yields None for removed objects until a sync
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or obs[-1]


def _expect_error(call, text):
    try:
        call()
    except RuntimeError as ex:   # an operator reporting ERROR raises when called from Python
        assert text in str(ex), ex
    else:
        raise AssertionError(f"expected an error: {text}")


def _locator_and_cube():
    sc = bpy.context.scene
    loc = bpy.data.objects.new("locator1", None)
    sc.collection.objects.link(loc)
    cube = bpy.data.objects.new("pCube1", bpy.data.meshes.new("pCube1"))
    sc.collection.objects.link(cube)
    return loc, cube


def _load(which, node_sel, channels):
    _select(*node_sel)
    cb.set_selected_channels(channels)
    assert bpy.ops.allset.sdk_load(which=which) == {'FINISHED'}


def _ry(cube):
    bpy.context.view_layer.update()
    return math.degrees(cube.rotation_euler[1])


def test_set_driven_key_rigging_06_order():
    """Maya: locator tx drives cube ry; Key at 0/0 and 1/90 -> tx 0.5 gives ry 45."""
    _clear()
    loc, cube = _locator_and_cube()
    bpy.ops.allset.sdk_window()
    st = bpy.context.window_manager.allset_sdk
    assert st.open
    _load('DRIVER', [loc], ["tx"])
    _load('DRIVEN', [cube], ["ry"])
    assert sdk.driver_node(st) == loc and st.driver_attr == "tx" and sdk.driven_keys(st) == ["ry"]
    assert bpy.ops.allset.sdk_key() == {'FINISHED'}
    fc = sdk.sdk_fcurve(cube, "ry")
    assert fc is not None and len(fc.keyframe_points) == 1 and not fc.modifiers
    assert cb.channel_state(cube, "ry") == 'DRIVEN'
    # pose: driver through the Channel Box, then the driven channel (held by the muted driver)
    _select(loc)
    cb.apply_entry("tx", "1")
    _select(cube)
    cb.apply_entry("ry", "90")
    assert fc.mute, "a Channel Box edit of a driven channel holds the typed value while the window is open"
    assert abs(_ry(cube) - 90) < 1e-3, _ry(cube)
    assert bpy.ops.allset.sdk_key() == {'FINISHED'}
    assert not fc.mute and len(fc.keyframe_points) == 2
    _select(loc)
    cb.apply_entry("tx", "0.5")
    assert abs(_ry(cube) - 45) < 1e-3, _ry(cube)
    cb.apply_entry("tx", "2")
    assert abs(_ry(cube) - 90) < 1e-3, "constant after the last key (Maya infinity Constant)"
    # same driver value again = replace the key
    cb.apply_entry("tx", "1")
    _select(cube)
    cb.apply_entry("ry", "60")
    bpy.ops.allset.sdk_key()
    assert len(fc.keyframe_points) == 2 and abs(_ry(cube) - 60) < 1e-3
    # Go to Previous / Next = driver value at the neighbouring key
    assert bpy.ops.allset.sdk_go(direction='PREVIOUS') == {'FINISHED'}
    assert abs(loc.location[0]) < 1e-6 and abs(_ry(cube)) < 1e-3
    assert bpy.ops.allset.sdk_go(direction='NEXT') == {'FINISHED'}
    assert abs(loc.location[0] - 1) < 1e-6
    assert bpy.ops.allset.sdk_go(direction='NEXT') == {'CANCELLED'}
    # a pose not keyed is dropped on Close
    _select(cube)
    cb.apply_entry("ry", "10")
    assert fc.mute
    bpy.ops.allset.sdk_close()
    assert not st.open and not fc.mute and abs(_ry(cube) - 60) < 1e-3


def test_driven_value_not_held_when_window_closed():
    _clear()
    loc, cube = _locator_and_cube()
    bpy.ops.allset.sdk_window()
    _load('DRIVER', [loc], ["tx"])
    _load('DRIVEN', [cube], ["ry"])
    bpy.ops.allset.sdk_key()
    bpy.ops.allset.sdk_close()
    _select(cube)
    cb.apply_entry("ry", "45")
    assert not sdk.sdk_fcurve(cube, "ry").mute and abs(_ry(cube)) < 1e-3, "the driver wins (Blender / Maya)"


def test_joint_and_custom_attribute_drivers():
    """A control's curl (custom) drives joint2 Rotate Z (pose bone)."""
    _clear()
    ctrl = bpy.data.objects.new("nurbsCircle1", None)
    bpy.context.scene.collection.objects.link(ctrl)
    _select(ctrl)
    bpy.ops.allset.add_attribute(long_name="curl", data_type='FLOAT', use_min=True, minimum=0, use_max=True,
                                   maximum=10, default=0)
    assert "curl" in ctrl.keys() and cb.channel_label("cp:curl") == "Curl"
    ui = ctrl.id_properties_ui("curl").as_dict()
    assert ui["min"] == 0 and ui["max"] == 10, ui
    arm = joints.new_skeleton(bpy.context)
    parent = None
    for p in ((0, 0, 0), (0, 0, 1), (0, 0, 2)):
        parent = joints.add_joint(arm, Vector(p), parent, length=0.5)
    joints.finish(bpy.context, arm, ["joint1", "joint2", "joint3"])
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.allset.sdk_window()
    _load('DRIVER', [ctrl], ["cp:curl"])
    _select(arm)
    bpy.ops.object.mode_set(mode='POSE')
    for pb in arm.pose.bones:
        cb.set_bone_selected(pb, pb.name == "joint2")
    arm.data.bones.active = arm.data.bones["joint2"]
    cb.set_selected_channels(["rz"])
    bpy.ops.allset.sdk_load(which='DRIVEN')
    bpy.ops.allset.sdk_key()
    pb = arm.pose.bones["joint2"]
    fc = sdk.sdk_fcurve(pb, "rz")
    assert fc is not None and fc.data_path == 'pose.bones["joint2"].rotation_euler' and fc.array_index == 2
    assert fc.driver.variables[0].targets[0].data_path == '["curl"]'
    cb.set_value(ctrl, "cp:curl", 10.0)   # the Channel Box path (tags the control for the driver)
    cb.apply_entry("rz", "90")          # pose bone channel (lead = joint2)
    bpy.ops.allset.sdk_key()
    cb.set_value(ctrl, "cp:curl", 5.0)
    bpy.context.view_layer.update()
    assert abs(math.degrees(pb.rotation_euler[2]) - 45) < 1e-3, math.degrees(pb.rotation_euler[2])
    bpy.ops.allset.sdk_close()


def test_constrain_in_pose_mode_goes_on_the_joint():
    _clear()
    arm = joints.new_skeleton(bpy.context)
    parent = None
    for p in ((0, 0, 0), (0, 0, 1)):
        parent = joints.add_joint(arm, Vector(p), parent, length=0.5)
    joints.finish(bpy.context, arm, ["joint1", "joint2"])
    bpy.ops.object.mode_set(mode='OBJECT')
    ctrl = bpy.data.objects.new("nurbsCircle1", None)
    bpy.context.scene.collection.objects.link(ctrl)
    ctrl.location = (1, 0, 1)
    _select(ctrl, arm, active=arm)
    bpy.ops.object.mode_set(mode='POSE')
    for pb in arm.pose.bones:
        cb.set_bone_selected(pb, pb.name == "joint2")
    arm.data.bones.active = arm.data.bones["joint2"]
    assert bpy.ops.allset.constrain(type='COPY_ROTATION') == {'FINISHED'}
    con = arm.pose.bones["joint2"].constraints[-1]
    # a joint copies the control's Maya axes through a hidden helper that follows the control
    helper = multi.helper_of(con)
    assert con.type == 'COPY_ROTATION' and helper is not None and not arm.constraints
    assert helper.constraints[0].target == ctrl
    assert bpy.ops.allset.constrain(type='CHILD_OF') == {'FINISHED'}
    assert multi.group_type(arm.pose.bones["joint2"].constraints[-1]) == "parentConstraint"
    # no target selected -> nothing, with Maya's Error
    bpy.ops.object.mode_set(mode='OBJECT')
    _select(arm)
    bpy.ops.object.mode_set(mode='POSE')
    for pb in arm.pose.bones:
        cb.set_bone_selected(pb, pb.name == "joint1")
    arm.data.bones.active = arm.data.bones["joint1"]
    try:
        bpy.ops.allset.constrain(type='COPY_LOCATION')
        raise AssertionError("no Maya error")
    except RuntimeError as ex:
        assert "Target list was empty or contained no valid targets." in str(ex), ex
    assert not arm.pose.bones["joint1"].constraints
    bpy.ops.object.mode_set(mode='OBJECT')
    # object mode: on the active object, target = the other selected
    cube = bpy.data.objects.new("pCube1", None)
    bpy.context.scene.collection.objects.link(cube)
    _select(ctrl, cube, active=cube)
    bpy.ops.allset.constrain(type='COPY_LOCATION')
    assert cube.constraints[-1].type == 'COPY_LOCATION' and cube.constraints[-1].target == ctrl


def test_add_edit_delete_attribute():
    _clear()
    a = bpy.data.objects.new("a", None)
    b = bpy.data.objects.new("b", None)
    for o in (a, b):
        bpy.context.scene.collection.objects.link(o)
    _select(a, b)
    assert bpy.ops.allset.add_attribute(long_name="fingerCurl", data_type='INT', use_min=True, minimum=-2,
                                          use_max=True, maximum=5, default=9) == {'FINISHED'}
    for o in (a, b):
        assert o["fingerCurl"] == 5 and isinstance(o["fingerCurl"], int), "default clamped to max"
    assert cb.channel_label("cp:fingerCurl") == "Finger Curl"
    assert "cp:fingerCurl" in cb._visible_channels(b)
    _expect_error(lambda: bpy.ops.allset.add_attribute(long_name="1bad name"), "not a valid attribute name")
    bpy.ops.allset.add_attribute(long_name="flag", data_type='BOOL', default=1)
    assert b["flag"] is True
    # Edit = rename + limits, keys follow the rename
    b.keyframe_insert('["fingerCurl"]', frame=1)
    cb.set_selected_channels(["cp:fingerCurl"])
    assert bpy.ops.allset.edit_attribute(attribute="fingerCurl", long_name="curl", data_type='INT',
                                           use_min=True, minimum=0, use_max=True, maximum=10,
                                           default=0) == {'FINISHED'}
    assert "curl" in b.keys() and "fingerCurl" not in b.keys()
    assert cb.fcurve(b, "cp:curl") is not None and cb.selected_channels() == ["cp:curl"]
    assert b.id_properties_ui("curl").as_dict()["max"] == 10
    # Delete = the attribute, its keys
    assert bpy.ops.allset.delete_attribute() == {'FINISHED'}
    assert "curl" not in a.keys() and "curl" not in b.keys() and cb.fcurve(b, "cp:curl") is None


def test_blend_shape_maya_order():
    _clear()

    def tri(name, z):
        me = bpy.data.meshes.new(name)
        me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, z)], [], [(0, 1, 2)])
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        return ob
    head, smile = tri("head", 0), tri("smile", 0.5)
    _select(smile, head)
    assert bpy.ops.allset.blend_shape() == {'FINISHED'}
    keys = [k.name for k in head.data.shape_keys.key_blocks]
    assert keys == ["Basis", "smile"] and head.data.shape_keys.key_blocks["smile"].value == 0
    other = bpy.data.objects.new("quad", bpy.data.meshes.new("quad"))
    other.data.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
    bpy.context.scene.collection.objects.link(other)
    _select(other, head)
    _expect_error(bpy.ops.allset.blend_shape, "different vertex count")


def test_quick_rig_enables_rigify_and_adds_a_metarig():
    _clear()
    import addon_utils
    try:
        assert bpy.ops.allset.quick_rig() == {'FINISHED'}
        assert "rigify" in bpy.context.preferences.addons
        arm = bpy.context.active_object
        assert arm is not None and arm.type == 'ARMATURE' and len(arm.data.bones) > 20
    finally:
        addon_utils.disable("rigify", default_set=True)


def test_menus_shelf_and_notices():
    m = menu_map.MAP
    assert menu_map.spec("Key/Set Driven Key/Set...") is not None
    assert m["Key/Set Driven Key/Set..."] == "allset.sdk_window"
    assert m["Key/Set Driven Key/Go to Next"][0] == "allset.sdk_go"
    assert m["Deform/Blend Shape"] == "allset.blend_shape" == m["Deform/Blend Shape#2/Add"]
    for path in ("Constrain/Parent", "Constrain/Orient", "Constrain/Point", "Constrain/Aim"):
        assert m[path][0] == "allset.constrain", path
    for label in ("Add Attribute...", "Edit Attribute...", "Delete Attribute..."):
        # the Attributes section comes from menu_data (tools/gen_menu_data.py RUNTIME_LABELS)
        assert (label,) in menu_data.MENUS["mainModifyMenu"][3] and m["Modify/" + label].startswith("allset.")
    assert m["Skeleton/Quick Rig"] == "allset.quick_rig"
    assert "Skeleton/Quick Rig" in notices.NOTICES and "Skeleton/HumanIK" in notices.NOTICES
    by = shelf_map.BY_COMMAND
    assert by["CreateBlendShape"][0] == "allset.blend_shape"
    assert by["SetDrivenKey"][0] == "allset.sdk_window" and by["QuickRigEditor"][0] == "allset.quick_rig"
    assert by["ParentConstraint"][0][0] == "allset.constrain"


def test_nice_names():
    assert [cb.nice_name(n) for n in ("fingerCurl", "curl", "ik_blend2", "translateX")] == \
        ["Finger Curl", "Curl", "Ik Blend 2", "Translate X"]
