"""F8 leaves the node editor, ordinary clicks pass through, and T reopens it in Object Mode."""
import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, tap, view3d, win

C = {'errors': []}


def mod(name):
    return import_module(MODULE+'.'+name)


def viewport():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def node():
    return mod('ui.node_attributes').target(bpy.context)


@step
def start():
    setup()
    with viewport():
        bpy.ops.wm.tool_set_by_id(name='builtin.move')
    editor = mod('ui.in_view_editor')
    original = editor.current_layout
    def observe(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except Exception as error:
            C['errors'].append(str(error))
            raise
    editor.current_layout = observe


@step
def bevel():
    with viewport():
        ob = bpy.context.active_object
        C['object'] = ob.name
        ob.scale = (4.195, 4.195, 4.195)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.wm.tool_set_by_id(name='builtin.move')
        bpy.context.scene.tool_settings.mesh_select_mode = (False, True, False)
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.allset.bevel('EXEC_DEFAULT', True, fraction=.25)
        bpy.ops.view3d.view_selected()
    area, region = view3d()
    C['point'] = region.x+int(region.width*.15), region.y+int(region.height*.2)
    ev('MOUSEMOVE', 'NOTHING', x=C['point'][0], y=C['point'][1])


@step
def exit_mode():
    with viewport():
        node().record.dismissed = False
        target, layout = mod('ui.in_view_editor').current_layout(bpy.context, fresh=True)
        check('Bevel editor is present before exiting component mode', target is not None and layout is not None)
        C['fraction'] = target.params['fraction']
    tap('F8')


@step
def object_mode():
    with viewport():
        check('F8 returns to Object Mode', bpy.context.mode == 'OBJECT')
        check('the old Edit Mode editor closes', mod('ui.in_view_editor').current_layout(bpy.context) == (None, None))
        check('the Bevel history and value survive exiting', node() is not None and node().params['fraction'] == C['fraction'])
    x, y = C['point']
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def clicked():
    check('viewport drawing and a normal click raise no errors after exiting', not C['errors'])
    with viewport():
        ob = bpy.data.objects[C['object']]
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
    tap('T')


@step
def reopened():
    with viewport():
        target, layout = mod('ui.in_view_editor').current_layout(bpy.context, fresh=True)
        check('T reopens the Bevel node in Object Mode', target is not None and layout is not None)
        mod('ui.in_view_editor').select(bpy.context, target, 'fraction')
    x, y = C['point']
    ev('MIDDLEMOUSE', 'PRESS', x=x, y=y)


for i in range(1, 4):
    def move(i=i):
        x, y = C['point']
        ev('MOUSEMOVE', 'NOTHING', x=x+5*i, y=y)
    step(move)


@step
def release():
    x, y = C['point']
    ev('MIDDLEMOUSE', 'RELEASE', x=x+15, y=y)


@step
def object_edit():
    with viewport():
        check('the reopened node accepts a viewport MMB drag', node().params['fraction'] > C['fraction'])
        check('Object Mode is restored after the node rebuild', bpy.context.mode == 'OBJECT')
    tap('W')


@step
def tool_exit():
    with viewport():
        check('W exits the reopened node editor', mod('ui.in_view_editor').current_layout(bpy.context) == (None, None))
    check('all exit and reopen events finish without a Python error', not C['errors'])


run()
