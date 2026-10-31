"""In a real UI (Maya Workflow Kit layout): red key ticks on the Time Slider at the keyed frames, and the
Range Slider bar dragged like Maya's (segment = move, end handle = that end, double-click = whole range)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, tap, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    path = os.path.join(SHOTS or os.path.join(os.environ.get("TEMP", "."), "gui73"), name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    screenshot(path)
    return path


def timeline():
    for area in win().screen.areas:
        if area.type == 'DOPESHEET_EDITOR' and area.spaces.active.mode == 'TIMELINE':
            return (area, next(r for r in area.regions if r.type == 'WINDOW'),
                    next(r for r in area.regions if r.type == 'HEADER'))
    raise LookupError("no timeline")


def rb():
    return import_module(MODULE + ".ui.range_bar")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def pixel(path, x, y):
    """RGB 0-255 of window pixel (x, y from the bottom) in a screenshot."""
    im = bpy.data.images.load(path, check_existing=False)
    w, _h = im.size
    i = (y * w + x) * 4
    px = im.pixels[i:i + 3]
    bpy.data.images.remove(im)
    return tuple(round(v * 255) for v in px)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    ob = bpy.data.objects["pCube1"]
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 200
    sc.frame_preview_start, sc.frame_preview_end = 1, 120
    sc.use_preview_range = True
    for f in (1, 12):
        ob.keyframe_insert("location", frame=f)
    sc.frame_set(30)
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    redraw()


@step
def s_wait():
    redraw()


@step
def s_ticks():
    _area, r, _h = timeline()
    # in the Maya layout a key tick sits on the frame's Maya tick, the left edge of its cell
    ts = import_module(MODULE + ".ui.time_slider")
    C["tick_x"] = {f: r.x + int(ts.key_x(r, f, True)) for f in (12, 20)}
    C["tick_y"] = r.y + r.height // 2
    redraw()


@step
def s_ticks_shot():
    path = shot("gui_step73_ticks.png")
    red = pixel(path, C["tick_x"][12], C["tick_y"])
    other = pixel(path, C["tick_x"][20], C["tick_y"])
    check(f"frame 12 key tick is red on the Time Slider ({red})", red[0] > 200 and red[1] < 60 and red[2] < 60)
    check(f"no tick at frame 20 ({other})", not (other[0] > 200 and other[1] < 60))
    area, _r, header = timeline()
    bar = rb()._bars.get(area.as_pointer())
    check(f"the Range Slider bar was found in the timeline header ({bar and (bar['x0'], bar['x1'])})",
          bar is not None and bar["x1"] - bar["x0"] > 100)
    if bar is None:
        return
    C["bar"], C["header"] = dict(bar), header
    xs, xe = rb().segment(bar, 1, 120)
    C["y"] = header.y + int((bar["y0"] + bar["y1"]) / 2)
    C["ppf"] = (bar["x1"] - bar["x0"]) / (bar["e"] - bar["s"])
    C["mid"] = header.x + int((xs + xe) / 2)
    C["end"] = header.x + int(xe) - 4
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"], y=C["y"])
    ev('LEFTMOUSE', 'PRESS', x=C["mid"], y=C["y"])


@step
def s_move():
    dx = int(round(30 * C["ppf"]))
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"] + dx // 2, y=C["y"])
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"] + dx, y=C["y"])


@step
def s_release():
    ev('LEFTMOUSE', 'RELEASE', x=C["mid"] + int(round(30 * C["ppf"])), y=C["y"])


@step
def s_moved():
    sc = bpy.context.scene
    got = (sc.frame_preview_start, sc.frame_preview_end)
    check(f"dragging the range segment 30 frames moves the playback range ({got})",
          sc.use_preview_range and got[1] - got[0] == 119 and 29 <= got[0] - 1 <= 31)
    C["after_move"] = got
    redraw()


@step
def s_moved_shot():
    shot("gui_step73_range_moved.png")
    xs, xe = rb().segment(C["bar"], *C["after_move"])
    C["end"] = C["header"].x + int(xe) - 4
    ev('MOUSEMOVE', 'NOTHING', x=C["end"], y=C["y"])
    ev('LEFTMOUSE', 'PRESS', x=C["end"], y=C["y"])


@step
def s_end_move():
    dx = -int(round(40 * C["ppf"]))
    ev('MOUSEMOVE', 'NOTHING', x=C["end"] + dx, y=C["y"])


@step
def s_end_release():
    ev('LEFTMOUSE', 'RELEASE', x=C["end"] - int(round(40 * C["ppf"])), y=C["y"])


@step
def s_end_done():
    sc = bpy.context.scene
    got = (sc.frame_preview_start, sc.frame_preview_end)
    a0, b0 = C["after_move"]
    check(f"dragging the end handle moves only the end ({(a0, b0)} -> {got})",
          got[0] == a0 and 38 <= b0 - got[1] <= 42)
    C["before_click"] = got
    tap_x = C["header"].x + int(C["bar"]["x0"]) + 60
    ev('MOUSEMOVE', 'NOTHING', x=tap_x, y=C["y"])
    ev('LEFTMOUSE', 'PRESS', x=tap_x, y=C["y"])
    ev('LEFTMOUSE', 'RELEASE', x=tap_x, y=C["y"])


@step
def s_click():
    sc = bpy.context.scene
    got = (sc.frame_preview_start, sc.frame_preview_end)
    check(f"a click without a drag changes nothing ({got})", got == C["before_click"])
    # Simulated events can't be DOUBLE_CLICK (event_simulate: PRESS/RELEASE only): run its action directly.
    rb().toggle_whole(sc)
    check(f"double-click action = whole animation range (preview range {sc.use_preview_range})",
          not sc.use_preview_range)
    redraw()


@step
def s_double_shot():
    shot("gui_step73_whole_range.png")
    _a, r, _h = timeline()
    check("the timeline follows the whole range (1-200 visible)",
          r.view2d.region_to_view(0, 0)[0] <= 2 and r.view2d.region_to_view(r.width, 0)[0] >= 198)


run()
