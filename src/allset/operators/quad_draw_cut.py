# SPDX-License-Identifier: GPL-3.0-or-later
"""Quad Draw cuts paired by source edge/factor, before live projection changes distances."""
from collections import defaultdict
import bmesh
from mathutils import Vector
from mathutils.geometry import intersect_line_line_2d,intersect_point_line
from . import mesh_tools,quad_draw_symmetry as symmetry


def factor(t):return round(min(.999,max(.001,float(t))),8)


def connections(ring):
    faces=defaultdict(list)
    for e,t in ring.items():
        for f in e.link_faces:faces[f].append((e,factor(t)))
    if any(len(hits)>2 for hits in faces.values()):raise symmetry.SymmetryError('The cut branches in a non-quad face; choose another edge')
    return faces


def segments(bm,index,t):
    bm.edges.ensure_lookup_table();ring=mesh_tools.edge_ring(bm.edges[index],bm.edges[index].verts[0],factor(t))
    return [(a.verts[0].co.lerp(a.verts[1].co,u),b.verts[0].co.lerp(b.verts[1].co,v))
            for hits in connections(ring).values() if len(hits)==2 for (a,u),(b,v) in [hits]]


class Plan:
    def __init__(self,bm,edge,t,stroke=None):
        self.bm=bm;self.stroke=stroke;self.ends={};self.coords={};self.values=defaultdict(set)
        self.face_connections=defaultdict(list);self.normals={};self.mirror={};self.face_mirror={}
        self.points={};self.new=[];self.intersections={}
        self.hint=edge.verts[0].co.lerp(edge.verts[1].co,factor(t))
        rings=[mesh_tools.edge_ring(edge,edge.verts[0],factor(t))]
        if stroke is not None:
            reflected={}
            for e,u in rings[0].items():
                a,b=e.verts;p,q=stroke.find_pair(a),stroke.find_pair(b)
                other=bm.edges.get((p,q)) if p is not None and q is not None and p is not q else None
                if other is None:raise symmetry.SymmetryError('The opposite cut edge has no matching topology; use a matched region or turn symmetry off')
                reflected[other]=factor(u if other.verts[0] is p else 1-u)
            rings.append(reflected)
        for ring in rings:
            for e,u in ring.items():
                if e.hide or len(e.link_faces)>2 or any(v.hide for v in e.verts) or any(f.hide for f in e.link_faces):
                    raise symmetry.SymmetryError('The cut reaches hidden or non-manifold geometry')
                self.ends[e]=tuple(e.verts);self.coords[e]=tuple(v.co.copy() for v in e.verts)
                self.values[e].add(factor(u))
            for f,hits in connections(ring).items():
                self.normals[f]=f.normal.copy()
                if len(hits)==2 and frozenset(hits) not in [frozenset(pair) for pair in self.face_connections[f]]:
                    self.face_connections[f].append(hits)
        if stroke is not None:
            faces={f for e in self.values for f in e.link_faces}
            stroke.require({v for f in faces for v in f.verts})
            by_ring={frozenset(f.verts):f for f in faces}
            for f in faces:
                mapped=[stroke.find_pair(v) for v in f.verts]
                other=by_ring.get(frozenset(mapped)) if all(v is not None for v in mapped) else None
                if other is None:raise symmetry.SymmetryError('The cut reaches faces without matching symmetry topology')
                self.face_mirror[f]=other
            for e,values in self.values.items():
                a,b=self.ends[e];p,q=stroke.find_pair(a),stroke.find_pair(b);other=bm.edges.get((p,q))
                for u in values:self.mirror[e,u]=(other,factor(u if self.ends[other][0] is p else 1-u))
        self.identity=bm.verts.layers.int.get(symmetry.IDENTITY)
        self.next_id=stroke.next_id if stroke else max((v[self.identity] for v in bm.verts),default=0)+1 if self.identity else 0

    def remember(self,v):
        if self.identity is not None:v[self.identity]=self.next_id;self.next_id+=1
        seed=self.bm.verts.layers.int.get(symmetry.SEED_LAYER)
        if seed is not None:v[seed]=0
        dots=self.bm.verts.layers.int.get('allset_dot')
        if dots is not None:v[dots]=0
        self.new.append(v)

    def split_face(self,regions,a,b):
        edge=self.bm.edges.get((a,b))
        if edge is not None:return edge
        face=next((f for f in a.link_faces if f in regions and b in f.verts),None)
        if face is None:return None
        other,_=bmesh.utils.face_split(face,a,b);regions.add(other)
        return self.bm.edges.get((a,b))

    def connect(self,parent,pairs):
        regions={parent};cuts=[];normal=self.normals[parent]
        drop=max(range(3),key=lambda i:abs(normal[i]));axes=[i for i in range(3) if i!=drop]
        xy=lambda v:Vector((v.co[axes[0]],v.co[axes[1]]))
        for (ea,ta),(eb,tb) in pairs:
            a,b=self.points[ea,ta],self.points[eb,tb]
            edge=self.split_face(regions,a,b)
            if edge is not None:cuts.append(edge);continue
            # Two symmetry cuts can cross inside a self-mirrored face. Split
            # their intersection once and reuse it on both resulting paths.
            found=False
            for cut in list(cuts):
                c,d=cut.verts;hit=intersect_line_line_2d(xy(a),xy(b),xy(c),xy(d))
                if hit is None:continue
                delta=xy(d)-xy(c);u=(hit-xy(c)).dot(delta)/max(delta.length_squared,1e-30)
                if not 1e-8<u<1-1e-8:continue
                _,v=bmesh.utils.edge_split(cut,c,u);self.remember(v);self.intersections[parent]=v
                if self.split_face(regions,a,v) is None or self.split_face(regions,v,b) is None:
                    raise symmetry.SymmetryError('Unable to connect the mirrored cut intersection')
                found=True;break
            if not found:raise symmetry.SymmetryError('The cut cannot be connected inside its source face')

    def apply(self,project=None):
        for edge,values in self.values.items():
            a,b=self.ends[edge];pa,pb=self.coords[edge];start=a;low=0
            for u in sorted(values):
                segment=self.bm.edges.get((start,b))
                if segment is None:raise symmetry.SymmetryError('A cut source edge changed')
                _,v=bmesh.utils.edge_split(segment,start,(u-low)/(1-low));v.co=pa.lerp(pb,u)
                self.remember(v);self.points[edge,u]=v;start=v;low=u
        for f,pairs in self.face_connections.items():self.connect(f,pairs)
        stroke=self.stroke
        if stroke is not None:
            stroke.next_id=self.next_id
            for key,other in self.mirror.items():
                a,b=self.points[key],self.points[other];stroke.pairs[a]=b;stroke.pairs[b]=a
            for f,v in self.intersections.items():
                other=self.intersections.get(self.face_mirror[f])
                if other is None:raise symmetry.SymmetryError('A mirrored cut intersection has no counterpart')
                stroke.pairs[v]=other
        if project is not None:
            seen=set()
            hint=0 if stroke is None else self.hint[stroke.axis] if stroke.about=='OBJECT' else (stroke.mw@self.hint)[stroke.axis]
            for v in self.new:
                if v in seen:continue
                other=stroke.pairs.get(v) if stroke is not None else None
                if stroke is None or stroke.about=='TOPOLOGY':
                    v.co=project(v.co)
                    if other is not None and other is not v:other.co=project(other.co);seen.add(other)
                    if other is v and stroke is not None:stroke.move([v])
                elif other is v:
                    p=project(v.co);v.co=(p+stroke.matrix@p)*.5
                else:
                    signed=v.co[stroke.axis] if stroke.about=='OBJECT' else (stroke.mw@v.co)[stroke.axis]
                    source=v if signed*(1 if hint>=0 else -1)>=0 else other
                    target=other if source is v else v
                    source.co=project(source.co);target.co=stroke.matrix@source.co;seen.add(other)
                seen.add(v)
        self.bm.normal_update()
        if stroke is not None:
            faces={f for v in self.new for f in v.link_faces}
            for face in faces:
                ring=[stroke.find_pair(v) for v in reversed(list(face.verts))]
                if any(v is None for v in ring) or self.bm.faces.get(ring) is None:
                    raise symmetry.SymmetryError('Cut topology does not match across symmetry')
                if any(len(e.link_faces)>2 for e in face.edges):raise symmetry.SymmetryError('The cut would create a non-manifold edge')
        return self.new
