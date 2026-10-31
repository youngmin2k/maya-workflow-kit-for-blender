"""Time Slider key ticks and the draggable Range Slider bar.
GUI: tests/gui/gui_step73_time_slider.py."""

from importlib import import_module

import bpy

import kit

ts = import_module(kit.MODULE + ".ui.time_slider")
rb = import_module(kit.MODULE + ".ui.range_bar")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for act in list(bpy.data.actions):
        bpy.data.actions.remove(act)


def test_key_frames_object():
    _clear()
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    ob.keyframe_insert("location", frame=1)
    ob.keyframe_insert("location", frame=12)
    ob.keyframe_insert("rotation_euler", index=2, frame=12)
    assert ts.key_frames([ob]) == [(1.0, False), (12.0, False)]
    assert ts.key_frames([]) == []


def test_key_frames_breakdown_merge():
    _clear()
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    ob.keyframe_insert("location", index=0, frame=5)
    ob.keyframe_insert("location", index=1, frame=5)
    ob.keyframe_insert("location", index=0, frame=8)
    fcs = {fc.array_index: fc for fc in kit.fcurves(ob)}
    for kp in fcs[0].keyframe_points:
        kp.type = 'BREAKDOWN'
    # frame 5: one curve has a regular key -> red; frame 8: only a breakdown -> green
    assert ts.key_frames([ob]) == [(5.0, False), (8.0, True)]


def test_key_frames_bone_only_its_curves():
    _clear()
    bpy.ops.object.armature_add()
    arm = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.armature.bone_primitive_add(name="Other")
    bpy.ops.object.mode_set(mode='POSE')
    a, b = arm.pose.bones["Bone"], arm.pose.bones["Other"]
    a.keyframe_insert("location", frame=3)
    b.keyframe_insert("location", frame=7)
    assert ts.key_frames([a]) == [(3.0, False)]
    assert ts.key_frames([b]) == [(7.0, False)]
    bpy.ops.object.mode_set(mode='OBJECT')


def test_bar_span():
    bg, f = (48, 48, 48), (84, 84, 84)
    row = [bg] * 10 + [f] * 30 + [bg] * 7 + [f] * 50 + [bg] * 7 + [f] * 50 + [bg] * 200 + [f] * 50 + [bg] * 300
    assert rb.bar_span(row, bg, min_w=100) == (154, 354)
    assert rb.bar_span(row, bg, min_w=100, skip=4) is None      # the last run reaches the edge: not a bar
    assert rb.bar_span([bg] * 50, bg, min_w=10) is None


def test_zone_and_segment():
    bar = dict(x0=100, x1=300, s=1, e=201)
    assert rb.segment(bar, 1, 101) == (100.0, 200.0)
    assert rb.zone(105, 100, 200, 18) == 'START'
    assert rb.zone(195, 100, 200, 18) == 'END'
    assert rb.zone(150, 100, 200, 18) == 'MOVE'
    assert rb.zone(250, 100, 200, 18) is None
    assert rb.segment(bar, -50, 400) == (100, 300)   # a preview range outside the animation range stays on the track


def test_drag_range():
    assert rb.drag_range('MOVE', 1, 120, 30, 1, 200) == (31, 150)
    assert rb.drag_range('MOVE', 1, 120, 500, 1, 200) == (81, 200)     # stays inside, keeps its length
    assert rb.drag_range('MOVE', 10, 40, -50, 1, 200) == (1, 31)
    assert rb.drag_range('START', 1, 120, 200, 1, 200) == (119, 120)   # never past the other end
    assert rb.drag_range('END', 1, 120, -500, 1, 200) == (1, 2)
    assert rb.drag_range('END', 1, 120, 500, 1, 200) == (1, 200)


def test_set_playback_order():
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, 200
    scene.use_preview_range = False
    assert rb.playback(scene) == (1, 200)
    rb.set_playback(scene, 10, 40)
    assert scene.use_preview_range and rb.playback(scene) == (10, 40)
    rb.set_playback(scene, 150, 180)   # start beyond the old end
    assert rb.playback(scene) == (150, 180)
    rb.set_playback(scene, 2, 5)
    assert rb.playback(scene) == (2, 5)
    scene.use_preview_range = False


def test_double_click_toggles_whole_range():
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, 200
    rb.set_playback(scene, 10, 40)
    rb.toggle_whole(scene)
    assert rb.playback(scene) == (1, 200)
    rb.toggle_whole(scene)
    assert rb.playback(scene) == (10, 40)      # Blender keeps the preview range while it is off
    scene.use_preview_range = False
