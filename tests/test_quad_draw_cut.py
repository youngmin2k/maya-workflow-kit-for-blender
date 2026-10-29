"""Source-edge cut pairing, shared loops, intersecting symmetry paths and UV interpolation."""
import math,bpy,bmesh
from importlib import import_module
from mathutils import Vector,Matrix
import kit
q=import_module(kit.MODULE+'.operators.quad_draw')
cut=import_module(kit.MODULE+'.operators.quad_draw_cut')
sy=import_module(kit.MODULE+'.operators.quad_draw_symmetry')

def fixture():
    me=bpy.data.meshes.new('cut_test');ob=bpy.data.objects.new('cut_test',me);bpy.context.scene.collection.objects.link(ob)
    bm=bmesh.new();bm.verts.layers.int.new(q.DOT_LAYER);sy.ensure_identity(bm)
    state=bpy.context.scene.allset_symmetry;state.on=True;state.about='WORLD';state.axis='X'
    return ob,bm

def quad(bm,points):
    face=bm.faces.new([bm.verts.new(p) for p in points]);q._indices(bm);return face

def clean(bm):
    assert all(len(e.link_faces)<=2 for e in bm.edges)
    assert all(len(f.verts)==4 and f.calc_area()>1e-8 for f in bm.faces)
    assert all(v.link_faces for v in bm.verts)

def test_shared_ring_pairs_before_asymmetric_live_projection():
    ob,bm=fixture();bmesh.ops.create_grid(bm,x_segments=4,y_segments=4,size=1);q._indices(bm)
    edge=next(e for e in bm.edges if all(abs(v.co.x-.5)<1e-6 for v in e.verts) and min(v.co.y for v in e.verts)==-.5)
    stroke=sy.begin(bpy.context,ob,bm)
    plan=cut.Plan(bm,edge,.35,stroke)
    new=plan.apply(lambda p:p+Vector((.002,0,.02*(1+p.x))))
    stroke.sync();assert len(bm.verts)==30 and len(bm.faces)==20
    assert len(new)==5 and sum(stroke.pairs[v] is v for v in new)==1
    for v in new:assert (stroke.pairs[v].co-stroke.matrix@v.co).length<1e-7
    clean(bm);stroke.close();bm.free()

def test_two_distinct_factors_on_the_same_mirrored_edge_make_two_clean_cuts():
    ob,bm=fixture();f=quad(bm,[(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0)])
    edge=next(e for e in f.edges if all(v.co.y==-1 for v in e.verts))
    stroke=sy.begin(bpy.context,ob,bm)
    new=cut.Plan(bm,edge,.3,stroke).apply();stroke.sync()
    assert len(new)==4 and len(bm.verts)==8 and len(bm.faces)==3
    assert all(abs(abs(v.co.x)-.4)<1e-6 for v in new)
    clean(bm);stroke.close();bm.free()

def test_centered_self_mirrored_edge_is_split_only_once():
    ob,bm=fixture();f=quad(bm,[(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0)])
    edge=next(e for e in f.edges if all(v.co.y==-1 for v in e.verts))
    stroke=sy.begin(bpy.context,ob,bm);new=cut.Plan(bm,edge,.5,stroke).apply();stroke.sync()
    assert len(new)==2 and len(bm.verts)==6 and len(bm.faces)==2
    assert all(stroke.pairs[v] is v for v in new)
    clean(bm);stroke.close();bm.free()

def test_crossing_mirrored_paths_share_one_intersection_and_interpolate_uvs():
    ob,bm=fixture();f=quad(bm,[(-1,0,0),(0,-1,0),(1,0,0),(0,1,0)])
    uv=bm.loops.layers.uv.new('UVMap')
    for loop in f.loops:loop[uv].uv=(loop.vert.co.x*.5+.5,loop.vert.co.y*.5+.5)
    edge=next(e for e in f.edges if all(v.co.x<=0 and v.co.y<=0 for v in e.verts))
    stroke=sy.begin(bpy.context,ob,bm)
    new=cut.Plan(bm,edge,.35,stroke).apply();stroke.sync()
    assert len(new)==5 and len(bm.verts)==9 and len(bm.faces)==4
    assert sum(len(v.link_faces)==4 for v in new)==1
    for face in bm.faces:
        for loop in face.loops:
            expected=Vector((loop.vert.co.x*.5+.5,loop.vert.co.y*.5+.5))
            assert (loop[uv].uv-expected).length<1e-6
    clean(bm);stroke.close();bm.free()

def test_all_object_and_world_axes_keep_cut_pairs_in_transformed_frames():
    for about in ('OBJECT','WORLD'):
        for axis in range(3):
            ob,bm=fixture();state=bpy.context.scene.allset_symmetry;state.about=about;state.axis='XYZ'[axis]
            ob.matrix_world=Matrix.Translation((.3,.1,.2))@Matrix.Rotation(.4,4,'Z')@Matrix.Diagonal((1.3,.8,1.1,1))
            bmesh.ops.create_grid(bm,x_segments=4,y_segments=4,size=1)
            for v in bm.verts:
                p=Vector();p[axis]=v.co.x;p[(axis+1)%3]=v.co.y
                v.co=p if about=='OBJECT' else ob.matrix_world.inverted()@p
            q._indices(bm);edge=next(e for e in bm.edges if len(e.link_faces)==2)
            stroke=sy.begin(bpy.context,ob,bm);new=cut.Plan(bm,edge,.4,stroke).apply()
            stroke.sync()
            for v in new:assert (stroke.pairs[v].co-stroke.matrix@v.co).length<2e-6
            clean(bm);stroke.close();bm.free()

def test_topology_cut_uses_edge_correspondence_and_disables_a_modified_seam():
    ob,bm=fixture();bmesh.ops.create_grid(bm,x_segments=4,y_segments=4,size=1)
    for v in bm.verts:v.co.x+=.4+.1*v.co.y*v.co.y
    q._indices(bm);state=bpy.context.scene.allset_symmetry;state.about='TOPOLOGY'
    seam=min((e for e in bm.edges if len(e.link_faces)==2 and abs(e.verts[0].co.y-e.verts[1].co.y)>.1),key=lambda e:sum(abs(v.co.x-(.4+.1*v.co.y*v.co.y)) for v in e.verts)+abs(sum(v.co.y for v in e.verts))*.01)
    sy.bind_seam(ob,bm,seam,state);edge=seam
    stroke=sy.begin(bpy.context,ob,bm);cut.Plan(bm,edge,.4,stroke).apply();stroke.sync()
    assert len(bm.faces)==20 and not state.on and stroke.disabled_reason
    assert sy.SEED not in ob.data
    clean(bm);stroke.close();bm.free()

def test_unpaired_cut_is_rejected_before_geometry_changes():
    ob,bm=fixture();f=quad(bm,[(1,0,0),(2,0,0),(2,1,0),(1,1,0)])
    stroke=sy.begin(bpy.context,ob,bm)
    try:cut.Plan(bm,list(f.edges)[0],.5,stroke)
    except sy.SymmetryError:pass
    else:raise AssertionError('unpaired geometry must not be cut partially')
    assert len(bm.verts)==4 and len(bm.faces)==1
    stroke.close();bm.free()

def test_projection_failure_restores_a_non_symmetric_cut_without_leaking_mesh_ids():
    from types import SimpleNamespace
    ob,bm=fixture();quad(bm,[(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0)]);bm.to_mesh(ob.data);bm.free()
    if bpy.context.object is not None and bpy.context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
    for other in bpy.context.selected_objects:other.select_set(False)
    ob.select_set(True);bpy.context.view_layer.objects.active=ob;bpy.context.scene.allset_symmetry.on=False
    bpy.ops.object.mode_set(mode='EDIT');messages=[]
    op=SimpleNamespace(_ob=ob.name,_refs=[ob],_sym=None,report=lambda kinds,message:messages.append(message))
    picker,project=q.component_at,q.project_point
    before=len(bpy.data.meshes)
    q.component_at=lambda *args,**kwargs:('EDGE',0,.5)
    def fail(*args,**kwargs):raise RuntimeError('projection failed')
    q.project_point=fail
    try:
        answer=q.ALLSET_OT_quad_draw._loop(op,bpy.context,(0,0))
        current=bmesh.from_edit_mesh(ob.data)
        assert answer=={'CANCELLED'} and len(current.verts)==4 and len(current.faces)==1
        assert messages==['projection failed'] and len(bpy.data.meshes)==before
    finally:
        q.component_at=picker;q.project_point=project;bpy.ops.object.mode_set(mode='OBJECT')
