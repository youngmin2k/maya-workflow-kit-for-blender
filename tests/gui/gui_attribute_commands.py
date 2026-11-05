"""Shared gestures, single-Enter entry, cancel and Undo through each modeling entry point."""
from importlib import import_module
from pathlib import Path
import sys
import math

import bpy
import bmesh

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sim import MODULE, check, ev, run, setup, step, tap, view3d, win

C = {}


def mod(name):
    return import_module(MODULE+'.'+name)


def viewport():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def current():
    return mod('ui.node_attributes').target(bpy.context)


def point(field=None, value=False):
    _area, region = view3d()
    if field is None:
        return region.x+region.width//5, region.y+region.height//5
    with viewport():
        _node, layout = mod('ui.in_view_editor').current_layout(bpy.context, fresh=True)
    row = next(row for row in layout['rows'] if row[0] == field)
    return region.x+round(row[1]+(row[3]-row[1])*(.8 if value else .1)), region.y+round((row[2]+row[4])/2)


def type_text(text):
    ev('A', 'PRESS', ctrl=True)
    ev('A', 'RELEASE', ctrl=True)
    for character in text:
        ev('TEXTINPUT', 'PRESS', unicode=character)
    tap('RET')


def fixture(kind):
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    mod('operators.extrude').clear()
    mod('ui.in_view_editor').clear()
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    if kind == 'PRIMITIVE':
        bpy.ops.allset.create('EXEC_DEFAULT', True, kind='CUBE')
    elif kind == 'BRIDGE':
        from test_bridge_paths import caps
        bm = caps()
        mesh = bpy.data.meshes.new('attribute_bridge')
        bm.to_mesh(mesh)
        bm.free()
        ob = bpy.data.objects.new('attribute_bridge', mesh)
        bpy.context.scene.collection.objects.link(ob)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.context.scene.tool_settings.mesh_select_mode = (False, False, True)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.allset.bridge('EXEC_DEFAULT', True, curve_type=1, divisions=3)
    else:
        bpy.ops.mesh.primitive_cube_add()
        mode = {'FACE': (False, False, True), 'EDGE': (False, True, False),
                'VERTEX': (True, False, False), 'SUBDIVIDE': (False, False, True)}[kind]
        bpy.context.scene.tool_settings.mesh_select_mode = mode
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(bpy.context.object.data)
        mod('operators.extrude').deselect_all(bm)
        if kind in {'FACE', 'SUBDIVIDE'}:
            face = max(bm.faces, key=lambda face: face.normal.z)
            face.select_set(True)
        elif kind == 'EDGE':
            next(iter(bm.edges)).select_set(True)
        else:
            next(iter(bm.verts)).select_set(True)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(bpy.context.object.data)
        operator = bpy.ops.allset.subdivide if kind == 'SUBDIVIDE' else bpy.ops.allset.extrude
        assert operator('EXEC_DEFAULT', True) == {'FINISHED'}
    bpy.ops.wm.tool_set_by_id(name='builtin.move')
    bpy.context.region_data.view_location = (0, 0, 2 if kind == 'BRIDGE' else 0)
    bpy.context.region_data.view_distance = 12
    bpy.context.region_data.view_perspective = 'ORTHO'
    assert mod('ui.in_view_editor').show(bpy.context)


@step
def start():
    setup()
    bpy.context.preferences.view.smooth_view = 0
    bpy.context.scene.unit_settings.system = 'NONE'
    prefs = mod('preferences').get()
    prefs.cb_speed, prefs.cb_hyperbolic = 'MEDIUM', False


def scenario(kind, field):
    @step
    def prepare():
        with viewport():
            fixture(kind)
            if kind == 'BRIDGE':
                for curve_type in (0, 1):
                    result = bpy.ops.allset.inview_setting(action='VALUE', field='curve_type', value=curve_type)
                    check('BRIDGE menu retains the integer type '+str(curve_type),
                          result == {'FINISHED'} and type(current().params['curve_type']) is int)
                    result = bpy.ops.allset.bridge_edit('INVOKE_DEFAULT')
                    check('BRIDGE native editing works after menu choice '+str(curve_type),
                          result == {'FINISHED'} and current().params['curve_type'] == curve_type)
            node = current()
            mod('ui.in_view_editor').select(bpy.context, node, field)
            C['before'] = dict(node.params)
            C['integer'] = node.spec.kinds[field] == 'INT'
        x, y = point()
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)

    @step
    def select_row():
        x, y = point(field)
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
        ev('LEFTMOUSE', 'PRESS', x=x, y=y)
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y)

    @step
    def press_drag():
        C['drag'] = point()
        x, y = C['drag']
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
        ev('MIDDLEMOUSE', 'PRESS', x=x, y=y)

    for index in range(1, 5):
        def move(index=index):
            x, y = C['drag']
            ev('MOUSEMOVE', 'NOTHING', x=x+10*index, y=y)
        step(move)

    @step
    def release_drag():
        x, y = C['drag']
        ev('MIDDLEMOUSE', 'RELEASE', x=x+40, y=y)

    @step
    def check_drag():
        with viewport():
            node = current()
            C['dragged'] = node.params[field]
            check(kind+' MMB adjusts the selected attribute outside its row', C['dragged'] > C['before'][field])
            check(kind+' preserves the other attributes', all(node.params[name] == value
                  for name, value in C['before'].items() if name != field))
            if C['integer']:
                check(kind+' integer drag remains an integer', isinstance(C['dragged'], int))
        x, y = C['drag']
        ev('MIDDLEMOUSE', 'PRESS', x=x, y=y)

    @step
    def cancel_move():
        x, y = C['drag']
        ev('MOUSEMOVE', 'NOTHING', x=x+40, y=y)

    @step
    def cancel_drag():
        tap('ESC')
        x, y = C['drag']
        ev('MIDDLEMOUSE', 'RELEASE', x=x+40, y=y)

    @step
    def check_cancel():
        with viewport():
            check(kind+' Esc restores the complete preview', current().params[field] == C['dragged'])
        ev('Z', 'PRESS', ctrl=True)
        ev('Z', 'RELEASE', ctrl=True)

    @step
    def check_undo():
        with viewport():
            check(kind+' one Undo restores the drag', current().params[field] == C['before'][field])
        ev('Z', 'PRESS', ctrl=True, shift=True)
        ev('Z', 'RELEASE', ctrl=True, shift=True)

    @step
    def cycle():
        with viewport():
            check(kind+' Redo restores the drag', current().params[field] == C['dragged'])
            mod('ui.in_view_editor').select(bpy.context, current(), field)
            C['active'] = mod('ui.in_view_editor').state(bpy.context, current())['field']

    @step
    def cycle_key():
        ev('TAB', 'PRESS', ctrl=True)
        ev('TAB', 'RELEASE', ctrl=True)

    @step
    def reverse_cycle():
        with viewport():
            editor = mod('ui.in_view_editor')
            check(kind+' Ctrl Tab cycles the active attribute', editor.state(bpy.context, current())['field'] != C['active'])
        ev('TAB', 'PRESS', ctrl=True, shift=True)
        ev('TAB', 'RELEASE', ctrl=True, shift=True)

    @step
    def type_field():
        with viewport():
            editor = mod('ui.in_view_editor')
            check(kind+' Ctrl Shift Tab reverses the cycle', editor.state(bpy.context, current())['field'] == C['active'])
            editor.select(bpy.context, current(), field)
        x, y = point(field, value=True)
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
        ev('LEFTMOUSE', 'PRESS', x=x, y=y)
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y)

    @step
    def enter_value():
        type_text('+=1' if C['integer'] else '+=0.25')

    @step
    def check_entry():
        with viewport():
            expected = C['dragged']+(1 if C['integer'] else .25)
            check(kind+' relative entry applies with one Enter', math.isclose(current().params[field], expected, abs_tol=1e-5))
            C['typed'] = current().params[field]
        ev('Z', 'PRESS', ctrl=True)
        ev('Z', 'RELEASE', ctrl=True)

    @step
    def undo_entry():
        with viewport():
            check(kind+' one Undo restores numeric entry', current().params[field] == C['dragged'])
        ev('Z', 'PRESS', ctrl=True, shift=True)
        ev('Z', 'RELEASE', ctrl=True, shift=True)

    @step
    def redo_entry():
        with viewport():
            check(kind+' Redo restores numeric entry', current().params[field] == C['typed'])
            editor = mod('ui.in_view_editor')
            editor.show(bpy.context)
            editor.select(bpy.context, current(), field)
            bpy.ops.allset.inview_number('INVOKE_DEFAULT', field=field)

    @step
    def cancel_typed_value():
        ev('A', 'PRESS', ctrl=True)
        ev('A', 'RELEASE', ctrl=True)
        ev('TEXTINPUT', 'PRESS', unicode='9')
        tap('ESC')

    @step
    def check_typed_cancel():
        with viewport():
            check(kind+' Esc cancels numeric entry', current().params[field] == C['typed'])
            node = current()
            cb = mod('ui.channel_box')
            key = cb.model_key(node.record, field) if hasattr(node, 'record') else cb.HISTORY_PREFIX+field
            cb.set_locked(node.ob, key, True)
            check(kind+' locked attributes reject numeric entry',
                  bpy.ops.allset.inview_number('INVOKE_DEFAULT', field=field) == {'CANCELLED'})
            cb.set_locked(node.ob, key, False)
            switch_mode = bpy.context.mode != 'OBJECT'
        if switch_mode:
            tap('F8')

    @step
    def show_object_mode():
        x, y = point()
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
        tap('T')

    @step
    def check_object_mode():
        with viewport():
            node, layout = mod('ui.in_view_editor').current_layout(bpy.context, fresh=True)
            check(kind+' T reopens the node in Object Mode', node is not None and layout is not None)
            result = bpy.ops.allset.inview_number('INVOKE_DEFAULT', field=field)
            check(kind+' Object Mode opens the numeric field', result in ({'FINISHED'}, {'INTERFACE'}, {'RUNNING_MODAL'}))

    @step
    def enter_object_value():
        type_text('+=1' if C['integer'] else '+=0.25')

    @step
    def check_object_entry():
        with viewport():
            expected = C['dragged']+(2 if C['integer'] else .5)
            check(kind+' Object Mode entry applies and keeps Object Mode', bpy.context.mode == 'OBJECT'
                  and math.isclose(current().params[field], expected, abs_tol=1e-5))
            C['object_typed'] = current().params[field]
        ev('Z', 'PRESS', ctrl=True)
        ev('Z', 'RELEASE', ctrl=True)

    @step
    def undo_object_entry():
        with viewport():
            check(kind+' one Undo restores Object Mode numeric entry', bpy.context.mode == 'OBJECT'
                  and current().params[field] == C['typed'])
        ev('Z', 'PRESS', ctrl=True, shift=True)
        ev('Z', 'RELEASE', ctrl=True, shift=True)

    @step
    def redo_object_entry():
        with viewport():
            check(kind+' Redo restores Object Mode numeric entry', bpy.context.mode == 'OBJECT'
                  and current().params[field] == C['object_typed'])


for kind, field in (('FACE', 'thickness'), ('EDGE', 'thickness'), ('VERTEX', 'width'),
                    ('BRIDGE', 'taper'), ('SUBDIVIDE', 'divisions'), ('PRIMITIVE', 'width')):
    scenario(kind, field)

GUI_TIMEOUT = 300
run()
