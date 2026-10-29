"""A hovered vertex/dot must not leave its red hover marker behind during an actual mouse drag."""
import os
import sys
from pathlib import Path
from importlib import import_module
import bmesh
import bpy
import numpy as np
from mathutils import Quaternion, Vector
from bpy_extras import view3d_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, setup, load_maya_layout, step, run, ev, view3d, win, check, screenshot, scale, MEASURED_SCALE

C = {}
qd = lambda: import_module(MODULE+'.operators.quad_draw')


def override():
    a,r=view3d()
    return bpy.context.temp_override(window=win(),area=a,region=r)


def pixel(world):
    a,r=view3d()
    p=view3d_utils.location_3d_to_region_2d(r,a.spaces.active.region_3d,Vector(world))
    return r.x+round(p.x), r.y+round(p.y)


def marker_pixels(name):
    path=Path(os.environ.get('ALLSET_GUI_SHOTS',bpy.app.tempdir))/(name+'.png')
    screenshot(str(path))
    im=bpy.data.images.load(str(path),check_existing=False)
    w,h=im.size
    data=np.empty(w*h*4,dtype=np.float32)
    im.pixels.foreach_get(data)
    bpy.data.images.remove(im)
    x,y=C['old']
    patch=data.reshape(h,w,4)[y-14:y+15,x-14:x+15,:3]
    return int(((patch[...,0]>.8)&(patch[...,1]<.35)&(patch[...,2]<.3)).sum())


@step
def prepare():
    setup()
    load_maya_layout()


@step
def surface():
    with override():
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob,do_unlink=True)
        bpy.ops.mesh.primitive_plane_add(size=10)
        import_module(MODULE+'.operators.live').set_objects(bpy.context.scene,[bpy.context.object])
        bpy.ops.mesh.primitive_plane_add(size=1.2)
        ob=bpy.context.object
        C['object']=ob.name
        bpy.ops.allset.quad_draw_start()
        bm=bmesh.from_edit_mesh(ob.data)
        for el in (*bm.verts,*bm.edges,*bm.faces):
            el.select=False
        bmesh.update_edit_mesh(ob.data)
        a,r=view3d();rv=a.spaces.active.region_3d
        rv.view_rotation=Quaternion((1,0,0,0));rv.view_perspective='ORTHO'
        rv.view_location=(0,0,0);rv.view_distance=5


@step
def hover_vertex():
    C['old']=pixel((-.6,-.6,0))
    x,y=C['old']
    ev('MOUSEMOVE','NOTHING',x=x+1,y=y)
    ev('MOUSEMOVE','NOTHING',x=x,y=y)


@step
def press_vertex():
    check('vertex hover marker is visible before pressing',marker_pixels('quad_vertex_before')>max(3,10*(scale()/MEASURED_SCALE)**2))
    ev('LEFTMOUSE','PRESS')


@step
def drag_vertex():
    x,y=pixel((-.2,-.25,0))
    ev('MOUSEMOVE','NOTHING',x=x,y=y)


@step
def vertex_in_flight():
    check('LMB drag removes the red marker at the original vertex',marker_pixels('quad_vertex_drag')<5)
    check('LMB drag has no stale hover preview',qd().STATE['preview'] is None)
    bm=bmesh.from_edit_mesh(bpy.context.edit_object.data)
    check('the vertex moved while the button is still held',any((v.co-Vector((-.2,-.25,0))).length<.025 for v in bm.verts))
    ev('LEFTMOUSE','RELEASE')


@step
def add_dot():
    with override():
        bm=bmesh.from_edit_mesh(bpy.context.edit_object.data)
        qd().add_dot(bm,Vector((0,-1,0)))
        bmesh.update_edit_mesh(bpy.context.edit_object.data)
        import_module(MODULE+'.operators.preselect').invalidate()
    C['old']=pixel((0,-1,0))
    x,y=C['old']
    ev('MOUSEMOVE','NOTHING',x=x+1,y=y)
    ev('MOUSEMOVE','NOTHING',x=x,y=y)


@step
def press_dot():
    check('loose dot hover marker is visible before pressing',marker_pixels('quad_dot_before')>max(3,10*(scale()/MEASURED_SCALE)**2))
    ev('MIDDLEMOUSE','PRESS')


@step
def drag_dot():
    x,y=pixel((.5,-1,0))
    ev('MOUSEMOVE','NOTHING',x=x,y=y)


@step
def dot_in_flight():
    check('MMB drag removes the red marker at the original dot',marker_pixels('quad_dot_drag')<5)
    check('MMB drag has no stale hover preview',qd().STATE['preview'] is None)
    dots=qd().dots(bmesh.from_edit_mesh(bpy.context.edit_object.data))
    check('the loose dot moves without making a duplicate',len(dots)==1 and (dots[0].co-Vector((.5,-1,0))).length<.025)
    ev('ESC','PRESS');ev('ESC','RELEASE')
    ev('MIDDLEMOUSE','RELEASE')


@step
def cancelled():
    dots=qd().dots(bmesh.from_edit_mesh(bpy.context.edit_object.data))
    check('Escape restores the loose dot and clears preview',len(dots)==1 and (dots[0].co-Vector((0,-1,0))).length<1e-5 and qd().STATE['preview'] is None)
    a,r=view3d()
    with bpy.context.temp_override(window=win(),area=a,region=r):
        ob=bpy.context.edit_object
        pre=import_module(MODULE+'.operators.preselect')
        c=next(c for candidate,c in pre.caches(bpy.context) if candidate==ob)
        b=bmesh.from_edit_mesh(ob.data)
        check('Escape refreshes cached display and picking coordinates',all((Vector(c.co[v.index])-ob.matrix_world@v.co).length<1e-6 for v in b.verts) and pre._coordinate_session is None)


run()
