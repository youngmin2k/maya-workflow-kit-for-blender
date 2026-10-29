"""Overlay ownership is per window/view; a different scene's object mode must not end Quad Draw."""
import sys,bpy
from pathlib import Path
from importlib import import_module
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sim import MODULE,setup,load_maya_layout,step,run,view3d,win,check
mod=lambda n:import_module(MODULE+'.'+n)
C={}
def primary():return mod('live_refs').window(C['primary'])
def child():return mod('live_refs').window(C['child'])
def parts(window):
 a=max((a for a in window.screen.areas if a.type=='VIEW_3D'),key=lambda a:a.width*a.height)
 return a,next(r for r in a.regions if r.type=='WINDOW')
def override(window):
 a,r=parts(window);return bpy.context.temp_override(window=window,area=a,region=r)
@step
def prepare():setup();load_maya_layout()
@step
def fixture():
 C['primary']=win().as_pointer()
 with override(primary()):
  bpy.ops.mesh.primitive_cube_add();C['object']=bpy.context.object.name;bpy.ops.wm.window_new_main()
@step
def child_scene():
 other=next(w for w in bpy.context.window_manager.windows if w.as_pointer()!=C['primary']);C['child']=other.as_pointer()
 scene=bpy.data.scenes.new('Display ownership other scene');ob=bpy.data.objects[C['object']].copy();ob.data=ob.data.copy();scene.collection.objects.link(ob)
 other.scene=scene;scene.view_layers[0].objects.active=ob;ob.select_set(True,view_layer=scene.view_layers[0])
 with override(other):
  bpy.ops.wm.tool_set_by_id(name='builtin.select_box',space_type='VIEW_3D');s=bpy.context.space_data;s.overlay.show_retopology=True;s.overlay.retopology_offset=.81
 C['child_space']=parts(other)[0].spaces.active.as_pointer()
@step
def primary_quad():
 with override(primary()):
  s=bpy.context.space_data;s.overlay.show_retopology=False;s.overlay.retopology_offset=.43;bpy.ops.allset.quad_draw_start();C['primary_space']=s.as_pointer()
@step
def independent_modes():
 q=mod('operators.quad_draw')
 with override(child()):
  check('the secondary window has its own object mode',bpy.context.mode=='OBJECT')
  check('a watcher in that window retains the primary edit-mode tool',q._watch()==.5)
 check('primary overlay ownership survives a different window context',C['primary_space'] in q.STATE['overlays'])
 s=parts(child())[0].spaces.active
 check('ordinary secondary view keeps its manually enabled native overlay',s.overlay.show_retopology and abs(s.overlay.retopology_offset-.81)<1e-6 and C['child_space'] not in q.STATE['overlays'])
 with override(child()):bpy.ops.allset.quad_draw_start()
@step
def both_owned():
 q=mod('operators.quad_draw');check('each actual Quad Draw window has a distinct snapshot',C['primary_space'] in q.STATE['overlays'] and C['child_space'] in q.STATE['overlays'])
 with bpy.context.temp_override(window=child()):bpy.ops.wm.window_close()
@step
def close_settle1():pass
@step
def close_settle2():pass
@step
def closed():
 q=mod('operators.quad_draw');check('closed-window ownership is pruned while the other window remains active',C['child_space'] not in q.STATE['overlays'] and C['primary_space'] in q.STATE['overlays'])
 with override(primary()):bpy.ops.wm.tool_set_by_id(name='builtin.select_box',space_type='VIEW_3D')
@step
def exit_settle1():pass
@step
def exit_settle2():pass
@step
def finished():
 q=mod('operators.quad_draw');s=parts(primary())[0].spaces.active
 check('last tool exit restores the primary custom settings and releases ownership',not s.overlay.show_retopology and abs(s.overlay.retopology_offset-.43)<1e-6 and not q.STATE['overlays'])
run()
