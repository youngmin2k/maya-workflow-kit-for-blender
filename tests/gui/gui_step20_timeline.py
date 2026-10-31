"""In a real UI: . , Alt+. Alt+, over the 3D View and the Timeline; Maya Workflow Kit template
timeline shows the playback range and follows it; Range Slider header."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, tap, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def scene():
    return bpy.context.scene


def timeline():
    for a in win().screen.areas:
        if a.type == 'DOPESHEET_EDITOR' and a.spaces.active.mode == 'TIMELINE':
            return a, next(r for r in a.regions if r.type == 'WINDOW')
    return None, None


def view_range():
    _a, r = timeline()
    x0 = r.view2d.region_to_view(0, r.height // 2)[0]
    x1 = r.view2d.region_to_view(r.width, r.height // 2)[0]
    return x0, x1


def combo(key, **mods):
    ev(key, 'PRESS', **mods)
    ev(key, 'RELEASE', **mods)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    C["x"], C["y"] = setup()
    cube = bpy.data.objects["Cube"]
    for f in (1, 10):
        scene().frame_set(f)
        cube.keyframe_insert("location")
    scene().frame_set(1)
    tap('PERIOD')


@step
def s_next_key():
    check(f"'.' over the 3D View: next key (frame {scene().frame_current})", scene().frame_current == 10)
    check("no pie / modal opened", not list(win().modal_operators))
    tap('COMMA')


@step
def s_prev_key():
    check(f"',' : previous key (frame {scene().frame_current})", scene().frame_current == 1)
    combo('PERIOD', alt=True)


@step
def s_next_frame():
    check(f"Alt+. : next frame ({scene().frame_current})", scene().frame_current == 2)
    combo('COMMA', alt=True)


@step
def s_prev_frame():
    check(f"Alt+, : previous frame ({scene().frame_current})", scene().frame_current == 1)
    _a, r = timeline()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    tap('PERIOD')


@step
def s_timeline_key():
    check(f"'.' over the Timeline: next key ({scene().frame_current})", scene().frame_current == 10)
    load_maya_layout()


@step
def s_template():
    import_module(MODULE + ".keymap").activate()   # --factory-startup: template reload resets prefs
    redraw()


@step
def s_template_wait():
    redraw()


@step
def s_template_range():
    s = scene()
    check(f"Maya Workflow Kit ranges: animation {s.frame_start}-{s.frame_end}, playback "
          f"{s.frame_preview_start}-{s.frame_preview_end}",
          (s.frame_start, s.frame_end, s.use_preview_range, s.frame_preview_start, s.frame_preview_end)
          == (1, 200, True, 1, 120))
    x0, x1 = view_range()
    check(f"timeline shows the playback range (view {x0:.1f} .. {x1:.1f})", -8 <= x0 <= 2 and 118 <= x1 <= 130)
    shot("step20_timeline.png")
    s.frame_preview_end = 60


@step
def s_follow_wait():
    redraw()


@step
def s_follow():
    x0, x1 = view_range()
    check(f"changing playback end to 60 refits the timeline (view {x0:.1f} .. {x1:.1f})", 58 <= x1 <= 66)
    scene().frame_preview_end = 120


run()
