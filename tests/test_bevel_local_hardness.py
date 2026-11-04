"""A local bevel must preserve hardness on distant unselected geometry."""
from importlib import import_module

import bmesh
from mathutils import Matrix

import kit

bev = import_module(kit.MODULE + '.operators.bevel_maya')


def edge_key(e):
    return tuple(sorted(tuple(round(x, 6) for x in v.co) for v in e.verts))


def test_distant_shell_keeps_mixed_hardness_after_a_local_bevel():
    for segments in (1, 2, 4):
        for smoothing in (0, 30, 180):
            bm = bmesh.new()
            picked = set(bmesh.ops.create_cube(bm, size=2)['verts'])
            remote = set(bmesh.ops.create_cube(bm, size=2, matrix=Matrix.Translation((5, 0, 0)))['verts'])
            remote_edges = [e for e in bm.edges if all(v in remote for v in e.verts)]
            for i, f in enumerate(bm.faces):
                f.smooth = i % 3 != 0
            for i, e in enumerate(remote_edges):
                e.smooth = i % 2 == 0
            before = {edge_key(e): bev.is_hard(e) for e in remote_edges}
            edges = [e for e in bm.edges if all(v in picked for v in e.verts)]
            assert bev.bevel_edges(bm, edges, fraction=0.2, segments=segments, smoothing_angle=smoothing)
            after = {edge_key(e): bev.is_hard(e) for e in bm.edges if all(v.co.x > 3 for v in e.verts)}
            assert before == after, (segments, smoothing)
            assert all(e.is_manifold for e in bm.edges)
            bm.free()
