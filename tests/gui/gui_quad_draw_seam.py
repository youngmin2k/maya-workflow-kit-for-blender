"""Pixel-tolerant symmetric center weld: live capture, hysteresis, cancel, vertex/edge, off switches."""
import bpy,bmesh,os,sys
from importlib import import_module
from mathutils import Quaternion,Vector
from bpy_extras import view3d_utils
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE,setup,step,run,view3d,win,ev,check
mod=lambda n:import_module(MODULE+'.operators.'+n)
C={}
def override():
 a,r=view3d();return bpy.context.temp_override(window=win(),area=a,region=r)
def world(x,y):return Vector((x,y,(9-x*x-y*y)**.5))
def bm():
 b=bmesh.from_edit_mesh(bpy.context.edit_object.data);b.verts.ensure_lookup_table();return b
def pixel(p):
 a,r=view3d();q=view3d_utils.location_3d_to_region_2d(r,a.spaces.active.region_3d,p)
 return r.x+round(q.x),r.y+round(q.y)
def move(p,offset=0):
 x,y=pixel(p);ev('MOUSEMOVE','NOTHING',x=x+offset,y=y)
def undo():
 with override():bpy.ops.ed.undo()
def seam_pair():return abs(bm().verts[0].co.x)<1e-6 and abs(bm().verts[4].co.x)<1e-6
@step
def prepare():
 setup()
 with override():
  bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
  bpy.ops.mesh.primitive_uv_sphere_add(radius=3,segments=64,ring_count=32)
  mod('live').set_objects(bpy.context.scene,[bpy.context.object])
  co=[world(x,y) for x,y in ((.35,-.5),(1.1,-.5),(1.1,.5),(.35,.5))]
  co += [Vector((-p.x,p.y,p.z)) for p in co]
  me=bpy.data.meshes.new('seam');me.from_pydata(co,[],[(0,1,2,3),(7,6,5,4)])
  ob=bpy.data.objects.new('seam',me);bpy.context.scene.collection.objects.link(ob)
  ob.select_set(True);bpy.context.view_layer.objects.active=ob;bpy.ops.allset.quad_draw_start()
  sy=bpy.context.scene.allset_symmetry;sy.on=True;sy.about='WORLD';sy.axis='X';mod('symmetry').apply(sy,[ob])
  a,r=view3d();rv=a.spaces.active.region_3d;rv.view_rotation=Quaternion((1,0,0,0));rv.view_perspective='ORTHO';rv.view_location=(0,0,1);rv.view_distance=6
  C['before']=[tuple(v.co) for v in bm().verts]
  bpy.ops.ed.undo_push(message='Symmetric seam fixture')
@step
def press():move(world(.35,-.5));ev('LEFTMOUSE','PRESS')
@step
def capture():move(world(0,-.5),8)
@step
def captured():
 check('near-plane drag snaps both points exactly to the center before release',seam_pair() and len(bm().verts)==8)
 check('the symmetry plane target has a live marker',bool(mod('quad_draw').STATE['snap']))
 move(world(0,-.5),12)
@step
def hysteresis():
 check('small cursor jitter retains the acquired center target',seam_pair())
 move(world(0,-.5),19)
@step
def free_drag():
 check('leaving the capture margin restores free symmetric dragging',not seam_pair() and not mod('quad_draw').STATE['snap'])
 move(world(0,-.5),8)
@step
def cancel():
 check('returning to the plane reacquires the target',seam_pair())
 ev('ESC','PRESS');ev('ESC','RELEASE');ev('LEFTMOUSE','RELEASE')
@step
def cancelled():
 check('Esc restores both original sides without welding',len(bm().verts)==8 and all(min((v.co-Vector(p)).length for v in bm().verts)<1e-6 for p in C['before']))
 move(world(.35,-.5));ev('LEFTMOUSE','PRESS')
@step
def vertex_drag():move(world(0,-.5),8)
@step
def vertex_release():ev('LEFTMOUSE','RELEASE')
@step
def vertex_result():
 check('vertex release makes one center vertex with both quads intact',len(bm().verts)==7 and len(bm().faces)==2 and sum(abs(v.co.x)<1e-6 for v in bm().verts)==1)
 undo()
@step
def edge_press():move(world(.35,0));ev('LEFTMOUSE','PRESS')
@step
def edge_drag():move(world(0,0),8)
@step
def edge_preview():
 check('edge drag snaps both endpoint pairs to the center',all(abs(bm().verts[i].co.x)<1e-6 for i in (0,3,4,7)) and len(bm().verts)==8)
 ev('LEFTMOUSE','RELEASE')
@step
def edge_result():
 check('edge release creates one shared center edge',len(bm().verts)==6 and len(bm().faces)==2 and sum(len(e.link_faces)==2 for e in bm().edges)==1)
 check('center edge has two correctly wound non-degenerate quads',all(len(f.verts)==4 and f.calc_area()>1e-6 and f.normal.z>0 for f in bm().faces))
 undo()
@step
def off_press():
 mod('poly_draw').settings().qd_auto_weld=False
 move(world(.35,-.5));ev('LEFTMOUSE','PRESS')
@step
def off_drag():move(world(0,-.5),8)
@step
def off_result():
 check('Auto-weld off disables virtual center snapping',not seam_pair() and not mod('quad_draw').STATE['snap'])
 ev('LEFTMOUSE','RELEASE')
@step
def off_released():
 check('Auto-weld off leaves opposite vertices separate',len(bm().verts)==8)
 undo()
@step
def soft_press():
 mod('poly_draw').settings().qd_auto_weld=True;bpy.context.scene.allset_soft_select=True
 move(world(.35,-.5));ev('LEFTMOUSE','PRESS')
@step
def soft_drag():move(world(0,-.5),8)
@step
def soft_result():
 check('Soft Selection also disables virtual center snapping',not seam_pair() and not mod('quad_draw').STATE['snap'])
 ev('ESC','PRESS');ev('ESC','RELEASE');ev('LEFTMOUSE','RELEASE')
@step
def side_view():
 bpy.context.scene.allset_soft_select=False
 with override():
  a,r=view3d();a.spaces.active.region_3d.view_rotation=Quaternion((0,1,0),1.57079632679)
@step
def side_result():
 with override():
  q=mod('quad_draw');sy=mod('quad_draw_symmetry');b=bm();ob=bpy.context.edit_object
  stroke=sy.begin(bpy.context,ob,b,coordinate_only=True)
  w=ob.matrix_world@b.verts[1].co
  from types import SimpleNamespace
  result,marks=stroke.snap_seam(bpy.context,bpy.context.region,bpy.context.region_data,{1:w},SimpleNamespace(pairs={}))
  check('side views do not pull distant points through the live object',not marks and (result[1]-w).length<1e-6)
  stroke.close()
run()
