"""Bridge lofts keep boundaries, native custom data and the last valid preview intact."""
from importlib import import_module
import math

import bpy
import bmesh
from mathutils import Matrix, Vector
import kit

poly = import_module(kit.MODULE+'.operators.poly_attribute_nodes')
ex = import_module(kit.MODULE+'.operators.extrude')
nodes = import_module(kit.MODULE+'.ui.node_attributes')


def caps():
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2)
    bmesh.ops.create_cube(bm, size=2, matrix=Matrix.Translation((0, 0, 4)))
    bm.normal_update()
    for face in bm.faces:
        face.select_set(abs(face.normal.z) > .9 and 0 < face.calc_center_median().z < 4)
    return bm


def params(**changes):
    return dict(poly.BRIDGE.defaults, use_faces=True, **changes)


def fingerprint(bm):
    return sorted(tuple(sorted(tuple(round(c, 5) for c in vertex.co) for vertex in face.verts)) for face in bm.faces)


def test_smooth_bridge_preserves_boundaries_and_builds_quad_rows():
    for divisions in (1, 3, 6):
        bm = caps()
        original = [vertex.co.copy() for vertex in bm.verts]
        tracked = poly.bridge(bm, params(curve_type=1, divisions=divisions), 1)
        assert tracked
        assert len(bm.faces) == 10+4*(divisions+1)
        assert len(bm.verts) == 16+4*divisions
        assert all(len(face.verts) == 4 for face in bm.faces)
        assert all((bm.verts[index].co-point).length < 1e-6 for index, point in enumerate(original))
        assert all(math.isfinite(c) for vertex in bm.verts for c in vertex.co)
        assert not any(name.startswith('.allset_bridge_') for name in bm.verts.layers.int.keys())
        assert not any(name.startswith('.allset_bridge_') for name in bm.verts.layers.float.keys())
        bm.free()


def test_taper_and_degree_twist_shape_the_middle_without_moving_endpoints():
    for taper, twist in ((.5, 0), (1.5, 0), (1, 90)):
        bm = caps()
        old_count = len(bm.verts)
        poly.bridge(bm, params(curve_type=1, divisions=3, taper=taper, twist_angle=twist), 1)
        middle = [vertex for index, vertex in enumerate(bm.verts) if index >= old_count and abs(vertex.co.z-2)<1e-5]
        assert len(middle) == 4
        assert all(abs(math.hypot(vertex.co.x, vertex.co.y)-math.sqrt(2)*taper)<1e-5 for vertex in middle)
        if twist:
            assert all(abs(abs(vertex.co.x)-1)<1e-5 and abs(abs(vertex.co.y)-1)<1e-5 for vertex in middle)
        bm.free()


def test_twist_is_continuous_and_linear_ignores_smooth_only_parameters():
    first = caps()
    second = caps()
    poly.bridge(first, params(curve_type=1, divisions=3, twist_angle=0), 1)
    poly.bridge(second, params(curve_type=1, divisions=3, twist_angle=10), 1)
    assert fingerprint(first) != fingerprint(second)
    first.free()
    second.free()
    first = caps()
    second = caps()
    poly.bridge(first, params(divisions=3), 1)
    poly.bridge(second, params(divisions=3, taper=.5, twist_angle=45), 1)
    assert fingerprint(first) == fingerprint(second)
    first.free()
    second.free()


def test_legacy_integer_twist_keeps_its_bridge_offset_meaning():
    first = caps()
    second = caps()
    poly.bridge(first, {'divisions': 3, 'twist': 1, 'use_faces': True}, 1)
    poly.bridge(second, params(divisions=3, bridge_offset=1), 1)
    assert fingerprint(first) == fingerprint(second)
    first.free()
    second.free()


def test_open_borders_are_connected_with_the_same_number_of_quad_rows():
    bm = bmesh.new()
    for z in (0, 3):
        row = [bm.verts.new((i, 0, z)) for i in range(4)]
        outside = [bm.verts.new((i, -1, z)) for i in range(4)]
        for index in range(3):
            bm.faces.new((row[index], row[index+1], outside[index+1], outside[index]))
        for index in range(3):
            bm.edges.get((row[index], row[index+1])).select_set(True)
    tracked = poly.bridge(bm, {'divisions': 3, 'curve_type': 1, 'taper': .7}, 1)
    assert tracked and len(bm.faces) == 18
    assert all(len(face.verts) == 4 for face in bm.faces)
    bm.free()


def test_invalid_border_selection_leaves_mesh_unchanged():
    bm = caps()
    for face in bm.faces:
        face.select_set(True)
    before = fingerprint(bm)
    assert not poly.bridge(bm, params(), 1)
    assert fingerprint(bm) == before
    bm.free()


def bridge_object():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    bm = caps()
    mesh = bpy.data.meshes.new('bridge_paths')
    bm.to_mesh(mesh)
    bm.free()
    ob = bpy.data.objects.new('bridge_paths', mesh)
    bpy.context.scene.collection.objects.link(ob)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.scene.tool_settings.mesh_select_mode = (False, False, True)
    assert bpy.ops.allset.bridge(divisions=3, curve_type=1) == {'FINISHED'}
    return ob, ex.active(bpy.context)[1]


def test_history_changes_rebuild_from_original_input_and_enum_is_not_a_slider():
    ob, record = bridge_object()
    original = fingerprint(bmesh.from_edit_mesh(ob.data))
    assert ex.set_params(bpy.context, taper=.5, twist_angle=15) == {'FINISHED'}
    assert fingerprint(bmesh.from_edit_mesh(ob.data)) != original
    assert ex.set_params(bpy.context, taper=1, twist_angle=0) == {'FINISHED'}
    assert fingerprint(bmesh.from_edit_mesh(ob.data)) == original
    cb = import_module(kit.MODULE+'.ui.channel_box')
    cb.set_selected_channels([cb.model_key(record, 'curve_type')])
    assert cb.slider_targets(bpy.context) == []
    node = nodes.target(bpy.context)
    assert nodes.parse_value(node, 'curve_type', 'Linear path', bpy.context.scene) == 0
    assert ex.set_params(bpy.context, curve_type=0) == {'FINISHED'}
    assert not nodes.editable(node, 'taper')
    assert cb.apply_entry(cb.model_key(record, 'taper'), '.5') == 0
    cb.set_selected_channels([])


def test_failed_preview_preserves_the_last_geometry_and_record():
    ob, record = bridge_object()
    before = fingerprint(bmesh.from_edit_mesh(ob.data))
    previous = dict(record.params)
    build = poly.BRIDGE.build
    def fail(bm, values, unit, ob=None):
        bm.verts.new((999, 999, 999))
        raise ValueError('injected bridge preview failure')
    try:
        poly.BRIDGE.build = fail
        try:
            ex.run(ob, record, dict(previous, taper=.5), 1)
        except ValueError:
            pass
        else:
            raise AssertionError('the preview failure must propagate')
    finally:
        poly.BRIDGE.build = build
    assert fingerprint(bmesh.from_edit_mesh(ob.data)) == before
    assert record.params == previous
    assert ex.current(ob) is record


def test_twist_respects_scene_angular_units():
    _ob, _record = bridge_object()
    node = nodes.target(bpy.context)
    scene = bpy.context.scene
    scene.unit_settings.system_rotation = 'DEGREES'
    assert math.isclose(nodes.parse_value(node, 'twist_angle', '45', scene), 45)
    scene.unit_settings.system_rotation = 'RADIANS'
    assert math.isclose(nodes.parse_value(node, 'twist_angle', str(math.pi/2), scene), 90, abs_tol=1e-4)
    scene.unit_settings.system_rotation = 'DEGREES'


def test_coordinate_preview_matches_full_rebuild_and_commits_a_valid_state():
    ob, record = bridge_object()
    node = nodes.target(bpy.context)
    states = len(record.states)
    values = dict(node.params, taper=.8, twist_angle=22.5)
    node.preview(bpy.context, values)
    assert record.fast_preview and record.live
    assert len(record.states) == states
    fast_result = fingerprint(bmesh.from_edit_mesh(ob.data))
    node.commit(bpy.context, values)
    node.finish()
    assert fingerprint(bmesh.from_edit_mesh(ob.data)) == fast_result
    assert not record.fast_preview and not record.live
    assert ex.current(ob) is record
    assert len(record.states) == states+1
    bpy.ops.object.mode_set(mode='OBJECT')
    assert ex.object_record(ob) is record


def test_coordinate_preview_cancel_restores_the_previous_record():
    ob, record = bridge_object()
    node = nodes.target(bpy.context)
    original = dict(node.params)
    before = fingerprint(bmesh.from_edit_mesh(ob.data))
    node.preview(bpy.context, dict(original, taper=.5))
    node.preview(bpy.context, original)
    node.finish()
    assert fingerprint(bmesh.from_edit_mesh(ob.data)) == before
    assert ex.current(ob) is record


def test_typed_commit_uses_a_complete_geometry_state_without_a_prior_drag():
    ob, record = bridge_object()
    node = nodes.target(bpy.context)
    node.commit(bpy.context, dict(node.params, taper=.75))
    node.finish()
    assert ex.current(ob) is record
    assert math.isclose(record.params['taper'], .75)
    bpy.ops.object.mode_set(mode='OBJECT')
    assert ex.object_record(ob) is record


def test_selection_membership_is_checked_even_when_selected_counts_match():
    ob, record = bridge_object()
    assert ex.caps_selected(ob, record)
    bm = bmesh.from_edit_mesh(ob.data)
    chosen = next(face for face in bm.faces if face.select)
    other = next(face for face in bm.faces if not face.select)
    chosen.select_set(False)
    other.select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    assert not ex.caps_selected(ob, record)


def test_legacy_offset_edits_are_absolute_and_repeatable():
    _ob, record = bridge_object()
    assert ex.set_params(bpy.context, twist=1) == {'FINISHED'}
    assert record.params['bridge_offset'] == 1
    assert ex.set_params(bpy.context, twist=1) == {'FINISHED'}
    assert record.params['bridge_offset'] == 1


def test_bridge_options_reach_the_editable_node():
    ob, record = bridge_object()
    bm = bmesh.from_edit_mesh(ob.data)
    ex.restore_pre(bm, record)
    bmesh.update_edit_mesh(ob.data)
    options = import_module(kit.MODULE+'.operators.option_windows')
    values = dict(options._BY_KEY['bridge'].defaults(), curve_type='Smooth path',
                  taper=.7, twist_angle=30, divisions=4)
    assert options.run(options._BY_KEY['bridge'], bpy.context, values) == {'FINISHED'}
    record = ex.active(bpy.context)[1]
    assert record.params['curve_type'] == 1 and record.params['divisions'] == 4
    assert math.isclose(record.params['taper'], .7, abs_tol=1e-5)
    assert record.params['twist_angle'] == 30


def test_bridge_type_menu_preserves_enum_type_and_subsequent_edits():
    _ob, record = bridge_object()
    editor = import_module(kit.MODULE+'.ui.in_view_editor')
    area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
    region = next(region for region in area.regions if region.type == 'WINDOW')
    for curve_type in (0, 1):
        with bpy.context.temp_override(area=area, region=region):
            assert editor.show(bpy.context)
            assert bpy.ops.allset.inview_setting(action='VALUE', field='curve_type',
                                                 value=curve_type) == {'FINISHED'}
        assert type(record.params['curve_type']) is int
        assert bpy.ops.allset.bridge_edit(**record.params) == {'FINISHED'}
        assert ex.set_params(bpy.context, divisions=4) == {'FINISHED'}
        assert record.params['curve_type'] == curve_type
    with bpy.context.temp_override(area=area, region=region):
        previous = dict(record.params)
        assert bpy.ops.allset.inview_setting(action='VALUE', field='curve_type', value=99) == {'CANCELLED'}
        assert record.params == previous


def test_channel_slider_mode_changes_restore_bridge_preview():
    from types import SimpleNamespace
    cb = import_module(kit.MODULE+'.ui.channel_box')
    edit = import_module(kit.MODULE+'.ui.attribute_edit')
    for start_mode in ('EDIT', 'OBJECT'):
        ob, record = bridge_object()
        original = fingerprint(bmesh.from_edit_mesh(ob.data))
        if start_mode == 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        node = nodes.target(bpy.context)
        previous = dict(node.params)
        initial_mode = bpy.context.mode
        node.preview(bpy.context, dict(previous, taper=.5))
        operator = SimpleNamespace(
            _finished=False, _nodes={ob: node}, _node_starts={ob: previous},
            _starts={(ob, cb.model_key(record, 'taper')): previous['taper']},
            _mode=initial_mode, _window=bpy.context.window.as_pointer(), _header=lambda *args: None)
        assert edit.claim(bpy.context, operator)
        bpy.ops.object.mode_set(mode='OBJECT' if start_mode == 'EDIT' else 'EDIT')
        assert cb.ALLSET_OT_cb_virtual_slider._finish(operator, bpy.context, cancel=True) == {'CANCELLED'}
        assert node.params == previous and not record.live and not record.fast_preview
        assert not edit.busy(bpy.context)
        if ob.mode == 'OBJECT':
            assert ex.object_record(ob) is record
            bpy.ops.object.mode_set(mode='EDIT')
        assert ex.current(ob) is record
        assert fingerprint(bmesh.from_edit_mesh(ob.data)) == original
        assert cb.ALLSET_OT_cb_virtual_slider._finish(operator, bpy.context, cancel=True) == {'CANCELLED'}
