"""Graph Editor key drags with Auto Key on (#270): editing keys is not a channel change, so Auto Key never sets a key
at the current time because of it — also when another curve edit lands between the update and Auto Key's check —
while a real channel change still gets its key."""

from importlib import import_module

import bpy

import kit

auto_key = import_module(kit.MODULE + ".operators.auto_key")


def _clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for act in list(bpy.data.actions):
        bpy.data.actions.remove(act)
    bpy.context.scene.frame_set(1)


def _keyed_cube():
    _clear()
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    for f, v in ((1, 0.0), (10, 5.0), (20, 2.0)):
        ob.location.x = v
        ob.keyframe_insert("location", index=0, frame=f)
    bpy.context.view_layer.update()
    return ob


def _curve(ob):
    return kit.fcurves(ob).find("location", index=0)


def _frames(ob):
    return [round(kp.co.x, 3) for kp in _curve(ob).keyframe_points]


def _flush_now():
    if bpy.app.timers.is_registered(auto_key._flush):
        bpy.app.timers.unregister(auto_key._flush)
    auto_key._flush()


class _AutoKey:
    def __enter__(self):
        auto_key._pending.clear()
        bpy.context.scene.allset_auto_key = True

    def __exit__(self, *_exc):
        bpy.context.scene.allset_auto_key = False
        auto_key._pending.clear()
        if bpy.app.timers.is_registered(auto_key._flush):
            bpy.app.timers.unregister(auto_key._flush)


def _move_key(fc, i, dx):
    kp = fc.keyframe_points[i]
    kp.co.x += dx
    kp.handle_left.x += dx
    kp.handle_right.x += dx


def test_key_drag_is_not_a_channel_change():
    ob = _keyed_cube()
    sc = bpy.context.scene
    with _AutoKey():
        sc.frame_set(15)
        fc = _curve(ob)
        _move_key(fc, 1, 15.0)              # key 10 slid past the last key, like a drag step
        fc.update()
        bpy.context.view_layer.update()     # the drag's depsgraph update
        assert ob.name not in auto_key._pending, "a curve edit doesn't wait to be auto keyed"
        # another curve edit before Auto Key looks (a tangent rule or a time snap run by a timer)
        kp = fc.keyframe_points[0]
        kp.handle_right.y += 1.0
        _flush_now()
        assert _frames(ob) == [1, 20, 25], f"no key added at the current time: {_frames(ob)}"


def test_channel_change_still_auto_keys():
    ob = _keyed_cube()
    sc = bpy.context.scene
    with _AutoKey():
        sc.frame_set(15)
        ob.location.x = 9.0
        bpy.context.view_layer.update()
        assert ob.name in auto_key._pending
        _flush_now()
        assert _frames(ob) == [1, 10, 15, 20], _frames(ob)
        assert abs(_curve(ob).evaluate(15) - 9.0) < 1e-5


def test_kit_key_drags_count_as_transforms():
    for name in ("ALLSET_OT_graph_key_drag", "ALLSET_OT_graph_axis_drag"):
        assert auto_key.waits_for(name), name
    assert not auto_key.waits_for("ALLSET_OT_cb_wheel")
