"""Symmetric mouse-driven bridge, extension weld, loop cut, delete, relax and edge weld."""
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
def world(x,y):return Vector((x,y,(16-x*x-y*y)**.5))
def move(x,y,**kw):
 a,r=view3d();p=view3d_utils.location_3d_to_region_2d(r,a.spaces.active.region_3d,world(x,y))
 ev('MOUSEMOVE','NOTHING',x=r.x+round(p.x),y=r.y+round(p.y),**kw)
def bm():return bmesh.from_edit_mesh(bpy.context.edit_object.data)
def paired():
 vs=list(bm().verts)
 return all(min((u.co-Vector((-v.co.x,v.co.y,v.co.z))).length for u in vs)<1e-5 for v in vs)
def undo():
 with override():bpy.ops.ed.undo()
@step
def prepare():
 setup()
 with override():
  bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
  bpy.ops.mesh.primitive_uv_sphere_add(segments=64,ring_count=32,radius=4)
  mod('live').set_objects(bpy.context.scene,[bpy.context.object])
  co=[world(x,y) for x,y in ((.4,-.6),(1.2,-.6),(1.2,.6),(.4,.6),(1.6,-.6),(2.4,-.6),(2.4,.6),(1.6,.6))]
  co+= [Vector((-v.x,v.y,v.z)) for v in co]
  me=bpy.data.meshes.new('retopo');me.from_pydata(co,[],[(0,1,2,3),(4,5,6,7),(11,10,9,8),(15,14,13,12)])
  ob=bpy.data.objects.new('retopo',me);bpy.context.scene.collection.objects.link(ob)
  ob.select_set(True);bpy.context.view_layer.objects.active=ob
  bpy.ops.allset.quad_draw_start()
  sy=bpy.context.scene.allset_symmetry;sy.on=True;sy.about='WORLD';sy.axis='X'
  mod('symmetry').apply(sy,[ob])
  a,r=view3d();rv=a.spaces.active.region_3d;rv.view_rotation=Quaternion((1,0,0,0));rv.view_perspective='ORTHO';rv.view_location=(0,0,1);rv.view_distance=8
  bpy.ops.ed.undo_push(message='Symmetric Quad Draw fixture')
@step
def bridge():move(1.4,0,shift=True);ev('LEFT_SHIFT','PRESS')
@step
def bridge_press():ev('LEFTMOUSE','PRESS',shift=True)
@step
def bridge_release():ev('LEFTMOUSE','RELEASE',shift=True);ev('LEFT_SHIFT','RELEASE')
@step
def bridge_result():
 check('bridge fills both gaps using existing vertices',len(bm().faces)==6 and len(bm().verts)==16 and paired());undo()
@step
def tab_start():move(1.2,0);ev('TAB','PRESS')
@step
def tab_press():ev('LEFTMOUSE','PRESS')
@step
def tab_drag():move(1.6,0)
@step
def tab_release():ev('LEFTMOUSE','RELEASE');ev('TAB','RELEASE')
@step
def tab_result():
 check('extension weld bridges both sides without duplicate vertices',len(bm().faces)==6 and len(bm().verts)==16 and paired());undo()
@step
def cut():move(.8,.6,ctrl=True);ev('LEFT_CTRL','PRESS')
@step
def cut_press():ev('LEFTMOUSE','PRESS',ctrl=True)
@step
def cut_release():ev('LEFTMOUSE','RELEASE',ctrl=True);ev('LEFT_CTRL','RELEASE')
@step
def cut_result():
 check('Ctrl cut splits both faces with corresponding new points',len(bm().faces)==6 and len(bm().verts)==20 and paired());undo()
@step
def delete():move(2,0,ctrl=True,shift=True);ev('LEFTMOUSE','PRESS',ctrl=True,shift=True)
@step
def delete_release():ev('LEFTMOUSE','RELEASE',ctrl=True,shift=True)
@step
def delete_result():
 check('Ctrl Shift face deletion removes both counterparts',len(bm().faces)==2 and paired());undo()
@step
def relax_press():
 C['co']=[tuple(v.co) for v in bm().verts]
 move(.4,-.6,shift=True);ev('LEFTMOUSE','PRESS',shift=True)
@step
def relax_drag():move(.45,-.55,shift=True)
@step
def relax_cancel():
 check('relax keeps paired coordinates',paired());ev('ESC','PRESS');ev('ESC','RELEASE');ev('LEFTMOUSE','RELEASE')
@step
def relax_result():
 check('Esc cancels relaxation on both sides',all(min((v.co-Vector(p)).length for v in bm().verts)<1e-6 for p in C['co']))
 move(1.2,0);ev('LEFTMOUSE','PRESS')
@step
def edge_drag():move(1.6,0)
@step
def edge_release():ev('LEFTMOUSE','RELEASE')
@step
def edge_result():
 check('edge weld joins both pairs of strips',len(bm().verts)==12 and len(bm().faces)==4 and paired())
 check('edge weld preserves consistent normals and manifold incidence',all(len(e.link_faces)<=2 for e in bm().edges) and all(f.normal.z>0 for f in bm().faces))
 undo()
@step
def undo_result():check('one Undo restores all four strips',len(bm().verts)==16 and len(bm().faces)==4 and paired())
run()
