"""UV interaction like Maya: in UV mode the 3D View shows the UV selection (not the mesh selection the kit makes so
every UV shows in the UV Editor)."""
from importlib import import_module

import bmesh
import bpy
import numpy as np

import kit

cc = import_module(kit.MODULE + ".ui.component_colors")
compat = import_module(kit.MODULE + ".compat")
uv_tools = import_module(kit.MODULE + ".operators.uv_tools")


def _cube_in_uv_mode():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.view_layer.objects.active
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')        # the kit's UV mode: every face shown in the UV Editor
    uv_tools.set_component(bpy.context, 'UV')         # F12: UV Sync off, every face selected
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


def test_uv_sync_off_alone_is_not_uv_mode():
    """A scene can start with UV Sync Selection off (the Maya layout does): vertex / edge / face editing there still
    shows the mesh selection; only the kit's UV component (F12) shows the UV selection."""
    _cube_in_uv_mode()
    ts = bpy.context.scene.tool_settings
    uv_tools.set_component(bpy.context, 'VERTEX')         # F9 turns UV Sync back on
    ts.use_uv_select_sync = False
    assert not cc.uv_mode(bpy.context), "UV Sync off without F12 = mesh components"
    uv_tools.set_component(bpy.context, 'UV')
    assert cc.uv_mode(bpy.context)
    uv_tools.forget_uv_mode()                           # a file load
    assert not cc.uv_mode(bpy.context)


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


# --- pre-selection of single UVs, edges and faces in the UV Editor -------------------------------------------

pv = import_module(kit.MODULE + ".ui.uv_shell_preview")


def _grid():
    """A 2 x 1 grid in edit mode, UVs: left face u 0..0.4, right face u 0.6..1 (v 0..1)."""
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    me = bpy.data.meshes.new("grid")
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, 0.0)) for y in (0, 1) for x in (0, 1, 2)]
    left = bm.faces.new((vs[0], vs[1], vs[4], vs[3]))
    right = bm.faces.new((vs[1], vs[2], vs[5], vs[4]))
    uv = bm.loops.layers.uv.new("map1")
    for face, u0 in ((left, 0.0), (right, 0.6)):
        for lp in face.loops:
            x, y = lp.vert.co.x - face.verts[0].co.x, lp.vert.co.y
            lp[uv].uv = (u0 + 0.4 * x, y)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("grid", me)
    bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    ts = bpy.context.scene.tool_settings
    ts.use_uv_select_sync = False
    ts.use_uv_select_island = False
    pv._cache.clear()
    return ob


def test_nearest_point_and_segment():
    pts = np.array([[0.0, 0.0], [10.0, 0.0], [30.0, 0.0]])
    assert pv.nearest_point(pts, (9.0, 1.0), 5.0) == 1
    assert pv.nearest_point(pts, (20.0, 0.0), 5.0) is None
    p = np.array([[0.0, 0.0], [0.0, 10.0]])
    q = np.array([[10.0, 0.0], [10.0, 10.0]])
    assert pv.nearest_segment(p, q, (5.0, 2.0), 5.0) == 0
    assert pv.nearest_segment(p, q, (5.0, 9.0), 5.0) == 1
    assert pv.nearest_segment(p, q, (5.0, 5.0), 4.0) is None
    assert pv.nearest_segment(np.array([[1.0, 1.0]]), np.array([[1.0, 1.0]]), (1.0, 2.0), 2.0) == 0, "zero length"


def test_component_mode_follows_the_select_mode():
    _grid()
    ts = bpy.context.scene.tool_settings
    for mode in ('VERTEX', 'EDGE', 'FACE'):
        ts.uv_select_mode = mode
        assert pv.component_mode(bpy.context) == mode
    ts.use_uv_select_island = True
    assert pv.component_mode(bpy.context) is None, "shells: the shell highlight instead"
    ts.use_uv_select_island = False
    ts.use_uv_select_sync = True
    ts.mesh_select_mode = (False, True, False)
    assert pv.component_mode(bpy.context) == 'EDGE', "UV Sync on: the mesh select mode"
    ts.mesh_select_mode = (True, False, False)
    ts.use_uv_select_sync = False


def test_component_under_the_mouse():
    _grid()
    ts = bpy.context.scene.tool_settings
    scale = (500.0, 500.0)                        # 500 px per UV unit
    ts.uv_select_mode = 'VERTEX'
    kind, pt = pv.component_under(bpy.context, 0.41, 0.98, scale, 20.0, 'VERTEX')
    assert kind == 'VERTEX' and np.allclose(pt[0], (0.4, 1.0)), pt
    assert pv.component_under(bpy.context, 0.5, 0.5, scale, 20.0, 'VERTEX') is None, "far from every UV"
    kind, seg = pv.component_under(bpy.context, 0.62, 0.5, scale, 20.0, 'EDGE')
    assert kind == 'EDGE' and np.allclose(seg[0][:, 0], 0.6), seg      # the right face's left edge
    kind, (tris, outline) = pv.component_under(bpy.context, 0.8, 0.5, scale, 20.0, 'FACE')
    assert kind == 'FACE' and tris.shape == (2, 3, 2) and outline.shape == (4, 2, 2)
    assert np.all(tris[..., 0] >= 0.6 - 1e-6), "only the face under the mouse"
    assert pv.component_under(bpy.context, 0.5, 0.5, scale, 20.0, 'FACE') is None


def test_hidden_from_the_uv_editor_is_not_preselected():
    ob = _grid()
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    bm.faces[1].select_set(False)                 # UV Sync off: unselected faces are not drawn in the UV Editor
    bmesh.update_edit_mesh(ob.data)
    pv._cache.clear()
    assert pv.component_under(bpy.context, 0.8, 0.5, (500.0, 500.0), 20.0, 'FACE') is None
