"""In a real UI: the Script Editor's History menu. Show Stack Trace is turned on through its Maya menu item
(``allset.menu_item``), a failing script runs with Ctrl+Enter -> the history pane (Blender's Info editor) lists
Maya's "# Error: ... file <maya console> line n: ..." line and the "# Traceback" lines; Echo All Commands on + a Maya
menu command -> its Python call is listed (an OPERATOR-type report, no status-bar banner). The History menu is drawn
with check / radio items (screenshot)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, setup, step, win, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 200
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
SCRIPT = "def inner():\n    return 1 / 0\n\ninner()\n"


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


def history_text(w):
    """The history pane's lines: Info editor Select All + Copy Reports -> clipboard."""
    se = mod(".ui.script_editor")
    info, _text = se.areas(w)
    region = next(r for r in info.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=w, area=info, region=region):
        bpy.ops.info.select_all(action='SELECT')
        bpy.ops.info.report_copy()
        bpy.ops.info.select_all(action='DESELECT')
    return bpy.context.window_manager.clipboard


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
        C["se"] = bpy.ops.allset.menu_item(item="Windows/General Editors/Script Editor")


@step
def s_options():
    w = newest()
    se = mod(".ui.script_editor")
    prefs = mod(".preferences").get()
    check(f"Script Editor window opened ({C['se']})", w is not None and w.as_pointer() in se._WINDOWS)
    check("defaults: Show Stack Trace off, Line numbers in errors on, Echo All Commands off, Show Both",
          not prefs.se_stack_trace and prefs.se_line_numbers and not prefs.se_echo_all
          and prefs.se_history_output == 'BOTH')
    _info, text = se.areas(w)
    with bpy.context.temp_override(window=w, area=text):
        res = bpy.ops.allset.menu_item(item="Script Editor/History/Show Stack Trace")
    check(f"History > Show Stack Trace through allset.menu_item ({res}) -> on", prefs.se_stack_trace)
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
def s_check_trace():
    w, _x, _y = C["text"]
    got = history_text(w)
    print("HISTORY <<<\n" + got + "\n>>>")
    check("history: Maya error line with the script line",
          "# Error: ZeroDivisionError: file <maya console> line 2: division by zero" in got)
    check("history: the traceback (Show Stack Trace)",
          "# Traceback (most recent call last):" in got and '#   File "<maya console>", line 4, in <module>' in got
          and '#   File "<maya console>", line 2, in inner' in got and "# ZeroDivisionError: division by zero" in got)
    check("no Blender report text in the history (Location: / bpy ops.py)", "Location:" not in got)
    C["log_n"] = len(mod(".command_line.runner").log)
    mod(".preferences").get().se_echo_all = True
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.menu_item(item="Create/Polygon Primitives/Cube")
    redraw()


@step
def s_check_echo():
    w, _x, _y = C["text"]
    got = history_text(w)
    runner = mod(".command_line.runner")
    new = runner.log[C["log_n"]:]
    check(f"Echo All Commands: one echo logged for Create > Cube ({new})",
          len(new) == 1 and new[0][0] == "ECHO" and new[0][2].startswith("bpy.ops."))
    check("its Python call is in the history pane", bool(new) and new[0][2] in got)
    mod(".preferences").get().se_echo_all = False
    redraw()


@step
def s_shot_history():
    w, _x, _y = C["text"]
    shot("gui_step216_history.png", w)


@step
def s_menu():
    w, x, y = C["text"]
    se = mod(".ui.script_editor")
    info, _text = se.areas(w)
    region = next(r for r in info.regions if r.type == 'WINDOW')
    mx, my = region.x + region.width // 3, region.y + region.height // 2
    w.event_simulate(type='MOUSEMOVE', value='NOTHING', x=mx, y=my)
    menu_sets = mod(".ui.menu_sets")
    with bpy.context.temp_override(window=w, area=info, region=region):
        bpy.ops.wm.call_menu(name=menu_sets.editor_menu_idname("Script Editor", 2))


@step
def s_wait():
    redraw()


@step
def s_shot_menu():
    w, _x, _y = C["text"]
    shot("gui_step216_history_menu.png", w)
    w.event_simulate(type='ESC', value='PRESS', x=10, y=10)
    w.event_simulate(type='ESC', value='RELEASE', x=10, y=10)
    mod(".preferences").get().se_stack_trace = False


run()
