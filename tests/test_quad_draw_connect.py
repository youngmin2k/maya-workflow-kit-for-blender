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


def test_existing_face_boundary_is_not_an_empty_gap():
    s=screen()
    assert s.plan((-100,0)) is None
    assert s.plan((-100,50)) is None
    assert fill.inside([(-200,0),(-100,0),(-100,100),(-200,100)],(-100,50),strict=False)


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


def test_quad_quality_prefers_regular_flow_over_a_tiny_skewed_proposal():
    s=screen([(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0),(.1,.2,0)],[])
    assert set(s.plan((0,0)))=={0,1,2,3}


def test_preview_is_stable_under_subpixel_motion_but_clears_in_empty_space():
    s=screen()
    first=s.plan((-50,50))
    for delta in (-.2,.1,-.1,.2):
        assert s.plan((-50+delta,50-delta))==first
    assert s.plan((10000,10000)) is None
    assert s.previous is None


def test_3d_fold_is_rejected_even_when_screen_polygon_looks_regular():
    xy=[(0,0),(100,0),(100,100),(0,100)]
    world=[(0,0,0),(1,0,0),(0,1,0),(1,1,0)]
    s=fill.ScreenFill(xy,[True]*4,[],[],[],world=world)
    assert not s.valid((0,1,2,3))
    s=fill.ScreenFill(xy,[True]*4,[],[],[],world=[(0,0,0),(1,0,0),(1,1,.2),(0,1,0)])
    assert s.valid((0,1,2,3))


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


def test_eyelid_prefers_two_local_dots_over_a_large_boundary_only_face():
    import json
    from pathlib import Path
    pre=import_module(kit.MODULE+'.operators.preselect')
    data=json.loads((Path(__file__).parent/'fixtures/quad_draw_eyelid.json').read_text())
    width,height=data['size']
    for scale in (.5,1,2):
        xy,front=pre.project(data['co'],data['projection'],width*scale,height*scale)
        boundary={v for e,n in zip(data['edges'],data['counts']) if n==1 for v in e}
        allowed=[i in boundary or i>=44 for i in range(len(xy))]
        s=fill.ScreenFill(xy,allowed,data['edges'],data['counts'],data['faces'],world=data['co'])
        ids=[2,3,44,45];mouse=xy[ids].mean(axis=0)
        assert set(s.plan(mouse))==set(ids),s.plan(mouse)
        for delta in (-.2,.2):
            assert set(s.plan(mouse+delta))==set(ids)
