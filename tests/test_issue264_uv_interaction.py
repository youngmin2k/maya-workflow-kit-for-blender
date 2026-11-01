"""UV interaction like Maya: in UV mode the 3D View shows the UV selection (not the mesh selection the kit makes so
every UV shows in the UV Editor)."""
from importlib import import_module

import bmesh
import bpy
import numpy as np

import kit

cc = import_module(kit.MODULE + ".ui.component_colors")
compat = import_module(kit.MODULE + ".compat")


def _cube_in_uv_mode():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.view_layer.objects.active
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')        # the kit's UV mode: every face shown in the UV Editor
    bpy.context.scene.tool_settings.use_uv_select_sync = False
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.active
    for f in bm.faces:
        for lp in f.loops:
            compat.set_uv_vert_selected(lp, uv, False)
    bm.faces.ensure_lookup_table()
    picked = bm.faces[0].loops[0]
    compat.set_uv_vert_selected(picked, uv, True)
    bmesh.update_edit_mesh(ob.data)
    return ob, picked.vert.index


def test_uv_mode_follows_uv_sync():
    _cube_in_uv_mode()
    ts = bpy.context.scene.tool_settings
    assert cc.uv_mode(bpy.context)
    ts.use_uv_select_sync = True
    assert not cc.uv_mode(bpy.context), "UV Sync on = mesh components: the mesh selection shows"
    ts.use_uv_select_sync = False


def test_points_show_the_uv_selection():
    ob, vi = _cube_in_uv_mode()
    bm = bmesh.from_edit_mesh(ob.data)
    sel = cc.uv_selected_verts(bm)
    assert np.flatnonzero(sel).tolist() == [vi], np.flatnonzero(sel)
    st = cc.state(ob, bpy.context.view_layer.depsgraph, faces=False, uv=True)
    assert st is not None and st.uv
    lay = cc.layers(st.arrays, (False, False, True), uv=True)     # face select mode left on: still points only
    assert lay["verts_sel"].tolist() == [vi]
    assert len(lay["verts"]) == 7
    assert "tris" not in lay and "edges_sel" not in lay
    assert len(lay["edges"]) == 12


def test_mesh_selection_shows_with_uv_sync():
    ob, _vi = _cube_in_uv_mode()
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    cc._cache.clear()
    st = cc.state(ob, bpy.context.view_layer.depsgraph, faces=True, uv=False)
    lay = cc.layers(st.arrays, (True, False, False))
    assert len(lay["verts_sel"]) == 8, "every vertex selected in the mesh"
    bpy.context.scene.tool_settings.use_uv_select_sync = False


def test_uv_click_changes_the_signature():
    ob, vi = _cube_in_uv_mode()
    bm = bmesh.from_edit_mesh(ob.data)
    before = cc._selection_signature(bm, True)
    assert cc._selection_signature(bm, False) != before
    uv = bm.loops.layers.uv.active
    bm.faces.ensure_lookup_table()
    lp = bm.faces[1].loops[2]
    compat.set_uv_vert_selected(lp, uv, True)
    assert cc._selection_signature(bm, True) != before, "a UV pick redraws the 3D View"
