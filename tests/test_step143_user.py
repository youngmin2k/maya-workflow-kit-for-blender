"""GitHub user reports before 0.3.0 (GUI: tests/gui/gui_step143_user.py).

- #84: the Maya double-click loop pick passed ``ring=False`` to ``mesh.loop_select``, which Blender 5.1+ no longer has
  (ring pick is ``mesh.edgering_select`` there): "keyword "ring" unrecognized" on 5.2.
- #80: after Ctrl+E the extrude manipulator hid the kit Move manipulator, and W didn't bring it back (the Move tool
  was already active), so the new faces couldn't be moved the usual way. Maya: a tool key swaps the extrude
  manipulator for that tool's one; the node stays in Channel Box INPUTS.
"""

import inspect
from importlib import import_module
from types import SimpleNamespace

import bmesh
import bpy

import kit

loop_pick = import_module(kit.MODULE + ".operators.loop_pick")
ex = import_module(kit.MODULE + ".operators.extrude")
in_view = import_module(kit.MODULE + ".ui.in_view")
taphold = import_module(kit.MODULE + ".operators.taphold")


# --- #84 ------------------------------------------------------------------------------------------------------------

def test_loop_select_keywords_exist_in_this_blender():
    props = {p.identifier for p in bpy.ops.mesh.loop_select.get_rna_type().properties}
    for between in (False, True):
        args = loop_pick.loop_select_args(between)
        missing = set(args) - props
        assert not missing, f"mesh.loop_select has no {missing} in Blender {bpy.app.version_string} ({props})"
        assert args["extend"] is between


def test_loop_pick_passes_no_ring_keyword():
    # a source check too: the RNA check above only covers the Blender the test runs on
    src = inspect.getsource(loop_pick.ALLSET_OT_loop_pick.invoke)
    assert "loop_select_args(" in src and "ring=" not in src, src
    assert "ring" not in loop_pick.loop_select_args(False)


# --- #80 ------------------------------------------------------------------------------------------------------------

def _cube_top_extruded():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.mesh.primitive_cube_add(size=1)
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    bm = bmesh.from_edit_mesh(ob.data)
    for f in bm.faces:
        f.select_set(False)
    for f in bm.faces:
        if f.normal.z > 0.9:
            f.select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.extrude() == {'FINISHED'}
    return ob


def _view_context(ob):
    """What ``in_view.record`` reads: a (non Tool Box) 3D View and the edit object."""
    space = SimpleNamespace(type='VIEW_3D', show_region_toolbar=False, show_region_header=True,
                            show_region_ui=False, show_object_viewport_mesh=True)
    return SimpleNamespace(space_data=space, edit_object=ob)


def test_extrude_manipulator_shows_after_ctrl_e():
    ob = _cube_top_extruded()
    _o, rec = in_view.record(_view_context(ob))
    assert rec is not None and rec.name.startswith("polyExtrudeFace") and not rec.dismissed


def test_tool_keys_swap_the_extrude_manipulator_for_the_tool():
    for name in ("tool_move", "tool_rotate", "tool_scale", "tool_select"):
        ob = _cube_top_extruded()
        ctx = _view_context(ob)
        assert in_view.record(ctx)[1] is not None
        taphold.get_binding(name).tap(bpy.context)       # the key's tap (tool_set_by_id fails in -b: caught)
        assert in_view.record(ctx) == (None, None), f"{name}: extrude manipulator still shown"
        _o, rec = ex.active(bpy.context)
        assert rec is not None and rec.dismissed, f"{name}: the extrusion must stay in Channel Box INPUTS"


def test_dismissed_extrusion_stays_editable():
    ob = _cube_top_extruded()
    taphold.get_binding("tool_move").tap(bpy.context)
    assert bpy.ops.allset.extrude_edit(local_translate_z=0.5) == {'FINISHED'}
    _o, rec = ex.active(bpy.context)
    assert rec is not None and abs(rec.params["local_translate_z"] - 0.5) < 1e-6
    assert in_view.record(_view_context(ob)) == (None, None)


def test_new_extrusion_shows_its_manipulator_again():
    ob = _cube_top_extruded()
    taphold.get_binding("tool_move").tap(bpy.context)
    assert bpy.ops.allset.extrude() == {'FINISHED'}       # Ctrl+E again on the new caps: a new node
    _o, rec = in_view.record(_view_context(ob))
    assert rec is not None and not rec.dismissed


# --- #80 F12 then F9 / F10 / F11 ------------------------------------------------------------------------------------

def _cube_one_edge():
    ob = _cube_top_extruded()
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.context.tool_settings.mesh_select_mode = (False, True, False)
    bpy.context.tool_settings.use_uv_select_sync = True
    bm = bmesh.from_edit_mesh(ob.data)
    bm.edges.ensure_lookup_table()
    bm.edges[0].select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    return ob


def _selected(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    return sum(v.select for v in bm.verts), sum(e.select for e in bm.edges), sum(f.select for f in bm.faces)


def test_f12_then_f9_is_vertex_mode_with_the_old_selection():
    ts = bpy.context.tool_settings
    # one edge selected before F12; F11 then keeps no face, like F11 straight from that selection
    for kind, mode, want in (('VERT', (True, False, False), (2, 1, 0)), ('EDGE', (False, True, False), (2, 1, 0)),
                             ('FACE', (False, False, True), (0, 0, 0))):
        ob = _cube_one_edge()
        assert bpy.ops.allset.uv_component(mode='UV') == {'FINISHED'}      # F12
        bm = bmesh.from_edit_mesh(ob.data)
        assert not ts.use_uv_select_sync and all(f.select for f in bm.faces), "F12: Maya UV mode, every face's UVs"
        assert bpy.ops.allset.component_mode(type=kind) == {'FINISHED'}    # F9 / F10 / F11
        assert ts.use_uv_select_sync, f"{kind}: UV Sync Selection must come back on"
        assert tuple(ts.mesh_select_mode) == mode
        assert _selected(ob) == want, f"{kind}: the selection from before F12 ({_selected(ob)})"


def test_f12_twice_keeps_the_first_selection():
    ob = _cube_one_edge()
    bpy.ops.allset.uv_component(mode='UV')
    bpy.ops.allset.uv_component(mode='SHELL')          # Alt+F12 while already in UV mode: nothing new to keep
    bpy.ops.allset.component_mode(type='VERT')
    assert _selected(ob) == (2, 1, 0)


def test_uv_editor_vertex_button_after_f12_restores_too():
    ob = _cube_one_edge()
    bpy.ops.allset.uv_component(mode='UV')
    assert bpy.ops.allset.uv_component(mode='VERTEX') == {'FINISHED'}    # UV Editor / marking menu Vertex
    assert bpy.context.tool_settings.use_uv_select_sync and _selected(ob) == (2, 1, 0)


def test_component_mode_without_uv_mode_keeps_the_selection():
    ob = _cube_one_edge()
    bpy.ops.allset.component_mode(type='VERT')
    assert bpy.context.tool_settings.use_uv_select_sync and _selected(ob)[0] == 2
