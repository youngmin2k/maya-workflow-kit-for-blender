"""Alt+RMB dolly follows Blender's Invert Zoom Direction preference (#295), in the 3D View and the UV / Image
Editor. The wheel stays Blender's own zoom, which reads its own Invert Wheel Zoom Direction preference."""

from importlib import import_module
from types import SimpleNamespace

import bpy

import kit

view = import_module(kit.MODULE + ".operators.view")


def test_dolly_maths_reverse_with_invert():
    d = view.dolly_distance
    assert d(10.0, 150, 0) < 10.0 < d(10.0, -150, 0), "default: drag right = in"
    assert d(10.0, 150, 0, invert=True) > 10.0 > d(10.0, -150, 0, invert=True), "inverted: drag right = out"
    assert abs(d(10.0, 150, 0, invert=True) - d(10.0, -150, 0)) < 1e-9
    f = view.dolly_zoom_factor
    assert f(150, 0) > 1.0 > f(150, 0, invert=True)
    assert abs(f(90, 30, invert=True) - 1.0 / d(1.0, 90, 30, invert=True)) < 1e-9, "2D and 3D still agree"


def test_invert_zoom_reads_blender_preference():
    inputs = bpy.context.preferences.inputs
    old = inputs.invert_mouse_zoom
    try:
        for value in (False, True):
            inputs.invert_mouse_zoom = value
            assert view.invert_zoom(bpy.context) is value
    finally:
        inputs.invert_mouse_zoom = old


def test_dolly_modal_follows_preference():
    """Run the 3D dolly's modal with a fake drag under a 3D View override, both preference values."""
    win = bpy.context.window_manager.windows[0]
    area = max(win.screen.areas, key=lambda a: a.width * a.height)
    old_type = area.ui_type
    inputs = bpy.context.preferences.inputs
    old_inv = inputs.invert_mouse_zoom
    try:
        area.ui_type = 'VIEW_3D'
        region = next(r for r in area.regions if r.type == 'WINDOW')
        rv3d = area.spaces.active.region_3d
        rv3d.view_perspective = 'PERSP'

        class Event:
            def __init__(self, type_, value, x, y):
                self.type, self.value, self.mouse_x, self.mouse_y = type_, value, x, y

        results = {}
        for value in (False, True):
            inputs.invert_mouse_zoom = value
            rv3d.view_distance = 10.0
            op = SimpleNamespace(_start=(100, 100), _d0=10.0, _button='RIGHTMOUSE')
            with bpy.context.temp_override(window=win, area=area, region=region, space_data=area.spaces.active):
                ctx = bpy.context
                view.ALLSET_OT_dolly.modal(op, ctx, Event('MOUSEMOVE', 'NOTHING', 250, 100))
            results[value] = rv3d.view_distance
        assert results[False] < 10.0 < results[True], results
    finally:
        inputs.invert_mouse_zoom = old_inv
        area.ui_type = old_type
