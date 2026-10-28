"""J pressed/released during pivot translate/rotate updates snapping without moving the mesh."""
import math
import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, tap, view3d, win

C = {}


def mod(name):
    return import_module(MODULE+'.'+name)


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def screen(point):
    area, region = view3d()
    xy = location_3d_to_region_2d(region, area.spaces.active.region_3d, point)
    return region.x+round(xy.x), region.y+round(xy.y)


def move(point):
    ev('MOUSEMOVE', 'NOTHING', x=point[0], y=point[1])


def world():
    ob = bpy.data.objects['Cube']
    return [ob.matrix_world @ v.co for v in ob.data.vertices]


def pivot_point():
    return bpy.data.objects['Cube'].matrix_world.translation.copy()


def preserved():
    ob = bpy.data.objects['Cube']
    return ob.location.length < 1e-6 and Vector(ob.rotation_euler).length < 1e-6 and all((p-q).length < 1e-5 for p, q in zip(C['world'], world()))


@step
def s_setup():
    setup()
    ob = bpy.data.objects['Cube']
    for other in bpy.context.view_layer.objects:
        other.select_set(other == ob)
        if other != ob:
            other.hide_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.context.tool_settings.use_snap = False
    bpy.context.tool_settings.snap_elements = {'VERTEX'}
    C['snap'] = mod('operators.hold').GROUPS['snap'].capture(bpy.context.tool_settings)
    C['world'] = world()
    man = mod('ui.manipulator')
    original = man.ALLSET_GGT_xform.draw_prepare
    def spy(self, context):
        original(self, context)
        C['group'] = self
    man.ALLSET_GGT_xform.draw_prepare = spy
    with override():
        bpy.ops.wm.tool_set_by_id(name='builtin.rotate')
    area, _region = view3d()
    rv = area.spaces.active.region_3d
    rv.view_perspective, rv.view_distance = 'ORTHO', 8
    tap('D')


@step
def s_wait_gizmo():
    check('D enables pivot editing before the J tests', bpy.context.tool_settings.use_transform_data_origin)
    view3d()[0].tag_redraw()


@step
def s_translate_hover():
    gz = next(gz for gz, role, axis in C['group'].handles if role == 'AXIS' and axis == 'X')
    C['start'] = screen(gz.matrix_world @ Vector((0, 0, .65)))
    C['delta'] = (75, 23)
    move(C['start'])


@step
def s_translate_press():
    ev('LEFTMOUSE', 'PRESS')


@step
def s_translate_drag():
    for i in range(1, 9):
        move((C['start'][0]+round(C['delta'][0]*i/8), C['start'][1]+round(C['delta'][1]*i/8)))


@step
def s_translate_free():
    C['free_point'] = pivot_point()
    check('pivot translate starts as a continuous drag', abs(C['free_point'].x-round(C['free_point'].x)) > .01)
    ev('J', 'PRESS')


@step
def s_translate_snapped():
    point = pivot_point()
    check('pressing J during translate immediately enables unit steps', abs(point.x-round(point.x)) < 1e-5 and abs(point.x) > .1)
    check('step translate keeps mesh and channels fixed', preserved())
    ev('J', 'RELEASE')


@step
def s_translate_unsnapped():
    check('releasing J during translate immediately restores free movement', (pivot_point()-C['free_point']).length < 1e-5)
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_translate_done():
    check('J translate preserves the original snap preferences', mod('operators.hold').GROUPS['snap'].capture(bpy.context.tool_settings) == C['snap'])
    handle = mod('operators.manip').HANDLES.get('TRANSLATE')
    check('pivot translation remembers the selected axis', handle is not None and tuple(handle['constraint_axis']) == (True, False, False))
    area, _region = view3d()
    area.spaces.active.region_3d.view_rotation = Matrix.Identity(3).to_quaternion()
    area.spaces.active.region_3d.view_location = pivot_point()


@step
def s_rotate_hover():
    gz = next(gz for gz, role, axis in C['group'].handles if role == 'PIVOT_RING' and axis == 'Z')
    matrix = gz.matrix_world.copy()
    C['ring_start'], C['ring_end'] = [screen(matrix @ Vector((math.cos(a), math.sin(a), 0))) for a in (.7, 1.39)]
    C['initial_axes'] = mod('operators.pivot').axes_for(bpy.data.objects['Cube'])
    move(C['ring_start'])


@step
def s_rotate_press():
    ev('LEFTMOUSE', 'PRESS')


@step
def s_rotate_drag():
    for i in range(1, 9):
        move((round(C['ring_start'][0]+(C['ring_end'][0]-C['ring_start'][0])*i/8),
              round(C['ring_start'][1]+(C['ring_end'][1]-C['ring_start'][1])*i/8)))


@step
def s_rotate_free():
    C['free_axes'] = mod('operators.pivot').axes_for(bpy.data.objects['Cube'])
    ev('J', 'PRESS')


@step
def s_rotate_snapped():
    frame = mod('operators.pivot').axes_for(bpy.data.objects['Cube'])
    angle = C['initial_axes'].to_quaternion().rotation_difference(frame.to_quaternion()).angle
    increment = bpy.context.tool_settings.snap_angle_increment_3d
    check('pressing J during rotate immediately enables angular steps', angle > .05 and abs(angle/increment-round(angle/increment)) < 1e-4)
    ev('J', 'RELEASE')


@step
def s_rotate_unsnapped():
    frame = mod('operators.pivot').axes_for(bpy.data.objects['Cube'])
    check('releasing J during rotate immediately restores the free angle', not mod('operators.hold').turned(frame, C['free_axes']))
    check('J rotate keeps mesh and channels fixed', preserved())
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_done():
    check('J rotate preserves original snap preferences', mod('operators.hold').GROUPS['snap'].capture(bpy.context.tool_settings) == C['snap'])
    tap('D')


run()
