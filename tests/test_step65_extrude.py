"""Maya polyExtrudeFace (Thickness / Local Translate Z / Offset / Divisions / Keep Faces Together), the
last-operation record (INPUTS row, In-View Editor). GUI: tests/gui/gui_step65_extrude.py."""

from importlib import import_module

import bmesh
import bpy
from mathutils import Vector

import kit

ex = import_module(kit.MODULE + ".operators.extrude")
units = import_module(kit.MODULE + ".operators.units")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")
mm = import_module(kit.MODULE + ".marking.menus")
mapping = import_module(kit.MODULE + ".keymap.mapping")

FACE_NORMALS = {"top": Vector((0, 0, 1)), "+x": Vector((1, 0, 0))}   # Blender Z-up


def _points(bm):
    return sorted(tuple(round(c, 4) + 0.0 for c in v.co) for v in bm.verts)


def _bm_cube(faces):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.normal_update()
    picked = [f for f in bm.faces if any((f.normal - FACE_NORMALS[n]).length < 1e-6 for n in faces)]
    return bm, picked


def test_fast_path_equals_rebuild():
    bm, picked = _bm_cube(["top", "+x"])
    _caps, moved = ex.extrude(bm, picked, divisions=3)
    ex.place(moved, 0.3, 0.2, 0.05)
    fast = _points(bm)
    bm.free()
    bm, picked = _bm_cube(["top", "+x"])
    ex.extrude(bm, picked, thickness=0.3, local_translate_z=0.2, offset=0.05, divisions=3)
    assert _points(bm) == fast
    bm.free()


def test_isolated_plane_has_no_bottom():
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=2, y_segments=2, size=1.0)
    caps, _m = ex.extrude(bm, list(bm.faces), local_translate_z=1.0)
    assert len(caps) == 4 and len(bm.faces) == 4 + 8, len(bm.faces)
    bm.free()


# --- operators and the record ---------------------------------------------------------------------

def _cube_top_selected():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.context.scene.pop(ex.COUNTER, None)
    bpy.ops.mesh.primitive_cube_add(size=1)
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    bm = bmesh.from_edit_mesh(ob.data)
    for f in bm.faces:
        f.select_set(False)
    for f in bm.faces:   # deselect first: a later face's select_set(False) would drop shared verts
        if f.normal.z > 0.9:
            f.select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    return ob


def _counts(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    return len(bm.verts), len(bm.faces)


def _top_z(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    return max(v.co.z for v in bm.verts)


def test_extrude_operator_and_node_name():
    ob = _cube_top_selected()
    assert bpy.ops.allset.extrude() == {'FINISHED'}
    assert _counts(ob) == (12, 10)
    o, rec = ex.active(bpy.context)
    assert o is ob and rec.name == "polyExtrudeFace1" and rec.params == ex.DEFAULTS, rec and rec.params
    assert ex.caps_selected(ob, rec)
    # a second extrusion is a new node
    assert bpy.ops.allset.extrude(local_translate_z=0.5) == {'FINISHED'}
    _o, rec = ex.active(bpy.context)
    assert rec.name == "polyExtrudeFace2" and abs(_top_z(ob) - 1.0) < 1e-6
    # no faces selected: nothing for the face extrusion (Ctrl+E then drags edges / vertices)
    bm = bmesh.from_edit_mesh(ob.data)
    for f in bm.faces:
        f.select_set(False)
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.extrude() == {'CANCELLED'}


def test_maya_units_in_cm_scene():
    ob = _cube_top_selected()
    us = bpy.context.scene.unit_settings
    old = (us.system, us.length_unit, us.scale_length)
    us.system, us.length_unit, us.scale_length = 'METRIC', 'CENTIMETERS', 1.0
    try:
        unit = units.maya_unit(bpy.context.scene)
        assert bpy.ops.allset.extrude(local_translate_z=0.5) == {'FINISHED'}
        assert abs(_top_z(ob) - (0.5 + 0.5 * unit)) < 1e-6, (_top_z(ob), unit)
    finally:
        us.system, us.length_unit, us.scale_length = old


def test_edit_last_extrusion_and_states():
    ob = _cube_top_selected()
    bpy.ops.allset.extrude()
    assert ex.set_params(bpy.context, local_translate_z=0.5) == {'FINISHED'}
    assert abs(_top_z(ob) - 1.0) < 1e-6 and _counts(ob) == (12, 10)
    assert ex.set_params(bpy.context, divisions=2) == {'FINISHED'}
    assert _counts(ob) == (16, 14) and abs(_top_z(ob) - 1.0) < 1e-6, "modeling_04: Local Translate Z 0.5, Divisions 2"
    _o, rec = ex.active(bpy.context)
    assert rec.name == "polyExtrudeFace1" and rec.params["divisions"] == 2
    # back to an earlier state (what Ctrl+Z does): the record follows with that state's values
    ex.run(ob, rec, dict(ex.DEFAULTS, local_translate_z=0.5), 1.0)
    rec.states.pop()               # pretend this state came back from the undo stack
    _o, rec = ex.active(bpy.context)
    assert rec is not None and rec.params["divisions"] == 1 and rec.params["local_translate_z"] == 0.5
    # any other edit: no longer the kit's extrusion
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    bm.verts[rec.cap_verts[0]].co.z += 0.3
    bmesh.update_edit_mesh(ob.data)
    assert ex.active(bpy.context) == (None, None)
    assert bpy.ops.allset.extrude_edit(divisions=3) == {'CANCELLED'}


def test_preview_then_edit_is_one_result():
    ob = _cube_top_selected()
    bpy.ops.allset.extrude()
    o, rec = ex.active(bpy.context)
    unit = units.maya_unit(bpy.context.scene)
    ex.preview(ob, rec, dict(rec.params, thickness=0.25), unit)
    assert abs(_top_z(ob) - 0.75) < 1e-6 and rec.live
    assert ex.set_params(bpy.context, thickness=0.25) == {'FINISHED'}
    _o, rec = ex.active(bpy.context)
    assert not rec.live and abs(_top_z(ob) - 0.75) < 1e-6 and _counts(ob) == (12, 10)


def test_redo_keeps_node_name():
    """Adjust Last Operation re-runs allset.extrude on the mesh before it: same polyExtrudeFace1."""
    ob = _cube_top_selected()
    bpy.ops.allset.extrude()
    _o, rec = ex.active(bpy.context)
    bm = bmesh.from_edit_mesh(ob.data)
    ex.restore_pre(bm, rec)
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.extrude(thickness=0.2) == {'FINISHED'}
    _o, rec = ex.active(bpy.context)
    assert rec.name == "polyExtrudeFace1" and bpy.context.scene[ex.COUNTER] == 1


def test_bindings_and_menus():
    action = ("v3d", "allset.extrude", {})
    km = kit.maya_kc().keymaps["Mesh"]
    ce = [k.idname for k in km.keymap_items if k.type == 'E' and k.ctrl and not k.shift and not k.alt and k.active]
    assert ce == ["allset.extrude"], ce
    assert menu_map.MAP["Edit Mesh/Extrude"] == action
    assert shelf_map.BY_COMMAND["PolyExtrude"][0] == action
    radial = mm.SHIFT_FACE.radial["S"]
    assert radial == ("Extrude Face", action), radial
    assert mapping.ENTRIES["PolyExtrude"]["check"][1] == "allset.extrude"


# --- Channel Box INPUTS, In-View Editor --------------------------------------------------------------

in_view = import_module(kit.MODULE + ".ui.in_view")


def test_channel_box_rows_edit_the_last_extrusion():
    """modeling_04: INPUTS > polyExtrudeFace1 > Local Translate Z 0.5, Divisions 2."""
    ob = _cube_top_selected()
    bpy.ops.allset.extrude()
    hist = bpy.context.window_manager.allset_history
    assert in_view.cb_record(bpy.context, ob).name == "polyExtrudeFace1"
    assert hist.local_translate_z_text == "0" and hist.divisions_text == "1" and hist.keep_faces_together_text == "on"
    hist.local_translate_z_text = "0.5"
    assert abs(_top_z(ob) - 1.0) < 1e-6 and hist.local_translate_z_text == "0.5"
    hist.local_translate_z_text = "+=0.25"
    assert abs(_top_z(ob) - 1.25) < 1e-6, "Maya relative entry"
    hist.divisions_text = "2"
    assert _counts(ob) == (16, 14) and hist.divisions_text == "2"
    hist.thickness_text = "nonsense"
    assert hist.thickness_text == "0", "unreadable text changes nothing"
    # object mode: Maya keeps listing the node (#204) while the mesh is its result; another edit hides it
    bpy.ops.object.mode_set(mode='OBJECT')
    assert in_view.cb_record(bpy.context, ob).name == "polyExtrudeFace1" and hist.divisions_text == "2"
    ob.data.vertices[0].co.x += 0.25
    assert in_view.cb_record(bpy.context, ob) is None and hist.divisions_text == ""


def test_in_view_layout():
    class R:
        width, height = 800, 600
    lay = in_view.layout(R, (300, 300), 1.0)
    rows = lay["rows"]
    assert [r[0] for r in rows] == list(ex.FIELDS)
    x0, y0, x1, y1 = lay["box"]
    assert (x1 - x0, y1 - y0) == (in_view.WIDTH, in_view.ROW_H * 6)
    assert x0 == 300 + in_view.GAP[0] and rows[0][4] == lay["title"][1]
    # kept inside the region near its edges
    lay = in_view.layout(R, (790, 5), 2.0)
    x0, y0, x1, y1 = lay["box"]
    assert x1 <= R.width and y0 >= 0, lay["box"]
    assert in_view.value_text(ex.Record("n", None, ex.DEFAULTS), "keep_faces_together") == "On"


def test_ui_registered():
    assert bpy.ops.allset.inview_drag.get_rna_type() is not None
    assert bpy.ops.allset.extrude_drag.get_rna_type() is not None
    assert bpy.ops.allset.inview_type.get_rna_type() is not None
    assert in_view._state["handle"] is not None
    assert not in_view.manip_visible(bpy.context), "no 3D View in the background"
