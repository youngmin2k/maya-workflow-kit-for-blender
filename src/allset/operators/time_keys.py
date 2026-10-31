# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya keys: S = Set Key on every keyable channel, Set Breakdown Key, and the Time Slider key edits
(Cut / Copy / Paste / Delete / Snap / Keys / Tangents / Set Range to).

Maya keys (S keys every keyable attribute); Maya
Time Slider menu (the time slider edits act on the Time Slider's highlighted range: the
Shift-dragged range, else the current frame), step 56.

Nodes are the Channel Box's (``ui/channel_box.targets``): selected objects, or the selected pose bones
in pose mode (a bone's curves are the armature action's ``pose.bones["n"]...`` curves).
"""

import math

import bpy
from bpy.props import BoolProperty, EnumProperty

from .. import results
from .. import undo_steps

# Maya tangent -> (interpolation, handle type or None); FLAT also levels the handles.
# (reused by the Graph Editor tangent buttons, step 67)
TANGENTS = {
    "SPLINE": ("BEZIER", 'AUTO'),
    "LINEAR": ("LINEAR", None),
    "CLAMPED": ("BEZIER", 'AUTO_CLAMPED'),
    "STEPPED": ("CONSTANT", None),
    "FLAT": ("BEZIER", 'ALIGNED'),
    "PLATEAU": ("BEZIER", 'AUTO_CLAMPED'),
    "AUTO": ("BEZIER", 'AUTO_CLAMPED'),
    # step 70: Fixed keeps the handles where they are; Blender has no
    # Stepped Next: Stepped. BREAK / UNIFY only change the handle type (free / aligned).
    "FIXED": ("BEZIER", 'ALIGNED'),
    "STEPPED_NEXT": ("CONSTANT", None),
    "BREAK": (None, 'FREE'),
    "UNIFY": (None, 'ALIGNED'),
}
# Maya names for the menus / buttons
TANGENT_LABELS = {"AUTO": "Auto", "SPLINE": "Spline", "CLAMPED": "Clamped", "LINEAR": "Linear", "FLAT": "Flat",
                  "STEPPED": "Stepped", "STEPPED_NEXT": "Stepped Next", "PLATEAU": "Plateau", "FIXED": "Fixed",
                  "BREAK": "Break Tangents", "UNIFY": "Unify Tangents"}


def apply_tangent(kp, kind, fc=None):
    """One key's Maya tangent (in and out); with the key's curve ``fc`` the Maya type is remembered for
    operators/maya_tangents.py (Clamped / Plateau / Flat share Blender handle types with others)."""
    interp, handle = TANGENTS[kind]
    if interp is not None:
        kp.interpolation = interp
    if handle is not None:
        kp.handle_left_type = kp.handle_right_type = handle
    if kind == "FLAT":
        kp.handle_left.y = kp.handle_right.y = kp.co.y
    if fc is not None:
        from . import maya_tangents
        maya_tangents.mark(fc, kp, kind)


def _maya_auto(fc):
    """Maya tangent shapes after the curve changed (operators/maya_tangents.py, steps 257, 310)."""
    from . import maya_tangents
    maya_tangents.apply(fc)


TANGENT_ITEMS = [(k, TANGENT_LABELS.get(k, k.title()), "") for k in TANGENTS]

_CLIPBOARD = {"nodes": [], "span": 0.0, "start": 0.0}


def _cb():
    from ..ui import channel_box
    return channel_box


# --- nodes and their curves ---------------------------------------------------------------

def nodes(context=None):
    return _cb().targets(context)


def prefix(node):
    """Animation path prefix of a node: ``pose.bones["n"]`` for a bone, "" for an object."""
    return node.path_from_id() if _cb().is_bone(node) else ""


def node_fcurves(node):
    """The node's F-curves (a bone: only its own ``pose.bones["n"]`` curves)."""
    fcs = _cb()._fcurves(node)
    if fcs is None:
        return []
    pre = prefix(node)
    if not pre:
        return list(fcs)
    return [fc for fc in fcs if fc.data_path.startswith(pre + ".") or fc.data_path.startswith(pre + "[")]


def time_range(context=None):
    """(start, end) the time slider edits act on: the Shift range, else the current frame."""
    context = context or bpy.context
    wm = context.window_manager
    if getattr(wm, "allset_time_range_on", False):
        a, b = wm.allset_time_range
        return min(a, b), max(a, b)
    f = context.scene.frame_current
    return f, f


def _in(kp, a, b):
    return a - 0.5 <= kp.co.x < b + 0.5


def keys_in(node, a, b):
    """[(fcurve, [keyframe points in a..b])] of a node."""
    out = []
    for fc in node_fcurves(node):
        pts = [kp for kp in fc.keyframe_points if _in(kp, a, b)]
        if pts:
            out.append((fc, pts))
    return out


# --- Set Key ----------------------------------------------------------------------------------

def keyable_channels(node):
    """Maya keyable attributes of a node: the Channel Box's shown channels that are keyable."""
    cb = _cb()
    return [k for k in cb._visible_channels(node) if cb.is_keyable(node, k)]


# Maya SetKeyTranslate / SetKeyRotate / SetKeyScale (Shift+W / E / R):
# setKeyframe on the translate / rotate / scale attributes of the selection only. Channel Box keys.
CHANNEL_SETS = {"TRANSLATE": ("tx", "ty", "tz"), "ROTATE": ("rx", "ry", "rz"), "SCALE": ("sx", "sy", "sz")}


def set_key(context, breakdown=False, channels=""):
    """S: key every keyable channel of every node (or the active keying set); ``channels`` = one of CHANNEL_SETS
    (Shift+W / E / R) keys only those. Count of channels keyed."""
    scene = context.scene
    keytype = 'BREAKDOWN' if breakdown else 'KEYFRAME'
    if not channels and not breakdown and scene.keying_sets.active is not None:
        # Maya: with a current character set, S keys that character's attributes (and its subcharacters'),
        # whatever is selected (step 187, rule 3)
        from . import character_sets
        return character_sets.key_current(context, keytype)
    if not channels:
        from . import point_keys
        if point_keys.applies(context):
            # Maya component mode: S keys the selected points' X / Y / Z (edges / faces: their vertices)
            return point_keys.key_points(context, keytype)
    only = CHANNEL_SETS.get(channels)
    from ..ui import cb_channels
    count = 0
    for node in nodes(context):
        # Channel Box Sync Selection in Graph Editor on: S keys the selected channels (step 158, as in Maya)
        synced = None if only is not None else cb_channels.synced_keys(context, node)
        for key in synced if synced is not None else keyable_channels(node):
            if (only is None or key in only) and _cb().is_keyable(node, key):
                count += bool(_cb().keyframe(node, key, keytype))
    return count


# --- Time Slider edits ------------------------------------------------------------------------

def delete_keys(context, a, b):
    n = 0
    for node in nodes(context):
        fcs = _cb()._fcurves(node)
        for fc, pts in keys_in(node, a, b):
            for kp in sorted(pts, key=lambda p: -p.co.x):
                fc.keyframe_points.remove(kp, fast=True)
                n += 1
            if len(fc.keyframe_points) == 0 and fcs is not None:
                fcs.remove(fc)
            else:
                fc.update()
                _maya_auto(fc)
    return n


def _note_kit_copy():
    from . import graph_key_menu
    graph_key_menu.note_kit_copy()


def copy_keys(context, a, b):
    """Time Slider copy: the nodes' keys in a..b onto the animation clipboard (see ``copy_scope``)."""
    # Time Slider frames are whole: a key within half a frame of the range counts (like ``_in``)
    return copy_scope(context, KeyScope(time_range="Start/End", start=a, end=b), pad=0.5 - EPS)


def paste_keys(context, frame):
    """Time Slider paste at ``frame`` (Merge by default, like Maya): one copied node goes to every node, several in order."""
    return paste_scope(context, frame=frame)


def _find_curve(node, path, index):
    fcs = _cb()._fcurves(node)
    return fcs.find(path, index=index) if fcs is not None else None


def _move(kp, dx):
    kp.co.x += dx
    kp.handle_left.x += dx
    kp.handle_right.x += dx


def snap_keys(context, a, b):
    n = 0
    for node in nodes(context):
        for fc, pts in keys_in(node, a, b):
            for kp in pts:
                dx = round(kp.co.x) - kp.co.x
                if dx:
                    _move(kp, dx)
                    n += 1
            fc.update()
    return n


def set_key_type(context, a, b, ktype):
    n = 0
    for node in nodes(context):
        for _fc, pts in keys_in(node, a, b):
            for kp in pts:
                kp.type = ktype
                n += 1
    return n


def inbetween(context, frame, delta):
    """Add (+1) / Remove (-1) an inbetween at ``frame``: the keys after it move by ``delta``
    (Remove only where the next key is more than one frame away, so keys never collide)."""
    n = 0
    for node in nodes(context):
        for fc in node_fcurves(node):
            later = [kp for kp in fc.keyframe_points if kp.co.x > frame + 0.5]
            if not later:
                continue
            if delta < 0 and min(kp.co.x for kp in later) < frame + 1.5:
                continue
            for kp in later:
                _move(kp, delta)
                n += 1
            fc.update()
    return n


def set_tangent(context, a, b, kind):
    n = 0
    for node in nodes(context):
        for fc, pts in keys_in(node, a, b):
            for kp in pts:
                apply_tangent(kp, kind, fc)
                n += 1
            fc.update()
            _maya_auto(fc)
    return n


def key_span(context):
    """(first, last) key frame of the nodes, or None."""
    frames = [kp.co.x for node in nodes(context) for fc in node_fcurves(node) for kp in fc.keyframe_points]
    return (int(round(min(frames))), int(round(max(frames)))) if frames else None


# --- Maya Key menu commands with their options (step 140, issue #35) ------------------------------
# Maya's Key > Delete / Cut / Copy / Paste / Scale / Snap Keys run cutKey / copyKey / pasteKey / scaleKey / snapKey with
# the option window's values (Time range All = every key, Time
# Slider = the playback range, Start/End = the fields). Results:
# Values (pivots, offsets, multiples) are Maya values: display units for
# translations, degrees for rotations.

class KeyScope:
    """The common Maya key window fields: which nodes, channels and times a key command acts on."""

    NAMES = ("objects", "hierarchy", "channels", "driven", "shapes", "time_range", "start", "end")

    def __init__(self, objects="Selected", hierarchy="Selected", channels="All keyable", driven=False, shapes=True,
                 time_range="All", start=0.0, end=10.0):
        self.objects, self.hierarchy, self.channels = objects, hierarchy, channels
        self.driven, self.shapes = driven, shapes
        self.time_range, self.start, self.end = time_range, start, end

    @classmethod
    def of(cls, values):
        return cls(**{k: values[k] for k in cls.NAMES if k in values})


class CurveRef:
    """One F-curve in scope: ``part`` "node" (the node's own), "driver" (a set-driven-key curve), "data" / "shape"
    (Maya Shapes: the object data's and its shape keys' curves)."""

    def __init__(self, node, part, coll, fc, rel):
        self.node, self.part, self.coll, self.fc, self.rel = node, part, coll, fc, rel

    @property
    def key(self):
        return (self.part, self.rel, self.fc.array_index)


def scope_nodes(context, scope):
    if scope.objects == "All":
        return [ob for ob in context.scene.objects if ob is not None]
    ns = nodes(context)
    if scope.hierarchy != "Below":
        return ns
    from .freeze import hierarchy
    out = []
    for n in ns:
        if _cb().is_bone(n):
            pose = n.id_data.pose
            chain = [n] + [pose.bones[b.name] for b in n.bone.children_recursive if b.name in pose.bones]
        else:
            chain = hierarchy([n])
        out.extend(x for x in chain if x not in out)
    return out


def _channel_filter(context, node):
    """{(data path, index)} of the Channel Box's selected channels on ``node`` (From Channel Box), None = all."""
    cb = _cb()
    allowed = set()
    for k in cb.selected_channels(context):
        if cb.is_shape_key(k) or cb.is_blend_key(k):    # curves on the object data / Key datablock, not the node
            continue
        if cb.is_input_key(k):      # an INPUTS channel: the modifier's property, on the object
            owner = cb.input_owner(node, k)
            if owner is not None:
                allowed.update((owner.path_from_id(p), max(i, 0)) for p, i in cb.input_paths(owner, k))
            continue
        try:
            path, idx, _kind = cb.channel_path(k)
        except KeyError:
            continue
        full = cb.full_path(node, path)
        if full:
            allowed.add((full, max(idx, 0)))
    return allowed or None      # nothing selected in the Channel Box: every channel


def scope_curves(context, scope):
    from .. import compat
    out, seen = [], set()

    def add(node, part, coll, fc, rel):
        if fc.as_pointer() not in seen:
            seen.add(fc.as_pointer())
            out.append(CurveRef(node, part, coll, fc, rel))

    for node in scope_nodes(context, scope):
        pre = prefix(node)
        allowed = _channel_filter(context, node) if scope.channels == "From Channel Box" else None
        coll = _cb()._fcurves(node)
        for fc in node_fcurves(node):
            if allowed is None or (fc.data_path, fc.array_index) in allowed:
                add(node, "node", coll, fc, fc.data_path[len(pre):])
        ad = node.id_data.animation_data
        if scope.driven and ad is not None:
            for fc in ad.drivers:
                if len(fc.keyframe_points) and (not pre or fc.data_path.startswith(pre)) and (
                        allowed is None or (fc.data_path, fc.array_index) in allowed):
                    add(node, "driver", None, fc, fc.data_path[len(pre):])
        if scope.shapes and allowed is None and not _cb().is_bone(node):
            data = getattr(node, "data", None)
            for part, idb in (("data", data), ("shape", getattr(data, "shape_keys", None))):
                if idb is None:
                    continue
                for fc in compat.id_fcurves(idb):
                    add(node, part, compat.id_fcurve_collection(idb), fc, fc.data_path)
    return out


def scope_range(context, scope):
    """(a, b) of a key command, or None = every key (Maya Time range All)."""
    if scope.time_range == "Start/End":
        return min(scope.start, scope.end), max(scope.start, scope.end)
    if scope.time_range == "Time Slider":     # Maya: the playback range
        sc = context.scene
        if sc.use_preview_range:
            return float(sc.frame_preview_start), float(sc.frame_preview_end)
        return float(sc.frame_start), float(sc.frame_end)
    return None


EPS = 1e-4


def _within(x, rng):
    return rng is None or rng[0] - EPS <= x <= rng[1] + EPS


def value_unit(fc):
    """Blender value per Maya value of a curve: the display length unit for translations, radians per degree."""
    import math
    from . import units
    path = fc.data_path.rsplit(".", 1)[-1]
    if path in ("location", "delta_location"):
        return units.maya_unit()
    if path in ("rotation_euler", "delta_rotation_euler"):
        return math.radians(1.0)
    return 1.0


def _remove_points(fc, pts):
    for kp in sorted(pts, key=lambda p: -p.co.x):
        fc.keyframe_points.remove(kp, fast=True)


def _drop_empty(ref):
    if ref.part != "driver" and ref.coll is not None and len(ref.fc.keyframe_points) == 0:
        ref.coll.remove(ref.fc)
        return
    if len(ref.fc.keyframe_points):
        ref.fc.update()


def _offset_value(kp, dv):
    kp.co.y += dv
    kp.handle_left.y += dv
    kp.handle_right.y += dv


def _points(ref, rng, pad=0.0):
    if rng is None:
        return list(ref.fc.keyframe_points)
    return [kp for kp in ref.fc.keyframe_points if rng[0] - pad - EPS <= kp.co.x <= rng[1] + pad + EPS]


def _key_record(kp, origin):
    """One clipboard key: time from ``origin``, value, type, interpolation, handle types and offsets."""
    return (kp.co.x - origin, kp.co.y, kp.type, kp.interpolation, kp.handle_left_type, kp.handle_right_type,
            (kp.handle_left.x - kp.co.x, kp.handle_left.y - kp.co.y),
            (kp.handle_right.x - kp.co.x, kp.handle_right.y - kp.co.y))


def _segment_record(fc, t, origin):
    """Maya Method Segments: a key where the curve crosses a range end (its value on the curve, linear)."""
    return (t - origin, fc.evaluate(t), 'KEYFRAME', 'LINEAR', 'VECTOR', 'VECTOR', (0.0, 0.0), (0.0, 0.0))


def _insert(fc, t, value, rec=None):
    kp = fc.keyframe_points.insert(t, value, keyframe_type=rec[2] if rec else 'KEYFRAME')
    if rec is not None:
        kp.interpolation = rec[3]
        kp.handle_left_type, kp.handle_right_type = rec[4], rec[5]
        if rec[4] in ('FREE', 'ALIGNED'):
            kp.handle_left = (t + rec[6][0], value + rec[6][1])
        if rec[5] in ('FREE', 'ALIGNED'):
            kp.handle_right = (t + rec[7][0], value + rec[7][1])
    return kp


def copy_scope(context, scope, method="Keys", pad=0.0):
    """Maya copyKey: the scope's keys onto the animation clipboard. ``method`` Keys / Segments (Segments adds keys
    where the curve crosses the range ends). The clipboard's time origin is the range start, or the first key with
    Time range All (a copy of 4..12 pasted at 30 puts the key at 5 on 31).
    Returns the number of keys copied."""
    _note_kit_copy()
    rng = scope_range(context, scope)
    refs = scope_curves(context, scope)
    per_node, order = {}, []
    if rng is None:
        frames = [kp.co.x for r in refs for kp in r.fc.keyframe_points]
        if not frames:
            _CLIPBOARD.update(nodes=[], span=0.0, start=0.0)
            return 0
        origin, span = min(frames), max(frames) - min(frames)
    else:
        origin, span = rng[0], rng[1] - rng[0]
    n = 0
    for ref in refs:
        pts = _points(ref, rng, pad)
        recs = [_key_record(kp, origin) for kp in pts]
        if method == "Segments" and rng is not None and len(ref.fc.keyframe_points):
            have = {round(kp.co.x, 4) for kp in pts}
            for t in rng:
                if round(t, 4) not in have:
                    recs.append(_segment_record(ref.fc, t, origin))
            recs.sort(key=lambda r: r[0])
        if not recs:
            continue
        key = id(ref.node)
        if key not in per_node:
            per_node[key] = {}
            order.append(key)
        per_node[key][ref.key] = recs
        n += len(recs)
    _CLIPBOARD.update(nodes=[per_node[k] for k in order], span=span, start=origin)
    return n


def _target_curve(node, part, rel, index, t0):
    """The F-curve a clipboard curve pastes into (made when missing, except driver curves)."""
    pre = prefix(node) if part in ("node", "driver") else ""
    owner = node.id_data if part in ("node", "driver") else (
        getattr(node, "data", None) if part == "data" else getattr(getattr(node, "data", None), "shape_keys", None))
    if owner is None:
        return None
    path = pre + rel
    if part == "driver":
        ad = owner.animation_data
        return ad.drivers.find(path, index=index) if ad is not None else None
    from .. import compat
    coll = compat.id_fcurve_collection(owner)
    fc = coll.find(path, index=index) if coll is not None else None
    if fc is not None:
        return fc
    try:
        owner.keyframe_insert(path, index=index, frame=t0)
    except (TypeError, RuntimeError):
        return None
    coll = compat.id_fcurve_collection(owner)
    fc = coll.find(path, index=index) if coll is not None else None
    if fc is not None:
        while len(fc.keyframe_points):        # only the pasted keys
            fc.keyframe_points.remove(fc.keyframe_points[0], fast=True)
    return fc


PASTE_METHODS = ("Insert", "Replace", "Merge")


def paste_scope(context, frame=None, time_range="Current", start=0.0, end=10.0, time_offset=0.0, value_offset=0.0,
                copies=1, method="Merge", replace_region="Time range"):
    """Maya pasteKey with the Paste Keys Options values:

    * time: Current = the current frame (or ``frame``), Start / Start/End = the Start time field, Clipboard = where
      the keys were copied; copy k (0-based) lands at time + offset + k * (clipboard span + offset).
    * Merge: the pasted keys go in, replacing keys at the same times, every other key stays.
    * Insert: the key at the paste time goes, keys after it move right by the pasted length.
    * Replace: keys in the pasted region (Start/End: the fields' range) go first; Entire curve: every key goes.

    One copied node goes onto every target node, several in order. Returns the number of pasted keys."""
    copied = _CLIPBOARD.get("nodes") or []
    if not copied:
        return 0
    span = float(_CLIPBOARD.get("span", 0.0))
    if time_range == "Clipboard":
        t = float(_CLIPBOARD.get("start", 0.0))
    elif time_range in ("Start", "Start/End"):
        t = float(start)
    else:
        t = float(context.scene.frame_current if frame is None else frame)
    copies = max(1, int(copies))
    length = copies * (span + time_offset)
    n = 0
    for i, node in enumerate(nodes(context)):
        curves = copied[0] if len(copied) == 1 else (copied[i] if i < len(copied) else None)
        if curves is None:
            break
        for (part, rel, index), recs in curves.items():
            fc = _target_curve(node, part, rel, index, t + time_offset + recs[0][0])
            if fc is None:
                continue
            dv = value_offset * value_unit(fc)
            pts = list(fc.keyframe_points)
            if method == "Insert":
                _remove_points(fc, [kp for kp in pts if abs(kp.co.x - t) <= EPS])
                for kp in fc.keyframe_points:
                    if kp.co.x > t + EPS:
                        _move(kp, length)
            elif method == "Replace":
                if replace_region == "Entire curve":
                    _remove_points(fc, pts)
                else:
                    lo, hi = (min(start, end), max(start, end)) if time_range == "Start/End" else (t, t + length)
                    _remove_points(fc, [kp for kp in pts if lo - EPS <= kp.co.x <= hi + EPS])
            for k in range(copies):
                base = t + time_offset + k * (span + time_offset)
                for rec in recs:
                    _insert(fc, base + rec[0], rec[1] + dv, rec)
                    n += 1
            fc.update()
    return n


def delete_scope(context, scope, method="Keys", adjustment="None", connect=False, clipboard=False):
    """Maya cutKey / cutKey -clear with the Delete / Cut Keys Options values:
    Keys = the keys in the range; Segments = also a key where the curve crosses each
    range end; Collapse = keys after the range move left by its length; Segments + Connect = the curve after the range
    joins the start key (later keys move left and by the value difference). ``clipboard`` (Cut) copies first.
    Returns the number of keys removed."""
    if clipboard:
        copy_scope(context, scope, method)
    rng = scope_range(context, scope)
    n = 0
    for ref in scope_curves(context, scope):
        fc = ref.fc
        if rng is None:
            n += len(fc.keyframe_points)
            _remove_points(fc, list(fc.keyframe_points))
            _drop_empty(ref)
            continue
        a, b = rng
        if not _points(ref, rng):
            if method != "Segments" or not len(fc.keyframe_points):
                continue
        if method == "Segments" and len(fc.keyframe_points):
            va, vb = fc.evaluate(a), fc.evaluate(b)
            inner = [kp for kp in fc.keyframe_points if a + EPS < kp.co.x < b - EPS]
            n += len(inner)
            _remove_points(fc, inner)
            for t, v in ((a, va), (b, vb)):
                if not any(abs(kp.co.x - t) <= EPS for kp in fc.keyframe_points):
                    kp = fc.keyframe_points.insert(t, v)
                    kp.interpolation = 'LINEAR'
            if connect:
                _remove_points(fc, [kp for kp in fc.keyframe_points if abs(kp.co.x - b) <= EPS])
                for kp in fc.keyframe_points:
                    if kp.co.x > b + EPS:
                        _move(kp, a - b)
                        _offset_value(kp, va - vb)
            elif adjustment == "Collapse":
                for kp in fc.keyframe_points:
                    if kp.co.x >= b - EPS and kp.co.x > a + EPS:
                        _move(kp, a - b)
        else:
            pts = _points(ref, rng)
            n += len(pts)
            _remove_points(fc, pts)
            if adjustment == "Collapse":
                for kp in fc.keyframe_points:
                    if kp.co.x > b + EPS:
                        _move(kp, a - b)
        _drop_empty(ref)
    return n


def scale_scope(context, scope, method="Scale/Pivot", only_specified=True, time_scale=1.0, time_pivot=0.0,
                value_scale=1.0, value_pivot=0.0, new_start=1.0, new_end=10.0):
    """Maya scaleKey with the Scale Keys Options values: Scale/Pivot
    scales key times about the time pivot and values about the value pivot (Maya units); Start/End maps the range
    (All: first..last key) onto New start / end. With Only scale specified keys off, keys before / after the range
    move with the first / last scaled key. Returns the number of keys scaled."""
    rng = scope_range(context, scope)
    refs = scope_curves(context, scope)
    if method == "Start/End":
        if rng is None:
            frames = [kp.co.x for r in refs for kp in r.fc.keyframe_points]
            if not frames:
                return 0
            span_rng = (min(frames), max(frames))
        else:
            span_rng = rng
        width = span_rng[1] - span_rng[0]
        k = (new_end - new_start) / width if abs(width) > EPS else 1.0

        def tmap(x):
            return new_start + (x - span_rng[0]) * k
    else:
        def tmap(x):
            return time_pivot + (x - time_pivot) * time_scale
    n = 0
    for ref in refs:
        fc = ref.fc
        inside = _points(ref, rng)
        if not inside:
            continue
        ids = {kp.as_pointer() for kp in inside}
        first = min(inside, key=lambda p: p.co.x)
        last = max(inside, key=lambda p: p.co.x)
        d_first, d_last = tmap(first.co.x) - first.co.x, tmap(last.co.x) - last.co.x
        vp = value_pivot * value_unit(fc)
        for kp in inside:
            x, y = kp.co.x, kp.co.y
            nx, ny = tmap(x), vp + (y - vp) * value_scale
            ks = tmap(x + 1.0) - nx
            for h in (kp.handle_left, kp.handle_right):
                h.x, h.y = nx + (h.x - x) * ks, ny + (h.y - y) * value_scale
            kp.co.x, kp.co.y = nx, ny
            n += 1
        if not only_specified and rng is not None:
            for kp in fc.keyframe_points:
                if kp.as_pointer() in ids:
                    continue
                if kp.co.x < rng[0] - EPS:
                    _move(kp, d_first)
                elif kp.co.x > rng[1] + EPS:
                    _move(kp, d_last)
        fc.update()
    return n


def _snap(x, m):
    return math.floor(x / m + 0.5) * m if m > 0 else x


def snap_scope(context, scope, snap="Times", time_multiple=1.0, value_multiple=1.0):
    """Maya snapKey with the Snap Keys Options values: key times to
    the nearest multiple of ``time_multiple``, values (Maya units) to multiples of ``value_multiple``. Returns the
    number of keys that moved."""
    rng = scope_range(context, scope)
    n = 0
    for ref in scope_curves(context, scope):
        fc = ref.fc
        u = value_unit(fc)
        for kp in _points(ref, rng):
            hit = False
            if snap in ("Times", "Both"):
                dx = _snap(kp.co.x, time_multiple) - kp.co.x
                if abs(dx) > 1e-9:
                    _move(kp, dx)
                    hit = True
            if snap in ("Values", "Both"):
                dv = _snap(kp.co.y / u, value_multiple) * u - kp.co.y
                if abs(dv) > 1e-12:
                    _offset_value(kp, dv)
                    hit = True
            n += hit
        fc.update()
    return n


# --- operators ----------------------------------------------------------------------------------

def _redraw(context):
    for area in context.screen.areas if context.screen else ():
        area.tag_redraw()


def global_key_applies(context):
    """Shift+W / E / R from any editor key the object / pose selection; edit, paint and sculpt modes keep their
    own keys for them."""
    return context.mode in {'OBJECT', 'POSE'}


@undo_steps.no_redo_panel      # step 147: no Adjust Last Operation (Maya has none)
class ALLSET_OT_set_key(bpy.types.Operator):
    """Set a key on every keyable channel of the selection (Maya S); the active keying set if there is one"""
    bl_idname = "allset.set_key"
    bl_label = "Set Key"
    bl_options = {'REGISTER', 'UNDO'}

    breakdown: BoolProperty(name="Breakdown", description="Set a breakdown key (Maya Set Breakdown Key)",
                            options={'SKIP_SAVE'})
    channels: EnumProperty(name="Channels", items=(("ALL", "All Keyable", "Every keyable channel"),
                                                   ("TRANSLATE", "Translate", "Translate X / Y / Z (Maya Shift+W)"),
                                                   ("ROTATE", "Rotate", "Rotate X / Y / Z (Maya Shift+E)"),
                                                   ("SCALE", "Scale", "Scale X / Y / Z (Maya Shift+R)")),
                           default="ALL", options={'SKIP_SAVE'})   # not "": Blender reads it as a separator (QA B)
    global_key: BoolProperty(name="Global Key", description="Run from a global hotkey: only in object / pose mode",
                             options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.scene.keying_sets.active is not None or _cb().lead(context) is not None

    def invoke(self, context, _event):
        if self.global_key and not global_key_applies(context):
            return {'PASS_THROUGH'}
        return self.execute(context)

    def execute(self, context):
        n = set_key(context, self.breakdown, "" if self.channels == 'ALL' else self.channels)
        if n == 0:
            self.report({'WARNING'}, "Nothing keyable selected")
            return {'CANCELLED'}
        # Maya prints nothing for a key (#100: Blender's "Successfully added ... keying set" text is gone too)
        _redraw(context)
        return {'FINISHED'}


ACTIONS = (("CUT", "Cut", "Remove keys and place on the animation clipboard"),
           ("COPY", "Copy", "Copy keys and place on the animation clipboard"),
           ("PASTE", "Paste", "Paste keys from the animation clipboard at the current time"),
           ("DELETE", "Delete", "Delete keys but do not place on the animation clipboard"),
           ("SNAP", "Snap", "Snap keys to whole frames"),
           ("TO_KEY", "Convert to Key", "Change existing breakdowns into keys"),
           ("TO_BREAKDOWN", "Convert to Breakdown", "Change existing keys into breakdowns"),
           ("ADD_INBETWEEN", "Add Inbetween", "Move every key after the current time one frame later"),
           ("REMOVE_INBETWEEN", "Remove Inbetween", "Move every key after the current time one frame earlier"),
           ("TANGENT", "Tangent", "Set in and out tangents"))


class ALLSET_OT_time_keys(bpy.types.Operator):
    """Edit the selection's keys in the Time Slider range (Shift-drag), else at the current frame (Maya Time Slider menu)"""
    bl_idname = "allset.time_keys"
    bl_label = "Time Slider Keys"
    bl_options = {'REGISTER', 'UNDO'}

    action: EnumProperty(name="Action", items=ACTIONS, options={'SKIP_SAVE'})
    tangent: EnumProperty(name="Tangent", items=TANGENT_ITEMS, options={'SKIP_SAVE'})
    # the Key / Edit > Keys menu items run with the default option values, like Maya (Time range All);
    # the Time Slider menu acts on its range / the current frame
    time_range: EnumProperty(name="Time Range", options={'SKIP_SAVE'}, items=(
        ('SLIDER', "Time Slider", "The Shift-dragged Time Slider range, else the current frame"),
        ('ALL', "All", "Every key of the selection (Maya Key menu, factory Time range All)")))

    @classmethod
    def description(cls, context, props):
        return next(d for k, _l, d in ACTIONS if k == props.action)

    @classmethod
    def poll(cls, context):
        return _cb().lead(context) is not None

    def execute(self, context):
        a, b = time_range(context)
        frame = context.scene.frame_current
        act = self.action
        if self.time_range == 'ALL' and act in ("COPY", "CUT", "DELETE", "SNAP"):
            scope = KeyScope()
            if act == "COPY":
                n = copy_scope(context, scope)
            elif act == "SNAP":
                n = snap_scope(context, scope)
            else:
                n = delete_scope(context, scope, clipboard=act == "CUT")
            results.result(self, f"{dict((k, l) for k, l, _d in ACTIONS)[act]}: {n} key(s)")
            _redraw(context)
            return {'FINISHED'}
        if act == "COPY":
            n = copy_keys(context, a, b)
        elif act == "CUT":
            n = copy_keys(context, a, b)
            delete_keys(context, a, b)
        elif act == "PASTE":
            n = paste_keys(context, frame)
        elif act == "DELETE":
            n = delete_keys(context, a, b)
        elif act == "SNAP":
            n = snap_keys(context, a, b)
        elif act in ("TO_KEY", "TO_BREAKDOWN"):
            n = set_key_type(context, a, b, 'KEYFRAME' if act == "TO_KEY" else 'BREAKDOWN')
        elif act in ("ADD_INBETWEEN", "REMOVE_INBETWEEN"):
            n = inbetween(context, frame, 1 if act == "ADD_INBETWEEN" else -1)
        else:
            n = set_tangent(context, a, b, self.tangent)
        results.result(self, f"{dict((k, l) for k, l, _d in ACTIONS)[act]}: {n} key(s)")
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_time_set_range(bpy.types.Operator):
    """Set the playback range (Maya Time Slider > Set Range to)"""
    bl_idname = "allset.time_set_range"
    bl_label = "Set Range to"
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(items=(("START_END", "Start/End", "Playback range = animation range"),
                              ("MIN_MAX", "Min/Max", "Playback range = first and last keys of the selection"),
                              ("SELECTED", "Selected", "Playback range = the Shift-dragged Time Slider range")),
                       options={'SKIP_SAVE'})

    def execute(self, context):
        scene, wm = context.scene, context.window_manager
        if self.mode == "START_END":
            a, b = scene.frame_start, scene.frame_end
        elif self.mode == "MIN_MAX":
            span = key_span(context)
            if span is None:
                self.report({'WARNING'}, "No keys found. Cannot determine min/max of animation range.")
                return {'CANCELLED'}
            a, b = span
        else:
            if not getattr(wm, "allset_time_range_on", False):
                self.report({'WARNING'}, "No range selected. Use Shift-LMB to select a range.")
                return {'CANCELLED'}
            a, b = time_range(context)
        scene.use_preview_range = True
        a, b = int(a), int(max(a, b))
        if a > scene.frame_preview_end:   # the setters keep start <= end: move the far side first
            scene.frame_preview_end, scene.frame_preview_start = b, a
        else:
            scene.frame_preview_start, scene.frame_preview_end = a, b
        return {'FINISHED'}


classes = (ALLSET_OT_set_key, ALLSET_OT_time_keys, ALLSET_OT_time_set_range)
