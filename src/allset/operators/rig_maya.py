# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Skeleton / Skin / Deform commands with Maya's results.

Reroot, Preferred Angle, IK Spline Handle; Hammer, Add / Remove
Influence, Remove Unused Influences; Cluster, Soft Mod (Nonlinear lives in ``menu_items``). A Maya joint is a
bone head (or a chain end's tail), skin = Armature modifier + vertex groups
named after the joints.
"""

import math

import bmesh
import bpy
from bpy.props import BoolProperty, FloatProperty
from mathutils import Matrix, Vector

from .. import results
from . import naming, units
from .joints import _InEditMode

PREFERRED_PROP = "allset_preferred_angle"
PREFERRED_NOTE = ("Preferred angle stored: RP handles on 3+ bones start their solve from it like Maya; "
                  "2-bone chains bend from the rest pose (Blender's IK).")
SOFT_MOD_RADIUS = 5.0          # Maya softMod falloffRadius default (Maya units)
SPLINE_SAMPLES = 200           # polyline samples for the IK Spline curve fit


def _cb():
    from ..ui import channel_box
    return channel_box


def _selected_bones(arm):
    cb = _cb()
    return [pb for pb in arm.pose.bones if cb.bone_selected(pb)]


def _armature(context):
    ob = context.active_object
    return ob if ob is not None and ob.type == 'ARMATURE' else None


# --- Reroot Skeleton ---------------------------------------------------------------------------

def reroot(arm, name):
    """Make the joint at the head of bone ``name`` the root: the bones on the way to the old root are reversed and
    re-parented (joint positions unchanged, Maya ``reroot``). Bone names stay. Returns False if already a root."""
    with _InEditMode(arm) as ebs:
        b = ebs[name]
        path, p = [], b.parent
        while p is not None:
            path.append(p)
            p = p.parent
        if not path:
            return False
        on_path = {eb.name for eb in path} | {b.name}
        others = {eb.name: [c.name for c in eb.children if c.name not in on_path] for eb in path}
        old_tail = {eb.name: eb.tail.copy() for eb in path}
        b.use_connect = False
        b.parent = None
        for eb in path:
            eb.use_connect = False
            eb.parent = None
        for eb in path:
            head, tail = eb.head.copy(), eb.tail.copy()
            eb.head, eb.tail = tail, head
        for i, eb in enumerate(path):
            if i > 0:
                eb.parent = path[i - 1]
                eb.use_connect = True
        # the other children of a path bone hang at its old tail = the previous reversed bone's tail
        for i, eb in enumerate(path):
            for cname in others[eb.name]:
                c = ebs[cname]
                at_tail = (c.head - old_tail[eb.name]).length < 1e-5
                if at_tail:
                    c.use_connect = False
                    c.parent = path[i - 1] if i > 0 else None
    return True


class ALLSET_OT_reroot_skeleton(bpy.types.Operator):
    """Make the selected joint the root of its skeleton (Maya Skeleton > Reroot Skeleton)"""
    bl_idname = "allset.reroot_skeleton"
    bl_label = "Reroot Skeleton"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _armature(context) is not None

    def execute(self, context):
        arm = _armature(context)
        act = arm.data.bones.active
        if act is None:
            self.report({'WARNING'}, "Select a joint")
            return {'CANCELLED'}
        if not reroot(arm, act.name):
            results.result(self, f"{act.name} is already a root")
        return {'FINISHED'}


# --- Set / Assume Preferred Angle -----------------------------------------------------------------

def _euler(pb):
    if pb.rotation_mode == 'QUATERNION':
        return pb.rotation_quaternion.to_euler()
    if pb.rotation_mode == 'AXIS_ANGLE':
        w, x, y, z = pb.rotation_axis_angle
        return Matrix.Rotation(w, 3, Vector((x, y, z))).to_euler()
    return pb.rotation_euler.copy()


def _set_euler(pb, e):
    if pb.rotation_mode == 'QUATERNION':
        pb.rotation_quaternion = e.to_quaternion()
    elif pb.rotation_mode == 'AXIS_ANGLE':
        axis, angle = e.to_quaternion().to_axis_angle()
        pb.rotation_axis_angle = (angle, *axis)
    else:
        pb.rotation_euler = e


def _with_children(bones):
    out = []
    for pb in bones:
        for b in (pb, *pb.children_recursive):
            if b not in out:
                out.append(b)
    return out


def set_preferred(bones, hierarchy=True):
    """Maya ``cmds.joint(edit=True, setPreferredAngles=True, children=True)``: preferredAngle = the current rotation, on
    the joints and their children (option window Options: Selected joint = ``hierarchy`` False, no ``children``)."""
    for pb in (_with_children(bones) if hierarchy else bones):
        pb[PREFERRED_PROP] = [math.degrees(a) for a in _euler(pb)]


def assume_preferred(bones, hierarchy=True):
    """Maya ``cmds.joint(edit=True, assumePreferredAngles=True, children=True)``: rotation = preferredAngle (joints
    without one keep their rotation)."""
    from mathutils import Euler
    for pb in (_with_children(bones) if hierarchy else bones):
        if PREFERRED_PROP in pb:
            d = pb[PREFERRED_PROP]
            _set_euler(pb, Euler([math.radians(a) for a in d], _euler(pb).order))


class _PoseBones:
    @classmethod
    def poll(cls, context):
        return _cb().pose_armature(context) is not None

    def bones(self, context):
        arm = _cb().pose_armature(context)
        bones = _selected_bones(arm) if arm else []
        if not bones and arm is not None:
            bones = [pb for pb in arm.pose.bones if pb.parent is None]   # Maya: the skeleton when no joint picked
        return bones


class ALLSET_OT_set_preferred_angle(_PoseBones, bpy.types.Operator):
    """Remember the selected joints' current rotation as their preferred angle (Maya Skeleton > Set Preferred
    Angle)"""
    bl_idname = "allset.set_preferred_angle"
    bl_label = "Set Preferred Angle"
    bl_options = {'REGISTER', 'UNDO'}

    hierarchy: BoolProperty(name="Hierarchy", default=True, options={'SKIP_SAVE', 'HIDDEN'})    # default like Maya

    def execute(self, context):
        set_preferred(self.bones(context), self.hierarchy)
        results.result(self, PREFERRED_NOTE)
        return {'FINISHED'}


class ALLSET_OT_assume_preferred_angle(_PoseBones, bpy.types.Operator):
    """Turn the selected joints back to their preferred angle (Maya Skeleton > Assume Preferred Angle)"""
    bl_idname = "allset.assume_preferred_angle"
    bl_label = "Assume Preferred Angle"
    bl_options = {'REGISTER', 'UNDO'}

    hierarchy: BoolProperty(name="Hierarchy", default=True, options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        assume_preferred(self.bones(context), self.hierarchy)
        return {'FINISHED'}


# --- IK Spline Handle ----------------------------------------------------------------------------

def _resample(points, n):
    seg = [(points[i + 1] - points[i]).length for i in range(len(points) - 1)]
    total = sum(seg) or 1.0
    out, i, acc = [], 0, 0.0
    for k in range(n + 1):
        d = total * k / n
        while i < len(seg) - 1 and acc + seg[i] < d:
            acc += seg[i]
            i += 1
        t = 0.0 if seg[i] == 0 else min(1.0, (d - acc) / seg[i])
        out.append((points[i].lerp(points[i + 1], t), k / n))
    return out


def fit_cubic(points):
    """One-span cubic (4 control points) with its ends on the first / last point and the middle two a least-squares
    fit of the polyline (Maya's IK Spline curve: spans 1, degree 3)."""
    p0, p3 = points[0], points[-1]
    a11 = a12 = a22 = 0.0
    r1, r2 = Vector(), Vector()
    for p, t in _resample(points, SPLINE_SAMPLES):
        b0, b1, b2, b3 = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3
        rest = p - p0 * b0 - p3 * b3
        a11 += b1 * b1
        a12 += b1 * b2
        a22 += b2 * b2
        r1 += rest * b1
        r2 += rest * b2
    det = a11 * a22 - a12 * a12
    if abs(det) < 1e-12:
        return [p0, p0.lerp(p3, 1 / 3), p0.lerp(p3, 2 / 3), p3]
    return [p0, (r1 * a22 - r2 * a12) / det, (r2 * a11 - r1 * a12) / det, p3]


def fit_spans(points, spans=1):
    """Clamped uniform cubic with ``spans`` spans (spans + 3 CVs), ends on the first / last point, inner CVs a
    least-squares fit of the polyline (Maya IK Spline Handle Tool "Number of spans", factory 1; 1 = ``fit_cubic``)."""
    if spans <= 1:
        return fit_cubic(points)
    from . import curves_math as cm
    n = spans + 3
    U = cm.full(cm.clamped_uniform(n, 3))
    p0, pn = points[0], points[-1]
    m = n - 2
    A = [[0.0] * m for _ in range(m)]
    B = [Vector() for _ in range(m)]
    for p, t in _resample(points, SPLINE_SAMPLES):
        row = cm._row(U, 3, n, t * spans, 0)
        rest = p - p0 * row[0] - pn * row[-1]
        for a in range(m):
            if row[a + 1]:
                B[a] += rest * row[a + 1]
                for b in range(m):
                    A[a][b] += row[a + 1] * row[b + 1]
    try:
        inner = [Vector(c) for c in cm.solve(A, [tuple(b) for b in B])]
    except ValueError:
        inner = [p0.lerp(pn, k / (n - 1)) for k in range(1, n - 1)]
    return [p0, *inner, pn]


# Blender's Spline IK walks the curve's evaluated polyline (resolution_u segments per span): at 128 the joints land
# where tests/test_step218_curve_rig.py expects them (64 is a little off), so kit Spline IK curves get
# at least this.
SPLINE_RESOLUTION = 128


def _first_cv_world(curve):
    sp = curve.data.splines[0]
    co = sp.bezier_points[0].co if sp.type == 'BEZIER' else Vector(sp.points[0].co[:3])
    return curve.matrix_world @ co


def _parent_curve(curve, arm, first):
    """Maya Auto parent curve: the curve goes under the start joint's parent (a bone of the skeleton, else the
    skeleton's parent object); a root without parent leaves it in the world."""
    world = curve.matrix_world.copy()
    if first.parent is not None:
        pb = first.parent
        # Blender's bone parent space = the bone's pose matrix moved to its tail
        parent = arm.matrix_world @ pb.matrix @ Matrix.Translation((0.0, pb.bone.length, 0.0))
        curve.parent = arm
        curve.parent_type = 'BONE'
        curve.parent_bone = pb.name
    elif arm.parent is not None:
        parent = arm.parent.matrix_world
        curve.parent = arm.parent
    else:
        return
    curve.matrix_parent_inverse = Matrix.Identity(4)
    curve.matrix_basis = parent.inverted_safe() @ world


def _new_spline_curve(context, cvs):
    data = bpy.data.curves.new("curveShape", 'CURVE')
    data.dimensions = '3D'
    sp = data.splines.new('NURBS')
    sp.points.add(len(cvs) - 1)
    for p, c in zip(sp.points, cvs):
        p.co = (c.x, c.y, c.z, 1.0)
    sp.order_u = 4
    sp.use_endpoint_u = True
    curve = bpy.data.objects.new("curve", data)
    context.view_layer.active_layer_collection.collection.objects.link(curve)
    naming.apply_maya_name(curve, "curve")
    return curve


def create_spline_ik(context, arm, start, end, curve=None, root_on_curve=True, snap_curve=False,
                     parent_curve=True, spans=1):
    """Spline IK constraint ``ikHandleN`` on the bone ending at the end joint (Maya ikSplineSolver).

    ``curve`` None = Auto create curve: ``curveN`` fitted through the chain (degree 3, ``spans`` spans).
    An existing curve: Root on curve moves the root onto
    the curve start and the joints keep their lengths along the curve (Blender Spline IK, Y scale None, no chain
    offset); off keeps the root where it is and the chain takes the curve's shape from there (Chain Offset; Maya
    instead puts the joints after the root on the curve itself, roc0_snc0: up to 1.35
    units apart, Blender's Spline IK has no start point on the curve); Snap curve to root moves the curve so its
    first CV is on the root joint. Returns (constraint, curve) or None."""
    from .skin import ik_chain
    chain = ik_chain(arm, start, end)
    if chain is None:
        return None
    ik_bone, count = chain
    bones, b = [], ik_bone
    for _ in range(count):
        bones.append(b)
        b = b.parent
    bones.reverse()
    mw = arm.matrix_world
    root = mw @ bones[0].head
    if curve is None:
        pts = [mw @ pb.head for pb in bones] + [mw @ ik_bone.tail]
        curve = _new_spline_curve(context, fit_spans(pts, spans))
    elif snap_curve:
        curve.matrix_world = Matrix.Translation(root - _first_cv_world(curve)) @ curve.matrix_world
    if curve.data.resolution_u < SPLINE_RESOLUTION:
        curve.data.resolution_u = SPLINE_RESOLUTION
    if parent_curve:
        context.view_layer.update()
        _parent_curve(curve, arm, bones[0])
    taken = {c.name for o in bpy.data.objects if o.pose for p in o.pose.bones for c in p.constraints}
    taken |= {o.name for o in bpy.data.objects}
    con = ik_bone.constraints.new('SPLINE_IK')
    con.name = f"ikHandle{naming.next_number('ikHandle', taken)}"
    con.target = curve
    con.chain_count = count
    con.y_scale_mode = 'NONE'           # Maya: bone lengths kept (no stretch by default)
    con.xz_scale_mode = 'NONE'
    con.use_curve_radius = False
    con.use_chain_offset = not root_on_curve
    # #166: Maya's handle with Twist / Roll / Twist Type (drivers on the chain's roll)
    from . import spline_twist
    spline_twist.setup(context, arm, ik_bone, con, mw @ ik_bone.tail)
    return con, curve


SPLINE_STATUS = "IK Spline Handle Tool: click the start joint, then the end joint{} (Esc: cancel)"


class ALLSET_OT_ik_spline_handle(bpy.types.Operator):
    """Create a spline IK from the start joint to the end joint: a new curve through the chain, or (Auto create
    curve off) the selected / clicked curve (Maya Skeleton > Create IK Spline Handle)"""
    bl_idname = "allset.ik_spline_handle"
    bl_label = "Create IK Spline Handle"
    bl_options = {'UNDO'}       # a click tool: Maya has no redo panel

    # Maya 2026 IK Spline Handle Tool factory settings (ikSplineHandleCtx)
    root_on_curve: BoolProperty(name="Root on curve", default=True, options={'SKIP_SAVE'})
    parent_curve: BoolProperty(name="Auto parent curve", default=True, options={'SKIP_SAVE'})
    snap_curve: BoolProperty(name="Snap curve to root", default=False, options={'SKIP_SAVE'})
    create_curve: BoolProperty(name="Auto create curve", default=True, options={'SKIP_SAVE'})
    spans: bpy.props.IntProperty(name="Number of spans", default=1, min=1, max=4, options={'SKIP_SAVE'})
    # Maya Twist type of the tool (factory Linear) = the new handle's Twist Type
    twist_type: bpy.props.IntProperty(name="Twist type", default=0, min=0, max=3, options={'SKIP_SAVE'})
    curve: bpy.props.StringProperty(name="Curve", default="", options={'SKIP_SAVE', 'HIDDEN'},
                                    description="Existing curve object (Auto create curve off); empty = the "
                                                "selected curve")

    def _existing_curve(self, context):
        if self.curve:
            ob = bpy.data.objects.get(self.curve)
            return ob if ob is not None and ob.type == 'CURVE' else None
        return next((o for o in context.selected_objects if o.type == 'CURVE'), None)

    def execute(self, context):
        from .skin import selected_pair
        pair = selected_pair(context)
        if pair is None:
            self.report({'WARNING'}, "Select the start joint, then the end joint (pose mode)")
            return {'CANCELLED'}
        return self._make(context, *pair, self._existing_curve(context))

    def _make(self, context, arm, start, end, curve):
        if not self.create_curve and curve is None:
            self.report({'WARNING'}, "Auto create curve is off: select or click a curve")
            return {'CANCELLED'}
        res = create_spline_ik(context, arm, start, end, None if self.create_curve else curve,
                               root_on_curve=self.root_on_curve, snap_curve=self.snap_curve,
                               parent_curve=self.parent_curve, spans=self.spans)
        if res is None:
            self.report({'WARNING'}, "The end joint must be below the start joint in the same skeleton")
            return {'CANCELLED'}
        con, curve = res
        handle = bpy.data.objects.get(con.name)
        if handle is not None and self.twist_type:
            handle["twistType"] = int(self.twist_type)
            handle.update_tag()
        # Maya selects the new ikHandle: the kit handle is the
        # constraint, so its bone becomes the only selected joint
        cb = _cb()
        owner = next(pb for pb in arm.pose.bones if pb.constraints.get(con.name) == con)
        for pb in arm.pose.bones:
            cb.set_bone_selected(pb, pb == owner)
        arm.data.bones.active = owner.bone
        results.result(self, f"Created {con.name} with {curve.name} (Spline IK constraint; Blender has no "
                              "effector node)")
        return {'FINISHED'}

    # --- click tool: start joint, end joint, then (Auto create curve off) the curve ------------------------

    def invoke(self, context, event):
        from .skin import selected_pair
        pair = selected_pair(context)
        curve = self._existing_curve(context)
        if context.window is None or (pair is not None and (self.create_curve or curve is not None)):
            return self.execute(context)
        self._picks = [] if pair is None else list(pair)
        self._swallow = False
        context.workspace.status_text_set(SPLINE_STATUS.format("" if self.create_curve else ", then the curve"))
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _pick_curve(self, context, event):
        from . import select_priority
        from .joints import view_under
        hit = view_under(context.window, event.mouse_x, event.mouse_y)
        if hit is None:
            return None
        area, region = hit
        mouse = (event.mouse_x - region.x, event.mouse_y - region.y)
        with context.temp_override(window=context.window, area=area, region=region):
            found = select_priority.hits(bpy.context, region, region.data, mouse)
        radius = 25 * context.preferences.system.ui_scale
        best = min((h for h in found if h[2] <= radius and bpy.data.objects[h[0]].type == 'CURVE'),
                   key=lambda h: h[2], default=None)
        return bpy.data.objects[best[0]] if best else None

    def modal(self, context, event):
        from .skin import ALLSET_OT_ik_handle
        if event.type == 'ESC' and event.value == 'PRESS':
            context.workspace.status_text_set(None)
            return {'CANCELLED'}
        if event.type != 'LEFTMOUSE':
            return {'PASS_THROUGH'}
        if event.value == 'RELEASE' and self._swallow:
            self._swallow = False
            return {'RUNNING_MODAL'}
        if event.value != 'PRESS' or event.alt or event.ctrl or event.shift:
            return {'PASS_THROUGH'}
        curve = None
        if len(self._picks) < 3:
            hit = ALLSET_OT_ik_handle._pick(self, context, event)
            if hit is None:
                return {'RUNNING_MODAL'} if self._swallow else {'PASS_THROUGH'}
            arm, joint = hit
            if not self._picks or self._picks[0] != arm:
                self._picks = [arm, joint]
            else:
                self._picks.append(joint)
            self._swallow = True
            if len(self._picks) < 3 or not self.create_curve:
                return {'RUNNING_MODAL'}
        else:
            curve = self._pick_curve(context, event)
            if curve is None:
                return {'RUNNING_MODAL'} if self._swallow else {'PASS_THROUGH'}
            self._swallow = True
        context.workspace.status_text_set(None)
        with context.temp_override(window=context.window):
            return self._make(context, *self._picks, curve)


# --- Skin: influences, Hammer ----------------------------------------------------------------------

def _skin_armature(mesh):
    md = next((m for m in mesh.modifiers if m.type == 'ARMATURE' and m.object is not None), None)
    return md.object if md else None


def _skinned(context):
    return [o for o in context.selected_objects if o.type == 'MESH' and _skin_armature(o) is not None]


def _influence_groups(mesh):
    arm = _skin_armature(mesh)
    bones = set(arm.data.bones.keys()) if arm else set()
    return [g for g in mesh.vertex_groups if g.name in bones]


def normalize(mesh, groups=None):
    """Weights of each vertex over the influence groups sum to 1 (Maya normalizeWeights Interactive)."""
    idx = {g.index for g in (groups if groups is not None else _influence_groups(mesh))}
    for v in mesh.data.vertices:
        ws = [g for g in v.groups if g.group in idx]
        total = sum(g.weight for g in ws)
        if total > 1e-12:
            for g in ws:
                g.weight /= total


# Maya Add Influence without Lock weights: the skin's
# weights are recomputed by the closest-distance rule of Bind Skin (skin.closest_distance_weights) over the old and
# the new influences, each with its own dropoff (old = the bind's, new = the option's Dropoff, factory 4).
MAX_INFLUENCES_PROP = "allset_max_influences"   # Maya skinCluster maxInfluences (Bind Skin factory 5)
DROPOFF_PROP = "allset_dropoff"                 # {influence: dropoff} of influences added with another dropoff
MAX_INFLUENCES = 5


def _joint_segments(arm, names):
    """{name: [(a, b) world segment]}: a joint's segments run to each child joint, an end joint is a point (the Bind
    Skin rule, skin.joint_segments, without its deform filter: a joint added as influence counts whatever its flag)."""
    mw = arm.matrix_world
    out = {}
    for name in names:
        bone = arm.data.bones.get(name)
        if bone is not None:
            a = mw @ bone.head_local
            out[name] = [(a, mw @ c.head_local) for c in bone.children] or [(a, a)]
    return out


def maya_add_weights(points, before, segments, is_new, locked, dropoffs, max_influences):
    """Weights (V, K) after Maya's Add Influence for world ``points`` (V, 3); columns = influences in skinCluster order
    (old ones, then the new ones), ``before`` (V, K) = current weights (0 for new), ``segments`` a list of K segment
    lists, ``is_new`` / ``locked`` (K,) bools, ``dropoffs`` (K,). Per vertex, w_i = distance(vertex, influence i) **
    -dropoff_i (a vertex on influences = those share equally), and:
    - no locked influence, K <= max influences: every influence gets w_i / sum w (painted weights are discarded);
    - no locked influence, K > max influences: the max influences largest w (ties: skinCluster order) are kept, but
      only new influences and those with weight > 0 before receive weight;
    - locked influences keep their weights; the rest (1 - locked sum) goes to the n largest w of the unlocked ones,
      n = min(unlocked old influences with weight > 0, max influences - locked influences with weight > 0)."""
    import numpy as np
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    before = np.asarray(before, dtype=np.float64).reshape(len(pts), -1)
    is_new, locked = np.asarray(is_new, dtype=bool), np.asarray(locked, dtype=bool)
    k = len(segments)
    dist = np.full((len(pts), k), np.inf)
    for j, segs in enumerate(segments):
        for a, b in segs:
            a = np.asarray(a, dtype=np.float64)
            ab = np.asarray(b, dtype=np.float64) - a
            ll = float(ab @ ab)
            t = np.clip((pts - a) @ ab / ll, 0.0, 1.0)[:, None] if ll > 0.0 else 0.0
            dist[:, j] = np.minimum(dist[:, j], np.linalg.norm(pts - (a + t * ab), axis=1))
    on = dist <= 1e-4                     # Maya's on-joint distance
    with np.errstate(divide='ignore'):
        w = np.where(on.any(axis=1)[:, None], on.astype(np.float64), dist ** -np.asarray(dropoffs, dtype=np.float64))
    w = np.where(np.isfinite(w), w, 0.0)
    had = before > 0.0
    if locked.any():
        ranked = np.where(locked[None, :], -1.0, w)
        order = np.argsort(-ranked, axis=1, kind='stable')
        rank = np.empty_like(order)
        np.put_along_axis(rank, order, np.arange(k)[None, :].repeat(len(pts), axis=0), axis=1)
        slots = np.minimum((had & ~locked & ~is_new).sum(axis=1),
                           max_influences - (had & locked).sum(axis=1))
        rec = ~locked[None, :] & (rank < slots[:, None])
    elif k <= max_influences:
        rec = np.ones_like(had)
    else:
        order = np.argsort(-w, axis=1, kind='stable')
        rank = np.empty_like(order)
        np.put_along_axis(rank, order, np.arange(k)[None, :].repeat(len(pts), axis=0), axis=1)
        rec = (rank < max_influences) & (had | is_new[None, :])
    rest = 1.0 - (before * locked[None, :]).sum(axis=1)
    total = (w * rec).sum(axis=1)
    ok = total > 0.0
    out = np.where(rec, w * (rest / np.where(ok, total, 1.0))[:, None], 0.0)
    out = np.where(locked[None, :], before, out)
    return np.where(ok[:, None], out, before)


def _add_by_distance(mesh, names, dropoff):
    import numpy as np
    from .skin import DROPOFF
    arm = _skin_armature(mesh)
    old = _influence_groups(mesh)
    new_names = [n for n in names if arm is not None and n in arm.data.bones]
    columns = [g.name for g in old] + new_names
    segs = _joint_segments(arm, columns) if arm is not None else {}
    if any(n not in segs for n in columns) or not new_names:
        return False
    me = mesh.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    mw = np.array(mesh.matrix_world)
    pts = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
    col = {g.index: j for j, g in enumerate(old)}
    before = np.zeros((len(me.vertices), len(columns)))
    for v in me.vertices:
        for g in v.groups:
            j = col.get(g.group)
            if j is not None:
                before[v.index, j] = g.weight
    stored = mesh.get(DROPOFF_PROP) or {}
    dropoffs = [float(stored.get(g.name, DROPOFF)) for g in old] + [float(dropoff)] * len(new_names)
    out = maya_add_weights(pts, before, [segs[n] for n in columns], [False] * len(old) + [True] * len(new_names),
                           [g.lock_weight for g in old] + [False] * len(new_names), dropoffs,
                           int(mesh.get(MAX_INFLUENCES_PROP, MAX_INFLUENCES)))
    groups = list(old) + [mesh.vertex_groups.new(name=n) for n in new_names]
    every = list(range(len(me.vertices)))
    for j, vg in enumerate(groups):
        if vg.lock_weight:
            continue
        vg.remove(every)
        for value in np.unique(out[:, j]):
            if value > 0.0:
                vg.add(np.flatnonzero(out[:, j] == value).tolist(), float(value), 'REPLACE')
    if float(dropoff) != DROPOFF:
        stored = dict(stored.items())
        stored.update({n: float(dropoff) for n in new_names})
        mesh[DROPOFF_PROP] = stored
    return True


def add_influence(mesh, bone_names, lock=False, weight=0.0, dropoff=4.0):
    """Maya Add Influence. Factory (Lock weights off): the skin weights are recomputed by distance with the new
    joints (``maya_add_weights``). Option window Lock weights:
    the new influence weighs ``weight`` on every vertex, the other influences are scaled
    by 1 - weight, and it is locked (Blender's vertex group lock)."""
    names = [n for n in dict.fromkeys(bone_names) if n not in mesh.vertex_groups]
    if not names:
        return []
    if not lock and _add_by_distance(mesh, names, dropoff):
        return names
    added = []
    all_verts = [v.index for v in mesh.data.vertices]
    w = min(max(weight, 0.0), 1.0) if lock else 0.0
    for name in names:
        if w > 0.0:
            idx = {g.index for g in _influence_groups(mesh)}
            for v in mesh.data.vertices:
                for g in v.groups:
                    if g.group in idx:
                        g.weight *= 1.0 - w
        g = mesh.vertex_groups.new(name=name)
        g.add(all_verts, w, 'REPLACE')
        g.lock_weight = lock
        added.append(name)
    return added


def remove_influence(mesh, bone_names):
    removed = []
    for name in bone_names:
        g = mesh.vertex_groups.get(name)
        if g is not None:
            mesh.vertex_groups.remove(g)
            removed.append(name)
    if removed:
        normalize(mesh)
    return removed


def unused_influences(mesh):
    groups = _influence_groups(mesh)
    used = {g.index: False for g in groups}
    for v in mesh.data.vertices:
        for g in v.groups:
            if g.group in used and g.weight > 1e-9:
                used[g.group] = True
    return [g.name for g in groups if not used[g.index]]


def _selected_bone_names(context):
    arm = None
    for o in context.selected_objects:
        if o.type == 'ARMATURE':
            arm = o
    if context.active_object is not None and context.active_object.type == 'ARMATURE':
        arm = context.active_object
    if arm is None:
        return []
    from ..ui import channel_box      # Bone.select is gone in 5.x: the shim
    return [pb.name for pb in arm.pose.bones if channel_box.bone_selected(pb)]


class ALLSET_OT_add_influence(bpy.types.Operator):
    """Add the selected joints to the selected skinned mesh; the weights are recomputed by distance (Maya Skin >
    Edit Influences > Add Influence)"""
    bl_idname = "allset.add_influence"
    bl_label = "Add Influence"
    bl_options = {'REGISTER', 'UNDO'}

    lock_weights: BoolProperty(name="Lock weights", default=False, options={'SKIP_SAVE', 'HIDDEN'})
    default_weight: FloatProperty(name="Default weight", default=0.0, min=0.0, max=1.0,
                                  options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        meshes, names = _skinned(context), _selected_bone_names(context)
        if not meshes or not names:
            self.report({'WARNING'}, "Select the skinned mesh and the joints to add")
            return {'CANCELLED'}
        added = [n for m in meshes for n in add_influence(m, names, self.lock_weights, self.default_weight)]
        results.result(self, f"Added {', '.join(added) or 'nothing (already influences)'}")
        return {'FINISHED'}


class ALLSET_OT_remove_influence(bpy.types.Operator):
    """Remove the selected joints from the selected skinned mesh; the weights are renormalised (Maya Skin > Edit
    Influences > Remove Influence)"""
    bl_idname = "allset.remove_influence"
    bl_label = "Remove Influence"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        meshes, names = _skinned(context), _selected_bone_names(context)
        if not meshes or not names:
            self.report({'WARNING'}, "Select the skinned mesh and the joints to remove")
            return {'CANCELLED'}
        for m in meshes:
            remove_influence(m, names)
        return {'FINISHED'}


class ALLSET_OT_remove_unused_influences(bpy.types.Operator):
    """Remove influences that weigh nothing on any vertex (Maya Skin > Edit Influences > Remove Unused
    Influences)"""
    bl_idname = "allset.remove_unused_influences"
    bl_label = "Remove Unused Influences"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        meshes = _skinned(context) or [o for o in context.selected_objects if o.type == 'MESH']
        n = 0
        for m in meshes:
            names = unused_influences(m)
            for name in names:
                m.vertex_groups.remove(m.vertex_groups[name])
            n += len(names)
        results.result(self, f"Removed {n} unused influence(s)")
        return {'FINISHED'}


def hammer(bm, deform, groups):
    """Selected vertices take the plain average of their edge neighbours' weights over ``groups`` (Maya Hammer Skin
    Weights). Returns the number of changed vertices."""
    new = {}
    for v in (v for v in bm.verts if v.select):
        nbrs = [e.other_vert(v) for e in v.link_edges]
        if not nbrs:
            continue
        avg = {g: sum(n[deform].get(g, 0.0) for n in nbrs) / len(nbrs) for g in groups}
        total = sum(avg.values())
        if total > 1e-12:
            avg = {g: w / total for g, w in avg.items()}
        new[v] = avg
    for v, avg in new.items():
        dv = v[deform]
        for g, w in avg.items():
            if w > 0.0 or g in dv:
                dv[g] = w
    return len(new)


class ALLSET_OT_hammer_weights(bpy.types.Operator):
    """Give the selected vertices the average skin weights of their neighbours (Maya Skin > Hammer Skin Weights)"""
    bl_idname = "allset.hammer_weights"
    bl_label = "Hammer Skin Weights"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ob = context.edit_object
        return ob is not None and ob.type == 'MESH'

    def execute(self, context):
        ob = context.edit_object
        groups = [g.index for g in (_influence_groups(ob) or ob.vertex_groups)]
        bm = bmesh.from_edit_mesh(ob.data)
        deform = bm.verts.layers.deform.verify()
        n = hammer(bm, deform, groups)
        bmesh.update_edit_mesh(ob.data)
        if not n:
            self.report({'WARNING'}, "Select vertices to hammer")
            return {'CANCELLED'}
        return {'FINISHED'}


# --- Cluster / Soft Mod (Hook modifiers + handle empties) ------------------------------------------

def _hook(context, ob, base, centre_world, vertex_indices=None):
    """Hook modifier ``<base>N`` driven by the empty ``<base>NHandle`` at ``centre_world`` (rest = no change).

    #34: a mesh's points are the vertex group ``<base>N`` (weight 1, the default deformer weight),
    which Deform > Paint Weights paints; ``vertex_indices`` None = every point (a Hook with neither a group nor
    indices moves nothing)."""
    from . import deformers
    name = deformers.new_name(base)
    handle = bpy.data.objects.new(f"{name}Handle", None)
    context.view_layer.active_layer_collection.collection.objects.link(handle)
    handle.empty_display_type = 'PLAIN_AXES'
    handle.empty_display_size = 0.5 * units.maya_unit(context.scene)
    handle.location = centre_world
    context.view_layer.update()
    md = ob.modifiers.new(name, 'HOOK')
    md.object = handle
    # inverted_safe: an object scaled to 0 on an axis still gets its cluster1 in Maya
    md.center = ob.matrix_world.inverted_safe() @ centre_world
    md.matrix_inverse = handle.matrix_world.inverted() @ ob.matrix_world
    if ob.type == 'MESH':
        vg = ob.vertex_groups.new(name=name)
        vg.add(list(vertex_indices) if vertex_indices is not None else list(range(len(ob.data.vertices))), 1.0,
               'REPLACE')
        md.vertex_group = vg.name
    elif vertex_indices is not None:
        md.vertex_indices_set(vertex_indices)
    return md, handle


def _selection(ob):
    """World centroid of the selected vertices and their indices (object mode: all vertices, the object's centre)."""
    if ob.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(ob.data)
        idx = [v.index for v in bm.verts if v.select]
        cos = [v.co for v in bm.verts if v.select]
    else:
        idx = None
        vs = [v.co for v in ob.data.vertices]          # undeformed points (bound_box follows the modifiers)
        cos = []
        if vs:   # the bounding-box corners: their mean is the box centre
            cos = [Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs))),
                   Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))]
    if not cos:
        return None, None
    c = sum(cos, Vector()) / len(cos)
    return ob.matrix_world @ c, idx


def control_points(ob):
    """``(hook index, local co, selected)`` of a curve / surface / lattice in the Hook modifier's point order: NURBS
    and poly points one each, a Bezier point three (left handle, point, right handle; the point carries the
    selection and the position)."""
    out = []
    if ob.type == 'LATTICE':
        for i, p in enumerate(ob.data.points):
            out.append((i, Vector(p.co_deform), p.select))
        return out
    i = 0
    for sp in ob.data.splines:
        if sp.type == 'BEZIER':
            for bp in sp.bezier_points:
                out.append(((i, i + 1, i + 2), bp.co.copy(), bp.select_control_point))
                i += 3
        else:
            for p in sp.points:
                out.append((i, Vector(p.co[:3]), p.select))
                i += 1
    return out


def _point_selection(ob, selected_only):
    """Maya cluster on CVs: the handle pivot is the centre
    of the selected CVs, the Hook acts on exactly those indices; object mode = every CV (pivot = their box centre,
    like a mesh). Returns (world centre, indices) or (None, None)."""
    pts = [p for p in control_points(ob) if p[2] or not selected_only]
    if not pts:
        return None, None
    idx = []
    for k, _co, _sel in pts:
        idx.extend(k if isinstance(k, tuple) else (k,))
    cos = [co for _k, co, _sel in pts]
    if selected_only:
        c = sum(cos, Vector()) / len(cos)
    else:
        lo = Vector([min(v[a] for v in cos) for a in range(3)])
        hi = Vector([max(v[a] for v in cos) for a in range(3)])
        c = (lo + hi) / 2
    return ob.matrix_world @ c, idx


def _select_handle(context, handle):
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in context.selected_objects:
        o.select_set(False)
    handle.select_set(True)
    context.view_layer.objects.active = handle


class ALLSET_OT_cluster(bpy.types.Operator):
    """Make a cluster of the selected components (or the whole object): a Hook modifier ``clusterN`` driven by the
    handle ``clusterNHandle`` at their centre (Maya Deform > Cluster)"""
    bl_idname = "allset.cluster"
    bl_label = "Cluster"
    bl_options = {'REGISTER', 'UNDO'}

    envelope: bpy.props.FloatProperty(name="Envelope", default=1.0, min=0.0, max=1.0,
                                      description="Maya cluster envelope = the Hook's strength")

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type in {'MESH', 'LATTICE', 'CURVE', 'SURFACE'}

    def execute(self, context):
        ob = context.active_object
        if ob.type == 'MESH':
            centre, idx = _selection(ob)
            if ob.mode == 'EDIT':
                bpy.ops.object.mode_set(mode='OBJECT')
        else:
            if ob.mode == 'EDIT':     # leaving edit mode writes the CV selection back to the data
                bpy.ops.object.mode_set(mode='OBJECT')
                centre, idx = _point_selection(ob, True)
            else:
                centre, idx = _point_selection(ob, False)
        if centre is None:
            self.report({'WARNING'}, "Select components or an object")
            return {'CANCELLED'}
        md, handle = _hook(context, ob, "cluster", centre, idx)
        md.strength = self.envelope
        handle.empty_display_type = 'SPHERE'
        _select_handle(context, handle)       # Maya: the new handle is selected
        return {'FINISHED'}


def cosine_falloff(curve_mapping, steps=10):
    """Hook falloff curve = Maya softMod's smooth curve: weight = (1 + cos(pi d / r)) / 2, input x = 1 - d / r."""
    curve = curve_mapping.curves[0]
    while len(curve.points) > 2:
        curve.points.remove(curve.points[1])
    curve.points[0].location = (0.0, 0.0)
    curve.points[-1].location = (1.0, 1.0)
    for k in range(1, steps):
        x = k / steps
        curve.points.new(x, (1 - math.cos(math.pi * x)) / 2)
    curve_mapping.update()


class ALLSET_OT_soft_mod(bpy.types.Operator):
    """Soft modification at the selection: a Hook modifier ``softModN`` on the whole mesh with Maya's falloff
    (radius 5, smooth) driven by ``softModNHandle`` (Maya Deform > Soft Modification)"""
    bl_idname = "allset.soft_mod"
    bl_label = "Soft Modification"
    bl_options = {'REGISTER', 'UNDO'}

    radius: bpy.props.FloatProperty(name="Falloff Radius", default=SOFT_MOD_RADIUS, min=0.0,
                                    description="Maya units (softMod falloffRadius)")

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'MESH'

    def execute(self, context):
        ob = context.active_object
        if ob.mode == 'EDIT':
            centre, _idx = _selection(ob)
            bpy.ops.object.mode_set(mode='OBJECT')
        else:
            centre = ob.matrix_world.translation.copy()
        if centre is None:
            self.report({'WARNING'}, "Select components or an object")
            return {'CANCELLED'}
        # a Hook with neither a vertex group nor indices moves nothing: every vertex, weighted by falloff
        md, handle = _hook(context, ob, "softMod", centre, None)
        md.falloff_type = 'CURVE'
        md.falloff_radius = self.radius * units.maya_unit(context.scene)
        cosine_falloff(md.falloff_curve)
        handle.empty_display_type = 'CUBE'
        _select_handle(context, handle)
        return {'FINISHED'}


classes = (ALLSET_OT_reroot_skeleton, ALLSET_OT_set_preferred_angle, ALLSET_OT_assume_preferred_angle,
           ALLSET_OT_ik_spline_handle, ALLSET_OT_add_influence, ALLSET_OT_remove_influence,
           ALLSET_OT_remove_unused_influences, ALLSET_OT_hammer_weights, ALLSET_OT_cluster, ALLSET_OT_soft_mod)
