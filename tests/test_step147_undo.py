"""#88 #92 #86: every Maya command is one undo step, and kit commands open no Adjust Last Operation.
GUI: tests/gui/gui_step147_hud.py.

``bpy.ops.ed.undo_push`` makes the undo stack in background (ed_undo.cc #60934), so undo is tested headless. A UI
button calls its operator at undo depth 0: ``op('EXEC_DEFAULT', True, ...)`` does the same from Python."""

from importlib import import_module

import bpy

import kit

menu_map = import_module(kit.MODULE + ".ui.menu_map")
modal = import_module(kit.MODULE + ".marking.modal")
undo_steps = import_module(kit.MODULE + ".undo_steps")


def _names():
    return sorted(o.name for o in bpy.context.scene.objects)


def _start():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.ed.undo_push(message="test start")


def _only(name):
    ob = bpy.data.objects[name]
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    return ob


def test_menu_command_is_its_own_undo_step():
    _start()
    before = _names()
    assert bpy.ops.allset.menu_item('EXEC_DEFAULT', True, item="Create/Polygon Primitives/Cube") == {'FINISHED'}
    made = [n for n in _names() if n not in before]
    assert len(made) == 1, made
    bpy.ops.transform.translate('EXEC_DEFAULT', True, value=(3, 0, 0))
    bpy.ops.ed.undo()                       # the move only: Maya keeps the cube
    assert made[0] in _names(), _names()
    assert tuple(bpy.data.objects[made[0]].location) == (0, 0, 0)
    bpy.ops.ed.undo()                       # then the command
    assert _names() == before, _names()


def test_88_tool_item_from_object_mode_keeps_component_mode_on_undo():
    _start()
    _only("Cube")
    bpy.ops.ed.undo_push(message="cube selected")
    bpy.ops.allset.menu_item('EXEC_DEFAULT', True, item="Mesh Tools/Insert Edge Loop")
    assert bpy.context.mode == 'EDIT_MESH'
    bpy.ops.mesh.select_all('EXEC_DEFAULT', True, action='DESELECT')     # the tool's first edit
    bpy.ops.ed.undo()
    assert bpy.context.mode == 'EDIT_MESH', "Ctrl+Z after the first edit left component mode (#88)"
    bpy.ops.ed.undo()
    assert bpy.context.mode == 'OBJECT'


def test_shelf_and_marking_runs_are_undo_steps_too():
    # shelf buttons, marking menus and the Modeling Toolkit run actions through run_action at depth 0
    _start()
    before = _names()
    res = modal.run_action(bpy.context, ("item", "Create/Polygon Primitives/Sphere"))
    assert 'FINISHED' in res, res
    assert undo_steps.depth() == 0
    made = [n for n in _names() if n not in before]
    bpy.ops.transform.translate('EXEC_DEFAULT', True, value=(0, 2, 0))
    bpy.ops.ed.undo()
    assert made[0] in _names()
    bpy.ops.ed.undo()
    assert _names() == before, _names()


def test_redo_option_box_registers_its_operator():
    # option box kind "redo" = run + Adjust Last Operation: the operator must be registered for the panel
    menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
    path = "Create/Lights/Point Light"      # the NURBS primitives open Maya windows now
    assert menu_sets.option_kind(path) == "redo"
    _start()
    before = _names()
    bpy.ops.allset.menu_option_box('EXEC_DEFAULT', True, item=path)
    ops = bpy.context.window_manager.operators
    assert len(ops) and ops[-1].bl_idname.lower().startswith(menu_map.spec(path)[1].split(".")[0]), \
        [o.bl_idname for o in ops]
    assert len(_names()) == len(before) + 1
    bpy.ops.ed.undo()                       # one step, not two
    assert _names() == before, _names()


def _reach():
    reach = {}
    for km in kit.maya_kc().keymaps:
        for ki in km.keymap_items:
            if ki.idname.startswith("allset.") and ki.active:
                reach.setdefault(ki.idname, []).append(km.name)
    return reach


def _opens_hud(cls):
    """Blender's redo panel test: REGISTER + UNDO and something to draw (interface_region_hud.cc last_redo_poll)."""
    opts = getattr(cls, "bl_options", set())
    if not ('REGISTER' in opts and 'UNDO' in opts):
        return False
    mod, name = cls.bl_idname.split(".")
    rna = getattr(getattr(bpy.ops, mod), name).get_rna_type()
    visible = [p.identifier for p in rna.properties if p.identifier != "rna_type" and not p.is_hidden]
    return bool(visible) or callable(getattr(cls, "draw", None))


def test_no_kit_command_opens_adjust_last_operation():
    # what can end at undo depth 0 and register: keymap items, window-level modal tools, option windows (props
    # dialogs); menu items run nested and never register
    reach = _reach()
    bad = []
    for name in dir(bpy.types):
        if not name.startswith("ALLSET_OT_"):
            continue
        cls = getattr(bpy.types, name)
        idname = cls.bl_idname
        if not (idname in reach or hasattr(cls, "modal") or idname.startswith("allset.opt_")):
            continue
        if _opens_hud(cls):
            bad.append((idname, reach.get(idname, ["modal" if hasattr(cls, "modal") else "window"])[:1]))
    assert not bad, f"these open Blender's redo panel: {sorted(bad)}"


def test_named_commands_92_86():
    for idname in ("allset.extrude", "allset.bevel", "allset.ik_handle", "allset.joint_tool",
                   "allset.extrude_edit", "allset.bevel_edit", "allset.opt_poly_cube"):
        mod, name = idname.split(".")
        cls = getattr(bpy.types, f"{mod.upper()}_OT_{name}", None)
        assert cls is not None, idname
        assert not _opens_hud(cls), idname
        assert 'UNDO' in cls.bl_options, idname
    # Ctrl+E / Ctrl+B stay registered so Repeat Last (Maya G) repeats them with the same values
    assert 'REGISTER' in bpy.types.ALLSET_OT_extrude.bl_options and 'REGISTER' in bpy.types.ALLSET_OT_bevel.bl_options
