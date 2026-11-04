"""In a real UI: Ctrl+Alt+Shift+M switches Maya mode off and on without a restart; the
open file's objects stay, Maya mode brings the Maya layout workspace (appended) and Blender mode
goes back to the user's workspace and removes it; the Maya / Blender switch shows in the top
bar in both modes (screenshots)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def sw():
    return import_module(MODULE + ".switch")


def scene_state():
    return sorted((o.name, tuple(round(v, 6) for v in o.location), o.type) for o in bpy.data.objects), \
        bpy.context.scene.unit_settings.length_unit, bpy.data.filepath


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def shortcut():
    _area, r = view3d()
    x, y = r.x + r.width // 2, r.y + r.height // 2
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('M', 'PRESS', x=x, y=y, ctrl=True, alt=True, shift=True)
    ev('M', 'RELEASE', x=x, y=y, ctrl=True, alt=True, shift=True)


@step
def s_setup():
    setup()
    bpy.ops.allset.keymap_activate()
    bpy.data.objects["Cube"].location = (1.5, 0.25, 0.0)
    C["scene"] = scene_state()
    C["ws"] = win().workspace.name
    check(f"enabled = Maya mode ({sw().is_on()}, keymap {bpy.context.window_manager.keyconfigs.active.name})",
          sw().is_on() and sys.modules["sim"].maya_keys())
    redraw()


@step
def s_shot_maya_keys():
    shot("gui_step60_maya_mode_factory_layout.png")
    shortcut()


@step
def s_wait_blender():
    # the switch runs from a timer once the key event is handled; a busy first redraw can delay that past one tick
    import sim
    C.setdefault("wait_off", 0)
    if sw().is_on() and C["wait_off"] < 10:
        C["wait_off"] += 1
        sim._steps.insert(0, s_wait_blender)


@step
def s_blender():
    kcs = bpy.context.window_manager.keyconfigs
    check(f"Ctrl+Alt+Shift+M -> Blender mode (keymap {kcs.active.name}, Maya classes gone)",
          not sw().is_on() and kcs.active.name == "Blender" and not hasattr(bpy.types.Scene, "allset_cb"))
    check("the open file's objects are untouched", scene_state() == C["scene"])
    check(f"workspace unchanged ({win().workspace.name})", win().workspace.name == C["ws"])
    redraw()


@step
def s_shot_blender():
    shot("gui_step60_blender_mode.png")
    shortcut()


@step
def s_maya():
    kcs = bpy.context.window_manager.keyconfigs
    ws = win().workspace
    check(f"Ctrl+Alt+Shift+M again -> Maya mode (keymap {kcs.active.name})",
          sw().is_on() and sys.modules["sim"].maya_keys() and hasattr(bpy.types.Scene, "allset_cb"))
    check(f"Maya layout workspace appended and active ({ws.name}, from {ws.get(sw().PREV_KEY)})",
          ws.name == sw().WORKSPACE and ws.get(sw().PREV_KEY) == C["ws"])
    check("objects still untouched", scene_state() == C["scene"])
    shelf = import_module(MODULE + ".ui.shelf")
    spaces = [a.spaces.active for a in win().screen.areas]
    check("the Maya layout's Status Line and Shelf rows are marked (masks loaded with it)",
          any(shelf.is_strip(sp) for sp in spaces) and any(shelf.is_shelf_row(sp) for sp in spaces))
    redraw()


@step
def s_shot_maya():
    shot("gui_step60_maya_mode.png")
    bpy.ops.allset.switch_mode(mode='BLENDER')     # what the top bar "Blender" button runs


@step
def s_back():
    # the Maya workspace is deleted once the window has left it (a timer): wait up to 40 ticks
    import sim as _sim
    C.setdefault("back_waits", 0)
    if (sw().is_on() or sw().WORKSPACE in bpy.data.workspaces) and C["back_waits"] < 40:
        C["back_waits"] += 1
        _sim._steps.insert(0, s_back)
        return
    names = [w.name for w in bpy.data.workspaces]
    check(f"back in Blender: the user's workspace again, the Maya one removed ({win().workspace.name}, {names})",
          not sw().is_on() and win().workspace.name == C["ws"] and sw().WORKSPACE not in names)
    check(f"and the masks it loaded ({[m.name for m in bpy.data.masks]})", len(bpy.data.masks) == 0)
    check("objects untouched after the round trip", scene_state() == C["scene"])
    redraw()


@step
def s_shot_back():
    shot("gui_step60_blender_again.png")


run()
