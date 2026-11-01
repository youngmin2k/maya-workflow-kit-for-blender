"""Actual G events after display/mode changes and mode-specific foreign G bindings."""
import os
import sys
from importlib import import_module

import bpy
import bmesh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, tap, view3d, win

rep = import_module(MODULE + '.operators.repeat_maya')
modal = import_module(MODULE + '.marking.modal')
keymap = import_module(MODULE + '.keymap')
C = {'foreign_calls': 0}


class REPEAT_MT_foreign(bpy.types.Menu):
    bl_label = 'Foreign G menu'

    def draw(self, context):
        C['foreign_calls'] += 1
        self.layout.label(text='Foreign G binding')


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def hover():
    area, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)


def count():
    return sum(ob.type == 'MESH' for ob in bpy.context.scene.objects)


@step
def prepare():
    setup()
    with override():
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.allset.menu_item(item='Create/Polygon Primitives/Cube', clicked=True)
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    hover()
    tap('FIVE')


@step
def repeat_after_display():
    check('5 keeps Cube as the command to repeat', rep.label(bpy.context) == 'Repeat "Cube"')
    tap('G')


@step
def display_result():
    check('G after display change creates the next cube', count() == 2)
    with override():
        modal.run_action(bpy.context, ('allset.component_mode', {'type': 'FACE'}))
        modal.run_action(bpy.context, ('object.mode_set', {'mode': 'OBJECT'}))
        modal.run_action(bpy.context, ('item', 'Select/All'))
    C['before_modes'] = count()
    hover()


@step
def repeat_after_modes():
    check('component marking-menu and selection changes keep Cube', rep.label(bpy.context) == 'Repeat "Cube"')
    tap('G')


@step
def modes_result():
    check('G after component menus still repeats the modeling command', count() == C['before_modes'] + 1)
    tap('ESC')
    bpy.utils.register_class(REPEAT_MT_foreign)
    C['foreign'] = []
    kc = bpy.context.window_manager.keyconfigs.addon
    for name in ('3D View', 'Object Mode', 'Mesh'):
        km = kc.keymaps.new(name, space_type='VIEW_3D' if name == '3D View' else 'EMPTY', region_type='WINDOW')
        item = km.keymap_items.new('wm.call_menu', 'G', 'PRESS')
        item.properties.name = 'REPEAT_MT_foreign'
        C['foreign'].append((km, item))


@step
def wait_for_priority():
    keymap.keep_first_now()
    C['before_foreign'] = count()
    hover()


@step
def foreign_press():
    tap('G')


@step
def foreign_result():
    check('Object G reaches Repeat ahead of foreign G menus', count() == C['before_foreign'] + 1 and C['foreign_calls'] == 0)
    tap('ESC')
    with override():
        # In Edit Mesh, a repeated extrusion changes the new face selection.
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.allset.extrude('EXEC_DEFAULT', True)
    C['verts'] = len(bmesh.from_edit_mesh(bpy.context.edit_object.data).verts)
    hover()


@step
def mesh_press():
    tap('G')


@step
def mesh_result():
    verts = len(bmesh.from_edit_mesh(bpy.context.edit_object.data).verts)
    check('Edit Mesh G repeats Extrude ahead of foreign menus', verts > C['verts'] and C['foreign_calls'] == 0)
    tap('ESC')
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')
        import_module(MODULE + '.switch').set_mode(False, layout=False)
    hover()


@step
def off_press():
    tap('G')


@step
def off_result():
    check('Maya mode off restores foreign G bindings', C['foreign_calls'] > 0)
    tap('ESC')
    for km, item in C['foreign']:
        km.keymap_items.remove(item)
    bpy.utils.unregister_class(REPEAT_MT_foreign)


run()
