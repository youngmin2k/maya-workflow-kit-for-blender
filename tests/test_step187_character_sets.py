"""Maya Character Sets on Blender Keying Sets.

pCube1 has a keyable custom attribute ``custom``; pCube2 / pCube3 plain cubes."""


from importlib import import_module

import bpy

import kit


def cs():
    return import_module(kit.MODULE + ".operators.character_sets")


def cb():
    return import_module(kit.MODULE + ".ui.channel_box")


T, R = ("translateX", "translateY", "translateZ"), ("rotateX", "rotateY", "rotateZ")


def maya(ob, extra=()):
    return sorted([f"{ob}.{a}" for a in T + R + tuple(extra)])


def scene():
    sc = bpy.context.scene
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    while sc.keying_sets:
        cs().remove_character(sc, sc.keying_sets[0])
    if cs().PARENT in sc:
        del sc[cs().PARENT]
    bpy.context.window_manager.allset_character_nodes = ""
    obs = []
    for name in ("pCube1", "pCube2", "pCube3"):
        me = bpy.data.meshes.new(name + "Shape")
        ob = bpy.data.objects.new(name, me)
        sc.collection.objects.link(ob)
        obs.append(ob)
    obs[0]["custom"] = 0.0
    sc.frame_set(5)
    return obs


def select(*obs):
    for ob in bpy.context.scene.objects:
        ob.select_set(ob in obs)
    bpy.context.view_layer.objects.active = obs[0] if obs else None


def op(opname, **kw):
    """Run an allset operator; an ERROR report (Maya's error line) raises in Python -> 'CANCELLED'."""
    try:
        return getattr(bpy.ops.allset, opname)('EXEC_DEFAULT', True, **kw)
    except RuntimeError as e:
        print("op error:", e)
        return {'CANCELLED'}


def members(name):
    sc = bpy.context.scene
    return sorted(cs().member_names(sc, cs().find(sc, name)))


def keyed():
    out = []
    for ob in bpy.context.scene.objects:
        for fc in kit.fcurves(ob) or ():
            out.append(f"{ob.name}.{cs().maya_attr(fc.data_path, fc.array_index)}")
    return sorted(out)


def clear_keys():
    for ob in bpy.context.scene.objects:
        ob.animation_data_clear()


def test_create_like_maya():
    a, b, c = scene()
    select(a)
    op("character_create")
    sc = bpy.context.scene
    assert members("character1") == maya("pCube1", ("custom",)), members("character1")
    assert cs().current(sc).bl_label == "character1", "the new set becomes current"
    select(b)
    op("character_create")
    assert members("character2") == maya("pCube2")
    assert cs().current(sc).bl_label == "character2"
    select()
    op("character_create")
    assert members("character3") == [], "nothing selected = an empty character"


def test_set_key_keys_the_current_character():
    a, b, c = scene()
    select(a)
    op("character_create")
    for sel in ((b,), ()):
        clear_keys()
        select(*sel)
        bpy.ops.allset.set_key('EXEC_DEFAULT', True)
        assert keyed() == maya("pCube1", ("custom",)), (sel, keyed())
    # Shift+W / E keep keying the selection
    clear_keys()
    select(b)
    bpy.ops.allset.set_key('EXEC_DEFAULT', True, channels="TRANSLATE")
    bpy.ops.allset.set_key('EXEC_DEFAULT', True, channels="ROTATE")
    assert keyed() == maya("pCube2"), keyed()
    # no current character: S keys the selection, scale and visibility included
    op("character_set_current", name="")
    assert cs().current(bpy.context.scene) is None
    clear_keys()
    select(a)
    bpy.ops.allset.set_key('EXEC_DEFAULT', True)
    want = sorted(maya("pCube1", ("custom", "scaleX", "scaleY", "scaleZ", "visibility")))
    assert keyed() == want, keyed()


def test_subcharacter_add_remove_merge():
    a, b, c = scene()
    sc = bpy.context.scene
    select(b)
    res = op("character_create", sub=True)
    assert res == {'CANCELLED'}, "Maya: Must have a current character."
    select(a)
    op("character_create")
    select(b)
    op("character_create", sub=True)
    assert members("subCharacter1") == maya("pCube2")
    assert members("character1") == sorted(maya("pCube1", ("custom",)) + ["subCharacter1"])
    assert cs().current(sc).bl_label == "character1", "the current character stays"
    clear_keys()
    select()
    bpy.ops.allset.set_key('EXEC_DEFAULT', True)
    assert keyed() == sorted(maya("pCube1", ("custom",)) + maya("pCube2")), "keys the subcharacter too"
    # Add / Remove = the Channel Box's selected channels
    select(c)
    cb().set_selected_channels([])
    assert op("character_edit", add=True) == {'CANCELLED'}, "No attributes are selected in the Channel Box."
    cb().set_selected_channels(["tx", "ry"])
    op("character_edit", add=True)
    assert "pCube3.translateX" in members("character1") and "pCube3.rotateY" in members("character1")
    select(a)
    cb().set_selected_channels(["tx"])
    op("character_edit", add=False)
    assert "pCube1.translateX" not in members("character1")
    # Merge: two picked character nodes, into the last picked
    select(c)
    cb().set_selected_channels([])
    op("character_set_current", name="")
    op("character_create")                     # character2 = pCube3 T / R
    wm = bpy.context.window_manager
    select()
    wm.allset_character_nodes = "character1,character2"
    op("character_merge")
    names = [ks.bl_label for ks in sc.keying_sets]
    assert "character1" not in names and "character2" in names, names
    m = members("character2")
    assert "pCube1.rotateX" in m and "pCube3.translateZ" in m and "subCharacter1" in m, m
    assert cs().current(sc).bl_label == "character2"
    wm.allset_character_nodes = "character2"
    assert op("character_merge") == {'CANCELLED'}, "Select the characters to be merged."


def test_edit_needs_a_character():
    a, b, c = scene()
    select(a)
    cb().set_selected_channels(["tx"])
    assert op("character_edit", add=True) == {'CANCELLED'}, "Must have a current character or select a character."


def test_select_members_and_node():
    a, b, c = scene()
    select(a, b)
    op("character_create")
    select(c)
    op("character_select", name="character1")
    assert {o.name for o in bpy.context.selected_objects} == {"pCube1", "pCube2"}
    op("character_select", name="character1", node=True)
    assert not bpy.context.selected_objects
    assert [ks.bl_label for ks in cs().picked(bpy.context)] == ["character1"]


def test_pure_rules():
    m = cs()
    assert m.next_name({"character1", "character3"}, "character") == "character4"   # Maya max + 1
    assert m.merge_target(["character1", "character2"], {}) == "character2"
    assert m.merge_target(["subCharacter1", "character1"], {"subCharacter1": "character1"}) == "character1"
    assert m.maya_attr("location", 2) == "translateZ" and m.maya_attr('["custom"]', -1) == "custom"
    assert m.maya_attr("hide_viewport", -1) == "visibility"


def test_menus_map_the_character_items():
    mm = import_module(kit.MODULE + ".ui.menu_map")
    for menu in ("Key", "Control"):
        for label in ("Create Character Set", "Create Subcharacter Set", "Attribute Editor", "Add to Character Set",
                      "Remove from Character Set", "Merge Character Sets", "Select Character Set Node",
                      "Select Character Set Members", "Set Current Character Set"):
            assert f"{menu}/{label}" in mm.MAP, (menu, label)
