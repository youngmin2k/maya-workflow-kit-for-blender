"""#277 IPR in a real UI: Maya Workflow Kit layout -> IPR (the Status Line / Render menu operator) opens a second
window with a 3D View in Rendered shading that looks where the main view looks, the main view keeps its own shading,
the IPR view follows when the main view turns, the IPR button looks pressed, and IPR again closes the window.
Screenshots: gui_issue277_ipr_window.png, gui_issue277_ipr_main.png."""

import os
import sys
from importlib import import_module

import bpy
from mathutils import Quaternion

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, setup, step, win  # noqa: E402

GUI_TIMEOUT = 240
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(MODULE + name)


def v3d():
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def shot(name, window):
    if SHOTS:
        with bpy.context.temp_override(window=window):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def wait(fn, cond, limit=150):
    """Run ``fn`` again next tick until ``cond()`` or ``limit`` ticks."""
    C.setdefault(fn.__name__, 0)
    if not cond() and C[fn.__name__] < limit:
        C[fn.__name__] += 1
        sys.modules["sim"]._steps.insert(0, fn)
        return True
    return False


def ipr_toggle():
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        return bpy.ops.allset.ipr_toggle()


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_open():
    area, _r = v3d()
    space = area.spaces.active
    space.shading.type = 'SOLID'
    C["windows"] = len(bpy.context.window_manager.windows)
    C["ret"] = ipr_toggle()


@step
def s_opened():
    ipr = mod(".ui.ipr_window")
    if wait(s_opened, lambda: ipr.view_area(ipr.window()) is not None):
        return
    w = ipr.window()
    a = ipr.view_area(w)
    check(f"IPR opens one more window ({C['windows']} -> {len(bpy.context.window_manager.windows)}, {C['ret']})",
          a is not None and len(bpy.context.window_manager.windows) == C["windows"] + 1)
    if a is None:
        return
    sp = a.spaces.active
    main = v3d()[0].spaces.active
    check(f"the IPR view is in Rendered shading ({sp.shading.type}), overlays off ({sp.overlay.show_overlays})",
          sp.shading.type == 'RENDERED' and not sp.overlay.show_overlays)
    check(f"the main view keeps its shading ({main.shading.type})", main.shading.type == 'SOLID')
    diff = sp.region_3d.view_rotation.rotation_difference(main.region_3d.view_rotation).angle
    check(f"the IPR view looks where the main view looks (angle {diff:.5f})",
          diff < 1e-4 and abs(sp.region_3d.view_distance - main.region_3d.view_distance) < 1e-4)
    sl = mod(".ui.status_line")
    check("the Status Line IPR button looks pressed", sl._ipr_on(main))
    main.region_3d.view_rotation = Quaternion((0.8, 0.4, 0.2, 0.4)).normalized()
    C["turned"] = main.region_3d.view_rotation.copy()


@step
def s_follows():
    ipr = mod(".ui.ipr_window")
    a = ipr.view_area(ipr.window())

    def same():
        return a is not None and a.spaces.active.region_3d.view_rotation.rotation_difference(C["turned"]).angle < 1e-4
    if wait(s_follows, same, limit=60):
        return
    check("the IPR view follows when the main view turns", same())
    shot("gui_issue277_ipr_window.png", ipr.window())
    shot("gui_issue277_ipr_main.png", win())
    C["ret2"] = ipr_toggle()


@step
def s_closed():
    ipr = mod(".ui.ipr_window")
    if wait(s_closed, lambda: len(bpy.context.window_manager.windows) == C["windows"], limit=60):
        return
    main = v3d()[0].spaces.active
    check(f"IPR again closes the window ({C['ret2']}, {len(bpy.context.window_manager.windows)} windows)",
          len(bpy.context.window_manager.windows) == C["windows"] and not ipr.is_open())
    check(f"the main view still has its shading ({main.shading.type})", main.shading.type == 'SOLID')
    check("the IPR button is no longer pressed", not mod(".ui.status_line")._ipr_on(main))
    C["ret3"] = ipr_toggle()


@step
def s_os_close():
    ipr = mod(".ui.ipr_window")
    if wait(s_os_close, lambda: ipr.window() is not None):
        return
    with bpy.context.temp_override(window=ipr.window()):
        bpy.ops.wm.window_close()


@step
def s_os_closed():
    ipr = mod(".ui.ipr_window")
    check(f"closing the IPR window itself turns IPR off ({len(bpy.context.window_manager.windows)} windows)",
          not ipr.is_open() and len(bpy.context.window_manager.windows) == C["windows"])


run()
