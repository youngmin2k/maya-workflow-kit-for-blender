# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya weighted / non-weighted tangents and tangent length locks.

Maya:
- a weighted tangent's weight is the Bezier arm length in (frame, value) space, the angle is taken there too:
  control point = key ± w·(cos a, sin a). Maya ``ix / iy`` = 3 × the arm in (seconds, value), so
  arm frames = ix·fps / 3, arm value = iy / 3 — exactly a Blender F-curve handle (FREE) minus its key.
- a non-weighted curve keeps every arm's time extent at Δt/3 of its neighbour interval (first / last key: their one
  interval), the angle free; Weighted Tangents keeps the shape, Non-weighted Tangents puts every arm back to Δt/3
  keeping its angle (the shape changes, key 5 at 40° stays 40°).
- Lock Tangent Length (default free): with the length locked, changing the angle keeps the weight.

Blender's F-curve handles already are weighted tangents, so the kit only stores what Maya adds:

``Action["allset_weights"]`` = {"<data_path>|<array_index>": {"w": 0 | 1, "n": key count, "locks": flat floats}}
- "w" 0 = the curve is non-weighted (the Δt/3 rule applies), 1 = weighted; a curve with no entry is weighted
  (Blender's nature: only curves the kit marked non-weighted get the Δt/3 rule).
- "locks" = [index, frame, left length, right length] per locked key; "n" = the curve's key count when they were
  written. A lock finds its key by frame (±1e-3); when no key sits there but the key count is still "n" (keys
  were moved, none added / removed) it takes the key at the stored index and follows its new frame.

Keeping the rules (``apply_rules``):
- live: a ``depsgraph_update_post`` handler re-applies both rules to every Action an update touched, so while a
  tangent handle of a non-weighted curve is dragged in the Graph Editor only its angle follows the mouse (Blender's
  transform recomputes each move from its start positions, the correction never adds up; the handler runs before
  the redraw). Its writes tag the Action once more and the next pass finds nothing to change.
- ``watch(context)`` (every 0.25 s from ``ui/graph_view._tick``) does the same for every marked Action; it waits while
  a modal operator runs, except the kit's click listeners (``LISTENERS``) that stay up for the whole session.
Only FREE / ALIGNED handles are rewritten: AUTO / AUTO_CLAMPED / VECTOR handles are Blender's to compute (a drag
turns them ALIGNED / FREE and then the rule applies). The writes push no undo step of their own.

New curves made by keying (Blender's own keying included: I key, Insert Keyframe, auto keying) get the Default
Tangent Weight (``adopt``): a curve of a local Action that is not part of the animation the file was loaded with
(``take_baseline`` at register / load), has no stored entry and holds exactly one key on the current frame. Loaded,
imported and appended animation keeps its tangents: it is in the baseline or has more than one key (a one-key curve
has no arm a rule could change).
"""

import math

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty

from .. import compat
from .. import results

PROP = "allset_weights"
EDITABLE = {'FREE', 'ALIGNED'}
EPS = 1e-6
# handles are float32: a rewritten arm reads back within ~1e-7 x the coordinate's size, so the watch compares with a
# tolerance that grows with the key's coordinates (else it would rewrite the same arm every tick)


def _tol(kp):
    return EPS + 2e-6 * max(1.0, abs(kp.co[0]), abs(kp.co[1]))
FRAME_TOL = 1e-3


# --- storage -------------------------------------------------------------------------------------------------

def curve_key(fc):
    return f"{fc.data_path}|{fc.array_index}"


def owner(fc):
    """The ID the curve's Maya data lives on: its Action (``fc.id_data`` in 4.5 and 5.x), or None."""
    ob = getattr(fc, "id_data", None)
    return ob if isinstance(ob, bpy.types.ID) else None


def _entry(fc, create=False):
    ob = owner(fc)
    if ob is None:
        return None
    if PROP not in ob:
        if not create:
            return None
        ob[PROP] = {}
    data = ob[PROP]
    key = curve_key(fc)
    if key not in data:
        if not create:
            return None
        data[key] = {"w": 1, "n": 0, "locks": []}
    return data[key]


def is_weighted(fc):
    entry = _entry(fc)
    return entry is None or int(entry.get("w", 1)) != 0


def set_weighted(fc, weighted):
    entry = _entry(fc, create=True)
    if entry is not None:
        entry["w"] = 1 if weighted else 0


def apply_default(fc, context=None):
    """Mark a curve the kit just created per add-on pref ``default_tangent_weight`` (Maya Curves > Default
    Tangent Weight); a non-weighted one gets its arms to Δt/3 right away. Returns the curve's weighted state."""
    from .. import preferences
    try:
        weighted = preferences.get(context).default_tangent_weight == 'WEIGHTED'
    except (KeyError, AttributeError):
        weighted = False
    set_weighted(fc, weighted)
    if not weighted:
        third_arms(fc)
    return weighted


def locks(fc):
    """{key index: (frame, left length, right length)} of the curve's locked keys (stored indices)."""
    entry = _entry(fc)
    if entry is None:
        return {}
    flat = list(entry.get("locks", ()))
    return {int(flat[i]): (flat[i + 1], flat[i + 2], flat[i + 3]) for i in range(0, len(flat) - 3, 4)}


def _write_locks(fc, table):
    entry = _entry(fc, create=bool(table))
    if entry is None:
        return
    flat = []
    for i in sorted(table):
        flat.extend((float(i),) + tuple(float(v) for v in table[i]))
    entry["locks"] = flat
    entry["n"] = len(fc.keyframe_points)


def _arm(kp, side):
    h = kp.handle_left if side == 0 else kp.handle_right
    return h[0] - kp.co[0], h[1] - kp.co[1]


def _set_arm(kp, side, dx, dy):
    x, y = kp.co[0] + dx, kp.co[1] + dy
    if side == 0:
        kp.handle_left = (x, y)
    else:
        kp.handle_right = (x, y)


def _type(kp, side):
    return kp.handle_left_type if side == 0 else kp.handle_right_type


def lock_keys(fc, points):
    """Lock the arm lengths of ``points`` (keyframe points of ``fc``)."""
    table = dict(locks(fc))
    index = {kp.as_pointer(): i for i, kp in enumerate(fc.keyframe_points)}
    for kp in points:
        i = index.get(kp.as_pointer())
        if i is not None:
            table[i] = (kp.co[0], math.hypot(*_arm(kp, 0)), math.hypot(*_arm(kp, 1)))
    _write_locks(fc, table)


def free_keys(fc, points):
    table = dict(locks(fc))
    if not table:
        return
    index = {kp.as_pointer(): i for i, kp in enumerate(fc.keyframe_points)}
    frames = [kp.co[0] for kp in points]
    for i in list(table):
        if any(abs(table[i][0] - f) <= FRAME_TOL for f in frames) or i in {index.get(kp.as_pointer()) for kp in points}:
            del table[i]
    _write_locks(fc, table)


def _locked_points(fc):
    """[(keyframe point, left length, right length)] after mapping the stored locks to the current keys."""
    table = locks(fc)
    if not table:
        return []
    pts = fc.keyframe_points
    entry = _entry(fc)
    same_count = int(entry.get("n", -1)) == len(pts)
    out, moved = [], False
    for i, (frame, ll, lr) in table.items():
        kp = next((p for p in pts if abs(p.co[0] - frame) <= FRAME_TOL), None)
        if kp is None and same_count and 0 <= i < len(pts):
            kp = pts[i]
            moved = True
        if kp is not None:
            out.append((kp, ll, lr))
    if moved:
        index = {kp.as_pointer(): i for i, kp in enumerate(pts)}
        _write_locks(fc, {index[kp.as_pointer()]: (kp.co[0], ll, lr) for kp, ll, lr in out})
    return out


# --- the Maya rules ---------------------------------------------------------------------------------------------

def third(fc, i, side):
    """Δt/3 of key ``i``'s neighbour interval on ``side`` (0 left, 1 right); the end keys use their one interval.
    None for a single-key curve."""
    pts = fc.keyframe_points
    n = len(pts)
    if n < 2:
        return None
    if side == 0:
        j = i - 1 if i > 0 else i + 1
    else:
        j = i + 1 if i < n - 1 else i - 1
    return abs(pts[j].co[0] - pts[i].co[0]) / 3.0


def third_arms(fc, only_editable=True):
    """Every arm's time extent back to Δt/3 keeping its angle (Maya non-weighted). Returns the number of arms
    changed. A vertical arm (no time extent) keeps its place: its angle can't be kept at another length."""
    changed = 0
    for i, kp in enumerate(fc.keyframe_points):
        for side in (0, 1):
            if only_editable and _type(kp, side) not in EDITABLE:
                continue
            t = third(fc, i, side)
            if t is None:
                continue
            dx, dy = _arm(kp, side)
            if abs(dx) < 1e-12 or abs(abs(dx) - t) <= _tol(kp):
                continue
            f = t / abs(dx)
            _set_arm(kp, side, dx * f, dy * f)
            changed += 1
    return changed


def keep_lengths(fc):
    """Locked keys of a weighted curve get their stored arm lengths back (direction kept)."""
    changed = 0
    for kp, ll, lr in _locked_points(fc):
        for side, length in ((0, ll), (1, lr)):
            if _type(kp, side) not in EDITABLE:
                continue
            dx, dy = _arm(kp, side)
            cur = math.hypot(dx, dy)
            if cur < 1e-12 or abs(cur - length) <= _tol(kp):
                continue
            f = length / cur
            _set_arm(kp, side, dx * f, dy * f)
            changed += 1
    return changed


def target_curves(context):
    """Curves with a selected key or a selected channel among the visible ones (``graph_keys.insert_curves``
    rule, locked curves included), else every visible curve."""
    curves = list(getattr(context, "visible_fcurves", None) or getattr(context, "editable_fcurves", None) or ())
    picked = [fc for fc in curves if fc.select or any(kp.select_control_point for kp in fc.keyframe_points)]
    return picked or curves


def selected_points(fc):
    return [kp for kp in fc.keyframe_points
            if kp.select_control_point or kp.select_left_handle or kp.select_right_handle]


# --- watch -----------------------------------------------------------------------------------------------------

# Kit modals that only listen for clicks and stay up for the whole session: they edit no keys
LISTENERS = {"ALLSET_OT_pose_empty_click", "ALLSET_OT_joint_outliner_select", "ALLSET_OT_cb_channel_drag",
             "ALLSET_OT_cb_wheel"}


def _busy():
    for window in bpy.context.window_manager.windows:
        if any(op.bl_idname not in LISTENERS for op in window.modal_operators):
            return True
    return False


def apply_rules(action):
    """Both rules on one Action's marked curves: Δt/3 arms for non-weighted ones, stored lengths for locked weighted
    ones. Returns the number of arms changed."""
    data = action.get(PROP)
    if data is None:
        return 0
    changed = 0
    for fc in compat.action_fcurves(action):
        entry = data.get(curve_key(fc))
        if entry is None:
            continue
        if int(entry.get("w", 1)) == 0:
            changed += third_arms(fc)
        elif len(entry.get("locks", ())):
            changed += keep_lengths(fc)
    return changed


def _redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type in {'GRAPH_EDITOR', 'VIEW_3D', 'DOPESHEET_EDITOR'}:
                area.tag_redraw()


def watch(context=None):
    """Re-apply the non-weighted Δt/3 rule and the length locks (cheap when nothing is marked; never raises)."""
    try:
        actions = [a for a in bpy.data.actions if PROP in a]
        if not actions or _busy():
            return 0
        changed = sum(apply_rules(action) for action in actions)
        if changed:
            _redraw()
        return changed
    except Exception as exc:    # a timer must never raise
        print("allset graph_weights.watch:", exc)
        return 0


# --- new curves: the Default Tangent Weight for curves made by keying --------------------------------------------

_baseline = {}              # Action name -> curve keys the file was loaded with (or that existed at register)
_state = {"loading": False}


def take_baseline():
    """Remember every curve that exists now: loaded animation is never adopted."""
    _baseline.clear()
    try:
        actions = list(bpy.data.actions)
    except AttributeError:          # restricted data while Blender starts: the startup file's load_post follows
        return
    for action in actions:
        _baseline[action.name] = frozenset(curve_key(fc) for fc in compat.action_fcurves(action))


def new_by_keying(action, fc, frame):
    """True for a curve keying just made: not loaded, exactly one key, on ``frame``."""
    if curve_key(fc) in _baseline.get(action.name, ()):
        return False
    pts = fc.keyframe_points
    return len(pts) == 1 and abs(pts[0].co[0] - frame) <= FRAME_TOL


def adopt(action, scene, context=None):
    """Give the curves keying just made in ``action`` the Default Tangent Weight. Returns how many."""
    if _state["loading"] or action.library is not None or action.override_library is not None:
        return 0
    frame = scene.frame_current + scene.frame_subframe
    n = 0
    for fc in compat.action_fcurves(action):
        data = action.get(PROP)
        if data is not None and curve_key(fc) in data:
            continue
        if new_by_keying(action, fc, frame):
            apply_default(fc, context)
            n += 1
    return n


@persistent
def _on_depsgraph(scene, depsgraph):
    try:
        if not depsgraph.id_type_updated('ACTION'):
            return
        changed = 0
        for update in depsgraph.updates:
            idd = update.id
            if not isinstance(idd, bpy.types.Action):
                continue
            action = idd.original
            adopt(action, scene)
            changed += apply_rules(action)
        if changed:
            _redraw()
    except Exception as exc:        # a handler must never raise
        print("allset graph_weights:", exc)


@persistent
def _load_pre(*_args):
    _state["loading"] = True


@persistent
def _load_post(*_args):
    _state["loading"] = False
    take_baseline()


# --- operators -------------------------------------------------------------------------------------------------

class ALLSET_OT_curve_weights(bpy.types.Operator):
    """Weighted tangents keep their length; non-weighted ones stay a third of the way to the next key
    (Maya Curves > Weighted / Non-weighted Tangents)"""
    bl_idname = "allset.curve_weights"
    bl_label = "Tangent Weights"
    bl_options = {'REGISTER', 'UNDO'}

    weighted: BoolProperty(name="Weighted", default=True, options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        if props.weighted:
            return "Make the curves' tangents weighted: their length can change (Maya Curves > Weighted Tangents)"
        return ("Make the curves' tangents non-weighted: every tangent a third of the way to the next key, its "
                "angle kept (Maya Curves > Non-weighted Tangents)")

    def execute(self, context):
        curves = target_curves(context)
        if not curves:
            self.report({'WARNING'}, "No animation curves")
            return {'CANCELLED'}
        for fc in curves:
            set_weighted(fc, self.weighted)
            if not self.weighted:
                third_arms(fc)
            fc.update()
        results.result(self, f"{len(curves)} curve{'s' if len(curves) != 1 else ''} "
                             f"{'weighted' if self.weighted else 'non-weighted'}")
        return {'FINISHED'}


class ALLSET_OT_tangent_weight_lock(bpy.types.Operator):
    """Lock or free the length of the selected keys' tangents (Maya Tangents > Lock / Free Tangent Length)"""
    bl_idname = "allset.tangent_weight_lock"
    bl_label = "Tangent Length"
    bl_options = {'REGISTER', 'UNDO'}

    lock: BoolProperty(name="Lock", default=True, options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        if props.lock:
            return "Changing a tangent's angle keeps its length (Maya Tangents > Lock Tangent Length)"
        return "Dragging a tangent changes its length (Maya Tangents > Free Tangent Length)"

    def execute(self, context):
        curves = list(getattr(context, "visible_fcurves", None) or ())
        count = 0
        for fc in curves:
            points = selected_points(fc)
            if not points:
                continue
            (lock_keys if self.lock else free_keys)(fc, points)
            count += len(points)
        if not count:
            self.report({'WARNING'}, "Select keys to lock or free their tangent length")
            return {'CANCELLED'}
        results.result(self, f"Tangent length {'locked' if self.lock else 'freed'} on {count} "
                             f"key{'s' if count != 1 else ''}")
        return {'FINISHED'}


classes = (ALLSET_OT_curve_weights, ALLSET_OT_tangent_weight_lock)


_HANDLERS = (("depsgraph_update_post", _on_depsgraph), ("load_pre", _load_pre), ("load_post", _load_post))


def register_handlers():
    _state["loading"] = False
    take_baseline()
    for name, fn in _HANDLERS:
        handlers = getattr(bpy.app.handlers, name)
        if fn not in handlers:
            handlers.append(fn)


def unregister_handlers():
    for name, fn in _HANDLERS:
        handlers = getattr(bpy.app.handlers, name)
        if fn in handlers:
            handlers.remove(fn)
    _baseline.clear()
    _state["loading"] = False
