"""Lane DEFORM (#34): Maya Deform menu items create Maya-like deformers (operators/deformers.py) with
Maya option windows (operators/option_windows_deform.py), Channel Box INPUTS rows and Paint Weights targets.

The Deform option windows (fields, defaults) and the deformers created with default options
(nodes, selection, Channel Box rows, paint targets), plus the Cluster / Soft Mod / Nonlinear handles."""

import math
from importlib import import_module

import bmesh
import bpy
from mathutils import Vector

import kit

ow = import_module(kit.MODULE + ".operators.option_windows")
owd = import_module(kit.MODULE + ".operators.option_windows_deform")
deformers = import_module(kit.MODULE + ".operators.deformers")
cb = import_module(kit.MODULE + ".ui.channel_box")
ae = import_module(kit.MODULE + ".ui.attribute_editor")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_data = import_module(kit.MODULE + ".ui.menu_data")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
notices = import_module(kit.MODULE + ".ui.notices")


# --- helpers ---------------------------------------------------------------------------------------

def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.lattices, bpy.data.curves, bpy.data.textures, bpy.data.shape_keys):
        for d in list(coll):
            try:
                coll.remove(d)
            except (TypeError, AttributeError):
                pass
    for w in owd.WINDOWS:
        ow.store(w.key, None)


def _select(*obs):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1]


def _cube(name="pCube1", loc=(0, 0, 0), size=1.0, scale=(1, 1, 1), cuts=3):
    """The test cube: polyCube -sx 4 -sy 4 -sz 4 (deformers made on it)."""
    bpy.ops.mesh.primitive_cube_add(size=size, location=loc)
    ob = bpy.context.active_object
    ob.name, ob.data.name = name, name + "Shape"
    ob.scale = scale
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
    bm.to_mesh(ob.data)
    bm.free()
    bpy.context.view_layer.update()
    _select(ob)
    return ob


def _run(key, **values):
    res = ow.run(ow._BY_KEY[key], bpy.context, values)
    assert not isinstance(res, str), (key, res)
    return res


def _rows(ob, md):
    """The Channel Box INPUTS rows (label, text) of modifier ``md`` with ``ob`` as lead (node expanded)."""
    _select(ob)
    cb.set_open(ob, cb.mod_node(md))
    bpy.context.scene.allset_cb.rows_sig = ""
    cb.rebuild_rows(bpy.context)
    out = []
    for r in bpy.context.scene.allset_cb.rows:
        if r.kind == "INPUT" and r.mod_type == md.type and r.nth == cb._nth_of_type(ob, md):
            out.append((cb.input_label(md, r.name), r.text))
    return out


def _evaluated(ob):
    bpy.context.view_layer.update()
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    cos = [ob.matrix_world @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    return cos


def _fields(key):
    return [(f.name, f.label, f.default) for f in ow._BY_KEY[key].fields]


# --- menu, windows ---------------------------------------------------------------------------------

PATHS = {
    "deform_lattice": "Deform/Lattice", "deform_delta_mush": "Deform/Delta Mush", "deform_wrap": "Deform/Wrap",
    "deform_shrink_wrap": "Deform/ShrinkWrap", "deform_proximity_wrap": "Deform/Proximity Wrap",
    "deform_cluster": "Deform/Cluster", "deform_soft_mod": "Deform/Soft Modification Tool",
    "deform_bend": "Deform/Nonlinear/Bend", "deform_flare": "Deform/Nonlinear/Flare",
    "deform_sine": "Deform/Nonlinear/Sine", "deform_squash": "Deform/Nonlinear/Squash",
    "deform_twist": "Deform/Nonlinear/Twist", "deform_wave": "Deform/Nonlinear/Wave", "deform_texture": "Deform/Texture",
}
# Wire / Paint Weights > Wire work (tests/test_step169_deform.py)
# Mapped: Tension / Solidify / Morph / Jiggle / Sculpt and their Paint Weights (operators/deformers_205a / _205b)
GREYED = ("Deform/Wrinkle",)


def test_menu_items_are_kit_deformers_with_windows():
    for key, path in PATHS.items():
        assert path in menu_map.MAP, path
        assert key in ow._BY_KEY, key
        assert ow.find_path(path).key == key, (path, ow.find_path(path).key)
        if path in menu_data.OPTION_BOXES:
            assert menu_sets.option_kind(path) == "window", path
        rna = getattr(bpy.ops.allset, "opt_" + key).get_rna_type()
        for f in ow._BY_KEY[key].fields:
            assert f.name in rna.properties, (key, f.name)
        spec = menu_map.spec(path)
        assert spec[1] in ("allset.deformer", "allset.cluster", "allset.soft_mod"), (path, spec)
    for path in GREYED:
        assert path not in menu_map.MAP, path
        assert notices.notice(path) is not None, path               # an honest notice, not just the category
    paint = menu_map.spec("Deform/Paint Weights/Lattice")
    assert paint == ("op", "allset.paint_deformer_weights", {"kind": "ffd"}), paint
    assert menu_map.spec("Deform/Curve Warp")[1] == "allset.deformer"


def test_window_titles_buttons_defaults_are_maya():
    # Deform option windows: title (button) and Basic tab fields in screen order
    titles = {k: (ow._BY_KEY[k].title, ow._BY_KEY[k].action) for k in PATHS}
    assert titles["deform_lattice"] == ("Lattice Options", "Create")
    assert titles["deform_soft_mod"] == ("Soft Modification Options", "Soft Modification")
    assert titles["deform_wrap"] == ("Wrap Options", "Create")
    assert titles["deform_shrink_wrap"] == ("ShrinkWrap Options", "Create")
    assert titles["deform_texture"] == ("Texture Options", "Create")
    for k in ("deform_bend", "deform_flare", "deform_sine", "deform_squash", "deform_twist", "deform_wave",
              "deform_cluster", "deform_delta_mush", "deform_proximity_wrap"):
        assert titles[k][1] == "Create" and titles[k][0].endswith(" Options"), titles[k]
    assert _fields("deform_lattice") == [("divisions", "Divisions:", (2, 5, 2)),
                                         ("center", "", True), ("auto_parent", "", False)]
    assert _fields("deform_delta_mush") == [("iterations", "Smoothing iterations:", 10),
                                            ("step", "Smoothing step:", 0.5), ("pin_border", "", True)]
    assert _fields("deform_cluster") == [("envelope", "Envelope:", 1.0)]
    assert _fields("deform_soft_mod") == [("radius", "Falloff radius:", 5.0)]
    assert _fields("deform_bend") == [("low", "Low bound:", -1.0), ("high", "High bound:", 1.0),
                                      ("curvature", "Curvature:", 0.0)]
    assert _fields("deform_twist") == [("low", "Low bound:", -1.0), ("high", "High bound:", 1.0),
                                       ("end_angle", "End angle:", 0.0)]
    assert _fields("deform_squash") == [("low", "Low bound:", -1.0), ("high", "High bound:", 1.0),
                                        ("factor", "Factor:", 0.0)]
    assert _fields("deform_flare") == [("low", "Low bound:", -1.0), ("high", "High bound:", 1.0),
                                       ("end_flare", "End flare X:", 1.0)]
    assert _fields("deform_sine") == [("amplitude", "Amplitude:", 0.0), ("wavelength", "Wavelength:", 2.0)]
    assert _fields("deform_wave") == [("max_radius", "Max radius:", 1.0), ("amplitude", "Amplitude:", 0.0),
                                      ("wavelength", "Wavelength:", 1.0)]
    assert _fields("deform_shrink_wrap") == [
        ("projection", "Projection:", "Toward Inner Object"), ("bidirectional", "", False), ("reverse", "", False),
        ("offset", "Offset:", 0.0), ("along_x", "", False), ("along_y", "", False), ("along_z", "", False)]
    assert _fields("deform_wrap") == [("render_influence", "", False)]
    assert _fields("deform_proximity_wrap") == []
    assert _fields("deform_texture") == [("point_space", "Point Space:", "UV"), ("direction", "Direction:", "Handle"),
                                         ("vector_space", "Vector Space:", "Object"), ("strength", "Strength:", 1.0),
                                         ("offset", "Offset:", 0.0)]
    # every window lists Maya's Advanced tab as not in Blender
    for k in ("deform_lattice", "deform_delta_mush", "deform_cluster", "deform_bend"):
        assert any(m.startswith("Deformation order") for m in ow._BY_KEY[k].missing), k


# --- Lattice -----------------------------------------------------------------------------------------

def test_lattice_fits_selection_with_maya_divisions():
    _clear()
    cube = _cube(loc=(2, 0, 1), scale=(1, 2, 1))
    assert bpy.ops.allset.deformer(kind='LATTICE') == {'FINISHED'}
    lat = bpy.data.objects["ffd1Lattice"]
    md = cube.modifiers["ffd1"]
    assert md.type == 'LATTICE' and md.object == lat and md.vertex_group == "ffd1"
    assert lat.data.name == "ffd1LatticeShape"
    # Maya divisions S T U = 2 5 2 (Maya Y = Blender Z): points_u / v / w = 2 2 5
    assert (lat.data.points_u, lat.data.points_v, lat.data.points_w) == (2, 2, 5)
    zs = [p.co.z for p in lat.data.points]
    assert (min(zs), max(zs)) == (-0.5, 0.5), (min(zs), max(zs))          # the lattice box = the scale
    assert (lat.location - Vector((2, 0, 1))).length < 1e-6                  # Center around selection
    assert (Vector(lat.scale) - Vector((1, 2, 1))).length < 1e-6              # the bounding box
    assert bpy.context.active_object == lat and list(bpy.context.selected_objects) == [lat]   # Maya: ffd1Lattice
    before = _evaluated(cube)
    assert all(abs(a - b) < 1e-5 for p, q in zip(before, [cube.matrix_world @ v.co for v in cube.data.vertices])
               for a, b in zip(p, q)), "a fitted lattice changes nothing"
    lat.location.z += 1.0
    after = _evaluated(cube)
    assert all(abs((q - p).z - 1.0) < 1e-4 for p, q in zip(before, after)), "moving the lattice moves the mesh"
    for pt in lat.data.points:                                       # lattice points edited after the move
        pt.co_deform.z += 0.25
    lat.data.update_tag()
    after = _evaluated(cube)
    assert all(abs((q - p).z - 1.25) < 1e-4 for p, q in zip(before, after)), "points deform in lattice space"
    assert [m.name for m in cb._inputs(cube)] == ["ffd1"]            # ffd1Base (the hook) is part of ffd1
    # INPUTS: the deformed mesh and the lattice both show ffd1 with Envelope 1
    assert _rows(cube, md) == [("Envelope", "1")], _rows(cube, md)
    assert cb.mod_node(md) in {cb.mod_node(m) for m in cb._inputs(lat)}
    assert ae.modifier_node(cube, md) == ("ffd1", "ffd")
    # ffd1LatticeShape: S / T / U Divisions 2 5 2
    assert [cb.shape_label(lat, p) for p in cb.SHAPE_PROPS['LATTICE']] == ["S Divisions", "T Divisions",
                                                                         "U Divisions"]
    assert [getattr(lat.data, p) for p in cb.SHAPE_PROPS['LATTICE']] == [2, 5, 2]


def test_lattice_window_options_and_components():
    _clear()
    cube = _cube()
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(cube.data)
    for v in bm.verts:
        v.select = v.co.z > 0.2
    bm.select_flush(True)
    bmesh.update_edit_mesh(cube.data)
    _run("deform_lattice", divisions=(3, 4, 6), auto_parent=True)
    lat = bpy.data.objects["ffd1Lattice"]
    assert (lat.data.points_u, lat.data.points_v, lat.data.points_w) == (3, 6, 4)
    assert abs(lat.location.z - 0.375) < 1e-6 and abs(lat.scale.z - 0.25) < 1e-6   # selected points only
    assert lat.parent == cube                                                    # Auto parent to selection
    vg = cube.vertex_groups["ffd1"]
    inside = {v.index for v in cube.data.vertices if any(g.group == vg.index for g in v.groups)}
    assert inside == {v.index for v in cube.data.vertices if v.co.z > 0.2}
    assert bpy.context.mode == 'OBJECT'


# --- Delta Mush ------------------------------------------------------------------------------------

def test_delta_mush_maya_defaults_and_inputs():
    _clear()
    cube = _cube()
    assert bpy.ops.allset.deformer(kind='DELTA_MUSH') == {'FINISHED'}
    md = cube.modifiers["deltaMush1"]
    assert md.type == 'CORRECTIVE_SMOOTH' and md.iterations == 10 and abs(md.factor - 0.5) < 1e-6
    assert md.use_pin_boundary and md.smooth_type == 'SIMPLE' and md.rest_source == 'ORCO'
    assert md.vertex_group == "deltaMush1"
    assert bpy.context.active_object == cube                                      # Maya: pCube1 stays selected
    assert _rows(cube, md) == [("Smoothing Iterations", "10"), ("Smoothing Step", "0.5"),
                               ("Pin Border Vertices", "on")], _rows(cube, md)
    assert ae.modifier_node(cube, md) == ("deltaMush1", "deltaMush")
    _run("deform_delta_mush", iterations=4, step=0.25, pin_border=False)
    md2 = cube.modifiers["deltaMush2"]
    assert (md2.iterations, round(md2.factor, 4), md2.use_pin_boundary) == (4, 0.25, False)


# --- Cluster / Soft Mod -------------------------------------------------------------------------------

def test_cluster_group_envelope_and_paint_target():
    _clear()
    cube = _cube()
    assert bpy.ops.allset.cluster() == {'FINISHED'}                   # object mode: the whole object
    md = cube.modifiers["cluster1"]
    h = bpy.data.objects["cluster1Handle"]
    assert md.vertex_group == "cluster1" and len(cube.vertex_groups["cluster1"].name) > 0
    assert bpy.context.active_object == h
    before = _evaluated(cube)
    h.location.x += 1.0
    after = _evaluated(cube)
    assert all(abs((q - p).x - 1.0) < 1e-5 for p, q in zip(before, after)), "the whole cluster moves"
    assert _rows(cube, md) == [("Envelope", "1")]
    assert ae.modifier_node(cube, md) == ("cluster1", "cluster")
    _select(cube)
    _run("deform_cluster", envelope=0.5)
    assert abs(cube.modifiers["cluster2"].strength - 0.5) < 1e-6
    # Paint Weights > Cluster with the handle selected paints cluster1's weights on the cube
    _select(h)
    assert bpy.ops.allset.paint_deformer_weights(kind="cluster") == {'FINISHED'}
    assert bpy.context.mode == 'PAINT_WEIGHT' and bpy.context.active_object == cube
    assert cube.vertex_groups.active.name == "cluster1"
    bpy.ops.object.mode_set(mode='OBJECT')


def test_soft_mod_inputs():
    _clear()
    cube = _cube()
    _run("deform_soft_mod", radius=2.0)
    md = cube.modifiers["softMod1"]
    assert md.type == 'HOOK' and abs(md.falloff_radius - 2.0) < 1e-6 and md.vertex_group == "softMod1"
    assert bpy.context.active_object.name == "softMod1Handle"
    assert _rows(cube, md) == [("Envelope", "1"), ("Falloff Radius", "2")], _rows(cube, md)
    assert ae.modifier_node(cube, md) == ("softMod1", "softMod")


# --- Nonlinear -----------------------------------------------------------------------------------------

def test_nonlinear_names_handles_selection_inputs():
    _clear()
    bpy.ops.mesh.primitive_cylinder_add(radius=1, depth=4, location=(1, 0, 2))
    cyl = bpy.context.active_object
    for kind, base, mtype in (('BEND', "bend", 'SIMPLE_DEFORM'), ('TWIST', "twist", 'SIMPLE_DEFORM'),
                              ('SQUASH', "squash", 'SIMPLE_DEFORM'), ('FLARE', "flare", 'SIMPLE_DEFORM'),
                              ('SINE', "sine", 'WAVE'), ('WAVE', "wave", 'WAVE')):
        _select(cyl)
        assert bpy.ops.allset.deformer(kind=kind) == {'FINISHED'}, kind
        h = bpy.data.objects[f"{base}1Handle"]
        md = cyl.modifiers[f"{base}1"]
        assert md.type == mtype and md.vertex_group == f"{base}1", kind
        assert (h.location - Vector((1, 0, 2))).length < 1e-5                     # bbox centre
        assert all(abs(s - 2.0) < 1e-5 for s in h.scale), kind                    # half the height
        assert bpy.context.active_object == h, kind                               # Maya: bend1Handle selected
        assert ae.modifier_node(cyl, md) == (f"{base}1", "nonLinear"), kind
        assert cb.mod_node(md) in {cb.mod_node(m) for m in cb._inputs(h)}, kind   # handle CB shows bend1
    bend = cyl.modifiers["bend1"]
    assert bend.deform_method == 'BEND' and bend.origin.name == "bend1Handle" and bend.deform_axis == 'Z'
    assert tuple(round(x, 6) for x in bend.limits) == (0.0, 1.0) and bend.angle == 0.0
    assert _rows(cyl, bend) == [("Curvature", "0"), ("Low Bound", "-1"), ("High Bound", "1")], \
        _rows(cyl, bend)
    assert _rows(cyl, cyl.modifiers["squash1"])[0] == ("Factor", "0")
    assert _rows(cyl, cyl.modifiers["flare1"])[0] == ("End Flare X", "1")
    assert _rows(cyl, cyl.modifiers["twist1"])[0][0] == "End Angle"
    sine, wave = cyl.modifiers["sine1"], cyl.modifiers["wave1"]
    assert sine.use_x and not sine.use_y and sine.speed == 0.0 and sine.height == 0.0
    assert abs(sine.width - 4.0) < 1e-5                                           # wavelength 2 × handle 2
    assert wave.use_x and wave.use_y and abs(wave.width - 2.0) < 1e-5 and abs(wave.falloff_radius - 2.0) < 1e-5
    # an INPUTS row writes the Maya value back: Low Bound -0.5 = limits 0.25
    _rows(cyl, bend)
    row = next(r for r in bpy.context.scene.allset_cb.rows if r.kind == "INPUT" and r.mod_type == 'SIMPLE_DEFORM'
               and cb.input_label(bend, r.name) == "Low Bound" and r.nth == 0)
    row.text = "-0.5"
    assert abs(bend.limits[0] - 0.25) < 1e-6, tuple(bend.limits)


def test_nonlinear_window_values():
    _clear()
    bpy.ops.mesh.primitive_cylinder_add(radius=1, depth=4, location=(0, 0, 2))
    cyl = bpy.context.active_object
    _run("deform_twist", end_angle=90.0)
    assert abs(cyl.modifiers["twist1"].angle - math.radians(90.0)) < 1e-6
    _select(cyl)
    _run("deform_bend", curvature=1.2, low=0.0)
    md = cyl.modifiers["bend1"]
    assert abs(md.angle - 1.2) < 1e-6 and abs(md.limits[0] - 0.5) < 1e-6
    _select(cyl)
    _run("deform_flare", end_flare=1.5)
    assert abs(cyl.modifiers["flare1"].factor - 0.5) < 1e-6


# --- Wrap / Proximity Wrap / ShrinkWrap / Texture / Curve Warp -----------------------------------------------

def test_wrap_binds_to_the_influence():
    _clear()
    cube = _cube("pCube1")
    infl = _cube("pCube2", size=1.2, cuts=0)
    _select(cube, infl)
    assert bpy.ops.allset.deformer(kind='WRAP') == {'FINISHED'}
    md = cube.modifiers["wrap1"]
    assert md.type == 'SURFACE_DEFORM' and md.target == infl and md.is_bound
    assert infl.hide_render                                       # Render influence objects: off
    assert list(bpy.context.selected_objects) == [cube]            # Maya: pCube1
    before = _evaluated(cube)
    for v in infl.data.vertices:
        v.co.x += 1.0
    infl.data.update()
    after = _evaluated(cube)
    assert all(abs((q - p).x - 1.0) < 1e-3 for p, q in zip(before, after)), "follows the influence's shape"
    infl.location.y += 2.0
    moved = _evaluated(cube)
    assert all(abs((q - p).y - 2.0) < 1e-3 for p, q in zip(after, moved)), "and its transform (Maya)"
    assert [m.name for m in cb._inputs(cube)] == ["wrap1"]
    assert _rows(cube, md) == [("Envelope", "1")]
    assert ae.modifier_node(cube, md) == ("wrap1", "wrap")


def test_proximity_wrap_and_shrink_wrap():
    _clear()
    cube = _cube("pCube1")
    drv = _cube("pCube2", size=0.5, cuts=0)
    _select(cube, drv)
    assert bpy.ops.allset.deformer(kind='PROXIMITY_WRAP') == {'FINISHED'}
    md = cube.modifiers["proximityWrap1"]
    assert md.type == 'SURFACE_DEFORM' and md.target == drv and md.is_bound
    assert set(bpy.context.selected_objects) == {cube, drv}        # Maya: pCube1, pCube2
    assert ae.modifier_node(cube, md) == ("proximityWrap1", "proximityWrap")
    _select(cube, drv)
    assert bpy.ops.allset.deformer(kind='SHRINK_WRAP') == {'FINISHED'}
    sw = cube.modifiers["shrinkWrap1"]
    assert sw.type == 'SHRINKWRAP' and sw.target == drv and sw.wrap_method == 'PROJECT'
    assert sw.use_negative_direction and not sw.use_positive_direction and sw.vertex_group == "shrinkWrap1"
    assert set(bpy.context.selected_objects) == {cube, drv}
    rows = dict(_rows(cube, sw))
    assert rows["Offset"] == "0" and rows["Bidirectional"] == "off" and rows["Along X"] == "off", rows
    _select(cube, drv)
    _run("deform_shrink_wrap", projection="Closest", offset=0.1)
    sw2 = cube.modifiers["shrinkWrap2"]
    assert sw2.wrap_method == 'NEAREST_SURFACEPOINT' and abs(sw2.offset - 0.1) < 1e-6
    _select(cube, drv)
    _run("deform_shrink_wrap", projection="Parallel To Axes", along_y=True)
    sw3 = cube.modifiers["shrinkWrap3"]
    assert sw3.wrap_method == 'PROJECT' and sw3.use_project_z and not sw3.use_project_y   # Maya Y = Blender Z


def test_wrap_needs_two_objects():
    _clear()
    cube = _cube()
    res = ow.run(ow._BY_KEY["deform_wrap"], bpy.context, {})
    assert isinstance(res, str) and "influence" in res.lower(), res
    assert not cube.modifiers


def test_texture_deformer_starts_neutral():
    _clear()
    cube = _cube()
    before = _evaluated(cube)
    assert bpy.ops.allset.deformer(kind='TEXTURE') == {'FINISHED'}
    md = cube.modifiers["textureDeformer1"]
    assert md.type == 'DISPLACE' and md.texture_coords == 'UV' and md.direction == 'Z' and md.space == 'LOCAL'
    assert md.strength == 1.0 and md.mid_level == 0.0 and md.vertex_group == "textureDeformer1"
    after = _evaluated(cube)
    assert all((p - q).length < 1e-6 for p, q in zip(before, after)), "Maya: no texture yet, nothing moves"
    assert dict(_rows(cube, md)) == {"Strength": "1", "Offset": "0"}
    _select(cube)
    _run("deform_texture", direction="Normal", point_space="World", offset=0.2, strength=2.0)
    md2 = cube.modifiers["textureDeformer2"]
    assert md2.direction == 'NORMAL' and md2.texture_coords == 'GLOBAL' and abs(md2.mid_level + 0.1) < 1e-6
    assert dict(_rows(cube, md2))["Offset"] == "0.2"


def test_curve_warp():
    _clear()
    cube = _cube()
    bpy.ops.curve.primitive_bezier_curve_add()
    curve = bpy.context.active_object
    _select(cube, curve)
    assert bpy.ops.allset.deformer(kind='CURVE_WARP') == {'FINISHED'}
    md = cube.modifiers["curveWarp1"]
    assert md.type == 'CURVE' and md.object == curve
    assert bpy.context.active_object == cube


# --- Paint Weights -------------------------------------------------------------------------------------

def test_paint_weights_targets_and_warning():
    _clear()
    cube = _cube()
    bpy.ops.allset.deformer(kind='DELTA_MUSH')
    bpy.ops.allset.deformer(kind='LATTICE')
    _select(cube)
    assert bpy.ops.allset.paint_deformer_weights(kind="deltaMush") == {'FINISHED'}
    assert bpy.context.mode == 'PAINT_WEIGHT' and cube.vertex_groups.active.name == "deltaMush1"
    bpy.ops.object.mode_set(mode='OBJECT')
    _select(bpy.data.objects["ffd1Lattice"])                        # the lattice selected (Maya's selection)
    assert bpy.ops.allset.paint_deformer_weights(kind="ffd") == {'FINISHED'}
    assert bpy.context.active_object == cube and cube.vertex_groups.active.name == "ffd1"
    bpy.ops.object.mode_set(mode='OBJECT')
    _select(cube)
    assert bpy.ops.allset.paint_deformer_weights(kind="shrinkWrap") == {'CANCELLED'}   # no such deformer
    assert bpy.context.mode == 'OBJECT'
    # every Paint Weights item that has a deformer kind maps here
    for label, kind in (("Cluster", "cluster"), ("Delta Mush", "deltaMush"), ("Lattice", "ffd"),
                        ("ShrinkWrap", "shrinkWrap"), ("Proximity Wrap", "proximityWrap"),
                        ("Nonlinear", "nonLinear"), ("Texture Deformer", "textureDeformer"),
                        ("Blend Shape", "blendShape")):
        assert menu_map.spec(f"Deform/Paint Weights/{label}") == (
            "op", "allset.paint_deformer_weights", {"kind": kind}), label


def test_paint_weights_blend_shape():
    _clear()
    base = _cube("pCube1")
    target = _cube("pCube2", loc=(3, 0, 0))
    _select(target, base)
    assert bpy.ops.allset.blend_shape() == {'FINISHED'}
    key = base.data.shape_keys
    _select(base)
    assert bpy.ops.allset.paint_deformer_weights(kind="blendShape") == {'FINISHED'}
    assert base.vertex_groups.active.name == key.name
    assert all(kb.vertex_group == key.name for kb in key.key_blocks[1:])
    bpy.ops.object.mode_set(mode='OBJECT')


def test_undo_and_names_count_up():
    _clear()
    cube = _cube()
    bpy.ops.allset.deformer(kind='LATTICE')
    _select(cube)
    bpy.ops.allset.deformer(kind='LATTICE')
    assert "ffd2" in cube.modifiers and "ffd2Lattice" in bpy.data.objects
