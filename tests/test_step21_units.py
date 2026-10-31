"""One length rule for every creation path.

A Maya length of 1 = one scene display unit: Create / shelf / menu / marking menu
(``allset.create``), ``cmds.polyCube()`` and a Maya FBX import give the same size,
with the Maya Workflow Kit template units (m + cm display), with "Maya Units" on and in a
factory (m) scene.
"""

import os
import tempfile
from importlib import import_module
from pathlib import Path

import bpy

import kit

units = import_module(kit.MODULE + ".operators.units")
create = import_module(kit.MODULE + ".operators.create")
cmds = import_module(kit.MODULE + ".command_line.cmds_shim")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")
mm = import_module(kit.MODULE + ".marking.menus")
preferences = import_module(kit.MODULE + ".preferences")

TOL = 1e-6
# Default primitive sizes in Maya units (operators/create.py KINDS) and the cmds call for each.
PAIRS = {
    'CUBE': (cmds.polyCube, (1.0, 1.0, 1.0)),
    'SPHERE': (cmds.polySphere, (2.0, 2.0, 2.0)),
    'CYLINDER': (cmds.polyCylinder, (2.0, 2.0, 2.0)),
    'PLANE': (cmds.polyPlane, (1.0, 1.0, 0.0)),
}
# name -> (system, length_unit, scale_length, BU per Maya unit)
MODES = {
    "template": ('METRIC', 'CENTIMETERS', 1.0, 0.01),     # tools/make_startup.py
    "maya_units": ('METRIC', 'CENTIMETERS', 0.01, 1.0),   # preference "Maya Units"
    "factory": ('METRIC', 'METERS', 1.0, 1.0),
}


def _fresh():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.curves, bpy.data.cameras, bpy.data.lights):
        for data in list(coll):
            coll.remove(data)


def _set_units(mode):
    system, unit, scale, _k = MODES[mode]
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = system, unit, scale


def _close(a, b, tol=TOL):
    return all(abs(x - y) <= tol * max(1.0, abs(y)) for x, y in zip(a, b))


def _obj(name):
    return bpy.data.objects[name]


def test_maya_unit_per_mode():
    for mode, (*_rest, k) in MODES.items():
        _set_units(mode)
        assert abs(units.maya_unit() - k) < 1e-6, (mode, units.maya_unit())
        assert abs(cmds.linear_factor() - k) < 1e-6, mode


def test_create_and_cmds_same_size_in_every_mode():
    for mode, (*_rest, k) in MODES.items():
        _set_units(mode)
        for kind, (cmd, maya_dims) in PAIRS.items():
            _fresh()
            a = create.create(bpy.context, kind)
            b = _obj(cmd()[0])
            want = [d * k for d in maya_dims]
            assert _close(a.dimensions, want), (mode, kind, tuple(a.dimensions), want)
            assert _close(b.dimensions, a.dimensions), (mode, kind, tuple(b.dimensions),
                                                        tuple(a.dimensions))
    _set_units("factory")


def test_template_cube_reads_one_cm():
    _set_units("template")
    _fresh()
    ob = create.create(bpy.context, 'CUBE')
    us = bpy.context.scene.unit_settings
    text = bpy.utils.units.to_string(us.system, 'LENGTH', ob.dimensions.x * us.scale_length)
    assert text.replace(" ", "") == "1cm", text
    assert cmds.getAttr(ob.name + ".scaleX") == 1.0
    cmds.move(5, 0, 0, ob.name)
    assert abs(ob.location.x - 0.05) < TOL and abs(cmds.getAttr(ob.name + ".translateX") - 5) < 1e-6
    _set_units("factory")


def test_other_kinds_scale_with_the_unit():
    _set_units("template")
    _fresh()
    bpy.ops.allset.group()
    grp = bpy.data.objects["group1"]
    assert abs(grp.empty_display_size - 0.01) < TOL, grp.empty_display_size
    loc = create.create(bpy.context, 'LOCATOR')
    assert abs(loc.empty_display_size - 0.01) < TOL, loc.empty_display_size
    cam = create.create(bpy.context, 'CAMERA')
    assert _close((cam.data.clip_start, cam.data.clip_end), (0.001, 100.0)), \
        (cam.data.clip_start, cam.data.clip_end)
    assert abs(cam.data.display_size - 0.01) < TOL
    assert (cam.data.lens, cam.data.sensor_width) == (35.0, 36.0), "camera 35 mm on 36 mm film"
    circle = create.create(bpy.context, 'NURBS_CIRCLE')
    assert _close(circle.dimensions[:2], (0.02, 0.02), 1e-3), tuple(circle.dimensions)
    curve = create.create(bpy.context, 'CV_CURVE')
    assert curve.name == "curve1" and curve.type == 'CURVE', curve.name
    assert max(curve.dimensions) < 0.1, tuple(curve.dimensions)
    area = create.create(bpy.context, 'AREA_LIGHT')
    assert abs(area.data.size - 0.02) < TOL, area.data.size     # area light 2 x 2 units
    _set_units("factory")


def test_every_creation_path_uses_allset_create():
    def actions(sub):
        for _pos, (label, action) in sub.radial.items():
            yield label, action
        for item in sub.items:
            if item != mm.DIVIDER:
                yield item
    created = {label: action for label, action in actions(mm.SHIFT_DEFAULT)
               if isinstance(action, tuple) and action and str(action[0]).startswith(("mesh.", "allset.create"))}
    assert set(created) == {"Disc", "Sphere", "Torus", "Cube", "Cone", "Cylinder", "Plane",
                            "Platonic Solid", "Pyramid", "Prism", "Pipe", "Helix", "Gear",
                            "Type"}, created   # Type, Pipe / Helix / Gear included
    for label, action in created.items():
        assert action[0] == "allset.create" and action[1]["kind"] in create.KINDS, (label, action)
    assert menu_map.MAP["Create/Curve Tools/Bezier Curve Tool"][0] == "allset.create"
    # CV / EP Curve Tool are click tools (operators/curve_draw.py; clicked points are already scene units)
    assert menu_map.MAP["Create/Curve Tools/CV Curve Tool"] == "allset.cv_curve_tool"
    assert shelf_map.BY_COMMAND["EPCurveTool"][0] == "allset.ep_curve_tool"
    for cmd in ("CreateBezierCurveTool", "CreatePolygonCube"):
        assert shelf_map.BY_COMMAND[cmd][0][0] == "allset.create", cmd
    # no menu / shelf / marking item adds a Blender primitive behind allset.create's back
    for label, action in list(menu_map.MAP.items()) + [(k, v[0]) for k, v in shelf_map.BY_COMMAND.items()]:
        op = action if isinstance(action, str) else action[0]
        assert not (isinstance(op, str) and ".primitive_" in op), (label, op)


def test_marking_cube_runs_maya_create():
    _set_units("template")
    _fresh()
    action = mm.SHIFT_DEFAULT.radial["S"][1]
    getattr(bpy.ops.allset, action[0].split(".")[1])(**action[1])
    ob = bpy.context.view_layer.objects.active
    assert ob.name == "pCube1" and _close(ob.dimensions, (0.01,) * 3), (ob.name, tuple(ob.dimensions))
    _set_units("factory")


def test_maya_fbx_import_matches_create():
    """A Maya scene is cm: an FBX with UnitScaleFactor 1 (Blender writes that from a
    scale_length 0.01 scene) holding a 1-unit cube imports at Create's size."""
    path = os.path.join(tempfile.mkdtemp(), "maya_cube.fbx")
    _set_units("maya_units")
    _fresh()
    cmds.polyCube()
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'MESH'})
    text = Path(path).read_bytes()
    assert b"UnitScaleFactor" in text
    for mode in ("template", "maya_units"):
        _set_units(mode)
        _fresh()
        ref = create.create(bpy.context, 'CUBE').dimensions.copy()
        _fresh()
        bpy.ops.import_scene.fbx(filepath=path)
        imported = [o for o in bpy.data.objects if o.type == 'MESH'][0]
        # dimensions include the object scale, where the importer may put the unit scale
        assert _close(imported.dimensions, ref, 1e-4), (mode, tuple(imported.dimensions), tuple(ref))
    _set_units("factory")


def _template_view():
    for area in bpy.data.workspaces["General"].screens[0].areas:
        if area.type == 'VIEW_3D':
            return area.spaces.active
    raise AssertionError("no 3D view in the template")


def test_template_view_is_maya_persp_and_rescales_with_maya_units():
    path = Path(import_module(kit.MODULE).__file__).parent / "app_template" / "Maya_Workflow_Kit" / "startup.blend"
    bpy.ops.wm.open_mainfile(filepath=str(path))
    v3d = _template_view()
    rv3d = v3d.region_3d
    assert abs(units.maya_unit() - 0.01) < 1e-9
    assert len(list(units._views())) > 1   # every workspace
    assert _close((v3d.clip_start, v3d.clip_end), (0.001, 100.0)), (v3d.clip_start, v3d.clip_end)
    assert abs(rv3d.view_distance - 0.4482) < 1e-3, rv3d.view_distance
    for space in units._views():
        assert _close((space.clip_start, space.clip_end), (0.001, 100.0)), space
    units.apply_file(rescale_views=True)       # what load_post does for a new file
    try:
        assert _close((v3d.clip_start, v3d.clip_end), (0.1, 10000.0)), (v3d.clip_start, v3d.clip_end)
        assert abs(rv3d.view_distance - 44.82) < 0.1, rv3d.view_distance
        ob = create.create(bpy.context, 'CUBE')
        assert _close(ob.dimensions, (1.0,) * 3), tuple(ob.dimensions)
    finally:
        units.restore_file()
    assert _close((v3d.clip_start, v3d.clip_end), (0.001, 100.0)), (v3d.clip_start, v3d.clip_end)
    assert abs(rv3d.view_distance - 0.4482) < 1e-3, rv3d.view_distance
    bpy.ops.wm.read_homefile()
