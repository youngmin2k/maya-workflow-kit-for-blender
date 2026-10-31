"""Maya Insert Key (shape kept), Nudge Keys, Select Previous / Next Key, keymap.
GUI: tests/gui/gui_step83_key_insert.py."""

from importlib import import_module

import bpy

import kit

ki = import_module(kit.MODULE + ".operators.key_insert")
patches = import_module(kit.MODULE + ".keymap.maya_patches")
cb = import_module(kit.MODULE + ".ui.channel_box")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)


def _animated(name="cube", keys=((1, 0.0), (10, 5.0), (20, -2.0), (30, 8.0)), path="location", index=0):
    _clear()
    ob = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(ob)
    for f, v in keys:
        getattr(ob, path)[index] = v
        ob.keyframe_insert(path, index=index, frame=f)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    return ob, cb._fcurves(ob).find(path, index=index)


def _samples(fc, a=-5.0, b=40.0, step=0.25):
    out, x = [], a
    while x <= b:
        out.append(fc.evaluate(x))
        x += step
    return out


def _same(s1, s2, tol=1e-4):
    return max(abs(p - q) for p, q in zip(s1, s2)) < tol


def test_bezier_split_keeps_shape():
    for frame in (4, 14.3, 19, 25):
        _ob, fc = _animated()
        before = _samples(fc)
        assert ki.insert_keep_shape(fc, frame)
        assert len(fc.keyframe_points) == 5 and ki._at(fc, frame) is not None
        assert _same(before, _samples(fc)), frame


def _free_overshoot(fc):
    k = fc.keyframe_points[1]
    k.handle_left_type = k.handle_right_type = 'FREE'
    k.handle_right = (k.co.x + 6, k.co.y + 9)
    fc.update()


def test_plain_blender_insert_misses_free_handles():
    # why the split is needed: Blender's insert keeps auto segments but not free / overshooting ones (0.36 here)
    _ob, fc = _animated()
    _free_overshoot(fc)
    before = _samples(fc)
    fc.keyframe_points.insert(13, fc.evaluate(13))
    fc.update()
    assert not _same(before, _samples(fc), tol=1e-2)


def test_auto_segments_stay_auto():
    _ob, fc = _animated()
    assert ki.insert_keep_shape(fc, 14)
    assert all(kp.handle_left_type == 'AUTO_CLAMPED' for kp in fc.keyframe_points)


def test_free_overshoot_handles_and_vector_kept():
    _ob, fc = _animated()
    _free_overshoot(fc)                                 # strong overshoot
    fc.keyframe_points[2].handle_left_type = 'VECTOR'
    fc.update()
    before = _samples(fc)
    assert ki.insert_keep_shape(fc, 13)
    assert _same(before, _samples(fc))


def test_linear_constant_outside_and_existing():
    _ob, fc = _animated()
    for kp in fc.keyframe_points:
        kp.interpolation = 'LINEAR'
    fc.keyframe_points[2].interpolation = 'CONSTANT'
    fc.update()
    before = _samples(fc)
    for frame in (5, 24, -3, 35):                     # linear, constant, before the first, after the last
        assert ki.insert_keep_shape(fc, frame), frame
    assert _same(before, _samples(fc))
    assert not ki.insert_keep_shape(fc, 10)            # a key is there already
    _ob, fc = _animated()                              # bezier ends: outside keys stay flat, inside unchanged
    before = _samples(fc)
    assert ki.insert_keep_shape(fc, 36) and ki.insert_keep_shape(fc, -2)
    assert _same(before, _samples(fc))


def test_insert_key_channels_only_existing_curves():
    ob, fc = _animated()
    ob.rotation_euler[2] = 1.0
    ob.keyframe_insert("rotation_euler", index=2, frame=1)
    ob.rotation_euler[2] = 2.0
    ob.keyframe_insert("rotation_euler", index=2, frame=20)
    bpy.context.scene.frame_set(7)
    rot = cb._fcurves(ob).find("rotation_euler", index=2)
    rv = rot.evaluate(7)
    assert bpy.ops.allset.insert_key(channels='ROTATE') == {'FINISHED'}
    assert ki._at(rot, 7) is not None and abs(rot.evaluate(7) - rv) < 1e-5
    assert ki._at(fc, 7) is None                       # translate untouched
    assert cb._fcurves(ob).find("scale", index=0) is None
    assert bpy.ops.allset.insert_key(channels='SCALE') == {'CANCELLED'}     # no scale curves: none made
    assert cb._fcurves(ob).find("scale", index=0) is None
    assert bpy.ops.allset.insert_key(channels='ALL') == {'FINISHED'}
    assert ki._at(fc, 7) is not None


def test_bone_channel_prefix():
    _clear()
    arm = bpy.data.objects.new("rig", bpy.data.armatures.new("rig"))
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    for n in ("joint1", "joint2"):
        b = arm.data.edit_bones.new(n)
        b.tail = (0, 0, 1)
    bpy.ops.object.mode_set(mode='POSE')
    for n in ("joint1", "joint2"):
        pb = arm.pose.bones[n]
        for f, v in ((1, 0.0), (11, 3.0)):
            pb.location[0] = v
            pb.keyframe_insert("location", index=0, frame=f)
    cb.set_bone_selected(arm.pose.bones["joint1"], True)
    cb.set_bone_selected(arm.pose.bones["joint2"], False)
    arm.data.bones.active = arm.data.bones["joint1"]
    curves = ki.channel_curves(arm.pose.bones["joint1"], 'TRANSLATE')
    assert [fc.data_path for fc in curves] == ['pose.bones["joint1"].location']
    bpy.ops.object.mode_set(mode='OBJECT')


def test_move_keys_overwrites_and_nudge_follows_time():
    _ob, fc = _animated()
    ki.move_keys(fc, [10.0], 10)                       # onto the key at 20: Maya -option over
    assert [round(kp.co.x) for kp in fc.keyframe_points] == [1, 20, 30]
    assert abs(fc.keyframe_points[1].co.y - 5.0) < 1e-6
    ob, fc = _animated()
    sc = bpy.context.scene
    sc.frame_set(10)
    bpy.context.window_manager.allset_time_range_on = False
    assert bpy.ops.allset.nudge_keys(delta=1) == {'FINISHED'}
    assert [round(kp.co.x) for kp in fc.keyframe_points] == [1, 11, 20, 30] and sc.frame_current == 11
    assert bpy.ops.allset.nudge_keys(delta=1) == {'FINISHED'}       # again: the key follows
    assert ki._at(fc, 12) is not None and sc.frame_current == 12
    assert bpy.ops.allset.nudge_keys(delta=-1) == {'FINISHED'}
    assert ki._at(fc, 11) is not None
    sc.frame_set(5)
    assert bpy.ops.allset.nudge_keys(delta=1) == {'CANCELLED'}      # no key at this time


def test_select_next_previous_key():
    ob, fc = _animated()
    sc = bpy.context.scene
    sc.frame_set(4)
    for kp in fc.keyframe_points:
        kp.select_control_point = False
    assert ki.select_key(bpy.context, 'NEXT') == 10 and sc.frame_current == 10
    assert [kp.select_control_point for kp in fc.keyframe_points] == [False, True, False, False]
    assert ki.select_key(bpy.context, 'NEXT') == 20                    # from the time it went to
    assert [kp.select_control_point for kp in fc.keyframe_points] == [False, False, True, False]
    assert ki.select_key(bpy.context, 'PREVIOUS') == 10 and sc.frame_current == 10
    for kp in fc.keyframe_points:
        kp.select_control_point = True                                  # outside a key editor: selection ignored
    assert ki.select_key(bpy.context, 'NEXT') == 20
    sc.frame_set(1)
    assert ki.select_key(bpy.context, 'PREVIOUS') is None              # nothing before frame 1
    assert ki.neighbour_time([1, 10, 20], 10, 'NEXT') == 20 and ki.neighbour_time([1, 10], 1, 'PREVIOUS') is None


def test_keymap_items():
    kc = kit.maya_kc()
    km = kc.keymaps["Screen"]

    def find(t, **mods):
        return [k for k in km.keymap_items if k.active and k.type == t and k.value == 'PRESS'
                and all(getattr(k, m) == mods.get(m, False) for m in ("shift", "ctrl", "alt"))]
    for t, mods, idname, prop, val in (("I", {"alt": True}, "allset.insert_key", "channels", "ALL"),
                                       ("W", {"ctrl": True, "shift": True}, "allset.insert_key", "channels", "TRANSLATE"),
                                       ("E", {"ctrl": True, "shift": True}, "allset.insert_key", "channels", "ROTATE"),
                                       ("R", {"ctrl": True, "shift": True}, "allset.insert_key", "channels", "SCALE"),
                                       ("NINE", {"shift": True}, "allset.nudge_keys", "delta", -1),
                                       ("ZERO", {"shift": True}, "allset.nudge_keys", "delta", 1),
                                       ("COMMA", {"ctrl": True, "alt": True}, "allset.select_key", "direction", "PREVIOUS"),
                                       ("PERIOD", {"ctrl": True, "alt": True}, "allset.select_key", "direction", "NEXT")):
        items = [k for k in find(t, **mods) if k.idname == idname]
        assert len(items) == 1 and getattr(items[0].properties, prop) == val, (t, mods)
    names = [a[1] for a in patches.ADDED]
    assert names.count("allset.insert_key") == 4 and names.count("allset.nudge_keys") == 2
