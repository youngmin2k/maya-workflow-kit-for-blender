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


def _box_edge():
    """A 2 x 3 x 4 box and its top front edge along X (side edges 3 and 4 long)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(2.0, 3.0, 4.0), verts=bm.verts)
    e = next(e for e in bm.edges if all(v.co.y > 1.0 and v.co.z > 1.9 for v in e.verts))
    return bm, e


def test_chamfer_off_keeps_the_corner():
    for segments in (1, 3):
        bm, e = _box_edge()
        corner = [v.co.copy() for v in e.verts]
        bev.bevel_edges(bm, [e], offset_as_fraction=False, offset=0.5, segments=segments, chamfer=False)
        w = 0.5 * bev.FIT
        for c in corner:
            ends = sorted((v.co.copy() for v in bm.verts if abs(v.co.x - c.x) < TOL and (v.co - c).length < 1.0),
                          key=lambda p: (p.z, -p.y))
            # Segments + 2 points from one face over the old corner to the other face, in equal steps
            assert len(ends) == segments + 2, (segments, len(ends))
            assert any((p - c).length < TOL for p in ends), "corner not kept"
            # distance along the two faces from the first end: equal steps of 2w / (Segments + 1)
            along = sorted(abs(p.z - c.z) if abs(p.y - c.y) < TOL else w + abs(p.y - c.y) for p in ends)
            steps = [b - a for a, b in zip(along, along[1:])]
            assert max(abs(s - 2 * w / (segments + 1)) for s in steps) < 1e-4, steps
        bm.free()


def test_world_space_ignores_object_scale():
    class Ob:
        def __init__(self, s):
            from mathutils import Matrix
            self.matrix_world = Matrix.Diagonal((s, s, s, 1.0))
    bm, e = _box_edge()
    for f in bm.edges:
        f.select = f is e
    bev.BEVEL.build(bm, {"fraction": 0.5, "offset_as_fraction": False, "offset": 0.5, "segments": 1, "depth": 1.0,
                         "chamfer": True, "world_space": True}, 1.0, ob=Ob(2.0))
    ys = sorted({round(v.co.y, 5) for v in bm.verts if abs(v.co.z - 2.0) < TOL})
    assert abs(ys[-1] - (1.5 - 0.25 * bev.FIT)) < 1e-5, ys       # half the width on an object scaled 2
    bm.free()


def test_absolute_offset_slides_past_a_short_side_edge():
    bm, e = _box_edge()
    bev.bevel_edges(bm, [e], offset_as_fraction=False, offset=3.5)
    w = 3.5 * bev.FIT
    # the vertical side edge is 3 long: the new vertex goes on past the bottom, like the 4 long one goes w along
    assert any(abs(v.co.y - (1.5 - w)) < 1e-5 and abs(v.co.z - 2.0) < TOL for v in bm.verts)
    assert any(abs(v.co.z - (2.0 - w)) < 1e-5 and abs(v.co.y - 1.5) < TOL for v in bm.verts)
    assert len(bm.verts) == 10
    bm.free()


def test_fraction_one_on_a_zero_length_extrusion_meets_in_one_vertex():
    """Bevel the cap of a zero-length face extrusion with Fraction 1: the four inner corners come within the merge
    tolerance (0.0001) of each other and become one vertex in the middle of the cap (a unit cube: the corners stop
    0.0001 short of the middle)."""
    ex = import_module(kit.MODULE + ".operators.extrude")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    top = max(bm.faces, key=lambda f: f.calc_center_median().z)
    caps, _moved = ex.extrude(bm, [top])
    bev.bevel_edges(bm, list(caps[0].edges), fraction=1.0)
    centre = [v for v in bm.verts if abs(v.co.x) < 1e-3 and abs(v.co.y) < 1e-3 and abs(v.co.z - 0.5) < 1e-3]
    assert len(centre) == 1, len(centre)
    assert (len(bm.verts), len(bm.faces)) == (9, 9), (len(bm.verts), len(bm.faces))
    bm.free()


def test_square_pyramid_tip_profiles_stand_upright():
    """Four bevelled edges at a square pyramid's tip (faces at 60 degrees there): each profile's points lie in the
    upright plane through the profile's two ends (its plane meets the edge at width / sin 60 from the tip)."""
    bm = bmesh.new()
    r = math.sqrt(2.0)
    base = [bm.verts.new((r * math.cos(a), r * math.sin(a), 0.0)) for a in (0.0, math.pi / 2, math.pi, 1.5 * math.pi)]
    tip = bm.verts.new((0.0, 0.0, math.sqrt(2.0)))       # side 2, equilateral side faces
    for i in range(4):
        bm.faces.new((base[i], base[(i + 1) % 4], tip))
    bm.faces.new(base[::-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    planes = [(f.normal.copy(), f.verts[0].co.copy()) for f in bm.faces if len(f.verts) == 3]
    frames = bev.hub_profile_frames(list(tip.link_edges), {tip} | {e.other_vert(tip) for e in tip.link_edges})
    assert len(frames) == 4 and all(abs(s - math.sin(math.radians(60))) < 1e-6 for _v, _d, s in frames.values())
    bev.bevel_edges(bm, list(tip.link_edges), offset_as_fraction=False, offset=0.2, segments=3)
    corner = next(f for f in bm.faces if len(f.verts) == 12)
    ring = [v.co.copy() for v in corner.verts]
    # profile ends lie on the old side faces; the two points between each pair of ends stand in their vertical plane
    ends = [k for k, p in enumerate(ring) if any(abs((p - q).dot(n)) < 1e-6 for n, q in planes)]
    assert len(ends) == 4, ends
    for k in ends:
        a, b, c, d = (ring[(k + j) % 12] for j in range(4))
        up = Vector((0.0, 0.0, 1.0))
        n = (d - a).cross(up)
        assert abs((b - a).dot(n.normalized())) < 1e-5 and abs((c - a).dot(n.normalized())) < 1e-5
    bm.free()
