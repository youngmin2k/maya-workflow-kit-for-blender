"""#277: the Time Slider shows the keys of the selected nodes only (nothing selected = no ticks), and the Tool Box
Outliner button is Maya's Outliner toggle. GUI: tests/gui/gui_issue277_time_slider.py, gui_issue277_outliner.py."""

from importlib import import_module
from types import SimpleNamespace

import bpy

import kit

ts = import_module(kit.MODULE + ".ui.time_slider")
cb = import_module(kit.MODULE + ".ui.channel_box")
tb = import_module(kit.MODULE + ".ui.toolbox")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for act in list(bpy.data.actions):
        bpy.data.actions.remove(act)


def _keyed_cube(frame, name):
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    ob.name = name
    ob.keyframe_insert("location", frame=frame)
    return ob


def test_deselected_active_object_shows_no_ticks():
    _clear()
    ob = _keyed_cube(10, "a")
    assert ts.tick_nodes(bpy.context) == [ob]
    assert [f for f, _b in ts.key_frames(ts.tick_nodes(bpy.context))] == [10]
    bpy.ops.object.select_all(action='DESELECT')
    assert bpy.context.view_layer.objects.active == ob, "Blender keeps the active object"
    assert ts.tick_nodes(bpy.context) == []
    assert ts.key_frames(ts.tick_nodes(bpy.context)) == []


def test_ticks_follow_the_selection():
    _clear()
    a = _keyed_cube(5, "a")
    b = _keyed_cube(20, "b")         # active, lead
    a.select_set(True)
    assert set(ts.tick_nodes(bpy.context)) == {a, b}
    assert [f for f, _bd in ts.key_frames(ts.tick_nodes(bpy.context))] == [5, 20]
    b.select_set(False)              # still active, no longer selected
    assert ts.tick_nodes(bpy.context) == [a]
    assert [f for f, _bd in ts.key_frames(ts.tick_nodes(bpy.context))] == [5]


def test_edit_mode_object_keeps_its_ticks():
    _clear()
    ob = _keyed_cube(7, "a")
    bpy.ops.object.mode_set(mode='EDIT')
    ob.select_set(False)             # the object being edited still shows its keys (its components are selected)
    assert ts.tick_nodes(bpy.context) == [ob]
    bpy.ops.object.mode_set(mode='OBJECT')


def test_pose_bones_only_selected():
    _clear()
    bpy.ops.object.armature_add()
    arm = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.armature.bone_primitive_add(name="Other")
    bpy.ops.object.mode_set(mode='POSE')
    a, b = arm.pose.bones["Bone"], arm.pose.bones["Other"]
    a.keyframe_insert("location", frame=3)
    b.keyframe_insert("location", frame=7)
    cb.set_bone_selected(a, True)
    cb.set_bone_selected(b, False)
    assert ts.tick_nodes(bpy.context) == [a]
    cb.set_bone_selected(a, False)
    assert ts.tick_nodes(bpy.context) == []
    bpy.ops.object.mode_set(mode='OBJECT')


def test_no_playhead_frame_helper_left():
    # the current-frame key is no longer drawn as a frame around Blender's box
    assert not hasattr(ts, "playhead_half_width")


class _Ops:
    def __init__(self, log):
        object.__setattr__(self, "log", log)

    def __getattr__(self, name):
        if name in ("row", "column", "box", "split"):
            return lambda *a, **k: _Ops(self.log)
        if name == "operator":
            def op(idname, **kw):
                self.log.append((idname, kw))
                return SimpleNamespace()
            return op
        return lambda *a, **k: None

    def __setattr__(self, name, value):
        pass


def test_toolbox_outliner_button_is_a_toggle():
    log = []
    tb.ALLSET_PT_toolbox_layouts.draw(SimpleNamespace(layout=_Ops(log)), bpy.context)
    ops = [i for i, _kw in log]
    assert "allset.open_editor" not in ops, ops
    kw = dict(log)["allset.toggle_outliner"]
    assert kw.get("depress") is tb.outliner_shown(bpy.context), kw    # pressed while an Outliner is shown
    assert hasattr(bpy.types, "ALLSET_OT_toggle_outliner")


def test_outliner_helpers():
    assert tb.outliner_areas(None) == []
    screen = bpy.context.screen or bpy.data.screens[0]
    assert tb.outliner_areas(screen) == [a for a in screen.areas if a.type == 'OUTLINER']
