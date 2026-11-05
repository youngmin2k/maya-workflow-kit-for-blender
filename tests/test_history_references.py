"""Persistent component bindings, legacy migration, transactional rebind and cache eviction."""
from importlib import import_module
import json
from types import SimpleNamespace

import bpy
import bmesh
import kit
from test_model_history import chain, digest

history = import_module(kit.MODULE+'.operators.model_history')
refs = import_module(kit.MODULE+'.operators.history_references')
ex = import_module(kit.MODULE+'.operators.extrude')


def side_chain():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.scene.tool_settings.mesh_select_mode = (False,False,True)
    bm = bmesh.from_edit_mesh(ob.data)
    ex.deselect_all(bm)
    max(bm.faces, key=lambda face:face.normal.z).select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.allset.extrude(thickness=.5, divisions=3)
    bm = bmesh.from_edit_mesh(ob.data)
    ex.deselect_all(bm)
    sides = [face for face in bm.faces if face.normal.x > .9 and face.calc_center_median().z > 1]
    min(sides, key=lambda face:face.calc_center_median().z).select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.allset.extrude(thickness=.1)
    return ob


def fail_side_edit(ob):
    data = history.read(ob)
    first = data['nodes'][0]
    try:
        history.edit(ob, first['id'], dict(first['params'], divisions=2))
    except refs.BindingError:
        pass
    else:
        raise AssertionError('The removed third-interval side must need an explicit replacement')


def test_missing_component_keeps_original_mesh_and_records_pending_proposal():
    ob = side_chain()
    before, text = digest(ob), ob.data[history.KEY]
    fail_side_edit(ob)
    assert digest(ob) == before and ob.data[history.KEY] == text
    info = history.pending(ob)
    assert info is not None and info['node_id'] == history.read(ob)['nodes'][1]['id']
    assert info['data']['nodes'][0]['params']['divisions'] == 2


def test_manual_rebind_replays_and_commits_the_complete_proposal():
    ob = side_chain()
    before = digest(ob)
    fail_side_edit(ob)
    bm, node = history.binding_input(ob)
    try:
        faces = [face for face in bm.faces if face.normal.x > .9 and face.calc_center_median().z > 1]
        min(faces, key=lambda face:face.calc_center_median().z).select_set(True)
        bm.select_flush_mode()
        selection = history._selection(bm)
    finally:
        bm.free()
    assert digest(ob) == before
    history.rebind(ob, selection)
    assert history.pending(ob) is None
    assert history.read(ob)['nodes'][0]['params']['divisions'] == 2
    assert digest(ob) != before and ex.current(ob) is not None


def test_schema_one_without_identity_attributes_migrates_on_the_next_edit():
    ob = chain()
    bpy.ops.object.mode_set(mode='OBJECT')
    data = json.loads(ob.data[history.KEY])
    data['version'] = 1
    for node in data['nodes']:
        node['selection'].pop('references', None)
    for mesh in (ob.data, ob.data[history.BASE]):
        for name in (refs.HIGH, refs.LOW):
            layer = mesh.attributes.get(name)
            if layer is not None:
                mesh.attributes.remove(layer)
    ob.data[history.KEY] = json.dumps(data)
    ex.clear()
    before = digest(ob)
    assert ex.object_record(ob) is not None and digest(ob) == before
    first = history.read(ob)['nodes'][0]
    history.edit(ob, first['id'], dict(first['params'], divisions=4))
    saved = json.loads(ob.data[history.KEY])
    assert saved['version'] == 2
    assert all('references' in node['selection'] for node in saved['nodes'])
    assert ex.object_record(ob) is not None


def test_inactive_bmesh_cache_is_evicted_and_recovers_from_persistent_recipe():
    budget = history.CACHE_BUDGET
    try:
        history.CACHE_BUDGET = 1
        first = chain()
        first_record = ex.current(first)
        bpy.ops.object.mode_set(mode='OBJECT')
        second = chain()
        assert first_record.pre is None and first.name not in ex.RECORDS
        assert len(history.read(first)['nodes']) == 2
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        first.select_set(True)
        bpy.context.view_layer.objects.active = first
        assert ex.object_record(first) is not None
        assert second.name not in ex.RECORDS
    finally:
        history.CACHE_BUDGET = budget


def test_rebind_ui_and_actions_preserve_repeat_command_and_delete_history_releases_ids():
    repeat = import_module(kit.MODULE+'.operators.repeat_maya')
    assert not repeat.repeatable('ALLSET_OT_history_rebind')
    assert not repeat.repeatable('ALLSET_OT_history_rebind_apply')
    ob = chain()
    bpy.ops.object.mode_set(mode='OBJECT')
    assert ob.data.attributes.get(refs.HIGH) is not None
    delete = import_module(kit.MODULE+'.operators.history')
    delete.delete_history(bpy.context, [ob])
    assert ob.data.attributes.get(refs.HIGH) is None and ob.data.attributes.get(refs.LOW) is None


def test_large_partial_selections_are_compact_and_recover_identical_bindings():
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=100, y_segments=100, size=2)
    bm.select_mode = {'VERT'}
    for index, vertex in enumerate(bm.verts):
        vertex.select = index%2 == 0
    selection = history._selection(bm)
    packed = refs.pack(selection)
    assert packed['encoding'] == 'zlib-json'
    assert len(json.dumps(packed)) < len(json.dumps(selection))*.5
    assert refs.unpack(packed) == json.loads(json.dumps(selection))
    history._select(bm, packed, 'largeSelection')
    assert sum(vertex.select for vertex in bm.verts) == len(selection['vertices'])
    bm.free()


def test_persisted_parameters_take_precedence_when_different_values_produce_the_same_mesh():
    ob = chain()
    record = ex.current(ob)
    original = ob.data[history.KEY]
    values = dict(record.params, thickness=0, local_translate_z=.25)
    node = import_module(kit.MODULE+'.ui.node_attributes').target(bpy.context)
    node.commit(bpy.context, values)
    node.finish()
    ob.data[history.KEY] = original
    restored = ex.current(ob)
    assert restored is not None and restored.params['thickness'] == .25
    assert restored.params['local_translate_z'] == 0


def test_primitive_topology_changes_require_explicit_bindings_and_keep_the_original_until_complete():
    ob = chain(primitive=True)
    before, text = digest(ob), ob.data[history.KEY]
    creation = history.read(ob)['creation']
    try:
        history.edit(ob, creation['id'], dict(creation['attrs'], subdivisionsWidth=2))
    except refs.BindingError:
        pass
    else:
        raise AssertionError('A split primitive face must request a replacement selection')
    assert digest(ob) == before and ob.data[history.KEY] == text
    attempts = 0
    while history.pending(ob) is not None:
        bm, _node = history.binding_input(ob)
        try:
            faces = [face for face in bm.faces if face.normal.z > .9]
            top = max(face.calc_center_median().z for face in faces)
            for face in faces:
                face.select_set(abs(face.calc_center_median().z-top) < 1e-5)
            bm.select_flush_mode()
            selection = history._selection(bm)
        finally:
            bm.free()
        try:
            history.rebind(ob, selection)
        except refs.BindingError:
            assert digest(ob) == before
        attempts += 1
        assert attempts <= 2
    assert attempts == 2 and digest(ob) != before
    assert history.read(ob)['creation']['attrs']['subdivisionsWidth'] == 2
    assert ex.current(ob) is not None


def test_invalid_external_history_is_not_rehashed_on_every_geometry_update():
    ob = chain()
    bpy.ops.object.mode_set(mode='OBJECT')
    original = ob.data.vertices[0].co.copy()
    ob.data.vertices[0].co.x += .2
    history.invalidate()
    assert ex.object_record(ob) is None
    uid = ob.data.session_uid
    assert history._valid[uid] is False
    update = SimpleNamespace(id=SimpleNamespace(original=ob.data), is_updated_geometry=True)
    history.changed(None, SimpleNamespace(updates=[update]))
    assert history._valid[uid] is False
    ob.data.vertices[0].co = original
    ex._on_undo()
    assert ex.object_record(ob) is not None


def test_identity_layers_and_replay_preserve_uv_material_and_vertex_color():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.object
    material = bpy.data.materials.new('History custom data')
    ob.data.materials.append(material)
    material_index = len(ob.data.materials)-1
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.verify()
    color = bm.verts.layers.float_color.new('History Color')
    for vertex in bm.verts:
        vertex[color] = (.1, .2, .3, 1)
    for face in bm.faces:
        face.material_index = material_index
        for loop in face.loops:
            loop[uv].uv = (.25, .75)
    bpy.context.scene.tool_settings.mesh_select_mode = (False,False,True)
    ex.deselect_all(bm)
    max(bm.faces, key=lambda face:face.normal.z).select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.allset.extrude(thickness=.5)
    bpy.ops.allset.extrude(thickness=.25)
    first = history.read(ob)['nodes'][0]
    history.edit(ob, first['id'], dict(first['params'], divisions=4))
    bm = bmesh.from_edit_mesh(ob.data)
    uv, color = bm.loops.layers.uv.active, bm.verts.layers.float_color['History Color']
    bottom = min(bm.faces, key=lambda face:face.calc_center_median().z)
    assert all((loop[uv].uv.x-.25)**2+(loop[uv].uv.y-.75)**2 < 1e-10 for loop in bottom.loops)
    assert all(abs(vertex[color][1]-.2) < 1e-6 for vertex in bottom.verts)
    assert ob.data.materials[material_index] is material
    assert bottom.material_index == material_index
