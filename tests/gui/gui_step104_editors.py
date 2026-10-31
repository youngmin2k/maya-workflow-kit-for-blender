"""In a real UI: the Maya Workflow Kit layout, pCube1 keyed like the audit-7 scene (translateX 0 -> 5 at 1 / 24,
translateY 3 at 12), Windows > Animation Editors > Graph Editor / Dope Sheet and UV > UV Editor in new windows ->
Maya menu bars, icon rows, channel names, UV Toolkit (screenshots with ALLSET_GUI_SHOTS)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, setup, step, win, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 240
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


def menu(path):
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        return bpy.ops.allset.menu_item(item=path)


def editor(ui_type):
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.ui_type == ui_type:
                return w, a
    return None, None


def close_extra_windows():
    wm = bpy.context.window_manager
    while len(wm.windows) > 1:
        w = wm.windows[-1]
        with bpy.context.temp_override(window=w):
            bpy.ops.wm.window_close()


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
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.active_object
    k = mod(".operators.units").maya_unit()
    sc = bpy.context.scene
    for frame, x in ((1, 0.0), (24, 5.0)):
        ob.location.x = x * k
        ob.keyframe_insert("location", index=0, frame=frame)
    ob.location.y = 3 * k
    ob.keyframe_insert("location", index=1, frame=12)
    sc.frame_set(12)
    C["ob"] = ob.name
    C["graph"] = menu("Windows/Animation Editors/Graph Editor")


def wev(window, type, value, x, y, **kw):
    window.event_simulate(type=type, value=value, x=x, y=y, **kw)


def view_range(area):
    r = next(rg for rg in area.regions if rg.type == 'WINDOW')
    return r.view2d.region_to_view(0, 0)[0], r.view2d.region_to_view(r.width, 0)[0]


@step
def s_graph():
    w, a = editor('FCURVES')
    check(f"Graph Editor window opened ({C['graph']})", a is not None)
    redraw()


@step
def s_graph_wait():
    redraw()


@step
def s_graph_shot():
    w, a = editor('FCURVES')
    chrome = mod(".ui.editor_chrome")
    check("Graph Editor header = the kit's Maya header", chrome.own_draw(bpy.types.GRAPH_HT_header) is chrome._graph_header)
    lo, hi = view_range(a)
    check(f"Graph Editor opens on the playback range from frame 1, no frame 0 (view {lo:.2f} .. {hi:.1f})",
          0.0 < lo < 1.0 and hi > 100)
    shot("gui_step104_graph_editor.png", w)
    ch = next(r for r in a.regions if r.type == 'CHANNELS')
    top, h = chrome.metrics(ch)
    C["ch"] = (w, ch.x + 60, ch.y + top - int(2.5 * h))     # third row: Translate Y
    wev(w, 'MOUSEMOVE', 'NOTHING', C["ch"][1], C["ch"][2])


@step
def s_channel_press():
    w, x, y = C["ch"]
    wev(w, 'LEFTMOUSE', 'PRESS', x, y)


@step
def s_channel_release():
    w, x, y = C["ch"]
    wev(w, 'LEFTMOUSE', 'RELEASE', x, y)


@step
def s_channel_check():
    chrome = mod(".ui.editor_chrome")
    fcs = chrome.object_curves(bpy.data.objects[C["ob"]])
    labels = [chrome.attr_label(fc) for fc in fcs]
    check(f"Graph Editor outliner: click Translate Y -> only that curve selected and shown ({labels}, "
          f"{[(fc.select, fc.hide) for fc in fcs]})",
          fcs[1].select and not fcs[1].hide and fcs[0].hide and not fcs[0].select)
    w, a = editor('FCURVES')
    redraw()
    hd = next(r for r in a.regions if r.type == 'HEADER')
    s = bpy.context.preferences.system.ui_scale
    C["menu"] = (w, hd.x + int(52 * s), hd.y + hd.height // 2)     # "Edit", after the editor-type button
    wev(w, 'MOUSEMOVE', 'NOTHING', *C["menu"][1:])


@step
def s_menu_press():
    w, x, y = C["menu"]
    shot("gui_step104_graph_channel_click.png", w)
    _w, a = editor('FCURVES')
    hd = next(r for r in a.regions if r.type == 'HEADER')
    ms = mod(".ui.menu_sets")
    with bpy.context.temp_override(window=w, area=a, region=hd):
        C["call"] = bpy.ops.wm.call_menu(name=ms.editor_menu_idname("Graph Editor", 5))     # Tangents


@step
def s_menu_wait():
    redraw()


@step
def s_menu_shot():
    w, x, y = C["menu"]
    check(f"Graph Editor Tangents menu opens ({C['call']})", C["call"] == {'FINISHED'} or 'INTERFACE' in C["call"])
    shot("gui_step104_graph_tangents_menu.png", w)
    wev(w, 'ESC', 'PRESS', x, y)
    wev(w, 'ESC', 'RELEASE', x, y)


@step
def s_graph_close():
    close_extra_windows()
    C["dope"] = menu("Windows/Animation Editors/Dope Sheet")


@step
def s_dope():
    w, a = editor('DOPESHEET')
    check(f"Dope Sheet window opened ({C['dope']})", a is not None)
    redraw()


@step
def s_dope_wait():
    redraw()


@step
def s_dope_shot():
    w, a = editor('DOPESHEET')
    lo, hi = view_range(a)
    check(f"Dope Sheet opens on the playback range from frame 1 (view {lo:.2f} .. {hi:.1f})",
          0.0 < lo < 1.0 and hi > 100)
    ch = next(r for r in a.regions if r.type == 'CHANNELS')
    check(f"Dope Sheet: Summary open, objects folded (Maya Dopesheet Summary + pCube1) "
          f"({a.spaces.active.dopesheet.show_expanded_summary})", a.spaces.active.dopesheet.show_expanded_summary)
    shot("gui_step104_dope_sheet.png", w)
    close_extra_windows()
    C["uv"] = menu("UV/UV Editor")


@step
def s_uv():
    w, a = editor('UV')
    check(f"UV Editor opened ({C['uv']})", a is not None)
    redraw()


@step
def s_uv_wait():
    redraw()


@step
def s_uv_shot():
    w, a = editor('UV')
    sp = a.spaces.active
    ui = next(r for r in a.regions if r.type == 'UI')
    check(f"UV Editor: icon row (tool header) and the UV Toolkit on the right "
          f"({sp.show_region_tool_header}, {sp.show_region_ui}, {ui.active_panel_category})",
          sp.show_region_tool_header and sp.show_region_ui and ui.active_panel_category == "UV Toolkit")
    shot("gui_step104_uv_editor.png", w)


run()
