"""Issue #280: the Move tool's Transform Constraint with the Move handles (W, then LMB-drag an arrow) in mesh edit
mode. Edge: the selected cube corner slides along one of its edges. Surface: a sphere vertex moves and stays on
the sphere's surface. Off: the arrow moves the vertex along X only."""
import os
import sys
from importlib import import_module

import bmesh
import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_location_3d
from mathutils import Quaternion, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, setup, step, view3d, win, MODULE, scale  # noqa: E402

C = {}


def mod(name):
    return import_module(MODULE + '.' + name)


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def bm():
    return bmesh.from_edit_mesh(bpy.context.edit_object.data)


def vert():
    return bm().verts[C['index']].co.copy()


def on_an_edge(co):
    return sum(abs(abs(c) - 1.0) < 1e-4 for c in co) >= 2


def slide_running():
    return [op.bl_idname for op in win().modal_operators]


def reset():
    with override():
        b = bm()
        b.verts.ensure_lookup_table()
        b.verts[C['index']].co = C['start_co']
        for i, co in C.get('others', {}).items():
            b.verts[i].co = co
        bmesh.update_edit_mesh(bpy.context.edit_object.data)


def screen(world):
    _area, region = view3d()
    p = location_3d_to_region_2d(region, region.data, world)
    return Vector((region.x + p.x, region.y + p.y))


def x_tip(center):
    """Window point 0.8 along the Move X arrow."""
    _area, region = view3d()
    p = location_3d_to_region_2d(region, region.data, center)
    w = region_2d_to_location_3d(region, region.data, p + Vector((1, 0)), center)
    px_world = (w - center).length
    n = mod("ui.manipulator").ARROW_PX * bpy.context.preferences.view.gizmo_size / 75.0 * scale()
    return screen(center + Vector((1, 0, 0)) * n * 0.8 * px_world)


def pick(ob_name, key, ring=False):
    with override():
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        ob = bpy.data.objects[ob_name]
        bpy.ops.object.select_all(action='DESELECT')
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='VERT')
        bpy.ops.mesh.select_all(action='DESELECT')
        b = bm()
        b.verts.ensure_lookup_table()
        v = max(b.verts, key=key)
        v.select_set(True)
        C['others'] = {}
        if ring:      # the vertex and its neighbours: every one of them must stay on the surface
            for e in v.link_edges:
                o = e.other_vert(v)
                o.select_set(True)
                C['others'][o.index] = o.co.copy()
        b.select_flush_mode()
        C['index'], C['start_co'] = v.index, v.co.copy()
        C['center'] = ob.matrix_world @ v.co
        bmesh.update_edit_mesh(ob.data)
        bpy.ops.wm.tool_set_by_id(name='builtin.move')


def arrow_drag(prefix, dx=60, dy=0):
    def hover():
        C['p'] = x_tip(C['center'])
        ev('MOUSEMOVE', 'NOTHING', x=int(C['p'].x), y=int(C['p'].y))

    def press():
        ev('LEFTMOUSE', 'PRESS', x=int(C['p'].x), y=int(C['p'].y))

    def move1():
        ev('MOUSEMOVE', 'NOTHING', x=int(C['p'].x) + dx // 2, y=int(C['p'].y) + dy // 2)

    def move2():
        C[prefix + '_ops'] = slide_running()
        ev('MOUSEMOVE', 'NOTHING', x=int(C['p'].x) + dx, y=int(C['p'].y) + dy)

    def release():
        ev('LEFTMOUSE', 'RELEASE', x=int(C['p'].x) + dx, y=int(C['p'].y) + dy)

    for f in (hover, press, move1, move2, release):
        f.__name__ = f"s_{prefix}_{f.__name__}"
        step(f)


@step
def s_setup():
    C['mouse'] = setup()
    with override():
        bpy.context.tool_settings.use_snap = False
        before = set(bpy.data.objects)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(4, 0, 0), segments=32, ring_count=16)
        (set(bpy.data.objects) - before).pop().name = "Ball"
        bpy.ops.object.mode_set(mode='OBJECT')
        region = view3d()[1]
        region.data.view_rotation = Quaternion((0.82, 0.42, 0.17, 0.34))
        region.data.view_location = (2, 0, 0)
        region.data.view_distance = 14
    pick('Cube', lambda v: (v.co.x, v.co.y, v.co.z))
    mod('preferences').get(bpy.context).transform_constraint = 'EDGE'


arrow_drag('edge', dx=-60)  # toward the cube: a corner can't slide outward


@step
def s_edge_result():
    co = vert()
    ops = C.get('edge_ops', [])
    check(f'Edge: the arrow drag runs a slide ({ops})',
          any(o in ('TRANSFORM_OT_vert_slide', 'TRANSFORM_OT_edge_slide') for o in ops))
    check(f'Edge: the corner moved and stays on a cube edge ({tuple(round(c, 3) for c in co)})',
          (co - C['start_co']).length > 1e-3 and on_an_edge(co))
    reset()
    mod('preferences').get(bpy.context).transform_constraint = 'SURFACE'
    # the sphere vertex facing the camera
    toward = view3d()[1].data.view_rotation @ Vector((0, 0, 1))
    pick('Ball', lambda v: v.co.normalized().dot(toward))


arrow_drag('surface', dx=40)


@step
def s_surface_result():
    co = vert()
    d = co - C['start_co']
    r = co.length
    check(f'Surface: the vertex moved ({d.length:.3f})', d.length > 0.05)
    # the faces of a 32 x 16 UV sphere sit at least cos(pi/16) ~ 0.98 from the centre
    check(f'Surface: the vertex stays on the sphere ({r:.4f})', 0.97 < r <= 1.0001)
    # along X as far as the surface allows: the move follows X laid onto the surface's tangent plane
    n = C['start_co'].normalized()
    tx = (Vector((1, 0, 0)) - n * n.x).normalized()
    along = d.normalized().dot(tx)
    check(f'Surface: the X arrow keeps the move to X on the surface ({tuple(round(c, 3) for c in d)}, {along:.3f})',
          along > 0.95)
    reset()
    toward = view3d()[1].data.view_rotation @ Vector((0, 0, 1))
    pick('Ball', lambda v: v.co.normalized().dot(toward), ring=True)


arrow_drag('ring', dx=40)


@step
def s_ring_result():
    b = bm()
    b.verts.ensure_lookup_table()
    radii = [b.verts[i].co.length for i in [C['index'], *C['others']]]
    moved = (b.verts[C['index']].co - C['start_co']).length
    check(f'Surface: several vertices move ({moved:.3f}) and all stay on the sphere '
          f'({min(radii):.4f} .. {max(radii):.4f})', moved > 0.05 and all(0.97 < r <= 1.0001 for r in radii))
    reset()
    mod('preferences').get(bpy.context).transform_constraint = 'NONE'
    pick('Cube', lambda v: (v.co.x, v.co.y, v.co.z))


arrow_drag('off')


@step
def s_off_result():
    d = vert() - C['start_co']
    check(f'Off: the arrow moves the vertex along X only ({tuple(round(c, 3) for c in d)})',
          d.x > 1e-3 and abs(d.y) < 1e-4 and abs(d.z) < 1e-4)


run()
