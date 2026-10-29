"""Maya-style Tab extend/strip: shared plane targets, projected preview, cancel and weld switches."""
import os,sys,bpy,bmesh
from importlib import import_module
from mathutils import Vector,Quaternion
from bpy_extras import view3d_utils
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE,setup,step,run,view3d,win,ev,check,screenshot
mod=lambda n:import_module(MODULE+'.operators.'+n)
C={}
def override():
 a,r=view3d();return bpy.context.temp_override(window=win(),area=a,region=r)
def bm():
 b=bmesh.from_edit_mesh(bpy.context.edit_object.data);b.verts.ensure_lookup_table();return b
def world(x,y):return Vector((x,y,(9-x*x-y*y)**.5))
def xy(w):
 a,r=view3d();p=view3d_utils.location_3d_to_region_2d(r,a.spaces.active.region_3d,w)
 return r.x+round(p.x),r.y+round(p.y)
def move(w,dx=0):
 x,y=xy(w);ev('MOUSEMOVE','NOTHING',x=x+dx,y=y)
def undo():
 with override():bpy.ops.ed.undo()
@step
def prepare():
 setup()
 with override():
  bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
  bpy.ops.mesh.primitive_uv_sphere_add(radius=3,segments=64,ring_count=32)
  mod('live').set_objects(bpy.context.scene,[bpy.context.object])
  co=[world(x,y) for x,y in ((.35,-.5),(1.1,-.5),(1.1,.5),(.35,.5))]
  co += [Vector((-p.x,p.y,p.z)) for p in co]
  me=bpy.data.meshes.new('extend_seam');me.from_pydata(co,[],[(0,1,2,3),(7,6,5,4)])
  ob=bpy.data.objects.new('extend_seam',me);bpy.context.scene.collection.objects.link(ob);ob.select_set(True);bpy.context.view_layer.objects.active=ob
  bpy.ops.allset.quad_draw_start()
  sy=bpy.context.scene.allset_symmetry;sy.on=True;sy.about='WORLD';sy.axis='X';mod('symmetry').apply(sy,[ob])
  a,r=view3d();rv=a.spaces.active.region_3d;rv.view_rotation=Quaternion((1,0,0,0));rv.view_perspective='ORTHO';rv.view_location=(0,0,1);rv.view_distance=6
  bpy.ops.ed.undo_push(message='Extend seam fixture')
@step
def tab():move(world(.35,0));ev('TAB','PRESS')
@step
def press():ev('LEFTMOUSE','PRESS')
@step
def drag():move(world(0,0),8)
@step
def preview():
 p=mod('quad_draw').STATE['preview'];markers=mod('quad_draw').STATE['snap']
 check('Tab extension previews two points on the symmetry plane',p is not None and len(markers)==2 and all(abs(v.x)<1e-6 for v in markers))
 check('extension preview allocates no mesh geometry',len(bm().verts)==8 and len(bm().faces)==2)
 ev('ESC','PRESS');ev('ESC','RELEASE');ev('LEFTMOUSE','RELEASE');ev('TAB','RELEASE')
@step
def cancelled():
 check('Escape cancels extension on both sides',len(bm().verts)==8 and len(bm().faces)==2)
 move(world(.35,0));ev('TAB','PRESS')
@step
def press2():ev('LEFTMOUSE','PRESS')
@step
def drag2():move(world(0,0),8)
@step
def release():ev('LEFTMOUSE','RELEASE');ev('TAB','RELEASE')
@step
def joined():
 b=bm()
 check('extension creates two new quads sharing their center edge',len(b.verts)==10 and len(b.faces)==4 and sum(len(e.link_faces)==2 and all(abs(v.co.x)<1e-6 for v in e.verts) for e in b.edges)==1)
 check('extension keeps clean quad topology',all(len(f.verts)==4 and f.calc_area()>1e-7 and f.normal.z>0 for f in b.faces))
 undo()
@step
def off():
 mod('poly_draw').settings().qd_auto_weld=False
 move(world(.35,0));ev('TAB','PRESS')
@step
def off_press():ev('LEFTMOUSE','PRESS')
@step
def off_drag():move(world(0,0),8)
@step
def off_preview():
 check('Auto-weld off disables extension plane capture',not mod('quad_draw').STATE['snap'])
 ev('LEFTMOUSE','RELEASE');ev('TAB','RELEASE')
@step
def off_result():
 check('Auto-weld off leaves two separate new border edges',len(bm().verts)==12 and len(bm().faces)==4 and not any(abs(v.co.x)<1e-6 for v in bm().verts))
 undo()
@step
def strip_start():
 mod('poly_draw').settings().qd_auto_weld=True
 x,y=xy(world(0,1.2));a,r=view3d();width=mod('poly_draw').settings().qd_strip_width*bpy.context.preferences.system.ui_scale
 C['strip']=(x+round(width/2)+4,y)
 ev('MOUSEMOVE','NOTHING',x=C['strip'][0],y=y);ev('TAB','PRESS')
@step
def strip_press():ev('LEFTMOUSE','PRESS')
for distance in (30,60,90,120):
 @step
 def strip_move(distance=distance):
  x,y=C['strip'];ev('MOUSEMOVE','NOTHING',x=x,y=y+distance)
@step
def strip_preview():
 C['seam_markers']=[p.copy() for p in mod('quad_draw').STATE['snap']]
 check('strip previews projected seam points before geometry exists',len(C['seam_markers'])>=3 and all(abs(p.x)<1e-6 for p in C['seam_markers']) and len(bm().verts)==8)
 ev('LEFTMOUSE','RELEASE');ev('TAB','RELEASE')
@step
def strip_result():
 b=bm();center=[v for v in b.verts if abs(v.co.x)<1e-6]
 check('strip commits exactly the seam positions shown in preview',len(center)==len(C['seam_markers']) and all(min((v.co-p).length for v in center)<1e-5 for p in C['seam_markers']))
 check('mirrored strips share manifold center edges',len(center)>=3 and sum(len(e.link_faces)==2 and all(abs(v.co.x)<1e-6 for v in e.verts) for e in b.edges)==len(center)-1)
 check('strip leaves no degenerate or duplicate quads',all(f.calc_area()>1e-7 and len(f.verts)==4 for f in b.faces) and len({frozenset(v.index for v in f.verts) for f in b.faces})==len(b.faces))
 if os.environ.get('ALLSET_GUI_SHOTS'):screenshot(os.path.join(os.environ['ALLSET_GUI_SHOTS'],'extend_strip_seam.png'))
 undo()
@step
def strip_undo():check('one Undo removes the entire two-sided strip',len(bm().verts)==8 and len(bm().faces)==2)
@step
def click_start():move(world(.35,0));ev('TAB','PRESS')
@step
def click_press():ev('LEFTMOUSE','PRESS')
@step
def click_release():ev('LEFTMOUSE','RELEASE');ev('TAB','RELEASE')
@step
def no_drag():
 check('Tab click without dragging creates no geometry',len(bm().verts)==8 and len(bm().faces)==2)
 bpy.context.scene.allset_soft_select=True;move(world(.35,0));ev('TAB','PRESS')
@step
def soft_press():ev('LEFTMOUSE','PRESS')
@step
def soft_drag():move(world(0,0),8)
@step
def soft_preview():
 check('Soft Selection disables plane capture during extension',not mod('quad_draw').STATE['snap'])
 ev('LEFTMOUSE','RELEASE');ev('TAB','RELEASE')
@step
def soft_committed():
 check('Soft Selection extension leaves two separate borders',len(bm().verts)==12 and len(bm().faces)==4 and not any(abs(v.co.x)<1e-6 for v in bm().verts))
 undo()
@step
def narrow_gap():
 bpy.context.scene.allset_soft_select=False
 with override():
  b=bm()
  for i,x in ((0,.08),(3,.04),(4,-.08),(7,-.04)):b.verts[i].co=world(x,b.verts[i].co.y)
  bmesh.update_edit_mesh(bpy.context.edit_object.data);mod('preselect').invalidate()
 move(world(.06,0));ev('TAB','PRESS')
@step
def narrow_press():ev('LEFTMOUSE','PRESS')
@step
def narrow_drag():move(world(0,0))
@step
def narrow_preview():
 points=mod('quad_draw').STATE['snap']
 check('extension across a narrow wedge prefers the center over its own anchors',len(points)==2 and all(abs(p.x)<1e-6 for p in points))
 ev('LEFTMOUSE','RELEASE');ev('TAB','RELEASE')
@step
def narrow_result():
 b=bm();check('narrow-wedge extension keeps both quads instead of collapsing one into a triangle',len(b.verts)==10 and len(b.faces)==4 and all(len(f.verts)==4 and f.calc_area()>1e-7 for f in b.faces))
run()
