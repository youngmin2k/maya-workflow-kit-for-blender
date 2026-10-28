# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya D tap/hold and component picking: pivot edits preserve geometry and selection."""
from importlib import import_module
from types import SimpleNamespace
import time

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

import kit

hold = import_module(kit.MODULE+'.operators.hold')
pivot = import_module(kit.MODULE+'.operators.pivot')
pick = import_module(kit.MODULE+'.operators.pivot_pick')
pre = import_module(kit.MODULE+'.operators.preselect')


def _cube(edit=False):
    hold.unregister_cleanup()
    pivot.stop()
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    ts = bpy.context.tool_settings
    ts.use_transform_data_origin = ts.use_transform_skip_children = False
    ts.transform_pivot_point = 'BOUNDING_BOX_CENTER'
    ts.mesh_select_mode = (False, True, False)
    bpy.context.scene.cursor.matrix = Matrix.Identity(4)
    wm = bpy.context.window_manager
    wm.allset_snap_pivot_pos = wm.allset_snap_pivot_ori = True
    if edit:
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bm = bmesh.from_edit_mesh(ob.data)
        bm.edges.ensure_lookup_table()
        bm.edges[0].select_set(True)
        bm.select_history.add(bm.edges[0])
        bm.select_flush_mode()
        bmesh.update_edit_mesh(ob.data)
    pre.invalidate()
    return ob


def _release(name, elapsed=.01, used=False):
    """Drive the real release/latch methods without installing a headless modal handler."""
    context = bpy.context
    removed = []
    stub_context = SimpleNamespace(scene=context.scene, mode=context.mode, window=context.window,
                                   window_manager=SimpleNamespace(event_timer_remove=removed.append))
    stub = SimpleNamespace(name=name, _key='D', _ts=context.tool_settings, _timer='timer',
                           _pivot_tap=True, _pressed_at=time.monotonic()-elapsed, _used=used)
    stub._finish = lambda ctx: hold.ALLSET_OT_hold._finish(stub, ctx)
    stub._latch = lambda ctx: hold.ALLSET_OT_hold._latch(stub, ctx)
    result = hold.ALLSET_OT_hold.modal(stub, stub_context, SimpleNamespace(type='D', value='RELEASE', is_repeat=False))
    assert result == {'FINISHED'} and removed == ['timer']


def _selection(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    return tuple(tuple(i for i, e in enumerate(elements) if e.select) for elements in (bm.verts, bm.edges, bm.faces))


def _world(ob):
    vertices = bmesh.from_edit_mesh(ob.data).verts if ob.mode == 'EDIT' else ob.data.vertices
    return [ob.matrix_world @ v.co for v in vertices]


def test_short_object_d_latches_and_second_toggle_restores_flags():
    _cube()
    ts = bpy.context.tool_settings
    ts.use_transform_skip_children = True
    hold.begin(ts, 'pivot')
    _release('pivot')
    assert ts.use_transform_data_origin and not hold.active_holds()
    hold.toggle_object_pivot(ts)
    assert not ts.use_transform_data_origin and ts.use_transform_skip_children


def test_long_or_used_d_stays_a_temporary_hold():
    for elapsed, used in ((.5, False), (.01, True)):
        _cube()
        ts = bpy.context.tool_settings
        hold.begin(ts, 'pivot')
        _release('pivot', elapsed, used)
        assert not ts.use_transform_data_origin and not hold.active_holds()


def test_short_component_d_latches_and_restores_multi_selection_mode():
    ob = _cube(edit=True)
    selected = _selection(ob)
    hold.COMPONENT.start(bpy.context)
    assert tuple(bpy.context.tool_settings.mesh_select_mode) == (True, True, True)
    _release('component_pivot')
    assert hold.COMPONENT.on and hold.COMPONENT.toggled
    hold.COMPONENT.finish(bpy.context)
    assert tuple(bpy.context.tool_settings.mesh_select_mode) == (False, True, False)
    assert _selection(ob) == selected


def test_component_frames_under_rotated_nonuniform_scale():
    ob = _cube()
    ob.location = (2, -3, 1)
    ob.rotation_euler = (.2, -.4, .5)
    ob.scale = (2, .7, 1.4)
    bpy.context.view_layer.update()
    cache = pre.MeshCache(ob)
    bm = cache.bm
    for kind, local in (('VERT', bm.verts[0].co),
                        ('EDGE', (bm.edges[0].verts[0].co+bm.edges[0].verts[1].co)/2),
                        ('FACE', bm.faces[0].calc_center_median())):
        point, axes = pick.component_frame(ob, bm, kind, 0)
        assert (point-ob.matrix_world @ local).length < 1e-6
        assert abs(axes.determinant()-1) < 1e-5
        assert all(abs((axes.transposed() @ axes)[i][j]-(1 if i == j else 0)) < 1e-5
                   for i in range(3) for j in range(3))
    point, axes = pick.component_frame(ob, bm, 'EDGE', 0)
    direction = (ob.matrix_world.to_3x3() @ (bm.edges[0].verts[1].co-bm.edges[0].verts[0].co)).normalized()
    assert abs(axes.col[0].dot(direction)) > .99999


def test_object_pick_moves_only_pivot_keeps_channels_geometry_and_children():
    ob = _cube()
    ob.location, ob.rotation_euler, ob.scale = (2, 1, -.5), (.3, .1, -.2), (1.3, .8, 1.1)
    child = bpy.data.objects.new('Child', None)
    bpy.context.collection.objects.link(child)
    child.parent = ob
    child.location = (3, 2, 1)
    bpy.context.view_layer.update()
    before, child_world = _world(ob), child.matrix_world.copy()
    location, rotation, scale = ob.location.copy(), ob.rotation_euler.copy(), ob.scale.copy()
    cache = pre.MeshCache(ob)
    point, axes = pick.component_frame(ob, cache.bm, 'VERT', 0)
    hold.toggle_object_pivot(bpy.context.tool_settings)
    pick.apply_component(bpy.context, point, axes)
    bpy.context.view_layer.update()
    assert (ob.matrix_world.translation-point).length < 1e-5
    assert all((a-b).length < 1e-5 for a, b in zip(before, _world(ob)))
    assert all(abs(a-b) < 1e-5 for ra, rb in zip(child.matrix_world, child_world) for a, b in zip(ra, rb))
    assert (ob.location-location).length < 1e-6 and (ob.scale-scale).length < 1e-6
    assert all(abs(a-b) < 1e-6 for a, b in zip(ob.rotation_euler, rotation))
    assert pivot.PROP in ob
    assert not hold.turned(pick.pivot_axes(bpy.context, ob), axes)
    hold.toggle_object_pivot(bpy.context.tool_settings)


def test_component_pick_preserves_selection_and_world_mesh():
    ob = _cube(edit=True)
    before, selected = _world(ob), _selection(ob)
    hold.COMPONENT.start(bpy.context)
    point = Vector((1, -1, 1))
    axes = Euler((.3, .1, .4)).to_matrix()
    pick.apply_component(bpy.context, point, axes)
    assert (bpy.context.scene.cursor.location-point).length < 1e-6
    hold.COMPONENT.finish(bpy.context)
    assert _selection(ob) == selected
    assert all((a-b).length < 1e-6 for a, b in zip(before, _world(ob)))
    assert bpy.context.tool_settings.transform_pivot_point == 'CURSOR'


def test_click_modifiers_and_snap_options():
    _cube(edit=True)
    hold.COMPONENT.start(bpy.context)
    cursor = bpy.context.scene.cursor
    axes = Euler((.3, -.2, .5)).to_matrix()
    before = cursor.location.copy()
    pick.apply_component(bpy.context, (2, 3, 4), axes, ctrl=True)
    assert (cursor.location-before).length < 1e-6
    assert not hold.turned(cursor.matrix.to_3x3(), axes)
    pick.apply_component(bpy.context, (3, 2, 1), Matrix.Identity(3), shift=True)
    assert (cursor.location-Vector((3, 2, 1))).length < 1e-6
    assert not hold.turned(cursor.matrix.to_3x3(), axes)
    before_matrix = cursor.matrix.copy()
    bpy.context.window_manager.allset_snap_pivot_pos = False
    bpy.context.window_manager.allset_snap_pivot_ori = False
    pick.apply_component(bpy.context, (9, 9, 9), Matrix.Identity(3))
    assert all(abs(a-b) < 1e-6 for ra, rb in zip(cursor.matrix, before_matrix) for a, b in zip(ra, rb))
    bpy.context.window_manager.allset_snap_pivot_pos = True
    bpy.context.window_manager.allset_snap_pivot_ori = True
    hold.COMPONENT.finish(bpy.context)


def test_component_orientation_only_edit_is_preserved():
    _cube(edit=True)
    hold.COMPONENT.start(bpy.context)
    point = bpy.context.scene.cursor.location.copy()
    axes = Euler((.2, .3, .1)).to_matrix()
    pick.apply_component(bpy.context, point, axes, ctrl=True)
    hold.COMPONENT.finish(bpy.context)
    assert bpy.context.tool_settings.transform_pivot_point == 'CURSOR'
    slot = bpy.context.scene.transform_orientation_slots[pivot.MOVE_SLOT]
    assert slot.type == pivot.ORIENT_NAME and not hold.turned(slot.custom_orientation.matrix, axes)


def test_ctrl_shift_aims_the_active_axis_without_moving_the_pivot():
    _cube(edit=True)
    hold.COMPONENT.start(bpy.context)
    manip = import_module(kit.MODULE+'.operators.manip')
    saved = manip.HANDLES.get('TRANSLATE')
    try:
        manip.HANDLES['TRANSLATE'] = {'constraint_axis': (False, True, False)}
        cursor = bpy.context.scene.cursor
        before = cursor.location.copy()
        direction = Vector((2, -3, 4)).normalized()
        pick.apply_component(bpy.context, before+direction, Matrix.Identity(3), shift=True, ctrl=True)
        assert (cursor.location-before).length < 1e-6
        assert cursor.matrix.to_3x3().col[1].dot(direction) > .99999
    finally:
        manip.HANDLES['TRANSLATE'] = saved
        hold.COMPONENT.finish(bpy.context)


def test_component_pivot_orientation_applies_to_rotate_and_reset():
    ob = _cube(edit=True)
    before, selected = _world(ob), _selection(ob)
    hold.COMPONENT.start(bpy.context)
    axes = Euler((.2, -.4, .6)).to_matrix()
    pick.apply_component(bpy.context, (1, 0, 0), axes)
    hold.COMPONENT.finish(bpy.context)
    slots = bpy.context.scene.transform_orientation_slots
    assert slots[pivot.ROTATE_SLOT].type == pivot.ORIENT_NAME
    assert not hold.turned(slots[pivot.ROTATE_SLOT].custom_orientation.matrix, axes)
    assert _selection(ob) == selected and all((a-b).length < 1e-6 for a, b in zip(before, _world(ob)))
    hold.COMPONENT.reset(bpy.context, position=False, orientation=True)
    assert all(slots[index].type != pivot.ORIENT_NAME for index in pivot.PIVOT_SLOTS)


def test_rotate_custom_axes_follow_the_lead_even_with_move_in_world_mode():
    ob = _cube()
    axes = Euler((.1, .3, -.4)).to_matrix()
    hold.toggle_object_pivot(bpy.context.tool_settings)
    pick.apply_component(bpy.context, (1, 0, 0), axes)
    hold.toggle_object_pivot(bpy.context.tool_settings)
    slots = bpy.context.scene.transform_orientation_slots
    assert slots[pivot.ROTATE_SLOT].type == pivot.ORIENT_NAME
    slots[pivot.MOVE_SLOT].type = 'GLOBAL'
    other = bpy.data.objects.new('OtherPivot', None)
    bpy.context.collection.objects.link(other)
    other[pivot.PROP] = tuple(Euler((-.3, .2, .7)).to_quaternion())
    bpy.context.view_layer.objects.active = other
    pivot._last_lead[0] = None
    pivot.follow_lead(bpy.context, bpy.context.scene)
    expected = pick.pivot_axes(bpy.context, other)
    assert not hold.turned(slots[pivot.ROTATE_SLOT].custom_orientation.matrix, expected)
    assert slots[pivot.MOVE_SLOT].type == 'GLOBAL'
    del other[pivot.PROP]
    pivot._last_lead[0] = None
    pivot.follow_lead(bpy.context, bpy.context.scene)
    assert slots[pivot.ROTATE_SLOT].type == 'LOCAL'
    assert slots[pivot.MOVE_SLOT].type == 'GLOBAL'
