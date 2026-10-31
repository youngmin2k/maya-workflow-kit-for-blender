"""Channel Box (proxies, channel selection, slider, Channels menu) and Layer Editor."""

import math
from importlib import import_module

import bpy

import kit

cb = import_module(kit.MODULE + ".ui.channel_box")
le = import_module(kit.MODULE + ".ui.layer_editor")
maya_patches = import_module(kit.MODULE + ".keymap.maya_patches")


def _obj(name, loc=(0, 0, 0)):
    ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    return ob


def _select(objs, active):
    bpy.context.view_layer.update()  # sync objects created/removed by the test
    for o in bpy.context.view_layer.objects:
        o.select_set(o in objs)
    bpy.context.view_layer.objects.active = active


def _fresh(n=2):
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    obs = [_obj(f"cb{i}", (i, 0, 0)) for i in range(n)]
    _select(obs, obs[0])
    cb.set_selected_channels([])
    return obs


P = lambda: bpy.context.scene.allset_cb  # noqa: E731


# --- proxies -------------------------------------------------------------------------------

def test_proxy_reads_lead_and_writes_all_selected():
    a, b = _fresh()
    a.location.x, b.location.x = 1.0, 5.0
    assert abs(P().tx - 1.0) < 1e-6, "getter shows the lead (active) object"
    P().tx = 3.0
    assert a.location.x == 3.0 and b.location.x == 3.0, "setter edits every selected object"
    P().rx = math.radians(45)
    assert abs(math.degrees(b.rotation_euler.x) - 45) < 1e-4
    P().sz = 2.0
    assert a.scale.z == 2.0 and b.scale.z == 2.0
    P().v = False
    assert a.hide_viewport and b.hide_viewport
    P().v = True
    assert not a.hide_viewport


def test_proxy_skips_locked_and_autokeys():
    a, b = _fresh()
    b.lock_location[0] = True
    P().tx = 7.0
    assert a.location.x == 7.0 and b.location.x == 1.0, "locked channel is not edited"
    assert cb.is_locked(b, "tx") and not cb.is_locked(a, "tx")
    sc = bpy.context.scene
    sc.allset_auto_key = True               # the kit's Maya Auto Key, not Blender's auto keying
    try:
        # Maya Auto Key: only channels that already have keys
        P().ty = 2.0
        assert cb.fcurve(a, "ty") is None, "Maya Auto Key doesn't key an unkeyed channel"
        a.keyframe_insert("location", index=1)
        P().ty = 3.0
        assert cb.fcurve(a, "ty") is not None
    finally:
        sc.allset_auto_key = False


def test_proxy_units():
    props = cb.ALLSET_PG_channel_box.bl_rna.properties
    assert props["tx"].unit == 'LENGTH' and props["rx"].unit == 'ROTATION'
    assert props["tx"].precision == 3


# --- channel selection, state ------------------------------------------------------------

def test_channel_selection_rules():
    _fresh()
    assert cb.select_channel("tx") == ["tx"]
    assert cb.select_channel("ty", "EXTEND") == ["tx", "ty"]
    assert cb.select_channel("tx", "TOGGLE") == ["ty"]
    assert cb.select_channel("rz", "SET") == ["rz"]


def test_channel_state():
    a, _b = _fresh()
    scene = bpy.context.scene
    assert cb.channel_state(a, "tx") is None
    scene.frame_set(1)
    a.keyframe_insert("location", index=0, frame=1)
    assert cb.channel_state(a, "tx", frame=1) == 'KEYED'
    assert cb.channel_state(a, "tx", frame=10) == 'ANIMATED'
    fc = a.driver_add("location", 1)
    fc.driver.expression = "0"
    assert cb.channel_state(a, "ty") == 'DRIVEN'


def test_custom_attributes_listed():
    a, _b = _fresh()
    a["speed"] = 1.5
    a["flag"] = True
    a["_private"] = 1
    a["allset_cb_hidden"] = ""
    assert cb.custom_keys(a) == ["flag", "speed"]
    assert cb.get_value(a, "cp:speed") == 1.5


# --- slider ----------------------------------------------------------------------------------

def test_slider_math():
    assert abs(cb.slider_delta(100, "LOC") - 1.0) < 1e-9              # 100 px = 1 m at Medium
    assert abs(cb.slider_delta(100, "LOC", ctrl=True) - 0.1) < 1e-9
    assert abs(cb.slider_delta(100, "LOC", shift=True) - 10.0) < 1e-9
    assert abs(cb.slider_delta(100, "LOC", speed=0.01) - 0.01) < 1e-9
    assert abs(math.degrees(cb.slider_delta(10, "ROT")) - 5.0) < 1e-9
    assert cb.slider_delta(-10, "SCALE", hyperbolic=True) < 0


def test_slider_targets_and_apply():
    a, b = _fresh()
    assert cb.slider_targets(bpy.context) == [], "no channel selected -> slider passes through"
    cb.set_selected_channels(["tx", "sy", "v"])
    b.lock_scale[1] = True
    pairs = cb.slider_targets(bpy.context)
    assert set((o.name, k) for o, k in pairs) == {("cb0", "tx"), ("cb1", "tx"), ("cb0", "sy")}
    starts = {(o, k): cb.get_value(o, k) for o, k in pairs}
    cb.slider_apply(starts, 50)
    assert abs(a.location.x - 0.5) < 1e-6 and abs(b.location.x - 1.5) < 1e-6, "relative per object"
    assert abs(a.scale.y - 1.5) < 1e-6 and b.scale.y == 1.0


# --- Channels menu -----------------------------------------------------------------------------

def test_key_selected_and_key_all():
    a, b = _fresh()
    cb.set_selected_channels(["tx"])
    assert bpy.ops.allset.cb_key_selected() == {'FINISHED'}
    assert cb.fcurve(a, "tx") and cb.fcurve(b, "tx") and not cb.fcurve(a, "ty")
    cb.set_selected_channels([])
    cb._set_flag_list(a, cb.NONKEYABLE_PROP, ["sz"])
    bpy.ops.allset.cb_key_all()
    assert cb.fcurve(a, "rz") and cb.fcurve(a, "sx") and not cb.fcurve(a, "sz"), "nonkeyable skipped"


def test_breakdown_mute_delete_break():
    a, _b = _fresh()
    cb.set_selected_channels(["tx"])
    bpy.ops.allset.cb_breakdown_selected()
    fc = cb.fcurve(a, "tx")
    assert fc.keyframe_points[0].type == 'BREAKDOWN'
    bpy.ops.allset.cb_mute(mute=True)
    assert fc.mute
    bpy.ops.allset.cb_mute(mute=False)
    assert not fc.mute
    bpy.ops.allset.cb_delete_keys()
    assert cb.fcurve(a, "tx") is None
    d = a.driver_add("location", 0)
    d.driver.expression = "1"
    bpy.ops.allset.cb_break_connections()
    assert cb.driver(a, "tx") is None


def test_lock_hide_keyable_duplicate():
    a, b = _fresh()
    cb.set_selected_channels(["ty", "rx"])
    bpy.ops.allset.cb_lock(lock=True)
    assert a.lock_location[1] and b.lock_rotation[0]
    bpy.ops.allset.cb_lock(lock=False)
    assert not a.lock_location[1]
    bpy.ops.allset.cb_hide(lock=True)
    assert cb.is_hidden(a, "ty") and a.lock_location[1]
    bpy.ops.allset.cb_show_all()
    assert not cb.is_hidden(a, "ty")
    bpy.ops.allset.cb_lock(lock=False)
    bpy.ops.allset.cb_keyable(keyable=False)
    assert not cb.is_keyable(a, "rx")
    bpy.ops.allset.cb_keyable(keyable=True)
    assert cb.is_keyable(a, "rx")
    a.location.y, b.location.y = 4.0, 9.0
    a.rotation_euler.x = 0.3
    bpy.ops.allset.cb_duplicate_values()
    assert b.location.y == 4.0 and abs(b.rotation_euler.x - 0.3) < 1e-6


def test_inputs_modifier_props():
    a, _b = _fresh()
    mod = a.modifiers.new("Smooth", 'SUBSURF')
    props = cb._modifier_props(mod)
    assert "levels" in props and "name" not in props and "show_viewport" not in props
    assert not [p for p in props if p.startswith(("open_", "is_")) or p.endswith("_panel")], props


# --- Layer Editor ------------------------------------------------------------------------------

def test_layer_new_from_selected():
    a, b = _fresh()
    scene = bpy.context.scene
    assert bpy.ops.allset.layer_new(selected=True) == {'FINISHED'}
    layer = le.layers(scene)[0]
    assert layer.name == "layer1" and set(o.name for o in layer.objects) == {"cb0", "cb1"}
    r = le.root(scene)
    assert bpy.context.view_layer.layer_collection.children[r.name].exclude, "root excluded"
    assert a.name in scene.collection.objects, "objects keep their own collection"
    assert a.visible_get(), "layer membership alone does not hide"


def test_layer_toggles():
    a, b = _fresh()
    scene = bpy.context.scene
    layer = le.new_layer(scene, [a])
    st = layer.allset_layer
    st.visible = False
    assert a.hide_get() and not b.hide_get() and not a.hide_viewport, "layer V = view-layer flag"
    st.visible = True
    st.display_type = "TEMPLATE"
    assert a.hide_select and a.display_type == 'WIRE'
    st.display_type = "REFERENCE"
    assert a.hide_select and a.display_type == 'TEXTURED'
    bpy.ops.allset.layer_cycle_type(layer=layer.name)
    assert st.display_type == "NORMAL" and not a.hide_select


def test_layer_exclusive_membership_and_delete():
    a, b = _fresh()
    scene = bpy.context.scene
    l1 = le.new_layer(scene, [a, b])
    l1.allset_layer.visible = False
    l2 = le.new_layer(scene, [a])
    assert a.name not in l1.objects and a.name in l2.objects, "one display layer per object"
    assert not a.hide_get(), "takes the new layer's state"
    le.delete_layer(scene, l1)
    assert not b.hide_get() and b.name not in [c.name for c in le.layers(scene)]


def test_layer_playback_handlers():
    a, b = _fresh()
    scene = bpy.context.scene
    layer = le.new_layer(scene, [a])
    layer.allset_layer.playback = False
    le.on_playback_pre(scene)
    assert a.hide_get() and not b.hide_get() and not a.hide_viewport, "layer V = view-layer flag"
    le.on_playback_post(scene)
    assert not a.hide_get()
    assert le.on_playback_pre in bpy.app.handlers.animation_playback_pre


def test_layer_assign_remove_select_ops():
    a, b = _fresh()
    scene = bpy.context.scene
    _select([a], a)
    bpy.ops.allset.layer_new(selected=False)
    _select([a, b], a)
    bpy.ops.allset.layer_assign(remove=False)
    layer = le.active_layer(bpy.context)
    assert len(layer.objects) == 2
    _select([b], b)
    bpy.ops.allset.layer_assign(remove=True)
    assert [o.name for o in layer.objects] == ["cb0"]
    _select([], None)
    bpy.ops.allset.layer_select()
    assert [o.name for o in bpy.context.selected_objects] == ["cb0"]
    name, before = layer.name, len(le.layers(scene))
    bpy.ops.allset.layer_delete()
    assert len(le.layers(scene)) == before - 1 and name not in bpy.data.collections


# --- keymap ------------------------------------------------------------------------------------

def test_slider_keymap_in_front_of_tool_mmb():
    kc = kit.maya_kc()
    for km_name in maya_patches.SLIDER_TOOL_KEYMAPS:
        # the emulated Alt+LMB tumble (#242) leads and passes through otherwise
        first_mmb = next(k for k in kc.keymaps[km_name].keymap_items
                         if k.type == 'MIDDLEMOUSE' and k.idname != "allset.emulated_tumble")
        assert first_mmb.idname == "allset.cb_virtual_slider", km_name
    assert any(k.idname == "allset.cb_virtual_slider"
               for k in kc.keymaps["Object Mode"].keymap_items)
