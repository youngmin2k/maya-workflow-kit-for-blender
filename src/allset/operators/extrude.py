# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya polyExtrudeFace and the "last kit modeling operation" history.

Maya 2022: Edit Mesh > Extrude = a zero-length extrusion
(Thickness 0, Local Translate Z 0, Offset 0, Divisions 1, Keep Faces Together on); Local Translate Z moves each face along
its normal (a vertex shared by several extruded faces moves by the average), Thickness offsets every face plane by the
same distance (shell), Offset shrinks the extruded faces in their plane (no new faces), Divisions = rings along the sides.

Blender keeps no history in edit mode. The kit remembers the last extrusion per object:
its node name (``polyExtrudeFaceN``), the mesh before it and the values; changing a value rebuilds the extrusion from that
mesh (``allset.extrude_edit``), so it is one undo step and the Adjust Last Operation panel shows the same Maya names.
The record is valid only while the mesh equals one of the states the kit made (Ctrl+Z / Ctrl+Shift+Z included).

#70, #16: the record is one ``Spec`` per Maya node - polyExtrudeEdge / polyExtrudeVertex here (edges /
vertices extrude at once, no drag) and polyBevel3 in operators/bevel_maya.py - each with its Maya fields, edit
operator and arrow field.

The extrude manipulator's other handles drive polyExtrudeFace Local Translate X / Y and Local
Scale X / Y / Z (Maya 2022, data in tests/test_step151_extrude_manip.py): every extruded face has its own frame
- Z = its normal, X = Maya world X (``localDirection`` 1 0 0, in world space) projected into the face plane
(Maya world Z = Blender -Y when the face faces X), Y = Z x X; Local Translate moves the face along X / Y, Local Scale scales it about its vertex mean along its X / Y / Z
(Z does nothing on a flat face); a vertex shared by several extruded faces takes the mean of their moves (Keep Faces
Together), the rings between take the level fraction, and Offset adds after the scale.
"""

import bmesh
import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty
from mathutils import Vector

from .. import undo_steps
from . import units

NODE = "polyExtrudeFace"
COUNTER = "allset_polyExtrudeFace"     # scene ID property: Maya numbers nodes per scene
FIELDS = ("thickness", "local_translate_z", "offset", "divisions", "keep_faces_together")
LABELS = {"thickness": "Thickness", "local_translate_z": "Local Translate Z", "offset": "Offset",
          "divisions": "Divisions", "keep_faces_together": "Keep Faces Together"}
DEFAULTS = {"thickness": 0.0, "local_translate_z": 0.0, "offset": 0.0, "divisions": 1, "keep_faces_together": True}
# polyExtrudeFace attributes only the manipulator handles set: not In-View / Channel Box rows
MANIP_FIELDS = ("local_translate_x", "local_translate_y", "local_scale_x", "local_scale_y", "local_scale_z")
MANIP_LABELS = {"local_translate_x": "Local Translate X", "local_translate_y": "Local Translate Y",
                "local_scale_x": "Local Scale X", "local_scale_y": "Local Scale Y", "local_scale_z": "Local Scale Z"}
MANIP_DEFAULTS = {"local_translate_x": 0.0, "local_translate_y": 0.0, "local_scale_x": 1.0, "local_scale_y": 1.0,
                  "local_scale_z": 1.0}
DEFAULTS.update(MANIP_DEFAULTS)
# Maya world X / Z in Blender world (Y-up -> Z-up: Maya Z = Blender -Y)
WORLD_X, MAYA_Z = Vector((1.0, 0.0, 0.0)), Vector((0.0, -1.0, 0.0))
NOTICE = "Edit-mode operations have no history in Blender: only the last one can be changed here."


class Spec:
    """One kind of Maya modeling node the kit records (edge / vertex extrusion, bevel).

    ``hidden`` = values ``build`` reads that show no row; ``with_object``: ``build`` also gets ``ob=``.
    ``kinds`` = Channel Box text kind per field (cb_entry: "NONE" float, "INT", "BOOL"); ``arrow`` = the field the
    In-View manipulator arrow drags (None: no arrow); ``edit_op`` = the operator that rebuilds the node with new
    values (one undo step); ``build(bm, params, unit)`` (not FACE) -> the vertices to track."""

    def __init__(self, kind, node, fields, labels, defaults, kinds, arrow, edit_op, build=None, node_type=None,
                 manip=(), in_view=True, object_check=None, pre_uv=False, hidden=(), with_object=False,
                 choices=None, enabled=None, atomic=False, preview=None):
        self.choices = choices or {}
        self.enabled = enabled
        self.atomic = atomic
        self.preview = preview
        self.hidden = tuple(hidden)            # values build reads that have no row (an option-window setting)
        self.with_object = with_object         # build(bm, params, unit, ob=...) also gets the object
        self.pre_uv = pre_uv                   # a rerun on the same mesh also needs the same UVs (UV projections)
        self.in_view = in_view                 # the In-View Editor shows it (not a UV projection)
        self.object_check = object_check       # (ob, rec) -> the object-mode mesh is still the node's result
        self.node_type = node_type or node     # Maya node type (the AE history tab title)
        self.kind, self.node, self.fields, self.labels = kind, node, tuple(fields), dict(labels)
        self.manip = tuple(manip)              # values only the manipulator sets: not shown as rows
        self.defaults, self.kinds, self.arrow, self.edit_op, self.build = dict(defaults), dict(kinds), arrow, \
            edit_op, build

    @property
    def all_fields(self):
        return self.fields + self.manip

    @property
    def counter(self):
        return "allset_" + self.node


SPECS = {}


class BuildResult(list):
    """Tracked vertices with optional backend data for coordinate-only previews."""
    def __init__(self, vertices, preview_data):
        super().__init__(vertices)
        self.preview_data = preview_data


def add_spec(spec):
    SPECS[spec.kind] = spec
    return spec


FACE = add_spec(Spec('FACE', NODE, FIELDS, dict(LABELS, **MANIP_LABELS), DEFAULTS,
                     dict({"thickness": "NONE", "local_translate_z": "NONE", "offset": "NONE", "divisions": "INT",
                           "keep_faces_together": "BOOL"}, **{k: "NONE" for k in MANIP_FIELDS}),
                     "local_translate_z", "extrude_edit", manip=MANIP_FIELDS))


# --- geometry (bmesh only) -------------------------------------------------------------------------

def _thickness_dir(normals):
    """Displacement that moves every face plane in ``normals`` by 1 (Maya Thickness, a shell)."""
    if len(normals) == 1:
        return normals[0].copy()
    if len(normals) == 2:
        n1, n2 = normals
        return (n1 + n2) / max(1.0 + n1.dot(n2), 1e-3)
    m = sum(normals, Vector()).normalized()
    return m / max(sum(m.dot(n) for n in normals) / len(normals), 0.1)


def _inward(face, edge):
    """Unit vector in ``face``'s plane, perpendicular to ``edge``, pointing into the face."""
    for loop in face.loops:
        if loop.edge is edge:
            t = (loop.link_loop_next.vert.co - loop.vert.co).normalized()
            return face.normal.cross(t).normalized()
    return Vector()


def _offset_dir(perps):
    """Offset of a boundary vertex: each of its two boundary edges moves 1 into the face."""
    if len(perps) == 2:
        a, b = perps
        return (a + b) / max(1.0 + a.dot(b), 1e-3)
    if perps:
        return sum(perps, Vector()) / len(perps)
    return Vector()


def face_axes(normal, direction=WORLD_X, fallback=MAYA_Z):
    """Maya's local X / Y of an extruded face (polyExtrudeFace ``localDirection`` 1 0 0): the
    direction projected into the face plane, ``fallback`` (Maya world Z) when the face looks along it; Y = Z x X."""
    n = normal.normalized() if normal.length > 1e-12 else Vector((0.0, 0.0, 1.0))
    for d in (direction, fallback, Vector((0.0, 1.0, 0.0))):
        x = d - n * d.dot(n)
        if x.length > 1e-6:
            x = x.normalized()
            return x, n.cross(x).normalized()
    return Vector((1.0, 0.0, 0.0)), Vector((0.0, 1.0, 0.0))


def _face_parts(f, v, direction, fallback):
    """(X, Y, SX, SY, SZ) of vertex ``v`` in face ``f``: the face's local X / Y and the move of ``v`` per unit of
    Local Scale - 1 along X / Y / Z about the face's vertex mean."""
    n = f.normal.normalized()
    x, y = face_axes(n, direction, fallback)
    r = v.co - f.calc_center_median()
    return x, y, x * r.dot(x), y * r.dot(y), n * r.dot(n)


def _mean(vectors):
    return sum(vectors, Vector()) / len(vectors)


def _vectors(faces, together, direction=WORLD_X, fallback=MAYA_Z):
    """{key: (base co, T, L, O, X, Y, SX, SY, SZ)} per extruded vertex (key = vertex index, or (face index, vertex
    index) for faces extruded one by one), from the faces before the extrusion."""
    sel = set(faces)
    out = {}
    if together:
        for f in faces:
            for v in f.verts:
                if v.index in out:
                    continue
                vf = [g for g in v.link_faces if g in sel]
                normals = [g.normal.copy() for g in vf]
                perps = []
                for e in v.link_edges:
                    ef = [g for g in e.link_faces if g in sel]
                    if len(ef) == 1:              # a border edge of the extruded region
                        perps.append(_inward(ef[0], e))
                parts = [_face_parts(g, v, direction, fallback) for g in vf]
                out[v.index] = (v.co.copy(), _thickness_dir(normals),
                                sum(normals, Vector()) / len(normals), _offset_dir(perps),
                                *(_mean([p[i] for p in parts]) for i in range(5)))
    else:
        for f in faces:
            n = f.normal.copy()
            for v in f.verts:
                perps = [_inward(f, e) for e in v.link_edges if f in e.link_faces]
                out[(f.index, v.index)] = (v.co.copy(), n.copy(), n.copy(), _offset_dir(perps),
                                           *_face_parts(f, v, direction, fallback))
    return out


def _key(co):
    return tuple(round(c, 6) for c in co)


def _caps(ret_geom):
    verts = {g for g in ret_geom if isinstance(g, bmesh.types.BMVert)}
    return [g for g in ret_geom if isinstance(g, bmesh.types.BMFace) and all(v in verts for v in g.verts)]


def _closed(faces):
    """No edge of ``faces`` borders an unextruded face or the mesh border: the faces are whole closed shells."""
    sel = set(faces)
    return bool(faces) and all(sum(1 for g in e.link_faces if g in sel) == 2 for f in faces for e in f.edges)


def _region(bm, faces):
    edges = {e for f in faces for e in f.edges}
    closed = _closed(faces)
    ret = bmesh.ops.extrude_face_region(bm, geom=list(faces) + list(edges))
    caps = _caps(ret["geom"])
    gone = [f for f in faces if f.is_valid]
    if gone and closed:
        # whole closed shells: Maya keeps the old faces, turned inside out;
        # bmesh has already turned them (Blender 4.5)
        pass
    elif gone:   # an isolated region keeps its faces in bmesh; Maya's extrusion has no bottom
        bmesh.ops.delete(bm, geom=gone, context='FACES_ONLY')
    return caps


def extrude_topology(bm, faces, divisions=1, together=True, direction=WORLD_X, fallback=MAYA_Z):
    """Zero-length extrusion of ``faces``, ``divisions`` times. Returns (caps, levels, vectors) where
    levels[k-1] maps a vertex key to the level-k vertex (level ``divisions`` = the caps)."""
    bm.verts.index_update()
    bm.faces.index_update()
    faces = [f for f in faces if f.is_valid]
    vectors = _vectors(faces, together, direction, fallback)
    if together:
        by_co = {_key(co): k for k, (co, *_r) in vectors.items()}
    else:
        by_co = {}
        for (fi, vi), (co, *_r) in vectors.items():
            by_co.setdefault(fi, {})[_key(co)] = (fi, vi)
    order = [f.index for f in faces]
    levels = []
    caps = faces
    if together and _closed(faces):
        divisions = 1        # Maya extrudes whole closed shells once whatever Divisions says
    for level in range(max(1, divisions)):
        if level == 0 and not together:
            caps = bmesh.ops.extrude_discrete_faces(bm, faces=caps)["faces"]
            gone = [f for f in faces if f.is_valid]
            if gone:
                bmesh.ops.delete(bm, geom=gone, context='FACES_ONLY')
        else:
            caps = _region(bm, caps)
        found = {}
        if together:
            for f in caps:
                for v in f.verts:
                    k = by_co.get(_key(v.co))
                    if k is not None:
                        found[k] = v
        else:
            # extrude_discrete_faces / later regions keep the face order; match vertices by position per face
            if level == 0:
                caps_by_face = dict(zip(order, caps))
            else:      # the next caps sit where the previous ones were
                caps_by_face = {fi: _match_face(caps, by_co[fi]) for fi in order}
            for fi, cap in caps_by_face.items():
                if cap is None:
                    continue
                for v in cap.verts:
                    k = by_co[fi].get(_key(v.co))
                    if k is not None:
                        found[k] = v
        levels.append(found)
    return caps, levels, vectors


def _match_face(caps, keys):
    want = set(keys)
    return next((c for c in caps if {_key(v.co) for v in c.verts} == want), None)


def moved_vertices(levels, vectors, unit=1.0):
    """[(vertex, P0, T, L, O, X, Y, SX, SY, SZ)] with the level fraction folded into every vector and the Maya unit
    into the length ones (T, L, O, X, Y; the scale moves SX / SY / SZ are already mesh lengths)."""
    n = len(levels)
    out = []
    for k, found in enumerate(levels, 1):
        frac = k / n
        f = frac * unit
        for key, v in found.items():
            co, t, l, o, x, y, sx, sy, sz = vectors[key]
            out.append((v, co.copy(), t * f, l * f, o * f, x * f, y * f, sx * frac, sy * frac, sz * frac))
    return out


def position(p0, vecs, params):
    """Where a moved vertex goes for ``params`` (vecs = T, L, O, X, Y, SX, SY, SZ of ``moved_vertices``)."""
    t, l, o, x, y, sx, sy, sz = vecs
    g = params.get
    return (p0 + t * g("thickness", 0.0) + l * g("local_translate_z", 0.0) + o * g("offset", 0.0)
            + x * g("local_translate_x", 0.0) + y * g("local_translate_y", 0.0)
            + sx * (g("local_scale_x", 1.0) - 1.0) + sy * (g("local_scale_y", 1.0) - 1.0)
            + sz * (g("local_scale_z", 1.0) - 1.0))


def place(moved, thickness=0.0, ltz=0.0, offset=0.0, **manip):
    params = dict(manip, thickness=thickness, local_translate_z=ltz, offset=offset)
    for v, p0, *vecs in moved:
        v.co = position(p0, vecs, params)


def extrude(bm, faces, thickness=0.0, local_translate_z=0.0, offset=0.0, divisions=1, keep_faces_together=True,
            unit=1.0, direction=WORLD_X, fallback=MAYA_Z, **manip):
    """Maya polyExtrudeFace on ``faces`` (bmesh). Returns (caps, moved); the caps end up selected. ``manip`` =
    Local Translate X / Y and Local Scale X / Y / Z (MANIP_FIELDS); ``direction`` / ``fallback`` = world X / Z
    in mesh space (the faces' local X)."""
    bm.faces.index_update()
    picked = sorted({f.index for f in faces if f.is_valid})
    plan = maya_plan(bm, picked, divisions, keep_faces_together)
    src = bm.verts.layers.int.new(".allset_extrude_src")     # added before elements are collected again
    for v in bm.verts:
        v[src] = v.index + 1
    bm.faces.ensure_lookup_table()
    faces = [bm.faces[i] for i in picked]
    caps, levels, vectors = extrude_topology(bm, faces, divisions, keep_faces_together, direction, fallback)
    # an inner vertex of a middle level is gone once the next level is extruded (Maya has only the cap's)
    levels = [{key: v for key, v in found.items() if v.is_valid} for found in levels]
    moved = moved_vertices(levels, vectors, unit)
    place(moved, thickness, local_translate_z, offset, **manip)
    for f in bm.faces:
        f.select = False
    for e in bm.edges:
        e.select = False
    for v in bm.verts:
        v.select = False
    for f in caps:
        f.select_set(True)
    caps, moved = renumber(bm, plan, levels, src, caps, moved)
    bm.verts.index_update()
    bm.faces.index_update()
    cap_ids = [f.index for f in caps]
    moved_ids = [(v.index, rest) for v, *rest in moved]
    bm.verts.layers.int.remove(src)     # removing a layer invalidates element references too
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    caps = [bm.faces[i] for i in cap_ids]
    moved = [(bm.verts[i], *rest) for i, rest in moved_ids]
    bm.select_flush_mode()
    bm.normal_update()
    return caps, moved


# --- Maya's numbering of the result (#149) ---------------------------------------------------------------
# polyExtrudeFacet (Maya 2026): vertices, edges and faces by index, with a border and for whole closed
# shells. The mesh's edge index is taken as Maya's edge id: kit
# primitives (polyCube / polyCylinder) and kit extrusions keep it so (bevel_maya.maya_edge_ids).

def maya_plan(bm, picked, divisions=1, together=True):
    """What Maya's polyExtrudeFacet of faces ``picked`` (indices) leaves, in Maya's order, as descriptors:
    ("o", i) = old vertex i, ("n", key, j) = the new vertex of ``key`` at level j (key = old vertex index, or
    (face index, vertex index) for faces apart; j = 0 for the one new vertex of an inner vertex).
    Returns {"verts", "edges", "faces", "div"} or None (no faces)."""
    bm.verts.index_update()
    bm.edges.index_update()
    bm.faces.index_update()
    sel = sorted(set(picked))
    if not sel:
        return None
    F = [[v.index for v in f.verts] for f in bm.faces]
    E = [(e.verts[0].index, e.verts[1].index) for e in bm.edges]
    eid = {frozenset(p): i for i, p in enumerate(E)}
    efaces = {}
    for fi, f in enumerate(F):
        for k in range(len(f)):
            efaces.setdefault(frozenset((f[k], f[(k + 1) % len(f)])), []).append(fi)

    def corner_edges(fi):
        f = F[fi]
        return [(f[k], f[(k + 1) % len(f)]) for k in range(len(f))]
    div = max(1, int(divisions))
    whole = set(sel)
    closed = together and all(len([x for x in efaces[frozenset(c)] if x in whole]) == 2
                              for fi in sel for c in corner_edges(fi))
    if closed:
        div = 1
    groups = [sel] if together else [[fi] for fi in sel]
    new_verts, new_edges, side_faces, removed, gone = [], [], [], set(), set()
    out_faces = [[("o", v) for v in f] for f in F]
    for grp in groups:
        g = set(grp)

        def border(key):
            return len([x for x in efaces[key] if x in g]) == 1
        bverts = set()
        for fi in grp:
            for c in corner_edges(fi):
                if border(frozenset(c)):
                    bverts |= set(c)
        chain, done = {}, set()

        def tag(x):
            return x if together else (grp[0], x)

        def lev(x, j):
            if j == 0:
                return ("o", x)
            c = chain[x]
            return c[j - 1] if len(c) > 1 else c[0]
        for fi in grp:
            for a, b in corner_edges(fi):
                key = frozenset((a, b))
                v0, v1 = E[eid[key]]
                for x in (v0, v1):          # new vertices in the order the walk meets them, edge ends in edge order
                    if x in chain:
                        continue
                    if x in bverts:         # a chain of Divisions vertices up from x
                        chain[x] = [("n", tag(x), j) for j in range(1, div + 1)]
                        new_verts += chain[x]
                        new_edges += list(zip([("o", x)] + chain[x][:-1], chain[x]))
                    else:                   # an inner (or closed-shell) vertex: one new vertex, the old one goes
                        chain[x] = [("n", tag(x), 0)]
                        new_verts.append(chain[x][0])
                        if not closed:
                            gone.add(x)
                if key not in done:
                    done.add(key)
                    if border(key):
                        new_edges += [(lev(v0, j), lev(v1, j)) for j in range(1, div + 1)]
                    else:
                        if not closed:
                            removed.add(eid[key])
                        new_edges.append((lev(v0, div), lev(v1, div)))
                if border(key):
                    side_faces += [[lev(a, j), lev(b, j), lev(b, j + 1), lev(a, j + 1)] for j in range(div)]
        for fi in grp:
            out_faces[fi] = [lev(v, div) for v in F[fi]]
    if closed:
        side_faces = [[("o", F[fi][0])] + [("o", v) for v in reversed(F[fi][1:])] for fi in sel]
    return {"verts": [("o", v) for v in range(len(bm.verts)) if v not in gone] + new_verts,
            "edges": [(("o", p[0]), ("o", p[1])) for i, p in enumerate(E) if i not in removed] + new_edges,
            "faces": out_faces + side_faces, "div": div}


def renumber(bm, plan, levels, src, caps, moved):
    """Sort the extruded mesh's vertices, edges and faces into ``plan``'s (Maya's) order; caps / moved come back as
    fresh references (a bmesh sort moves the data under existing ones). Left as it is when the kit's result doesn't
    match the plan element for element."""
    if plan is None:
        return caps, moved
    elem, newer = {}, set()
    for j, found in enumerate(levels, 1):
        for key, v in found.items():
            if v.is_valid:
                elem[("n", key, j)] = v
                newer.add(v)
    if len(levels) == plan["div"]:
        for key, v in levels[-1].items():      # inner vertices: the cap level's
            if v.is_valid:
                elem.setdefault(("n", key, 0), v)
    for v in bm.verts:
        if v not in newer:
            elem[("o", v[src] - 1)] = v
    try:
        vrank = {elem[d]: i for i, d in enumerate(plan["verts"])}
        edge_of = {frozenset(e.verts): e for e in bm.edges}
        face_of = {frozenset(f.verts): f for f in bm.faces}
        erank = {edge_of[frozenset((elem[a], elem[b]))]: i for i, (a, b) in enumerate(plan["edges"])}
        frank = {face_of[frozenset(elem[d] for d in f)]: i for i, f in enumerate(plan["faces"])}
    except KeyError:
        return caps, moved
    if not (len(vrank) == len(bm.verts) == len(plan["verts"]) and len(erank) == len(bm.edges) == len(plan["edges"])
            and len(frank) == len(bm.faces) == len(plan["faces"])):
        return caps, moved
    cap_ids = [frank[f] for f in caps]
    moved_ids = [(vrank[v], rest) for v, *rest in moved]
    bm.verts.sort(key=lambda v: vrank[v])
    bm.edges.sort(key=lambda e: erank[e])
    bm.faces.sort(key=lambda f: frank[f])
    bm.verts.index_update()
    bm.edges.index_update()
    bm.faces.index_update()
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    return [bm.faces[i] for i in cap_ids], [(bm.verts[i], *rest) for i, rest in moved_ids]


# --- polyExtrudeEdge / polyExtrudeVertex ------------

def deselect_all(bm):
    for seq in (bm.faces, bm.edges, bm.verts):
        for el in seq:
            el.select = False


def _unit_or(vec, fallback):
    return vec.normalized() if vec.length > 1e-9 else Vector(fallback)


def edge_frame(e):
    """Maya's local frame of an extruded edge (a -> b = the edge's vertex order): X along the edge, Z = mean of the
    adjacent face normals (Local Translate Z / Thickness), Y = Z x X (Offset)."""
    a, b = e.verts
    x = _unit_or(b.co - a.co, (1.0, 0.0, 0.0))
    z = _unit_or(sum((f.normal for f in e.link_faces), Vector()), (0.0, 0.0, 1.0))
    y = _unit_or(z.cross(x), (0.0, 1.0, 0.0))
    return x, y, z


def extrude_edges(bm, edges, thickness=0.0, local_translate_z=0.0, offset=0.0, divisions=1, unit=1.0, **_unused):
    """Maya polyExtrudeEdge (Keep Faces Together off, the default for edges in Maya): every edge alone gets ``divisions``
    quads ``(a, b, b', a')``; the new edge moves by Z * (Thickness + Local Translate Z) + Y * Offset (Maya units).
    The outer edges end up selected. Returns the new vertices."""
    bm.normal_update()
    edges = [e for e in edges if e.is_valid]
    k = max(1, int(divisions))
    plan = []
    for e in edges:
        _x, y, z = edge_frame(e)
        plan.append((e.verts[0], e.verts[1], (z * (thickness + local_translate_z) + y * offset) * unit,
                     e.link_faces[0] if e.link_faces else None))
    new, outer = [], []
    for a, b, d, example in plan:
        pa, pb = a, b
        for j in range(1, k + 1):
            na = bm.verts.new(a.co + d * (j / k))
            nb = bm.verts.new(b.co + d * (j / k))
            bm.faces.new((pa, pb, nb, na), example)
            new += [na, nb]
            pa, pb = na, nb
        outer.append(bm.edges.get((pa, pb)))
    deselect_all(bm)
    for e in outer:
        if e is not None:
            e.select_set(True)
    bm.select_flush_mode()
    bm.normal_update()
    return new


def _split_edges_at(bm, verts, width):
    """Split every edge of ``verts`` at ``width`` x its length from the vertex (Maya width = a fraction of each
    edge, on a 4 x 1 x 2 box). Returns {vertex: [base vertices]}."""
    vset = set(verts)
    base = {v: [] for v in verts}
    edges = sorted({e for v in verts for e in v.link_edges}, key=lambda e: e.index)
    plan = []
    for e in edges:
        a, b = e.verts
        plan.append((e, a, b, {x: x.co + (e.other_vert(x).co - x.co) * width for x in (a, b) if x in vset}))
    for e, a, b, targets in plan:
        cur = e
        if a in targets:
            _ne, nv = bmesh.utils.edge_split(cur, a, 0.5)
            nv.co = targets[a]
            base[a].append(nv)
            cur = bm.edges.get((nv, b))
        if b in targets and cur is not None:
            _ne, nv = bmesh.utils.edge_split(cur, b, 0.5)
            nv.co = targets[b]
            base[b].append(nv)
    return base


def _cut_corner(bm, v):
    """Cut every face around ``v`` between its two neighbours: ``v`` keeps only triangles (Maya's cone)."""
    for f in list(v.link_faces):
        if len(f.verts) <= 3:
            continue
        loop = next(lp for lp in f.loops if lp.vert is v)
        p, q = loop.link_loop_prev.vert, loop.link_loop_next.vert
        if bm.edges.get((p, q)) is None:
            bmesh.utils.face_split(f, p, q)


def _rings(bm, v, k):
    """``k`` - 1 rings on the cone of ``v`` (Maya divisions: rings at j/k from the base ring to the tip)."""
    tris = [f for f in v.link_faces if len(f.verts) == 3]
    ring = {}

    def at(b, j):
        if j == 0:
            return b
        if j == k:
            return v
        key = (b, j)
        if key not in ring:
            ring[key] = bm.verts.new(b.co + (v.co - b.co) * (j / k))
        return ring[key]

    rebuild = []
    for f in tris:
        loop = next(lp for lp in f.loops if lp.vert is v)
        rebuild.append((loop.link_loop_next.vert, loop.link_loop_next.link_loop_next.vert, f))
    spokes = list(v.link_edges)
    for p, q, f in rebuild:
        for j in range(k - 1):
            bm.faces.new((at(p, j), at(q, j), at(q, j + 1), at(p, j + 1)), f)
        bm.faces.new((v, at(p, k - 1), at(q, k - 1)), f)
    bmesh.ops.delete(bm, geom=[f for _p, _q, f in rebuild], context='FACES_ONLY')
    bmesh.ops.delete(bm, geom=[e for e in spokes if e.is_valid and not e.link_faces], context='EDGES')
    return list(ring.values())


def extrude_vertices(bm, verts, width=0.5, length=1.0, divisions=1, unit=1.0, **_unused):
    """Maya polyExtrudeVertex: the vertex becomes the tip of a cone, ``length`` (Maya units) along the mean normal
    of its faces; the base ring sits at ``width`` x each edge from it; ``divisions`` rings in between. The tip
    vertices end up selected. Returns the new / moved vertices."""
    bm.normal_update()
    verts = [v for v in verts if v.is_valid and v.link_faces]
    tips = {v: v.co + _unit_or(sum((f.normal for f in v.link_faces), Vector()), (0.0, 0.0, 1.0)) * (length * unit)
            for v in verts}
    base = _split_edges_at(bm, verts, width)
    k = max(1, int(divisions))
    out = []
    for v in verts:
        _cut_corner(bm, v)
    for v in verts:
        v.co = tips[v]
        out.append(v)
        out += base[v]
        if k > 1:
            out += _rings(bm, v, k)
    deselect_all(bm)
    for v in verts:
        v.select_set(True)
    bm.select_flush_mode()
    bm.normal_update()
    return out


def _build_edges(bm, params, unit):
    return extrude_edges(bm, [e for e in bm.edges if e.select], unit=unit, **params)


def _build_vertices(bm, params, unit):
    return extrude_vertices(bm, [v for v in bm.verts if v.select], unit=unit, **params)


EDGE = add_spec(Spec('EDGE', "polyExtrudeEdge", ("thickness", "local_translate_z", "offset", "divisions"),
                     {k: LABELS[k] for k in ("thickness", "local_translate_z", "offset", "divisions")},
                     {"thickness": 0.0, "local_translate_z": 0.0, "offset": 0.0, "divisions": 1},
                     {"thickness": "NONE", "local_translate_z": "NONE", "offset": "NONE", "divisions": "INT"},
                     "local_translate_z", "extrude_edge_edit", _build_edges))
VERTEX = add_spec(Spec('VERTEX', "polyExtrudeVertex", ("width", "length", "divisions"),
                       {"width": "Width", "length": "Length", "divisions": "Divisions"},
                       {"width": 0.5, "length": 1.0, "divisions": 1},
                       {"width": "NONE", "length": "NONE", "divisions": "INT"},
                       "length", "extrude_vertex_edit", _build_vertices))


def selection_signature(bm):
    bm.verts.index_update()
    bm.edges.index_update()
    bm.faces.index_update()
    return (tuple(v.index for v in bm.verts if v.select), tuple(e.index for e in bm.edges if e.select),
            tuple(f.index for f in bm.faces if f.select))


# --- the record ------------------------------------------------------------------------------------

class Record:
    """The last kit extrusion on one object."""

    def __init__(self, name, pre, params, spec=None):
        self.name = name            # polyExtrudeFaceN (polyExtrudeEdgeN, polyExtrudeVertexN, polyBevelN)
        self.spec = spec or FACE    # which Maya node
        self.pre = pre              # BMesh copy before the extrusion
        self.params = dict(params)
        self.cap_verts = []         # vertex indices whose positions identify the kit's state
        self.sel = None             # selection signature the operation left (not FACE)
        self.topology = None        # (divisions, together) of ``moved``
        self.moved = []             # [(vertex index, P0, T, L, O, X, Y, SX, SY, SZ)]
        self.cap_faces = []         # face indices
        self.states = []            # [(params, signature, selection signature, whole-mesh coordinate hash)]
        self.live = False           # a drag is previewing values
        self.mesh_uid = None        # session_uid of the mesh it was made on
        self.dismissed = False      # Q/W/E/R picked a tool since: Maya shows that tool's manipulator (#80)
        self.preview_data = None
        self.fast_preview = False

    def free(self):
        self.preview_data = None
        if self.pre is not None:
            self.pre.free()
            self.pre = None


RECORDS = {}   # object name -> Record
# Delete History drops an object's record; Maya's undo brings the node back (redo drops it again). Delete
# History doesn't change the mesh, so the parked record is valid again after the undo (its signature still matches).
PARKED = {}    # object name -> Record dropped by Delete History


def park(name):
    """Delete History: the object's record leaves the Channel Box but stays for an undo. Returns it (or None)."""
    rec = RECORDS.pop(name, None)
    if rec is not None:
        old = PARKED.pop(name, None)
        if old is not None and old is not rec:
            old.free()
        PARKED[name] = rec
    return rec


@bpy.app.handlers.persistent
def _on_undo(*_args):
    for name, rec in PARKED.items():
        RECORDS.setdefault(name, rec)


@bpy.app.handlers.persistent
def _on_redo(*_args):
    for name, rec in PARKED.items():
        if RECORDS.get(name) is rec:
            del RECORDS[name]


def keep(context, ob, rec):
    """Remember ``rec`` as the object's history node, unless Maya's Construction History is off (Status Line
    toggle): Maya's menu commands then run without construction history and leave no polyExtrude / polyBevel
    node (Maya's Construction History)."""
    from . import prim_history
    if prim_history.history_on(context):
        parked = PARKED.pop(ob.name, None)          # a new node: the dropped one can't come back any more
        if parked is not None and parked is not RECORDS.get(ob.name) and parked is not rec:
            parked.free()
        RECORDS[ob.name] = rec
        return
    rec.free()
    RECORDS.pop(ob.name, None)


def clear():
    for rec in {id(r): r for r in (*RECORDS.values(), *PARKED.values())}.values():
        rec.free()
    RECORDS.clear()
    PARKED.clear()


def signature(bm, cap_verts):
    bm.verts.ensure_lookup_table()
    if any(i >= len(bm.verts) for i in cap_verts):
        return None
    return (len(bm.verts), len(bm.faces), tuple(cap_verts), tuple(_key(bm.verts[i].co) for i in cap_verts))


def _store(rec, bm, caps, moved, params):
    bm.verts.index_update()
    bm.faces.index_update()
    rec.params = dict(params)
    rec.topology = (params["divisions"], params["keep_faces_together"])
    rec.moved = [(v.index, p0, *vecs) for v, p0, *vecs in moved]
    rec.cap_faces = [f.index for f in caps]
    cap_verts = sorted({v.index for f in caps for v in f.verts})
    rec.cap_verts = cap_verts
    rec.states.append((dict(params), signature(bm, cap_verts), None, coords_hash(bm)))
    del rec.states[:-64]
    rec.live = False


def _store_generic(rec, bm, tracked, params, full_hash=None, preview_data=None):
    bm.verts.index_update()
    rec.params = dict(params)
    rec.preview_data = preview_data if preview_data is not None else getattr(tracked, 'preview_data', None)
    rec.fast_preview = False
    rec.cap_verts = sorted({v.index for v in tracked if v.is_valid})
    rec.cap_faces = []
    rec.sel = selection_signature(bm)
    rec.states.append((dict(params), signature(bm, rec.cap_verts), rec.sel,
                       coords_hash(bm) if full_hash is None else full_hash))
    del rec.states[:-64]
    rec.live = False


def restore_pre(bm, rec):
    """Put the mesh from before the extrusion back into ``bm`` (an edit-mode bmesh)."""
    restore_mesh(bm, rec.pre)


def restore_mesh(bm, source):
    """Restore a BMesh snapshot, including its custom data, after an edit or failed build."""
    me = bpy.data.meshes.new(".allset_pre")
    try:
        source.to_mesh(me)
        bm.clear()
        bm.from_mesh(me)
    finally:
        bpy.data.meshes.remove(me)


def run(ob, rec, params, unit):
    """Rebuild the extrusion of ``rec`` on ``ob`` (edit mode) with ``params``."""
    bm = bmesh.from_edit_mesh(ob.data)
    if rec.spec is not FACE:
        rollback = bpy.data.meshes.new('.allset_preview') if rec.spec.atomic else None
        full_hash = None
        try:
            if rollback is not None:
                bm.to_mesh(rollback)
            try:
                restore_pre(bm, rec)
                values = {k: params[k] for k in rec.spec.fields + rec.spec.hidden if k in params}
                tracked = rec.spec.build(bm, values, unit, **({"ob": ob} if rec.spec.with_object else {}))
                if rec.spec.atomic and not tracked:
                    raise ValueError('The attributes do not produce a valid '+rec.spec.node_type)
            except Exception:
                if rollback is not None:
                    bm.clear()
                    bm.from_mesh(rollback)
                    bmesh.update_edit_mesh(ob.data)
                raise
            preview_data = getattr(tracked, 'preview_data', None)
            if rollback is not None:
                # The build succeeded. Reuse its compact rollback mesh for the native coordinate hash.
                bm.to_mesh(rollback)
                full_hash = mesh_coords_hash(rollback)
            _store_generic(rec, bm, tracked, params, full_hash, preview_data)
        finally:
            if rollback is not None:
                bpy.data.meshes.remove(rollback)
        bmesh.update_edit_mesh(ob.data)
        return bool(tracked)
    restore_pre(bm, rec)
    faces = [f for f in bm.faces if f.select]
    caps, moved = extrude(bm, faces, unit=unit, **params, **mesh_axes(ob))
    _store(rec, bm, caps, moved, params)
    bmesh.update_edit_mesh(ob.data)
    return bool(caps)


def mesh_axes(ob):
    """Maya world X / Z in ``ob``'s mesh space (Maya takes ``localDirection`` in world space)."""
    m = ob.matrix_world.to_3x3().inverted_safe()
    return {"direction": m @ WORLD_X, "fallback": m @ MAYA_Z}


def preview(ob, rec, params, unit):
    """Show ``params`` during a drag: move the vertices when only lengths change, else rebuild."""
    if rec.spec is not FACE:
        if rec.spec.preview is not None and rec.spec.preview(ob, rec, params, unit):
            rec.fast_preview = True
            rec.live = True
            return
        run(ob, rec, params, unit)
        rec.live = True
        return
    topo = (params["divisions"], params["keep_faces_together"])
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    if topo != rec.topology or any(i >= len(bm.verts) for i, *_r in rec.moved):
        run(ob, rec, params, unit)
    else:
        for i, p0, *vecs in rec.moved:
            bm.verts[i].co = position(p0, vecs, params)
        bm.normal_update()
        bmesh.update_edit_mesh(ob.data, loop_triangles=True, destructive=False)
        rec.params = dict(params)
    rec.live = True


def current(ob):
    """The valid record of ``ob`` (its mesh equals a state the kit made), with that state's values; else None."""
    if ob is None or ob.type != 'MESH' or ob.mode != 'EDIT':
        return None
    rec = RECORDS.get(ob.name)
    if rec is None or rec.pre is None or rec.mesh_uid != ob.data.session_uid:
        return None
    if rec.live:
        return rec
    bm = bmesh.from_edit_mesh(ob.data)
    for params, sig, sel, *_full in reversed(rec.states):
        cap_verts = list(sig[2]) if sig else []
        if sig is not None and signature(bm, cap_verts) == sig:
            if rec.spec is not FACE:
                rec.params, rec.cap_verts, rec.sel = dict(params), cap_verts, sel
                return rec
            if params != rec.params or cap_verts != getattr(rec, "cap_verts", None):
                rec.params = dict(params)
                rec.topology = None          # ``moved`` belongs to another state: the next drag rebuilds
                rec.cap_verts = cap_verts
                rec.cap_faces = _cap_faces(bm, cap_verts)
            return rec
    return None


def coords_hash(bm):
    """Hash of every vertex position of ``bm`` (float32, the precision a Mesh stores)."""
    import numpy as np
    a = np.fromiter((c for v in bm.verts for c in v.co), dtype=np.float32, count=3 * len(bm.verts))
    return hash(a.tobytes())


def mesh_coords_hash(me):
    import numpy as np
    a = np.empty(3 * len(me.vertices), dtype=np.float32)
    me.vertices.foreach_get("co", a)
    return hash(a.tobytes())


def mesh_signature(me, cap_verts):
    """``signature`` read from an object-mode Mesh (same vertex order as the edit-mode BMesh it was written from)."""
    verts = me.vertices
    if any(i >= len(verts) for i in cap_verts):
        return None
    return (len(verts), len(me.polygons), tuple(cap_verts), tuple(_key(verts[i].co) for i in cap_verts))


def mesh_state_ok(ob, rec):
    """The object-mode mesh of ``ob`` equals a state the kit made for ``rec`` (the edit-mode rule of ``current``);
    takes that state's values."""
    me = ob.data
    full = None
    for params, sig, sel, *rest in reversed(rec.states):
        if sig is None:
            continue
        cap_verts = list(sig[2])
        if mesh_signature(me, cap_verts) != sig:
            continue
        if full is None:
            full = mesh_coords_hash(me)
        if rest and rest[0] != full:        # object mode checks every vertex (cheap there)
            continue
        if rec.spec is not FACE:
            rec.params, rec.cap_verts, rec.sel = dict(params), cap_verts, sel
        elif params != rec.params or cap_verts != getattr(rec, "cap_verts", None):
            rec.params = dict(params)
            rec.topology = None
            rec.cap_verts = cap_verts
            s = set(cap_verts)
            rec.cap_faces = [p.index for p in me.polygons if all(v in s for v in p.vertices)]
        return True
    return False


def object_record(ob):
    """The record of ``ob`` in object mode, else None. Maya lists a mesh's history nodes in object mode too: a kit
    node shows (and can be edited) there while the mesh is still the result the kit made (UV > Automatic checks its
    UVs instead)."""
    if not isinstance(ob, bpy.types.Object) or ob.type != 'MESH' or ob.mode == 'EDIT':   # a pose bone lead too
        return None
    rec = RECORDS.get(ob.name)
    if rec is None or rec.pre is None or rec.mesh_uid != ob.data.session_uid:
        return None
    check = rec.spec.object_check or mesh_state_ok
    return rec if check(ob, rec) else None


def run_from_object_mode(context, ob, rec, params, unit):
    """Rebuild ``rec`` with ``params`` while in object mode: ``ob`` alone into edit mode, rerun, back to object mode
    with the selection as it was (the caller's operator is the undo step)."""
    view_layer = context.view_layer
    sel = [o for o in context.selected_objects]
    active_ob = view_layer.objects.active
    for o in sel:
        o.select_set(o == ob)
    ob.select_set(True)
    view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        ok = run(ob, rec, params, unit)
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')
        ob.select_set(ob in sel)
        for o in sel:
            o.select_set(True)
        view_layer.objects.active = active_ob
    return ok


def edit_from_object_mode(context, edit_op, params_of):
    """Body of a kit node's edit operator in object mode: True when the active object's node was rebuilt."""
    ob = getattr(context, "active_object", None)
    rec = object_record(ob)
    if rec is None or rec.spec.edit_op != edit_op:
        return False
    return run_from_object_mode(context, ob, rec, params_of(rec.spec), units.maya_unit(context.scene))


def _cap_faces(bm, cap_verts):
    s = set(cap_verts)
    bm.faces.ensure_lookup_table()
    return [f.index for f in bm.faces if f.verts and all(v.index in s for v in f.verts)]


def caps_selected(ob, rec):
    """Maya's extrude manipulator / In-View Editor stay while the extruded faces are the selection (edge / vertex
    extrusion, bevel: while the selection is the one the operation left)."""
    bm = bmesh.from_edit_mesh(ob.data)
    selected = (None, None, rec.cap_faces) if rec.spec is FACE else rec.sel
    if selected is None or (rec.spec is FACE and not rec.cap_faces):
        return False
    return _selection_matches(ob, bm, selected)


def _selection_matches(ob, bm, selected):
    if selected is None:
        return False
    for sequence, indices, count in zip((bm.verts, bm.edges, bm.faces), selected,
                                        ('total_vert_sel', 'total_edge_sel', 'total_face_sel')):
        if indices is None:
            continue
        if getattr(ob.data, count) != len(indices):
            return False
        sequence.ensure_lookup_table()
        if any(index >= len(sequence) or not sequence[index].select for index in indices):
            return False
    return True


def active(context):
    """(object, record) of the active edit object when its last extrusion can be edited."""
    ob = context.edit_object if context is not None else None
    rec = current(ob)
    return (ob, rec) if rec is not None else (None, None)


def dismiss(context):
    """Maya: picking a tool (Q / W / E / R) after an extrusion swaps the extrude manipulator and In-View Editor for
    that tool's manipulator; the node stays in Channel Box INPUTS (issue #80). True when one was showing."""
    _ob, rec = active(context)
    if rec is None or rec.dismissed:
        return False
    rec.dismissed = True
    return True


def next_name(scene, spec=None):
    spec = spec or FACE
    n = int(scene.get(spec.counter, 0)) + 1
    scene[spec.counter] = n
    return f"{spec.node}{n}"


def _pre_signature(bm):
    return (len(bm.verts), len(bm.edges), len(bm.faces)) + selection_signature(bm)


def _uv_signature(bm):
    uv = bm.loops.layers.uv.active
    if uv is None:
        return None
    return hash(tuple(round(c, 7) for f in bm.faces for lp in f.loops for c in lp[uv].uv))


def kind_of(bm, select_mode):
    """Which Maya extrusion the selection asks for: the select mode first (Maya extrudes the selected
    component type), then whatever is selected."""
    sv, se, sf = select_mode
    has = {'FACE': any(f.select for f in bm.faces), 'EDGE': any(e.select for e in bm.edges),
           'VERTEX': any(v.select for v in bm.verts)}
    for kind, on in (('FACE', sf), ('EDGE', se), ('VERTEX', sv)):
        if on and has[kind]:
            return kind
    return next((k for k in ('FACE', 'EDGE', 'VERTEX') if has[k]), None)


def record_new(context, ob, bm, spec, params, unit):
    """Run ``spec`` on the selection of ``ob`` (edit mode) as a new history node; the same node again when
    Adjust Last Operation re-runs it on the same mesh. Returns the record or None."""
    try:
        return _record_bm(context, ob, bm, spec, params, unit)
    finally:
        # A failed build can replace the BMesh while restoring its snapshot.
        bmesh.update_edit_mesh(ob.data)


def record_object(context, ob, spec, params, unit):
    """``record_new`` on an object-mode mesh: every component of it (Maya acts on the whole mesh for an object
    selection). Returns the record or None."""
    me = ob.data
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        for el in (*bm.verts, *bm.edges, *bm.faces):
            el.select = True
        rec = _record_bm(context, ob, bm, spec, params, unit)
        if rec is not None:
            bm.to_mesh(me)
            me.update()
    finally:
        bm.free()
    return rec


def _record_bm(context, ob, bm, spec, params, unit):
    old = RECORDS.get(ob.name)
    name = None
    if (old is not None and old.spec is spec and old.pre is not None and old.mesh_uid == ob.data.session_uid
            and _pre_signature(old.pre) == _pre_signature(bm)
            and (not spec.pre_uv or _uv_signature(old.pre) == _uv_signature(bm))):
        name = old.name
    pre = bm.copy()
    try:
        tracked = spec.build(bm, params, unit, **({"ob": ob} if spec.with_object else {}))
    except Exception:
        try:
            restore_mesh(bm, pre)
        finally:
            pre.free()
        raise
    if not tracked:
        restore_mesh(bm, pre)
        pre.free()
        return None
    if old is not None:
        old.free()
    rec = Record(name or next_name(context.scene, spec), pre, params, spec)
    rec.mesh_uid = ob.data.session_uid
    _store_generic(rec, bm, tracked, params)
    keep(context, ob, rec)
    return rec


# --- operators -------------------------------------------------------------------------------------

def _props():
    return {
        "thickness": FloatProperty(name="Thickness", default=0.0, options={'SKIP_SAVE'},
                                   description="Every extruded face plane moves out by this much (Maya units)"),
        "local_translate_z": FloatProperty(name="Local Translate Z", default=0.0, options={'SKIP_SAVE'},
                                           description="Move the extruded faces along their normals (Maya units)"),
        "offset": FloatProperty(name="Offset", default=0.0, options={'SKIP_SAVE'},
                                description="Shrink the extruded faces in their plane (Maya units)"),
        "divisions": IntProperty(name="Divisions", default=1, min=1, soft_max=20, options={'SKIP_SAVE'},
                                 description="Segments along the extruded sides"),
        "keep_faces_together": BoolProperty(name="Keep Faces Together", default=True,
                                            description="Extrude adjacent faces as one piece (off: each face alone)"),
        # polyExtrudeFace values of the manipulator handles
        "local_translate_x": FloatProperty(name="Local Translate X", default=0.0, options={'SKIP_SAVE'},
                                           description="Move the extruded faces along their local X (Maya units)"),
        "local_translate_y": FloatProperty(name="Local Translate Y", default=0.0, options={'SKIP_SAVE'},
                                           description="Move the extruded faces along their local Y (Maya units)"),
        "local_scale_x": FloatProperty(name="Local Scale X", default=1.0, options={'SKIP_SAVE'},
                                       description="Scale the extruded faces along their local X"),
        "local_scale_y": FloatProperty(name="Local Scale Y", default=1.0, options={'SKIP_SAVE'},
                                       description="Scale the extruded faces along their local Y"),
        "local_scale_z": FloatProperty(name="Local Scale Z", default=1.0, options={'SKIP_SAVE'},
                                       description="Scale the extruded faces along their normal"),
        # polyExtrudeVertex
        "width": FloatProperty(name="Width", default=0.5, soft_min=0.0, soft_max=1.0, options={'SKIP_SAVE'},
                               description="Base of the extruded vertex as a fraction of each of its edges"),
        "length": FloatProperty(name="Length", default=1.0, options={'SKIP_SAVE'},
                                description="Tip of the extruded vertex along its normal (Maya units)"),
    }


def _params(op, spec=None):
    return {k: getattr(op, k) for k in (spec or FACE).all_fields}


class _ExtrudeProps:
    __annotations__ = _props()


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_extrude(_ExtrudeProps, bpy.types.Operator):
    """Extrude the selection now (Maya polyExtrudeFace / polyExtrudeEdge / polyExtrudeVertex by the component
    type): change its values with the manipulator, the In-View Editor or Channel Box INPUTS"""
    bl_idname = "allset.extrude"
    bl_label = "Extrude"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def invoke(self, context, event):
        # Maya extrudes edges / vertices at once too (no drag: #70)
        return self.execute(context)

    def execute(self, context):
        unit = units.maya_unit(context.scene)
        mode = tuple(context.scene.tool_settings.mesh_select_mode)
        done = 0
        for ob in context.objects_in_mode_unique_data:
            if ob.type != 'MESH':
                continue
            bm = bmesh.from_edit_mesh(ob.data)
            kind = kind_of(bm, mode)
            if kind is None:
                continue
            if kind != 'FACE':
                spec = SPECS[kind]
                if record_new(context, ob, bm, spec, _params(self, spec), unit) is not None:
                    done += 1
                continue
            params = _params(self)
            faces = [f for f in bm.faces if f.select]
            old = RECORDS.get(ob.name)
            name = None
            if (old is not None and old.spec is FACE and old.pre is not None and old.mesh_uid == ob.data.session_uid
                    and _pre_signature(old.pre) == _pre_signature(bm)):
                name = old.name          # Adjust Last Operation re-runs the same extrusion
            if old is not None:
                old.free()
            rec = Record(name or next_name(context.scene), bm.copy(), params)
            rec.mesh_uid = ob.data.session_uid
            caps, moved = extrude(bm, faces, unit=unit, **params, **mesh_axes(ob))
            _store(rec, bm, caps, moved, params)
            keep(context, ob, rec)
            bmesh.update_edit_mesh(ob.data)
            done += 1
        return {'FINISHED'} if done else {'CANCELLED'}


class _ExtrudeEdit(_ExtrudeProps):
    """Shared body of the edit operators (a registered operator class can't be subclassed: its poll broke)."""
    bl_options = {'REGISTER', 'UNDO'}
    _op = "extrude_edit"                  # the specs this operator edits (Spec.edit_op)

    @classmethod
    def poll(cls, context):
        return context.mode in {'EDIT_MESH', 'OBJECT'}     # Maya edits history nodes in object mode too (#204)

    def invoke(self, context, event):
        _ob, rec = active(context)
        if rec is None:
            rec = object_record(getattr(context, "active_object", None))
        if rec is None or rec.spec.edit_op != self._op:
            return {'CANCELLED'}
        for k, v in rec.params.items():
            if not self.properties.is_property_set(k):
                setattr(self, k, v)
        return self.execute(context)

    def execute(self, context):
        unit = units.maya_unit(context.scene)
        if context.mode == 'OBJECT':
            if edit_from_object_mode(context, self._op, lambda spec: _params(self, spec)):
                return {'FINISHED'}
            self.report({'WARNING'}, "No extrusion to change: " + NOTICE)
            return {'CANCELLED'}
        done = 0
        for ob in context.objects_in_mode_unique_data:
            rec = RECORDS.get(ob.name)
            if rec is None or rec.pre is None or rec.spec.edit_op != self._op or (
                    not rec.live and current(ob) is None):
                continue
            if run(ob, rec, _params(self, rec.spec), unit):
                done += 1
        if not done:
            self.report({'WARNING'}, "No extrusion to change: " + NOTICE)
            return {'CANCELLED'}
        return {'FINISHED'}


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_extrude_edit(_ExtrudeEdit, bpy.types.Operator):
    """Change the last extrusion (Maya: edit the polyExtrudeFace node). Blender keeps no edit-mode history,
    so only the last one can be changed"""
    bl_idname = "allset.extrude_edit"
    bl_label = "polyExtrudeFace"          # the Adjust Last Operation title = the Maya node
    _op = "extrude_edit"


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_extrude_edge_edit(_ExtrudeEdit, bpy.types.Operator):
    """Change the last edge extrusion (Maya: edit the polyExtrudeEdge node). Blender keeps no edit-mode history,
    so only the last one can be changed"""
    bl_idname = "allset.extrude_edge_edit"
    bl_label = "polyExtrudeEdge"
    _op = "extrude_edge_edit"


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_extrude_vertex_edit(_ExtrudeEdit, bpy.types.Operator):
    """Change the last vertex extrusion (Maya: edit the polyExtrudeVertex node). Blender keeps no edit-mode
    history, so only the last one can be changed"""
    bl_idname = "allset.extrude_vertex_edit"
    bl_label = "polyExtrudeVertex"
    _op = "extrude_vertex_edit"


INT_FIELDS = ("divisions", "segments")


def set_params(context, **changes):
    """Change values of the active object's last kit node (one undo step). Returns the operator result."""
    _ob, rec = active(context)
    if rec is None:
        rec = object_record(getattr(context, "active_object", None))
    if rec is None:
        return {'CANCELLED'}
    params = dict(rec.params)
    params.update(changes)
    properties = getattr(bpy.ops.allset, rec.spec.edit_op).get_rna_type().properties
    for key in rec.spec.all_fields:
        prop = properties.get(key)
        if prop is not None and prop.type == 'INT':
            params[key] = max(prop.hard_min, min(prop.hard_max, int(params[key])))
    # undo=True: a Python operator call pushes no undo step by default (bpy.ops positional ``undo``)
    return getattr(bpy.ops.allset, rec.spec.edit_op)('EXEC_DEFAULT', True, **params)


classes = (ALLSET_OT_extrude, ALLSET_OT_extrude_edit, ALLSET_OT_extrude_edge_edit, ALLSET_OT_extrude_vertex_edit)


@bpy.app.handlers.persistent
def _on_load(_dummy):
    clear()


_HANDLERS = (("load_pre", _on_load), ("undo_post", _on_undo), ("redo_post", _on_redo))


def register_handlers():
    for name, fn in _HANDLERS:
        lst = getattr(bpy.app.handlers, name)
        if fn not in lst:
            lst.append(fn)


def unregister_handlers():
    for name, fn in _HANDLERS:
        lst = getattr(bpy.app.handlers, name)
        if fn in lst:
            lst.remove(fn)
    clear()
