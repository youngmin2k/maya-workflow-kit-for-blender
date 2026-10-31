# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Deform > Morph and Deform > Jiggle > Jiggle Deformer (issue #112).

Maya rules: nodes / names / option windows, Morph, Jiggle.
Blender has neither deformer, so each is a Geometry Nodes modifier named like the Maya node (``morph1``,
``jiggle1``) on a shared node group, like the kit wire (operators/wire_deformer.py): it deforms whatever
reaches it (upstream modifiers / shape keys), its painted weights are the vertex group of the node's name (default
weight 1, like Maya), Deform > Paint Weights > Jiggle paints it, Delete Non-Deformer History keeps it
(history.is_deformer: every kit deformer of ``deformers.BASES``), and the Channel Box INPUTS show the Maya
attributes (``deformers.ATTRS``, rows ``maya:<key>``).

Morph: w = envelope · weight; Absolute out = input + w (target − input); Relative out = input + w (target −
base rest) (Use Original Morph Target: target − target orig); Surface out = input + w F_in F_restᵀ (target − rest)
with the per-vertex frame F = [n, t, n × t] (n = Σ cross(next − p, prev − p) over the vertex's corners, t = the edge
to the next corner in its first face, made normal to n); Retarget out = input + w s F_rest F_toᵀ (target − target
orig), s = Σ rest 1-ring edge lengths / Σ target-orig ones; Mirror: the receiving side takes its mirror partner's
input (partner = the vertex at the mirrored rest position), mirrored. Object space reads the target in its own
space, World space maps its world position into the deformed object's space. The rest ("<shape>Orig") of the base
and of the target are hidden objects that share their mesh data (shape keys show the basis only, like Maya's Orig
under a blendShape), kept on the owner's mesh by a depsgraph handler (Delete History swaps the mesh).

Jiggle: a Simulation zone steps, per frame in world space, v = x − x_prev, S = goal − x, û = S / |S|,
F = (k + d) S − d (v·û) û, F *= fan c + fot (1 − c) with c = |F̂·n̂|, x ← goal + (x + v + F − goal) · jiggleWeight ·
envelope · weight (the weighted point is the next state). Disable = the input; Ignore Transform = the same in object
space (the object's motion moves nothing); Enable Only After Object Stops follows the step-205 model (the input while
the goal moves, then the spring from a point moved back by Motion Multiplier × the last goal step); Direction Bias
is kept but changes nothing. Blender's simulation cache plays Maya's jiggle1Cache (bake folder ``//jiggle1Cache``).
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty

from .. import compat
from . import deformers, wire_deformer

MORPH_GROUP = ".Allset Morph"
JIGGLE_GROUP = ".Allset Jiggle"
VERSION_PROP = "allset_205b_version"
VERSION = 1
REST_OF = "allset_rest_of"           # on a rest helper object: the object whose mesh it shows
REST_SUFFIX = "Rest"                 # morph1Rest (base rest), morph1TargetRest (target orig)

MORPH_MODES = ("Absolute", "Relative", "Surface", "Retarget", "Mirror")
MORPH_SPACES = ("Object", "World")
MIRROR_DIRECTIONS = ("+X", "-X", "+Y", "-Y", "+Z", "-Z", "Flip X", "Flip Y", "Flip Z")
JIGGLE_ENABLE = ("Enable", "Disable", "Enable Only After Object Stops")

# Maya mirrorDirection -> (Blender axis, receiving side): Maya Y-up -> Blender Z-up = X -> X, Y -> Z, Z -> -Y
#. +X: the vertices with x < 0 receive; Flip: every vertex (side 0).
MIRROR_AXES = ((0, -1), (0, 1), (2, -1), (2, 1), (1, 1), (1, -1), (0, 0), (2, 0), (1, 0))

# (socket name, socket type, default, min, max) — Maya attribute order of the Channel Box / AE
MORPH_INPUTS = (
    ("Target", 'NodeSocketObject', None, None, None),
    ("Target Orig", 'NodeSocketObject', None, None, None),
    ("Base Rest", 'NodeSocketObject', None, None, None),
    ("Envelope", 'NodeSocketFloat', 1.0, 0.0, 1.0),
    ("Weight", 'NodeSocketFloat', 1.0, 0.0, 1.0),
    ("Morph Mode", 'NodeSocketInt', 0, 0, 4),
    ("Morph Space", 'NodeSocketInt', 0, 0, 1),
    ("Mirror Direction", 'NodeSocketInt', 0, 0, 8),
    ("Use Original Morph Target", 'NodeSocketBool', False, None, None),
    # Maya attributes Maya's modes don't use (Retarget's scaling rules are): kept for the Channel Box
    ("Scale Envelope", 'NodeSocketFloat', 1.0, None, None),
    ("Uniform Scale Weight", 'NodeSocketFloat', 1.0, None, None),
    ("Normal Scale", 'NodeSocketFloat', 1.0, None, None),
    ("Tangent Plane Scale", 'NodeSocketFloat', 1.0, None, None),
    ("Tangential Damping", 'NodeSocketFloat', 0.0, None, None),
    ("Inward Constraint", 'NodeSocketFloat', 0.0, None, None),
    ("Outward Constraint", 'NodeSocketFloat', 0.0, None, None),
    ("Use Component Lookup", 'NodeSocketBool', False, None, None),
)
JIGGLE_INPUTS = (
    ("Envelope", 'NodeSocketFloat', 1.0, 0.0, 1.0),
    ("Weight", 'NodeSocketFloat', 1.0, 0.0, 1.0),
    ("Enable", 'NodeSocketInt', 0, 0, 2),
    ("Ignore Transform", 'NodeSocketBool', False, None, None),
    ("Force Along Normal", 'NodeSocketFloat', 1.0, None, None),
    ("Force On Tangent", 'NodeSocketFloat', 1.0, None, None),
    ("Motion Multiplier", 'NodeSocketFloat', 1.0, None, None),
    ("Stiffness", 'NodeSocketFloat', 0.5, 0.0, 1.0),
    ("Damping", 'NodeSocketFloat', 0.5, 0.0, 1.0),
    ("Jiggle Weight", 'NodeSocketFloat', 1.0, 0.0, 1.0),
    ("Direction Bias", 'NodeSocketFloat', 0.0, -1.0, 1.0),
)
ENUMS = {"Morph Mode": MORPH_MODES, "Morph Space": MORPH_SPACES, "Mirror Direction": MIRROR_DIRECTIONS,
         "Enable": JIGGLE_ENABLE}
STATE = ("allset_jx", "allset_jxp", "allset_jg")     # jiggle state attributes (point, previous point, previous goal)


# --- node groups --------------------------------------------------------------------------------------------

class _B(wire_deformer._B):
    """wire_deformer's builder + the few nodes these groups need."""

    def sample(self, geo, value, index, dtype='FLOAT_VECTOR', domain='POINT'):
        n = self.node("GeometryNodeSampleIndex", data_type=dtype, domain=domain)
        self.link(geo, n.inputs["Geometry"])
        self._in(n.inputs["Value"], value)
        self._in(n.inputs["Index"], index)
        return n.outputs["Value"]

    def index(self):
        return self.node("GeometryNodeInputIndex").outputs[0]

    def position(self):
        return self.node("GeometryNodeInputPosition").outputs[0]

    def info(self, obj_socket, space):
        n = self.node("GeometryNodeObjectInfo", transform_space=space)
        self.link(obj_socket, n.inputs["Object"])
        return n

    def on_domain(self, value, domain, dtype='FLOAT_VECTOR'):
        n = self.node("GeometryNodeFieldOnDomain", domain=domain, data_type=dtype)
        self.link(value, n.inputs[0])
        return n.outputs[0]

    def vertex_of(self, corner):
        n = self.node("GeometryNodeVertexOfCorner")
        self.link(corner, n.inputs["Corner Index"])
        return n.outputs["Vertex Index"]

    def offset_corner(self, corner, offset):
        n = self.node("GeometryNodeOffsetCornerInFace")
        self.link(corner, n.inputs["Corner Index"])
        n.inputs["Offset"].default_value = offset
        return n.outputs["Corner Index"]

    def switch(self, kind, cond, false, true):
        n = self.node("GeometryNodeSwitch", input_type=kind)
        self._in(n.inputs["Switch"], cond)
        self._in(n.inputs["False"], false)
        self._in(n.inputs["True"], true)
        return n.outputs["Output"]

    def index_switch(self, dtype, index, values):
        n = self.node("GeometryNodeIndexSwitch", data_type=dtype)
        while len(n.index_switch_items) < len(values):
            n.index_switch_items.new()
        self._in(n.inputs["Index"], index)
        for i, v in enumerate(values):
            self._in(n.inputs[i + 1], v)
        return n.outputs[0]

    def compare(self, op, a, b, dtype='INT'):
        n = self.node("FunctionNodeCompare", data_type=dtype, operation=op)
        sa, sb = compat.compare_inputs(n)          # 5.2 keeps only the current type's sockets
        self._in(sa, a)
        self._in(sb, b)
        return n.outputs[0]

    def lerp(self, a, b, f):
        """a + (b - a) f (vectors, f a float)."""
        return self.vmath('ADD', a, self.vmath('SCALE', self.vmath('SUBTRACT', b, a), scale=f))

    def dot(self, a, b):
        return self.vmath('DOT_PRODUCT', a, b, out="Value")

    def store(self, geo, name, value, dtype='FLOAT_VECTOR'):
        n = self.node("GeometryNodeStoreNamedAttribute", data_type=dtype, domain='POINT')
        self.link(geo, n.inputs["Geometry"])
        n.inputs["Name"].default_value = name
        self._in(n.inputs["Value"], value)
        return n.outputs["Geometry"]

    def named(self, name, dtype='FLOAT_VECTOR'):
        n = self.node("GeometryNodeInputNamedAttribute", data_type=dtype)
        n.inputs["Name"].default_value = name
        return n.outputs["Attribute"]

    def transform(self, vec, matrix, direction=False):
        n = self.node("FunctionNodeTransformDirection" if direction else "FunctionNodeTransformPoint")
        self.link(vec, n.inputs[0])
        self.link(matrix, n.inputs["Transform"])
        return n.outputs[0]


def _new_group(name, inputs):
    ng = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    ng[VERSION_PROP] = VERSION
    ng.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    for sname, stype, default, lo, hi in inputs:
        s = ng.interface.new_socket(sname, in_out='INPUT', socket_type=stype)
        if default is not None:
            s.default_value = default
        if lo is not None:
            s.min_value = lo
        if hi is not None:
            s.max_value = hi
    ng.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    return ng


def _frame(b, geo):
    """(n, t, n × t) per vertex as fields of ``geo``'s point domain (use inside ``b.sample(geo, ...)`` or on geo
    itself): n = normalised Σ over the vertex's corners of cross(next − p, prev − p) (Maya's vertex normal here),
    t = the edge to the next corner of the vertex's first corner (lowest face), Gram-Schmidt against n."""
    pos = b.position()
    ci = b.index()                                        # in the corner context of the domain evaluation below
    pn = b.sample(geo, pos, b.vertex_of(b.offset_corner(ci, 1)))
    pp = b.sample(geo, pos, b.vertex_of(b.offset_corner(ci, -1)))
    cr = b.vmath('CROSS_PRODUCT', b.vmath('SUBTRACT', pn, pos), b.vmath('SUBTRACT', pp, pos))
    n = b.vmath('NORMALIZE', b.on_domain(cr, 'CORNER'))
    cv = b.node("GeometryNodeCornersOfVertex")            # default weights = corner index: sort 0 = first face
    b.link(b.index(), cv.inputs["Vertex Index"])
    c0 = cv.outputs["Corner Index"]
    p0 = b.sample(geo, pos, b.vertex_of(b.offset_corner(c0, 1)))
    t = b.vmath('SUBTRACT', p0, pos)
    t = b.vmath('NORMALIZE', b.vmath('SUBTRACT', t, b.vmath('SCALE', n, scale=b.dot(t, n))))
    return n, t, b.vmath('CROSS_PRODUCT', n, t)


def _to_frame(b, d, frame):
    """The coordinates of ``d`` in ``frame`` (a vector (d·n, d·t, d·b))."""
    n = b.node("ShaderNodeCombineXYZ")
    for i, axis in enumerate(frame):
        b.link(b.dot(d, axis), n.inputs[i])
    return n.outputs[0]


def _from_frame(b, c, frame):
    sep = b.node("ShaderNodeSeparateXYZ")
    b.link(c, sep.inputs[0])
    out = None
    for i, axis in enumerate(frame):
        term = b.vmath('SCALE', axis, scale=sep.outputs[i])
        out = term if out is None else b.vmath('ADD', out, term)
    return out


def _sampled_frame(b, geo):
    return tuple(b.sample(geo, f, b.index()) for f in _frame(b, geo))


def _edge_mean(b, geo):
    """Mean length of the edges around each vertex of ``geo`` (a field of geo's points)."""
    ev = b.node("GeometryNodeInputMeshEdgeVertices")
    ln = b.vmath('DISTANCE', ev.outputs["Position 1"], ev.outputs["Position 2"], out="Value")
    return b.on_domain(ln, 'EDGE', 'FLOAT')


def build_morph():
    ng = _new_group(MORPH_GROUP, MORPH_INPUTS)
    b = _B(ng)
    gin = b.node("NodeGroupInput")
    gout = b.node("NodeGroupOutput")
    I = gin.outputs                                               # noqa: E741
    geo = I["Geometry"]
    p = b.position()
    idx = b.index()
    # target / target orig in the target's object space; World space: carried into this object's space
    t_geo = b.info(I["Target"], 'ORIGINAL').outputs["Geometry"]
    t_rel = b.info(I["Target"], 'RELATIVE').outputs["Transform"]
    o_geo = b.info(I["Target Orig"], 'ORIGINAL').outputs["Geometry"]
    r_geo = b.info(I["Base Rest"], 'ORIGINAL').outputs["Geometry"]
    world = b.compare('EQUAL', I["Morph Space"], 1)

    def spaced(local):
        return b.switch('VECTOR', world, local, b.transform(local, t_rel))
    tp = spaced(b.sample(t_geo, b.position(), idx))
    to = spaced(b.sample(o_geo, b.position(), idx))
    r = b.sample(r_geo, b.position(), idx)
    # Absolute / Relative
    d_abs = b.vmath('SUBTRACT', tp, p)
    d_rel = b.vmath('SUBTRACT', tp, b.switch('VECTOR', I["Use Original Morph Target"], r, to))
    # Surface: the rest-frame coordinates of (target - rest), rebuilt in the input's frame
    f_in = _frame(b, geo)
    f_rest = _sampled_frame(b, r_geo)
    d_surf = _from_frame(b, _to_frame(b, b.vmath('SUBTRACT', tp, r), f_rest), f_in)
    # Retarget: the target-orig-frame coordinates of (target - target orig), rebuilt in the rest frame, scaled
    f_to = _sampled_frame(b, o_geo)
    scale = b.math('DIVIDE', b.sample(r_geo, _edge_mean(b, r_geo), idx, 'FLOAT'),
                   b.sample(o_geo, _edge_mean(b, o_geo), idx, 'FLOAT'))
    d_ret = b.vmath('SCALE', _from_frame(b, _to_frame(b, b.vmath('SUBTRACT', tp, to), f_to), f_rest), scale=scale)
    # Mirror: the partner = the vertex at the mirrored rest position; receivers by side
    axis = b.index_switch('VECTOR', I["Mirror Direction"],
                          [tuple(1.0 if k == a else 0.0 for k in range(3)) for a, _s in MIRROR_AXES])
    side = b.index_switch('FLOAT', I["Mirror Direction"], [float(s) for _a, s in MIRROR_AXES])

    def mirrored(v):
        return b.vmath('SUBTRACT', v, b.vmath('SCALE', axis, scale=b.math('MULTIPLY', b.dot(v, axis), 2.0)))
    near = b.node("GeometryNodeSampleNearest", domain='POINT')
    b.link(r_geo, near.inputs["Geometry"])
    b.link(mirrored(r), near.inputs["Sample Position"])
    pj = b.sample(geo, b.position(), near.outputs["Index"])
    coord = b.math('MULTIPLY', b.dot(r, axis), side)
    flip = b.compare('EQUAL', side, 0.0, 'FLOAT')
    recv = b.math('MAXIMUM', b.math('GREATER_THAN', coord, 1e-6), flip)
    d_mir = b.vmath('SCALE', b.vmath('SUBTRACT', mirrored(pj), p), scale=recv)
    d = b.index_switch('VECTOR', I["Morph Mode"], [d_abs, d_rel, d_surf, d_ret, d_mir])
    # modes with a target: nothing when the target's point count differs (Maya: "Geometries do not have the same
    # point count"); Mirror needs the rest only
    cnt = b.node("GeometryNodeAttributeDomainSize", component='MESH')
    b.link(geo, cnt.inputs["Geometry"])
    tcnt = b.node("GeometryNodeAttributeDomainSize", component='MESH')
    b.link(t_geo, tcnt.inputs["Geometry"])
    rcnt = b.node("GeometryNodeAttributeDomainSize", component='MESH')
    b.link(r_geo, rcnt.inputs["Geometry"])
    n_ok = b.compare('EQUAL', cnt.outputs["Point Count"], b.switch('INT', b.compare('EQUAL', I["Morph Mode"], 4),
                                                                    tcnt.outputs["Point Count"],
                                                                    rcnt.outputs["Point Count"]))
    w = b.math('MULTIPLY', I["Envelope"], I["Weight"])
    w = b.switch('FLOAT', n_ok, 0.0, w)
    sp = b.node("GeometryNodeSetPosition")
    b.link(geo, sp.inputs["Geometry"])
    b.link(b.vmath('SCALE', d, scale=w), sp.inputs["Offset"])
    b.link(sp.outputs["Geometry"], gout.inputs[0])
    return ng


def build_jiggle():
    ng = _new_group(JIGGLE_GROUP, JIGGLE_INPUTS)
    b = _B(ng)
    gin = b.node("NodeGroupInput")
    gout = b.node("NodeGroupOutput")
    I = gin.outputs                                               # noqa: E741
    geo = I["Geometry"]
    me = b.info(b.node("GeometryNodeSelfObject").outputs[0], 'ORIGINAL').outputs["Transform"]
    ident = b.node("FunctionNodeCombineTransform").outputs[0]
    M = b.switch('MATRIX', I["Ignore Transform"], me, ident)        # noqa: N806
    inv = b.node("FunctionNodeInvertMatrix")
    b.link(M, inv.inputs["Matrix"])
    g = b.transform(b.position(), M)                                 # the goal: this frame's input, world space
    init = geo
    for name in STATE:
        init = b.store(init, name, g)
    si = b.node("GeometryNodeSimulationInput")
    so = b.node("GeometryNodeSimulationOutput")
    si.pair_with_output(so)
    b.link(init, si.inputs["Geometry"])
    state = si.outputs["Geometry"]
    idx = b.index()
    x = b.sample(state, b.named(STATE[0]), idx)
    xp = b.sample(state, b.named(STATE[1]), idx)
    gp = b.sample(state, b.named(STATE[2]), idx)
    k, dmp = I["Stiffness"], I["Damping"]
    kd = b.math('ADD', k, dmp)
    v = b.vmath('SUBTRACT', x, xp)
    s = b.vmath('SUBTRACT', g, x)
    u = b.vmath('NORMALIZE', s)
    F = b.vmath('SUBTRACT', b.vmath('SCALE', s, scale=kd),                         # noqa: N806
                b.vmath('SCALE', u, scale=b.math('MULTIPLY', dmp, b.dot(v, u))))
    nrm = b.vmath('NORMALIZE', b.transform(b.node("GeometryNodeInputNormal").outputs[0], M, direction=True))
    c = b.math('DIVIDE', b.math('ABSOLUTE', b.dot(F, nrm)), b.vmath('LENGTH', F, out="Value"))
    fac = b.math('ADD', b.math('MULTIPLY', I["Force Along Normal"], c),
                 b.math('MULTIPLY', I["Force On Tangent"], b.math('SUBTRACT', 1.0, c)))
    F = b.vmath('SCALE', F, scale=fac)                                                # noqa: N806
    sw = b.math('MULTIPLY', b.math('MULTIPLY', I["Jiggle Weight"], I["Envelope"]), I["Weight"])
    x_on = b.lerp(g, b.vmath('ADD', b.vmath('ADD', x, v), F), sw)                     # Enable
    # Enable Only After Object Stops (step-205 model; Maya scales it by ~0.69)
    moving = b.math('GREATER_THAN', b.vmath('DISTANCE', g, gp, out="Value"), 1e-9)
    F2 = b.vmath('SUBTRACT', b.vmath('SCALE', s, scale=kd), b.vmath('SCALE', v, scale=dmp))   # noqa: N806
    x_still = b.vmath('ADD', b.vmath('ADD', x, v), F2)
    x_stop = b.lerp(x_still, g, moving)
    xp_stop = b.lerp(x, b.vmath('SUBTRACT', g, b.vmath('SCALE', b.vmath('SUBTRACT', g, gp),
                                                     scale=I["Motion Multiplier"])), moving)
    x_new = b.index_switch('VECTOR', I["Enable"], [x_on, g, x_stop])
    xp_new = b.index_switch('VECTOR', I["Enable"], [x, g, xp_stop])
    out = b.store(geo, STATE[0], x_new)
    out = b.store(out, STATE[1], xp_new)
    out = b.store(out, STATE[2], g)
    b.link(out, so.inputs["Geometry"])
    res = so.outputs["Geometry"]
    # the state's point (Enable Only After Object Stops keeps it unweighted) back in object space
    xs = b.named(STATE[0])
    gs = b.named(STATE[2])
    stops = b.compare('EQUAL', I["Enable"], 2)
    xo = b.switch('VECTOR', stops, xs, b.lerp(gs, xs, sw))
    sp = b.node("GeometryNodeSetPosition")
    b.link(res, sp.inputs["Geometry"])
    b.link(b.transform(xo, inv.outputs["Matrix"]), sp.inputs["Position"])
    clean = sp.outputs["Geometry"]
    for name in STATE:
        rm = b.node("GeometryNodeRemoveAttribute")
        b.link(clean, rm.inputs["Geometry"])
        rm.inputs["Name"].default_value = name
        clean = rm.outputs["Geometry"]
    b.link(clean, gout.inputs[0])
    return ng


def _group(name, build):
    ng = bpy.data.node_groups.get(name)
    if ng is not None and ng.bl_idname == 'GeometryNodeTree' and ng.get(VERSION_PROP) == VERSION:
        return ng
    if ng is not None:
        ng.name = name + ".old"
    return build()


def morph_group():
    return _group(MORPH_GROUP, build_morph)


def jiggle_group():
    return _group(JIGGLE_GROUP, build_jiggle)


def is_morph(md):
    return md.type == 'NODES' and md.node_group is not None and md.node_group.name.startswith(MORPH_GROUP)


def is_jiggle(md):
    return md.type == 'NODES' and md.node_group is not None and md.node_group.name.startswith(JIGGLE_GROUP)


get, set_ = wire_deformer.get, wire_deformer.set_


# --- the Maya attributes on Channel Box INPUTS (deformers.ATTRS) -----------------------------------------------

def _input(key, label, kind, socket):
    def g(md):
        v = get(md, socket)
        return (bool(v) if kind == "BOOL" else int(v) if kind == "INT" else float(v)) if v is not None else 0

    def s(md, v):
        set_(md, socket, bool(v) if kind == "BOOL" else int(round(v)) if kind == "INT" else float(v))
    return deformers.Attr(key, label, kind, g, s)


# keyable Maya attributes, in Maya's Channel Box order
ATTRS = {
    "morph": [_input("envelope", "Envelope", "NONE", "Envelope"),
              _input("scaleEnvelope", "Scale Envelope", "NONE", "Scale Envelope"),
              _input("uniformScaleWeight", "Uniform Scale Weight", "NONE", "Uniform Scale Weight"),
              _input("normalScale", "Normal Scale", "NONE", "Normal Scale"),
              _input("tangentPlaneScale", "Tangent Plane Scale", "NONE", "Tangent Plane Scale"),
              _input("tangentialDamping", "Tangential Damping", "NONE", "Tangential Damping"),
              _input("inwardConstraint", "Inward Constraint", "NONE", "Inward Constraint"),
              _input("outwardConstraint", "Outward Constraint", "NONE", "Outward Constraint")],
    "jiggle": [_input("envelope", "Envelope", "NONE", "Envelope"),
               _input("enable", "Enable", "INT", "Enable"),
               _input("ignoreTransform", "Ignore Transform", "BOOL", "Ignore Transform"),
               _input("forceAlongNormal", "Force Along Normal", "NONE", "Force Along Normal"),
               _input("forceOnTangent", "Force On Tangent", "NONE", "Force On Tangent"),
               _input("motionMultiplier", "Motion Multiplier", "NONE", "Motion Multiplier"),
               _input("stiffness", "Stiffness", "NONE", "Stiffness"),
               _input("damping", "Damping", "NONE", "Damping"),
               _input("jiggleWeight", "Jiggle Weight", "NONE", "Jiggle Weight"),
               _input("directionBias", "Direction Bias", "NONE", "Direction Bias")],
}
# non-keyable Maya attributes the AE shows = node inputs
AE_EXTRA = {"morph": ("Morph Mode", "Morph Space", "Mirror Direction", "Use Original Morph Target",
                      "Use Component Lookup"),
            "jiggle": ()}

# Maya node base -> (Blender modifier type, Maya node type): joins operators/deformers.BASES (names, INPUTS, AE
# node type, Paint Weights, history.is_deformer) while this module is imported
BASES = {"morph": ('NODES', "morph"), "jiggle": ('NODES', "jiggle")}
deformers.BASES.update(BASES)
deformers.ATTRS.update(ATTRS)


# --- rest helpers ---------------------------------------------------------------------------------------------

def _rest(name, owner):
    """A hidden object (in no collection) sharing ``owner``'s mesh, showing its basis shape: Maya's Orig shape."""
    ob = bpy.data.objects.new(name, owner.data)
    ob[REST_OF] = owner
    ob.show_only_shape_key = True
    ob.active_shape_key_index = 0
    return ob


def sync_rest():
    """Keep every rest helper on its owner's current mesh (Delete History / Freeze give the owner a new one)."""
    for ob in bpy.data.objects:
        owner = ob.get(REST_OF) if REST_OF in ob else None
        if owner is not None and getattr(owner, "data", None) is not None and ob.data != owner.data:
            ob.data = owner.data
            ob.show_only_shape_key = True
            ob.active_shape_key_index = 0


@bpy.app.handlers.persistent
def _on_depsgraph(_scene, _depsgraph=None):
    try:
        sync_rest()
    except (ReferenceError, AttributeError, TypeError):
        pass


# --- creators -------------------------------------------------------------------------------------------------

def _vertex_group(ob, name, idx):
    vg = ob.vertex_groups.new(name=name)
    vg.add(list(idx) if idx is not None else list(range(len(ob.data.vertices))), 1.0, 'REPLACE')
    return vg.name


def _counts(ob):
    return len(ob.data.vertices)


def create_morph(context, mode="Absolute", space="Object", use_original=False):
    """Maya Morph: select the deformed object(s), then the target (Blender: the active object); Mirror mode needs only
    the deformed object. Returns the modifiers made."""
    deformers._object_mode(context)
    active = context.active_object
    sel = [o for o in context.selected_objects if o.type == 'MESH']
    if mode == "Mirror" and len(sel) == 1:
        bases, target = sel, None
    else:
        if active is None or not active.select_get() or active.type != 'MESH':
            raise RuntimeError("Select the object(s) to deform, then the morph target (a mesh).")
        bases, target = [o for o in sel if o != active], active
        if not bases:
            raise RuntimeError("Select the object(s) to deform, then the morph target (a mesh).")
    name = deformers.new_name("morph")
    if target is not None:
        for ob in bases:
            if _counts(ob) != _counts(target):
                raise RuntimeError(f"{name} (Morph): Geometries do not have the same point count (Original Geometry)")
    made = []
    for ob in bases:
        md = ob.modifiers.new(name, 'NODES')
        md.node_group = morph_group()
        set_(md, "Base Rest", _rest(f"{name}{REST_SUFFIX}", ob))
        if target is not None:
            set_(md, "Target", target)
            set_(md, "Target Orig", _rest(f"{name}Target{REST_SUFFIX}", target))
        set_(md, "Morph Mode", MORPH_MODES.index(mode))
        set_(md, "Morph Space", MORPH_SPACES.index(space))
        set_(md, "Use Original Morph Target", bool(use_original))
        from .. import compat
        compat.gn_input_attribute(md, wire_deformer.ident(md, "Weight"), _vertex_group(ob, name, None))
        made.append(md)
    deformers._select_only(context, bases + ([target] if target is not None else []), bases[0])  # pCube1, pCube2
    return made


def create_jiggle(context, stiffness=0.5, damping=0.5, weight=1.0, only_when_stops=False, ignore_transform=False):
    """Maya Jiggle Deformer on the selected meshes / vertices (jiggle1 + jiggle1Cache)."""
    items = [(ob, idx) for ob, idx in deformers._deformed(context) if ob.type == 'MESH']
    if not items:
        raise RuntimeError("Select a mesh (or its vertices) to jiggle.")
    name = deformers.new_name("jiggle")
    made = []
    from .. import compat
    for ob, idx in items:
        md = ob.modifiers.new(name, 'NODES')
        md.node_group = jiggle_group()
        set_(md, "Stiffness", float(stiffness))
        set_(md, "Damping", float(damping))
        set_(md, "Jiggle Weight", float(weight))
        set_(md, "Enable", 2 if only_when_stops else 0)
        set_(md, "Ignore Transform", bool(ignore_transform))
        compat.gn_input_attribute(md, wire_deformer.ident(md, "Weight"), _vertex_group(ob, name, idx))
        if hasattr(md, "bake_directory"):
            md.bake_directory = f"//{name}Cache"           # Maya's jiggle1Cache (a disk cache node)
        made.append(md)
    obs = [ob for ob, _i in items]
    deformers._select_only(context, obs, obs[0])           # Maya selects jiggle1Cache (not an object here)
    return made


# --- operators ------------------------------------------------------------------------------------------------

def _items(names):
    return [(n.upper().replace(" ", "_"), n, "") for n in names]


class ALLSET_OT_morph(bpy.types.Operator):
    """Maya Deform > Morph: select the object(s) to deform, then the target; a Geometry Nodes modifier morph1 with
    Maya's morph rule"""
    bl_idname = "allset.morph"
    bl_label = "Morph"
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(name="Morph mode", items=_items(MORPH_MODES), options={'HIDDEN', 'SKIP_SAVE'})
    space: EnumProperty(name="Morph space", items=_items(MORPH_SPACES), options={'HIDDEN', 'SKIP_SAVE'})
    use_original: BoolProperty(name="Use Original Morph Target", options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        try:
            create_morph(context, mode=self.mode.title(), space=self.space.title(), use_original=self.use_original)
        except RuntimeError as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_jiggle(bpy.types.Operator):
    """Maya Deform > Jiggle > Jiggle Deformer: a Geometry Nodes modifier jiggle1 that springs the points behind the
    object's motion (simulated frame by frame from the start frame)"""
    bl_idname = "allset.jiggle"
    bl_label = "Jiggle Deformer"
    bl_options = {'REGISTER', 'UNDO'}

    stiffness: FloatProperty(name="Stiffness", default=0.5, min=0.0, max=1.0, options={'HIDDEN', 'SKIP_SAVE'})
    damping: FloatProperty(name="Damping", default=0.5, min=0.0, max=1.0, options={'HIDDEN', 'SKIP_SAVE'})
    weight: FloatProperty(name="Weight", default=1.0, min=0.0, max=1.0, options={'HIDDEN', 'SKIP_SAVE'})
    only_when_stops: BoolProperty(name="Jiggle only when object stops", options={'HIDDEN', 'SKIP_SAVE'})
    ignore_transform: BoolProperty(name="Ignore transform", options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        try:
            create_jiggle(context, self.stiffness, self.damping, self.weight, self.only_when_stops,
                          self.ignore_transform)
        except RuntimeError as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_gn_deformer_enum(bpy.types.Operator):
    """Set this Maya attribute of the deformer node"""
    bl_idname = "allset.gn_deformer_enum"
    bl_label = "Set Deformer Attribute"
    bl_options = {'UNDO'}

    object: StringProperty(options={'HIDDEN'})
    modifier: StringProperty(options={'HIDDEN'})
    socket: StringProperty(options={'HIDDEN'})
    value: IntProperty(options={'HIDDEN'})

    def execute(self, context):
        ob = bpy.data.objects.get(self.object)
        md = ob.modifiers.get(self.modifier) if ob is not None else None
        if md is None:
            return {'CANCELLED'}
        set_(md, self.socket, int(self.value))
        return {'FINISHED'}


# --- Attribute Editor (ui/attribute_editor.draw_history) --------------------------------------------------------

def _draw_input(layout, md, socket, label):
    from .. import compat
    key = wire_deformer.ident(md, socket)
    if key is None:
        return
    if socket in ENUMS:
        row = layout.row(align=True)
        row.label(text=label)
        cur = get(md, socket)
        for i, text in enumerate(ENUMS[socket]):
            op = row.operator("allset.gn_deformer_enum", text=text, depress=cur == i)
            op.object, op.modifier, op.socket, op.value = md.id_data.name, md.name, socket, i
        return
    if compat.GN_INPUT_STRUCT:
        item = compat._gn_input(md, key)
        if item is not None:
            layout.prop(item, "value", text=label)
        return
    layout.prop(md, f'["{key}"]', text=label)


def draw_ae(layout, md):
    """Draw a Morph / Jiggle node's Maya attributes in its AE tab; False for other modifiers."""
    base = deformers.base_of(md)
    if base not in ATTRS:
        return False
    for a in ATTRS[base]:
        socket = next(s for s, *_r in (MORPH_INPUTS + JIGGLE_INPUTS) if a.label == s or
                      a.label.lower() == s.lower())
        _draw_input(layout, md, socket, a.label)
    for socket in AE_EXTRA[base]:
        _draw_input(layout, md, socket, socket)
    return True


# --- menus / option windows -------------------------------------------------------------------------------------

MENU = {
    "Deform/Morph": "allset.morph",
    "Deform/Jiggle/Jiggle Deformer": "allset.jiggle",
    "Deform/Paint Weights/Jiggle": ("allset.paint_deformer_weights", {"kind": "jiggle"}),
}


def _run_morph(context, v):
    return bpy.ops.allset.morph('EXEC_DEFAULT', mode=v["mode"].upper(), space=v["space"].upper(),
                                use_original=bool(v["use_original"]))


def _run_jiggle(context, v):
    return bpy.ops.allset.jiggle('EXEC_DEFAULT', stiffness=float(v["stiffness"]), damping=float(v["damping"]),
                                 weight=float(v["weight"]), only_when_stops=bool(v["only_when_stops"]),
                                 ignore_transform=bool(v["ignore_transform"]))


def windows():
    """Maya's Morph Options / Jiggle Deformer Options / Paint Weights > Jiggle boxes (default
    values); main adds them to operators/option_windows.WINDOWS."""
    from .option_windows import F, Window
    from .option_windows_deform import ADVANCED, PAINT_FIELDS, PAINT_MISSING, _paint
    return [
        # Maya's Morph Options default values: Morph mode Absolute, Morph space Object, Use Original Morph Target off,
        # Use Component Lookup off
        Window("deform_morph", "Morph Options", "Create", ("allset.morph", {}), [
            F("mode", "Morph mode:", "enum", "Absolute", items=MORPH_MODES),
            F("space", "Morph space:", "enum", "Object", items=MORPH_SPACES),
            F("use_original", "", "bool", False, text="Use Original Morph Target")], _run_morph,
            paths=("Deform/Morph",),
            missing=("Use Component Lookup (points pair by index)",) + ADVANCED),
        # Maya Jiggle Options default values: Stiffness 0.5, Damping 0.5, Weight 1.0, Jiggle only when object stops
        # off, Ignore transform off
        Window("deform_jiggle", "Jiggle Deformer Options", "Create", ("allset.jiggle", {}), [
            F("stiffness", "Stiffness:", "float", 0.5, lo=0.0, hi=1.0),
            F("damping", "Damping:", "float", 0.5, lo=0.0, hi=1.0),
            F("weight", "Weight:", "float", 1.0, lo=0.0, hi=1.0),
            F("only_when_stops", "", "bool", False, text="Jiggle only when object stops"),
            F("ignore_transform", "", "bool", False, text="Ignore transform")], _run_jiggle,
            paths=("Deform/Jiggle/Jiggle Deformer",),
            missing=("Disk cache (Blender's simulation cache: bake it in the modifier)",)),
        Window("paint_weights_jiggle", "Paint Attributes Tool", "Paint", None, PAINT_FIELDS(), _paint("jiggle"),
               paths=("Deform/Paint Weights/Jiggle",), missing=PAINT_MISSING),
    ]


classes = (ALLSET_OT_morph, ALLSET_OT_jiggle, ALLSET_OT_gn_deformer_enum)


def register_handlers():
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)


def unregister_handlers():
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
