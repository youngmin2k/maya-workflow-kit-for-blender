"""In a real UI, Maya animation_01 hand order: frame 1 S -> LMB on the Time Slider at 24 -> move ->
S -> keys [1, 24] -> RMB on the Time Slider at 24 > Delete -> only frame 24's key goes -> K held + LMB drag in the
view moves the time and keeps the selection -> Shift+LMB drag highlights a red range -> MMB moves the time to 40
without updating the scene -> S keys the held pose at 40 -> LMB at 30 updates the scene again."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, px, run, scale, screenshot, setup, step, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def timeline():
    for area in win().screen.areas:
        if area.type == 'DOPESHEET_EDITOR' and area.spaces.active.mode == 'TIMELINE':
            return area, next(r for r in area.regions if r.type == 'WINDOW')
    raise LookupError("no timeline")


def tx(frame):
    """Window position of ``frame`` in the timeline body."""
    _area, r = timeline()
    x = r.view2d.view_to_region(frame, 0, clip=False)[0]
    return r.x + int(x), r.y + r.height // 2


def cube():
    return bpy.data.objects["Cube"]


def frames():
    ad = cube().animation_data
    if ad is None or ad.action is None:
        return []
    cb = import_module(MODULE + ".ui.channel_box")
    fc = cb._fcurves(cube()).find("location", index=0)
    return [round(k.co.x) for k in fc.keyframe_points] if fc else []


def hover_view():
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    setup()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 48
    sc.frame_set(1)
    for o in bpy.context.view_layer.objects:
        o.select_set(o.name == "Cube")
    bpy.context.view_layer.objects.active = cube()
    area, r = timeline()
    with bpy.context.temp_override(window=win(), area=area, region=r):
        bpy.ops.anim.scene_range_frame()      # the Maya time slider shows the playback range
    hover_view()


@step
def s_key_1():
    tap('S')


@step
def s_scrub_hover():
    check(f"S at frame 1 keyed translateX ({frames()})", frames() == [1])
    C["t24"] = tx(24)
    ev('MOUSEMOVE', 'NOTHING', x=C["t24"][0], y=C["t24"][1])


@step
def s_scrub_click():
    x, y = C["t24"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_moved_time():
    check(f"LMB on the Time Slider at 24 = time 24 ({bpy.context.scene.frame_current})",
          bpy.context.scene.frame_current == 24)
    cube().location.x += 2.0      # W move (other GUI tests drag the manipulator)
    hover_view()


@step
def s_key_24():
    tap('S')


@step
def s_rmb_hover():
    check(f"second S keyed frame 24 ({frames()})", frames() == [1, 24])
    x, y = C["t24"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_rmb():
    x, y = C["t24"]
    ev('RIGHTMOUSE', 'PRESS', x=x, y=y)
    ev('RIGHTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_menu_shot():
    shot("gui_step56_time_slider_menu.png")
    # Delete by its underlined key (the menu opens upward at the window bottom, rows move)
    tap('D')


@step
def s_deleted():
    check(f"RMB > Delete at 24 removed only frame 24's key ({frames()})", frames() == [1])
    hover_view()
    C["sel"] = sorted(o.name for o in bpy.context.selected_objects)
    C["frame0"] = bpy.context.scene.frame_current
    ev('K', 'PRESS')


@step
def s_k_click():
    _a, r = view3d()
    C["k0"] = (r.x + r.width // 2, r.y + r.height // 2)
    ev('LEFTMOUSE', 'PRESS', x=C["k0"][0], y=C["k0"][1])


@step
def s_k_drag():
    x, y = C["k0"]
    ev('MOUSEMOVE', 'NOTHING', x=x + px(150), y=y)


@step
def s_k_drag2():
    x, y = C["k0"]
    ev('MOUSEMOVE', 'NOTHING', x=x + px(300), y=y)
    redraw()


@step
def s_k_release():
    shot("gui_step56_k_drag.png")
    x, y = C["k0"]
    ev('LEFTMOUSE', 'RELEASE', x=x + px(300), y=y)
    ev('K', 'RELEASE')


@step
def s_k_done():
    f = bpy.context.scene.frame_current
    check(f"K + LMB drag right moved the time {C['frame0']} -> {f}", f > C["frame0"])
    check("... and kept the selection (the LMB went to the time dragger)",
          sorted(o.name for o in bpy.context.selected_objects) == C["sel"])
    C["t10"], C["t30"] = tx(10), tx(30)
    ev('MOUSEMOVE', 'NOTHING', x=C["t10"][0], y=C["t10"][1])


@step
def s_range_press():
    x, y = C["t10"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y, shift=True)


@step
def s_range_drag():
    x, y = C["t30"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y, shift=True)


@step
def s_range_release():
    x, y = C["t30"]
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y, shift=True)
    redraw()


@step
def s_range_check():
    wm = bpy.context.window_manager
    check(f"Shift+LMB drag highlighted 10..30 ({tuple(wm.allset_time_range)}, on={wm.allset_time_range_on})",
          wm.allset_time_range_on and tuple(wm.allset_time_range) == (10, 30))
    redraw()


@step
def s_range_shot():
    shot("gui_step56_range.png")
    x, y = tx(40)
    C["t40"] = (x, y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_mmb():
    # a far key so frame 40 evaluates to another pose than the one held
    ob, scene = cube(), bpy.context.scene
    held = tuple(ob.location)
    ob.location = (held[0] + 8.0, held[1], held[2])
    ob.keyframe_insert("location", frame=100)
    scene.frame_set(scene.frame_current)
    C["held"] = tuple(round(v, 4) for v in ob.location)
    x, y = C["t40"]
    ev('MIDDLEMOUSE', 'PRESS', x=x, y=y)
    ev('MIDDLEMOUSE', 'RELEASE', x=x, y=y)


@step
def s_mmb_check():
    ob = cube()
    now = tuple(round(v, 4) for v in ob.location)
    check(f"MMB on the Time Slider: time 40 ({bpy.context.scene.frame_current})",
          bpy.context.scene.frame_current == 40)
    check(f"MMB keeps the pose ({now} == {C['held']})", now == C["held"])
    wm = bpy.context.window_manager
    check("a plain click drops the range", not wm.allset_time_range_on)
    hover_view()


@step
def s_mmb_key():
    tap('S')


@step
def s_mmb_key_check():
    check(f"S keys the held pose at 40 ({frames()})", 40 in frames())
    ob, scene = cube(), bpy.context.scene
    fc = import_module(MODULE + ".ui.channel_box")._fcurves(ob).find("location", index=0)
    check(f"the key at 40 holds the pose ({fc.evaluate(40):.4f})", abs(fc.evaluate(40) - C["held"][0]) < 1e-3)
    x, y = tx(30)
    C["t30"] = (x, y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_lmb_after():
    x, y = C["t30"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_lmb_after_check():
    ob = cube()
    fc = import_module(MODULE + ".ui.channel_box")._fcurves(ob).find("location", index=0)
    check(f"LMB updates the scene again (frame {bpy.context.scene.frame_current}, x {ob.location.x:.4f})",
          bpy.context.scene.frame_current == 30 and abs(ob.location.x - fc.evaluate(30)) < 1e-4)


run()
