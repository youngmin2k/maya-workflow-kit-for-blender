"""Maya 2026's Dope Sheet keys (Maya 2026: g frames the playback range, t centres the current
time, h / j lock / unlock the selected channels, a / f stay Blender's frame all / selected). In the Timeline (Maya's
Time Slider, not a Dope Sheet) the kit key passes, so g stays the window key there.
Shots (ALLSET_GUI_SHOTS): gui_step269_dope_sheet.png."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, screenshot, setup, step, view3d  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def area():
    return C["area"]


def region():
    return next(r for r in area().regions if r.type == 'WINDOW')


def v2d_span():
    r = region()
    return r.view2d.region_to_view(0, 0)[0], r.view2d.region_to_view(r.width, 0)[0]


def hover():
    r = region()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)


def fcurves(ob):
    from importlib import import_module
    from sim import MODULE
    return list(import_module(MODULE + ".compat").id_fcurves(ob))


@step
def s_setup():
    setup()
    scene = bpy.context.scene
    ob = bpy.context.active_object or next(o for o in scene.objects if o.type == 'MESH')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    for f in (1, 40):
        scene.frame_set(f)
        ob.location.x = f * 0.1
        ob.keyframe_insert("location", index=0)
    scene.frame_start, scene.frame_end = 1, 100
    scene.frame_set(70)
    a, _r = view3d()
    a.ui_type = 'DOPESHEET'
    C["area"] = a
    C["ob"] = ob


@step
def s_select_channel():
    space = area().spaces.active
    space.mode = 'DOPESHEET'
    for fc in fcurves(C["ob"]):
        fc.select = True
        fc.lock = False
    hover()


@step
def s_g():
    C["span0"] = v2d_span()
    ev('G', 'PRESS')
    ev('G', 'RELEASE')


@step
def s_g_check():
    lo, hi = v2d_span()
    check(f"g frames the playback range 1-100 ({lo:.1f}, {hi:.1f})", lo <= 1 and hi >= 100 and (hi - lo) < 160)
    ev('T', 'PRESS')
    ev('T', 'RELEASE')


@step
def s_t_check():
    lo, hi = v2d_span()
    check(f"t centres the current time 70 ({lo:.1f}, {hi:.1f})", abs((lo + hi) / 2 - 70) < 3)
    ev('H', 'PRESS')
    ev('H', 'RELEASE')


@step
def s_h_check():
    locks = [fc.lock for fc in fcurves(C["ob"])]
    check(f"h locks the selected channels ({locks})", locks and all(locks))
    ev('J', 'PRESS')
    ev('J', 'RELEASE')


@step
def s_j_check():
    locks = [fc.lock for fc in fcurves(C["ob"])]
    check(f"j unlocks them ({locks})", locks and not any(locks))
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step269_dope_sheet.png"))
    space = area().spaces.active
    space.mode = 'TIMELINE'


@step
def s_timeline():
    hover()
    C["frames"] = (bpy.context.scene.frame_start, bpy.context.scene.frame_end)
    C["span0"] = v2d_span()
    ev('G', 'PRESS')
    ev('G', 'RELEASE')


@step
def s_timeline_check():
    with bpy.context.temp_override(area=area(), region=region(), space_data=area().spaces.active):
        polled = bpy.ops.allset.dope_sheet_key.poll()
    check(f"in the Timeline the Dope Sheet key passes (poll {polled})", not polled)


run(interval=0.4, first=2.0)
