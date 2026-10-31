# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya creation history for primitives (#11, #12): ``polyCube1`` / ``makeNurbCircle1`` ... nodes.

Maya keeps the creation node upstream of the shape; its attributes (Width, Subdivisions Caps, Radius, Sections ...)
show in the Channel Box INPUTS and the Attribute Editor, and editing one rebuilds the shape. Blender has no such
node, so the kit stores it as an ID property on the shape data (``Mesh`` / ``Curve``; on the group empty for
nurbsSquare / nurbsCube, whose parts are four / six curves) and rebuilds the data from ``prim_shapes`` when a value
changes. Object, transforms and materials stay; Delete History drops the node (like the extrusion record).

A node is shown only while the shape still is what the kit built (a signature of the points): Blender edits made
after creation would be thrown away by a rebuild, and Maya would keep them as tweaks the kit can't replay.
"""

import hashlib

import bpy

from . import naming, prim_shapes, units

KEY = "allset_history"        # the node, on the shape data or the group empty
PART = "allset_history_part"  # nurbsSquare / nurbsCube part index, on the part objects
UV_NAME = "map1"              # default UV set name, like Maya

# Create menu kind -> (Maya node type, transform base name)
KIND_NODES = {
    'CUBE': ("polyCube", "pCube"), 'SPHERE': ("polySphere", "pSphere"), 'CYLINDER': ("polyCylinder", "pCylinder"),
    'CONE': ("polyCone", "pCone"), 'TORUS': ("polyTorus", "pTorus"), 'PLANE': ("polyPlane", "pPlane"),
    'DISC': ("polyDisc", "pDisc"), 'PLATONIC': ("polyPlatonic", "pPlatonic"), 'PYRAMID': ("polyPyramid", "pPyramid"),
    'PRISM': ("polyPrism", "pPrism"),
    'PIPE': ("polyPipe", "pPipe"), 'HELIX': ("polyHelix", "pHelix"), 'GEAR': ("polyGear", "pGear"),
    'SOCCER_BALL': ("polyPrimitiveMisc", "pSolid"), 'SUPER_ELLIPSE': ("polySuperShape", "pSuperShape"),
    'SPHERICAL_HARMONICS': ("polySuperShape", "pSuperShape"), 'ULTRA_SHAPE': ("polySuperShape", "pSuperShape"),
    'NURBS_SPHERE': ("makeNurbSphere", "nurbsSphere"), 'NURBS_CYLINDER': ("makeNurbCylinder", "nurbsCylinder"),
    'NURBS_CONE': ("makeNurbCone", "nurbsCone"), 'NURBS_PLANE': ("makeNurbPlane", "nurbsPlane"),
    'NURBS_TORUS': ("makeNurbTorus", "nurbsTorus"), 'NURBS_CIRCLE': ("makeNurbCircle", "nurbsCircle"),
    'NURBS_SQUARE': ("makeNurbsSquare", "nurbsSquare"), 'NURBS_CUBE': ("makeNurbCube", "nurbsCube"),
}
# Create menu items that share a node type but start from other values (polySuperShape -shape)
KIND_VALUES = {'SUPER_ELLIPSE': {"shape": 0}, 'SPHERICAL_HARMONICS': {"shape": 1}, 'ULTRA_SHAPE': {"shape": 2}}
GROUPS = {"makeNurbsSquare", "makeNurbCube"}
SURFACES = {"makeNurbSphere", "makeNurbCylinder", "makeNurbCone", "makeNurbPlane", "makeNurbTorus", "makeNurbCube"}


def history_on(context):
    """Maya's Construction History toggle (Status Line, ``cmds.constructionHistory(toggle=...)``): on by default, one
    state for the session that File > New keeps,
    hence a WindowManager property (ui/input_line.py)."""
    return getattr(context.window_manager, "allset_construction_history", True)


def to_blender(p, k):
    """Maya Y-up point -> Blender Z-up, scaled by the Maya unit: (x, y, z) -> (x, -z, y) * k."""
    return (p[0] * k, -p[2] * k, p[1] * k)


# --- the node ---------------------------------------------------------------------------------------------------

def owner_of(ob):
    """The ID holding ``ob``'s creation node (its data, or the nurbsSquare / nurbsCube group), or None."""
    if ob is None or not isinstance(ob, bpy.types.Object):
        return None
    data = ob.data
    if data is not None and KEY in data:
        return data
    if KEY in ob:
        return ob
    if PART in ob and ob.parent is not None and KEY in ob.parent:
        return ob.parent
    return None


def node_dict(owner):
    return owner[KEY].to_dict() if owner is not None and KEY in owner else None


def attrs(owner):
    node = node_dict(owner)
    if node is None:
        return {}
    out = prim_shapes.defaults(node["type"])
    out.update({k: v for k, v in node["attrs"].items() if k in out})
    if "createUVs" in out and "createUVs" not in node["attrs"] and node.get("createUVs") == 0:
        out["createUVs"] = 0          # a node saved before Create UVs was a Channel Box attribute
    return out


def uvs_on(values, extra):
    """Whether the shape gets UVs: the node's own Create UVs (polyCylinder), else the stored create option."""
    if "createUVs" in values:
        return values["createUVs"] != 0
    return extra.get("createUVs", 1) != 0


def _sig_mesh(me, bm=None):
    """Counts + rounded vertex positions; the same for object-mode mesh data and an edit-mode bmesh."""
    import numpy as np
    h = hashlib.md5()
    if bm is not None:
        h.update(f"{len(bm.verts)}/{len(bm.faces)}".encode())
        co = np.array([c for v in bm.verts for c in v.co], dtype=np.float32)
    else:
        h.update(f"{len(me.vertices)}/{len(me.polygons)}".encode())
        co = np.empty(len(me.vertices) * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
    h.update(np.round(co.astype(np.float64), 4).tobytes())
    return h.hexdigest()


def _sig_curve(cu):
    h = hashlib.md5()
    for sp in cu.splines:
        h.update(f"{len(sp.points)}|".encode())
        for p in sp.points:
            h.update(("%.4f,%.4f,%.4f;" % tuple(p.co[:3])).encode())
    return h.hexdigest()


def _parts(group):
    return sorted((c for c in group.children if PART in c), key=lambda c: c[PART])


def signature(owner):
    if isinstance(owner, bpy.types.Mesh):
        ob = next((o for o in bpy.data.objects if o.data is owner and o.mode == 'EDIT'), None)
        if ob is not None:
            import bmesh
            return _sig_mesh(owner, bmesh.from_edit_mesh(owner))
        return _sig_mesh(owner)
    if isinstance(owner, bpy.types.Curve):
        return _sig_curve(owner)
    if isinstance(owner, bpy.types.Object):
        return "+".join(_sig_curve(c.data) for c in _parts(owner) if c.data is not None)
    return ""


def is_valid(owner):
    """The shape still is what the kit built (else a rebuild would lose the user's edits)."""
    node = node_dict(owner)
    if node is None:
        return False
    if isinstance(owner, bpy.types.Curve) and any(o.mode == 'EDIT' for o in bpy.data.objects if o.data is owner):
        return False   # curve edit mode keeps its own copy of the points
    try:
        return signature(owner) == node.get("sig")
    except (ReferenceError, AttributeError, ValueError):
        return False


def node_of(ob):
    """(owner, node dict) of ``ob``'s live creation node, or (None, None)."""
    owner = owner_of(ob)
    if owner is None or not is_valid(owner):
        return None, None
    return owner, node_dict(owner)


def _next_name(node_type):
    taken = set()
    for coll in (bpy.data.meshes, bpy.data.curves, bpy.data.objects):
        for idb in coll:
            if idb.users and KEY in idb:
                taken.add(idb[KEY].get("name", ""))
    from . import naming
    return f"{node_type}{naming.next_number(node_type, taken)}"   # Maya: one past the highest


def drop(ob):
    """Delete History: forget ``ob``'s creation node (the shape stays as it is). True when there was one."""
    owner = owner_of(ob)
    if owner is None:
        return False
    del owner[KEY]
    if isinstance(owner, bpy.types.Object):
        for c in owner.children:
            if PART in c:
                del c[PART]
    return True


# --- building ---------------------------------------------------------------------------------------------------

def fill_bmesh(bm, shape, k, uvs=True):
    """Write a ``prim_shapes.Mesh`` into an empty bmesh (Maya units -> Blender, scaled by ``k``)."""
    verts = [bm.verts.new(to_blender(p, k)) for p in shape.verts]
    bm.verts.index_update()
    if shape.edges:     # Maya's edge ids = the bmesh edge index (bevel_maya.maya_edge_ids)
        for a, b in shape.edges:
            bm.edges.new((verts[a], verts[b]))
    uv = bm.loops.layers.uv.new(UV_NAME) if uvs and shape.uvs is not None else None
    flat = shape.hard == prim_shapes.ALL
    for fi, f in enumerate(shape.faces):
        face = bm.faces.new([verts[i] for i in f])
        face.smooth = not flat
        if uv is not None:
            for loop, t in zip(face.loops, shape.uvs[fi]):
                loop[uv].uv = t
    if not flat and shape.hard:
        bm.edges.ensure_lookup_table()
        for e in bm.edges:
            if frozenset((e.verts[0].index, e.verts[1].index)) in shape.hard:
                e.smooth = False
    bm.normal_update()


def _write_mesh(me, shape, k, uvs):
    import bmesh
    ob = next((o for o in bpy.data.objects if o.data is me and o.mode == 'EDIT'), None)
    if ob is not None:
        bm = bmesh.from_edit_mesh(me)
        bm.clear()
        for layer in list(bm.loops.layers.uv.values()):
            bm.loops.layers.uv.remove(layer)
        fill_bmesh(bm, shape, k, uvs)
        bmesh.update_edit_mesh(me, loop_triangles=True, destructive=True)
        return _sig_mesh(me, bm)
    bm = bmesh.new()
    fill_bmesh(bm, shape, k, uvs)
    for layer in list(me.uv_layers):
        me.uv_layers.remove(layer)
    bm.to_mesh(me)
    bm.free()
    me.update()
    return _sig_mesh(me)


def _curve_points(cu, patch, k):
    """Fill curve / surface datablock ``cu`` (one spline) with ``patch`` (needs the rows already made)."""
    sp = cu.splines[0]
    pts = [p for row in patch.points for p in row]
    for p, q in zip(sp.points, pts):
        p.co = (*to_blender(q, k), 1.0)
    sp.order_u = min(patch.order_u, len(patch.points[0]))
    sp.use_cyclic_u = patch.cyclic_u
    sp.use_endpoint_u = not patch.cyclic_u
    if len(patch.points) > 1:
        sp.order_v = min(patch.order_v, len(patch.points))
        sp.use_cyclic_v = patch.cyclic_v
        sp.use_endpoint_v = not patch.cyclic_v
    sp.use_smooth = True


def new_curve_data(context, name, patch, k):
    """A Curve ('CURVE' for one row, 'SURFACE' otherwise) datablock holding ``patch``.

    Blender's Python API can't add rows to a NURBS surface: the rows are made by extruding the first one in edit
    mode of a temporary object (``curve.extrude`` works in background)."""
    rows, cols = len(patch.points), len(patch.points[0])
    cu = bpy.data.curves.new(name, 'SURFACE' if rows > 1 else 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('NURBS')
    sp.points.add(cols - 1)
    if rows > 1:
        for p in sp.points:
            p.select = True
        tmp = bpy.data.objects.new(".allset_tmp_surface", cu)
        context.scene.collection.objects.link(tmp)
        layer = context.view_layer
        prev = layer.objects.active
        layer.objects.active = tmp
        try:
            bpy.ops.object.mode_set(mode='EDIT')
            for _ in range(rows - 1):
                bpy.ops.curve.extrude(mode='TRANSLATION')
            bpy.ops.object.mode_set(mode='OBJECT')
        finally:
            layer.objects.active = prev
            bpy.data.objects.remove(tmp)
    _curve_points(cu, patch, k)
    return cu


def _swap_curve(context, ob, patch, k):
    """Rebuild ``ob``'s curve data (rows may change): new datablock, same name and materials."""
    old = ob.data
    name = old.name
    mats = list(old.materials)
    settings = {a: getattr(old, a) for a in ("resolution_u", "resolution_v", "render_resolution_u",
                                              "render_resolution_v") if hasattr(old, a)}
    node = old[KEY].to_dict() if KEY in old else None
    if old.users == 1 and len(old.splines) == 1 and len(old.splines[0].points) == sum(map(len, patch.points)) \
            and (len(patch.points) == 1 or old.splines[0].point_count_v == len(patch.points)):
        _curve_points(old, patch, k)     # same layout: keep the datablock
        return old
    cu = new_curve_data(context, name + ".rebuild", patch, k)
    for m in mats:
        cu.materials.append(m)
    for a, v in settings.items():
        setattr(cu, a, v)
    ob.data = cu
    if old.users == 0:
        bpy.data.curves.remove(old)
    cu.name = name
    if node is not None:
        cu[KEY] = node
    return cu


def _store(owner, node_type, name, values, k, extra=None):
    node = {"type": node_type, "name": name, "unit": k, "attrs": values}
    if extra:
        node.update(extra)
    owner[KEY] = node
    owner[KEY]["sig"] = signature(owner)


def rebuild(context, ob, changes):
    """Set node attributes (Maya units / degrees) on ``ob``'s creation node and rebuild its shape. Returns the
    applied values, or None when ``ob`` has no live node."""
    owner, node = node_of(ob)
    if owner is None:
        return None
    ntype = node["type"]
    values = attrs(owner)
    for name, v in changes.items():
        if name in values:
            values[name] = prim_shapes.clamp(ntype, name, v)
    k = node.get("unit", 1.0)
    shape = prim_shapes.build(ntype, values)
    extra = {key: node[key] for key in ("createUVs",) if key in node}
    if ntype in prim_shapes.POLY:
        _write_mesh(owner, shape, k, uvs_on(values, extra))
    elif ntype in GROUPS:
        for part, patch in zip(_parts(owner), shape):
            _swap_curve(context, part, patch, k)
    else:
        target = next(o for o in bpy.data.objects if o.data is owner)
        owner = _swap_curve(context, target, shape[0], k)
    _store(owner, ntype, node["name"], values, k, extra)
    return values


def create_object(context, kind, values=None, maya_naming=True, create_uvs=True):
    """Build ``kind`` from its Maya node (factory values + ``values``) at the origin; returns the new object
    (for nurbsSquare / nurbsCube the group empty). The node is stored for Channel Box INPUTS. Without Maya naming
    the object gets the Create menu label ("Cube", "NURBS Circle"), like Blender's own Add menu names."""
    node_type, base = KIND_NODES[kind]
    if not maya_naming:
        from .create import KINDS
        base = KINDS[kind][0].replace(" ", "")
    vals = prim_shapes.defaults(node_type)
    for name, v in {**KIND_VALUES.get(kind, {}), **(values or {})}.items():
        if name in vals:
            vals[name] = prim_shapes.clamp(node_type, name, v)
    if not create_uvs and "createUVs" in vals:
        vals["createUVs"] = 0
    k = units.maya_unit(context.scene)
    shape = prim_shapes.build(node_type, vals)
    coll = context.collection
    extra = {} if create_uvs else {"createUVs": 0}
    create_uvs = uvs_on(vals, extra)
    if node_type in prim_shapes.POLY:
        import bmesh
        me = bpy.data.meshes.new(base + "Shape")
        bm = bmesh.new()
        fill_bmesh(bm, shape, k, create_uvs)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(base, me)
        coll.objects.link(ob)
        owner = me
    elif node_type in GROUPS:
        ob = bpy.data.objects.new(base, None)
        ob.empty_display_type = 'PLAIN_AXES'
        ob.empty_display_size = 0.0
        coll.objects.link(ob)
        if maya_naming:
            naming.apply_maya_name(ob, base, rename_data=False)
        for i, patch in enumerate(shape):
            cu = new_curve_data(context, f"{patch.name}{ob.name}Shape", patch, k)
            part = bpy.data.objects.new(f"{patch.name}{ob.name}", cu)   # Maya: topnurbsSquare1 ...
            coll.objects.link(part)
            part.parent = ob
            part[PART] = i
        owner = ob
    else:
        cu = new_curve_data(context, base + "Shape", shape[0], k)
        ob = bpy.data.objects.new(base, cu)
        coll.objects.link(ob)
        owner = cu
    if maya_naming and node_type not in GROUPS:
        naming.apply_maya_name(ob, base)
    if history_on(context):                  # off: Maya's -ch 0 primitive has no polyCube1 node
        _store(owner, node_type, _next_name(node_type), vals, k, extra)
    for o in context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    context.view_layer.objects.active = ob
    context.view_layer.update()   # bounds / dimensions right away, as after Blender's add operators
    return ob


# --- display helpers (Channel Box INPUTS / Attribute Editor) ----------------------------------------------------

ENTRY_KIND = {"length": "LENGTH", "float": "NONE", "int": "INT", "bool": "BOOL", "angle": "ROTATION"}


def entry_kind(node_type, name):
    kind = prim_shapes.spec(node_type, name)[3]
    return "ENUM" if isinstance(kind, tuple) else ENTRY_KIND[kind]


def enum_labels(node_type, name):
    kind = prim_shapes.spec(node_type, name)[3]
    if kind[0] == "enum3":
        return [str(c) for c in kind[1]], list(kind[1])
    if kind is prim_shapes.DEGREE:
        return list(kind[1]), [1, 3]
    return list(kind[1]), list(range(len(kind[1])))


def to_entry(node, name, value):
    """Maya attribute value -> the value cb_entry formats (Blender units / radians)."""
    import math
    kind = entry_kind(node["type"], name)
    if kind == "LENGTH":
        return value * node.get("unit", 1.0)
    if kind == "ROTATION":
        return math.radians(value)
    return value


def from_entry(node, name, value):
    import math
    kind = entry_kind(node["type"], name)
    if kind == "LENGTH":
        k = node.get("unit", 1.0) or 1.0
        return value / k
    if kind == "ROTATION":
        return math.degrees(value)
    return value
