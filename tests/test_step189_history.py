"""Maya's Status Line Construction History toggle.

Maya: with the toggle off Maya's menu commands run
with -ch 0 — CreatePolygonCube / CreateNURBSSphere / CreateNURBSCircle leave no polyCube1 / makeNurb* node,
PolyExtrude / BevelPolygon no polyExtrudeFace / polyBevel node; history made before stays (the kit keeps one node per object: the mesh then no longer matches it); File > New keeps the state.
"""

from importlib import import_module

import bmesh
import bpy

import kit

ex = import_module(kit.MODULE + ".operators.extrude")
prim_history = import_module(kit.MODULE + ".operators.prim_history")
panel_menu_data = import_module(kit.MODULE + ".ui.panel_menu_data")
notices = import_module(kit.MODULE + ".ui.notices")


def _fresh():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    ex.RECORDS.clear()


def _set(on):
    bpy.context.window_manager.allset_construction_history = on


def _top_face_selected(ob):
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
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


def test_default_on():
    assert bpy.context.window_manager.allset_construction_history is True


def test_off_primitives_have_no_node():
    _fresh()
    _set(False)
    try:
        for kind in ('CUBE', 'NURBS_SPHERE', 'NURBS_CIRCLE'):
            assert bpy.ops.allset.create(kind=kind) == {'FINISHED'}, kind
            ob = bpy.context.view_layer.objects.active
            assert prim_history.node_of(ob)[1] is None, kind
        assert bpy.context.view_layer.objects.active.name == "nurbsCircle1"
    finally:
        _set(True)
    assert bpy.ops.allset.create(kind='CUBE') == {'FINISHED'}
    assert prim_history.node_of(bpy.context.view_layer.objects.active)[1] is not None


def test_off_extrude_keeps_no_record_and_old_history_stays():
    _fresh()
    assert bpy.ops.allset.create(kind='CUBE') == {'FINISHED'}
    ob = bpy.context.view_layer.objects.active
    _top_face_selected(ob)
    assert bpy.ops.allset.extrude() == {'FINISHED'}
    assert ex.RECORDS.get(ob.name) is not None
    bpy.ops.object.mode_set(mode='OBJECT')
    _set(False)
    try:
        _top_face_selected(ob)
        n = len(ob.data.polygons)
        assert bpy.ops.allset.extrude() == {'FINISHED'}
        bm = bmesh.from_edit_mesh(ob.data)
        assert len(bm.faces) == n + 4, (len(bm.faces), n)        # the extrusion itself still happens
        assert ex.RECORDS.get(ob.name) is None
        bpy.ops.object.mode_set(mode='OBJECT')
    finally:
        _set(True)


def test_toggle_operator_and_status_line_not_greyed():
    _set(True)
    assert bpy.ops.allset.construction_history() == {'FINISHED'}
    assert bpy.context.window_manager.allset_construction_history is False
    assert bpy.ops.allset.construction_history() == {'FINISHED'}
    assert bpy.context.window_manager.allset_construction_history is True
    assert "Status Line/Construction History" not in panel_menu_data.STATUS_LINE
    assert not notices.greyed_notice("Status Line/Construction History")
