"""Step 105 in a real UI: the Maya Workflow Kit layout, pCube1 with lambert1 + a Blinn, then Windows > Rendering Editors >
Hypershade, Render > Render Settings, Windows > General Editors > Script Editor in new windows -> Maya menu bars,
Browser tabs, Blender's Render tab, history over MEL / Python input (screenshots with ALLSET_GUI_SHOTS)."""

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


def newest():
    wins = bpy.context.window_manager.windows
    return wins[-1] if len(wins) > 1 else None


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
    m = mod(".operators.material")
    for kind in ('BLINN', 'RAMP', 'STANDARD_SURFACE'):
        m.new_material(kind).use_fake_user = True
    C["hs"] = menu("Windows/Rendering Editors/Hypershade")


def hs_window():
    hs = mod(".ui.hypershade")
    w = newest()
    return w if w is not None and sum(1 for a in w.screen.areas if hs.pane(a)) == 4 else None


@step
def s_hs():
    C.setdefault("hs_wait", 0)
    if hs_window() is None and C["hs_wait"] < 40:       # the layout is split one area per tick (step 131)
        C["hs_wait"] += 1
        sys.modules["sim"]._steps.insert(0, s_hs)
        redraw()
        return
    w = hs_window()
    hs = mod(".ui.hypershade")
    a = hs.graph_area(w.screen) if w else None
    check(f"Hypershade window opened ({C['hs']}, graph {a and a.ui_type})", a is not None and a.ui_type == 'ShaderNodeTree')
    redraw()


@step
def s_hs_wait():
    redraw()


@step
def s_hs_shot():
    w = newest()
    hs = mod(".ui.hypershade")
    check("Hypershade menu strip + Graph header draw the Maya menus / graph toolbar",
          hs.menu_area(w.screen) is not None and hs.graph_area(w.screen) is not None)
    shot("gui_step105_hypershade.png", w)
    close_extra_windows()
    C["rs"] = menu("Render/Render Settings...")


@step
def s_rs():
    w = newest()
    redraw()


@step
def s_rs_wait():
    w = newest()
    a = w.screen.areas[0] if w else None
    check(f"Render Settings = a Properties window on Blender's Render tab ({C['rs']}, "
          f"{a and a.ui_type}, {a and a.spaces.active.context})",
          a is not None and a.ui_type == 'PROPERTIES' and a.spaces.active.context == 'RENDER')
    shot("gui_step105_render_settings.png", w)
    close_extra_windows()
    C["se"] = menu("Windows/General Editors/Script Editor")


@step
def s_se():
    w = newest()
    se = mod(".ui.script_editor")
    types_ = sorted(a.type for a in w.screen.areas) if w else []
    check(f"Script Editor window = history (Info) over input (Text) ({C['se']}, {types_})",
          types_ == ['INFO', 'TEXT_EDITOR'] and w.as_pointer() in se._WINDOWS)
    info, text = se.areas(w)
    check(f"history pane above the input pane ({info.y}, {text.y})", info.y > text.y)
    sp = text.spaces.active
    sp.text.clear()
    sp.text.write("import maya.cmds as cmds\ncmds.polySphere()\n")
    region = next(r for r in text.regions if r.type == 'WINDOW')
    C["text"] = (w, region.x + region.width // 2, region.y + region.height // 2)
    w.event_simulate(type='MOUSEMOVE', value='NOTHING', x=C["text"][1], y=C["text"][2])


@step
def s_se_run():
    w, x, y = C["text"]
    C["n"] = len(bpy.data.objects)
    w.event_simulate(type='RET', value='PRESS', x=x, y=y, ctrl=True)
    w.event_simulate(type='RET', value='RELEASE', x=x, y=y, ctrl=True)


@step
def s_se_check():
    w, _x, _y = C["text"]
    se = mod(".ui.script_editor")
    _info, text = se.areas(w)
    check(f"Ctrl+Enter runs the Python tab (cmds.polySphere: objects {C['n']} -> {len(bpy.data.objects)}), "
          f"input kept", len(bpy.data.objects) == C["n"] + 1 and "polySphere" in text.spaces.active.text.as_string())
    redraw()


@step
def s_se_wait():
    redraw()


@step
def s_se_shot():
    w, _x, _y = C["text"]
    shot("gui_step105_script_editor.png", w)


run()
