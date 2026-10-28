"""J steps preserve pivot-only transforms, cursor selection, and persistent snap settings."""
from importlib import import_module
from types import SimpleNamespace

import bpy
from mathutils import Euler, Vector

import kit
from test_pivot_tap_components import _cube, _world, _selection

hold = import_module(kit.MODULE+'.operators.hold')
pivot = import_module(kit.MODULE+'.operators.pivot')
move = import_module(kit.MODULE+'.operators.pivot_translate')


def test_j_hold_uses_the_settings_from_before_the_temporary_hold():
    _cube()
    ts = bpy.context.tool_settings
    ts.use_snap, ts.snap_elements = False, {'VERTEX'}
    before = hold.GROUPS['snap'].capture(ts)
    hold.begin(ts, 'step')
    assert hold.step_state(ts, 'TRANSLATE') == (True, False)
    assert hold.step_state(ts, 'ROTATE') == (True, False)
    hold.end(ts, 'step')
    assert hold.GROUPS['snap'].capture(ts) == before


def test_j_translate_uses_custom_axes_and_keeps_geometry_channels_and_children():
    ob = _cube()
    bpy.context.scene.unit_settings.system = 'NONE'
    ob.rotation_euler, ob.scale = (.2, -.1, .4), (1.4, .7, 1.2)
    ob[pivot.PROP] = tuple(Euler((.3, .5, -.4)).to_quaternion())
    child = bpy.data.objects.new('Child', None)
    bpy.context.collection.objects.link(child)
    child.parent, child.location = ob, (2, -3, 1)
    bpy.context.view_layer.update()
    before, child_world = _world(ob), child.matrix_world.copy()
    location, scale, rotation = ob.location.copy(), ob.scale.copy(), ob.rotation_euler.copy()
    session = SimpleNamespace(constraint_axis=(False, True, False))
    move.ALLSET_OT_pivot_translate._capture(session, bpy.context)
    session._raw_delta = session._frame @ Vector((.6, .63, -.3))
    session._step_held = True
    delta = move.ALLSET_OT_pivot_translate._drag_value(session, bpy.context, SimpleNamespace(ctrl=False))
    assert (session._frame.transposed() @ delta-Vector((0, 1, 0))).length < 1e-5
    move.ALLSET_OT_pivot_translate._apply(session, bpy.context, delta)
    assert (ob.matrix_world.translation-session._origin-delta).length < 1e-5
    assert all((a-b).length < 1e-5 for a, b in zip(before, _world(ob)))
    assert (ob.location-location).length < 1e-6 and (ob.scale-scale).length < 1e-6
    assert all(abs(a-b) < 1e-6 for a, b in zip(ob.rotation_euler, rotation))
    assert all(abs(a-b) < 1e-5 for ra, rb in zip(child.matrix_world, child_world) for a, b in zip(ra, rb))
    move.ALLSET_OT_pivot_translate._apply(session, bpy.context, Vector())
    assert (ob.matrix_world.translation-session._origin).length < 1e-5
    assert all((a-b).length < 1e-5 for a, b in zip(before, _world(ob)))


def test_j_in_component_pivot_edit_changes_only_the_cursor():
    ob = _cube(edit=True)
    bpy.context.scene.unit_settings.system = 'NONE'
    before, selected = _world(ob), _selection(ob)
    hold.COMPONENT.start(bpy.context)
    bpy.context.scene.cursor.rotation_euler = (.2, -.3, .4)
    session = SimpleNamespace(constraint_axis=(False, False, False))
    move.ALLSET_OT_pivot_translate._capture(session, bpy.context)
    session._raw_delta = session._frame @ Vector((.63, .21, -.8))
    session._step_held = True
    snapped = move.ALLSET_OT_pivot_translate._drag_value(session, bpy.context, SimpleNamespace(ctrl=False))
    assert (session._frame.transposed() @ snapped-Vector((1, 0, -1))).length < 1e-5
    move.ALLSET_OT_pivot_translate._apply(session, bpy.context, snapped)
    session._step_held = session._baseline_step = False
    free = move.ALLSET_OT_pivot_translate._drag_value(session, bpy.context, SimpleNamespace(ctrl=False))
    move.ALLSET_OT_pivot_translate._apply(session, bpy.context, free)
    assert (bpy.context.scene.cursor.location-session._origin-session._raw_delta).length < 1e-5
    assert _selection(ob) == selected and all((a-b).length < 1e-5 for a, b in zip(before, _world(ob)))
    hold.COMPONENT.finish(bpy.context)
