"""Modeling recipes replay older nodes transactionally and survive native Blender persistence."""
from importlib import import_module
import json
import os
from pathlib import Path

import bmesh
import bpy
import kit

ex = import_module(kit.MODULE+'.operators.extrude')
history = import_module(kit.MODULE+'.operators.model_history')
nodes = import_module(kit.MODULE+'.ui.node_attributes')
prim = import_module(kit.MODULE+'.operators.prim_history')


def chain(primitive=False):
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    if primitive:
        ob = prim.create_object(bpy.context, 'CUBE')
    else:
        bpy.ops.mesh.primitive_cube_add()
        ob = bpy.context.object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.scene.tool_settings.mesh_select_mode = (False, False, True)
    bm = bmesh.from_edit_mesh(ob.data)
    ex.deselect_all(bm)
    max(bm.faces, key=lambda face: face.normal.z).select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.extrude(thickness=.5) == {'FINISHED'}
    assert bpy.ops.allset.extrude(thickness=.25) == {'FINISHED'}
    assert len(history.read(ob)['nodes']) == 2
    return ob


def digest(ob):
    return (ex.coords_hash(bmesh.from_edit_mesh(ob.data)) if ob.mode == 'EDIT'
            else ex.mesh_coords_hash(ob.data))


def test_earlier_node_replays_downstream_and_exposes_distinct_channels():
    ob = chain()
    before = digest(ob)
    entries = history.records(ob)
    history.activate(ob, entries[0].history_id)
    node = nodes.target(bpy.context)
    assert isinstance(node, nodes.HistoryNode)
    node.commit(bpy.context, dict(node.params, thickness=1))
    assert digest(ob) != before
    assert history.read(ob)['nodes'][1]['params']['thickness'] == .25
    assert ex.current(ob) is not None
    cb = import_module(kit.MODULE+'.ui.channel_box')
    assert cb.model_key(entries[0], 'thickness') != cb.model_key(entries[1], 'thickness')
    assert cb.model_node(ob, cb.model_key(entries[0], 'thickness')).name == entries[0].name
    node.commit(bpy.context, dict(node.params, thickness=.5))
    assert digest(ob) == before


def test_upstream_divisions_preserve_the_downstream_cap_binding():
    ob = chain()
    data = json.loads(ob.data[history.KEY])
    history.edit(ob, data['nodes'][0]['id'], dict(data['nodes'][0]['params'], divisions=4))
    assert history.read(ob)['nodes'][0]['params']['divisions'] == 4
    assert history.read(ob)['nodes'][1]['params']['thickness'] == .25
    assert ex.current(ob) is not None
    assert abs(max(vertex.co.z for vertex in bmesh.from_edit_mesh(ob.data).verts)-1.75) < 1e-5


def test_creation_node_remains_editable_through_the_modeling_chain():
    ob = chain(primitive=True)
    before = digest(ob)
    owner, creation = prim.node_of(ob)
    assert owner is ob.data and creation['type'] == 'polyCube'
    assert prim.rebuild(bpy.context, ob, {'width': 3})['width'] == 3
    assert digest(ob) != before and len(history.read(ob)['nodes']) == 2
    assert prim.attrs(owner)['width'] == 3
    history.activate(ob, creation['name'])
    assert isinstance(nodes.target(bpy.context), nodes.CreationHistoryNode)


def test_duplicate_data_shares_immutable_input_and_has_independent_parameters():
    ob = chain()
    bpy.ops.object.mode_set(mode='OBJECT')
    copy = ob.copy()
    copy.data = ob.data.copy()
    bpy.context.scene.collection.objects.link(copy)
    original = digest(ob)
    data = history.read(copy)
    assert copy.data[history.BASE] == ob.data[history.BASE]
    history.edit(copy, data['nodes'][0]['id'], dict(data['nodes'][0]['params'], thickness=.75))
    assert digest(copy) != original and digest(ob) == original


def test_native_save_load_recovers_the_chain_and_input_mesh():
    ob = chain()
    bpy.ops.object.mode_set(mode='OBJECT')
    name = ob.name
    original = digest(ob)
    path = Path(os.environ['BLENDER_USER_CONFIG']).parent/'model_history.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    bpy.ops.wm.open_mainfile(filepath=str(path))
    ob = bpy.data.objects[name]
    assert digest(ob) == original
    assert len(history.read(ob)['nodes']) == 2
    assert ex.object_record(ob) is not None
    data = history.read(ob)
    history.edit(ob, data['nodes'][0]['id'], dict(data['nodes'][0]['params'], thickness=.8))
    assert digest(ob) != original


def test_delete_history_removes_recipe_and_external_edits_invalidate_it():
    ob = chain()
    bpy.ops.object.mode_set(mode='OBJECT')
    before = digest(ob)
    delete = import_module(kit.MODULE+'.operators.history')
    delete.delete_history(bpy.context, [ob])
    assert history.read(ob) is None and digest(ob) == before
    ob = chain()
    bpy.ops.object.mode_set(mode='OBJECT')
    ob.data.vertices[0].co.x += .2
    ob.data.update()
    history._valid.pop(ob.data.session_uid, None)
    assert history.ensure(ob) is None


def test_object_preview_and_commit_reuse_the_geometry_cache():
    from test_bridge_paths import bridge_object
    ob, record = bridge_object()
    bpy.ops.object.mode_set(mode='OBJECT')
    node = nodes.target(bpy.context)
    original_pre = record.pre
    values = dict(node.params, taper=.75)
    node.preview(bpy.context, values)
    assert record.fast_preview and record.pre is original_pre
    preview = digest(ob)
    node.commit(bpy.context, values)
    node.finish()
    assert digest(ob) == preview and record.pre is original_pre
    assert ex.object_record(ob) is record and not record.fast_preview


def test_whole_mesh_selection_uses_constant_size_history_metadata():
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=50, y_segments=50, size=2)
    for sequence in (bm.verts, bm.edges, bm.faces):
        for element in sequence:
            element.select = True
    selection = history._selection(bm)
    assert len(json.dumps(selection)) < 250
    history._select(bm, selection, 'wholeMesh')
    assert all(element.select for sequence in (bm.verts, bm.edges, bm.faces) for element in sequence)
    bm.free()


def test_legacy_channel_locks_remain_effective_and_can_be_unlocked():
    ob = chain()
    cb = import_module(kit.MODULE+'.ui.channel_box')
    cb.set_locked(ob, 'mh:FACE:thickness', True)
    key = cb.model_key(ex.current(ob), 'thickness')
    assert cb.is_locked(ob, key)
    cb.set_locked(ob, key, False)
    assert not cb.is_locked(ob, key)


def test_attribute_editor_tabs_route_shared_text_fields_to_each_node():
    ob = chain()
    ae = import_module(kit.MODULE+'.ui.attribute_editor')
    entries = history.records(ob)
    key = 'H:'+entries[0].history_id
    assert any(tab[0] == key for tab in ae.tabs(ob))
    ae.set_tab(bpy.context, key)
    hist = bpy.context.window_manager.allset_history
    assert float(hist.thickness_text) == .5
    hist.thickness_text = '.75'
    assert history.read(ob)['nodes'][0]['params']['thickness'] == .75
    assert history.read(ob)['nodes'][1]['params']['thickness'] == .25
    ae.set_tab(bpy.context, 'H')
    assert float(hist.thickness_text) == .25
