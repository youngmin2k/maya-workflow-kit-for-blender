"""Issue #177 ( Blender 5.1 + a 2-button mouse with a wheel): Alt+LMB tumble with Emulate 3 Button Mouse off / on.

1. Emulate off: Alt+LMB drag tumbles (the view rotation changes).
2. Emulate on: Blender turns Alt+LMB into a plain MMB without Alt before any keymap sees it; with Alt still held
   (asked from the OS) the kit tumbles anyway (#242) (wm_event_system.cc
   wm_eventemulation :5637-5658, only on the GHOST path :6226 / :6276; ``event_simulate`` skips it), so the add-on only ever
   gets that MMB drag. Sent here as such: no tumble.
3. Emulate on: the kit's hint is in the welcome dialog paragraphs and in the add-on preferences (read only).
Shots (ALLSET_GUI_SHOTS): gui_step267_welcome_emulate.png."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, tap, view3d  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def rv3d():
    return view3d()[0].spaces.active.region_3d


def drag(button, dx, dy=0, alt=False):
    x, y = C["x"], C["y"]
    ev(button, 'PRESS', x=x, y=y, alt=alt)
    ev('MOUSEMOVE', 'NOTHING', x=x + dx // 2, y=y + dy // 2, alt=alt)
    ev('MOUSEMOVE', 'NOTHING', x=x + dx, y=y + dy, alt=alt)
    ev(button, 'RELEASE', x=x + dx, y=y + dy, alt=alt)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_setup():
    C["x"], C["y"] = setup()
    C["rot"] = tuple(rv3d().view_rotation)
    drag('LEFTMOUSE', 150, 40, alt=True)


@step
def s_off_tumbles():
    check(f"Blender {bpy.app.version_string}, Emulate 3 Button off: Alt+LMB tumbles",
          tuple(rv3d().view_rotation) != C["rot"])
    prefs = import_module(MODULE + ".preferences")
    check("Emulate off: no hint", prefs.emulate_hint() is None)
    bpy.context.preferences.inputs.use_mouse_emulate_3_button = True   # sandbox prefs (factory startup, never saved)
    C["rot"] = tuple(rv3d().view_rotation)
    C["view"] = (rv3d().view_distance, tuple(rv3d().view_location))
    drag('MIDDLEMOUSE', 150, 40)      # what Blender hands on for Alt+LMB with Emulate on


@step
def s_on_no_tumble():
    r = rv3d()
    check("Emulate on: the converted Alt+LMB (= plain MMB drag) does not tumble",
          tuple(r.view_rotation) == C["rot"])
    C["moved_view"] = (r.view_distance, tuple(r.view_location)) != C["view"]
    print("GUI note: plain MMB drag changed the view:", C["moved_view"], flush=True)
    # the same converted drag with the Alt key still held (Windows can tell): the kit tumbles (#242)
    import sim
    sim._down.add('LEFT_ALT')
    C["rot"] = tuple(r.view_rotation)
    drag('MIDDLEMOUSE', 150, 40)


@step
def s_on_alt_held_tumbles():
    import sim
    sim._down.discard('LEFT_ALT')
    check("Emulate on + Alt held: the converted Alt+LMB tumbles", tuple(rv3d().view_rotation) != C["rot"])


@step
def s_hint():
    prefs = import_module(MODULE + ".preferences")
    hint = prefs.emulate_hint()
    check("Emulate on: the kit has a hint", bool(hint) and "Emulate 3 Button" in hint)
    bpy.ops.allset.welcome('INVOKE_DEFAULT')    # the shot shows the hint as the dialog's last paragraph


@step
def s_wait():
    pass


@step
def s_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step267_welcome_emulate.png"))
    tap('ESC')
    bpy.context.preferences.inputs.use_mouse_emulate_3_button = False


run(interval=0.4, first=2.0)
