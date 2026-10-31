# SPDX-License-Identifier: GPL-3.0-or-later
"""``maya.cmds`` time and key commands of the kit's look-alike (Issue #115): currentTime, setKeyframe,
cutKey, keyframe, playbackOptions.

Maya's behaviour: return values (setKeyframe = keys set, cutKey /
keyframe -e = curves changed, cutKey -clear = 0), values in Maya units / degrees, a keyed attribute takes its curve's
value at the current time. Keys go on the Channel Box channels' F-curves (``ui/channel_box.py``) with the kit's
default tangents (``graph_key_menu.after_insert``). Maya's animation range = the scene frame range,
its playback range = the preview range.
"""

import math

import bpy

from .cmds_shim import (_Flags, _cb, _flatten, _object, _selection, _split_attr, channel_keys, from_internal,
                        to_internal)

EPS = 1e-4


def currentTime(*args, **kwargs):
    f = _Flags("currentTime", kwargs)
    query = f.get("query", "q", False)
    f.get("edit", "e", False)
    f.get("update", "u", True)
    f.done()
    scene = bpy.context.scene
    if query or not args:
        return float(scene.frame_current) + scene.frame_subframe
    t = float(args[0])
    scene.frame_set(int(math.floor(t)), subframe=t - math.floor(t))
    return t


# --- targets ---------------------------------------------------------------------------------------------------------

def _all_keys(ob):
    cb = _cb()
    return [c[0] for c in cb.MAIN if cb.has_channel(ob, c[0])] + [cb.CUSTOM_PREFIX + k for k in cb.custom_keys(ob)]


def _attr_keys(ob, attrs):
    out = []
    for a in attrs:
        keys = channel_keys(ob, str(a))
        if keys is None:
            raise ValueError(f"No attribute '{a}' on {ob.name}")
        out += [k for k in keys if k not in out]
    return out


def _targets(args, at, mode):
    """[(object, [channel keys])]: ``node.attr`` names that attribute, else ``at`` or (``mode``) every keyable
    channel ("keyable") / every animated channel ("animated")."""
    names = list(_flatten(args))
    if not names:
        names = _selection()
        if not names:
            raise RuntimeError("Nothing selected")
    attrs = list(_flatten([at])) if at is not None else None
    out = []
    for n in names:
        if isinstance(n, str) and "." in n.rsplit("|", 1)[-1]:
            ob, attr = _split_attr(n)
            out.append((ob, _attr_keys(ob, [attr])))
            continue
        ob = _object(n)
        if attrs:
            keys = _attr_keys(ob, attrs)
        elif mode == "keyable":
            from ..operators import time_keys
            keys = time_keys.keyable_channels(ob)
        else:
            keys = [k for k in _all_keys(ob) if _cb().fcurve(ob, k) is not None]
        out.append((ob, keys))
    return out


def _times(t):
    """Maya -time: a frame, a list of frames, a (start, end) range or "start:end"."""
    if t is None:
        return None
    if isinstance(t, str):
        a, _, b = t.partition(":")
        return [float(a), float(b or a)]
    return [float(x) for x in _flatten([t])]


def _range(t):
    v = _times(t)
    if v is None:
        return -math.inf, math.inf
    return (v[0], v[0]) if len(v) == 1 else (min(v), max(v))


def _internal_value(ob, key):
    path, idx, kind = _cb().channel_path(key)
    if kind == "VIS":
        return 1.0 if ob.hide_viewport else 0.0
    if kind == "CUSTOM":
        return float(ob[key[len(_cb().CUSTOM_PREFIX):]])
    return getattr(ob, path)[idx]


def refresh(touched):
    """Each keyed channel takes its curve's value at the current time (Maya evaluates the animCurve)."""
    scene = bpy.context.scene
    frame = scene.frame_current + scene.frame_subframe
    cb = _cb()
    for ob, key in touched:
        fc = cb.fcurve(ob, key)
        if fc is None or not len(fc.keyframe_points):
            continue
        value = fc.evaluate(frame)
        path, idx, kind = cb.channel_path(key)
        if kind == "VIS":
            ob.hide_viewport = value >= 0.5
        elif kind == "CUSTOM":
            name = key[len(cb.CUSTOM_PREFIX):]
            ob[name] = type(ob[name])(value) if not isinstance(ob[name], bool) else value >= 0.5
        else:
            getattr(ob, path)[idx] = value


def _point_at(fc, frame):
    return next((kp for kp in fc.keyframe_points if abs(kp.co.x - frame) < EPS), None)


def _move_value(kp, y):
    dy = y - kp.co.y
    kp.co.y = y
    kp.handle_left.y += dy
    kp.handle_right.y += dy


def insert_key(ob, key, frame, value=None, breakdown=False):
    """One Maya key on channel ``key`` at ``frame`` (``value`` in Maya units, None = the current value)."""
    from ..operators import anim_layers, graph_key_menu
    cb = _cb()
    path, idx, kind = cb.channel_path(key)
    if kind == "CUSTOM" and isinstance(ob.get(key[len(cb.CUSTOM_PREFIX):]), str):
        return False
    keytype = 'BREAKDOWN' if breakdown else 'KEYFRAME'
    scene = bpy.context.scene
    if anim_layers.has_layers(ob):
        if value is not None or abs(frame - scene.frame_current) > EPS:
            raise RuntimeError(f"{ob.name} is in an animation layer: key it at the current time without -value")
        return bool(cb.keyframe(ob, key, keytype))
    internal = _internal_value(ob, key) if value is None else to_internal(key, value)
    if not ob.keyframe_insert(path, index=idx, frame=frame, keytype=keytype):
        return False
    fc = cb.fcurve(ob, key)
    kp = _point_at(fc, frame) if fc is not None else None
    if kp is not None and abs(kp.co.y - internal) > 1e-9:
        _move_value(kp, internal)
    graph_key_menu.after_insert(ob, path, idx, frame)
    if fc is not None:
        fc.update()
    return True


# --- setKeyframe / cutKey / keyframe -------------------------------------------------------------------------------

def setKeyframe(*args, **kwargs):
    """Returns the number of keys set (Maya: a new cube = 10, two attributes at one time = 2)."""
    f = _Flags("setKeyframe", kwargs)
    at = f.get("attribute", "at")
    t = f.get("time", "t")
    v = f.get("value", "v")
    bd = f.get("breakdown", "bd", False)
    f.get("inTangentType", "itt")
    f.get("outTangentType", "ott")
    f.get("shape", "s", True)
    f.get("hierarchy", "hi", "none")
    f.get("controlPoints", "cp", False)
    f.done()
    scene = bpy.context.scene
    times = _times(t) or [scene.frame_current + scene.frame_subframe]
    cb = _cb()
    count, touched = 0, []
    for ob, keys in _targets(args, at, "keyable"):
        for key in keys:
            if cb.is_locked(ob, key):
                continue                 # Maya skips locked attributes
            for frame in times:
                count += bool(insert_key(ob, key, frame, None if v is None else float(v), bd))
            # Maya leaves the attribute alone when a key at another time goes onto an existing curve (until the time
            # changes); Blender's next depsgraph update writes every animated
            # property from its curve anyway, so the script sees that value right away (a kit difference)
            touched.append((ob, key))
    refresh(touched)
    return count


def _remove_points(ob, key, a, b):
    """Remove the channel's keys in [a, b]; the curve goes when it has none left. Number removed."""
    cb = _cb()
    fc = cb.fcurve(ob, key)
    if fc is None:
        return 0
    pts = sorted((kp for kp in fc.keyframe_points if a - EPS <= kp.co.x <= b + EPS), key=lambda p: -p.co.x)
    for kp in pts:
        fc.keyframe_points.remove(kp, fast=True)
    if pts:
        if len(fc.keyframe_points) == 0:
            cb.remove_channel_curves(ob, key)
        else:
            fc.update()
    return len(pts)


def cutKey(*args, **kwargs):
    """Remove keys (all, or in -time); returns the number of curves cut, 0 with -clear. The keys are
    not put on the animation clipboard (the kit's clipboard holds Channel Box / Graph Editor copies)."""
    f = _Flags("cutKey", kwargs)
    at = f.get("attribute", "at")
    t = f.get("time", "t")
    clear = f.get("clear", "cl", False)
    f.get("option", "o", "keys")
    f.get("index", None)
    f.get("hierarchy", "hi", "none")
    f.get("shape", "s", True)
    f.done()
    a, b = _range(t)
    curves = 0
    for ob, keys in _targets(args, at, "animated"):
        for key in keys:
            if _remove_points(ob, key, a, b):
                curves += 1
    # Maya: the attributes keep the values they had (a cut curve doesn't re-evaluate them)
    return 0 if clear else curves


def keyframe(*args, **kwargs):
    """Query (-q -tc / -vc / -kc, optional -time range) or change (-e: -tc / -vc, -r relative or absolute) keys."""
    f = _Flags("keyframe", kwargs)
    query = f.get("query", "q", False)
    edit = f.get("edit", "e", False)
    at = f.get("attribute", "at")
    t = f.get("time", "t")
    tc = f.get("timeChange", "tc")
    vc = f.get("valueChange", "vc")
    kc = f.get("keyframeCount", "kc", False)
    relative = f.get("relative", "r", False)
    f.get("absolute", "a", False)
    f.get("index", None)
    f.get("option", "o", "move")
    f.done()
    a, b = _range(t)
    cb = _cb()
    groups = []
    for ob, keys in _targets(args, at, "animated"):
        for key in keys:
            fc = cb.fcurve(ob, key)
            if fc is None:
                continue
            pts = [kp for kp in fc.keyframe_points if a - EPS <= kp.co.x <= b + EPS]
            groups.append((ob, key, fc, pts))
    if query:
        if kc:
            return sum(len(p) for *_x, p in groups)
        out = []
        for _ob, key, _fc, pts in groups:
            for kp in sorted(pts, key=lambda p: p.co.x):
                row = []
                if tc:
                    row.append(float(kp.co.x))
                if vc or not tc:
                    v = from_internal(key, kp.co.y)
                    row.append(float(v) if not isinstance(v, bool) else float(v))
                out += row
        return out or None
    if not (edit or tc is not None or vc is not None):
        raise TypeError("keyframe: use -query or -edit with -timeChange / -valueChange")
    changed, touched = 0, []
    for ob, key, fc, pts in groups:
        if not pts:
            continue
        for kp in pts:
            if tc is not None:
                dx = float(tc) if relative else float(tc) - kp.co.x
                kp.co.x += dx
                kp.handle_left.x += dx
                kp.handle_right.x += dx
            if vc is not None:
                if relative:
                    y = kp.co.y + to_internal(key, float(vc)) - to_internal(key, 0.0)
                else:
                    y = to_internal(key, float(vc))
                _move_value(kp, y)
        fc.update()
        changed += 1
        touched.append((ob, key))
    refresh(touched)
    return changed


# --- playbackOptions ------------------------------------------------------------------------------------------------

def _playback(scene):
    if scene.use_preview_range:
        return scene.frame_preview_start, scene.frame_preview_end
    return scene.frame_start, scene.frame_end


def playbackOptions(*args, **kwargs):
    """Maya's playback range (-min / -max = the Time Slider's) is the preview range, the animation range (-ast /
    -aet = the Range Slider's ends) the scene frame range. A min past the max pushes the max to min + 1
    (Maya: min 90 with max 60 -> 90 / 91)."""
    f = _Flags("playbackOptions", kwargs)
    query = f.get("query", "q", False)
    f.get("edit", "e", False)
    lo = f.get("minTime", "min")
    hi = f.get("maxTime", "max")
    ast = f.get("animationStartTime", "ast")
    aet = f.get("animationEndTime", "aet")
    by = f.get("by", "by")
    f.done()
    if args:
        raise TypeError("playbackOptions takes no objects")
    scene = bpy.context.scene
    if query:
        start, end = _playback(scene)
        if lo:
            return float(start)
        if hi:
            return float(end)
        if ast:
            return float(scene.frame_start)
        if aet:
            return float(scene.frame_end)
        if by:
            return float(scene.frame_step)
        raise TypeError("playbackOptions -query needs -min, -max, -ast, -aet or -by")
    if ast is not None or aet is not None:
        s = int(round(ast)) if ast is not None else scene.frame_start
        e = int(round(aet)) if aet is not None else scene.frame_end
        scene.frame_end = max(e, s)            # set the end first: Blender pushes start <= end
        scene.frame_start = s
        scene.frame_end = max(e, s)
    if lo is not None or hi is not None:
        start, end = _playback(scene)
        s = int(round(lo)) if lo is not None else start
        e = int(round(hi)) if hi is not None else end
        if e <= s:
            if lo is not None:
                e = s + 1
            else:
                s = e - 1
        scene.use_preview_range = True
        scene.frame_preview_end = max(e, scene.frame_preview_start)
        scene.frame_preview_start = s
        scene.frame_preview_end = e
    if by is not None:
        scene.frame_step = max(1, int(round(by)))
    return None


__all__ = ["currentTime", "setKeyframe", "cutKey", "keyframe", "playbackOptions", "insert_key", "refresh"]
