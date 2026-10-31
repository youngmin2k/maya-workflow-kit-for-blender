"""In a real UI (Maya Workflow Kit layout): type into the Status Line input line like a Maya user —
Absolute X = 10 moves pCube1 to x = 10 cm, Rename "crate", Select by name "pSph*".

Python can't tell where a header layout put a field, so the test finds it: it moves the mouse along the
Status Line and asks ``ui.copy_data_path_button`` which property is under it."""

GUI_SKIP = "hangs without a result on this PC (Windows clipboard via wm.clipboard; same at aef175f)"   # tests/gui/run.py leaves it out (--include-skipped runs it)

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, tap, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {"scan": None}
STEP_PX = 12


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def strip():
    shelf = import_module(MODULE + ".ui.shelf")
    area = shelf.strip_area(win().screen)
    return area, next(r for r in area.regions if r.type == 'HEADER')


def inp():
    return bpy.context.scene.allset_input


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def probe_path():
    """Data path of the button under the mouse in the strip header, or ""."""
    area, region = strip()
    wm = bpy.context.window_manager
    wm.clipboard = ""
    try:
        with bpy.context.temp_override(window=win(), screen=win().screen, area=area, region=region):
            bpy.ops.ui.copy_data_path_button(full_path=False)
    except RuntimeError:
        return ""
    return wm.clipboard


def scanner(prop, key, steps=140):
    """Steps that sweep the strip header right to left until the field of ``prop`` is under the mouse."""
    def start():
        _a, region = strip()
        C["scan"] = (key, prop, region.x + region.width - 8, region.y + region.height // 2)
        C[key] = None
        x, y = C["scan"][2], C["scan"][3]
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    step(start)

    def look():
        if C[key] is not None or C["scan"] is None:
            return
        k, p, x, y = C["scan"]
        if probe_path().endswith(p):
            C[key] = (x, y)
            C["scan"] = None
            return
        x -= STEP_PX
        C["scan"] = (k, p, x, y)
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    for _i in range(steps):
        step(look)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    # the Status Line starts with the input line collapsed, like Maya: open it, as a user would
    bpy.ops.allset.status_group(group="INPUT")
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        bpy.ops.allset.create(kind='SPHERE')
    for o in bpy.context.view_layer.objects:
        o.select_set(o.name == "pCube1")
    bpy.context.view_layer.objects.active = bpy.data.objects["pCube1"]
    inp().mode = 'ABS'
    redraw()


scanner("allset_input.x", "x_field")


@step
def s_click_x():
    check(f"found the input line X field in the Status Line ({C['x_field']})", C["x_field"] is not None)
    if C["x_field"] is None:
        return
    x, y = C["x_field"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_type_x():
    for ch in "10":
        ev('TEXTINPUT', 'PRESS', unicode=ch)
    redraw()


@step
def s_typed_shot():
    shot("gui_step75_abs_typing.png")
    tap('RET')


@step
def s_abs_done():
    ob = bpy.data.objects["pCube1"]
    check(f"Absolute X = 10 moves pCube1 to x = 10 cm ({ob.location.x:.4f} m)", abs(ob.location.x - 0.10) < 1e-6)
    inp().mode = 'RENAME'
    redraw()


scanner("allset_input.text", "text_field")


@step
def s_rename_shot():
    check(f"Rename mode shows the lead's name ({inp().text})", inp().text == "pCube1")
    shot("gui_step75_rename_field.png")
    if C["text_field"] is None:
        check("found the input line text field", False)
        return
    x, y = C["text_field"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_type_name():
    ev('A', 'PRESS', ctrl=True)
    ev('A', 'RELEASE', ctrl=True)
    for ch in "crate":
        ev('TEXTINPUT', 'PRESS', unicode=ch)


@step
def s_rename_enter():
    tap('RET')


@step
def s_renamed():
    names = sorted(o.name for o in bpy.data.objects)
    check(f"typing 'crate' + Enter renames pCube1 ({names})", "crate" in names and "pCube1" not in names)
    check(f"its shape follows ({bpy.data.objects['crate'].data.name})", bpy.data.objects["crate"].data.name == "crateShape")
    inp().mode = 'SELECT'
    redraw()


@step
def s_click_select():
    x, y = C["text_field"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_type_select():
    for ch in "pSph*":
        ev('TEXTINPUT', 'PRESS', unicode=ch)


@step
def s_select_enter():
    tap('RET')


@step
def s_selected():
    sel = sorted(o.name for o in bpy.context.selected_objects)
    check(f"Select by name 'pSph*' selects pSphere1 ({sel})", sel == ["pSphere1"])
    redraw()


@step
def s_final_shot():
    shot("gui_step75_select.png")


run()
