"""Maya keys and Time Slider — S keys every keyable channel, Set Breakdown Key, Time Slider
Cut / Copy / Paste / Delete / Snap / Keys / Tangents / Set Range to, Key > Delete Keys = all keys,
keymaps (timeline LMB / Shift / MMB / RMB, K time drag, S), the Channel Box RMB items.
GUI: tests/gui/gui_step56_time_slider.py."""

import types
from importlib import import_module

import bpy

import kit

cb = import_module(kit.MODULE + ".ui.channel_box")
tk = import_module(kit.MODULE + ".operators.time_keys")
taphold = import_module(kit.MODULE + ".operators.taphold")
ts = import_module(kit.MODULE + ".ui.time_slider")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")
ic_data = import_module(kit.MODULE + ".keymap.ic_data")
maya_patches = import_module(kit.MODULE + ".keymap.maya_patches")
patch = import_module(kit.MODULE + ".keymap.patch")


class Recorder:
    def __init__(self, log=None):
        self.log = [] if log is None else log

    def __getattr__(self, name):
        if name in ("row", "column", "split", "box"):
            return lambda *a, **k: Recorder(self.log)
        if name in ("menu", "operator", "prop", "prop_enum", "label"):
            def add(*args, **kw):
                self.log.append((name, kw.get("text", args[0] if args else "")))
                return types.SimpleNamespace()
            return add
        return lambda *a, **k: None

    def __setattr__(self, name, value):
        if name == "log":
            object.__setattr__(self, name, value)

    def texts(self, kinds=("operator", "menu", "prop_enum", "label")):
        return [t for k, t in self.log if k in kinds]


def _scene(n=1):
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    sc = bpy.context.scene
    sc.keying_sets.active_index = -1
    sc.frame_start, sc.frame_end, sc.use_preview_range = 1, 200, False
    sc.frame_set(1)
    wm = bpy.context.window_manager
    wm.allset_cb_selected = ""
    wm.allset_time_range_on = False
    obs = []
    for i in range(n):
        bpy.ops.mesh.primitive_cube_add(location=(i, 0, 0))
        obs.append(bpy.context.active_object)
    for ob in obs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = obs[0] if obs else None
    return obs


def _paths(ob):
    fcs = cb._fcurves(ob)
    return sorted((fc.data_path, fc.array_index) for fc in fcs) if fcs else []


def _frames(ob, path="location", index=0):
    fc = cb._fcurves(ob).find(path, index=index)
    return [round(kp.co.x) for kp in fc.keyframe_points] if fc else []


def test_s_keys_every_keyable_channel():
    ob, = _scene()
    ob["curl"] = 1.0
    cb._set_flag_list(ob, cb.HIDDEN_PROP, ["sz"])          # Channel Box Hide = not keyable (Maya)
    cb._set_flag_list(ob, cb.NONKEYABLE_PROP, ["tx"])
    assert bpy.ops.allset.set_key() == {'FINISHED'}
    want = [('["curl"]', 0), ("hide_viewport", 0), ("location", 1), ("location", 2), ("rotation_euler", 0),
            ("rotation_euler", 1), ("rotation_euler", 2), ("scale", 0), ("scale", 1)]
    assert _paths(ob) == want, _paths(ob)


def test_set_breakdown_key_and_keying_set():
    ob, = _scene()
    bpy.ops.allset.set_key()
    bpy.context.scene.frame_set(12)
    assert bpy.ops.allset.set_key(breakdown=True) == {'FINISHED'}
    fc = cb._fcurves(ob).find("location", index=0)
    assert [(round(k.co.x), k.type) for k in fc.keyframe_points] == [(1, 'KEYFRAME'), (12, 'BREAKDOWN')]


def test_s_keys_selected_joints():
    _scene(0)
    bpy.ops.allset.create(kind='JOINT')
    arm = bpy.context.active_object
    bpy.ops.object.mode_set(mode='POSE')
    pb = arm.pose.bones["joint1"]
    cb.set_bone_selected(pb, True)
    arm.data.bones.active = pb.bone
    bpy.ops.allset.set_key()
    paths = {p for p, _i in _paths(arm)}
    assert paths == {'pose.bones["joint1"].location', 'pose.bones["joint1"].rotation_euler',
                     'pose.bones["joint1"].scale'}, paths
    bpy.ops.object.mode_set(mode='OBJECT')


def _two_keys(ob):
    sc = bpy.context.scene
    sc.frame_set(1)
    bpy.ops.allset.set_key()
    sc.frame_set(24)
    ob.location.x = 3.0
    bpy.ops.allset.set_key()


def test_time_slider_delete_this_frame_and_range():
    ob, = _scene()
    _two_keys(ob)
    assert _frames(ob) == [1, 24]
    assert bpy.ops.allset.time_keys(action='DELETE') == {'FINISHED'}   # frame 24, no range
    assert _frames(ob) == [1]
    _two_keys(ob)
    ts.set_range(bpy.context.window_manager, 20, 30)
    bpy.context.scene.frame_set(1)
    bpy.ops.allset.time_keys(action='DELETE')
    assert _frames(ob) == [1], "the Shift range, not the current frame"
    ts.set_range(bpy.context.window_manager, 0, 30)
    bpy.ops.allset.time_keys(action='DELETE')
    assert cb._fcurves(ob).find("location", index=0) is None, "an emptied curve goes"


def test_copy_paste_cut():
    a, b = _scene(2)
    b.select_set(False)
    _two_keys(a)
    sc = bpy.context.scene
    sc.frame_set(24)
    bpy.ops.allset.time_keys(action='COPY')
    sc.frame_set(40)
    bpy.ops.allset.time_keys(action='PASTE')
    assert _frames(a) == [1, 24, 40]
    fc = cb._fcurves(a).find("location", index=0)
    assert abs(fc.keyframe_points[2].co.y - 3.0) < 1e-6
    bpy.ops.allset.time_keys(action='CUT')
    assert _frames(a) == [1, 24]
    sc.frame_set(10)
    b.select_set(True)
    bpy.context.view_layer.objects.active = b
    a.select_set(False)
    bpy.ops.allset.time_keys(action='PASTE')                  # the cut keys onto another object
    assert _frames(b) == [10] and abs(cb._fcurves(b).find("location", index=0).keyframe_points[0].co.y - 3) < 1e-6


def test_snap_convert_inbetween_tangents():
    ob, = _scene()
    _two_keys(ob)
    fc = cb._fcurves(ob).find("location", index=0)
    fc.keyframe_points[1].co.x = 24.4
    ts.set_range(bpy.context.window_manager, 1, 30)
    bpy.ops.allset.time_keys(action='SNAP')
    assert _frames(ob) == [1, 24] and fc.keyframe_points[1].co.x == 24.0
    bpy.ops.allset.time_keys(action='TO_BREAKDOWN')
    assert {k.type for k in fc.keyframe_points} == {'BREAKDOWN'}
    bpy.ops.allset.time_keys(action='TO_KEY')
    assert {k.type for k in fc.keyframe_points} == {'KEYFRAME'}
    for kind, interp in (("LINEAR", 'LINEAR'), ("STEPPED", 'CONSTANT'), ("SPLINE", 'BEZIER')):
        bpy.ops.allset.time_keys(action='TANGENT', tangent=kind)
        assert {k.interpolation for k in fc.keyframe_points} == {interp}, kind
    bpy.ops.allset.time_keys(action='TANGENT', tangent='FLAT')
    kp = fc.keyframe_points[1]
    assert abs(kp.handle_left.y - kp.co.y) < 1e-6 and abs(kp.handle_right.y - kp.co.y) < 1e-6
    bpy.context.window_manager.allset_time_range_on = False
    bpy.context.scene.frame_set(10)
    bpy.ops.allset.time_keys(action='ADD_INBETWEEN')
    assert _frames(ob) == [1, 25]
    bpy.ops.allset.time_keys(action='REMOVE_INBETWEEN')
    assert _frames(ob) == [1, 24]


def test_set_range_to():
    ob, = _scene()
    _two_keys(ob)
    sc = bpy.context.scene
    bpy.ops.allset.time_set_range(mode='MIN_MAX')
    assert sc.use_preview_range and (sc.frame_preview_start, sc.frame_preview_end) == (1, 24)
    bpy.ops.allset.time_set_range(mode='START_END')
    assert (sc.frame_preview_start, sc.frame_preview_end) == (1, 200)
    ts.set_range(bpy.context.window_manager, 30, 10)
    bpy.ops.allset.time_set_range(mode='SELECTED')
    assert (sc.frame_preview_start, sc.frame_preview_end) == (10, 30)
    bpy.context.window_manager.allset_time_range_on = False
    assert bpy.ops.allset.time_set_range(mode='SELECTED') == {'CANCELLED'}


def test_key_menu_mapping():
    m = menu_map.MAP
    assert m["Key/Delete Keys"] == ("v3d", "anim.keyframe_clear_v3d", {"confirm": False}), "Maya: all keys"
    assert m["Edit/Keys/Delete Keys"] == m["Key/Delete Keys"]
    assert m["Key/Set Key"] == "allset.set_key"
    assert m["Key/Set Breakdown Key"] == ("allset.set_key", {"breakdown": True})
    for path in ("Key/Copy Keys", "Key/Paste Keys", "Key/Cut Keys", "Edit/Keys/Copy Keys"):
        assert m[path][0] == "allset.time_keys", path
    assert m["Playback/Set Range to/Min/Max"] == ("allset.time_set_range", {"mode": "MIN_MAX"})
    assert "Playback/Playback Looping/Once" in notices.NOTICES


def test_keymap_patches():
    data = maya_patches.apply(ic_data.generate())
    kd = patch.KeyconfigData(data)
    dope = kd.items("Dopesheet")
    first = [(it[0], patch.event_key(it[1])) for it in dope[:5]]
    # the range drag (passes through off the range) sits in front of time_scrub
    assert {f[0] for f in first} == {"allset.time_range_drag", "allset.time_scrub", "allset.time_slider_menu"}, first
    assert kd.find("Dopesheet", "allset.time_scrub", type="LEFTMOUSE", shift=True)
    assert kd.find("Dopesheet", "allset.time_scrub", type="MIDDLEMOUSE")
    assert not kd.find("Dopesheet", "action.select_column", type="K")
    assert kd.find("Dopesheet", "action.select_column", type="K", ctrl=True), "the K variants stay"
    assert not kd.find("Mesh", "wm.tool_set_by_id", type="K"), "no knife K (Multi-Cut = Ctrl+Shift+X)"
    assert kd.find("Screen", "allset.tap_hold", type="K")
    for km in ("Object Mode", "Pose"):
        assert kd.find(km, "allset.set_key", type="S") and not kd.find(km, "anim.keyframe_insert_by_name", type="S")
    assert "time_drag" in taphold.binding_names()


def test_time_drag_speed():
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end, sc.use_preview_range = 1, 200, True
    sc.frame_preview_start, sc.frame_preview_end = 1, 120
    fpp = taphold.frames_per_pixel(sc, 1200)
    assert abs(fpp - 0.1) < 1e-9, "the editor width = the playback range"
    assert taphold.time_from_drag(10, 100, fpp) == 20 and taphold.time_from_drag(10, -100, fpp) == 0
    assert taphold.frames_per_pixel(sc, 100000) == 0.02
    sc.use_preview_range = False


def test_time_slider_menu_order():
    rec = Recorder()
    ts.ALLSET_MT_time_slider.draw(types.SimpleNamespace(layout=rec), bpy.context)
    assert rec.texts() == ["Cut", "Copy", "Paste", "Delete", "Snap", "Keys", "Tangents", "Playback Speed",
                           "Playback Looping", "Set Range to", "Playblast..."], rec.texts()
    rec = Recorder()
    ts.ALLSET_MT_time_slider_tangents.draw(types.SimpleNamespace(layout=rec), bpy.context)
    assert rec.texts() == ["Spline", "Linear", "Clamped", "Stepped", "Flat", "Plateau", "Auto"]
    rec = Recorder()
    ts.ALLSET_MT_time_slider_looping.draw(types.SimpleNamespace(layout=rec), bpy.context)
    assert rec.texts() == ["Once", "Oscillate", "Continuous"]
    tip = ts.ALLSET_OT_time_slider_unavailable.description(bpy.context, types.SimpleNamespace(item="Once"))
    assert "always loops" in tip


def test_channel_box_rmb_items():
    _scene()
    rec = Recorder()
    ctx = types.SimpleNamespace(button_pointer=bpy.context.scene.allset_cb, button_operator=None)
    cb.draw_button_menu(types.SimpleNamespace(layout=rec), ctx)
    assert rec.texts()[:2] == ["Key Selected", "Breakdown Selected"], rec.texts()
    rec = Recorder()
    ctx = types.SimpleNamespace(button_pointer=bpy.context.scene, button_operator=None)
    cb.draw_button_menu(types.SimpleNamespace(layout=rec), ctx)
    assert rec.texts() == [], "other buttons keep Blender's menu"
    assert cb.draw_button_menu in bpy.types.UI_MT_button_context_menu._dyn_ui_initialize()
