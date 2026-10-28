"""E / D component picking, return to Rotate, and rotate around the picked custom axis."""
import math
import os
import sys
from importlib import import_module

import bpy
import bmesh
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, tap, view3d, win

C = {}


def mod(name):
    return import_module(MODULE+'.'+name)


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def tool():
    return bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=False)


def screen(point):
    area, region = view3d()
    xy = location_3d_to_region_2d(region, area.spaces.active.region_3d, Vector(point))
    return region.x+round(xy.x), region.y+round(xy.y)


def world():
    ob = bpy.data.objects['Cube']
    return [ob.matrix_world @ v.co for v in ob.data.vertices]


@step
def s_setup():
    setup()
    ob = bpy.data.objects['Cube']
    for other in bpy.context.view_layer.objects:
        other.select_set(other == ob)
        if other != ob:
            other.hide_set(True)
    bpy.context.view_layer.objects.active = ob
    with override():
        bpy.ops.wm.tool_set_by_id(name='builtin.rotate')
    C['widget'] = tool().widget
    C['world'] = world()
    tap('D')


@step
def s_pivot_on():
    check('E then D keeps Rotate selected and enables pivot handles',
          tool().idname == 'builtin.rotate' and tool().widget == mod('ui.manipulator').GROUP
          and bpy.context.tool_settings.use_transform_data_origin)
    area, region = view3d()
    with override():
        check('Rotate pivot editing uses translation handles', mod('ui.manipulator').tool_kind(bpy.context) == 'TRANSLATE')
        for y in (-.65, -.35, .35, .65):
            for z in (-.65, -.35, .35, .65):
                x, yy = screen((1, y, z))
                hit = mod('operators.preselect').pick(bpy.context, region, area.spaces.active.region_3d, (x-region.x, yy-region.y))
                if hit is not None and hit[1] == 'FACE':
                    C['pick'] = (x, yy)
                    break
            if 'pick' in C:
                break
    assert 'pick' in C, 'no visible face outside pivot handles'
    ev('MOUSEMOVE', 'NOTHING', x=C['pick'][0], y=C['pick'][1])
    ev('LEFTMOUSE', 'PRESS')
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_picked():
    ob = bpy.data.objects['Cube']
    check('face can be picked with E active', (ob.matrix_world.translation-Vector((1, 0, 0))).length < 1e-5)
    check('picking from Rotate preserves channels and geometry', ob.location.length < 1e-6
          and Vector(ob.rotation_euler).length < 1e-6 and all((a-b).length < 1e-5 for a, b in zip(C['world'], world())))
    tap('D')


@step
def s_rotate_back():
    pv = mod('operators.pivot')
    slot = bpy.context.scene.transform_orientation_slots[pv.ROTATE_SLOT]
    check('D again restores normal Rotate rings', tool().idname == 'builtin.rotate' and tool().widget == C['widget']
          and not bpy.context.tool_settings.use_transform_data_origin)
    check('Rotate adopts picked face axes', slot.type == pv.ORIENT_NAME and slot.custom_orientation.matrix.col[2].x > .999)
    C['pivot'] = bpy.data.objects['Cube'].matrix_world.translation.copy()
    C['axes'] = slot.custom_orientation.matrix.copy()
    area, region = view3d()
    rv = area.spaces.active.region_3d
    rv.view_rotation = Vector((0, 0, 1)).rotation_difference(Vector((1, 0, 0)))
    rv.view_location = C['pivot']
    rv.view_perspective = 'ORTHO'
    rv.view_distance = 8


def rotated():
    return abs(bpy.data.objects['Cube'].rotation_euler.x) > .05


for factor in (.9, .75, 1.05):
    @step
    def hover_ring(factor=factor):
        if rotated():
            return
        x, y = screen(C['pivot'])
        radius = factor*bpy.context.preferences.view.gizmo_size*bpy.context.preferences.system.ui_scale
        C['start'] = (round(x+radius*math.cos(.7)), round(y+radius*math.sin(.7)))
        C['end'] = (round(x+radius*math.cos(1.3)), round(y+radius*math.sin(1.3)))
        ev('MOUSEMOVE', 'NOTHING', x=C['start'][0], y=C['start'][1])

    @step
    def press_ring():
        if not rotated():
            ev('LEFTMOUSE', 'PRESS', x=C['start'][0], y=C['start'][1])

    @step
    def drag_ring():
        if not rotated():
            for i in range(1, 9):
                ev('MOUSEMOVE', 'NOTHING', x=round(C['start'][0]+(C['end'][0]-C['start'][0])*i/8),
                   y=round(C['start'][1]+(C['end'][1]-C['start'][1])*i/8))

    @step
    def release_ring():
        ev('LEFTMOUSE', 'RELEASE', x=C['end'][0], y=C['end'][1])


@step
def s_rotated():
    ob = bpy.data.objects['Cube']
    check('native custom Z ring rotates around picked world X axis', rotated()
          and abs(ob.rotation_euler.y) < 1e-5 and abs(ob.rotation_euler.z) < 1e-5)
    check('rotation keeps the picked pivot fixed', (ob.matrix_world.translation-C['pivot']).length < 1e-5)
    check('rotation turns the mesh', any((a-b).length > .01 for a, b in zip(C['world'], world())))
    tap('INSERT')


@step
def s_insert_on():
    check('Insert also enables Rotate pivot editing', tool().widget == mod('ui.manipulator').GROUP)
    tap('INSERT')


@step
def s_insert_off():
    check('Insert exit restores Rotate rings', tool().widget == C['widget'])
    with override():
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.wm.tool_set_by_id(name='builtin.rotate')
    tap('D')


@step
def s_component_pick():
    check('D from component Rotate enables pivot edit', mod('operators.hold').COMPONENT.on)
    area, region = view3d()
    with override():
        pre = mod('operators.preselect')
        for ob, cache in pre.caches(bpy.context):
            for point in cache.co:
                x, y = screen(point)
                hit = pre.pick(bpy.context, region, area.spaces.active.region_3d, (x-region.x, y-region.y))
                if hit is not None and hit[1] == 'VERT':
                    C['component_point'], C['component_axes'] = mod('operators.pivot_pick').component_frame(ob, cache.bm, 'VERT', hit[2])
                    C['component_world'] = [ob.matrix_world @ v.co for v in bmesh.from_edit_mesh(ob.data).verts]
                    C['component_xy'] = (x, y)
                    break
            if 'component_xy' in C:
                break
    assert 'component_xy' in C
    ev('MOUSEMOVE', 'NOTHING', x=C['component_xy'][0], y=C['component_xy'][1])
    ev('LEFTMOUSE', 'PRESS')
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_component_picked():
    check('component Rotate pivot snaps to vertex', (bpy.context.scene.cursor.location-C['component_point']).length < 1e-5)
    tap('D')


@step
def s_component_rotate_back():
    pv = mod('operators.pivot')
    slot = bpy.context.scene.transform_orientation_slots[pv.ROTATE_SLOT]
    check('component editing returns to Rotate with picked axes', tool().idname == 'builtin.rotate'
          and slot.type == pv.ORIENT_NAME and not mod('operators.hold').turned(slot.custom_orientation.matrix, C['component_axes']))
    ob = bpy.context.edit_object
    check('component Rotate pivot editing preserves mesh', all((p-ob.matrix_world @ v.co).length < 1e-5
          for p, v in zip(C['component_world'], bmesh.from_edit_mesh(ob.data).verts)))
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.wm.tool_set_by_id(name='builtin.rotate')
    ev('D', 'PRESS')


@step
def s_hold():
    check('holding D from Rotate enables pivot handles', tool().widget == mod('ui.manipulator').GROUP)
    ev('D', 'RELEASE')


@step
def s_hold_released():
    check('releasing held D restores Rotate rings', tool().widget == C['widget'] and not bpy.context.tool_settings.use_transform_data_origin)
    tap('D')


@step
def s_disable():
    mod('switch').set_mode(False, layout=False)
    check('disabling Maya mode restores Rotate tool and origin settings', tool().widget == C['widget']
          and not bpy.context.tool_settings.use_transform_data_origin)


run()
