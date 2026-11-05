"""Converted Alt LMB must tumble instead of editing the armed node attribute."""
import sys
from pathlib import Path
from importlib import import_module
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sim
from sim import MODULE, setup, step, run, check, ev, view3d, win

C = {}
def mod(name):
    return import_module(MODULE+'.'+name)
def viewport():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)

@step
def start():
    setup()
    bpy.context.preferences.inputs.use_mouse_emulate_3_button=True
    bpy.context.preferences.inputs.mouse_emulate_3_button_modifier='ALT'
    with viewport():
        bpy.ops.wm.tool_set_by_id(name='builtin.move')

@step
def bevel():
    with viewport():
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.wm.tool_set_by_id(name='builtin.move')
        bpy.context.scene.tool_settings.mesh_select_mode=(False,True,False)
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.allset.bevel('EXEC_DEFAULT',True,fraction=.25)
    area, region = view3d()
    C['point']=region.x+int(region.width*.15),region.y+int(region.height*.2)
    ev('MOUSEMOVE','NOTHING',x=C['point'][0],y=C['point'][1])

@step
def prepare():
    with viewport():
        node=mod('ui.node_attributes').target(bpy.context)
        node.record.dismissed=False
        mod('ui.in_view_editor').select(bpy.context,node,'fraction')
        C['fraction']=node.params['fraction']
        C['rotation']=bpy.context.region_data.view_rotation.copy()
    sim._down.add('LEFT_ALT')
    x,y=C['point']
    ev('MIDDLEMOUSE','PRESS',x=x,y=y)

for i in range(1,5):
    def move(i=i):
        x,y=C['point']
        ev('MOUSEMOVE','NOTHING',x=x+20*i,y=y+5*i)
    step(move)

@step
def release():
    x,y=C['point']
    ev('MIDDLEMOUSE','RELEASE',x=x+80,y=y+20)
    sim._down.discard('LEFT_ALT')

@step
def result():
    with viewport():
        node=mod('ui.node_attributes').target(bpy.context)
        changed=C['rotation'].rotation_difference(bpy.context.region_data.view_rotation).angle
        check(f'emulated Alt LMB tumbles with an active In-View Editor, angle {changed}',changed>.02)
        check(f"navigation preserves Fraction, before {C['fraction']}, after {node.params['fraction']}",
              node.params['fraction']==C['fraction'])

run()
