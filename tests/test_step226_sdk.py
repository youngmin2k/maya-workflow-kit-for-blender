"""Lane D (Issue #136): Set Driven Key like Maya (operators/driven_key.py).

Expected: curve shapes
of 2 / 3 / 4 keys (29 samples each, auto tangents, infinity Constant), two drivers on one channel = blendWeighted sum
(20 pairs), rotate 10 / 10 -> 60, a third driver (0, 0) (1, 5) -> 65."""

import math
from importlib import import_module

import bpy
from mathutils import Vector

import kit

sdk = import_module(kit.MODULE + ".operators.driven_key")
cb = import_module(kit.MODULE + ".ui.channel_box")
joints = import_module(kit.MODULE + ".operators.joints")

TOL = 1e-4


def _clear():
    st = bpy.context.window_manager.allset_sdk
    st.open = False
    st.driven.clear()
    st.driver.object = None
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for coll in (bpy.data.objects, bpy.data.armatures, bpy.data.meshes, bpy.data.textures):
        for idb in list(coll):
            coll.remove(idb)


def _empty(name, **props):
    ob = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(ob)
    for k, v in props.items():
        ob[k] = float(v)
    return ob


def _select(*obs, active=None):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or obs[-1]


def _set(node, key, value):
    sdk.set_raw_value(node, key, value)
    node.id_data.update_tag()
    bpy.context.view_layer.update()


def _key(drv, dattr, dv, tgt, attr, v):
    """Maya setDrivenKeyframe -cd drv.dattr -dv dv -v v (the other drivers sit at 0 = their keys at 0)."""
    _set(drv, dattr, dv)
    fc = sdk.sdk_fcurve(tgt, attr)
    if fc is not None:
        fc.mute = True                   # what the window does while posing (hold_driven)
    sdk.set_raw_value(tgt, attr, v)
    sdk.set_key(tgt, attr, drv, dattr)
    _set(drv, dattr, 0.0)


def _read(node, key):
    bpy.context.view_layer.update()
    return sdk.raw_value(node, key)


def test_maya_slopes_rule():
    pts = [(0, 0), (3, 20), (10, 90)]
    assert sdk.maya_slopes(pts) == [0.0, 9.0, 0.0]
    assert sdk.maya_slopes([(0, 0), (2, 50), (6, 40), (10, 90)]) == [0.0, 0.0, 0.0, 0.0]


def _rz(ob):
    bpy.context.view_layer.update()
    return math.degrees(ob.rotation_euler[2])


def _load_driver(drv, attr):
    _select(drv)
    cb.set_selected_channels([attr])
    assert bpy.ops.allset.sdk_load(which='DRIVER') == {'FINISHED'}


def test_rotate_two_and_three_drivers_through_the_window():
    """Maya: curl (0,0)(10,90) + spread (0,0)(10,-30) on rz -> 60; fist (0,0)(1,5) -> 65. Window flow: Key /
    pose held while open / Go to Previous / Next / Close."""
    _clear()
    drv = _empty("drv", curl=0, spread=0, fist=0)
    tgt = _empty("tgt")
    st = bpy.context.window_manager.allset_sdk
    bpy.ops.allset.sdk_window()
    _load_driver(drv, "cp:curl")
    _select(tgt)
    cb.set_selected_channels(["rz"])
    assert bpy.ops.allset.sdk_load(which='DRIVEN') == {'FINISHED'}

    def pose(driver_values, rz=None):
        for k, v in driver_values.items():
            cb.set_value(drv, "cp:" + k, float(v))
        bpy.context.view_layer.update()
        if rz is not None:
            _select(tgt)
            cb.apply_entry("rz", str(rz))        # Channel Box edit: held by the muted driver

    pose({"curl": 0})
    assert bpy.ops.allset.sdk_key() == {'FINISHED'}
    pose({"curl": 10}, 90)
    bpy.ops.allset.sdk_key()
    pose({"curl": 0})
    _load_driver(drv, "cp:spread")
    pose({"spread": 0})
    bpy.ops.allset.sdk_key()
    pose({"spread": 10}, -30)
    bpy.ops.allset.sdk_key()
    pose({"curl": 10, "spread": 10})
    assert abs(_rz(tgt) - 60.0) < TOL, _rz(tgt)
    assert sdk.is_blend(sdk.sdk_fcurve(tgt, "rz"))
    # third driver: keyed while curl / spread give 60 -> its input keeps only its own part
    _load_driver(drv, "cp:fist")
    pose({"fist": 0})
    bpy.ops.allset.sdk_key()
    pose({"fist": 1}, 65)
    bpy.ops.allset.sdk_key()
    blend = sdk.sdk_fcurve(tgt, "rz")
    assert len(blend.driver.variables) == 3 and not blend.mute
    assert abs(_rz(tgt) - 65.0) < TOL, _rz(tgt)
    pose({"curl": 0, "spread": 0})
    assert abs(_rz(tgt) - 5.0) < TOL, ("Maya: fist alone gives its own curve", _rz(tgt))
    pose({"curl": 10, "spread": 10})
    # Go to Previous / Next walk the loaded driver's keys (fist 0 / 1)
    assert bpy.ops.allset.sdk_go(direction='PREVIOUS') == {'FINISHED'}
    assert abs(drv["fist"]) < 1e-6 and abs(_rz(tgt) - 60.0) < TOL
    assert bpy.ops.allset.sdk_go(direction='NEXT') == {'FINISHED'}
    assert abs(drv["fist"] - 1) < 1e-6 and abs(_rz(tgt) - 65.0) < TOL
    assert bpy.ops.allset.sdk_go(direction='NEXT') == {'CANCELLED'}
    # posing the summed channel holds the typed value while the window is open; Close drops it
    pose({}, 30)
    assert blend.mute and abs(_rz(tgt) - 30.0) < 1e-3, _rz(tgt)
    bpy.ops.allset.sdk_close()
    assert not st.open and not blend.mute and abs(_rz(tgt) - 65.0) < TOL
    # release_all after a load-like reset unmutes summed channels too
    blend.mute = True
    assert sdk.release_all() >= 1 and not blend.mute


def test_blend_shape_weight_is_a_driven_node():
    _clear()
    me = bpy.data.meshes.new("pSphere1")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    head = bpy.data.objects.new("pSphere1", me)
    bpy.context.scene.collection.objects.link(head)
    head.shape_key_add(name="Basis")
    head.shape_key_add(name="smile").value = 0.0   # Blender 5.x starts a new key at 1.0
    key = me.shape_keys
    key.name = "blendShape1"
    drv = _empty("ctrl", curl=0, spread=0)
    bpy.ops.allset.sdk_window()
    _load_driver(drv, "cp:curl")
    _select(head)
    cb.set_selected_channels([])
    bpy.ops.allset.sdk_load(which='DRIVEN')
    st = bpy.context.window_manager.allset_sdk
    nodes = sdk.driven_nodes(st)
    assert nodes[0] == head and nodes[1] == key, nodes
    assert sdk.node_label(nodes[1]) == "blendShape1" and sdk.channels(key) == ["bs:smile"]
    bpy.ops.allset.sdk_pick(which='NODE', index=1)
    assert [i.label for i in st.driven_items] == ["smile"]
    bpy.ops.allset.sdk_pick(which='DRIVEN', key="bs:smile")
    bpy.ops.allset.sdk_key()
    fc = sdk.sdk_fcurve(key, "bs:smile")
    assert fc is not None and fc.id_data == key and fc.data_path == 'key_blocks["smile"].value'
    cb.set_value(drv, "cp:curl", 10.0)
    bpy.context.view_layer.update()
    key.key_blocks["smile"].value = 1.0
    sdk._on_posed(key.name, 'KEY', fc.data_path, -1)     # = the msgbus notification of that edit
    assert fc.mute
    bpy.ops.allset.sdk_key()
    assert not fc.mute
    cb.set_value(drv, "cp:curl", 5.0)
    assert abs(_read(key, "bs:smile") - 0.5) < TOL, _read(key, "bs:smile")
    # a second driver on the target weight: inputs on the shape Key ID
    cb.set_value(drv, "cp:curl", 0.0)
    _load_driver(drv, "cp:spread")
    bpy.ops.allset.sdk_key()
    blend = sdk.sdk_fcurve(key, "bs:smile")
    tex = sdk.helper(create=False)
    assert sdk.is_blend(blend) and all(v.targets[0].id == tex for v in blend.driver.variables)
    assert not any(k.startswith("allset_sdk_") for k in key.keys())
    cb.set_value(drv, "cp:curl", 5.0)
    assert abs(_read(key, "bs:smile") - 0.5) < TOL
    bpy.ops.allset.sdk_close()


def test_constraint_weight_is_a_driven_node():
    _clear()
    loc = _empty("locator1")
    tgt = _empty("pCube1")
    con = tgt.constraints.new('COPY_LOCATION')
    con.target = loc
    drv = _empty("ctrl", curl=0)
    bpy.ops.allset.sdk_window()
    _load_driver(drv, "cp:curl")
    _select(tgt)
    bpy.ops.allset.sdk_load(which='DRIVEN')
    st = bpy.context.window_manager.allset_sdk
    nodes = sdk.driven_nodes(st)
    assert nodes[1] == con and sdk.node_label(con) == "pCube1_pointConstraint1", sdk.node_label(con)
    assert sdk.channels(con) == ["cw"] and sdk.attr_label(con, "cw") == "locator1W0"
    st.driven_index = 1
    st.driven_attrs = "cw"
    bpy.ops.allset.sdk_key()                     # curl 0 -> influence 1
    fc = sdk.sdk_fcurve(con, "cw")
    assert fc.data_path == 'constraints["Copy Location"].influence'
    cb.set_value(drv, "cp:curl", 10.0)
    con.influence = 0.0
    sdk._on_posed(tgt.name, 'OBJECT', fc.data_path, -1)
    bpy.ops.allset.sdk_key()
    cb.set_value(drv, "cp:curl", 5.0)
    assert abs(_read(con, "cw") - 0.5) < TOL
    # a multi-target group's Maya weight property (lane C) is driven instead of the influence
    tgt["allset_w_Copy Location"] = 1.0
    c = sdk.chan(con, "cw")
    assert c.path == '["allset_w_Copy Location"]' and c.struct == tgt
    bpy.ops.allset.sdk_close()


def test_ik_blend_and_hidden_inputs_on_a_joint():
    """ikBlend is the handle's custom attribute: it lists like any custom channel. Two drivers on a joint
    channel put the hidden inputs on the pose bone."""
    _clear()
    handle = _empty("ikHandle1", ikBlend=1)
    assert "cp:ikBlend" in sdk.channels(handle)
    drv = _empty("ctrl", curl=0, spread=0)
    arm = joints.new_skeleton(bpy.context)
    parent = None
    for p in ((0, 0, 0), (0, 0, 1), (0, 0, 2)):
        parent = joints.add_joint(arm, Vector(p), parent, length=0.5)
    joints.finish(bpy.context, arm, ["joint1", "joint2", "joint3"])
    bpy.ops.object.mode_set(mode='OBJECT')
    pb = arm.pose.bones["joint2"]
    _key(drv, "cp:curl", 0, pb, "rz", 0)
    _key(drv, "cp:curl", 10, pb, "rz", math.radians(90))
    _key(drv, "cp:spread", 0, pb, "rz", 0)
    _key(drv, "cp:spread", 10, pb, "rz", math.radians(-30))
    blend = sdk.sdk_fcurve(pb, "rz")
    assert sdk.is_blend(blend) and blend.data_path == 'pose.bones["joint2"].rotation_euler'
    t0 = blend.driver.variables[0].targets[0]
    assert t0.id == sdk.helper(create=False) and t0.id_type == 'TEXTURE' and t0.data_path.startswith('["allset_sdk_')
    assert not any(k.startswith("allset_sdk_") for k in pb.keys()) and cb.custom_keys(pb) == []
    drv["curl"] = drv["spread"] = 10.0
    drv.update_tag()
    bpy.context.view_layer.update()
    assert abs(math.degrees(pb.rotation_euler[2]) - 60.0) < TOL, math.degrees(pb.rotation_euler[2])
