"""Move tool slides: Ctrl+Shift+MMB drag slides a cube vertex along an edge; with Transform Constraint Edge the
plain MMB drag slides too, with Off it moves the vertex freely."""
import os
import sys
from importlib import import_module

import bmesh
import bpy
from mathutils import Quaternion, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, setup, step, view3d, win, MODULE

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
    """A cube vertex slid along one of its edges keeps two of its three coordinates at +-1."""
    return sum(abs(abs(c) - 1.0) < 1e-4 for c in co) >= 2


def slide_running():
    return any(op.bl_idname in ('TRANSFORM_OT_vert_slide', 'TRANSFORM_OT_edge_slide', 'TRANSFORM_OT_shrink_fatten')
               for op in win().modal_operators)


def reset():
    with override():
        b = bm()
        b.verts[C['index']].co = C['start_co']
        bmesh.update_edit_mesh(bpy.context.edit_object.data)


def mmb_drag(prefix, ctrl_shift):
    """Steps: press MMB at the view centre, move right in two ticks, release."""
    def press():
        x, y = C['mouse']
        if ctrl_shift:
            ev('LEFT_CTRL', 'PRESS', ctrl=True)
            ev('LEFT_SHIFT', 'PRESS', ctrl=True, shift=True)
        ev('MIDDLEMOUSE', 'PRESS', x=x, y=y, ctrl=ctrl_shift, shift=ctrl_shift)

    def move1():
        x, y = C['mouse']
        ev('MOUSEMOVE', 'NOTHING', x=x - 15, y=y - 8, ctrl=ctrl_shift, shift=ctrl_shift)

    def move2():
        x, y = C['mouse']
        C[prefix + '_running'] = slide_running()
        ev('MOUSEMOVE', 'NOTHING', x=x - 50, y=y - 30, ctrl=ctrl_shift, shift=ctrl_shift)

    def release():
        x, y = C['mouse']
        ev('MIDDLEMOUSE', 'RELEASE', x=x - 50, y=y - 30, ctrl=ctrl_shift, shift=ctrl_shift)
        if ctrl_shift:
            ev('LEFT_SHIFT', 'RELEASE', ctrl=True)
            ev('LEFT_CTRL', 'RELEASE')
    for f in (press, move1, move2, release):
        f.__name__ = f"s_{prefix}_{f.__name__}"
        step(f)


@step
def s_setup():
    C['mouse'] = setup()
    with override():
        ob = bpy.data.objects['Cube']
        bpy.ops.object.select_all(action='DESELECT')
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.context.tool_settings.use_snap = False
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='VERT')
        bpy.ops.mesh.select_all(action='DESELECT')
        b = bm()
        b.verts.ensure_lookup_table()
        v = max(b.verts, key=lambda v: (v.co.x, v.co.y, v.co.z))
        v.select_set(True)
        C['index'], C['start_co'] = v.index, v.co.copy()
        bmesh.update_edit_mesh(ob.data)
        bpy.ops.wm.tool_set_by_id(name='builtin.move')
        region = view3d()[1]
        region.data.view_rotation = Quaternion((0.82, 0.42, 0.17, 0.34))
        region.data.view_location = (0, 0, 0)
        region.data.view_distance = 9
        mod('preferences').get(bpy.context).transform_constraint = 'NONE'
    ev('MOUSEMOVE', 'NOTHING', x=C['mouse'][0], y=C['mouse'][1])


@step
def s_near_vertex():
    # slides follow the mouse from the vertex: start the drags a little off the selected vertex on screen
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    area, region = view3d()
    ob = bpy.data.objects['Cube']
    xy = location_3d_to_region_2d(region, region.data, ob.matrix_world @ C['start_co'])
    C['mouse'] = (round(region.x + xy.x) - 10, round(region.y + xy.y) - 10)
    ev('MOUSEMOVE', 'NOTHING', x=C['mouse'][0], y=C['mouse'][1])


mmb_drag('cs', True)


@step
def s_cs_result():
    co = vert()
    check('Ctrl+Shift+MMB runs a slide', C.get('cs_running'))
    check(f'the vertex moved and stays on a cube edge ({tuple(round(c, 3) for c in co)})',
          (co - C['start_co']).length > 1e-3 and on_an_edge(co))
    reset()
    with override():
        mod('preferences').get(bpy.context).transform_constraint = 'EDGE'


mmb_drag('edge', False)


@step
def s_edge_result():
    co = vert()
    check('Transform Constraint Edge: plain MMB slides', C.get('edge_running'))
    check('the vertex stays on a cube edge', (co - C['start_co']).length > 1e-3 and on_an_edge(co))
    reset()
    with override():
        mod('preferences').get(bpy.context).transform_constraint = 'NONE'


mmb_drag('off', False)


@step
def s_off_result():
    check('Transform Constraint Off: MMB moves (no slide)', not C.get('off_running'))
    check('the vertex moved', (vert() - C['start_co']).length > 1e-3)
    reset()
    with override():
        mod('preferences').get(bpy.context).transform_constraint = 'NORMAL'


mmb_drag('normal', False)


@step
def s_normal_result():
    d = vert() - C['start_co']
    along = d.normalized().dot(C['start_co'].normalized()) if d.length > 1e-6 else 0.0
    check('Transform Constraint Along Normals: MMB moves along the normal', C.get('normal_running'))
    check(f'the corner moved along its normal ({tuple(round(c, 3) for c in d)}, {along:.4f})',
          d.length > 1e-3 and abs(along) > 0.99)
    reset()
    with override():
        mod('preferences').get(bpy.context).transform_constraint = 'NONE'


run()
