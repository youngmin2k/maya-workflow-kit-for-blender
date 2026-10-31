# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Deform menu deformers (issue #34).

Maya 2022 facts: the Deform option windows (fields / defaults), the deformers made with default options
(nodes, names, selection afterwards, Channel Box rows, Paint Weights targets) and the handle position / size.
Each Maya deformer becomes the Blender
modifier that does the same job, named like the Maya node (``ffd1``, ``deltaMush1``, ``bend1``), plus the Maya
transform it is driven by (``ffd1Lattice``, ``bend1Handle``). Its weights are the vertex group of the node's name
(weight 1 on the deformed points), which Deform > Paint Weights paints.

``ATTRS`` are the Maya attributes the Channel Box INPUTS show for a node (ui/channel_box.py reads them as virtual
rows ``maya:<key>``): each converts between the Maya value and the modifier's own settings.
"""

import math
import re

import bmesh
import bpy
from mathutils import Vector

from . import units

# --- names / node types --------------------------------------------------------------------------------

# Maya node base name -> (Blender modifier type, Maya node type)
BASES = {
    "ffd": ('LATTICE', "ffd"), "deltaMush": ('CORRECTIVE_SMOOTH', "deltaMush"), "wrap": ('SURFACE_DEFORM', "wrap"),
    "proximityWrap": ('SURFACE_DEFORM', "proximityWrap"), "shrinkWrap": ('SHRINKWRAP', "shrinkWrap"),
    "cluster": ('HOOK', "cluster"), "softMod": ('HOOK', "softMod"),
    "bend": ('SIMPLE_DEFORM', "nonLinear"), "twist": ('SIMPLE_DEFORM', "nonLinear"),
    "squash": ('SIMPLE_DEFORM', "nonLinear"), "flare": ('SIMPLE_DEFORM', "nonLinear"),
    "sine": ('WAVE', "nonLinear"), "wave": ('WAVE', "nonLinear"),
    "textureDeformer": ('DISPLACE', "textureDeformer"), "curveWarp": ('CURVE', "curveWarp"),
    "wire": ('NODES', "wire"),            # Geometry Nodes, operators/wire_deformer.py
}
_NAME = re.compile(r"^([A-Za-z]+?)(\d+)$")


def base_of(md):
    """The Maya node base of a kit deformer modifier (``bend`` for ``bend1``), or None."""
    m = _NAME.match(md.name)
    if m is None or m.group(1) not in BASES:
        return None
    return m.group(1) if BASES[m.group(1)][0] == md.type else None


def node_type(md):
    """Maya node type of a kit deformer modifier (``ffd``, ``nonLinear``, ...), or None."""
    base = base_of(md)
    return BASES[base][1] if base else None


def is_base(md):
    """The Hook that carries a kit lattice's / wrap influence's transform (``ffd1Base``, ``wrap1Base``, see
    ``_base_hook``), or a wrap's extra influence ``wrap1Influence2`` + its Hook ``wrap1Influence2Base`` (
    operators/pins_205.py): part of that node, not an INPUTS node of its own."""
    if md.type == 'SURFACE_DEFORM':
        return re.match(r"^wrap\d+Influence\d+$", md.name) is not None
    return md.type == 'HOOK' and re.match(r"^((ffd|wrap|proximityWrap)\d+|wrap\d+Influence\d+)Base$",
                                          md.name) is not None


def _taken():
    names = {o.name for o in bpy.data.objects}
    names |= {m.name for o in bpy.data.objects for m in o.modifiers}
    names |= {g.name for o in bpy.data.objects for g in getattr(o, "vertex_groups", ())}
    return names


def new_name(base):
    """``<base>N`` with N the lowest free number for the node, its handle and its lattice (Maya numbering)."""
    taken = _taken()
    n = 1
    while any(f"{base}{n}{s}" in taken for s in ("", "Handle", "Lattice", "Base")):
        n += 1
    return f"{base}{n}"


# --- the Maya attributes on Channel Box INPUTS ---------------------------------------------------------

class Attr:
    """One Maya attribute of a deformer node: ``kind`` = Channel Box entry kind (NONE / INT / BOOL / LENGTH /
    ROTATION; LENGTH values are Blender metres, shown in display units)."""

    def __init__(self, key, label, kind, get, set_):
        self.key, self.label, self.kind, self.get, self.set = key, label, kind, get, set_


def _prop(key, label, kind, prop, scale=1.0, offset=0.0):
    def get(md):
        return getattr(md, prop) / scale - offset

    def set_(md, v):
        setattr(md, prop, type(getattr(md, prop))((v + offset) * scale))
    return Attr(key, label, kind, get, set_)


def _limit(i):
    def get(md):
        return md.limits[i] * 2.0 - 1.0

    def set_(md, v):
        lim = list(md.limits)
        lim[i] = min(1.0, max(0.0, (v + 1.0) / 2.0))
        md.limits = lim
    return get, set_


def _handle_scale(md):
    h = getattr(md, "start_position_object", None) or getattr(md, "origin", None)
    s = max(abs(x) for x in h.scale) if h is not None else 1.0
    return s if s > 1e-9 else 1.0


def _handle_len(key, label, prop):
    """A nonlinear length in handle units (Maya values are in the handle's space)."""
    def get(md):
        return getattr(md, prop) / _handle_scale(md)

    def set_(md, v):
        setattr(md, prop, v * _handle_scale(md))
    return Attr(key, label, "NONE", get, set_)


def _sw_bidir_get(md):
    return md.use_positive_direction and md.use_negative_direction


def _sw_bidir_set(md, v):
    md.use_positive_direction, md.use_negative_direction = (True, True) if v else (False, True)


def _sw_reverse_get(md):
    return md.use_positive_direction and not md.use_negative_direction


def _sw_reverse_set(md, v):
    md.use_positive_direction, md.use_negative_direction = (True, False) if v else (False, True)


def _tex_offset_get(md):
    return -md.mid_level * md.strength


def _tex_offset_set(md, v):
    md.mid_level = -v / md.strength if abs(md.strength) > 1e-12 else 0.0


def _wire_input(name):
    def get(md):
        from . import wire_deformer
        v = wire_deformer.get(md, name)
        return float(v) if v is not None else 0.0

    def set_(md, v):
        from . import wire_deformer
        wire_deformer.set_(md, name, float(v))
    return get, set_


_ENVELOPE = _prop("envelope", "Envelope", "NONE", "strength")
_BOUNDS = [Attr("lowBound", "Low Bound", "NONE", *_limit(0)), Attr("highBound", "High Bound", "NONE", *_limit(1))]

# Maya deformers made with default options: their Channel Box rows (only those Blender can hold)
ATTRS = {
    "ffd": [_ENVELOPE],
    "deltaMush": [_prop("smoothingIterations", "Smoothing Iterations", "INT", "iterations"),
                  _prop("smoothingStep", "Smoothing Step", "NONE", "factor"),
                  _prop("pinBorderVertices", "Pin Border Vertices", "BOOL", "use_pin_boundary")],
    "wrap": [_ENVELOPE],
    "proximityWrap": [_ENVELOPE],
    "shrinkWrap": [_prop("offset", "Offset", "LENGTH", "offset"),
                   Attr("bidirectional", "Bidirectional", "BOOL", _sw_bidir_get, _sw_bidir_set),
                   Attr("reverse", "Reverse", "BOOL", _sw_reverse_get, _sw_reverse_set),
                   # Maya X / Y / Z = Blender X / Z / Y (Y-up -> Z-up)
                   _prop("alongX", "Along X", "BOOL", "use_project_x"),
                   _prop("alongY", "Along Y", "BOOL", "use_project_z"),
                   _prop("alongZ", "Along Z", "BOOL", "use_project_y")],
    "cluster": [_ENVELOPE],
    "softMod": [_ENVELOPE, _prop("falloffRadius", "Falloff Radius", "LENGTH", "falloff_radius")],
    "bend": [_prop("curvature", "Curvature", "NONE", "angle")] + _BOUNDS,
    "twist": [_prop("endAngle", "End Angle", "ROTATION", "angle")] + _BOUNDS,
    "squash": [_prop("factor", "Factor", "NONE", "factor")] + _BOUNDS,
    "flare": [_prop("endFlareX", "End Flare X", "NONE", "factor", offset=-1.0),
              _prop("endFlareZ", "End Flare Z", "NONE", "factor", offset=-1.0)] + _BOUNDS,
    "sine": [_handle_len("amplitude", "Amplitude", "height"), _handle_len("wavelength", "Wavelength", "width")],
    "wave": [_handle_len("amplitude", "Amplitude", "height"), _handle_len("wavelength", "Wavelength", "width"),
             _handle_len("maxRadius", "Max Radius", "falloff_radius")],
    "textureDeformer": [_prop("strength", "Strength", "NONE", "strength"),
                        Attr("offset", "Offset", "NONE", _tex_offset_get, _tex_offset_set)],
    "curveWarp": [],
    # the wire modifier's inputs; Crossing Effect / Tension / Local Influence /
    # Scale[0] have no form in the kit wire (defaults 0 / 1 / 0 / 1 = no effect)
    "wire": [Attr("envelope", "Envelope", "NONE", *_wire_input("Envelope")),
             Attr("rotation", "Rotation", "NONE", *_wire_input("Rotation")),
             Attr("dropoffDistance[0]", "Dropoff Distance[0]", "LENGTH", *_wire_input("Dropoff Distance"))],
}
PREFIX = "maya:"


def attrs(md):
    """The Maya attributes of a kit deformer modifier, or None (not a kit deformer)."""
    base = base_of(md)
    return ATTRS.get(base) if base else None


def attr(md, name):
    """The Attr behind a virtual row name ``maya:<key>`` on modifier ``md``, or None."""
    if not name.startswith(PREFIX):
        return None
    for a in attrs(md) or ():
        if a.key == name[len(PREFIX):]:
            return a
    return None


def driven_modifiers(ob):
    """Kit deformer modifiers that ``ob`` drives (a lattice / handle object): Maya shows the deformer node in
    the handle's INPUTS (ffd1Lattice, bend1Handle)."""
    if ob is None or getattr(ob, "type", None) not in {'EMPTY', 'LATTICE'}:
        return []
    out = []
    for o in bpy.data.objects:
        for md in getattr(o, "modifiers", ()):
            if base_of(md) is None:
                continue
            for p in ("object", "origin", "start_position_object"):
                if getattr(md, p, None) == ob:
                    out.append(md)
                    break
    return out


# --- selection -------------------------------------------------------------------------------------------

_DEFORMABLE = {'MESH', 'LATTICE', 'CURVE', 'SURFACE'}


def _object_mode(context):
    if context.mode != 'OBJECT' and context.active_object is not None:
        bpy.ops.object.mode_set(mode='OBJECT')


def _deformed(context, exclude=None):
    """[(object, selected vertex indices or None = every point)] Maya deforms: the selected components in edit
    mode, else the selected deformable objects. Leaves object mode."""
    out = []
    if context.mode == 'EDIT_MESH':
        for ob in context.objects_in_mode:
            if ob.type != 'MESH' or ob == exclude:
                continue
            bm = bmesh.from_edit_mesh(ob.data)
            idx = [v.index for v in bm.verts if v.select]
            if idx:
                out.append((ob, idx))
        _object_mode(context)
    else:
        _object_mode(context)
        out = [(ob, None) for ob in context.selected_objects if ob.type in _DEFORMABLE and ob != exclude]
    return out


def _points(items):
    """World positions of the deformed points (undeformed: the bounding box follows the modifiers)."""
    pts = []
    for ob, idx in items:
        mw = ob.matrix_world
        if ob.type == 'MESH':
            vs = ob.data.vertices
            pts.extend(mw @ vs[i].co for i in (idx if idx is not None else range(len(vs))))
        elif ob.type == 'LATTICE':
            pts.extend(mw @ p.co for p in ob.data.points)
        else:
            pts.extend(mw @ Vector(c) for c in ob.bound_box)
    return pts


def _bounds(items):
    pts = _points(items)
    if not pts:
        raise RuntimeError("Select objects or components to deform.")
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def _weights(ob, name, idx):
    """The deformer's weights = vertex group ``name``, weight 1 on its points (default weights)."""
    if not hasattr(ob, "vertex_groups") or ob.type not in {'MESH', 'LATTICE'}:
        return ""
    count = len(ob.data.vertices) if ob.type == 'MESH' else len(ob.data.points)
    vg = ob.vertex_groups.new(name=name)
    vg.add(list(idx) if idx is not None else list(range(count)), 1.0, 'REPLACE')
    return vg.name


def _add(ob, name, mtype, idx):
    md = ob.modifiers.new(name, mtype)
    group = _weights(ob, name, idx)
    if group and hasattr(md, "vertex_group"):
        md.vertex_group = group
    return md


def _base_hook(ob, name, driver, group):
    """Hook ``<name>Base``: moves ``ob``'s points of ``group`` by ``driver``'s transform since now (rest = none)."""
    hk = ob.modifiers.new(f"{name}Base", 'HOOK')
    hk.object = driver
    if group:
        hk.vertex_group = group
    else:
        hk.vertex_indices_set(list(range(len(ob.data.vertices))) if ob.type == 'MESH' else [])
    hk.center = ob.matrix_world.inverted_safe() @ driver.matrix_world.translation     # scale 0
    hk.matrix_inverse = driver.matrix_world.inverted() @ ob.matrix_world
    return hk


def _link(context, ob):
    context.view_layer.active_layer_collection.collection.objects.link(ob)
    return ob


def _select_only(context, obs, active):
    for o in context.selected_objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    context.view_layer.objects.active = active


def _driver(context):
    """(deformed objects, driver) for deformers that read a second object: the driver is selected last
    (Blender's active object) — Maya: select the deformed objects, then the influence / target / curve."""
    _object_mode(context)
    driver = context.active_object
    if driver is None or not driver.select_get():
        return [], None
    return [(ob, None) for ob in context.selected_objects if ob != driver and ob.type in _DEFORMABLE], driver


# --- creators -----------------------------------------------------------------------------------------------

def _lattice(context, v):
    items = _deformed(context)
    lo, hi = _bounds(items)
    name = new_name("ffd")
    lat = bpy.data.lattices.new(f"{name}LatticeShape")
    s, t, u = (max(2, int(x)) for x in v["divisions"])
    # the object first: a lattice used by an object keeps its -0.5..0.5 box when its points change, a bare one grows
    # to (points - 1) units
    lob = _link(context, bpy.data.objects.new(f"{name}Lattice", lat))
    lat.points_u, lat.points_v, lat.points_w = s, u, t           # Maya S T U along X Y Z; Maya Y = Blender Z
    size = hi - lo
    big = max(size.x, size.y, size.z, 1e-6)
    # Maya's ffd1Lattice Scale = the box size in Maya units (#95): the cm factor goes in
    # delta_scale, so the Channel Box / AE Scale reads Maya's number and the world size stays the box
    u = units.maya_unit(context.scene)
    lob.delta_scale = (u, u, u)
    lob.scale = tuple(max(c, big * 1e-3) / u for c in size)
    lob.location = (lo + hi) / 2 if v["center"] else Vector()
    context.view_layer.update()
    for ob, idx in items:
        group = _weights(ob, name, idx)
        if group:
            # Maya deforms by the lattice relative to ffd1Base: moving / scaling ffd1Lattice carries the points.
            # Blender's lattice space moves with the lattice object (moving it changes nothing), so a Hook to the
            # lattice in front of the Lattice modifier is that base: it applies the lattice's transform since
            # creation, then the lattice deforms the points in its own (rest) space.
            _base_hook(ob, name, lob, group)
        md = ob.modifiers.new(name, 'LATTICE')
        md.object = lob
        if group:
            md.vertex_group = group
    if v["auto_parent"]:
        from .parenting import set_parent_maya
        set_parent_maya(lob, items[0][0])
    _select_only(context, [lob], lob)                     # Maya: ffd1Lattice selected
    return lob


def _delta_mush(context, v):
    items = [(ob, idx) for ob, idx in _deformed(context) if ob.type == 'MESH']
    if not items:
        raise RuntimeError("Select a mesh to deform.")
    name = new_name("deltaMush")
    for ob, idx in items:
        md = _add(ob, name, 'CORRECTIVE_SMOOTH', idx)
        md.smooth_type = 'SIMPLE'
        md.rest_source = 'ORCO'
        md.iterations = int(v["iterations"])
        md.factor = float(v["step"])
        md.use_pin_boundary = bool(v["pin_border"])
    return items[0][0]


def _bind(ob, md):
    with bpy.context.temp_override(object=ob, active_object=ob):
        bpy.ops.object.surfacedeform_bind(modifier=md.name)
    bpy.context.view_layer.update()
    if not md.is_bound:
        raise RuntimeError(f"{md.name}: Blender couldn't bind {ob.name} to {md.target.name}.")


def _surface(context, base, render_influence=True, select_driver=True):
    items, drv = _driver(context)
    items = [(ob, idx) for ob, idx in items if ob.type == 'MESH']
    if drv is None or drv.type != 'MESH' or not items:
        raise RuntimeError("Select the object(s) to deform, then the influence object (a mesh).")
    name = new_name(base)
    for ob, idx in items:
        md = _add(ob, name, 'SURFACE_DEFORM', idx)
        md.target = drv
        _bind(ob, md)
        # Surface Deform follows the influence's shape but not its transform; Maya's wrap follows both.
        # A Hook to the influence after it carries the points by the influence's transform since creation.
        _base_hook(ob, md.name, drv, md.vertex_group)
    if not render_influence:
        drv.hide_render = True
    deformed = [ob for ob, _i in items]
    _select_only(context, deformed + ([drv] if select_driver else []), deformed[0])
    return deformed[0]


# Maya projection -> (wrap_method, positive, negative)
PROJECTIONS = {
    "Toward Inner Object": ('PROJECT', False, True), "Toward Center": ('NEAREST_SURFACEPOINT', False, True),
    "Parallel To Axes": ('PROJECT', False, True), "Vertex Normals": ('PROJECT', True, True),
    "Closest": ('NEAREST_SURFACEPOINT', False, True),
}


def _shrink_wrap(context, v):
    items, drv = _driver(context)
    if drv is None or drv.type != 'MESH' or not items:
        raise RuntimeError("Select the object(s) to deform, then the target object (a mesh).")
    method, pos, neg = PROJECTIONS[v["projection"]]
    if v["bidirectional"]:
        pos, neg = True, True
    elif v["reverse"]:
        pos, neg = neg, pos
    name = new_name("shrinkWrap")
    for ob, idx in items:
        md = _add(ob, name, 'SHRINKWRAP', idx)
        md.target = drv
        md.wrap_method = method
        if method == 'PROJECT':
            md.use_positive_direction, md.use_negative_direction = pos, neg
            if v["projection"] == "Parallel To Axes":
                md.use_project_x, md.use_project_z, md.use_project_y = v["along_x"], v["along_y"], v["along_z"]
        md.offset = float(v["offset"]) * units.maya_unit(context.scene)
    _select_only(context, [ob for ob, _i in items] + [drv], items[0][0])   # Maya: pCube1, pCube2
    return items[0][0]


def _curve_warp(context, v):
    items, drv = _driver(context)
    if drv is None or drv.type != 'CURVE' or not items:
        raise RuntimeError("Select the object(s) to deform, then the curve.")
    name = new_name("curveWarp")
    for ob, idx in items:
        md = _add(ob, name, 'CURVE', idx)
        md.object = drv
    _select_only(context, [ob for ob, _i in items], items[0][0])           # Maya: pCubeShape1
    return items[0][0]


def _wire(context, v):
    """Maya Wire: the deformed objects, then the wire curve (Maya's Wire Tool picks them in that
    order); a kit wire per object named like the node, weights = vertex group of that name, base wire = a hidden copy
    of the curve. Maya selects the curve afterwards."""
    from . import wire_deformer
    items, drv = _driver(context)
    items = [(ob, idx) for ob, idx in items if ob.type == 'MESH']
    if drv is None or drv.type != 'CURVE' or not items:
        raise RuntimeError("Select the object(s) to deform, then the wire curve.")
    name = new_name("wire")
    dropoff = float(v["dropoff"]) * units.maya_unit(context.scene)
    for ob, idx in items:
        group = _weights(ob, name, idx)
        wire_deformer.add_wire(context, ob, drv, name, group, dropoff, envelope=float(v["envelope"]))
    _select_only(context, [drv], drv)                                      # Maya: curve1
    return drv


NONLINEAR = {'BEND': ("bend", 'BEND'), 'TWIST': ("twist", 'TWIST'), 'SQUASH': ("squash", 'STRETCH'),
             'FLARE': ("flare", 'TAPER'), 'SINE': ("sine", None), 'WAVE': ("wave", None)}


def _nonlinear(context, kind, v):
    base, method = NONLINEAR[kind]
    items = _deformed(context)
    lo, hi = _bounds(items)
    name = new_name(base)
    # Maya: the handle at the bounding-box centre, pointing up (Maya +Y = Blender +Z),
    # uniform scale = half the height; handle scale 0.5 on the unit cube
    handle = _link(context, bpy.data.objects.new(f"{name}Handle", None))
    handle.empty_display_type = 'SINGLE_ARROW'
    handle.empty_display_size = 1.0
    handle.location = (lo + hi) / 2
    s = max((hi.z - lo.z) / 2, 1e-6)
    handle.scale = (s, s, s)
    context.view_layer.update()
    for ob, idx in items:
        if method is not None:
            md = _add(ob, name, 'SIMPLE_DEFORM', idx)
            md.deform_method = method
            md.deform_axis = 'Z'
            md.origin = handle
            md.angle = 0.0
            md.factor = 0.0
            md.limits = (min(1.0, max(0.0, (v.get("low", -1.0) + 1) / 2)),
                         min(1.0, max(0.0, (v.get("high", 1.0) + 1) / 2)))
            if kind == 'BEND':
                md.angle = float(v.get("curvature", 0.0))
            elif kind == 'TWIST':
                md.angle = math.radians(float(v.get("end_angle", 0.0)))
            elif kind == 'SQUASH':
                md.factor = float(v.get("factor", 0.0))
            elif kind == 'FLARE':
                md.factor = float(v.get("end_flare", 1.0)) - 1.0
        else:
            md = _add(ob, name, 'WAVE', idx)
            md.start_position_object = handle
            md.use_normal = False
            md.use_x, md.use_y = True, kind == 'WAVE'
            md.speed = 0.0                           # Maya's wave is still; Blender's moves with time
            md.time_offset = 0.0
            md.height = float(v.get("amplitude", 0.0)) * s
            md.width = max(1e-6, float(v.get("wavelength", 2.0 if kind == 'SINE' else 1.0)) * s)
            if kind == 'WAVE':
                md.falloff_radius = float(v.get("max_radius", 1.0)) * s
    _select_only(context, [handle], handle)          # Maya: bend1Handle, bend1
    return handle


TEX_COORDS = {"World": 'GLOBAL', "Local": 'LOCAL', "UV": 'UV'}
TEX_DIRECTION = {"Normal": 'NORMAL', "Handle": 'Z', "Vector": 'RGB_TO_XYZ'}
TEX_SPACE = {"Object": 'LOCAL', "World": 'GLOBAL'}


def _texture(context, v):
    items = [(ob, idx) for ob, idx in _deformed(context) if ob.type == 'MESH']
    if not items:
        raise RuntimeError("Select a mesh to deform.")
    if v["direction"] == "Vector" and v["vector_space"] not in TEX_SPACE:
        raise RuntimeError("Blender displaces along object or world axes: Vector Space Tangent isn't available.")
    name = new_name("textureDeformer")
    # no texture yet: Maya's deformer moves nothing; Blender's Displace without a texture pushes by 1, an empty
    # ('NONE') texture by 0
    tex = bpy.data.textures.new(f"{name}Texture", 'NONE')
    strength = float(v["strength"])
    for ob, idx in items:
        md = _add(ob, name, 'DISPLACE', idx)
        md.texture = tex
        md.texture_coords = TEX_COORDS[v["point_space"]]
        md.direction = TEX_DIRECTION[v["direction"]]
        md.space = TEX_SPACE.get(v["vector_space"], 'LOCAL')
        md.strength = strength
        md.mid_level = -float(v["offset"]) / strength if abs(strength) > 1e-12 else 0.0
    return items[0][0]


# option window field defaults
DEFAULTS = {
    'LATTICE': {"divisions": (2, 5, 2), "center": True, "auto_parent": False},
    'DELTA_MUSH': {"iterations": 10, "step": 0.5, "pin_border": True},
    'WRAP': {"render_influence": False},
    'PROXIMITY_WRAP': {},
    'SHRINK_WRAP': {"projection": "Toward Inner Object", "bidirectional": False, "reverse": False, "offset": 0.0,
                    "along_x": False, "along_y": False, "along_z": False},
    'BEND': {"low": -1.0, "high": 1.0, "curvature": 0.0},
    'TWIST': {"low": -1.0, "high": 1.0, "end_angle": 0.0},
    'SQUASH': {"low": -1.0, "high": 1.0, "factor": 0.0},
    'FLARE': {"low": -1.0, "high": 1.0, "end_flare": 1.0},
    'SINE': {"amplitude": 0.0, "wavelength": 2.0},
    'WAVE': {"max_radius": 1.0, "amplitude": 0.0, "wavelength": 1.0},
    'TEXTURE': {"point_space": "UV", "direction": "Handle", "vector_space": "Object", "strength": 1.0,
                "offset": 0.0},
    'CURVE_WARP': {},
    'WIRE': {"envelope": 1.0, "dropoff": 1.0},             # Wire Tool settings
}


def create(context, kind, values=None):
    """Make the Maya deformer ``kind`` on the selection with ``values`` (Maya option window values; missing =
    default). Raises RuntimeError with a Maya-style message when the selection doesn't fit."""
    v = {**DEFAULTS[kind], **(values or {})}
    if kind == 'LATTICE':
        return _lattice(context, v)
    if kind == 'DELTA_MUSH':
        return _delta_mush(context, v)
    if kind == 'WRAP':
        return _surface(context, "wrap", render_influence=v["render_influence"], select_driver=False)
    if kind == 'PROXIMITY_WRAP':
        return _surface(context, "proximityWrap")
    if kind == 'SHRINK_WRAP':
        return _shrink_wrap(context, v)
    if kind == 'TEXTURE':
        return _texture(context, v)
    if kind == 'CURVE_WARP':
        return _curve_warp(context, v)
    if kind == 'WIRE':
        return _wire(context, v)
    return _nonlinear(context, kind, v)


KINDS = tuple((k, k.replace("_", " ").title(), "") for k in DEFAULTS)


class ALLSET_OT_deformer(bpy.types.Operator):
    """Make a Maya deformer on the selection with the default options (Maya Deform menu)"""
    bl_idname = "allset.deformer"
    bl_label = "Create Deformer"
    bl_options = {'REGISTER', 'UNDO'}

    kind: bpy.props.EnumProperty(items=KINDS, name="Deformer", options={'HIDDEN'})

    @classmethod
    def description(cls, context, properties):
        return f"Maya Deform > {properties.kind.replace('_', ' ').title()}: the Blender modifier that does the same"

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


# --- Paint Weights -------------------------------------------------------------------------------------------

def _paint_candidates(context):
    """[(mesh, modifiers to prefer)]: the selected meshes, and the meshes a selected handle / lattice deforms
    (that handle's own deformer first)."""
    obs = [context.active_object] if context.active_object is not None else []
    obs += [o for o in context.selected_objects if o not in obs]
    out = []
    for ob in obs:
        if ob.type == 'MESH':
            out.append((ob, []))
        for md in driven_modifiers(ob):
            out.append((md.id_data, [md]))
        if ob.type == 'CURVE':                     # a wire curve: the meshes its kit wires deform
            from . import wire_deformer
            out.extend((o, [md]) for o, md in wire_deformer.wires_of_curve(ob))
    return out


def paint_group(ob, kind, prefer=()):
    """The vertex group that holds ``ob``'s weights of its newest deformer of Maya type ``kind`` (``prefer``:
    these modifiers first; None: no such deformer)."""
    if ob.type != 'MESH':
        return None
    if kind == "blendShape":
        key = ob.data.shape_keys
        if key is None or len(key.key_blocks) < 2:
            return None
        vg = ob.vertex_groups.get(key.name) or ob.vertex_groups.new(name=key.name)
        if not any(vg.index == g.group for v in ob.data.vertices for g in v.groups):
            vg.add(list(range(len(ob.data.vertices))), 1.0, 'REPLACE')     # Maya base weights 1
        for kb in key.key_blocks[1:]:
            if not kb.vertex_group:
                kb.vertex_group = vg.name
        return vg.name
    for md in list(prefer) + list(reversed(ob.modifiers)):
        group = getattr(md, "vertex_group", "") or (md.name if md.type == 'NODES' else "")   # a kit wire: its name
        if node_type(md) == kind and group in ob.vertex_groups:
            return group
    return None


class ALLSET_OT_paint_deformer_weights(bpy.types.Operator):
    """Paint the weights of the selected object's deformer of this kind: Weight Paint on the deformer's vertex
    group (Maya Deform > Paint Weights)"""
    bl_idname = "allset.paint_deformer_weights"
    bl_label = "Paint Deformer Weights"
    bl_options = {'REGISTER', 'UNDO'}

    kind: bpy.props.StringProperty(name="Deformer", options={'HIDDEN'})

    def execute(self, context):
        if context.mode not in {'OBJECT', 'PAINT_WEIGHT'}:
            bpy.ops.object.mode_set(mode='OBJECT')
        for ob, prefer in _paint_candidates(context):
            group = paint_group(ob, self.kind, prefer)
            if group is None:
                continue
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            _select_only(context, [ob], ob)
            ob.vertex_groups.active_index = ob.vertex_groups[group].index
            bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
            return {'FINISHED'}
        self.report({'WARNING'}, f"No {self.kind} deformer on the selected objects.")
        return {'CANCELLED'}


classes = (ALLSET_OT_deformer, ALLSET_OT_paint_deformer_weights)
