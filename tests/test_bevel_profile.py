"""Edit Mesh > Bevel with Segments > 1 (operators/bevel_maya.py): every profile is a circle that touches both faces,
cut in equal angle steps, Depth moves the points toward the chord, and a corner where three or more bevelled edges
meet is closed by one polygon through the ends of the profiles."""

import math
from importlib import import_module

import bmesh
from mathutils import Vector

import kit

bev = import_module(kit.MODULE + ".operators.bevel_maya")
TOL = 1e-5


def _box():
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    return bm


def _prism():
    """Triangle prism, side edges along Y (60 degrees between their faces)."""
    bm = bmesh.new()
    r = 2.0 / math.sqrt(3.0)
    ring = [(r * math.cos(a), r * math.sin(a)) for a in (math.pi, math.pi / 3, -math.pi / 3)]
    lo = [bm.verts.new((x, -1.0, z)) for x, z in ring]
    hi = [bm.verts.new((x, 1.0, z)) for x, z in ring]
    for i in range(3):
        k = (i + 1) % 3
        bm.faces.new((lo[i], lo[k], hi[k], hi[i]))
    bm.faces.new(lo[::-1])
    bm.faces.new(hi)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def _edges_at(bm, corner):
    v = min(bm.verts, key=lambda x: (x.co - Vector(corner)).length)
    return list(v.link_edges)


def test_box_corner_is_one_polygon():
    for segments, sides in ((2, 6), (3, 9)):
        bm = _box()
        bev.bevel_edges(bm, list(bm.edges), offset_as_fraction=False, offset=0.3, segments=segments)
        corner = [f for f in bm.faces if len(f.verts) == sides]
        assert len(corner) == 8, (segments, len(corner))
        # no vertex left inside a corner: each corner has only its polygon's vertices
        assert len(bm.verts) == 8 * sides, len(bm.verts)
        bm.free()


def test_three_edge_corner_keeps_box_profiles():
    """At a box corner the profile ends are the same quarter circles as along the edges."""
    bm = _box()
    bev.bevel_edges(bm, _edges_at(bm, (1, 1, 1)), offset_as_fraction=False, offset=0.4, segments=3)
    w = 0.4 * bev.FIT
    near = [v.co for v in bm.verts if min(v.co) > 0.5 and (v.co - Vector((1, 1, 1))).length < 1.0]
    for p in near:
        # each point lies on a circle of radius w around the axis line offset by w from two box faces
        ok = False
        for i in range(3):
            a, b = [k for k in range(3) if k != i]
            if abs(math.hypot(p[a] - (1 - w), p[b] - (1 - w)) - w) < 1e-4 and p[a] >= 1 - w - TOL \
                    and p[b] >= 1 - w - TOL:
                ok = True
        assert ok, tuple(p)
    bm.free()


def _side_profile(segments, depth=1.0):
    bm = _prism()
    side = [e for e in bm.edges if abs(e.verts[0].co.y - e.verts[1].co.y) > 1.0]
    e = min(side, key=lambda x: x.verts[0].co.x)      # the edge at x = -r
    bev.bevel_edges(bm, [e], offset_as_fraction=False, offset=0.3, segments=segments, depth=depth)
    pts = sorted((v.co.copy() for v in bm.verts if abs(v.co.y + 1.0) < TOL and v.co.x < -0.1),
                 key=lambda p: p.z)
    bm.free()
    return pts


def test_sixty_degree_profile_is_a_circle():
    r = 2.0 / math.sqrt(3.0)
    corner = Vector((-r, -1.0, 0.0))
    w = 0.3 * bev.FIT
    half = math.radians(30.0)
    # the circle touches each face w from the edge; its centre is on the bisector (+X)
    centre = corner + Vector((w / math.cos(half), 0.0, 0.0))
    radius = w * math.tan(half)
    for segments in (2, 3, 4):
        pts = _side_profile(segments)
        assert len(pts) == segments + 1, (segments, len(pts))
        for p in pts:
            assert abs((p - centre).length - radius) < 1e-4, (segments, tuple(p))
        steps = [(a - centre).angle(b - centre) for a, b in zip(pts, pts[1:])]
        assert max(steps) - min(steps) < 1e-4, steps


def test_depth_moves_points_toward_the_chord():
    arc = _side_profile(4, 1.0)
    for depth in (0.0, 0.5, -1.0):
        got = _side_profile(4, depth)
        p0, p1 = arc[0], arc[-1]
        d = (p1 - p0).normalized()
        for a, g in zip(arc[1:-1], got[1:-1]):
            q = p0 + d * (a - p0).dot(d)
            assert (g - (q + (a - q) * depth)).length < 1e-4, (depth, tuple(g))
