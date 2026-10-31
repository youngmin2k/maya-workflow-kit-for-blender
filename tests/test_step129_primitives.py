"""Step 129 (#11, #12): Maya primitive topology and creation history nodes in Channel Box INPUTS.

Counts: Create menu default option boxes.
"""

from importlib import import_module

import bpy

import kit

prim_shapes = import_module(kit.MODULE + ".operators.prim_shapes")
prim_history = import_module(kit.MODULE + ".operators.prim_history")
history = import_module(kit.MODULE + ".operators.history")
creation_inputs = import_module(kit.MODULE + ".ui.creation_inputs")
attribute_editor = import_module(kit.MODULE + ".ui.attribute_editor")

# Create menu item -> Maya node, (vertices, edges, faces), face sizes (menu default settings)
MAYA_MENU = {
    'CUBE': ("polyCube", (8, 12, 6), {4: 6}),
    'SPHERE': ("polySphere", (382, 780, 400), {4: 360, 3: 40}),
    'CYLINDER': ("polyCylinder", (42, 100, 60), {4: 20, 3: 40}),
    'CONE': ("polyCone", (21, 40, 21), {20: 1, 3: 20}),
    'TORUS': ("polyTorus", (400, 800, 400), {4: 400}),
    'PLANE': ("polyPlane", (121, 220, 100), {4: 100}),
    'DISC': ("polyDisc", (61, 108, 48), {4: 48}),
    'PLATONIC': ("polyPlatonic", (12, 30, 20), {3: 20}),
    'PYRAMID': ("polyPyramid", (5, 8, 5), {4: 1, 3: 4}),
    'PRISM': ("polyPrism", (6, 9, 5), {4: 3, 3: 2}),
}

# node, attributes -> expected (vertices, edges, faces) for non-default values
VARIANTS = [
    ("polyCube", dict(subdivisionsWidth=2, subdivisionsHeight=3, subdivisionsDepth=4), (54, 104, 52)),
    ("polySphere", dict(subdivisionsAxis=8, subdivisionsHeight=4), (26, 56, 32)),
    ("polySphere", dict(subdivisionsAxis=6, subdivisionsHeight=3), (14, 30, 18)),
    ("polyCylinder", dict(subdivisionsCaps=0), (40, 60, 22)),
    ("polyCylinder", dict(subdivisionsCaps=2), (82, 180, 100)),
    ("polyCylinder", dict(subdivisionsCaps=3), (122, 260, 140)),
    ("polyCylinder", dict(subdivisionsAxis=6, subdivisionsHeight=2, subdivisionsCaps=2), (32, 66, 36)),
    ("polyCylinder", dict(subdivisionsAxis=6, subdivisionsCaps=3, roundCap=True), (38, 78, 42)),
    ("polyCone", dict(subdivisionsCap=1), (22, 60, 40)),
    ("polyCone", dict(subdivisionsCap=2), (42, 100, 60)),
    ("polyCone", dict(subdivisionsAxis=6, subdivisionsHeight=3, subdivisionsCap=2), (26, 54, 30)),
    ("polyTorus", dict(subdivisionsAxis=6, subdivisionsHeight=4), (24, 48, 24)),
    ("polyPlane", dict(subdivisionsWidth=2, subdivisionsHeight=3), (12, 17, 6)),
    ("polyPyramid", dict(numberOfSides=5, subdivisionsHeight=2, subdivisionsCaps=2), (17, 35, 20)),
    ("polyPyramid", dict(numberOfSides=3), (4, 6, 4)),
    ("polyPrism", dict(numberOfSides=5, subdivisionsHeight=2, subdivisionsCaps=2), (27, 55, 30)),
    ("polyPrism", dict(subdivisionsCaps=1), (8, 15, 9)),
    ("polyDisc", dict(sides=4, subdivisionMode=0, subdivisions=1), (9, 12, 4)),
    ("polyDisc", dict(sides=6, subdivisionMode=4, subdivisions=2), (37, 60, 24)),
    ("polyDisc", dict(sides=3, subdivisionMode=1, subdivisions=3), (15, 30, 16)),
    ("polyDisc", dict(sides=4, subdivisionMode=1, subdivisions=3), (25, 60, 36)),
    ("polyDisc", dict(sides=4, subdivisionMode=2, subdivisions=3), (21, 56, 36)),
    ("polyDisc", dict(sides=6, subdivisionMode=3, subdivisions=2), (19, 36, 18)),
    ("polyPlatonic", dict(primitive=0), (4, 6, 4)),
    ("polyPlatonic", dict(primitive=1), (8, 12, 6)),
    ("polyPlatonic", dict(primitive=2), (6, 12, 8)),
    ("polyPlatonic", dict(primitive=3), (20, 30, 12)),
    ("polyPlatonic", dict(subdivisionMode=0, subdivisions=1), (62, 120, 60)),
    ("polyPlatonic", dict(subdivisionMode=1, subdivisions=1), (42, 120, 80)),
    ("polyPlatonic", dict(subdivisionMode=2, subdivisions=1), (32, 90, 60)),
    ("polyPlatonic", dict(subdivisionMode=3, subdivisions=2), (152, 330, 180)),
    ("polyPlatonic", dict(primitive=1, subdivisionMode=1, subdivisions=2), (50, 144, 96)),
]

# NURBS: Create menu item -> node, [(Maya CVs u x v with the periodic overlap removed, cyclic u, cyclic v)] per shape
MAYA_NURBS = {
    'NURBS_CIRCLE': ("makeNurbCircle", [((1, 8), True, False)]),
    'NURBS_SQUARE': ("makeNurbsSquare", [((1, 4), False, False)] * 4),
    'NURBS_SPHERE': ("makeNurbSphere", [((7, 8), True, False)]),
    'NURBS_CYLINDER': ("makeNurbCylinder", [((4, 8), True, False)]),
    'NURBS_CONE': ("makeNurbCone", [((4, 8), True, False)]),
    'NURBS_PLANE': ("makeNurbPlane", [((4, 4), False, False)]),
    'NURBS_TORUS': ("makeNurbTorus", [((4, 8), True, True)]),
    'NURBS_CUBE': ("makeNurbCube", [((4, 4), False, False)] * 6),
}


def _fresh():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.curves):
        for data in list(coll):
            coll.remove(data)
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'METERS', 1.0


def _make(kind):
    assert bpy.ops.allset.create(kind=kind) == {'FINISHED'}, kind
    return bpy.context.view_layer.objects.active


def _counts(me):
    sizes = {}
    for p in me.polygons:
        sizes[len(p.vertices)] = sizes.get(len(p.vertices), 0) + 1
    return (len(me.vertices), len(me.edges), len(me.polygons)), sizes


def _shape_counts(shape):
    edges = {frozenset((f[i], f[i - 1])) for f in shape.faces for i in range(len(f))}
    return len(shape.verts), len(edges), len(shape.faces)


def test_menu_primitives_match_maya_topology():
    _fresh()
    for kind, (node_type, counts, sizes) in MAYA_MENU.items():
        ob = _make(kind)
        got, got_sizes = _counts(ob.data)
        assert got == counts and got_sizes == sizes, (kind, got, got_sizes, counts, sizes)
        owner, node = prim_history.node_of(ob)
        assert node is not None and node["type"] == node_type and node["name"] == f"{node_type}1", (kind, node)
        assert ob.data.uv_layers.get("map1") is not None, kind


def test_cylinder_caps_are_triangle_fans_around_a_centre_vertex():
    _fresh()
    ob = _make('CYLINDER')
    me = ob.data
    centres = [v for v in me.vertices if abs(v.co.x) < 1e-6 and abs(v.co.y) < 1e-6]
    assert len(centres) == 2 and sorted(round(v.co.z, 5) for v in centres) == [-1.0, 1.0], [v.co for v in centres]
    for c in centres:
        fan = [p for p in me.polygons if c.index in p.vertices]
        assert len(fan) == 20 and all(len(p.vertices) == 3 for p in fan), len(fan)
    assert all(len(p.vertices) <= 4 for p in me.polygons)   # no n-gon cap (#12)
    # Maya: caps rims hard, the 20-sided sides soft
    sharp = me.attributes.get("sharp_edge")
    assert sharp is not None and sum(1 for d in sharp.data if d.value) == 40


def test_variants_match_maya_counts():
    for node_type, values, counts in VARIANTS:
        got = _shape_counts(prim_shapes.build(node_type, values))
        assert got == counts, (node_type, values, got, counts)


def test_nurbs_primitives_match_maya_cvs():
    _fresh()
    for kind, (node_type, shapes) in MAYA_NURBS.items():
        ob = _make(kind)
        parts = sorted((c for c in ob.children), key=lambda c: c[prim_history.PART]) if ob.type == 'EMPTY' else [ob]
        assert len(parts) == len(shapes), (kind, len(parts))
        for part, ((rows, cols), cu, cv) in zip(parts, shapes):
            sp = part.data.splines[0]
            assert len(part.data.splines) == 1 and sp.type == 'NURBS', kind
            assert (sp.point_count_v, sp.point_count_u) == (rows, cols), (kind, sp.point_count_v, sp.point_count_u)
            assert sp.use_cyclic_u == cu and (rows == 1 or sp.use_cyclic_v == cv), (kind, sp.use_cyclic_u)
            assert sp.order_u == 4, kind
        owner, node = prim_history.node_of(ob)
        assert node is not None and node["type"] == node_type and node["name"] == f"{node_type}1", (kind, node)
    # the Maya circle: periodic cubic, CVs at 6 / (4 + 2 cos 45) = 1.108194 x radius, normal +Y (Blender +Z)
    circle = bpy.data.objects["nurbsCircle1"]
    for p in circle.data.splines[0].points:
        assert abs(p.co.z) < 1e-6 and abs((p.co.x ** 2 + p.co.y ** 2) ** 0.5 - 1.108194) < 1e-5, tuple(p.co)


def test_inputs_rows_and_editing_subdivisions_caps_rebuilds():
    _fresh()
    ob = _make('CYLINDER')
    ob.location = (3.0, 0.0, 0.0)
    mat = ob.data.materials[0]
    props = bpy.context.scene.allset_creation
    assert props.subdivisionsCaps_text == "1" and props.subdivisionsAxis_text == "20"
    assert props.radius_text == "1" and props.height_text == "2", (props.radius_text, props.height_text)
    rows = creation_inputs.node_rows("polyCylinder")
    assert rows[:9] == ["heightBaseline", "radius", "height", "subdivisionsAxis", "subdivisionsHeight",
                        "subdivisionsCaps", "createUVs", "roundCap", "roundCapHeightCompensation"]
    props.subdivisionsCaps_text = "2"
    assert _counts(ob.data)[0] == (82, 180, 100), _counts(ob.data)
    assert props.subdivisionsCaps_text == "2"
    assert tuple(ob.location) == (3.0, 0.0, 0.0) and ob.data.materials[0] is mat and ob.name == "pCylinder1"
    props.subdivisionsAxis_text = "-=14"                      # Maya relative entry: 20 - 14 = 6
    assert props.subdivisionsAxis_text == "6" and _counts(ob.data)[0][0] == 6 * 2 + 6 * 2 + 2
    props.radius_text = "*=2"
    assert abs(max(v.co.x for v in ob.data.vertices) - 2.0) < 1e-5
    # Attribute Editor: a polyCylinder1 tab after the shape
    keys = [t[0] for t in attribute_editor.tabs(ob)]
    assert ("CH", "polyCylinder1", "polyCylinder") in attribute_editor.tabs(ob) and keys.index("CH") > keys.index("S")


def test_nurbs_circle_inputs_rebuild():
    _fresh()
    ob = _make('NURBS_CIRCLE')
    props = bpy.context.scene.allset_creation
    assert props.radius_text == "1" and props.sections_text == "8" and props.degree_text == "Cubic"
    assert props.normalY_text == "1" and props.sweep_text == "360", (props.normalY_text, props.sweep_text)
    props.radius_text = "2"
    pts = ob.data.splines[0].points
    assert abs(pts[0].co.to_3d().length - 2 * 1.108194) < 1e-4
    props.sections_text = "+=4"
    assert len(ob.data.splines[0].points) == 12 and props.sections_text == "12"
    props.sweep_text = "180"                                    # an open arc: 12 spans -> 15 CVs, clamped
    sp = ob.data.splines[0]
    assert len(sp.points) == 15 and not sp.use_cyclic_u and sp.use_endpoint_u
    props.degree_text = "Linear"
    assert ob.data.splines[0].order_u == 2 and len(ob.data.splines[0].points) == 13


def test_nurbs_surface_and_group_rebuild():
    _fresh()
    sphere = _make('NURBS_SPHERE')
    props = bpy.context.scene.allset_creation
    assert props.spans_text == "4" and props.sections_text == "8"
    props.spans_text = "6"
    sp = sphere.data.splines[0]
    assert (sp.point_count_v, sp.point_count_u) == (9, 8), (sp.point_count_v, sp.point_count_u)
    assert sphere.data.materials[0] is not None and sphere.name == "nurbsSphere1"
    square = _make('NURBS_SQUARE')
    part = square.children[0]
    bpy.context.view_layer.objects.active = part
    assert props.spansPerSide_text == "1"
    props.spansPerSide_text = "3"
    assert all(len(c.data.splines[0].points) == 6 for c in square.children)


def test_multi_select_edits_every_node_of_that_type():
    _fresh()
    a = _make('CYLINDER')
    b = _make('CYLINDER')
    c = _make('CUBE')
    assert prim_history.node_of(b)[1]["name"] == "polyCylinder2"
    for ob in (a, b, c):
        ob.select_set(True)
    bpy.context.view_layer.objects.active = b
    bpy.context.scene.allset_creation.subdivisionsCaps_text = "0"
    assert _counts(a.data)[0] == (40, 60, 22) and _counts(b.data)[0] == (40, 60, 22)
    assert _counts(c.data)[0] == (8, 12, 6)


def test_edits_and_delete_history_drop_the_node():
    _fresh()
    ob = _make('SPHERE')
    assert creation_inputs.has_node(ob)
    ob.data.vertices[0].co.z += 0.5                 # a Blender edit the node can't replay: the node hides
    assert not creation_inputs.has_node(ob)
    ob.data.vertices[0].co.z -= 0.5
    assert creation_inputs.has_node(ob)
    baked, _notes = history.delete_history(bpy.context, [ob])
    assert baked == 1 and not creation_inputs.has_node(ob) and prim_history.owner_of(ob) is None
    assert _counts(ob.data)[0] == (382, 780, 400)    # the shape stays


def test_edit_mode_keeps_the_node():
    _fresh()
    ob = _make('CUBE')
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        assert creation_inputs.has_node(ob)
        bpy.context.scene.allset_creation.subdivisionsWidth_text = "3"
        import bmesh
        assert len(bmesh.from_edit_mesh(ob.data).verts) == 16
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')
    assert len(ob.data.vertices) == 16 and creation_inputs.has_node(ob)


def test_duplicate_has_no_creation_node():
    """Maya Duplicate copies the shape, not its input graph: pCube2 has no polyCube node (instances share it)."""
    _fresh()
    ob = _make('CUBE')
    bpy.ops.allset.duplicate()
    copy = bpy.context.view_layer.objects.active
    assert copy is not ob and creation_inputs.has_node(ob) and not creation_inputs.has_node(copy), copy.name
