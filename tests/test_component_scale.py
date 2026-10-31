"""Single-axis zero scale, native transform compatibility, and the shared UI option."""
from importlib import import_module
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

import kit

scale = import_module(kit.MODULE+'.operators.component_scale')
prefs = import_module(kit.MODULE+'.preferences')
ui = import_module(kit.MODULE+'.ui.manipulator')


def setup(mode='VERT'):
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
    ob = bpy.context.object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type=mode)
    bpy.ops.mesh.select_all(action='SELECT')
    ts = bpy.context.tool_settings
    ts.transform_pivot_point = 'CURSOR'
    ts.use_proportional_edit = False
    ts.use_transform_correct_face_attributes = False
    ts.use_snap = False
    bpy.context.scene.cursor.location = (0, 0, 0)
    bpy.context.scene.transform_orientation_slots[3].type = 'GLOBAL'
    prefs.get(bpy.context).prevent_negative_scale = True
    return ob


def bm():
    return bmesh.from_edit_mesh(bpy.context.edit_object.data)


def coordinates():
    return [v.co.copy() for v in bm().verts]


def close(a, b):
    assert len(a) == len(b)
    assert all((Vector(x)-Vector(y)).length < 2e-5 for x, y in zip(a, b)), (a, b)


def run(axis=0, value=0., **kwargs):
    values = [1., 1., 1.]
    values[axis] = value
    assert bpy.ops.allset.component_scale(value=values, constraint_axis=tuple(i == axis for i in range(3)), **kwargs) == {'FINISHED'}


def test_zero_and_negative_stop_exactly_at_pivot_on_each_axis():
    for axis in range(3):
        for mode in ('VERT', 'EDGE', 'FACE'):
            setup(mode)
            bpy.context.scene.cursor.location = (2, -3, 4)
            run(axis, -2.)
            assert all(abs(v.co[axis]-(2, -3, 4)[axis]) < 1e-5 for v in bm().verts), (axis, mode, coordinates())
            assert (len(bm().verts), len(bm().edges), len(bm().faces)) == (8, 12, 6)


def test_selected_loop_flattens_without_changing_other_vertices():
    setup('EDGE')
    for v in bm().verts:
        v.select_set(v.co.z > 0)
    bm().select_flush_mode()
    before = coordinates()
    indices = [i for i, v in enumerate(bm().verts) if v.select]
    run(0, 0.)
    for i, v in enumerate(bm().verts):
        if i in indices:
            assert abs(v.co.x) < 1e-6, coordinates()
        else:
            assert (v.co-before[i]).length < 1e-6


def test_custom_plane_under_rotated_nonuniform_object_scale():
    ob = setup()
    ob.rotation_euler = (.2, .3, .7)
    ob.scale = (2, .5, 3)
    bpy.context.view_layer.update()
    frame = Matrix.Rotation(.6, 3, 'Z') @ Matrix.Rotation(.3, 3, 'X')
    centre = Vector((1, 2, 3))
    bpy.context.scene.cursor.location = centre
    before = [ob.matrix_world @ v.co for v in bm().verts]
    run(1, 0., orient_matrix=frame)
    after = [ob.matrix_world @ v.co for v in bm().verts]
    assert all(abs((p-centre).dot(frame.col[1])) < 2e-5 for p in after)
    for a, b in zip(before, after):
        assert abs((a-b).dot(frame.col[0])) < 2e-5
        assert abs((a-b).dot(frame.col[2])) < 2e-5


def test_local_orientation_is_not_overridden_by_gizmo_identity_matrix():
    ob = setup()
    ob.rotation_euler = (0, 0, math.pi/4)
    bpy.context.view_layer.update()
    run(0, 0., orient_type='LOCAL', orient_matrix=Matrix.Identity(3))
    assert all(abs(v.co.x) < 1e-5 for v in bm().verts)


def native_match(configure):
    ob = setup()
    configure(ob)
    snapshot = scale.Snapshot(bpy.context)
    ts = bpy.context.tool_settings
    kwargs = dict(value=(.25, 1, 1), constraint_axis=(True, False, False), orient_type='GLOBAL',
                  center_override=(0, 0, 0), use_proportional_edit=ts.use_proportional_edit,
                  proportional_size=ts.proportional_size, proportional_edit_falloff=ts.proportional_edit_falloff,
                  use_proportional_connected=ts.use_proportional_connected,
                  use_proportional_projected=ts.use_proportional_projected, snap=False)
    bpy.ops.transform.resize(**kwargs)
    expected = coordinates()
    uv = bm().loops.layers.uv.active
    expected_uv = [lp[uv].uv.copy() for f in bm().faces for lp in f.loops] if uv else []
    snapshot.restore()
    run(0, .25)
    close(coordinates(), expected)
    if uv:
        close([lp[uv].uv for f in bm().faces for lp in f.loops], expected_uv)


def test_soft_selection_uses_native_weights():
    def configure(ob):
        ts = bpy.context.tool_settings
        ts.use_proportional_edit = True
        ts.proportional_size = 4
        ts.proportional_edit_falloff = 'LINEAR'
        ts.use_proportional_connected = True
        for v in bm().verts:
            v.select_set(v.co.x > 0 and v.co.y > 0)
    native_match(configure)


def test_mesh_symmetry_matches_native_scale():
    def configure(ob):
        ob.data.use_mirror_x = True
        for v in bm().verts:
            v.select_set(v.co.x > 0)
    native_match(configure)


def test_preserve_uvs_and_snapshot_restore_match_native():
    def configure(ob):
        bpy.context.tool_settings.use_transform_correct_face_attributes = True
        for v in bm().verts:
            v.select_set(v.co.z > 0)
    native_match(configure)


def test_zero_with_uv_correction_remains_finite_and_reversible():
    setup()
    bpy.context.tool_settings.use_transform_correct_face_attributes = True
    snapshot = scale.Snapshot(bpy.context)
    layer = bm().loops.layers.uv.active
    before = [lp[layer].uv.copy() for f in bm().faces for lp in f.loops]
    run(0, 0.)
    assert all(math.isfinite(x) for f in bm().faces for lp in f.loops for x in lp[layer].uv)
    snapshot.restore()
    close(before, [lp[layer].uv for f in bm().faces for lp in f.loops])


def test_shape_key_mesh_preserves_basis_and_native_active_shape():
    ob = setup()
    bpy.ops.object.mode_set(mode='OBJECT')
    basis = ob.shape_key_add(name='Basis')
    key = ob.shape_key_add(name='Raised')
    for v in key.data:
        v.co.z += .5
    ob.active_shape_key_index = 1
    before = [v.co.copy() for v in basis.data]
    bpy.ops.object.mode_set(mode='EDIT')
    snapshot = scale.Snapshot(bpy.context)
    original = coordinates()
    run(0, 0.)
    snapshot.restore()
    close(original, coordinates())
    run(0, .5)
    bpy.ops.object.mode_set(mode='OBJECT')
    close(before, [v.co for v in basis.data])
    close([Vector((p.x*.5, p.y, p.z)) for p in original], [v.co for v in key.data])


def test_multi_object_edit_uses_one_world_pivot():
    ob = setup()
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.mesh.primitive_cube_add(location=(4, 2, 0))
    second = bpy.context.object
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.context.scene.cursor.location = (2, 3, 0)
    run(1, 0.)
    for node in (ob, second):
        assert all(abs((node.matrix_world @ v.co).y-3) < 1e-5 for v in bmesh.from_edit_mesh(node.data).verts)


def test_snapshot_recovers_zero_scaled_mesh():
    setup()
    snapshot = scale.Snapshot(bpy.context)
    before = coordinates()
    run(0, 0)
    snapshot.restore()
    close(before, coordinates())
    run(0, .5)
    close([Vector((v.x*.5, v.y, v.z)) for v in before], coordinates())


def test_tool_option_toggle_reset_marking_state_and_object_scope():
    setup()
    assert scale.enabled(bpy.context)
    marking = import_module(kit.MODULE+'.marking.draw')
    action = ('allset.prevent_negative_scale', {})
    assert marking.checked(action) is True
    bpy.ops.allset.prevent_negative_scale()
    assert not scale.enabled(bpy.context) and marking.checked(action) is False
    settings = import_module(kit.MODULE+'.ui.tool_settings')
    settings.reset_maya_options(bpy.context, 'RESIZE')
    assert scale.enabled(bpy.context)
    bpy.ops.object.mode_set(mode='OBJECT')
    assert not scale.enabled(bpy.context) and not bpy.ops.allset.prevent_negative_scale.poll()


def test_object_mode_scaling_stays_native():
    ob = setup()
    axis = bpy.context.scene.transform_orientation_slots[3]
    axis.type = 'GLOBAL'
    assert scale.enabled(bpy.context)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.transform.resize(value=(-1, 1, 1))
    assert ob.scale.x == -1
