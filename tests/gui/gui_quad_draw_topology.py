"""Pick a seam from the Toolkit, show paired components, preserve posed seam, invalidate on seam edits."""
import bpy,bmesh,os,sys
import numpy as np
from importlib import import_module
from mathutils import Vector,Quaternion
from bpy_extras import view3d_utils
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE,setup,step,run,view3d,win,ev,check,dock_area,screenshot
mod=lambda n:import_module(MODULE+'.operators.'+n)
C={}
def override():
 a,r=view3d();return bpy.context.temp_override(window=win(),area=a,region=r)
def bm():
 b=bmesh.from_edit_mesh(bpy.context.edit_object.data);b.verts.ensure_lookup_table();b.edges.ensure_lookup_table();return b
def xy(p):
 a,r=view3d();p=view3d_utils.location_3d_to_region_2d(r,a.spaces.active.region_3d,p)
 return r.x+round(p.x),r.y+round(p.y)
def move(p,**kw):
 x,y=xy(p);ev('MOUSEMOVE','NOTHING',x=x,y=y,**kw)
@step
def prepare():
 setup()
 with override():
  bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
  bpy.ops.mesh.primitive_grid_add(x_subdivisions=4,y_subdivisions=4,size=4)
  ob=bpy.context.object
  # Pose the seam away from every object/world axis; the picked edge must drive mapping.
  for v in ob.data.vertices:
   v.co.x+=.35+.06*v.co.y*v.co.y
   if v.co.x>.6:v.co.z=.15*v.co.x
  bpy.ops.allset.quad_draw_start()
  b=bm()
  for el in (*b.verts,*b.edges,*b.faces):el.select=False
  state=bpy.context.scene.allset_symmetry;state.about='TOPOLOGY';state.on=True
  mod('symmetry').apply(state,[ob])
  a,r=view3d();rv=a.spaces.active.region_3d;rv.view_rotation=Quaternion((1,0,0,0));rv.view_perspective='ORTHO';rv.view_location=(.4,0,0);rv.view_distance=7
  center=sorted(set(round(v.co.y,5) for v in b.verts))
  # Use the first interior vertical edge closest to the curved seam.
  edge=min((e for e in b.edges if len(e.link_faces)==2 and abs(e.verts[0].co.y-e.verts[1].co.y)>.1),key=lambda e:sum(abs(v.co.x-(.35+.06*v.co.y*v.co.y)) for v in e.verts)+abs(sum(v.co.y for v in e.verts))*.01)
  C['mid']=sum((v.co for v in edge.verts),Vector())/2
  bpy.ops.ed.undo_push(message='Posed topology fixture')
 dock_area('MODELING_TOOLKIT')
@step
def pick_from_dock():
 area=dock_area('MODELING_TOOLKIT');region=next(r for r in area.regions if r.type=='WINDOW')
 with bpy.context.temp_override(window=win(),area=area,region=region):bpy.ops.allset.quad_draw_pick_seam('INVOKE_DEFAULT')
 move(C['mid'])
@step
def pick():ev('LEFTMOUSE','PRESS')
@step
def picked():ev('LEFTMOUSE','RELEASE')
@step
def correspondence():
 sy=mod('quad_draw_symmetry');ob=bpy.context.edit_object
 check('Toolkit seam picker stores stable identities on the actual center edge',sy.SEED in ob.data)
 with override():
  info=mod('quad_draw').topology_preview(bpy.context,ob)
  check('picked posed topology has matched components and a visible seam',info is not None and info['paired']>0 and info['unmatched']==0 and bool(info['seam']))
  C['map']=dict(info['pairs'])
  v=next(bm().verts[i] for i,j in info['pairs'].items() if i!=j)
  C['source']=v.index;C['target']=info['pairs'][v.index];C['point']=v.co.copy()
 move(C['point'])
@step
def hover_pair():
 check('hover shows the corresponding component on the posed half',bool(mod('quad_draw').STATE.get('topology_hover')))
 path=os.path.join(os.environ.get('ALLSET_GUI_SHOTS',os.path.dirname(os.path.abspath(sys.argv[-1]))),'topology_seam_pairs.png')
 screenshot(path);im=bpy.data.images.load(path,check_existing=False);w,h=im.size
 values=np.empty(w*h*4,dtype='float32');im.pixels.foreach_get(values);bpy.data.images.remove(im)
 pixels=values.reshape(h,w,4);x,y=xy(C['mid']);patch=pixels[y-4:y+5,x-4:x+5,:3]
 check('yellow seam remains visible over the black retopology wire',int(((patch[:,:,0]>.8)&(patch[:,:,1]>.5)&(patch[:,:,2]<.4)).sum())>5)
 point=bm().verts[C['target']].co;x,y=xy(point);patch=pixels[y-8:y+9,x-8:x+9,:3]
 check('paired vertex has a visible green highlight',int(((patch[:,:,1]>.7)&(patch[:,:,0]<.5)).sum())>5)
 with override():
  # Reopen correspondence from saved IDs after leaving/re-entering the tool.
  ob=bpy.context.edit_object;mod('quad_draw')._drop_dots(ob.name)
  check('leaving Quad Draw preserves a bound seam identity layer',bm().verts.layers.int.get(mod('quad_draw_symmetry').IDENTITY) is not None)
  mod('preselect').invalidate();info=mod('quad_draw').topology_preview(bpy.context,ob)
  check('bound seam reconstructs the same pairing after cleanup',info['pairs']==C['map'])
 move(C['mid'],ctrl=True);ev('LEFT_CTRL','PRESS')
@step
def cut_seam():ev('LEFTMOUSE','PRESS',ctrl=True)
@step
def cut_release():ev('LEFTMOUSE','RELEASE',ctrl=True);ev('LEFT_CTRL','RELEASE')
@step
def invalidated():
 check('editing a seam edge disables topology symmetry as in Maya',not bpy.context.scene.allset_symmetry.on)
 check('editing a seam discards the stale seam binding',mod('quad_draw_symmetry').SEED not in bpy.context.edit_object.data)
 with override():bpy.ops.ed.undo()
@step
def restored():
 check('Undo restores the previous seam binding and symmetry state',bpy.context.scene.allset_symmetry.on and mod('quad_draw_symmetry').SEED in bpy.context.edit_object.data)
 with override():bpy.ops.ed.redo()
@step
def redone():
 check('Redo disables the edited seam again',not bpy.context.scene.allset_symmetry.on and mod('quad_draw_symmetry').SEED not in bpy.context.edit_object.data)
 with override():bpy.ops.ed.undo()
@step
def explicit_off():
 with override():bpy.ops.allset.symmetry(mode='OFF')
@step
def off_after_unrelated_undo():
 with override():
  bpy.ops.ed.undo_push(message='Explicit symmetry off')
  v=bm().verts[C['source']];v.co.y+=.01;bmesh.update_edit_mesh(bpy.context.edit_object.data)
  bpy.ops.ed.undo_push(message='Unrelated coordinate edit');bpy.ops.ed.undo()
@step
def stays_off():
 check('Undo of an unrelated edit preserves explicit symmetry Off',not bpy.context.scene.allset_symmetry.on)
 with override():
  bpy.ops.allset.symmetry(mode='TOPOLOGY')
  C['saved_ids']=tuple(bpy.context.edit_object.data[mod('quad_draw_symmetry').SEED])
  C['save']=os.path.join(os.path.dirname(os.path.abspath(sys.argv[-1])),'topology-binding.blend')
  bpy.ops.wm.save_as_mainfile(filepath=C['save'])
@step
def reopen():bpy.ops.wm.open_mainfile(filepath=C['save'],use_scripts=False)
@step
def reopened_binding():
 with override():
  ob=bpy.context.object
  if ob.mode!='EDIT':bpy.ops.object.mode_set(mode='EDIT')
  b=bm();sy=mod('quad_draw_symmetry')
  check('saved and reopened file retains stable seam binding and pairs',tuple(ob.data[sy.SEED])==C['saved_ids'] and bool(sy.topology_mapping(ob,b,bpy.context.scene.allset_symmetry)))
  bpy.ops.allset.quad_draw_start()
  edge=min((e for e in b.edges if e.is_boundary),key=lambda e:sum(v.co.y for v in e.verts)+abs(sum(v.co.x for v in e.verts))*.01)
  C['border_mid']=sum((v.co for v in edge.verts),Vector())*.5;C['before_border']=len(b.faces)
 move(C['border_mid'],ctrl=True,shift=True)
@step
def loaded_border_settle():move(C['border_mid'],ctrl=True,shift=True)
@step
def delete_bound_border():
 with override():
  a,r=view3d();x,y=xy(C['border_mid']);q=mod('quad_draw')
  comp=q.component_at(bpy.context,r,a.spaces.active.region_3d,(x-r.x,y-r.y),bpy.context.edit_object)
  print('BOUND_BORDER_TARGET',q.tool_active(bpy.context),comp,q.STATE['preview'],flush=True)
 move(C['border_mid'],ctrl=True,shift=True);ev('LEFTMOUSE','PRESS',ctrl=True,shift=True)
@step
def release_bound_border():ev('LEFTMOUSE','RELEASE',ctrl=True,shift=True)
@step
def bound_border_removed():
 print('BOUND_BORDER_RESULT',C['before_border'],len(bm().faces),bpy.context.scene.allset_symmetry.on,flush=True)
 check('deleting a border loop crossing the seam retains its complete strip edit',len(bm().faces)==C['before_border']-4)
 check('a border strip that removes a seam edge disables topology symmetry',not bpy.context.scene.allset_symmetry.on)
 with override():bpy.ops.ed.undo()
@step
def border_undone():
 check('Undo of the border strip restores topology symmetry and the seam',len(bm().faces)==C['before_border'] and bpy.context.scene.allset_symmetry.on and mod('quad_draw_symmetry').SEED in bpy.context.edit_object.data)
run()
