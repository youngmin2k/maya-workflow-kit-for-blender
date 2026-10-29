"""Mouse-driven symmetric dot/fill/tweak, undo/cancel, strip width and options menu."""
import os,sys
from importlib import import_module
import bpy,bmesh
from mathutils import Quaternion,Vector
from bpy_extras import view3d_utils
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE,setup,step,run,view3d,win,ev,check,screenshot
C={};mod=lambda n:import_module(MODULE+'.operators.'+n)

def override():
    a,r=view3d();return bpy.context.temp_override(window=win(),area=a,region=r)
def world(x,y):return Vector((x,y,(9-x*x-y*y)**.5))
def xy(p):
    a,r=view3d();p=view3d_utils.location_3d_to_region_2d(r,a.spaces.active.region_3d,p)
    return r.x+round(p.x),r.y+round(p.y)
def move(p,**kw):
    x,y=xy(p);ev('MOUSEMOVE','NOTHING',x=x,y=y,**kw)
def bm():return bmesh.from_edit_mesh(bpy.context.edit_object.data)
def paired():
    vs=list(bm().verts)
    return all(min((u.co-Vector((-v.co.x,v.co.y,v.co.z))).length for u in vs)<1e-5 for v in vs)

@step
def prepare():
    setup()
    with override():
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=64,ring_count=32,radius=3)
        mod('live').set_objects(bpy.context.scene,[bpy.context.object])
        bpy.ops.allset.quad_draw_start()
        sym=bpy.context.scene.allset_symmetry;sym.on=True;sym.about='WORLD';sym.axis='X'
        mod('symmetry').apply(sym,[bpy.context.edit_object])
        a,r=view3d();rv=a.spaces.active.region_3d
        rv.view_rotation=Quaternion((1,0,0,0));rv.view_perspective='ORTHO';rv.view_location=(0,0,1);rv.view_distance=6

for x,y in ((.4,-.4),(1.2,-.4),(1.2,.4),(.4,.4)):
    @step
    def dot_press(x=x,y=y):
        move(world(x,y));ev('LEFTMOUSE','PRESS')
    @step
    def dot_release():ev('LEFTMOUSE','RELEASE')

@step
def dots_and_hover():
    check('World X creates four dot pairs on a live surface',len(bm().verts)==8 and paired())
    move(world(.8,0),shift=True);ev('LEFT_SHIFT','PRESS')
@step
def fill_press():
    p=mod('quad_draw').STATE['preview']
    check('symmetry keeps a local four-point fill preview',p is not None and p[0]=='FILL' and len(p[1])==4)
    ev('LEFTMOUSE','PRESS',shift=True)
@step
def fill_release():ev('LEFTMOUSE','RELEASE',shift=True);ev('LEFT_SHIFT','RELEASE')
@step
def face_result_and_grab():
    check('fill commits two faces with no loose dots',len(bm().faces)==2 and not mod('quad_draw').dots(bm()) and paired())
    C['before']=[tuple(v.co) for v in bm().verts]
    move(world(1.2,.4));ev('LEFTMOUSE','PRESS')
@step
def drag():move(world(1,.65))
@step
def live_pair_and_cancel():
    check('opposite point follows during dragging',paired() and max(v.co.y for v in bm().verts)>.5)
    ev('ESC','PRESS');ev('ESC','RELEASE');ev('LEFTMOUSE','RELEASE')
@step
def cancelled():
    check('Esc restores both sides and both faces',len(bm().faces)==2 and all(min((v.co-Vector(p)).length for v in bm().verts)<1e-6 for p in C['before']))
    move(world(1.2,.4));ev('LEFTMOUSE','PRESS')
@step
def drag_again():move(world(1,.65))
@step
def release():ev('LEFTMOUSE','RELEASE')
@step
def undo():
    check('released tweak remains symmetrical',paired())
    with override():bpy.ops.ed.undo()
@step
def restored_and_width_start():
    check('one Undo restores both sides',all(min((v.co-Vector(p)).length for v in bm().verts)<1e-6 for p in C['before']))
    C['width']=mod('poly_draw').settings().qd_strip_width
    move(world(0,1.5));ev('TAB','PRESS')
@step
def width_press():ev('MIDDLEMOUSE','PRESS')
@step
def width_drag():
    a,r=view3d();x,y=xy(world(0,1.5));ev('MOUSEMOVE','NOTHING',x=x+45,y=y)
@step
def width_release():
    check('Tab MMB outside mesh changes strip width without geometry',mod('poly_draw').settings().qd_strip_width>C['width'] and len(bm().faces)==2)
    ev('MIDDLEMOUSE','RELEASE');ev('TAB','RELEASE')
@step
def second_width():
    C['width']=mod('poly_draw').settings().qd_strip_width
    move(world(0,1.5));ev('TAB','PRESS')
@step
def second_press():ev('MIDDLEMOUSE','PRESS')
@step
def second_drag():
    x,y=xy(world(0,1.5));ev('MOUSEMOVE','NOTHING',x=x+30,y=y)
@step
def width_cancel():ev('ESC','PRESS');ev('ESC','RELEASE');ev('MIDDLEMOUSE','RELEASE');ev('TAB','RELEASE')
@step
def options():
    check('Esc restores the previous strip width',mod('poly_draw').settings().qd_strip_width==C['width'])
    move(world(0,1.5));ev('RIGHTMOUSE','PRESS',ctrl=True,shift=True)
@step
def menu_shot():
    if os.environ.get('ALLSET_GUI_SHOTS'):screenshot(os.path.join(os.environ['ALLSET_GUI_SHOTS'],'quad_options_menu.png'))
    ev('RIGHTMOUSE','RELEASE',ctrl=True,shift=True);ev('ESC','PRESS');ev('ESC','RELEASE')
run()
