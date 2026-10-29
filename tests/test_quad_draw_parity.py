"""Surface-aware inference, collective strip snapping and scale-independent topology checks."""
from importlib import import_module
import numpy as np
from mathutils import Vector,Matrix
import kit
f=import_module(kit.MODULE+'.operators.quad_draw_fill')
w=import_module(kit.MODULE+'.operators.quad_draw_weld')

def test_foreshortened_depth_spike_does_not_beat_the_nearby_surface_quad():
    xy=[(0,0),(100,0),(100,100),(0,100),(75,85)]
    world=[(0,0,0),(1,0,0),(1,1,6),(0,1,0),(.75,.85,0)]
    for scale in (1e-6,1,1e6):
        s=f.ScreenFill(xy,[True]*5,[],[],[],world=np.asarray(world)*scale)
        assert set(s.plan((40,40)))=={0,1,3,4}
        for delta in (-.15,.15):assert set(s.plan((40+delta,40-delta)))=={0,1,3,4}

def test_valid_surface_quads_and_degenerate_corners_do_not_depend_on_scene_units():
    xy=[(0,0),(100,0),(100,100),(0,100)]
    for size in (1e-9,1e-6,.01,1,1e6):
        co=np.asarray([(0,0,0),(1,0,0),(1,1,.1),(0,1,0)])*size
        s=f.ScreenFill(xy,[True]*4,[],[],[],world=co)
        assert s.valid((0,1,2,3)),size
        assert set(s.plan((50,50)))=={0,1,2,3}
        co[2]=co[1]
        assert not f.ScreenFill(xy,[True]*4,[],[],[],world=co).valid((0,1,2,3))

def strip():
    co=[(-1,0,0),(0,0,0),(0,1,0),(-1,1,0),(0,2,0),(-1,2,0),(1,0,0),(2,0,0),(2,1,0),(1,1,0),(2,2,0),(1,2,0)]
    faces=[(0,1,2,3),(3,2,4,5),(6,7,8,9),(9,8,10,11)]
    return co,w.Topology(co,faces)

def test_three_endpoint_strip_finds_a_collective_weld_instead_of_starving_the_middle():
    co,t=strip();proposed={1:Vector(co[6]),2:Vector(co[9]),4:Vector(co[11])}
    pairs=w.choose_pairs({1:[9,6],2:[9],4:[11]},proposed,t.valid)
    assert pairs=={1:6,2:9,4:11} and t.valid(pairs,proposed)

def test_long_strip_reassigns_targets_and_retains_topology_checked_fallback():
    options={0:[101,100],1:[101],2:[102],3:[103],4:[104],5:[105]};proposed={i:Vector((i,0,0)) for i in options}
    pairs=w.choose_pairs(options,proposed,lambda pairs,co:len(set(pairs.values()))==len(pairs))
    assert len(pairs)==6 and pairs[0]==100 and pairs[1]==101
    pairs=w.choose_pairs(options,proposed,lambda pairs,co:len(set(pairs.values()))==len(pairs) and pairs.get(2)!=102)
    assert 2 not in pairs and len(set(pairs.values()))==len(pairs)
