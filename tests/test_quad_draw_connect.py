"""Quad Draw bridge proposals and topology-safe transactional welds."""
from importlib import import_module
import numpy as np
from mathutils import Vector
import kit

fill=import_module(kit.MODULE+'.operators.quad_draw_fill')
weld=import_module(kit.MODULE+'.operators.quad_draw_weld')

CO=[(-2,0,0),(-1,0,0),(-1,1,0),(-2,1,0),(0,0,0),(1,0,0),(1,1,0),(0,1,0)]
FACES=[(0,1,2,3),(4,5,6,7)]


def screen(co=CO,faces=FACES):
    counts={}
    for f in faces:
        for a,b in zip(f,f[1:]+f[:1]):
            key=tuple(sorted((a,b)))
            counts[key]=counts.get(key,0)+1
    return fill.ScreenFill([(x*100,y*100) for x,y,*_ in co],[True]*len(co),list(counts),list(counts.values()),faces)


def test_gap_uses_four_existing_boundary_vertices():
    s=screen()
    ring=s.plan((-50,50))
    assert set(ring)=={1,2,4,7},ring
    assert len(ring)==4 and s.valid(ring)


def test_nearby_dots_do_not_replace_the_two_opposing_edges():
    co=CO+[(-.7,-.1,0),(-.6,1.1,0),(-.3,1.15,0),(-.2,-.1,0)]
    s=screen(co)
    ring=s.plan((-50,50))
    assert set(ring)=={1,2,4,7},ring


def test_no_triangle_or_quad_over_existing_face():
    s=screen()
    assert s.plan((-150,50)) is None
    assert not s.valid((0,1,2))
    assert not s.valid((0,1,2,3))


def test_nonmanifold_edge_is_not_used_for_a_new_face():
    s=screen()
    s.counts[(1,2)]=2
    assert not s.valid((1,4,7,2))


def test_coincident_geometry_is_rejected_even_with_different_vertex_ids():
    co=CO+CO[:4]
    assert not screen(co).valid((8,9,10,11))


def test_proposal_does_not_skip_a_boundary_vertex():
    co=CO+[(-.5,0,0),(-.5,-.5,0)]
    s=screen(co,FACES+[(1,8,9)])
    assert not s.valid((1,4,7,2))


def test_visible_candidates_only():
    assert screen().plan((-50,50),lambda i:i!=7) is None


def test_pure_dots_still_make_quads_and_triangles():
    s=screen([(0,0,0),(1,0,0),(1,1,0),(0,1,0)],[])
    assert set(s.plan((50,50)))=={0,1,2,3}
    s=screen([(0,0,0),(1,0,0),(.5,1,0)],[])
    assert set(s.plan((50,30)))=={0,1,2}


def test_weld_two_boundary_endpoints_keeps_valid_shared_edge():
    topology=weld.Topology(CO,FACES)
    assert topology.valid({1:4,2:7},{1:Vector(CO[4]),2:Vector(CO[7])})
    assert not topology.valid({1:4,2:4},{})


def test_weld_rejects_duplicate_faces_and_collapsed_triangles():
    topology=weld.Topology(CO,FACES)
    assert not topology.valid(dict(zip(range(4),(4,5,6,7))),{})
    tri=weld.Topology([(0,0,0),(1,0,0),(0,1,0)],[(0,1,2)])
    assert not tri.valid({1:0},{})


def test_weld_rejects_a_third_face_and_inconsistent_winding():
    co=CO+[(0,.5,1),(-.5,.5,1)]
    topology=weld.Topology(co,FACES+[(4,7,8)])
    assert not topology.valid({1:4,2:7},{})
    topology=weld.Topology(CO,[FACES[0],tuple(reversed(FACES[1]))])
    assert not topology.valid({1:4,2:7},{})
