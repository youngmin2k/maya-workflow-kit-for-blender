# SPDX-License-Identifier: GPL-3.0-or-later
"""Graph Editor / Dope Sheet curve commands (Issue #110).

- Curves > Change Rotation Interp (Maya ``cmds.rotationInterpolation(convert=...)`` on the curves of
  the selected keys + the highlighted channels): one rotate curve converts the node's three. Every mode but
  Independent Euler synchronises keys first: rx / ry / rz get a key at the union of their key times, inserted keys
  keep the curve shape (Maya: fixed tangents keeping the slope) — evaluated curves unchanged (exact).
  Synchronized Euler keeps that: an owner marked ``PROP`` = "EULER" has key moves / inserts / deletes on one rotate
  channel copied onto the other two by a depsgraph handler -> timer (after the transform ends); a key set on one
  channel adds keys on the others at their curve value with the previous key's out tangent, and the touched
  keys get Maya's non-weighted fixed tangents (slope kept, handle a third of the interval) — move / set / cut behave
  like Maya's. Quaternion modes: Blender's
  rotation mode QUATERNION with W/X/Y/Z curves keyed at the synchronised times; each segment is a Bezier
  least-squares fit of Maya's interpolation (Slerp; Cubic / Tangent Dependent = squad, both
  the same in Maya), Blender normalises the quaternion. The Euler curves are kept in ``SNAP`` so Independent /
  Synchronized Euler gives them back exactly (Maya keeps the Euler curves) while the quaternion
  keys are the kit's; edited quaternion keys are turned back into Euler keys.
- Curves > Key Sync Filter (``cmds.filterCurve(filter="keySync", selectedKeys=True)``): range = first .. last
  selected key over the curves shown; every shown curve gets a key at each key time any of them has in that range (value
  = its curve there, constant beyond its ends); inserted keys and their neighbours get Auto tangents (Maya: auto).
- Curves > Peak Removal Filter (``cmds.filterCurve(filter="peakRemover", selectedKeys=True)``): a key between the
  first and last selected key of its curve with two keys on each side, evenly spaced, that is a strict local extremum
  whose distance to its neighbours' mean exceeds both outer neighbour steps (|v - (a + b)/2| > max(|a - a'|, |b - b'|))
  becomes the mean of its two neighbours (values of the curve before the filter). Maya's
  noisy-curve smoothing  isn't reproduced.
- Edit > Select Curve Nodes: Maya selects the anim curve nodes of the curves with selected keys. Blender's curves
  aren't scene nodes: the kit selects those curves' channels and deselects the others (scene selection kept, so the
  editor still shows them); no selected keys = no channel selected.
"""

import json
import math

import bpy
from bpy.props import EnumProperty

from .. import compat, results, undo_steps

EPS = 1e-4
PROP = "allset_rot_interp"          # owner custom property: mode key of the kit Change Rotation Interp
TIMES = "allset_rot_sync_times"     # Synchronized Euler: the key times last synchronised
SNAP = "allset_rot_euler"           # quaternion modes: JSON of the Euler curves + the quaternion keys written

MODES = (
    ("NONE", "Independent Euler", "Each rotate channel interpolates on its own (Maya rotationInterpolation none)"),
    ("EULER", "Synchronized Euler", "Rotate X / Y / Z keep keys at the same times; editing one edits all (euler)"),
    ("SLERP", "Quaternion Slerp", "Rotation interpolates along the shortest arc at constant speed (quaternionSlerp)"),
    ("SQUAD", "Quaternion Cubic", "Rotation interpolates smoothly through the keys (quaternionSquad)"),
    ("TANGENT", "Quaternion Tangent Dependent", "Quaternion interpolation shaped by the keys (quaternion)"),
)
MAYA_MODE = {"NONE": "none", "EULER": "euler", "SLERP": "quaternionSlerp", "SQUAD": "quaternionSquad",
             "TANGENT": "quaternion"}
QUATERNION_MODES = {"SLERP", "SQUAD", "TANGENT"}
EULER_PATH = "rotation_euler"
QUAT_PATH = "rotation_quaternion"


# --- quaternion maths (bpy-free; tuples w, x, y, z) -----------------------------------------------------------

def _dot(a, b):
    return sum(i * j for i, j in zip(a, b))


def _mul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return (w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2)


def _conj(q):
    return (q[0], -q[1], -q[2], -q[3])


def _log(q):
    w = max(-1.0, min(1.0, q[0]))
    n = math.sqrt(_dot(q[1:], q[1:]))
    if n < 1e-12:
        return (0.0, 0.0, 0.0, 0.0)
    a = math.acos(w)
    return (0.0,) + tuple(a * c / n for c in q[1:])


def _exp(q):
    a = math.sqrt(_dot(q[1:], q[1:]))
    if a < 1e-12:
        return (1.0, 0.0, 0.0, 0.0)
    return (math.cos(a),) + tuple(math.sin(a) * c / a for c in q[1:])


def slerp(a, b, t):
    """Spherical linear interpolation, shortest arc."""
    c = _dot(a, b)
    if c < 0.0:
        b, c = tuple(-x for x in b), -c
    om = math.acos(min(1.0, c))
    if om < 1e-9:
        return tuple(x + (y - x) * t for x, y in zip(a, b))
    s = math.sin(om)
    return tuple((math.sin((1 - t) * om) * x + math.sin(t * om) * y) / s for x, y in zip(a, b))


def continuous(quats):
    """Flip signs so each quaternion is on the side of the previous one (no long-way turns)."""
    out = []
    for q in quats:
        q = tuple(q)
        if out and _dot(out[-1], q) < 0.0:
            q = tuple(-x for x in q)
        out.append(q)
    return out


def squad_controls(quats):
    """Shoemake's inner quadrangle points; an end key counts itself as its missing neighbour (close to Maya 2022's
    quaternionSquad; mirrored ends are not)."""
    out = []
    n = len(quats)
    for i, q in enumerate(quats):
        inv = _conj(q)
        nxt = quats[i + 1] if i + 1 < n else q
        prv = quats[i - 1] if i > 0 else q
        a, b = _log(_mul(inv, nxt)), _log(_mul(inv, prv))
        out.append(_mul(q, _exp(tuple(-(x + y) / 4.0 for x, y in zip(a, b)))))
    return out


def segment_function(quats, kind):
    """f(i, s) = the rotation between key i and i + 1 at s in [0, 1]."""
    if kind == "SLERP":
        return lambda i, s: slerp(quats[i], quats[i + 1], s)
    ctrl = squad_controls(quats)

    def squad(i, s):
        return slerp(slerp(quats[i], quats[i + 1], s), slerp(ctrl[i], ctrl[i + 1], s), 2.0 * s * (1.0 - s))
    return squad


def fit_segment(f, p0, p3, samples=16):
    """Inner control points (P1, P2) of the cubic Bezier through p0 / p3 closest (least squares) to ``f(s)``."""
    a11 = a12 = a22 = 0.0
    r1 = [0.0] * len(p0)
    r2 = [0.0] * len(p0)
    for k in range(samples):
        s = (k + 1) / (samples + 1)
        u = 1.0 - s
        b1, b2 = 3 * s * u * u, 3 * s * s * u
        q = f(s)
        if _dot(q, p0) + _dot(q, p3) < 0.0:
            q = tuple(-x for x in q)
        a11 += b1 * b1
        a12 += b1 * b2
        a22 += b2 * b2
        for c in range(len(p0)):
            r = q[c] - u * u * u * p0[c] - s * s * s * p3[c]
            r1[c] += b1 * r
            r2[c] += b2 * r
    det = a11 * a22 - a12 * a12
    p1 = tuple((a22 * r1[c] - a12 * r2[c]) / det for c in range(len(p0)))
    p2 = tuple((a11 * r2[c] - a12 * r1[c]) / det for c in range(len(p0)))
    return p1, p2


# --- peak removal / key sync rules (bpy-free) -----------------------------------------------------------------

def peak_indices(times, values, lo, hi):
    """{index: new value} of the keys Maya's peak remover replaces among indices lo..hi (see module doc)."""
    n = len(values)
    out = {}
    if n < 5:
        return out
    for i in range(max(2, lo), min(n - 3, hi) + 1):
        gaps = [times[k + 1] - times[k] for k in range(i - 2, i + 2)]
        if max(gaps) - min(gaps) > EPS:
            continue
        a2, a, v, b, b2 = values[i - 2:i + 3]
        if not ((v > a and v > b) or (v < a and v < b)):
            continue
        mean = (a + b) / 2.0
        if abs(v - mean) > max(abs(a - a2), abs(b - b2)) + 1e-9 * max(1.0, abs(v)):
            out[i] = mean
    return out


def sync_times(curve_times, lo, hi):
    """Key Sync: the times every curve must have = every key time in [lo, hi] of any curve."""
    out = []
    for ts in curve_times:
        for t in ts:
            if lo - EPS <= t <= hi + EPS and not any(abs(t - u) < EPS for u in out):
                out.append(t)
    return sorted(out)


# --- curves and owners --------------------------------------------------------------------------------------

def _in_key_editor(context):
    space = getattr(context, "space_data", None)
    return space is not None and (space.type == 'GRAPH_EDITOR' or
                                  (space.type == 'DOPESHEET_EDITOR' and space.mode != 'TIMELINE'))


def context_curves(context):
    """(curves, from_editor): the curves a key editor shows, else the curves of the selected objects."""
    if _in_key_editor(context):
        curves = getattr(context, "editable_fcurves", None)
        if curves is None:
            curves = getattr(context, "visible_fcurves", None) or ()
        return [fc for fc in curves if not fc.lock], True
    out = []
    for ob in getattr(context, "selected_objects", None) or ():
        out += [fc for fc in compat.id_fcurves(ob) if not fc.lock]
    return out, False


def _has_selected_key(fc):
    return any(kp.select_control_point for kp in fc.keyframe_points)


def curve_owners(scene):
    """{fcurve pointer: object} for every animated object of the scene (an F-curve's id_data is its Action)."""
    out = {}
    for ob in scene.objects:
        if ob is None:
            continue
        for fc in compat.id_fcurves(ob):
            out[fc.as_pointer()] = ob
    return out


def _split(path):
    """('pose.bones["b"]', 'rotation_euler') / ('', 'rotation_euler')."""
    head, _dot_, tail = path.rpartition(".")
    return head, tail


def _owner(ob, prefix):
    if not prefix:
        return ob
    try:
        return ob.path_resolve(prefix)
    except (ValueError, AttributeError):
        return None


def _path(prefix, name):
    return f"{prefix}.{name}" if prefix else name


def _curves(ob, prefix, name, count):
    out = [None] * count
    full = _path(prefix, name)
    for fc in compat.id_fcurves(ob):
        if fc.data_path == full and 0 <= fc.array_index < count:
            out[fc.array_index] = fc
    return out


def euler_curves(ob, prefix=""):
    return _curves(ob, prefix, EULER_PATH, 3)


def quat_curves(ob, prefix=""):
    return _curves(ob, prefix, QUAT_PATH, 4)


def _group(ob, prefix):
    if prefix.startswith("pose.bones["):
        return prefix[len('pose.bones["'):-2]
    return "Object Transforms"


def _new_curve(ob, prefix, name, index):
    act = ob.animation_data.action
    full = _path(prefix, name)
    if hasattr(act, "fcurve_ensure_for_datablock"):
        try:
            return act.fcurve_ensure_for_datablock(ob, full, index=index, group_name=_group(ob, prefix))
        except TypeError:
            return act.fcurve_ensure_for_datablock(ob, full, index=index)
    return compat.id_fcurve_collection(ob).new(full, index=index, action_group=_group(ob, prefix))


def _remove_curve(ob, fc):
    coll = compat.id_fcurve_collection(ob)
    if coll is not None and fc is not None:
        coll.remove(fc)


def rotation_targets(scene, curves, from_editor):
    """[(object, path prefix)] whose rotation the picked curves belong to (Maya: one curve = the node's three)."""
    owners = curve_owners(scene)
    out = []
    for fc in curves:
        head, tail = _split(fc.data_path)
        if tail not in (EULER_PATH, QUAT_PATH):
            continue
        if from_editor and not (fc.select or _has_selected_key(fc)):
            continue
        ob = owners.get(fc.as_pointer())
        if ob is not None and (ob, head) not in out:
            out.append((ob, head))
    return out


# --- key snapshots ------------------------------------------------------------------------------------------

_KEY_ATTRS = ("interpolation", "handle_left_type", "handle_right_type", "easing")


def read_keys(fc):
    return [[list(kp.co), list(kp.handle_left), list(kp.handle_right)] + [getattr(kp, a) for a in _KEY_ATTRS]
            for kp in fc.keyframe_points]


def write_keys(fc, keys):
    pts = fc.keyframe_points
    if hasattr(pts, "clear"):
        pts.clear()
    else:
        while len(pts):
            pts.remove(pts[0], fast=True)
    pts.add(len(keys))
    for kp, k in zip(pts, keys):
        co, hl, hr = k[0], k[1], k[2]
        kp.co = co
        for a, v in zip(_KEY_ATTRS, k[3:]):
            setattr(kp, a, v)
        kp.handle_left = hl
        kp.handle_right = hr
    fc.update()


def _times(fc):
    return sorted({round(kp.co.x, 4) for kp in fc.keyframe_points})


def _key_at(fc, t):
    return next((kp for kp in fc.keyframe_points if abs(kp.co.x - t) < EPS), None)


# --- Euler synchronisation ----------------------------------------------------------------------------------

def _pin_all(fc):
    from .key_insert import _pin
    for kp in fc.keyframe_points:
        _pin(kp)


def sync_euler_curves(curves):
    """Every curve gets a key at each key time of any of them, keeping its shape (fixed tangents). Count added."""
    from .key_insert import insert_keep_shape
    union = sorted({t for fc in curves for t in _times(fc)})
    n = 0
    for fc in curves:
        _pin_all(fc)
        for t in union:
            if _key_at(fc, t) is None and insert_keep_shape(fc, t):
                n += 1
        _pin_all(fc)
        fc.update()
    return n


def ensure_euler_curves(ob, prefix, owner):
    """The owner's three Euler curves; a missing channel gets a curve holding its current value."""
    curves = euler_curves(ob, prefix)
    present = [fc for fc in curves if fc is not None]
    times = sorted({t for fc in present for t in _times(fc)}) or [0.0]
    for i, fc in enumerate(curves):
        if fc is None:
            fc = _new_curve(ob, prefix, EULER_PATH, i)
            value = owner.rotation_euler[i]
            fc.keyframe_points.add(1)
            kp = fc.keyframe_points[0]
            kp.co = (times[0], value)
            kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'
            fc.update()
            curves[i] = fc
    return curves


def _euler_order(owner, snap=None):
    if snap and snap.get("order"):
        return snap["order"]
    mode = owner.rotation_mode
    return mode if len(mode) == 3 else 'XYZ'


def _load_snap(owner):
    try:
        return json.loads(owner.get(SNAP, "") or "null")
    except (TypeError, ValueError):
        return None


def _clear_marks(owner):
    for key in (PROP, TIMES, SNAP):
        if key in owner:
            del owner[key]


def _snap_matches(snap, qcurves):
    if not snap or not all(qcurves):
        return False
    times, quats = snap.get("times") or [], snap.get("quat") or []
    for c, fc in enumerate(qcurves):
        pts = sorted(fc.keyframe_points, key=lambda kp: kp.co.x)
        if len(pts) != len(times):
            return False
        for kp, t, q in zip(pts, times, quats):
            if abs(kp.co.x - t) > EPS or abs(kp.co.y - q[c]) > 1e-5:
                return False
    return True


def to_euler(ob, prefix, owner):
    """Give a quaternion-mode owner its Euler curves back: the kit's snapshot when the quaternion keys are still the
    kit's, else Euler keys converted from the quaternion keys (Auto tangents). Returns the Euler curves."""
    from mathutils import Quaternion
    if owner.rotation_mode != 'QUATERNION':
        return euler_curves(ob, prefix)
    snap = _load_snap(owner)
    order = _euler_order(owner, snap)
    qcurves = quat_curves(ob, prefix)
    if any(qcurves):
        if _snap_matches(snap, qcurves):
            keys = snap["euler"]
        else:
            times = sorted({t for fc in qcurves if fc for t in _times(fc)})
            keys = [[] for _i in range(3)]
            prev = None
            static = tuple(owner.rotation_quaternion)
            for t in times:
                q = Quaternion([fc.evaluate(t) if fc else static[c] for c, fc in enumerate(qcurves)])
                q.normalize()
                e = q.to_euler(order, prev) if prev is not None else q.to_euler(order)
                prev = e
                for c in range(3):
                    keys[c].append([[t, e[c]], [t - 1.0, e[c]], [t + 1.0, e[c]],
                                    'BEZIER', 'AUTO_CLAMPED', 'AUTO_CLAMPED', 'AUTO'])
        old = euler_curves(ob, prefix)
        for c in range(3):
            fc = old[c] or _new_curve(ob, prefix, EULER_PATH, c)
            write_keys(fc, keys[c])
        for fc in qcurves:
            _remove_curve(ob, fc)
    else:
        e = owner.rotation_quaternion.to_euler(order)
        owner.rotation_mode = order
        owner.rotation_euler = e
    owner.rotation_mode = order
    if SNAP in owner:
        del owner[SNAP]
    return euler_curves(ob, prefix)


def build_quaternion(ob, prefix, owner, curves, kind):
    """Replace the (synchronised) Euler curves with W / X / Y / Z curves interpolating Maya's way."""
    from mathutils import Euler
    order = _euler_order(owner)
    times = sorted({t for fc in curves for t in _times(fc)})
    quats = continuous(tuple(Euler([fc.evaluate(t) for fc in curves], order).to_quaternion()) for t in times)
    snap = {"order": order, "times": times, "quat": [list(q) for q in quats],
            "euler": [read_keys(fc) for fc in curves]}
    f = segment_function(quats, kind)
    controls = [fit_segment(lambda s, i=i: f(i, s), quats[i], quats[i + 1]) for i in range(len(times) - 1)]
    qcurves = quat_curves(ob, prefix)
    for c in range(4):
        fc = qcurves[c] or _new_curve(ob, prefix, QUAT_PATH, c)
        keys = []
        for i, t in enumerate(times):
            v = quats[i][c]
            left = times[i - 1] if i else None
            right = times[i + 1] if i + 1 < len(times) else None
            hl = [t - (t - left) / 3.0, controls[i - 1][1][c]] if left is not None else [t - 1.0, v]
            hr = [t + (right - t) / 3.0, controls[i][0][c]] if right is not None else [t + 1.0, v]
            keys.append([[t, v], hl, hr, 'BEZIER', 'FREE', 'FREE', 'AUTO'])
        write_keys(fc, keys)
    for fc in curves:
        _remove_curve(ob, fc)
    owner.rotation_mode = 'QUATERNION'
    owner[SNAP] = json.dumps(snap)


def change_rotation_interp(ob, prefix, mode):
    """Maya rotationInterpolation -c on one node (object or pose bone). Returns True when anything changed."""
    owner = _owner(ob, prefix)
    if owner is None or owner.rotation_mode == 'AXIS_ANGLE':
        return False
    before = owner.get(PROP)
    if mode == "NONE" and owner.rotation_mode != 'QUATERNION':
        if before is not None:
            _clear_marks(owner)
        return before is not None
    curves = to_euler(ob, prefix, owner)
    if mode == "NONE":
        _clear_marks(owner)
        return True
    curves = ensure_euler_curves(ob, prefix, owner)
    sync_euler_curves(curves)
    if mode == "EULER":
        owner[PROP] = mode
        owner[TIMES] = _times(curves[0])
        if SNAP in owner:
            del owner[SNAP]
    else:
        build_quaternion(ob, prefix, owner, curves, mode)
        owner[PROP] = mode
        if TIMES in owner:
            del owner[TIMES]
    return True


# --- Synchronized Euler: live sync --------------------------------------------------------------------------

def third_handles(fc, times):
    """Maya non-weighted fixed tangents on the keys at ``times`` and their neighbours: slope kept, each handle a
    third of its interval (auto handles are Blender's to compute)."""
    pts = sorted(fc.keyframe_points, key=lambda kp: kp.co.x)
    idx = set()
    for k, kp in enumerate(pts):
        if any(abs(kp.co.x - t) < EPS for t in times):
            idx.update((k - 1, k, k + 1))
    for k in sorted(i for i in idx if 0 <= i < len(pts)):
        kp = pts[k]
        x, y = kp.co
        if k > 0 and kp.handle_left_type in {'ALIGNED', 'FREE'}:
            dx = x - kp.handle_left.x
            slope = (y - kp.handle_left.y) / dx if dx > 1e-9 else 0.0
            length = (x - pts[k - 1].co.x) / 3.0
            kp.handle_left = (x - length, y - slope * length)
        if k + 1 < len(pts) and kp.handle_right_type in {'ALIGNED', 'FREE'}:
            dx = kp.handle_right.x - x
            slope = (kp.handle_right.y - y) / dx if dx > 1e-9 else 0.0
            length = (pts[k + 1].co.x - x) / 3.0
            kp.handle_right = (x + length, y + slope * length)
    fc.update()


def _previous_slope(fc, t):
    """Maya's key set on a synchronised channel (euler_setkey_rx_12): the value of the curve there and the out
    tangent of the key before it (Maya: ry / rz key 12 = key 10's angle)."""
    pts = sorted(fc.keyframe_points, key=lambda kp: kp.co.x)
    k = next((i for i, kp in enumerate(pts) if abs(kp.co.x - t) < EPS), None)
    if not k:
        return
    prev, kp = pts[k - 1], pts[k]
    dx = prev.handle_right.x - prev.co.x
    slope = (prev.handle_right.y - prev.co.y) / dx if dx > 1e-9 else 0.0
    x, y = kp.co
    kp.handle_left_type = kp.handle_right_type = 'ALIGNED'
    kp.handle_left = (x - 1.0, y - slope)
    kp.handle_right = (x + 1.0, y + slope)


def _shift(kp, dx):
    kp.co.x += dx
    kp.handle_left.x += dx
    kp.handle_right.x += dx


def sync_owner(ob, prefix, owner):
    """Copy one Synchronized Euler channel's key moves / inserts / deletes onto the other two. Returns the number of
    key edits made."""
    from .key_insert import insert_keep_shape
    curves = euler_curves(ob, prefix)
    if not all(curves):
        return 0
    old = [round(t, 4) for t in owner.get(TIMES, [])]
    per = [_times(fc) for fc in curves]
    if all(p == old for p in per):
        return 0
    edits = 0
    touched = set()
    if not (per[0] == per[1] == per[2]):
        oldset = set(old)
        for i, p in enumerate(per):
            if p == old:
                continue
            added = sorted(set(p) - oldset)
            removed = sorted(oldset - set(p))
            others = [curves[j] for j in range(3) if j != i]
            if added and len(added) == len(removed):
                pairs = list(zip(removed, added))
                for fc in others:
                    for r, a in (pairs if pairs[0][1] < pairs[0][0] else reversed(pairs)):
                        kp = _key_at(fc, r)
                        if kp is not None and _key_at(fc, a) is None:
                            _shift(kp, a - r)
                            edits += 1
                    fc.update()
                touched.update(added)
            else:
                for fc in others:
                    for r in removed:
                        kp = _key_at(fc, r)
                        if kp is not None:
                            fc.keyframe_points.remove(kp)
                            edits += 1
                    fc.update()
                    for a in added:
                        if _key_at(fc, a) is None:
                            _pin_all(fc)
                            if insert_keep_shape(fc, a):
                                _previous_slope(fc, a)
                                edits += 1
                    _pin_all(fc)
                touched.update(added)
                touched.update(removed)
    if touched:
        for fc in curves:
            near = set(touched)
            for t in touched:                 # neighbours of a removed key
                xs = [kp.co.x for kp in fc.keyframe_points]
                below = [x for x in xs if x < t - EPS]
                above = [x for x in xs if x > t + EPS]
                if below:
                    near.add(max(below))
                if above:
                    near.add(min(above))
            third_handles(fc, near)
    owner[TIMES] = sorted({t for fc in curves for t in _times(fc)})
    return edits


def _owners_of(ob):
    yield ob, "", ob
    pose = getattr(ob, "pose", None)
    if pose is not None:
        for pb in pose.bones:
            yield ob, f'pose.bones["{pb.name}"]', pb


def sync_scene(scene):
    n = 0
    for ob in list(scene.objects):
        if ob is None or ob.animation_data is None:
            continue
        for o, prefix, owner in _owners_of(ob):
            if owner.get(PROP) == "EULER":
                n += sync_owner(o, prefix, owner)
    return n


_state = {"busy": False, "scheduled": False}
SYNC_DELAY = 0.1


def _transform_running():
    wm = bpy.context.window_manager
    for w in getattr(wm, "windows", ()):
        for op in w.modal_operators:
            if op.bl_idname.startswith("TRANSFORM_OT"):
                return True
    return False


def _sync_tick():
    try:
        if _transform_running():
            return SYNC_DELAY
        _state["scheduled"] = False
        scene = bpy.context.scene
        if scene is None:
            return None
        _state["busy"] = True
        try:
            if sync_scene(scene):
                for w in bpy.context.window_manager.windows:
                    for a in w.screen.areas:
                        if a.type in {'GRAPH_EDITOR', 'DOPESHEET_EDITOR', 'VIEW_3D'}:
                            a.tag_redraw()
        finally:
            _state["busy"] = False
    except (ReferenceError, AttributeError, RuntimeError):
        _state["scheduled"] = False
    return None


@bpy.app.handlers.persistent
def _on_depsgraph(_scene, depsgraph):
    if _state["busy"] or _state["scheduled"]:
        return
    if any(isinstance(u.id, bpy.types.Action) for u in depsgraph.updates):
        _state["scheduled"] = True
        bpy.app.timers.register(_sync_tick, first_interval=SYNC_DELAY)


# --- Key Sync / Peak Removal on curves ----------------------------------------------------------------------

def key_sync(curves):
    """Maya Key Sync Filter on ``curves`` (range = their selected keys). Count of keys added."""
    sel = [kp.co.x for fc in curves for kp in fc.keyframe_points if kp.select_control_point]
    if not sel or len(curves) < 2:
        return 0
    want = sync_times([[kp.co.x for kp in fc.keyframe_points] for fc in curves], min(sel), max(sel))
    n = 0
    for fc in curves:
        new = [(t, fc.evaluate(t)) for t in want if _key_at(fc, t) is None]     # values of the curve before
        for t, v in new:
            fc.keyframe_points.insert(t, v, options={'FAST'})
        new = [t for t, _v in new]
        if not new:
            continue
        n += len(new)
        pts = sorted(fc.keyframe_points, key=lambda kp: kp.co.x)
        for k, kp in enumerate(pts):
            if any(abs(kp.co.x - t) < EPS for t in new):
                for j in (k - 1, k, k + 1):
                    if 0 <= j < len(pts) and pts[j].interpolation == 'BEZIER':
                        pts[j].handle_left_type = pts[j].handle_right_type = 'AUTO_CLAMPED'
        fc.update()
    return n


def peak_removal(curves):
    """Maya Peak Removal Filter on the selected-key span of each curve. Count of keys changed."""
    from . import time_keys
    n = 0
    for fc in curves:
        pts = sorted(fc.keyframe_points, key=lambda kp: kp.co.x)
        sel = [k for k, kp in enumerate(pts) if kp.select_control_point]
        if not sel:
            continue
        new = peak_indices([kp.co.x for kp in pts], [kp.co.y for kp in pts], min(sel), max(sel))
        for k, v in new.items():
            time_keys._offset_value(pts[k], v - pts[k].co.y)
        if new:
            fc.update()
            n += len(new)
    return n


def select_curve_nodes(curves):
    """Channels of the curves with selected keys become the selected channels. Returns those curves."""
    picked = [fc for fc in curves if _has_selected_key(fc)]
    for fc in curves:
        fc.select = fc in picked
    return picked


def _redraw(context):
    screen = getattr(context, "screen", None)
    for area in screen.areas if screen else ():
        if area.type in {'GRAPH_EDITOR', 'DOPESHEET_EDITOR', 'VIEW_3D', 'PROPERTIES'}:
            area.tag_redraw()


# --- operators ----------------------------------------------------------------------------------------------

@undo_steps.no_redo_panel
class ALLSET_OT_rotation_interp(bpy.types.Operator):
    """Change how rotation interpolates between keys on the selected rotate curves' nodes (Maya Curves > Change
    Rotation Interp)"""
    bl_idname = "allset.rotation_interp"
    bl_label = "Change Rotation Interp"
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(items=MODES, name="Mode", default="NONE", options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        return next(d for k, _l, d in MODES if k == props.mode)

    def execute(self, context):
        curves, from_editor = context_curves(context)
        targets = rotation_targets(context.scene, curves, from_editor)
        if not targets:
            self.report({'WARNING'}, "Select keys of rotate curves to change their rotation interpolation")
            return {'CANCELLED'}
        from . import anim_layers
        done = 0
        _state["busy"] = True
        try:
            for ob, prefix in targets:
                if anim_layers.has_layers(ob):
                    self.report({'WARNING'}, f"{ob.name} has animation layers: rotation interpolation unchanged")
                    continue
                done += change_rotation_interp(ob, prefix, self.mode)
        finally:
            _state["busy"] = False
        _redraw(context)
        results.result(self, f"rotationInterpolation -c {MAYA_MODE[self.mode]}: {done}")
        return {'FINISHED'}


@undo_steps.no_redo_panel
class ALLSET_OT_key_sync_filter(bpy.types.Operator):
    """Give every curve shown a key wherever another has one within the selected keys' time range (Maya Curves >
    Key Sync Filter)"""
    bl_idname = "allset.key_sync_filter"
    bl_label = "Key Sync Filter"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        curves, _from_editor = context_curves(context)
        if not any(_has_selected_key(fc) for fc in curves):
            self.report({'WARNING'}, "Select keys to set the time range of the Key Sync Filter")
            return {'CANCELLED'}
        n = key_sync(curves)
        _redraw(context)
        results.result(self, f"Result: {n}")
        return {'FINISHED'}


@undo_steps.no_redo_panel
class ALLSET_OT_peak_removal_filter(bpy.types.Operator):
    """Replace isolated spikes among the selected keys by their neighbours' mean (Maya Curves > Peak Removal
    Filter)"""
    bl_idname = "allset.peak_removal_filter"
    bl_label = "Peak Removal Filter"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        curves, _from_editor = context_curves(context)
        if not any(_has_selected_key(fc) for fc in curves):
            self.report({'WARNING'}, "Select the keys to filter")
            return {'CANCELLED'}
        n = peak_removal(curves)
        _redraw(context)
        results.result(self, f"Result: {n}")
        return {'FINISHED'}


class ALLSET_OT_select_curve_nodes(bpy.types.Operator):
    """Select the curves of the selected keys (Maya Edit > Select Curve Nodes; Blender's curves aren't scene nodes:
    their channels are selected)"""
    bl_idname = "allset.select_curve_nodes"
    bl_label = "Select Curve Nodes"
    bl_options = {'UNDO'}

    def execute(self, context):
        from .graph_menu_198 import curve_attr
        curves, _from_editor = context_curves(context)
        picked = select_curve_nodes(curves)
        owners = curve_owners(context.scene)
        names = []
        for fc in picked:
            ob = owners.get(fc.as_pointer())
            names.append(f"{ob.name}_{curve_attr(fc)}" if ob is not None else curve_attr(fc))
        _redraw(context)
        results.result(self, "Result: " + " ".join(names) if names else "Result: (nothing)")
        return {'FINISHED'}


classes = (ALLSET_OT_rotation_interp, ALLSET_OT_key_sync_filter, ALLSET_OT_peak_removal_filter,
           ALLSET_OT_select_curve_nodes)


def _menu():
    m = {}
    for ed in ("Graph Editor", "Dope Sheet"):
        for key, label, _d in MODES:
            m[f"{ed}/Curves/Change Rotation Interp/{label}"] = ("allset.rotation_interp", {"mode": key})
        m[f"{ed}/Curves/Key Sync Filter"] = "allset.key_sync_filter"
        m[f"{ed}/Curves/Peak Removal Filter"] = "allset.peak_removal_filter"
        m[f"{ed}/Edit/Select Curve Nodes"] = "allset.select_curve_nodes"
    return m


MENU = _menu()     # merged into ui/editor_menu_map.MAP


def register_handlers():
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)


def unregister_handlers():
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    if bpy.app.timers.is_registered(_sync_tick):
        bpy.app.timers.unregister(_sync_tick)
    _state["busy"] = _state["scheduled"] = False
