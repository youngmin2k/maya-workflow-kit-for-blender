"""Step 211 (audit 16 fix batch, #117): Light Linking submenu, Maya max + 1 names for sets / layers / anim layers /
characters / bookmarks, Ctrl+V pasted__ names under a group, startup cameras first in the Outliner, AE tab row, nHair
option boxes = the Curves windows. Maya values."""

from importlib import import_module

import bpy
from mathutils import Vector

import kit


def m(name):
    return import_module(f"{kit.MODULE}.{name}")


def _clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    bpy.context.scene.timeline_markers.clear()


def _cube(name="pCube1", coll=None):
    me = bpy.data.meshes.new(name.replace("pCube", "pCubeShape"))
    me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    ob = bpy.data.objects.new(name, me)
    (coll or bpy.context.scene.collection).objects.link(ob)
    return ob


def _select(obs):
    for o in bpy.context.scene.objects:
        o.select_set(o in obs)
    if obs:
        bpy.context.view_layer.objects.active = obs[0]


# --- (1) Windows > Relationship Editors > Light Linking -----------------------------------------------------

def test_light_linking_submenu_opens_the_kit_editor():
    mm, ms = m("ui.menu_map"), m("ui.menu_sets")
    # since the step 219 menus the submenu is in the menu data itself, no run-time CHILDREN entry
    md = m("ui.menu_data")
    win = next(it for it in md.MENUS["mainWindowMenu"][3] if it[0] == "Relationship Editors")
    assert ("Light Linking", [("Light-Centric",), ("Object-Centric",)]) in win[1]
    for label, mode in (("Light-Centric", 'LIGHT_CENTRIC'), ("Object-Centric", 'OBJECT_CENTRIC')):
        act = mm.MAP[f"Windows/Relationship Editors/Light Linking/{label}"]
        assert act == ("v3d", "allset.light_linking_editor", {"mode": mode}), act
    assert "Windows/Relationship Editors/Light Linking" not in mm.MAP, "a submenu now, not the Properties tab"
    # same editor as Lighting/Shading > Light Linking Editor
    assert mm.MAP["Lighting/Shading/Light Linking Editor"][1] == "allset.light_linking_editor"
    paths = {p for p, *_rest in ms.iter_items()} if hasattr(ms, "iter_items") else set()
    if paths:
        assert "Windows/Relationship Editors/Light Linking/Object-Centric" in paths


# --- (2) names: Maya max + 1 ---------------------------------------------------------------------------------

def test_set_names_count_past_the_highest():
    _clear()
    sets = m("operators.sets")
    for _ in range(3):
        sets.create()
    assert [c.name for c in sets.all_sets()] == ["set1", "set2", "set3"]
    sets.delete(bpy.data.collections["set2"])
    assert sets.next_name() == "set4", "Maya: set1 set2 set3, delete set2 -> set4"
    bpy.data.collections["set3"].name = "set10"
    assert sets.next_name() == "set11", "Maya: renamed set10 -> set11"


def test_display_layer_names_count_past_the_highest():
    _clear()
    le = m("ui.layer_editor")
    for n in ("layer1", "layer3"):
        bpy.data.collections.new(n)
    assert le.next_layer_name() == "layer4", "Maya: layer1 layer2 layer3, delete layer2 -> layer4"
    bpy.data.collections.new("layer10")
    assert le.next_layer_name() == "layer11"


def test_anim_layer_and_character_and_bookmark_names():
    _clear()
    al = m("operators.anim_layers")

    class _E:
        def __init__(self, name):
            self.name = name
    real = al.layers
    try:
        al.layers = lambda scene: [_E("BaseAnimation"), _E("AnimLayer1"), _E("AnimLayer3")]
        assert al.unique_name(bpy.context.scene) == "AnimLayer4", "Maya: AnimLayer1 .. 3, delete 2 -> AnimLayer4"
    finally:
        al.layers = real
    cs = m("operators.character_sets")
    assert cs.next_name({"character1", "character3"}, "character") == "character4"
    assert cs.next_name({"character10"}, "character") == "character11"
    assert cs.next_name(set(), "character") == "character1"
    bm = m("operators.bookmarks")
    sc = bpy.context.scene
    sc.timeline_markers.new("bookmark1", frame=1)
    sc.timeline_markers.new("bookmark3", frame=5)
    assert bm.next_name(sc) == "bookmark4", "Maya: timeSliderBookmark1 .. 3, delete 2 -> timeSliderBookmark4"


def test_naming_doc_says_no_gap_filling():
    doc = m("operators.naming").__doc__
    assert "lowest one free" not in doc and "gaps are not filled" in doc


# --- (2b) Ctrl+V: pasted__ names under a group (Maya) ---------------------------------------------------------

def test_paste_names_group_and_selection():
    _clear()
    gk = m("operators.global_keys4")
    cube = _cube("pCube1")
    cube.location = (1.0, 2.0, 3.0)
    _select([cube])
    assert bpy.ops.view3d.copybuffer() == {'FINISHED'}
    assert bpy.ops.allset.paste() == {'FINISHED'}
    objs = bpy.data.objects
    assert "group" in objs and "pasted__pCube1" in objs, sorted(objs.keys())
    pasted, grp = objs["pasted__pCube1"], objs["group"]
    assert pasted.parent == grp and grp.parent is None
    assert pasted.data.name == "pasted__pCubeShape1", pasted.data.name
    assert (pasted.matrix_world.translation - Vector((1, 2, 3))).length < 1e-6, "world position kept"
    assert grp.matrix_world.translation.length < 1e-9, "group at the origin"
    assert [o.name for o in bpy.context.selected_objects] == ["group"], "Maya selects only the group"
    assert bpy.context.view_layer.objects.active == grp
    assert objs["pCube1"].data.name == "pCubeShape1", "the original keeps its names"
    # second paste: Maya -> group1 | pasted__pCube1 (a second short name under another group); Blender names are
    # unique, so the kit counts up
    assert bpy.ops.allset.paste() == {'FINISHED'}
    assert "group1" in objs and "pasted__pCube2" in objs, sorted(objs.keys())
    assert objs["pasted__pCube2"].parent == objs["group1"]
    assert objs["pasted__pCube2"].data.name == "pasted__pCubeShape2"
    bpy.ops.ed.undo_push(message="x")
    assert gk.pasted_name("pCube1", {"pasted__pCube1", "pasted__pCube7"}) == "pasted__pCube8"
    assert gk.paste_group_name(set()) == "group" and gk.paste_group_name({"group"}) == "group1"
    assert gk.paste_group_name({"group", "group1", "group5"}) == "group6"


# --- (3) startup cameras first in the Outliner ----------------------------------------------------------------

def _shown(coll):
    """The top rows Blender's Outliner shows for ``coll``'s link order (its qsort rotation, ui/outliner_order.py)."""
    oo = m("ui.outliner_order")
    top = [o.name for o in coll.objects if o.parent is None]
    return oo.display_order(top, oo.rotates_small_lists())


def _maya_scene():
    _clear()
    sc = bpy.context.scene
    coll = bpy.data.collections.new("Collection")
    sc.collection.children.link(coll)
    sc.unit_settings.system, sc.unit_settings.length_unit, sc.unit_settings.scale_length = 'METRIC', 'CENTIMETERS', 1.0
    return sc, coll


def test_startup_cameras_lead_the_dag_and_stay_hidden():
    sc, coll = _maya_scene()
    early = _cube("pCube1", coll)
    _select([early])
    stc = m("operators.startup_cameras")
    cams = stc.ensure(sc, bpy.context.view_layer)
    assert [c.name for c in cams] == ["persp", "top", "front", "side"]
    assert _shown(coll) == ["persp", "top", "front", "side", "pCube1"], "cameras first in the Outliner"
    assert early.select_get() and bpy.context.view_layer.objects.active == early, "user selection kept"
    for c in cams:
        assert c.hide_viewport and c.hide_render and c.type == 'CAMERA'
    assert stc.ensure(sc) == cams, "idempotent"
    unit = m("operators.units").maya_unit(sc)
    persp, top = cams[0], cams[1]
    # Maya persp (28, 21, 28) Y-up = Blender (28, -28, 21) x unit, looking at the origin
    assert (persp.matrix_world.translation - Vector((28, -28, 21)) * unit).length < 1e-6
    look = persp.matrix_world.to_3x3() @ Vector((0, 0, -1))
    assert look.angle(-persp.matrix_world.translation) < 0.01
    assert persp.data.lens == 35.0 and persp.data.sensor_width == 36.0 and persp.data.type == 'PERSP'
    assert top.data.type == 'ORTHO' and abs(top.data.ortho_scale - 30 * unit) < 1e-6
    assert (top.matrix_world.to_3x3() @ Vector((0, 0, -1)) - Vector((0, 0, -1))).length < 1e-6, "top looks down"
    front = cams[2]
    assert (front.matrix_world.to_3x3() @ Vector((0, 0, -1)) - Vector((0, 1, 0))).length < 1e-6, "front looks +Y"
    # the Outliner draws only the cameras the scene doesn't have
    os_ = m("ui.outliner_sets")
    assert [e[1] for e in os_.default_entries(sc)] == ["defaultLightSet", "defaultObjectSet"]
    assert [e[1] for e in os_.default_entries()][:4] == ["persp", "top", "front", "side"]


def test_startup_cameras_cant_be_deleted_and_stay_out_of_exports():
    sc, coll = _maya_scene()
    stc = m("operators.startup_cameras")
    cams = stc.ensure(sc, bpy.context.view_layer)
    cube = _cube("pCube1", coll)
    dag = m("operators.dag")
    assert dag.delete_hierarchy(bpy.context, [cams[0], cube]) == 1, "Maya: Non-deletable node 'persp'"
    assert "persp" in bpy.data.objects and "pCube1" not in bpy.data.objects
    cube = _cube("pCube2", coll)
    _select([cube])
    with stc.excluded(sc, bpy.context.view_layer):
        assert not any(stc.is_startup(o) for o in sc.objects)
    m("ui.outliner_order").sync(sc, bpy.context.view_layer)
    assert _shown(coll) == ["persp", "top", "front", "side", "pCube2"], "linked back first"
    assert cube.select_get() and bpy.context.view_layer.objects.active == cube


def test_maya_outliner_lists_in_creation_order():
    class _Space:
        pass
    sp = _Space()
    sp.use_sort_alpha = True
    m("ui.maya_outliner").setup(sp)
    assert sp.use_sort_alpha is False


# --- (4) AE tab row ---------------------------------------------------------------------------------------

def test_ae_tab_window_is_one_scrolling_row():
    tw = m("ui.attribute_editor").tab_window
    widths = [60, 110, 150, 80]
    assert tw(widths, 500, 2, 40) == (0, 4, False), "all fit: one row"
    assert tw(widths, None, 0, 40) == (0, 4, False)
    a, b, over = tw(widths, 300, 2, 40)          # room 260
    assert over and a <= 2 < b and sum(widths[a:b]) <= 260, (a, b)
    a, b, over = tw(widths, 100, 3, 40)
    assert over and (a, b) == (3, 4), "the current tab is always shown"
    a, b, over = tw(widths, 280, 0, 40)
    assert over and a == 0 and b == 2


# --- (5) nHair Modify Curves option boxes = the Curves windows ---------------------------------------------------

def test_nhair_modify_curves_boxes_open_the_curves_windows():
    ow = m("operators.option_windows")
    for label, key in (("Bend", "bend_curves"), ("Curl", "curl_curves"), ("Scale Curvature", "scale_curvature")):
        w = ow.find_path(f"nHair/Modify Curves/{label}")
        assert w is not None and w.key == key, (label, w and w.key)
        assert ow.find_path(f"Curves/{label}") is w
    assert m("ui.menu_sets").option_kind("nHair/Modify Curves/Bend") == "window"


# --- (3b) Outliner order compensation (ui/outliner_order.py) ----------------------------------------------------

def test_outliner_rotation_rule_is_inverted():
    oo = m("ui.outliner_order")
    for n in range(0, 14):
        want = list(range(n))
        assert oo.display_order(oo.base_for(want)) == want, n
    # in the GUI (4.5, Windows): linked persp top front side pCube1 pSphere1 -> shown from top
    assert oo.display_order(["p", "t", "f", "s", "c", "y"]) == ["t", "f", "s", "c", "y", "p"]
    assert oo.display_order(list("abcdefghi")) == list("abcdefghi"), "9 and more: Blender's quicksort keeps them"
    assert oo.base_for(["a", "b"], rotate=False) == ["a", "b"]


def test_outliner_sync_keeps_creation_order_children_and_state():
    sc, coll = _maya_scene()
    oo = m("ui.outliner_order")
    stc = m("operators.startup_cameras")
    stc.ensure(sc, bpy.context.view_layer)
    a, b = _cube("pCube1", coll), _cube("pCube2", coll)
    grp = bpy.data.objects.new("group1", None)
    coll.objects.link(grp)
    kids = [_cube(f"pCube{i}", coll) for i in (3, 4, 5)]
    for k in kids:
        k.parent = grp
    _select([b])
    a.hide_set(True)
    m("operators.sets").create(objects=[a])            # a kit set is a collection outside the scene: still synced
    oo.sync(sc, bpy.context.view_layer, rotate=True)
    links = [o.name for o in coll.objects]
    top = [n for n in links if bpy.data.objects[n].parent is None]
    assert oo.display_order(top) == ["persp", "top", "front", "side", "pCube1", "pCube2", "group1"], links
    under = [n for n in links if bpy.data.objects[n].parent == grp]
    assert under == ["pCube3", "pCube4", "pCube5"], links       # child lists draw in link order (not rotated)
    assert b.select_get() and bpy.context.view_layer.objects.active == b and a.hide_get(), "state kept"
    assert oo.sync(sc, bpy.context.view_layer, rotate=True) is False, "nothing to do the second time"
    # a second collection: left alone (Blender's base order crosses collections)
    other = bpy.data.collections.new("other")
    sc.collection.children.link(other)
    _cube("pCube9", other)
    assert oo.sync(sc, bpy.context.view_layer, rotate=True) is False


def test_reparent_goes_last_and_mmb_place_keeps_order():
    sc, coll = _maya_scene()
    oo = m("ui.outliner_order")
    od = m("operators.outliner_drag")
    parenting = m("operators.parenting")
    a, b, c, d = (_cube(n, coll) for n in ("pCube1", "pCube2", "pCube3", "pCube4"))
    oo.sync(sc, bpy.context.view_layer, rotate=True)

    def shown(parent=None):
        links = [o.name for o in coll.objects if o.parent == parent]
        return oo.display_order(links) if parent is None else links
    assert shown() == ["pCube1", "pCube2", "pCube3", "pCube4"]
    parenting.parent_maya([b], a)                    # Maya: P puts pCube2 under pCube1
    parenting.unparent([b])                          # ... and back to the world: last among the world's nodes
    oo.sync(sc, bpy.context.view_layer, rotate=True)
    assert shown() == ["pCube1", "pCube3", "pCube4", "pCube2"], shown()
    assert oo.place(sc, bpy.context.view_layer, [d], a, False, od.reordered)    # MMB pCube4 before pCube1
    assert shown() == ["pCube4", "pCube1", "pCube3", "pCube2"], shown()
    parenting.parent_maya([c, b], a)
    oo.sync(sc, bpy.context.view_layer, rotate=True)
    assert shown(a) == ["pCube3", "pCube2"] and shown() == ["pCube4", "pCube1"]
