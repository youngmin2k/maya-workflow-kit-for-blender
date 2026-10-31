"""#186: Set Driven Key blendWeighted inputs live on their own data-block (operators/driven_key.py).

Two drivers summed on one transform channel read a stale input now and then while the inputs sat on the driven ID
itself; on the hidden helper Texture the sum is right every time. Older files move over on load (once, no undo step
of their own), a duplicated object gets its own inputs, inputs no channel reads are dropped."""

import math
import os
import tempfile
from importlib import import_module

import bpy

import kit

sdk = import_module(kit.MODULE + ".operators.driven_key")

N = 2000


def _clear():
    for coll in (bpy.data.objects, bpy.data.armatures, bpy.data.meshes, bpy.data.textures):
        for idb in list(coll):
            coll.remove(idb)


def _empty(name, **props):
    ob = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(ob)
    for k, v in props.items():
        ob[k] = float(v)
    return ob


def _key(drv, dkey, dv, tgt, key, v):
    sdk.set_raw_value(drv, dkey, dv)
    drv.update_tag()
    bpy.context.view_layer.update()
    sdk.set_raw_value(tgt, key, v)
    sdk.set_key(tgt, key, drv, dkey)
    bpy.context.view_layer.update()


def _rig(drv, tgt):
    """curl (0, 0) (10, 90 deg) + spread (0, 0) (10, -30 deg) summed on tgt rz (Maya: 10 / 10 -> 60)."""
    for k in ("curl", "spread"):
        sdk.set_raw_value(drv, "cp:" + k, 0.0)
    _key(drv, "cp:curl", 0, tgt, "rz", 0.0)
    _key(drv, "cp:curl", 10, tgt, "rz", math.radians(90))
    sdk.set_raw_value(drv, "cp:curl", 0.0)
    _key(drv, "cp:spread", 0, tgt, "rz", 0.0)
    _key(drv, "cp:spread", 10, tgt, "rz", math.radians(-30))
    sdk.set_raw_value(drv, "cp:spread", 0.0)
    drv.update_tag()
    bpy.context.view_layer.update()
    assert sdk.is_blend(sdk.sdk_fcurve(tgt, "rz"))


def _pose(drv, curl, spread):
    drv["curl"], drv["spread"] = float(curl), float(spread)
    drv.update_tag()
    bpy.context.view_layer.update()


def _want(curl, spread):
    return 90.0 * (curl / 10.0) + (-30.0) * (spread / 10.0) if curl in (0, 10) and spread in (0, 10) else None


def _stale_count(drv, tgt):
    stale = 0
    for k in range(1, N + 1):
        curl, spread = (10 if k % 2 else 0), (10 if k % 3 == 0 else 0)
        _pose(drv, curl, spread)
        if abs(math.degrees(tgt.rotation_euler[2]) - _want(curl, spread)) > 1e-4:
            stale += 1
    return stale


def test_inputs_on_the_helper_never_stale():
    _clear()
    drv = _empty("drv", curl=0, spread=0)
    tgt = _empty("tgt")
    _rig(drv, tgt)
    tex = sdk.helper(create=False)
    assert tex is not None and tex.name.startswith(".") and tex.use_fake_user and tex.type == 'NONE'
    assert tex.users == 1, tex.users          # only the fake user: no material / brush uses it
    assert not any(k.startswith(sdk.INPUT_PROP) for k in tgt.keys())
    stale = _stale_count(drv, tgt)
    print(f"STEP280 stale {stale}/{N} blender {bpy.app.version_string}")
    assert stale == 0, stale


def test_driver_on_the_driven_object_itself():
    """The driver attributes on the driven object (Maya: a custom attribute of the same node)."""
    _clear()
    tgt = _empty("tgt", curl=0, spread=0)
    _rig(tgt, tgt)
    stale = _stale_count(tgt, tgt)
    assert stale == 0, stale


def _old_layout(drv, tgt, host_path=""):
    """What 0.6.x wrote: inputs ``allset_sdk_<n>`` on the driven ID (``host_path`` = the pose bone), each with its
    own SDK driver, and a SUM driver on rz over them."""
    host = tgt.path_resolve(host_path) if host_path else tgt
    prefix = host_path
    blend_path = (host_path + "." if host_path else "") + "rotation_euler"
    for i, (dk, deg) in enumerate((("curl", 90), ("spread", -30))):
        name = f"allset_sdk_{i}"
        host[name] = 0.0
        fc = tgt.driver_add(f'{prefix}["{name}"]')
        for m in list(fc.modifiers):
            fc.modifiers.remove(m)
        while len(fc.keyframe_points):
            fc.keyframe_points.remove(fc.keyframe_points[0])
        fc.driver.type = 'AVERAGE'
        v = fc.driver.variables.new()
        v.name = "sdk"
        v.targets[0].id = drv
        v.targets[0].data_path = f'["{dk}"]'
        fc.keyframe_points.insert(0, 0)
        fc.keyframe_points.insert(10, math.radians(deg))
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
        fc.extrapolation = 'CONSTANT'
    blend = tgt.driver_add(blend_path, 2)
    for m in list(blend.modifiers):
        blend.modifiers.remove(m)
    while len(blend.keyframe_points):
        blend.keyframe_points.remove(blend.keyframe_points[0])
    blend.driver.type = 'SUM'
    for i in range(2):
        v = blend.driver.variables.new()
        v.name = "sdk" if i == 0 else f"sdk{i}"
        v.targets[0].id = tgt
        v.targets[0].data_path = f'{prefix}["allset_sdk_{i}"]'
    return host


def _save(path):
    bpy.ops.wm.save_as_mainfile(filepath=path)


def _open(path):
    bpy.ops.wm.open_mainfile(filepath=path)


def _check_migrated(host_path=""):
    tgt = bpy.data.objects["tgt"]
    drv = bpy.data.objects["drv"]
    host = tgt.path_resolve(host_path) if host_path else tgt
    tex = sdk.helpers()
    assert len(tex) == 1, [t.name for t in tex]
    tex = tex[0]
    assert sorted(k for k in tex.keys() if k.startswith(sdk.INPUT_PROP)) == ["allset_sdk_0", "allset_sdk_1"]
    assert not any(k.startswith(sdk.INPUT_PROP) for k in host.keys())
    assert all(not fc.data_path.endswith('_0"]') and not fc.data_path.endswith('_1"]')
               for fc in tgt.animation_data.drivers), [fc.data_path for fc in tgt.animation_data.drivers]
    blend = tgt.animation_data.drivers.find((host_path + "." if host_path else "") + "rotation_euler", index=2)
    assert sdk.is_blend(blend) and all(v.targets[0].id == tex for v in blend.driver.variables)
    rot = (host if host_path else tgt).rotation_euler
    for curl, spread in ((10, 10), (10, 0), (0, 10), (0, 0)):
        _pose(drv, curl, spread)
        assert abs(math.degrees(rot[2]) - _want(curl, spread)) < 1e-4, (curl, spread, math.degrees(rot[2]))
    return tex


def test_old_file_moves_on_load_once_and_survives_save_reopen_undo():
    _clear()
    drv = _empty("drv", curl=0, spread=0)
    tgt = _empty("tgt")
    _old_layout(drv, tgt)
    folder = tempfile.mkdtemp()
    old = os.path.join(folder, "old.blend")
    _save(old)
    _open(old)
    _check_migrated()
    assert sdk.sync() == (0, 0, 0), "a second pass changes nothing"
    again = os.path.join(folder, "again.blend")
    _save(again)
    _open(again)
    _check_migrated()
    assert sdk.sync() == (0, 0, 0)
    # undo past the load's first step keeps the moved inputs (the move is part of the loaded state)
    bpy.ops.ed.undo_push(message="step280 a")
    bpy.data.objects["drv"].location.x = 3.0
    bpy.ops.ed.undo_push(message="step280 b")
    for _ in range(3):
        try:
            bpy.ops.ed.undo()
        except RuntimeError:
            break
    assert bpy.data.objects["drv"].location.x == 0.0, "undo ran"
    _check_migrated()


def test_old_joint_inputs_move_on_load():
    from mathutils import Vector
    joints = import_module(kit.MODULE + ".operators.joints")
    _clear()
    drv = _empty("drv", curl=0, spread=0)
    arm = joints.new_skeleton(bpy.context)
    parent = None
    for p in ((0, 0, 0), (0, 0, 1), (0, 0, 2)):
        parent = joints.add_joint(arm, Vector(p), parent, length=0.5)
    joints.finish(bpy.context, arm, ["joint1", "joint2", "joint3"])
    bpy.ops.object.mode_set(mode='OBJECT')
    arm.name = "tgt"
    _old_layout(drv, arm, 'pose.bones["joint2"]')
    path = os.path.join(tempfile.mkdtemp(), "old_joint.blend")
    _save(path)
    _open(path)
    _check_migrated('pose.bones["joint2"]')


def test_key_on_an_old_channel_moves_it_first():
    """A file opened with the kit off keeps the old layout until a Key on that channel (or the next load)."""
    _clear()
    drv = _empty("drv", curl=0, spread=0, fist=0)
    tgt = _empty("tgt")
    _old_layout(drv, tgt)
    _key(drv, "cp:fist", 0, tgt, "rz", 0.0)
    blend = sdk.sdk_fcurve(tgt, "rz")
    tex = sdk.helper(create=False)
    assert len(blend.driver.variables) == 3 and all(v.targets[0].id == tex for v in blend.driver.variables)
    assert not any(k.startswith(sdk.INPUT_PROP) for k in tgt.keys())


def test_duplicate_gets_its_own_inputs_and_unused_inputs_go():
    _clear()
    drv = _empty("drv", curl=0, spread=0)
    tgt = _empty("tgt")
    _rig(drv, tgt)
    for o in bpy.context.scene.objects:
        o.select_set(o == tgt)
    bpy.context.view_layer.objects.active = tgt
    assert bpy.ops.object.duplicate() == {'FINISHED'}
    dup = bpy.context.active_object
    assert dup != tgt
    sdk.sync()
    paths = [{v.targets[0].data_path for v in sdk.sdk_fcurve(o, "rz").driver.variables} for o in (tgt, dup)]
    assert len(paths[0]) == 2 and not paths[0] & paths[1], paths
    tex = sdk.helper(create=False)
    assert len([k for k in tex.keys() if k.startswith(sdk.INPUT_PROP)]) == 4
    _pose(drv, 10, 10)
    for o in (tgt, dup):
        assert abs(math.degrees(o.rotation_euler[2]) - 60.0) < 1e-4, o.name
    # the copy's curves are its own: re-keying the original leaves the copy alone
    _key(drv, "cp:curl", 10, tgt, "rz", math.radians(100))     # 100 - (-30) = 130 on the curl input
    _pose(drv, 10, 10)
    assert abs(math.degrees(tgt.rotation_euler[2]) - 100.0) < 1e-4
    assert abs(math.degrees(dup.rotation_euler[2]) - 60.0) < 1e-4
    bpy.data.objects.remove(dup)
    assert sdk.sync() == (0, 0, 2)
    bpy.data.objects.remove(tgt)
    assert sdk.sync() == (0, 0, 2)
    assert sdk.helpers() == [], "an empty helper goes away"


def test_second_helper_from_append_is_merged():
    _clear()
    drv = _empty("drv", curl=0, spread=0)
    tgt = _empty("tgt")
    _rig(drv, tgt)
    main = sdk.helper(create=False)
    other = bpy.data.textures.new(".allset_sdk", 'NONE')     # = a helper brought in by append / paste
    other[sdk.HELPER] = 1
    other["allset_sdk_0"] = 0.0
    fc = other.driver_add('["allset_sdk_0"]')
    fc.driver.type = 'AVERAGE'
    v = fc.driver.variables.new()
    v.name = "sdk"
    v.targets[0].id = drv
    v.targets[0].data_path = '["curl"]'
    blend = sdk.sdk_fcurve(tgt, "rz")
    t = blend.driver.variables[0].targets[0]
    t.id_type = 'TEXTURE'
    t.id = other
    sdk.sync()
    assert sdk.helpers() == [main], [x.name for x in sdk.helpers()]
    assert all(v.targets[0].id == main for v in blend.driver.variables)


def test_disable_keeps_working_channels():
    """The helper is scene data: with the kit off the summed channel still evaluates."""
    _clear()
    drv = _empty("drv", curl=0, spread=0)
    tgt = _empty("tgt")
    _rig(drv, tgt)
    kit.disable()
    try:
        _pose(drv, 10, 10)
        assert abs(math.degrees(tgt.rotation_euler[2]) - 60.0) < 1e-4
    finally:
        kit.enable()
