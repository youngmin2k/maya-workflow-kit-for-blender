"""Step 74: pre-selection highlight for vertices, edges and faces, also with the transform tools.
Plan: docs/steps/step_74.md; GUI: tests/gui/gui_step74_preselect.py."""

from importlib import import_module

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

import kit

pre = import_module(kit.MODULE + ".operators.preselect")
preferences = import_module(kit.MODULE + ".preferences")


def _cube():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.mesh.primitive_cube_add()
    return bpy.context.active_object


def test_project():
    xy, front = pre.project([(0, 0, 0), (1, 1, 0), (0, 0, 5)], Matrix.Identity(4), 200, 100)
    assert xy.tolist()[:2] == [[100.0, 50.0], [200.0, 100.0]] and front.all()
    persp = Matrix(((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, -1, 0)))   # w = -z
    _xy, front = pre.project([(0, 0, -2), (0, 0, 2)], persp, 10, 10)
    assert front.tolist() == [True, False]


def test_pick_vert_nearest_visible_within_radius():
    xy = np.array([[10.0, 10.0], [14.0, 10.0], [40.0, 40.0]])
    ok = np.array([True, True, True])
    assert pre.pick_vert(xy, ok, (13.0, 10.0), 16, lambda i: True) == 1
    assert pre.pick_vert(xy, ok, (13.0, 10.0), 16, lambda i: i != 1) == 0      # 1 hidden behind a face
    assert pre.pick_vert(xy, ok, (100.0, 100.0), 16, lambda i: True) is None   # nothing within the radius
    assert pre.pick_vert(xy, np.array([True, False, True]), (13.0, 10.0), 16, lambda i: True) == 0


def test_pick_edge_follows_edge_mode_near_a_vertex():
    # a square's 4 edges; the mouse right next to corner (0, 0) still picks an edge (Maya pre_04)
    xy = np.array([[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]])
    edges = [(0, 1), (1, 2), (2, 3), (3, 0)]
    ok = np.array([True] * 4)
    assert pre.pick_edge(xy, edges, ok, (50.0, 3.0), 16, lambda i, t: True) == 0
    assert pre.pick_edge(xy, edges, ok, (4.0, 1.0), 16, lambda i, t: True) == 0
    assert pre.pick_edge(xy, edges, ok, (97.0, 50.0), 16, lambda i, t: True) == 1
    # mouse inside the face, far from every edge: the nearest edge of the face under it
    assert pre.pick_edge(xy, edges, ok, (50.0, 30.0), 16, lambda i, t: True, fallback=(0, 1, 2, 3)) == 0
    assert pre.pick_edge(xy, edges, ok, (50.0, 30.0), 16, lambda i, t: True) is None
    # the parameter t reaches the visibility test
    seen = []
    pre.pick_edge(xy, edges, ok, (25.0, 2.0), 16, lambda i, t: seen.append((i, round(t, 2))) or True)
    assert seen == [(0, 0.25)]


def test_near_handles():
    tips = [(200.0, 100.0), (100.0, 200.0)]
    assert pre.near_handles((150.0, 105.0), (100.0, 100.0), tips, 9, 12)      # on the X arrow
    assert pre.near_handles((104.0, 96.0), (100.0, 100.0), tips, 9, 12)       # centre square
    assert not pre.near_handles((160.0, 160.0), (100.0, 100.0), tips, 9, 12)  # between the arrows
    assert not pre.near_handles((0.0, 0.0), None, tips, 9, 12)


def test_mesh_cache_world_and_hidden():
    ob = _cube()
    ob.location = (5, 0, 0)
    bpy.context.view_layer.update()
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    bm.faces[0].hide_set(True)
    bmesh.update_edit_mesh(ob.data)
    c = pre.MeshCache(ob)
    assert c.co.shape == (8, 3) and abs(c.co[:, 0].mean() - 5.0) < 1e-6
    assert len(c.edges) == 12 and len(c.bm.faces) == 6 and len(c.face_verts(1)) == 4
    assert c.face_ok(0) is False and 0 not in c.bvh_map and len(c.bvh_map) == 5
    # a ray from +X hits the x = 6 face first
    hit = c.ray(Vector((20, 0.1, 0.1)), Vector((-1, 0, 0)))
    assert hit is not None and abs(hit[0] - 14.0) < 1e-5
    bpy.ops.object.mode_set(mode='OBJECT')


def test_poll_modes_and_tools():
    ob = _cube()
    assert pre._enabled(bpy.context) is False, "object mode: Maya 2022 has no object pre-selection"
    bpy.ops.object.mode_set(mode='EDIT')
    orig = pre.tool_id
    try:
        for tid, want in (("builtin.select_box", True), ("builtin.select_lasso", True), ("builtin.move", True),
                          ("builtin.rotate", True), ("builtin.scale", True), ("builtin.knife", False),
                          ("builtin.extrude_region", False), ("allset.target_weld_tool", True)):
            pre.tool_id = lambda _c, t=tid: t
            for mode in ('VERT', 'EDGE', 'FACE'):
                bpy.ops.mesh.select_mode(type=mode)
                assert pre._enabled(bpy.context) is want, (tid, mode)
        pre.tool_id = lambda _c: "builtin.select_box"
        preferences.get().preselect_highlight = False
        assert pre._enabled(bpy.context) is False
    finally:
        preferences.get().preselect_highlight = True
        pre.tool_id = orig
        bpy.ops.object.mode_set(mode='OBJECT')
    del ob


class _Update:
    def __init__(self, idd, geometry=False, transform=False):
        self.id, self.is_updated_geometry, self.is_updated_transform = idd, geometry, transform


class _Depsgraph:
    def __init__(self, *updates):
        self.updates = updates


def test_cache_kept_on_selection_dropped_on_geometry():
    ob = _cube()
    bpy.ops.object.mode_set(mode='EDIT')
    c = pre._cache[1] = pre.MeshCache(ob)
    assert c.selection()[0]                          # primitive_cube_add leaves all selected
    pre.invalidate(None, _Depsgraph(_Update(ob.data)))           # selection only
    assert pre._cache.get(1) is c and c._sel is None
    pre.invalidate(None, _Depsgraph(_Update(ob.data, geometry=True)))
    assert not pre._cache
    pre._cache[1] = c
    pre.invalidate()                                 # no depsgraph: drop everything
    assert not pre._cache
    assert pre.invalidate in bpy.app.handlers.depsgraph_update_post
    bpy.ops.object.mode_set(mode='OBJECT')


def test_coordinate_modal_retains_topology_refreshes_bvh_and_resets_on_transform():
    import bmesh
    ob=_cube();bpy.ops.object.mode_set(mode='EDIT')
    c=pre._cache[ob.as_pointer()]=pre.MeshCache(ob)
    old_bvh=c.bvh;edges=c.edges
    bm=bmesh.from_edit_mesh(ob.data);bm.verts.ensure_lookup_table()
    v=bm.verts[0];v.co.z+=.3
    pre.coordinates_changed(ob,[v])
    pre.invalidate(None,_Depsgraph(_Update(ob.data,geometry=True)))
    assert pre._cache[ob.as_pointer()] is c and c.edges is edges
    assert abs(c.co[0,2]-(ob.matrix_world@v.co).z)<1e-7
    assert c.revision==1 and c._bvh_dirty
    assert c.bvh is not old_bvh and not c._bvh_dirty
    pre.invalidate(None,_Depsgraph(_Update(ob,transform=True)))
    assert not pre._cache and pre._coordinate_session is None
    bpy.ops.object.mode_set(mode='OBJECT')


def test_bulk_edit_cache_matches_bmesh_with_hidden_and_loose_geometry():
    import bmesh
    import numpy as np
    if bpy.context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
    me=bpy.data.meshes.new('bulk_cache');ob=bpy.data.objects.new('bulk_cache',me)
    bpy.context.scene.collection.objects.link(ob)
    source=bmesh.new();bmesh.ops.create_grid(source,x_segments=64,y_segments=32,size=2)
    a=source.verts.new((10,0,0));b=source.verts.new((11,0,0));source.edges.new((a,b))
    source.to_mesh(me);source.free();ob.select_set(True);bpy.context.view_layer.objects.active=ob
    bpy.ops.object.mode_set(mode='EDIT');bm=bmesh.from_edit_mesh(me)
    bm.verts.ensure_lookup_table();bm.edges.ensure_lookup_table();bm.faces.ensure_lookup_table()
    bm.verts[0].hide=True;bm.edges[0].hide=True;bm.faces[0].hide=True
    count=len(bpy.data.meshes)
    c=pre.MeshCache(ob)
    assert c.arrays is not None and len(bpy.data.meshes)==count
    assert np.allclose(c.co,[ob.matrix_world@v.co for v in bm.verts])
    assert c.vok.tolist()==[not v.hide for v in bm.verts]
    assert c.eok.tolist()==[not e.hide for e in bm.edges]
    assert c.arrays[4].tolist()==[len(e.link_faces) for e in bm.edges]
    assert c.arrays[5].tolist()==[v.is_boundary or not v.link_faces for v in bm.verts]
    assert c.arrays[6].tolist()==[not f.hide for f in bm.faces]
    assert all(tuple(ring)==tuple(v.index for v in bm.faces[i].verts) for ids,rings in c.arrays[7] for i,ring in zip(ids,rings))
    bpy.ops.object.mode_set(mode='OBJECT');pre.invalidate()
