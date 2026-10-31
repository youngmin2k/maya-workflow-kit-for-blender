"""PR #125 follow-up (#36 crash class): the joint watchers PR #125 added (``allset.pose_empty_click``
in 3D Views, ``allset.joint_outliner_select`` in Outliners, the Channel Box wheel watcher, the armature mode ticks)
must not keep Window / Area objects across timer ticks. A second window is opened, the watchers start in it, each
click watcher schedules its deferred check, and the window closes before the check runs. The checks used to read
``win.screen`` of the freed window (EXCEPTION_ACCESS_VIOLATION). PASSES when Blender is still running afterwards."""

import os
import sys
from importlib import import_module
from types import SimpleNamespace

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, setup, step, view3d, win  # noqa: E402

C = {}


def mod(name):
    return import_module(MODULE + name)


def second():
    return next((w for w in bpy.context.window_manager.windows if w.as_pointer() == C.get("ptr")), None)


def area_of(w, kind):
    area = max((a for a in w.screen.areas if a.type == kind), key=lambda a: a.width * a.height, default=None)
    region = next((r for r in area.regions if r.type == 'WINDOW'), None) if area else None
    return area, region


def click(region, value):
    return SimpleNamespace(type='LEFTMOUSE', value=value, shift=False, ctrl=False, alt=False, oskey=False,
                           mouse_region_x=region.width // 2, mouse_region_y=region.height // 2)


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    bpy.ops.object.armature_add()            # an armature selected: the pose / pulse ticks have work to do


@step
def s_open():
    before = {w.as_pointer() for w in bpy.context.window_manager.windows}
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.window_new()
    new = [w for w in bpy.context.window_manager.windows if w.as_pointer() not in before]
    check("a second window opened", len(new) == 1)
    C["ptr"] = new[0].as_pointer() if new else None


@step
def s_outliner():
    w = second()            # Window > New Window shows one 3D View: split an Outliner off it
    area, region = area_of(w, 'VIEW_3D')
    before = {a.as_pointer() for a in w.screen.areas}
    with bpy.context.temp_override(window=w, screen=w.screen, area=area, region=region):
        bpy.ops.screen.area_split(direction='VERTICAL', factor=0.3)
    new = next((a for a in w.screen.areas if a.as_pointer() not in before), None)
    check("an area split off in the second window", new is not None)
    if new is not None:
        new.ui_type = 'OUTLINER'


for _ in range(4):       # the watchers start from 1 s timers
    step(lambda: None)


def _close_soon():
    """Close the second window before the deferred checks run (the checks wait 0.06 s)."""
    w = second()
    if w is not None:
        with bpy.context.temp_override(window=w):
            bpy.ops.wm.window_close()
    return None


@step
def s_click_then_close():
    w = second()
    check("the second window is still open", w is not None)
    if w is None:
        return
    tb = mod(".ui.toolbox")
    scheduled = []
    real = bpy.app.timers.register

    def spy(fn, *a, **kw):
        scheduled.append(fn.__name__)
        return real(fn, *a, **kw)
    bpy.app.timers.register = spy
    try:
        area, region = area_of(w, 'VIEW_3D')
        with bpy.context.temp_override(window=w, area=area, region=region):
            me = SimpleNamespace(_area_ptr=area.as_pointer(), _press=None)
            tb.ALLSET_OT_pose_empty_click.modal(me, bpy.context, click(region, 'PRESS'))
            tb.ALLSET_OT_pose_empty_click.modal(me, bpy.context, click(region, 'RELEASE'))
        area, region = area_of(w, 'OUTLINER')
        C["types"] = [a.type for a in w.screen.areas]
        if area is not None:
            with bpy.context.temp_override(window=w, area=area, region=region):
                me = SimpleNamespace(_area_ptr=area.as_pointer())
                tb.ALLSET_OT_joint_outliner_select.modal(me, bpy.context, click(region, 'RELEASE'))
    finally:
        bpy.app.timers.register = real
    check(f"the viewport and Outliner watchers scheduled their checks ({scheduled}, areas {C['types']})",
          "check" in scheduled and "after_selection" in scheduled)
    real(_close_soon, first_interval=0.0)


@step
def s_closed():
    check("the second window closed", second() is None)


for _ in range(6):       # > the 0.06 s checks, the 0.18 s armature tick, the 0.25 s wheel watch and 1 s watch ticks
    step(lambda: None)


@step
def s_alive():
    check("Blender still running after closing a window with the PR #125 watchers in it", True)


run()
