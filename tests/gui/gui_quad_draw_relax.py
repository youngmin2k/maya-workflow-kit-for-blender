"""Mouse-driven Soft Selection relax: held region, reversible scrub, live projection, cancellation and Undo."""
import bpy,bmesh,os,sys,numpy as np
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
 b=bmesh.from_edit_mesh(bpy.context.edit_object.data);b.verts.ensure_lookup_table();return b
def co():return np.asarray([v.co[:] for v in bm().verts])
def point(p):
 a,r=view3d();v=view3d_utils.location_3d_to_region_2d(r,a.spaces.active.region_3d,Vector(p));return r.x+round(v.x),r.y+round(v.y)
def at_press(dx=0):
 x,y=C['press'];ev('MOUSEMOVE','NOTHING',x=x+dx,y=y,shift=True)
def undo():
 with override():bpy.ops.ed.undo()
def image(name):
 p=Path(os.environ.get('ALLSET_GUI_SHOTS',os.path.dirname(sys.argv[-1])))/(name+'.png');screenshot(str(p))
 im=bpy.data.images.load(str(p),check_existing=False);w,h=im.size
 values=np.empty(w*h*4,dtype='float32');im.pixels.foreach_get(values);bpy.data.images.remove(im)
 a,r=view3d();return values.reshape(h,w,4)[r.y:r.y+r.height,r.x:r.x+r.width,:3]
@step
def prepare():
 setup()
 with override():
  bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
  bpy.ops.mesh.primitive_uv_sphere_add(radius=3,segments=96,ring_count=48)
  mod('live').set_objects(bpy.context.scene,[bpy.context.object])
  bpy.ops.mesh.primitive_grid_add(x_subdivisions=8,y_subdivisions=8,size=2)
  ob=bpy.context.object
  center=min(ob.data.vertices,key=lambda v:v.co.length);center.co.x+=.12
  for v in ob.data.vertices:v.co.z=(9-v.co.x*v.co.x-v.co.y*v.co.y)**.5
  C['center']=center.index
  bpy.ops.allset.quad_draw_start()
  state=bpy.context.scene.allset_symmetry;state.on=False;mod('symmetry').apply(state,[ob])
  bpy.context.scene.allset_soft_select=False;mod('poly_draw').settings().qd_relax='ALL'
  bpy.context.scene.tool_settings.proportional_size=.55
  for seq in (bm().verts,bm().edges,bm().faces):
   for el in seq:el.select=False
  a,r=view3d();rv=a.spaces.active.region_3d;rv.view_rotation=Quaternion((1,0,0,0));rv.view_perspective='ORTHO';rv.view_location=(0,0,2);rv.view_distance=6
  C['original']=co();C['faces']=len(bm().faces);bpy.ops.ed.undo_push(message='Soft relax fixture')
@step
def baseline():
 C['base_image']=image('relax_before_soft');bpy.context.scene.allset_soft_select=True
 x,y=point(bm().verts[C['center']].co);C['press']=(x,y);ev('MOUSEMOVE','NOTHING',x=x,y=y)
@step
def soft_preview():
 area=mod('quad_draw').STATE.get('relax_area')
 check('Soft Selection hover previews a multi-vertex influence area',area is not None and np.count_nonzero(area['weights'])>4)
 data=image('relax_soft_influence')
 check('Soft Selection has a visible falloff tint without extra dots',np.count_nonzero(data[:,:,0]-C['base_image'][:,:,0]>.08)>100)
 ev('MIDDLEMOUSE','PRESS',shift=True)
@step
def scrub_right():at_press(48)
@step
def scrubbed():
 current=co();C['right_error']=np.linalg.norm(current-C['original']);C['accepted']=current.copy()
 check('Shift MMB relax affects nearby vertices beyond the seed component',np.count_nonzero(np.linalg.norm(current-C['original'],axis=1)>1e-6)>4)
 check('relaxation retains topology and projects onto the curved live surface',len(bm().faces)==C['faces'] and np.max(abs(np.linalg.norm(current,axis=1)-3))<.005)
 before=C['original'];outside=np.linalg.norm(before-before[C['center']],axis=1)>.55+1e-5
 check('vertices outside the held Soft Selection radius stay unchanged',np.max(abs(current[outside]-before[outside]))<1e-7)
 at_press(24)
@step
def partial_reverse():
 check('dragging left reduces the same stroke relaxation',0<np.linalg.norm(co()-C['original'])<C['right_error'])
 at_press(0)
@step
def at_origin():
 check('returning to the press position restores the exact initial coordinates',np.max(abs(co()-C['original']))<1e-7)
 at_press(48)
@step
def cancel():ev('ESC','PRESS');ev('ESC','RELEASE');ev('MIDDLEMOUSE','RELEASE')
@step
def cancelled():
 check('Escape restores a non-symmetric relax stroke',np.max(abs(co()-C['original']))<1e-7)
 check('cancel discards the held influence preview',mod('quad_draw').STATE.get('relax_area') is None)
 at_press(0);ev('MIDDLEMOUSE','PRESS',shift=True)
@step
def accept_right():at_press(48)
@step
def accept_release():
 C['accepted']=co();ev('MIDDLEMOUSE','RELEASE',shift=True)
@step
def accepted():
 check('release commits the visible relax result',np.max(abs(co()-C['accepted']))<1e-7 and np.linalg.norm(co()-C['original'])>1e-5)
 undo()
@step
def undone():
 check('one Undo restores the complete relax stroke',np.max(abs(co()-C['original']))<1e-7)
 with override():bpy.ops.ed.redo()
@step
def redone():
 check('Redo reapplies the accepted relax result',np.max(abs(co()-C['accepted']))<1e-7);undo()
@step
def repeat_press():at_press(0);ev('MIDDLEMOUSE','PRESS',shift=True)
for dx in (12,24,36,48):
 @step
 def repeat_move(dx=dx):at_press(dx)
@step
def repeat_result():
 check('the same scrub distance produces the same geometry independent of event count',np.max(abs(co()-C['accepted']))<2e-6)
 ev('ESC','PRESS');ev('ESC','RELEASE');ev('MIDDLEMOUSE','RELEASE')
@step
def brush_press():
 bpy.context.scene.allset_soft_select=False;at_press(0);ev('LEFTMOUSE','PRESS',shift=True)
@step
def brush_drag():at_press(20)
@step
def brush_cancel():
 check('Shift LMB still paints relaxation without Soft Selection',np.linalg.norm(co()-C['original'])>1e-5)
 ev('ESC','PRESS');ev('ESC','RELEASE');ev('LEFTMOUSE','RELEASE')
@step
def brush_restored():
 check('Escape also restores ordinary Shift LMB brush strokes',np.max(abs(co()-C['original']))<1e-7)
 with override():bpy.ops.allset.quad_draw_exit()
@step
def exit_wait():pass
@step
def exit_released():
 q=mod('quad_draw');overlay=mod('quad_draw_overlay');relax=mod('quad_draw_relax')
 check('tool exit releases loop, influence and display caches',q._component_loop_cache is None and relax._preview is None and overlay._relax_preview is None and overlay._delete_preview is None)
run()
