"""Channel Box middle-drag (#273): picked channels drive a middle drag in a view only until another tool is picked
(the channels stay highlighted, like Maya); deselecting everything also deselects the channels."""

from importlib import import_module

import bpy

import kit

cb = import_module(kit.MODULE + ".ui.channel_box")
marking = import_module(kit.MODULE + ".marking")


def _fresh():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    ob = bpy.data.objects.new("c273", bpy.data.meshes.new("c273"))
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    cb.set_selected_channels([])
    return ob


def _binding(name):
    return next(b for b in marking.TOOL_BINDINGS if b.name == name)()


def test_picking_channels_arms_the_slider():
    _fresh()
    assert not cb.slider_armed(bpy.context), "nothing picked: the tool keeps its middle drag"
    cb.set_selected_channels(["tx"])
    assert cb.slider_armed(bpy.context)
    cb.set_selected_channels([])
    assert not cb.slider_armed(bpy.context)


def test_tool_key_ends_the_slider_but_keeps_the_highlight():
    _fresh()
    for name in ("tool_rotate", "tool_move", "tool_select", "tool_scale"):
        cb.set_selected_channels(["tx"])
        assert cb.slider_armed(bpy.context)
        _binding(name)._set_tool()
        assert not cb.slider_armed(bpy.context), name
        assert cb.selected_channels() == ["tx"], "the channel stays highlighted, like Maya"
    # picking a channel again gives the middle drag back
    cb.select_channel("ry")
    assert cb.slider_armed(bpy.context)


def test_other_tool_than_at_pick_time_passes():
    _fresh()
    cb.set_selected_channels(["tx"])
    saved = dict(cb._slider)
    try:
        cb._slider["tool"] = "builtin.some_other_tool"      # the tool changed (toolbar, Y) since the pick
        assert not cb.slider_armed(bpy.context)
    finally:
        cb._slider.update(saved)


def test_deselect_all_deselects_channels():
    ob = _fresh()
    cb.set_selected_channels(["tx", "ry"])
    ob.select_set(False)
    ob.location.x += 1.0                                   # any update runs the handlers
    bpy.context.view_layer.update()
    assert cb.selected_channels() == [], cb.selected_channels()
    assert not cb.slider_armed(bpy.context)


def test_selecting_another_object_keeps_channels():
    ob = _fresh()
    other = bpy.data.objects.new("c273b", bpy.data.meshes.new("c273b"))
    bpy.context.scene.collection.objects.link(other)
    bpy.context.view_layer.update()
    cb.set_selected_channels(["tx"])
    ob.select_set(False)
    other.select_set(True)
    bpy.context.view_layer.objects.active = other
    bpy.context.view_layer.update()
    assert cb.selected_channels() == ["tx"], "like Maya, the highlight stays on another object"


def test_translate_channels_follow_their_axis_on_screen():
    """A selected translate channel moves like that axis of the Move manipulator: the mouse move projected on the
    axis as drawn (px per unit), so vertical moves count; rotate channels turn 0.36 degrees per px (right / down
    = more)."""
    import math
    assert cb.projected_delta((100.0, 0.0), 50, 30) == 0.5
    assert abs(cb.projected_delta((60.0, -80.0), 0, 40) - (-0.32)) < 1e-9     # up along an axis drawn downwards
    assert cb.projected_delta((0.0, 0.0), 10, 10) == 0.0
    assert abs(cb.rotate_delta(120, 0) - math.radians(43.2)) < 1e-9
    assert abs(cb.rotate_delta(0, 120) + math.radians(43.2)) < 1e-9


def test_node_axes_in_parent_space():
    """Translate X of a child of a turned parent moves along the parent's X in the world."""
    from mathutils import Vector
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    parent = bpy.data.objects.new("axesParent", None)
    child = bpy.data.objects.new("axesChild", None)
    for ob in (parent, child):
        bpy.context.scene.collection.objects.link(ob)
    parent.rotation_euler.z = 1.5707963267948966      # parent X points along world Y
    parent.scale = (2.0, 2.0, 2.0)
    child.parent = parent
    child.rotation_euler.x = 0.7         # the child's own turn doesn't change where its channel moves it
    child.location = (1.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    origin, direction = cb.node_axes(child, "tx")
    assert (direction - Vector((0.0, 2.0, 0.0))).length < 1e-5, direction
    assert (origin - child.matrix_world.translation).length < 1e-6
    assert cb.node_axes(child, "rx") is None and cb.node_axes(child, "sx") is None
    for ob in (child, parent):
        bpy.data.objects.remove(ob)
