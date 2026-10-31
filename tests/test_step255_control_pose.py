"""#171: a bone with a Custom Shape is a control (DECISIONS7), so the Move tool never turns a pick of it into
the Edit-mode joint move — an unkeyed Rigify rig dropped to Edit mode on a W click. Plain joints keep
their Edit-mode joint move. The click paths themselves are checked in tests/gui/gui_step255_rigify_pose.py."""

from importlib import import_module

import bpy

import kit

js = import_module(kit.MODULE + ".operators.joint_selection")


def _rig(shaped):
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    arm = bpy.data.armatures.new("a")
    ob = bpy.data.objects.new("rig", arm)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for i in range(2):
        eb = arm.edit_bones.new(f"b{i}")
        eb.head, eb.tail = (0, 0, i), (0, 0, i + 1)
    bpy.ops.object.mode_set(mode='POSE')
    if shaped:
        widget = bpy.data.objects.new("WGT", bpy.data.meshes.new("w"))
        ob.pose.bones["b1"].custom_shape = widget
    return ob


def _pick_with_move_tool(ob, name):
    old = js.move_tool_active
    js.move_tool_active = lambda context: True
    try:
        js.select(bpy.context, ob, name)
        return js.sync_tool_mode(bpy.context), ob.mode
    finally:
        js.move_tool_active = old


def test_control_stays_in_pose_with_move_tool():
    ob = _rig(shaped=True)
    assert js.joint_mode(ob) == 'EDIT'       # unskinned, unkeyed: the case of a freshly generated rig
    switched, mode = _pick_with_move_tool(ob, "b1")
    assert mode == 'POSE' and switched is None, (switched, mode)


def test_plain_joint_still_moves_in_edit_mode():
    ob = _rig(shaped=False)
    switched, mode = _pick_with_move_tool(ob, "b1")
    assert mode == 'EDIT', (switched, mode)
