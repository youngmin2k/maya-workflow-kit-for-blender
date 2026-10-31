"""In a real UI: F / A / Ctrl+Shift+F / Shift+F fit 0.95 of the part of the view
not under the sidebar; hotbox rows stay inside the window."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def view_mod():
    return import_module(MODULE + ".operators.view")


def corners(obs):
    """Maya fits the axis-aligned bounding box of everything framed (fitPanel)."""
    pts = []
    for ob in obs:
        if ob.type == 'MESH':
            pts += [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        else:
            pts.append(ob.matrix_world.translation.copy())
    return import_module(MODULE + ".operators.framing").box_corners(pts)


def maya_fit(inside, ratio, persp=True):
    """Maya's perspective viewFit leaves more room than 0.95 (tests/test_step258_view.py);
    orthographic views still fill 0.95."""
    return inside and (0.5 < ratio < 0.95 if persp else abs(ratio - 0.95) < 0.03)


def fit_ratio(area, region, obs):
    """(inside, ratio) of the projected bounding box against the visible rect."""
    rv3d = region.data
    rect = view_mod().visible_bounds(area, region)
    pp = [location_3d_to_region_2d(region, rv3d, p) for p in corners(obs)]
    if any(p is None for p in pp):
        return False, 0.0
    xs, ys = [p.x for p in pp], [p.y for p in pp]
    inside = min(xs) >= rect[0] - 2 and max(xs) <= rect[2] + 2 and min(ys) >= rect[1] - 2 and max(ys) <= rect[3] + 2
    ratio = max((max(xs) - min(xs)) / (rect[2] - rect[0]), (max(ys) - min(ys)) / (rect[3] - rect[1]))
    return inside, ratio


def only(*names):
    for o in bpy.context.view_layer.objects:
        o.select_set(o.name in names)
    bpy.context.view_layer.objects.active = bpy.data.objects[names[0]]


@step
def s_setup():
    C["x"], C["y"] = setup()
    area, region = view3d()
    area.spaces.active.show_region_ui = True     # sidebar open, overlapping (factory)
    child = bpy.data.objects.new("far_child", None)
    bpy.context.scene.collection.objects.link(child)
    child.parent = bpy.data.objects["Cube"]
    child.location = (12.0, 0.0, 0.0)
    only("Cube")


@step
def s_press_f():
    area, region = view3d()
    C["x"] = region.x + int(view_mod().visible_bounds(area, region)[2] * 0.5)
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    tap('F')


@step
def s_f_drawn():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_f():
    area, region = view3d()
    rect = view_mod().visible_bounds(area, region)
    ui = next(r for r in area.regions if r.type == 'UI')
    # with Region Overlap (Blender's default) the rect stops at the sidebar; Maya mode turns overlap off
    # and the sidebar is beside the view region
    check(f"sidebar excluded from the visible rect ({rect[2]:.0f} of {region.width} px, sidebar at {ui.x - region.x})",
          region.x + rect[2] <= ui.x + 1)
    inside, ratio = fit_ratio(area, region, [bpy.data.objects["Cube"]])
    check(f"F: cube inside the visible part with Maya's margin (ratio {ratio:.3f})", maya_fit(inside, ratio))
    shot("step17_f.png")
    ev('F', 'PRESS', ctrl=True, shift=True)
    ev('F', 'RELEASE', ctrl=True, shift=True)


@step
def s_ctrl_shift_f_drawn():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_ctrl_shift_f():
    area, region = view3d()
    obs = [bpy.data.objects["Cube"], bpy.data.objects["far_child"]]
    inside, ratio = fit_ratio(area, region, obs)
    check(f"Ctrl+Shift+F: cube + child fit (ratio {ratio:.3f})", maya_fit(inside, ratio))
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    tap('A')


@step
def s_a_drawn():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_a():
    area, region = view3d()
    obs = [o for o in bpy.context.view_layer.objects if o.visible_get()]
    inside, ratio = fit_ratio(area, region, obs)
    check(f"A tap: everything fits (ratio {ratio:.3f})", maya_fit(inside, ratio))
    shot("step17_a.png")
    only("Cube")
    tap('SPACE')   # four views


@step
def s_quad_split():
    # the four view splits its top row one timer tick later; a key sent in the tick right
    # after a layout change can be lost under event simulation (gui_step4_view) — hover a tick first
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])


@step
def s_quad_hover():
    # the old Quad View had its four views meeting at the area centre; real panels have their own sidebars there
    panes = import_module(MODULE + ".ui.four_view").panes(win().screen)
    r = next(r for r in panes[0].regions if r.type == 'WINDOW')
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)


@step
def s_quad():
    ev('F', 'PRESS', shift=True)
    ev('F', 'RELEASE', shift=True)


@step
def s_quad_drawn():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_quad_check():
    # Four View = four real 3D View areas (ui/four_view.py), not one area's Quad View regions
    panes = import_module(MODULE + ".ui.four_view").panes(win().screen)
    pairs = [(a, next(r for r in a.regions if r.type == 'WINDOW')) for a in panes]
    regs = [r for _a, r in pairs]
    res = [fit_ratio(a, r, [bpy.data.objects["Cube"]]) for a, r in pairs]
    check(f"Shift+F frames the cube in all {len(regs)} views (ratios {[round(x[1], 3) for x in res]})",
          len(regs) == 4 and all(maya_fit(i, r, a.spaces.active.region_3d.is_perspective)
                                 for (i, r), (a, _r) in zip(res, pairs)))
    shot("step17_quad.png")
    persp = import_module(MODULE + ".ui.four_view").roles(win().screen).get("persp", pairs[0][0])
    r = next(r for r in persp.regions if r.type == 'WINDOW')
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    # back to one view through Tool Box > Single Perspective View (a Space tap here left the factory layout's view
    # without a hotbox on the next Space press; in the Maya layout it works)
    with bpy.context.temp_override(window=win(), area=persp, region=r):
        bpy.ops.allset.quick_layout(layout='SINGLE')


@step
def s_after_leave():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_after_leave2():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_hotbox_hover():
    # after the four view closed, a key in the same tick as the move is lost under event simulation
    area, region = view3d()
    rect = view_mod().visible_bounds(area, region)
    C["hx"] = region.x + int(rect[2]) - 30          # near the sidebar's left edge
    ev('MOUSEMOVE', 'NOTHING', x=C["hx"], y=C["y"])


@step
def s_hotbox():
    ev('SPACE', 'PRESS')


@step
def s_hotbox_wait():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_hotbox_wait2():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_hotbox_check():
    draw = import_module(MODULE + ".marking.draw")
    area, region = view3d()
    # Maya's hotbox floats over the whole window, sidebar included: rows stay in the window
    rect = draw.window_bounds(win(), region)
    lay = draw.ACTIVE.get("hotbox")
    xs = [r[2] for r, _k, _l in lay.labels] if lay else []
    check(f"hotbox rows end inside the window (max x {max(xs) if xs else -1:.0f} <= {rect[2]:.0f})",
          bool(xs) and max(xs) <= rect[2] + 1)
    shot("step17_hotbox.png")
    ev('SPACE', 'RELEASE')
    tap('ESC')


run()
