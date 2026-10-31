# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Attach to Motion Path / Set Motion Path Key on Follow Path.

- Attach to Motion Path (default option values): the
  selected objects + one curve in any order (Maya takes the curve as the path). Per
  object one Follow Path constraint ``motionPathN`` (Maya's node name, numbered one past the highest) with Fixed
  Position on: its Offset = Maya's ``uValue`` in fraction mode (arc-length fraction), keyed at the Time Slider start
  (0) and end (1) with Maya auto tangents (two keys = flat ends; ``driven_key.maya_auto``), constant extrapolation.
  Maya places the object on the path without adding its own position or rotation (``mp_offset`` /
  ``mp_rotated_obj`` = ``mp_default``), so the object's Translate (and Rotate while Follow is on) are zeroed
  (Blender's Follow Path adds the owner's transform).
- Arc length: Blender's path is the evaluated polyline of the curve; at the default 12 per segment the position is
  off by 5e-3 (0.15 deg) on the test path, so the path's splines get ``PATH_POINTS`` evaluated points (resolution
  256 on the 4-span path: within about 1e-4 of the exact arc length; rotation 1e-3 deg).
- Front / Up axis: Maya local X / Y / Z = Blender X / Z / -Y. Blender's Up is a positive axis
  only: a negative up axis (Maya Up Z, or Inverse up) is the positive one plus a 180 deg delta rotation about the
  front axis (the owner's rotation is applied inside the path frame). World up: Blender keeps the up axis toward
  world Z (Maya Scene up = Vector (0, 1, 0)); on a planar path that matches Maya, on a 3D path Blender's roll rule
  (vec_to_quat) differs from Maya's world-up projection (by several degrees). Bank, Object up / Object rotation
  up / Normal and other world up vectors have no Follow Path equivalent (option window ``missing``).
- Parametric length on (Maya fractionMode off): Blender's path is always by length, so the Maya
  parameter keys (start -> 0, end -> maxValue) are kept on the object (``PROP``) and the Offset is baked to their
  arc-length fraction on every frame (exact on whole frames, linear between; not live when the curve changes).
- Set Motion Path Key (``setKeyPath``): Maya adds an
  edit point at the object's current position — the cubic is re-interpolated through the old edit points plus that
  position, with the old knots plus a new knot placed between the neighbouring edit points by chord length,
  and the old end derivatives — and keys ``uValue`` at the current time with the point's fraction of the new curve
  (auto tangents). A non-uniform curve
  is written as an exact Bezier decomposition (``curves_maya.write_spline``); its Maya knots stay in ``KNOTS_PROP``
  while the Bezier still matches them.
"""

import bisect
import math

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty

from .. import compat, results, undo_steps
from . import curves_maya, naming
from . import curves_math as cm

PROP = "allset_motion_path"          # object ID prop: {"constraint", "parametric", "keys" (parametric: f, u, ...)}
KNOTS_PROP = "allset_mp_maya_curve"  # curve data ID prop: Maya knots / CVs of a spline written as Bezier
PATH_POINTS = 1024                   # evaluated points per path spline (module docstring)
DENSE = 4096                         # arc-length table samples
BASE = "motionPath"

MSG_SELECT = "Select the objects to animate and one curve for the path."
MSG_AXES = "The front and up axes must differ."
MSG_NO_PATH = "Select an object attached to a motion path."

# Maya local axis -> Blender local axis and sign (Maya Y-up)
AXIS = {"X": ("X", 1), "Y": ("Z", 1), "Z": ("Y", -1)}
FORWARD = {("X", 1): 'FORWARD_X', ("Y", 1): 'FORWARD_Y', ("Z", 1): 'FORWARD_Z',
           ("X", -1): 'TRACK_NEGATIVE_X', ("Y", -1): 'TRACK_NEGATIVE_Y', ("Z", -1): 'TRACK_NEGATIVE_Z'}


# --- the path curve ---------------------------------------------------------------------------------------------------

def _segments(sp):
    if sp.type == 'BEZIER':
        n = len(sp.bezier_points)
    else:
        n = len(sp.points)
    return max(1, n if sp.use_cyclic_u else n - 1)


def prepare_path(cob):
    """Blender's path follows the evaluated polyline: give every spline ``PATH_POINTS`` points (module docstring)."""
    cu = cob.data
    cu.use_path = True
    for sp in cu.splines:
        if sp.type == 'POLY':
            continue
        want = min(1024, max(sp.resolution_u, math.ceil(PATH_POINTS / _segments(sp))))
        if sp.resolution_u != want:
            sp.resolution_u = want


def _flat_bezier(cvs, knots):
    segs = cm.to_bezier(list(cvs), list(knots), 3)
    out = [segs[0][0]]
    for s in segs:
        out += [s[1], s[2], s[3]]
    return out


def maya_curve(cob):
    """The path's first spline as a Maya curve (local space): stored Maya knots while the Bezier still matches."""
    sp = cob.data.splines[0]
    mc = curves_maya.read_spline(sp)
    stored = cob.data.get(KNOTS_PROP)
    if stored and sp.type == 'BEZIER':
        knots = [float(k) for k in stored["knots"]]
        flat = list(stored["cvs"])
        cvs = [tuple(flat[i:i + 3]) for i in range(0, len(flat), 3)]
        try:
            bez = _flat_bezier(cvs, knots)
        except (ValueError, IndexError):
            bez = []
        if len(bez) == len(mc.cvs) and all(cm.norm(cm.sub(a, b)) < 1e-5 for a, b in zip(bez, mc.cvs)):
            return curves_maya.MCurve(cvs, knots, 3)
    return mc


class Lengths:
    """Arc-length table of a Maya curve: parameter <-> fraction of the length."""

    def __init__(self, mc, dense=DENSE):
        a, b = mc.knots[0], mc.knots[-1]
        self.a, self.b = a, b
        self.u = [a + (b - a) * i / dense for i in range(dense + 1)]
        pts = [cm.evaluate(mc.cvs, mc.knots, mc.degree, u, mc.weights) for u in self.u]
        acc = [0.0]
        for p, q in zip(pts, pts[1:]):
            acc.append(acc[-1] + cm.norm(cm.sub(q, p)))
        self.acc = acc
        self.total = acc[-1]

    def fraction(self, u):
        u = min(max(u, self.a), self.b)
        i = min(max(bisect.bisect_right(self.u, u) - 1, 0), len(self.u) - 2)
        t = (u - self.u[i]) / (self.u[i + 1] - self.u[i])
        s = self.acc[i] + t * (self.acc[i + 1] - self.acc[i])
        return s / self.total if self.total else 0.0

    def param(self, fraction):
        s = min(max(fraction, 0.0), 1.0) * self.total
        i = min(max(bisect.bisect_right(self.acc, s) - 1, 0), len(self.acc) - 2)
        seg = self.acc[i + 1] - self.acc[i]
        t = (s - self.acc[i]) / seg if seg else 0.0
        return self.u[i] + t * (self.u[i + 1] - self.u[i])


def insert_edit_point(mc, u):
    """Maya setKeyPath's curve edit at curve parameter ``u`` (module docstring): (new Maya curve, new knot), or None
    when Maya's rule doesn't apply here (not a cubic with simple inner knots, periodic / rational, u at an end or on a
    knot)."""
    if mc.periodic or mc.weights or mc.degree != 3:
        return None
    knots = list(mc.knots)
    inner = knots[3:-3]
    if len(set(inner)) != len(inner):
        return None
    uniq = sorted(set(knots))
    if u <= uniq[0] + 1e-9 or u >= uniq[-1] - 1e-9 or any(abs(u - k) < 1e-9 for k in uniq):
        return None
    # the new knot sits between its edit points by chord length (Maya: the object at curve parameter 0.699 on
    # span [0, 1] between edit points (0,0,0) and (10,0,0) -> knot 0.719319 = 7.945 / (7.945 + 3.100))
    i = max(j for j in range(len(uniq) - 1) if uniq[j] < u)
    pos = cm.evaluate(mc.cvs, knots, 3, u)
    ea, eb = (cm.evaluate(mc.cvs, knots, 3, uniq[j]) for j in (i, i + 1))
    da, db = cm.norm(cm.sub(pos, ea)), cm.norm(cm.sub(eb, pos))
    knot = uniq[i] + (uniq[i + 1] - uniq[i]) * (da / (da + db) if da + db > 0.0 else 0.5)
    params = sorted(uniq + [knot])
    pts = [pos if p == knot else cm.evaluate(mc.cvs, knots, 3, p) for p in params]
    d0 = cm.evaluate(mc.cvs, knots, 3, knots[0], deriv=1)
    d1 = cm.evaluate(mc.cvs, knots, 3, knots[-1], deriv=1)
    new_knots = sorted(knots + [knot])
    cvs = cm.interpolate(pts, params, new_knots, 3, d0, d1)
    return curves_maya.MCurve(cvs, new_knots, 3), knot


def write_path(cob, mc):
    """Replace the path's only spline with ``mc`` (Bezier when non-uniform; Maya knots kept in ``KNOTS_PROP``)."""
    data = cob.data
    data.splines.clear()
    sp = curves_maya.write_spline(data, mc)
    if sp.type == 'BEZIER':
        data[KNOTS_PROP] = {"knots": list(mc.knots), "cvs": [c for p in mc.cvs for c in p]}
    elif KNOTS_PROP in data:
        del data[KNOTS_PROP]
    prepare_path(cob)


# --- the u curve -----------------------------------------------------------------------------------------------------

def hermite(keys, t):
    """Value at ``t`` of sorted (frame, value) keys with Maya auto tangents, constant outside."""
    from .driven_key import maya_slopes
    if not keys:
        return 0.0
    if t <= keys[0][0] or len(keys) == 1:
        return keys[0][1]
    if t >= keys[-1][0]:
        return keys[-1][1]
    m = maya_slopes(keys)
    i = max(j for j in range(len(keys) - 1) if keys[j][0] <= t)
    (x0, y0), (x1, y1) = keys[i], keys[i + 1]
    h = x1 - x0
    s = (t - x0) / h
    return ((2 * s ** 3 - 3 * s ** 2 + 1) * y0 + (s ** 3 - 2 * s ** 2 + s) * h * m[i]
            + (-2 * s ** 3 + 3 * s ** 2) * y1 + (s ** 3 - s ** 2) * h * m[i + 1])


def find(ob):
    """The kit motion path (Follow Path constraint) of ``ob``, or None."""
    rec = ob.get(PROP)
    if not rec:
        return None
    c = ob.constraints.get(rec.get("constraint", ""))
    return c if c is not None and c.type == 'FOLLOW_PATH' else None


def offset_path(c):
    return c.path_from_id("offset_factor")


def offset_curve(ob, c):
    path = offset_path(c)
    return next((fc for fc in compat.id_fcurves(ob) if fc.data_path == path), None)


def _key(ob, c, frame, value):
    c.offset_factor = min(max(value, 0.0), 1.0)
    ob.keyframe_insert(offset_path(c), frame=frame)


def _clear_keys(ob, c):
    fc = offset_curve(ob, c)
    coll = compat.id_fcurve_collection(ob)
    if fc is not None and coll is not None:
        coll.remove(fc)


def _finish_auto(ob, c):
    from .driven_key import maya_auto
    fc = offset_curve(ob, c)
    if fc is not None:
        maya_auto(fc)
        fc.extrapolation = 'CONSTANT'


def bake_parametric(ob, c, lengths):
    """Offset keys on every frame of the stored Maya parameter keys (module docstring)."""
    rec = ob[PROP]
    flat = list(rec.get("keys", ()))
    keys = sorted((flat[i], flat[i + 1]) for i in range(0, len(flat), 2))
    _clear_keys(ob, c)
    if not keys:
        return
    frames = sorted({k[0] for k in keys} | set(range(math.ceil(keys[0][0]), math.floor(keys[-1][0]) + 1)))
    for f in frames:
        _key(ob, c, f, lengths.fraction(hermite(keys, f)))
    fc = offset_curve(ob, c)
    if fc is not None:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
        fc.extrapolation = 'CONSTANT'
        fc.update()


def remove(ob):
    """Drop ``ob``'s kit motion path (constraint, its keys, the record)."""
    c = find(ob)
    if c is not None:
        _clear_keys(ob, c)
        ob.constraints.remove(c)
    if PROP in ob:
        del ob[PROP]


def _zero_rotation(ob):
    ob.rotation_euler = (0.0, 0.0, 0.0)
    ob.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
    ob.rotation_axis_angle = (0.0, 0.0, 1.0, 0.0)


def axes(front, up, inverse_front=False, inverse_up=False):
    """(forward_axis, up_axis, flip axis or None) of Maya front / up axes, or None when they are the same axis."""
    fa, fs = AXIS[front]
    ua, us = AXIS[up]
    if fa == ua:
        return None
    fs = -fs if inverse_front else fs
    us = -us if inverse_up else us
    return FORWARD[(fa, fs)], 'UP_' + ua, (fa if us < 0 else None)


def time_keys(scene, time_range, start, end, last):
    """Maya's u keys of the time range option: Time Slider = playback range, Start = one key, Start/End."""
    if time_range == 'TIME_SLIDER':
        from ..ui import time_slider
        a, b = time_slider.playback_range(scene)
        return [(float(a), 0.0), (float(b), last)]
    if time_range == 'START':
        return [(float(start), 0.0)]
    return [(float(start), 0.0), (float(end), last)]


def attach(context, objects, cob, time_range='TIME_SLIDER', start=1.0, end=30.0, parametric=False, follow=True,
           front="X", up="Y", inverse_front=False, inverse_up=False):
    """Attach ``objects`` to curve object ``cob``; the constraints made."""
    ax = axes(front, up, inverse_front, inverse_up)
    if ax is None:
        raise ValueError(MSG_AXES)
    forward, up_axis, flip = ax
    prepare_path(cob)
    mc = maya_curve(cob)
    lengths = Lengths(mc) if parametric else None
    last = mc.knots[-1] if parametric else 1.0
    keys = time_keys(context.scene, time_range, start, end, last)
    if parametric:
        keys = [(f, mc.knots[0] if v == 0.0 else v) for f, v in keys]
    taken = {c.name for o in bpy.data.objects for c in o.constraints}
    made = []
    for ob in objects:
        remove(ob)
        name = f"{BASE}{naming.next_number(BASE, taken)}"
        taken.add(name)
        c = ob.constraints.new('FOLLOW_PATH')
        c.name = name
        c.target = cob
        c.use_fixed_location = True
        c.use_curve_follow = follow
        c.forward_axis = forward
        c.up_axis = up_axis
        ob.location = (0.0, 0.0, 0.0)
        if follow:
            _zero_rotation(ob)
        ob.delta_rotation_euler = tuple(math.pi if flip == a else 0.0 for a in "XYZ")
        ob[PROP] = {"constraint": name, "parametric": int(parametric),
                    "keys": [x for k in keys for x in k] if parametric else []}
        if parametric:
            bake_parametric(ob, c, lengths)
        else:
            for f, v in keys:
                _key(ob, c, f, v)
            _finish_auto(ob, c)
        made.append(c)
    return made


def set_path_key(context, ob, frame=None):
    """Maya Set Motion Path Key on ``ob`` at ``frame`` (current time): edit point + u key (module docstring).
    Returns the keyed Maya value (fraction, or parameter when parametric)."""
    c = find(ob)
    cob = c.target
    scene = context.scene
    if frame is None:
        frame = scene.frame_current + scene.frame_subframe
    rec = ob[PROP]
    parametric = bool(rec.get("parametric"))
    mc = maya_curve(cob)
    lengths = Lengths(mc)
    if parametric:
        flat = list(rec.get("keys", ()))
        keys = sorted((flat[i], flat[i + 1]) for i in range(0, len(flat), 2))
        u = hermite(keys, frame)
    else:
        fc = offset_curve(ob, c)
        frac = fc.evaluate(frame) if fc is not None else c.offset_factor
        u = lengths.param(frac)
    edit = insert_edit_point(mc, u) if len(cob.data.splines) == 1 else None
    if edit is not None:
        new, u = edit           # the object's point is the new edit point, at the new knot
        write_path(cob, new)
        lengths = Lengths(new)
    else:
        prepare_path(cob)
    if parametric:
        keys = [k for k in keys if abs(k[0] - frame) > 1e-6] + [(frame, u)]
        rec["keys"] = [x for k in sorted(keys) for x in k]
        bake_parametric(ob, c, lengths)
        return u
    value = lengths.fraction(u)
    _key(ob, c, frame, value)
    _finish_auto(ob, c)
    return value


# --- operators -------------------------------------------------------------------------------------------------------

_XYZ = [(a, a, "") for a in "XYZ"]


@undo_steps.no_redo_panel      # Maya has no redo panel
class ALLSET_OT_motion_path_attach(bpy.types.Operator):
    """Maya Attach to Motion Path: animate the selected objects along the selected curve (Follow Path constraint,
    its Offset keyed over the Time Slider)"""
    bl_idname = "allset.motion_path_attach"
    bl_label = "Attach to Motion Path"
    bl_options = {'REGISTER', 'UNDO'}

    time_range: EnumProperty(name="Time range", items=(
        ('TIME_SLIDER', "Time Slider", "The Time Slider's playback range"),
        ('START', "Start", "One key at the start time"),
        ('START_END', "Start/End", "Keys at the start and end times")), default='TIME_SLIDER')
    start_time: FloatProperty(name="Start time", default=1.0)
    end_time: FloatProperty(name="End time", default=30.0)
    parametric: BoolProperty(name="Parametric length", default=False,
                             description="Move by curve parameter (Maya fraction mode off) instead of by length")
    follow: BoolProperty(name="Follow", default=True, description="Turn the object along the path")
    front_axis: EnumProperty(name="Front axis", items=_XYZ, default="X")
    up_axis: EnumProperty(name="Up axis", items=_XYZ, default="Y")
    inverse_up: BoolProperty(name="Inverse up", default=False)
    inverse_front: BoolProperty(name="Inverse front", default=False)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        sel = list(context.selected_objects)
        curves = [o for o in sel if o.type == 'CURVE']
        act = context.active_object
        if act is not None and act.type == 'CURVE' and act in sel:
            path = act
        elif len(curves) == 1:
            path = curves[0]
        else:
            path = None
        objects = [o for o in sel if o is not path]
        if path is None or not objects or not path.data.splines:
            self.report({'WARNING'}, MSG_SELECT)
            return {'CANCELLED'}
        try:
            made = attach(context, objects, path, self.time_range, self.start_time, self.end_time, self.parametric,
                          self.follow, self.front_axis, self.up_axis, self.inverse_front, self.inverse_up)
        except ValueError as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        context.view_layer.update()
        results.result(self, ", ".join(c.name for c in made))
        return {'FINISHED'}


@undo_steps.no_redo_panel
class ALLSET_OT_motion_path_key(bpy.types.Operator):
    """Maya Set Motion Path Key: key the selected objects' place on their motion path at the current time (adds an
    edit point to the path there)"""
    bl_idname = "allset.motion_path_key"
    bl_label = "Set Motion Path Key"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        obs = [o for o in context.selected_objects if find(o) is not None and find(o).target is not None]
        if not obs:
            self.report({'WARNING'}, MSG_NO_PATH)
            return {'CANCELLED'}
        for ob in obs:
            set_path_key(context, ob)
        context.view_layer.update()
        results.result(self, ", ".join(find(o).name for o in obs))
        return {'FINISHED'}


classes = (ALLSET_OT_motion_path_attach, ALLSET_OT_motion_path_key)


# --- option window (Maya Attach to Motion Path Options factory values) -----

WINDOWS = []
_RANGE = {"Time Slider": 'TIME_SLIDER', "Start": 'START', "Start/End": 'START_END'}


def _run(context, v):
    return bpy.ops.allset.motion_path_attach(
        'EXEC_DEFAULT', time_range=_RANGE[v["time_range"]], start_time=v["start_time"], end_time=v["end_time"],
        parametric=v["parametric"], follow=v["follow"], front_axis=v["front_axis"], up_axis=v["up_axis"],
        inverse_up=v["inverse_up"], inverse_front=v["inverse_front"])


def windows():
    if not WINDOWS:
        from .option_windows import F, Window
        WINDOWS.append(Window(
            "motion_path_attach", "Attach to Motion Path Options", "Attach", ("allset.motion_path_attach", {}), [
                F("time_range", "Time range:", "enum", "Time Slider", items=list(_RANGE)),
                F("start_time", "Start time:", "float", 1.0),
                F("end_time", "End time:", "float", 30.0),
                F("parametric", "Parametric length:", "bool", False),
                F("follow", "Follow:", "bool", True),
                F("front_axis", "Front axis:", "enum", "X", items=["X", "Y", "Z"]),
                F("up_axis", "Up axis:", "enum", "Y", items=["X", "Y", "Z"]),
                F("inverse_up", "", "bool", False, text="Inverse up"),
                F("inverse_front", "", "bool", False, text="Inverse front"),
            ], _run, paths=("Constrain/Motion Paths/Attach to Motion Path",),
            missing=("World up type Object up / Object rotation up / Normal (Blender keeps the up axis toward world Z "
                     "= Scene up / Vector 0 1 0)", "World up vector / object", "Bank / Bank scale / Bank limit")))
    return WINDOWS


def register_props():
    pass


def unregister_props():
    pass
