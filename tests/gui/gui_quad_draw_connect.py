"""Two retopo strips on a sphere: bridge, live vertex/edge magnet, commit, cancel and Tab extension."""
import os
import sys
from importlib import import_module
import bmesh
import bpy
from mathutils import Quaternion,Vector
from bpy_extras import view3d_utils
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE,setup,load_maya_layout,step,run,ev,view3d,win,check,screenshot

C={}
mod=lambda n:import_module(MODULE+'.'+n)


def override():
    a,r=view3d()
    return bpy.context.temp_override(window=win(),area=a,region=r)


def bm():
    b=bmesh.from_edit_mesh(bpy.context.edit_object.data)
    b.verts.ensure_lookup_table();b.edges.ensure_lookup_table()
    return b


def world(x,y):
    return Vector((x,y,(9-x*x-y*y)**.5))


def point(p):
    a,r=view3d()
    xy=view3d_utils.location_3d_to_region_2d(r,a.spaces.active.region_3d,Vector(p))
    return r.x+round(xy.x),r.y+round(xy.y)


def move(p,dx=0,**kw):
    x,y=point(p)
    ev('MOUSEMOVE','NOTHING',x=x+dx,y=y,**kw)


def press(p,button='LEFTMOUSE',**kw):
    move(p,**kw);ev(button,'PRESS',**kw)


def undo():
    ev('Z','PRESS',ctrl=True);ev('Z','RELEASE',ctrl=True)


@step
def prepare():
    setup();load_maya_layout()


@step
def surface():
    with override():
        for o in list(bpy.data.objects):bpy.data.objects.remove(o,do_unlink=True)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=3,segments=64,ring_count=32)
        mod('operators.live').set_objects(bpy.context.scene,[bpy.context.object])
        co=[world(x,y) for x,y in ((-1.6,-.6),(-.8,-.6),(-.8,.6),(-1.6,.6),(0,-.6),(.8,-.6),(.8,.6),(0,.6))]
        me=bpy.data.meshes.new('strips');me.from_pydata(co,[],[(0,1,2,3),(4,5,6,7)])
        ob=bpy.data.objects.new('strips',me);bpy.context.scene.collection.objects.link(ob)
        ob.select_set(True);bpy.context.view_layer.objects.active=ob
        bpy.ops.allset.quad_draw_start()
        b=bm()
        for el in (*b.verts,*b.edges,*b.faces):el.select=False
        bmesh.update_edit_mesh(me)
        a,r=view3d();rv=a.spaces.active.region_3d
        rv.view_rotation=Quaternion((1,0,0,0));rv.view_perspective='ORTHO'
        rv.view_location=(0,0,2);rv.view_distance=6
        C['target']=co[4].copy()
        bpy.ops.ed.undo_push(message='Quad Draw strips fixture')


@step
def bridge_hover():
    move(world(-.4,0),shift=True)


@step
def bridge_press():
    q=mod('operators.quad_draw')
    check('gap preview is a quad',q.STATE['preview'] is not None and q.STATE['preview'][0]=='FILL' and len(q.STATE['preview'][1])==4)
    ev('LEFTMOUSE','PRESS',shift=True)


@step
def bridge_release():ev('LEFTMOUSE','RELEASE',shift=True)


@step
def bridge_result():
    b=bm()
    check('Shift fill joins both strips without duplicate vertices',len(b.verts)==8 and len(b.faces)==3 and sum(len(e.link_faces)==2 for e in b.edges)==2)
    undo()


@step
def vertex_press():
    check('Undo restores the two separate strips',len(bm().faces)==2 and len(bm().verts)==8)
    press(world(-.8,-.6))


@step
def vertex_drag():move(C['target'],dx=4)


@step
def vertex_snap():
    b=bm()
    check('vertex snaps before the mouse is released',(b.verts[1].co-C['target']).length<1e-5 and len(b.verts)==8)
    check('the current weld target is highlighted',bool(mod('operators.quad_draw').STATE['snap']))
    if os.environ.get('ALLSET_GUI_SHOTS'):screenshot(os.path.join(os.environ['ALLSET_GUI_SHOTS'],'quad_live_weld.png'))
    ev('LEFTMOUSE','RELEASE')


@step
def vertex_welded():
    b=bm()
    check('release welds to exactly the previewed target',len(b.verts)==7 and sum((v.co-C['target']).length<1e-5 for v in b.verts)==1)
    check('target position and both faces survive',len(b.faces)==2 and all(f.calc_area()>1e-8 for f in b.faces))
    undo()


@step
def cancel_press():press(world(-.8,-.6),button='MIDDLEMOUSE')


@step
def cancel_drag():move(C['target'],dx=3)


@step
def cancel_snap():
    check('MMB uses the same live magnet',(bm().verts[1].co-C['target']).length<1e-5)
    ev('ESC','PRESS');ev('ESC','RELEASE');ev('MIDDLEMOUSE','RELEASE')


@step
def cancel_result():
    check('Escape restores position and topology before welding',len(bm().verts)==8 and (bm().verts[1].co-world(-.8,-.6)).length<1e-5)
    press(world(-.8,0))


@step
def edge_drag():move(world(0,0),dx=3)


@step
def edge_snap():
    b=bm()
    check('both edge endpoints snap together',(b.verts[1].co-world(0,-.6)).length<1e-5 and (b.verts[2].co-world(0,.6)).length<1e-5)
    ev('LEFTMOUSE','RELEASE')


@step
def edge_welded():
    b=bm()
    check('edge release creates a shared manifold edge',len(b.verts)==6 and len(b.faces)==2 and sum(len(e.link_faces)==2 for e in b.edges)==1)
    undo()


@step
def extend_tab():
    move(world(-.8,0));ev('TAB','PRESS')


@step
def extend_press():ev('LEFTMOUSE','PRESS')


@step
def extend_drag():move(world(0,0),dx=3)


@step
def extend_snap():
    check('Tab extension previews two weld targets',len(mod('operators.quad_draw').STATE['snap'])==2)
    ev('LEFTMOUSE','RELEASE')


@step
def extend_end():ev('TAB','RELEASE')


@step
def extend_result():
    b=bm()
    check('Tab extension joins the strips with one clean quad',len(b.verts)==8 and len(b.faces)==3 and sum(len(e.link_faces)==2 for e in b.edges)==2)
    check('extension leaves no collapsed or overlapping duplicate faces',all(f.calc_area()>1e-8 for f in b.faces) and len({frozenset(v.index for v in f.verts) for f in b.faces})==3)
    undo()


@step
def disabled_press():
    mod('operators.poly_draw').settings().qd_auto_weld=False
    press(world(-.8,-.6))


@step
def disabled_drag():move(C['target'],dx=4)


@step
def disabled_check():
    check('Auto-weld off disables live snapping',(bm().verts[1].co-C['target']).length>.005 and not mod('operators.quad_draw').STATE['snap'])
    ev('LEFTMOUSE','RELEASE')


@step
def disabled_result():
    check('Auto-weld off keeps vertices separate',len(bm().verts)==8)
    undo()


@step
def final_position_press():
    mod('operators.poly_draw').settings().qd_auto_weld=True
    press(world(-.8,-.6))


@step
def final_position_drag():move(C['target'],dx=4)


@step
def final_position_release():
    check('release-position test first acquires a snap target',bool(mod('operators.quad_draw').STATE['snap']))
    x,y=point(C['target'])
    ev('LEFTMOUSE','RELEASE',x=x+25,y=y)


@step
def final_position_result():
    check('release uses its final coordinates rather than welding a stale preview',len(bm().verts)==8 and (bm().verts[1].co-C['target']).length>.025)
    undo()


@step
def soft_press():
    mod('operators.poly_draw').settings().qd_auto_weld=True
    bpy.context.scene.allset_soft_select=True
    press(world(-.8,-.6))


@step
def soft_drag():move(C['target'],dx=4)


@step
def soft_check():
    check('Soft Selection disables the magnet even when Auto-weld is on',(bm().verts[1].co-C['target']).length>.005 and not mod('operators.quad_draw').STATE['snap'])
    ev('LEFTMOUSE','RELEASE')


@step
def filtering_and_tolerance():
    bpy.context.scene.allset_soft_select=False
    with override():
        ctx=bpy.context;a,r=view3d();rv=a.spaces.active.region_3d
        b=bm()
        back=b.verts.new((0,-.6,-world(0,-.6).z))
        hidden=b.verts.new((.4,0,3));hidden.hide=True
        mod('operators.quad_draw')._indices(b)
        back_id,hidden_id=back.index,hidden.index
        bmesh.update_edit_mesh(ctx.edit_object.data)
        magnet=mod('operators.quad_draw_weld').Magnet(ctx,ctx.edit_object,[1])
        magnet.project(ctx,r,rv)
        check('hidden vertices are excluded from target search',hidden_id not in magnet.allowed)
        check('a point behind the live sphere cannot be a weld target',not magnet.visible(ctx,r,rv,back_id))
        target=magnet.co[4]
        xy=view3d_utils.location_3d_to_region_2d(r,rv,target)
        def proposed(dx):
            return {1:view3d_utils.region_2d_to_location_3d(r,rv,xy+Vector((dx,0)),target)}
        _,pairs=magnet.query(ctx,r,rv,proposed(9))
        check('10 px tolerance captures a point nine actual pixels away',pairs.get(1)==4)
        _,pairs=magnet.query(ctx,r,rv,proposed(12))
        check('small cursor jitter keeps the already captured target',pairs.get(1)==4)
        _,pairs=magnet.query(ctx,r,rv,proposed(18))
        check('moving beyond the release radius returns to a free drag',not pairs)


run()
