"""Real sphere-ring rendering, red component hover and short-edge picking."""
import math
import os
import sys
from pathlib import Path
from importlib import import_module
from types import SimpleNamespace
import bpy
import bmesh
import numpy as np
from mathutils import Vector, Quaternion, Euler
from bpy_extras import view3d_utils
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE,setup,load_maya_layout,step,run,view3d,win,check,screenshot,ev

C={}
mod=lambda n:import_module(MODULE+'.operators.'+n)


def override():
    a,r=view3d()
    return bpy.context.temp_override(window=win(),area=a,region=r)


def xy(p):
    a,r=view3d()
    return view3d_utils.location_3d_to_region_2d(r,a.spaces.active.region_3d,Vector(p))


def picture(name):
    path=Path(os.environ.get('ALLSET_GUI_SHOTS',bpy.app.tempdir))/(name+'.png')
    screenshot(str(path))
    im=bpy.data.images.load(str(path),check_existing=False)
    w,h=im.size
    values=np.empty(w*h*4,dtype=np.float32);im.pixels.foreach_get(values)
    bpy.data.images.remove(im)
    a,r=view3d()
    return values.reshape(h,w,4)[r.y:r.y+r.height,r.x:r.x+r.width,:3]


def red_count(data,p,radius=12):
    x,y=map(round,xy(p))
    patch=data[max(0,y-radius):y+radius+1,max(0,x-radius):x+radius+1]
    return int(((patch[...,0]>.8)&(patch[...,1]<.35)&(patch[...,2]<.3)).sum())


def hover(kind,p):
    with override():
        a,r=view3d();ctx=bpy.context
        q=mod('quad_draw');ob=ctx.edit_object
        comp=q.component_at(ctx,r,a.spaces.active.region_3d,xy(p),ob)
        check(kind+' hover picks intended component',comp and comp[0]==kind)
        q.update_hover(ctx,r,a.spaces.active.region_3d,xy(p),False,False)
        grab=SimpleNamespace(_ob=ob.name,_refs=q.reference_objects(ctx))
        got=q.ALLSET_OT_quad_draw._grab_at(grab,ctx,xy(p))
        check(kind+' hover and press agree',got and len(got[1])=={'VERT':1,'EDGE':2,'FACE':4}[kind])
        C[kind]=p
        a.tag_redraw()
    a,r=view3d();point=xy(p)
    ev('MOUSEMOVE','NOTHING',x=r.x+round(point.x)+1,y=r.y+round(point.y))
    ev('MOUSEMOVE','NOTHING',x=r.x+round(point.x),y=r.y+round(point.y))


@step
def prepare():
    setup();load_maya_layout()


@step
def ring():
    with override():
        for ob in list(bpy.data.objects):bpy.data.objects.remove(ob,do_unlink=True)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=2,segments=96,ring_count=48)
        mod('live').set_objects(bpy.context.scene,[bpy.context.object])
        points=[]
        for radius in (.55,1.2):
            for i in range(8):
                t=i*math.tau/8
                x,y=radius*math.cos(t),radius*math.sin(t)
                points.append((x,y,math.sqrt(4-radius*radius)))
        faces=[(i,i+8,(i+1)%8+8,(i+1)%8) for i in range(8)]
        me=bpy.data.meshes.new('ring');me.from_pydata(points,[],faces)
        ob=bpy.data.objects.new('ring',me);bpy.context.scene.collection.objects.link(ob)
        ob.select_set(True);bpy.context.view_layer.objects.active=ob
        bpy.ops.allset.quad_draw_start()
        bm=bmesh.from_edit_mesh(me)
        for el in (*bm.verts,*bm.edges,*bm.faces):el.select=False
        bmesh.update_edit_mesh(me)
        mod('preselect').invalidate()
        a,r=view3d();rv=a.spaces.active.region_3d
        rv.view_rotation=Quaternion((1,0,0,0));rv.view_perspective='ORTHO'
        rv.view_location=(0,0,1);rv.view_distance=5
        C['points']=points
        C['edge']=(Vector(points[0])+Vector(points[8]))*.5
        C['face']=sum((Vector(points[i]) for i in faces[0]),Vector())*.25
        C['offset']=a.spaces.active.overlay.retopology_offset
    a,r=view3d();ev('MOUSEMOVE','NOTHING',x=r.x+r.width//2,y=r.y+r.height//2)


@step
def clean_wire():
    data=picture('quad_ring_clean')
    # Sample edge centres; the custom wire should remain continuous above the
    # curved reference, rather than alternating with reference shading.
    hits=[]
    p=C['points']
    for a,b in ((0,8),(1,9),(8,9),(0,1)):
        for t in np.linspace(.15,.85,21):
            x,y=map(round,xy(Vector(p[a]).lerp(Vector(p[b]),float(t))))
            patch=data[y-2:y+3,x-2:x+3]
            hits.append(bool((patch.max(axis=2)<.25).any()))
    check('ring wire has continuous dark coverage over curved reference',sum(hits)>=len(hits)*.95)
    print('WIRE_COVERAGE',sum(hits),len(hits),flush=True)
    check('drawing does not rewrite native retopology offset',view3d()[0].spaces.active.overlay.retopology_offset==C['offset'])
    hover('VERT',p[0])


@step
def vertex():
    data=picture('quad_ring_hover_vertex')
    check('hovered vertex has a visible red ring',red_count(data,C['VERT'])>10)
    hover('EDGE',C['edge'])


@step
def edge():
    data=picture('quad_ring_hover_edge')
    check('hovered edge has a visible thin red stroke',red_count(data,C['EDGE'])>15)
    hover('FACE',C['face'])


@step
def face():
    data=picture('quad_ring_hover_face')
    check('hovered face has red boundary',red_count(data,C['edge'])>15)
    x,y=map(round,xy(C['face']))
    base=C['face_pixel']=data[y,x]
    with override():
        mod('quad_draw').STATE['preview']=None
        view3d()[0].tag_redraw()


@step
def face_fill_and_orbit():
    data=picture('quad_ring_no_hover')
    x,y=map(round,xy(C['face']))
    check('hover lightens the interior of the face',float(C['face_pixel'].sum()-data[y,x].sum())>.05)
    with override():
        rv=view3d()[0].spaces.active.region_3d
        rv.view_rotation=Euler((.4,.2,.2)).to_quaternion();rv.view_perspective='PERSP'
        rv.view_distance=4


@step
def perspective():
    data=picture('quad_ring_perspective')
    cyan=(data[...,0]<.4)&(data[...,1]>.4)&(data[...,2]>.5)
    check('ring tint survives orbit and perspective zoom',int(cyan.sum())>1000)
    with override():
        ctx=bpy.context;a,r=view3d();rv=a.spaces.active.region_3d
        rv.view_rotation=Quaternion((1,0,0,0));rv.view_perspective='ORTHO';rv.view_distance=5
        # An isolated, small quad used to be impossible to pick in face mode:
        # every point was inside an oversized vertex hit zone.
        bpy.ops.allset.quad_draw_exit();bpy.ops.object.mode_set(mode='OBJECT')
        mod('live').set_objects(ctx.scene,[])
        for ob in list(bpy.data.objects):bpy.data.objects.remove(ob,do_unlink=True)
        bpy.ops.mesh.primitive_plane_add(size=.11,location=(0,0,1))
        bpy.ops.allset.quad_draw_start()


@step
def tiny():
    with override():
        ctx=bpy.context;a,r=view3d();rv=a.spaces.active.region_3d;q=mod('quad_draw')
        ob=ctx.edit_object
        bm=bmesh.from_edit_mesh(ob.data)
        f=bm.faces[0]
        center=ob.matrix_world@f.calc_center_median()
        p=q.component_at(ctx,r,rv,xy(center),ob)
        check('small quad centre selects face instead of a nearby vertex',p and p[0]=='FACE')
        e=f.edges[0];point=ob.matrix_world@((e.verts[0].co+e.verts[1].co)*.5)
        p=q.component_at(ctx,r,rv,xy(point),ob)
        check('small quad midpoint selects edge instead of a nearby vertex',p and p[0]=='EDGE')
        overlay=mod('quad_draw_overlay');overlay.batches(ctx)
        check('display buffer has a finite bounded payload',0<overlay.buffer_bytes()<10000)
        q._restore_overlays()
        check('exit releases geometry and hover buffers',overlay._cached is None and overlay._hover is None and overlay.buffer_bytes()==0)


@step
def far_sheet():
    with override():
        ctx=bpy.context;a,r=view3d();rv=a.spaces.active.region_3d
        bpy.ops.object.mode_set(mode='OBJECT')
        for ob in list(bpy.data.objects):bpy.data.objects.remove(ob,do_unlink=True)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=2)
        mod('live').set_objects(ctx.scene,[ctx.object])
        me=bpy.data.meshes.new('hidden_dot');me.from_pydata([(0,0,-2)],[],[])
        ob=bpy.data.objects.new('hidden_dot',me);ctx.scene.collection.objects.link(ob)
        ob.select_set(True);ctx.view_layer.objects.active=ob
        bpy.ops.allset.quad_draw_start()
        C['hidden']=ob.name


@step
def hidden_pick():
    with override():
        ctx=bpy.context;a,r=view3d();rv=a.spaces.active.region_3d
        q=mod('quad_draw');ob=bpy.data.objects[C['hidden']]
        check('component picking rejects a vertex behind the live reference',q.component_at(ctx,r,rv,xy((0,0,-2)),ob) is None)
        bpy.ops.allset.quad_draw_exit()


run()
