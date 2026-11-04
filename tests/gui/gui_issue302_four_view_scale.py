"""Issue #302: Space tap on a high-DPI screen split the viewport again and again.

At larger UI scales the gaps between the four panels are wider, the four view was not found, and every tap split the
panel under the mouse into four more. Here: at UI scale 1, 2 and 3 a Space tap gives four panels, the next tap over
a panel keeps that panel alone, the next tap gives four again (never more than four 3D View panels)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, setup, step, view3d, win  # noqa: E402

C = {}
SCALES = (1.0, 2.0, 3.0)


def fv():
    return import_module(f"{MODULE}.ui.four_view")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def tap(area):
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active,
                                   region_data=region.data):
        return bpy.ops.allset.toggle_quad_view()


def gaps(placed):
    """Horizontal and vertical px between the four panels."""
    t, p, f, s = (placed[r] for r in ("top", "persp", "front", "side"))
    return (p.x - (t.x + t.width), t.y - (f.y + f.height), s.x - (f.x + f.width), p.y - (s.y + s.height))


@step
def s_setup():
    setup()
    load_maya_layout()
    C["scale0"] = bpy.context.preferences.view.ui_scale


for _ in range(5):
    step(redraw)


def one_scale(scale):
    @step
    def s_scale():
        bpy.context.preferences.view.ui_scale = scale
        redraw()

    for _ in range(3):
        step(redraw)

    @step
    def s_enter():
        panes = fv().panes(win().screen)
        check(f"scale {scale}: one panel before ({len(panes)})", len(panes) == 1)
        tap(panes[0])
        redraw()

    for _ in range(4):
        step(redraw)

    @step
    def s_four():
        screen = win().screen
        n = len(fv().panes(screen))
        placed = fv().block(screen)
        g = gaps(placed or fv().roles(screen, fv().panes(screen)))
        print(f"ISSUE302 scale={scale} pixel_size={bpy.context.preferences.system.pixel_size} panes={n} gaps={g}")
        check(f"scale {scale}: four panels ({n})", n == 4)
        check(f"scale {scale}: the four view is found (gaps {g})", len(placed) == 4)
        tap(placed.get("persp") or fv().panes(screen)[0])
        redraw()

    for _ in range(4):
        step(redraw)

    @step
    def s_single():
        n = len(fv().panes(win().screen))
        check(f"scale {scale}: tap in the four view keeps one panel ({n})", n == 1)


for _s in SCALES:
    one_scale(_s)


@step
def s_restore():
    bpy.context.preferences.view.ui_scale = C["scale0"]


run()
