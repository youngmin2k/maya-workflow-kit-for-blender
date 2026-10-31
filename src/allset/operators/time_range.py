# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Time Slider range drag: the middle of a Shift-highlighted range moves its keys, an end arrow scales them
.

The maths is bpy-free (``zone``, ``map_frame``, ``new_range``); ``Drag`` edits the F-curves of the range's keys from
a snapshot of every key on each update, because sorting moves the points and a KeyframePoint reference would then
point at another key. While dragging the points are only sorted (``keyframe_points.sort`` + ``handles_recalc``):
``FCurve.update()`` also merges keys on the same frame, which would eat a key the range passes over.
"""

KEY_PROPS = ("co", "handle_left", "handle_right", "handle_left_type", "handle_right_type", "interpolation", "type",
             "easing", "back", "amplitude", "period", "select_control_point", "select_left_handle",
             "select_right_handle")


def zone(x, x0, x1, edge):
    """Where window x falls on a range drawn x0..x1: 'LEFT' / 'RIGHT' end arrows (edge px), 'MOVE', or None."""
    if x < x0 or x > x1:
        return None
    if x1 - x0 < 3 * edge:
        return 'MOVE'
    if x < x0 + edge:
        return 'LEFT'
    if x > x1 - edge:
        return 'RIGHT'
    return 'MOVE'


def new_range(a, b, mode, f0, f):
    """Range a..b after dragging from frame f0 to f (whole frames). An end never crosses the other one."""
    d = int(round(f - f0))
    if mode == 'MOVE' or a == b:
        return a + d, b + d
    if mode == 'RIGHT':
        return a, max(a + 1, b + d)
    return min(b - 1, a + d), b


def map_frame(t, a, b, mode, f0, f):
    """New time of a key at t in the range a..b (rounded to a whole frame) and the time scale factor."""
    na, nb = new_range(a, b, mode, f0, f)
    if mode == 'MOVE' or a == b:
        return t + (na - a), 1.0
    s = (nb - na) / (b - a)
    pivot_old, pivot_new = (a, na) if mode == 'RIGHT' else (b, nb)
    return float(round(pivot_new + (t - pivot_old) * s)), s


def clashes(xs, moved):
    """Indices to remove after a drag: other keys within half a frame of a moved key (Maya -option over), and of
    moved keys landing on the same frame all but the last. ``xs`` = final key times, ``moved`` = moved indices."""
    moved = sorted(moved)
    dest = {}
    for i in moved:
        dest.setdefault(round(xs[i]), []).append(i)
    drop = {i for idx in dest.values() for i in idx[:-1]}
    for i, x in enumerate(xs):
        if i not in moved and any(abs(x - d) < 0.5 for d in dest):
            drop.add(i)
    return sorted(drop, reverse=True)


class Drag:
    """The range's keys of some F-curves, re-placed from the snapshot taken at the press."""

    def __init__(self, curves, a, b):
        # curves: [(fcurve, [indices of keys in a..b])]
        self.a, self.b = a, b
        self.curves = []
        for fc, idx in curves:
            snap = [{p: _copy(getattr(kp, p)) for p in KEY_PROPS} for kp in fc.keyframe_points]
            self.curves.append((fc, snap, set(idx)))

    def _place(self, fc, snap, idx, mode, f0, f):
        """Write the snapshot back slot by slot (whatever order update() left) and re-place the range's keys."""
        pts = fc.keyframe_points
        for i, data in enumerate(snap):
            kp = pts[i]
            for p, v in data.items():
                setattr(kp, p, v)
            if i in idx and mode is not None:
                x = data["co"][0]
                nx, s = map_frame(x, self.a, self.b, mode, f0, f)
                kp.co.x = nx
                kp.handle_left.x = nx + (data["handle_left"][0] - x) * s
                kp.handle_right.x = nx + (data["handle_right"][0] - x) * s

    def apply(self, mode, f0, f):
        for fc, snap, idx in self.curves:
            self._place(fc, snap, idx, mode, f0, f)
            _sort(fc)

    def finish(self, mode, f0, f):
        """Final placement with the clashes removed. Returns the number of keys moved."""
        n = 0
        for fc, snap, idx in self.curves:
            self._place(fc, snap, idx, mode, f0, f)
            pts = fc.keyframe_points
            xs = [kp.co.x for kp in pts]               # snapshot order: indices match ``idx``
            for i in clashes(xs, idx):
                pts.remove(pts[i])
            fc.update()
            n += len(idx)
        return n

    def cancel(self):
        for fc, snap, idx in self.curves:
            self._place(fc, snap, idx, None, 0, 0)
            _sort(fc)


def _sort(fc):
    fc.keyframe_points.sort()
    fc.keyframe_points.handles_recalc()


def _copy(v):
    if isinstance(v, (str, bool, int, float)):
        return v
    return tuple(v)            # mathutils vectors (co, handles)
