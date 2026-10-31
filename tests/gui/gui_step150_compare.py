"""#96: the Graph Editor (pCube1 Translate X
0 -> 5 -> 0 at frames 1 / 10 / 20, Frame All) and its outliner (only pCube1 blue,
Translate X red). Also Ctrl+A over the Graph Editor = Attribute Editor / Channel Box (Maya's global Ctrl+a) and the
mouse wheel over the kit outliner reaches allset.graph_channel_scroll. Shots with ``--shots``."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, maya_kc, run, setup, step, win  # noqa: E402

GUI_TIMEOUT = 240
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(MODULE + name)


def shot(name, window):
    if SHOTS:
        with bpy.context.temp_override(window=window):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def v3d():
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def graph():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.ui_type == 'FCURVES':
                return w, a
    return None, None


def region(area, kind):
    return next(r for r in area.regions if r.type == kind)


def redraw():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, reg = v3d()
    k = mod(".operators.units").maya_unit()
    with bpy.context.temp_override(window=win(), area=area, region=reg):
        bpy.ops.allset.create(kind='CUBE')
        cube = bpy.context.active_object
        for frame, x in ((1, 0.0), (10, 5.0), (20, 0.0)):
            cube.location.x = x * k
            cube.keyframe_insert("location", index=0, frame=frame)
        bpy.ops.allset.menu_item(item="Windows/Animation Editors/Graph Editor")


@step
def s_frame():
    w, a = graph()
    check("Graph Editor window opened", a is not None)
    with bpy.context.temp_override(window=w, area=a, region=region(a, 'WINDOW')):
        bpy.ops.graph.view_all()
    redraw()


step(redraw)
step(redraw)


@step
def s_shot():
    w, a = graph()
    shot("gui_step150_graph_frame_all.png", w)
    chrome = mod(".ui.editor_chrome")
    ch = region(a, 'CHANNELS')
    with bpy.context.temp_override(window=w, area=a, region=ch):
        rows = chrome.rows(bpy.context, a.spaces.active)
    labels = [chrome.attr_label(f) if f is not None else n.name for _k, n, f in rows]
    check(f"outliner rows = pCube1 > Translate X ({labels})", labels == ["pCube1", "Translate X"])
    # Ctrl+A over the Graph Editor's curve area: Maya's global AE / Channel Box swap
    wm = bpy.context.window_manager
    C["dock"] = wm.allset_dock
    r = region(a, 'WINDOW')
    x, y = r.x + r.width // 2, r.y + r.height // 2
    w.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
    w.event_simulate(type='LEFT_CTRL', value='PRESS', x=x, y=y)
    w.event_simulate(type='A', value='PRESS', x=x, y=y, ctrl=True)
    w.event_simulate(type='A', value='RELEASE', x=x, y=y, ctrl=True)
    w.event_simulate(type='LEFT_CTRL', value='RELEASE', x=x, y=y)


@step
def s_ctrl_a():
    wm = bpy.context.window_manager
    check(f"Ctrl+A over the Graph Editor swaps the dock ({C['dock']} -> {wm.allset_dock})", wm.allset_dock != C["dock"])
    km = maya_kc().keymaps["View2D"]
    keys = sorted((i.type, i.properties.delta) for i in km.keymap_items
                  if i.idname == "allset.graph_channel_scroll" and i.active)
    check(f"wheel over the outliner = allset.graph_channel_scroll ({keys})",
          keys == [("WHEELDOWNMOUSE", 3), ("WHEELUPMOUSE", -3)])
    # a long list: 30 keyed custom attributes, then a real wheel event over the outliner pane
    cube = bpy.data.objects["pCube1"]
    for i in range(30):
        cube[f"attr{i:02d}"] = 0.0
        cube.keyframe_insert(f'["attr{i:02d}"]', frame=1)
    redraw()


step(redraw)


@step
def s_wheel():
    w, a = graph()
    ch = region(a, 'CHANNELS')
    chrome = mod(".ui.editor_chrome")
    C["ptr"] = a.as_pointer()
    C["before"] = chrome._scroll.get(C["ptr"], 0)
    x, y = ch.x + ch.width // 2, ch.y + ch.height // 2
    w.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
    w.event_simulate(type='WHEELDOWNMOUSE', value='PRESS', x=x, y=y)


step(redraw)


@step
def s_wheel_check():
    w, a = graph()
    chrome = mod(".ui.editor_chrome")
    after = chrome._scroll.get(C["ptr"], 0)
    check(f"wheel down over the outliner scrolls the kit rows ({C['before']} -> {after})", after > C["before"])
    shot("gui_step150_graph_scrolled.png", w)

run()
