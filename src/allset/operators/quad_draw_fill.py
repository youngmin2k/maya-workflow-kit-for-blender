# SPDX-License-Identifier: GPL-3.0-or-later
"""Screen-space Quad Draw proposals constrained by existing mesh topology."""
import itertools
import math
from collections import defaultdict
import numpy as np


def area(poly):
    return .5*sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(poly,poly[1:]+poly[:1]))


def orient(a,b,c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def inside(poly,p):
    # Strict containment: a shared boundary is not an overlap.
    result=False
    for a,b in zip(poly,poly[1:]+poly[:1]):
        if abs(orient(a,b,p))<1e-5 and min(a[0],b[0])-1e-6<=p[0]<=max(a[0],b[0])+1e-6 and min(a[1],b[1])-1e-6<=p[1]<=max(a[1],b[1])+1e-6:
            return False
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
    def __init__(self, xy, allowed, edges, edge_counts, faces):
        self.xy=np.asarray(xy,dtype=float).reshape(-1,2)
        self.allowed=np.asarray(allowed,dtype=bool)
        self.edges=np.asarray(edges,dtype=np.int32).reshape(-1,2)
        self.counts={tuple(sorted(e)):int(n) for e,n in zip(self.edges.tolist(),edge_counts)}
        self.boundary=self.edges[np.asarray(edge_counts)==1]
        connected=np.zeros(len(self.xy),dtype=bool)
        connected[self.edges.ravel()]=True
        self.connected=np.flatnonzero(connected)
        faces=[tuple(f) for f in faces]
        self.face_sets={frozenset(f) for f in faces}
        groups=defaultdict(list)
        for i,f in enumerate(faces):
            groups[len(f)].append(i)
        boxes=np.empty((len(faces),4),dtype=float)
        front=np.zeros(len(faces),dtype=bool)
        self.directions=set()
        for n,ids in groups.items():
            indices=np.asarray([faces[i] for i in ids],dtype=np.int32)
            points=self.xy[indices]
            following=np.roll(points,-1,axis=1)
            visible=np.sum(points[:,:,0]*following[:,:,1]-points[:,:,1]*following[:,:,0],axis=1)>1e-5
            front[ids]=visible
            boxes[ids,:2]=points.min(axis=1)
            boxes[ids,2:]=points.max(axis=1)
            directed=np.stack((indices[visible],np.roll(indices[visible],-1,axis=1)),axis=-1).reshape(-1,2)
            self.directions.update(map(tuple,directed.tolist()))
        self.faces=[f for i,f in enumerate(faces) if front[i]]
        self.boxes=boxes[front]

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

    def plan(self, mouse, visible=lambda i:True):
        from .preselect import segment_distance
        if len(self.xy)<3:
            return None
        if len(self.boxes):
            b=self.boxes
            at=np.flatnonzero((b[:,0]<=mouse[0])&(b[:,2]>=mouse[0])&(b[:,1]<=mouse[1])&(b[:,3]>=mouse[1]))
            if any(inside(self.polygon(i),mouse) for i in at):
                return None
        distance=((self.xy-mouse)**2).sum(axis=1)
        eligible=np.flatnonzero(self.allowed)
        if not len(eligible):
            return None
        nearest=eligible[np.argsort(distance[eligible])[:8]]
        proposals={frozenset(map(int,c)) for n in (4,3) for c in itertools.combinations(nearest,n)}
        edges=self.boundary
        if len(edges):
            distances,_=segment_distance(mouse,self.xy[edges[:,0]],self.xy[edges[:,1]])
            ok=self.allowed[edges[:,0]]&self.allowed[edges[:,1]]
            ids=np.flatnonzero(ok)
            close=edges[ids[np.argsort(distances[ids])[:8]]]
            # Opposing edges can be farther apart than the nearest eight vertices.
            proposals.update(frozenset(map(int,(*a,*b))) for a,b in itertools.combinations(close,2))
        ordered=[]
        for combo in proposals:
            if len(combo) not in (3,4):
                continue
            ring=self.ring(combo)
            poly=[tuple(self.xy[i]) for i in ring]
            if not inside(poly,mouse):
                continue
            shared=sum(self.counts.get(tuple(sorted((a,b))),0)==1 for a,b in zip(ring,ring[1:]+ring[:1]))
            ordered.append((len(ring)!=4,-shared,abs(area(poly)),ring))
        visibility={}
        for _,_,_,ring in sorted(ordered):
            if not self.valid(ring):
                continue
            for i in ring:
                if i not in visibility:
                    visibility[i]=visible(i)
            if all(visibility[i] for i in ring):
                return ring
        return None
