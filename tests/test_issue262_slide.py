"""Move tool Transform Constraint (Edge / Surface slide) and Ctrl+Shift+MMB edge slide. GUI:
tests/gui/gui_issue262_slide.py."""
from importlib import import_module

import bpy

import kit

xc = import_module(kit.MODULE + ".operators.xform_constraint")
prefs = import_module(kit.MODULE + ".preferences")
menus = import_module(kit.MODULE + ".marking.menus")
draw = import_module(kit.MODULE + ".marking.draw")
ts_ui = import_module(kit.MODULE + ".ui.tool_settings")


def _edit_cube():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    bpy.ops.mesh.primitive_cube_add()
    bpy.ops.object.mode_set(mode='EDIT')


def test_default_off_and_setting():
    p = prefs.get(bpy.context)
    assert p.bl_rna.properties["transform_constraint"].default == 'NONE'
    _edit_cube()
    p.transform_constraint = 'NONE'
    assert not xc.active(bpy.context)
    assert bpy.ops.allset.xform_constraint(mode='EDGE') == {'FINISHED'}
    assert p.transform_constraint == 'EDGE' and xc.active(bpy.context)
    bpy.ops.object.mode_set(mode='OBJECT')
    assert not xc.active(bpy.context), "object mode moves objects as before"
    p.transform_constraint = 'NONE'


def test_vertex_only():
    assert xc.vertex_only((True, False, False))
    assert not xc.vertex_only((True, True, False))
    assert not xc.vertex_only((False, False, True))


def test_marking_menu_radio_items():
    p = prefs.get(bpy.context)
    sub = dict(menus._constraints())["Transform Constraints"]
    labels = [label for label, _action in sub.items]
    assert labels == ["Off", "Edge Slide", "Surface Slide", "Along Normals"]
    p.transform_constraint = 'SURFACE'
    states = [draw.checked(action) for _label, action in sub.items[:3]]
    assert states == [False, False, True], states
    p.transform_constraint = 'NONE'


def test_reset_tool_turns_it_off():
    p = prefs.get(bpy.context)
    p.transform_constraint = 'EDGE'
    ts_ui.reset_maya_options(bpy.context, 'TRANSLATE')
    assert p.transform_constraint == 'NONE'


def test_ctrl_shift_mmb_in_move_tool():
    km = kit.maya_kc().keymaps["3D View Tool: Move"]
    items = [k for k in km.keymap_items if k.idname == "allset.component_slide" and k.active]
    assert len(items) == 1
    k = items[0]
    assert (k.type, k.value, k.ctrl, k.shift, k.alt) == ('MIDDLEMOUSE', 'PRESS', True, True, False)
    assert k.properties.mode == 'EDGE'
