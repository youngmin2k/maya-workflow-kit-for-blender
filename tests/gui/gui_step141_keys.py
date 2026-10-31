"""With simulated events: Alt+RMB drag in the UV Editor zooms like Maya's dolly — right =
in, left = out — with Blender's Zoom Axis preference left at its factory Vertical."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, setup, step, view3d, win  # noqa: E402

C = {}


def area():
    return next(a for a in win().screen.areas if a.as_pointer() == C["area"])


def zoom():
    return area().spaces.active.zoom[0]


def centre():
    r = next(r for r in area().regions if r.type == 'WINDOW')
    return r.x + r.width // 2, r.y + r.height // 2


def drag(dx, dy=0):
    x, y = centre()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('RIGHTMOUSE', 'PRESS', x=x, y=y, alt=True)
    ev('MOUSEMOVE', 'NOTHING', x=x + dx // 2, y=y + dy // 2, alt=True)
    ev('MOUSEMOVE', 'NOTHING', x=x + dx, y=y + dy, alt=True)
    ev('RIGHTMOUSE', 'RELEASE', x=x + dx, y=y + dy, alt=True)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_setup():
    setup()
    a, _r = view3d()
    C["area"] = a.as_pointer()
    a.ui_type = 'UV'


@step
def s_uv_ready():
    check("the viewport became a UV Editor", area().type == 'IMAGE_EDITOR')
    check("Blender's Zoom Axis preference is factory Vertical (the kit doesn't set it)",
          bpy.context.preferences.inputs.view_zoom_axis == 'VERTICAL')
    x, y = centre()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_measure():
    C["z0"] = zoom()
    drag(120)


@step
def s_wait_in():
    pass   # the zoom getter reads the view: one redraw


@step
def s_in():
    z = zoom()
    check(f"Alt+RMB drag right zooms in ({C['z0']:.3f} -> {z:.3f})", z > C["z0"] * 1.2)
    C["z1"] = z
    drag(-240)


@step
def s_wait_out():
    pass


@step
def s_out():
    z = zoom()
    check(f"Alt+RMB drag left zooms out ({C['z1']:.3f} -> {z:.3f})", z < C["z1"] / 1.5)
    check("back past the start: the same px per doubling both ways", z < C["z0"])
    C["z2"] = z
    drag(0, 0)


@step
def s_click_no_change():
    pass


@step
def s_still():
    check("Alt+RMB without a drag leaves the zoom", abs(zoom() - C["z2"]) < 1e-6 * max(C["z2"], 1.0))


run()
