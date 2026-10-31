"""Maya buffer curves (Snapshot / Swap / Show Buffer Curves) and weighted / non-weighted tangents,
tangent length locks (operators/graph_buffers.py, operators/graph_weights.py).

Maya results. Scene: pCube1.tx keys (1,0) (5,2) (10,5) (15,3) (25,8) at 24 fps;
``ix / iy / ox / oy`` = Maya keyTangent queries (3 x the arm in seconds / value for weighted curves, a unit
direction for non-weighted ones), ``eval`` = the curve value at t = 1, 1.25, ... 25.
"""


import math
from importlib import import_module

import bpy

import kit

gw = import_module(kit.MODULE + ".operators.graph_weights")
gb = import_module(kit.MODULE + ".operators.graph_buffers")
preferences = import_module(kit.MODULE + ".preferences")

FPS = 24
KEYS = ((1, 0.0), (5, 2.0), (10, 5.0), (15, 3.0), (25, 8.0))
TIMES = [x / 4.0 for x in range(4, 101)]
# Maya buffer results: key 10 set to 9, swap -> 5, swap -> 9; key 5 moved to 6, swap -> times back
AFTER_SWAP = (0.0, 2.0, 5.0, 3.0, 8.0)
AFTER_SWAP2 = (0.0, 2.0, 9.0, 3.0, 8.0)
SWAP_AFTER_TIME_MOVE = ((1.0, 5.0, 10.0, 15.0, 25.0), (0.0, 2.0, 5.0, 3.0, 8.0))

MAYA = {
    'to_weighted': {
        "weighted": True,
        'ix': (0.166666666667, 0.166666666667, 0.208333333333, 0.208333333333, 0.416666666667),
        'iy': (0.0, 2.222222222222, 0.0, 0.0, 0.0),
        'ox': (0.166666666667, 0.208333333333, 0.208333333333, 0.416666666667, 0.416666666667),
        'oy': (0.0, 2.777777777778, 0.0, 0.0, 0.0),
        "eval": (
            0.0, 0.0143229167, 0.0555555556, 0.12109375, 0.2083333333, 0.3146701389, 0.4375, 0.57421875,
            0.7222222222, 0.87890625, 1.0416666667, 1.2078993056, 1.375, 1.5403645833, 1.7013888889, 1.85546875,
            2.0, 2.1470972222, 2.309, 2.4832916667, 2.6675555556, 2.859375, 3.0563333333, 3.2560138889,
            3.456, 3.653875, 3.8472222222, 4.033625, 4.2106666667, 4.3759305556, 4.527, 4.6614583333,
            4.7768888889, 4.870875, 4.941, 4.9848472222, 5.0, 4.9855, 4.944, 4.8785,
            4.792, 4.6875, 4.568, 4.4365, 4.296, 4.1495, 4.0, 3.8505,
            3.704, 3.5635, 3.432, 3.3125, 3.208, 3.1215, 3.056, 3.0145,
            3.0, 3.00921875, 3.03625, 3.08015625, 3.14, 3.21484375, 3.30375, 3.40578125,
            3.52, 3.64546875, 3.78125, 3.92640625, 4.08, 4.24109375, 4.40875, 4.58203125,
            4.76, 4.94171875, 5.12625, 5.31265625, 5.5, 5.68734375, 5.87375, 6.05828125,
            6.24, 6.41796875, 6.59125, 6.75890625, 6.92, 7.07359375, 7.21875, 7.35453125,
            7.48, 7.59421875, 7.69625, 7.78515625, 7.86, 7.91984375, 7.96375, 7.99078125,
            8.0,
        ),
    },
    'edited_weights': {
        "weighted": True,
        'ix': (0.166666666667, 0.054634829758, 0.208333333333, 0.208333333333, 0.416666666667),
        'iy': (0.0, 0.728464396768, 0.0, 0.0, 0.0),
        'ox': (0.166666666667, 0.655617957091, 0.208333333333, 0.416666666667, 0.416666666667),
        'oy': (0.0, 8.741572761215, 0.0, 0.0, 0.0),
        "eval": (
            0.0, 0.0183964314, 0.066800705, 0.1380528189, 0.2274652523, 0.3317659375, 0.4485575509, 0.5760134961,
            0.7126932283, 0.8574213198, 1.0092003654, 1.1671378696, 1.3303669527, 1.4979240854, 1.6684748012, 1.8393902343,
            2.0, 2.1397841185, 2.2814697884, 2.4252447907, 2.5713308489, 2.7199929342, 2.8715521222, 3.0264037973,
            3.185044175, 3.3481102363, 3.5164422292, 3.6911859885, 3.8739692458, 4.0672215781, 4.2747656566, 4.5026066606,
            4.7529971951, 4.9397492984, 4.9890076671, 4.9986829519, 5.0, 4.9855, 4.944, 4.8785,
            4.792, 4.6875, 4.568, 4.4365, 4.296, 4.1495, 4.0, 3.8505,
            3.704, 3.5635, 3.432, 3.3125, 3.208, 3.1215, 3.056, 3.0145,
            3.0, 3.00921875, 3.03625, 3.08015625, 3.14, 3.21484375, 3.30375, 3.40578125,
            3.52, 3.64546875, 3.78125, 3.92640625, 4.08, 4.24109375, 4.40875, 4.58203125,
            4.76, 4.94171875, 5.12625, 5.31265625, 5.5, 5.68734375, 5.87375, 6.05828125,
            6.24, 6.41796875, 6.59125, 6.75890625, 6.92, 7.07359375, 7.21875, 7.35453125,
            7.48, 7.59421875, 7.69625, 7.78515625, 7.86, 7.91984375, 7.96375, 7.99078125,
            8.0,
        ),
    },
    'locked_angle_change': {
        "weighted": True,
        'ix': (0.166666666667, 0.047877777368, 0.208333333333, 0.208333333333, 0.416666666667),
        'iy': (0.0, 0.964181363583, 0.0, 0.0, 0.0),
        'ox': (0.166666666667, 0.574533332339, 0.208333333333, 0.416666666667, 0.416666666667),
        'oy': (0.0, 11.570176974358, 0.0, 0.0, 0.0),
    },
    'back_nonweighted': {
        "weighted": False,
        'ix': (1.0, 0.049595294618, 1.0, 1.0, 1.0),
        'iy': (0.0, 0.998769396183, 0.0, 0.0, 0.0),
        'ox': (1.0, 0.049595292342, 1.0, 1.0, 1.0),
        'oy': (0.0, 0.998769396296, 0.0, 0.0, 0.0),
        "eval": (
            0.0, 0.0101694396, 0.040049241, 0.0886966286, 0.1551688264, 0.2385230586, 0.3378165495, 0.4521065231,
            0.5804502037, 0.7219048154, 0.8755275825, 1.040375729, 1.2155064792, 1.3999770572, 1.5928446872, 1.7931665934,
            2.0, 2.2110718543, 2.4238353506, 2.6369371126, 2.849023764, 3.0587419282, 3.2647382289, 3.4656592898,
            3.6601517344, 3.8468621865, 4.0244372695, 4.1915236071, 4.346767823, 4.4888165407, 4.6163163838, 4.7279139761,
            4.822255941, 4.8979889022, 4.9537594834, 4.9882143081, 5.0, 4.9855, 4.944, 4.8785,
            4.792, 4.6875, 4.568, 4.4365, 4.296, 4.1495, 4.0, 3.8505,
            3.704, 3.5635, 3.432, 3.3125, 3.208, 3.1215, 3.056, 3.0145,
            3.0, 3.00921875, 3.03625, 3.08015625, 3.14, 3.21484375, 3.30375, 3.40578125,
            3.52, 3.64546875, 3.78125, 3.92640625, 4.08, 4.24109375, 4.40875, 4.58203125,
            4.76, 4.94171875, 5.12625, 5.31265625, 5.5, 5.68734375, 5.87375, 6.05828125,
            6.24, 6.41796875, 6.59125, 6.75890625, 6.92, 7.07359375, 7.21875, 7.35453125,
            7.48, 7.59421875, 7.69625, 7.78515625, 7.86, 7.91984375, 7.96375, 7.99078125,
            8.0,
        ),
    },
}


class Editor:
    """A Graph Editor in the first area for the duration of a with block (test_step157 helper)."""

    def __enter__(self):
        self.area = bpy.context.window_manager.windows[0].screen.areas[0]
        self.old = self.area.ui_type
        self.area.ui_type = 'FCURVES'
        region = next(r for r in self.area.regions if r.type == 'WINDOW')
        self.ctx = bpy.context.temp_override(area=self.area, region=region)
        self.ctx.__enter__()
        return self

    def __exit__(self, *exc):
        self.ctx.__exit__(*exc)
        self.area.ui_type = self.old


def _clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def _cube():
    _clear()
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    for frame, x in KEYS:
        ob.location.x = x
        ob.keyframe_insert("location", index=0, frame=frame)
    fc = _tx(ob)
    for kp in fc.keyframe_points:
        kp.select_control_point = kp.select_left_handle = kp.select_right_handle = False
    return ob, fc


def _tx(ob):
    return next(fc for fc in kit.fcurves(ob) if fc.data_path == "location" and fc.array_index == 0)


def _maya_curve(state):
    """pCube1.tx with FREE handles made from Maya's tangents of ``state`` (weighted: arm = (ix * fps / 3, iy / 3);
    non-weighted: direction ix / iy with a time extent of a third of the interval)."""
    ob, fc = _cube()
    m = MAYA[state]
    pts = fc.keyframe_points
    for i, kp in enumerate(pts):
        kp.handle_left_type = kp.handle_right_type = 'FREE'
        if m["weighted"]:
            left = (m["ix"][i] * FPS / 3, m["iy"][i] / 3)
            right = (m["ox"][i] * FPS / 3, m["oy"][i] / 3)
        else:
            dl = gw.third(fc, i, 0)
            dr = gw.third(fc, i, 1)
            left = (dl, dl * m["iy"][i] / m["ix"][i] / FPS)
            right = (dr, dr * m["oy"][i] / m["ox"][i] / FPS)
        x, y = kp.co
        kp.handle_left = (x - left[0], y - left[1])
        kp.handle_right = (x + right[0], y + right[1])
    return ob, fc


def _err(fc, values, lo=None, hi=None):
    worst = 0.0
    for t, v in zip(TIMES, values):
        if (lo is not None and t < lo) or (hi is not None and t > hi):
            continue
        worst = max(worst, abs(fc.evaluate(t) - v))
    return worst


def _handles(fc):
    return [(tuple(kp.co), tuple(kp.handle_left), tuple(kp.handle_right)) for kp in fc.keyframe_points]


def _close(a, b, tol):
    return all(abs(x - y) <= tol for pa, pb in zip(a, b) for va, vb in zip(pa, pb) for x, y in zip(va, vb)) \
        and len(a) == len(b)


# --- Maya weight <-> Blender handle -------------------------------------------------------------------------

def test_maya_weighted_tangents_evaluate_like_maya():
    _ob, fc = _maya_curve("to_weighted")
    assert _err(fc, MAYA["to_weighted"]["eval"]) < 1e-4, _err(fc, MAYA["to_weighted"]["eval"])
    # weight w at angle a = the arm length / angle in (frame, value): key 5 out = (5/3 frames, 0.9259)
    kp = fc.keyframe_points[1]
    dx, dy = kp.handle_right[0] - kp.co[0], kp.handle_right[1] - kp.co[1]
    assert abs(math.hypot(dx, dy) - 1.906598174256852) < 1e-5
    assert abs(math.degrees(math.atan2(dy, dx)) - 29.054604099077146) < 1e-4

    _ob, fc = _maya_curve("edited_weights")
    ev = MAYA["edited_weights"]["eval"]
    assert _err(fc, ev, hi=5) < 1e-4 and _err(fc, ev, lo=10) < 1e-4, (_err(fc, ev, hi=5), _err(fc, ev, lo=10))
    # key 5's out weight 6 reaches past key 10 (5.24 frames in a 5-frame interval): Maya evaluates the plain Bezier,
    # Blender shortens a handle that reaches past the segment's other key to end at that key before evaluating - a
    # known gap (only arms longer than their whole interval differ)
    kp = fc.keyframe_points[1]
    assert kp.handle_right[0] > fc.keyframe_points[2].co[0]
    assert _err(fc, ev, lo=5, hi=10) > 1e-2
    # ... which the buffer sampler models: its corrected Bezier lies on Blender's curve
    rec = gb.read_keys(fc)
    for x, y in gb.sample(rec, steps=40):
        assert abs(fc.evaluate(x) - y) < 1e-4, (x, y, fc.evaluate(x))


def test_non_weighted_tangents_match_maya():
    ob, fc = _maya_curve("locked_angle_change")          # edited weights + key 5 out at 40 degrees, weighted
    with Editor():
        assert fc in list(bpy.context.visible_fcurves)
        assert bpy.ops.allset.curve_weights(weighted=False) == {'FINISHED'}
    assert not gw.is_weighted(fc)
    ev = MAYA["back_nonweighted"]["eval"]
    assert _err(fc, ev) < 1e-4, _err(fc, ev)
    kp = fc.keyframe_points[1]
    assert abs(kp.handle_right[0] - kp.co[0] - 5 / 3) < 1e-5 and abs(kp.co[0] - kp.handle_left[0] - 4 / 3) < 1e-5
    assert abs(math.degrees(math.atan2(kp.handle_right[1] - kp.co[1], 5 / 3)) - 40.0) < 1e-4


def test_weighted_tangents_keep_the_shape():
    ob, fc = _maya_curve("edited_weights")
    before = _handles(fc)
    with Editor():
        assert bpy.ops.allset.curve_weights(weighted=True) == {'FINISHED'}
    assert gw.is_weighted(fc)
    assert _close(before, _handles(fc), 1e-9)
    # a non-weighted curve made weighted keeps its shape too (Maya to_weighted == nonweighted)
    with Editor():
        bpy.ops.allset.curve_weights(weighted=False)
        mid = _handles(fc)
        bpy.ops.allset.curve_weights(weighted=True)
    assert _close(mid, _handles(fc), 1e-9)


def test_watch_keeps_non_weighted_arms_at_a_third():
    _clear()
    assert gw.watch(bpy.context) == 0, "nothing marked: nothing to do"
    ob, fc = _maya_curve("to_weighted")
    gw.set_weighted(fc, False)
    kp = fc.keyframe_points[1]
    kp.handle_right = (kp.co[0] + 3.0, kp.co[1] + 2.0)          # drag the out arm long, slope 2/3
    assert gw.watch(bpy.context) >= 1
    dx, dy = kp.handle_right[0] - kp.co[0], kp.handle_right[1] - kp.co[1]
    assert abs(dx - 5 / 3) < 1e-5 and abs(dy / dx - 2 / 3) < 1e-5, (dx, dy)
    assert gw.watch(bpy.context) == 0, "stable after one pass"
    # weighted curves are left alone
    gw.set_weighted(fc, True)
    kp.handle_right = (kp.co[0] + 3.0, kp.co[1] + 2.0)
    gw.watch(bpy.context)
    assert abs(kp.handle_right[0] - kp.co[0] - 3.0) < 1e-5


def test_watch_keeps_locked_lengths():
    ob, fc = _maya_curve("edited_weights")
    kp = fc.keyframe_points[1]
    kp.select_control_point = True
    with Editor():
        assert bpy.ops.allset.tangent_weight_lock(lock=True) == {'FINISHED'}
    assert set(gw.locks(fc)) == {1}
    # turn the out tangent to 40 degrees at another length: the weight (6.0) comes back, the angle stays
    a = math.radians(40.0)
    kp.handle_right = (kp.co[0] + 2.0 * math.cos(a), kp.co[1] + 2.0 * math.sin(a))
    assert gw.watch(bpy.context) >= 1
    dx, dy = kp.handle_right[0] - kp.co[0], kp.handle_right[1] - kp.co[1]
    assert abs(math.hypot(dx, dy) - 6.0) < 1e-5 and abs(math.degrees(math.atan2(dy, dx)) - 40.0) < 1e-4
    # Maya locked_angle_change: out arm = (ox * fps / 3, oy / 3)
    m = MAYA["locked_angle_change"]
    assert abs(dx - m["ox"][1] * FPS / 3) < 1e-5 and abs(dy - m["oy"][1] / 3) < 1e-5, (dx, dy)
    left = math.hypot(kp.handle_left[0] - kp.co[0], kp.handle_left[1] - kp.co[1])
    assert abs(left - 0.5) < 1e-5
    # the key moves (same key count): the lock follows it
    for p in (kp,):
        p.co[0] += 0.5
        p.handle_left[0] += 0.5
        p.handle_right[0] += 0.5
    kp.handle_right = (kp.co[0] + 1.0, kp.co[1] + 1.0)
    gw.watch(bpy.context)
    assert abs(math.hypot(kp.handle_right[0] - kp.co[0], kp.handle_right[1] - kp.co[1]) - 6.0) < 1e-5
    assert abs(gw.locks(fc)[1][0] - 5.5) < 1e-5
    # free: dragging changes the length again
    with Editor():
        assert bpy.ops.allset.tangent_weight_lock(lock=False) == {'FINISHED'}
    assert not gw.locks(fc)
    kp.handle_right = (kp.co[0] + 1.0, kp.co[1] + 1.0)
    gw.watch(bpy.context)
    assert abs(kp.handle_right[0] - kp.co[0] - 1.0) < 1e-5
    # no key selected: Maya's warning, nothing done
    kp.select_control_point = False
    with Editor():
        assert bpy.ops.allset.tangent_weight_lock(lock=True) == {'CANCELLED'}


def test_watch_skips_auto_handles_and_never_raises():
    ob, fc = _cube()                                    # Blender AUTO_CLAMPED keys
    gw.set_weighted(fc, False)
    before = _handles(fc)
    gw.watch(bpy.context)
    assert _close(before, _handles(fc), 1e-9), "AUTO handles stay Blender's"
    ob.animation_data.action[gw.PROP][gw.curve_key(fc)] = {"w": 1, "n": 5, "locks": [0.0]}   # broken record
    gw.watch(bpy.context)


def test_default_tangent_weight():
    p = preferences.get()
    old = p.default_tangent_weight
    try:
        ob, fc = _maya_curve("edited_weights")
        p.default_tangent_weight = 'NON_WEIGHTED'
        assert gw.apply_default(fc) is False and not gw.is_weighted(fc)
        kp = fc.keyframe_points[1]
        assert abs(kp.handle_right[0] - kp.co[0] - 5 / 3) < 1e-5, "non-weighted right away"
        p.default_tangent_weight = 'WEIGHTED'
        assert gw.apply_default(fc) is True and gw.is_weighted(fc)
        _ob, fc2 = _cube()
        assert gw.is_weighted(fc2), "a curve the kit never marked counts as weighted"
    finally:
        p.default_tangent_weight = old


# --- buffer curves --------------------------------------------------------------------------------------------

def _values(fc):
    return tuple(round(kp.co[1], 6) for kp in fc.keyframe_points)


def _times(fc):
    return tuple(round(kp.co[0], 6) for kp in fc.keyframe_points)


def _move_key(kp, dx=0.0, dy=0.0):
    kp.co = (kp.co[0] + dx, kp.co[1] + dy)
    kp.handle_left = (kp.handle_left[0] + dx, kp.handle_left[1] + dy)
    kp.handle_right = (kp.handle_right[0] + dx, kp.handle_right[1] + dy)


def test_buffer_snapshot_and_swap():
    ob, fc = _cube()
    fc.keyframe_points[3].interpolation = 'LINEAR'
    fc.keyframe_points[2].handle_right_type = 'FREE'
    fc.update()
    original = _handles(fc)
    with Editor():
        assert bpy.ops.allset.buffer_swap() == {'CANCELLED'}, "no buffer yet"
        assert bpy.ops.allset.buffer_snapshot() == {'FINISHED'}
        assert gb.has_buffer(fc) and gb.PROP in ob.animation_data.action
        _move_key(fc.keyframe_points[2], dy=4.0)                  # key 10: 5 -> 9
        fc.update()
        assert bpy.ops.allset.buffer_swap() == {'FINISHED'}
        fc = _tx(ob)
        assert _values(fc) == AFTER_SWAP
        assert _close(original, _handles(fc), 1e-6), "handles come back too"
        assert fc.keyframe_points[3].interpolation == 'LINEAR' and fc.keyframe_points[2].handle_right_type == 'FREE'
        assert 9.0 in [round(v, 6) for v in gb.buffer_keys(fc)["co"][1::2]], "the buffer holds the edit"
        assert bpy.ops.allset.buffer_swap() == {'FINISHED'}
        fc = _tx(ob)
        assert _values(fc) == AFTER_SWAP2
        # Maya: buffer = the original, key 5 moved to 6, swap -> times and values come back
        _move_key(fc.keyframe_points[1], dx=1.0)
        fc.update()
        assert _times(fc) == (1.0, 6.0, 10.0, 15.0, 25.0)
        assert bpy.ops.allset.buffer_swap() == {'FINISHED'}
        fc = _tx(ob)
        assert (_times(fc), _values(fc)) == SWAP_AFTER_TIME_MOVE, (_times(fc), _values(fc))


def test_buffer_key_count_change_and_undo_data():
    ob, fc = _cube()
    with Editor():
        bpy.ops.allset.buffer_snapshot()
        fc.keyframe_points.remove(fc.keyframe_points[4])
        assert len(fc.keyframe_points) == 4
        bpy.ops.allset.buffer_swap()
        fc = _tx(ob)
        assert len(fc.keyframe_points) == 5 and len(gb.buffer_keys(fc)["co"]) == 8


def test_buffer_sampling_and_drawing():
    lin = bpy.types.Keyframe.bl_rna.properties["interpolation"].enum_items["LINEAR"].value
    const = bpy.types.Keyframe.bl_rna.properties["interpolation"].enum_items["CONSTANT"].value
    rec = {"co": [1.0, 0.0, 5.0, 2.0, 9.0, 4.0], "hl": [0.0] * 6, "hr": [0.0] * 6,
           "ipo": [lin, const, lin], "hlt": [0] * 3, "hrt": [0] * 3, "ease": [0] * 3}
    assert gb.sample(rec) == [(1.0, 0.0), (5.0, 2.0), (9.0, 2.0), (9.0, 4.0)]
    ob, fc = _cube()
    pts = gb.sample(gb.read_keys(fc), steps=8)
    assert len(pts) == 1 + 4 * 8 and pts[0] == (1.0, 0.0) and abs(pts[-1][0] - 25.0) < 1e-9
    for x, y in pts:
        assert abs(fc.evaluate(x) - y) < 1e-4
    p = preferences.get()
    old = p.graph_show_buffers
    try:
        p.graph_show_buffers = True
        with Editor():
            bpy.ops.allset.buffer_snapshot()
            lines = gb.buffer_lines(bpy.context)
            assert len(lines) == 1 and any(abs(x - 10.0) < 1e-9 and abs(y - 5.0) < 1e-9 for x, y in lines[0])
            gb.draw_buffers()                                     # no GPU in -b: draws nothing, no error
    finally:
        p.graph_show_buffers = old
    assert gb._handles, "draw handler registered"


def test_buffer_lines_show_rotation_in_degrees():
    _clear()
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    for frame, z in ((1, 0.0), (10, math.pi / 2)):
        ob.rotation_euler.z = z
        ob.keyframe_insert("rotation_euler", index=2, frame=frame)
    with Editor():
        bpy.ops.allset.buffer_snapshot()
        lines = gb.buffer_lines(bpy.context)
    assert any(abs(y - 90.0) < 1e-4 for x, y in lines[0]), lines[0][-3:]
