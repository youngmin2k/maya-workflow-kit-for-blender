# SPDX-License-Identifier: GPL-3.0-or-later
"""Stroke-local Quad Draw relaxation and reversible, fixed-selection MMB scrubbing."""
import math
import numpy as np
import bmesh
import bpy
from mathutils import Vector
from . import poly_draw,preselect,soft_select

SCRUB_PX=48.0
MAX_LEVELS=16
_preview=None


def clear():
    global _preview
    _preview=None


def mesh_cache(context,ob):
    return next((c for candidate,c in preselect.caches(context) if candidate==ob),None)


def component_ids(c,comp):
    if comp is None:return []
    kind,i=comp[:2]
    return [i] if kind=='VERT' else [v.index for v in (c.bm.edges[i].verts if kind=='EDGE' else c.bm.faces[i].verts)]


def soft_area(context,c,seeds):
    """Use the existing world-space Soft Selection radius/mode; relax strength is uniform inside it.

    Maya's relax brush uses the falloff *area*, rather than weighting its smoothing
    by the falloff curve. The curve remains useful for the influence preview.
    """
    n=len(c.co);selected=np.zeros(n,dtype=bool);selected[seeds]=True
    ts=context.scene.tool_settings;radius=max(float(ts.proportional_size),1e-12)
    connected=ts.use_proportional_connected;axis=None
    if ts.use_proportional_projected and not connected:axis=tuple(context.region_data.view_rotation@Vector((0,0,1)))
    corners=None
    if connected and seeds:
        # Limit across-face propagation to the ball that can be reached within
        # the radius, instead of creating corner tuples for the complete mesh.
        near=soft_select.distances(c.co,selected,radius)<=radius
        if c.arrays is not None:
            faces=[ids[near[ids].all(axis=1)].tolist() for _,ids in c.arrays[7]]
            faces=[f for group in faces for f in group]
        else:faces=[tuple(v.index for v in f.verts) for f in c.bm.faces if not f.hide and all(near[v.index] for v in f.verts)]
        corners=soft_select.face_corners(faces)
    distances=soft_select.distances(c.co,selected,radius,c.edges[c.eok],corners,connected,axis)
    allowed=c.vok & (distances<=radius)
    weights=soft_select.falloff(1-distances/radius,ts.proportional_edit_falloff)
    weights[~allowed]=0
    return np.flatnonzero(allowed),weights


def preview(context,ob,mouse):
    global _preview
    from . import quad_draw as q
    c=mesh_cache(context,ob)
    if c is None:return
    ts=context.scene.tool_settings
    key=(c,c.revision,tuple(mouse),ts.proportional_size,ts.use_proportional_connected,ts.use_proportional_projected,ts.proportional_edit_falloff,
         tuple(map(tuple,context.region_data.perspective_matrix)))
    if _preview is None or _preview[0]!=key:
        comp=q.component_at(context,context.region,context.region_data,mouse,ob)
        seeds=component_ids(c,comp)
        if not seeds:_preview=key,None
        else:
            _,weights=soft_area(context,c,seeds)
            _preview=key,{'cache':c,'weights':weights}
    q.STATE['relax_area']=_preview[1]


def boundary_component(bm,seed):
    """One continuous visible boundary; nearby disconnected borders are independent."""
    seen={seed};todo=[seed]
    while todo:
        v=todo.pop()
        for e in v.link_edges:
            if not e.is_boundary or e.hide:continue
            other=e.other_vert(v)
            if not other.hide and other not in seen:seen.add(other);todo.append(other)
    return {v.index for v in seen}


class Kernel:
    """Small numeric one-ring snapshot; no full-mesh scan per smoothing step."""
    def __init__(self,c,ids,mode,neighbours):
        bm=c.bm;self.ids=list(ids)
        rings=[]
        for i in self.ids:
            if i not in neighbours:
                v=bm.verts[i]
                neighbours[i]=tuple(e.other_vert(v).index for e in v.link_edges if not e.hide and not e.other_vert(v).hide and (not v.is_boundary or mode=='ALL' or e.is_boundary))
            rings.append(neighbours[i])
        support=sorted(set(self.ids)|{i for ring in rings for i in ring})
        lookup={i:j for j,i in enumerate(support)}
        self.base=np.asarray([bm.verts[i].co[:] for i in support],dtype=float).reshape(-1,3)
        self.rows=np.asarray([lookup[i] for i in self.ids],dtype='int32')
        self.initial=self.base[self.rows].copy()
        self.dest=np.repeat(np.arange(len(ids)),[len(r) for r in rings])
        self.source=np.asarray([lookup[i] for ring in rings for i in ring],dtype='int32')
        self.counts=np.asarray([len(r) for r in rings],dtype=float)

    def step(self,points):
        support=self.base.copy();support[self.rows]=points
        sums=np.zeros_like(points);np.add.at(sums,self.dest,support[self.source])
        average=sums/np.maximum(self.counts[:,None],1)
        return np.where((self.counts>0)[:,None],points+(average-points)*.5,points)


class Session:
    def __init__(self,context,owner,mouse):
        self.owner=owner;self.ob=bpy.data.objects[owner._ob];self.c=mesh_cache(context,self.ob)
        self.press=tuple(mouse);self.original={};self.neighbours={};self.border=None
        self.mode=poly_draw.settings(context).qd_relax;self.fixed=None;self.weights=None
        self.levels=[];self.kernel=None;self.projection=None
        if owner.middle:self._fixed_selection(context,mouse)

    def _screen(self,context):
        c=self.c;rv=context.region_data;r=context.region
        key=(c.revision,r.width,r.height,tuple(map(tuple,rv.perspective_matrix)))
        if self.projection is None or self.projection[0]!=key:
            xy,front=preselect.project(c.co,rv.perspective_matrix,r.width,r.height)
            self.projection=key,xy,front
        return self.projection[1:]

    def _filter(self,context,ids,mouse):
        if not len(ids):return []
        c=self.c;bm=c.bm;xy,_=self._screen(context)
        ids=[int(i) for i in ids if c.vok[i] and bm.verts[int(i)].link_edges]
        if not ids:return []
        nearest=min(ids,key=lambda i:float(np.sum((xy[i]-mouse)**2)))
        if self.mode=='AUTO_LOCK':
            if not hasattr(self.owner,'_relax_lock'):self.owner._relax_lock='BORDER' if bm.verts[nearest].is_boundary else 'INTERIOR'
            mode=self.owner._relax_lock
        else:mode=self.mode
        if mode=='INTERIOR':ids=[i for i in ids if not bm.verts[i].is_boundary]
        elif mode=='BORDER':
            ids=[i for i in ids if bm.verts[i].is_boundary]
            if ids and self.border is None:
                seed=min(ids,key=lambda i:float(np.sum((xy[i]-mouse)**2)))
                self.border=boundary_component(bm,bm.verts[seed])
            ids=[i for i in ids if i in (self.border or ())]
        sym=getattr(self.owner,'_sym',None)
        if sym is not None:
            sym.require([bm.verts[i] for i in ids])
            # The side closest to the stroke anchor drives each pair once.
            ordered=sorted(ids,key=lambda i:float(np.sum((xy[i]-self.press)**2)))
            kept=[];seen=set()
            for i in ordered:
                v=bm.verts[i]
                if v in seen:continue
                kept.append(i);seen.add(v)
                other=sym.find_pair(v)
                if other is not None:seen.add(other)
            ids=kept
        return ids

    def _area(self,context,mouse):
        from . import quad_draw as q
        c=self.c;xy,front=self._screen(context)
        if context.scene.allset_soft_select:
            comp=q.component_at(context,context.region,context.region_data,mouse,self.ob)
            seeds=component_ids(c,comp)
            if not seeds:return []
            ids,self.weights=soft_area(context,c,seeds)
        elif self.owner.middle:
            comp=q.component_at(context,context.region,context.region_data,mouse,self.ob)
            ids=component_ids(c,comp)
        else:
            radius=q.BRUSH_PX*q._ui_scale(context)
            ids=np.flatnonzero(c.vok & front & (np.sum((xy-mouse)**2,axis=1)<=radius*radius))
        return self._filter(context,ids,mouse)

    def _fixed_selection(self,context,mouse):
        self.fixed=self._area(context,mouse)
        if self.fixed:
            mode=getattr(self.owner,'_relax_lock',self.mode)
            self.kernel=Kernel(self.c,self.fixed,mode,self.neighbours)
            self.levels=[self.kernel.initial.copy()]

    def _project(self,context,points):
        if not self.owner._refs:return points
        from . import quad_draw as q
        mw=self.ob.matrix_world;inv=mw.inverted_safe()
        return np.asarray([tuple(inv@q.project_point(context,mw@Vector(p),self.owner._refs,context.region,context.region_data)) for p in points],dtype=float).reshape(-1,3)

    def apply(self,context,mouse):
        from . import quad_draw as q
        c=self.c;bm=c.bm
        if self.owner.middle:
            ids=self.fixed or []
            if not ids:return
            amount=max(0,min(MAX_LEVELS,(mouse[0]-self.press[0])/(SCRUB_PX*q._ui_scale(context))))
            low=int(math.floor(amount));high=int(math.ceil(amount))
            while len(self.levels)<=high:self.levels.append(self._project(context,self.kernel.step(self.levels[-1])))
            points=self.levels[low]*(1-(amount-low))+self.levels[high]*(amount-low)
            if amount!=low:points=self._project(context,points)
        else:
            ids=self._area(context,mouse)
            if not ids:return
            kernel=Kernel(c,ids,getattr(self.owner,'_relax_lock',self.mode),self.neighbours)
            points=self._project(context,kernel.step(kernel.initial))
        moving=[]
        for i,p in zip(ids,points):
            v=bm.verts[i]
            if i not in self.original:self.original[i]=v.co.copy()
            v.co=p;moving.append(v)
        sym=getattr(self.owner,'_sym',None)
        if sym is not None:sym.move(moving)
        changed=moving+([sym.pairs[v] for v in moving if v in sym.pairs and sym.pairs[v].is_valid] if sym else [])
        preselect.coordinates_changed(self.ob,changed)
        bmesh.update_edit_mesh(self.ob.data,loop_triangles=False,destructive=False)
        if self.weights is not None:q.STATE['relax_area']={'cache':c,'weights':self.weights}
        radius=q.BRUSH_PX*q._ui_scale(context)
        if context.scene.allset_soft_select:
            center=self.ob.matrix_world@bm.verts[ids[0]].co
            right=context.region_data.view_rotation@Vector((1,0,0))
            a=q._screen_xy(context.region,context.region_data,center)
            b=q._screen_xy(context.region,context.region_data,center+right*context.scene.tool_settings.proportional_size)
            if a and b:radius=(Vector(a)-Vector(b)).length
        at=self.press if self.owner.middle else mouse
        q.STATE['preview']=('BRUSH',(*at,radius))

    def restore(self):
        if self.c is None:return
        bm=self.c.bm
        for i,p in self.original.items():
            if i<len(bm.verts) and bm.verts[i].is_valid:bm.verts[i].co=p
        bmesh.update_edit_mesh(self.ob.data,loop_triangles=False,destructive=False)

    def close(self):
        self.original.clear();self.neighbours.clear();self.levels.clear()
        self.kernel=self.c=self.border=self.projection=self.weights=self.fixed=None
