"""Real numeric entry, AE gestures and grouped history typing with Undo/Redo."""
import sys
from pathlib import Path
from importlib import import_module
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sim import MODULE, setup, step, run, check, ev, tap, view3d, win, dock_area, dock_region, find_button, open_inputs, scroll_channel_box

C = {}
def mod(name):
    return import_module(MODULE+'.'+name)
def viewport():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)
def dock():
    return dock_area(), dock_region()
def text(value):
    ev('A','PRESS',ctrl=True)
    ev('A','RELEASE',ctrl=True)
    for char in value:
        ev('TEXTINPUT','PRESS',unicode=char)
    tap('RET')

@step
def start():
    setup()
    with viewport():
        scene=bpy.context.scene
        scene.unit_settings.system='METRIC'
        scene.unit_settings.length_unit='CENTIMETERS'
        scene.unit_settings.scale_length=1
        bpy.ops.object.select_all(action='DESELECT')
        ob=mod('operators.prim_history').create_object(bpy.context,'CUBE')
        ob.select_set(True)
        bpy.context.view_layer.objects.active=ob
        C['primitive']=ob.name
    tap('T')

@step
def width():
    with viewport():
        node,layout=mod('ui.in_view_editor').current_layout(bpy.context)
        row=next(row for row in layout['rows'] if row[0]=='width')
    area, region = view3d()
    C['width_point']=(region.x+round(row[1]+(row[3]-row[1])*.8),region.y+round((row[2]+row[4])/2))
    ev('MOUSEMOVE','NOTHING',x=C['width_point'][0],y=C['width_point'][1])

@step
def click_width():
    x,y=C['width_point']
    ev('LEFTMOUSE','PRESS',x=x,y=y)
    ev('LEFTMOUSE','RELEASE',x=x,y=y)

@step
def type_width(): text('5')

@step
def width_result():
    with viewport():
        node=mod('ui.node_attributes').target(bpy.context)
        check(f"typed Width 5 cm should retain Maya width 5, actual {node.params['width']}",abs(node.params['width']-5)<1e-5)
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.mesh.primitive_cube_add()
        C['ae_object']=bpy.context.object.name
        C['location']=bpy.context.object.location.x
        bpy.context.scene.unit_settings.system='NONE'
    dock_area('ATTRIBUTE_EDITOR')
    bpy.ops.allset.ae_tab(key='T')

step(find_button(dock,lambda path,command:path.endswith('allset_cb.tx_text'),C,'ae_field',x_frac=.45,step_px=8))

@step
def hover_ae():
    check('AE Translate X field is found',C.get('ae_field') is not None)
    x,y=C['ae_field']
    ev('MOUSEMOVE','NOTHING',x=x,y=y)

@step
def press_ae():
    check('AE Transform field is recognized by shared numeric handler',bool(mod('ui.attribute_fields')._hover.get(win().as_pointer())))
    x,y=C['ae_field']
    ev('MIDDLEMOUSE','PRESS',x=x,y=y,ctrl=True)

for i in range(1,5):
    def move(i=i):
        x,y=C['ae_field']
        ev('MOUSEMOVE','NOTHING',x=x+10*i,y=y,ctrl=True)
    step(move)

@step
def release_ae():
    x,y=C['ae_field']
    ev('MIDDLEMOUSE','RELEASE',x=x+40,y=y,ctrl=True)

@step
def ae_result():
    value=bpy.data.objects[C['ae_object']].location.x
    check(f'Ctrl MMB changes AE Translate X, actual {value}',value!=C['location'])
    with viewport():
        first=bpy.context.object
        bpy.ops.mesh.primitive_cube_add(location=(3,0,0))
        first.select_set(True)
        C['model_objects']=[first.name,bpy.context.object.name]
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.context.scene.tool_settings.mesh_select_mode=(False,False,True)
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.allset.extrude('EXEC_DEFAULT',True)
        node=mod('ui.node_attributes').target(bpy.context)
        C['history_name']=node.name
        cb=mod('ui.channel_box')
        C['selected']=[cb.model_key(node.record,'thickness'),cb.model_key(node.record,'offset')]
        cb.set_selected_channels(C['selected'])
    dock_area('CHANNEL_BOX')
    open_inputs(C['history_name'])
    scroll_channel_box()

step(find_button(dock,lambda path,command:path.endswith('allset_history.thickness_text'),C,'model_field',x_frac=.8,step_px=8))

@step
def click_model():
    check('Thickness history value field is found',C.get('model_field') is not None)
    x,y=C['model_field']
    ev('MOUSEMOVE','NOTHING',x=x,y=y)

@step
def press_model():
    x,y=C['model_field']
    ev('LEFTMOUSE','PRESS',x=x,y=y)
    ev('LEFTMOUSE','RELEASE',x=x,y=y)

@step
def type_model(): text('0.2')

@step
def model_result():
    with viewport():
        node=mod('ui.node_attributes').target(bpy.context)
        selected=mod('ui.channel_box').selected_channels()
        check('the two modeling channels remain selected during typing',selected==C['selected'])
        check(f"typing 0.2 updates both selected channels, actual {node.params['thickness']}, {node.params['offset']}",
              abs(node.params['thickness']-.2)<1e-5 and abs(node.params['offset']-.2)<1e-5)
        check('typing finishes the modeling preview', not node.record.live)
        records=[mod('ui.node_attributes').target(bpy.context,bpy.data.objects[name]) for name in C['model_objects']]
        check('typing updates compatible selected objects together',all(abs(n.params['thickness']-.2)<1e-5
              and abs(n.params['offset']-.2)<1e-5 for n in records))
    area, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x+region.width//4, y=region.y+region.height//3)


@step
def undo_model():
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def check_undo_model():
    with viewport():
        node=mod('ui.node_attributes').target(bpy.context)
        check('one Undo restores both typed modeling channels', node is not None
              and abs(node.params['thickness'])<1e-5 and abs(node.params['offset'])<1e-5)
    ev('Z', 'PRESS', ctrl=True, shift=True)
    ev('Z', 'RELEASE', ctrl=True, shift=True)


@step
def check_redo_model():
    with viewport():
        node=mod('ui.node_attributes').target(bpy.context)
        check('one Redo restores both typed modeling channels', node is not None
              and abs(node.params['thickness']-.2)<1e-5 and abs(node.params['offset']-.2)<1e-5)

run()
