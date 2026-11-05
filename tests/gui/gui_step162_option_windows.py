"""In a real UI: Display > Toggle Show/Hide ❒ and Edit > Delete by Type > Non-Deformer History ❒ open
Maya's option windows; Enter = the window's command with its default values.
Screenshots (ALLSET_GUI_SHOTS) for the step doc."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
TOGGLE = "Display/Toggle Show/Hide"
NONDEF = "Edit/Delete by Type/Non-Deformer History"


def shot(name):
    if SHOTS:
        window = next((w for w in bpy.context.window_manager.windows
                       if w.as_pointer() in mod('ui.option_editor')._sessions), win())
        with bpy.context.temp_override(window=window):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def mod(name):
    return import_module(f"{MODULE}.{name}")


def key(k):
    editor = mod('ui.option_editor')
    window = next((w for w in bpy.context.window_manager.windows if w.as_pointer() in editor._sessions), None)
    if window is not None:
        area = window.screen.areas[0]
        region = next(r for r in area.regions if r.type == 'WINDOW')
        for value in ('PRESS', 'RELEASE'):
            window.event_simulate(type=k, value=value, x=region.x+region.width//2, y=region.y+region.height//2)
        return
    ev(k, 'PRESS')
    ev(k, 'RELEASE')


def _open(path):
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0], y=C["mid"][1])
    with bpy.context.temp_override(window=win()):
        res = bpy.ops.allset.menu_option_box('INVOKE_DEFAULT', item=path)
    check(f"{path} option box opens ({res})", res in ({'FINISHED'}, {'RUNNING_MODAL'}))


@step
def s_setup():
    setup()
    key('ESC')                                   # the factory splash eats events until ESC


@step
def s_scene():
    a, r = view3d()
    C["mid"] = (a.x + a.width // 2, a.y + a.height // 2)
    with bpy.context.temp_override(window=win(), area=a, region=r):
        bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.view_layer.objects.active
    ob.modifiers.new("polyExtrudeFace1", 'SOLIDIFY')
    ob.modifiers.new("bend1", 'SIMPLE_DEFORM')
    ob.modifiers.new("polyBevel1", 'BEVEL')
    C["ob"] = ob.name
    for path in (TOGGLE, NONDEF):
        check(f"{path} option box = a Maya window ({mod('ui.menu_sets').option_kind(path)})",
              mod("ui.menu_sets").option_kind(path) == "window")
    _open(NONDEF)


@step
def s_away1():
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0] + 200, y=C["mid"][1] - 10)   # inside the window, off its buttons


@step
def s_nondef_shot():
    shot("gui_step162_non_deformer_history.png")
    key('RET')                                   # Maya's Delete button: All non-deformer history


@step
def s_nondef_done():
    ob = bpy.data.objects[C["ob"]]
    names = [m.name for m in ob.modifiers if not m.name.startswith("Maya")]
    check(f"Delete (factory All non-deformer history) keeps only the deformer ({names})", names == ["bend1"])
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    _open(TOGGLE)


@step
def s_away2():
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0] + 200, y=C["mid"][1] - 10)


@step
def s_toggle_shot():
    shot("gui_step162_toggle_show_hide.png")
    key('RET')                                   # Apply and Close: Independent toggles the selected cube


@step
def s_toggle_done():
    ob = bpy.data.objects[C["ob"]]
    check(f"Apply and Close toggled the selected cube off ({ob.hide_viewport})", ob.hide_viewport)
    saved = mod("operators.option_windows").saved("toggle_show_hide")
    check(f"the window's value is kept for h ({saved})", saved == {"first_selection": "Independent"})


run()
