"""Blender 5.x pass — unified paint settings (#90), menus that stay open (5.0), radial submenus open only
from their own sector."""

import math
from importlib import import_module

import bpy

import kit

compat = import_module(kit.MODULE + ".compat")
engine = import_module(kit.MODULE + ".marking.engine")
mm = import_module(kit.MODULE + ".marking.menus")


def test_unified_paint_settings_radius_round_trip():
    ts = bpy.context.scene.tool_settings
    ups = compat.unified_paint_settings(ts, "weight_paint")
    assert isinstance(ups, bpy.types.UnifiedPaintSettings)
    compat.set_unprojected_radius(ups, 0.35)
    assert abs(compat.unprojected_radius(ups) - 0.35) < 1e-6
    assert abs(ups.unprojected_size - 0.7) < 1e-6                 # 5.x stores the diameter
    ups.weight = 0.25
    assert abs(compat.unified_paint_settings(ts).weight - 0.25) < 1e-6


def test_menus_close_on_leave():
    view = bpy.context.preferences.view
    want = view.menu_close_leave
    assert compat.menus_close_on_leave(bpy.context.preferences) == want


def _measure(text):
    return 7.0 * len(text)


def test_diagonal_gesture_through_a_wide_north_box():
    # Move Options: N = Symmetry (a submenu) is a Maya-wide box that reaches into the NE sector (Maya ring geometry)
    p = engine.Params()
    origin = (500.0, 400.0)
    s = engine.Session(mm.OPT_MOVE, origin, 0.0, _measure, p)
    n = s.stack[0][0].radial["N"]
    assert n.sub is not None
    # a point of the N box past the ring, in the NE sector
    x0, y0, x1, y1 = n.rect
    pt = None
    for yy in range(int(y0) + 1, int(y1)):
        for xx in range(int(x1) - 1, 0, -1):
            if math.hypot(xx, yy) >= p.radius and engine.direction(xx, yy, p.dead) == "NE":
                pt = (xx, yy)
                break
        if pt:
            break
    assert pt is not None, f"N box {n.rect} doesn't reach the NE sector"
    s.move(origin[0] + pt[0] / 2, origin[1] + pt[1] / 2, 0.05)
    s.move(origin[0] + pt[0], origin[1] + pt[1], 0.1)
    assert len(s.stack) == 1, "crossing the N box on a NE stroke opened the N submenu"
    far = max(pt) * 2
    res = s.release(origin[0] + far, origin[1] + far, 0.2)
    assert res and res[0] == "RUN" and res[1].label == "Component", res


def test_straight_stroke_still_opens_the_radial_submenu():
    p = engine.Params()
    origin = (500.0, 400.0)
    s = engine.Session(mm.OPT_MOVE, origin, 0.0, _measure, p)
    s.move(origin[0], origin[1] + p.radius + 15, 0.1)
    assert len(s.stack) == 2
