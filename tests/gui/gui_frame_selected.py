"""F must reach Frame Selection ahead of another addon's Object/Mesh menu, then restore that menu on exit."""
import os,sys,bpy,bmesh
from importlib import import_module
from mathutils import Vector,Quaternion,Matrix
from bpy_extras.view3d_utils import location_3d_to_region_2d
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE,setup,step,run,view3d,win,ev,tap,check
view=import_module(MODULE+'.operators.view')
keymap=import_module(MODULE+'.keymap')
C={'menus':0}

class FRAME_MT_foreign(bpy.types.Menu):
 bl_label='Foreign F menu'
 def draw(self,context):C['menus']+=1;self.layout.label(text='Another addon owns F outside Maya mode')

def override():
 a,r=view3d();return bpy.context.temp_override(window=win(),area=a,region=r)
def hover():
 a,r=view3d();ev('MOUSEMOVE','NOTHING',x=r.x+r.width//2,y=r.y+r.height//2)
def far_view():
 a,r=view3d();r.data.view_location=(2,-3,4);r.data.view_distance=5
 C['before']=r.data.view_distance;C['rotation']=r.data.view_rotation.copy();C['menu_before']=C['menus'];hover()
def framed(points,label,point=False):
 a,r=view3d();rv=r.data;rect=view.visible_bounds(a,r)
 xy=[location_3d_to_region_2d(r,rv,p) for p in points]
 check(label+': F reaches Frame Selection rather than the foreign menu',C['menus']==C['menu_before'] and abs(rv.view_distance-C['before'])>1e-4)
 check(label+': selection is inside the usable viewport',all(p is not None and rect[0]-2<=p.x<=rect[2]+2 and rect[1]-2<=p.y<=rect[3]+2 for p in xy))
 if all(p is not None for p in xy):
  x=(min(p.x for p in xy)+max(p.x for p in xy))*.5;y=(min(p.y for p in xy)+max(p.y for p in xy))*.5
  check(label+': selection is centered',abs(x-(rect[0]+rect[2])*.5)<2 and abs(y-(rect[1]+rect[3])*.5)<2)
 check(label+': view orientation is preserved',abs(rv.view_rotation.dot(C['rotation']))>1-1e-6)
 tap('ESC')

@step
def prepare():
 setup();bpy.utils.register_class(FRAME_MT_foreign)
 kc=bpy.context.window_manager.keyconfigs.addon;C['foreign']=[]
 for name in ('Object Mode','Mesh'):
  km=kc.keymaps.new(name,space_type='EMPTY',region_type='WINDOW');k=km.keymap_items.new('wm.call_menu','F','PRESS');k.properties.name='FRAME_MT_foreign';C['foreign'].append((km,k))
 with override():
  bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
  bpy.ops.mesh.primitive_cube_add(size=.06,location=(.2,-.12,.08));ob=bpy.context.object;C['ob']=ob.name
  # A far-away object origin must not become the framed center.
  for v in ob.data.vertices:v.co+=Vector((.1,.03,.02))
  ob.scale=(1.3,.8,1.1);ob.data.update()
  bpy.context.scene.unit_settings.scale_length=.01
  a,r=view3d();a.spaces.active.lens=70;r.data.view_rotation=Quaternion((1,0,0,0));r.data.view_perspective='PERSP';a.spaces.active.show_region_ui=True
  bpy.ops.wm.tool_set_by_id(name='builtin.scale')
 far_view()
@step
def wait_watch():pass
@step
def wait_again():pass
@step
def object_press():tap('F')
@step
def object_result():
 ob=bpy.data.objects[C['ob']];framed([ob.matrix_world@Vector(p) for p in ob.bound_box],'Object')
 check('Object F preserves the active selection',ob.select_get() and bpy.context.view_layer.objects.active is ob)
 with override():
  bpy.ops.object.mode_set(mode='EDIT');bm=bmesh.from_edit_mesh(ob.data);bm.verts.ensure_lookup_table()
  for f in bm.faces:f.select_set(False)
  for e in bm.edges:e.select_set(False)
  for v in bm.verts:v.select_set(False)
  bpy.context.scene.tool_settings.mesh_select_mode=(True,False,False);bm.verts[0].select_set(True);bm.select_flush_mode()
  C['points']=[ob.matrix_world@bm.verts[0].co];C['counts']=(len(bm.verts),len(bm.edges),len(bm.faces));bmesh.update_edit_mesh(ob.data)
 far_view()
@step
def vertex_press():tap('F')
@step
def vertex_result():
 framed(C['points'],'Vertex',True)
 with override():
  ob=bpy.context.edit_object;bm=bmesh.from_edit_mesh(ob.data);bm.edges.ensure_lookup_table()
  for v in bm.verts:v.select_set(False)
  bpy.context.scene.tool_settings.mesh_select_mode=(False,True,False);edge=bm.edges[0];edge.select_set(True);bm.select_flush_mode()
  C['points']=[ob.matrix_world@v.co for v in edge.verts];bmesh.update_edit_mesh(ob.data)
 far_view()
@step
def edge_press():tap('F')
@step
def edge_result():
 framed(C['points'],'Edge')
 with override():
  ob=bpy.context.edit_object;bm=bmesh.from_edit_mesh(ob.data);bm.faces.ensure_lookup_table()
  for e in bm.edges:e.select_set(False)
  for v in bm.verts:v.select_set(False)
  bpy.context.scene.tool_settings.mesh_select_mode=(False,False,True)
  face=max(bm.faces,key=lambda f:f.calc_center_median().z);face.select_set(True);bm.select_flush_mode()
  C['points']=[ob.matrix_world@v.co for v in face.verts];bmesh.update_edit_mesh(ob.data)
 far_view()
@step
def face_press():tap('F')
@step
def face_result():
 framed(C['points'],'Face');bm=bmesh.from_edit_mesh(bpy.context.edit_object.data)
 check('component F never creates/deletes mesh geometry',(len(bm.verts),len(bm.edges),len(bm.faces))==C['counts'])
 with override():bpy.ops.object.mode_set(mode='OBJECT')
 C['ortho_points']=[bpy.context.object.matrix_world@Vector(p) for p in bpy.context.object.bound_box]
 a,r=view3d();r.data.view_perspective='ORTHO';far_view()
@step
def ortho_press():tap('F')
@step
def ortho_result():
 framed(C['ortho_points'],'Orthographic')
 with override():bpy.ops.view3d.localview(frame_selected=False)
 far_view()
@step
def local_press():tap('F')
@step
def local_result():
 framed(C['ortho_points'],'Local View')
 with override():
  bpy.ops.view3d.localview(frame_selected=False)
  import_module(MODULE+'.switch').set_mode(False,layout=False)
 C['off_before']=C['menus'];hover()
@step
def off_press():tap('F')
@step
def off_result():
 check('Maya mode off restores the other addon F menu',C['menus']>C['off_before'])
 tap('ESC')
@step
def reenable():
 with override():import_module(MODULE+'.switch').set_mode(True,layout=False)
 far_view()
@step
def reenabled_press():tap('F')
@step
def reenabled_result():
 framed(C['ortho_points'],'Maya mode reenabled')
 for km,k in C['foreign']:km.keymap_items.remove(k)
 bpy.utils.unregister_class(FRAME_MT_foreign)
run()
