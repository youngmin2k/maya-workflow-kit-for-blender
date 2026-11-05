"""Native Undo/Redo, taper pointer editing and Delete History through the real event loop."""
import os
import sys
from importlib import import_module

import bpy
import bmesh
from mathutils import Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, tap, view3d, win

C = {}


def mod(name):
    return import_module(MODULE+'.'+name)


def viewport():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


@step
def start():
    setup()
    with viewport():
        bpy.ops.ed.undo_push(message='Start')
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.context.scene.tool_settings.mesh_select_mode = (False, False, True)
        bm = bmesh.from_edit_mesh(bpy.context.object.data)
        mod('operators.extrude').deselect_all(bm)
        max(bm.faces, key=lambda f: f.normal.z).select_set(True)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(bpy.context.object.data)
        bpy.ops.allset.extrude('EXEC_DEFAULT', True, thickness=.5)
        bpy.ops.allset.extrude('EXEC_DEFAULT', True, thickness=.25)
        C['ob'] = bpy.context.object.name
        C['data'] = mod('operators.model_history').read(bpy.context.object)
        C['first'] = C['data']['nodes'][0]['id']
        C['before'] = mod('operators.extrude').coords_hash(bmesh.from_edit_mesh(bpy.context.object.data))


@step
def earlier():
    with viewport():
        ob = bpy.data.objects[C['ob']]
        mod('operators.model_history').activate(ob, C['first'])
        node = mod('ui.node_attributes').target(bpy.context)
        check('earlier history node is available', node is not None)
        mod('ui.in_view_editor').apply(bpy.context, node, dict(node.params, thickness=1))
        C['after'] = mod('operators.extrude').coords_hash(bmesh.from_edit_mesh(ob.data))
        check('editing earlier node changes downstream geometry', C['after'] != C['before'])
    tap('Z')


@step
def undo_earlier():
    with viewport():
        ob = bpy.data.objects[C['ob']]
        actual = mod('operators.extrude').coords_hash(bmesh.from_edit_mesh(ob.data))
        check('native Undo restores earlier-node geometry', actual == C['before'])
        node = mod('ui.node_attributes').target(bpy.context)
        check('native Undo keeps history editable with restored parameters', node is not None and node.params['thickness'] == .5)
    ev('Z', 'PRESS', shift=True)
    ev('Z', 'RELEASE', shift=True)


@step
def redo_earlier():
    with viewport():
        ob = bpy.data.objects[C['ob']]
        actual = mod('operators.extrude').coords_hash(bmesh.from_edit_mesh(ob.data))
        check('native Redo restores the downstream result', actual == C['after'])
        check('native Redo keeps history editable', mod('ui.node_attributes').target(bpy.context) is not None)
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.allset.delete_history('EXEC_DEFAULT', True)
    tap('Z')


@step
def undo_delete():
    with viewport():
        ob = bpy.data.objects[C['ob']]
        check('Undo Delete History restores every node', len(mod('operators.model_history').records(ob)) == 2)


@step
def bridge():
    with viewport():
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        bm = bmesh.new()
        for z in (0, 4):
            bmesh.ops.create_cube(bm, size=2, matrix=Matrix.Translation((0, 0, z)))
        bm.normal_update()
        for f in bm.faces:
            f.select_set(abs(f.normal.z) > .9 and 0 < f.calc_center_median().z < 4)
        mesh = bpy.data.meshes.new('history_bridge')
        bm.to_mesh(mesh)
        bm.free()
        ob = bpy.data.objects.new('history_bridge', mesh)
        bpy.context.scene.collection.objects.link(ob)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.allset.bridge('EXEC_DEFAULT', True, divisions=3, curve_type=1)
        C['ramp_before'] = mod('ui.node_attributes').target(bpy.context).params['taper_curve']
        check('ramp graph opens', bpy.ops.allset.bridge_ramp('INVOKE_DEFAULT') == {'RUNNING_MODAL'})


@step
def add_point():
    folder = os.environ.get('ALLSET_GUI_SHOTS')
    if folder:
        screenshot(os.path.join(folder, 'bridge_taper_curve.png'))
    editor = mod('ui.bridge_editor')._editors[0]
    x0, y0, x1, y1 = editor._graph
    area, region = view3d()
    C['point'] = region.x+round((x0+x1)/2), region.y+round(y0+.25*(y1-y0))
    x, y = C['point']
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def accept_point():
    tap('THREE')
    tap('RET')


@step
def accepted():
    with viewport():
        node = mod('ui.node_attributes').target(bpy.context)
        check('pointer graph commits its changed ramp', node.params['taper_curve'] != C['ramp_before'])
        check('graph releases shared attribute ownership', not mod('ui.attribute_edit').busy(bpy.context))
        check('graph removes its draw handler and modal state', not mod('ui.bridge_editor')._editors)
    tap('Z')


@step
def undo_ramp():
    with viewport():
        node = mod('ui.node_attributes').target(bpy.context)
        check('one Undo restores the ramp', node is not None and node.params['taper_curve'] == C['ramp_before'])


@step
def edit_curve():
    with viewport():
        node = mod('ui.node_attributes').target(bpy.context)
        mod('ui.in_view_editor').apply(bpy.context, node, dict(node.params, curve_type=2))
        C['bridge'] = node.ob.name
        bpy.ops.object.mode_set(mode='OBJECT')
        C['curve_before'] = mod('operators.extrude').mesh_coords_hash(node.ob.data)
        check('Edit Path enters native curve editing', bpy.ops.allset.bridge_path('INVOKE_DEFAULT', edit=True) == {'FINISHED'})
        path = bpy.context.object
        for point in path.data.splines[0].points:
            point.select = False
        path.data.splines[0].points[2].select = True
        bpy.ops.transform.translate('EXEC_DEFAULT', True, value=(1, 0, 0))


@step
def curve_changed():
    with viewport():
        ob = bpy.data.objects[C['bridge']]
        check('native curve editing updates Bridge through dependency handling',
              mod('operators.extrude').mesh_coords_hash(ob.data) != C['curve_before'])
        check('the live Bridge remains editable', mod('operators.extrude').object_record(ob) is not None)


run()
