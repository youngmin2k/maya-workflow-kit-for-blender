"""Visible Quad Draw tint, automatic Modeling Toolkit and stable projection on live surfaces."""
import os
import sys
from pathlib import Path
from importlib import import_module
from types import SimpleNamespace
import bmesh
import bpy
import numpy as np
from mathutils import Euler, Quaternion, Vector
from bpy_extras import view3d_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, setup, load_maya_layout, step, run, view3d, win, check, screenshot

C = {}
mod = lambda name: import_module(MODULE + '.' + name)


def override():
    a, r = view3d()
    return bpy.context.temp_override(window=win(), area=a, region=r)


def image_crop(name):
    a, r = view3d()
    path = Path(os.environ.get('ALLSET_GUI_SHOTS', bpy.app.tempdir)) / (name + '.png')
    screenshot(str(path))
    img = bpy.data.images.load(str(path), check_existing=False)
    w, h = img.size
    values = np.empty(w*h*4, dtype=np.float32)
    img.pixels.foreach_get(values)
    bpy.data.images.remove(img)
    return values.reshape(h, w, 4)[r.y:r.y+r.height, r.x:r.x+r.width, :3]


@step
def prepare():
    setup()
    load_maya_layout()


@step
def surface():
    with override():
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=2, segments=64, ring_count=32)
        ref = bpy.context.object
        mod('operators.live').set_objects(bpy.context.scene, [ref])
        me = bpy.data.meshes.new('retopo')
        me.from_pydata([(x, y, (4-x*x-y*y)**.5) for x,y in ((-.7,-.7),(.7,-.7),(.7,.7),(-.7,.7))], [], [(0,1,2,3)])
        ob = bpy.data.objects.new('retopo', me)
        bpy.context.scene.collection.objects.link(ob)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.context.view_layer.update()
        a,r=view3d(); space=a.spaces.active
        C['overlays'] = space.overlay.show_retopology, space.overlay.show_faces, space.overlay.retopology_offset
        C['theme'] = tuple(bpy.context.preferences.themes[0].view_3d.face_retopology)
        rv=space.region_3d
        rv.view_rotation=Quaternion((1,0,0,0));rv.view_perspective='ORTHO'
        rv.view_location=(0,0,1);rv.view_distance=6
        bpy.ops.allset.quad_draw_start()
        C['materials'] = list(me.materials)


@step
def options_and_tint():
    check('Quad Draw automatically raises Modeling Toolkit', bpy.context.window_manager.allset_dock == 'MODELING_TOOLKIT')
    data=image_crop('quad_draw_cyan')
    blue=(data[...,0]<.5)&(data[...,1]>.35)&(data[...,2]>data[...,1]*1.15)
    check('retopology faces have the reference blue fill', int(blue.sum())>500)
    ob=bpy.context.edit_object
    check('display tint leaves mesh materials and theme unchanged', list(ob.data.materials)==C['materials'] and tuple(bpy.context.preferences.themes[0].view_3d.face_retopology)==C['theme'])
    s=mod('operators.poly_draw').settings()
    s.qd_mesh_color=(1,0,0); s.qd_mesh_alpha=1
    a,r=view3d()
    a.spaces.active.region_3d.view_perspective='PERSP'
    a.spaces.active.region_3d.view_rotation=Euler((.3,.4,0)).to_quaternion()


@step
def changed_color():
    data=image_crop('quad_draw_red')
    red=(data[...,0]>.8)&(data[...,1]<.15)&(data[...,2]<.15)
    check('Mesh Color and Mesh Alpha update actual faces in perspective',int(red.sum())>500)
    mod('operators.poly_draw').settings().qd_mesh_alpha=0


@step
def alpha_and_drag():
    data=image_crop('quad_draw_alpha_zero')
    red=(data[...,0]>.8)&(data[...,1]<.15)&(data[...,2]<.15)
    check('zero Mesh Alpha removes the fill',int(red.sum())<100)
    with override():
        ctx=bpy.context; a,r=view3d();rv=a.spaces.active.region_3d
        q=mod('operators.quad_draw');ob=ctx.edit_object
        bm=bmesh.from_edit_mesh(ob.data);bm.verts.ensure_lookup_table()
        start=ob.matrix_world@bm.verts[0].co
        xy=view3d_utils.location_3d_to_region_2d(r,rv,start)
        press=xy+Vector((3,2))
        drag=SimpleNamespace(_ob=ob.name,_refs=q.reference_objects(ctx),_press=press,
                             _grab=('MESH',[0],[start],start),_depth=start)
        q.ALLSET_OT_quad_draw._drag_to(drag,ctx,press)
        at=ob.matrix_world@bm.verts[0].co
        check('off-centre component grab keeps its cursor offset', (view3d_utils.location_3d_to_region_2d(r,rv,at)-xy).length<.75)
        q.ALLSET_OT_quad_draw._drag_to(drag,ctx,press+Vector((20,10)))
        at=ob.matrix_world@bm.verts[0].co
        actual=view3d_utils.location_3d_to_region_2d(r,rv,at)
        check('drag tracks a twenty-pixel motion without snapping to cursor', (actual-xy-Vector((20,10))).length<.75)
        q.ALLSET_OT_quad_draw._drag_to(drag,ctx,(r.width*20,r.height*20))
        check('leaving the reference silhouette keeps the last surface point', (ob.matrix_world@bm.verts[0].co-at).length<1e-6)
        # A nearest-only query would choose the lower sheet. Visible projection must choose the upper one.
        bpy.ops.object.mode_set(mode='OBJECT')
        mod('operators.live').set_objects(ctx.scene,[])
        refs=[]
        for z in (0,.02):
            bpy.ops.mesh.primitive_plane_add(size=4, location=(0,0,z))
            refs.append(ctx.object)
        mod('operators.live').set_objects(ctx.scene,refs)
        point=q.project_point(ctx,Vector((0,0,.001)),refs,r,rv)
        check('projection stays on the visible sheet instead of the nearest hidden sheet',abs(point.z-.02)<1e-5)
        q._restore_overlays()
        check('leaving Quad Draw releases its GPU and screen caches', mod('operators.quad_draw_overlay')._cached is None and q._pick_projection is None)
        ov=a.spaces.active.overlay
        check('original viewport overlay settings are restored',(ov.show_retopology,ov.show_faces,ov.retopology_offset)==C['overlays'])


@step
def cache_and_occlusion():
    with override():
        ctx=bpy.context; a,r=view3d()
        rv=a.spaces.active.region_3d
        rv.view_rotation=Quaternion((1,0,0,0));rv.view_perspective='ORTHO'
        mod('operators.live').set_objects(ctx.scene,[])
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob,do_unlink=True)
        bpy.ops.mesh.primitive_plane_add(size=6)
        ref=ctx.object
        # Cover the target silhouette too: equal-size planes leave half of every
        # screen-space wire legitimately outside the foreground surface.
        bpy.ops.mesh.primitive_plane_add(size=2.0,location=(0,0,1.5))
        ctx.object.name='occluder'
        mod('operators.live').set_objects(ctx.scene,[ref])
        bpy.ops.mesh.primitive_plane_add(size=1.4)
        ob=ctx.object
        C['target']=ob.name
        pd=mod('operators.poly_draw')
        pd.reset_settings(pd.settings(),'QUAD_DRAW')
        pd.settings().qd_mesh_color=(1,0,0)
        pd.settings().qd_mesh_alpha=1
        pd.settings().qd_wire_color=(1,0,0)
        # A saved offset must not make the new cage-depth handling paint through
        # an unrelated foreground object.
        a.spaces.active.overlay.retopology_offset=.6
        bpy.ops.allset.quad_draw_start()
        cache=mod('operators.quad_draw_overlay')
        first=cache.batches(ctx)
        second=cache.batches(ctx)
        check('unchanged geometry reuses both GPU batches',first[0] is second[0] and first[1] is second[1])
        q=mod('operators.quad_draw')
        q.component_at(ctx,r,a.spaces.active.region_3d,(r.width/2,r.height/2),ob)
        old=q._pick_projection
        a.spaces.active.region_3d.view_distance=5.5
        q.component_at(ctx,r,a.spaces.active.region_3d,(r.width/2,r.height/2),ob)
        # A view redraw updates perspective_matrix; the next step verifies the key changed.
        C['projection']=old[1]


@step
def settle_new_tool():
    with override():
        bpy.ops.allset.quad_draw_start()
        check('the new occlusion fixture is using Quad Draw',mod('operators.quad_draw').tool_active(bpy.context))


@step
def occluded_faces():
    data=image_crop('quad_draw_occlusion')
    red=(data[...,0]>.8)&(data[...,1]<.15)&(data[...,2]<.15)
    check('retopology tint and front-layer wires stay behind a foreground occluder',int(red.sum())<100)
    with override():
        ctx=bpy.context; a,r=view3d();q=mod('operators.quad_draw')
        q.component_at(ctx,r,a.spaces.active.region_3d,(r.width/2,r.height/2),ctx.edit_object)
        check('view changes invalidate the cached screen projection',q._pick_projection[1]!=C['projection'])
        bpy.ops.allset.quad_draw_exit()


@step
def wait_for_exit():
    pass


@step
def lifecycle():
    cache=mod('operators.quad_draw_overlay')
    check('the real tool-exit watcher releases display caches',cache._cached is None)


@step
def relax_stroke():
    with override():
        ctx=bpy.context; a,r=view3d();q=mod('operators.quad_draw')
        bpy.ops.object.mode_set(mode='OBJECT')
        mod('operators.live').set_objects(ctx.scene,[])
        bpy.ops.mesh.primitive_grid_add(x_subdivisions=4,y_subdivisions=4,size=1.4)
        ob=ctx.object
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.wm.tool_set_by_id(name=q.TOOL,space_type='VIEW_3D')
        brush=SimpleNamespace(_ob=ob.name,_refs=[],middle=False)
        rv=a.spaces.active.region_3d
        bm=bmesh.from_edit_mesh(ob.data)
        border=min(bm.verts,key=lambda v:v.co.x*v.co.x+(v.co.y+.7)**2)
        border_xy=view3d_utils.location_3d_to_region_2d(r,rv,ob.matrix_world@border.co)
        inner=next(v for v in bm.verts if not v.is_boundary)
        inner_xy=view3d_utils.location_3d_to_region_2d(r,rv,ob.matrix_world@inner.co)
        q.ALLSET_OT_quad_draw._relax_at(brush,ctx,(-10000,-10000))
        check('empty space does not choose an Auto-Lock mode',not hasattr(brush,'_relax_lock'))
        q.ALLSET_OT_quad_draw._relax_at(brush,ctx,border_xy)
        check('starting at the border chooses border relaxation',brush._relax_lock=='BORDER')
        q.ALLSET_OT_quad_draw._relax_at(brush,ctx,inner_xy)
        check('Auto-Lock keeps its border choice when the stroke crosses interior vertices',brush._relax_lock=='BORDER')


run()
