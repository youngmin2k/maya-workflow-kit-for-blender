"""Verify modeless option windows remain usable when saved UI is reloaded."""
import sys
import os
from pathlib import Path
from importlib import import_module
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sim import MODULE, setup, step, run, check, view3d, win

def mod(name):
    return import_module(MODULE+'.'+name)
def viewport():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)

@step
def start():
    setup()
    mod('preferences').get().maya_layout_on_open=False
    with viewport():
        bpy.ops.allset.opt_poly_cube('INVOKE_DEFAULT')

for i in range(8):
    step(lambda: None)

@step
def save():
    editor=mod('ui.option_editor')
    check('Options editor is usable before saving',editor.find(bpy.context,'poly_cube') is not None)
    editor.owner(bpy.context.window_manager, 'poly_cube').width = 3.5
    path=Path(os.environ['BLENDER_USER_CONFIG']).parent/'options_reload.blend'
    with viewport():
        bpy.ops.wm.save_as_mainfile(filepath=str(path),check_existing=False)

@step
def reload():
    path=Path(os.environ['BLENDER_USER_CONFIG']).parent/'options_reload.blend'
    with viewport():
        bpy.ops.wm.open_mainfile(filepath=str(path),load_ui=True)

for i in range(8):
    step(lambda: None)

@step
def check_restored():
    editor=mod('ui.option_editor')
    marked=mod('ui.marked_window')
    areas=[area for window in bpy.context.window_manager.windows for area in window.screen.areas if marked.kind_of(area)==editor.KIND]
    check(f'loaded Options windows have live editor sessions, areas {len(areas)}, sessions {len(editor._sessions)}',
          len(areas)==1 and bool(editor._sessions))
    window=editor.find(bpy.context,'poly_cube')
    check('the loaded editor keeps its unsaved current options',
          abs(editor.owner(bpy.context.window_manager,'poly_cube').width-3.5)<1e-5)
    C['before']=len(bpy.context.scene.objects)
    area=window.screen.areas[0]
    region=next(r for r in area.regions if r.type=='WINDOW')
    with bpy.context.temp_override(window=window,area=area,region=region):
        check('Apply resolves the originating viewport after loading',
              bpy.ops.allset.option_editor_action(action='APPLY')=={'FINISHED'})
    check('loaded Options creates geometry in the main scene',len(bpy.context.scene.objects)==C['before']+1)


@step
def reenable():
    import addon_utils
    addon_utils.disable(MODULE)
    addon_utils.enable(MODULE, default_set=True)


for i in range(4):
    step(lambda: None)


@step
def after_reenable():
    editor=mod('ui.option_editor')
    window=editor.find(bpy.context,'poly_cube')
    check('Options restores without previous Python sessions or schemas',window is not None)
    check('restoring Options keeps schema registration lazy',set(editor._groups)=={'poly_cube'})
    check('Options values survive addon reload',abs(editor.owner(bpy.context.window_manager,'poly_cube').width-3.5)<1e-5)
    area=window.screen.areas[0]
    region=next(r for r in area.regions if r.type=='WINDOW')
    with bpy.context.temp_override(window=window,area=area,region=region):
        bpy.ops.allset.option_editor_action(action='CLOSE')

C = {}
run()
