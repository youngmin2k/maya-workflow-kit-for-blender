"""Both sides of a border-loop delete/tweak, clean topology, cancel and Undo."""
import os,sys,bpy,bmesh,numpy as np
from pathlib import Path
from importlib import import_module
from mathutils import Vector,Quaternion
from bpy_extras import view3d_utils
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sim import MODULE,setup,step,run,view3d,win,ev,check
mod=lambda n:import_module(MODULE+'.operators.'+n)
C={}
def override():
 a,r=view3d();return bpy.context.temp_override(window=win(),area=a,region=r)
def bm():
 b=bmesh.from_edit_mesh(bpy.context.edit_object.data);b.verts.ensure_lookup_table();return b
def co():return np.asarray([v.co[:] for v in bm().verts])
def world(x,y):return Vector((x,y,(9-x*x-y*y)**.5))
def move(p):
 a,r=view3d();v=view3d_utils.location_3d_to_region_2d(r,a.spaces.active.region_3d,p)
 ev('MOUSEMOVE','NOTHING',x=r.x+round(v.x),y=r.y+round(v.y),ctrl=True,shift=True)
def undo():
 with override():bpy.ops.ed.undo()
@step
def prepare():
 setup()
 with override():
  bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
  bpy.ops.mesh.primitive_uv_sphere_add(radius=3,segments=96,ring_count=48);mod('live').set_objects(bpy.context.scene,[bpy.context.object])
  points=[world(.4+i*.25,-.5+j*.25) for j in range(5) for i in range(5)]
  faces=[(j*5+i,j*5+i+1,(j+1)*5+i+1,(j+1)*5+i) for j in range(4) for i in range(4)]
  points += [Vector((-p.x,p.y,p.z)) for p in points]
  faces += [tuple(i+25 for i in reversed(f)) for f in list(faces)]
  me=bpy.data.meshes.new('loop_symmetry');me.from_pydata(points,[],faces);ob=bpy.data.objects.new('loop_symmetry',me);bpy.context.scene.collection.objects.link(ob)
  ob.select_set(True);bpy.context.view_layer.objects.active=ob;bpy.ops.allset.quad_draw_start()
  state=bpy.context.scene.allset_symmetry;state.on=True;state.about='WORLD';state.axis='X';mod('symmetry').apply(state,[ob]);bpy.context.scene.allset_soft_select=False
  a,r=view3d();rv=a.spaces.active.region_3d;rv.view_rotation=Quaternion((1,0,0,0));rv.view_perspective='ORTHO';rv.view_location=(0,0,1);rv.view_distance=6
  C['original']=co();bpy.ops.ed.undo_push(message='Paired border loops')
@step
def hover():move(world(.775,-.5))
@step
def click():ev('LEFTMOUSE','PRESS',ctrl=True,shift=True)
@step
def release():ev('LEFTMOUSE','RELEASE',ctrl=True,shift=True)
@step
def deleted():
 b=bm();check('border-loop delete removes both symmetrical face strips',len(b.faces)==24 and len(b.verts)==40)
 check('mirrored border deletion keeps clean quads and manifold edges',all(len(f.verts)==4 and f.calc_area()>1e-7 and f.normal.z>0 for f in b.faces) and all(len(e.link_faces)<=2 for e in b.edges))
 undo()
@step
def delete_undone():
 check('one Undo restores both deleted border strips',len(bm().verts)==50 and len(bm().faces)==32 and np.max(abs(co()-C['original']))<1e-7)
 move(world(.775,-.5));ev('MIDDLEMOUSE','PRESS',ctrl=True,shift=True)
@step
def drag():move(world(.775,-.35))
@step
def moved():
 data=co();changed=np.linalg.norm(data-C['original'],axis=1)>1e-5
 check('loop tweak moves all five border vertices on both sides',np.count_nonzero(changed)==10)
 reflected=data[:25].copy();reflected[:,0]*=-1
 check('mirrored border points follow during the drag',np.max(abs(reflected-data[25:]))<1e-6)
 ev('ESC','PRESS');ev('ESC','RELEASE');ev('MIDDLEMOUSE','RELEASE')
@step
def cancelled():
 check('Escape restores both complete border loops',np.max(abs(co()-C['original']))<1e-7)
 move(world(.775,-.5));ev('MIDDLEMOUSE','PRESS',ctrl=True,shift=True)
@step
def drag_again():move(world(.775,-.35))
@step
def accept():ev('MIDDLEMOUSE','RELEASE',ctrl=True,shift=True)
@step
def accepted():
 check('released border-loop tweak keeps both sides and topology',np.count_nonzero(np.linalg.norm(co()-C['original'],axis=1)>1e-5)==10 and len(bm().faces)==32)
 undo()
@step
def undone():check('one Undo restores both accepted loop tweaks',np.max(abs(co()-C['original']))<1e-7)
run()
