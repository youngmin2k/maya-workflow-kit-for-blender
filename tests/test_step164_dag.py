"""Maya DAG rules for a parent: hiding a parent hides its descendants without
touching their own Visibility, Delete / Export Selection / Isolate take the hierarchy."""

import os
from importlib import import_module

import bpy

import kit

dag = import_module(kit.MODULE + ".operators.dag")
visibility = import_module(kit.MODULE + ".operators.visibility")
layer_editor = import_module(kit.MODULE + ".ui.layer_editor")
ow = import_module(kit.MODULE + ".operators.option_windows")

IO = os.path.join(os.environ.get("ALLSET_TEST_TMP", bpy.app.tempdir), "dag164")


def _scene():
    """group1 > pCube1 (Maya-named, through the kit's create / group), pCube2 beside it; group1 selected."""
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)
    ow.store(visibility.TOGGLE_KEY, {"first_selection": "Independent"})
    bpy.ops.allset.create(kind='CUBE')
    c1 = bpy.context.active_object
    bpy.ops.allset.create(kind='CUBE')
    c2 = bpy.context.active_object
    for o in bpy.context.scene.objects:
        o.select_set(o == c1)
    bpy.context.view_layer.objects.active = c1
    bpy.ops.allset.group()
    g = bpy.context.active_object
    for o in bpy.context.scene.objects:
        o.select_set(o == g)
    bpy.context.view_layer.update()
    assert c1.parent == g and g.name == "group1" and c1.name == "pCube1", (c1.parent, g.name, c1.name)
    return g, c1, c2


def _upd():
    bpy.context.view_layer.update()
    dag.sync()


def test_h_on_a_parent_hides_the_child_but_not_its_channel():
    g, c1, c2 = _scene()
    bpy.ops.allset.visibility(action='TOGGLE')
    _upd()
    assert g.hide_viewport and not c1.visible_get(), (g.hide_viewport, c1.visible_get())
    assert not c1.hide_viewport, "the child's own Visibility channel stays on (Maya)"
    assert c2.visible_get()
    bpy.ops.allset.visibility(action='TOGGLE')
    _upd()
    assert not g.hide_viewport and c1.visible_get() and dag.MARK not in c1


def test_channel_box_visibility_and_own_hidden_child():
    g, c1, _c2 = _scene()
    g.hide_viewport = True                       # the Channel Box Visibility row
    _upd()
    assert not c1.visible_get()
    c1.hide_viewport = True                      # the child hidden on its own
    g.hide_viewport = False
    _upd()
    assert not c1.visible_get(), "Maya: showing the parent leaves a child hidden on its own hidden"
    c1.hide_viewport = False
    _upd()
    assert c1.visible_get()


def test_ctrl_h_deselects_and_shift_h_shows():
    g, c1, _c2 = _scene()
    bpy.ops.allset.visibility(action='HIDE')
    _upd()
    assert g.hide_viewport and not c1.visible_get() and not g.select_get()
    bpy.ops.allset.visibility(action='SHOW_LAST')
    _upd()
    assert c1.visible_get()


def test_hide_unselected_keeps_the_selected_hierarchy():
    g, c1, c2 = _scene()
    bpy.ops.allset.visibility(action='HIDE_UNSELECTED')
    _upd()
    assert c1.visible_get() and not c2.visible_get(), (c1.visible_get(), c2.visible_get())


def test_display_layer_hides_members_children():
    g, c1, c2 = _scene()
    coll = layer_editor.new_layer(bpy.context.scene, [g])
    coll.allset_layer.visible = False
    _upd()
    assert not g.visible_get() and not c1.visible_get() and c2.visible_get()
    assert not c1.hide_viewport
    coll.allset_layer.visible = True
    _upd()
    assert g.visible_get() and c1.visible_get()


def test_delete_takes_the_hierarchy():
    g, c1, c2 = _scene()
    shape = c1.data.name
    assert bpy.ops.allset.delete() == {'FINISHED'}
    names = {o.name for o in bpy.data.objects}
    assert names == {c2.name}, names
    assert shape not in bpy.data.meshes, "pCubeShape1 goes with pCube1 (Maya)"
    # the menu item and the Delete key use it
    menu_map = import_module(kit.MODULE + ".ui.menu_map")
    assert menu_map.MAP["Edit/Delete"] == "allset.delete"
    kc = kit.maya_kc()
    om = kc.keymaps["Object Mode"]
    assert any(i.idname == "allset.delete" and i.type == 'DEL' and not i.shift for i in om.keymap_items)
    assert not any(i.idname == "object.delete" and i.type == 'DEL' and not i.shift and i.active
                   for i in om.keymap_items)


def test_export_selection_takes_the_children():
    os.makedirs(IO, exist_ok=True)
    g, c1, c2 = _scene()
    path = os.path.join(IO, "group1.fbx")
    if os.path.exists(path):
        os.remove(path)
    res = bpy.ops.allset.file_dialog('EXEC_DEFAULT', mode='EXPORT_SELECTION', export_type='FBX', filepath=path)
    assert res == {'FINISHED'} and os.path.exists(path)
    assert g.select_get() and not c1.select_get(), "the selection is put back"
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    res = bpy.ops.allset.file_dialog('EXEC_DEFAULT', mode='IMPORT', import_type='AUTO', filepath=path)
    assert res == {'FINISHED'}
    names = sorted(o.name for o in bpy.data.objects)
    assert len(names) == 2 and any(n.startswith("group1") for n in names) and any(n.startswith("pCube1") for n in names), names


def test_isolate_selects_the_hierarchy_for_local_view():
    g, c1, _c2 = _scene()
    with dag.selected_hierarchy(bpy.context):
        assert g.select_get() and c1.select_get()
    assert g.select_get() and not c1.select_get()
    kc = kit.maya_kc()
    assert any(i.idname == "allset.isolate" and i.type == 'ONE' and i.ctrl for i in kc.keymaps["3D View"].keymap_items)


def test_unregister_shows_what_the_parent_rule_hid():
    g, c1, _c2 = _scene()
    g.hide_viewport = True
    _upd()
    assert dag.MARK in c1
    dag.release_all()
    assert dag.MARK not in c1 and not c1.hide_get()


def test_blender_hide_on_a_parent_keeps_the_child_visible():
    """Blender's own eye / H hide (``hide_set``) on a parent hides only that object, like in Blender: the kit's
    parent rule follows Visibility and display layers only."""
    g, c1, c2 = _scene()
    g.hide_set(True)
    _upd()
    assert not g.visible_get()
    assert c1.visible_get() and dag.MARK not in c1, (c1.visible_get(), dag.MARK in c1)
    g.hide_set(False)
    _upd()
    assert c1.visible_get() and g.visible_get()


def test_visibility_off_on_a_parent_still_hides_the_child():
    """Maya's Hide (Visibility off) on a group hides its children and a node parented under it."""
    g, c1, c2 = _scene()
    g.hide_viewport = True
    _upd()
    assert not c1.visible_get() and dag.MARK in c1
    c2.parent = g
    _upd()
    assert not c2.visible_get(), "a node parented under a hidden group is hidden"
    c2.parent = None
    g.hide_viewport = False
    _upd()
    assert c1.visible_get() and c2.visible_get()


def test_hair_under_a_blender_hidden_surface_stays_visible():
    """A hair Curves object parented to a surface mesh hidden with Blender's eye (a usual setup in files made in
    Blender) stays visible."""
    g, c1, c2 = _scene()
    scalp = c2
    scalp.parent = None
    hair = bpy.data.objects.new("hair", bpy.data.hair_curves.new("hair"))
    bpy.context.scene.collection.objects.link(hair)
    hair.parent = scalp
    scalp.hide_set(True)
    _upd()
    assert hair.visible_get() and dag.MARK not in hair, (hair.visible_get(), dag.MARK in hair)
    bpy.data.objects.remove(hair)
