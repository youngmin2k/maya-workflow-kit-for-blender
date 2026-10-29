"""Display audit: irregular quads, close view and persisted native retopology offset."""
import os, sys, math, json
from pathlib import Path
from importlib import import_module
import bpy, bmesh, numpy as np
from mathutils import Vector, Euler, Quaternion
from bpy_extras import view3d_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, setup, load_maya_layout, step, run, view3d, win, check, ev, screenshot
C = {'results': []}
mod = lambda n: import_module(MODULE + '.operators.' + n)

def override():
    a, r = view3d()
    return bpy.context.temp_override(window=win(), area=a, region=r)

def xy(p):
    a, r = view3d()
    return view3d_utils.location_3d_to_region_2d(r, a.spaces.active.region_3d, Vector(p))

def use_offset(value):
    with override():
        q = mod('quad_draw')
        q._restore_overlays()
        a, r = view3d()
        a.spaces.active.overlay.retopology_offset = value
        q._retopology_on(bpy.context)
        a.tag_redraw()

def capture(tag):
    a, r = view3d()
    path = Path(os.environ.get('ALLSET_GUI_SHOTS', bpy.app.tempdir)) / (tag + '.png')
    screenshot(str(path))
    im = bpy.data.images.load(str(path), check_existing=False)
    w, h = im.size
    data = np.empty(w * h * 4, dtype=np.float32)
    im.pixels.foreach_get(data)
    bpy.data.images.remove(im)
    data = data.reshape(h, w, 4)[r.y:r.y + r.height, r.x:r.x + r.width, :3]
    with override():
        ctx = bpy.context
        cache = mod('quad_draw_overlay')
        cache.batches(ctx)
        c = cache._cached[0]
        rates = []
        for ids in c.edges:
            a, b = (Vector(c.co[i]) for i in ids)
            pixels = []
            for t in np.linspace(0.12, 0.88, 25):
                x, y = map(round, xy(a.lerp(b, float(t))))
                if 3 <= x < r.width - 3 and 32 <= y < r.height - 24:
                    pixels.append(bool((data[y - 2:y + 3, x - 2:x + 3].max(axis=2) < 0.25).any()))
            if pixels:
                rates.append(sum(pixels) / len(pixels))
        result = {'tag': tag, 'mean': float(np.mean(rates)), 'min': min(rates), 'bad_edges': sum((v < 0.95 for v in rates)), 'edges': len(rates), 'wire_on': mod('poly_draw').settings().qd_wire_overlay, 'native_offset': ctx.space_data.overlay.retopology_offset, 'saved_offset': mod('quad_draw').STATE['overlays'][ctx.space_data.as_pointer()][2]}
        print('DISPLAY_AUDIT', result, flush=True)
        C['results'].append(result)

@step
def prepare():
    setup()
    load_maya_layout()

@step
def fixture():
    with override():
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=2, segments=96, ring_count=48)
        ref = bpy.context.object
        for p in ref.data.polygons:
            p.use_smooth = True
        mod('live').set_objects(bpy.context.scene, [ref])
        co = []
        for radius in (0.6, 1.1):
            for i in range(8):
                t = i * math.tau / 8
                r0 = radius * (1 + 0.08 * math.sin(i * 1.7))
                co.append((r0 * math.cos(t), 0.5 + r0 * math.sin(t)))
        faces = [(i, i + 8, (i + 1) % 8 + 8, (i + 1) % 8) for i in range(8)]
        previous = [12, 13, 14, 15, 8]
        for row in (((-1.1, -0.85), (-0.65, -1.1), (0, -1.25), (0.7, -1.1), (1.15, -0.8)), ((-1.5, -1.15), (-0.85, -1.5), (0, -1.7), (0.85, -1.5), (1.5, -1.15))):
            ids = list(range(len(co), len(co) + len(row)))
            co.extend(row)
            faces.extend(((b, a, n, m) for a, b, n, m in zip(previous, previous[1:], ids, ids[1:])))
            previous = ids
        positions = [(x, y, math.sqrt(4 - x * x - y * y)) for x, y in co]
        me = bpy.data.meshes.new('irregular')
        me.from_pydata(positions, [], faces)
        ob = bpy.data.objects.new('irregular', me)
        bpy.context.scene.collection.objects.link(ob)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        a, r = view3d()
        a.spaces.active.overlay.retopology_offset = 0.6
        bpy.ops.allset.quad_draw_start()
        bm = bmesh.from_edit_mesh(me)
        for el in (*bm.verts, *bm.edges, *bm.faces):
            el.select = False
        bmesh.update_edit_mesh(me)
        mod('preselect').invalidate()
        a, r = view3d()
        rv = a.spaces.active.region_3d
        rv.view_rotation = Quaternion((1, 0, 0, 0))
        rv.view_perspective = 'ORTHO'
        rv.view_location = (0, 0, 1)
        rv.view_distance = 4.5
        C['offset'] = a.spaces.active.overlay.retopology_offset
    a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + 10, y=r.y + 10)

@step
def persisted_offset():
    capture('quad_depth_saved_06')
    check('saved scene offset is retained by the compositor', abs(C['results'][-1]['saved_offset'] - 0.6) < 1e-06)
    check('native cage depth stays unshifted', C['results'][-1]['native_offset'] == 0.0)
    check('irregular quads have continuous wires with a saved offset', C['results'][-1]['min'] >= 0.95)
    use_offset(2.0)

@step
def larger_offset():
    capture('quad_depth_saved_20')
    check('large original offset remains available to the compositor', C['results'][-1]['saved_offset'] == 2.0)
    check('a large saved offset does not clip the wires', C['results'][-1]['min'] >= 0.95)
    use_offset(0.6)
    a, r = view3d()
    a.spaces.active.region_3d.view_perspective = 'PERSP'
    a.spaces.active.region_3d.view_rotation = Euler((0.25, 0.1, 0)).to_quaternion()
    a.spaces.active.region_3d.view_distance = 4.0

@step
def perspective():
    capture('quad_depth_perspective')
    check('persisted offset is safe in a close perspective view', C['results'][-1]['min'] >= 0.95)
    with override():
        bm = bmesh.from_edit_mesh(bpy.context.edit_object.data)
        check('display correction leaves topology untouched', (len(bm.verts), len(bm.faces)) == (26, 16))
        bpy.ops.allset.quad_draw_exit()

@step
def settle_exit():
    pass

@step
def restored():
    a, r = view3d()
    check('leaving the real tool restores the original native offset', abs(a.spaces.active.overlay.retopology_offset - 0.6) < 1e-06)
    check('tool exit releases display caches', mod('quad_draw_overlay')._cached is None)

@step
def restored_workspace_tool():
    with override():
        q = mod('quad_draw')
        a, r = view3d()
        a.spaces.active.overlay.retopology_offset = 2.0
        # Reopening a workspace can restore its active tool without invoking Start.
        bpy.ops.wm.tool_set_by_id(name=q.TOOL, space_type='VIEW_3D')

@step
def resumed_display():
    capture('quad_depth_resumed_workspace')
    check('a restored workspace captures its original offset', C['results'][-1]['saved_offset'] == 2.0)
    check('a restored workspace also has continuous wires', C['results'][-1]['min'] >= .95)
    check('a restored workspace arms normal exit cleanup', bpy.app.timers.is_registered(mod('quad_draw')._watch))
    with override():
        bpy.ops.allset.quad_draw_exit()

@step
def settle_resumed_exit():
    pass

@step
def resumed_restoration():
    a, r = view3d()
    check('exiting a restored tool returns its original offset', a.spaces.active.overlay.retopology_offset == 2.0)
    check('exiting a restored tool releases its display cache', mod('quad_draw_overlay')._cached is None)

@step
def centimetre_scene():
    with override():
        q = mod('quad_draw')
        target = bpy.context.edit_object
        factor = .005
        bm = bmesh.from_edit_mesh(target.data)
        for v in bm.verts:
            v.co *= factor
        bmesh.update_edit_mesh(target.data)
        for ob in q.reference_objects(bpy.context):
            for v in ob.data.vertices:
                v.co *= factor
            ob.data.update()
        mod('preselect').invalidate()
        mod('live')._trees.clear()
        a, r = view3d()
        a.spaces.active.clip_start = .001
        a.spaces.active.clip_end = 100
        rv = a.spaces.active.region_3d
        rv.view_location *= factor
        rv.view_distance *= factor
        a.spaces.active.overlay.retopology_offset = .01
        bpy.ops.wm.tool_set_by_id(name=q.TOOL, space_type='VIEW_3D')
        q.reset_preview()

@step
def centimetre_wires():
    capture('quad_depth_centimetre')
    check('centimetre-scale mesh keeps continuous perspective wires', C['results'][-1]['min'] >= .95)
    check('centimetre scene retains its saved display offset', abs(C['results'][-1]['saved_offset']-.01) < 1e-6)
    a, r = view3d()
    a.spaces.active.region_3d.view_perspective = 'ORTHO'

@step
def centimetre_ortho():
    capture('quad_depth_centimetre_ortho')
    check('centimetre-scale mesh also has continuous orthographic wires', C['results'][-1]['min'] >= .95)
    with override():
        bpy.ops.allset.quad_draw_exit()

@step
def settle_centimetre_exit():
    pass

@step
def centimetre_restored():
    a, r = view3d()
    check('small-scene exit restores its original native offset', abs(a.spaces.active.overlay.retopology_offset-.01) < 1e-6)

run()
