# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya 2022 Curves menu (maths in
``curves_math`` / ``surfaces_math``, bpy-free).

- Bend / Curl / Scale Curvature = Maya's Curves menu commands on the CVs in object space (Maya Y-up: Blender local
  (x, y, z) is Maya (x, z, -y), the frame's twist axis comes from Maya's world up). Object selected = every CV; in edit
  mode the selected CV range of a spline = Maya's ``cv[a:b]`` (the CVs after b follow).
- Lock / Unlock Length = Maya's ``lockLength`` attribute (curve data ID property); while it is on, CV edits keep every
  CV leg length (``curves_math.keep_leg_lengths``, a depsgraph handler; Maya's CV manipulator rule is).
- CV Hardness = ``cmds.hardenPointCurve(multiplicity=-1)`` on the last selected CV (knots; shape exact through
  write_spline).
- Fit B-spline = fitBspline on degree-1 curves: a new ``fitBsplineCurveN``.
- Align = alignCurve (position + tangent): the first selected curve moves onto the closest end of the other.
- Duplicate Surface Curves = duplicateCurve: the surface's visible isoparms (surface selected) or the isoparms through
  the selected CV rows / columns (edit mode, like Surfaces > Detach), new ``duplicatedCurveN``.
- Intersect = curveIntersect: a locator (Empty) at every crossing on each curve, parented to it (Maya curve-point
  locators ``locatorN``).
"""

import bpy
from bpy.props import EnumProperty, FloatProperty
from mathutils import Matrix, Vector

from .. import results, undo_steps
from . import curves_math as cm
from . import naming, units
from .curves_maya import MCurve, _curves_selected, _new_curve_object, _replace_splines, read_spline
from .modify_maya import selection_order

LOCK = "allset_lock_length"
_last = {}          # curve data pointer -> CV signature last seen (Lock Length)
_busy = [False]


def to_maya(p):
    return (p[0], p[2], -p[1])


def from_maya(p):
    return (p[0], -p[2], p[1])


# --- Bend / Curl / Scale Curvature ------------------------------------------------------------------------------

KINDS = (('BEND', "Bend", "Maya Curves > Bend (default amount 0.2, twist 0)"),
         ('CURL', "Curl", "Maya Curves > Curl (default amount 0.3, frequency 1)"),
         ('CURVATURE', "Scale Curvature", "Maya Curves > Scale Curvature (default 1.1, max curvature 0.8)"))
FACTORY = {'BEND': (0.2, 0.0), 'CURL': (0.3, 1.0), 'CURVATURE': (1.1, 0.8)}


def modify_points(kind, points, a1, a2, start=0, count=None):
    """Maya-space points of one curve -> new points (CVs from ``start`` on, ``count`` of them edited)."""
    pts = [tuple(p) for p in points]
    head, tail = pts[:start], pts[start:]
    if kind == 'BEND':
        tail = cm.bend_cvs(tail, a1, a2, count)
    elif kind == 'CURL':
        tail = cm.curl_cvs(tail, a1, a2, count)
    else:
        tail = cm.scale_curvature_cvs(tail, a1, a2, count)
    return head + [tuple(p) for p in tail]


def _spline_points(sp):
    return sp.bezier_points if sp.type == 'BEZIER' else sp.points


def _selected_range(sp):
    pts = _spline_points(sp)
    sel = [i for i, p in enumerate(pts) if (p.select_control_point if sp.type == 'BEZIER' else p.select)]
    return (sel[0], sel[-1]) if sel else None


@undo_steps.no_redo_panel
class ALLSET_OT_curve_modify(bpy.types.Operator):
    """Bend, curl or scale the curvature of the selected curves (Maya Curves > Bend / Curl / Scale Curvature)"""
    bl_idname = "allset.curve_modify"
    bl_label = "Modify Curves"
    bl_options = {'REGISTER', 'UNDO'}

    kind: EnumProperty(name="Operation", items=KINDS, default='BEND', options={'SKIP_SAVE'})
    amount: FloatProperty(name="Amount", default=-1e9, options={'SKIP_SAVE', 'HIDDEN'})
    second: FloatProperty(name="Second", default=-1e9, options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'EDIT_CURVE'} and any(o.type == 'CURVE' for o in context.selected_objects)

    def execute(self, context):
        a1, a2 = FACTORY[self.kind]
        if self.amount != -1e9:
            a1 = self.amount
        if self.second != -1e9:
            a2 = self.second
        edit = context.mode == 'EDIT_CURVE'
        ranges = {}
        if edit:
            for ob in context.objects_in_mode_unique_data:
                if ob.type == 'CURVE':
                    ranges[ob.name] = [_selected_range(sp) for sp in ob.data.splines]
            bpy.ops.object.mode_set(mode='OBJECT')
        done = 0
        for ob in _curves_selected(context):
            out = []
            for k, sp in enumerate(ob.data.splines):
                c = read_spline(sp)
                rng = ranges.get(ob.name, [None] * (k + 1))[k] if edit else (0, len(c.cvs) - 1)
                if c.periodic or rng is None or len(c.cvs) < 3:
                    out.append(c)
                    continue
                start, last = rng
                if sp.type == 'BEZIER':          # Bezier control points -> their B-spline CV indices
                    start, last = start * 3, min(len(c.cvs) - 1, last * 3)
                count = len(c.cvs) - start if not edit else last - start + 1
                if count < 3:
                    out.append(c)
                    continue
                # Maya numbers are Maya lengths (Bend / Curl amounts are offsets): 1 = one Maya unit
                u = units.maya_unit()
                pts = modify_points(self.kind, [cm.mul(to_maya(p), 1.0 / u) for p in c.cvs], a1, a2, start, count)
                out.append(MCurve([from_maya(cm.mul(p, u)) for p in pts], c.knots, c.degree, c.weights))
                done += 1
            _replace_splines(ob, out)
            remember(ob)
        if edit:
            bpy.ops.object.mode_set(mode='EDIT')
        if not done:
            self.report({'WARNING'}, "Select curves (or a range of at least 3 CVs)")
            return {'CANCELLED'}
        return {'FINISHED'}


# --- Lock / Unlock Length -------------------------------------------------------------------------------------

def _cvs_of(data):
    if any(sp.type == 'BEZIER' for sp in data.splines):
        return None
    return [tuple(p.co[:3]) for sp in data.splines for p in sp.points]


def remember(ob):
    if ob.type == 'CURVE' and ob.data.get(LOCK):
        _last[ob.data.as_pointer()] = _cvs_of(ob.data)


def apply_lock(data):
    """Restore every leg length of a locked curve after its CVs moved (each spline on its own). Returns True when
    something was corrected."""
    old = _last.get(data.as_pointer())
    new = _cvs_of(data)
    if old is None or new is None or len(old) != len(new):
        _last[data.as_pointer()] = new
        return False
    changed = False
    i = 0
    for sp in data.splines:
        n = len(sp.points)
        fixed = cm.keep_leg_lengths(old[i:i + n], new[i:i + n])
        for p, q in zip(sp.points, fixed):
            if (Vector(p.co[:3]) - Vector(q)).length > 1e-9:
                p.co = (*q, p.co[3])
                changed = True
        i += n
    _last[data.as_pointer()] = _cvs_of(data)
    return changed


@bpy.app.handlers.persistent
def _on_depsgraph(scene, depsgraph):
    if _busy[0]:
        return
    try:
        datas = {u.id.original for u in depsgraph.updates if isinstance(u.id, bpy.types.Curve)
                 and u.id.original.get(LOCK)}
    except (ReferenceError, AttributeError):
        return
    if not datas:
        return
    _busy[0] = True
    try:
        for data in datas:
            if apply_lock(data):
                data.update_tag()
    finally:
        _busy[0] = False


@undo_steps.no_redo_panel
class ALLSET_OT_curve_lock_length(bpy.types.Operator):
    """Lock or unlock the length of the selected curves: CV edits then keep the curve's length (Maya Curves > Lock /
    Unlock Length; the shape's lockLength attribute)"""
    bl_idname = "allset.curve_lock_length"
    bl_label = "Lock Length"
    bl_options = {'REGISTER', 'UNDO'}

    lock: bpy.props.BoolProperty(name="Lock", default=True, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return any(o.type == 'CURVE' for o in context.selected_objects)

    def execute(self, context):
        obs = [o for o in context.selected_objects if o.type == 'CURVE']
        for ob in obs:
            ob.data[LOCK] = self.lock
            if self.lock:
                remember(ob)
            else:
                _last.pop(ob.data.as_pointer(), None)
        results.result(self, "%s %s" % ("lockLength" if self.lock else "unlocked", " ".join(o.name for o in obs)))
        return {'FINISHED'}


# --- CV Hardness ------------------------------------------------------------------------------------------------

@undo_steps.no_redo_panel
class ALLSET_OT_curve_cv_hardness(bpy.types.Operator):
    """Give the selected CV full knot multiplicity so the curve passes through it with a corner (Maya Curves > CV
    Hardness; Maya hardens the last selected CV, and only CVs away from the curve ends)"""
    bl_idname = "allset.curve_cv_hardness"
    bl_label = "CV Hardness"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_CURVE'

    def execute(self, context):
        picks = []
        for ob in context.objects_in_mode_unique_data:
            if ob.type != 'CURVE':
                continue
            for k, sp in enumerate(ob.data.splines):
                rng = _selected_range(sp)
                if rng is not None and sp.type != 'BEZIER':
                    picks.append((ob, k, rng[1]))
        bpy.ops.object.mode_set(mode='OBJECT')
        done = 0
        for ob, k, cv in picks:
            out = []
            for j, sp in enumerate(ob.data.splines):
                c = read_spline(sp)
                if j == k and not c.periodic:
                    knots = cm.harden(c.knots, c.degree, cv)
                    if knots != c.knots:
                        c = MCurve(c.cvs, knots, c.degree, c.weights)
                        done += 1
                out.append(c)
            _replace_splines(ob, out)
        bpy.ops.object.mode_set(mode='EDIT')
        if not done:
            self.report({'WARNING'}, "Select a CV away from the curve ends")
            return {'CANCELLED'}
        return {'FINISHED'}


# --- Fit B-spline -----------------------------------------------------------------------------------------------

@undo_steps.no_redo_panel
class ALLSET_OT_curve_fit_bspline(bpy.types.Operator):
    """A cubic curve through the CVs of each selected linear curve (Maya Curves > Fit B-spline)"""
    bl_idname = "allset.curve_fit_bspline"
    bl_label = "Fit B-spline"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(o.type == 'CURVE' for o in context.selected_objects)

    def execute(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        made = []
        for ob in _curves_selected(context):
            curves = []
            for sp in ob.data.splines:
                c = read_spline(sp, ob.matrix_world)
                if c.degree == 1 and not c.periodic and len(c.cvs) >= 2:
                    cvs, knots, deg = cm.fit_bspline(c.cvs)
                    curves.append(MCurve(cvs, knots, deg))
            if curves:
                new = _new_curve_object(context, "fitBsplineCurve", curves, select=False)
                naming.apply_maya_name(new, "fitBsplineCurve")
                made.append(new)
        if not made:
            self.report({'WARNING'}, "Select linear (degree 1) curves")
            return {'CANCELLED'}
        _select(context, made)
        results.result(self, " ".join(o.name for o in made))
        return {'FINISHED'}


def _select(context, obs):
    for o in context.selected_objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    context.view_layer.objects.active = obs[-1]


# --- Align ------------------------------------------------------------------------------------------------------

@undo_steps.no_redo_panel
class ALLSET_OT_curve_align(bpy.types.Operator):
    """Move the first selected curve onto the nearest end of the second with matching tangent (Maya Curves > Align;
    default position + tangent)"""
    bl_idname = "allset.curve_align"
    bl_label = "Align Curves"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return sum(1 for o in context.selected_objects if o.type == 'CURVE') >= 2

    def execute(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        obs = [o for o in selection_order(context) if o.type == 'CURVE' and o.data.splines]
        if len(obs) < 2:
            self.report({'WARNING'}, "Select two curves")
            return {'CANCELLED'}
        a, b = obs[0], obs[1]
        ca = read_spline(a.data.splines[0], a.matrix_world)
        cb = read_spline(b.data.splines[0], b.matrix_world)
        if ca.periodic or cb.periodic or len(ca.cvs) < 2 or len(cb.cvs) < 2:
            self.report({'WARNING'}, "Align works on open curves")
            return {'CANCELLED'}
        new = cm.align_ends(ca.cvs, cb.cvs)
        inv = a.matrix_world.inverted()
        local = MCurve([tuple(inv @ Vector(p)) for p in new], ca.knots, ca.degree, ca.weights)
        rest = [read_spline(sp) for sp in a.data.splines[1:]]
        _replace_splines(a, [local] + rest)
        remember(a)
        return {'FINISHED'}


# --- Duplicate Surface Curves -----------------------------------------------------------------------------------

@undo_steps.no_redo_panel
class ALLSET_OT_duplicate_surface_curves(bpy.types.Operator):
    """Curves from the surface's isoparms: every visible isoparm of a selected surface, or the isoparms through the
    selected CV rows / columns in edit mode (Maya Curves > Duplicate Surface Curves)"""
    bl_idname = "allset.duplicate_surface_curves"
    bl_label = "Duplicate Surface Curves"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(o.type == 'SURFACE' for o in context.selected_objects) or context.mode == 'EDIT_SURFACE'

    def execute(self, context):
        from . import surfaces_maya, surfaces_math as sm
        jobs = []
        if context.mode == 'EDIT_SURFACE':
            got = surfaces_maya._picked_lines(context)
            if got is not None:
                ob, s, direction, ts = got[:4]
                jobs.append((s, [(direction, t) for t in ts]))
        else:
            for ob in [o for o in selection_order(context) if o.type == 'SURFACE' and o.data.splines]:
                s = surfaces_maya.read_surface(ob)
                jobs.append((s, sm.visible_isoparms(s)))
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        made = []
        for s, lines in jobs:
            for direction, t in lines:
                cr = sm.isoparm(s, direction, t)
                new = _new_curve_object(context, "duplicatedCurve", [MCurve(cr.cvs, cr.knots, cr.degree,
                                                                            periodic=cr.periodic)], select=False)
                naming.apply_maya_name(new, "duplicatedCurve")
                made.append(new)
        if not made:
            self.report({'WARNING'}, "Select a surface (or CVs of one of its rows / columns)")
            return {'CANCELLED'}
        _select(context, made)
        results.result(self, " ".join(o.name for o in made))
        return {'FINISHED'}


# --- Intersect --------------------------------------------------------------------------------------------------

def _locator(context, parent, point, scale):
    ob = bpy.data.objects.new("locator", None)
    ob.empty_display_type = 'PLAIN_AXES'
    ob.empty_display_size = scale
    (context.collection or context.scene.collection).objects.link(ob)
    naming.apply_maya_name(ob, "locator", rename_data=False)
    ob.parent = parent
    ob.matrix_world = Matrix.Translation(point)
    return ob


@undo_steps.no_redo_panel
class ALLSET_OT_curve_intersect(bpy.types.Operator):
    """Mark where the selected curves cross with a locator on each curve (Maya Curves > Intersect)"""
    bl_idname = "allset.curve_intersect"
    bl_label = "Intersect Curves"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return sum(1 for o in context.selected_objects if o.type == 'CURVE') >= 2

    def execute(self, context):
        from . import units
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        obs = [o for o in selection_order(context) if o.type == 'CURVE' and o.data.splines]
        cur = {o: read_spline(o.data.splines[0], o.matrix_world) for o in obs}
        hits = {o: [] for o in obs}
        for i, a in enumerate(obs):
            for b in obs[i + 1:]:
                for ua, ub in cm.intersections(cur[a].math(), cur[b].math(), tol=0.01 * units.maya_unit()):
                    hits[a].append(ua)
                    hits[b].append(ub)
        made = []
        size = 0.2 * units.maya_unit()
        for o in obs:
            for u in sorted(hits[o]):
                made.append(_locator(context, o, Vector(cm.evaluate(*cur[o].math()[:3], u, cur[o].weights)), size))
        if not made:
            self.report({'WARNING'}, "The selected curves don't intersect")
            return {'CANCELLED'}
        _select(context, made)
        results.result(self, " ".join(o.name for o in made))
        return {'FINISHED'}


classes = (ALLSET_OT_curve_modify, ALLSET_OT_curve_lock_length, ALLSET_OT_curve_cv_hardness,
           ALLSET_OT_curve_fit_bspline, ALLSET_OT_curve_align, ALLSET_OT_duplicate_surface_curves,
           ALLSET_OT_curve_intersect)


def register_handlers():
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)


def unregister_handlers():
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    _last.clear()
