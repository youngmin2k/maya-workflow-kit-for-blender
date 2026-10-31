"""Maya dock grey and Time Slider current-time block (dock #444444,
current-time block #525252). The pixel results are checked by look-comparison shots
(compare_s195_*); here the rules behind them."""

from importlib import import_module

import bpy

import kit

dock = import_module(kit.MODULE + ".ui.maya_dock")
ts = import_module(kit.MODULE + ".ui.time_slider")
prefs = import_module(kit.MODULE + ".preferences")


def test_dock_lift_reaches_maya_grey():
    back = max(tuple(bpy.context.preferences.themes[0].properties.space.back)[:3])
    d = dock.dock_lift(bpy.context)
    assert abs(back + d - 0x44 / 255) < 1e-6, (back, d)
    assert abs(round((back + d) * 255) - 0x44) == 0
    prefs.get().maya_dock_colors = False
    try:
        assert dock.dock_lift(bpy.context) == 0.0
    finally:
        prefs.get().maya_dock_colors = True


def test_dock_lift_skips_light_themes():
    th = bpy.context.preferences.themes[0]
    keep = tuple(th.properties.space.back)
    try:
        th.properties.space.back = (0.6, 0.6, 0.6)
        assert dock.dock_lift(bpy.context) == 0.0, "a light theme is never lifted"
    finally:
        th.properties.space.back = keep


def test_list_hole_geometry():
    assert dock._around(None, 100, 200) == [(0, 0, 100, 200)]
    parts = dock._around((10, 5, 90, 60), 100, 200)
    area = sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in parts)
    assert area == 100 * 200 - 80 * 55
    assert dock.dark_span([60, 60, 30, 31, 70, 30, 60], 44) == (2, 5)
    assert dock.dark_span([60, 60], 44) is None
    # a selected (light) layer row inside the list doesn't end the block; a long light run does
    col = [30] * 10 + [90] * 5 + [30] * 10 + [70] * 40 + [30] * 3
    assert dock.dark_top(col, 2, 44, 8) == 24
    assert dock.dark_top(col, 2, 44, 3) == 9


def test_current_time_block_is_maya_grey():
    a = ts.RULER_CURRENT[3]
    over = 0x2b + a * (0xff - 0x2b)
    assert round(over) == 0x52, over
