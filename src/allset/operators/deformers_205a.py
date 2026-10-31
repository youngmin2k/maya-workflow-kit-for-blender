# SPDX-License-Identifier: GPL-3.0-or-later
"""Lane A (issue #112): Maya Deform > Tension, Solidify, Sculpt (+ Paint Weights > Tension, Prune Membership >
Sculpt).

Maya 2022 facts: nodes / names / selection / Channel Box rows / option windows, Tension, Solidify, Sculpt.
Blender has none of these deformers, so
each is a Geometry Nodes modifier named like the Maya node (``tension1``) on a shared node group built here (the
pattern of operators/wire_deformer.py); it reads its input from the modifiers above it (Maya: the upstream
deformers) and its weights from the vertex group of its name (weight 1 on the deformed points).
Maya's ``<shape>Orig`` (the rest shape Tension / Solidify compare with) is the mesh's base positions when the deformer
is made, kept in a hidden point attribute ``.allset_rest_<node>`` (component edits made later are Maya tweaks = input,
not rest); a topology change (Delete Non-Deformer History of a bevel, ...) re-takes it with the partner table.

- **Tension** (the node group repeats Maya's Jacobi passes in a
  Repeat zone): partner table per vertex = edge neighbours (strength 1), face diagonals (Shear Strength), bend partners
  (Bend Strength) as hidden INT point attributes ``.allset_tension_p<k>`` = partner · 8 + flags (1 edge, 2 diagonal,
  4 bend, -1 none), computed from the topology in Python (operators can't build variable lists in Geometry Nodes).
  Vertex normals = Maya's corner rule (cross(f[k+h] - p, f[k-h] - p), h = max(1, m // 2 - 1)), recomputed each pass.
- **Solidify** : the known parts — membership = the vertex group (points selected at creation) picks
  the solid region; Full on the whole mesh = a rigid transform of the rest region onto the input with translation =
  input centroid; Borders on the whole mesh = nothing moves; a region's border ring stays (falloff on) / moves too
  (falloff off); envelope blends linearly. Unknown: the rotation is the least-squares (Kabsch / polar)
  fit, Stabilization Level n divides the angle by 1 + n/2 (Maya: level 2 halves it), the
  border falloff is Blender's Blur Attribute of the inside weights, Scale Mode Edge / Edge Global = uniform scale by
  the region's edge-length ratio (× Scale Envelope), Normal / Tangent Plane Scale scale the normal / tangent part.
- **Sculpt**: sculptor = an Empty ``sculptor1`` (display Sphere, radius 1 Maya unit: Maya's implicit sphere;
  delta scale = maya_unit so the Channel Box shows Maya's Scale 1) and ``sculpt1StretchOrigin`` (plain axes), both at
  the deformed points' bounding-box centre ("Center within selection"); the rule =
  a model ("O": Stretch / Even, Flip / Ring, Project at the sculptor); Stretch with the origin moved off the
  sculptor, Flip / Even, Stretch / Ring, scaled sculptors and dropoff type None are (the same rule, gaps recorded
  in tests/test_step205_deform_a.py). Maximum Displacement is a length (× maya_unit) in Stretch / Flip and a
  fraction in Project (Maya: the same attribute).

Delete Non-Deformer History keeps all three (history.is_deformer: every kit deformer in deformers.BASES); Delete
History bakes them. The Maya names / node types / Channel Box rows join deformers.BASES / ATTRS at register.
"""


import bpy
from bpy.props import EnumProperty
from mathutils import Vector

from .. import results, undo_steps
from . import deformers, units, wire_deformer

VERSION_PROP = "allset_205a_version"
VERSION = 1
GROUPS = {"tension": ".Allset Tension", "solidify": ".Allset Solidify", "sculpt": ".Allset Sculpt"}
SLOT = ".allset_tension_p"          # + k: partner * 8 + flags, -1 = none
SLOT_COUNT = ".allset_tension_n"     # partners per vertex
REST = ".allset_rest_"               # + node name: rest (Maya <shape>Orig) positions
TOPO_PROP = "allset_205a_topo"       # mesh: (verts, edges, loops) the partner table / rest were taken from

TENSION_INPUTS = (
    ("Rest", 'NodeSocketVector', None), ("Weight", 'NodeSocketFloat', 1.0), ("Envelope", 'NodeSocketFloat', 1.0),
    ("Smoothing Iterations", 'NodeSocketInt', 10), ("Smoothing Step", 'NodeSocketFloat', 0.5),
    ("Inward Constraint", 'NodeSocketFloat', 0.0), ("Outward Constraint", 'NodeSocketFloat', 0.0),
    ("Squash Constraint", 'NodeSocketFloat', 1.0), ("Stretch Constraint", 'NodeSocketFloat', 1.0),
    ("Shear Strength", 'NodeSocketFloat', 0.0), ("Bend Strength", 'NodeSocketFloat', 0.0),
    ("Relative", 'NodeSocketFloat', 0.0), ("Pin Border Vertices", 'NodeSocketBool', True))
SOLIDIFY_INPUTS = (
    ("Rest", 'NodeSocketVector', None), ("Weight", 'NodeSocketFloat', 1.0), ("Envelope", 'NodeSocketFloat', 1.0),
    ("Normal Scale", 'NodeSocketFloat', 1.0), ("Tangent Plane Scale", 'NodeSocketFloat', 1.0),
    ("Scale Envelope", 'NodeSocketFloat', 1.0), ("Attachment Mode", 'NodeSocketInt', 0),
    ("Stabilization Level", 'NodeSocketInt', 0), ("Use Border Falloff", 'NodeSocketBool', True),
    ("Border Falloff Blur", 'NodeSocketInt', 2), ("Scale Mode", 'NodeSocketInt', 0))
SCULPT_INPUTS = (
    ("Sculptor", 'NodeSocketObject', None), ("Stretch Origin", 'NodeSocketObject', None),
    ("Weight", 'NodeSocketFloat', 1.0), ("Envelope", 'NodeSocketFloat', 1.0), ("Mode", 'NodeSocketInt', 2),
    ("Inside Mode", 'NodeSocketInt', 1), ("Maximum Displacement", 'NodeSocketFloat', 0.1),
    ("Dropoff Distance", 'NodeSocketFloat', 1.0), ("Dropoff Type", 'NodeSocketInt', 1), ("Unit", 'NodeSocketFloat', 1.0))
INPUTS = {"tension": TENSION_INPUTS, "solidify": SOLIDIFY_INPUTS, "sculpt": SCULPT_INPUTS}


# --- node builder -----------------------------------------------------------------------------------------------

class _B(wire_deformer._B):
    """wire_deformer's builder + the nodes these groups need (each helper returns an output socket)."""

    def out(self, n, name=0):
        return n.outputs[name]

    def cmp(self, a, b, eps=0.5):
        """1.0 where |a - b| <= eps (Math Compare)."""
        n = self.node("ShaderNodeMath", operation='COMPARE')
        self._in(n.inputs[0], a)
        self._in(n.inputs[1], b)
        self._in(n.inputs[2], eps)
        return n.outputs[0]

    def mix(self, cond, a, b):
        """a + cond · (b - a) for floats (cond 0 / 1)."""
        return self.math('ADD', a, self.math('MULTIPLY', cond, self.math('SUBTRACT', b, a)))

    def switch(self, kind, cond, false, true):
        n = self.node("GeometryNodeSwitch", input_type=kind)
        self._in(n.inputs["Switch"], cond)
        self._in(n.inputs["False"], false)
        self._in(n.inputs["True"], true)
        return n.outputs[0]

    def combine(self, x, y, z):
        n = self.node("ShaderNodeCombineXYZ")
        for i, v in enumerate((x, y, z)):
            self._in(n.inputs[i], v)
        return n.outputs[0]

    def separate(self, v):
        n = self.node("ShaderNodeSeparateXYZ")
        self._in(n.inputs[0], v)
        return n.outputs

    def at_index(self, value, index, domain='POINT', data_type='FLOAT_VECTOR'):
        n = self.node("GeometryNodeFieldAtIndex", domain=domain, data_type=data_type)
        self._in(n.inputs["Value"], value)
        self._in(n.inputs["Index"], index)
        return n.outputs[0]

    def on_domain(self, value, domain, data_type='FLOAT'):
        n = self.node("GeometryNodeFieldOnDomain", domain=domain, data_type=data_type)
        self._in(n.inputs[0], value)
        return n.outputs[0]

    def named(self, name, data_type='FLOAT'):
        n = self.node("GeometryNodeInputNamedAttribute", data_type=data_type)
        self._in(n.inputs["Name"], name)
        return n.outputs["Attribute"]

    def store(self, geo, name, value, data_type='FLOAT', domain='POINT'):
        n = self.node("GeometryNodeStoreNamedAttribute", data_type=data_type, domain=domain)
        self.link(geo, n.inputs["Geometry"])
        self._in(n.inputs["Name"], name)
        self._in(n.inputs["Value"], value)
        return n.outputs[0]

    def stat(self, geo, value, selection=None, domain='POINT', data_type='FLOAT'):
        n = self.node("GeometryNodeAttributeStatistic", domain=domain, data_type=data_type)
        self.link(geo, n.inputs["Geometry"])
        self._in(n.inputs["Attribute"], value)
        if selection is not None:
            self._in(n.inputs["Selection"], selection)
        return n.outputs

    def position(self):
        return self.node("GeometryNodeInputPosition").outputs[0]

    def index(self):
        return self.node("GeometryNodeInputIndex").outputs[0]

    def set_position(self, geo, offset=None, position=None):
        n = self.node("GeometryNodeSetPosition")
        self.link(geo, n.inputs["Geometry"])
        if offset is not None:
            self._in(n.inputs["Offset"], offset)
        if position is not None:
            self._in(n.inputs["Position"], position)
        return n.outputs[0]

    def repeat(self, geo, iterations, items=()):
        """(repeat input node, repeat output node): state = geometry (+ ``items`` (type, name, value))."""
        ri = self.node("GeometryNodeRepeatInput")
        ro = self.node("GeometryNodeRepeatOutput")
        ri.pair_with_output(ro)
        for kind, name, _v in items:
            ro.repeat_items.new(kind, name)
        self._in(ri.inputs["Iterations"], iterations)
        self.link(geo, ri.inputs["Geometry"])
        for kind, name, v in items:
            self._in(ri.inputs[name], v)
        return ri, ro

    def vlen(self, v):
        return self.vmath('LENGTH', v, out="Value")

    def dot(self, a, b):
        return self.vmath('DOT_PRODUCT', a, b, out="Value")


def _new_group(name, inputs):
    ng = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    ng[VERSION_PROP] = VERSION
    ng.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    for sname, stype, default in inputs:
        s = ng.interface.new_socket(sname, in_out='INPUT', socket_type=stype)
        if default is not None:
            s.default_value = default
    ng.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    b = _B(ng)
    gin, gout = b.node("NodeGroupInput"), b.node("NodeGroupOutput")
    return ng, b, gin.outputs, gout


def _maya_normal(b):
    """Maya's vertex normal (tension_model.normals): normalised sum over the vertex's corners of
    cross(P[f[k+h]] - p, P[f[k-h]] - p), h = max(1, m // 2 - 1) for an m-gon; a point field of the current geometry."""
    corner = b.index()
    foc = b.node("GeometryNodeFaceOfCorner")
    b.link(corner, foc.inputs["Corner Index"])
    cof = b.node("GeometryNodeCornersOfFace")
    b.link(foc.outputs["Face Index"], cof.inputs["Face Index"])
    m = cof.outputs["Total"]
    h = b.math('MAXIMUM', 1.0, b.math('SUBTRACT', b.math('FLOOR', b.math('DIVIDE', m, 2.0)), 1.0))
    sides = []
    for sign in (1.0, -1.0):
        off = b.node("GeometryNodeOffsetCornerInFace")
        b.link(corner, off.inputs["Corner Index"])
        b._in(off.inputs["Offset"], b.math('MULTIPLY', h, sign))
        sides.append(b.at_index(b.position(), off.outputs[0], domain='CORNER'))
    p = b.position()
    c = b.vmath('CROSS_PRODUCT', b.vmath('SUBTRACT', sides[0], p), b.vmath('SUBTRACT', sides[1], p))
    return b.vmath('NORMALIZE', b.on_domain(c, 'CORNER', 'FLOAT_VECTOR'))


def _slot(b, I, k):
    """(include 0/1, strength, partner index) of partner slot ``k`` (single int value) of each point."""
    vs = b.node("FunctionNodeValueToString")
    b._in(vs.inputs["Value"], k)
    b._in(vs.inputs["Decimals"], 0)
    name = b.node("FunctionNodeReplaceString")       # "<SLOT>#" with # = k (no link-order question)
    name.inputs["String"].default_value = SLOT + "#"
    name.inputs["Find"].default_value = "#"
    b.link(vs.outputs[0], name.inputs["Replace"])
    code = b.named(name.outputs[0], 'INT')
    valid = b.math('GREATER_THAN', code, -0.5)
    j = b.math('FLOOR', b.math('DIVIDE', code, 8.0))
    fl = b.math('SUBTRACT', code, b.math('MULTIPLY', j, 8.0))
    edge = b.cmp(fl, 1.0, 0.25)
    diag = b.math('GREATER_THAN', b.math('MODULO', fl, 4.0), 1.5)
    bend = b.math('GREATER_THAN', fl, 3.5)
    extra = b.math('MAXIMUM', b.math('MULTIPLY', diag, I["Shear Strength"]),
                   b.math('MULTIPLY', bend, I["Bend Strength"]))
    strength = b.mix(edge, extra, 1.0)
    inc = b.math('MULTIPLY', valid, b.math('GREATER_THAN', strength, 0.0))
    return inc, strength, j


def build_tension():
    """Maya tension: ``Smoothing Iterations`` Jacobi passes on the input, then
    out = input + envelope · weight · (P - input)."""
    ng, b, I, gout = _new_group(GROUPS["tension"], TENSION_INPUTS)
    g0 = I["Geometry"]
    # pinned = Pin Border Vertices and the point is on an edge with one face
    fc = b.node("GeometryNodeInputMeshEdgeNeighbors").outputs["Face Count"]
    border = b.math('GREATER_THAN', b.on_domain(b.cmp(fc, 1.0, 0.25), 'EDGE'), 0.0)
    free = b.math('SUBTRACT', 1.0, b.math('MULTIPLY', border, I["Pin Border Vertices"]))
    slots = b.stat(g0, b.named(SLOT_COUNT, 'INT'))["Max"]

    ri, ro = b.repeat(g0, I["Smoothing Iterations"])
    g = ri.outputs["Geometry"]
    # pass 1: Σ|P_i - P_j|, Σ|R_i - R_j| over the partners (Relative's s_i)
    g1 = b.store(b.store(g, ".allset_t_sl", 0.0), ".allset_t_sr", 0.0)
    r1, o1 = b.repeat(g1, slots)
    inc, _s, j = _slot(b, I, r1.outputs["Iteration"])
    p = b.position()
    L = b.vlen(b.vmath('SUBTRACT', p, b.at_index(b.position(), j)))
    L0 = b.vlen(b.vmath('SUBTRACT', I["Rest"], b.at_index(I["Rest"], j)))
    acc = b.store(r1.outputs["Geometry"], ".allset_t_sl",
                  b.math('ADD', b.named(".allset_t_sl"), b.math('MULTIPLY', inc, L)))
    acc = b.store(acc, ".allset_t_sr", b.math('ADD', b.named(".allset_t_sr"), b.math('MULTIPLY', inc, L0)))
    b.link(acc, o1.inputs["Geometry"])
    g2 = o1.outputs["Geometry"]
    s_i = b.math('DIVIDE', b.named(".allset_t_sl"), b.named(".allset_t_sr"))
    k_i = b.math('ADD', 1.0, b.math('MULTIPLY', I["Relative"], b.math('SUBTRACT', s_i, 1.0)))
    g2 = b.store(g2, ".allset_t_k", k_i)
    # pass 2: targets t_ij and their mean
    g2 = b.store(b.store(g2, ".allset_t_sum", (0.0, 0.0, 0.0), 'FLOAT_VECTOR'), ".allset_t_cnt", 0.0)
    r2, o2 = b.repeat(g2, slots)
    inc, strength, j = _slot(b, I, r2.outputs["Iteration"])
    p = b.position()
    pj = b.at_index(b.position(), j)
    d = b.vmath('SUBTRACT', p, pj)
    L = b.vlen(d)
    L0 = b.math('MULTIPLY', b.vlen(b.vmath('SUBTRACT', I["Rest"], b.at_index(I["Rest"], j))), b.named(".allset_t_k"))
    c = b.mix(b.math('LESS_THAN', L, L0), I["Stretch Constraint"], I["Squash Constraint"])
    lt = b.math('ADD', L, b.math('MULTIPLY', b.math('MULTIPLY', c, strength), b.math('SUBTRACT', L0, L)))
    t = b.vmath('ADD', pj, b.vmath('SCALE', d, scale=b.math('DIVIDE', lt, L)))      # Math DIVIDE by 0 = 0
    acc = b.store(r2.outputs["Geometry"], ".allset_t_sum",
                  b.vmath('ADD', b.named(".allset_t_sum", 'FLOAT_VECTOR'), b.vmath('SCALE', t, scale=inc)),
                  'FLOAT_VECTOR')
    acc = b.store(acc, ".allset_t_cnt", b.math('ADD', b.named(".allset_t_cnt"), inc))
    b.link(acc, o2.inputs["Geometry"])
    g3 = o2.outputs["Geometry"]
    cnt = b.named(".allset_t_cnt")
    p = b.position()
    mean = b.vmath('SCALE', b.named(".allset_t_sum", 'FLOAT_VECTOR'), scale=b.math('DIVIDE', 1.0, cnt))
    has = b.math('GREATER_THAN', cnt, 0.0)
    delta = b.vmath('SCALE', b.vmath('SUBTRACT', mean, p), scale=b.math('MULTIPLY', I["Smoothing Step"], has))
    n = _maya_normal(b)
    dn = b.dot(delta, n)
    corr = b.math('ADD', b.math('MULTIPLY', b.math('MINIMUM', dn, 0.0), I["Inward Constraint"]),
                  b.math('MULTIPLY', b.math('MAXIMUM', dn, 0.0), I["Outward Constraint"]))
    delta = b.vmath('SUBTRACT', delta, b.vmath('SCALE', n, scale=corr))
    g4 = b.set_position(g3, offset=b.vmath('SCALE', delta, scale=free))
    b.link(g4, ro.inputs["Geometry"])
    final = ro.outputs["Geometry"]

    pf = b.node("GeometryNodeSampleIndex", data_type='FLOAT_VECTOR', domain='POINT')
    b.link(final, pf.inputs["Geometry"])
    b.link(b.position(), pf.inputs["Value"])
    b.link(b.index(), pf.inputs["Index"])
    w = b.math('MULTIPLY', I["Envelope"], I["Weight"])
    out = b.set_position(g0, offset=b.vmath('SCALE', b.vmath('SUBTRACT', pf.outputs[0], b.position()), scale=w))
    b.link(out, gout.inputs[0])
    return ng


def build_sculpt():
    """Maya sculpt (the step-205 model)."""
    ng, b, I, gout = _new_group(GROUPS["sculpt"], SCULPT_INPUTS)
    info = b.node("GeometryNodeObjectInfo", transform_space='RELATIVE')
    b.link(I["Sculptor"], info.inputs["Object"])
    M = info.outputs["Transform"]
    inv = b.node("FunctionNodeInvertMatrix")
    b.link(M, inv.inputs["Matrix"])
    Minv = inv.outputs["Matrix"]
    oinfo = b.node("GeometryNodeObjectInfo", transform_space='RELATIVE')
    b.link(I["Stretch Origin"], oinfo.inputs["Object"])

    def tp(v, m):
        n = b.node("FunctionNodeTransformPoint")
        b._in(n.inputs["Vector"], v)
        b.link(m, n.inputs["Transform"])
        return n.outputs[0]

    def td(v, m):
        n = b.node("FunctionNodeTransformDirection")
        b._in(n.inputs["Direction"], v)
        b.link(m, n.inputs["Transform"])
        return n.outputs[0]

    md_len = b.math('MULTIPLY', I["Maximum Displacement"], I["Unit"])
    dd = b.math('MULTIPLY', I["Dropoff Distance"], I["Unit"])
    linear = b.cmp(I["Dropoff Type"], 1.0, 0.25)
    p = b.position()
    q = tp(p, Minv)
    rq = b.vlen(q)
    inside = b.math('LESS_THAN', rq, 1.0)
    # stretch (origin = the stretch origin) / flip (origin = the sculptor centre): rays from the origin
    centre = tp((0.0, 0.0, 0.0), M)
    src = b.switch('VECTOR', b.cmp(I["Mode"], 2.0, 0.25), centre, oinfo.outputs["Location"])
    sq = tp(src, Minv)
    dvec = b.vmath('SUBTRACT', q, sq)
    tiny = b.math('LESS_THAN', b.vlen(dvec), 1e-12)
    fallback = b.switch('VECTOR', b.math('GREATER_THAN', b.vlen(sq), 1e-12), (1.0, 0.0, 0.0),
                        b.vmath('SCALE', sq, scale=-1.0))
    dvec = b.switch('VECTOR', tiny, dvec, fallback)
    dl = b.vmath('NORMALIZE', dvec)
    bb = b.dot(sq, dl)
    cc = b.math('SUBTRACT', b.dot(sq, sq), 1.0)
    t = b.math('ADD', b.math('MULTIPLY', bb, -1.0),
               b.math('SQRT', b.math('MAXIMUM', b.math('SUBTRACT', b.math('MULTIPLY', bb, bb), cc), 0.0)))
    s = tp(b.vmath('ADD', sq, b.vmath('SCALE', dl, scale=t)), M)
    dw = b.vmath('NORMALIZE', td(dl, M))
    dist = b.math('MULTIPLY', b.math('SUBTRACT', rq, 1.0),
                  b.vlen(td(b.vmath('SCALE', q, scale=b.math('DIVIDE', 1.0, rq)), M)))
    w_lin = b.math('MAXIMUM', 0.0, b.math('SUBTRACT', 1.0, b.math('DIVIDE', dist, dd)))
    w_none = b.math('SUBTRACT', 1.0, b.math('GREATER_THAN', dist, dd))
    w = b.mix(linear, w_none, w_lin)
    np_in = b.vmath('ADD', s, b.vmath('SCALE', dw, scale=md_len))
    np_out = b.vmath('ADD', p, b.vmath('SCALE', dw, scale=b.math('MULTIPLY', md_len, w)))
    np_s = b.switch('VECTOR', inside, np_out, np_in)
    # project: towards the radial surface point by Maximum Displacement (a fraction)
    nq = b.switch('VECTOR', b.math('GREATER_THAN', rq, 0.0), (1.0, 0.0, 0.0),
                  b.vmath('SCALE', q, scale=b.math('DIVIDE', 1.0, rq)))
    sw = tp(nq, M)
    distp = b.vlen(b.vmath('SUBTRACT', p, sw))
    skip = b.math('MULTIPLY', b.math('MULTIPLY', b.math('SUBTRACT', 1.0, inside), b.math('GREATER_THAN', distp, dd)),
                  linear)
    np_p = b.vmath('ADD', p, b.vmath('SCALE', b.vmath('SUBTRACT', sw, p),
                                     scale=b.math('MULTIPLY', I["Maximum Displacement"], b.math('SUBTRACT', 1.0, skip))))
    target = b.switch('VECTOR', b.cmp(I["Mode"], 1.0, 0.25), np_s, np_p)
    wt = b.math('MULTIPLY', I["Envelope"], I["Weight"])
    out = b.set_position(I["Geometry"], offset=b.vmath('SCALE', b.vmath('SUBTRACT', target, p), scale=wt))
    b.link(out, gout.inputs[0])
    return ng


def build_solidify():
    """Maya solidify (rule — see the module doc)."""
    ng, b, I, gout = _new_group(GROUPS["solidify"], SOLIDIFY_INPUTS)
    g0 = I["Geometry"]
    mem = b.math('GREATER_THAN', I["Weight"], 0.0)
    # region border: member points next to a face that is not wholly member
    face_in = b.math('GREATER_THAN', b.on_domain(mem, 'POINT'), 0.999)
    out_faces = b.on_domain(b.math('SUBTRACT', 1.0, face_in), 'FACE')
    border = b.math('MULTIPLY', mem, b.math('GREATER_THAN', out_faces, 0.001))
    has_border = b.math('GREATER_THAN', b.stat(g0, border)["Max"], 0.5)
    w0 = b.math('MULTIPLY', mem, b.math('SUBTRACT', 1.0, border))
    blur = b.node("GeometryNodeBlurAttribute", data_type='FLOAT')
    b._in(blur.inputs["Value"], w0)
    b._in(blur.inputs["Iterations"], I["Border Falloff Blur"])
    w_fall = b.math('MULTIPLY', blur.outputs[0], w0)
    w = b.switch('FLOAT', I["Use Border Falloff"], mem, w_fall)
    full = b.cmp(I["Attachment Mode"], 1.0, 0.25)
    w = b.math('MULTIPLY', w, b.math('MAXIMUM', full, has_border))      # Borders without a border: nothing moves
    w = b.math('MULTIPLY', w, b.math('MULTIPLY', I["Weight"], I["Envelope"]))

    # least-squares rotation of the rest region onto the input (polar factor of Σ dp drᵀ)
    cr = b.stat(g0, I["Rest"], mem, data_type='FLOAT_VECTOR')["Mean"]
    cp = b.stat(g0, b.position(), mem, data_type='FLOAT_VECTOR')["Mean"]
    dr = b.vmath('SUBTRACT', I["Rest"], cr)
    dp = b.vmath('SUBTRACT', b.position(), cp)
    rest_geo = b.set_position(g0, position=I["Rest"])
    n_r = b.vmath('NORMALIZE', b.stat(rest_geo, b.node("GeometryNodeInputNormal").outputs[0], mem,
                                      data_type='FLOAT_VECTOR')["Sum"])
    n_p = b.vmath('NORMALIZE', b.stat(g0, b.node("GeometryNodeInputNormal").outputs[0], mem,
                                      data_type='FLOAT_VECTOR')["Sum"])
    sc = b.stat(g0, b.math('MULTIPLY', b.vlen(dr), b.vlen(dp)), mem)["Sum"]
    drs = b.separate(dr)
    nrs = b.separate(n_r)
    cols = []
    for k in range(3):
        col = b.stat(g0, b.vmath('SCALE', dp, scale=drs[k]), mem, data_type='FLOAT_VECTOR')["Sum"]
        cols.append(b.vmath('ADD', col, b.vmath('SCALE', n_p, scale=b.math('MULTIPLY', sc, nrs[k]))))
    fro = b.math('SQRT', b.math('DIVIDE', b.math('ADD', b.math('ADD', b.dot(cols[0], cols[0]), b.dot(cols[1], cols[1])),
                                                 b.dot(cols[2], cols[2])), 3.0))
    inv_f = b.math('DIVIDE', 1.0, fro)
    cm = b.node("FunctionNodeCombineMatrix")
    for k in range(3):
        comp = b.separate(b.vmath('SCALE', cols[k], scale=inv_f))
        for r in range(3):
            b._in(cm.inputs[k * 4 + r], comp[r])
        cm.inputs[k * 4 + 3].default_value = 0.0
    for r in range(3):
        cm.inputs[12 + r].default_value = 0.0
    cm.inputs[15].default_value = 1.0
    ri = b.node("GeometryNodeRepeatInput")
    ro = b.node("GeometryNodeRepeatOutput")
    ri.pair_with_output(ro)
    ro.repeat_items.new('MATRIX', "X")
    ri.inputs["Iterations"].default_value = 16
    b.link(g0, ri.inputs["Geometry"])
    b.link(cm.outputs[0], ri.inputs["X"])
    b.link(ri.outputs["Geometry"], ro.inputs["Geometry"])
    x = ri.outputs["X"]
    xi = b.node("FunctionNodeInvertMatrix")
    b.link(x, xi.inputs["Matrix"])
    xt = b.node("FunctionNodeTransposeMatrix")
    b.link(xi.outputs["Matrix"], xt.inputs["Matrix"])
    sa = b.node("FunctionNodeSeparateMatrix")
    b.link(x, sa.inputs["Matrix"])
    sb = b.node("FunctionNodeSeparateMatrix")
    b.link(xt.outputs["Matrix"], sb.inputs["Matrix"])
    nx = b.node("FunctionNodeCombineMatrix")
    for i in range(16):
        if i % 4 == 3 or i >= 12:
            nx.inputs[i].default_value = 1.0 if i == 15 else 0.0
            continue
        b.link(b.math('MULTIPLY', b.math('ADD', sa.outputs[i], sb.outputs[i]), 0.5), nx.inputs[i])
    b.link(nx.outputs[0], ro.inputs["X"])
    sep = b.node("FunctionNodeSeparateTransform")
    b.link(ro.outputs["X"], sep.inputs["Transform"])
    aa = b.node("FunctionNodeRotationToAxisAngle")
    b.link(sep.outputs["Rotation"], aa.inputs["Rotation"])
    ang = b.math('DIVIDE', aa.outputs["Angle"], b.math('ADD', 1.0, b.math('MULTIPLY', I["Stabilization Level"], 0.5)))
    rot = b.node("FunctionNodeAxisAngleToRotation")
    b.link(aa.outputs["Axis"], rot.inputs["Axis"])
    b.link(ang, rot.inputs["Angle"])

    def turn(v):
        n = b.node("FunctionNodeRotateVector")
        b._in(n.inputs["Vector"], v)
        b.link(rot.outputs["Rotation"], n.inputs["Rotation"])
        return n.outputs[0]
    o = turn(dr)
    # Scale Mode Edge / Edge Global: uniform scale by the region's edge-length ratio
    ev = b.node("GeometryNodeInputMeshEdgeVertices")
    v1, v2 = ev.outputs["Vertex Index 1"], ev.outputs["Vertex Index 2"]
    e_mem = b.math('MULTIPLY', b.at_index(mem, v1, data_type='FLOAT'), b.at_index(mem, v2, data_type='FLOAT'))
    e_in = b.vlen(b.vmath('SUBTRACT', ev.outputs["Position 1"], ev.outputs["Position 2"]))
    e_rest = b.vlen(b.vmath('SUBTRACT', b.at_index(I["Rest"], v1), b.at_index(I["Rest"], v2)))
    ratio = b.math('DIVIDE', b.stat(g0, e_in, e_mem, domain='EDGE')["Sum"],
                   b.stat(g0, e_rest, e_mem, domain='EDGE')["Sum"])
    s = b.math('ADD', 1.0, b.math('MULTIPLY', I["Scale Envelope"], b.math('SUBTRACT', ratio, 1.0)))
    nn = b.vmath('NORMALIZE', turn(n_r))
    on = b.vmath('SCALE', nn, scale=b.dot(o, nn))
    ot = b.vmath('SUBTRACT', o, on)
    scaled = b.vmath('SCALE', b.vmath('ADD', b.vmath('SCALE', ot, scale=I["Tangent Plane Scale"]),
                                      b.vmath('SCALE', on, scale=I["Normal Scale"])), scale=s)
    o = b.switch('VECTOR', b.math('GREATER_THAN', I["Scale Mode"], 0.5), o, scaled)
    target = b.vmath('ADD', cp, o)
    out = b.set_position(g0, offset=b.vmath('SCALE', b.vmath('SUBTRACT', target, b.position()), scale=w))
    b.link(out, gout.inputs[0])
    return ng


BUILDERS = {"tension": build_tension, "solidify": build_solidify, "sculpt": build_sculpt}


def group(kind):
    ng = bpy.data.node_groups.get(GROUPS[kind])
    if ng is not None and ng.bl_idname == 'GeometryNodeTree' and ng.get(VERSION_PROP) == VERSION:
        return ng
    if ng is not None:
        ng.name = GROUPS[kind] + ".old"
    return BUILDERS[kind]()


def kind_of(md):
    """"tension" / "solidify" / "sculpt" for a kit modifier of this module, else None."""
    if md.type != 'NODES' or md.node_group is None:
        return None
    for kind, name in GROUPS.items():
        if md.node_group.name.startswith(name):
            return kind
    return None


# --- topology tables / rest ---------------------------------------------------------------------------------------

def partners(faces, n):
    """[[(partner, flags)]] per vertex: edge neighbours (flag 1), then face diagonals (2) / bend partners (4) — the
    sets of the step-205 tension model (diagonals, bend_partners)."""
    nb = [set() for _ in range(n)]
    edge_faces = {}
    for fi, f in enumerate(faces):
        for k in range(len(f)):
            a, c = f[k], f[(k + 1) % len(f)]
            nb[a].add(c)
            nb[c].add(a)
            edge_faces.setdefault((min(a, c), max(a, c)), set()).add(fi)
    dg = [set() for _ in range(n)]
    for f in faces:
        for v in f:
            for u in f:
                if u != v and u not in nb[v]:
                    dg[v].add(u)
    bp = [set() for _ in range(n)]
    for f in faces:
        for k in range(2, len(f) - 1):
            bp[f[0]].add(f[k])
            bp[f[k]].add(f[0])
    for i in range(n):
        for j in nb[i]:
            fij = edge_faces[(min(i, j), max(i, j))]
            for k in nb[j]:
                if k != i and not (edge_faces[(min(j, k), max(j, k))] & fij):
                    bp[i].add(k)
    out = []
    for i in range(n):
        row = [(j, 1) for j in sorted(nb[i])]
        row += [(j, (2 if j in dg[i] else 0) | (4 if j in bp[i] else 0)) for j in sorted(dg[i] | bp[i])]
        out.append(row)
    return out


def _signature(me):
    return [len(me.vertices), len(me.edges), len(me.loops)]


def write_partners(me):
    """The tension partner table of ``me`` as hidden INT point attributes."""
    n = len(me.vertices)
    rows = partners([list(p.vertices) for p in me.polygons], n)
    width = max((len(r) for r in rows), default=0)
    for a in [a.name for a in me.attributes if a.name.startswith(SLOT)]:     # names first: removing shifts them
        me.attributes.remove(me.attributes[a])
    if SLOT_COUNT in me.attributes:
        me.attributes.remove(me.attributes[SLOT_COUNT])
    cnt = me.attributes.new(SLOT_COUNT, 'INT', 'POINT')
    cnt.data.foreach_set("value", [len(r) for r in rows])
    for k in range(width):
        a = me.attributes.new(f"{SLOT}{k}", 'INT', 'POINT')
        a.data.foreach_set("value", [r[k][0] * 8 + r[k][1] if k < len(r) else -1 for r in rows])


def write_rest(me, node):
    """``.allset_rest_<node>`` = the mesh's base positions (Maya's <shape>Orig)."""
    name = REST + node
    if name in me.attributes:
        me.attributes.remove(me.attributes[name])
    a = me.attributes.new(name, 'FLOAT_VECTOR', 'POINT')
    co = [0.0] * (3 * len(me.vertices))
    me.vertices.foreach_get("co", co)
    a.data.foreach_set("vector", co)


def sync(ob):
    """After a topology change (or on a mesh without the tables): partner table and rest positions again; tables of
    removed deformers are dropped. Returns True when the mesh was written."""
    if ob.type != 'MESH' or ob.mode == 'EDIT' or ob.data is None:
        return False
    me = ob.data
    mds = [(md, kind_of(md)) for md in ob.modifiers]
    mds = [(md, k) for md, k in mds if k in ("tension", "solidify")]
    sig = _signature(me)
    changed = list(me.get(TOPO_PROP, [])) != sig
    wrote = False
    if any(k == "tension" for _m, k in mds) and (changed or SLOT_COUNT not in me.attributes):
        write_partners(me)
        wrote = True
    if not any(k == "tension" for _m, k in mds) and SLOT_COUNT in me.attributes:
        for a in [a.name for a in me.attributes if a.name.startswith(SLOT) or a.name == SLOT_COUNT]:
            me.attributes.remove(me.attributes[a])
        wrote = True
    wanted = {REST + md.name for md, _k in mds}
    for md, _k in mds:
        if changed or REST + md.name not in me.attributes:
            write_rest(me, md.name)
            _attr_input(md, "Rest", REST + md.name)
            wrote = True
    for a in [a.name for a in me.attributes if a.name.startswith(REST) and a.name not in wanted]:
        me.attributes.remove(me.attributes[a])
        wrote = True
    if mds and changed:
        me[TOPO_PROP] = sig
    elif not mds and TOPO_PROP in me:
        del me[TOPO_PROP]
    return wrote


def _attr_input(md, name, attribute):
    from .. import compat
    compat.gn_input_attribute(md, wire_deformer.ident(md, name), attribute)


# --- creation ---------------------------------------------------------------------------------------------------

DEFAULTS = {
    # Tension Options (default values)
    'TENSION': {"iterations": 10, "step": 0.5, "pin_border": True, "relative": 0.0, "inward": 0.0, "outward": 0.0,
                "squash": 1.0, "stretch": 1.0, "shear": 0.0, "bend": 0.0},
    # Solidify Options (default values)
    'SOLIDIFY': {"attachment": "Borders", "stabilization": 0, "border_falloff": True, "falloff_iterations": 2},
    # Sculpt Options (default values)
    'SCULPT': {"mode": "Stretch", "inside_mode": "Even", "max_displacement": 0.1, "dropoff_type": "Linear",
               "dropoff_distance": 1.0, "centered": True},
}
SCULPT_MODES = ("Flip", "Project", "Stretch")      # Maya enum 0 / 1 / 2
INSIDE_MODES = ("Ring", "Even")
DROPOFF_TYPES = ("None", "Linear")


def _meshes(context):
    items = [(ob, idx) for ob, idx in deformers._deformed(context) if ob.type == 'MESH']
    if not items:
        raise RuntimeError("Select a mesh to deform.")
    return items


def _add_node(ob, name, kind, idx):
    """The GN modifier ``name`` + its weights vertex group (weight 1 on the deformed points)."""
    vg = deformers._weights(ob, name, idx)
    md = ob.modifiers.new(name, 'NODES')
    md.node_group = group(kind)
    _attr_input(md, "Weight", vg)
    if kind in ("tension", "solidify"):
        sync(ob)
    return md


def _set(md, values):
    for key, v in values.items():
        wire_deformer.set_(md, key, v)


def _tension(context, v):
    items = _meshes(context)
    name = deformers.new_name("tension")
    for ob, idx in items:
        md = _add_node(ob, name, "tension", idx)
        _set(md, {"Smoothing Iterations": int(v["iterations"]), "Smoothing Step": float(v["step"]),
                  "Pin Border Vertices": bool(v["pin_border"]), "Relative": float(v["relative"]),
                  "Inward Constraint": float(v["inward"]), "Outward Constraint": float(v["outward"]),
                  "Squash Constraint": float(v["squash"]), "Stretch Constraint": float(v["stretch"]),
                  "Shear Strength": float(v["shear"]), "Bend Strength": float(v["bend"])})
    obs = [ob for ob, _i in items]
    deformers._select_only(context, obs, obs[0])                 # Maya: pCube1, tension1
    return obs[0]


def _solidify(context, v):
    items = _meshes(context)
    name = deformers.new_name("solidify")
    for ob, idx in items:
        md = _add_node(ob, name, "solidify", idx)
        _set(md, {"Attachment Mode": 1 if v["attachment"] == "Full" else 0,
                  "Stabilization Level": int(v["stabilization"]), "Use Border Falloff": bool(v["border_falloff"]),
                  "Border Falloff Blur": int(v["falloff_iterations"])})
    obs = [ob for ob, _i in items]
    deformers._select_only(context, obs, obs[0])                 # Maya: pCube1, solidify1
    return obs[0]


def _sculpt(context, v):
    items = _meshes(context)
    lo, hi = deformers._bounds(items)
    name = deformers.new_name("sculpt")
    u = units.maya_unit(context.scene)
    n = 1
    taken = {o.name for o in bpy.data.objects}
    while f"sculptor{n}" in taken:
        n += 1
    centre = (lo + hi) / 2 if v["centered"] else Vector()
    sculptor = deformers._link(context, bpy.data.objects.new(f"sculptor{n}", None))
    sculptor.empty_display_type = 'SPHERE'          # Maya implicitSphere sphereShape1, radius 1
    sculptor.empty_display_size = 1.0
    origin = deformers._link(context, bpy.data.objects.new(f"{name}StretchOrigin", None))
    origin.empty_display_type = 'PLAIN_AXES'
    origin.empty_display_size = 1.0
    for e in (sculptor, origin):
        e.delta_scale = (u, u, u)                   # Maya units: Channel Box Scale 1 (like ffd1Lattice)
        e.location = centre
    context.view_layer.update()
    for ob, idx in items:
        md = _add_node(ob, name, "sculpt", idx)
        _set(md, {"Sculptor": sculptor, "Stretch Origin": origin, "Mode": SCULPT_MODES.index(v["mode"]),
                  "Inside Mode": INSIDE_MODES.index(v["inside_mode"]),
                  "Maximum Displacement": float(v["max_displacement"]),
                  "Dropoff Type": DROPOFF_TYPES.index(v["dropoff_type"]),
                  "Dropoff Distance": float(v["dropoff_distance"]), "Unit": float(u)})
    deformers._select_only(context, [sculptor], sculptor)       # Maya: sculptor1
    return sculptor


def create(context, kind, values=None):
    """Make Maya deformer ``kind`` (TENSION / SOLIDIFY / SCULPT) on the selection with ``values`` (option window
    values; missing = the default). Raises RuntimeError with a Maya-style message when the selection doesn't fit."""
    v = {**DEFAULTS[kind], **(values or {})}
    return {'TENSION': _tension, 'SOLIDIFY': _solidify, 'SCULPT': _sculpt}[kind](context, v)


KINDS = tuple((k, k.title(), "") for k in DEFAULTS)


class ALLSET_OT_deformer_tss(bpy.types.Operator):
    """Make a Maya Tension / Solidify / Sculpt deformer on the selection (Maya Deform menu)"""
    bl_idname = "allset.deformer_tss"
    bl_label = "Create Deformer"
    bl_options = {'REGISTER', 'UNDO'}

    kind: EnumProperty(items=KINDS, name="Deformer", options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        return {'TENSION': "Keep the edge lengths of the deformed mesh (Maya Deform > Tension)",
                'SOLIDIFY': "Keep a region of the deformed mesh rigid (Maya Deform > Solidify)",
                'SCULPT': "Push the mesh with a sphere (Maya Deform > Sculpt)"}.get(properties.kind, "")

    def execute(self, context):
        from . import option_windows
        window = next((w for w in option_windows.WINDOWS if w.match == (self.bl_idname, {"kind": self.kind})), None)
        values = option_windows.saved(window.key) if window is not None else None
        try:
            create(context, self.kind, values)
        except RuntimeError as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        return {'FINISHED'}


# --- Prune Membership > Sculpt -------------------------------------------------------------------------------------

def sculpt_targets(context):
    """[(mesh object, sculpt modifier)] for the selection: selected meshes' sculpt nodes, and the nodes a selected
    sculptor / stretch origin drives."""
    sel = set(context.selected_objects) | ({context.active_object} if context.active_object else set())
    out = []
    for ob in bpy.data.objects:
        for md in getattr(ob, "modifiers", ()):
            if kind_of(md) != "sculpt":
                continue
            if ob in sel or wire_deformer.get(md, "Sculptor") in sel or wire_deformer.get(md, "Stretch Origin") in sel:
                out.append((ob, md))
    return out


def sculpt_influence(md, points, ob_matrix):
    """Indices of ``points`` (object space) the sculpt node can move (weights and envelope aside): inside the sphere,
    or within the dropoff distance of it (Project: of its radial surface point)."""
    get = wire_deformer.get
    sculptor = get(md, "Sculptor")
    if sculptor is None:
        return set()
    M = ob_matrix.inverted() @ sculptor.matrix_world
    Minv = M.inverted()
    dd = float(get(md, "Dropoff Distance")) * float(get(md, "Unit"))
    linear = int(get(md, "Dropoff Type")) == 1
    project = int(get(md, "Mode")) == 1
    out = set()
    for i, p in enumerate(points):
        q = Minv @ p
        rq = q.length
        if rq < 1.0 or not linear and project:
            out.add(i)
            continue
        if project:
            dist = (p - M @ (q / rq)).length
            if dist <= dd:
                out.add(i)
            continue
        dist = (rq - 1.0) * (M.to_3x3() @ (q / rq)).length
        if (dist < dd) if linear else (dist <= dd):
            out.add(i)
    return out


def _input_points(context, ob, md):
    """Object-space positions the modifier ``md`` receives (the modifiers above it evaluated)."""
    shown = {m.name: m.show_viewport for m in ob.modifiers}
    after = False
    for m in ob.modifiers:
        if m == md:
            after = True
        if after:
            m.show_viewport = False
    try:
        dg = context.evaluated_depsgraph_get()
        dg.update()
        me = ob.evaluated_get(dg).to_mesh()
        pts = [v.co.copy() for v in me.vertices]
        ob.evaluated_get(dg).to_mesh_clear()
    finally:
        for m in ob.modifiers:
            m.show_viewport = shown[m.name]
    if len(pts) != len(ob.data.vertices):
        pts = [v.co.copy() for v in ob.data.vertices]
    return pts


def prune_sculpt(context):
    """Maya ``cmds.sculpt(edit=True, prune=True)``: the points the sculptor can't reach leave the node's vertex group.
    Returns the count."""
    n = 0
    for ob, md in sculpt_targets(context):
        vg = ob.vertex_groups.get(md.name)
        if vg is None:
            continue
        keep = sculpt_influence(md, _input_points(context, ob, md), ob.matrix_world)
        drop = [v.index for v in ob.data.vertices if v.index not in keep
                and any(g.group == vg.index for g in v.groups)]
        if drop:
            vg.remove(drop)
            n += len(drop)
    return n


@undo_steps.no_redo_panel
class ALLSET_OT_prune_sculpt(bpy.types.Operator):
    """Remove the points the sculptor can't reach from the sculpt deformer (Maya Deform > Prune Membership > Sculpt)"""
    bl_idname = "allset.prune_sculpt"
    bl_label = "Prune Membership"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from . import deform_edit
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        if not sculpt_targets(context):
            self.report({'WARNING'}, "Select a sculpt deformer, its sculptor or the deformed object.")
            return {'CANCELLED'}
        n = prune_sculpt(context)
        if not n:
            results.result(self, deform_edit.PRUNE_NONE)
            return {'CANCELLED'}
        results.result(self, f"{n} points pruned")
        return {'FINISHED'}


classes = (ALLSET_OT_deformer_tss, ALLSET_OT_prune_sculpt)


# --- Maya names / Channel Box rows (joined into deformers.BASES / ATTRS at register) ----------------------------------

def _gn(name, cast=float):
    def get(md):
        v = wire_deformer.get(md, name)
        return cast(v) if v is not None else cast(0)

    def set_(md, v):
        wire_deformer.set_(md, name, cast(v))
    return get, set_


def _attrs(rows):
    return [deformers.Attr(key, label, kind, *_gn(name, int if kind == "INT" else bool if kind == "BOOL" else float))
            for key, label, kind, name in rows]


BASES = {"tension": ('NODES', "tension"), "solidify": ('NODES', "solidify"), "sculpt": ('NODES', "sculpt")}
# keyable rows (Channel Box INPUTS), default order
ATTR_ROWS = {
    "tension": [("envelope", "Envelope", "NONE", "Envelope"),
                ("smoothingIterations", "Smoothing Iterations", "INT", "Smoothing Iterations"),
                ("smoothingStep", "Smoothing Step", "NONE", "Smoothing Step"),
                ("inwardConstraint", "Inward Constraint", "NONE", "Inward Constraint"),
                ("outwardConstraint", "Outward Constraint", "NONE", "Outward Constraint"),
                ("squashConstraint", "Squash Constraint", "NONE", "Squash Constraint"),
                ("stretchConstraint", "Stretch Constraint", "NONE", "Stretch Constraint"),
                ("relative", "Relative", "NONE", "Relative")],
    "solidify": [("envelope", "Envelope", "NONE", "Envelope"), ("normalScale", "Normal Scale", "NONE", "Normal Scale"),
                 ("tangentPlaneScale", "Tangent Plane Scale", "NONE", "Tangent Plane Scale"),
                 ("scaleEnvelope", "Scale Envelope", "NONE", "Scale Envelope")],
    "sculpt": [("envelope", "Envelope", "NONE", "Envelope"),
               ("maximumDisplacement", "Maximum Displacement", "NONE", "Maximum Displacement"),
               ("dropoffDistance", "Dropoff Distance", "NONE", "Dropoff Distance")],
}

# AE "<Type> Attributes": the keyable rows, then the node's other attributes
AE_EXTRA = {"tension": ("Shear Strength", "Bend Strength", "Pin Border Vertices"),
            "solidify": ("Attachment Mode", "Stabilization Level", "Use Border Falloff", "Border Falloff Blur",
                         "Scale Mode"),
            "sculpt": ("Mode", "Inside Mode", "Dropoff Type", "Sculptor", "Stretch Origin")}


def _draw_input(layout, md, socket, label):
    from .. import compat
    key = wire_deformer.ident(md, socket)
    if key is None:
        return
    if compat.GN_INPUT_STRUCT:
        item = compat._gn_input(md, key)
        if item is not None:
            layout.prop(item, "value", text=label)
        return
    layout.prop(md, f'["{key}"]', text=label)


def draw_ae(layout, md):
    """Draw a Tension / Solidify / Sculpt node's Maya attributes in its AE tab; False for other modifiers."""
    kind = kind_of(md)
    if kind is None or deformers.base_of(md) != kind:
        return False
    for _key, label, _k, socket in ATTR_ROWS[kind]:
        _draw_input(layout, md, socket, label)
    for socket in AE_EXTRA[kind]:
        _draw_input(layout, md, socket, socket)
    return True


# Maya menu paths -> kit actions (merged into ui/menu_map.py by the main lane)
MENU = {
    "Deform/Tension": ("allset.deformer_tss", {"kind": 'TENSION'}),
    "Deform/Solidify": ("allset.deformer_tss", {"kind": 'SOLIDIFY'}),
    "Deform/Sculpt": ("allset.deformer_tss", {"kind": 'SCULPT'}),
    "Deform/Paint Weights/Tension": ("allset.paint_deformer_weights", {"kind": "tension"}),
    "Deform/Prune Membership/Sculpt": "allset.prune_sculpt",
}


# --- Maya option windows (appended by operators/option_windows._extend) ----------------------------------------------

def _windows():
    from .option_windows import F, Window
    from .option_windows_deform import ADVANCED

    def run(kind):
        def go(context, v):
            create(context, kind, v)
            return {'FINISHED'}
        return go
    match = "allset.deformer_tss"
    return [
        # Tension Options: Create / Apply / Close
        Window("deform_tension", "Tension Options", "Create", (match, {"kind": 'TENSION'}), [
            F("iterations", "Smoothing iterations:", "int", 10, lo=0, hi=100),
            F("step", "Smoothing step:", "float", 0.5, lo=0.0, hi=1.0),
            F("pin_border", "", "bool", True, text="Pin border vertices"),
            F("relative", "Relative:", "float", 0.0, lo=0.0, hi=1.0),
            F("inward", "Inward constraint:", "float", 0.0, lo=0.0, hi=1.0, heading="Constraints"),
            F("outward", "Outward constraint:", "float", 0.0, lo=0.0, hi=1.0),
            F("squash", "Squash constraint:", "float", 1.0, lo=0.0, hi=1.0),
            F("stretch", "Stretch constraint:", "float", 1.0, lo=0.0, hi=1.0),
            F("shear", "Shear strength:", "float", 0.0, lo=0.0, hi=1.0),
            F("bend", "Bend strength:", "float", 0.0, lo=0.0, hi=1.0)], run('TENSION'),
            paths=("Deform/Tension",), missing=ADVANCED),
        # Solidify Options
        Window("deform_solidify", "Solidify Options", "Create", (match, {"kind": 'SOLIDIFY'}), [
            F("attachment", "Attachment mode:", "enum", "Borders", items=("Borders", "Full")),
            F("stabilization", "Stabilization Level:", "int", 0, lo=0, hi=100),
            F("border_falloff", "", "bool", True, text="Use border falloff"),
            F("falloff_iterations", "Falloff iterations:", "int", 2, lo=0, hi=100)], run('SOLIDIFY'),
            paths=("Deform/Solidify",), missing=ADVANCED),
        # Sculpt Options (default values)
        Window("deform_sculpt", "Sculpt Options", "Create", (match, {"kind": 'SCULPT'}), [
            F("mode", "Mode:", "enum", "Stretch", items=SCULPT_MODES),
            F("inside_mode", "Inside mode:", "enum", "Even", items=INSIDE_MODES),
            F("max_displacement", "Max displacement:", "float", 0.1, lo=0.0, hi=10.0),
            F("dropoff_type", "Dropoff type:", "enum", "Linear", items=DROPOFF_TYPES),
            F("dropoff_distance", "Dropoff distance:", "float", 1.0, lo=0.0, hi=20.0),
            F("centered", "", "bool", True, text="Center within selection", heading="Positioning")], run('SCULPT'),
            paths=("Deform/Sculpt",),
            missing=("Group sculptor with locator (the sculptor and its origin stay separate Empties)",
                     "Use secondary NURBS or polygon object (the sculptor is a sphere)")),
    ]


WINDOWS = []          # filled by windows() when option_windows._extend asks (avoids an import cycle at load)


def windows():
    if not WINDOWS:
        WINDOWS.extend(_windows())
        # Deform > Paint Weights > Tension ❒ = Maya's Paint Attributes Tool, like the other Paint Weights boxes
        from .option_windows import Window
        from .option_windows_deform import PAINT_FIELDS, PAINT_MISSING, _paint
        WINDOWS.append(Window("paint_weights_tension", "Paint Attributes Tool", "Paint", None, PAINT_FIELDS(),
                              _paint("tension"), paths=("Deform/Paint Weights/Tension",), missing=PAINT_MISSING))
    return WINDOWS


# --- register --------------------------------------------------------------------------------------------------------

def _on_depsgraph(scene, depsgraph):
    seen = set()
    obs = []
    for upd in depsgraph.updates:
        idb = getattr(upd.id, "original", upd.id)
        if isinstance(idb, bpy.types.Object):
            obs.append(idb)
        elif isinstance(idb, bpy.types.Mesh):          # a new / replaced mesh (Delete History swaps ob.data)
            obs.extend(o for o in scene.objects if o.data == idb)
    for ob in obs:
        if ob.type != 'MESH' or ob.name in seen:
            continue
        seen.add(ob.name)
        me = ob.data
        if (any(kind_of(md) in ("tension", "solidify") for md in ob.modifiers) or TOPO_PROP in me
                or SLOT_COUNT in me.attributes or any(a.name.startswith(REST) for a in me.attributes)):
            try:
                sync(ob)
            except (AttributeError, ReferenceError, RuntimeError):
                pass


def register_handlers():
    deformers.BASES.update(BASES)
    deformers.ATTRS.update({k: _attrs(rows) for k, rows in ATTR_ROWS.items()})
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)


def unregister_handlers():
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    for k in BASES:
        deformers.BASES.pop(k, None)
        deformers.ATTRS.pop(k, None)
