"""Bevel at a box corner (two or three bevelled edges meeting, square or tilted side faces): the kit's result stays a
clean closed mesh, cuts only into the box and keeps a symmetric corner symmetric."""

from importlib import import_module

import bmesh
from mathutils import Vector

import kit

bev = import_module(kit.MODULE + ".operators.bevel_maya")
EPS = 1e-6


def _box(tilt=0.0):
    """A unit box (0..1); ``tilt`` leans the +X side face by moving its top edge along +X."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co += Vector((0.5, 0.5, 0.5))
        if v.co.x > 0.5 and v.co.z > 0.5:
            v.co.x += tilt
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    return bm


def _corner_edges(bm, count):
    """The ``count`` box edges at the corner (1, 1, 1) — x / y edges first, then z."""
    corner = min(bm.verts, key=lambda v: (v.co - Vector((1.0, 1.0, 1.0))).length)
    edges = sorted(corner.link_edges, key=lambda e: abs((e.other_vert(corner).co - corner.co).z))
    return edges[:count]


def _check(bm, label, bounds):
    lo, hi = bounds
    for e in bm.edges:
        assert len(e.link_faces) == 2, f"{label}: open edge after the bevel"
    for f in bm.faces:
        assert f.calc_area() > EPS, f"{label}: degenerate face"
    for v in bm.verts:
        for i in range(3):
            assert lo[i] - EPS <= v.co[i] <= hi[i] + EPS, f"{label}: vertex {tuple(v.co)} outside the box"


def _bounds(bm):
    cos = [v.co for v in bm.verts]
    return (Vector([min(c[i] for c in cos) for i in range(3)]), Vector([max(c[i] for c in cos) for i in range(3)]))


def test_two_and_three_edge_corners_stay_clean():
    for tilt in (0.0, 0.05, 0.15, 0.3):
        for count in (2, 3):
            for kw in ({"fraction": 0.3}, {"offset_as_fraction": False, "offset": 0.1}):
                bm = _box(tilt)
                box = _bounds(bm)
                made = bev.bevel_edges(bm, _corner_edges(bm, count), **kw)
                label = f"tilt {tilt}, {count} edges, {kw}"
                assert made, f"{label}: nothing bevelled"
                _check(bm, label, box)
                bm.free()


def test_square_corner_is_symmetric():
    """Two bevelled edges of a square corner: swapping x and y maps the result onto itself."""
    bm = _box()
    bev.bevel_edges(bm, _corner_edges(bm, 2), fraction=0.3)
    pts = [v.co.copy() for v in bm.verts]
    bm.free()
    for p in pts:
        q = Vector((p.y, p.x, p.z))
        assert min((q - r).length for r in pts) < 1e-5, f"no mirror point for {tuple(p)}"


def test_corner_next_to_a_bent_side_face():
    """The upright edge at the corner leans along one bevelled edge, so one side face is no longer flat: the result
    stays clean and inside the box, and no new vertex goes deeper below the top face than the bevel width."""
    for axis in (0, 1):
        for lean in (-0.1, 0.1):
            bm = _box()
            low = min(bm.verts, key=lambda v: (v.co - Vector((1.0, 1.0, 0.0))).length)
            low.co[axis] += lean
            box = _bounds(bm)
            edges = _corner_edges(bm, 2)
            ids = bev.maya_edge_ids(bm)
            w = bev.width(edges, 0.3, corners=bev.corner_pairs(edges, ids), triples=bev.corner_triples(edges, ids))
            made = bev.bevel_edges(bm, edges, fraction=0.3)
            label = f"axis {axis}, lean {lean}"
            assert made, f"{label}: nothing bevelled"
            _check(bm, label, box)
            depth = max(1.0 - v.co.z for v in made if v.co.z > 0.5)
            assert depth <= w + EPS, f"{label}: a new vertex {depth:.6f} below the top face, width {w:.6f}"
            bm.free()
