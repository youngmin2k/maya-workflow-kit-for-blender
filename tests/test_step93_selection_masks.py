"""Shift+Q check marks, selection masks kept across File > New / Open (Maya: they are session
state), Tool Settings Reset Tool."""

import math
from importlib import import_module

import bpy

import kit

engine = import_module(kit.MODULE + ".marking.engine")
draw = import_module(kit.MODULE + ".marking.draw")
menus = import_module(kit.MODULE + ".marking.menus")
status_line = import_module(kit.MODULE + ".ui.status_line")
tool_settings = import_module(kit.MODULE + ".ui.tool_settings")
snap_align = import_module(kit.MODULE + ".operators.snap_align")
prefs_mod = import_module(kit.MODULE + ".preferences")


def _mask(kind):
    return ("allset.component_mask", {"kind": kind})


def test_mask_items_are_check_boxes():
    assert engine.is_toggle(_mask("VERT")) and engine.is_toggle(_mask("EDGE")) and engine.is_toggle(_mask("FACE"))
    assert not engine.is_toggle(_mask("ALL")), "All Components on is a command in Maya"
    ts = bpy.context.scene.tool_settings
    ts.mesh_select_mode = (True, False, True)
    assert draw.checked(_mask("VERT")) is True and draw.checked(_mask("EDGE")) is False
    assert draw.checked(_mask("FACE")) is True and draw.checked(_mask("ALL")) is None
    # the Shift+Q menu really holds these actions
    found = set()

    def walk(sub):
        for _d, (_label, act) in sub.radial.items():
            if isinstance(act, menus.Sub):
                walk(act)
            elif isinstance(act, tuple) and act[0] == "allset.component_mask":
                found.add(act[1]["kind"])
    walk(menus.SELECT_COMPONENT)
    assert {"VERT", "EDGE", "FACE"} <= found, found


def _spaces():
    return list(status_line.all_view3d_spaces())


def test_masks_survive_new_file():
    ts = bpy.context.scene.tool_settings
    for sp in _spaces():
        sp.show_object_select_mesh = False
        sp.show_object_select_curve = False
    ts.mesh_select_mode = (False, True, False)
    bpy.ops.wm.read_homefile(use_factory_startup=True)     # File > New: load_pre / load_post run
    spaces = _spaces()
    assert spaces, "no 3D views after the load"
    assert all(not sp.show_object_select_mesh and not sp.show_object_select_curve for sp in spaces)
    assert all(sp.show_object_select_camera for sp in spaces), "untouched masks stay on"
    assert tuple(bpy.context.scene.tool_settings.mesh_select_mode) == (False, True, False)
    for sp in spaces:                                       # leave the defaults for the next tests
        sp.show_object_select_mesh = sp.show_object_select_curve = True
    bpy.context.scene.tool_settings.mesh_select_mode = (True, False, False)


def test_no_carry_without_a_remembered_state():
    status_line._carried.clear()
    status_line._masks_after_load()                         # nothing remembered: nothing changes
    assert all(sp.show_object_select_mesh for sp in _spaces())


def _set_tool(idname):
    bpy.ops.wm.tool_set_by_id(name=idname, space_type='VIEW_3D')
    return bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=False)


def test_reset_tool_restores_defaults():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    tool = _set_tool("builtin.rotate")
    assert tool is not None and tool.idname == "builtin.rotate"
    props = tool.operator_properties("transform.rotate")
    props.release_confirm = True
    assert props.is_property_set("release_confirm")
    scene, ts = bpy.context.scene, bpy.context.scene.tool_settings
    scene.transform_orientation_slots[2].type = 'GLOBAL'
    ts.transform_pivot_point = 'MEDIAN_POINT'
    ts.snap_angle_increment_3d = math.radians(5)
    snap_align.set_step_snap(ts, 'ROTATE', 'RELATIVE')
    assert snap_align.step_snap_mode(ts, 'ROTATE') != 'OFF'
    assert bpy.ops.allset.reset_tool() == {'FINISHED'}
    assert not props.is_property_set("release_confirm")
    assert scene.transform_orientation_slots[2].type == 'LOCAL'          # Maya Rotate axis = Object
    assert ts.transform_pivot_point == 'ACTIVE_ELEMENT'
    assert abs(ts.snap_angle_increment_3d - math.radians(15)) < 1e-6
    assert snap_align.step_snap_mode(ts, 'ROTATE') == 'OFF'


def test_reset_move_tool_options():
    tool = _set_tool("builtin.move")
    prefs = prefs_mod.get()
    default = prefs.bl_rna.properties["smart_duplicate"].default
    prefs.smart_duplicate = not default
    bpy.context.scene.transform_orientation_slots[1].type = 'LOCAL'
    assert tool_settings.reset_tool(bpy.context)[0] == "builtin.move"
    assert prefs.smart_duplicate == default
    assert bpy.context.scene.transform_orientation_slots[1].type == 'GLOBAL'   # Maya Move axis = World
    assert "transform.translate" in tool_settings.tool_operators(bpy.context, tool)


def test_reset_row_in_tool_settings():
    assert tool_settings.draw_reset_row in bpy.types.VIEW3D_PT_active_tool._dyn_ui_initialize()
