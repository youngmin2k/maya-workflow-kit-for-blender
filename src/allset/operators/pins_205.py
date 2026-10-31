# SPDX-License-Identifier: GPL-3.0-or-later
"""Issue #112: Constrain > UV Pin / Proximity Pin, Deform > Display / Hide Intermediate Objects,
Deform > Wrap > Add / Remove Influence.

Maya 2022 behaviour (Maya's option windows):

- UV Pin: factory = Pin locations
  *Transforms*, Output *Existing Transform*, Normal axis X, Tangent axis Y, UV set "" (current), Normalize isoparms on.
  The geometry is selected first, then the transforms. For each transform the UV at the closest point of the
  geometry becomes an input of one uvPin node (``uvPin1``); the transform's translate /
  rotate / scale are cleared, the node's output matrix drives its offsetParentMatrix
  and inheritsTransform is turned off ("Inherit transform has been turned off for [...]"). Components mode (option)
  pins new ``pinOutput`` transforms / locators to the selected vertices' UVs, faces' mean UV, edges' mid UV;
  with Existing Transform it errors "Output mode does not work with this creation mode".
- Proximity Pin: factory = Setup Transforms,
  Output Existing Transform, Input *New Locator*, Maintain offset on, Mode Edge, axes X / Y. One proximityPin node; per
  transform a ``pinInput`` locator holding the transform's matrix relative to the geometry, the transform cleared and
  driven by the node. Components setup: "Not yet implemented...".

The kit: a pinned transform gets a Copy Transforms constraint named like the Maya node (``uvPin1``) in mode Before
Original (Full) — world = pin matrix @ own channels, Maya's offsetParentMatrix with inheritsTransform off (the
"Inherit transform has been turned off" warning lists every pinned existing transform, like Maya) — targeting a hidden
helper empty that a depsgraph / frame handler keeps at the pin matrix (the pattern of operators/constrain_199.py). The
pin matrix follows Maya's rules (within 1e-4, checked by
tests/test_step205_pins_maya.py): quad locations are bilinear (s, t), normal = blend of Maya vertex normals (unit
face-normal average), tangent = dP/du of the face's first triangle; UV Pin = the frame at the stored UV on the deformed
mesh; Proximity Pin = the closest point of the *original* mesh to pinInput at every evaluation, output = F1 · F0⁻¹ ·
input (Offset Translation 0 = on the surface, Offset Orientation 0 = Edge / UV orientation, Envelope = slerp / lerp
towards the input). Deformed points = the evaluated mesh when its topology equals the mesh's (the smooth preview: its
first vertices).

Intermediate objects: Maya's intermediate object of a deformed shape is its
``<shape>Orig`` (every mesh deformer adds one); Display sets intermediateObject 0
on it and selects it, Hide sets it back and selects the deformed objects. Blender keeps the undeformed mesh as the
object's own data, so the kit shows it as a child object ``<shape>Orig`` sharing that mesh with no modifiers (edits
to it edit the original shape, like Maya) and deletes it on Hide. Base wires / pin and constraint helpers
are not intermediate objects in Maya (curve1BaseWire = a hidden transform) and stay as they are.

Wrap influences (Maya's Wrap deformer): the deformed surfaces are selected, the influence last. Blender's
Surface Deform reads one target, so every extra influence is one more Surface Deform ``wrap1Influence<k>`` (+ its Hook
``wrap1Influence<k>Base`` like wrap1Base) and each wrapped point follows the influence nearest to it (its weight moves to
that influence's vertex group; Maya blends influences by distance). Removing the last influence removes
the wrap node (Maya keeps an empty wrap1).
"""

import math

import bmesh
import bpy
import numpy as np
from bpy.props import BoolProperty, EnumProperty
from mathutils import Matrix, Vector

from .. import results, undo_steps
from . import deformers, units

KIND = "allset_pin"                  # helper empty: "uvPin" | "proximityPin"
NODE = "allset_pin_node"             # helper empty: Maya node name (uvPin1)
OWNER = "allset_pin_owner"           # helper empty: the pinned transform
GEOM = "allset_pin_geometry"         # helper empty: the geometry (mesh object)
UV = "allset_pin_uv"                 # uvPin helper: (u, v)
INPUT = "allset_pin_input"           # proximityPin helper: pinInput object (None = stored matrix INPUT_MATRIX)
INPUT_MATRIX = "allset_pin_input_matrix"
OFFSET = "allset_pin_offset"         # proximityPin helper: maintain offset (the default of the two below)
OFFSET_T = "allset_pin_offset_translation"   # proximityPin helper: Maya offsetTranslation (0..1)
OFFSET_O = "allset_pin_offset_orientation"   # proximityPin helper: Maya offsetOrientation (0..1)
ENVELOPE = "allset_pin_envelope"     # proximityPin helper: Maya envelope (0..1)
MODE = "allset_pin_mode"             # "edge" | "uv" (coordinate system of the tangent)
AXES = "allset_pin_axes"             # (normal axis, tangent axis), 0..5 = X Y Z -X -Y -Z
INTERMEDIATE_OF = "allset_intermediate_of"
PIN_TYPES = ("uvPin", "proximityPin")
AXIS_ITEMS = ("X", "Y", "Z", "-X", "-Y", "-Z")

# Maya messages (Maya 2022 string resources)
MSG_GEOMETRY = "Must select geometry before adding this constraint."
MSG_OUTPUT_MODE = "Output mode does not work with this creation mode"
MSG_NO_COMPONENTS = "No components were selected: no uvPin node created"
MSG_NOT_IMPLEMENTED = "Not yet implemented..."
MSG_IO = "Existing transform cannot be used as both an input and output."
MSG_INHERIT = "Inherit transform has been turned off for {0}"
MSG_AXIS = ("Selection rejected because normal axis cannot be the same as tangent axis. Choose an axis that is "
            "different than the tangent axis.")
HINT_UV = ("Select geometry to constrain to and then Shift + select transforms to derive input uvs Or selected "
           "geometry components to specify input uvs.")
HINT_PROX = "Select geometry to constrain to and then Shift + select objects to be constrained."
MSG_NO_DEFORMABLE = "No deformable object is selected."
MSG_ALREADY_OFF = "Display is already toggled off."
MSG_ALREADY_ON = "Display is already toggled on."
MSG_FOUND_NONE = "Found no intermediate objects."
MSG_WRAP_SELECT = "Select at least one surface (or wrap node) and one influence object."
MSG_WRAP_INFLUENCE = "Influence objects must be polygon meshes, NURBS curves or NURBS surfaces."
MSG_NO_WRAP = "No wrap deformer is associated with surface {0}."


# --- geometry: original and deformed points of one mesh -------------------------------------------------------
#
# Maya's pin surface frame (every "O" case within 1.4e-7):
# a location is (face, weights over its corners) — on a quad the bilinear (s, t) of its corners f0 f1 f2 f3, found
# from the UV (UV Pin) or the closest point (Proximity Pin); position = the same blend of the corner points, normal =
# the same blend of Maya vertex normals (normalised sum of the unit face normals around the vertex), tangent = dP/du
# of the face's FIRST Maya triangle (f0, f1, f[-1]) made orthogonal to the normal; the normal / tangent go to the
# chosen axes and the third axis completes a right-handed frame. N-gons / triangles use the triangle barycentrics.

def _vec_array(coll, attr, n, dim=3):
    a = np.empty(n * dim, dtype=np.float64)
    coll.foreach_get(attr, a)
    return a.reshape(n, dim)


def _int_array(coll, attr, n):
    a = np.empty(n, dtype=np.int64)
    coll.foreach_get(attr, a)
    return a


def _unit_rows(a):
    n = np.linalg.norm(a, axis=1)
    return a / np.where(n > 1e-30, n, 1.0)[:, None]


def _inv_bilinear(q, x):
    """(s, t) in [0, 1]² with (1-s)(1-t)q0 + s(1-t)q1 + st q2 + (1-s)t q3 closest to ``x`` (Gauss-Newton; exact on a
    UV rectangle / planar quad)."""
    s = t = 0.5
    for _i in range(40):
        b = (1 - s) * (1 - t) * q[0] + s * (1 - t) * q[1] + s * t * q[2] + (1 - s) * t * q[3]
        bs = (1 - t) * (q[1] - q[0]) + t * (q[2] - q[3])
        bt = (1 - s) * (q[3] - q[0]) + s * (q[2] - q[1])
        j = np.stack([bs, bt], axis=1)
        jtj = j.T @ j
        if abs(np.linalg.det(jtj)) < 1e-30:
            break
        d = np.linalg.solve(jtj, j.T @ (x - b))
        s, t = s + d[0], t + d[1]
        if abs(d[0]) + abs(d[1]) < 1e-15:
            break
    return min(max(s, 0.0), 1.0), min(max(t, 0.0), 1.0)


class Geo:
    """A mesh's faces / triangles (original topology), UVs and its original (local) / deformed (local) points."""

    def __init__(self, ob, depsgraph):
        me = ob.data
        if ob.mode == 'EDIT':
            # the original mesh's loop data is empty while the edit BMesh owns it (foreach_get raised on every
            # update): the pin waits where it is and follows again when edit mode ends
            self.ok = False
            return
        tris = me.loop_triangles
        nt = len(tris)
        self.ok = nt > 0
        if not self.ok:
            return
        self.tv = _int_array(tris, "vertices", nt * 3).reshape(nt, 3)
        self.tl = _int_array(tris, "loops", nt * 3).reshape(nt, 3)
        self.tp = _int_array(tris, "polygon_index", nt)
        npoly, nl = len(me.polygons), len(me.loops)
        self.ls = _int_array(me.polygons, "loop_start", npoly)
        self.lt = _int_array(me.polygons, "loop_total", npoly)
        self.lv = _int_array(me.loops, "vertex_index", nl)
        uvl = me.uv_layers.active
        self.luv = _vec_array(uvl.uv, "vector", nl, 2) if uvl is not None else None
        self.tuv = self.luv[self.tl] if self.luv is not None else None
        nv = len(me.vertices)
        self.co0 = _vec_array(me.vertices, "co", nv)
        ev = ob.evaluated_get(depsgraph) if depsgraph is not None else ob
        self.mw = np.array(ev.matrix_world, dtype=np.float64)
        em = ev.data
        if len(em.vertices) == nv and len(em.polygons) == npoly:
            self.co = _vec_array(em.vertices, "co", nv)
        elif len(em.vertices) > nv:
            # a subdivided result (the kit's smooth preview): Blender's subdivision writes the mesh's own vertices
            # first, at their smoothed place — the pin rides the displayed surface. Maya's preview is
            # display only (the pin keeps the unsmoothed shape): Blender can't give the deformed,
            # unsubdivided points here (BMesh.from_object(cage=True) applies deform modifiers twice).
            self.co = _vec_array(em.vertices, "co", len(em.vertices))[:nv]
        else:
            self.co = self.co0
        self._normals = {}

    def world_points(self):
        m = self.mw
        return self.co @ m[:3, :3].T + m[:3, 3]

    def normals(self, deformed=True):
        """Maya vertex normals (local): normalised sum of the unit (Newell) face normals around each vertex."""
        got = self._normals.get(deformed)
        if got is None:
            co = self.co if deformed else self.co0
            npoly, nl = len(self.ls), len(self.lv)
            poly = np.repeat(np.arange(npoly), self.lt)
            nxt = np.arange(1, nl + 1)
            nxt[self.ls + self.lt - 1] = self.ls
            fn = np.zeros((npoly, 3))
            np.add.at(fn, poly, np.cross(co[self.lv], co[self.lv[nxt]]))
            vn = np.zeros_like(co)
            np.add.at(vn, self.lv, _unit_rows(fn)[poly])
            got = self._normals[deformed] = _unit_rows(vn)
        return got

    def _loc(self, t, bw, coords):
        """Location (face, corner weights) from triangle t / barycentric bw; quads get Maya's bilinear (s, t) of the
        point ``coords[corners]`` blend (UVs or points)."""
        p = int(self.tp[t])
        ls, lt = int(self.ls[p]), int(self.lt[p])
        if lt == 4:
            q = coords[ls:ls + 4]
            s, tt = _inv_bilinear(q, np.asarray(bw) @ coords[self.tl[t]])
            return p, np.array([(1 - s) * (1 - tt), s * (1 - tt), s * tt, (1 - s) * tt])
        w = np.zeros(lt)
        for k in range(3):
            w[int(self.tl[t][k]) - ls] += bw[k]
        return p, w

    def closest(self, p, original=False, world=True):
        """Location of the closest point to ``p`` on the deformed (world) / original (local) mesh."""
        from mathutils.bvhtree import BVHTree
        pts = self.co0 if original else (self.world_points() if world else self.co)
        bvh = BVHTree.FromPolygons([tuple(x) for x in pts.tolist()], self.tv.tolist())
        hit = bvh.find_nearest(Vector(p))
        if hit is None or hit[2] is None:
            return None
        t = int(hit[2])
        return self._loc(t, _bary(np.array(hit[0], dtype=np.float64), pts[self.tv[t]]), pts[self.lv])

    def at_uv(self, uv):
        """Location of ``uv`` (the triangle whose UVs contain it, else the nearest one, clamped)."""
        if self.tuv is None:
            return None
        a, b, c = self.tuv[:, 0], self.tuv[:, 1], self.tuv[:, 2]
        p = np.asarray(uv, dtype=np.float64)
        v0, v1, v2 = b - a, c - a, p - a
        d00 = (v0 * v0).sum(1)
        d01 = (v0 * v1).sum(1)
        d11 = (v1 * v1).sum(1)
        d20 = (v2 * v0).sum(1)
        d21 = (v2 * v1).sum(1)
        den = d00 * d11 - d01 * d01
        good = np.abs(den) > 1e-18
        den = np.where(good, den, 1.0)
        w1 = (d11 * d20 - d01 * d21) / den
        w2 = (d00 * d21 - d01 * d20) / den
        w0 = 1.0 - w1 - w2
        worst = np.minimum(np.minimum(w0, w1), w2)
        worst = np.where(good, worst, -1e30)
        t = int(np.argmax(worst))
        w = np.clip(np.array([w0[t], w1[t], w2[t]]), 0.0, None)
        s = w.sum()
        return self._loc(t, w / s if s > 0 else np.array([1 / 3, 1 / 3, 1 / 3]), self.luv)

    def uv_at(self, loc):
        if self.luv is None or loc is None:
            return None
        p, w = loc
        ls = int(self.ls[p])
        return tuple((self.luv[ls:ls + len(w)] * np.asarray(w)[:, None]).sum(0))

    def frame(self, loc, axes=(0, 1), deformed=True, world=True):
        """4x4 Maya pin frame (numpy, column vectors) at ``loc``: deformed points in world space, or original local."""
        p, w = loc
        ls, lt = int(self.ls[p]), int(self.lt[p])
        vs = self.lv[ls:ls + lt]
        P = (self.co if deformed else self.co0)[vs]
        N = self.normals(deformed)[vs]
        if world:
            m3, tr = self.mw[:3, :3], self.mw[:3, 3]
            P = P @ m3.T + tr
            try:
                N = N @ np.linalg.inv(m3)
            except np.linalg.LinAlgError:
                pass
        w = np.asarray(w, dtype=np.float64)
        pos = w @ P
        n = w @ N
        if np.linalg.norm(n) < 1e-12:
            n = np.cross(P[1] - P[0], P[-1] - P[0])
        n = n / (np.linalg.norm(n) or 1.0)
        tan = None
        e = np.stack([P[1] - P[0], P[-1] - P[0]], axis=1)          # the first Maya triangle f0, f1, f[-1]
        if self.luv is not None:
            uv = self.luv[ls:ls + lt]
            a = np.stack([uv[1] - uv[0], uv[-1] - uv[0]], axis=1)
            if abs(np.linalg.det(a)) > 1e-18:
                tan = (e @ np.linalg.inv(a))[:, 0]                  # dP/du
        if tan is None:
            tan = e[:, 0]                                           # no UVs: the edge f0 -> f1
        tan = tan - n * float(np.dot(tan, n))
        if np.linalg.norm(tan) < 1e-12:
            tan = np.cross(n, (1.0, 0.0, 0.0))
            if np.linalg.norm(tan) < 1e-9:
                tan = np.cross(n, (0.0, 1.0, 0.0))
        tan = tan / np.linalg.norm(tan)
        na, ta = axes
        cols = [None, None, None]
        cols[na % 3] = n * (1.0 if na < 3 else -1.0)
        cols[ta % 3] = tan * (1.0 if ta < 3 else -1.0)
        r = 3 - na % 3 - ta % 3
        cols[r] = np.cross(cols[(r + 1) % 3], cols[(r + 2) % 3])
        m = np.identity(4)
        for i in range(3):
            m[:3, i] = cols[i]
        m[:3, 3] = pos
        return m


def _bary(p, tri):
    a, b, c = tri
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
    d20, d21 = v2 @ v0, v2 @ v1
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-30:
        return np.array([1 / 3, 1 / 3, 1 / 3])
    w1 = (d11 * d20 - d01 * d21) / den
    w2 = (d00 * d21 - d01 * d20) / den
    return np.array([1.0 - w1 - w2, w1, w2])


# --- helpers (one per pinned output) and the handler that keeps them at the pin -------------------------------

_state = {"busy": False, "count": -1, "names": set()}


def helpers():
    if len(bpy.data.objects) != _state["count"]:
        _state["count"] = len(bpy.data.objects)
        _state["names"] = {o.name for o in bpy.data.objects if o.get(KIND) in PIN_TYPES}
    out = []
    for name in list(_state["names"]):
        ob = bpy.data.objects.get(name)
        if ob is None or ob.get(KIND) not in PIN_TYPES:
            _state["count"] = -1
            continue
        out.append(ob)
    return out


def _rescan(*_args):
    _state["count"] = -1


def helper_of(con):
    t = getattr(con, "target", None) if con.type == 'COPY_TRANSFORMS' else None
    return t if t is not None and t.get(KIND) in PIN_TYPES else None


def pin_type(con):
    """``uvPin`` / ``proximityPin`` for a kit pin constraint, else None (ui/channel_box INPUTS / AE tab type)."""
    h = helper_of(con)
    return h.get(KIND) if h is not None else None


def node_name(con):
    """The Maya node name of a kit pin constraint (``uvPin1``), else None."""
    h = helper_of(con)
    return h.get(NODE) if h is not None else None


def geometry_of(con):
    h = helper_of(con)
    g = h.get(GEOM) if h is not None else None
    return g if isinstance(g, bpy.types.Object) else None


def _parent_matrix(owner, depsgraph):
    if owner.parent is None:
        return Matrix.Identity(4)
    par = owner.parent.evaluated_get(depsgraph) if depsgraph is not None else owner.parent
    return par.matrix_world @ owner.matrix_parent_inverse


def _input_matrix(h):
    inp = h.get(INPUT)
    if isinstance(inp, bpy.types.Object):
        return np.array(inp.matrix_world, dtype=np.float64)
    flat = h.get(INPUT_MATRIX)
    if flat is not None and len(flat) == 16:
        return np.array(list(flat), dtype=np.float64).reshape(4, 4)
    return None


def offsets(h):
    """(Offset Translation, Offset Orientation, Envelope) of a proximityPin helper (Maya keyable attributes; Maintain
    offset on = 1 / 1, off = 0 / 0)."""
    on = 1.0 if h.get(OFFSET, True) else 0.0
    return (float(h.get(OFFSET_T, on)), float(h.get(OFFSET_O, on)), float(h.get(ENVELOPE, 1.0)))


def _rot_blend(a, b, f):
    """3x3 rotation slerp a -> b by f (the scale of ``a`` kept)."""
    qa = Matrix(a.tolist()).to_quaternion()
    qb = Matrix(b.tolist()).to_quaternion()
    m = qa.slerp(qb, f).to_matrix()
    sc = np.linalg.norm(a, axis=0)
    return np.array(m, dtype=np.float64) * sc[None, :]


def _orientation_base(inp, geo, loc, mode, axes):
    """Offset Orientation 0: Edge = the input turned by the minimal rotation taking its normal axis
    onto the rest normal n0; UV = the rest frame on the normal / tangent options."""
    if mode == "uv":
        return geo.frame(loc, axes, deformed=False, world=False)[:3, :3]
    na = axes[0]
    r = inp[:3, :3]
    ax = Vector(r[:, na % 3] * (1.0 if na < 3 else -1.0))
    n0 = Vector(geo.frame(loc, (0, 1), deformed=False, world=False)[:3, 0])
    if ax.length < 1e-12:
        return r
    turn = np.array(ax.normalized().rotation_difference(n0).to_matrix(), dtype=np.float64)
    return turn @ r


def pin_matrix(h, geo):
    """World matrix (numpy 4x4) the pin puts its output at, or None."""
    axes = tuple(h.get(AXES, (0, 1)))
    if h.get(KIND) == "uvPin":
        # UV Pin: the frame at the stored UV on the deformed mesh (the target's own rotation is dropped)
        uv = h.get(UV)
        loc = geo.at_uv(tuple(uv)) if uv is not None else None
        return geo.frame(loc, axes) if loc is not None else None
    # Proximity Pin: each evaluation the closest point to the input on the ORIGINAL mesh (moving pinInput moves the
    # pin); output = F1 · F0⁻¹ · wanted (Maya row vectors: M · F0⁻¹ · F1), F0 / F1 = rest / deformed frames (X, Y).
    mode = h.get(MODE, "edge")
    inp = _input_matrix(h)
    if inp is None:
        return None
    loc = geo.closest(inp[:3, 3], original=True)
    if loc is None:
        return None
    off_t, off_o, env = offsets(h)
    f0 = geo.frame(loc, (0, 1), deformed=False, world=False)
    f1 = geo.frame(loc, (0, 1))
    want = inp.copy()
    if off_t != 1.0:
        want[:3, 3] = off_t * inp[:3, 3] + (1.0 - off_t) * f0[:3, 3]      # 0 = on the surface
    if off_o != 1.0:
        base = _orientation_base(inp, geo, loc, mode, axes)
        want[:3, :3] = base if off_o == 0.0 else _rot_blend(base, inp[:3, :3], off_o)   # between 0 and 1
    out = f1 @ np.linalg.inv(f0) @ want
    if env != 1.0:
        # Envelope: rotation slerp(input, pinned, e), translation lerp (the input as the geometry carries it at rest)
        src = geo.mw @ inp
        res = np.identity(4)
        res[:3, :3] = _rot_blend(src[:3, :3], out[:3, :3], env)
        res[:3, 3] = (1.0 - env) * src[:3, 3] + env * out[:3, 3]
        out = res
    return out


def update(depsgraph=None):
    """Move every pin helper to its pin (no write when it is already there: the handler doesn't loop)."""
    if _state["busy"]:
        return
    hs = helpers()
    if not hs:
        return
    _state["busy"] = True
    try:
        if depsgraph is None:
            depsgraph = bpy.context.evaluated_depsgraph_get()
        geos = {}
        for h in hs:
            owner, geom = h.get(OWNER), h.get(GEOM)
            if not isinstance(owner, bpy.types.Object) or not isinstance(geom, bpy.types.Object):
                continue
            if geom.type != 'MESH':
                continue
            geo = geos.get(geom.name)
            if geo is None:
                geo = geos[geom.name] = Geo(geom, depsgraph)
            if not geo.ok:
                continue
            m = pin_matrix(h, geo)
            if m is None:
                continue
            new = Matrix(m.tolist()) @ _parent_matrix(owner, depsgraph).inverted_safe()
            old = h.matrix_world
            if max(abs(old[i][j] - new[i][j]) for i in range(4) for j in range(4)) > 1e-7 or h.parent is not None:
                h.parent = None
                h.matrix_world = new
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
    _rescan()


# --- creating pins ----------------------------------------------------------------------------------------------

def _maya_unique(base):
    """Maya naming of ``-n base``: ``base`` when free, else ``base1``, ``base2`` ..."""
    taken = {o.name for o in bpy.data.objects}
    if base not in taken:
        return base
    n = 1
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


def new_node(kind):
    """``<kind>N`` with N the lowest number no pin node / object uses (Maya: uvPin1, uvPin2 ...)."""
    used = {h.get(NODE) for h in helpers()} | {o.name for o in bpy.data.objects}
    n = 1
    while f"{kind}{n}" in used:
        n += 1
    return f"{kind}{n}"


def _link_like(ob, other, context):
    cols = list(getattr(other, "users_collection", ())) or [context.scene.collection]
    cols[0].objects.link(ob)


def _empty(context, name, like, display='PLAIN_AXES', size=None):
    ob = bpy.data.objects.new(_maya_unique(name), None)
    ob.empty_display_type = display
    ob.empty_display_size = units.maya_unit(context.scene) if size is None else size
    _link_like(ob, like, context)
    return ob


def _clear_channels(ob):
    """Maya clears the pinned transform: translate / rotate / shear 0, scale 1 (the pin drives the transform)."""
    ob.location = (0.0, 0.0, 0.0)
    ob.rotation_euler = (0.0, 0.0, 0.0)
    ob.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
    ob.rotation_axis_angle = (0.0, 0.0, 1.0, 0.0)
    ob.scale = (1.0, 1.0, 1.0)


def _pin_output(context, kind, node, i, owner, geom, props):
    """Helper empty + the Copy Transforms on ``owner`` (Maya: node output -> offsetParentMatrix)."""
    h = bpy.data.objects.new(f"{node}Output{i}", None)
    h.empty_display_size = 0.0
    h.hide_viewport = h.hide_render = h.hide_select = True
    h[KIND], h[NODE], h[OWNER], h[GEOM] = kind, node, owner, geom
    for k, v in props.items():
        h[k] = v
    _link_like(h, owner, context)
    _rescan()
    _clear_channels(owner)
    con = owner.constraints.new('COPY_TRANSFORMS')
    con.name = node
    con.target = h
    con.mix_mode = 'BEFORE_FULL'
    return h


def _axes(normal_axis, tangent_axis):
    na, ta = AXIS_ITEMS.index(normal_axis), AXIS_ITEMS.index(tangent_axis)
    if na % 3 == ta % 3:
        raise RuntimeError(MSG_AXIS)
    return [na, ta]


def _geometry_and_targets(context):
    """(geometry, transforms) in Maya selection order: the geometry = a selected mesh that isn't the active object
    (the first by name when there are several, operators/modify_maya.selection_order), the transforms = the rest."""
    from .modify_maya import selection_order
    obs = selection_order(context)
    lead = obs[-1] if obs and obs[-1] is context.view_layer.objects.active else None
    geom = next((o for o in obs if o is not lead and o.type == 'MESH'), None)
    if geom is None:
        return None, []
    return geom, [o for o in obs if o is not geom]


def _component_uvs(ob):
    """Maya's UVs of the selection on a mesh in edit mode: vertices -> their UV, faces -> mean corner UV, edges -> mid
    of the two vertices' UVs (the vertex UV = its first face corner)."""
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    if uvl is None:
        return []

    def vuv(v):
        for lp in v.link_loops:
            return tuple(lp[uvl].uv)
        return None
    out = []
    mode = bm.select_mode
    if 'VERT' in mode:
        out += [vuv(v) for v in bm.verts if v.select]
    elif 'EDGE' in mode:
        for e in bm.edges:
            if e.select:
                a, b = vuv(e.verts[0]), vuv(e.verts[1])
                if a and b:
                    out.append(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
    else:
        for f in bm.faces:
            if f.select:
                us = [tuple(lp[uvl].uv) for lp in f.loops]
                out.append((sum(u for u, _v in us) / len(us), sum(v for _u, v in us) / len(us)))
    return [u for u in out if u is not None]


def uv_pin(context, setup='TRANSFORMS', output='CURRENT', normal_axis="X", tangent_axis="Y"):
    """Maya UV Pin. Returns (node name, [pinned objects], [inherit warnings])."""
    axes = _axes(normal_axis, tangent_axis)
    if setup == 'COMPONENTS' and output == 'CURRENT':
        raise RuntimeError(MSG_OUTPUT_MODE)
    depsgraph = context.evaluated_depsgraph_get()
    if setup == 'COMPONENTS':
        geom = context.edit_object if context.mode == 'EDIT_MESH' else None
        if geom is None or geom.type != 'MESH':
            raise RuntimeError(MSG_GEOMETRY)
        uvs = _component_uvs(geom)
        bpy.ops.object.mode_set(mode='OBJECT')
        if not uvs:
            raise RuntimeError(MSG_NO_COMPONENTS)
        targets = [None] * len(uvs)
    else:
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        geom, targets = _geometry_and_targets(context)
        if geom is None:
            raise RuntimeError(MSG_GEOMETRY)
        if not targets:
            raise RuntimeError(HINT_UV)
        uvs = None
    geo = Geo(geom, depsgraph)
    if not geo.ok or geo.tuv is None:
        raise RuntimeError(f"{geom.name} has no UVs to pin to.")
    node = new_node("uvPin")
    pinned, inherit = [], []
    for i, target in enumerate(targets):
        if uvs is not None:
            uv = uvs[i]
        else:
            hit = geo.closest(np.array(target.matrix_world.translation, dtype=np.float64))
            if hit is None:
                continue
            uv = geo.uv_at(hit)
        if output != 'CURRENT':
            target = _empty(context, "pinOutput", geom, size=None if output == 'LOCATOR' else 0.0)
        else:
            inherit.append(target.name)          # Maya turns inheritsTransform off on every pinned transform
        _pin_output(context, "uvPin", node, i, target, geom, {UV: list(uv), AXES: axes, MODE: "uv"})
        pinned.append(target)
    update(depsgraph)
    context.view_layer.update()
    return node, pinned, inherit


def proximity_pin(context, setup='TRANSFORMS', output='CURRENT', input_='LOCATOR', maintain_offset=True,
                  mode='EDGE', normal_axis="X", tangent_axis="Y"):
    """Maya Proximity Pin. Returns (node name, [pinned objects], [pinInput objects], [inherit warnings])."""
    axes = _axes(normal_axis, tangent_axis)
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    geom, targets = _geometry_and_targets(context)
    if geom is None:
        raise RuntimeError(MSG_GEOMETRY)
    if input_ == 'CURRENT' and output == 'CURRENT':
        raise RuntimeError(MSG_IO)
    if setup == 'COMPONENTS':
        raise RuntimeError(MSG_NOT_IMPLEMENTED)
    if not targets:
        raise RuntimeError(HINT_PROX)
    depsgraph = context.evaluated_depsgraph_get()
    geo = Geo(geom, depsgraph)
    if not geo.ok:
        raise RuntimeError(MSG_GEOMETRY)
    node = new_node("proximityPin")
    gm = geom.matrix_world.inverted_safe()
    pinned, inputs, inherit = [], [], []
    for i, target in enumerate(targets):
        rel = gm @ target.matrix_world          # Maya matchTransform to the geometry: the input in geometry space
        on = 1.0 if maintain_offset else 0.0
        props = {OFFSET: bool(maintain_offset), OFFSET_T: on, OFFSET_O: on, ENVELOPE: 1.0, AXES: axes,
                 MODE: "uv" if mode == 'UV' else "edge"}
        if input_ == 'MATRIX':
            props[INPUT_MATRIX] = [x for row in rel for x in row]
        else:
            inp = _empty(context, "pinInput", geom, size=None if input_ == 'LOCATOR' else 0.0)
            inp.matrix_world = rel
            props[INPUT] = inp
            inputs.append(inp)
        if output != 'CURRENT':
            target = _empty(context, "pinOutput", geom, size=None if output == 'LOCATOR' else 0.0)
        else:
            inherit.append(target.name)          # Maya turns inheritsTransform off on every pinned transform
        _pin_output(context, "proximityPin", node, i, target, geom, props)
        pinned.append(target)
    update(depsgraph)
    context.view_layer.update()
    for o in inputs:
        o.select_set(True)                       # Maya selects the created nodes
    return node, pinned, inputs, inherit


_AXIS_ENUM = [(a, a, "") for a in AXIS_ITEMS]
_OUTPUTS = [('CURRENT', "Existing Transform", ""), ('NULL', "New Transform", ""), ('LOCATOR', "New Locator", "")]


@undo_steps.no_redo_panel
class ALLSET_OT_uv_pin(bpy.types.Operator):
    """Constrains one or more objects to the UVs of a deforming target object (Maya Constrain > UV Pin): select the
    geometry, then the transforms"""
    bl_idname = "allset.uv_pin"
    bl_label = "UV Pin"
    bl_options = {'REGISTER', 'UNDO'}

    setup: EnumProperty(name="Pin locations", items=[('COMPONENTS', "Components", ""), ('TRANSFORMS', "Transforms", "")],
                        default='TRANSFORMS', options={'SKIP_SAVE'})
    output: EnumProperty(name="Output", items=_OUTPUTS, default='CURRENT', options={'SKIP_SAVE'})
    normal_axis: EnumProperty(name="Normal axis", items=_AXIS_ENUM, default="X", options={'SKIP_SAVE'})
    tangent_axis: EnumProperty(name="Tangent axis", items=_AXIS_ENUM, default="Y", options={'SKIP_SAVE'})

    def execute(self, context):
        try:
            node, pinned, inherit = uv_pin(context, self.setup, self.output, self.normal_axis, self.tangent_axis)
        except RuntimeError as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        if inherit:
            self.report({'WARNING'}, MSG_INHERIT.format(inherit))
        if self.output != 'CURRENT':
            deformers._select_only(context, pinned, pinned[-1] if pinned else None)
        results.result(self, node)
        return {'FINISHED'}


@undo_steps.no_redo_panel
class ALLSET_OT_proximity_pin(bpy.types.Operator):
    """Keeps objects on a deforming surface at the spot nearest to each, optionally with their current offset (Maya
    Constrain > Proximity Pin): select the geometry, then the objects to constrain"""
    bl_idname = "allset.proximity_pin"
    bl_label = "Proximity Pin"
    bl_options = {'REGISTER', 'UNDO'}

    setup: EnumProperty(name="Setup mode", items=[('COMPONENTS', "Components", ""), ('TRANSFORMS', "Transforms", "")],
                        default='TRANSFORMS', options={'SKIP_SAVE'})
    output: EnumProperty(name="Output", items=_OUTPUTS, default='CURRENT', options={'SKIP_SAVE'})
    input: EnumProperty(name="Input", items=_OUTPUTS + [('MATRIX', "Matrix", "")], default='LOCATOR',
                        options={'SKIP_SAVE'})
    maintain_offset: BoolProperty(name="Maintain offset", default=True, options={'SKIP_SAVE'})
    mode: EnumProperty(name="Mode", items=[('EDGE', "Edge", ""), ('UV', "UV", "")], default='EDGE',
                       options={'SKIP_SAVE'})
    normal_axis: EnumProperty(name="Normal axis", items=_AXIS_ENUM, default="X", options={'SKIP_SAVE'})
    tangent_axis: EnumProperty(name="Tangent axis", items=_AXIS_ENUM, default="Y", options={'SKIP_SAVE'})

    def execute(self, context):
        try:
            node, pinned, _inputs, inherit = proximity_pin(
                context, self.setup, self.output, self.input, self.maintain_offset, self.mode, self.normal_axis,
                self.tangent_axis)
        except RuntimeError as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        if inherit:
            self.report({'WARNING'}, MSG_INHERIT.format(inherit))
        results.result(self, node)
        return {'FINISHED'}


# --- intermediate objects ------------------------------------------------------------------------------------

_SHAPED = {'MESH', 'CURVE', 'SURFACE', 'LATTICE'}


def is_intermediate(ob):
    """``ob`` stands for a Maya intermediate object: the kit's ``<shape>Orig`` display of a deformed object's
    original shape (made by Display Intermediate Objects)."""
    try:
        return isinstance(ob.get(INTERMEDIATE_OF), bpy.types.Object)
    except (ReferenceError, AttributeError):
        return False


def intermediates_of(ob):
    return [o for o in bpy.data.objects if is_intermediate(o) and o.get(INTERMEDIATE_OF) == ob]


def is_deformed(ob):
    """Maya gives ``ob`` an Orig shape: it has a deformer (history.is_deformer: kit deformers, skin, ...)."""
    if ob.type not in _SHAPED or ob.data is None:
        return False
    from . import history
    from . import display
    return any(history.is_deformer(md) and not display.is_preview(md) for md in ob.modifiers)


def _make_orig(context, ob):
    orig = bpy.data.objects.new(f"{ob.data.name}Orig", ob.data)
    orig[INTERMEDIATE_OF] = ob
    _link_like(orig, ob, context)
    orig.parent = ob
    orig.matrix_parent_inverse = Matrix.Identity(4)
    return orig


def display_intermediate(context):
    """Maya displayInterObjects 0. Returns the shown intermediate objects (selected)."""
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    sel = list(context.selected_objects)
    if not sel:
        raise RuntimeError(MSG_NO_DEFORMABLE)
    shown, already = [], 0
    for ob in sel:
        if is_intermediate(ob):
            already += 1
            continue
        if not is_deformed(ob):
            continue
        if intermediates_of(ob):
            already += 1
            continue
        shown.append(_make_orig(context, ob))
    if not shown:
        raise RuntimeError(MSG_ALREADY_ON if already else MSG_FOUND_NONE)
    context.view_layer.update()
    deformers._select_only(context, shown, shown[-1])
    return shown


def hide_intermediate(context):
    """Maya displayInterObjects 1. Returns (the deformed objects (selected), number of intermediate objects hidden)."""
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    sel = list(context.selected_objects)
    if not sel:
        raise RuntimeError(MSG_NO_DEFORMABLE)
    owners, hidden, already = [], 0, 0
    for ob in sel:
        owner = ob.get(INTERMEDIATE_OF) if is_intermediate(ob) else ob
        if owner is None or owner in owners:
            continue
        origs = intermediates_of(owner)
        if not origs:
            if is_deformed(owner):
                already += 1
            continue
        for o in origs:
            bpy.data.objects.remove(o, do_unlink=True)
            hidden += 1
        owners.append(owner)
    if not hidden:
        raise RuntimeError(MSG_ALREADY_OFF if already else MSG_FOUND_NONE)
    deformers._select_only(context, owners, owners[-1])
    return owners, hidden


@undo_steps.no_redo_panel
class ALLSET_OT_intermediate_objects(bpy.types.Operator):
    """Display / hide the original (undeformed) shape of the selected deformed objects (Maya Deform > Display /
    Hide Intermediate Objects)"""
    bl_idname = "allset.intermediate_objects"
    bl_label = "Intermediate Objects"
    bl_options = {'REGISTER', 'UNDO'}

    show: BoolProperty(name="Display", default=True, options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        return "Display intermediate objects" if props.show else "Hide intermediate objects"

    def execute(self, context):
        try:
            n = len(display_intermediate(context)) if self.show else hide_intermediate(context)[1]
        except RuntimeError as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        results.result(self, f"Toggled {'on' if self.show else 'off'} {n} objects.")
        return {'FINISHED'}


# --- wrap influences --------------------------------------------------------------------------------------------

def _influence_parts(ob, md):
    """[(Surface Deform modifier, its Base hook or None)] of wrap node ``md`` on ``ob``: md first, then the kit's
    extra influences ``<md>Influence<k>`` in stack order."""
    out = [(md, ob.modifiers.get(f"{md.name}Base"))]
    for m in ob.modifiers:
        if m.type == 'SURFACE_DEFORM' and m.name.startswith(f"{md.name}Influence") \
                and m.name[len(md.name) + 9:].isdigit():
            out.append((m, ob.modifiers.get(f"{m.name}Base")))
    return out


def _wraps(ob):
    return [m for m in ob.modifiers if deformers.base_of(m) == "wrap"]


def _weights(ob, group):
    vg = ob.vertex_groups.get(group) if group else None
    if vg is None:
        return {}
    out = {}
    for v in ob.data.vertices:
        for g in v.groups:
            if g.group == vg.index and g.weight > 0.0:
                out[v.index] = g.weight
    return out


def _distances(ob, idx, infl, depsgraph):
    """Distance from each rest point ``idx`` of ``ob`` (world) to the evaluated surface of ``infl`` (world)."""
    from mathutils.bvhtree import BVHTree
    ev = infl.evaluated_get(depsgraph)
    bvh = BVHTree.FromObject(ev, depsgraph)
    inv = ev.matrix_world.inverted_safe()
    mw = ob.matrix_world
    out = []
    for i in idx:
        p = mw @ ob.data.vertices[i].co
        hit = bvh.find_nearest(inv @ p)
        out.append(math.inf if hit is None or hit[0] is None else (ev.matrix_world @ hit[0] - p).length)
    return out


def _partition(context, ob, parts, weights):
    """Give each wrapped point (weights = Maya wrap weight) to the vertex group of its nearest influence."""
    depsgraph = context.evaluated_depsgraph_get()
    idx = sorted(weights)
    dist = [_distances(ob, idx, sd.target, depsgraph) for sd, _hk in parts]
    groups = [ob.vertex_groups.get(sd.vertex_group) for sd, _hk in parts]
    for k, vg in enumerate(groups):
        mine = [i for j, i in enumerate(idx) if min(range(len(parts)), key=lambda q: dist[q][j]) == k]
        others = [i for i in idx if i not in set(mine)]
        if others:
            vg.remove(others)
        for i in mine:
            vg.add([i], weights[i], 'REPLACE')


def _move_after(context, ob, names, after):
    """Put modifiers ``names`` (in order) right after index ``after``."""
    with context.temp_override(object=ob, active_object=ob):
        for k, name in enumerate(names):
            bpy.ops.object.modifier_move_to_index(modifier=name, index=after + 1 + k)


def add_wrap_influence(context, ob, md, infl):
    parts = _influence_parts(ob, md)
    if any(sd.target == infl for sd, _hk in parts):
        return None
    weights = {}
    for sd, _hk in parts:
        for i, w in _weights(ob, sd.vertex_group).items():
            weights[i] = weights.get(i, 0.0) + w
    k = 2
    while ob.modifiers.get(f"{md.name}Influence{k}") or ob.vertex_groups.get(f"{md.name}Influence{k}"):
        k += 1
    name = f"{md.name}Influence{k}"
    ob.vertex_groups.new(name=name)
    new = ob.modifiers.new(name, 'SURFACE_DEFORM')
    new.target = infl
    new.vertex_group = name
    _partition(context, ob, parts + [(new, None)], weights)
    last = max(ob.modifiers.find(m.name) for sd, hk in parts for m in (sd, hk) if m is not None)
    deformers._bind(ob, new)
    hk = deformers._base_hook(ob, name, infl, name)
    _move_after(context, ob, [new.name, hk.name], last)
    return new


def remove_wrap_influence(context, ob, md, infl):
    parts = _influence_parts(ob, md)
    hit = next(((sd, hk) for sd, hk in parts if sd.target == infl), None)
    if hit is None:
        return False
    weights = {}
    for sd, _hk in parts:
        for i, w in _weights(ob, sd.vertex_group).items():
            weights[i] = weights.get(i, 0.0) + w
    if len(parts) == 1:                        # the last influence: the wrap node goes (Maya keeps an empty wrap1)
        group = md.vertex_group
        for m in (md, hit[1]):
            if m is not None:
                ob.modifiers.remove(m)
        vg = ob.vertex_groups.get(group)
        if vg is not None:
            ob.vertex_groups.remove(vg)
        return True
    sd, hk = hit
    if sd == md:
        # the node's own influence goes: its first extra influence takes the node's modifier (target, bind, hook)
        extra, extra_hk = parts[1]
        md.target = extra.target
        main_hk = parts[0][1]
        if main_hk is not None and extra_hk is not None:
            main_hk.object = extra_hk.object
            main_hk.center = extra_hk.center
            main_hk.matrix_inverse = extra_hk.matrix_inverse
        sd, hk = extra, extra_hk
        parts = [(md, main_hk)] + parts[2:]
    else:
        parts = [p for p in parts if p[0] != sd]
    group = sd.vertex_group
    for m in (sd, hk):
        if m is not None:
            ob.modifiers.remove(m)
    vg = ob.vertex_groups.get(group)
    if vg is not None:
        ob.vertex_groups.remove(vg)
    _partition(context, ob, parts, weights)
    if hit[0] is md:
        _rebind(ob, md)
    return True


def _rebind(ob, md):
    """Bind ``md`` again to its (new) target: Blender's bind operator toggles, so unbind first."""
    if md.is_bound:
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.object.surfacedeform_bind(modifier=md.name)
    deformers._bind(ob, md)


def wrap_influence(context, add):
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    infl = context.view_layer.objects.active
    surfaces = [o for o in context.selected_objects if o is not infl]
    if infl is None or not infl.select_get() or not surfaces:
        raise RuntimeError(MSG_WRAP_SELECT)
    if infl.type not in {'MESH'}:
        raise RuntimeError(MSG_WRAP_INFLUENCE)
    done = []
    for ob in surfaces:
        wraps = _wraps(ob) if ob.type == 'MESH' else []
        if not wraps:
            raise RuntimeError(MSG_NO_WRAP.format(ob.name))
        for md in wraps:
            name = md.name
            if add:
                if add_wrap_influence(context, ob, md, infl) is not None:
                    done.append(name)
            elif remove_wrap_influence(context, ob, md, infl):
                done.append(name)
    infl.select_set(False)                     # Maya: the influence leaves the selection (select -tgl)
    context.view_layer.objects.active = surfaces[-1]
    context.view_layer.update()
    return done


@undo_steps.no_redo_panel
class ALLSET_OT_wrap_influence(bpy.types.Operator):
    """Add / remove the last selected object as an influence of the selected surfaces' wrap deformers (Maya Deform >
    Wrap > Add Influence / Remove Influence)"""
    bl_idname = "allset.wrap_influence"
    bl_label = "Wrap Influence"
    bl_options = {'REGISTER', 'UNDO'}

    action: EnumProperty(items=[('ADD', "Add Influence", ""), ('REMOVE', "Remove Influence", "")], default='ADD',
                         options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        return ("Let this object drive the wrap deformation too" if props.action == 'ADD'
                else "Remove wrap influence")

    def execute(self, context):
        try:
            done = wrap_influence(context, self.action == 'ADD')
        except RuntimeError as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        results.result(self, " ".join(done))
        return {'FINISHED'}


classes = (ALLSET_OT_uv_pin, ALLSET_OT_proximity_pin, ALLSET_OT_intermediate_objects, ALLSET_OT_wrap_influence)


# --- Maya option windows (UV Pin / Proximity Pin Options) — appended by operators/option_windows._extend ------------

def _windows():
    from .option_windows import F, Window
    axes = list(AXIS_ITEMS)
    outputs = ("Existing Transform", "New Transform", "New Locator")
    out_key = {"Existing Transform": 'CURRENT', "New Transform": 'NULL', "New Locator": 'LOCATOR', "Matrix": 'MATRIX'}

    def run_uv(context, v):
        return bpy.ops.allset.uv_pin('EXEC_DEFAULT', setup=v["setup"].upper(), output=out_key[v["output"]],
                                     normal_axis=v["normal_axis"], tangent_axis=v["tangent_axis"])

    def run_prox(context, v):
        return bpy.ops.allset.proximity_pin(
            'EXEC_DEFAULT', setup=v["setup"].upper(), output=out_key[v["output"]], input=out_key[v["input"]],
            maintain_offset=v["maintain_offset"], mode=v["mode"].upper(), normal_axis=v["normal_axis"],
            tangent_axis=v["tangent_axis"])
    return [
        # Maya's UV Pin Options: factory values and labels
        Window("uv_pin", "UV Pin Options", "Add", ("allset.uv_pin", {}),
               [F("setup", "Pin locations", "enum", "Transforms", items=("Components", "Transforms"),
                  heading="Connections"),
                F("output", "Output", "enum", "Existing Transform", items=outputs),
                F("normal_axis", "Normal axis", "enum", "X", items=axes, heading="Coordinate System"),
                F("tangent_axis", "Tangent axis", "enum", "Y", items=axes)],
               run_uv, paths=("Constrain/UV Pin",),
               missing=("Output: Matrix", "UV set name (the active UV map)", "Normalize isoparms (NURBS)")),
        # Maya's Proximity Pin Options
        Window("proximity_pin", "Proximity Pin Options", "Add", ("allset.proximity_pin", {}),
               [F("setup", "Setup mode", "enum", "Transforms", items=("Components", "Transforms"),
                  heading="Connections"),
                F("output", "Output", "enum", "Existing Transform", items=outputs),
                F("input", "Input", "enum", "New Locator", items=outputs + ("Matrix",)),
                F("maintain_offset", "", "bool", True, text="Maintain offset"),
                F("mode", "Mode", "enum", "Edge", items=("Edge", "UV"), heading="Coordinate System"),
                F("normal_axis", "Normal axis", "enum", "X", items=axes),
                F("tangent_axis", "Tangent axis", "enum", "Y", items=axes)],
               run_prox, paths=("Constrain/Proximity Pin",),
               missing=("Output: Matrix", "UV set name (the active UV map)")),
    ]


WINDOWS = []          # filled by windows() when option_windows._extend asks (avoids an import cycle at load)


def windows():
    if not WINDOWS:
        WINDOWS.extend(_windows())
    return WINDOWS
