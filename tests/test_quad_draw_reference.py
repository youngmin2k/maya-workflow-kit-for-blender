"""Evaluated posed-reference seams, correspondence lifetime and atomic fast cuts."""
import bpy,bmesh,tempfile
from pathlib import Path
from importlib import import_module
from mathutils import Vector,Matrix
from types import SimpleNamespace
import kit
q=import_module(kit.MODULE+'.operators.quad_draw')
r=import_module(kit.MODULE+'.operators.quad_draw_reference')
s=import_module(kit.MODULE+'.operators.quad_draw_symmetry')
live=import_module(kit.MODULE+'.operators.live')

def reference(name='posed_reference',bind=True):
    bm=bmesh.new();bmesh.ops.create_grid(bm,x_segments=4,y_segments=4,size=2)
    seam=next(e for e in bm.edges if len(e.link_faces)==2 and all(abs(v.co.x)<1e-6 for v in e.verts))
    bm.verts.index_update();ends={v.index for v in seam.verts}
    for v in bm.verts:
        if v.co.x>0:v.co.z=v.co.x*.5
        v.co=Matrix.Translation((5,7,3))@Matrix.Rotation(.4,4,'Z')@v.co
    me=bpy.data.meshes.new(name);bm.to_mesh(me);bm.free()
    ob=bpy.data.objects.new(name,me);bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    bpy.context.scene.allset_symmetry.allow_partial=True
    if bind:r.bind(bpy.context,ob,next(e.index for e in me.edges if set(e.vertices)==ends),0)
    return ob

def clean():
    if bpy.context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
    live.set_objects(bpy.context.scene,[]);r.clear()

def test_explicit_reference_seam_maps_posed_surface_away_from_axis():
    ob=reference();mapping=r.get(bpy.context,ob,0)
    transform=Matrix.Translation((5,7,3))@Matrix.Rotation(.4,4,'Z')
    distance,p=mapping.point(transform@Vector((1,.3,.5)),0)
    assert distance<1e-5 and (p-transform@Vector((-1,.3,0))).length<1e-5,p
    # Offset is applied along the destination normal, rather than the view ray.
    _,offset=mapping.point(transform@Vector((1,.3,.5)),.02)
    assert abs((offset-p).length-.02)<1e-5
    clean()

def test_reference_binding_persists_and_rejects_same_count_connectivity_changes():
    ob=reference();fingerprint=r.signature(ob.data)
    path=Path(tempfile.gettempdir())/'allset_qd_reference_test.blend'
    try:
        bpy.data.libraries.write(str(path),{ob})
        with bpy.data.libraries.load(str(path)) as (source,target):target.objects=[ob.name]
        restored=target.objects[0];bpy.context.scene.collection.objects.link(restored)
        bpy.context.view_layer.update()
        assert restored.get(r.SIGNATURE)==fingerprint
        assert len(r.get(bpy.context,restored,0).tri)>0
        # Same vertex/edge/face counts, changed connectivity: IDs alone are unsafe.
        edge=restored.data.edges[0];edge.vertices=(edge.vertices[0],(edge.vertices[1]+1)%len(restored.data.vertices))
        restored.data.update();bpy.context.view_layer.update();live._trees.clear();r.clear()
        assert r.signature(restored.data)!=fingerprint
        try:r.get(bpy.context,restored,0)
        except s.SymmetryError as ex:assert 'topology changed' in str(ex)
        else:raise AssertionError('stale bound seam must not silently map rewired reference')
    finally:
        path.unlink(missing_ok=True);clean()

def test_reference_cache_reuses_target_edits_and_invalidates_reference_revisions():
    ob=reference();before=len(bpy.data.meshes);first=r.get(bpy.context,ob,0)
    assert r.get(bpy.context,ob,0) is first
    # Target mesh updates must not invalidate the expensive reference map.
    me=bpy.data.meshes.new('retopo_target');me.from_pydata([(0,0,0)],[],[]);me.update();bpy.context.view_layer.update()
    assert r.get(bpy.context,ob,0) is first
    ob.location.x+=1;bpy.context.view_layer.update();live.changed(None,bpy.context.evaluated_depsgraph_get())
    second=r.get(bpy.context,ob,0);assert second is not first
    ob.data.vertices[0].co.z+=.1;ob.data.update();bpy.context.view_layer.update();live.changed(None,bpy.context.evaluated_depsgraph_get())
    assert r.get(bpy.context,ob,0) is not second
    for i in range(r.MAX_ENTRIES+2):r.get(bpy.context,reference('cache_'+str(i)),0)
    assert len(r._cache)<=r.MAX_ENTRIES and sum(v.triangles for v in r._cache.values())<=r.MAX_TRIANGLES
    # No to_mesh() IDs survive any reference build; the six explicit fixtures do.
    assert len(bpy.data.meshes)==before+1+r.MAX_ENTRIES+2
    r.clear();assert not r._cache
    clean()

def test_strict_reference_mode_does_not_reuse_partial_correspondence():
    ob=reference(bind=False);bm=bmesh.new();bm.from_mesh(ob.data)
    corner=max(bm.faces,key=lambda f:f.calc_center_median().x+f.calc_center_median().y)
    bmesh.ops.triangulate(bm,faces=[corner]);bm.to_mesh(ob.data);bm.free();bpy.context.view_layer.update()
    inverse=(Matrix.Translation((5,7,3))@Matrix.Rotation(.4,4,'Z')).inverted()
    edge=next(e for e in ob.data.edges if all(abs((inverse@ob.data.vertices[i].co).x)<1e-5 for i in e.vertices))
    r.bind(bpy.context,ob,edge.index,0,True)
    mapping=r.get(bpy.context,ob,0);assert mapping.triangles>0
    paired={tuple(sorted(tri)) for tri in mapping.tri}
    evaluated=ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).data;evaluated.calc_loop_triangles()
    unmatched=next(tri for tri in evaluated.loop_triangles if tuple(sorted(tri.vertices)) not in paired)
    point=sum((ob.matrix_world@evaluated.vertices[i].co for i in unmatched.vertices),Vector())/3
    try:mapping.point(point,0)
    except s.SymmetryError as ex:assert 'no topology counterpart' in str(ex)
    else:raise AssertionError('partial mode must not project an unmatched patch onto a remote paired patch')
    far=reference('far_paired_surface');far.location.x+=20;bpy.context.view_layer.update()
    live.set_objects(bpy.context.scene,[ob,far])
    try:r.point(bpy.context,ob,point,0)
    except s.SymmetryError:pass
    else:raise AssertionError('an unrelated live surface must not supply a missing counterpart')
    bpy.context.scene.allset_symmetry.allow_partial=False
    try:r.get(bpy.context,ob,0)
    except s.SymmetryError:pass
    else:raise AssertionError('strict symmetry must reject unmatched reference topology')
    bpy.context.scene.allset_symmetry.allow_partial=True;clean()

def test_new_dot_preview_coordinates_match_committed_topology_counterparts():
    ref=reference();live.set_objects(bpy.context.scene,[ref])
    me=bpy.data.meshes.new('new_patch');ob=bpy.data.objects.new('new_patch',me);bpy.context.scene.collection.objects.link(ob)
    bm=bmesh.new();bm.verts.layers.int.new(q.DOT_LAYER);s.ensure_identity(bm)
    state=bpy.context.scene.allset_symmetry;state.on=True;state.about='TOPOLOGY';state.axis='X'
    transform=Matrix.Translation((5,7,3))@Matrix.Rotation(.4,4,'Z')
    points=[transform@Vector(p) for p in ((.3,0,.15),(.9,0,.45),(.9,.5,.45),(.3,.5,.15))]
    expected=[r.point(bpy.context,ob,p,0) for p in points]
    stroke=s.begin(bpy.context,ob,bm,coordinate_only=True);stroke.prepare_topology(local=True)
    verts=[q.add_dot(bm,p) for p in points];bm.faces.new(verts);stroke.sync()
    assert len(bm.faces)==2 and len(bm.verts)==8
    assert all((stroke.pairs[v].co-p).length<1e-5 for v,p in zip(verts,expected))
    stroke.rollback();assert not bm.verts and not stroke.pairs and stroke.backup is None
    bm.free();clean()

def test_fast_cut_operator_rollback_restores_uv_and_custom_layers():
    clean();me=bpy.data.meshes.new('fast_cut');ob=bpy.data.objects.new('fast_cut',me);bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active=ob;ob.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
    bm=bmesh.from_edit_mesh(me);bmesh.ops.create_grid(bm,x_segments=4,y_segments=4,size=2)
    uv=bm.loops.layers.uv.new('UVMap');attribute=bm.faces.layers.int.new('face_marker')
    for f in bm.faces:
        f[attribute]=73
        for loop in f.loops:loop[uv].uv=(loop.vert.co.x*.25+.5,loop.vert.co.y*.25+.5)
    q._indices(bm);bmesh.update_edit_mesh(me)
    edge=next(e for e in bm.edges if all(v.co.x<-.1 for v in e.verts))
    state=bpy.context.scene.allset_symmetry;state.on=True;state.about='WORLD';state.axis='X'
    operator=SimpleNamespace(_ob=ob.name,_refs=[],_sym=s.begin(bpy.context,ob,bm,coordinate_only=True),report=lambda *_:None)
    cut=import_module(kit.MODULE+'.operators.quad_draw_cut');original=q.component_at,cut.Plan.apply
    counts=(len(bm.verts),len(bm.edges),len(bm.faces));meshes=len(bpy.data.meshes)
    q.component_at=lambda *a,**kw:('EDGE',edge.index,.35)
    native=cut.Plan.apply
    def fail_after_edit(self,project):native(self,project);raise s.SymmetryError('injected post-edit failure')
    cut.Plan.apply=fail_after_edit
    try:
        area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D');region=next(rg for rg in area.regions if rg.type=='WINDOW')
        with bpy.context.temp_override(area=area,region=region):result=q.ALLSET_OT_quad_draw._loop(operator,bpy.context,(0,0))
        assert result=={'CANCELLED'} and operator._sym is None
        assert (len(bm.verts),len(bm.edges),len(bm.faces))==counts and len(bpy.data.meshes)==meshes
        uv=bm.loops.layers.uv['UVMap'];attribute=bm.faces.layers.int['face_marker']
        assert all(f[attribute]==73 for f in bm.faces)
        assert all((l[uv].uv-Vector((l.vert.co.x*.25+.5,l.vert.co.y*.25+.5))).length<1e-6 for f in bm.faces for l in f.loops)
    finally:q.component_at,cut.Plan.apply=original;clean()
