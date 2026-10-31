"""In the Maya Workflow Kit layout: a panel torn off by its ::::: handle and a torn-off menu
open windows sized to their content (min / max), and the dock column gets its height back."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, screenshot, setup, step, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
MIN_WINDOW = 200     # Blender doesn't open a window shorter than about this (194 px at any UI scale)


def mod(name):
    return import_module(MODULE + name)


def md():
    return mod(".ui.maya_dock")


def floating():
    wm = bpy.context.window_manager
    return [w for w in wm.windows if md().is_floating(w, wm)]


def close_floating():
    for w in floating():
        with bpy.context.temp_override(window=w):
            bpy.ops.wm.window_close()


def shot(name, window):
    path = os.path.join(SHOTS or os.path.join(os.environ.get("TEMP", "."), "gui129"), name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with bpy.context.temp_override(window=window):
        bpy.ops.screen.screenshot(filepath=path)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_tear_panel():
    bpy.ops.allset.keymap_activate()
    stack = md().find_stack(win().screen)
    C["stack_h"] = stack.height
    bpy.context.window_manager.allset_dock = 'ATTRIBUTE_EDITOR'
    region = next(r for r in stack.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=win(), screen=win().screen, area=stack, region=region):
        C["rows"] = md().panel_rows(bpy.context, stack)
        C["want"] = md().content_height(bpy.context, C["rows"], stack.height)
        bpy.ops.allset.dock_handle('EXEC_DEFAULT')


@step
def s_wait1():
    pass


@step
def s_panel_window():
    fl = floating()
    h = fl[0].height if fl else None
    check(f"the torn-off Attribute Editor (nothing selected) is a floating window ({len(fl)})",
          len(fl) == 1 and md().role(fl[0].screen.areas[0]) == 'ATTRIBUTE_EDITOR')
    check(f"#4: its height follows the content ({h} px for {C['rows']} rows, wanted {C['want']:.0f}, "
          f"dock {C['stack_h']})", C["rows"] is not None and h is not None
          and C["want"] - 5 <= h <= max(C["want"], MIN_WINDOW) + 40 and h < C["stack_h"] - 60)
    # the split piece is closed again: the dock column is as tall as its row (the template's first screen
    # change also re-fits other rows: the same happens when the Tool Settings dock opens, so only the column's
    # height against the viewport beside it is checked)
    stack = md().find_stack(win().screen)
    v3d = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    check(f"#4: the dock column is whole again ({stack and stack.height} / viewport {v3d.height})",
          stack is not None and stack.height == v3d.height and stack.y == v3d.y)
    if fl:
        shot("gui_step129_tear_panel.png", fl[0])
    close_floating()


@step
def s_tear_short_menu():
    sets = mod(".ui.menu_sets")
    rows = {}
    for name in sets.menus_for_set(sets.current_set()):
        idname = sets.menu_idname(name)
        rows[idname] = md().menu_rows(bpy.context, idname)
    C["short"] = min(rows, key=rows.get)
    C["long"] = max(rows, key=rows.get)
    C["rows"] = rows
    with bpy.context.temp_override(window=win()):
        md().tear_menu(bpy.context, C["short"], "Short")


@step
def s_wait2():
    pass


@step
def s_short_window():
    fl = floating()
    C["short_h"] = fl[0].height if fl else None
    check(f"a torn-off menu window opens ({len(fl)})", len(fl) == 1 and md().role(fl[0].screen.areas[0]) == 'MENU')
    if fl:
        shot("gui_step129_tear_menu_short.png", fl[0])
    close_floating()
    with bpy.context.temp_override(window=win()):
        md().tear_menu(bpy.context, C["long"], "Long")


@step
def s_wait3():
    pass


@step
def s_long_window():
    fl = floating()
    long_h = fl[0].height if fl else None
    short_h = C["short_h"]
    check(f"#4: a short menu ({C['rows'][C['short']]:.0f} rows) tears off shorter than a long one "
          f"({C['rows'][C['long']]:.0f} rows): {short_h} < {long_h} px", short_h and long_h and short_h < long_h - 60)
    check(f"#4: the short menu's window is about its content ({short_h} px)",
          short_h is not None
          and short_h < max(md().content_height(bpy.context, C['rows'][C['short']], 5000), MIN_WINDOW) + 40)
    if fl:
        shot("gui_step129_tear_menu_long.png", fl[0])
    close_floating()


run()
