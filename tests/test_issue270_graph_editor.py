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


# --- Scale Keys manipulator -----------------------------------------------------------------------------------------

sb = import_module(kit.MODULE + ".operators.graph_scale_box")


def test_scale_box_rules():
    assert sb.box_of([(10, 20)]) is None, "one key: nothing to scale"
    box = sb.box_of([(10, 20), (110, 60), (50, 40)])
    assert box == (10, 20, 110, 60)
    assert sb.hit(box, 10, 20) == "LB" and sb.hit(box, 110, 60) == "RT"
    assert sb.hit(box, 112, 45) == "R" and sb.hit(box, 8, 30) == "L"
    assert sb.hit(box, 60, 61) == "T" and sb.hit(box, 70, 19) == "B"
    assert sb.hit(box, 60, 40) is None, "inside the box: Blender's own click"
    assert sb.hit(box, 200, 40) is None
    # the opposite side stays: right side -> pivot on the left, time only
    assert sb.pivot_of(box, "R") == (10, 40.0, 110, None, True, False)
    assert sb.pivot_of(box, "B") == (60.0, 60, None, 20, False, True)
    assert sb.pivot_of(box, "LT")[:2] == (110, 20) and sb.pivot_of(box, "LT")[4:] == (True, True)
    assert sb.factor(110, 10, 50) == 1.5 and sb.factor(110, 10, -100) == 0.0
    assert sb.factor(10, 10, 30) == 1.0, "an edge on its pivot doesn't scale"
    # keys on one frame: the box has no width, its left / right sides can't be grabbed
    flat = sb.box_of([(40, 20), (40, 80)])
    assert sb.hit(flat, 40, 50) is None and sb.hit(flat, 40, 80) in ("LT", "RT", "T")
    assert sb.hit(flat, 40, 81) in ("LT", "RT", "T")


def test_scale_box_keymap_and_pref():
    km = kit.maya_kc().keymaps["Graph Editor"]
    plain = [i.idname for i in km.keymap_items if i.active and i.type == 'LEFTMOUSE' and i.value == 'PRESS'
             and not (i.shift or i.ctrl or i.alt)]
    assert "allset.graph_scale_box" in plain, plain
    assert plain.index("allset.graph_scale_box") < plain.index("graph.clickselect"), plain
    preferences = import_module(kit.MODULE + ".preferences")
    assert preferences.get().graph_scale_manipulator, "on by default"
    assert auto_key.waits_for("ALLSET_OT_graph_scale_box")


def test_scale_box_scales_keys_about_the_opposite_side():
    """KeySet.apply_scale with the box's pivot: the right side dragged 50 % further scales time by 1.5 about the
    left side (the first selected key stays)."""
    gm = import_module(kit.MODULE + ".operators.graph_move")
    ob = _keyed_cube()
    fc = _curve(ob)
    for kp in fc.keyframe_points:
        kp.select_control_point = kp.co.x in (1.0, 10.0)
    keys = gm.KeySet.__new__(gm.KeySet)
    keys.curves = [(fc, 1.0, [(i, tuple(kp.co), tuple(kp.handle_left), tuple(kp.handle_right))
                              for i, kp in enumerate(fc.keyframe_points) if kp.select_control_point])]
    keys.offsets = [0.0]
    keys.types = {}
    keys.apply_scale((1.0, 0.0), sb.factor(10.0, 1.0, 4.5), 1.0, True)
    keys.finish()
    assert _frames(ob) == [1, 14, 20], _frames(ob)
