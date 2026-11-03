"""Graph Editor / Dope Sheet toolbar row (#277): in an editor too narrow for every button, the groups that fit stay
in Maya's order and the rest go behind a » button at the right end (no button is cut off)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, find_button, load_maya_layout, run, screenshot, setup, step, win  # noqa: E402

GUI_TIMEOUT = 240
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "") or bpy.app.tempdir
C = {}
FOUND = {}


def chrome():
    return import_module(MODULE + ".ui.editor_chrome")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def area():
    return next(a for a in win().screen.areas if a.as_pointer() == C["area"])


def footer():
    a = area()
    return a, next(r for r in a.regions if r.type == 'FOOTER')


def group_of(editor, data_path, command):
    """Index of the toolbar group the button (data path, Python command) belongs to, -1 when none."""
    hit = -1
    for k, group in enumerate(chrome().icon_groups(editor)):
        for it in group:
            if not isinstance(it, tuple):
                if it == "STATS" and "allset_key_" in data_path:
                    hit = k
                continue
            key, _icon, action, _tip = it
            if f'|{key}"' in command:
                hit = k
            elif action is not None and action[0] == "prop":
                attr = action[1].rsplit(".", 1)[1]
                value = action[2].get("value")
                if value is None and data_path.endswith(attr):
                    hit = k
                elif value is not None and action[1] in command:
                    hit = k
    return hit


def toolbar_button(dp, cmd):
    return "editor_icon" in cmd or "menu_set_value" in cmd or dp.endswith(("use_snap_anim", "allset_auto_load",
                                                                             "graph_unconstrained_drag",
                                                                             "use_auto_normalization",
                                                                             "allset_key_value", "allset_key_time"))


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_graph():
    a = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    C["area"] = a.as_pointer()
    a.ui_type = 'FCURVES'


@step
def s_wait():
    redraw()


@step
def s_wait2():
    redraw()


@step
def s_fold():
    a, foot = footer()
    check(f"toolbar on its own row ({a.width} px wide)", chrome().toolbar_row(a))
    editor, n = chrome()._FIRST_HIDDEN.get(a.as_pointer(), (None, 0))
    total = len(chrome().icon_groups("Graph Editor"))
    C["n"] = n
    screenshot(os.path.join(SHOTS, "gui_issue277_toolbar_fold.png"))
    check(f"a {foot.width} px toolbar row folds: {n} of {total} groups shown", editor == "Graph Editor"
          and 3 <= n < total)


s_find = step(find_button(footer, toolbar_button, FOUND, "last", step_px=6))


@step
def s_last_group():
    found = FOUND.get("last")
    check(f"rightmost toolbar button found at {found}", found is not None)
    if found is None:
        return
    a, foot = footer()
    from sim import button_under_mouse, ev
    ev('MOUSEMOVE', 'NOTHING', x=found[0], y=found[1])
    C["at"] = found


@step
def s_last_check():
    from sim import button_under_mouse
    a, foot = footer()
    dp, cmd = button_under_mouse(a, foot)
    g = group_of("Graph Editor", dp, cmd)
    check(f"the rightmost button belongs to the last shown group {C['n'] - 1} (got {g}: {dp!r} {cmd!r})",
          g == C["n"] - 1)
    x = C["at"][0] - foot.x
    check(f"... and sits left of the » button ({x} px of {foot.width})", x < foot.width - 30)


@step
def s_dope():
    area().ui_type = 'DOPESHEET'


@step
def s_wait3():
    redraw()


@step
def s_wait4():
    redraw()


@step
def s_dope_check():
    a, foot = footer()
    editor, n = chrome()._FIRST_HIDDEN.get(a.as_pointer(), (None, 0))
    total = len(chrome().icon_groups("Dope Sheet"))
    check(f"Dope Sheet: {foot.width} px row shows {n} of {total} groups", editor == "Dope Sheet" and n >= 1)


run()
