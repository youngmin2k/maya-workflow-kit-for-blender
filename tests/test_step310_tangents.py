"""Issue #210: Maya Spline / Clamped / Plateau / Flat tangent shapes.

Each Maya tangent type has its own slope rule; handles sit at a third of each interval. The kit keeps the Maya type
per key side on the Action and writes the handles again after Blender edits the curve."""

from importlib import import_module

import bpy

import kit

mt = import_module(kit.MODULE + ".operators.maya_tangents")
time_keys = import_module(kit.MODULE + ".operators.time_keys")
compat = import_module(kit.MODULE + ".compat")


def _fresh(name="n"):
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for act in list(bpy.data.actions):
        bpy.data.actions.remove(act)
    ob = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _curve(ob, keys, path="location", index=2):
    for f, v in keys:
        if path.startswith('["'):
            ob[path[2:-2]] = v
            ob.keyframe_insert(path, frame=f)
        else:
            getattr(ob, path)[index] = v
            ob.keyframe_insert(path, index=index, frame=f)
    return next(fc for fc in compat.id_fcurves(ob) if fc.data_path == path
                and (path.startswith('["') or fc.array_index == index))


def _set(fc, kind):
    for kp in fc.keyframe_points:
        time_keys.apply_tangent(kp, kind, fc)
    fc.update()
    mt.apply(fc)


def _slopes(fc):
    out = []
    for kp in fc.keyframe_points:
        out.append((mt._slope(kp, 0), mt._slope(kp, 1)))
    return out


def _thirds(fc):
    """Every handle sits a third of its interval from its key."""
    pts = fc.keyframe_points
    times = [kp.co.x for kp in pts]
    for k, kp in enumerate(pts):
        h0, h1 = mt._intervals(times, k)
        assert abs((kp.co.x - kp.handle_left.x) - h0 / 3) < 1e-4, (k, kp.handle_left[:], h0)
        assert abs((kp.handle_right.x - kp.co.x) - h1 / 3) < 1e-4, (k, kp.handle_right[:], h1)


def _near(got, want, tol=1e-5):
    assert len(got) == len(want), (got, want)
    for (a, b), m in zip(got, want):
        assert abs(a - m) < tol and abs(b - m) < tol, (got, want)


def test_rules_pure():
    T, V = [0, 10, 30], [0, 4, 10]
    assert [mt.spline_slope(T, V, k) for k in range(3)] == [0.4, 1 / 3, 0.3]
    T, V = [0, 10, 12, 20], [0, 2, 2.04, 5]
    assert [mt.clamped_slope(T, V, k) for k in range(4)] == [0.2, 0.0, 0.0, (5 - 2.04) / 8]
    V = [0, 2, 2.06, 5]
    assert abs(mt.clamped_slope(T, V, 1) - 2.06 / 12) < 1e-12
    kinds = [("PLATEAU", "PLATEAU")] * 3
    assert mt.solve([0, 10, 20], [0, 5, 0], kinds) == [(0.0, 0.0)] * 3              # extreme
    _near(mt.solve([0, 10, 20], [0, 1, 2], kinds), [0, 0.1, 0])
    assert mt.solve([0, 1, 20], [0, 9, 10], kinds)[1] == (0.0, 0.0)                  # would overshoot 10


def test_spline_curve():
    ob = _fresh()
    fc = _curve(ob, [(0, 0), (10, 4), (30, 10)])
    _set(fc, "SPLINE")
    _near(_slopes(fc), [0.4, 1 / 3, 0.3])
    _thirds(fc)
    assert all(kp.handle_left_type == 'AUTO' for kp in fc.keyframe_points)


def test_clamped_curve_and_units():
    ob = _fresh()
    fc = _curve(ob, [(0, 0), (10, 2), (12, 2.04), (20, 5)], path='["c"]')
    _set(fc, "CLAMPED")
    _near(_slopes(fc), [0.2, 0, 0, (5 - 2.04) / 8])
    _thirds(fc)
    # a length curve compares in display units (a centimetre scene stores 0.01 m per unit)
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'CENTIMETERS', 1.0
    try:
        ob = _fresh()
        fc = _curve(ob, [(0, 0), (10, 0.02), (12, 0.0206), (20, 0.05)])
        mt.forget()
        _set(fc, "CLAMPED")
        assert abs(_slopes(fc)[1][0] - 0.0206 / 12) < 1e-6, _slopes(fc)          # 0.06 Maya units apart
        ob2 = _fresh()
        fc = _curve(ob2, [(0, 0), (10, 0.02), (12, 0.0204), (20, 0.05)])
        _set(fc, "CLAMPED")
        assert abs(_slopes(fc)[1][0]) < 1e-9, _slopes(fc)                         # 0.04 Maya units apart
    finally:
        us.length_unit, us.scale_length = 'METERS', 1.0
        mt.forget()


def test_plateau_curve_and_types_kept():
    ob = _fresh()
    fc = _curve(ob, [(0, 0), (10, 1), (20, 2), (21, 9), (40, 10)], path='["p"]')
    _set(fc, "PLATEAU")
    s = _slopes(fc)
    assert abs(s[1][0] - 0.1) < 1e-6 and abs(s[2][0]) < 1e-9, s
    act = ob.animation_data.action
    assert act[mt.PROP]['["p"]|0']["t"] == "PP" * 5
    # Blender recomputes its own automatic handles on any curve update: the watch writes Maya's again
    for kp in fc.keyframe_points:
        kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'
    fc.update()
    mt.watch()
    s2 = _slopes(fc)
    assert all(abs(a[0] - b[0]) < 1e-6 for a, b in zip(s, s2)), (s, s2)


def test_flat_follows_moved_key():
    ob = _fresh()
    fc = _curve(ob, [(0, 0), (10, 5), (30, 0)], path='["f"]')
    _set(fc, "FLAT")
    _thirds(fc)
    kp = fc.keyframe_points[1]
    for attr in ("co", "handle_left", "handle_right"):      # a Blender key move carries the handles along
        x, y = getattr(kp, attr)
        setattr(kp, attr, (x + 6, y))
    fc.update()
    mt.watch()
    kp = fc.keyframe_points[1]          # update() reallocates the keys: look the key up again
    assert abs(kp.co.x - 16) < 1e-6, [p.co[:] for p in fc.keyframe_points]
    _thirds(fc)
    _near(_slopes(fc), [0, 0, 0])


def test_user_handle_edit_is_kept():
    ob = _fresh()
    fc = _curve(ob, [(0, 0), (10, 1), (20, 2)], path='["u"]')
    _set(fc, "CLAMPED")
    kp = fc.keyframe_points[1]
    kp.handle_left_type = kp.handle_right_type = 'ALIGNED'     # what a handle drag does
    kp.handle_right = (kp.co.x + 3, kp.co.y + 3)
    kp.handle_left = (kp.co.x - 3, kp.co.y - 3)
    mt.watch()
    assert abs(mt._slope(kp, 1) - 1.0) < 1e-6
    assert ob.animation_data.action[mt.PROP]['["u"]|0']["t"] == "CC--CC"


def test_one_side_and_key_count_change():
    ob = _fresh()
    fc = _curve(ob, [(0, 0), (10, 4), (30, 10)], path='["s"]')
    graph_keys = import_module(kit.MODULE + ".operators.graph_keys")
    _set(fc, "SPLINE")
    graph_keys.apply_side(fc, 1, "FLAT", "OUT")
    fc.update()
    mt.apply(fc)
    s = _slopes(fc)
    assert abs(s[1][0] - 1 / 3) < 1e-6 and abs(s[1][1]) < 1e-9, s
    # a new key: the stored Flat side follows its key by frame
    ob["s"] = 12.0
    ob.keyframe_insert('["s"]', frame=40)
    fc.update()
    mt.apply(fc)
    s = _slopes(fc)
    assert abs(s[1][1]) < 1e-9 and abs(s[2][0] - (12 - 4) / 30) < 1e-6, s
