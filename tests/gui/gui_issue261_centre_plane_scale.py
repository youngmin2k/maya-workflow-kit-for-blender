"""Prevent Negative Scale on the Scale tool's centre and plane handles: components stop at zero (onto the pivot /
onto a line through it) instead of flipping; Object Mode still scales past zero."""
import os
import sys
from importlib import import_module

import bmesh
import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
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


def move(p):
    ev('MOUSEMOVE', 'NOTHING', x=round(p[0]), y=round(p[1]))


def handle_drag():
    return any(op.bl_idname == 'ALLSET_OT_manip_scale' for op in win().modal_operators)


def factor():
    return mod('operators.manip_scale').LAST.get('factor')


def screen_of(point):
    area, region = view3d()
    xy = location_3d_to_region_2d(region, region.data, point)
    return Vector((round(region.x + xy.x), round(region.y + xy.y)))


def handle(role, data=None):
    return next(g for g, r, d in C['group'].handles if r == role and (data is None or d == data))


def reset_mesh():
    with override():
        bm_ = bm()
        for v, co in zip(bm_.verts, C['before']):
            v.co = co
        bmesh.update_edit_mesh(bpy.context.edit_object.data)


@step
def s_setup():
    mouse = setup()
    ui = mod('ui.manipulator')
    original = ui.ALLSET_GGT_xform.draw_prepare

    def spy(self, context):
        original(self, context)
        C['group'] = self
    ui.ALLSET_GGT_xform.draw_prepare = spy
    with override():
        ob = bpy.data.objects['Cube']
        bpy.ops.object.select_all(action='DESELECT')
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.context.scene.cursor.location = (0, 0, 0)
        ts = bpy.context.tool_settings
        ts.transform_pivot_point = 'CURSOR'
        ts.use_snap = False
        mod('preferences').get(bpy.context).prevent_negative_scale = True
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='VERT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.context.scene.transform_orientation_slots[3].type = 'GLOBAL'
        bpy.ops.wm.tool_set_by_id(name='builtin.scale')
        region = view3d()[1]
        region.data.view_rotation = Quaternion((1, 0, 0, 0))     # top view: the XY plane handle faces the camera
        region.data.view_location = (0, 0, 0)
        region.data.view_distance = 9
        C['before'] = [v.co.copy() for v in bm().verts]
    move(mouse)


@step
def s_wait_tool():
    mod('ui.manipulator').ensure_tools(patched=True)
    view3d()[0].tag_redraw()


@step
def s_wait_draw():
    view3d()[0].tag_redraw()


# --- centre handle: a horizontal drag to the left past zero -----------------------------------------------------

@step
def s_centre_hover():
    C['start'] = screen_of(handle('CENTER').matrix_world.translation)
    move(C['start'])


@step
def s_centre_press():
    ev('LEFTMOUSE', 'PRESS', x=round(C['start'].x), y=round(C['start'].y))


@step
def s_centre_nudge():
    move(C['start'] - Vector((8, 0)))


@step
def s_centre_far():
    check('centre handle starts the Maya scale drag', handle_drag())
    move(C['start'] - Vector((600, 0)))


@step
def s_centre_result():
    check(f'centre handle stops at zero (no flip, factor {factor()})', factor() == 0.0)
    check('every vertex meets the pivot', all(v.co.length < 1e-6 for v in bm().verts))
    ev('LEFTMOUSE', 'RELEASE', x=round(C['start'].x) - 600, y=round(C['start'].y))


@step
def s_centre_released():
    check('release keeps the collapsed result', all(v.co.length < 1e-6 for v in bm().verts))
    reset_mesh()
    view3d()[0].tag_redraw()


@step
def s_wait_reset():
    view3d()[0].tag_redraw()


# --- XY plane handle: drag through the pivot and beyond ---------------------------------------------------------

@step
def s_plane_hover():
    gz = handle('PLANE', 'XY')
    at = mod('ui.manipulator').PLANE_AT
    C['start'] = screen_of(gz.matrix_world @ Vector((at, at, 0.0)))     # the square sits off the centre
    centre = screen_of(Vector((0, 0, 0)))
    away = C['start'] - centre
    C['end'] = C['start'] - away * 4.0           # well past the pivot on the other side
    move(C['start'])


@step
def s_plane_press():
    ev('LEFTMOUSE', 'PRESS', x=round(C['start'].x), y=round(C['start'].y))


@step
def s_plane_nudge():
    move(C['start'] + (C['end'] - C['start']) * 0.05)


@step
def s_plane_far():
    check('plane handle starts the Maya scale drag', handle_drag())
    move(C['end'])


@step
def s_plane_result():
    check(f'plane handle stops at zero (no flip, factor {factor()})', factor() == 0.0)
    vs = bm().verts
    check('X and Y meet the pivot, Z is kept',
          all(abs(v.co.x) < 1e-6 and abs(v.co.y) < 1e-6 for v in vs)
          and all(abs(v.co.z - b.z) < 1e-6 for v, b in zip(vs, C['before'])))
    ev('LEFTMOUSE', 'RELEASE', x=round(C['end'].x), y=round(C['end'].y))


@step
def s_done():
    reset_mesh()


run()
