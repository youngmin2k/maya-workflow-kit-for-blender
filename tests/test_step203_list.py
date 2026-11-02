"""Lane B (#110): Graph Editor / Dope Sheet List > Load / Add Selected Objects with Auto Load, Curves > Pin /
Unpin Channel, Show > Attributes filters (Hidden, Driven by Anim Curve / Expression / Driven Key, User Defined),
Show > Objects > IkHandles / Sets / Characters, List > Show Upstream Curves / Hierarchy Below (ui/editor_chrome.py),
like Maya."""

import types
from importlib import import_module

import bpy

import kit

chrome = import_module(kit.MODULE + ".ui.editor_chrome")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")


def _clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.armatures, bpy.data.actions):
        for d in list(coll):
            coll.remove(d)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for ks in list(bpy.context.scene.keying_sets):
        bpy.context.scene.keying_sets.active = ks
        bpy.ops.anim.keying_set_remove()
    chrome._expanded.clear()
    chrome._picked["ids"], chrome._picked["sig"] = set(), None
    chrome._pinned.clear()
    chrome._kit_hidden.clear()
    wm = bpy.context.window_manager
    for name, _label, _tip in chrome.FLAGS:
        setattr(wm, name, name in chrome.FLAGS_ON)       # default state
    wm.allset_show_characters = False


def _space(kind='GRAPH_EDITOR', only_selected=True):
    return types.SimpleNamespace(type=kind, mode='FCURVES' if kind == 'GRAPH_EDITOR' else 'DOPESHEET',
                                 dopesheet=types.SimpleNamespace(show_only_selected=only_selected, show_hidden=True,
                                                                 filter_text="", filter_collection=None))


def _cube(name, keys=("location",)):
    ob = bpy.data.objects.new(name, bpy.data.meshes.new(name + "Shape"))
    bpy.context.scene.collection.objects.link(ob)
    for path in keys:
        if path == "location":
            ob.keyframe_insert("location", index=0, frame=1)
            ob.keyframe_insert("location", index=1, frame=1)
        else:
            ob.keyframe_insert(path, frame=1)
    return ob


def _select(*obs):
    for ob in bpy.context.scene.objects:
        ob.select_set(ob in obs)


def _names(space):
    return [ob.name for ob in chrome.listed_objects(bpy.context, space)]


def _labels(space):
    return [(k, n.name if k != "ATTR" else chrome.attr_label(fc)) for k, n, fc in chrome.rows(bpy.context, space)]


# --- List > Load / Add Selected Objects, Auto Load ---------------------------------------------------------------

def test_load_keeps_the_list_and_turns_auto_load_off():
    _clear()
    a, b = _cube("pCube1"), _cube("pCube2")
    sp = _space()
    _select(a)
    assert _names(sp) == ["pCube1"] and chrome.auto_load(sp)
    chrome.load_selected(bpy.context, sp)
    assert not chrome.auto_load(sp) and not sp.dopesheet.show_only_selected
    coll = sp.dopesheet.filter_collection
    assert coll is not None and coll.get(chrome.LIST_MARK) and list(coll.objects) == [a]
    _select(b)                               # Maya: a loaded list doesn't follow the selection
    assert _names(sp) == ["pCube1"]
    assert not chrome.sync_space(bpy.context, sp) or list(coll.objects) == [a]


def test_add_selected_adds_to_the_list():
    _clear()
    a, b, c = _cube("pCube1"), _cube("pCube2"), _cube("pCube3")
    sp = _space()
    _select(a)
    chrome.load_selected(bpy.context, sp)
    _select(b)
    chrome.load_selected(bpy.context, sp, add=True)
    assert _names(sp) == ["pCube1", "pCube2"]
    assert set(sp.dopesheet.filter_collection.objects) == {a, b}
    _select(c)
    chrome.load_selected(bpy.context, sp)       # Load replaces
    assert _names(sp) == ["pCube3"]


def test_auto_load_off_freezes_the_list_and_add_appends():
    # Maya: unchecking Auto Load freezes the list shown (selecting others no longer changes it); Add appends
    _clear()
    a, b = _cube("pCube1"), _cube("pCube2")
    sp = _space()
    _select(a)
    chrome.set_auto_load(bpy.context, sp, False)
    assert not chrome.auto_load(sp) and _names(sp) == ["pCube1"]
    _select(b)
    assert _names(sp) == ["pCube1"]
    chrome.load_selected(bpy.context, sp, add=True)
    assert _names(sp) == ["pCube1", "pCube2"] and not chrome.auto_load(sp)
    chrome.set_auto_load(bpy.context, sp, False)          # already off: nothing changes
    assert _names(sp) == ["pCube1", "pCube2"]


def test_load_and_add_greyed_while_auto_load_is_on():
    # Maya: Load / Add Selected Objects are disabled while Auto Load Selected Objects is checked (factory)
    _clear()
    a = _cube("pCube1")
    sp = _space()
    _select(a)
    op = bpy.types.ALLSET_OT_graph_list
    ctx = types.SimpleNamespace(space_data=sp)
    assert chrome.auto_load(sp) and not op.poll(ctx)
    chrome.set_auto_load(bpy.context, sp, False)
    assert op.poll(ctx)
    assert bpy.context.window_manager.bl_rna.properties["allset_show_upstream"].default


def test_load_with_nothing_selected_empties_the_list():
    _clear()
    _cube("pCube1")
    sp = _space()
    _select()
    chrome.load_selected(bpy.context, sp)
    assert _names(sp) == [] and len(sp.dopesheet.filter_collection.objects) == 0


def test_auto_load_on_drops_the_loaded_list():
    _clear()
    a, b = _cube("pCube1"), _cube("pCube2")
    sp = _space()
    _select(a)
    chrome.load_selected(bpy.context, sp)
    _select(b)
    chrome.set_auto_load(bpy.context, sp, True)
    assert chrome.auto_load(sp) and _names(sp) == ["pCube2"]
    # Blender's own filter again: Only Show Selected, no collection filter, kit list removed
    assert sp.dopesheet.show_only_selected and sp.dopesheet.filter_collection is None
    assert not [c for c in bpy.data.collections if c.get(chrome.LIST_MARK)]
    chrome.set_auto_load(bpy.context, sp, False)        # freezes the selection (Maya's locked copy)
    assert not chrome.auto_load(sp) and _names(sp) == ["pCube2"]


def test_loaded_joints_only():
    _clear()
    arm = bpy.data.objects.new("skeleton1", bpy.data.armatures.new("skeleton1"))
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    for i, name in enumerate(("joint1", "joint2")):
        eb = arm.data.edit_bones.new(name)
        eb.head, eb.tail = (0, 0, i), (0, 0, i + 1)
    bpy.ops.object.mode_set(mode='POSE')
    for name in ("joint1", "joint2"):
        arm.pose.bones[name].keyframe_insert("location", index=0, frame=1)
    _select(arm)
    cb = import_module(kit.MODULE + ".ui.channel_box")      # Bone.select is gone in 5.x: the kit shim
    for pb in arm.pose.bones:
        cb.set_bone_selected(pb, pb.name == "joint1")
    sp = _space()
    chrome.load_selected(bpy.context, sp)
    for pb in arm.pose.bones:
        cb.set_bone_selected(pb, pb.name == "joint2")
    joints = [n.name for k, n, _c in chrome.listed_nodes(bpy.context, sp) if k == "JOINT"]
    bpy.ops.object.mode_set(mode='OBJECT')
    assert joints == ["joint1"], joints


# --- Pin / Unpin Channel -----------------------------------------------------------------------------------------

def test_pinned_channel_stays_when_the_selection_changes():
    _clear()
    a, b = _cube("pCube1"), _cube("pCube2")
    sp = _space()
    _select(a)
    # nothing picked: the selected node's row is highlighted = all its channels (Maya, a node row)
    assert [(n.name, fc.array_index) for n, fc in chrome._target_rows(bpy.context, sp)] == [("pCube1", 0),
                                                                                             ("pCube1", 1)]
    _pick(("pCube1", "location", 0))                       # the Translate X row highlighted
    targets = chrome._target_rows(bpy.context, sp)
    assert [(n.name, fc.array_index) for n, fc in targets] == [("pCube1", 0)]
    chrome._pinned.update((chrome.node_key(n), fc.data_path, fc.array_index) for n, fc in targets)
    _select(b)
    # pinned nodes not in the list follow it (order not confirmed)
    assert _labels(sp) == [("OBJECT", "pCube2"), ("ATTR", "Translate X"), ("ATTR", "Translate Y"),
                           ("OBJECT", "pCube1"), ("ATTR", "Translate X")], _labels(sp)
    # Blender has to draw pCube1 too: a kit list (pCube1 + the selection), Auto Load kept on
    assert chrome.needs_kit_list(bpy.context, sp)
    chrome.sync_space(bpy.context, sp)
    assert set(sp.dopesheet.filter_collection.objects) == {a, b} and chrome.auto_load(sp)
    # pCube1's unpinned Translate Y is hidden while only its pin keeps it drawn
    chrome.sync_hidden(bpy.context, [sp])
    ty = next(fc for fc in chrome.object_curves(a) if fc.array_index == 1)
    tx = next(fc for fc in chrome.object_curves(a) if fc.array_index == 0)
    assert ty.hide and not tx.hide
    # Unpin: back to Blender's Only Show Selected, the hidden curve shown again
    chrome._pinned.clear()
    chrome.sync_space(bpy.context, sp)
    chrome.sync_hidden(bpy.context, [sp])
    assert sp.dopesheet.show_only_selected and sp.dopesheet.filter_collection is None
    assert not ty.hide and not chrome._kit_hidden
    assert _names(sp) == ["pCube2"]


def _pick(*ids):
    chrome._picked["ids"], chrome._picked["sig"] = set(ids), chrome.selection_sig(bpy.context)


def test_pin_with_nothing_highlighted_pins_nothing():
    # Maya: nothing highlighted -> nothing pinned, "no channels selected"
    _clear()
    a = _cube("pCube1")
    sp = _space()
    _select(a)
    chrome.set_auto_load(bpy.context, sp, False)          # pCube1 stays listed ...
    _select()                                             # ... but is no longer selected: no highlight
    assert _names(sp) == ["pCube1"] and chrome._target_rows(bpy.context, sp) == []
    _pick("pCube1")                                       # its node row picked: all its channels
    assert len(chrome._target_rows(bpy.context, sp)) == 2


def test_picks_never_hide_a_pinned_curve():
    _clear()
    a = _cube("pCube1")
    sp = _space()
    _select(a)
    tx = next(fc for fc in chrome.object_curves(a) if fc.array_index == 0)
    ty = next(fc for fc in chrome.object_curves(a) if fc.array_index == 1)
    chrome._pinned.add(("pCube1", "location", 0))
    ctx = types.SimpleNamespace(scene=bpy.context.scene, space_data=sp)
    chrome.show_rows(ctx, {ty})
    assert not tx.hide and not ty.hide and ty.select and not tx.select


def test_pin_operators_registered():
    assert hasattr(bpy.types, "ALLSET_OT_graph_pin") and hasattr(bpy.types, "ALLSET_OT_graph_list")
    for path, op in (("Graph Editor/Curves/Pin Channel", "allset.graph_pin"),
                     ("Graph Editor/Curves/Unpin Channel", "allset.graph_pin"),
                     ("Graph Editor/List/Load Selected Objects", "allset.graph_list"),
                     ("Graph Editor/List/Add Selected Objects", "allset.graph_list"),
                     ("Dope Sheet/List/Load Selected Objects", "allset.graph_list"),
                     ("Dope Sheet/List/Add Selected Objects", "allset.graph_list")):
        assert menu_map.MAP[path][0] == op, path


# --- Show > Attributes -------------------------------------------------------------------------------------------

def _attr_rig():
    _clear()
    ob = _cube("pCube1")
    ob["speed"] = 1.0
    ob.keyframe_insert('["speed"]', frame=1)
    chrome_cb = import_module(kit.MODULE + ".ui.channel_box")
    chrome_cb._set_flag_list(ob, chrome_cb.HIDDEN_PROP, ["ty"])
    d = ob.driver_add("location", 2).driver           # expression
    d.type = 'SCRIPTED'
    d.expression = "frame"
    fc = ob.driver_add("scale", 0)                     # kit SDK driver
    v = fc.driver.variables.new()
    v.name = "sdk"
    fc.driver.type = 'AVERAGE'
    _select(ob)
    return ob


def _attr_labels(space):
    return [lbl for k, lbl in _labels(space) if k == "ATTR"]


def test_attribute_filters():
    _attr_rig()
    sp = _space()
    wm = bpy.context.window_manager
    # Maya: unfiltered = keyed and driven channels (expression Translate Z, driven key Scale X)
    assert _attr_labels(sp) == ["Translate X", "Translate Y", "Translate Z", "Scale X", "speed"], _attr_labels(sp)
    cases = (("allset_attr_hidden", ["Translate Y"]),
             ("allset_attr_anim_curve", ["Translate X", "Translate Y", "Scale X", "speed"]),
             ("allset_attr_expression", ["Translate Z"]),
             ("allset_attr_driven_key", ["Scale X"]),
             ("allset_attr_user_defined", ["speed"]))
    for prop, want in cases:
        setattr(wm, prop, True)
        try:
            assert _attr_labels(sp) == want, (prop, _attr_labels(sp))
        finally:
            setattr(wm, prop, False)
    wm.allset_attr_hidden = True
    wm.allset_attr_user_defined = True
    assert _attr_labels(sp) == ["Translate Y", "speed"]          # checked filters add up
    wm.allset_attr_hidden = wm.allset_attr_user_defined = False


def test_character_member_is_not_driven_by_anim_curve():
    # Maya: a character member's curve feeds the character node first -> not "Driven by Anim Curve"
    _clear()
    a = _cube("pCube1")
    ks = bpy.context.scene.keying_sets.new(idname="character1", name="character1")
    ks.paths.add(a, "location", index=1)
    sp = _space()
    _select(a)
    bpy.context.window_manager.allset_attr_anim_curve = True
    assert _attr_labels(sp) == ["Translate X"], _attr_labels(sp)


def test_attribute_filter_hides_unlisted_curves_and_clear_shows_them():
    ob = _attr_rig()
    sp = _space()
    wm = bpy.context.window_manager
    wm.allset_attr_user_defined = True
    chrome.sync_hidden(bpy.context, [sp])
    hidden = sorted((fc.data_path, fc.array_index) for fc in chrome.object_curves(ob) if fc.hide)
    assert hidden == [("location", 0), ("location", 1)], hidden
    wm.allset_attr_user_defined = False
    chrome.sync_hidden(bpy.context, [sp])
    assert not [fc for fc in chrome.object_curves(ob) if fc.hide] and not chrome._kit_hidden


# --- Show > Objects / List extras --------------------------------------------------------------------------------

def test_ik_handles_only():
    _clear()
    a = _cube("pCube1")
    handle = bpy.data.objects.new("ikHandle1", None)
    bpy.context.scene.collection.objects.link(handle)
    handle.keyframe_insert("location", index=0, frame=1)
    arm = bpy.data.objects.new("skeleton1", bpy.data.armatures.new("skeleton1"))
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.data.edit_bones.new("joint1")
    eb.head, eb.tail = (0, 0, 0), (0, 0, 1)
    bpy.ops.object.mode_set(mode='OBJECT')
    con = arm.pose.bones["joint1"].constraints.new('IK')
    con.target = handle
    sp = _space(only_selected=False)
    assert _names(sp) == ["ikHandle1", "pCube1"]
    bpy.context.window_manager.allset_show_ik_handles = True
    assert _names(sp) == ["ikHandle1"]
    assert chrome.needs_kit_list(bpy.context, sp)
    chrome.sync_space(bpy.context, sp)
    assert list(sp.dopesheet.filter_collection.objects) == [handle]
    _ = a


def test_sets_are_listed_as_nodes():
    _clear()
    sets = import_module(kit.MODULE + ".operators.sets")
    a, b = _cube("pCube1"), _cube("pCube2")
    sets.create("set1", [b])
    ks = bpy.context.scene.keying_sets.new(idname="character1", name="character1")
    ks.paths.add(a, "location", index=0)
    sp = _space()
    _select(a)
    bpy.context.window_manager.allset_show_sets = True
    # Maya: Sets lists only set nodes, a character is a set; a set row has no channels
    nodes = [(k, chrome.node_name(n), len(c)) for k, n, c in chrome.listed_nodes(bpy.context, sp)]
    assert nodes == [("CHARACTER", "character1", 1), ("SET", "set1", 0)], nodes
    assert chrome.drawn_objects(bpy.context, sp) == [a]          # the character's member
    assert [k for k, _n, _f in chrome.rows(bpy.context, sp)] == ["CHARACTER", "ATTR", "SET"]
    ds_space = _space('DOPESHEET_EDITOR')
    assert chrome.drawn_objects(bpy.context, ds_space) == [a]
    _ = b


def test_dope_sheet_characters_draw_members():
    _clear()
    a, b = _cube("pCube1"), _cube("pCube2")
    ks = bpy.context.scene.keying_sets.new(idname="character1", name="character1")
    ks.paths.add(b, "location", index=0)
    sp = _space('DOPESHEET_EDITOR')
    _select(a)
    assert chrome.drawn_objects(bpy.context, sp) == [a]
    bpy.context.window_manager.allset_show_characters = True      # Maya: only the character's channels
    assert chrome.drawn_objects(bpy.context, sp) == [b]
    chrome.sync_space(bpy.context, sp)
    assert list(sp.dopesheet.filter_collection.objects) == [b]


def test_hierarchy_below():
    # Maya: descendants' keys show in the object's rows; Blender's Dope Sheet can't merge them, the kit lists
    # the descendants. Graph Editor: no effect.
    _clear()
    a, child = _cube("pCube1"), _cube("pCube2")
    child.parent = a
    _select(a)
    wm = bpy.context.window_manager
    ds_space, ge_space = _space('DOPESHEET_EDITOR'), _space()
    assert not wm.allset_hierarchy_below                  # default off
    wm.allset_hierarchy_below = True
    assert _names(ds_space) == ["pCube1", "pCube2"] and _names(ge_space) == ["pCube1"]


def _sdk_rig():
    _clear()
    cube = _cube("pCube1", keys=())
    cube["userA"] = 0.0
    cube.keyframe_insert('["userA"]', frame=1)
    cube.keyframe_insert("location", index=0, frame=1)
    sphere = _cube("pSphere1", keys=())
    sphere.keyframe_insert("location", index=1, frame=1)
    fc = sphere.driver_add("scale", 0)                    # kit SDK driver: variable "sdk" reading pCube1.userA
    fc.driver.type = 'AVERAGE'
    v = fc.driver.variables.new()
    v.name = "sdk"
    v.type = 'SINGLE_PROP'
    v.targets[0].id = cube
    v.targets[0].data_path = '["userA"]'
    _select(sphere)
    return cube, sphere


def test_show_upstream_curves():
    # Maya: on (default) = under the driven-key channel "> pCube1.User A" (the SDK curve) and
    # "pCube1.User A" (the driver's own curve); off = only the channel's own rows
    cube, sphere = _sdk_rig()
    sp = _space()
    wm = bpy.context.window_manager
    assert wm.allset_show_upstream
    rows = chrome.rows(bpy.context, sp)
    got = [(k, chrome._up_label.get((k, fc.as_pointer())) if k.startswith("UP") else
            (n.name if k != "ATTR" else chrome.attr_label(fc))) for k, n, fc in rows]
    assert got == [("OBJECT", "pSphere1"), ("ATTR", "Translate Y"), ("ATTR", "Scale X"),
                   ("UP_SDK", "> pCube1.userA"), ("UP_CURVE", "pCube1.userA")], got
    up_curve = rows[-1][2]
    assert up_curve.data_path == '["userA"]'
    # Blender has to draw pCube1's userA curve, but not its Translate X
    assert set(chrome.drawn_objects(bpy.context, sp)) == {cube, sphere}
    assert up_curve in chrome.listed_curves(bpy.context, sp)
    chrome.sync_space(bpy.context, sp)                    # a kit list: pSphere1 + pCube1, Auto Load kept on
    assert set(sp.dopesheet.filter_collection.objects) == {cube, sphere} and chrome.auto_load(sp)
    chrome.sync_hidden(bpy.context, [sp])
    tx = next(fc for fc in chrome.object_curves(cube) if fc.data_path == "location")
    assert tx.hide and not up_curve.hide
    # Driven by Anim Curve hides the upstream rows, Driven by Driven Key keeps them
    wm.allset_attr_anim_curve = True
    assert not [r for r in chrome.rows(bpy.context, sp) if r[0].startswith("UP")]
    wm.allset_attr_anim_curve = False
    wm.allset_attr_driven_key = True
    assert [r[0] for r in chrome.rows(bpy.context, sp)] == ["OBJECT", "ATTR", "UP_SDK", "UP_CURVE"]
    wm.allset_attr_driven_key = False
    wm.allset_show_upstream = False
    assert [r[0] for r in chrome.rows(bpy.context, sp)] == ["OBJECT", "ATTR", "ATTR"]
    assert chrome.drawn_objects(bpy.context, sp) == [sphere]
    wm.allset_show_upstream = True


# --- menus, notices, unregister ----------------------------------------------------------------------------------

MAPPED = [f"Graph Editor/{p}" for p in (
    "List/Show Upstream Curves", "Show/Attributes/Hidden", "Show/Attributes/Driven by Anim Curve",
    "Show/Attributes/Driven by Expression", "Show/Attributes/Driven by Driven Key", "Show/Attributes/User Defined",
    "Show/Objects/IkHandles", "Show/Objects/Sets", "Show/Objects/Characters")] + [f"Dope Sheet/{p}" for p in (
    "List/Hierarchy Below", "Show/Objects/IkHandles", "Show/Objects/Sets", "Show/Objects/Characters",
    "Show/Attributes/Driven by Expression", "Show/Attributes/User Defined")]


def test_menu_items_mapped_without_notices():
    for path in MAPPED + ["Graph Editor/Curves/Pin Channel", "Graph Editor/List/Load Selected Objects",
                          "Dope Sheet/List/Add Selected Objects"]:
        assert path in menu_map.MAP, path
        assert path not in notices.NOTICES, path
    for path in ("Graph Editor/Show/Attributes/Published", "Dope Sheet/Show/Attributes/Published"):
        assert path not in menu_map.MAP, path


def test_icon_row_buttons_work():
    for editor in (chrome.GE, chrome.DS):
        spec = chrome._icon_spec(editor, "list_load")
        assert spec[2] == ("allset.graph_list", {"action": "LOAD"})
        assert chrome._icon_spec(editor, "list_auto_load")[2][1] == "window_manager.allset_auto_load"
    assert chrome._icon_spec(chrome.DS, "hierarchy_below")[2][1] == "window_manager.allset_hierarchy_below"
    assert "list_load" not in chrome.NOTICES and "hierarchy_below" not in chrome.NOTICES


def test_release_all_on_disable():
    _clear()
    a = _cube("pCube1")
    sp = _space()
    _select(a)
    chrome.load_selected(bpy.context, sp)
    chrome._pinned.add(("pCube1", "location", 0))
    fc = chrome.object_curves(a)[1]
    fc.hide = True
    chrome._kit_hidden.add(("OBJECT", "pCube1", fc.data_path, fc.array_index))
    kit.disable()
    try:
        assert not hasattr(bpy.types.WindowManager, "allset_auto_load")
        assert not hasattr(bpy.types.WindowManager, "allset_attr_hidden")
        assert not [c for c in bpy.data.collections if c.get("allset_list")]
        assert not fc.hide
    finally:
        kit.enable()


def test_dope_sheet_attribute_filter_keeps_objects_with_such_attributes():
    _attr_rig()
    b = _cube("pCube2")
    sp = _space('DOPESHEET_EDITOR', only_selected=False)
    assert _names(sp) == ["pCube1", "pCube2"]
    wm = bpy.context.window_manager
    wm.allset_attr_user_defined = True
    try:
        assert _names(sp) == ["pCube1"]
        assert chrome.needs_kit_list(bpy.context, sp)
        chrome.sync_space(bpy.context, sp)
        assert [o.name for o in sp.dopesheet.filter_collection.objects] == ["pCube1"]
    finally:
        wm.allset_attr_user_defined = False
    chrome.sync_space(bpy.context, sp)
    assert sp.dopesheet.filter_collection is None and not sp.dopesheet.show_only_selected
    _ = b
