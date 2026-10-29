"""A shared closed ring on an asymmetric live surface must commit once, including Ctrl MMB and Undo."""
import os,sys,math,bpy,bmesh,numpy as np
from pathlib import Path
from importlib import import_module
from mathutils import Vector,Quaternion
from bpy_extras import view3d_utils
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sim import MODULE,setup,step,run,view3d,win,ev,check,screenshot
mod=lambda n:import_module(MODULE+'.operators.'+n)
C={}
def override():
 a,r=view3d();return bpy.context.temp_override(window=win(),area=a,region=r)
def bm():
 b=bmesh.from_edit_mesh(bpy.context.edit_object.data);b.verts.ensure_lookup_table();b.edges.ensure_lookup_table();return b
def co():return np.asarray([v.co[:] for v in bm().verts])
def move(t=.35):
 b=bm();a,bv=b.verts[10],b.verts[22]
 p=bpy.context.edit_object.matrix_world@a.co.lerp(bv.co,t)
 area,r=view3d();xy=view3d_utils.location_3d_to_region_2d(r,area.spaces.active.region_3d,p)
 ev('MOUSEMOVE','NOTHING',x=r.x+round(xy.x),y=r.y+round(xy.y),ctrl=True)
@step
def prepare():
 setup()
 with override():
  bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
  bpy.ops.mesh.primitive_uv_sphere_add(radius=2,segments=96,ring_count=48)
  ref=bpy.context.object
  for v in ref.data.vertices:v.co.x*=1+.025*(1-v.co.x/2);v.co.z+=v.co.x*.012
  mod('live').set_objects(bpy.context.scene,[ref])
  points=[(math.sqrt(4-z*z)*math.cos(i*math.tau/12),math.sqrt(4-z*z)*math.sin(i*math.tau/12),z) for z in (-.6,0,.6) for i in range(12)]
  faces=[(row*12+i,row*12+(i+1)%12,(row+1)*12+(i+1)%12,(row+1)*12+i) for row in range(2) for i in range(12)]
  me=bpy.data.meshes.new('asymmetric_cut');me.from_pydata(points,[],faces);ob=bpy.data.objects.new('asymmetric_cut',me);bpy.context.scene.collection.objects.link(ob)
  ob.select_set(True);bpy.context.view_layer.objects.active=ob;bpy.ops.allset.quad_draw_start()
  state=bpy.context.scene.allset_symmetry;state.on=True;state.about='WORLD';state.axis='X';mod('symmetry').apply(state,[ob])
  mod('poly_draw').settings().qd_offset_on=False
  for seq in (bm().verts,bm().edges,bm().faces):
   for el in seq:el.select=False
  area,r=view3d();rv=area.spaces.active.region_3d;rv.view_rotation=Quaternion((1,0,0),math.pi/2);rv.view_perspective='ORTHO';rv.view_location=(0,0,0);rv.view_distance=7
  C['original']=co();bpy.ops.ed.undo_push(message='Asymmetric live closed ring')
@step
def hover():move()
@step
def preview():
 pv=mod('quad_draw').STATE['preview'];C['preview_count']=len(pv[1]) if pv and pv[0]=='LOOP' else 0
 check('Ctrl previews the closed twelve-face ring',C['preview_count']==12)
 ev('LEFTMOUSE','PRESS',ctrl=True)
@step
def release():ev('LEFTMOUSE','RELEASE',ctrl=True)
@step
def committed():
 b=bm();check('Ctrl LMB commits the shared ring exactly once with symmetry enabled',len(b.verts)==48 and len(b.faces)==36)
 check('cut retains clean connected quads',all(len(f.verts)==4 and f.calc_area()>1e-7 for f in b.faces) and all(len(e.link_faces)<=2 for e in b.edges) and all(v.link_faces for v in b.verts))
 data=co();reflected=data.copy();reflected[:,0]*=-1
 check('live projection cannot break the paired cut vertices',all(np.min(np.linalg.norm(data-p,axis=1))<2e-6 for p in reflected))
 C['committed']=data
 if os.environ.get('ALLSET_GUI_SHOTS'):screenshot(os.path.join(os.environ['ALLSET_GUI_SHOTS'],'asymmetric_closed_cut.png'))
 with override():bpy.ops.ed.undo()
@step
def undone():
 check('one Undo restores the original closed strip',len(bm().verts)==36 and len(bm().faces)==24 and np.max(abs(co()-C['original']))<1e-7)
 with override():bpy.ops.ed.redo()
@step
def redone():
 check('Redo restores the complete accepted cut',co().shape==C['committed'].shape and np.max(abs(co()-C['committed']))<1e-7)
 with override():bpy.ops.ed.undo()
@step
def center_hover():move(.5)
@step
def center_press():ev('MIDDLEMOUSE','PRESS',ctrl=True)
@step
def center_release():ev('MIDDLEMOUSE','RELEASE',ctrl=True)
@step
def centered():
 check('Ctrl MMB also commits a single centered closed ring',len(bm().verts)==48 and len(bm().faces)==36)
 with override():bpy.ops.ed.undo()
@step
def offset_hover():
 mod('poly_draw').settings().qd_offset_on=True;mod('poly_draw').settings().qd_surface_offset=.01
 move()
@step
def offset_press():ev('LEFTMOUSE','PRESS',ctrl=True)
@step
def offset_release():ev('LEFTMOUSE','RELEASE',ctrl=True)
@step
def offset_cut():
 check('a nonzero live offset does not cancel the shared cut',len(bm().verts)==48 and len(bm().faces)==36)
 with override():bpy.ops.ed.undo()
@step
def ordinary_hover():
 mod('poly_draw').settings().qd_offset_on=False
 with override():bpy.ops.allset.symmetry(mode='OFF')
 move()
@step
def ordinary_press():ev('LEFTMOUSE','PRESS',ctrl=True)
@step
def ordinary_release():ev('LEFTMOUSE','RELEASE',ctrl=True)
@step
def ordinary_cut():check('ordinary Ctrl cutting still works with symmetry off',len(bm().verts)==48 and len(bm().faces)==36)
run()
