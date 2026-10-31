"""#170 #172: the UV Editor froze on dense meshes in the Maya layout — the UV HUD statistics and the shell /
texture borders were recomputed in Python on every redraw after a mesh or selection change (1.2-1.9 s each on a
48 400-face sphere), and Cut UV Edges scanned the whole shell per cut vertex (36 s).

operators/uv_arrays.py does the same in numpy. Checked here: the numpy results equal the Python rules
(uv_hud.mesh_statistics, uv_display.border_segments) on meshes with seams, cuts, hidden faces, stacked and reversed
shells, UV Sync on / off and a UV selection, read both from the evaluated mesh and from the BMesh; and the time on a
dense mesh stays interactive."""

import time
from importlib import import_module

import bmesh
import bpy

import kit

uv_arrays = import_module(kit.MODULE + ".operators.uv_arrays")
uv_tools = import_module(kit.MODULE + ".operators.uv_tools")
hud = import_module(kit.MODULE + ".ui.uv_hud")
display = import_module(kit.MODULE + ".ui.uv_display")
kcompat = import_module(kit.MODULE + ".compat")


def _clear():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _sphere(cuts=0, seg=12, rings=8):
    _clear()
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings)
    ob = bpy.context.object
    bpy.ops.object.mode_set(mode='EDIT')
    if cuts:
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.subdivide(number_cuts=cuts)
    bpy.ops.mesh.select_all(action='DESELECT')
    return ob


def _bm(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    for seq in (bm.verts, bm.edges, bm.faces):
        seq.ensure_lookup_table()
    return bm, bm.loops.layers.uv.active


def _depsgraph():
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    return dg


def _python_stats(bm, uv, synced):
    got = hud.mesh_statistics(bm, uv, synced)
    return got[:6], sorted(got[6])


def _numpy_stats(ob, bm, uv, synced, evaluated):
    a = uv_arrays.read(ob, bm, uv, _depsgraph(), evaluated=evaluated)
    got = uv_arrays.statistics(a, bm, uv, synced, hud.STACK_EPS)
    return got[:6], sorted(got[6])


def _python_borders(bm, uv, synced):
    segs = display.border_segments(bm, uv, display.shown_faces(bm, synced))
    return sorted((round(a[0], 6), round(a[1], 6), round(b[0], 6), round(b[1], 6)) for a, b in segs)


def _numpy_borders(ob, bm, uv, synced, evaluated):
    a = uv_arrays.read(ob, bm, uv, _depsgraph(), evaluated=evaluated)
    pts = uv_arrays.border_points(a, uv_arrays.shown_faces(a, synced))
    return sorted((round(float(pts[i][0]), 6), round(float(pts[i][1]), 6), round(float(pts[i + 1][0]), 6),
                   round(float(pts[i + 1][1]), 6)) for i in range(0, len(pts), 2))


def _compare(ob, label):
    for synced in (True, False):
        bm, uv = _bm(ob)
        want_s = _python_stats(bm, uv, synced)
        want_b = _python_borders(bm, uv, synced)
        for evaluated in (True, False):
            bm, uv = _bm(ob)
            got_s = _numpy_stats(ob, bm, uv, synced, evaluated)
            bm, uv = _bm(ob)
            got_b = _numpy_borders(ob, bm, uv, synced, evaluated)
            tag = f"{label} sync={synced} evaluated={evaluated}"
            assert got_s[0] == want_s[0], (tag, "stats", got_s[0], want_s[0])
            assert [tuple(round(x, 6) for x in c) for c in got_s[1]] == \
                [tuple(round(x, 6) for x in c) for c in want_s[1]], (tag, "coords")
            assert got_b == want_b, (tag, "borders", len(got_b), len(want_b))


def _cut_middle(ob):
    bm, uv = _bm(ob)
    edges = [e for e in bm.edges if all(abs(v.co.z) < 1e-4 for v in e.verts)]
    assert edges
    uv_tools.cut(bm, uv, edges)
    bmesh.update_edit_mesh(ob.data)
    return len(edges)


def _select_some(ob, every=3):
    bm, uv = _bm(ob)
    for i, f in enumerate(bm.faces):
        f.select_set(i % every == 0)
    for i, f in enumerate(bm.faces):     # a UV selection on part of the shown faces
        if f.select:
            for k, l in enumerate(f.loops):
                kcompat.set_uv_vert_selected(l, uv, k % 2 == 0)
    bmesh.update_edit_mesh(ob.data)


def test_plain_sphere_matches_python():
    ob = _sphere()
    _compare(ob, "sphere")
    _select_some(ob)
    _compare(ob, "sphere + selection")


def test_cut_hidden_stacked_reversed_match_python():
    ob = _sphere(cuts=1)
    _cut_middle(ob)
    bm, uv = _bm(ob)
    bm.faces[3].hide_set(True)
    for l in bm.faces[10].loops:        # a reversed face: mirror its UVs
        l[uv].uv.x = 1.0 - l[uv].uv.x
    for l in bm.faces[20].loops:        # a UV stacked exactly on another shell's UV
        l[uv].uv = bm.faces[40].loops[0][uv].uv.copy()
    bmesh.update_edit_mesh(ob.data)
    _select_some(ob, every=2)
    _compare(ob, "cut + hidden + reversed + stacked")
    bm, uv = _bm(ob)
    stats = hud.mesh_statistics(bm, uv, True)
    assert stats[0] >= 2 and stats[2] > 0 and stats[4] > 0, stats     # the case covers shells, overlaps, reversed


def test_non_manifold_edge_matches_python():
    _clear()
    me = bpy.data.meshes.new("nm")
    # three quads on one edge (0, 1)
    me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0), (0, -1, 0), (1, -1, 0), (0, 0, 1), (1, 0, 1)], [],
                   [(0, 1, 3, 2), (1, 0, 4, 5), (0, 1, 7, 6)])
    uvl = me.uv_layers.new(name="map1")
    for poly in me.polygons:
        for k in range(poly.loop_total):
            v = me.vertices[me.loops[poly.loop_start + k].vertex_index].co
            uvl.data[poly.loop_start + k].uv = (v.x, v.y + v.z * 3)
    ob = bpy.data.objects.new("nm", me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    _compare(ob, "non-manifold")


def test_with_edit_mode_modifier_reads_bmesh():
    ob = _sphere()
    bpy.ops.object.mode_set(mode='OBJECT')
    md = ob.modifiers.new("s", 'SUBSURF')
    md.show_in_editmode = True
    bpy.ops.object.mode_set(mode='EDIT')
    _cut_middle(ob)
    _compare(ob, "subsurf in edit mode")


def test_dense_mesh_is_interactive():
    ob = _sphere(cuts=10, seg=32, rings=16)      # 48 400 faces, the slow case
    bm, uv = _bm(ob)
    n = len(bm.faces)
    assert n >= 48000, n
    t = time.perf_counter()
    cut = _cut_middle(ob)
    t_cut = time.perf_counter() - t
    bm, uv = _bm(ob)
    dg = _depsgraph()       # Blender evaluates the edited mesh anyway before it draws
    t = time.perf_counter()
    a = uv_arrays.read(ob, bm, uv, dg)
    uv_arrays.statistics(a, bm, uv, True, hud.STACK_EPS)
    uv_arrays.border_points(a, uv_arrays.shown_faces(a, True))
    t_draw = time.perf_counter() - t
    print(f"{n} faces: cut {cut} edges {t_cut:.2f} s (was 27.6 s), HUD + borders {t_draw * 1000:.0f} ms (was 3.6 s)")
    assert t_cut < 3.0, t_cut
    assert t_draw < 0.4, t_draw


def test_cut_still_splits_and_sew_still_joins():
    ob = _sphere(cuts=1)
    bm, uv = _bm(ob)
    before = len(uv_tools.islands(bm, uv))
    edges = [e for e in bm.edges if all(abs(v.co.z) < 1e-4 for v in e.verts)]
    assert uv_tools.cut(bm, uv, edges) == len(edges)
    after = len(uv_tools.islands(bm, uv))
    assert after == before + 1, (before, after)
    assert uv_tools.sew(bm, uv, edges) == len(edges)
    assert len(uv_tools.islands(bm, uv)) == before
