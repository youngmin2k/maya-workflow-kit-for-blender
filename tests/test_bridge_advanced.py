"""Bridge curves, ramps and dependencies survive normal editing and native persistence."""
from importlib import import_module
import math
import os
from pathlib import Path

import bmesh
import bpy
import kit
from test_bridge_paths import bridge_object, caps, fingerprint, params

curve = import_module(kit.MODULE+'.operators.bridge_curve')
poly = import_module(kit.MODULE+'.operators.poly_attribute_nodes')
ex = import_module(kit.MODULE+'.operators.extrude')
history = import_module(kit.MODULE+'.operators.model_history')
nodes = import_module(kit.MODULE+'.ui.node_attributes')


def test_ramp_interpolation_and_invalid_inputs():
    repeat = import_module(kit.MODULE+'.operators.repeat_maya')
    assert not repeat.repeatable('ALLSET_OT_bridge_ramp')
    assert not repeat.repeatable('ALLSET_OT_bridge_path')
    for mode in range(4):
        points = curve.ramp_points('[[0,0,%d],[1,2,1]]' % mode)
        assert curve.ramp_value(points, 0) == 0
        assert curve.ramp_value(points, 1) == 2
        assert math.isclose(curve.ramp_value(points, .5), 0 if mode == 0 else 1)
    assert curve.ramp_value(curve.ramp_points('[[0.5,1,3]]'), .2) == 1
    for text in ('[]', '[[2,1,1]]', '[[0,-1,1]]', '[[0,1,8]]', '[[0,NaN,1]]'):
        try:
            curve.ramp_points(text)
        except ValueError:
            pass
        else:
            raise AssertionError(text)


def test_quintic_centerline_matches_maya_2025_reference():
    bm = caps()
    tracked = poly.bridge(bm, params(curve_type=1, divisions=3), 1)
    profiles = tracked.preview_data['profiles']
    for (t, row), expected in zip(profiles['rows'], (1.5732421875, 2, 2.4267578125)):
        centre = sum((bm.verts[index].co.z for index, _a, _b in row))/len(row)
        assert abs(centre-expected) < 1e-6
    bm.free()


def test_direction_and_smoothing_previews_match_full_rebuild():
    ob, record = bridge_object()
    node = nodes.target(bpy.context)
    values = dict(node.params, direction=1, source_direction=1, smoothing_angle=0)
    node.commit(bpy.context, values)
    node.finish()
    fast = fingerprint(bmesh.from_edit_mesh(ob.data))
    ex.run(ob, record, values, 1)
    assert fingerprint(bmesh.from_edit_mesh(ob.data)) == fast
    assert any(not edge.smooth for edge in bmesh.from_edit_mesh(ob.data).edges)


def test_explicit_curve_creation_edit_rename_save_load_and_delete_history():
    ob, record = bridge_object()
    node = nodes.target(bpy.context)
    node.commit(bpy.context, dict(node.params, curve_type=2))
    node.finish()
    path = curve.curve_object(ob, record.params)
    assert path.parent == ob and path.type == 'CURVE'
    before = fingerprint(bmesh.from_edit_mesh(ob.data))
    path.data.splines[0].points[2].co.x += 1
    path.data.update_tag()
    curve._dirty.add(path.data.session_uid)
    curve.refresh()
    assert fingerprint(bmesh.from_edit_mesh(ob.data)) != before
    assert ex.current(ob) is record
    path.name = 'Renamed Bridge Path'
    assert curve.curve_object(ob, record.params) is path
    bpy.ops.object.mode_set(mode='OBJECT')
    name = ob.name
    before = ex.mesh_coords_hash(ob.data)
    target = Path(os.environ['BLENDER_USER_CONFIG']).parent/'bridge_curve.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(target))
    bpy.ops.wm.open_mainfile(filepath=str(target))
    ob = bpy.data.objects[name]
    assert ex.mesh_coords_hash(ob.data) == before
    record = ex.object_record(ob)
    assert record is not None
    assert curve.curve_object(ob, record.params).name == 'Renamed Bridge Path'
    delete = import_module(kit.MODULE+'.operators.history')
    delete.delete_history(bpy.context, [ob])
    path = bpy.data.objects['Renamed Bridge Path']
    path.data.splines[0].points[2].co.x += 1
    curve._dirty.add(path.data.session_uid)
    curve.refresh()
    assert ex.mesh_coords_hash(ob.data) == before


def test_direct_bridge_edit_can_create_a_curve_and_ramp():
    ob, record = bridge_object()
    values = dict(record.params, curve_type=2, taper_curve='[[0,1,2],[0.5,0.4,2],[1,1,2]]')
    assert bpy.ops.allset.bridge_edit(**values) == {'FINISHED'}
    assert curve.curve_object(ob, record.params) is not None
    assert record.params['taper_curve'] == values['taper_curve']
    assert ex.current(ob) is record


def test_long_unicode_curve_names_have_bounded_persistent_reference_keys():
    assert len(curve.reference_key('Đường dẫn dài '*20)) < 64


def test_invalid_curve_rolls_back_without_leaving_generated_objects():
    ob, record = bridge_object()
    before = fingerprint(bmesh.from_edit_mesh(ob.data))
    objects = set(bpy.data.objects)
    node = nodes.target(bpy.context)
    try:
        node.commit(bpy.context, dict(node.params, curve_type=2, taper_curve='[]'))
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid ramp must fail')
    assert fingerprint(bmesh.from_edit_mesh(ob.data)) == before
    assert set(bpy.data.objects) == objects
    assert ex.current(ob) is record


def test_legacy_bridge_evaluation_is_preserved_until_explicit_upgrade():
    ob, record = bridge_object()
    node = nodes.target(bpy.context)
    node.commit(bpy.context, dict(node.params, evaluation_version=0, twist_angle=45))
    node.finish()
    before = fingerprint(bmesh.from_edit_mesh(ob.data))
    assert history.read(ob)['nodes'][-1]['params']['evaluation_version'] == 0
    assert bpy.ops.allset.bridge_upgrade() == {'FINISHED'}
    assert record.params['evaluation_version'] == 1
    assert fingerprint(bmesh.from_edit_mesh(ob.data)) != before
