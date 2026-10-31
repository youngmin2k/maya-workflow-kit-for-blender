"""In a real UI: the Maya Graph Editor outliner rows for Pin Channel and List > Load Selected Objects
(Maya Graph Editor rules): pCube1 (translate X) and pSphere1 (translate Y) keyed; pick pCube1's
row + Curves > Pin Channel, select only pSphere1 -> pSphere1's rows plus pCube1's pinned row below them (pin
marks drawn); Auto Load off + Load Selected on pSphere1, then select pCube1 -> the list stays."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, setup, step, win, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 200
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(MODULE + name)


def shot(name, window=None):
    if SHOTS:
        with bpy.context.temp_override(window=window or win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def v3d():
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def graph():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.ui_type == 'FCURVES':
                return w, a, next(r for r in a.regions if r.type == 'CHANNELS')
    return None, None, None


def redraw():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


def select_only(name):
    for ob in bpy.context.scene.objects:
        ob.select_set(ob.name == name)
    bpy.context.view_layer.objects.active = bpy.data.objects[name]


def row_names():
    w, a, ch = graph()
    chrome = mod(".ui.editor_chrome")
    with bpy.context.temp_override(window=w, area=a, region=ch):
        return [(k, n.name) for k, n, _f in chrome.rows(bpy.context, a.spaces.active)]


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, region = v3d()
    k = mod(".operators.units").maya_unit()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        cube = bpy.context.active_object
        for frame, x in ((1, 0.0), (24, 5.0)):
            cube.location.x = x * k
            cube.keyframe_insert("location", index=0, frame=frame)
        bpy.ops.allset.create(kind='SPHERE')
        sphere = bpy.context.active_object
        for frame, y in ((1, 0.0), (24, 3.0)):
            sphere.location.y = y * k
            sphere.keyframe_insert("location", index=1, frame=frame)
        select_only(cube.name)
        C["graph"] = bpy.ops.allset.menu_item(item="Windows/Animation Editors/Graph Editor")
    C["cube"], C["sphere"] = cube.name, sphere.name


@step
def s_graph():
    w, a, _ch = graph()
    check(f"Graph Editor window opened ({C['graph']})", a is not None)
    redraw()


@step
def s_pin():
    w, a, ch = graph()
    chrome = mod(".ui.editor_chrome")
    with bpy.context.temp_override(window=w, area=a, region=ch):
        rows = chrome.rows(bpy.context, a.spaces.active)
        node = next(r for r in rows if r[0] != "ATTR" and r[1].name == C["cube"])
        chrome.pick_row(bpy.context, node)          # highlight pCube1's node row = all its channels
        C["pin"] = bpy.ops.allset.graph_pin(pin=True)
    check(f"Curves > Pin Channel on the highlighted pCube1 row ({C['pin']})", C["pin"] == {'FINISHED'})
    select_only(C["sphere"])
    redraw()


@step
def s_pin_wait():
    redraw()


@step
def s_pin_check():
    names = row_names()
    nodes = [n for k, n in names if k != "ATTR"]
    check(f"pSphere1 selected: its rows, then pCube1's pinned rows below ({names})",
          nodes[:1] == [C["sphere"]] and C["cube"] in nodes[1:]
          and any(k == "ATTR" for k, n in names[nodes.index(C["cube"]) + 1:] or []))
    shot("gui_step203_pinned.png", graph()[0])


@step
def s_unpin_and_load():
    w, a, ch = graph()
    chrome = mod(".ui.editor_chrome")
    with bpy.context.temp_override(window=w, area=a, region=ch):
        rows = chrome.rows(bpy.context, a.spaces.active)
        node = next(r for r in rows if r[0] != "ATTR" and r[1].name == C["cube"])
        chrome.pick_row(bpy.context, node)
        bpy.ops.allset.graph_pin(pin=False)
        greyed = not bpy.ops.allset.graph_list.poll()
        bpy.context.window_manager.allset_auto_load = False
        C["load"] = bpy.ops.allset.graph_list(action='LOAD')
    check("Load Selected Objects is greyed while Auto Load is on (Maya)", greyed)
    check(f"Auto Load off + Load Selected Objects ({C['load']})", C["load"] == {'FINISHED'})
    select_only(C["cube"])
    redraw()


@step
def s_load_wait():
    redraw()


@step
def s_load_check():
    nodes = [n for k, n in row_names() if k != "ATTR"]
    check(f"loaded list keeps pSphere1 after selecting pCube1 ({nodes})", nodes == [C["sphere"]])
    shot("gui_step203_loaded.png", graph()[0])


run()
