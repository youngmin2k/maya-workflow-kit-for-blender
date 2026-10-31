"""Audit 128 (UI lane), GitHub issue #3: double-clicking a Tool Box tool icon (Maya: opens that tool's Tool
Settings Tool Box) should open the Tool Settings dock. event_simulate can't send
DOUBLE_CLICK, so this sends two press/release pairs on the Move icon in one tick (and,
as a second try, in two ticks 0.2 s apart). PASSES when the Tool Settings dock is shown afterwards.
Screenshot: audit128_toolbox_dbl.png."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sim import MODULE, check, ev, find_button, run, setup, step, win, _steps, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 200
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(MODULE + name)


def toolbox_area():
    tb = mod(".ui.toolbox")
    return next((a for a in win().screen.areas if tb.is_toolbox(a.spaces.active)), None)


def tools_where():
    tb = mod(".ui.toolbox")
    area = toolbox_area()
    r = next(r for r in area.regions if r.type == 'TOOLS')
    if r.width >= tb.column_width() - 1:
        return area, r
    main = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    return main, next(r for r in main.regions if r.type == 'TOOLS')


def dock_shown():
    return mod(".ui.tool_dock").find(win().screen) is not None


def shot(name):
    if SHOTS:
        with bpy.context.temp_override(window=win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_prep():
    bpy.ops.allset.keymap_activate()
    C["before"] = dock_shown()
    print("AUDIT128 tool dock before", C["before"])


step(find_button(tools_where, lambda path, cmd: "builtin.move" in cmd, C, "move", step_px=6, x_frac=0.5))


@step
def s_hover():
    print("AUDIT128 move button", C.get("move"))
    check("the Move icon is found in the Tool Box", C.get("move") is not None)
    if C.get("move"):
        ev('MOUSEMOVE', 'NOTHING', x=C["move"][0], y=C["move"][1])


@step
def s_double():
    if not C.get("move"):
        return
    x, y = C["move"]
    for _ in range(2):
        ev('LEFTMOUSE', 'PRESS', x=x, y=y)
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_wait():
    pass


@step
def s_check():
    tool = bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode).idname
    print("AUDIT128 active tool", tool, "dock", dock_shown())
    check(f"the double click made Move the active tool ({tool})", tool == "builtin.move")
    check("double-clicking the Move icon in the Tool Box opens Tool Settings (Maya)",
          not C["before"] and dock_shown())
    shot("audit128_toolbox_dbl.png")


run(interval=0.2)
