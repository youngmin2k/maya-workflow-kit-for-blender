"""One tool across object / component modes (Maya keeps currentCtx when the selection mode changes).
The rule is bpy-free; the GUI test tests/gui/gui_step174_tool_modes.py presses
the keys."""

from importlib import import_module

import bpy

import kit

tk = import_module(kit.MODULE + ".operators.tool_keys")


def test_sacred_tool_carries_into_the_new_mode():
    rule = tk.carried_tool
    assert rule('OBJECT', 'EDIT_MESH', "builtin.move", "builtin.select_box") == "builtin.move"     # W, F9
    assert rule('EDIT_MESH', 'OBJECT', "builtin.rotate", "builtin.move") == "builtin.rotate"        # E in comp, F8
    assert rule('OBJECT', 'EDIT_CURVE', "builtin.scale", None) == "builtin.scale"
    assert rule('OBJECT', 'POSE', "builtin.select_box", "builtin.move") == "builtin.select_box"     # Q
    # T = Maya ShowManipulators: after F9 Maya is in selectSuperContext
    assert rule('OBJECT', 'EDIT_MESH', "builtin.transform", "builtin.move") == "builtin.select_box"
    assert rule('OBJECT', 'EDIT_MESH', "builtin.transform", "builtin.select_box") is None


def test_no_carry_when_not_needed():
    rule = tk.carried_tool
    assert rule('OBJECT', 'OBJECT', "builtin.move", "builtin.select_box") is None                # no mode change
    assert rule('OBJECT', 'EDIT_MESH', "builtin.move", "builtin.move") is None                   # already there
    assert rule('EDIT_MESH', 'OBJECT', "builtin.cursor", "builtin.move") is None                 # not Q/W/E/R/T
    assert rule('EDIT_MESH', 'OBJECT', "allset.quad_draw_tool", "builtin.move") is None          # a kit tool
    assert rule('OBJECT', 'SCULPT', "builtin.move", None) is None                                # brushes stay
    assert rule('PAINT_WEIGHT', 'OBJECT', "builtin.move", None) is None


def test_handlers_registered_and_removed():
    assert tk._on_depsgraph in bpy.app.handlers.depsgraph_update_post
    assert tk._on_load in bpy.app.handlers.load_post
    kit.disable()
    assert not any(getattr(h, "__module__", "").endswith("tool_keys") for h in bpy.app.handlers.depsgraph_update_post)
    kit.enable()
