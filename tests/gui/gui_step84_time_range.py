"""In a real UI: Shift-drag a Time Slider range, drag its middle = move the keys (range follows, overwrite),
undo once, drag the right end arrow = scale the keys from the left end, a click on the range = plain click;
screenshot of the range arrows."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
KEYS = ((1, 0.0), (12, 5.0), (15, -2.0), (20, 8.0), (30, 1.0))


def timeline():
    for area in win().screen.areas:
        if area.type == 'DOPESHEET_EDITOR' and area.spaces.active.mode == 'TIMELINE':
            return area, next(r for r in area.regions if r.type == 'WINDOW')
    raise LookupError("no timeline")


def tx(frame):
    _area, r = timeline()
    return r.x + int(r.view2d.view_to_region(frame, 0, clip=False)[0]), r.y + r.height // 2


def cube():
    return bpy.data.objects["Cube"]


def keys():
    fc = import_module(MODULE + ".ui.channel_box")._fcurves(cube()).find("location", index=0)
    return [(round(k.co.x), round(k.co.y, 3)) for k in fc.keyframe_points]


def wm():
    return bpy.context.window_manager


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def drag(x0, x1, shift=False):
    def s1():
        if shift:
            ev('LEFT_SHIFT', 'PRESS')
        ev('MOUSEMOVE', 'NOTHING', x=x0()[0], y=x0()[1], shift=shift)

    def s2():
        ev('LEFTMOUSE', 'PRESS', shift=shift)

    def s3():
        a, b = x0(), x1()
        ev('MOUSEMOVE', 'NOTHING', x=(a[0] + b[0]) // 2, y=a[1], shift=shift)

    def s4():
        ev('MOUSEMOVE', 'NOTHING', x=x1()[0], y=x1()[1], shift=shift)

    def s5():
        ev('LEFTMOUSE', 'RELEASE', shift=shift)
        if shift:
            ev('LEFT_SHIFT', 'RELEASE')
    for s in (s1, s2, s3, s4, s5):
        step(s)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    bpy.ops.allset.create(kind='CUBE')
    bpy.context.active_object.name = "Cube"
    _a, r = timeline()
    print("TIMELINE region", r.x, r.y, r.width, r.height)
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 48
    for o in bpy.context.view_layer.objects:
        o.select_set(o.name == "Cube")
    bpy.context.view_layer.objects.active = cube()
    for f, v in KEYS:
        cube().location.x = v
        cube().keyframe_insert("location", index=0, frame=f)
    sc.frame_set(1)
    area, r = timeline()
    with bpy.context.temp_override(window=win(), area=area, region=r):
        bpy.ops.anim.scene_range_frame()
    bpy.ops.ed.undo_push(message="keys")
    redraw()


drag(lambda: tx(10), lambda: tx(16), shift=True)


@step
def s_range():
    check(f"Shift-drag highlights 10-16 ({tuple(wm().allset_time_range)})",
          wm().allset_time_range_on and tuple(sorted(wm().allset_time_range)) == (10, 16))
    redraw()


@step
def s_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step84_range_arrows.png"))


drag(lambda: tx(13), lambda: tx(18))


@step
def s_move_check():
    check(f"middle drag +5: keys 12 15 -> 17 20, the old 20 overwritten ({keys()})",
          keys() == [(1, 0.0), (17, 5.0), (20, -2.0), (30, 1.0)])
    check(f"the range follows: 15-21 ({tuple(wm().allset_time_range)})",
          tuple(sorted(wm().allset_time_range)) == (15, 21))
    with bpy.context.temp_override(window=win()):
        bpy.ops.ed.undo()


@step
def s_undo_check():
    check(f"one undo = before the drag ({keys()})", keys() == list(KEYS))
    wm().allset_time_range = (10, 16)
    wm().allset_time_range_on = True
    redraw()


def right_end():
    _a, r = timeline()
    ts = import_module(MODULE + ".ui.time_slider")
    _x0, x1 = ts.range_rect(r, 10, 16)
    return r.x + int(x1) - 3, r.y + r.height // 2


drag(right_end, lambda: tx(22))


@step
def s_scale_check():
    check(f"right end drag 16 -> 22: keys scale x2 from 10 (12 -> 14, 15 -> 20 overwriting 20) ({keys()})",
          keys() == [(1, 0.0), (14, 5.0), (20, -2.0), (30, 1.0)])
    check(f"range 10-22 ({tuple(wm().allset_time_range)})", tuple(sorted(wm().allset_time_range)) == (10, 22))


@step
def s_click_hover():
    ev('MOUSEMOVE', 'NOTHING', x=tx(15)[0], y=tx(15)[1])


@step
def s_click():
    ev('LEFTMOUSE', 'PRESS')
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_click_check():
    check(f"a click on the range = plain click: range off, time 15 ({bpy.context.scene.frame_current})",
          not wm().allset_time_range_on and bpy.context.scene.frame_current == 15
          and keys() == [(1, 0.0), (14, 5.0), (20, -2.0), (30, 1.0)])


run()
