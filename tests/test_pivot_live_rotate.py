"""Pivot ring rotations accumulate in the displayed frame without changing geometry/channels."""
from importlib import import_module
from types import SimpleNamespace

import bpy
from mathutils import Euler, Matrix, Vector

import kit
from test_pivot_tap_components import _cube, _world

pivot = import_module(kit.MODULE+'.operators.pivot')
rotate = import_module(kit.MODULE+'.operators.pivot_rotate')
hold = import_module(kit.MODULE+'.operators.hold')


def same(a, b):
    return all(abs(x-y) < 1e-5 for ra, rb in zip(a, b) for x, y in zip(ra, rb))


def test_repeated_rotations_use_the_current_custom_axes_with_scaled_parent():
    ob = _cube()
    parent = bpy.data.objects.new('Parent', None)
    bpy.context.collection.objects.link(parent)
    parent.rotation_euler, parent.scale = (.3, -.1, .2), (1.7, .8, 1.2)
    ob.parent = parent
    ob.rotation_euler, ob.scale = (.1, .4, -.3), (.7, 1.4, 1.1)
    child = bpy.data.objects.new('Child', None)
    bpy.context.collection.objects.link(child)
    child.parent, child.location = ob, (2, -3, 1)
    ob[pivot.PROP] = tuple(Euler((.4, -.2, .7)).to_quaternion())
    bpy.context.view_layer.update()
    basis, child_world, before = ob.matrix_basis.copy(), child.matrix_world.copy(), _world(ob)
    hold.toggle_object_pivot(bpy.context.tool_settings)
    for axis, angle in (('Z', .6), ('X', -.4), ('Y', .3), ('Z', .5)):
        initial = pivot.axes_for(ob)
        expected = Matrix.Rotation(angle, 3, initial.col['XYZ'.index(axis)]) @ initial
        assert bpy.ops.allset.pivot_rotate(axis=axis, angle=angle) == {'FINISHED'}
        bpy.context.view_layer.update()
        assert same(pivot.axes_for(ob), expected)
        assert same(ob.matrix_basis, basis) and same(child.matrix_world, child_world)
        assert all((a-b).length < 1e-5 for a, b in zip(before, _world(ob)))
        for index in pivot.PIVOT_SLOTS:
            slot = bpy.context.scene.transform_orientation_slots[index]
            assert slot.type == pivot.ORIENT_NAME and same(slot.custom_orientation.matrix, expected)
    hold.toggle_object_pivot(bpy.context.tool_settings)


def test_cancel_restores_existing_orientation_and_property_after_live_updates():
    ob = _cube()
    ob[pivot.PROP] = tuple(Euler((.2, -.4, .3)).to_quaternion())
    axes = pivot.axes_for(ob)
    pivot.set_custom_orientation(bpy.context, axes)
    bpy.context.scene.transform_orientation_slots[pivot.ROTATE_SLOT].type = 'LOCAL'
    slots = tuple(slot.type for slot in bpy.context.scene.transform_orientation_slots)
    saved = tuple(ob[pivot.PROP])
    session = SimpleNamespace(axis='Y')
    rotate.ALLSET_OT_pivot_rotate._capture(session, bpy.context)
    for angle in (.2, .5, .9):
        rotate.ALLSET_OT_pivot_rotate._apply(session, bpy.context, angle)
        assert not same(pivot.axes_for(ob), axes)
    rotate.ALLSET_OT_pivot_rotate._restore(session, bpy.context)
    assert tuple(ob[pivot.PROP]) == saved and same(pivot.axes_for(ob), axes)
    assert tuple(slot.type for slot in bpy.context.scene.transform_orientation_slots) == slots
    assert same(pivot._orientation(bpy.context.scene).matrix, axes)


def test_cancel_first_rotation_removes_the_temporary_pivot_property():
    ob = _cube()
    initial = pivot.axes_for(ob)
    session = SimpleNamespace(axis='X')
    rotate.ALLSET_OT_pivot_rotate._capture(session, bpy.context)
    rotate.ALLSET_OT_pivot_rotate._apply(session, bpy.context, .6)
    rotate.ALLSET_OT_pivot_rotate._restore(session, bpy.context)
    assert pivot.PROP not in ob and same(pivot.axes_for(ob), initial)
