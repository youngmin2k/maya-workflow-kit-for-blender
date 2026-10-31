"""In a real UI: a Maya script typed into the Script Editor's Python tab (Ctrl+Enter) that starts a new scene
(``cmds.file(new=True, force=True)``), builds a small rig with group / parent / spaceLocator / duplicate, keys it and
sets the playback range -> the scene has the Maya names and keys, the Script Editor window and its input survive the
new scene, ``file -q -modified`` right after it is logged (the kit reports True inside a script)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, setup, step, win, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 200
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
SCRIPT = """import maya.cmds as cmds
cmds.file(new=True, force=True)
M = cmds.file(q=True, modified=True)
a = cmds.polyCube()[0]
ctrl = cmds.spaceLocator(n='ctrl')[0]
g = cmds.group(a, n='geo_grp')
cmds.parent(g, ctrl)
cmds.move(0, 5, 0, ctrl)
copy = cmds.duplicate(a)
cmds.setKeyframe(ctrl, at='ty', t=1, v=0)
cmds.setKeyframe(ctrl, at='ty', t=24, v=10)
cmds.playbackOptions(min=1, max=24)
cmds.currentTime(12)
cmds.select(ctrl)
"""


def mod(name):
    return import_module(MODULE + name)


def shot(name, window=None):
    if SHOTS:
        with bpy.context.temp_override(window=window or win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def v3d():
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def newest():
    wins = bpy.context.window_manager.windows
    return wins[-1] if len(wins) > 1 else None


def redraw():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_open():
    bpy.ops.allset.keymap_activate()
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='SPHERE')          # something the new scene must clear
        C["se"] = bpy.ops.allset.menu_item(item="Windows/General Editors/Script Editor")


@step
def s_type():
    w = newest()
    se = mod(".ui.script_editor")
    check(f"Script Editor window opened ({C['se']})", w is not None and w.as_pointer() in se._WINDOWS)
    _info, text = se.areas(w)
    sp = text.spaces.active
    sp.text.clear()
    sp.text.write(SCRIPT)
    region = next(r for r in text.regions if r.type == 'WINDOW')
    C["text"] = (w, region.x + region.width // 2, region.y + region.height // 2)
    w.event_simulate(type='MOUSEMOVE', value='NOTHING', x=C["text"][1], y=C["text"][2])


@step
def s_run():
    w, x, y = C["text"]
    w.event_simulate(type='RET', value='PRESS', x=x, y=y, ctrl=True)
    w.event_simulate(type='RET', value='RELEASE', x=x, y=y, ctrl=True)


@step
def s_check():
    runner = mod(".command_line.runner")
    ns = runner.namespace()
    names = sorted(o.name for o in bpy.context.scene.objects)
    check(f"the script ran in a new scene: {names}", names == ["ctrl", "geo_grp", "pCube1", "pCube2"])
    # Maya: 0. Blender marks a file read inside a running operator (the script's Run Script) as modified; a new
    # scene from a timer is not (seen here) -> documented deviation
    print(f"file -q -modified right after file -new inside the script: {ns.get('M')!r}")
    ob = bpy.data.objects.get("pCube1")
    check("pCube1 under geo_grp under ctrl (Maya parent / group)",
          ob is not None and ob.parent is not None and ob.parent.name == "geo_grp" and
          ob.parent.parent is not None and ob.parent.parent.name == "ctrl")
    ctrl = bpy.data.objects.get("ctrl")
    cmds = mod(".command_line.cmds_shim")
    keys = cmds.keyframe("ctrl", at="ty", q=True, tc=True, vc=True) if ctrl else None
    check(f"ctrl.ty keys (1, 0) (24, 10): {keys}",
          keys is not None and len(keys) == 4 and all(abs(a - b) < 1e-5 for a, b in zip(keys, (1, 0, 24, 10))))
    sc = bpy.context.scene
    check(f"playback range = preview 1-24 ({sc.use_preview_range}, {sc.frame_preview_start}-{sc.frame_preview_end})",
          sc.use_preview_range and (sc.frame_preview_start, sc.frame_preview_end) == (1, 24))
    check(f"ctrl at time 12 between its keys ({cmds.getAttr('ctrl.ty') if ctrl else None})",
          ctrl is not None and 3.0 < cmds.getAttr("ctrl.ty") < 7.0)
    check("ctrl's shape is a locator (ls -type locator)", cmds.ls(type="locator") == ["ctrlShape"])
    w, _x, _y = C["text"]
    se = mod(".ui.script_editor")
    alive = w in list(bpy.context.window_manager.windows)
    check("the Script Editor window stays after file -new", alive)
    if alive:
        _info, text = se.areas(w)
        t = text.spaces.active.text if text else None
        check(f"its Python tab keeps the script ({t.name if t else None})",
              t is not None and "cmds.file(new=True, force=True)" in t.as_string())
    redraw()


@step
def s_wait():
    redraw()


@step
def s_shot():
    w, _x, _y = C["text"]
    shot("gui_step208_main.png")
    if w in list(bpy.context.window_manager.windows):
        shot("gui_step208_script_editor.png", w)


run()
