"""Pixel regression: component shading survives Quad Draw save/reload and legacy viewport repair."""
import os,sys,json
from pathlib import Path
from importlib import import_module
import bpy,bmesh,numpy as np
from mathutils import Vector
from bpy_extras import view3d_utils
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sim import MODULE,setup,load_maya_layout,step,run,view3d,win,ev,check,screenshot
mod=lambda n:import_module(MODULE+'.'+n)
OUT=Path(os.environ.get('ALLSET_GUI_SHOTS',bpy.app.tempdir));OUT.mkdir(parents=True,exist_ok=True)
C={};POINTS=((.45,-1,.2),(1,.2,.3),(.2,.25,1))


def override():
    a,r=view3d();return bpy.context.temp_override(window=win(),area=a,region=r)


def shade(tag,expected=True):
    a,r=view3d();s=a.spaces.active
    path=OUT/(tag+'.png');screenshot(str(path))
    im=bpy.data.images.load(str(path),check_existing=False);w,h=im.size
    data=np.empty(w*h*4,np.float32);im.pixels.foreach_get(data);bpy.data.images.remove(im);data=data.reshape(h,w,4)
    bg=np.median(data[r.y+75:r.y+82,r.x+65:r.x+72,:3].reshape(-1,3),axis=0)
    colors=[]
    for point in POINTS:
        xy=view3d_utils.location_3d_to_region_2d(r,s.region_3d,Vector(point));x,y=round(r.x+xy.x),round(r.y+xy.y)
        colors.append(np.median(data[y-3:y+4,x-3:x+4,:3].reshape(-1,3),axis=0))
    colors=np.asarray(colors);visible=bool(np.all(np.max(abs(colors-bg),axis=1)>.035) and np.ptp(colors.mean(axis=1))>.05)
    check(tag+(' has distinct shaded faces separate from the background' if expected else ' reproduces the legacy invisible-face fixture'),visible if expected else bool(np.max(abs(colors-bg))<.015))
    print('SHADE_PIXELS',tag,'background',bg.tolist(),'faces',colors.tolist(),flush=True)
    return colors


def park():
    a,r=view3d();ev('MOUSEMOVE','NOTHING',x=r.x+25,y=r.y+80)


def menu_steps(kind,key):
    @step
    def press():
        a,r=view3d();C['press']=(r.x+r.width//2,r.y+r.height//2);ev('RIGHTMOUSE','PRESS',x=C['press'][0],y=C['press'][1])
    @step
    def move():
        session=mod('marking.draw').ACTIVE['session'];box=session.layout.radial[key].rect
        x=C['press'][0]+int(session.center[0]-session.press[0]+(box[0]+box[2])/2)
        y=C['press'][1]+int(session.center[1]-session.press[1]+(box[1]+box[3])/2)
        C['release']=(x,y);ev('MOUSEMOVE','NOTHING',x=x,y=y)
    @step
    def release():ev('RIGHTMOUSE','RELEASE',x=C['release'][0],y=C['release'][1]);park()
    @step
    def result():
        expected={'EDGE':(False,True,False),'VERT':(True,False,False),'FACE':(False,False,True),'MULTI':(True,True,True)}[kind]
        check('RMB selects '+kind,bpy.context.mode=='EDIT_MESH' and tuple(bpy.context.scene.tool_settings.mesh_select_mode)==expected)
        shade('component_'+kind)


@step
def prepare():setup();load_maya_layout()
@step
def fixture():
    with override():
        for ob in list(bpy.data.objects):bpy.data.objects.remove(ob,do_unlink=True)
        bpy.ops.mesh.primitive_cube_add(size=2);mod('operators.material').give_default(bpy.context.object)
        C['object']=bpy.context.object.name
        bpy.ops.wm.tool_set_by_id(name='builtin.scale',space_type='VIEW_3D')
        a,r=view3d();s=a.spaces.active;s.overlay.show_floor=False;s.shading.background_type='VIEWPORT';s.shading.background_color=(0,0,0)
        rv=s.region_3d;rv.view_rotation=Vector((6,-8,5)).to_track_quat('Z','Y');rv.view_distance=8;rv.view_location=(0,0,0);rv.view_perspective='ORTHO'
    park()
@step
def original():C['shade']=shade('object_black_background')

menu_steps('EDGE','N');menu_steps('VERT','W');menu_steps('FACE','S');menu_steps('MULTI','SE')

@step
def gray_background():
    a,r=view3d();a.spaces.active.shading.background_color=(.10702,)*3;park()
@step
def gray_shade():
    shade('components_gray_background')
    with override():
        bpy.ops.object.mode_set(mode='OBJECT');C['primary']=win().workspace.name;bpy.ops.workspace.duplicate()
@step
def secondary_workspace():
    C['secondary']=win().workspace.name
    check('workspace duplicate has completed its deferred activation',C['secondary']!=C['primary'])
    with override():
        bpy.ops.wm.tool_set_by_id(name='builtin.scale',space_type='VIEW_3D')
        a,r=view3d();a.spaces.active.overlay.retopology_offset=.27
        win().workspace=bpy.data.workspaces[C['primary']]
@step
def start_quad():
    with override():
        a,r=view3d();a.spaces.active.overlay.retopology_offset=.37
        bpy.ops.allset.quad_draw_start();q=mod('operators.quad_draw');C['primary_ptr']=a.spaces.active.as_pointer();C['original']=q.STATE['overlays'][C['primary_ptr']]
        C['toolbox']={s.as_pointer():q._overlay_values(s) for a in win().screen.areas if a.type=='VIEW_3D' for s in [a.spaces.active] if mod('ui.toolbox').is_toolbox(s)}
@step
def saving():
    with override():
        q=mod('operators.quad_draw');C['runtime']=q._overlay_values(bpy.context.space_data);C['saved']=str(OUT/'display_lifecycle_saved.blend')
        bpy.ops.wm.save_as_mainfile(filepath=C['saved']);bpy.ops.wm.save_mainfile()
        check('saving resumes Quad Draw with its native depth override',q._overlay_values(bpy.context.space_data)==C['runtime'] and not q._overlay_saving)
        check('save completion releases its suspended state',not q._overlay_save_runtime)
        check('the tool never owns the Maya Tool Box column',all(ptr not in q.STATE['overlays'] for ptr in C['toolbox']))
@step
def save_failure():
    with override():
        q=mod('operators.quad_draw');bad=OUT/'unwritable_target.blend';bad.mkdir(exist_ok=True);failed=False
        try:answer=bpy.ops.wm.save_as_mainfile(filepath=str(bad));failed=answer!={'FINISHED'}
        except RuntimeError:failed=True
        check('the fixture triggers a real save failure',failed)
        check('failed save restores the live display and releases suspension',q._overlay_values(bpy.context.space_data)==C['runtime'] and not q._overlay_saving and not q._overlay_save_runtime)
@step
def change_workspace():win().workspace=bpy.data.workspaces[C['secondary']]
@step
def settle_workspace1():pass
@step
def settle_workspace2():pass
@step
def workspace_restored():
    q=mod('operators.quad_draw');primary=bpy.data.workspaces[C['primary']]
    main=q._overlay_space(C['primary_ptr'])
    check('switching workspace restores the now-inactive primary viewport',not main.overlay.show_retopology and abs(main.overlay.retopology_offset-.37)<1e-6)
    a,r=view3d();check('another workspace retains its own custom offset',abs(a.spaces.active.overlay.retopology_offset-.27)<1e-6)
    win().workspace=primary
@step
def return_settle():pass
@step
def return_quad():
    with override():bpy.ops.allset.quad_draw_start()
@step
def object_mode():
    with override():bpy.ops.object.mode_set(mode='OBJECT')
@step
def settle_object1():pass
@step
def settle_object2():pass
@step
def object_restored():
    shade('object_after_quad');a,r=view3d();check('object mode restores the native overlay',not a.spaces.active.overlay.show_retopology)
    bpy.ops.wm.open_mainfile(filepath=C['saved'],load_ui=True,use_scripts=False)
@step
def load_settle1():pass
@step
def load_settle2():pass
@step
def reopened():
    q=mod('operators.quad_draw');a,r=view3d();saved=q.STATE['overlays'].get(a.spaces.active.as_pointer())
    check('reopened Quad Draw captures the saved native settings rather than old overrides',saved is not None and not saved[0] and abs(saved[2]-.37)<1e-6)
    with override():
        bpy.ops.allset.quad_draw_exit()
        check('explicit exit restores native shading before its cleanup timer',not bpy.context.space_data.overlay.show_retopology)
        bpy.ops.wm.tool_set_by_id(name='builtin.scale',space_type='VIEW_3D')
@step
def exit_settle1():pass
@step
def exit_settle2():pass
@step
def ordinary_modeling():
    shade('modeling_after_reload');q=mod('operators.quad_draw');a,r=view3d()
    check('exiting the reopened tool releases ownership and GPU data',not q.STATE['overlays'] and mod('operators.quad_draw_overlay')._cached is None)
    with override():
        bpy.ops.mesh.select_all(action='SELECT');bpy.ops.ed.undo_push(message='Display regression base');bpy.ops.transform.translate(value=(.05,0,0));bpy.ops.ed.undo()
@step
def undone():
    shade('modeling_after_undo')
    with override():bpy.ops.ed.redo()
@step
def redone():
    shade('modeling_after_redo')
    with override():bpy.ops.ed.undo()
@step
def legacy_fixture():
    with override():
        q=mod('operators.quad_draw');q._restore_overlays();s=bpy.context.space_data;s.overlay.show_retopology=True;s.overlay.retopology_offset=0
@step
def legacy_repair():
    shade('legacy_invisible_mesh',expected=False)
    with override():
        ob=bpy.context.edit_object;C['geometry']=[tuple(v.co) for v in bmesh.from_edit_mesh(ob.data).verts];C['materials']=[m.name if m else None for m in ob.data.materials]
        bpy.ops.allset.panel_run(op='allset.restore_modeling_display')
@step
def repaired():
    shade('legacy_repaired_modeling');a,r=view3d();q=mod('operators.quad_draw')
    check('Shading menu exposes legacy display repair',any(row[0]=='run' and row[2]=='allset.restore_modeling_display' for row in mod('ui.panel_menu_data').SHADING))
    with override():
        ob=bpy.context.edit_object
        check('repair preserves mesh coordinates and materials',C['geometry']==[tuple(v.co) for v in bmesh.from_edit_mesh(ob.data).verts] and C['materials']==[m.name if m else None for m in ob.data.materials])
    check('repair leaves ordinary component shading enabled',not a.spaces.active.overlay.show_retopology)
run()
