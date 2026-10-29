"""Quad Draw loop semantics, continuous boundaries, and the Soft Selection relax area."""
import math
from types import SimpleNamespace
from importlib import import_module
import bmesh,bpy,numpy as np
from mathutils import Quaternion
import kit
q=import_module(kit.MODULE+'.operators.quad_draw')
r=import_module(kit.MODULE+'.operators.quad_draw_relax')

def grid():
    bm=bmesh.new();bmesh.ops.create_grid(bm,x_segments=4,y_segments=4,size=1)
    q._indices(bm);return bm

def boundary(bm):
    return min((e for e in bm.edges if e.is_boundary),key=lambda e:sum(v.co.y for v in e.verts)+abs(sum(v.co.x for v in e.verts))*.01)

def cache(bm):
    q._indices(bm);bm.verts.ensure_lookup_table();bm.edges.ensure_lookup_table();bm.faces.ensure_lookup_table()
    edges=np.asarray([tuple(v.index for v in e.verts) for e in bm.edges],dtype='int32').reshape(-1,2)
    return SimpleNamespace(bm=bm,co=np.asarray([v.co[:] for v in bm.verts]),edges=edges,eok=np.asarray([not e.hide for e in bm.edges],dtype=bool),vok=np.asarray([not v.hide for v in bm.verts],dtype=bool),arrays=None)

def test_border_loop_deletes_the_complete_face_strip_without_loose_dots():
    bm=grid();edge=boundary(bm)
    assert len(q.component_loop(edge))==4
    q.delete_loop(bm,edge.index)
    assert len(bm.faces)==12 and len(bm.verts)==20
    assert all(len(f.verts)==4 for f in bm.faces) and all(v.link_faces for v in bm.verts)
    bm.free()

def test_hidden_boundary_edge_stops_loop_traversal():
    bm=grid();bottom=sorted((e for e in bm.edges if e.is_boundary and all(abs(v.co.y+1)<1e-7 for v in e.verts)),key=lambda e:sum(v.co.x for v in e.verts))
    bottom[1].hide=True
    assert q.component_loop(bottom[0])==[bottom[0]]
    assert not q.component_loop(bottom[1])
    bm.free()

def test_non_manifold_loop_target_does_not_remove_any_faces():
    bm=bmesh.new();a=bm.verts.new((0,0,0));b=bm.verts.new((1,0,0))
    for p in ((0,1,0),(0,-1,0),(0,0,1)):bm.faces.new((a,b,bm.verts.new(p)))
    q._indices(bm);edge=bm.edges.get((a,b))
    assert not q.component_loop(edge) and not q.delete_loop(bm,edge.index) and len(bm.faces)==3
    bm.free()

def test_closed_interior_loop_dissolves_without_deleting_its_surface():
    bm=bmesh.new();rows=[[bm.verts.new((math.cos(i*math.tau/8),math.sin(i*math.tau/8),z)) for i in range(8)] for z in range(4)]
    for a,b in zip(rows,rows[1:]):
        for i in range(8):bm.faces.new((a[i],a[(i+1)%8],b[(i+1)%8],b[i]))
    q._indices(bm);edge=bm.edges.get((rows[1][0],rows[1][1]))
    assert len(q.component_loop(edge))==8
    q.delete_loop(bm,edge.index)
    assert len(bm.faces)==16 and len(bm.verts)==24 and all(len(f.verts)==4 for f in bm.faces)
    bm.free()

def islands():
    bm=bmesh.new()
    for center in (-.1,.1):bm.faces.new([bm.verts.new((center+x,y,0)) for x,y in ((-.03,-.03),(.03,-.03),(.03,.03),(-.03,.03))])
    q._indices(bm);bm.verts.ensure_lookup_table();return bm

def test_boundary_relax_connectivity_does_not_cross_a_nearby_island():
    bm=islands();ids=r.boundary_component(bm,bm.verts[0])
    assert ids==set(range(4))
    c=cache(bm);kernel=r.Kernel(c,sorted(ids),'BORDER',{})
    points=kernel.step(kernel.initial)
    assert np.allclose(points.mean(axis=0),kernel.initial.mean(axis=0))
    assert np.linalg.norm(points-kernel.initial)>0
    bm.free()

def test_soft_relax_area_honours_radius_hidden_vertices_and_connected_mode():
    bm=islands();bm.verts[3].hide=True;c=cache(bm)
    ts=bpy.context.scene.tool_settings;ts.proportional_size=.5;ts.proportional_edit_falloff='SMOOTH'
    ts.use_proportional_projected=False;ts.use_proportional_connected=False
    ids,weights=r.soft_area(bpy.context,c,[0])
    assert len(ids)==7 and weights[3]==0 and weights[0]==1
    ts.use_proportional_connected=True
    ids,_=r.soft_area(bpy.context,c,[0]);assert set(ids)=={0,1,2}
    ts.use_proportional_connected=False;ts.proportional_size=.02
    ids,_=r.soft_area(bpy.context,c,[0]);assert list(ids)==[0]
    bm.free()

def test_projected_soft_area_ignores_depth_and_curve_does_not_change_membership():
    bm=bmesh.new()
    for p in ((0,0,0),(.1,0,5),(.3,0,0)):bm.verts.new(p)
    c=cache(bm);ts=bpy.context.scene.tool_settings;ts.proportional_size=.2
    ts.use_proportional_connected=False;ts.use_proportional_projected=False
    ids,_=r.soft_area(bpy.context,c,[0]);assert list(ids)==[0]
    ts.use_proportional_projected=True
    context=SimpleNamespace(scene=bpy.context.scene,region_data=SimpleNamespace(view_rotation=Quaternion((1,0,0,0))))
    ts.proportional_edit_falloff='SHARP';a,wa=r.soft_area(context,c,[0])
    ts.proportional_edit_falloff='CONSTANT';b,wb=r.soft_area(context,c,[0])
    assert list(a)==list(b)==[0,1] and wa[1]<wb[1]
    ts.use_proportional_projected=False;bm.free()
