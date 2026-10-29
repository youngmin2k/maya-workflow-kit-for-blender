"""Pick an evaluated posed-reference seam and commit the mirrored face shown by Shift hover."""
import bpy,bmesh,os,sys
from importlib import import_module
from mathutils import Matrix,Vector,Quaternion
from bpy_extras import view3d_utils
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE,setup,step,run,view3d,win,ev,check,screenshot
mod=lambda n:import_module(MODULE+'.operators.'+n)
C={}
def override():
 a,r=view3d();return bpy.context.temp_override(window=win(),area=a,region=r)
def bm():return bmesh.from_edit_mesh(bpy.context.edit_object.data)
def move(p,**kw):
 a,r=view3d();v=view3d_utils.location_3d_to_region_2d(r,a.spaces.active.region_3d,p)
 ev('MOUSEMOVE','NOTHING',x=r.x+round(v.x),y=r.y+round(v.y),**kw)
@step
def prepare():
 setup()
 with override():
  bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
  rb=bmesh.new();bmesh.ops.create_grid(rb,x_segments=4,y_segments=4,size=2)
  seam=next(e for e in rb.edges if len(e.link_faces)==2 and all(abs(v.co.x)<1e-6 for v in e.verts))
  transform=Matrix.Translation((5,7,3))@Matrix.Rotation(.4,4,'Z');C['transform']=transform
  for v in rb.verts:
   if v.co.x>0:v.co.z=v.co.x*.5
   v.co=transform@v.co
  C['seam']=sum((v.co for v in seam.verts),Vector())*.5
  me=bpy.data.meshes.new('posed_reference');rb.to_mesh(me);rb.free()
  ref=bpy.data.objects.new('posed_reference',me);bpy.context.scene.collection.objects.link(ref);C['reference']=ref.name
  subdivision=ref.modifiers.new('Evaluated seam','SUBSURF');subdivision.subdivision_type='SIMPLE';subdivision.levels=1
  C['seam']=transform@Vector((0,.25,0));bpy.context.view_layer.update()
  mod('live').set_objects(bpy.context.scene,[ref])
  me=bpy.data.meshes.new('retopo');ob=bpy.data.objects.new('retopo',me);bpy.context.scene.collection.objects.link(ob)
  ob.select_set(True);bpy.context.view_layer.objects.active=ob;bpy.ops.allset.quad_draw_start()
  state=bpy.context.scene.allset_symmetry;state.on=True;state.about='TOPOLOGY';state.axis='X'
  mod('symmetry').apply(state,[ob])
  mod('poly_draw').settings().qd_offset_on=False
  a,r=view3d();rv=a.spaces.active.region_3d;rv.view_rotation=Quaternion((1,0,0,0));rv.view_perspective='ORTHO';rv.view_location=(5,7,3);rv.view_distance=7
  bpy.ops.ed.undo_push(message='Posed live reference')
@step
def begin_picker():
 with override():
  state=bpy.context.scene.allset_symmetry;state.on=False;mod('symmetry').apply(state,[bpy.context.edit_object])
  bpy.ops.allset.quad_draw_pick_seam('INVOKE_DEFAULT',reference=True)
 move(C['seam'])
@step
def pick():ev('LEFTMOUSE','PRESS')
@step
def release():ev('LEFTMOUSE','RELEASE')
@step
def picked():
 check('reference picker binds the evaluated seam away from every axis',mod('quad_draw_reference').SEAM in bpy.data.objects[C['reference']])
 check('reference binding uses evaluated modifier topology',len(bpy.data.objects[C['reference']].evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices)>len(bpy.data.objects[C['reference']].data.vertices))
 check('picking a reference seam enables Topology symmetry',bpy.context.scene.allset_symmetry.on and bpy.context.scene.allset_symmetry.about=='TOPOLOGY')
 move(C['transform']@Vector((.35,-.5,.175)))
@step
def dot1():ev('LEFTMOUSE','PRESS')
@step
def dot1_end():ev('LEFTMOUSE','RELEASE')
@step
def next2():move(C['transform']@Vector((1.1,-.5,.55)))
@step
def dot2():ev('LEFTMOUSE','PRESS')
@step
def dot2_end():ev('LEFTMOUSE','RELEASE')
@step
def next3():move(C['transform']@Vector((1.1,.5,.55)))
@step
def dot3():ev('LEFTMOUSE','PRESS')
@step
def dot3_end():ev('LEFTMOUSE','RELEASE')
@step
def next4():move(C['transform']@Vector((.35,.5,.175)))
@step
def dot4():ev('LEFTMOUSE','PRESS')
@step
def dot4_end():ev('LEFTMOUSE','RELEASE')
@step
def hover():
 check('four real dot clicks create eight points on the posed paired surface',len(bm().verts)==8)
 move(C['transform']@Vector((.7,0,.35)),shift=True)
@step
def preview():
 q=mod('quad_draw');pv=q.STATE.get('topology_preview');C['preview']=pv
 check('Topology Shift hover includes a mirrored four-point face',pv is not None and pv[0]=='FILL' and len(pv[1])==4)
 if os.environ.get('ALLSET_GUI_SHOTS'):screenshot(os.path.join(os.environ['ALLSET_GUI_SHOTS'],'posed_reference_fill.png'))
 ev('LEFTMOUSE','PRESS',shift=True)
@step
def fill_release():ev('LEFTMOUSE','RELEASE',shift=True)
@step
def committed():
 check('Shift fill creates exactly two clean quads',len(bm().verts)==8 and len(bm().faces)==2 and all(len(f.verts)==4 for f in bm().faces))
 if C['preview']:
  check('committed counterpart equals the mirrored hover preview',any(all(min((v.co-p).length for v in f.verts)<1e-5 for p in C['preview'][1]) for f in bm().faces))
 with override():bpy.ops.ed.undo()
@step
def undone():check('one Undo removes both faces and restores all eight dots',not bm().faces and len(bm().verts)==8)
run()
