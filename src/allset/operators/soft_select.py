# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya soft selection as ONE global state (issues #1, #15) and the falloff maths of the colour overlay (#2).

Maya's soft select is one global option (``cmds.softSelect(softSelectEnabled=...)``, off by default).
Blender has two per-scene flags, ``use_proportional_edit_objects`` (object mode)
and ``use_proportional_edit`` (edit modes, UV), so the kit keeps both flags of every scene equal to ``STATE``:
kit toggles call ``set_on``; a flag changed by Blender's own UI is pulled in (``pull``: depsgraph handler +
msgbus); loads / undo / redo push the state back (a file saved with soft select on follows the global state).

Falloff maths = Blender's transform (``set_prop_dist``, ``transform_convert_mesh_connectivity_distance`` +
``geodesic_distance_propagate_across_triangle``, ``calculatePropRatio``) so the colours show what G / R / S
will do; the colour ramp is Maya's ``cmds.softSelect(query=True, softSelectColorCurve=True)`` (yellow 1, red 0.5,
black 0).
"""

import bpy
import numpy as np
from bpy.app.handlers import persistent

STATE = {"on": False}          # off by default

FLAGS = ("use_proportional_edit_objects", "use_proportional_edit")


# --- state ---------------------------------------------------------------------------------------

def is_on():
    return STATE["on"]


def _scenes():
    try:
        return list(bpy.data.scenes)
    except AttributeError:          # restricted data during register
        return []


def push():
    """Write the state into both Blender flags of every scene."""
    on = STATE["on"]
    for sc in _scenes():
        ts = sc.tool_settings
        for f in FLAGS:
            if getattr(ts, f) != on:
                setattr(ts, f, on)


def set_on(value, context=None):
    """Turn Maya soft select on / off everywhere. Turning it on with Blender's untouched radius uses Maya's
    (5 Maya units)."""
    STATE["on"] = bool(value)
    push()
    if STATE["on"] and context is not None:
        from . import taphold
        taphold.maya_soft_radius(context)
    return STATE["on"]


def pull(scene):
    """A flag that differs from the state was changed by Blender (header button, menu, UV toolkit): it is the
    new state for both modes. Returns True when the state changed."""
    if scene is None:
        return False
    ts = scene.tool_settings
    if any(getattr(ts, f) != STATE["on"] for f in FLAGS):
        STATE["on"] = not STATE["on"]
        push()
        return True
    return False


def toggle(context):
    pull(context.scene)
    return set_on(not STATE["on"], context)


# Scene.allset_soft_select: the checkbox of the Modeling Toolkit / Tool Settings.

def _prop_get(_self):
    return STATE["on"]


def _prop_set(self, value):
    from . import taphold
    STATE["on"] = bool(value)
    push()
    if STATE["on"]:
        ts = self.tool_settings
        if abs(ts.proportional_size - taphold.BLENDER_SOFT_RADIUS) < 1e-9:
            from . import units
            ts.proportional_size = taphold.MAYA_SOFT_RADIUS * units.maya_unit(self)


# --- handlers ------------------------------------------------------------------------------------

_owner = object()


def _on_msgbus():
    try:
        pull(bpy.context.scene)
    except (AttributeError, ReferenceError):
        pass


def _subscribe():
    bpy.msgbus.clear_by_owner(_owner)
    for f in FLAGS:
        bpy.msgbus.subscribe_rna(key=(bpy.types.ToolSettings, f), owner=_owner, args=(), notify=_on_msgbus)


@persistent
def _on_depsgraph(scene, _depsgraph):
    pull(scene)


@persistent
def _on_rebaseline(*_args):
    push()


@persistent
def _on_load(*_args):
    push()
    _subscribe()


def _push_later():
    push()
    return None


def register_handlers():
    bpy.types.Scene.allset_soft_select = bpy.props.BoolProperty(
        name="Soft Select", description="Maya soft selection (one setting for object and component mode; B)",
        get=_prop_get, set=_prop_set, options={'SKIP_SAVE'})
    bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)
    bpy.app.handlers.load_post.append(_on_load)
    bpy.app.handlers.undo_post.append(_on_rebaseline)
    bpy.app.handlers.redo_post.append(_on_rebaseline)
    _subscribe()
    # Maya mode starts with the global state (off on a fresh start); bpy.data is restricted during register.
    bpy.app.timers.register(_push_later, first_interval=0.0)


def unregister_handlers():
    if bpy.app.timers.is_registered(_push_later):
        bpy.app.timers.unregister(_push_later)
    bpy.msgbus.clear_by_owner(_owner)
    for lst, fn in ((bpy.app.handlers.redo_post, _on_rebaseline), (bpy.app.handlers.undo_post, _on_rebaseline),
                    (bpy.app.handlers.load_post, _on_load), (bpy.app.handlers.depsgraph_update_post, _on_depsgraph)):
        if fn in lst:
            lst.remove(fn)
    del bpy.types.Scene.allset_soft_select


# --- falloff maths (numpy, no bpy) ---------------------------------------------------------------

# Colour ramp "1,1,0,1,1, 1,0,0,0.5,1, 0,0,0,0,1": (r, g, b, position, linear).
RAMP_POS = (0.0, 0.5, 1.0)
RAMP_RGB = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0))


def ramp(w):
    """Maya's soft select false colour for weights ``w`` (n,) -> (n, 3)."""
    w = np.clip(np.asarray(w, dtype=np.float64), 0.0, 1.0)
    rgb = np.array(RAMP_RGB)
    return np.stack([np.interp(w, RAMP_POS, rgb[:, k]) for k in range(3)], axis=-1)


def falloff(t, kind):
    """Blender calculatePropRatio: ``t`` = (radius - distance) / radius in [0, 1]."""
    t = np.clip(t, 0.0, 1.0)
    if kind == 'SHARP':
        return t * t
    if kind == 'SMOOTH':
        return 3.0 * t * t - 2.0 * t * t * t
    if kind == 'ROOT':
        return np.sqrt(t)
    if kind == 'CONSTANT':
        return np.ones_like(t)
    if kind == 'SPHERE':
        return np.sqrt(np.maximum(2.0 * t - t * t, 0.0))
    if kind == 'INVERSE_SQUARE':
        return t * (2.0 - t)
    return t          # LINEAR; RANDOM (re-rolled by every transform) is drawn as LINEAR


_PAIR_BUDGET = 4_000_000


def _nearest(points, targets):
    """Distance from each of ``points`` to the nearest of ``targets`` (both (n, k))."""
    out = np.empty(len(points))
    if len(targets) * len(points) > 40 * _PAIR_BUDGET:
        from mathutils.kdtree import KDTree
        k = targets.shape[1]
        tree = KDTree(len(targets))
        for i, p in enumerate(targets):
            tree.insert(tuple(p) if k == 3 else (p[0], p[1], 0.0), i)
        tree.balance()
        for i, p in enumerate(points):
            out[i] = tree.find(tuple(p) if k == 3 else (p[0], p[1], 0.0))[2]
        return out
    step = max(1, _PAIR_BUDGET // max(len(targets), 1))
    for a in range(0, len(points), step):
        d = points[a:a + step, None, :] - targets[None, :, :]
        out[a:a + step] = np.sqrt(np.min(np.einsum('ijk,ijk->ij', d, d), axis=1))
    return out


def _plane(v, axis):
    axis = np.asarray(axis, dtype=np.float64)
    axis = axis / np.linalg.norm(axis)
    return v - np.outer(v @ axis, axis)


def _volume(co, sel, radius, view_axis):
    d = np.full(len(co), np.inf)
    d[sel] = 0.0
    s = co[sel]
    lo, hi = s.min(axis=0) - radius, s.max(axis=0) + radius
    if view_axis is None:
        cand = np.flatnonzero(~sel & np.all((co >= lo) & (co <= hi), axis=1))
        pts, tgt = co[cand], s
    else:   # projected: only the part of the offset in the view plane counts (depth ignored)
        cand = np.flatnonzero(~sel)
        axis = np.asarray(view_axis, dtype=np.float64)
        axis = axis / np.linalg.norm(axis)
        u = np.cross(axis, (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0))
        u /= np.linalg.norm(u)
        v = np.cross(axis, u)
        basis = np.stack([u, v], axis=1)
        pts, tgt = co[cand] @ basis, s @ basis
        lo2, hi2 = tgt.min(axis=0) - radius, tgt.max(axis=0) + radius
        keep = np.all((pts >= lo2) & (pts <= hi2), axis=1)
        cand, pts = cand[keep], pts[keep]
    if len(cand):
        d[cand] = _nearest(pts, tgt)
    return d


def _tri_dist(v0, v1, v2, d1, d2):
    """BLI geodesic_distance_propagate_across_triangle, vectorised: distance at v0 from known d1 at v1 and d2
    at v2."""
    v10 = v0 - v1
    v12 = v2 - v1
    fall = np.minimum(d1 + np.linalg.norm(v10, axis=1), d2 + np.linalg.norm(v0 - v2, axis=1))
    with np.errstate(invalid='ignore', divide='ignore', over='ignore'):
        d12 = np.linalg.norm(v12, axis=1)
        u = v12 / d12[:, None]
        n = np.cross(v12, v10)
        n = n / np.linalg.norm(n, axis=1)[:, None]
        v = np.cross(n, u)
        x0 = np.einsum('ij,ij->i', v10, u)
        y0 = np.abs(np.einsum('ij,ij->i', v10, v))
        a = 0.5 * (1.0 + (d1 * d1 - d2 * d2) / (d12 * d12))
        hh = d1 * d1 - a * a * d12 * d12
        h = np.sqrt(np.maximum(hh, 0.0))
        sx = a * d12
        xi = sx + h * (x0 - sx) / (y0 + h)
        geo = np.hypot(sx - x0, -h - y0)
        ok = ((d1 != 0) & (d2 != 0) & np.isfinite(d1) & np.isfinite(d2) & (d12 > 0) & (hh > 0)
              & (xi >= 0) & (xi <= d12) & np.isfinite(geo))
    return np.where(ok, geo, fall)


def _surface(co, sel, radius, edges, corners):
    """Connected distance: Blender's edge + across-face propagation, run to its fixed point inside the radius
    (a path shorter than the radius never leaves the ball of that radius around the selection)."""
    near = _volume(co, sel, radius, None) <= radius
    d = np.full(len(co), np.inf)
    d[sel] = 0.0
    if edges is not None and len(edges):
        e = edges[near[edges[:, 0]] & near[edges[:, 1]]]
        e = np.concatenate([e, e[:, ::-1]])           # both directions: (to, from)
        elen = np.linalg.norm(co[e[:, 0]] - co[e[:, 1]], axis=1)
    else:
        e, elen = np.zeros((0, 2), dtype=np.int64), np.zeros(0)
    if corners is not None and len(corners):
        c = corners[near[corners[:, 0]] & near[corners[:, 1]] & near[corners[:, 2]]]
    else:
        c = np.zeros((0, 3), dtype=np.int64)
    p0, p1, p2 = co[c[:, 0]], co[c[:, 1]], co[c[:, 2]]
    changed = sel.copy()            # only rows next to a vertex whose distance just changed can improve
    for _ in range(100000):
        new = d.copy()
        if len(e):
            live = changed[e[:, 1]]
            if live.any():
                np.minimum.at(new, e[live, 0], d[e[live, 1]] + elen[live])
        if len(c):
            live = changed[c[:, 1]] | changed[c[:, 2]]
            if live.any():
                d1, d2 = d[c[live, 1]], d[c[live, 2]]
                cand = _tri_dist(p0[live], p1[live], p2[live], d1, d2)
                np.minimum.at(new, c[live, 0], cand)
        new[sel] = 0.0
        changed = new < d - 1e-9
        d = new
        if not changed.any():
            break
    return d


def distances(co, sel, radius, edges=None, corners=None, connected=False, view_axis=None):
    co = np.asarray(co, dtype=np.float64)
    sel = np.asarray(sel, dtype=bool)
    if not sel.any():
        return np.full(len(co), np.inf)
    if connected:
        return _surface(co, sel, radius, edges, corners)
    return _volume(co, sel, radius, view_axis)


def weights(co, sel, radius, kind, edges=None, corners=None, connected=False, view_axis=None):
    """Blender's proportional factor per vertex (selected 1, beyond the radius 0)."""
    d = distances(co, sel, radius, edges, corners, connected, view_axis)
    w = np.zeros(len(d))
    radius = max(float(radius), 1e-12)
    inside = d <= radius
    w[inside] = falloff((radius - d[inside]) / radius, kind)
    w[np.asarray(sel, dtype=bool)] = 1.0
    return w


def face_corners(faces):
    """(v0, v1, v2) rows for Blender's face propagation: every face vertex v0 from every face edge (v1, v2)
    it isn't on. ``faces`` = list of vertex index tuples."""
    by_size = {}
    for f in faces:
        by_size.setdefault(len(f), []).append(f)
    out = [np.zeros((0, 3), dtype=np.int64)]
    for n, group in by_size.items():
        if n < 3:
            continue
        f = np.array(group, dtype=np.int64)            # (m, n)
        for k in range(n):
            v1, v2 = f[:, k], f[:, (k + 1) % n]
            for j in range(n):
                if j != k and j != (k + 1) % n:
                    out.append(np.stack([f[:, j], v1, v2], axis=1))
    return np.concatenate(out)
