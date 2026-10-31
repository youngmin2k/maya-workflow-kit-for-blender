# SPDX-License-Identifier: GPL-3.0-or-later
"""Constrain > Normal / Tangent / Remove Target / Set Rest Position / Modify Constrained Axis.

- Normal / Tangent (Maya Normal / Tangent Constraint Options, default: weight 1, aim (1, 0, 0),
  up (0, 1, 0), world up type Vector (0, 1, 0)): Maya only turns the object — its aim vector = the target's normal at
  the closest surface point (MFnMesh.getClosestPointAndNormal) / the curve's tangent at the closest curve point, its up
  vector towards the world up. No Blender constraint computes Maya's normal: Blender's Shrinkwrap uses Blender's
  corner-angle normals on Blender's triangulation, Maya interpolates face-vertex normals weighted by corner angle x
  face area (mesh vertexNormalMethod "Angle and Area Weighted") on its own triangulation (a quad is split along the
  shorter diagonal only when d02^2 < 0.999 d13^2, else 1-3). So the kit setup is: a Track To on
  the object (Maya's aim / up, rig_tools.aim) towards a hidden helper empty that a depsgraph / frame handler keeps at
  P + L * direction  (P = the object's world position, direction computed the Maya way in double precision:
  ``SurfaceData.normal`` / ``CurveData.tangent``).
- Remove Target: targets selected, the constrained object last; the constraints of the
  checked types whose target is selected go. When the last target of a type goes Maya deletes the constraint node and
  the channels keep the constrained value (Maya) — the kit bakes the visual value into the object's own channels.
- Set Rest Position: Maya stores the current constrained channels as the constraint's
  rest values, used when every target weight is 0. In Blender a constraint at influence 0 shows the object's own
  channels, so the rest position is the own channels: the kit writes the current constrained values into them.
- Modify Constrained Axis (default X / Y / Z on, Maintain offset off): which axes the point
  / orient / scale / parent constraints drive (Blender use_x / use_y / use_z, Child Of use_location_* / use_rotation_*;
  the axes are the Channel Box's). A newly skipped channel keeps its last constrained value (Maya); Maintain offset
  = Blender's constraint offsets set so nothing moves now.
"""

import math

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty
from mathutils import Matrix, Vector

from .. import results
from . import rig_tools

KIND = "allset_aim_kind"             # helper empty: "normal" | "tangent"
OWNER = "allset_aim_owner"           # helper empty: the constrained object
SURFACE = "allset_aim_surface"       # helper empty: the Maya target (mesh / curve)
LABEL = {"normal": "Normal Constraint", "tangent": "Tangent Constraint"}
MAYA_NODE = {"normal": "normalConstraint", "tangent": "tangentConstraint"}
QUAD_SPLIT = 0.999                   # Maya splits a quad 0-2 only when d02^2 < 0.999 d13^2

# Maya's own messages
MSG_REMOVE_SELECT = "You must select one or more target(s) followed by the constrained object."
MSG_REMOVE_CONSTRAINED = "A constrained object must be the last object selected."
MSG_REST = "A constrained object must be selected."
MSG_AXES_SELECT = "You must select the constrained object."
MSG_AXES_NONE = "No axes were selected."
MSG_AXES_INVALID = "An aim-, orient-, parent-, point-, or scale-constrained object must be the last object selected."
SURFACE_HINT = "Select the target surface(s), then the object to constrain last"
CURVE_HINT = "Select the target curve(s), then the object to constrain last"


# --- small vector maths (double precision) ------------------------------------------------------------

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def closest_on_triangle(p, a, b, c):
    """(closest point, barycentric (wa, wb, wc)) of p on triangle abc (Ericson, Real-Time Collision Detection 5.1.5)."""
    ab, ac, ap = _sub(b, a), _sub(c, a), _sub(p, a)
    d1, d2 = _dot(ab, ap), _dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return (1.0, 0.0, 0.0)
    bp = _sub(p, b)
    d3, d4 = _dot(ab, bp), _dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return (0.0, 1.0, 0.0)
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3)
        return (1 - v, v, 0.0)
    cp = _sub(p, c)
    d5, d6 = _dot(ab, cp), _dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return (0.0, 0.0, 1.0)
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6)
        return (1 - w, 0.0, w)
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return (0.0, 1 - w, w)
    den = 1.0 / (va + vb + vc)
    v, w = vb * den, vc * den
    return (1 - v - w, v, w)


def _point(bc, a, b, c):
    return tuple(bc[0] * a[i] + bc[1] * b[i] + bc[2] * c[i] for i in range(3))


def quad_split(q):
    """Maya's triangles of quad corners 0..3 (MFnMesh.getTriangles)."""
    d02 = _dot(_sub(q[0], q[2]), _sub(q[0], q[2]))
    d13 = _dot(_sub(q[1], q[3]), _sub(q[1], q[3]))
    return ((0, 1, 2), (0, 2, 3)) if d02 < QUAD_SPLIT * d13 else ((0, 1, 3), (1, 2, 3))


# --- Maya surface normal on a Blender mesh ------------------------------------------------------------

class SurfaceData:
    """World-space triangles of a mesh with Maya's corner normals (face normals weighted by corner angle x face
    area over each smooth fan; hard edges / flat faces split the fans)."""

    def __init__(self, mesh, matrix):
        import numpy as np
        from mathutils.bvhtree import BVHTree
        n = len(mesh.vertices)
        co = np.empty(n * 3, dtype=np.float32)
        mesh.vertices.foreach_get("co", co)
        co = co.reshape(n, 3).astype(np.float64)
        m = np.array(matrix, dtype=np.float64)
        co = co @ m[:3, :3].T + m[:3, 3]
        self.co = [tuple(v) for v in co.tolist()]
        polys = mesh.polygons
        starts = [p.loop_start for p in polys]
        totals = [p.loop_total for p in polys]
        lv = [lp.vertex_index for lp in mesh.loops]
        le = [lp.edge_index for lp in mesh.loops]
        sharp_e = mesh.attributes.get("sharp_edge")
        sharp_e = [d.value for d in sharp_e.data] if sharp_e is not None and sharp_e.domain == 'EDGE' else None
        sharp_f = mesh.attributes.get("sharp_face")
        sharp_f = [d.value for d in sharp_f.data] if sharp_f is not None and sharp_f.domain == 'FACE' else None
        # face normals: Newell's method, unit length; face area = half the Newell length
        fn, area = [], []
        for s, t in zip(starts, totals):
            x = y = z = 0.0
            for k in range(t):
                a = self.co[lv[s + k]]
                b = self.co[lv[s + (k + 1) % t]]
                x += (a[1] - b[1]) * (a[2] + b[2])
                y += (a[2] - b[2]) * (a[0] + b[0])
                z += (a[0] - b[0]) * (a[1] + b[1])
            ln = math.sqrt(x * x + y * y + z * z) or 1.0
            fn.append((x / ln, y / ln, z / ln))
            area.append(ln / 2)
        # smooth fans: (vertex, face) pairs joined across smooth edges
        parent = {}

        def find(k):
            while parent.setdefault(k, k) != k:
                parent[k] = parent[parent[k]]
                k = parent[k]
            return k

        edge_faces = {}
        for f, (s, t) in enumerate(zip(starts, totals)):
            for k in range(t):
                edge_faces.setdefault(le[s + k], []).append(f)
        edges = mesh.edges
        for e, faces in edge_faces.items():
            if len(faces) < 2 or (sharp_e and sharp_e[e]):
                continue
            if sharp_f and any(sharp_f[f] for f in faces):
                continue
            for v in edges[e].vertices:
                for f in faces[1:]:
                    a, b = find((v, faces[0])), find((v, f))
                    if a != b:
                        parent[a] = b
        # Maya's mesh vertexNormalMethod default "Angle and Area Weighted": corner angle x face area
        fan = {}
        for f, (s, t) in enumerate(zip(starts, totals)):
            for k in range(t):
                v = self.co[lv[s + k]]
                e1 = _sub(self.co[lv[s + (k + 1) % t]], v)
                e2 = _sub(self.co[lv[s + (k - 1) % t]], v)
                l1, l2 = math.sqrt(_dot(e1, e1)), math.sqrt(_dot(e2, e2))
                cosa = _dot(e1, e2) / (l1 * l2) if l1 * l2 > 0 else 1.0
                w = math.acos(max(-1.0, min(1.0, cosa))) * area[f]
                key = find((lv[s + k], f))
                acc = fan.setdefault(key, [0.0, 0.0, 0.0])
                for i in range(3):
                    acc[i] += fn[f][i] * w
        for acc in fan.values():
            ln = math.sqrt(_dot(acc, acc)) or 1.0
            acc[:] = [c / ln for c in acc]
        # Maya triangulation; n-gons use Blender's triangles (Maya's n-gon rule is unknown)
        tris, tri_normals, tri_faces = [], [], []
        ngon_tris = {}
        if any(t > 4 for t in totals):
            mesh.calc_loop_triangles()
            for lt in mesh.loop_triangles:
                ngon_tris.setdefault(lt.polygon_index, []).append(tuple(lt.loops))
        for f, (s, t) in enumerate(zip(starts, totals)):
            if t == 3:
                corner_sets = [(s, s + 1, s + 2)]
            elif t == 4:
                q = [self.co[lv[s + k]] for k in range(4)]
                corner_sets = [tuple(s + k for k in tri) for tri in quad_split(q)]
            else:
                corner_sets = ngon_tris.get(f, [])
            for corners in corner_sets:
                tris.append(tuple(lv[c] for c in corners))
                tri_normals.append(tuple(tuple(fan[find((lv[c], f))]) for c in corners))
                tri_faces.append(f)
        self.tris, self.tri_normals, self.tri_faces = tris, tri_normals, tri_faces
        self.bvh = BVHTree.FromPolygons(self.co, tris, all_triangles=True) if tris else None

    def normal(self, p):
        """Maya's interpolated normal at the closest point of the surface to world point ``p`` (None without faces)."""
        if self.bvh is None:
            return None
        hit = self.bvh.find_nearest(Vector(p))
        if hit[2] is None:
            return None
        cands = {hit[2]}
        for h in self.bvh.find_nearest_range(Vector(p), hit[3] * (1 + 1e-5) + 1e-6):
            cands.add(h[2])
        found = []
        for i in cands:             # BVH distances are single precision: settle near ties in double
            a, b, c = (self.co[v] for v in self.tris[i])
            bc = closest_on_triangle(p, a, b, c)
            q = _point(bc, a, b, c)
            found.append((_dot(_sub(p, q), _sub(p, q)), i, bc))
        dmin = min(f[0] for f in found)
        # a point on a shared edge / corner: Maya took the higher face index (hard sphere ridge)
        _d, i, bc = max((f for f in found if f[0] <= dmin * (1 + 1e-9) + 1e-18),
                        key=lambda f: (self.tri_faces[f[1]], -f[0]))
        ns = self.tri_normals[i]
        n = [bc[0] * ns[0][k] + bc[1] * ns[1][k] + bc[2] * ns[2][k] for k in range(3)]
        ln = math.sqrt(_dot(n, n))
        return tuple(c / ln for c in n) if ln > 1e-15 else None


# --- Maya curve tangent on a Blender curve ------------------------------------------------------------

def _domain(c):
    k, d = c.knots, c.degree
    return k[d - 1], k[len(k) - d]


def _curve_ders(c, u):
    from . import curves_math as cm
    cvs, knots, deg, w = c.math()
    if w is None:
        return (cm.evaluate(cvs, knots, deg, u), cm.evaluate(cvs, knots, deg, u, deriv=1),
                cm.evaluate(cvs, knots, deg, u, deriv=2) if deg > 1 else (0.0, 0.0, 0.0))
    h = 1e-5
    a, b = _domain(c)
    lo, hi = max(a, u - h), min(b, u + h)
    p0, p, p1 = (cm.evaluate(cvs, knots, deg, x, w) for x in (lo, u, hi))
    d1 = tuple((p1[i] - p0[i]) / (hi - lo) for i in range(3))
    d2 = tuple((p1[i] - 2 * p[i] + p0[i]) / ((hi - lo) / 2) ** 2 for i in range(3))
    return p, d1, d2


def closest_param(c, p):
    """Maya parameter of the closest point of MCurve ``c`` to ``p`` (coarse samples + Newton, clamped / wrapped)."""
    a, b = _domain(c)
    spans = max(1, len(c.cvs) - c.degree)
    n = 48 * spans
    coarse = []
    for i in range(n + 1):
        u = a + (b - a) * i / n
        q = _curve_ders(c, u)[0]
        coarse.append((_dot(_sub(q, p), _sub(q, p)), u))
    coarse.sort()
    best = None
    for _d0, u in coarse[:4]:
        for _it in range(60):
            q, d1, d2 = _curve_ders(c, u)
            r = _sub(q, p)
            f = _dot(r, d1)
            fp = _dot(d1, d1) + _dot(r, d2)
            if abs(fp) < 1e-300:
                break
            du = -f / fp
            nu = u + du
            if c.periodic:
                nu = a + (nu - a) % (b - a)
            else:
                nu = min(b, max(a, nu))
            if abs(nu - u) < 1e-14:
                u = nu
                break
            u = nu
        q = _curve_ders(c, u)[0]
        d = _dot(_sub(q, p), _sub(q, p))
        if best is None or d < best[0]:
            best = (d, u)
    return best[1]


class CurveData:
    def __init__(self, ob):
        from . import curves_maya
        self.curves = [curves_maya.read_spline(sp, ob.matrix_world) for sp in ob.data.splines
                       if len(sp.points) + len(sp.bezier_points) >= 2]

    def tangent(self, p):
        best = None
        for c in self.curves:
            u = closest_param(c, p)
            q, d1, _d2 = _curve_ders(c, u)
            d = _dot(_sub(q, p), _sub(q, p))
            if best is None or d < best[0]:
                best = (d, d1)
        if best is None:
            return None
        t = best[1]
        ln = math.sqrt(_dot(t, t))
        return tuple(x / ln for x in t) if ln > 1e-15 else None


# --- the live setup: helper empties kept up to date by handlers -----------------------------------------

_cache = {}          # surface name -> (signature, data)
_state = {"busy": False, "count": -1, "names": set()}


def _signature(ob, depsgraph):
    ev = ob.evaluated_get(depsgraph) if depsgraph is not None else ob
    m = tuple(round(x, 12) for row in ev.matrix_world for x in row)
    if ob.type == 'MESH':
        import numpy as np
        me = ev.data
        co = np.empty(len(me.vertices) * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
        return (m, len(me.polygons), len(me.edges), hash(co.tobytes()))
    pts = []
    for sp in ob.data.splines:
        pts.append((sp.type, sp.order_u, sp.use_cyclic_u, sp.use_endpoint_u))
        pts.extend(tuple(p.co) for p in sp.points)
        pts.extend((tuple(p.co), tuple(p.handle_left), tuple(p.handle_right)) for p in sp.bezier_points)
    return (m, hash(tuple(pts)))


def surface_data(ob, depsgraph=None):
    sig = _signature(ob, depsgraph)
    hit = _cache.get(ob.name)
    if hit is not None and hit[0] == sig:
        return hit[1]
    if ob.type == 'MESH':
        ev = ob.evaluated_get(depsgraph) if depsgraph is not None else ob
        data = SurfaceData(ev.data, ev.matrix_world)
    else:
        data = CurveData(ob)
    _cache[ob.name] = (sig, data)
    return data


def direction(kind, surface, p, depsgraph=None):
    data = surface_data(surface, depsgraph)
    return data.normal(p) if kind == "normal" else data.tangent(p)


def helpers():
    """Helper empties of kit normal / tangent constraints (cached by name, rescanned when objects come and go)."""
    if len(bpy.data.objects) != _state["count"]:
        _state["count"] = len(bpy.data.objects)
        _state["names"] = {o.name for o in bpy.data.objects if o.get(KIND) in LABEL}
    out = []
    for name in list(_state["names"]):
        ob = bpy.data.objects.get(name)
        if ob is None or ob.get(KIND) not in LABEL:
            _state["count"] = -1
            continue
        out.append(ob)
    return out


def _rescan(*_args):
    _state["count"] = -1


def update(depsgraph=None):
    """Move every helper to  P + L * direction  (no write when it is already there: the handler doesn't loop)."""
    if _state["busy"]:
        return
    hs = helpers()
    if not hs:
        return
    _state["busy"] = True
    try:
        if depsgraph is None:
            depsgraph = bpy.context.evaluated_depsgraph_get()
        for h in hs:
            owner, surface = h.get(OWNER), h.get(SURFACE)
            if not isinstance(owner, bpy.types.Object) or not isinstance(surface, bpy.types.Object):
                continue
            if surface.type not in {'MESH', 'CURVE'}:
                continue
            p = tuple(owner.evaluated_get(depsgraph).matrix_world.translation)
            d = direction(h[KIND], surface, p, depsgraph)
            if d is None:
                continue
            length = 1000.0 * max(1.0, math.sqrt(_dot(p, p)))     # far away: the float32 helper keeps the angle
            new = Vector(p) + Vector(d) * length
            if (h.location - new).length > 1e-7 * length or h.parent is not None:
                h.parent = None
                h.location = new
    finally:
        _state["busy"] = False


@bpy.app.handlers.persistent
def _on_depsgraph(scene, depsgraph):
    update(depsgraph)


@bpy.app.handlers.persistent
def _on_frame(scene, depsgraph=None):
    update(depsgraph)


@bpy.app.handlers.persistent
def _on_load(*_args):
    _cache.clear()
    _rescan()


_HANDLERS = (("depsgraph_update_post", _on_depsgraph), ("frame_change_post", _on_frame),
             ("load_post", _on_load), ("undo_post", _on_load), ("redo_post", _on_load))


def register_handlers():
    for attr, fn in _HANDLERS:
        lst = getattr(bpy.app.handlers, attr)
        if fn not in lst:
            lst.append(fn)


def unregister_handlers():
    for attr, fn in _HANDLERS:
        lst = getattr(bpy.app.handlers, attr)
        if fn in lst:
            lst.remove(fn)
    _cache.clear()
    _rescan()


def helper_of(con):
    t = getattr(con, "target", None)
    return t if t is not None and t.get(KIND) in LABEL else None


def helpers_owned_by(objects):
    """Helper empties of the kit normal / tangent constraints on ``objects``."""
    owners = set(objects)
    return [h for h in helpers() if h.get(OWNER) in owners]


def remove_helpers(objs):
    """Delete helper empties (each once; objects already gone are skipped). Maya's normal / tangent constraint is a
    DAG child of the constrained object, so it goes with the object and with Delete by Type > Constraints
    (#109; Remove Target already did this, ``remove_targets``)."""
    seen = set()
    for h in objs:
        try:
            if h.as_pointer() in seen or h.get(KIND) not in LABEL:
                continue
        except ReferenceError:
            continue
        seen.add(h.as_pointer())
        bpy.data.objects.remove(h, do_unlink=True)
    if seen:
        _rescan()
    return len(seen)


def surface_of(con):
    h = helper_of(con)
    return h.get(SURFACE) if h is not None else None


def _link_like(ob, owner, context):
    cols = list(owner.users_collection) or [context.scene.collection]
    cols[0].objects.link(ob)


def add_surface_constraint(context, kind, owner, surface, aim_vector=rig_tools.AIM_VECTOR,
                           up_vector=rig_tools.UP_VECTOR, world_up=rig_tools.WORLD_UP, weight=1.0):
    """Kit normal / tangent constraint on ``owner`` from ``surface``: helper empty + Track To. Returns the constraint."""
    n = 1 + sum(1 for c in owner.constraints if helper_of(c) is not None and helper_of(c).get(KIND) == kind)
    helper = bpy.data.objects.new(f"{owner.name}_{MAYA_NODE[kind]}{n}Aim", None)
    helper.empty_display_size = 0.0
    helper.hide_viewport = helper.hide_render = helper.hide_select = True
    helper[KIND], helper[OWNER], helper[SURFACE] = kind, owner, surface
    _link_like(helper, owner, context)
    _rescan()
    cons = owner.constraints
    con = cons.new('TRACK_TO')
    con.target = helper
    con = rig_tools.aim(cons, con, aim_vector, up_vector, world_up)
    con.name = f"{LABEL[kind]} {surface.name}"
    con.influence = weight
    context.view_layer.update()
    update(context.evaluated_depsgraph_get())
    context.view_layer.update()
    return con


WORLD_UP_ITEMS = (("Vector", "Vector", "World up vector (0, 1, 0) = Blender world Z (default)"),
                  ("Scene up", "Scene up", "The scene's up axis (Maya Y = Blender Z)"),
                  ("None", "None", "No up vector: the shortest turn (Blender Damped Track)"))


class _SurfaceConstraint:
    bl_options = {'REGISTER', 'UNDO'}
    kind = "normal"

    weight: FloatProperty(name="Weight", default=1.0, min=0.0, max=1.0)
    aim_vector: FloatVectorProperty(name="Aim vector", default=(1.0, 0.0, 0.0), size=3)
    up_vector: FloatVectorProperty(name="Up vector", default=(0.0, 1.0, 0.0), size=3)
    world_up_type: EnumProperty(name="World up type", items=WORLD_UP_ITEMS, default="Vector")

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.active_object is not None

    def _targets(self, context, owner):
        want = {'MESH'} if self.kind == "normal" else {'CURVE'}
        return [o for o in context.selected_objects if o is not owner and o.type in want]

    def execute(self, context):
        owner = context.active_object
        targets = self._targets(context, owner)
        if not targets:
            self.report({'WARNING'}, SURFACE_HINT if self.kind == "normal" else CURVE_HINT)
            return {'CANCELLED'}
        try:
            for t in targets:
                add_surface_constraint(context, self.kind, owner, t, tuple(self.aim_vector), tuple(self.up_vector),
                                       self.world_up_type, self.weight)
        except RuntimeError as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        results.result(self, f"{LABEL[self.kind]} on {owner.name} (target {', '.join(t.name for t in targets)})")
        return {'FINISHED'}


class ALLSET_OT_normal_constraint(_SurfaceConstraint, bpy.types.Operator):
    """Maya Normal constraint: select the target surface(s), then the object; its aim vector follows the surface
    normal at the closest point"""
    bl_idname = "allset.normal_constraint"
    bl_label = "Normal Constraint"
    kind = "normal"


class ALLSET_OT_tangent_constraint(_SurfaceConstraint, bpy.types.Operator):
    """Maya Tangent constraint: select the target curve(s), then the object; its aim vector follows the curve
    tangent at the closest point"""
    bl_idname = "allset.tangent_constraint"
    bl_label = "Tangent Constraint"
    kind = "tangent"


# --- Maya constraint types of the kit's Blender constraints -------------------------------------------

CHANNELS = {"point": "t", "geometry": "t", "aim": "r", "orient": "r", "normal": "r", "tangent": "r",
            "scale": "s", "parent": "tr"}


def maya_type(con):
    t = con.type
    if t in {'TRACK_TO', 'DAMPED_TRACK', 'LOCKED_TRACK'}:
        h = helper_of(con)
        return h.get(KIND) if h is not None else "aim"
    return {'CHILD_OF': "parent", 'COPY_TRANSFORMS': "parent", 'COPY_LOCATION': "point",
            'COPY_ROTATION': "orient", 'COPY_SCALE': "scale", 'SHRINKWRAP': "geometry"}.get(t)


def maya_target(con, arm=None):
    """(object, bone name or "") the Maya target of a kit constraint."""
    s = surface_of(con)
    if s is not None:
        return s, ""
    t = getattr(con, "target", None)
    return t, (getattr(con, "subtarget", "") if t is not None and t.type == 'ARMATURE' else "")


# --- baking the visual value into the own channels ------------------------------------------------------

def _save(node):
    return {"t": node.location.copy(), "e": node.rotation_euler.copy(), "q": node.rotation_quaternion.copy(),
            "a": tuple(node.rotation_axis_angle), "s": node.scale.copy()}


def _restore(node, saved, keys, axes=None):
    """Put back the saved channels not in ``keys`` (and, with ``axes``, the axes of ``keys`` not in ``axes``)."""
    for k in "trs":
        if k in keys and axes is None:
            continue
        if k == "t":
            cur = node.location.copy()
            node.location = [cur[i] if (k in keys and i in axes) else saved["t"][i] for i in range(3)]
        elif k == "s":
            cur = node.scale.copy()
            node.scale = [cur[i] if (k in keys and i in axes) else saved["s"][i] for i in range(3)]
        else:
            if k in keys:                   # per axis: only Euler channels split; other modes keep the new value
                if node.rotation_mode not in {'QUATERNION', 'AXIS_ANGLE'}:
                    cur = node.rotation_euler.copy()
                    node.rotation_euler = [cur[i] if i in axes else saved["e"][i] for i in range(3)]
                continue
            node.rotation_euler = saved["e"]
            node.rotation_quaternion = saved["q"]
            node.rotation_axis_angle = saved["a"]


def visual(context, node):
    context.view_layer.update()
    return node.matrix.copy() if isinstance(node, bpy.types.PoseBone) else node.matrix_world.copy()


def bake(context, node, keys, axes=None, matrix=None):
    """Write the visual (constrained) value of channels ``keys`` ("t" / "r" / "s") into ``node``'s own channels."""
    if not keys:
        return
    m = visual(context, node) if matrix is None else matrix
    saved = _save(node)
    if isinstance(node, bpy.types.PoseBone):
        node.matrix = m
    else:
        node.matrix_world = m
    _restore(node, saved, keys, axes)
    context.view_layer.update()


# --- Remove Target ------------------------------------------------------------------------------------

REMOVE_TYPES = ("point", "orient", "aim", "scale", "parent", "geometry", "normal", "tangent", "pole_vector")


def _owner_and_targets(context):
    """(constrained node, [(object, bone name)] targets) in Maya's selection order (constrained last)."""
    if context.mode == 'POSE' and context.active_pose_bone is not None:
        pb = context.active_pose_bone
        arm = pb.id_data
        targets = [(o, "") for o in context.selected_objects if o is not arm]
        targets += [(arm, b.name) for b in context.selected_pose_bones or () if b != pb]
        return pb, targets
    ob = context.active_object
    return ob, [(o, "") for o in context.selected_objects if o is not ob]


def remove_targets(context, owner, targets, types=REMOVE_TYPES):
    """Remove the kit constraints of ``types`` on ``owner`` whose Maya target is in ``targets``; bake the channels of
    a Maya type whose last target goes. Returns [(maya type, target name)] removed, or None when ``owner`` is not
    constrained at all."""
    removed = []
    cons = list(getattr(owner, "constraints", ()))
    poles = []
    if "pole_vector" in types and isinstance(owner, bpy.types.Object):
        from . import skin
        poles = [(arm, pb, con) for arm, pb, con in skin.ik_constraints_on(owner) if con.pole_target is not None]
    typed = [(c, maya_type(c)) for c in cons]
    typed = [(c, t) for c, t in typed if t is not None]
    if not typed and not poles:
        return None
    tset = {(o.name, b) for o, b in targets}
    doomed = []
    for c, t in typed:
        if t not in types:
            continue
        obj, bone = maya_target(c)
        if obj is not None and (obj.name, bone) in tset:
            doomed.append((c, t, obj.name + ("." + bone if bone else "")))
    for t in {t for _c, t, _n in doomed}:
        left = [c for c, tt in typed if tt == t and all(c is not d for d, _t, _n in doomed)]
        if not left:
            bake(context, owner, CHANNELS[t])
    for c, t, name in doomed:
        h = helper_of(c)
        owner.constraints.remove(c)
        if h is not None:
            bpy.data.objects.remove(h)
            _rescan()
        removed.append((t, name))
    for arm, pb, con in poles:
        if (con.pole_target.name, getattr(con, "pole_subtarget", "") or "") in tset:
            name = con.pole_target.name
            con.pole_target = None
            removed.append(("pole_vector", name))
    context.view_layer.update()
    return removed


class ALLSET_OT_remove_constraint_target(bpy.types.Operator):
    """Maya Remove Target: select the target(s), then the constrained object; the constraints from those targets go
    (the last one of a type leaves the channels where the constraint had them)"""
    bl_idname = "allset.remove_constraint_target"
    bl_label = "Remove Target"
    bl_options = {'REGISTER', 'UNDO'}

    remove_all: BoolProperty(name="All", default=True, description="Remove the targets from every constraint type")
    point: BoolProperty(name="Point constraint", default=True)
    orient: BoolProperty(name="Orient constraint", default=True)
    aim: BoolProperty(name="Aim constraint", default=True)
    scale: BoolProperty(name="Scale constraint", default=True)
    parent: BoolProperty(name="Parent constraint", default=True)
    geometry: BoolProperty(name="Geometry constraint", default=True)
    normal: BoolProperty(name="Normal constraint", default=True)
    tangent: BoolProperty(name="Tangent constraint", default=True)
    pole_vector: BoolProperty(name="Pole vector constraint", default=True)

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'POSE'} and context.active_object is not None

    def execute(self, context):
        owner, targets = _owner_and_targets(context)
        if owner is None or not targets:
            self.report({'ERROR'}, MSG_REMOVE_SELECT)
            return {'CANCELLED'}
        types = REMOVE_TYPES if self.remove_all else tuple(t for t in REMOVE_TYPES if getattr(self, t))
        removed = remove_targets(context, owner, targets, types)
        if removed is None:
            self.report({'ERROR'}, MSG_REMOVE_CONSTRAINED)
            return {'CANCELLED'}
        if removed:
            results.result(self, f"Removed {', '.join(f'{n} ({t})' for t, n in removed)} from {owner.name}")
        else:
            results.result(self, f"No selected target constrains {owner.name}")
        return {'FINISHED'}


# --- Set Rest Position ----------------------------------------------------------------------------------

REST_TYPES = ("point", "aim", "orient", "scale", "tangent", "normal", "parent")


def has_offset(con):
    """True when the constraint adds the own channels in (Copy Location / Scale Offset, Copy Rotation mixing): the own
    channels are its offset, so they can't also hold the rest position."""
    if con.type in {'COPY_LOCATION', 'COPY_SCALE'}:
        return con.use_offset
    if con.type == 'COPY_ROTATION':
        return con.mix_mode != 'REPLACE'
    return False


def set_rest(context, node):
    """The constrained channels become the own channels (= what Blender shows at influence 0); nothing moves now.
    Returns (keys written, names of constraints whose own channels are an offset and were left alone)."""
    keys, kept = set(), []
    cons = [(c, maya_type(c)) for c in getattr(node, "constraints", ())]
    cons = [(c, t) for c, t in cons if t in REST_TYPES]
    for c, t in cons:
        if has_offset(c):
            kept.append(c.name)
        else:
            keys.update(CHANNELS[t] + ("s" if c.type == 'CHILD_OF' else ""))   # its inverse is reset below
    for c, t in cons:
        if has_offset(c):
            keys.difference_update(CHANNELS[t])
    if keys:
        bake(context, node, "".join(sorted(keys)))
        # Child Of multiplies the own channels in: a new inverse keeps the object where it is (and moving the
        # target then moves it exactly as before)
        for c, _t in cons:
            if c.type == 'CHILD_OF':
                c.set_inverse_pending = True
        context.view_layer.update()
    return keys, kept


class ALLSET_OT_set_constraint_rest(bpy.types.Operator):
    """Maya Set Rest Position: the constrained objects' current values become where they go when the constraint
    weights are 0"""
    bl_idname = "allset.set_constraint_rest"
    bl_label = "Set Rest Position"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'POSE'}

    def execute(self, context):
        nodes = list(context.selected_pose_bones or ()) if context.mode == 'POSE' else list(context.selected_objects)
        done, kept, constrained = [], [], False
        for n in nodes:
            constrained |= any(maya_type(c) in REST_TYPES for c in getattr(n, "constraints", ()))
            keys, k = set_rest(context, n)
            if keys:
                done.append(n.name)
            kept += k
        if not constrained:
            self.report({'ERROR'}, MSG_REST)
            return {'CANCELLED'}
        if kept:
            self.report({'WARNING'}, f"These keep their offset in the own channels: {', '.join(kept)}")
        if not done:
            return {'FINISHED'}
        results.result(self, f"Rest position set: {', '.join(done)}")
        return {'FINISHED'}


# --- Modify Constrained Axis ----------------------------------------------------------------------------

AXIS_TYPES = ("point", "aim", "orient", "scale", "parent")


def _target_matrix(con):
    t = con.target
    if t is None:
        return Matrix.Identity(4)
    if t.type == 'ARMATURE' and getattr(con, "subtarget", ""):
        pb = t.pose.bones.get(con.subtarget)
        if pb is not None:
            return t.matrix_world @ pb.matrix
    return t.matrix_world.copy()


def _flags(con):
    if con.type == 'CHILD_OF':
        return [con.use_location_x, con.use_location_y, con.use_location_z]
    return [con.use_x, con.use_y, con.use_z]


def _set_flags(con, flags):
    if con.type == 'CHILD_OF':
        for i, a in enumerate("xyz"):
            setattr(con, f"use_location_{a}", flags[i])
            setattr(con, f"use_rotation_{a}", flags[i])
        return
    con.use_x, con.use_y, con.use_z = flags


def modify_axes(context, node, flags, maintain=False):
    """Set the constrained axes of ``node``'s point / orient / scale / parent constraints. Returns (changed, skipped):
    skipped = aim constraints (Blender's Track To always aims on every axis)."""
    changed, skipped = [], []
    is_bone = isinstance(node, bpy.types.PoseBone)
    for c in list(getattr(node, "constraints", ())):
        t = maya_type(c)
        if t not in AXIS_TYPES:
            continue
        if t == "aim":
            if not all(flags):
                skipped.append(c.name)
            continue
        before = _flags(c)
        vis = visual(context, node)
        newly_off = [i for i in range(3) if before[i] and not flags[i]]
        _set_flags(c, flags)
        key = CHANNELS[t]
        if maintain and not is_bone and t in {"point", "scale", "orient"}:
            _maintain(context, node, c, t, vis, flags)
        else:
            if t in {"point", "scale"}:
                c.use_offset = False
            elif t == "orient":
                c.mix_mode = 'REPLACE'
            elif t == "parent":
                # Child Of multiplies the own channels in: a new inverse keeps the object where it is (Maya zeroes
                # the offset without Maintain offset)
                bake(context, node, "trs", matrix=vis)
                c.set_inverse_pending = True
            if newly_off and t != "parent":
                bake(context, node, key, axes=set(newly_off), matrix=vis)
        changed.append(c.name)
    context.view_layer.update()
    return changed, skipped


def _maintain(context, node, con, t, vis, flags):
    """Blender offsets so the object stays where it is now (Maya's Maintain offset)."""
    tm = _target_matrix(con)
    loc, rot, sca = vis.decompose()
    tl, tr, ts = tm.decompose()
    saved = _save(node)
    if t == "point":
        con.use_offset = True                       # result = target + own (world space, axes that follow)
        want = Vector([loc[i] - tl[i] if flags[i] else loc[i] for i in range(3)])
        node.matrix_world = Matrix.LocRotScale(want, rot, sca)
        _restore(node, saved, "t")
    elif t == "scale":
        con.use_offset, con.use_add = True, False   # result = target x own
        want = Vector([sca[i] / ts[i] if flags[i] and abs(ts[i]) > 1e-12 else sca[i] for i in range(3)])
        node.scale = want
    else:                                           # orient: result = target rotation, then the own rotation
        if all(flags):
            con.mix_mode = 'BEFORE'
            own = (tr.inverted() @ rot)
            node.matrix_world = Matrix.LocRotScale(loc, own, sca)
            _restore(node, saved, "r")
        else:
            con.mix_mode = 'REPLACE'
            newly = [i for i in range(3) if not flags[i]]
            bake(context, node, "r", axes=set(newly), matrix=vis)
    context.view_layer.update()


class ALLSET_OT_modify_constraint_axes(bpy.types.Operator):
    """Maya Modify Constrained Axis: which axes the selected objects' point / orient / scale / parent constraints
    drive"""
    bl_idname = "allset.modify_constraint_axes"
    bl_label = "Modify Constrained Axis"
    bl_options = {'REGISTER', 'UNDO'}

    x: BoolProperty(name="X", default=True, description="Enable to make the constraint act upon the X axis")
    y: BoolProperty(name="Y", default=True, description="Enable to make the constraint act upon the Y axis")
    z: BoolProperty(name="Z", default=True, description="Enable to make the constraint act upon the Z axis")
    maintain_offset: BoolProperty(name="Maintain offset", default=False,
                                  description="Preserve the current offset of the constrained objects")

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'POSE'}

    def execute(self, context):
        nodes = list(context.selected_pose_bones or ()) if context.mode == 'POSE' else list(context.selected_objects)
        if not nodes:
            self.report({'ERROR'}, MSG_AXES_SELECT)
            return {'CANCELLED'}
        flags = [self.x, self.y, self.z]
        if not any(flags):
            self.report({'ERROR'}, MSG_AXES_NONE)
            return {'CANCELLED'}
        changed, skipped = [], []
        for n in nodes:
            c, s = modify_axes(context, n, flags, self.maintain_offset)
            changed += c
            skipped += s
        if not changed and not skipped:
            self.report({'ERROR'}, MSG_AXES_INVALID)
            return {'CANCELLED'}
        if skipped:
            self.report({'WARNING'}, f"Blender's Track To aims on every axis: {', '.join(skipped)} unchanged")
        if changed:
            axes = "".join(a for a, f in zip("XYZ", flags) if f)
            results.result(self, f"Constrained axes {axes}: {', '.join(changed)}")
        return {'FINISHED'}


classes = (ALLSET_OT_normal_constraint, ALLSET_OT_tangent_constraint, ALLSET_OT_remove_constraint_target,
           ALLSET_OT_set_constraint_rest, ALLSET_OT_modify_constraint_axes)
