"""#103: Create > Polygon Primitives (Disc ... Ultra Shape) and Create > NURBS Primitives option boxes open
Maya's option windows (default values) and fill the kit's Maya
creation node (operators/option_windows_prims.py)."""

from importlib import import_module

import bpy

import kit

ow = import_module(kit.MODULE + ".operators.option_windows")
prims = import_module(kit.MODULE + ".operators.option_windows_prims")
create = import_module(kit.MODULE + ".operators.create")
prim_history = import_module(kit.MODULE + ".operators.prim_history")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
menu_map = import_module(kit.MODULE + ".ui.menu_map")

KINDS = {w.key: w.match[1]["kind"] for w in prims.WINDOWS}


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for w in prims.WINDOWS:
        ow.store(w.key, None)


def _run(key, **values):
    res = ow.run(ow._BY_KEY[key], bpy.context, values)
    assert not isinstance(res, str) and 'FINISHED' in res, (key, res)
    return bpy.context.active_object


def _points(ob):
    """Vertex count of a mesh, CV count of a curve / surface, summed over nurbsSquare / nurbsCube parts."""
    if ob.type == 'MESH':
        return len(ob.data.vertices)
    if ob.type in {'CURVE', 'SURFACE'}:
        return sum(len(sp.points) for sp in ob.data.splines)
    return sum(_points(c) for c in ob.children)


def _attrs(ob):
    owner, node = prim_history.node_of(ob)
    assert node is not None, ob.name
    return node["attrs"]


def test_windows_wired_to_the_create_menu():
    keys = [w.key for w in prims.WINDOWS]
    assert len(keys) == 19 and len(set(keys)) == 19, keys
    for w in prims.WINDOWS:
        assert ow._BY_KEY.get(w.key) is w, f"{w.key}: not in option_windows.WINDOWS (_extend)"
        assert hasattr(bpy.ops.allset, "opt_" + w.key), w.key
        assert w.action == "Create" and w.title.endswith("Options"), (w.key, w.title, w.action)
        path = next(p for p, a in menu_map.MAP.items() if p.startswith("Create/") and ow.find(a) is w)
        assert ow.find_path(path) is w and menu_sets.option_kind(path) == "window", (w.key, path)


def test_default_window_builds_the_plain_menu_object():
    for w in prims.WINDOWS:
        _clear()
        plain = create.create(bpy.context, KINDS[w.key])
        n_plain, attrs_plain = _points(plain), _attrs(plain)
        ob = _run(w.key)
        assert ob is not plain and ob.type == plain.type, (w.key, ob.type, plain.type)
        assert _points(ob) == n_plain, (w.key, _points(ob), n_plain)
        attrs = _attrs(ob)
        for name, v in attrs_plain.items():
            assert abs(float(attrs[name]) - float(v)) < 1e-6, (w.key, name, attrs[name], v)


def test_nurbs_windows_make_surfaces_and_curves():
    want = {'NURBS_SPHERE': 'SURFACE', 'NURBS_CYLINDER': 'SURFACE', 'NURBS_CONE': 'SURFACE', 'NURBS_PLANE': 'SURFACE',
            'NURBS_TORUS': 'SURFACE', 'NURBS_CIRCLE': 'CURVE'}
    for key, kind in KINDS.items():
        if not kind.startswith("NURBS"):
            continue
        _clear()
        ob = _run(key)
        if kind in want:
            assert ob.type == want[kind], (key, ob.type)
        else:      # nurbsCube = six surfaces, nurbsSquare = four curves under a group
            types = {c.type for c in ob.children}
            assert types == ({'SURFACE'} if kind == 'NURBS_CUBE' else {'CURVE'}), (key, types)


def test_changed_fields_reach_the_node():
    _clear()
    cases = [
        ("poly_disc", {"sides": 6, "subdivision_mode": "Pie"}, {"sides": 6, "subdivisionMode": 2}),
        ("poly_platonic", {"primitive": "Cube", "subdivisions": 2}, {"primitive": 1, "subdivisions": 2}),
        ("poly_pyramid", {"number_of_sides": "5", "subdivisionsHeight": 3}, {"numberOfSides": 5, "subdivisionsHeight": 3}),
        ("poly_prism", {"numberOfSides": 6, "length": 4.0}, {"numberOfSides": 6, "length": 4.0}),
        ("poly_pipe", {"subdivisionsAxis": 8, "thickness": 0.25}, {"subdivisionsAxis": 8, "thickness": 0.25}),
        ("poly_helix", {"coils": 5.0, "direction": "Clockwise"}, {"coils": 5.0, "direction": 0}),
        ("poly_gear", {"sides": 10, "taper": 0.5}, {"sides": 10, "taper": 0.5}),
        ("poly_soccer_ball", {"radius": 2.0}, {"radius": 2.0}),
        ("poly_soccer_ball", {"sideLength": 1.0}, {"radius": 1.0 / 0.4036}),   # Maya links side length -> radius
        ("poly_super_ellipse", {"horizontalDivisions": 8, "ellipse0": 2.0}, {"horizontalDivisions": 8, "ellipse0": 2.0}),
        ("poly_ultra_shape", {"shape": "Spherical Harmonics", "harmonics0": 3.0}, {"shape": 1, "harmonics0": 3.0}),
        ("nurbs_sphere", {"sections": 6, "radius": 2.0, "degree": "Linear"}, {"sections": 6, "radius": 2.0, "degree": 1}),
        ("nurbs_cylinder", {"radius": 2.0, "height": 6.0}, {"radius": 2.0, "heightRatio": 3.0}),
        ("nurbs_cone", {"height": 1.0, "spans": 3}, {"heightRatio": 1.0, "spans": 3}),
        ("nurbs_torus", {"radius": 2.0, "minor_radius": 0.5, "minor_sweep": 180.0},
         {"heightRatio": 0.25, "minorSweep": 180.0}),
        ("nurbs_plane", {"width": 2.0, "length": 6.0, "patches_u": 3}, {"width": 2.0, "lengthRatio": 3.0, "patchesU": 3}),
        ("nurbs_cube", {"width": 2.0, "height": 1.0, "patches_v": 2}, {"heightRatio": 0.5, "patchesV": 2}),
        ("nurbs_circle", {"sections": 12, "sweep": 180.0, "axis": "Z"}, {"sections": 12, "sweep": 180.0, "normalZ": 1.0}),
        ("nurbs_square", {"side1": 3.0, "spans_per_side": 2}, {"sideLength1": 3.0, "spansPerSide": 2}),
        ("nurbs_sphere", {"pivot": "User defined", "pivot_point": (1.0, 2.0, 3.0), "axis": "Free",
                          "axis_definition": (1.0, 1.0, 0.0)},
         {"pivotX": 1.0, "pivotY": 2.0, "pivotZ": 3.0, "axisX": 1.0, "axisY": 1.0, "axisZ": 0.0}),
    ]
    for key, values, want in cases:
        ob = _run(key, **values)
        attrs = _attrs(ob)
        for name, v in want.items():
            assert abs(float(attrs[name]) - float(v)) < 1e-4, (key, name, attrs[name], v)


def test_changed_fields_change_the_geometry():
    _clear()
    for key, values in (("poly_disc", {"sides": 6}), ("poly_pipe", {"subdivisionsAxis": 8}),
                        ("poly_gear", {"sides": 10}), ("poly_super_ellipse", {"verticalDivisions": 8}),
                        ("nurbs_sphere", {"sections": 6}), ("nurbs_circle", {"sections": 12}),
                        ("nurbs_square", {"spans_per_side": 3})):
        n0 = _points(_run(key))
        n1 = _points(_run(key, **values))
        assert n1 != n0, (key, n0, n1)
    # Axis X: the pipe lies along Blender X (polyPipe is half its Height attribute tall);
    # Create UVs off: no UV map
    ob = _run("poly_pipe", axis="X", create_uvs=False, height=8.0)
    dims = ob.dimensions
    assert dims.x > dims.y and dims.x > dims.z and not ob.data.uv_layers, (tuple(dims), len(ob.data.uv_layers))
    ob = _run("poly_ultra_shape", create_uvs="None")
    assert not ob.data.uv_layers


def test_lengths_follow_the_maya_unit():
    _clear()
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'CENTIMETERS', 1.0     # Maya Workflow Kit template
    k = create.units.maya_unit(bpy.context.scene)
    ob = _run("poly_pipe", radius=3.0)
    bpy.context.view_layer.update()
    assert abs(ob.dimensions.x - 6.0 * k) < 1e-5, (ob.dimensions.x, k)
    us.length_unit, us.scale_length = 'METERS', 1.0
