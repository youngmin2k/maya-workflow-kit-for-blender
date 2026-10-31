# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya's wire deformer (Deform > Wire and Deform > Wire >).

Maya rule: for a deformed point p, c = the nearest point of the
*base* wire (a hidden copy of the curve made with the deformer, ``curve1BaseWire``) at parameter u, c' = the wire at
the same u, T / T' their tangents, d = |p - c|, D = Dropoff Distance (× the dropoff locators' scale at u):

    w  = (1 - (d / D)²) · weight              (0 when d >= D)
    p' = p + envelope · [ w (c' - c) + R(T -> T', w · rotation · angle(T, T')) (p - c) - (p - c) ]

so a moved curve pulls the points with it, a bent one turns their offsets, and twist / scale of the curve object
alone change nothing (the curve's points don't move). Blender has no wire modifier, so the kit wire is a Geometry
Nodes modifier named like the Maya node (``wire1``) on a shared node group: both curves become polylines at their
evaluated points (same count, uniform in parameter), the nearest base edge gives c and u. The weights are the
vertex group ``wire1`` (default weight 1), which Deform > Paint Weights > Wire paints.

Dropoff locators: a locator at parameter a with Percent s scales D; between neighbouring knots
[0, locators sorted by parameter, 1] with scales [1, s..., 1] the scale is s_a + (s_b - s_a) g(t), g(t) = 1 - (1 - t²)²;
the kit keeps up to ``LOCATOR_SLOTS`` per wire.
"""

import bpy
from mathutils import Vector

GROUP = ".Allset Wire"           # leading dot: hidden in node menus
LOCATOR_SLOTS = 4
RESOLUTION = 64                  # evaluated points per span: polyline error ~ 1e-5 for Maya-sized bends
VERSION_PROP = "allset_wire_version"
VERSION = 1
BASE_SUFFIX = "BaseWire"
WIRE_PROP = "allset_wire"        # on the curve object: the wire node names it drives (comma list)
LOC_PROP = "allset_dropoff"      # on a dropoff locator empty: "<object>|<wire node>"

INPUTS = (("Wire", 'NodeSocketObject', None), ("Base Wire", 'NodeSocketObject', None),
          ("Dropoff Distance", 'NodeSocketFloat', 1.0), ("Rotation", 'NodeSocketFloat', 1.0),
          ("Envelope", 'NodeSocketFloat', 1.0), ("Weight", 'NodeSocketFloat', 1.0)) + tuple(
    item for i in range(1, LOCATOR_SLOTS + 1)
    for item in ((f"Locator {i} Param", 'NodeSocketFloat', 1.0), (f"Locator {i} Percent", 'NodeSocketFloat', 1.0)))


# --- node group -------------------------------------------------------------------------------------------------

class _B:
    """Tiny node builder: math helpers that return output sockets."""

    def __init__(self, ng):
        self.ng, self.x = ng, 0

    def node(self, kind, **props):
        n = self.ng.nodes.new(kind)
        for k, v in props.items():
            setattr(n, k, v)
        self.x += 30
        n.location = (self.x, 0)
        return n

    def link(self, out, inp):
        self.ng.links.new(out, inp)

    def _in(self, sock, value):
        if hasattr(value, "is_output"):
            self.link(value, sock)
        else:
            sock.default_value = value

    def math(self, op, a, b=0.0, clamp=False):
        n = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        self._in(n.inputs[0], a)
        self._in(n.inputs[1], b)
        return n.outputs[0]

    def vmath(self, op, a, b=None, scale=None, out="Vector"):
        n = self.node("ShaderNodeVectorMath", operation=op)
        self._in(n.inputs[0], a)
        if b is not None:
            self._in(n.inputs[1], b)
        if scale is not None:
            self._in(n.inputs["Scale"], scale)
        return n.outputs[out]

    def sample_index(self, geo, value, index, domain='EDGE'):
        n = self.node("GeometryNodeSampleIndex", data_type='FLOAT_VECTOR', domain=domain)
        self.link(geo, n.inputs["Geometry"])
        self.link(value, n.inputs["Value"])
        self.link(index, n.inputs["Index"])
        return n.outputs["Value"]


def _polyline(b, obj_socket):
    info = b.node("GeometryNodeObjectInfo", transform_space='RELATIVE')
    b.link(obj_socket, info.inputs["Object"])
    rs = b.node("GeometryNodeResampleCurve")
    if hasattr(rs, "mode"):
        rs.mode = 'EVALUATED'
    else:                                    # later Blender: the mode is a menu socket
        rs.inputs["Mode"].default_value = 'Evaluated'
    b.link(info.outputs["Geometry"], rs.inputs["Curve"])
    cm = b.node("GeometryNodeCurveToMesh")
    b.link(rs.outputs["Curve"], cm.inputs["Curve"])
    return cm.outputs["Mesh"]


def _g(b, t):
    """1 - (1 - t²)²."""
    t2 = b.math('MULTIPLY', t, t)
    one = b.math('SUBTRACT', 1.0, t2)
    return b.math('SUBTRACT', 1.0, b.math('MULTIPLY', one, one))


def build_group():
    ng = bpy.data.node_groups.new(GROUP, 'GeometryNodeTree')
    ng[VERSION_PROP] = VERSION
    ng.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    for name, stype, default in INPUTS:
        s = ng.interface.new_socket(name, in_out='INPUT', socket_type=stype)
        if default is not None:
            s.default_value = default
    ng.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    b = _B(ng)
    gin = b.node("NodeGroupInput")
    gout = b.node("NodeGroupOutput")
    I = gin.outputs                                             # noqa: E741
    base = _polyline(b, I["Base Wire"])
    wire = _polyline(b, I["Wire"])
    p = b.node("GeometryNodeInputPosition").outputs[0]
    near = b.node("GeometryNodeSampleNearest", domain='EDGE')
    b.link(base, near.inputs["Geometry"])
    b.link(p, near.inputs["Sample Position"])
    e = near.outputs["Index"]
    ev = b.node("GeometryNodeInputMeshEdgeVertices")
    A = b.sample_index(base, ev.outputs["Position 1"], e)
    B = b.sample_index(base, ev.outputs["Position 2"], e)
    A2 = b.sample_index(wire, ev.outputs["Position 1"], e)
    B2 = b.sample_index(wire, ev.outputs["Position 2"], e)
    ab = b.vmath('SUBTRACT', B, A)
    ab2 = b.vmath('SUBTRACT', B2, A2)
    num = b.vmath('DOT_PRODUCT', b.vmath('SUBTRACT', p, A), ab, out="Value")
    den = b.vmath('DOT_PRODUCT', ab, ab, out="Value")
    f = b.math('DIVIDE', num, den, clamp=True)
    c = b.vmath('ADD', A, b.vmath('SCALE', ab, scale=f))
    c2 = b.vmath('ADD', A2, b.vmath('SCALE', ab2, scale=f))
    # parameter u along the wire (evaluated points are uniform in parameter)
    size = b.node("GeometryNodeAttributeDomainSize", component='MESH')
    b.link(base, size.inputs["Geometry"])
    u = b.math('DIVIDE', b.math('ADD', e, f), size.outputs["Edge Count"])
    # dropoff scale from the locators: telescoping sum over the segments [0, p1 .. p4, 1]
    knots = [0.0] + [I[f"Locator {i} Param"] for i in range(1, LOCATOR_SLOTS + 1)] + [1.0]
    scales = [1.0] + [I[f"Locator {i} Percent"] for i in range(1, LOCATOR_SLOTS + 1)] + [1.0]
    scale = 1.0
    for j in range(len(knots) - 1):
        span = b.math('SUBTRACT', knots[j + 1], knots[j])
        t = b.math('DIVIDE', b.math('SUBTRACT', u, knots[j]), span, clamp=True)
        step = b.math('SUBTRACT', scales[j + 1], scales[j])
        scale = b.math('ADD', scale, b.math('MULTIPLY', step, _g(b, t)))
    dropoff = b.math('MULTIPLY', I["Dropoff Distance"], scale)
    v = b.vmath('SUBTRACT', p, c)
    d = b.vmath('LENGTH', v, out="Value")
    r = b.math('DIVIDE', d, dropoff)
    w = b.math('MAXIMUM', b.math('SUBTRACT', 1.0, b.math('MULTIPLY', r, r)), 0.0)
    w = b.math('MULTIPLY', w, I["Weight"])
    T = b.vmath('NORMALIZE', ab)
    T2 = b.vmath('NORMALIZE', ab2)
    axis = b.vmath('CROSS_PRODUCT', T, T2)
    ang = b.math('ARCTAN2', b.vmath('LENGTH', axis, out="Value"), b.vmath('DOT_PRODUCT', T, T2, out="Value"))
    ang = b.math('MULTIPLY', b.math('MULTIPLY', ang, w), I["Rotation"])
    aa = b.node("FunctionNodeAxisAngleToRotation")
    b.link(axis, aa.inputs["Axis"])
    b.link(ang, aa.inputs["Angle"])
    rv = b.node("FunctionNodeRotateVector")
    b.link(v, rv.inputs["Vector"])
    b.link(aa.outputs["Rotation"], rv.inputs["Rotation"])
    disp = b.vmath('ADD', b.vmath('SCALE', b.vmath('SUBTRACT', c2, c), scale=w),
                   b.vmath('SUBTRACT', rv.outputs["Vector"], v))
    sp = b.node("GeometryNodeSetPosition")
    b.link(I["Geometry"], sp.inputs["Geometry"])
    b.link(b.vmath('SCALE', disp, scale=I["Envelope"]), sp.inputs["Offset"])
    b.link(sp.outputs["Geometry"], gout.inputs[0])
    return ng


def group():
    ng = bpy.data.node_groups.get(GROUP)
    if ng is not None and ng.bl_idname == 'GeometryNodeTree' and ng.get(VERSION_PROP) == VERSION:
        return ng
    if ng is not None:
        ng.name = GROUP + ".old"
    return build_group()


# --- modifier inputs ------------------------------------------------------------------------------------------

def ident(md, name):
    item = md.node_group.interface.items_tree.get(name) if md.node_group is not None else None
    return item.identifier if item is not None else None


def get(md, name):
    from .. import compat
    key = ident(md, name)
    return compat.gn_input_get(md, key) if key is not None else None


def set_(md, name, value):
    from .. import compat
    key = ident(md, name)
    if key is not None:
        compat.gn_input_set(md, key, value)      # 5.2 moved the inputs off the modifier's ID properties
        md.id_data.update_tag()


def is_wire(md):
    return md.type == 'NODES' and md.node_group is not None and md.node_group.name.startswith(GROUP)


def wires_of_curve(curve):
    """[(object, modifier)] of the kit wires the curve object drives."""
    out = []
    for ob in bpy.data.objects:
        for md in getattr(ob, "modifiers", ()):
            if is_wire(md) and get(md, "Wire") == curve:
                out.append((ob, md))
    return out


# --- base wire ------------------------------------------------------------------------------------------------

def make_base(context, curve):
    """``<curve>BaseWire``: a hidden copy of the curve (Maya: transform + nurbsCurve, hidden)."""
    data = curve.data.copy()
    data.name = f"{curve.name}{BASE_SUFFIX}Shape"
    base = bpy.data.objects.new(f"{curve.name}{BASE_SUFFIX}", data)
    for coll in curve.users_collection or (context.scene.collection,):
        coll.objects.link(base)
    base.matrix_world = curve.matrix_world.copy()
    base.hide_set(True)
    base.hide_render = True
    return base


def prepare_curve(curve):
    """The wire's polyline must be fine and have as many points as the base's (a copy of the same data)."""
    if curve.data.resolution_u < RESOLUTION:
        curve.data.resolution_u = RESOLUTION


def add_wire(context, ob, curve, name, group_name, dropoff, envelope=1.0, rotation=1.0):
    """One kit wire node ``name`` on ``ob`` driven by ``curve`` (a base wire is made from its current shape)."""
    prepare_curve(curve)
    base = make_base(context, curve)
    md = ob.modifiers.new(name, 'NODES')
    md.node_group = group()
    set_(md, "Wire", curve)
    set_(md, "Base Wire", base)
    set_(md, "Dropoff Distance", float(dropoff))
    set_(md, "Envelope", float(envelope))
    set_(md, "Rotation", float(rotation))
    key = ident(md, "Weight")
    if group_name:
        from .. import compat
        compat.gn_input_attribute(md, key, group_name)
    names = [n for n in curve.get(WIRE_PROP, "").split(",") if n]
    curve[WIRE_PROP] = ",".join(names + [name])
    return md


def reset(md):
    """Maya Reset: the wire curve goes back to its base (shape and transform), so the wire deforms nothing."""
    curve, base = get(md, "Wire"), get(md, "Base Wire")
    if curve is None or base is None:
        return False
    curve.data.splines.clear()
    for sp in base.data.splines:
        new = curve.data.splines.new(sp.type)
        if sp.type == 'BEZIER':
            new.bezier_points.add(len(sp.bezier_points) - 1)
            for a, b in zip(new.bezier_points, sp.bezier_points):
                a.co, a.handle_left, a.handle_right = b.co, b.handle_left, b.handle_right
                a.handle_left_type, a.handle_right_type = b.handle_left_type, b.handle_right_type
        else:
            new.points.add(len(sp.points) - 1)
            for a, b in zip(new.points, sp.points):
                a.co = b.co
            new.order_u = sp.order_u
            new.use_endpoint_u = sp.use_endpoint_u
        new.use_cyclic_u = sp.use_cyclic_u
        new.resolution_u = sp.resolution_u
    curve.matrix_world = base.matrix_world.copy()
    return True


def remove(md):
    """Maya Remove: the node and its base wire go, the curve stays (curve1 kept, no BaseWire left)."""
    ob = md.id_data
    curve, base = get(md, "Wire"), get(md, "Base Wire")
    name = md.name
    ob.modifiers.remove(md)
    vg = ob.vertex_groups.get(name)
    if vg is not None:
        ob.vertex_groups.remove(vg)
    for loc in [o for o in bpy.data.objects if o.get(LOC_PROP) == f"{ob.name}|{name}"]:
        bpy.data.objects.remove(loc, do_unlink=True)
    if base is not None and not any(get(m, "Base Wire") == base for o in bpy.data.objects
                                    for m in getattr(o, "modifiers", ()) if is_wire(m)):
        data = base.data
        bpy.data.objects.remove(base, do_unlink=True)
        if data is not None and data.users == 0:
            bpy.data.curves.remove(data)
    if curve is not None:
        names = [n for n in curve.get(WIRE_PROP, "").split(",") if n and n != name]
        if names:
            curve[WIRE_PROP] = ",".join(names)
        elif WIRE_PROP in curve:
            del curve[WIRE_PROP]


# --- dropoff locators -----------------------------------------------------------------------------------------

def locators(md):
    """[(param, percent)] in slot order (unused slots param 1, percent 1)."""
    return [(get(md, f"Locator {i} Param"), get(md, f"Locator {i} Percent")) for i in range(1, LOCATOR_SLOTS + 1)]


def add_locator(context, md, param, percent=1.0, envelope=1.0):
    """A Maya dropoff locator at curve parameter ``param`` (0..1 of the curve's range): an empty on the wire at that
    point whose ``percent`` (× envelope, Maya's locator envelope) scales the dropoff there. Returns the empty."""
    used = [(p, s) for p, s in locators(md) if p is not None and p < 1.0 - 1e-9]
    if len(used) >= LOCATOR_SLOTS:
        raise RuntimeError(f"A kit wire takes {LOCATOR_SLOTS} dropoff locators.")
    scale = 1.0 + float(envelope) * (float(percent) - 1.0)
    used.append((float(param), scale))
    used.sort()
    for i in range(1, LOCATOR_SLOTS + 1):
        p, s = used[i - 1] if i <= len(used) else (1.0, 1.0)
        set_(md, f"Locator {i} Param", p)
        set_(md, f"Locator {i} Percent", s)
    curve = get(md, "Wire")
    from . import deformers
    loc = bpy.data.objects.new(deformers.new_name("locator"), None)
    loc.empty_display_type = 'PLAIN_AXES'
    context.view_layer.active_layer_collection.collection.objects.link(loc)
    if curve is not None:
        loc.location = point_at(curve, param)
        loc.parent = curve
        loc.matrix_parent_inverse = curve.matrix_world.inverted()
    loc[LOC_PROP] = f"{md.id_data.name}|{md.name}"
    loc["percent"] = float(percent)
    loc["param"] = float(param)
    return loc


def point_at(curve, fraction):
    """World point of ``curve`` at parameter fraction (first spline)."""
    from . import curves_maya, curves_math
    mc = curves_maya.read_spline(curve.data.splines[0], curve.matrix_world)
    full = curves_math.full(mc.knots)
    lo, hi = full[mc.degree], full[len(mc.cvs)]
    return Vector(curves_math.evaluate(mc.cvs, mc.knots, mc.degree, lo + (hi - lo) * fraction, mc.weights))


def nearest_param(curve, world_point, samples=400):
    """Parameter fraction of the curve point nearest to ``world_point``."""
    best = None
    for i in range(samples + 1):
        f = i / samples
        dd = (point_at(curve, f) - world_point).length
        if best is None or dd < best[0]:
            best = (dd, f)
    return best[1]
