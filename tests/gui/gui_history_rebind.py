"""Rebind selection accepts once, cancels cleanly and restores native Undo/Save behavior."""
from importlib import import_module
import os
from pathlib import Path
import sys

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sim import MODULE, check, ev, run, setup, step, tap, view3d, win
from test_history_references import side_chain, fail_side_edit

C = {}


def mod(name):
    return import_module(MODULE+'.'+name)


def viewport():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def fingerprint(ob):
    ex = mod('operators.extrude')
    return ex.coords_hash(bmesh.from_edit_mesh(ob.data)) if ob.mode == 'EDIT' else ex.mesh_coords_hash(ob.data)


def propose(divisions):
    ob = bpy.data.objects[C['object']]
    history = mod('operators.model_history')
    first = history.read(ob)['nodes'][0]
    try:
        history.edit(ob, first['id'], dict(first['params'], divisions=divisions))
    except ValueError:
        pass
    check('the proposed topology edit has a replacement selection request', history.pending(ob) is not None)
    check('Rebind Selection opens', bpy.ops.allset.history_rebind('INVOKE_DEFAULT', object_name=ob.name) == {'RUNNING_MODAL'})


@step
def initialize():
    setup()


@step
def start():
    with viewport():
        ob = side_chain()
        C['object'], C['before'] = ob.name, fingerprint(ob)
        mod('undo_steps').push('Before rebind')
        propose(2)


@step
def choose():
    with viewport():
        ob = bpy.data.objects[C['object']]
        session = mod('ui.history_rebind')._session
        check('original geometry stays intact while choosing', fingerprint(ob) == C['before'])
        check('the original is hidden and a detached input is editable', ob.hide_get() and session is not None
              and bpy.context.object.name == session._preview)
        bm = bmesh.from_edit_mesh(bpy.context.object.data)
        sides = [face for face in bm.faces if face.normal.x > .9 and face.calc_center_median().z > 1]
        min(sides, key=lambda face:face.calc_center_median().z).select_set(True)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(bpy.context.object.data)
    tap('RET')


@step
def accepted():
    with viewport():
        ob = bpy.data.objects[C['object']]
        history = mod('operators.model_history')
        check('Enter commits the proposed upstream edit', history.read(ob)['nodes'][0]['params']['divisions'] == 2)
        check('the original edit context and visibility are restored', bpy.context.object == ob
              and ob.mode == 'EDIT' and not ob.hide_get())
        check('Rebind removes its temporary object and ownership', mod('ui.history_rebind')._session is None
              and not mod('ui.attribute_edit').busy(bpy.context)
              and not any(item.get('allset_history_rebind_preview') for item in bpy.data.objects))
        C['after'] = fingerprint(ob)
    tap('Z')


@step
def undone():
    with viewport():
        ob = bpy.data.objects[C['object']]
        check('one native Undo restores geometry and original divisions', fingerprint(ob) == C['before']
              and mod('operators.model_history').read(ob)['nodes'][0]['params']['divisions'] == 3)
        check('Undo retains editable history', mod('operators.extrude').current(ob) is not None)
    ev('Z','PRESS',shift=True)
    ev('Z','RELEASE',shift=True)


@step
def redone():
    with viewport():
        ob = bpy.data.objects[C['object']]
        check('native Redo restores the rebound result', fingerprint(ob) == C['after'])
        propose(3)
    tap('ESC')


@step
def cancelled():
    with viewport():
        ob = bpy.data.objects[C['object']]
        check('Esc preserves the original geometry and clears the proposal', fingerprint(ob) == C['after']
              and mod('operators.model_history').pending(ob) is None)
        check('Esc restores visibility and removes preview state', not ob.hide_get()
              and mod('ui.history_rebind')._session is None)
        propose(3)


@step
def saved():
    with viewport():
        path = Path(os.environ['BLENDER_USER_CONFIG']).parent/'rebind_save.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        check('Save cancels the detached preview before serialization', mod('ui.history_rebind')._session is None
              and not any(item.get('allset_history_rebind_preview') for item in bpy.data.objects))


@step
def reopen():
    with viewport():
        path = Path(os.environ['BLENDER_USER_CONFIG']).parent/'rebind_save.blend'
        bpy.ops.wm.open_mainfile(filepath=str(path))


@step
def loaded():
    with viewport():
        ob = bpy.data.objects[C['object']]
        check('Save Load keeps the accepted original result', fingerprint(ob) == C['after'] and not ob.hide_get())
        check('Save Load retains identity-based history', mod('operators.model_history').read(ob)['version'] == 2)


@step
def another_layer():
    with viewport():
        C['source_layer'] = bpy.context.view_layer.name
        propose(3)
        layer = bpy.context.scene.view_layers.new('Rebind Context Test')
        win().view_layer = layer
        area, region = view3d()
        ev('MOUSEMOVE','NOTHING',x=region.x+region.width//2,y=region.y+region.height//2)


@step
def layer_cancelled():
    ob = bpy.data.objects[C['object']]
    original_layer = win().scene.view_layers[C['source_layer']]
    check('changing View Layer cancels the replacement session', mod('ui.history_rebind')._session is None)
    check('cancellation restores visibility in the original View Layer', not ob.hide_get(view_layer=original_layer))
    check('cancellation preserves the chosen View Layer', win().view_layer.name == 'Rebind Context Test')


run()
