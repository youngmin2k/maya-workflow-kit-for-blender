"""Regressions for units, numeric proxies, grouped entry and damaged editor layouts."""
from importlib import import_module
from types import SimpleNamespace
import json
import math

import bpy
import kit

editor = import_module(kit.MODULE+'.ui.in_view_editor')
nodes = import_module(kit.MODULE+'.ui.node_attributes')
fields = import_module(kit.MODULE+'.ui.attribute_fields')
primitives = import_module(kit.MODULE+'.operators.prim_history')
cb = import_module(kit.MODULE+'.ui.channel_box')


def object_mode():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')


def test_primitive_numeric_entry_converts_stored_and_display_units():
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(area=area, region=region):
        object_mode()
        scene = bpy.context.scene
        scene.unit_settings.system = 'METRIC'
        scene.unit_settings.length_unit = 'CENTIMETERS'
        scene.unit_settings.scale_length = 1
        ob = primitives.create_object(bpy.context, 'CUBE')
        editor.show(bpy.context)
        node = nodes.target(bpy.context)
        op = SimpleNamespace(_identity=node.identity, _field='width', text='5', report=lambda *args: None)
        assert editor.ALLSET_OT_inview_number.execute(op, bpy.context) == {'FINISHED'}
        assert math.isclose(node.params['width'], 5)
        op.text = '+=2'
        editor.ALLSET_OT_inview_number.execute(op, bpy.context)
        assert math.isclose(node.params['width'], 7)
        scene.unit_settings.length_unit = 'METERS'
        op.text = '0.1'
        editor.ALLSET_OT_inview_number.execute(op, bpy.context)
        assert math.isclose(node.params['width'], 10)
        op.text = '*=2'
        editor.ALLSET_OT_inview_number.execute(op, bpy.context)
        assert math.isclose(node.params['width'], 20)
        field = fields.NodeField(bpy.context, 'width')
        assert math.isclose(field.read(), .2)
        assert math.isclose(field.descriptor(bpy.context).step, .0001)
        scene.unit_settings.system = 'NONE'


def test_euler_descriptor_and_primitive_angles_use_degrees():
    object_mode()
    bpy.ops.mesh.primitive_cube_add()
    field = fields.NumericField(bpy.context.object, 'rotation_euler', 0)
    assert field.kind == 'ROTATION'
    assert field.descriptor(bpy.context).step == .5
    ob = primitives.create_object(bpy.context, 'TORUS')
    node = nodes.target(bpy.context)
    assert math.isclose(node.to_entry('twist', 90), math.pi/2)
    assert math.isclose(node.from_entry('twist', math.pi), 180)
    descriptor = nodes.display_descriptor(node, 'twist', bpy.context)
    assert math.isclose(descriptor.step, .01)


def test_ae_transform_proxies_resolve_to_native_numeric_fields():
    object_mode()
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.object
    context = SimpleNamespace(property=(bpy.context.scene, 'allset_cb.tx_text', -1), area=None,
                              active_object=ob, mode='OBJECT')
    field = fields.under_pointer(context)
    assert field.owner == ob and field.name == 'location' and field.index == 0
    field.write(2)
    assert ob.location.x == 2
    ob.lock_location[0] = True
    assert fields.under_pointer(context) is None
    ob.lock_location[0] = False
    context.property = (bpy.context.scene, 'allset_cb.rx_text', -1)
    assert fields.under_pointer(context).kind == 'ROTATION'


def test_grouped_model_entry_preserves_relative_values_and_locks():
    object_mode()
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.scene.tool_settings.mesh_select_mode = (False, False, True)
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.allset.extrude()
    node = nodes.target(bpy.context)
    keys = [cb.model_key(node.record, f) for f in ('thickness', 'offset')]
    cb.set_selected_channels(keys)
    assert cb.apply_entry(keys[0], '.2') == 2
    assert node.params['thickness'] == .2 and node.params['offset'] == .2
    assert not node.record.live
    cb.set_locked(ob, keys[1], True)
    assert cb.apply_entry(keys[0], '+=.1') == 1
    assert math.isclose(node.params['thickness'], .3) and node.params['offset'] == .2
    assert cb.apply_entry(keys[0], '/=0') == 0
    assert math.isclose(node.params['thickness'], .3)
    cb.set_locked(ob, keys[1], False)
    cb.set_selected_channels([])
    bpy.ops.object.mode_set(mode='OBJECT')


def test_layout_validation_rejects_nested_damage_and_accepts_partial_layouts():
    invalid = [[], {'height': 'broken'}, {'width': 0}, {'width': True},
               {'height': float('nan')}, {'position': [1]}, {'position': [1, float('inf')]},
               {'hidden': 'width'}, {'order': [1]}, {'width': 10**400}]
    for value in invalid:
        text = json.dumps({'polyBevel3': value})
        try:
            editor.validate_layouts(text)
        except ValueError:
            pass
        else:
            raise AssertionError(text)
        assert editor._layouts(text) == {}
    valid = {'polyBevel3': {'height': 48, 'width': 180, 'position': None}, 'polyCube': {}}
    assert editor.validate_layouts(json.dumps(valid)) == valid
    mixed = dict(valid, damaged={'order': None})
    assert editor._layouts(json.dumps(mixed)) == valid


def test_invalid_import_is_skipped_and_cached_layouts_are_not_mutated():
    prefs = import_module(kit.MODULE+'.preferences').get()
    io = import_module(kit.MODULE+'.settings_io')
    original = prefs.inview_layouts
    try:
        prefs.inview_layouts = json.dumps({'polyCube': {'hidden': ['width']}})
        done, skipped = io.import_preferences(prefs, {'inview_layouts': '{"polyBevel3":{"height":"broken"}}'})
        assert 'inview_layouts' in skipped and 'inview_layouts' not in done
        node = SimpleNamespace(spec=SimpleNamespace(node_type='polyCube'))
        saved = editor.settings(bpy.context, node)
        saved['hidden'].append('height')
        assert editor.settings(bpy.context, node)['hidden'] == ['width']
    finally:
        prefs.inview_layouts = original
        editor.persist_layouts(bpy.context)


def test_typed_model_edits_do_not_replace_repeat_command():
    assert not import_module(kit.MODULE+'.operators.repeat_maya').repeatable('ALLSET_OT_model_channel_entry')


def test_persisted_layout_load_keeps_valid_nodes_and_discards_damaged_nodes():
    prefs = import_module(kit.MODULE+'.preferences').get()
    original = prefs.inview_layouts
    path = editor.layout_file(create=True)
    previous_file = path.read_text(encoding='utf-8') if path.is_file() else None
    try:
        path.write_text('{"polyCube":{"width":200},"polyBevel3":{"height":"broken"}}', encoding='utf-8')
        editor.load_layouts()
        assert json.loads(prefs.inview_layouts) == {'polyCube': {'width': 200}}
    finally:
        prefs.inview_layouts = original
        if previous_file is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(previous_file, encoding='utf-8')
