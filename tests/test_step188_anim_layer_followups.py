"""Animation layer follow-ups, like Maya:
Auto Key on a layered object keys the selected layer only where that attribute already has keys on it, solved so the
result is the typed value; Channel Box > Channels > Add to / Remove From Selected Layers edit the layer's attributes
(a key on a non-member attribute goes to BaseAnimation, removing a keyed attribute deletes its layer curve);
Windows > Relationship Editors > Animation Layers opens the Layer Editor's Anim tab."""

from importlib import import_module

import bpy

import kit
import test_step180_anim_layers as t180

al = import_module(kit.MODULE + ".operators.anim_layers")
ak = import_module(kit.MODULE + ".operators.auto_key")
cb = import_module(kit.MODULE + ".ui.channel_box")


def base_tx(ob, frame):
    fc = al._fcurve(al.tracks(ob)[al.BASE].strips[0].action, "location", 0)
    return fc.evaluate(frame)


def layer_keys(ob, layer, path="location", index=0):
    tr = al.tracks(ob).get(layer)
    if tr is None:
        return None
    fc = al._fcurve(tr.strips[0].action, path, index)
    return None if fc is None else [(round(kp.co[0], 4), round(kp.co[1], 4)) for kp in fc.keyframe_points]


def test_auto_key_on_a_layer_keyed_attribute():
    """Maya autokey_layer_keyed: AnimLayer1 has a tx key; tx typed at frame 5 -> a layer key = value - base."""
    sc, ob = t180.scene()
    l1 = t180.new_layer(sc)
    t180.mkey(sc, ob, l1, "translateX", 1, 1.0)
    sc.frame_set(5)
    ob.location.x = 10.0
    assert ak.key_changed(ob, 5) == 1
    keys = layer_keys(ob, l1)
    want = 10.0 - base_tx(ob, 5)
    assert any(t == 5 and abs(v - want) < 1e-4 for t, v in keys), (keys, want)
    sc.frame_set(6)
    sc.frame_set(5)
    assert abs(ob.location.x - 10.0) < 1e-5, ob.location.x


def test_auto_key_skips_attributes_without_layer_keys():
    """Maya autokey: no key on the layer for tx (only BaseAnimation keys) -> nothing keyed, the value goes back."""
    sc, ob = t180.scene()
    l1 = t180.new_layer(sc)
    sc.allset_anim_layer_index = 1
    sc.frame_set(5)
    ob.location.x = 9.0
    assert ak.changed_layer_channels(ob, 5) == []
    assert ak.key_changed(ob, 5) == 0
    assert layer_keys(ob, l1) is None


def test_add_remove_selected_layers():
    sc, ob = t180.scene()
    bpy.ops.allset.anim_layer_create(from_selected=False)
    l1 = sc.allset_anim_layers[sc.allset_anim_layer_index].name
    assert l1 not in al.tracks(ob)
    cb.set_selected_channels(["tx", "ry"])
    bpy.ops.allset.anim_layer_attrs(add=True)
    assert sorted(al.member_keys(ob, l1)) == ["ry", "tx"], al.member_keys(ob, l1)
    # Maya setkey_nonmember: with the layer selected, a non-member attribute (ty) is keyed on BaseAnimation
    sc.frame_set(5)
    ob.location.y = 2.0
    assert cb.keyframe(ob, "ty")
    assert layer_keys(ob, l1, "location", 1) is None
    assert layer_keys(ob, al.BASE, "location", 1) == [(5.0, 2.0)]
    ob.location.x = 7.0
    assert cb.keyframe(ob, "tx")
    assert layer_keys(ob, l1) == [(5.0, round(7.0 - base_tx(ob, 5), 4))]
    # Maya remove of a keyed attribute: the layer curve goes, the value is BaseAnimation's again
    cb.set_selected_channels(["tx"])
    bpy.ops.allset.anim_layer_attrs(add=False)
    assert al.member_keys(ob, l1) == ["ry"] and layer_keys(ob, l1) is None
    sc.frame_set(6)
    sc.frame_set(5)
    assert abs(ob.location.x - base_tx(ob, 5)) < 1e-5
    cb.set_selected_channels(["ry"])
    bpy.ops.allset.anim_layer_attrs(add=False)
    assert l1 not in al.tracks(ob), "no attribute left: the object leaves the layer"


def test_relationship_editor_opens_the_anim_tab():
    mm = import_module(kit.MODULE + ".ui.menu_map")
    notices = import_module(kit.MODULE + ".ui.notices")
    act = mm.MAP["Windows/Relationship Editors/Animation Layers"]
    assert act[1] == "allset.dock_show" and act[2] == {"dock": 'CHANNEL_BOX', "le_tab": 'ANIM'}, act
    assert "Windows/Relationship Editors/Animation Layers" not in notices.NOTICES
    wm = bpy.context.window_manager
    wm.allset_le_tab = 'DISPLAY'
    bpy.ops.allset.dock_show(dock='CHANNEL_BOX', le_tab='ANIM')
    assert wm.allset_le_tab == 'ANIM'
