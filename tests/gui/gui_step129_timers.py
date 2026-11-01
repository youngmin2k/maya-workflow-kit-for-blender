"""#36: kit timers keep window / area pointers, not Window / Area objects. Each step opens a kit window
whose setup retries from a timer (Hypershade: sidebar tab; Light Editor: an Outliner window; Graph Editor: frame range; a torn-off
Channel Box and a torn-off menu: dock role) and closes it in the same step, before the timer's first tick. A timer
that kept the freed Window crashed Blender (EXCEPTION_ACCESS_VIOLATION). PASSES when Blender is still running 3 s
after the last close (longer than every retry loop: 100 x 0.05 s at most)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, dock_area, run, setup, step, view3d, win  # noqa: E402

C = {}


def mod(name):
    return import_module(MODULE + name)


def new_windows():
    return [w for w in bpy.context.window_manager.windows if w.as_pointer() not in C["before"]]


def remember():
    C["before"] = {w.as_pointer() for w in bpy.context.window_manager.windows}
    # kit windows reopen at their last place, which earlier GUI files in the same sandbox may have saved: such a
    # window opens a few ticks later (its place is carved out first), not in this step -- forget the places
    wp = mod(".ui.window_places")
    wp.place("")                      # loads the saved places
    wp._places.clear()


def close_new(label):
    new = new_windows()
    check(f"{label} opened a window", len(new) >= 1)
    for w in new:
        with bpy.context.temp_override(window=w):
            bpy.ops.wm.window_close()
    check(f"{label} window closed at once", not new_windows())


def in_view(fn, **kw):
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        return fn(**kw)


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    dock_area('CHANNEL_BOX')          # a tab stack for the tear-off step (role set from a timer)


@step
def s_hypershade():
    remember()
    in_view(bpy.ops.allset.hypershade)
    close_new("Hypershade")


@step
def s_light_editor():
    remember()
    in_view(bpy.ops.allset.light_editor)
    close_new("Light Editor")


@step
def s_graph_editor():
    remember()
    in_view(bpy.ops.allset.open_editor, ui_type='FCURVES')
    close_new("Graph Editor")


@step
def s_tear_panel():
    md = mod(".ui.maya_dock")
    stack = md.find_stack(win().screen)
    check("the tab stack exists", stack is not None)
    if stack is None:
        return
    remember()
    region = next(r for r in stack.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=win(), screen=win().screen, area=stack, region=region):
        md.tear_off(bpy.context, stack)


# a tear-off sizes its window first and opens it from a timer a tick later
step(lambda: None)
step(lambda: close_new("Torn-off Channel Box"))


@step
def s_tear_menu():
    md = mod(".ui.maya_dock")
    name = next((n for n in dir(bpy.types) if n.startswith("ALLSET_MT_") and "proxy" not in n
                 and getattr(getattr(bpy.types, n), "bl_label", "") == "File"), None)
    check("a Maya File menu class exists", name is not None)
    if name is None:
        return
    remember()
    with bpy.context.temp_override(window=win()):
        md.tear_menu(bpy.context, name, "File")


step(lambda: None)
step(lambda: close_new("Torn-off File menu"))


for _ in range(8):       # 8 x 0.4 s > 3 s: every retry timer has ticked on its closed window
    step(lambda: None)


@step
def s_alive():
    check("Blender still running 3 s after closing the windows (no timer touched a freed Window)", True)
    check("only the main window is left", len(bpy.context.window_manager.windows) == 1)


run()
