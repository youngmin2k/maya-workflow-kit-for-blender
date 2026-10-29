# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit evaluated-reference seams and bounded triangle correspondence for posed Quad Draw."""
from collections import OrderedDict
import hashlib
import bmesh
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform
from bpy_extras import view3d_utils

SEAM='allset_qd_reference_seam'
SIGNATURE='allset_qd_reference_topology'
_cache=OrderedDict()
MAX_ENTRIES=4
MAX_TRIANGLES=2_000_000


def clear():_cache.clear()


def signature(mesh):
    digest=hashlib.blake2b(digest_size=16)
    for collection,prop,size in ((mesh.edges,'vertices',len(mesh.edges)*2),(mesh.loops,'vertex_index',len(mesh.loops)),(mesh.polygons,'loop_total',len(mesh.polygons))):
        data=np.empty(size,dtype='int32');collection.foreach_get(prop,data);digest.update(data.tobytes())
    return f'{len(mesh.vertices)}:{len(mesh.edges)}:{len(mesh.polygons)}:'+digest.hexdigest()


def bind(context,ob,edge_index,axis,partial=True):
    from .quad_draw_symmetry import topology_pairs,SymmetryError
    mesh=ob.evaluated_get(context.evaluated_depsgraph_get()).data
    if not 0<=edge_index<len(mesh.edges):raise SymmetryError('Reference topology changed; pick its seam again')
    ends=tuple(mesh.edges[edge_index].vertices)
    bm=bmesh.new()
    try:
        bm.from_mesh(mesh);bm.verts.ensure_lookup_table();edge=bm.edges.get(tuple(bm.verts[i] for i in ends))
        if edge is None or len(edge.link_faces)!=2 or not topology_pairs(bm,[edge],partial):
            raise SymmetryError('Pick a manifold reference edge between matching halves')
    finally:bm.free()
    ob[SEAM]=list(ends);ob[SIGNATURE]=signature(mesh);clear()
    return ends


def pick(context,region,rv3d,mouse):
    from . import live,preselect,quad_draw
    origin=view3d_utils.region_2d_to_origin_3d(region,rv3d,mouse)
    direction=view3d_utils.region_2d_to_vector_3d(region,rv3d,mouse)
    best=None
    for ob in quad_draw.reference_objects(context):
        hit=live.tree(context,ob).ray_cast(origin,direction)
        if hit[0] is None:continue
        mesh=ob.evaluated_get(context.evaluated_depsgraph_get()).data
        if hit[2] is None or not 0<=hit[2]<len(mesh.polygons):continue
        face=mesh.polygons[hit[2]]
        for loop in range(face.loop_start,face.loop_start+face.loop_total):
            edge=mesh.edges[mesh.loops[loop].edge_index]
            points=[ob.matrix_world@mesh.vertices[i].co for i in edge.vertices]
            xy=[quad_draw._screen_xy(region,rv3d,p) for p in points]
            if any(p is None for p in xy):continue
            distances,_=preselect.segment_distance(mouse,np.asarray([xy[0]]),np.asarray([xy[1]]));distance=float(distances[0])
            rank=(hit[3],distance)
            if distance<=10*quad_draw._ui_scale(context) and (best is None or rank<best[0]):best=rank,ob,edge.index,points
    return best[1:] if best else None


class ReferenceMap:
    def __init__(self,context,ob,axis):
        from .quad_draw_symmetry import topology_pairs,SymmetryError
        from . import live
        mesh=ob.evaluated_get(context.evaluated_depsgraph_get()).data
        bound=tuple(ob.get(SEAM,()))
        partial=context.scene.allset_symmetry.allow_partial
        if bound and (len(bound)!=2 or ob.get(SIGNATURE)!=signature(mesh)):
            raise SymmetryError('Reference topology changed; use Pick Reference Seam again')
        bm=bmesh.new()
        try:
            bm.from_mesh(mesh);bm.verts.ensure_lookup_table();bm.verts.index_update()
            if bound:
                seeds=[bm.edges.get(tuple(bm.verts[i] for i in bound))]
                if seeds[0] is None:raise SymmetryError('Reference seam is no longer an edge')
            else:
                epsilon=max(ob.dimensions)*1e-5+1e-8
                seeds=[e for e in bm.edges if len(e.link_faces)==2 and all(abs(v.co[axis])<=epsilon for v in e.verts)]
            pairs=topology_pairs(bm,seeds,partial)
            if not pairs:raise SymmetryError('No matching reference seam; use Pick Reference Seam')
            mapping=np.full(len(mesh.vertices),-1,dtype='int32')
            for v,other in pairs.items():mapping[v.index]=other.index
        finally:bm.free()
        mesh.calc_loop_triangles();tri=np.empty(len(mesh.loop_triangles)*3,dtype='int32');mesh.loop_triangles.foreach_get('vertices',tri);tri=tri.reshape(-1,3)
        tri=tri[(mapping[tri]>=0).all(axis=1)]
        if not len(tri):raise SymmetryError('Reference seam has no paired surface triangles')
        co=np.empty(len(mesh.vertices)*3);mesh.vertices.foreach_get('co',co);co=co.reshape(-1,3)
        matrix=np.asarray(ob.matrix_world);self.co=co@matrix[:3,:3].T+matrix[:3,3]
        self.tri=tri;self.target=mapping[tri];self.triangles=len(tri)
        self.bytes=self.co.nbytes+self.tri.nbytes+self.target.nbytes
        self.tree=BVHTree.FromPolygons(self.co,self.tri,all_triangles=True)
        self.surface=live.tree(context,ob)
        self.tolerance=max(float(np.ptp(self.co,axis=0).max())*1e-6,1e-9)

    def point(self,world,offset):
        from .quad_draw_symmetry import SymmetryError
        p,normal,index,distance=self.tree.find_nearest(world)
        if p is None:raise SymmetryError('No paired reference triangle near this point')
        nearest=self.surface.find_nearest(world)
        if nearest[0] is not None and distance>nearest[3]+self.tolerance:
            raise SymmetryError('The nearest reference patch has no topology counterpart')
        source=[Vector(p) for p in self.co[self.tri[index]]]
        target=[Vector(p) for p in self.co[self.target[index]]]
        mapped=barycentric_transform(p,*source,*target)
        normal=(target[2]-target[0]).cross(target[1]-target[0]).normalized()
        return distance,mapped+normal*offset


def get(context,ob,axis):
    from . import live
    surface=live.tree(context,ob)
    key=(ob.session_uid,surface,axis,tuple(ob.get(SEAM,())),ob.get(SIGNATURE,''),context.scene.allset_symmetry.allow_partial)
    if key in _cache:_cache.move_to_end(key);return _cache[key]
    value=ReferenceMap(context,ob,axis)
    for stale in list(_cache):
        if stale[0]==ob.session_uid:del _cache[stale]
    if value.triangles<=MAX_TRIANGLES:
        _cache[key]=value
        while len(_cache)>MAX_ENTRIES or sum(v.triangles for v in _cache.values())>MAX_TRIANGLES:_cache.popitem(last=False)
    return value


def point(context,ob,co,axis):
    from . import quad_draw,live
    from .quad_draw_symmetry import SymmetryError
    world=ob.matrix_world@co;best=None
    for reference in quad_draw.reference_objects(context):
        hit=live.tree(context,reference).find_nearest(world)
        if hit[0] is not None and (best is None or hit[3]<best[0]):best=hit[3],reference
    if best is None:raise SymmetryError('Topology symmetry needs a paired live reference for new points')
    mapped=get(context,best[1],axis).point(world,quad_draw.surface_offset(context))[1]
    return ob.matrix_world.inverted_safe()@mapped
