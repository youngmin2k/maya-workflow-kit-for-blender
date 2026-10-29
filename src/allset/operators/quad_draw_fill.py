# SPDX-License-Identifier: GPL-3.0-or-later
"""Screen-space Quad Draw proposals constrained by existing mesh topology."""
import itertools
import math
from collections import defaultdict
import numpy as np
from mathutils.kdtree import KDTree


def nearest_ids(values, ids, count):
    """Bounded partial selection, with deterministic ordering on ties."""
    if len(ids)>count:
        ids=ids[np.argpartition(values[ids],count-1)[:count]]
    return ids[np.lexsort((ids,values[ids]))]


def area(poly):
    return .5*sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(poly,poly[1:]+poly[:1]))


def orient(a,b,c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def inside(poly,p,strict=True):
    # Strict containment: a shared boundary is not an overlap.
    result=False
    for a,b in zip(poly,poly[1:]+poly[:1]):
        if abs(orient(a,b,p))<1e-5 and min(a[0],b[0])-1e-6<=p[0]<=max(a[0],b[0])+1e-6 and min(a[1],b[1])-1e-6<=p[1]<=max(a[1],b[1])+1e-6:
            return not strict
        if (a[1]>p[1]) != (b[1]>p[1]) and p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:
            result=not result
    return result


def overlaps(a,b):
    for p,q in zip(a,a[1:]+a[:1]):
        for r,s in zip(b,b[1:]+b[:1]):
            if orient(p,q,r)*orient(p,q,s)<-1e-8 and orient(r,s,p)*orient(r,s,q)<-1e-8:
                return True
    # Edge midpoints also catch a triangle drawn inside an existing quad, whose
    # vertices all sit on the quad's boundary.
    for first,second in ((a,b),(b,a)):
        center=(sum(p[0] for p in first)/len(first),sum(p[1] for p in first)/len(first))
        if inside(second,center):
            return True
        if any(inside(second,p) for p in first):
            return True
        if any(inside(second,((p[0]+q[0])*.5,(p[1]+q[1])*.5)) for p,q in zip(first,first[1:]+first[:1])):
            return True
    return False


class ScreenFill:
    """One bounded projection cache; queries examine nearby boundary edges and points."""
    def __init__(self, xy, allowed, edges, edge_counts, faces, world=None, groups=None):
        self.xy=np.asarray(xy,dtype=float).reshape(-1,2)
        self.allowed=np.asarray(allowed,dtype=bool)
        self.edges=np.asarray(edges,dtype=np.int32).reshape(-1,2)
        usable=self.allowed[self.edges[:,0]]&self.allowed[self.edges[:,1]]
        self.counts={tuple(sorted(e)):int(n) for e,n in zip(self.edges[usable].tolist(),np.asarray(edge_counts)[usable])}
        self.boundary=self.edges[np.asarray(edge_counts)==1]
        self.world=None if world is None else np.asarray(world,dtype=float)
        self.previous=None
        self.adjacency=defaultdict(list)
        for a,b in self.boundary.tolist():
            self.adjacency[a].append(b)
            self.adjacency[b].append(a)
        connected=np.zeros(len(self.xy),dtype=bool)
        connected[self.edges.ravel()]=True
        self.connected=np.flatnonzero(connected)
        self.connected=self.connected[self.allowed[self.connected]]
        eligible=np.flatnonzero(self.allowed)
        self.loose_ids=eligible[~connected[eligible]]
        self.tree=KDTree(len(eligible))
        for i in eligible:
            self.tree.insert((*self.xy[i],0),int(i))
        self.tree.balance()
        if groups is None:
            by_size=defaultdict(list)
            for f in faces:by_size[len(f)].append(tuple(f))
            groups=[np.asarray(fs,dtype=np.int32) for fs in by_size.values()]
        self.face_sets=set();self.normals={};self.directions=set()
        self.faces=[];boxes=[]
        for indices in groups:
            if not len(indices):continue
            n=indices.shape[1]
            permitted=self.allowed[indices].all(axis=1)
            self.face_sets.update(map(frozenset,indices[permitted].tolist()))
            points=self.xy[indices]
            if self.world is not None:
                world=self.world[indices]
                normals=np.cross(world[:,1]-world[:,0],world[:,2]-world[:,0])
                normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-12)
                following_ids=np.roll(indices,-1,axis=1)
                for k in range(n):
                    aa,bb=indices[:,k],following_ids[:,k]
                    mask=self.allowed[aa]&self.allowed[bb]
                    for a,b,normal in zip(aa[mask],bb[mask],normals[mask]):
                        edge=(min(int(a),int(b)),max(int(a),int(b)))
                        if self.counts.get(edge)==1:self.normals[edge]=normal
            following=np.roll(points,-1,axis=1)
            visible=np.sum(points[:,:,0]*following[:,:,1]-points[:,:,1]*following[:,:,0],axis=1)>1e-5
            boxes.append(np.column_stack((points[visible].min(axis=1),points[visible].max(axis=1))))
            self.faces.extend(indices[visible].tolist())
            directed=np.stack((indices[visible],np.roll(indices[visible],-1,axis=1)),axis=-1).reshape(-1,2)
            directed=directed[self.allowed[directed[:,0]]&self.allowed[directed[:,1]]]
            self.directions.update(map(tuple,directed.tolist()))
        self.boxes=np.concatenate(boxes) if boxes else np.empty((0,4))

    def polygon(self,i):
        return self.xy[list(self.faces[i])].tolist()

    def ring(self, combo):
        center=self.xy[list(combo)].mean(axis=0)
        return tuple(sorted(combo,key=lambda i:math.atan2(self.xy[i,1]-center[1],self.xy[i,0]-center[0])))

    def valid(self, ring):
        if frozenset(ring) in self.face_sets:
            return False
        poly=[tuple(self.xy[i]) for i in ring]
        if area(poly)<1e-4 or any(abs(orient(poly[k-1],poly[k],poly[(k+1)%len(poly)]))<1e-5 for k in range(len(poly))):
            return False
        if self.world is not None:
            p=self.world[list(ring)]
            normals=np.cross(p[1:-1]-p[0],p[2:]-p[0])
            lengths=np.linalg.norm(normals,axis=1)
            if np.any(lengths<1e-12):
                return False
            normals/=lengths[:,None]
            # A screen-space polygon can connect folded or opposite-facing sheets.
            if len(normals)>1 and float(normals[0]@normals[1])<=0:
                return False
            normal=normals.mean(axis=0)
            for a,b in zip(ring,ring[1:]+ring[:1]):
                neighbour=self.normals.get(tuple(sorted((a,b))))
                if neighbour is not None and float(neighbour@normal)<-.05:
                    return False
        for a,b in zip(ring,ring[1:]+ring[:1]):
            if self.counts.get(tuple(sorted((a,b))),0)>=2:
                return False
            if (a,b) in self.directions:
                return False
            # Do not skip an existing boundary vertex and create a T-junction.
            p,q=self.xy[a],self.xy[b]
            ids=self.connected
            points=self.xy[ids]
            near=ids[(points[:,0]>=min(p[0],q[0])-1e-5)&(points[:,0]<=max(p[0],q[0])+1e-5)
                     &(points[:,1]>=min(p[1],q[1])-1e-5)&(points[:,1]<=max(p[1],q[1])+1e-5)]
            if any(i not in ring and self.allowed[i] and abs(orient(p,q,self.xy[i]))<1e-5 for i in near):
                return False
        lo=np.min(poly,axis=0);hi=np.max(poly,axis=0)
        if len(self.boxes):
            boxes=self.boxes
            near=np.flatnonzero((boxes[:,0]<hi[0]-1e-5)&(boxes[:,2]>lo[0]+1e-5)&(boxes[:,1]<hi[1]-1e-5)&(boxes[:,3]>lo[1]+1e-5))
            if any(overlaps(poly,self.polygon(i)) for i in near):
                return False
        return True

    def quality(self, ring):
        """Dimensionless corner/skew cost, with continuation of adjacent edge flow."""
        p=self.xy[list(ring)]
        edges=np.roll(p,-1,axis=0)-p
        lengths=np.linalg.norm(edges,axis=1)
        unit=edges/np.maximum(lengths[:,None],1e-9)
        corner=np.abs(np.sum(unit*np.roll(unit,1,axis=0),axis=1)).mean()
        aspect=math.log(max(float(lengths.max()/max(lengths.min(),1e-9)),1.0))
        flow=[]
        for k,a in enumerate(ring):
            for b in self.adjacency.get(a,()):
                if b not in ring:
                    delta=self.xy[b]-self.xy[a]
                    size=float(np.linalg.norm(delta))
                    if size>1e-6:
                        flow.append(1-max(abs(float(delta@unit[k]))/size,
                                          abs(float(delta@unit[k-1]))/size))
        return float(corner)+aspect*.2+(sum(flow)/len(flow)*.35 if flow else 0)

    def plan(self, mouse, visible=lambda i:True):
        from .preselect import segment_distance
        if len(self.xy)<3:
            return None
        previous=self.previous
        # A closed four-edge hole is unambiguous. Its topology and projection are
        # immutable for this cache generation; only visibility needs refreshing.
        if previous and len(previous)==4 and all(self.counts.get(tuple(sorted(e)))==1
                for e in zip(previous,previous[1:]+previous[:1])):
            poly=[tuple(self.xy[i]) for i in previous]
            if inside(poly,mouse) and not any(inside(poly,tuple(self.xy[i])) for i in self.loose_ids) and all(visible(i) for i in previous):
                return previous
        if len(self.boxes):
            b=self.boxes
            at=np.flatnonzero((b[:,0]<=mouse[0])&(b[:,2]>=mouse[0])&(b[:,1]<=mouse[1])&(b[:,3]>=mouse[1]))
            if any(inside(self.polygon(i),mouse,strict=False) for i in at):
                self.previous=None
                return None
        distance=((self.xy-mouse)**2).sum(axis=1)
        eligible=np.flatnonzero(self.allowed)
        if not len(eligible):
            return None
        nearest=np.asarray([i for _,i,_ in self.tree.find_n((*mouse,0),min(8,len(eligible)))],dtype=int)
        proposals={frozenset(map(int,c)) for n in (4,3) for c in itertools.combinations(nearest,n)}
        edges=self.boundary
        if len(edges):
            distances,_=segment_distance(mouse,self.xy[edges[:,0]],self.xy[edges[:,1]])
            ok=self.allowed[edges[:,0]]&self.allowed[edges[:,1]]
            ids=np.flatnonzero(ok)
            close=edges[nearest_ids(distances,ids,12)]
            # Opposing edges can be farther apart than the nearest eight vertices.
            proposals.update(frozenset(map(int,(*a,*b))) for a,b in itertools.combinations(close,2))
            # Follow local border paths as well as proximity. A short nearby edge
            # should not hide the fourth corner of a larger hole. Bounded even at
            # branch vertices: no unbounded traversal or all-mesh combinations.
            local=set(map(int,close.ravel()))
            paths=[(i,) for i in sorted(local)]
            for _ in range(3):
                paths=list(itertools.islice(((*p,n) for p in paths for n in self.adjacency[p[-1]]
                       if n not in p and self.allowed[n]),192))
                proposals.update(frozenset(p) for p in paths if len(p) in (3,4))
        ordered=[]
        for combo in proposals:
            if len(combo) not in (3,4):
                continue
            ring=self.ring(combo)
            poly=[tuple(self.xy[i]) for i in ring]
            if not inside(poly,mouse):
                continue
            shared=sum(self.counts.get(tuple(sorted((a,b))),0)==1 for a,b in zip(ring,ring[1:]+ring[:1]))
            size=abs(area(poly))
            # Closed holes and opposing edges give useful evidence, but cannot
            # override a much more local dot-to-border quad (eyelids, lips).
            radius2=float(distance[list(ring)].mean())
            ordered.append((len(ring)!=4, shared, size, radius2,ring))
        if not ordered:
            self.previous=None
            return None
        local=min(row[3] for row in ordered if row[0]==min(r[0] for r in ordered))
        ranked=[]
        for triangle,shared,size,radius2,ring in ordered:
            locality=math.log(max(radius2/max(local,1e-9),1))
            # Two opposing shared edges stay stronger than incidental nearby
            # dots, while distant three-edge proposals no longer swallow them.
            context_bonus=(.55 if shared>=2 else .2 if shared else 0)
            score=self.quality(ring)+1.3*locality-context_bonus-(.08 if ring==previous else 0)
            ranked.append((triangle,score,size,ring))
        visibility={}
        for *_,ring in sorted(ranked):
            if not self.valid(ring):
                continue
            for i in ring:
                if i not in visibility:
                    visibility[i]=visible(i)
            if all(visibility[i] for i in ring):
                self.previous=ring
                return ring
        self.previous=None
        return None
