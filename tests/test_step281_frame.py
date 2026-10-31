"""#192: Graph Editor F / A frame Maya's rectangle (operators/graph_frame.py) and Auto Frame refits the
value axis only (ui/graph_view.py)."""

from importlib import import_module

import bpy

import kit

gf = import_module(kit.MODULE + ".operators.graph_frame")
graph_view = import_module(kit.MODULE + ".ui.graph_view")
preferences = import_module(kit.MODULE + ".preferences")

TOL = 1e-6


def _lin(*pts):
    """Linear keys (no handle widening)."""
    return [(t, v, v, v, False) for t, v in pts]


def _close(got, want, tol=TOL):
    assert all(abs(a - b) <= tol for a, b in zip(got, want)), (got, want)


# --- maths (Maya's numbers) -----------------------------------------------------------------------------------------

TY = _lin((1, -10), (30, 40))
SX = _lin((1, 0), (5, 4), (10, 6), (15, 2), (25, 8))


def test_bezier_segment_widened_by_its_handles():
    # a key's out handle at 10.833 lifts the box above the keys (Maya: control polygon max, not the curve peak)
    keys = [(0, 0.0, 0.0, 10.833, True), (10, 10.0, 10.0, 10.0, True)]
    _t0, _t1, _v0, v1 = gf.all_box([(keys, [])])
    assert abs(v1 - 10.833) < TOL
    # a linear segment ignores its handles
    keys = [(0, 0.0, 0.0, 10.833, False), (10, 10.0, 10.0, 10.0, True)]
    assert abs(gf.all_box([(keys, [])])[3] - 10.0) < TOL


def test_union_over_curves():
    _close(gf.maya_rect(gf.all_box([(TY, []), (SX, [])])), gf.maya_rect((1, 30, -10, 40)))


def test_view_for_keeps_the_ruler_and_scroll_bar_clear():
    x0, x1, y0, y1 = gf.view_for((0, 10, 0, 100), 500, 420, 20, 40)
    assert (x0, x1) == (0, 10)
    per_px = 100 / 360
    _close((y0, y1), (-20 * per_px, 100 + 40 * per_px))
    _close(gf.to_pixels((2, 4, 10, 30), (0, 0.5, 0, 2)), (4, 8, 5, 15))


# --- in Blender -----------------------------------------------------------------------------------------------------

def _scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    sc = bpy.context.scene
    sc.timeline_markers.clear()
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    for f, v in ((1, -10.0), (30, 40.0)):
        ob.location[1] = v
        ob.keyframe_insert("location", index=1, frame=f)
    for f, v in ((1, 0.0), (5, 4.0), (10, 6.0), (15, 2.0), (25, 8.0)):
        ob.scale[0] = v
        ob.keyframe_insert("scale", index=0, frame=f)
    for fc in kit.fcurves(ob):
        for p in fc.keyframe_points:
            p.interpolation = 'LINEAR'
    return ob


def _graph():
    w = bpy.context.window_manager.windows[0]
    area = max(w.screen.areas, key=lambda a: a.width * a.height)
    area.ui_type = 'FCURVES'
    area.spaces.active.dopesheet.show_only_selected = True
    region = next(r for r in area.regions if r.type == 'WINDOW')
    return w, area, region


def _canvas(region, area):
    """(t0, t1, v0, v1) the canvas between the ruler strip and the scroll bar shows."""
    w = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=w, area=area, region=region):
        bottom, top = gf.pads(bpy.context, area.spaces.active)
    v = region.view2d
    x0, y0 = v.region_to_view(0.0, bottom)
    w, h = gf.span_px(region)
    x1, y1 = v.region_to_view(float(w), h - top)
    return x0, x1, y0, y1


def _select_keys(ob, which):
    for fc in kit.fcurves(ob):
        for p in fc.keyframe_points:
            p.select_control_point = p.select_left_handle = p.select_right_handle = False
    for path, index, frames in which:
        for fc in kit.fcurves(ob):
            if fc.data_path == path and fc.array_index == index:
                for p in fc.keyframe_points:
                    p.select_control_point = p.co.x in frames


def _frame(mode, **kw):
    w, area, region = _graph()
    with bpy.context.temp_override(window=w, area=area, region=region):
        got = gf.frame(bpy.context, region, mode, **kw)
    assert got is not None
    return _canvas(region, area)


def _near(got, want, region, area, px=0.05):
    """Within ``px`` region pixels on every edge."""
    sx = (want[1] - want[0]) / region.width
    sy = (want[3] - want[2]) / region.height
    for g, wv, s in zip(got, want, (sx, sx, sy, sy)):
        assert abs(g - wv) <= px * s, (got, want)


def test_frame_all_reaches_maya_rect():
    ob = _scene()
    _w, area, region = _graph()
    _select_keys(ob, ())
    got = _frame('ALL')
    _near(got, gf.maya_rect((1, 30, -10, 40)), region, area)


def test_frame_from_far_views():
    """From a view far off / far zoomed in or out the frame still lands."""
    ob = _scene()
    w, area, region = _graph()
    _select_keys(ob, ())
    want = gf.maya_rect((1, 30, -10, 40))
    for view in ((5000, 5000.01, -3e4, -3e4 + 0.01), (-1e5, 1e5, -1e6, 1e6), (10, 11, 20, 21)):
        with bpy.context.temp_override(window=w, area=area, region=region):
            gf.apply_view(bpy.context, region, view)
        _near(_frame('ALL'), want, region, area)


def test_rotation_curves_in_degrees():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    for f, v in ((1, 0.0), (11, 1.0)):
        ob.rotation_euler[2] = v
        ob.keyframe_insert("rotation_euler", index=2, frame=f)
    _w, area, region = _graph()
    deg = 57.29577951308232
    _near(_frame('ALL'), gf.maya_rect((1, 11, 0, deg)), region, area)


def test_auto_frame_keeps_the_time_range():
    ob = _scene()
    w, area, region = _graph()
    with bpy.context.temp_override(window=w, area=area, region=region):
        gf.apply_view(bpy.context, region, (-4.0, 25.0, -100.0, 100.0))
    x0, x1, _y0, _y1 = gf.current_view(region)
    assert graph_view.frame_all(w, area, region)
    got = _canvas(region, area)
    _close(got[:2], (x0, x1), 1e-3)
    want = gf.maya_rect((1, 30, -10, 40))
    _near((x0, x1) + got[2:], (x0, x1) + want[2:], region, area)
    # Auto Frame Time alone: time refit, value kept
    _y = gf.current_view(region)[2:]
    assert graph_view.frame_time(w, area, region)
    got = _canvas(region, area)
    _near(got[:2] + (0, 1), want[:2] + (0, 1), region, area)
    _close(gf.current_view(region)[2:], _y, 1e-3)
    del ob


def test_auto_frame_step_refits_value_only():
    a = _scene()
    w, area, region = _graph()
    p = preferences.get(bpy.context)
    p.graph_auto_frame, p.graph_auto_frame_time = True, False
    for o in bpy.context.scene.objects:
        o.select_set(False)
    graph_view._state["sig"] = None
    graph_view.step(bpy.context, p)                       # baseline (nothing selected)
    with bpy.context.temp_override(window=w, area=area, region=region):
        gf.apply_view(bpy.context, region, (-4.0, 25.0, -100.0, 100.0))
    a.select_set(True)
    bpy.context.view_layer.objects.active = a
    assert graph_view.step(bpy.context, p) == 1
    x0, x1, _y0, _y1 = gf.current_view(region)
    assert abs(x0 + 4.0) < 1e-3 and abs(x1 - 25.0) < 1e-3, (x0, x1)
    got = _canvas(region, area)
    _near(got, (x0, x1) + gf.maya_rect((1, 30, -10, 40))[2:], region, area)


def test_operator_from_the_header_and_the_normalized_view():
    """The toolbar button / View menu run the operator from the header: it frames the editor's canvas. A normalised
    view keeps Blender's own frame."""
    if not hasattr(bpy.types, "ALLSET_OT_graph_frame"):     # before the operators package registers it
        bpy.utils.register_class(gf.ALLSET_OT_graph_frame)
    ob = _scene()
    w, area, region = _graph()
    _select_keys(ob, ())
    with bpy.context.temp_override(window=w, area=area, region=region):
        gf.apply_view(bpy.context, region, (100.0, 160.0, 300.0, 900.0))
    header = next(r for r in area.regions if r.type == 'HEADER')
    with bpy.context.temp_override(window=w, area=area, region=header):
        assert bpy.ops.allset.graph_frame(mode='ALL') == {'FINISHED'}
    _near(_canvas(region, area), gf.maya_rect((1, 30, -10, 40)), region, area)
    area.spaces.active.use_normalization = True
    try:
        with bpy.context.temp_override(window=w, area=area, region=region):
            assert bpy.ops.allset.graph_frame(mode='ALL') == {'FINISHED'}
        _x0, _x1, y0, y1 = gf.current_view(region)
        assert y0 < -1.0 and y1 > 1.0 and y1 - y0 < 4.0, (y0, y1)      # Blender's frame of the -1 .. 1 curves
    finally:
        area.spaces.active.use_normalization = False
