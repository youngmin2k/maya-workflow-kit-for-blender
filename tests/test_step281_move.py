"""#192: Graph Editor key moves the Maya way: Shift axis lock (first 3 px decide) and time snap landing on
whole frames."""

import math
from importlib import import_module
from types import SimpleNamespace

import bpy

import kit

gm = import_module(kit.MODULE + ".operators.graph_move")


def _cube_with_keys(keys=((1, 0.0), (10, 5.0), (20, 0.0))):
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    ob = bpy.data.objects.new("pCube1", bpy.data.meshes.new("pCubeShape1"))
    bpy.context.scene.collection.objects.link(ob)
    for f, v in keys:
        ob.location.x = v
        ob.keyframe_insert("location", index=0, frame=f)
    fc = kit.fcurves(ob).find("location", index=0)
    for kp in fc.keyframe_points:
        kp.select_control_point = kp.select_left_handle = kp.select_right_handle = False
    return ob, fc


def _ctx(fcurves, normalized=False):
    return SimpleNamespace(editable_fcurves=list(fcurves), scene=bpy.context.scene,
                           space_data=SimpleNamespace(use_normalization=normalized))


def test_first_three_px_decide_the_axis():
    assert gm.decide(1, 2) is None and gm.decide(2, 2) is None and gm.decide(0, -2) is None
    assert gm.decide(3, 0) == 'TIME'
    assert gm.decide(0, -3) == 'VALUE'
    assert gm.decide(4, -3.6) == 'TIME'
    assert gm.decide(3, 3) == 'TIME'                   # a tie goes to time
    assert gm.decide(-3, -4) == 'VALUE'
    assert gm.decide(40, -1) == 'TIME'


def test_time_snap_lands_on_whole_frames():
    assert gm.snapped_time(10.3, 0.38, True) == 10.0
    assert gm.snapped_time(10.3, 0.59, True) == 11.0
    assert gm.snapped_time(10.3, 0.995, True) == 11.0
    assert gm.snapped_time(10.0, 0.4, True) == 10.0
    assert gm.snapped_time(10.0, 0.6, True) == 11.0
    assert gm.snapped_time(10.0, 1.4, True) == 11.0
    assert gm.snapped_time(10.0, 2.49, True) == 12.0
    assert gm.snapped_time(10.0, -0.6, True) == 9.0
    assert math.isclose(gm.snapped_time(10.0, 52 / 37.2, False), 10.0 + 52 / 37.2)
    assert gm.whole_frame(10.99995) == 11.0 and gm.whole_frame(-0.5) == -1.0


def test_normalization_factor():
    # one Bezier segment 0 -> 5 whose inner handles reach 1 and 6 (the first key's left handle doesn't count)
    f, off = gm.normalization([(0.0, -1.0, 1.0, 'BEZIER'), (5.0, 6.0, 4.0, 'BEZIER')])
    assert math.isclose(f, 2 / 6) and math.isclose(off, -3.0)
    f, off = gm.normalization([(2.0, 2.0, 2.0, 'LINEAR'), (2.0, 2.0, 2.0, 'LINEAR')])
    assert f == 1.0 and off == -2.0


def test_keyset_moves_selected_keys_and_handles():
    _ob, fc = _cube_with_keys()
    kp = fc.keyframe_points[1]
    kp.select_control_point = True
    kp.handle_left_type = kp.handle_right_type = 'FREE'
    left0, right0 = tuple(kp.handle_left), tuple(kp.handle_right)
    keys = gm.KeySet(_ctx([fc]))
    assert keys
    keys.apply(2.07, 0.0, True, time_axis=True)        # 77 px at 37.2 px / frame -> +2 frames
    assert kp.co.x == 12.0 and kp.co.y == 5.0
    assert math.isclose(kp.handle_left.x, left0[0] + 2.0, abs_tol=1e-4)
    keys.apply(0.0, 0.826, True, time_axis=False)      # value only: time back at the press, value moved
    assert kp.co.x == 10.0 and math.isclose(kp.co.y, 5.826, abs_tol=1e-5)
    assert math.isclose(kp.handle_right.y - right0[1], 0.826, abs_tol=1e-4)
    keys.restore()
    assert tuple(kp.co) == (10.0, 5.0)
    assert fc.keyframe_points[0].co.x == 1.0 and fc.keyframe_points[2].co.x == 20.0   # unselected keys stay


def test_keyset_fractional_key_snaps_to_whole_frame():
    _ob, fc = _cube_with_keys(((1, 0.0), (10, 5.0), (20, 0.0)))
    kp = fc.keyframe_points[1]
    kp.co.x = 10.3
    kp.handle_left.x += 0.3
    kp.handle_right.x += 0.3
    kp.select_control_point = True
    keys = gm.KeySet(_ctx([fc]))
    keys.apply(0.38, 0.0, True)
    assert kp.co.x == 10.0
    keys.apply(0.59, 0.0, True)
    assert kp.co.x == 11.0
    keys.apply(0.59, 0.0, False)
    assert math.isclose(kp.co.x, 10.89, abs_tol=1e-5)


def test_rotation_curves_move_in_degrees():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    ob = bpy.data.objects.new("pCube1", bpy.data.meshes.new("pCubeShape1"))
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.scene.unit_settings.system_rotation = 'DEGREES'
    for f in (1, 10):
        ob.keyframe_insert("rotation_euler", index=2, frame=f)
    fc = kit.fcurves(ob).find("rotation_euler", index=2)
    fc.keyframe_points[1].select_control_point = True
    keys = gm.KeySet(_ctx([fc]))
    keys.apply(0.0, 90.0, True, time_axis=False)        # 90 on the value axis = 90 degrees
    assert math.isclose(fc.keyframe_points[1].co.y, math.pi / 2, abs_tol=1e-5)


def test_drop_fractions_after_blender_move():
    _ob, fc = _cube_with_keys()
    for kp, x in zip(fc.keyframe_points, (1.0, 12.3, 20.0)):
        d = x - kp.co.x
        kp.co.x = x
        kp.handle_left.x += d
        kp.handle_right.x += d
    fc.keyframe_points[1].select_control_point = True
    assert gm.drop_fractions([fc]) == 1
    kp = fc.keyframe_points[1]
    assert kp.co.x == 12.0 and kp.handle_left.x < 12.0 < kp.handle_right.x
    assert gm.drop_fractions([fc]) == 0                 # whole frames stay


def test_time_snap_state_is_the_toolbar_button():
    ts = bpy.context.scene.tool_settings
    ts.use_snap_anim = True
    assert gm.time_snap_on(bpy.context.scene)
    ts.use_snap_anim = False
    assert not gm.time_snap_on(bpy.context.scene)
    ts.use_snap_anim = True


def test_operators_registered():
    assert hasattr(bpy.types, "ALLSET_OT_graph_axis_drag")
    assert hasattr(bpy.types, "ALLSET_OT_graph_move_snap")


def test_keymap_items():
    km = kit.maya_kc().keymaps["Graph Editor"]
    items = [(i.idname, i.type, i.value, i.shift) for i in km.keymap_items]
    assert ("allset.graph_axis_drag", 'MIDDLEMOUSE', 'PRESS', True) in items
    assert ("allset.graph_axis_drag", 'LEFTMOUSE', 'CLICK_DRAG', True) in items
    assert ("allset.graph_move_snap", 'MIDDLEMOUSE', 'CLICK_DRAG', False) in items
    assert ("allset.graph_move_snap", 'LEFTMOUSE', 'CLICK_DRAG', False) in items
