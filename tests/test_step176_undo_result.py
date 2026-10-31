"""G2: after Ctrl+Z / Shift+Z the Command Line result field shows Maya's "Undo: <command>" / "Redo: <command>",
not the last command's "Result: group1".

``bpy.ops.ed.undo_push`` makes the undo stack in background; ``op('EXEC_DEFAULT', True, ...)`` runs an
operator at undo depth 0 like a key or button, so it pushes its step and Blender registers it."""

from importlib import import_module

import bpy

import kit

command_line = import_module(kit.MODULE + ".command_line")
undo_text = import_module(kit.MODULE + ".command_line.undo_text")
undo_steps = import_module(kit.MODULE + ".undo_steps")
modal = import_module(kit.MODULE + ".marking.modal")


def _field():
    return command_line._result["text"]


def _start():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.ed.undo_push(message="test start")


def _select_all():
    for ob in bpy.context.scene.objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = bpy.context.scene.objects[0]


def test_undo_after_group_shows_undo_group_not_its_result():
    _start()
    _select_all()
    assert bpy.ops.allset.group('EXEC_DEFAULT', True) == {'FINISHED'}
    assert _field().startswith("Result: group"), _field()
    bpy.ops.ed.undo()
    assert _field() == "Undo: Group", _field()
    bpy.ops.ed.redo()
    assert _field() == "Redo: Group", _field()
    bpy.ops.ed.undo()


def test_steps_are_named_in_order_kit_and_blender_operators():
    _start()
    _select_all()
    bpy.ops.allset.group('EXEC_DEFAULT', True)                     # kit operator with a result (counted once)
    bpy.ops.object.location_clear('EXEC_DEFAULT', True)            # Blender operator, registered
    undo_steps.command("Combine", lambda: {'FINISHED'})            # a Maya menu command's step
    bpy.ops.ed.undo()
    assert _field() == "Undo: Combine", _field()
    bpy.ops.ed.undo()
    assert _field() == "Undo: Clear Location", _field()
    bpy.ops.ed.undo()
    assert _field() == "Undo: Group", _field()
    bpy.ops.ed.redo()
    assert _field() == "Redo: Group", _field()
    bpy.ops.ed.redo()
    assert _field() == "Redo: Clear Location", _field()
    # a new step after an undo drops the redo branch, like Blender's stack
    bpy.ops.ed.undo()
    assert bpy.ops.object.scale_clear('EXEC_DEFAULT', True) == {'FINISHED'}
    bpy.ops.ed.undo()
    assert _field() == "Undo: Clear Scale", _field()
    bpy.ops.ed.undo()
    assert _field() == "Undo: Group", _field()


def test_menu_item_run_is_named_after_the_item():
    _start()
    res = modal.run_action(bpy.context, ("item", "Create/Polygon Primitives/Sphere"))
    assert 'FINISHED' in res, res
    bpy.ops.ed.undo()
    assert _field() == "Undo: Sphere", _field()
    bpy.ops.ed.redo()
    assert _field() == "Redo: Sphere", _field()


def test_command_line_entry_is_named_by_its_text():
    _start()
    bpy.context.window_manager.allset_cmd = "a = 1 + 1"
    bpy.ops.ed.undo()
    assert _field() == "Undo: a = 1 + 1", _field()      # Maya: "Undo: select -r pCube1; move -r 0 0 2"


def test_unknown_step_reads_like_a_nameless_maya_chunk():
    _start()
    bpy.ops.object.location_clear('EXEC_DEFAULT', True)
    undo_text.reset()                       # = steps from before a file load / before the add-on started
    command_line.show_result("Result: group1")
    bpy.ops.ed.undo()
    assert _field() == "Undo: ", _field()
    assert not command_line._result["error"]


def test_disable_removes_the_handlers():
    handlers = [fn for _name, fn in undo_text.HANDLERS]
    for name, fn in undo_text.HANDLERS:
        assert fn in getattr(bpy.app.handlers, name), name
    kit.disable()
    try:
        for name in ("undo_pre", "undo_post", "redo_pre", "redo_post", "load_post", "depsgraph_update_post"):
            left = [fn for fn in getattr(bpy.app.handlers, name)
                    if getattr(fn, "__module__", "").endswith("command_line.undo_text")]
            assert not left, (name, left)
        assert not any(fn in handlers for name, _fn in undo_text.HANDLERS for fn in getattr(bpy.app.handlers, name))
    finally:
        kit.enable()
