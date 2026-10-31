# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya tangent shapes: Auto, Spline, Clamped, Plateau and Flat (steps 257, 310; Issues #151, #210).

Every Maya tangent type computes its own slope m (value per frame) from the keys; the curve between two keys is a
plain cubic Hermite in time, i.e. Bezier handles at a third of each interval: in = (-h-/3, -m h-/3),
out = (h+/3, m h+/3). Slope rules, key k with neighbours (t-, v-) and (t+, v+):

- auto (the default type in Maya): first / last key flat; a middle key takes the central difference
  m = (v+ - v-) / (t+ - t-), = 0 when the two secants s-, s+ differ in sign or m's sign differs from theirs (a zero
  secant counts as positive), else |m| <= min(3|s-|, 3|s+|);
- spline: the central difference for a middle key, the secant to the one neighbour for an end key;
- clamped: the spline slope, but flat when a neighbour is within 0.05 in value (an end key compares its one
  neighbour);
- plateau: flat for end keys, keys equal to a neighbour and extremes; otherwise the spline slope unless the control
  polygon of the segment before or after (with the neighbour key's own slope) passes the segment's key values, then
  flat;
- flat: m = 0, handles at a third of the interval like every other type.

Blender knows two automatic handle types: 'AUTO' (the kit's Spline) and 'AUTO_CLAMPED' (Auto, Clamped and Plateau)
and places them by its own rule, so the kit writes Maya's handles itself. Which of Auto / Clamped / Plateau (and
Flat, an Aligned / Free handle) a key side has is kept per curve on its Action:

``Action["allset_tangents"]`` = {"<data_path>|<array_index>": {"f": [key frames], "t": "<in, out char per key>"}}
with chars A / S / C / P / F, "-" = told by the handle type ('AUTO' = Spline, 'AUTO_CLAMPED' = Auto). The entry
follows its keys by index while the key count stays (keys moved), else by frame. A stored Clamped / Plateau side
that is no longer 'AUTO_CLAMPED', or a Flat side that isn't level any more, is the user's own tangent now (Maya
Fixed) and loses its type.

Blender recomputes automatic handles whenever it edits the curve (a Graph Editor drag), so ``watch`` (every 0.25 s
from ``ui/graph_view``, never while a modal tool runs) writes Maya's handles again on every curve of an Action
that carries the property.
"""

import bpy

AUTO = 'AUTO_CLAMPED'
PROP = "allset_tangents"
CHARS = {"AUTO": "A", "SPLINE": "S", "CLAMPED": "C", "PLATEAU": "P", "FLAT": "F"}
KINDS = {c: k for k, c in CHARS.items()}
# kinds that keep the key's stored type (they only change the handle type)
KEEP = {"BREAK", "UNIFY"}
CLAMP_TOL = 0.05            # Maya value units
EQUAL_EPS = 1e-10
FRAME_TOL = 1e-3
_PASSES = 5


def _sign(x):
    return -1 if x < 0 else 1           # Maya counts a zero secant as positive


# --- slope rules (pure) ---------------------------------------------------------------------------------------

def slopes(times, values):
    """Maya auto slope (value per frame) of every key of a curve whose keys are (times, values), times rising."""
    n = len(times)
    out = [0.0] * n
    for k in range(1, n - 1):
        h0, h1 = times[k] - times[k - 1], times[k + 1] - times[k]
        if h0 <= 0 or h1 <= 0:
            continue
        s0 = (values[k] - values[k - 1]) / h0
        s1 = (values[k + 1] - values[k]) / h1
        m = (values[k + 1] - values[k - 1]) / (h0 + h1)
        if _sign(s0) != _sign(s1) or _sign(m) != _sign(s0):
            continue
        lim = min(3.0 * abs(s0), 3.0 * abs(s1))
        out[k] = max(-lim, min(lim, m))
    return out


def spline_slope(times, values, k):
    n = len(times)
    if n < 2:
        return 0.0
    a, b = (0, 1) if k == 0 else (n - 2, n - 1) if k == n - 1 else (k - 1, k + 1)
    dt = times[b] - times[a]
    return (values[b] - values[a]) / dt if dt > 1e-9 else 0.0


def clamped_slope(times, values, k, tol=CLAMP_TOL):
    n = len(times)
    if n < 2:
        return 0.0
    v = values[k]
    vp = values[k - 1] if k > 0 else values[k + 1]
    vn = values[k + 1] if k < n - 1 else values[k - 1]
    if abs(v - vp) > tol and abs(v - vn) > tol:
        return spline_slope(times, values, k)
    return 0.0


def _polygon(t0, v0, m0, t1, v1, m1):
    """Lowest and highest point of a segment's control polygon (handles at a third of the segment)."""
    d = (t1 - t0) / 3.0
    ys = (v0, v0 + m0 * d, v1 - m1 * d, v1)
    return min(ys), max(ys)


def _plateau(times, values, k, m_prev, m_next, eps):
    n = len(times)
    if k == 0 or k == n - 1:
        return 0.0
    v, vp, vn = values[k], values[k - 1], values[k + 1]
    if abs(vp - v) <= eps or abs(vn - v) <= eps:
        return 0.0
    if (vp <= v - eps and vn <= v - eps) or (v + eps <= vp and v + eps <= vn):
        return 0.0                      # extreme
    s = spline_slope(times, values, k)
    lo, hi = _polygon(times[k - 1], vp, m_prev, times[k], v, s)
    if (lo + eps <= v and lo + eps <= vp) or (v <= hi - eps and vp <= hi - eps):
        return 0.0
    lo, hi = _polygon(times[k], v, s, times[k + 1], vn, m_next)
    if (v < lo + eps or vn < lo + eps) and (hi - eps < v or hi - eps < vn):
        return s
    return 0.0


def solve(times, values, kinds, current=None, tol=CLAMP_TOL, eps=EQUAL_EPS):
    """[(in slope, out slope)] per key. ``kinds`` = [(in kind, out kind)] with 'AUTO' / 'SPLINE' / 'CLAMPED' /
    'PLATEAU' / 'FLAT' or None (the side keeps ``current``'s slope, default 0); ``tol`` = the Clamped closeness and
    ``eps`` the Plateau equality in the curve's own value units."""
    n = len(times)
    cur = list(current) if current is not None else [(0.0, 0.0)] * n
    auto = None
    out = []
    for k in range(n):
        pair = []
        for side, kind in enumerate(kinds[k]):
            if kind == "AUTO":
                if auto is None:
                    auto = slopes(times, values)
                m = auto[k]
            elif kind == "SPLINE":
                m = spline_slope(times, values, k)
            elif kind == "CLAMPED":
                m = clamped_slope(times, values, k, tol)
            elif kind in ("FLAT", "PLATEAU"):
                m = 0.0
            else:
                m = cur[k][side]
            pair.append(m)
        out.append(pair)
    if any("PLATEAU" in kk for kk in kinds):
        # a plateau key reads its neighbours' slopes: repeat until nothing changes
        for _ in range(_PASSES):
            changed = False
            for k in range(n):
                if "PLATEAU" not in kinds[k]:
                    continue
                m_prev = out[k - 1][1] if k > 0 else 0.0
                m_next = out[k + 1][0] if k < n - 1 else 0.0
                m = _plateau(times, values, k, m_prev, m_next, eps)
                for side in (0, 1):
                    if kinds[k][side] == "PLATEAU" and out[k][side] != m:
                        out[k][side] = m
                        changed = True
            if not changed:
                break
    return [tuple(p) for p in out]


def _intervals(times, k):
    n = len(times)
    h0 = (times[k] - times[k - 1]) if k > 0 else None
    h1 = (times[k + 1] - times[k]) if k < n - 1 else None
    h0 = h0 if h0 is not None else (h1 if h1 is not None else 3.0)
    h1 = h1 if h1 is not None else h0
    return h0, h1


def handles_of(times, values, pairs):
    """[(left x, left y, right x, right y)] for the slopes ``pairs`` with handles at a third of each interval."""
    out = []
    for k, (mi, mo) in enumerate(pairs):
        h0, h1 = _intervals(times, k)
        t, v = times[k], values[k]
        out.append((t - h0 / 3.0, v - mi * h0 / 3.0, t + h1 / 3.0, v + mo * h1 / 3.0))
    return out


def handles(times, values):
    """[(left x, left y, right x, right y)] Bezier handles of the Maya auto curve through the keys."""
    m = slopes(times, values)
    return handles_of(times, values, [(s, s) for s in m])


# --- stored types -----------------------------------------------------------------------------------------------

def is_auto(kp):
    return kp.handle_left_type == AUTO and kp.handle_right_type == AUTO


def curve_key(fc):
    return f"{fc.data_path}|{fc.array_index}"


def _action(fc):
    ob = getattr(fc, "id_data", None)
    return ob if isinstance(ob, bpy.types.Action) else None


def _stored(fc, frames):
    """Stored chars per key side, realigned to the curve's keys ("-" where nothing is stored)."""
    act = _action(fc)
    data = act.get(PROP) if act is not None else None
    entry = data.get(curve_key(fc)) if data is not None else None
    n = len(frames)
    if entry is None:
        return ["-"] * (2 * n)
    chars = str(entry.get("t", ""))
    old = list(entry.get("f", ()))
    if len(old) == n and len(chars) == 2 * n:
        return list(chars)
    out = ["-"] * (2 * n)
    for j, f in enumerate(old):
        if 2 * j + 1 >= len(chars):
            break
        for i, g in enumerate(frames):
            if abs(f - g) <= FRAME_TOL:
                out[2 * i], out[2 * i + 1] = chars[2 * j], chars[2 * j + 1]
                break
    return out


def _store(fc, frames, chars):
    act = _action(fc)
    if act is None:
        return
    if PROP not in act:
        act[PROP] = {}
    data = act[PROP]
    key = curve_key(fc)
    text = "".join(chars)
    if text.strip("-") == "":
        if key in data:
            del data[key]
        return
    entry = data.get(key)
    if entry is not None and str(entry.get("t", "")) == text and list(entry.get("f", ())) == list(frames):
        return
    data[key] = {"f": list(frames), "t": text}


def watch_action(fc):
    """Make ``watch`` look after this curve's Action (empty property = nothing stored, Auto / Spline sides only)."""
    act = _action(fc)
    if act is not None and PROP not in act:
        act[PROP] = {}


def _level(kp, side):
    co = kp.co
    h = kp.handle_left if side == 0 else kp.handle_right
    return abs(h[1] - co[1]) <= 1e-6 + 2e-6 * max(1.0, abs(co[1]))


def _side_type(kp, side):
    return kp.handle_left_type if side == 0 else kp.handle_right_type


def side_kind(kp, side, char):
    """Maya kind of one key side for the stored char, or None (the user's own tangent / not a handle Maya places)."""
    t = _side_type(kp, side)
    if char in ("C", "P", "A"):
        if t == AUTO:
            return KINDS[char]
    elif char == "S":
        if t == 'AUTO':
            return "SPLINE"
    elif char == "F":
        if t in {'ALIGNED', 'FREE'} and _level(kp, side):
            return "FLAT"
    if t == 'AUTO':
        return "SPLINE"
    if t == AUTO:
        return "AUTO"
    return None


def mark(fc, kp, kind, side="BOTH"):
    """Remember that ``kp`` (a key of ``fc``) got the Maya tangent ``kind`` on ``side`` ('IN' / 'OUT' / 'BOTH')."""
    if kind in KEEP:
        return
    pts = fc.keyframe_points
    frames = [p.co.x for p in pts]
    index = next((i for i, f in enumerate(frames) if abs(f - kp.co.x) <= FRAME_TOL), None)
    if index is None:
        return
    chars = _stored(fc, frames)
    c = CHARS.get(kind, "-")
    if side in ("IN", "BOTH"):
        chars[2 * index] = c
    if side in ("OUT", "BOTH"):
        chars[2 * index + 1] = c
    _store(fc, frames, chars)


# --- writing --------------------------------------------------------------------------------------------------

def tolerances(fc):
    """(Clamped closeness, Plateau equality) in the curve's own units: lengths are Maya units x ``maya_unit()``,
    rotations Maya degrees."""
    unit = _unit(fc)
    k = 1.0
    if unit == 'LENGTH':
        from . import units
        try:
            k = units.maya_unit()
        except (AttributeError, RuntimeError):
            k = 1.0
    elif unit == 'ROTATION':
        k = 0.017453292519943295
    return CLAMP_TOL * k, EQUAL_EPS * k


_units = {}


def _unit(fc):
    act = _action(fc)
    key = (act.as_pointer() if act is not None else 0, curve_key(fc))
    if key not in _units:
        try:
            from ..ui import graph_units
            _units[key] = graph_units.curve_units([fc])[0]
        except (ImportError, AttributeError, ReferenceError, RuntimeError):
            return 'NONE'
    return _units[key]


def _slope(kp, side):
    h = kp.handle_left if side == 0 else kp.handle_right
    dx = kp.co[0] - h[0] if side == 0 else h[0] - kp.co[0]
    dy = kp.co[1] - h[1] if side == 0 else h[1] - kp.co[1]
    return dy / dx if dx > 1e-12 else 0.0


def _close(a, b, kp):
    return abs(a - b) <= 1e-6 + 2e-6 * max(1.0, abs(kp.co[0]), abs(kp.co[1]))


def apply(fc):
    """Write Maya's handles on every key side whose Maya type the kit places. Returns how many keys changed."""
    pts = fc.keyframe_points
    if not len(pts):
        return 0
    times = [kp.co.x for kp in pts]
    if any(b < a for a, b in zip(times, times[1:])):
        fc.update()                     # sorts the keys
        times = [kp.co.x for kp in pts]
    values = [kp.co.y for kp in pts]
    chars = _stored(fc, times)
    kinds, current, kept = [], [], []
    for i, kp in enumerate(pts):
        pair = []
        for side in (0, 1):
            stored = chars[2 * i + side]
            kind = side_kind(kp, side, stored)
            pair.append(kind)
            kept.append(stored if stored != "-" and kind == KINDS.get(stored) else "-")
        kinds.append(tuple(pair))
        current.append((_slope(kp, 0), _slope(kp, 1)))
    tol, eps = tolerances(fc)
    pairs = solve(times, values, kinds, current, tol, eps)
    n = 0
    for kp, kk, (lx, ly, rx, ry) in zip(pts, kinds, handles_of(times, values, pairs)):
        hit = False
        if kk[0] is not None and not (_close(kp.handle_left[0], lx, kp) and _close(kp.handle_left[1], ly, kp)):
            kp.handle_left = (lx, ly)
            hit = True
        if kk[1] is not None and not (_close(kp.handle_right[0], rx, kp) and _close(kp.handle_right[1], ry, kp)):
            kp.handle_right = (rx, ry)
            hit = True
        n += hit
    _store(fc, times, kept)
    watch_action(fc)
    return n


def apply_all(fcurves):
    return sum(apply(fc) for fc in fcurves)


# --- watch -----------------------------------------------------------------------------------------------------

_sigs = {}


def _signature(fc):
    pts = fc.keyframe_points
    buf = [0.0] * (2 * len(pts))
    out = []
    for attr in ("co", "handle_left", "handle_right"):
        pts.foreach_get(attr, buf)
        out.append(tuple(buf))
    return tuple(out)


def _busy():
    # the kit's click listeners stay up all session in the Maya layout: they don't count
    from ..modal_listeners import tool_running
    return tool_running()


def watch(context=None):
    """Write Maya's handles again on curves Blender changed since the kit last wrote them (never raises)."""
    try:
        actions = [a for a in bpy.data.actions if PROP in a]
        if not actions or _busy():
            return 0
        from .. import compat
        changed = 0
        live = set()
        for action in actions:
            for fc in compat.action_fcurves(action):
                key = (action.as_pointer(), curve_key(fc))
                live.add(key)
                if _sigs.get(key) == _signature(fc):
                    continue
                changed += apply(fc)
                _sigs[key] = _signature(fc)
        for key in set(_sigs) - live:
            del _sigs[key]
        if changed:
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type in {'GRAPH_EDITOR', 'VIEW_3D', 'DOPESHEET_EDITOR'}:
                        area.tag_redraw()
        return changed
    except Exception as exc:    # a timer must never raise
        print("allset maya_tangents.watch:", exc)
        return 0


def forget():
    """Drop the watch caches (file load: Action pointers are reused)."""
    _sigs.clear()
    _units.clear()
