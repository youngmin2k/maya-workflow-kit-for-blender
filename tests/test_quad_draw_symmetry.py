"""Real BMesh symmetry operations: geometry, topology, seam, weld and rollback."""
import bmesh,bpy
from importlib import import_module
from mathutils import Matrix,Vector
import kit

q=import_module(kit.MODULE+'.operators.quad_draw')
sym=import_module(kit.MODULE+'.operators.quad_draw_symmetry')

def fixture(mode='WORLD'):
    me=bpy.data.meshes.new('symmetry_test');ob=bpy.data.objects.new('symmetry_test',me)
    bpy.context.scene.collection.objects.link(ob)
    s=bpy.context.scene.allset_symmetry;s.on=True;s.about=mode;s.axis='X'
    bm=bmesh.new();bm.verts.layers.int.new(q.DOT_LAYER)
    sym.ensure_identity(bm)
    return ob,bm

def test_world_and_object_planes_respect_rotated_translated_objects():
    ob,bm=fixture()
    ob.matrix_world=Matrix.Translation((3,1,2))@Matrix.Rotation(.7,4,'Z')
    v=bm.verts.new((1,2,3))
    for mode in ('WORLD','OBJECT'):
        bpy.context.scene.allset_symmetry.about=mode
        stroke=sym.begin(bpy.context,ob,bm)
        w=ob.matrix_world@v.co
        p=ob.matrix_world@stroke.point(v.co)
        expected=Vector((-w.x,w.y,w.z)) if mode=='WORLD' else ob.matrix_world@Vector((-1,2,3))
        assert (p-expected).length<1e-5,(p,expected)
        stroke.close()
    bm.free()

def test_new_dot_pair_moves_live_and_cancel_restores_empty_mesh():
    ob,bm=fixture();stroke=sym.begin(bpy.context,ob,bm)
    v=q.add_dot(bm,Vector((1,0,0)));stroke.sync()
    assert len(bm.verts)==2
    other=stroke.pairs[v];v.co.x=2;stroke.move([v])
    assert other.co.x==-2
    stroke.rollback()
    assert not bm.verts
    bm.free()

def test_face_creation_uses_existing_pairs_and_reverse_winding():
    ob,bm=fixture()
    source=[bm.verts.new(p) for p in [(1,0,0),(2,0,0),(2,1,0),(1,1,0)]]
    target=[bm.verts.new((-v.co.x,v.co.y,v.co.z)) for v in source]
    stroke=sym.begin(bpy.context,ob,bm)
    bm.faces.new(source);stroke.sync()
    assert len(bm.faces)==2 and len(bm.verts)==8
    bm.normal_update();assert all(f.normal.z>.99 for f in bm.faces)
    stroke.close();bm.free()

def test_seam_reuses_vertices_and_face_deletion_mirrors():
    ob,bm=fixture();stroke=sym.begin(bpy.context,ob,bm)
    source=[bm.verts.new(p) for p in [(0,0,0),(1,0,0),(1,1,0),(0,1,0)]]
    bm.faces.new(source);stroke.sync();stroke.close()
    assert len(bm.verts)==6 and len(bm.faces)==2
    assert sum(len(e.link_faces)==2 for e in bm.edges)==1
    stroke=sym.begin(bpy.context,ob,bm)
    bm.faces.remove(bm.faces.get(source));stroke.sync();stroke.close()
    assert not bm.faces
    bm.free()

def test_edge_split_and_weld_replay_without_duplicate_geometry():
    ob,bm=fixture();stroke=sym.begin(bpy.context,ob,bm)
    source=[bm.verts.new(p) for p in [(1,0,0),(2,0,0),(2,1,0),(1,1,0)]]
    bm.faces.new(source);stroke.sync();stroke.close()
    stroke=sym.begin(bpy.context,ob,bm)
    bmesh.ops.subdivide_edges(bm,edges=list(bm.faces.get(source).edges),cuts=1,use_grid_fill=True)
    stroke.sync();stroke.close()
    assert len(bm.faces)==8 and len(bm.verts)==18,(len(bm.faces),len(bm.verts))
    source=[min(bm.verts,key=lambda v:(v.co-Vector(p)).length_squared) for p in [(1,0,0),(2,0,0),(2,1,0),(1,1,0)]]
    stroke=sym.begin(bpy.context,ob,bm)
    v=bm.verts.new((1.1,1.1,0));stroke.sync();stroke.close()
    stroke=sym.begin(bpy.context,ob,bm)
    target=source[3];opposite=stroke.find_pair(v)
    bmesh.ops.weld_verts(bm,targetmap={v:target});stroke.sync();stroke.close()
    assert not opposite.is_valid and len(bm.verts)==18
    bm.free()

def test_topology_pairing_propagates_on_a_posed_grid():
    ob,bm=fixture('TOPOLOGY')
    bmesh.ops.create_grid(bm,x_segments=4,y_segments=3,size=2)
    bm.verts.ensure_lookup_table()
    for v in bm.verts:
        if v.co.x>0:v.co.z=.2*v.co.x*v.co.y;v.co.x+=.3
    stroke=sym.begin(bpy.context,ob,bm)
    assert len(stroke.pairs)==len(bm.verts)
    assert all(stroke.pairs.get(other) is v for v,other in stroke.pairs.items())
    v=next(v for v in bm.verts if v.co.x<0);other=stroke.pairs[v];start=other.co.copy()
    v.co.y+=.1;stroke.move([v]);assert abs(other.co.y-start.y-.1)<1e-6
    stroke.close();bm.free()

def test_invalid_topology_reports_instead_of_using_geometric_reflection():
    ob,bm=fixture('TOPOLOGY');bm.verts.new((1,0,0))
    try:
        sym.begin(bpy.context,ob,bm)
    except sym.SymmetryError:pass
    else:raise AssertionError('unpaired topology must not silently mirror')
    bm.free()


def test_topology_new_dots_follow_a_posed_live_reference():
    live=import_module(kit.MODULE+'.operators.live')
    ob,bm=fixture('TOPOLOGY')
    reference=bpy.data.meshes.new('posed_reference')
    rb=bmesh.new();bmesh.ops.create_grid(rb,x_segments=4,y_segments=3,size=2)
    for v in rb.verts:
        if v.co.x>0:v.co.z=v.co.x*.5
    rb.to_mesh(reference);rb.free()
    ref=bpy.data.objects.new('posed_reference',reference);bpy.context.scene.collection.objects.link(ref)
    bpy.context.view_layer.update();live.set_objects(bpy.context.scene,[ref])
    stroke=sym.begin(bpy.context,ob,bm)
    v=q.add_dot(bm,Vector((1,.2,.5)));stroke.sync()
    other=stroke.pairs[v]
    assert (other.co-Vector((-1,.2,0))).length<1e-5,other.co
    stroke.close()
    # Further strokes must recover the two loose dot counterparts.
    stroke=sym.begin(bpy.context,ob,bm)
    assert stroke.pairs[v] is other
    v.co.y=.4;stroke.move([v]);assert abs(other.co.y-.4)<1e-5
    stroke.close();live.set_objects(bpy.context.scene,[]);bm.free()


def test_mirrored_failure_rolls_back_all_topology_and_custom_dot_data():
    ob,bm=fixture();v=q.add_dot(bm,Vector((1,0,0)))
    stroke=sym.begin(bpy.context,ob,bm)
    bm.verts.new((2,0,0));stroke.rollback()
    layer=bm.verts.layers.int.get(q.DOT_LAYER)
    assert len(bm.verts)==1 and layer is not None and list(bm.verts)[0][layer]==1
    assert stroke.backup is None and not stroke.pairs
    bm.free()


def test_weld_between_opposite_dots_keeps_one_center_seam_vertex():
    ob,bm=fixture();stroke=sym.begin(bpy.context,ob,bm)
    v=q.add_dot(bm,Vector((.01,0,0)));stroke.sync();other=stroke.pairs[v];stroke.close()
    stroke=sym.begin(bpy.context,ob,bm)
    stroke.weld({v:other});stroke.sync();stroke.close()
    assert len(bm.verts)==1 and abs(list(bm.verts)[0].co.x)<1e-8
    bm.free()


def test_paired_weld_preserves_both_target_positions_and_faces():
    ob,bm=fixture();stroke=sym.begin(bpy.context,ob,bm)
    source=[bm.verts.new(p) for p in [(1,0,0),(2,0,0),(2,1,0),(1,1,0)]]
    bm.faces.new(source);v=q.add_dot(bm,Vector((1.1,1.1,0)))
    stroke.sync();opposite=stroke.pairs[v];stroke.close()
    stroke=sym.begin(bpy.context,ob,bm)
    stroke.weld({v:source[3]});stroke.sync();stroke.close()
    assert not v.is_valid and not opposite.is_valid and len(bm.faces)==2 and len(bm.verts)==8
    assert all(f.calc_area()>.99 for f in bm.faces)
    bm.free()


def test_mismatched_counterpart_topology_rejects_weld_and_rolls_back():
    ob,bm=fixture()
    co=[(1,0,0),(2,0,0),(2,1,0),(1,1,0),(3,0,0),(4,0,0),(4,1,0),(3,1,0)]
    co += [(-x,y,z) for x,y,z in co]
    vs=[bm.verts.new(p) for p in co]
    for ids in ((0,1,2,3),(4,5,6,7),(11,10,9,8),(15,14,13,12)):
        bm.faces.new([vs[i] for i in ids])
    extra=bm.verts.new((-2.5,.5,1));bm.faces.new((vs[12],vs[15],extra))
    stroke=sym.begin(bpy.context,ob,bm)
    try:stroke.weld({vs[1]:vs[4],vs[2]:vs[7]})
    except sym.SymmetryError:stroke.rollback()
    else:raise AssertionError('mismatched opposite topology must reject a three-face edge')
    assert len(bm.faces)==5 and len(bm.verts)==17
    assert all(len(e.link_faces)<=2 for e in bm.edges)
    bm.free()


def test_center_capture_and_weld_respect_all_transformed_object_and_world_axes():
    from types import SimpleNamespace
    from bpy_extras import view3d_utils
    pd=import_module(kit.MODULE+'.operators.poly_draw')
    weld=import_module(kit.MODULE+'.operators.quad_draw_weld')
    saved=q._screen_xy,q.reference_objects,view3d_utils.region_2d_to_location_3d
    pd.reset_settings(pd.settings(),'QUAD_DRAW')
    try:
        q.reference_objects=lambda ctx:[]
        for mode in ('OBJECT','WORLD'):
            for axis in range(3):
                ob,bm=fixture(mode);bpy.context.scene.allset_symmetry.axis='XYZ'[axis]
                ob.matrix_world=Matrix.Translation((.3,.2,.1))@Matrix.Rotation(.4,4,'Z')@Matrix.Diagonal((2,.8,1.2,1))
                co=Vector((.2,.2,.2));co[axis]=1
                v=bm.verts.new(co);other=bm.verts.new(sym.reflection(ob,mode,axis)@co)
                bm.verts.index_update();bm.verts.ensure_lookup_table()
                stroke=sym.begin(bpy.context,ob,bm)
                normal=Vector(tuple(int(k==axis) for k in range(3)))
                if mode=='OBJECT':normal=(ob.matrix_world.to_3x3()@normal).normalized()
                q._screen_xy=lambda region,rv,w:(w.dot(normal)*100,0)
                view3d_utils.region_2d_to_location_3d=lambda region,rv,p,w:w+normal*.01
                target=co.copy();target[axis]=.03
                w=ob.matrix_world@target
                if mode=='WORLD':w[axis]=.03
                topology=weld.Topology([ob.matrix_world@u.co for u in bm.verts],[])
                out,markers=stroke.snap_seam(bpy.context,None,None,{v.index:w},SimpleNamespace(pairs={},topology=topology))
                p=out[v.index] if mode=='WORLD' else ob.matrix_world.inverted()@out[v.index]
                assert abs(p[axis])<1e-6 and markers,(mode,axis,p)
                v.co=ob.matrix_world.inverted()@out[v.index];stroke.move([v])
                stroke.weld(stroke.seam_targets());stroke.sync();stroke.close()
                assert len(bm.verts)==1
                bm.free()
    finally:q._screen_xy,q.reference_objects,view3d_utils.region_2d_to_location_3d=saved


def test_local_topology_snapshot_replays_subdivision_and_rolls_back():
    ob,bm=fixture();source=[bm.verts.new(p) for p in [(1,0,0),(2,0,0),(2,1,0),(1,1,0)]]
    stroke=sym.begin(bpy.context,ob,bm);bm.faces.new(source);stroke.sync();stroke.close()
    stroke=sym.begin(bpy.context,ob,bm,coordinate_only=True)
    stroke.prepare_topology(local=True,vertices=source)
    bmesh.ops.subdivide_edges(bm,edges=list(bm.faces.get(source).edges),cuts=1,use_grid_fill=True)
    stroke.sync()
    assert len(bm.faces)==8 and len(bm.verts)==18
    stroke.rollback();assert len(bm.faces)==2 and len(bm.verts)==8
    bm.free()


def test_explicit_seam_survives_vertex_index_reordering():
    ob,bm=fixture('TOPOLOGY');bmesh.ops.create_grid(bm,x_segments=4,y_segments=3,size=2)
    edge=next(e for e in bm.edges if len(e.link_faces)==2 and all(abs(v.co.x)<1e-8 for v in e.verts))
    state=bpy.context.scene.allset_symmetry
    before=sym.bind_seam(ob,bm,edge,state);saved=tuple(ob.data[sym.SEED])
    bm.verts.sort(key=lambda v:-v.co.y-v.co.x*.1);bm.verts.index_update()
    stroke=sym.begin(bpy.context,ob,bm,coordinate_only=True)
    assert tuple(ob.data[sym.SEED])==saved and len(stroke.pairs)==len(before)
    stroke.close();bm.free()


def test_partial_mapping_stops_at_an_asymmetrical_patch():
    ob,bm=fixture('TOPOLOGY');bmesh.ops.create_grid(bm,x_segments=4,y_segments=4,size=2)
    face=max(bm.faces,key=lambda f:f.calc_center_median().x+f.calc_center_median().y*.1)
    bmesh.ops.triangulate(bm,faces=[face])
    edge=min((e for e in bm.edges if len(e.link_faces)==2 and all(abs(v.co.x)<1e-8 for v in e.verts)),key=lambda e:sum(v.co.y for v in e.verts))
    partial=sym.topology_pairs(bm,[edge],partial=True)
    assert 2<len(partial)<len(bm.verts),(len(partial),len(bm.verts))
    assert not sym.topology_pairs(bm,[edge],partial=False)
    bm.free()


def test_editing_a_topology_seam_disables_symmetry_without_reverting_the_edit():
    ob,bm=fixture('TOPOLOGY');bmesh.ops.create_grid(bm,x_segments=4,y_segments=3,size=2)
    edge=next(e for e in bm.edges if len(e.link_faces)==2 and all(abs(v.co.x)<1e-8 for v in e.verts))
    state=bpy.context.scene.allset_symmetry;sym.bind_seam(ob,bm,edge,state)
    stroke=sym.begin(bpy.context,ob,bm);count=len(bm.verts)
    bmesh.ops.subdivide_edges(bm,edges=[edge],cuts=1)
    stroke.sync()
    assert not state.on and stroke.disabled_reason and sym.SEED not in ob.data
    assert len(bm.verts)>count
    stroke.close();bm.free()


def test_new_mirror_vertices_do_not_inherit_a_bound_seam_marker():
    ob,bm=fixture();bm.verts.layers.int.new(sym.SEED_LAYER)
    v=bm.verts.new((1,0,0));v[bm.verts.layers.int[sym.SEED_LAYER]]=3
    stroke=sym.begin(bpy.context,ob,bm,coordinate_only=True)
    other=stroke.counterpart(v)
    assert other[bm.verts.layers.int[sym.SEED_LAYER]]==0
    stroke.close();bm.free()
