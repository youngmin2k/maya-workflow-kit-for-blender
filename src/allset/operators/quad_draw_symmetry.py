# SPDX-License-Identifier: GPL-3.0-or-later
"""Stroke-local symmetry for BMesh operations, independent of native transform mirroring.

Pairs contain BMVert references, not indices which cut/weld can renumber. Coordinate
updates touch only the edited components; topology replay happens at operation commit.
"""
import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

IDENTITY='allset_qd_identity'


def ensure_identity(bm):
    return bm.verts.layers.int.get(IDENTITY) or bm.verts.layers.int.new(IDENTITY)


def reflection(ob, about, axis):
    matrix=Matrix.Identity(4)
    matrix[axis][axis]=-1
    return matrix if about=='OBJECT' else ob.matrix_world.inverted_safe()@matrix@ob.matrix_world


SEED='allset_qd_topology_seam'
SEED_LAYER='allset_qd_seam'


def seed_ids(ob,bm):
    flags=bm.verts.layers.int.get(SEED_LAYER);identity=bm.verts.layers.int.get(IDENTITY)
    if flags is not None and identity is not None:
        return tuple(v[identity] for v in bm.verts if v[flags])
    return tuple(ob.data.get(SEED,()))


def topology_pairs(bm,seeds,partial=True):
    """Reflect opposite face loops from a seam; stop at unmatched regions in partial mode."""
    pairs={};visited={};queue=[]
    for edge in seeds:
        if len(edge.link_faces)!=2:continue
        a,b=edge.verts;pairs[a]=a;pairs[b]=b
        queue.append((edge.link_faces[0],edge.link_faces[1],a))
    while queue:
        left,right,a=queue.pop()
        if left in visited:
            if visited[left] is not right and not partial:return {}
            continue
        ls=list(left.verts);rs=list(right.verts)
        if len(ls)!=len(rs) or a not in ls or pairs.get(a) not in rs:
            if partial:continue
            return {}
        n=len(ls);li=ls.index(a);ri=rs.index(pairs[a]);candidate={};valid=True
        for k in range(n):
            x,y=ls[(li+k)%n],rs[(ri-k)%n]
            for v,other in ((x,y),(y,x)):
                if (v in pairs and pairs[v] is not other) or (v in candidate and candidate[v] is not other):valid=False
                candidate[v]=other
        if not valid:
            if partial:continue
            return {}
        pairs.update(candidate);visited[left]=right;visited[right]=left
        for loop in left.loops:
            u,v=loop.vert,loop.link_loop_next.vert
            mirror=bm.edges.get((pairs[u],pairs[v]))
            lf=[f for f in loop.edge.link_faces if f is not left]
            rf=[f for f in mirror.link_faces if f is not right] if mirror else []
            if mirror is None or len(lf)!=len(rf) or len(lf)>1:
                if not partial:return {}
                continue
            if lf:queue.append((lf[0],rf[0],u))
    return pairs if any(a is not b for a,b in pairs.items()) else {}


def stable_identities(bm,seed=()):
    layer=ensure_identity(bm)
    values=[v[layer] for v in bm.verts];used=set(values);next_id=max(used,default=0)+1;seen=set()
    for identity in seed:
        if values.count(identity)!=1:raise SymmetryError('Topology seam identity changed; pick the seam again')
    for v in bm.verts:
        identity=v[layer]
        if identity<=0 or identity in seen:
            identity=next_id;next_id+=1;v[layer]=identity
        seen.add(identity)
    return layer,next_id


def topology_mapping(ob,bm,sym):
    """Explicit stored seam first, active selected edge second, legacy axis seam last."""
    ids=seed_ids(ob,bm)
    if ids:
        layer=bm.verts.layers.int.get(IDENTITY)
        vertices=[v for v in bm.verts if layer is not None and v[layer] in ids]
        edge=bm.edges.get(vertices) if len(vertices)==2 else None
        if edge is None or len(edge.link_faces)!=2:raise SymmetryError('The topology seam changed; pick a new seam edge')
        seeds=[edge]
    else:
        active=bm.select_history.active
        if isinstance(active,bmesh.types.BMEdge) and len(active.link_faces)==2:seeds=[active]
        else:
            axis='XYZ'.index(sym.axis)
            extent=max((v.co.length for v in bm.verts),default=0)
            eps=max(extent*1e-5,1e-8)
            seeds=[e for e in bm.edges if len(e.link_faces)==2 and all(abs(v.co[axis])<=eps for v in e.verts)]
    return topology_pairs(bm,seeds,getattr(sym,'allow_partial',True))


def bind_seam(ob,bm,edge,sym):
    if len(edge.link_faces)!=2:raise SymmetryError('Choose a manifold edge between the two symmetrical halves')
    # Adding the identity layer can invalidate element wrappers: keep indices first.
    bm.verts.index_update();indices=[v.index for v in edge.verts]
    layer,_=stable_identities(bm)
    flags=bm.verts.layers.int.get(SEED_LAYER) or bm.verts.layers.int.new(SEED_LAYER)
    bm.verts.ensure_lookup_table();vertices=[bm.verts[i] for i in indices]
    edge=bm.edges.get(vertices)
    pairs=topology_pairs(bm,[edge],getattr(sym,'allow_partial',True))
    if not pairs:raise SymmetryError('No matching topology around this edge; choose a seam without straddling faces')
    for v in bm.verts:v[flags]=0
    for v in vertices:v[flags]=3  # binding + active state, captured by native edit Undo
    ob.data[SEED]=[v[layer] for v in vertices]
    return pairs


class SymmetryError(ValueError):
    pass


class Stroke:
    def __init__(self,context,ob,bm,backup=True,coordinate_only=False,mapping=None):
        from . import symmetry
        sym=symmetry.state(context.scene)
        layer,self.next_id=stable_identities(bm,seed_ids(ob,bm))
        self.context=context;self.ob=ob;self.bm=bm
        self.about=sym.about;self.axis='XYZ'.index(sym.axis)
        self.matrix=reflection(ob,self.about,self.axis)
        self.mw=ob.matrix_world.copy();self.inv=self.mw.inverted_safe()
        self.backup=None
        self.want_backup=backup
        self.topology_ready=False
        self.original={v:v.co.copy() for v in bm.verts}
        self.faces={};self.edges={}
        self.local=False;self.face_refs=set();self.edge_refs=set()
        self.touched_faces={};self.touched_edges={}
        self.generated=set();self.generated_faces=set();self.pairs={}
        self.identities={v:v[layer] for v in bm.verts}
        self.generated_face_keys=set()
        self.weld_survivors=set()
        self.seam_sources=set()
        self.seam_locks=set()
        self.virtual_origins={}
        self.reference=None
        if not coordinate_only:self.prepare_topology()
        coords=[v.co for v in bm.verts]
        span=max(((max(p[k] for p in coords)-min(p[k] for p in coords)) for k in range(3)),default=0) if coords else 0
        self.eps=max(span*1e-5,1e-8)
        if self.about=='TOPOLOGY':
            bm.verts.ensure_lookup_table()
            self.pairs={bm.verts[i]:bm.verts[j] for i,j in mapping.items()} if mapping is not None else topology_mapping(ob,bm,sym)
            verts=[v for v in bm.verts if v not in self.pairs and not v.link_faces]
            if verts:
                tree=KDTree(len(verts))
                for i,v in enumerate(verts):tree.insert(v.co,i)
                tree.balance()
                try:
                    for v in verts:
                        p=self.point(v.co);_,i,distance=tree.find(p)
                        if distance<=self.eps:self.pairs[v]=verts[i]
                except SymmetryError:pass
            if bm.verts and not self.pairs:
                self.close()
                raise SymmetryError('Topology symmetry: select a manifold seam edge on matching topology')
        else:
            self.tree=KDTree(len(coords));self.tree_verts=list(bm.verts)
            for i,v in enumerate(self.tree_verts):self.tree.insert(v.co,i)
            self.tree.balance()

        self.seam_edges=[tuple(e.verts) for e in bm.edges if all(self.pairs.get(v) is v for v in e.verts)] if self.about=='TOPOLOGY' else []
        self.disabled_reason=None

    def prepare_backup(self):
        """Native atomic rollback without a Python copy of every face/edge ring."""
        if self.want_backup and self.backup is None:self.backup=self.bm.copy()

    def prepare_topology(self,local=False,vertices=()):
        if not self.topology_ready:
            self.topology_ready=True;self.local=local
            self.prepare_backup()
            if local:
                self.face_refs=set(self.bm.faces);self.edge_refs=set(self.bm.edges)
            else:
                self.faces={frozenset(f.verts):tuple(f.verts) for f in self.bm.faces}
                self.edges={frozenset(e.verts):tuple(e.verts) for e in self.bm.edges}
        if self.local:
            roots=set(vertices)
            roots.update(other for v in list(roots) if (other:=self.find_pair(v)) is not None and other.is_valid)
            faces={f for v in roots if v.is_valid for f in v.link_faces}
            edges={e for v in roots if v.is_valid for e in v.link_edges}|{e for f in faces for e in f.edges}
            for f in faces:
                if f not in self.touched_faces:
                    ring=tuple(f.verts);self.touched_faces[f]=ring;self.faces[frozenset(ring)]=ring
            for e in edges:
                if e not in self.touched_edges:
                    ends=tuple(e.verts);self.touched_edges[e]=ends;self.edges[frozenset(ends)]=ends

    def find_pair(self,v):
        other=self.pairs.get(v)
        if other is not None:return other
        if self.about=='TOPOLOGY':return None
        co=self.original.get(v)
        if co is None:return None
        hits=self.tree.find_range(self.matrix@co,self.eps)
        for _,i,_ in sorted(hits,key=lambda h:(h[2],h[1])):
            other=self.tree_verts[i]
            if other not in self.pairs or self.pairs[other] is v:
                self.pairs[v]=other;self.pairs[other]=v
                return other
        return None

    def close(self):
        if getattr(self,'backup',None) is not None:
            self.backup.free();self.backup=None
        self.reference=None
        for name in ('original','faces','edges','pairs','generated','generated_faces','identities','generated_face_keys','weld_survivors','seam_sources','seam_locks','face_refs','edge_refs','touched_faces','touched_edges','virtual_origins','seam_edges'):
            value=getattr(self,name,None)
            if value is not None:value.clear()
        self.new_tree=None;self.new_verts=[]
        self.tree=None;self.tree_verts=[]

    def __del__(self):
        self.close()

    def rollback(self):
        if self.backup is None:
            for v,co in self.original.items():
                if v.is_valid:v.co=co
            self.close();return
        coords={self.identities[v]:co for v,co in self.original.items()}
        mesh=bpy.data.meshes.new('_quad_draw_rollback')
        try:
            self.backup.to_mesh(mesh)
            self.bm.clear();self.bm.from_mesh(mesh)
            layer=self.bm.verts.layers.int.get(IDENTITY)
            for v in self.bm.verts:
                co=coords.get(v[layer])
                if co is not None:v.co=co
        finally:bpy.data.meshes.remove(mesh)
        self.close()

    def _refresh(self):
        """Subdivision can reallocate custom data and invalidate *all* wrappers.

        Integer identities survive that reallocation. New subdivided points may
        inherit an endpoint ID; keep the original coordinate match, renumber copies.
        """
        layer=self.bm.verts.layers.int.get(IDENTITY)
        if all(v.is_valid for v in self.original):return
        all_dead=not any(v.is_valid for v in self.original)
        from collections import defaultdict
        groups=defaultdict(list)
        for v in self.bm.verts:groups[v[layer]].append(v)
        original_ids={self.identities[v]:co for v,co in self.original.items()}
        alive={}
        for identity,vs in groups.items():
            if identity<=0:continue
            co=original_ids.get(identity)
            keep=min(vs,key=lambda v:(v.co-co).length_squared) if co is not None else vs[0]
            alive[identity]=keep
            for v in vs:
                if v is not keep:v[layer]=0
        def remap(v):return alive.get(self.identities.get(v),v)
        if self.local and all_dead:
            # Native subdivision can replace every wrapper. Reconstruct from
            # the native rollback copy only in that case; common additive edits
            # never allocate Python rings for unrelated faces.
            by_id={self.identities[v]:remap(v) for v in self.original}
            old_layer=self.backup.verts.layers.int.get(IDENTITY)
            rings=[tuple(by_id[v[old_layer]] for v in f.verts) for f in self.backup.faces]
            ends=[tuple(by_id[v[old_layer]] for v in e.verts) for e in self.backup.edges]
            self.faces={frozenset(r):r for r in rings};self.edges={frozenset(e):e for e in ends}
            self.local=False
        self.original={remap(v):co for v,co in self.original.items()}
        self.faces={frozenset(remap(v) for v in ring):tuple(remap(v) for v in ring) for ring in self.faces.values()}
        self.edges={frozenset(remap(v) for v in ends):tuple(remap(v) for v in ends) for ends in self.edges.values()}
        self.pairs={remap(v):remap(other) for v,other in self.pairs.items()}
        self.generated={remap(v) for v in self.generated}
        self.seam_edges=[tuple(remap(v) for v in ends) for ends in self.seam_edges]
        self.tree_verts=[remap(v) for v in getattr(self,'tree_verts',[])]
        self.generated_faces={f for f in self.bm.faces if frozenset(v[layer] for v in f.verts) in self.generated_face_keys}
        self.identities.update({v:v[layer] for v in self.bm.verts})

    def _remember(self):
        layer=self.bm.verts.layers.int.get(IDENTITY)
        for v in self.bm.verts:
            if v[layer]<=0:
                v[layer]=self.next_id;self.next_id+=1
            self.identities[v]=v[layer]
        self.generated_face_keys={frozenset(v[layer] for v in f.verts) for f in self.generated_faces if f.is_valid}

    def _topology_point(self,co):
        """Use the same posed-reference correspondence as the visible preview."""
        from . import quad_draw_reference
        return quad_draw_reference.point(self.context,self.ob,co,self.axis)

    def point(self,co):
        if self.about=='TOPOLOGY':return self._topology_point(co)
        return self.matrix@co

    def require(self,vertices):
        if self.about=='TOPOLOGY' and any(v.link_faces and v not in self.pairs for v in vertices):
            raise SymmetryError('This operation leaves the matched topology region; choose another seam or a matched component')

    def counterpart(self,v):
        other=self.find_pair(v)
        if other is not None and other.is_valid:return other
        if self.about=='TOPOLOGY' and v in self.original and v.link_faces:
            raise SymmetryError('This component is outside the matched topology; pick another seam or use a matched region')
        p=self.point(v.co)
        if (p-v.co).length<=self.eps:
            v.co=(p+v.co)*.5;other=v
        else:
            # A cut loop can already have created its opposite-side vertex.
            # The commit-local tree avoids duplicating it without per-frame scans.
            hit=self.new_tree.find(p) if getattr(self,'new_tree',None) else (None,None,None)
            other=self.new_verts[hit[1]] if hit[0] is not None and hit[2]<=self.eps else None
            if other is None:
                other=self.bm.verts.new(p);self.generated.add(other)
            for layer in self.bm.verts.layers.int.values():
                if layer.name not in {IDENTITY,SEED_LAYER}:other[layer]=v[layer]
        self.pairs[v]=other;self.pairs[other]=v
        return other

    def move(self,verts):
        """O(number of moved components); avoid reprocessing a pair twice."""
        touched=set()
        for v in verts:
            if not v.is_valid or v in touched:continue
            other=self.find_pair(v)
            if other is None or not other.is_valid:
                if self.about=='TOPOLOGY':raise SymmetryError('This component is outside the matched topology region')
                continue
            touched.update((v,other))
            if other is v:
                if self.about=='TOPOLOGY':
                    from mathutils.geometry import intersect_point_line
                    choices=[]
                    for a,b in self.seam_edges:
                        _,t=intersect_point_line(v.co,self.original[a],self.original[b])
                        p=self.original[a].lerp(self.original[b],max(0,min(1,t)))
                        choices.append(((p-v.co).length_squared,p))
                    if choices:v.co=min(choices,key=lambda item:item[0])[1]
                else:v.co=(v.co+self.matrix@v.co)*.5
            elif self.about=='TOPOLOGY':
                # For posed topology map displacement, preserving the destination
                # anchor; projection keeps it on its own side of the reference.
                start=self.original.get(v,v.co)
                destination=self.original.get(other,other.co)
                p=destination+self.matrix.to_3x3()@(v.co-start)
                from . import live,quad_draw
                refs=quad_draw.reference_objects(self.context)
                if refs:
                    try:other.co=self.point(v.co);continue
                    except SymmetryError:pass
                other.co=p
            else:other.co=self.matrix@v.co

    def moving_mirrors(self,indices):
        """Moving counterparts cannot also be static magnet targets."""
        if self.about=='TOPOLOGY':return set()
        moving=set(indices);excluded=set()
        self.bm.verts.ensure_lookup_table()
        for i in moving:
            other=self.find_pair(self.bm.verts[i])
            if other is not None and other.is_valid and other.index not in moving:
                excluded.add(other.index)
        return excluded

    def seam_targets(self):
        targets={}
        for v in self.seam_sources:
            if not v.is_valid:continue
            other=self.find_pair(v)
            if other is not None and other.is_valid and other is not v and other not in targets:
                targets[v]=other
        return targets

    def plane_point(self,context,region,rv3d,w,limit,refs):
        from bpy_extras import view3d_utils
        from . import quad_draw,live
        center=self.mw@((self.inv@w+self.matrix@(self.inv@w))*.5)
        p=quad_draw._screen_xy(region,rv3d,w);q=quad_draw._screen_xy(region,rv3d,center)
        if p is None or q is None or (Vector(p)-Vector(q)).length>limit:return None
        pixel=view3d_utils.region_2d_to_location_3d(region,rv3d,(p[0]+1,p[1]),w)
        if (center-w).length>max((pixel-w).length*limit*2,self.eps):return None
        # Find the nearby surface at the seam, retaining a strict plane
        # constraint after projection (including transformed Object planes).
        for _ in range(2) if refs else ():
            hit=live.nearest(context,center,refs)
            if hit is None:break
            surface=quad_draw._surface_point(context,hit)
            local=self.inv@surface
            center=self.mw@((local+self.matrix@local)*.5)
        return center

    def snap_seam(self,context,region,rv3d,proposed,magnet):
        """A screen-tolerance target on the actual plane, with weld on release.

        Use the same Auto-weld switch/tolerance as the ordinary magnet. A world
        distance cap prevents side views (where both sides project to one pixel)
        from snapping distant geometry through the reference.
        """
        from bpy_extras import view3d_utils
        from . import quad_draw,live
        self.seam_sources.clear()
        radius=quad_draw._weld_px(context)
        if radius is None or self.about=='TOPOLOGY':
            self.seam_locks.clear();return proposed,[]
        self.bm.verts.ensure_lookup_table()
        result=dict(proposed);candidates={};locks=set();markers=[]
        refs=quad_draw.reference_objects(context)
        for i,w in proposed.items():
            if i in magnet.pairs:continue  # a real stationary vertex takes precedence
            v=self.bm.verts[i]
            if not v.is_boundary and v.link_faces:continue
            limit=radius*(1.4 if i in self.seam_locks else 1)
            center=self.plane_point(context,region,rv3d,w,limit,refs)
            if center is None:continue
            candidates[i]=(v,center)
        if not candidates:
            self.seam_locks.clear();return result,[]
        test=dict(result);pairs={}
        for i,(v,point) in candidates.items():
            test[i]=point
            other=self.find_pair(v)
            if other is not None and other is not v and other.is_valid:
                test[other.index]=point
                if other.index not in pairs:pairs[i]=other.index
        if pairs and not magnet.topology.valid(pairs,test):
            self.seam_locks.clear();return result,[]
        for i,(v,point) in candidates.items():
            result[i]=point;locks.add(i);markers.append(point)
            other=self.find_pair(v)
            if other is None or other.index not in candidates or i<other.index:self.seam_sources.add(v)
        self.seam_locks=locks
        return result,markers

    def snap_virtual(self,context,region,rv3d,proposed,magnet,raw=None):
        """Plane capture for preview-only vertices, before any BMesh allocation."""
        from . import quad_draw
        radius=quad_draw._weld_px(context)
        if radius is None or self.about=='TOPOLOGY':
            self.seam_locks.clear();return proposed,[]
        refs=quad_draw.reference_objects(context)
        result=dict(proposed);locked=set();markers=[]
        for i,w in proposed.items():
            target=magnet.pairs.get(i) if magnet is not None else None
            origin=self.virtual_origins.get(i)
            own_mirror=target is not None and origin is not None and self.find_pair(origin) is self.bm.verts[target]
            if target is not None and not own_mirror:continue
            if raw is not None:w=raw[i]
            point=self.plane_point(context,region,rv3d,w,radius*(1.4 if i in self.seam_locks else 1),refs)
            if point is not None:
                if own_mirror:magnet.pairs.pop(i,None)
                result[i]=point;locked.add(i);markers.append(point)
        self.seam_locks=locked
        return result,markers

    def weld(self,targets):
        """Apply both welds together; a pair welded to itself becomes one seam vertex."""
        expanded=dict(targets)
        for source,target in targets.items():
            opposite=self.counterpart(source)
            destination=self.counterpart(target)
            if opposite is target or destination is source:
                target.co=(target.co+self.matrix@target.co)*.5
                self.pairs[target]=target
                self.pairs[source]=target
                self.weld_survivors.add(target)
            elif opposite is not source:
                if opposite in expanded and expanded[opposite] is not destination:
                    raise SymmetryError('Symmetry weld has conflicting targets')
                expanded[opposite]=destination
        expanded={a:b for a,b in expanded.items() if a is not b}
        if expanded:bmesh.ops.weld_verts(self.bm,targetmap=expanded)
        # The visible side may be valid while its counterpart has different
        # topology. Never leave a three-face edge or conflicting winding there.
        touched={e for v in expanded.values() if v.is_valid for e in v.link_edges}
        for edge in touched:
            if len(edge.link_faces)>2:
                raise SymmetryError('Symmetry weld would create a non-manifold edge')
            loops=list(edge.link_loops)
            if len(loops)==2 and loops[0].vert is loops[1].vert:
                raise SymmetryError('Symmetry weld would reverse adjacent face winding')
        return len(targets)

    def check_seam(self):
        bm=self.bm
        if self.about=='TOPOLOGY' and any(not all(v.is_valid for v in ends) or (e:=bm.edges.get(ends)) is None or len(e.link_faces)!=2 for ends in self.seam_edges):
            from . import symmetry
            state=symmetry.state(self.context.scene);state.on=False;symmetry.apply(state,[self.ob])
            if SEED in self.ob.data:del self.ob.data[SEED]
            flags=bm.verts.layers.int.get(SEED_LAYER)
            if flags is not None:
                for v in bm.verts:v[flags]=0
            self.disabled_reason='Topology symmetry disabled because a seam edge was modified; pick the seam again'
            return True
        return False

    def sync(self):
        """Replay the operation's changed faces/edges, reversing reflected winding."""
        bm=self.bm
        self._refresh()
        if self.check_seam():return
        if self.local:
            current={key:f for key,ring in self.faces.items() if all(v.is_valid for v in ring) and (f:=bm.faces.get(ring)) is not None}
            new_faces={f for f in bm.faces if f not in self.face_refs and f not in self.generated_faces}
            new_faces.update(f for f,old in self.touched_faces.items() if f.is_valid and frozenset(f.verts)!=frozenset(old) and f not in self.generated_faces)
            new_edges={e for e in bm.edges if e not in self.edge_refs and not all(v in self.generated for v in e.verts)}
            new_edges.update(e for e,old in self.touched_edges.items() if e.is_valid and frozenset(e.verts)!=frozenset(old))
        else:
            current={frozenset(f.verts):f for f in bm.faces}
            new_faces=[f for key,f in current.items() if key not in self.faces and f not in self.generated_faces]
            new_edges=[e for e in bm.edges if frozenset(e.verts) not in self.edges and not all(v in self.generated for v in e.verts)]
        # Identify all counterpart rings before deleting elements whose wrappers
        # become invalid; original mapping remains usable after a weld.
        removed=[]
        for key,ring in self.faces.items():
            if key not in current:
                mapped=[self.find_pair(v) for v in ring]
                if all(v is not None and v.is_valid for v in mapped):
                    f=bm.faces.get(mapped)
                    if f is not None and frozenset(mapped)!=key:removed.append(f)
        for f in set(removed):
            if f.is_valid:bm.faces.remove(f)
        for key,ends in self.edges.items():
            if any(not v.is_valid for v in ends) or bm.edges.get(ends) is None:
                mapped=[self.find_pair(v) for v in ends]
                if all(v is not None and v.is_valid for v in mapped):
                    e=bm.edges.get(mapped)
                    if e is not None and not e.link_faces:bm.edges.remove(e)
        for v in self.original:
            if not v.is_valid:
                other=self.find_pair(v)
                if other is not None and other.is_valid and other not in self.weld_survivors:bm.verts.remove(other)
        self.new_verts=[v for v in bm.verts if v not in self.original and v not in self.generated]
        self.new_tree=KDTree(len(self.new_verts))
        for i,v in enumerate(self.new_verts):self.new_tree.insert(v.co,i)
        self.new_tree.balance()
        for v in list(bm.verts):
            if v not in self.original and v not in self.generated:self.counterpart(v)
        for f in new_faces:
            if not f.is_valid:continue
            ring=[self.counterpart(v) for v in reversed(list(f.verts))]
            if len(set(ring))!=len(ring):raise SymmetryError('Symmetry would collapse a face at the seam')
            if bm.faces.get(ring) is None:
                if any((e:=bm.edges.get((a,b))) is not None and len(e.link_faces)>=2 for a,b in zip(ring,ring[1:]+ring[:1])):
                    raise SymmetryError('Symmetry would create a non-manifold edge')
                new=bm.faces.new(ring);new.material_index=f.material_index
                self.generated_faces.add(new)
        for e in new_edges:
            if e.is_valid:
                ends=[self.counterpart(v) for v in e.verts]
                if ends[0] is not ends[1] and bm.edges.get(ends) is None:bm.edges.new(ends)
        bm.normal_update()
        self._remember()


def begin(context,ob,bm,backup=True,coordinate_only=False,mapping=None):
    return Stroke(context,ob,bm,backup,coordinate_only,mapping) if context.scene.allset_symmetry.on else None
