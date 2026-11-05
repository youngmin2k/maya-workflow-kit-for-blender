"""T exposes creation attributes; actual Ctrl+MMB in the Attribute Editor adjusts a camera field."""
import os
import sys
from importlib import import_module
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, view3d, win, tap, dock_area, dock_region, find_button

C = {}


def mod(name):
    return import_module(MODULE+'.'+name)


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


@step
def start():
    setup()
    with override():
        bpy.ops.object.select_all(action='DESELECT')
        ob = mod('operators.prim_history').create_object(bpy.context, 'CUBE')
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)
        C['cube'] = ob.name
    area, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x+int(region.width*.3), y=region.y+int(region.height*.3))


@step
def show_editor():
    tap('T')


@step
def creation_editor():
    with override():
        editor = mod('ui.in_view_editor')
        node, lay = editor.current_layout(bpy.context)
        check('T opens the primitive creation editor', node is not None and node.spec.node_type == 'polyCube')
        check('the primitive editor contains Width and subdivisions',
              {'width', 'subdivisionsWidth'} <= {row[0] for row in lay['rows']})
        C['original'] = editor.fields(bpy.context, node)
        bpy.ops.allset.inview_setting(action='TOGGLE', field='width')
        check('displayed attributes can be hidden', 'width' not in editor.fields(bpy.context, node))
        bpy.ops.allset.inview_setting(action='RESET')
        check('reset restores the default attribute list', editor.fields(bpy.context, node) == C['original'])
        check('the context attribute menu resolves for the node', editor.attribute_menu(bpy.context))


@step
def grip():
    with override():
        _node, lay = mod('ui.in_view_editor').current_layout(bpy.context)
        C['box'] = lay['box']
    _area, region = view3d()
    C['grip'] = region.x+round(lay['box'][2]-3), region.y+round(lay['box'][1]+3)
    x, y = C['grip']
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def grip_press():
    x, y = C['grip']
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


@step
def grip_move():
    x, y = C['grip']
    ev('MOUSEMOVE', 'NOTHING', x=x+40, y=y+32)


@step
def grip_preview():
    with override():
        _node, lay = mod('ui.in_view_editor').current_layout(bpy.context)
        check('resize changes the width during the drag', lay['box'][2]-lay['box'][0] > C['box'][2]-C['box'][0])
        check('resize changes the visible row count during the drag', len(lay['rows']) < len(C['original']))
    x, y = C['grip']
    ev('LEFTMOUSE', 'RELEASE', x=x+40, y=y+32)


@step
def layout_saved():
    editor = mod('ui.in_view_editor')
    with override():
        node = mod('ui.node_attributes').target(bpy.context)
        saved = editor.settings(bpy.context, node)
        check('resized dimensions are saved in the kit user folder',
              editor.layout_file().is_file() and saved.get('width', 0) > 180 and saved.get('height') is not None)
        import json
        stored = json.loads(editor.layout_file().read_text())
        check('saved settings match the active primitive editor', stored['polyCube'] == saved)
        bpy.ops.allset.inview_setting(action='RESET')


@step
def camera():
    with override():
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.object.camera_add()
        C['camera'] = bpy.context.object.name
        C['lens'] = bpy.context.object.data.lens
        mod('undo_steps').push('Camera before field gesture')
    dock_area('ATTRIBUTE_EDITOR')
    bpy.ops.allset.ae_tab(key='S')


@step
def redraw_camera():
    for area in win().screen.areas:
        area.tag_redraw()


step(find_button(lambda: (dock_area(), dock_region()), lambda path, command: path.endswith('lens'),
                 C, 'field', x_frac=.75, step_px=8))


@step
def hover_field():
    check('camera Focal Length field is visible in the Attribute Editor', C.get('field') is not None)
    x, y = C['field']
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def press_field():
    check('the numeric field is recognized by the shared field handler',
          bool(mod('ui.attribute_fields')._hover))
    x, y = C['field']
    ev('MIDDLEMOUSE', 'PRESS', x=x, y=y, ctrl=True)


for i in range(1, 5):
    def move(i=i):
        x, y = C['field']
        ev('MOUSEMOVE', 'NOTHING', x=x+10*i, y=y, ctrl=True)
    step(move)


@step
def release_field():
    x, y = C['field']
    ev('MIDDLEMOUSE', 'RELEASE', x=x+40, y=y, ctrl=True)


@step
def field_changed():
    lens = bpy.data.objects[C['camera']].data.lens
    check('Ctrl+MMB on a native Attribute Editor field changes its value', lens > C['lens'])
    C['lens_after'] = lens
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def field_undo():
    check('one Undo restores the native numeric field', bpy.data.objects[C['camera']].data.lens == C['lens'])
    ev('Z', 'PRESS', ctrl=True, shift=True)
    ev('Z', 'RELEASE', ctrl=True, shift=True)


@step
def field_redo():
    check('Redo restores the native numeric field', bpy.data.objects[C['camera']].data.lens == C['lens_after'])
    area, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x+region.width//2, y=region.y+region.height//2)


run()
