"""Real Quad Draw delete/move gestures and disconnected-border / reversible-relax regressions."""
import os,sys,bpy,bmesh,numpy as np
from pathlib import Path
from importlib import import_module
from types import SimpleNamespace
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
def point(p):
 a,r=view3d();v=view3d_utils.location_3d_to_region_2d(r,a.spaces.active.region_3d,Vector(p));return r.x+round(v.x),r.y+round(v.y)
def move(p,**kw):
 x,y=point(p);ev('MOUSEMOVE','NOTHING',x=x,y=y,**kw)
def undo():
 with override():bpy.ops.ed.undo()
@step
def prepare():
 setup()
 with override():
  bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
  bpy.ops.mesh.primitive_grid_add(x_subdivisions=4,y_subdivisions=4,size=2)
  bpy.ops.allset.quad_draw_start()
  bpy.context.scene.allset_symmetry.on=False;mod('symmetry').apply(bpy.context.scene.allset_symmetry,[bpy.context.edit_object])
  for seq in (bm().verts,bm().edges,bm().faces):
   for el in seq:el.select=False
  a,r=view3d();rv=a.spaces.active.region_3d;rv.view_rotation=Quaternion((1,0,0,0));rv.view_perspective='ORTHO';rv.view_location=(0,0,0);rv.view_distance=6
  bpy.ops.ed.undo_push(message='Quad Draw gesture audit fixture')
  C['faces']=len(bm().faces)
@step
def internal_hover():move((0,-.25,0),ctrl=True,shift=True)
@step
def internal_preview():
 with override():
  q=mod('quad_draw');a,r=view3d();x,y=point((0,-.25,0));comp=q.component_at(bpy.context,r,a.spaces.active.region_3d,(x-r.x,y-r.y),bpy.context.edit_object)
  check('Ctrl Shift targets an internal edge at its midpoint',comp and comp[0]=='EDGE')
  C['loop']=len(q.edge_loop(bm().edges[comp[1]]));pv=q.STATE['preview']
  print('INTERNAL_HOVER',C['loop'],pv,flush=True)
  check('Ctrl Shift previews every edge that will be removed',pv is not None and len(pv[1])==C['loop']*2)
  path=Path(os.environ.get('ALLSET_GUI_SHOTS',os.path.dirname(sys.argv[-1])))/'delete_loop_preview.png'
  screenshot(str(path));im=bpy.data.images.load(str(path),check_existing=False);w,h=im.size
  values=np.empty(w*h*4,dtype='float32');im.pixels.foreach_get(values);bpy.data.images.remove(im)
  pixels=values.reshape(h,w,4);visible=[]
  for p0,p1 in zip(pv[1][::2],pv[1][1::2]):
   x,y=point((Vector(p0)+Vector(p1))*.5);patch=pixels[y-3:y+4,x-3:x+4,:3]
   visible.append(bool(((patch[:,:,0]>.8)&(patch[:,:,1]<.35)&(patch[:,:,2]<.3)).any()))
  check('every target loop segment is visibly red over the base wire',all(visible))
 ev('LEFTMOUSE','PRESS',ctrl=True,shift=True)
@step
def internal_release():ev('LEFTMOUSE','RELEASE',ctrl=True,shift=True)
@step
def internal_result():
 check('Ctrl Shift LMB dissolves an entire interior quad loop',len(bm().faces)==C['faces']-C['loop'])
 print('INTERNAL_DELETE',C['faces'],len(bm().faces),flush=True);undo()
@step
def border_hover():move((-.25,-1,0),ctrl=True,shift=True)
@step
def border_press():
 with override():
  q=mod('quad_draw');a,r=view3d();x,y=point((-.25,-1,0));comp=q.component_at(bpy.context,r,a.spaces.active.region_3d,(x-r.x,y-r.y),bpy.context.edit_object)
  check('Ctrl Shift targets the border edge',comp and comp[0]=='EDGE')
  edge=bm().edges[comp[1]];C['border_faces']=len({f for e in q.border_chain(edge) for f in e.link_faces})
 ev('LEFTMOUSE','PRESS',ctrl=True,shift=True)
@step
def border_release():ev('LEFTMOUSE','RELEASE',ctrl=True,shift=True)
@step
def border_result():
 print('BORDER_DELETE',C['faces'],len(bm().faces),'expected border strip faces',C['border_faces'],flush=True)
 check('Ctrl Shift border loop deletes its corresponding border face strip',len(bm().faces)==C['faces']-C['border_faces']);undo()
@step
def border_move_start():
 C['co']=[v.co.copy() for v in bm().verts];move((-.25,-1,0),ctrl=True,shift=True);ev('MIDDLEMOUSE','PRESS',ctrl=True,shift=True)
@step
def border_move_drag():move((-.1,-1,0),ctrl=True,shift=True)
@step
def border_move_release():ev('MIDDLEMOUSE','RELEASE',ctrl=True,shift=True)
@step
def border_move_result():
 changed=sum((v.co-p).length>1e-5 for v,p in zip(bm().verts,C['co']))
 print('BORDER_MOVE',changed,'of expected 5 vertices',flush=True)
 check('Ctrl Shift MMB moves the complete straight border loop',changed==5);undo()
@step
def select_tool():
 move((0,0,0));ev('Q','PRESS');ev('Q','RELEASE')
@step
def reactivate():ev('Y','PRESS');ev('Y','RELEASE')
@step
def last_tool():
 with override():check('Y reactivates Quad Draw through the shared last-tool command',mod('quad_draw').tool_active(bpy.context))
@step
def relax_islands():
 with override():
  ob=bpy.context.edit_object;b=bm();b.clear()
  for center in (-.1,.1):b.faces.new([b.verts.new((center+x,y,0)) for x,y in ((-.03,-.03),(.03,-.03),(.03,.03),(-.03,.03))])
  b.normal_update();bmesh.update_edit_mesh(ob.data);mod('quad_draw')._geometry_reset(None)
  b.verts.ensure_lookup_table();before=[v.co.copy() for v in b.verts]
  mod('poly_draw').settings().qd_relax='BORDER'
  op=SimpleNamespace(_ob=ob.name,_refs=[],middle=False,_sym=None)
  a,r=view3d();x,y=point((-.1,0,0));mod('quad_draw').ALLSET_OT_quad_draw._relax_at(op,bpy.context,(x-r.x,y-r.y))
  left=sum((b.verts[i].co-before[i]).length>1e-6 for i in range(4));right=sum((b.verts[i].co-before[i]).length>1e-6 for i in range(4,8))
  print('DISCONNECTED_BORDER_RELAX',left,right,flush=True)
  check('Border relax stays within one continuous boundary component',left>0 and right==0)
@step
def relax_direction():
 with override():
  ob=bpy.context.edit_object;b=bm();b.clear()
  b.faces.new([b.verts.new((x,y,0)) for x,y in ((-.3,-.3),(.3,-.3),(.3,.3),(-.3,.3))]);b.normal_update();bmesh.update_edit_mesh(ob.data);mod('quad_draw')._geometry_reset(None)
  b.verts.ensure_lookup_table();before=[v.co.copy() for v in b.verts]
  bpy.context.scene.allset_soft_select=True;mod('poly_draw').settings().qd_relax='ALL'
  a,r=view3d();px,py=point((0,0,0))
  op=SimpleNamespace(_ob=ob.name,_refs=[],middle=True,_sym=None,_press=(px-r.x,py-r.y))
  a,r=view3d()
  x,y=point((.05,0,0));mod('quad_draw').ALLSET_OT_quad_draw._relax_at(op,bpy.context,(x-r.x,y-r.y))
  right=sum((v.co-p).length for v,p in zip(b.verts,before))
  x,y=point((-.05,0,0));mod('quad_draw').ALLSET_OT_quad_draw._relax_at(op,bpy.context,(x-r.x,y-r.y))
  left=sum((v.co-p).length for v,p in zip(b.verts,before))
  print('RELAX_DIRECTION',right,left,flush=True)
  check('Soft-selection Shift MMB left reverses the previous relaxation',left<right)
run()
