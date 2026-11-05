"""Numeric drags preserve continuity, typed bounds and the existing modeling history backend."""
from importlib import import_module
import math

import bpy
import bmesh
import kit

edit = import_module(kit.MODULE + '.ui.attribute_edit')
nodes = import_module(kit.MODULE + '.ui.node_attributes')
cb = import_module(kit.MODULE + '.ui.channel_box')


def test_drag_sensitivity_rebases_without_jumping():
    drag = edit.Drag(0.0, edit.Field(step=0.01))
    assert math.isclose(drag.move(20), 0.2)
    assert math.isclose(drag.move(0, ctrl=True), 0.2)
    assert math.isclose(drag.move(10, ctrl=True), 0.21)
    assert math.isclose(drag.move(0, shift=True), 0.21)
    assert math.isclose(drag.move(1, shift=True), 0.31)


def test_integer_accumulation_and_limits_reverse_immediately():
    drag = edit.Drag(1, edit.Field('INT', 0.05, 1, 12, 1))
    for _ in range(9):
        assert drag.move(1) == 1
    assert drag.move(2) == 2
    assert drag.move(1000) == 12
    assert drag.move(-20) == 11
    assert drag.move(-1000) == 1
    assert drag.move(20) == 2


def test_hyperbolic_mode_rebases_and_values_are_finite():
    drag = edit.Drag(0, edit.Field(step=0.01))
    assert math.isclose(drag.move(10), 0.1)
    assert math.isclose(drag.move(0, hyperbolic=True), 0.1)
    assert math.isclose(drag.move(50, hyperbolic=True), 0.6)
    for value in (float('inf'), float('-inf'), float('nan')):
        try:
            edit.Field().limit(value)
        except ValueError:
            continue
        raise AssertionError(value)


def cube():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.mesh.primitive_cube_add()
    return bpy.context.object


def test_bevel_model_channel_preview_uses_current_record():
    ob = cube()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.scene.tool_settings.mesh_select_mode = (False, True, False)
    bpy.ops.mesh.select_all(action='SELECT')
    assert bpy.ops.allset.bevel() == {'FINISHED'}
    node = nodes.target(bpy.context)
    key = cb.model_key(node.record, 'segments')
    assert cb.has_channel(ob, key)
    assert cb.entry_kind(ob, key) == 'INT'
    assert cb.channel_label(key) == 'Segments'
    before = len(bmesh.from_edit_mesh(ob.data).verts)
    cb.set_value(ob, key, 3)
    assert cb.get_value(ob, key) == 3
    assert len(bmesh.from_edit_mesh(ob.data).verts) > before
    cb.set_locked(ob, key, True)
    assert cb.is_locked(ob, key)
    cb.set_locked(ob, key, False)
    node.finish()
    bpy.ops.object.mode_set(mode='OBJECT')
    assert nodes.target(bpy.context).params['segments'] == 3


def test_primitive_uses_creation_history_with_its_own_bounds():
    cube()
    prim = import_module(kit.MODULE + '.operators.prim_history')
    ob = prim.create_object(bpy.context, 'CYLINDER')
    bpy.context.view_layer.objects.active = ob
    node = nodes.target(bpy.context)
    assert isinstance(node, nodes.PrimitiveNode)
    assert node.descriptor('subdivisionsCaps').minimum == 0
    start = dict(node.params)
    node.preview(bpy.context, dict(start, radius=2.0, subdivisionsCaps=0))
    assert node.params['radius'] == 2.0 and node.params['subdivisionsCaps'] == 0
    node.preview(bpy.context, start)
    assert node.params == start


def test_attribute_ui_edits_do_not_replace_repeat_command():
    repeat = import_module(kit.MODULE+'.operators.repeat_maya')
    for name in ('ALLSET_OT_node_attribute_apply', 'ALLSET_OT_inview_setting',
                 'ALLSET_OT_attribute_field_drag', 'ALLSET_OT_cb_virtual_slider'):
        assert not repeat.repeatable(name)
    assert repeat.repeatable('ALLSET_OT_bevel')
    assert repeat.repeatable('ALLSET_OT_bridge')


def test_native_fields_honor_driver_and_transform_lock():
    fields = import_module(kit.MODULE+'.ui.attribute_fields')
    ob = cube()
    field = fields.NumericField(ob, 'location', 0)
    assert field.writable()
    ob.lock_location[0] = True
    assert not field.writable()
    ob.lock_location[0] = False
    field.write(2)
    assert ob.location.x == 2
    ob.driver_add('location', 0)
    assert not field.writable()


def test_native_custom_field_preserves_limits_and_dotted_name():
    fields = import_module(kit.MODULE+'.ui.attribute_fields')
    ob = cube()
    ob['my.weight'] = 0.5
    ob.id_properties_ui('my.weight').update(min=0, max=1)
    field = fields.NumericField(ob, '["my.weight"]', -1)
    assert field.read() == 0.5 and field.writable()
    descriptor = field.descriptor(bpy.context)
    assert descriptor.limit(100) == 1
    field.write(0.75)
    assert ob['my.weight'] == 0.75
    ob.driver_add('["my.weight"]')
    assert not field.writable()


def test_forced_modal_cancellation_restores_preview_and_releases_ownership_once():
    from types import SimpleNamespace
    editor = import_module(kit.MODULE+'.ui.in_view_editor')
    ob = cube()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.scene.tool_settings.mesh_select_mode = (False, True, False)
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.allset.bevel()
    node = nodes.target(bpy.context)
    start = dict(node.params)
    node.preview(bpy.context, dict(start, segments=3))
    operator = SimpleNamespace(_finished=False, _node=node, _role='ROW', _moved=True,
                               _start=start, _view=(bpy.context.window.as_pointer(), 0),
                               _timer=bpy.context.window_manager.event_timer_add(.1, window=bpy.context.window))
    assert edit.claim(bpy.context, operator)
    assert editor.finish_drag(operator, bpy.context, cancel=True) == {'CANCELLED'}
    assert node.params == start and not node.record.live and not edit.busy(bpy.context)
    assert editor.finish_drag(operator, bpy.context, cancel=True) == {'CANCELLED'}


def test_optional_attributes_scroll_into_a_bounded_editor():
    import json
    editor = import_module(kit.MODULE+'.ui.in_view_editor')
    preferences = import_module(kit.MODULE+'.preferences')
    ob = cube()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.scene.tool_settings.mesh_select_mode = (False, False, True)
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.allset.extrude()
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    region = next(region for region in area.regions if region.type == 'WINDOW')
    prefs = preferences.get()
    previous = prefs.inview_layouts
    try:
        prefs.inview_layouts = json.dumps({'polyExtrudeFace': {'height': 48}})
        with bpy.context.temp_override(area=area, region=region):
            target = nodes.target(bpy.context)
            assert 'local_scale_x' not in editor.fields(bpy.context, target)
            bpy.ops.allset.inview_select(field='local_scale_x')
            target, layout = editor.current_layout(bpy.context)
            assert len(layout['rows']) <= 2
            assert 'local_scale_x' in [row[0] for row in layout['rows']]
            assert layout['box'][0] >= 0 and layout['box'][1] >= 0
    finally:
        prefs.inview_layouts = previous
        editor.persist_layouts(bpy.context)
