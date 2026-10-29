"""Surface Offset on a Maya-sized sphere: visible dots, fill, stable projection and drag."""
import os, sys
from pathlib import Path
from importlib import import_module
from types import SimpleNamespace
import bpy, bmesh
from mathutils import Vector, Euler
from bpy_extras import view3d_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, setup, load_maya_layout, step, run, view3d, win, check, ev, screenshot
C = {}
mod = lambda n: import_module(MODULE + '.operators.' + n)

def override():
    a, r = view3d()
    return bpy.context.temp_override(window=win(), area=a, region=r)

def bm():
    b = bmesh.from_edit_mesh(bpy.context.edit_object.data)
    b.verts.ensure_lookup_table()
    return b

def xy(p):
    a, r = view3d()
    return view3d_utils.location_3d_to_region_2d(r, a.spaces.active.region_3d, Vector(p))

def mouse(p, **kw):
    a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + round(p[0]), y=r.y + round(p[1]), **kw)

@step
def prepare():
    setup()
    load_maya_layout()

@step
def scene():
    with override():
        ctx = bpy.context
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        us = ctx.scene.unit_settings
        us.system = 'METRIC'
        us.length_unit = 'CENTIMETERS'
        us.scale_length = 1
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.01, segments=20, ring_count=20)
        mod('live').set_objects(ctx.scene, [ctx.object])
        bpy.ops.allset.quad_draw_start()
        s = mod('poly_draw').settings(ctx)
        s.qd_offset_on = True
        s.qd_surface_offset = 0.1
        a, r = view3d()
        space = a.spaces.active
        space.clip_start = 0.001
        space.clip_end = 100
        rv = space.region_3d
        rv.view_rotation = Euler((0.3, 0.2, 0)).to_quaternion()
        rv.view_perspective = 'PERSP'
        rv.view_location = (0, 0, 0)
        rv.view_distance = 0.03

@step
def offsets():
    center = xy((0, 0, 0))
    C['mouse'] = [center + Vector(p) for p in ((-65, -55), (65, -55), (65, 55), (-65, 55))]
    check('0.10 in a centimetre scene equals 0.001 Blender units', abs(mod('quad_draw').surface_offset(bpy.context) - 0.001) < 1e-08)
    with override():
        a, r = view3d()
        q = mod('quad_draw')
        check('offset tolerance does not expose points behind the live surface', not q._reference_visible(bpy.context, r, a.spaces.active.region_3d, Vector((0, 0, -0.01)), q.reference_objects(bpy.context)))
for i in range(4):

    @step
    def press(i=i):
        mouse(C['mouse'][i])
        ev('LEFTMOUSE', 'PRESS')

    @step
    def release(i=i):
        ev('LEFTMOUSE', 'RELEASE')

@step
def dots():
    with override():
        ctx = bpy.context
        q = mod('quad_draw')
        points = [ctx.edit_object.matrix_world @ v.co for v in bm().verts]
        check('four real clicks produce four offset dots', len(q.dots(bm())) == 4)
        check('offset dots remain in front of the camera', all((xy(p) is not None for p in points)))
        distances = [(mod('live').nearest(ctx, p, q.reference_objects(ctx))[0] - p).length for p in points]
        check('each dot is 0.10 cm from the live surface', all((abs(d - 0.001) < 1e-07 for d in distances)))
        a, r = view3d()
        rv = a.spaces.active.region_3d
        projected = q.project_point(ctx, points[0], q.reference_objects(ctx), r, rv)
        check('projecting an offset point again does not move it', xy(projected) is not None and (xy(projected) - xy(points[0])).length < 0.5)
    mouse(sum(C['mouse'], Vector((0, 0))) / 4, shift=True)
    ev('LEFTMOUSE', 'PRESS', shift=True)

@step
def fill_release():
    ev('LEFTMOUSE', 'RELEASE', shift=True)

@step
def fill():
    check('Shift fill creates a quad from offset dots', len(bm().faces) == 1 and len(bm().verts) == 4)
    with override():
        ctx = bpy.context
        q = mod('quad_draw')
        p = ctx.edit_object.matrix_world @ bm().verts[0].co
        screen = xy(p)
        C['start'] = p
        C['screen'] = screen
        C['drag'] = SimpleNamespace(_ob=ctx.edit_object.name, _refs=q.reference_objects(ctx), _press=screen, _grab=('MESH', [0], [p], p), _depth=p, _new_dot=False, _snap=None)
        q.ALLSET_OT_quad_draw._drag_to(C['drag'], ctx, screen)
        actual = xy(ctx.edit_object.matrix_world @ bm().verts[0].co)
        check('zero-distance grab does not make an offset vertex jump', (actual - screen).length < 0.5)

@step
def moving():
    with override():
        ctx = bpy.context
        q = mod('quad_draw')
        q.ALLSET_OT_quad_draw._drag_to(C['drag'], ctx, C['screen'] + Vector((15, 8)))
        p = ctx.edit_object.matrix_world @ bm().verts[0].co
        check('dragging preserves the requested physical offset', abs((mod('live').nearest(ctx, p, q.reference_objects(ctx))[0] - p).length - 0.001) < 1e-07)
        check('dragging moves the vertex in the requested direction', (xy(p) - C['screen']).dot(Vector((15, 8))) > 0)
        q.ALLSET_OT_quad_draw._cancel(C['drag'], ctx)
        check('Escape restores the original offset vertex', (ctx.edit_object.matrix_world @ bm().verts[0].co - C['start']).length < 1e-08)
        check('cancel releases the cached offset anchors', C['drag']._surface_anchors is None)
    screenshot(str(Path(os.environ.get('ALLSET_GUI_SHOTS', bpy.app.tempdir)) / 'quad_offset_centimetre.png'))
run()
