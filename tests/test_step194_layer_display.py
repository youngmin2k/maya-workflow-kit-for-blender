"""Animation layer keys stay visible. A layered object's active action is
the selected layer's strip action at influence 0: the evaluated result is unchanged, the Time Slider ticks show the
selected layer + the BaseAnimation keys of channels not in it, the Channel Box marks layer members (Maya teal),
Zero Key Layer and Merge Layers follow Maya."""

from importlib import import_module

import bpy

import kit

al = import_module(kit.MODULE + ".operators.anim_layers")
cb = import_module(kit.MODULE + ".ui.channel_box")
ts = import_module(kit.MODULE + ".ui.time_slider")
compat = import_module(kit.MODULE + ".compat")
FRAMES = (-5, 1, 3, 6, 9, 12, 15, 18, 21, 24, 30)


def _scene():
    """The layer scene: pCube1, base tx 0@1 5@12 0@24, ry 0@1 90@24 (here radians)."""
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for act in list(bpy.data.actions):
        bpy.data.actions.remove(act)
    sc = bpy.context.scene
    sc.allset_anim_layers.clear()
    sc.allset_anim_layer_index = 0
    me = bpy.data.meshes.new("pCubeShape1")
    ob = bpy.data.objects.new("pCube1", me)
    sc.collection.objects.link(ob)
    for f, x in ((1, 0.0), (12, 5.0), (24, 0.0)):
        ob.location.x = x
        ob.keyframe_insert("location", index=0, frame=f)
    for f, r in ((1, 0.0), (24, 1.5708)):
        ob.rotation_euler.y = r
        ob.keyframe_insert("rotation_euler", index=1, frame=f)
    for o in sc.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    return sc, ob


def _evaluated(sc, ob):
    out = []
    for f in FRAMES:
        sc.frame_set(f)
        e = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        out.append(tuple(e.location) + tuple(e.rotation_euler) + tuple(e.scale))
    sc.frame_set(1)
    return out


def _ticks(ob):
    return sorted(f for f, _b in ts.key_frames([ob]))


def _layered():
    """The scene with AnimLayer1 from the selected cube, ry taken out of it, layer tx keys 2@6 and -1@18
    (Maya: setKeyframe -v on the layer keys the result, so the result values are given)."""
    sc, ob = _scene()
    before = _ticks(ob), _evaluated(sc, ob)
    bpy.ops.allset.anim_layer_create(from_selected=True)
    al.remove_attrs(sc, ob, "AnimLayer1", ["ry"])
    for f in (6, 18):
        base = al.base_curve(ob, "location", 0).evaluate(f)
        al.key(ob, "location", 0, frame=f, value=base + (2.0 if f == 6 else -1.0), scene=sc)
    return sc, ob, before


def test_display_action_keeps_the_result():
    sc, ob, (ticks0, eval0) = _layered()
    layer = al.layers(sc)[sc.allset_anim_layer_index].name
    assert layer == "AnimLayer1"
    ad = ob.animation_data
    assert ad.action is not None and ad.action.get(al.MARK) == "AnimLayer1", ad.action
    assert ad.action_influence == 0.0
    # the shown action plays only through its strip: switching the shown layer changes no value
    sc.allset_anim_layer_index = 0
    assert ad.action.get(al.MARK) == al.BASE
    shown_base = _evaluated(sc, ob)
    sc.allset_anim_layer_index = 1
    shown_layer = _evaluated(sc, ob)
    keep, ad.action = ad.action, None
    none = _evaluated(sc, ob)
    ad.action = keep
    assert max(abs(a - b) for r1, r2 in zip(shown_base, none) for a, b in zip(r1, r2)) < 1e-6
    assert max(abs(a - b) for r1, r2 in zip(shown_layer, none) for a, b in zip(r1, r2)) < 1e-6
    # the base is unchanged where the layer has no keys and the layer adds 2 at frame 6
    sc.frame_set(6)
    assert abs(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).location.x
               - (al.base_curve(ob, "location", 0).evaluate(6) + 2.0)) < 1e-4
    sc.frame_set(1)


def test_readers_follow_the_selected_layer():
    """Like Maya: Base selected -> ticks 1 12 24 (as before any layer); AnimLayer1
    selected -> 1 6 18 24 (layer tx + base ry, which is not in the layer); Graph Editor curves = the shown layer's."""
    sc, ob, (ticks0, _e) = _layered()
    assert ticks0 == [1.0, 12.0, 24.0], ticks0
    sc.allset_anim_layer_index = 0
    assert _ticks(ob) == ticks0, _ticks(ob)
    assert {(fc.data_path, fc.array_index) for fc in compat.id_fcurves(ob)} == {("location", 0),
                                                                               ("rotation_euler", 1)}
    sc.allset_anim_layer_index = 1
    assert _ticks(ob) == [1.0, 6.0, 18.0, 24.0], _ticks(ob)
    assert [(fc.data_path, fc.array_index) for fc in compat.id_fcurves(ob)] == [("location", 0)]
    # mute keeps the layer's keys shown (Maya state e)
    al.layers(sc)[1].mute = True
    assert _ticks(ob) == [1.0, 6.0, 18.0, 24.0]
    al.layers(sc)[1].mute = False


def test_channel_box_states():
    """Maya: every layer member is teal (kit state LAYERED) in every layer state, keyed or not; a channel outside the
    layer keeps its BaseAnimation state (ry pink between keys, red on a key)."""
    sc, ob, _b = _layered()
    for index in (0, 1):
        sc.allset_anim_layer_index = index
        for f in (6, 12):
            sc.frame_set(f)
            assert cb.channel_state(ob, "tx") == 'LAYERED', (index, f)
            assert cb.channel_state(ob, "sx") == 'LAYERED', (index, f)
            assert cb.channel_state(ob, "ry") == 'ANIMATED', (index, f, cb.channel_state(ob, "ry"))
        sc.frame_set(24)
        assert cb.channel_state(ob, "ry") == 'KEYED'
    sc.frame_set(1)


def test_zero_key_layer():
    """Maya: identity keys on every member attribute at the current time, existing layer keys kept,
    the value at a key frame overwritten; nothing on BaseAnimation."""
    sc, ob, _b = _layered()
    sc.frame_set(12)
    assert al.zero_key(sc, [ob]) > 0
    curves = {(fc.data_path, fc.array_index): fc for fc in al.layer_curves(ob, "AnimLayer1")}
    tx = curves[("location", 0)]
    assert [(round(k.co.x), round(k.co.y, 4)) for k in tx.keyframe_points] == [(6, 2.0), (12, 0.0), (18, -1.0)]
    assert abs(curves[("scale", 0)].evaluate(12) - 1.0) < 1e-6
    assert ("rotation_euler", 1) not in curves, "ry is not in the layer"
    assert abs(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).location.x - 5.0) < 1e-4
    sc.frame_set(6)
    al.zero_key(sc, [ob])
    assert abs(tx.evaluate(6)) < 1e-6
    sc.allset_anim_layer_index = 0
    assert al.zero_key(sc, [ob]) is None
    sc.frame_set(1)


def test_merge_layers_keeps_the_result():
    """Maya (Base + AnimLayer1): the layer is gone, every member channel with layer keys gets a base
    key on every frame 1-24 holding the result, ry keeps its 2 keys, the result is unchanged."""
    sc, ob, _b = _layered()
    before = _evaluated(sc, ob)
    name = al._strip(al.tracks(ob)["AnimLayer1"]).action.name
    assert al.merge_down(sc, "AnimLayer1")
    assert "AnimLayer1" not in al.tracks(ob) and [e.name for e in al.layers(sc)] == [al.BASE]
    assert name not in bpy.data.actions, "the merged layer's action is deleted"
    assert ob.animation_data.action.get(al.MARK) == al.BASE
    tx = al.base_curve(ob, "location", 0)
    assert [round(k.co.x) for k in tx.keyframe_points] == list(range(1, 25))
    assert len(al.base_curve(ob, "rotation_euler", 1).keyframe_points) == 2
    after = _evaluated(sc, ob)
    for f, r1, r2 in zip(FRAMES, before, after):
        if 1 <= f <= 24:
            assert max(abs(a - b) for a, b in zip(r1, r2)) < 1e-4, (f, r1, r2)


def test_delete_layer_leaves_no_shown_action():
    sc, ob, _b = _layered()
    act = ob.animation_data.action
    assert act.get(al.MARK) == "AnimLayer1"
    bpy.ops.allset.anim_layer_delete()
    ad = ob.animation_data
    assert ad.action is not None and ad.action.get(al.MARK) == al.BASE
    assert "AnimLayer1_pCube1" not in bpy.data.actions
