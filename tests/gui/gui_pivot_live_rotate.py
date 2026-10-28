"""Observe arrows and pivot axes during real ring drags, before release and after cancel."""
import math
import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Euler, Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, tap, view3d, win

C = {}


def mod(name):
    return import_module(MODULE+'.'+name)


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def axes():
    return mod('operators.pivot').axes_for(bpy.data.objects['Cube'])


def same(a, b):
    return all(abs(x-y) < 1e-4 for ra, rb in zip(a, b) for x, y in zip(ra, rb))


def world():
    ob = bpy.data.objects['Cube']
    return [ob.matrix_world @ v.co for v in ob.data.vertices]


def untouched():
    ob = bpy.data.objects['Cube']
    return same(ob.matrix_basis, C['basis']) and all((p-q).length < 1e-5 for p, q in zip(C['world'], world()))


def ring_point(angle):
    area, region = view3d()
    point = C['ring_matrix'] @ Vector((math.cos(angle), math.sin(angle), 0))
    xy = location_3d_to_region_2d(region, area.spaces.active.region_3d, point)
    return region.x+round(xy.x), region.y+round(xy.y)


@step
def s_setup():
    setup()
    ob = bpy.data.objects['Cube']
    for other in bpy.context.view_layer.objects:
        other.select_set(other == ob)
        if other != ob:
            other.hide_set(True)
    bpy.context.view_layer.objects.active = ob
    ob.rotation_euler, ob.scale = (.2, -.1, .3), (1.4, .8, 1.1)
    pv = mod('operators.pivot')
    ob[pv.PROP] = tuple(Euler((.5, .3, -.4)).to_quaternion())
    bpy.context.view_layer.update()
    C['world'], C['basis'] = world(), ob.matrix_basis.copy()
    man = mod('ui.manipulator')
    original = man.ALLSET_GGT_xform.draw_prepare
    def spy(self, context):
        original(self, context)
        C['group'] = self
    man.ALLSET_GGT_xform.draw_prepare = spy
    with override():
        bpy.ops.wm.tool_set_by_id(name='builtin.rotate')
    tap('D')


for gesture in range(3):
    @step
    def prepare(gesture=gesture):
        C['initial'] = axes().copy()
        C['gesture'] = gesture
        C['axis'] = 'ZXY'[gesture]
        area, _region = view3d()
        rv = area.spaces.active.region_3d
        rv.view_rotation = (C['initial'] @ mod('ui.manipulator')._axis_rot(C['axis'])).to_quaternion()
        rv.view_location = bpy.data.objects['Cube'].matrix_world.translation
        rv.view_distance, rv.view_perspective = 8, 'ORTHO'

    @step
    def hover():
        gz = next(gz for gz, role, axis in C['group'].handles if role == 'PIVOT_RING' and axis == C['axis'])
        C['ring_matrix'] = gz.matrix_world.copy()
        C['start'], C['middle'], C['end'] = [ring_point(a) for a in (.7, 1.15, 1.5)]
        with override():
            _center, frame, _otype = mod('ui.manipulator').pivot_frame(bpy.context, 'TRANSLATE')
            check('pivot arrows and rings start in the saved custom frame', same(frame, C['initial']))
        ev('MOUSEMOVE', 'NOTHING', x=C['start'][0], y=C['start'][1])

    @step
    def press():
        ev('LEFTMOUSE', 'PRESS', x=C['start'][0], y=C['start'][1])

    @step
    def drag_first():
        for i in range(1, 7):
            ev('MOUSEMOVE', 'NOTHING', x=round(C['start'][0]+(C['middle'][0]-C['start'][0])*i/6),
               y=round(C['start'][1]+(C['middle'][1]-C['start'][1])*i/6))

    @step
    def observe_live():
        check('pivot ring uses the live pivot rotation operator', any(op.bl_idname == 'ALLSET_OT_pivot_rotate' for op in win().modal_operators))
        check('pivot orientation changes while mouse is still down', not same(axes(), C['initial']))
        live = axes()
        index = 'XYZ'.index(C['axis'])
        check('drag turns around the displayed '+C['axis']+' axis', live.col[index].dot(C['initial'].col[index]) > .9999)
        for gz, role, axis in C['group'].handles:
            if role == 'AXIS':
                actual = gz.matrix_basis.to_3x3().col[2].normalized()
                check('arrow '+axis+' follows live pivot rotation', actual.dot(live.col['XYZ'.index(axis)]) > .9999)
            elif role == 'PIVOT_RING':
                actual = gz.matrix_basis.to_3x3().col[2].normalized()
                check('ring '+axis+' shares the live arrow frame', actual.dot(live.col['XYZ'.index(axis)]) > .9999)
        check('mesh and channels stay fixed during pivot rotation', untouched())
        ev('MOUSEMOVE', 'NOTHING', x=C['end'][0], y=C['end'][1])

    @step
    def finish(gesture=gesture):
        C['preview'] = axes().copy()
        if gesture == 2:
            tap('ESC')
        else:
            ev('LEFTMOUSE', 'RELEASE', x=C['end'][0], y=C['end'][1])

    @step
    def after(gesture=gesture):
        if gesture == 2:
            check('Escape restores the exact frame from before the drag', same(axes(), C['initial']))
            ev('LEFTMOUSE', 'RELEASE')
        else:
            check('releasing the mouse keeps the last displayed orientation without jumping', same(axes(), C['preview']))
        check('pivot rotation leaves geometry and channels unchanged', untouched())


@step
def s_exit():
    C['final'] = axes().copy()
    tap('D')


@step
def s_finished():
    pv = mod('operators.pivot')
    check('leaving pivot edit retains the displayed orientation', same(axes(), C['final']))
    check('Rotate receives the final preview frame', same(bpy.context.scene.transform_orientation_slots[pv.ROTATE_SLOT].custom_orientation.matrix, C['final']))
    area, _region = view3d()
    area.spaces.active.region_3d.view_rotation = C['final'].to_quaternion()
    ev('D', 'PRESS')


def prepare_ring():
    gz = next(gz for gz, role, axis in C['group'].handles if role == 'PIVOT_RING' and axis == 'Z')
    C['ring_matrix'] = gz.matrix_world.copy()
    C['initial'] = axes().copy()
    C['start'], C['middle'] = [ring_point(a) for a in (.7, 1.3)]
    ev('MOUSEMOVE', 'NOTHING', x=C['start'][0], y=C['start'][1])


@step
def s_hold_hover():
    prepare_ring()
    ev('J', 'PRESS')


@step
def s_hold_press():
    ev('LEFTMOUSE', 'PRESS', x=C['start'][0], y=C['start'][1])


@step
def s_hold_drag():
    for i in range(1, 9):
        ev('MOUSEMOVE', 'NOTHING', x=round(C['start'][0]+(C['middle'][0]-C['start'][0])*i/8),
           y=round(C['start'][1]+(C['middle'][1]-C['start'][1])*i/8))


@step
def s_snap():
    live = axes()
    angle = math.atan2(C['initial'].col[2].dot(C['initial'].col[0].cross(live.col[0])), C['initial'].col[0].dot(live.col[0]))
    increment = bpy.context.tool_settings.snap_angle_increment_3d
    check('J snaps the live pivot ring to the angular increment', abs(angle) > .05 and abs(angle/increment-round(angle/increment)) < 1e-4)
    C['preview'] = axes().copy()
    ev('D', 'RELEASE')
    ev('J', 'RELEASE')


@step
def s_d_released_during_drag():
    check('releasing held D waits for the active ring drag', bpy.context.tool_settings.use_transform_data_origin
          and any(op.bl_idname == 'ALLSET_OT_pivot_rotate' for op in win().modal_operators))
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_hold_finished():
    check('held pivot edit exits after the ring drag finishes', not bpy.context.tool_settings.use_transform_data_origin)
    check('D release preserves the last preview and geometry', same(axes(), C['preview']) and untouched())
    area, _region = view3d()
    area.spaces.active.region_3d.view_rotation = axes().to_quaternion()
    tap('D')


@step
def s_numeric_hover():
    prepare_ring()


@step
def s_numeric_press():
    ev('LEFTMOUSE', 'PRESS', x=C['start'][0], y=C['start'][1])


@step
def s_numeric_start():
    ev('MOUSEMOVE', 'NOTHING', x=C['middle'][0], y=C['middle'][1])


@step
def s_numeric_entry():
    ev('TEXTINPUT', 'PRESS', unicode='4')
    ev('TEXTINPUT', 'PRESS', unicode='5')


@step
def s_numeric_confirm():
    expected = Matrix.Rotation(math.radians(45), 3, C['initial'].col[2]) @ C['initial']
    check('numeric entry sets an exact angle in the displayed pivot frame', same(axes(), expected))
    tap('RET')
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_done():
    check('numeric pivot rotation preserves geometry and channels', untouched())
    tap('D')


run()
