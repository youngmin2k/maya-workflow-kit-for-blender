"""Edit Mesh > Connect / Merge / Symmetrize and Mesh > Smooth against the expected numbers.
Maya Y-up -> Blender Z-up: Maya (x, y, z) = Blender (x, -z, y).
"""

from importlib import import_module

import bmesh
import bpy
from mathutils import Vector

import kit

poly = import_module(kit.MODULE + ".operators.poly_maya")
option_windows = import_module(kit.MODULE + ".operators.option_windows")
menu_map = import_module(kit.MODULE + ".ui.menu_map")


def B(x, y, z):
    """Maya world position -> Blender."""
    return Vector((x, -z, y))


def _cube():
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    _lookup(bm)
    return bm


def _lookup(bm):
    for seq in (bm.verts, bm.edges, bm.faces):
        seq.ensure_lookup_table()


def _counts(bm):
    return (len(bm.verts), len(bm.edges), len(bm.faces))


def _vert(bm, p):
    return next(v for v in bm.verts if (v.co - p).length < 1e-4)


def _edge(bm, p, q):
    a, b = _vert(bm, p), _vert(bm, q)
    return next(e for e in a.link_edges if e.other_vert(a) is b)


def _face(bm, normal):
    return next(f for f in bm.faces if (f.normal - normal).length < 1e-4)


def _has(bm, p, tol=1e-3):
    return any((v.co - p).length < tol for v in bm.verts)


TOP, FRONT, BOTTOM, RIGHT = B(0, 1, 0), B(0, 0, 1), B(0, -1, 0), B(1, 0, 0)
# Maya polyCube top face corners (y = 0.5), in its loop order 2, 3, 5, 4
T2, T3, T5, T4 = B(-.5, .5, .5), B(.5, .5, .5), B(.5, .5, -.5), B(-.5, .5, -.5)


# --- Connect -----------------------------------------------------------------------------------

def _connect(select, mode, bm=None):
    bm = bm or _cube()
    for el in select(bm):
        el.select = True
    poly.connect(bm, mode)
    out = (_counts(bm), sorted(len(f.verts) for f in bm.faces))
    return bm, out


def test_connect_edges_like_maya():
    # Maya: opposite 10/15/7, adjacent 10/15/7 (a corner triangle), three edges of a face 11/18/9, the edge ring around
    # the cube 12/20/10, one edge alone 8/12/6 (nothing)
    bm, (c, sizes) = _connect(lambda b: [_edge(b, T2, T3), _edge(b, T5, T4)], 'EDGE')
    assert c == (10, 15, 7) and sizes == [4, 4, 4, 4, 4, 5, 5], (c, sizes)
    assert _has(bm, B(0, .5, .5)) and _has(bm, B(0, .5, -.5))
    bm, (c, sizes) = _connect(lambda b: [_edge(b, T2, T3), _edge(b, T3, T5)], 'EDGE')
    assert c == (10, 15, 7) and sizes == [3, 4, 4, 4, 5, 5, 5], (c, sizes)
    assert _has(bm, B(0, .5, .5)) and _has(bm, B(.5, .5, 0))
    bm, (c, sizes) = _connect(lambda b: [_edge(b, T2, T3), _edge(b, T3, T5), _edge(b, T5, T4)], 'EDGE')
    assert c == (11, 18, 9) and sizes == [3, 3, 3, 4, 4, 4, 5, 5, 5], (c, sizes)
    bm, (c, sizes) = _connect(lambda b: [e for e in b.edges if abs(e.verts[0].co.x - e.verts[1].co.x) > .5], 'EDGE')
    assert c == (12, 20, 10) and sizes == [4] * 10, (c, sizes)
    bm, (c, sizes) = _connect(lambda b: [_edge(b, T2, T3)], 'EDGE')
    assert c == (8, 12, 6), c


def test_connect_vertices_like_maya():
    # Maya: two diagonal vertices of a face 8/13/7, two vertices of one edge 8/12/6, three vertices of a face 8/13/7
    # (only the diagonal is a chord), two vertices that share no face 8/12/6
    _bm, (c, sizes) = _connect(lambda b: [_vert(b, T2), _vert(b, T5)], 'VERT')
    assert c == (8, 13, 7) and sizes == [3, 3, 4, 4, 4, 4, 4], (c, sizes)
    _bm, (c, _s) = _connect(lambda b: [_vert(b, T2), _vert(b, T3)], 'VERT')
    assert c == (8, 12, 6), c
    _bm, (c, _s) = _connect(lambda b: [_vert(b, T2), _vert(b, T3), _vert(b, T5)], 'VERT')
    assert c == (8, 13, 7), c
    _bm, (c, _s) = _connect(lambda b: [_vert(b, B(-.5, -.5, .5)), _vert(b, B(.5, .5, -.5))], 'VERT')
    assert c == (8, 12, 6), c


def _grid3():
    """Maya polyPlane -sx 3 -sy 3 (w = h = 1): 16 / 24 / 9, faces row by row from Maya z = +1/3 ... in Blender -y."""
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=3, y_segments=3, size=0.5)
    _lookup(bm)
    return bm


def _grid_face(bm, mx, mz):
    """The face whose centre is Maya (mx, 0, mz)."""
    p = B(mx, 0, mz)
    return min(bm.faces, key=lambda f: (f.calc_center_median() - p).length)


def test_connect_faces_like_maya():
    # Maya: one face 8/12/6; top + front 9/13/6 (only the shared edge's midpoint); top + front + bottom 12/19/9 (a
    # line through the strip, the end faces cut to their far edges); the 4-face ring 12/20/10; three faces at a corner
    # 11/18/9. polyPlane 3 x 3: a row of 3 -> 20/31/12, 2 x 2 -> 20/32/13, an L of 3 -> 20/31/12, two -> 17/25/9
    _bm, (c, _s) = _connect(lambda b: [_face(b, TOP)], 'FACE')
    assert c == (8, 12, 6), c
    bm, (c, _s) = _connect(lambda b: [_face(b, TOP), _face(b, FRONT)], 'FACE')
    assert c == (9, 13, 6) and _has(bm, B(0, .5, .5)), c
    bm, (c, _s) = _connect(lambda b: [_face(b, TOP), _face(b, FRONT), _face(b, BOTTOM)], 'FACE')
    assert c == (12, 19, 9), c
    for p in (B(0, .5, -.5), B(0, .5, .5), B(0, -.5, .5), B(0, -.5, -.5)):
        assert _has(bm, p), p
    _bm, (c, _s) = _connect(lambda b: [_face(b, n) for n in (TOP, FRONT, BOTTOM, B(0, 0, -1))], 'FACE')
    assert c == (12, 20, 10), c
    _bm, (c, _s) = _connect(lambda b: [_face(b, TOP), _face(b, FRONT), _face(b, RIGHT)], 'FACE')
    assert c == (11, 18, 9), c
    t = 1.0 / 3.0
    cases = {"row": ([(-t, 0), (0, 0), (t, 0)], (20, 31, 12)), "2x2": ([(-t, t), (0, t), (-t, 0), (0, 0)], (20, 32, 13)),
             "L": ([(-t, t), (0, t), (0, 0)], (20, 31, 12)), "two": ([(-t, 0), (0, 0)], (17, 25, 9))}
    for name, (cells, want) in cases.items():
        bm, (c, _s) = _connect(lambda b, cells=cells: [_grid_face(b, x, z) for x, z in cells], 'FACE', _grid3())
        assert c == want, (name, c, want)
    bm, _ = _connect(lambda b: [_grid_face(b, x, z) for x, z in cases["row"][0]], 'FACE', _grid3())
    for p in (B(-.5, 0, 0), B(-1 / 6, 0, 0), B(1 / 6, 0, 0), B(.5, 0, 0)):
        assert _has(bm, p), p


# --- Merge ---------------------------------------------------------------------------------------

V0, V1, V2 = B(-.5, -.5, .5), B(.5, -.5, .5), B(-.5, .5, .5)      # Maya pCube1.vtx[0], [1], [2]


def _merge(select, setup=None, always_two=True, mode='VERT'):
    bm = _cube()
    if setup:
        setup(bm)
    for v in select(bm):
        v.select = True
    poly.merge_selection(bm, mode, poly.MERGE_THRESHOLD, always_two)
    _lookup(bm)
    return bm


def test_merge_like_maya():
    # two neighbours (distance 1): 7/11/6 at the midpoint (0, -0.5, 0.5)
    bm = _merge(lambda b: [_vert(b, V0), _vert(b, V1)])
    assert _counts(bm) == (7, 11, 6) and _has(bm, B(0, -.5, .5)), _counts(bm)
    # two vertices sharing no face: 7/12/6 at (0, 0, 0); a face diagonal: 7/10/5 at (0, 0.5, 0)
    bm = _merge(lambda b: [_vert(b, B(-.5, -.5, .5)), _vert(b, B(.5, .5, -.5))])
    assert _counts(bm) == (7, 12, 6) and _has(bm, B(0, 0, 0)), _counts(bm)
    bm = _merge(lambda b: [_vert(b, B(-.5, .5, .5)), _vert(b, B(.5, .5, -.5))])
    assert _counts(bm) == (7, 10, 5) and _has(bm, B(0, .5, 0)), _counts(bm)
    # three far vertices: nothing; Always merge off with two far vertices: nothing
    bm = _merge(lambda b: [_vert(b, V0), _vert(b, V1), _vert(b, V2)])
    assert _counts(bm) == (8, 12, 6)
    bm = _merge(lambda b: [_vert(b, V0), _vert(b, V1)], always_two=False)
    assert _counts(bm) == (8, 12, 6)

    def near(b):
        _vert(b, V1).co = B(-.495, -.5, .5)
    # three selected, one pair 0.005 apart: that pair -> its midpoint (-0.4975, -0.5, 0.5), 7/11/6
    bm = _merge(lambda b: [_vert(b, V0), _vert(b, B(-.495, -.5, .5)), _vert(b, V2)], near)
    assert _counts(bm) == (7, 11, 6) and _has(bm, B(-.4975, -.5, .5), 1e-4), _counts(bm)

    def cluster(b):
        _vert(b, V1).co = B(-.495, -.5, .5)
        _vert(b, V2).co = B(-.5, -.497, .5)
    # three within the threshold: one vertex at their mean (-0.4983, -0.499, 0.5), 6/9/5
    bm = _merge(lambda b: [_vert(b, V0), _vert(b, B(-.495, -.5, .5)), _vert(b, B(-.5, -.497, .5))], cluster)
    assert _counts(bm) == (6, 9, 5) and _has(bm, B(-.49833, -.499, .5), 1e-4), _counts(bm)

    def moved(b):
        _vert(b, V1).co = B(.9, -.2, .3)
    # unequal pair: the mean (0.2, -0.35, 0.4)
    bm = _merge(lambda b: [_vert(b, V0), _vert(b, B(.9, -.2, .3))], moved)
    assert _counts(bm) == (7, 11, 6) and _has(bm, B(.2, -.35, .4), 1e-4)
    # an edge of a closed cube (Maya: polySewEdge, nothing): unchanged
    bm = _cube()
    _edge(bm, V0, V1).select = True
    poly.merge_selection(bm, 'EDGE', poly.MERGE_THRESHOLD)
    assert _counts(bm) == (8, 12, 6)


# --- Smooth --------------------------------------------------------------------------------------

def _positions(bm):
    return sorted(tuple(round(c, 4) for c in v.co) for v in bm.verts)


def test_smooth_whole_cube_like_maya():
    # Maya: 26/48/24, corners +-0.2778, edge points (+-0.375, +-0.375, 0), face points +-0.5 on an axis
    bm = _cube()
    poly.smooth(bm, list(bm.faces))
    assert _counts(bm) == (26, 48, 24), _counts(bm)
    want = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                want.append((sx * .2778, sy * .2778, sz * .2778))
    for a in range(3):
        for s1 in (-1, 1):
            for s2 in (-1, 1):
                p = [0.0, 0.0, 0.0]
                others = [i for i in range(3) if i != a]
                p[others[0]], p[others[1]] = s1 * .375, s2 * .375
                want.append(tuple(p))
        for s in (-1, 1):
            p = [0.0, 0.0, 0.0]
            p[a] = s * .5
            want.append(tuple(p))
    assert _positions(bm) == sorted(tuple(round(c, 4) + 0.0 for c in p) for p in want), _positions(bm)
    assert all(len(f.verts) == 4 for f in bm.faces)


def test_smooth_selected_faces_like_maya():
    # one face: 13/20/9, every old vertex stays, new ones at the face centre and edge midpoints (selection border kept)
    bm = _cube()
    old = _positions(bm)
    poly.smooth(bm, [_face(bm, TOP)])
    assert _counts(bm) == (13, 20, 9), _counts(bm)
    assert sorted(len(f.verts) for f in bm.faces) == [4, 4, 4, 4, 4, 5, 5, 5, 5]
    for p in [Vector(c) for c in old] + [B(0, .5, 0), B(0, .5, .5), B(.5, .5, 0), B(0, .5, -.5), B(-.5, .5, 0)]:
        assert _has(bm, p, 1e-4), p
    # top + front: 17/27/12, the shared edge gets the Catmull-Clark edge point (0, 0.375, 0.375)
    bm = _cube()
    poly.smooth(bm, [_face(bm, TOP), _face(bm, FRONT)])
    assert _counts(bm) == (17, 27, 12) and _has(bm, B(0, .375, .375), 1e-4), _counts(bm)
    assert sorted(len(f.verts) for f in bm.faces) == [4] * 8 + [5, 5, 6, 6]
    # the faces around vertex 0 (Maya smooths a vertex selection's faces): 20/33/15, vertex 0 -> -0.2778
    bm = _cube()
    v0 = _vert(bm, V0)
    poly.smooth(bm, list(v0.link_faces))
    assert _counts(bm) == (20, 33, 15) and _has(bm, B(-.2778, -.2778, .2778), 1e-4), _counts(bm)


def test_smooth_open_plane_like_maya():
    # polyPlane -sx 2 -sy 2 -w 2 -h 2, centre vertex up 0.5: 25/40/16, centre -> 0.28125, inner edge points 0.1875,
    # face points 0.125, the border stays flat
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=2, y_segments=2, size=1.0)
    _lookup(bm)
    centre = min(bm.verts, key=lambda v: v.co.length)
    centre.co.z = 0.5
    poly.smooth(bm, list(bm.faces))
    assert _counts(bm) == (25, 40, 16), _counts(bm)
    zs = sorted(v.co.z for v in bm.verts)
    want = [0.0] * 16 + [0.125] * 4 + [0.1875] * 4 + [0.28125]
    assert all(abs(a - b) < 1e-5 for a, b in zip(zs, want)), zs


# --- Symmetrize ----------------------------------------------------------------------------------

def _sym_cube():
    """Maya polyCube -sx 2 with every +X vertex moved out 0.3 (the top ones also up 0.2)."""
    bm = _cube()
    for e in bm.edges:
        e.select = abs(e.verts[0].co.x - e.verts[1].co.x) > .5
    poly.connect(bm, 'EDGE')
    for el in (*bm.verts, *bm.edges, *bm.faces):
        el.select = False
    for v in bm.verts:
        if v.co.x > .4:
            v.co.x += .3
            if v.co.z > 0:
                v.co.z += .2
    _lookup(bm)
    seam = next(e for e in bm.edges if all(abs(v.co.x) < 1e-6 and v.co.z > .4 for v in e.verts))
    return bm, seam


def _sides(bm):
    minus = sorted(tuple(round(c, 4) for c in v.co) for v in bm.verts if v.co.x < -.1)
    plus = sorted(tuple(round(c, 4) for c in v.co) for v in bm.verts if v.co.x > .1)
    return minus, plus


UNIT = sorted((x, y, z) for x in (.5,) for y in (-.5, .5) for z in (-.5, .5))


def test_symmetrize_like_maya():
    # selected side drives, counterparts take the mirrored position about the seam (x = 0)
    bm, seam = _sym_cube()
    poly.symmetrize(bm, seam, [v for v in bm.verts if v.co.x < -.1])        # Maya topo_minus: +X back to 0.5
    minus, plus = _sides(bm)
    assert plus == UNIT and minus == sorted((-x, y, z) for x, y, z in UNIT), (minus, plus)
    bm, seam = _sym_cube()
    poly.symmetrize(bm, seam, [v for v in bm.verts if v.co.x > .1])         # Maya topo_plus: -X -> -0.8, top 0.7
    minus, plus = _sides(bm)
    assert minus == sorted((-x, y, z) for x, y, z in plus) and (-.8, -.5, .7) in minus, (minus, plus)
    bm, seam = _sym_cube()
    poly.symmetrize(bm, seam, list(bm.verts))                               # Maya topo_all: the -X side drove
    minus, plus = _sides(bm)
    assert plus == UNIT, plus
    bm, seam = _sym_cube()
    one = _vert(bm, Vector((-.5, -.5, -.5)))
    poly.symmetrize(bm, seam, [one])                                         # Maya topo_one_minus: only its twin
    _minus, plus = _sides(bm)
    assert (.5, -.5, -.5) in plus and sum(1 for p in plus if p[0] > .7) == 3, plus


# --- menu paths (operators) ----------------------------------------------------------------------

def _mesh_object():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    me = bpy.data.meshes.new("pCubeShape1")
    bm = _cube()
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("pCube1", me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    return ob


def _edit(ob, mode, pick):
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type=mode)
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(ob.data)
    _lookup(bm)
    for el in pick(bm):
        el.select = True
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)


def _done(ob):
    bpy.ops.object.mode_set(mode='OBJECT')
    me = ob.data
    return (len(me.vertices), len(me.edges), len(me.polygons))


def test_menu_rows():
    assert menu_map.MAP["Edit Mesh/Connect"] == "allset.connect"
    assert menu_map.MAP["Edit Mesh/Merge"] == "allset.merge"
    assert menu_map.MAP["Mesh/Smooth"] == "allset.smooth"
    assert menu_map.MAP["Edit Mesh/Symmetrize"] == "allset.symmetrize"
    assert menu_map.OBJECT_MODE["Edit Mesh/Symmetrize"] == poly.SYMMETRIZE_NO_COMPONENTS


def test_menu_paths_in_component_mode():
    ob = _mesh_object()
    _edit(ob, 'EDGE', lambda b: [_edge(b, T2, T3), _edge(b, T5, T4)])
    bpy.ops.allset.menu_item(item="Edit Mesh/Connect")
    assert _done(ob) == (10, 15, 7), _done(ob)
    ob = _mesh_object()
    _edit(ob, 'VERT', lambda b: [_vert(b, V0), _vert(b, V1)])
    bpy.ops.allset.menu_item(item="Edit Mesh/Merge")
    assert _done(ob) == (7, 11, 6), _done(ob)
    ob = _mesh_object()
    _edit(ob, 'FACE', lambda b: [_face(b, TOP)])
    bpy.ops.allset.menu_item(item="Mesh/Smooth")
    assert _done(ob) == (13, 20, 9), _done(ob)
    ob = _mesh_object()
    bpy.ops.allset.menu_item(item="Mesh/Smooth")                  # object mode: the whole mesh
    assert _done(ob) == (26, 48, 24) and not ob.modifiers, _done(ob)
    # Merge from object mode: every vertex, threshold only (Maya merge_object_none_within: unchanged)
    ob = _mesh_object()
    bpy.ops.allset.menu_item(item="Edit Mesh/Merge")
    assert bpy.context.mode == 'OBJECT' and len(ob.data.vertices) == 8


def test_merge_uses_option_window_values():
    old = option_windows.saved("merge")
    try:
        option_windows.store("merge", {"threshold": 0.01, "always_two": False})
        ob = _mesh_object()
        _edit(ob, 'VERT', lambda b: [_vert(b, V0), _vert(b, V1)])
        bpy.ops.allset.merge()
        assert _done(ob) == (8, 12, 6), _done(ob)
    finally:
        option_windows.store("merge", old or {"threshold": 0.01, "always_two": True})


def test_symmetrize_operator():
    ob = _mesh_object()
    # object mode: Maya's error, nothing happens
    res = bpy.ops.allset.menu_item(item="Edit Mesh/Symmetrize")
    assert res == {'CANCELLED'} and len(ob.data.vertices) == 8
    me = ob.data
    bm, seam = _sym_cube()
    bm.to_mesh(me)
    bm.free()
    before = sorted(tuple(round(c, 4) for c in v.co) for v in me.vertices)
    _edit(ob, 'VERT', lambda b: [v for v in b.verts if v.co.x < -.1])
    # the menu item only enters the pick tool (headless: no click) -> mesh unchanged
    bpy.ops.allset.menu_item(item="Edit Mesh/Symmetrize")
    bpy.ops.object.mode_set(mode='OBJECT')
    assert sorted(tuple(round(c, 4) for c in v.co) for v in me.vertices) == before
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(me)
    _lookup(bm)
    seam = next(e for e in bm.edges if all(abs(v.co.x) < 1e-6 and v.co.z > .4 for v in e.verts))
    assert bpy.ops.allset.symmetrize(edge=seam.index, object_name=ob.name) == {'FINISHED'}
    bpy.ops.object.mode_set(mode='OBJECT')
    plus = sorted(tuple(round(c, 4) for c in v.co) for v in me.vertices if v.co.x > .1)
    assert plus == UNIT, plus
