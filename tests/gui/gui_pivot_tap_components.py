"""Maya D tap toggles custom pivot edit; V/E/F clicks place the pivot, not geometry."""
import os
import sys
from importlib import import_module

import bmesh
import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, tap, view3d, win

C = {}


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def click(point):
    area, region = view3d()
    xy = location_3d_to_region_2d(region, area.spaces.active.region_3d, Vector(point))
    x, y = region.x+round(xy.x), region.y+round(xy.y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


def available(points, kind):
    """Choose a visible component away from the manipulator, whose handles own their pixels."""
    area, region = view3d()
    with override():
        pre = import_module(MODULE+'.operators.preselect')
        for point in points:
            xy = location_3d_to_region_2d(region, area.spaces.active.region_3d, Vector(point))
            target = pre.pick(bpy.context, region, area.spaces.active.region_3d, (round(xy.x), round(xy.y)))
            if target is not None and target[1] == kind:
                if kind != 'FACE':
                    ob, cache = next((ob, cache) for ob, cache in pre.caches(bpy.context) if ob.as_pointer() == target[0])
                    picked, _axes = import_module(MODULE+'.operators.pivot_pick').component_frame(ob, cache.bm, kind, target[2])
                    if (picked-Vector(point)).length > 1e-5:
                        continue
                return point
    raise AssertionError('No unoccluded '+kind+' point outside the manipulator')


def world_vertices():
    ob = bpy.data.objects['Cube']
    vertices = bmesh.from_edit_mesh(ob.data).verts if ob.mode == 'EDIT' else ob.data.vertices
    return [ob.matrix_world @ v.co for v in vertices]


def geometry_stays():
    return all((a-b).length < 1e-5 for a, b in zip(C['world'], world_vertices()))


def selected():
    bm = bmesh.from_edit_mesh(bpy.data.objects['Cube'].data)
    return tuple(tuple(e.index for e in elements if e.select) for elements in (bm.verts, bm.edges, bm.faces))


@step
def s_setup():
    C['mouse'] = setup()
    ob = bpy.data.objects['Cube']
    for other in bpy.context.view_layer.objects:
        other.select_set(other == ob)
        if other != ob:
            other.hide_set(True)
    bpy.context.view_layer.objects.active = ob
    with override():
        bpy.ops.wm.tool_set_by_id(name='builtin.move')
    C['world'] = world_vertices()
    tap('D')


@step
def s_object_latched():
    check('D tap stays in object pivot edit after release', bpy.context.scene.tool_settings.use_transform_data_origin)
    click((1, -1, 1))


@step
def s_vertex():
    ob = bpy.data.objects['Cube']
    check('object pivot snaps exactly to clicked vertex', (ob.matrix_world.translation-Vector((1, -1, 1))).length < 1e-5)
    check('vertex pick preserves object channels and world geometry', ob.location.length < 1e-6 and geometry_stays())
    with override():
        bpy.ops.allset.reset_pivot()


@step
def s_click_edge():
    click((1, 0, 1))


@step
def s_edge():
    ob = bpy.data.objects['Cube']
    check('object pivot snaps exactly to edge midpoint', (ob.matrix_world.translation-Vector((1, 0, 1))).length < 1e-5)
    check('edge pick preserves world geometry', geometry_stays())
    with override():
        bpy.ops.allset.reset_pivot()


@step
def s_click_face():
    click(available([(1, y, z) for y in (-.65, -.35, .35, .65) for z in (-.65, -.35, .35, .65)], 'FACE'))


@step
def s_face():
    ob = bpy.data.objects['Cube']
    check(f'face click sets pivot to face centre ({tuple(ob.matrix_world.translation)})', (ob.matrix_world.translation-Vector((1, 0, 0))).length < 1e-5)
    check('face pick preserves world geometry', geometry_stays())
    tap('D')


@step
def s_object_off():
    check('second D tap exits object pivot edit', not bpy.context.scene.tool_settings.use_transform_data_origin)
    with override():
        bpy.ops.allset.reset_pivot()
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.context.scene.tool_settings.mesh_select_mode = (False, True, False)
        bm = bmesh.from_edit_mesh(bpy.context.edit_object.data)
        bm.edges.ensure_lookup_table()
        bm.edges[0].select_set(True)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(bpy.context.edit_object.data)
        bpy.ops.wm.tool_set_by_id(name='builtin.move')
    C['selected'] = selected()
    tap('D')


@step
def s_component_on():
    hold = import_module(MODULE+'.operators.hold')
    check('component D tap stays in pivot edit', hold.COMPONENT.on and hold.COMPONENT.toggled)
    check('pivot editing enables multi-component picking', tuple(bpy.context.tool_settings.mesh_select_mode) == (True, True, True))
    C['vertex'] = available([tuple(p) for p in C['world']], 'VERT')
    click(C['vertex'])


@step
def s_component_vertex():
    check(f'component pivot snaps exactly to vertex ({tuple(bpy.context.scene.cursor.location)})', (bpy.context.scene.cursor.location-Vector(C['vertex'])).length < 1e-5)
    check('pivot pick leaves original component selection and geometry intact', selected() == C['selected'] and geometry_stays())
    ob = bpy.data.objects['Cube']
    bm = bmesh.from_edit_mesh(ob.data)
    C['edge'] = available([tuple(ob.matrix_world @ ((e.verts[0].co+e.verts[1].co)/2)) for e in bm.edges], 'EDGE')
    click(C['edge'])


@step
def s_component_edge():
    check(f"component pivot snaps exactly to edge midpoint ({tuple(bpy.context.scene.cursor.location)} vs {C['edge']})", (bpy.context.scene.cursor.location-Vector(C['edge'])).length < 1e-5)
    check('edge pick preserves component selection and geometry', selected() == C['selected'] and geometry_stays())
    click(available([(1, y, z) for y in (-.65, -.35, .35, .65) for z in (-.65, -.35, .35, .65)], 'FACE'))


@step
def s_component_face():
    check('component pivot snaps exactly to face centre', (bpy.context.scene.cursor.location-Vector((1, 0, 0))).length < 1e-5)
    check('face pick preserves component selection and geometry', selected() == C['selected'] and geometry_stays())
    tap('D')


@step
def s_component_off():
    hold = import_module(MODULE+'.operators.hold')
    check('second component D tap exits pivot edit', not hold.COMPONENT.on)
    check('original edge selection mode returns', tuple(bpy.context.tool_settings.mesh_select_mode) == (False, True, False))
    check('placed pivot stays available for transforms', bpy.context.scene.tool_settings.transform_pivot_point == 'CURSOR')
    folder = os.environ.get('ALLSET_GUI_SHOTS')
    if folder:
        screenshot(os.path.join(folder, 'pivot_tap_components.png'))


run()
