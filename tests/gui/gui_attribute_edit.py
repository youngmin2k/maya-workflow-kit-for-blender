"""Real pointer events select an attribute and drive it outside the In-View Editor."""
import os
import sys
from importlib import import_module

import bpy
import bmesh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, view3d, win, tap

C = {}


def mod(name):
    return import_module(MODULE+'.'+name)


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def node():
    return mod('ui.node_attributes').target(bpy.context)


def point(field=None):
    area, region = view3d()
    if field is None:
        return region.x+int(region.width*.2), region.y+int(region.height*.2)
    with override():
        _node, lay = mod('ui.in_view_editor').current_layout(bpy.context)
    row = next(r for r in lay['rows'] if r[0] == field)
    return region.x+round(row[1]+12), region.y+round((row[2]+row[4])*.5)


def pick(field, tag):
    @step
    def hover():
        C[tag] = point(field)
        ev('MOUSEMOVE', 'NOTHING', x=C[tag][0], y=C[tag][1])
    @step
    def click():
        x, y = C[tag]
        ev('LEFTMOUSE', 'PRESS', x=x, y=y)
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y)
    @step
    def away():
        x, y = point()
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


def drag(dx, tag, cancel=False, ctrl=False):
    @step
    def begin():
        C[tag] = point()
        ev('MIDDLEMOUSE', 'PRESS', x=C[tag][0], y=C[tag][1], ctrl=ctrl)
    for i in range(1, 5):
        def move(i=i):
            x, y = C[tag]
            ev('MOUSEMOVE', 'NOTHING', x=x+round(dx*i/4), y=y, ctrl=ctrl)
        step(move)
    @step
    def end():
        x, y = C[tag]
        if cancel:
            tap('ESC')
        ev('MIDDLEMOUSE', 'RELEASE', x=x+dx, y=y, ctrl=ctrl)


@step
def start():
    setup()
    with override():
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.context.scene.tool_settings.mesh_select_mode = (False, True, False)
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.allset.bevel('EXEC_DEFAULT', True)
    C['scale'] = bpy.context.preferences.system.ui_scale


pick('fraction', 'fraction')

@step
def selected():
    with override():
        current = mod('ui.in_view_editor').state(bpy.context, node())
        check('attribute remains active after pointer leaves the row', current['field'] == 'fraction')


drag(20, 'fraction_drag')

@step
def fraction_changed():
    expected = .5+.2/C['scale']
    check(f"MMB outside the editor changes Fraction ({node().params['fraction']}, expected {expected})",
          abs(node().params['fraction']-expected)<.025)
    C['fraction_value'] = node().params['fraction']


pick('segments', 'segments')
drag(40, 'segments_drag')

@step
def segments_changed():
    check(f"MMB changes Segments in integer steps ({node().params['segments']})", node().params['segments'] >= 2)
    check('changing Segments preserves Fraction', node().params['fraction'] == C['fraction_value'])
    C['segments_value'] = node().params['segments']


drag(40, 'cancel_drag', cancel=True)

@step
def cancelled():
    check('Esc restores the integer attribute before the drag', node().params['segments'] == C['segments_value'])
    with override():
        cb = mod('ui.channel_box')
        cb.select_channel(cb.model_key(node().record, 'depth'), context=bpy.context)


drag(-20, 'channel_drag')

@step
def channel_result():
    check('Channel Box history selection owns the next MMB drag', node().params['depth'] < 1)
    check('history slider leaves other parameters intact', node().params['segments'] == C['segments_value'])
    C['depth_value'] = node().params['depth']


@step
def undo_channel_drag():
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def undone():
    check(f"one Undo restores the whole Channel Box drag ({node().params['depth']})", node().params['depth'] == 1)
    check('Undo preserves the previous Segments edit', node().params['segments'] == C['segments_value'])
    ev('Z', 'PRESS', ctrl=True, shift=True)
    ev('Z', 'RELEASE', ctrl=True, shift=True)


@step
def redone():
    check('Redo restores the final drag value', node().params['depth'] == C['depth_value'])


run()
