"""Repeat modeling commands after display, selection and component-menu changes.

Maya reference: https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Basics/files/GUID-8AB8C493-9FC7-437C-82F5-323904ECA9DF.htm
"""
from importlib import import_module

import bpy

import kit

rep = import_module(kit.MODULE + ".operators.repeat_maya")
modal = import_module(kit.MODULE + ".marking.modal")
CUBE = "Create/Polygon Primitives/Cube"


def viewport():
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    return bpy.context.temp_override(area=area, region=region)


def prepare():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    rep.HISTORY.clear()
    modal.run_action(bpy.context, ('item', CUBE))
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def test_display_key_does_not_replace_the_modeling_command():
    with viewport():
        prepare()
        bpy.ops.allset.display_mode('EXEC_DEFAULT', True, mode='SHADED')
        assert rep.label(bpy.context) == 'Repeat "Cube"'
        assert bpy.ops.allset.repeat_last() == {'FINISHED'}
        assert len([o for o in bpy.context.scene.objects if o.type == 'MESH']) == 2


def test_component_marking_menu_and_select_menu_preserve_the_command():
    with viewport():
        prepare()
        modal.run_action(bpy.context, ('allset.component_mode', {'type': 'FACE'}))
        assert rep.label(bpy.context) == 'Repeat "Cube"'
        modal.run_action(bpy.context, ('object.mode_set', {'mode': 'OBJECT'}))
        modal.run_action(bpy.context, ('item', 'Select/All'))
        assert rep.label(bpy.context) == 'Repeat "Cube"'
        assert bpy.ops.allset.repeat_last() == {'FINISHED'}
        assert len([o for o in bpy.context.scene.objects if o.type == 'MESH']) == 2
        assert all(row[2] == 'Cube' for row in rep.recent(bpy.context) if row[0] == 'kit')


def test_noncommand_actions_do_not_displace_the_saved_command():
    with viewport():
        prepare()
        for action in (('menu', 'VIEW3D_MT_object'), ('tool', 'builtin.move', False),
                       ('prop', 'scene.tool_settings.use_snap', {}),
                       ('item', 'Select/Components/Edge'),
                       ('allset.extrude_edit', {'local_translate_z': 1.0})):
            rep.record('UI change', action)
        assert rep.label(bpy.context) == 'Repeat "Cube"'


def test_custom_manipulators_and_modes_are_not_repeat_commands():
    for idname in ('OBJECT_OT_mode_set', 'OBJECT_OT_editmode_toggle',
                   'ALLSET_OT_component_mode', 'ALLSET_OT_component_mask',
                   'ALLSET_OT_convert_selection', 'ALLSET_OT_toggle_sel_mode',
                   'ALLSET_OT_display_mode', 'ALLSET_OT_frame',
                   'ALLSET_OT_component_scale', 'ALLSET_OT_live_translate',
                   'ALLSET_OT_pivot_translate', 'ALLSET_OT_pivot_rotate'):
        assert not rep.repeatable(idname), idname
    for idname in ('ALLSET_OT_extrude', 'ALLSET_OT_bevel', 'ALLSET_OT_duplicate',
                   'MESH_OT_primitive_cube_add', 'MESH_OT_remove_doubles'):
        assert rep.repeatable(idname), idname


def test_explicit_smart_extrude_record_remains_repeatable():
    rep.HISTORY.clear()
    action = ('v3d', 'allset.smart_extrude', {'translation': (0, 0, 0.5)})
    rep.record('Smart Extrude', action)
    assert rep.HISTORY[-1]['action'] == action


def test_bevel_repeats_on_the_new_edge_after_a_component_menu():
    import bmesh
    prepare()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.scene.tool_settings.mesh_select_mode = (False, True, False)
    bpy.ops.mesh.select_all(action='SELECT')
    assert bpy.ops.allset.bevel('EXEC_DEFAULT', True, fraction=0.1) == {'FINISHED'}
    modal.run_action(bpy.context, ('allset.component_mode', {'type': 'EDGE'}))
    bm = bmesh.from_edit_mesh(bpy.context.edit_object.data)
    bpy.ops.mesh.select_all(action='DESELECT')
    max(bm.edges, key=lambda edge: edge.calc_length()).select_set(True)
    bm.select_flush_mode()
    before = len(bm.verts)
    bmesh.update_edit_mesh(bpy.context.edit_object.data)
    assert rep.label(bpy.context) == 'Repeat "Bevel"'
    assert bpy.ops.allset.repeat_last() == {'FINISHED'}
    assert len(bmesh.from_edit_mesh(bpy.context.edit_object.data).verts) > before


def test_registered_component_selection_wrapper_does_not_replace_native_command():
    import bmesh
    prepare()
    bpy.ops.mesh.primitive_uv_sphere_add('EXEC_DEFAULT', True, segments=8, ring_count=4)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.allset.component_command('EXEC_DEFAULT', True, item='Select/All')
    what = rep.last(bpy.context)
    assert what[0] == 'blender'
    assert bpy.context.window_manager.operators[what[1]].bl_idname == 'MESH_OT_primitive_uv_sphere_add'
    before = len(bmesh.from_edit_mesh(bpy.context.edit_object.data).verts)
    assert bpy.ops.allset.repeat_last() == {'FINISHED'}
    assert len(bmesh.from_edit_mesh(bpy.context.edit_object.data).verts) > before


def test_cancelled_repeated_command_reports_cancelled():
    with viewport():
        prepare()
        rep.record('Bevel', 'allset.bevel')
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        assert bpy.ops.allset.repeat_last() == {'CANCELLED'}
