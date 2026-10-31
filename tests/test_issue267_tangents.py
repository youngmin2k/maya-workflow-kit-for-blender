"""Non-weighted tangents (#267): curves made by Blender's own keying get the Default Tangent Weight, loaded animation
keeps its tangents, the Δt/3 rule follows every edit at once (depsgraph update), and the 0.25 s watch is not held up
by the kit's click listeners."""

import math
import os
from importlib import import_module

import bpy

import kit

gw = import_module(kit.MODULE + ".operators.graph_weights")
preferences = import_module(kit.MODULE + ".preferences")


def _clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for act in list(bpy.data.actions):
        bpy.data.actions.remove(act)
    bpy.context.scene.frame_set(1)


def _object():
    _clear()
    bpy.ops.mesh.primitive_cube_add()
    return bpy.context.active_object


def _curve(ob, index=0):
    return kit.fcurves(ob).find("location", index=index)


def _update():
    bpy.context.view_layer.update()


class _Pref:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        p = preferences.get()
        self.old = p.default_tangent_weight
        p.default_tangent_weight = self.value

    def __exit__(self, *_exc):
        preferences.get().default_tangent_weight = self.old


def test_blender_keying_gets_the_default_tangent_weight():
    with _Pref('NON_WEIGHTED'):
        ob = _object()
        ob.keyframe_insert("location", frame=1)          # Blender's own keying (I key / Insert Keyframe / auto key)
        _update()
        for i in range(3):
            assert not gw.is_weighted(_curve(ob, i)), f"location[{i}] made by keying is non-weighted"
    with _Pref('WEIGHTED'):
        ob = _object()
        ob.keyframe_insert("rotation_euler", frame=1)
        _update()
        fc = kit.fcurves(ob).find("rotation_euler", index=0)
        entry = ob.animation_data.action[gw.PROP][gw.curve_key(fc)]
        assert gw.is_weighted(fc) and int(entry["w"]) == 1, "pref Weighted marks the new curve weighted"


def test_non_weighted_rule_follows_edits_at_once():
    with _Pref('NON_WEIGHTED'):
        ob = _object()
        for f, v in ((1, 0.0), (10, 2.0), (22, 1.0)):
            bpy.context.scene.frame_set(f)
            ob.location.x = v
            ob.keyframe_insert("location", index=0, frame=f)
            _update()
        fc = _curve(ob)
        assert not gw.is_weighted(fc)
        kp = fc.keyframe_points[1]
        kp.handle_right_type = 'FREE'
        kp.handle_right = (kp.co[0] + 7.0, kp.co[1] + 1.4)       # a long arm, angle atan2(1.4, 7)
        _update()                                                # the depsgraph update applies the rule
        dx, dy = kp.handle_right[0] - kp.co[0], kp.handle_right[1] - kp.co[1]
        assert abs(dx - 4.0) < 1e-4, f"right arm back to a third of 10 -> 22 ({dx})"
        assert abs(math.atan2(dy, dx) - math.atan2(1.4, 7.0)) < 1e-5, "angle kept"
        gw.set_weighted(fc, True)
        kp.handle_right = (kp.co[0] + 7.0, kp.co[1] + 1.4)
        _update()
        assert abs(kp.handle_right[0] - kp.co[0] - 7.0) < 1e-5, "a weighted arm keeps its length"


def test_adoption_rule():
    with _Pref('NON_WEIGHTED'):
        ob = _object()
        ob.location.x = 1.0
        ob.keyframe_insert("location", index=0, frame=1)
        ob.keyframe_insert("location", index=0, frame=5)
        ob.keyframe_insert("location", index=1, frame=7)        # one key, not on the current frame (1)
        fc0, fc1 = _curve(ob, 0), _curve(ob, 1)
        act = ob.animation_data.action
        assert not gw.new_by_keying(act, fc0, 1.0), "two keys: not just made"
        assert not gw.new_by_keying(act, fc1, 1.0), "one key away from the current frame: not keying"
        assert gw.new_by_keying(act, fc1, 7.0)
        assert gw.adopt(act, bpy.context.scene) == 0
        assert gw.PROP not in act or gw.curve_key(fc0) not in act[gw.PROP]


def test_loaded_animation_keeps_its_tangents():
    """A one-key curve on the current frame saved in a file is part of the loaded animation: not adopted."""
    with _Pref('NON_WEIGHTED'):
        ob = _object()
        gw._state["loading"] = True               # a file made elsewhere: its curve carries no mark
        try:
            ob.keyframe_insert("location", index=2, frame=1)
            fc = _curve(ob, 2)
            act = ob.animation_data.action
            if gw.PROP in act:
                del act[gw.PROP]
            path = os.path.join(bpy.app.tempdir, "issue267_loaded.blend")
            bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
        finally:
            gw._state["loading"] = False
        del ob, fc, act
        bpy.ops.wm.open_mainfile(filepath=path)
        act = bpy.data.actions[0]
        fc = gw.compat.action_fcurves(act)[0]
        fc.keyframe_points[0].co.y += 0.5                     # an edit: the Action is updated
        _update()
        assert gw.PROP not in act or gw.curve_key(fc) not in act[gw.PROP], "loaded curve left unmarked"
        assert gw.is_weighted(fc)
        bpy.ops.wm.read_homefile(use_empty=True)


def test_nothing_adopted_while_a_file_loads():
    ob = _object()
    ob.keyframe_insert("location", index=0, frame=1)
    act = ob.animation_data.action
    gw._state["loading"] = True
    try:
        assert gw.adopt(act, bpy.context.scene) == 0, "nothing adopted while a file loads"
    finally:
        gw._state["loading"] = False


def test_watch_waits_only_for_editing_modals():
    listeners = import_module(kit.MODULE + ".modal_listeners")
    for name in ("ALLSET_OT_joint_outliner_select", "ALLSET_OT_pose_empty_click", "ALLSET_OT_cb_wheel",
                 "ALLSET_OT_cb_channel_drag"):
        assert name in listeners.NAMES, name
    assert "TRANSFORM_OT_translate" not in listeners.NAMES
    assert gw._busy() is False


def test_handlers_follow_enable_disable():
    assert gw._on_depsgraph in bpy.app.handlers.depsgraph_update_post
    assert gw._load_post in bpy.app.handlers.load_post
    kit.disable()
    try:
        for name in ("depsgraph_update_post", "load_pre", "load_post"):
            names = {getattr(fn, "__qualname__", "") for fn in getattr(bpy.app.handlers, name)
                     if getattr(fn, "__module__", "").endswith("graph_weights")}
            assert not names, (name, names)
    finally:
        kit.enable()
