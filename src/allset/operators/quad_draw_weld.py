# SPDX-License-Identifier: GPL-3.0-or-later
"""Transactional Quad Draw magnet: stable screen targets, topology checks, weld on release."""
import itertools
import math
from collections import defaultdict
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy_extras import view3d_utils


def normal(points):
    result=Vector()
    origin=Vector(points[0])
    for a,b in zip(points,points[1:]+points[:1]):
        result+=(Vector(a)-origin).cross(Vector(b)-origin)
    return result


class Topology:
    def __init__(self, co, faces, share=False):
        self.co=co if share else [Vector(p) for p in co]
        self.faces=[tuple(f) for f in faces]
        self.links=defaultdict(set)
        self.edges=defaultdict(set)
        self.sets=defaultdict(set)
        for fi,face in enumerate(self.faces):
            self.sets[frozenset(face)].add(fi)
            for a,b in zip(face,face[1:]+face[:1]):
                self.links[a].add(fi)
                self.edges[tuple(sorted((a,b)))].add(fi)

    def valid(self, pairs, proposed):
        if not pairs or len(set(pairs.values()))!=len(pairs):
            return not pairs
        affected=set().union(*(self.links[i] for i in (*pairs,*pairs.values())))
        new_faces=[]
        seen=set()
        for fi in affected:
            original=self.faces[fi]
            ring=[]
            for i in original:
                i=pairs.get(i,i)
                if not ring or ring[-1]!=i:
                    ring.append(i)
            if len(ring)>1 and ring[-1]==ring[0]:
                ring.pop()
            key=frozenset(ring)
            if len(key)<3 or len(key)!=len(ring) or key in seen or self.sets.get(key,set())-affected:
                return False
            seen.add(key)
            points=[proposed.get(i,self.co[i]) for i in ring]
            n=normal(points)
            old=normal([self.co[i] for i in original])
            span=max((Vector(a)-Vector(b)).length_squared for a,b in zip(points,points[1:]+points[:1]))
            if n.length_squared<=max(1e-24,span*span*1e-12) or (old.length_squared>1e-20 and n.dot(old)<=0):
                return False
            new_faces.append(ring)
        counts={}
        directions={}
        for ring in new_faces:
            for a,b in zip(ring,ring[1:]+ring[:1]):
                key=tuple(sorted((a,b)))
                counts[key]=counts.get(key,len(self.edges.get(key,set())-affected))+1
                if counts[key]>2:
                    return False
                if key not in directions:
                    directions[key]=[]
                    for fi in self.edges.get(key,set())-affected:
                        f=self.faces[fi]
                        directions[key].extend(x<y for x,y in zip(f,f[1:]+f[:1]) if tuple(sorted((x,y)))==key)
                directions[key].append(a<b)
                if len(directions[key])==2 and directions[key][0]==directions[key][1]:
                    return False
        return True


def choose_pairs(options, proposed, valid):
    """Joint choices for small tweaks, bounded reassignment for extended strips."""
    sources=list(proposed)
    def key(pairs):
        return -len(pairs),sum(options[i].index(t) for i,t in pairs.items())
    if len(sources)<=4:
        ranked=[]
        for targets in itertools.product(*(options[i]+[None] for i in sources)):
            pairs={i:t for i,t in zip(sources,targets) if t is not None}
            if len(set(pairs.values()))==len(pairs):ranked.append(pairs)
        for pairs in sorted(ranked,key=key):
            if valid(pairs,proposed):return pairs
        return {}
    # An augmenting path can move an earlier greedy choice to its second
    # target instead of starving the next endpoint. Candidate lists stay <=3.
    assigned={};owner={};order={source:i for i,source in enumerate(sources)}
    def place(source):
        queue=[source];parents={source:None};seen=set()
        for current in queue:
            for target in options[current]:
                if target in seen:continue
                seen.add(target);previous=owner.get(target)
                if previous is None:
                    while True:
                        assigned[current]=target;owner[target]=current
                        if current==source:return
                        current,target=parents[current]
                if previous not in parents:parents[previous]=(current,target);queue.append(previous)
    for source in sorted(sources,key=lambda i:(len(options[i]),order[i])):place(source)
    if valid(assigned,proposed):return assigned
    # Keep the topology-checked greedy path as a safe fallback when the
    # maximum-cardinality screen assignment has incompatible mesh topology.
    best={}
    for source in sources:
        for target in options[source]:
            pairs={**best,source:target}
            if valid(pairs,proposed):best=pairs;break
    return best


class Magnet:
    """One stroke owns one snapshot; a radius-sized grid avoids per-event full-mesh scans."""
    def __init__(self, context, ob, moving, extra=(), extra_faces=(), exclude=()):
        import bmesh
        from . import quad_draw
        bm=bmesh.from_edit_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        mw=ob.matrix_world.copy()
        self.co=[mw@v.co for v in bm.verts]+[Vector(p) for p in extra]
        self.moving=set(moving)
        excluded=set(exclude)
        self.radius=quad_draw._weld_px(context)
        self.refs=quad_draw.reference_objects(context)
        self.allowed=[v.index for v in bm.verts if v.index not in self.moving and v.index not in excluded and not v.hide and (v.is_boundary or not v.link_faces)]
        # Every changed or duplicate face touches a source/target. Include its edge
        # neighbours too, so edge incidence remains exact without copying all mesh topology.
        relevant=set(self.allowed)|self.moving|excluded
        touched={f for i in relevant if i<len(bm.verts) for f in bm.verts[i].link_faces}
        neighbours=touched|{other for f in touched for e in f.edges for other in e.link_faces}
        faces=[tuple(v.index for v in f.verts) for f in neighbours]
        self.base_count=len(bm.verts);self.base_faces=faces
        self.topology=Topology(self.co,faces+list(extra_faces),share=True)
        self.virtual_faces=list(extra_faces)
        self._bm=bm
        self.bvh=None
        self.key=None
        self.pairs={}
        self.visibility={}
        self.grid={}

    def set_virtual(self,points,faces):
        """Grow a strip without re-reading every existing mesh vertex."""
        self.co[self.base_count:]=[Vector(p) for p in points]
        faces=list(faces)
        if faces!=self.virtual_faces:
            self.topology=Topology(self.co,self.base_faces+faces,share=True)
            self.virtual_faces=faces

    def project(self, context, region, rv3d):
        from . import preselect
        key=(region.width,region.height,tuple(map(tuple,rv3d.perspective_matrix)))
        if key!=self.key:
            self.xy,self.front=preselect.project(self.co,rv3d.perspective_matrix,region.width,region.height)
            self.grid=defaultdict(list)
            for i in self.allowed:
                if self.front[i]:
                    self.grid[self.cell(self.xy[i])].append(i)
            self.key=key
            self.visibility.clear()

    def cell(self, xy):
        return math.floor(xy[0]/self.radius),math.floor(xy[1]/self.radius)

    def visible(self, context, region, rv3d, i):
        if i in self.visibility:
            return self.visibility[i]
        p=self.co[i]
        origin=view3d_utils.region_2d_to_origin_3d(region,rv3d,self.xy[i])
        direction=(p-origin).normalized()
        distance=(p-origin).length
        epsilon=max(1e-5,distance*1e-7)
        if self.bvh is None and self._bm is not None:
            faces=[tuple(v.index for v in f.verts) for f in self._bm.faces if not f.hide and all(v.index not in self.moving for v in f.verts)]
            self.bvh=BVHTree.FromPolygons(self.co,faces) if faces else None
            self._bm=None
        hidden=False
        if self.bvh is not None:
            hit=self.bvh.ray_cast(origin,direction)
            hidden=hit[0] is not None and hit[3]<distance-epsilon
        if not hidden and self.refs:
            from . import live,quad_draw
            hit=live.ray_hit(context,origin,direction,self.refs,True)
            offset=abs(quad_draw.surface_offset(context))
            hidden=hit is not None and (hit[0]-origin).length<distance-epsilon-offset*1.1
        self.visibility[i]=not hidden
        return not hidden

    def query(self, context, region, rv3d, proposed):
        from . import quad_draw
        if quad_draw._weld_px(context) is None:
            self.pairs={}
            return proposed,{}
        self.project(context,region,rv3d)
        options={}
        for source,p in proposed.items():
            point=quad_draw._screen_xy(region,rv3d,p)
            candidates=[]
            if point is not None:
                locked=self.pairs.get(source)
                if locked is not None and self.front[locked] and self.visible(context,region,rv3d,locked) and np.linalg.norm(self.xy[locked]-point)<=self.radius*1.4:
                    candidates.append(locked)
                x,y=self.cell(point)
                near=[i for dx in (-1,0,1) for dy in (-1,0,1) for i in self.grid.get((x+dx,y+dy),())]
                near.sort(key=lambda i:((self.xy[i]-point)**2).sum())
                for i in near:
                    if i not in candidates and np.linalg.norm(self.xy[i]-point)<=self.radius and self.visible(context,region,rv3d,i):
                        candidates.append(i)
                    if len(candidates)>=3:
                        break
            options[source]=candidates
        best=choose_pairs(options,proposed,self.topology.valid)
        self.pairs=best
        result=dict(proposed)
        for i,target in best.items():
            result[i]=self.co[target].copy()
        return result,dict(best)

    def commit(self, bm, source_verts):
        import bmesh
        bm.verts.ensure_lookup_table()
        pairs={source_verts[i]:bm.verts[t] for i,t in self.pairs.items() if i in source_verts}
        if pairs:
            bmesh.ops.weld_verts(bm,targetmap=pairs)
        return len(pairs)
