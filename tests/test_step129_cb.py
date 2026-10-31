"""One Maya visibility (#26), Channel Box channel ranges + one value into every selected channel
(#6), Layer Editor rows / order (#7)."""

from importlib import import_module

import bpy

import kit

cb = import_module(kit.MODULE + ".ui.channel_box")
le = import_module(kit.MODULE + ".ui.layer_editor")
visibility = import_module(kit.MODULE + ".operators.visibility")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
maya_patches = import_module(kit.MODULE + ".keymap.maya_patches")


def _fresh(n=2):
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    obs = []
    for i in range(n):
        ob = bpy.data.objects.new(f"pCube{i + 1}", bpy.data.meshes.new(f"pCube{i + 1}"))
        bpy.context.scene.collection.objects.link(ob)
        ob.location.x = float(i)
        obs.append(ob)
    bpy.context.view_layer.update()
    _select(*obs)
    cb.set_selected_channels([])
    return obs


def _select(*obs):
    for o in bpy.context.scene.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = obs[0] if obs else None


def _vis(action):
    assert bpy.ops.allset.visibility(action=action) == {'FINISHED'}


def _shown(ob):
    bpy.context.view_layer.update()
    return ob.visible_get()


P = lambda: bpy.context.scene.allset_cb  # noqa: E731


# --- #26 one visibility -------------------------------------------------------------------------------------------

def test_h_writes_the_channel_box_visibility():
    a, b = _fresh()
    _select(a)
    _vis('TOGGLE')
    assert a.hide_viewport and not _shown(a), "h hides through Maya's visibility attribute"
    assert cb.get_value(a, "v") is False, "the Channel Box Visibility row shows off"
    _vis('TOGGLE')
    assert not a.hide_viewport and a.select_get(), "h again shows it, still selected"


def test_channel_box_visibility_comes_back_with_display_show():
    a, b = _fresh()
    cb.set_value(b, "v", False)
    assert not _shown(b)
    assert menu_map.MAP["Display/Show"] == ("allset.visibility", {"action": 'SHOW_ALL'})
    _vis('SHOW_ALL')
    assert _shown(b) and not b.hide_viewport


def test_display_hide_menu_is_maya_visibility():
    assert menu_map.MAP["Display/Hide"] == ("allset.visibility", {"action": 'HIDE'})


def test_hide_and_show_last():
    a, b, c = _fresh(3)
    _select(a)
    _vis('HIDE')
    assert a.hide_viewport and not a.select_get()
    _select(b)
    _vis('HIDE_UNSELECTED')
    assert a.hide_viewport and c.hide_viewport and not b.hide_viewport
    _vis('SHOW_LAST')
    assert not c.hide_viewport and a.hide_viewport


def test_layer_visibility_is_an_override():
    a, b = _fresh()
    coll = le.new_layer(bpy.context.scene, [a, b])
    cb.set_value(a, "v", False)
    coll.allset_layer.visible = False
    assert not _shown(a) and not _shown(b)
    assert not b.hide_viewport, "the layer never writes the object's own visibility"
    coll.allset_layer.visible = True
    assert not _shown(a), "own Visibility 0 stays hidden when the layer comes back"
    assert _shown(b)
    assert cb.get_value(b, "v") is True


def test_layer_template_keeps_own_display():
    a, b = _fresh()
    a.display_type = 'BOUNDS'
    b.hide_select = True
    coll = le.new_layer(bpy.context.scene, [a, b])
    st = coll.allset_layer
    st.display_type = "TEMPLATE"
    assert a.display_type == 'WIRE' and a.hide_select
    st.display_type = "REFERENCE"
    assert a.hide_select
    st.display_type = "NORMAL"
    assert a.display_type == 'BOUNDS' and not a.hide_select, "the object's own display type comes back"
    assert b.hide_select, "an object that was unselectable stays so"
    st.display_type = "TEMPLATE"
    le.remove_objects(bpy.context.scene, coll, [a])
    assert a.display_type == 'BOUNDS' and not a.hide_select
    le.delete_layer(bpy.context.scene, coll)
    assert b.hide_select and b.display_type == 'TEXTURED'


def test_layer_delete_shows_members_again():
    a, b = _fresh()
    coll = le.new_layer(bpy.context.scene, [a])
    coll.allset_layer.visible = False
    assert not _shown(a)
    le.delete_layer(bpy.context.scene, coll)
    assert _shown(a)


def test_layer_playback_uses_the_layer_flag():
    a, b = _fresh()
    coll = le.new_layer(bpy.context.scene, [a])
    coll.allset_layer.playback = False
    le.on_playback_pre(bpy.context.scene)
    assert not _shown(a) and not a.hide_viewport
    le.on_playback_post(bpy.context.scene)
    assert _shown(a)


# --- #6 channel ranges and one value into all of them -------------------------------------------------------------

def test_channel_range_in_drawn_order():
    a, b = _fresh()
    keys = cb.drawn_keys(a)
    assert keys[:3] == ["tx", "ty", "tz"] and keys[-1] == "v"
    assert cb.channel_range(a, "tx", "sz") == ["tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"]
    assert cb.channel_range(a, "sz", "rx") == ["rx", "ry", "rz", "sx", "sy", "sz"]
    a["fingerCurl"] = 1.0
    assert cb.drawn_keys(a)[-1] == "cp:fingerCurl"


def test_select_range_modes():
    a, b = _fresh()
    cb.select_range(a, "tx", "tz", "SET")
    assert cb.selected_channels() == ["tx", "ty", "tz"]
    cb.select_range(a, "sx", "sy", "ADD")
    assert cb.selected_channels() == ["tx", "ty", "tz", "sx", "sy"]
    cb.select_range(a, "ry", "ry", "SET")
    assert cb.selected_channels() == ["ry"]


def test_sel_proxies_show_and_toggle_selection():
    a, b = _fresh()
    cb.set_selected_channels(["ty"])
    assert P().ty_sel and not P().tx_sel
    P().tx_sel = True
    assert set(cb.selected_channels()) == {"tx", "ty"}
    P().ty_sel = False
    assert cb.selected_channels() == ["tx"]


def test_one_value_into_every_selected_channel_of_every_object():
    a, b = _fresh()
    cb.select_range(a, "tx", "sz", "SET")
    P().ry_text = "2"
    for ob in (a, b):
        assert tuple(ob.location) == (2.0, 2.0, 2.0) or all(abs(v - 2.0) < 1e-6 for v in ob.location)
        assert all(abs(v - 2.0) < 1e-6 for v in ob.scale)
    import math
    assert abs(math.degrees(b.rotation_euler.x) - 2.0) < 1e-4


def test_relative_entry_per_channel():
    a, b = _fresh()
    a.location = (1, 2, 3)
    b.location = (10, 20, 30)
    cb.select_range(a, "tx", "tz", "SET")
    P().tx_text = "+=5"
    assert tuple(round(v, 4) for v in a.location) == (6, 7, 8)
    assert tuple(round(v, 4) for v in b.location) == (15, 25, 35)


def test_field_owner_for_the_popup_editor():
    a, b = _fresh()
    a["curl"] = 0.5
    cb.rebuild_rows()
    assert cb.field_owner(bpy.context, "tx") == (P(), "tx_text")
    owner, prop = cb.field_owner(bpy.context, "cp:curl")
    assert prop == "text" and owner.name == "curl"
    assert cb.field_owner(bpy.context, "cp:nothing") == (None, None)


def test_custom_row_sel_proxy():
    a, b = _fresh()
    a["curl"] = 0.5
    b["curl"] = 0.0
    cb.rebuild_rows()
    row = next(r for r in P().rows if r.kind == "CUSTOM" and r.name == "curl")
    row.sel = True
    assert cb.selected_channels() == ["cp:curl"]


def test_channel_cell_key_from_property_path():
    assert cb.cell_key("allset_cb.tx_text", None) == ("tx", "VALUE")
    assert cb.cell_key("allset_cb.sz_sel", None) == ("sz", "NAME")
    assert cb.cell_key("allset_cb.something", None) is None
    a, b = _fresh()
    a["curl"] = 0.5
    cb.rebuild_rows()
    i = next(i for i, r in enumerate(P().rows) if r.name == "curl")
    assert cb.cell_key(f"allset_cb.rows[{i}].text", bpy.context.scene) == ("cp:curl", "VALUE")
    assert cb.cell_key(f"allset_cb.rows[{i}].sel", bpy.context.scene) == ("cp:curl", "NAME")


def test_hover_keymap_item_first_in_property_editor():
    items = [a for a in maya_patches.ADDED if a[1] == "allset.cb_hover"]
    assert items and items[0][0] == "Property Editor" and items[0][2]["type"] == "MOUSEMOVE"
    assert "allset.cb_hover" in maya_patches.PASS_THROUGH_FIRST


# --- #7 Layer Editor ----------------------------------------------------------------------------------------------

def test_layers_newest_first_and_move():
    a, b = _fresh()
    sc = bpy.context.scene
    l1 = le.new_layer(sc, [a])
    l2 = le.new_layer(sc, [b])
    l3 = le.new_layer(sc, [])
    assert [c.name for c in le.display_order(sc)] == [l3.name, l2.name, l1.name], "Maya lists the newest on top"
    le.move_layer(sc, l1, -1)       # up in the list
    assert [c.name for c in le.display_order(sc)] == [l3.name, l1.name, l2.name]
    le.move_layer(sc, l1, -1)
    le.move_layer(sc, l1, -1)       # already on top: stays
    assert [c.name for c in le.display_order(sc)] == [l1.name, l3.name, l2.name]
    assert set(o.name for o in l1.objects) == {a.name} and set(o.name for o in l2.objects) == {b.name}


def test_layer_move_operator():
    a, b = _fresh()
    sc = bpy.context.scene
    l1 = le.new_layer(sc, [a])
    l2 = le.new_layer(sc, [b])
    sc.allset_layer_index = le.layers(sc).index(l1)
    assert bpy.ops.allset.layer_move(direction='UP') == {'FINISHED'}
    assert [c.name for c in le.display_order(sc)] == [l1.name, l2.name]
    assert le.active_layer(bpy.context) == l1
