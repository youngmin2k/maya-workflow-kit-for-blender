"""Modeless Options share numeric gestures and execute in their originating editor."""
import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, tap, view3d, win

C = {}


def mod(name):
    return import_module(MODULE+'.'+name)


def main_context():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def options(key='poly_cube'):
    return mod('ui.option_editor').find(bpy.context, key)


def option_context(key='poly_cube'):
    window = options(key)
    area = window.screen.areas[0]
    region = next(r for r in area.regions if r.type == 'WINDOW')
    return bpy.context.temp_override(window=window, area=area, region=region)


def event(type, value, **kw):
    x, y = C['point']
    options().event_simulate(type=type, value=value, x=x, y=y, **kw)


@step
def start():
    setup()
    check('unused Options schemas are not allocated at startup', not mod('ui.option_editor')._groups)
    with main_context():
        C['objects'] = len(bpy.context.scene.objects)
        mod('undo_steps').push('Before modeless options')
        check('Cube options opens without starting a modal command',
              bpy.ops.allset.opt_poly_cube('INVOKE_DEFAULT') == {'FINISHED'})


for _i in range(8):
    step(lambda: None)


@step
def ready():
    check('Cube Options has its own window', options() is not None and options() != win())
    check('opening options creates no geometry', len(bpy.context.scene.objects) == C['objects'])
    check('opening Cube allocates only its own option schema', set(mod('ui.option_editor')._groups) == {'poly_cube'})
    with main_context():
        bpy.ops.allset.opt_poly_cube('INVOKE_DEFAULT')
    check('reopening the same options reuses its window', len(bpy.context.window_manager.windows) == 2)
    area = options().screen.areas[0]
    region = next(r for r in area.regions if r.type == 'WINDOW')
    C['scan'] = region.x+int(region.width*.75), region.y+region.height-20


def find_width():
    entry = mod('ui.attribute_fields')._hover.get(options().as_pointer())
    if entry is not None and entry[0].path.endswith('allset_options_poly_cube.width'):
        C['point'] = entry[3], entry[4]
        C['owner'] = mod('ui.option_editor').owner(bpy.context.window_manager, 'poly_cube')
        check('the real Width field is recognized in the modeless editor', True)
        shots = os.environ.get('ALLSET_GUI_SHOTS')
        if shots:
            with option_context():
                bpy.ops.screen.screenshot(filepath=os.path.join(shots, 'modeless_cube_options.png'))
        return
    x, y = C['scan']
    C['scan'] = x, y-8
    if y < 10:
        raise AssertionError('Width field not found in the modeless Options editor')
    options().event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
    import sim
    sim._steps.insert(0, find_width)


step(find_width)


def gesture(button, tag):
    @step
    def hover():
        C[tag] = C['owner'].width
        event('MOUSEMOVE', 'NOTHING')
    @step
    def press():
        event(button, 'PRESS', ctrl=True)
    for i in range(1, 5):
        def move(i=i):
            x, y = C['point']
            options().event_simulate(type='MOUSEMOVE', value='NOTHING', x=x+10*i, y=y, ctrl=True)
        step(move)
    @step
    def release():
        x, y = C['point']
        options().event_simulate(type=button, value='RELEASE', x=x+40, y=y, ctrl=True)
    @step
    def result():
        C[tag+'_delta'] = C['owner'].width-C[tag]
        check(f'{button} with Ctrl changes the Options numeric field', C[tag+'_delta'] > 0)


gesture('LEFTMOUSE', 'fine')
gesture('MIDDLEMOUSE', 'normal')
gesture('RIGHTMOUSE', 'coarse')


@step
def apply():
    check('MMB has ten times the fine LMB sensitivity', abs(C['normal_delta']/C['fine_delta']-10) < .1)
    check('RMB has ten times the normal MMB sensitivity', abs(C['coarse_delta']/C['normal_delta']-10) < .1)
    with option_context():
        check('Apply succeeds in the source viewport', bpy.ops.allset.option_editor_action(action='APPLY') == {'FINISHED'})
    check('Apply creates one cube and keeps the Options editor',
          len(bpy.context.scene.objects) == C['objects']+1 and options() is not None)
    area, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x+region.width//2, y=region.y+region.height//2)


@step
def undo():
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def undone():
    check('one Undo removes the applied cube', len(bpy.context.scene.objects) == C['objects'])
    ev('Z', 'PRESS', ctrl=True, shift=True)
    ev('Z', 'RELEASE', ctrl=True, shift=True)


@step
def redone():
    check('Redo restores the applied cube', len(bpy.context.scene.objects) == C['objects']+1)
    tap('G')


@step
def repeated():
    check('G repeats Cube after Options and field gestures', len(bpy.context.scene.objects) == C['objects']+2)
    with option_context():
        bpy.ops.allset.option_editor_action(action='RESET')
    C['owner'] = mod('ui.option_editor').owner(bpy.context.window_manager, 'poly_cube')
    check('Reset Settings restores the schema defaults', C['owner'].width == 1)
    C['owner'].width = 2.3
    with option_context():
        bpy.ops.allset.option_editor_action(action='SAVE')
    check('Save Settings uses the existing option store',
          abs(mod('operators.option_windows').saved('poly_cube')['width']-2.3) < 1e-5)
    with main_context():
        bpy.ops.allset.opt_bevel('INVOKE_DEFAULT')


for _i in range(8):
    step(lambda: None)


@step
def two_windows():
    check('different command options can stay open together', options('bevel') is not None and options() is not None)
    for key in ('bevel', 'poly_cube'):
        with option_context(key):
            bpy.ops.allset.option_editor_action(action='CLOSE')


@step
def closed():
    check('Close releases both option sessions and preserves the main window',
          len(bpy.context.window_manager.windows) == 1 and not mod('ui.option_editor')._sessions)


run()
