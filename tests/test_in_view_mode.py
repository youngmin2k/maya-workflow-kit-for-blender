"""In-View state follows mode transitions and object-mode nodes use Mesh coordinates."""
from importlib import import_module
from types import SimpleNamespace

import bmesh
import bpy
import kit

editor = import_module(kit.MODULE+'.ui.in_view_editor')
in_view = import_module(kit.MODULE+'.ui.in_view')
nodes = import_module(kit.MODULE+'.ui.node_attributes')
extrude = import_module(kit.MODULE+'.operators.extrude')


def viewport():
    area = max((a for a in bpy.context.screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width*a.height)
    region = next(r for r in area.regions if r.type == 'WINDOW')
    return bpy.context.temp_override(area=area, region=region)


def bevel():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.object
    ob.location = (2, 3, 1)
    ob.scale = (4.195, 2, 1)
    bpy.context.view_layer.update()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.wm.tool_set_by_id(name='builtin.move')
    bpy.context.scene.tool_settings.mesh_select_mode = (False, True, False)
    bm = bmesh.from_edit_mesh(ob.data)
    extrude.deselect_all(bm)
    bm.edges.ensure_lookup_table()
    bm.edges[0].select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.allset.bevel(fraction=.25)
    editor.clear()
    node, layout = editor.current_layout(bpy.context, fresh=True)
    assert node is not None and layout is not None
    return ob, node


def test_leaving_edit_mode_hides_the_old_editor_before_mouse_dispatch():
    with viewport():
        ob, node = bevel()
        params = dict(node.params)
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.wm.tool_set_by_id(name='builtin.move')
        assert editor.current_layout(bpy.context, fresh=True) == (None, None)
        event = SimpleNamespace(alt=False, oskey=False)
        assert editor.invoke_drag(SimpleNamespace(row=-1), bpy.context, event) == {'PASS_THROUGH'}
        assert extrude.object_record(ob) is node.record and node.params == params


def test_explicit_object_editor_uses_the_same_component_anchor_and_still_edits():
    with viewport():
        ob, node = bevel()
        expected = in_view.cap_frame(ob, node.record)
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.wm.tool_set_by_id(name='builtin.move')
        assert editor.show(bpy.context)
        current, layout = editor.current_layout(bpy.context, fresh=True)
        assert isinstance(current, nodes.ModelingNode) and layout is not None
        frame = in_view.cap_frame(ob, current.record)
        assert (frame[0]-expected[0]).length < 1e-5
        assert (frame[1]-expected[1]).length < 1e-5
        assert abs(frame[2]-expected[2]) < 1e-5
        current.preview(bpy.context, dict(current.params, segments=2))
        current.finish()
        assert ob.mode == 'OBJECT' and editor.current_layout(bpy.context, fresh=True)[0] is not None


def test_tool_dismissal_is_respected_in_object_mode():
    with viewport():
        ob, node = bevel()
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.wm.tool_set_by_id(name='builtin.move')
        assert editor.show(bpy.context)
        node.record.dismissed = True
        assert editor.current_layout(bpy.context, fresh=True) == (None, None)
        assert editor.show(bpy.context)
        assert editor.current_layout(bpy.context, fresh=True)[0] is not None


def test_face_extrusion_anchor_matches_after_leaving_edit_mode():
    with viewport():
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.mesh.primitive_cube_add()
        ob = bpy.context.object
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.context.scene.tool_settings.mesh_select_mode = (False, False, True)
        bm = bmesh.from_edit_mesh(ob.data)
        extrude.deselect_all(bm)
        bm.faces.ensure_lookup_table()
        max(bm.faces, key=lambda face: face.calc_center_median().z).select_set(True)
        bmesh.update_edit_mesh(ob.data)
        bpy.ops.allset.extrude(local_translate_z=.5)
        node = nodes.target(bpy.context)
        expected = in_view.cap_frame(ob, node.record)
        bpy.ops.object.mode_set(mode='OBJECT')
        actual = in_view.cap_frame(ob, node.record)
        assert (actual[0]-expected[0]).length < 1e-5
        assert (actual[1]-expected[1]).length < 1e-5
        assert abs(actual[2]-expected[2]) < 1e-5
