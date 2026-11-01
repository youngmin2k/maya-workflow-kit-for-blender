"""Modeling Toolkit dock, soft select in Maya units, Combine / Separate / Mirror / Boolean with Maya meaning.
GUI: tests/gui/gui_step63_mtk.py."""

from importlib import import_module

import bpy

import kit

mesh_maya = import_module(kit.MODULE + ".operators.mesh_maya")
taphold = import_module(kit.MODULE + ".operators.taphold")
units = import_module(kit.MODULE + ".operators.units")
mtk = import_module(kit.MODULE + ".ui.modeling_toolkit")
ae = import_module(kit.MODULE + ".ui.attribute_editor")
status_line = import_module(kit.MODULE + ".ui.status_line")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")
mm = import_module(kit.MODULE + ".marking.menus")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)


def _select(*obs, active=None):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or obs[-1]


def _create(kind, x=0.0):
    bpy.ops.allset.create(kind=kind)
    ob = bpy.context.active_object
    ob.location.x = x
    return ob


def _world_verts(ob):
    bpy.context.view_layer.update()     # matrix_world after a location change
    return sorted(tuple(round(c, 4) for c in ob.matrix_world @ v.co) for v in ob.data.vertices)


def test_dock_and_status_line_toggle():
    ids = [i[0] for i in ae.DOCK_ITEMS]
    assert ids == ['CHANNEL_BOX', 'ATTRIBUTE_EDITOR', 'MODELING_TOOLKIT'], ids
    wm = bpy.context.window_manager
    wm.allset_dock = 'MODELING_TOOLKIT'
    assert ae.dock_mode(bpy.context) == 'MODELING_TOOLKIT'
    # one dock panel draws every mode (in the Maya dock areas)
    assert not hasattr(bpy.types, "ALLSET_PT_modeling_toolkit") and hasattr(bpy.types, "ALLSET_PT_maya_dock")
    wm.allset_dock = 'CHANNEL_BOX'
    assert status_line.EDITORS[0][0] == "MODELING_TOOLKIT", "Maya order: MTK first"
    m = menu_map.MAP
    assert m["Windows/Modeling Editors/Modeling Toolkit"][1] == "allset.dock_show"
    assert m["Mesh Tools/Hide Modeling Toolkit"][0] == "allset.editor_toggle"


def test_mtk_buttons_are_menu_actions():
    for label, path, _icon in mtk.MESH + mtk.COMPONENTS + mtk.TOOLS:
        if label == "Extrude":
            continue
        assert path in menu_map.MAP, (label, path)   # Target Weld: a kit tool


def test_combine_maya_name_and_centre_pivot():
    """Maya 2022: pCube1 + pSphere1 -> pCube2, pivot at the bounding-box centre, translate 0."""
    _clear()
    cube = _create('CUBE', 0.0)
    sphere = _create('SPHERE', 3.0)
    before = sorted(_world_verts(cube) + _world_verts(sphere))
    _select(cube, sphere)
    assert bpy.ops.allset.combine() == {'FINISHED'}
    obs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    assert len(obs) == 1 and obs[0].name == "pCube2", [o.name for o in obs]
    ob = obs[0]
    assert ob.data.name == "pCubeShape2"
    assert tuple(ob.location) == (0, 0, 0), "translate channels 0 (Maya)"
    bpy.context.view_layer.update()
    lo = min(v[0] for v in before)
    hi = max(v[0] for v in before)
    pivot = ob.matrix_world.translation
    assert abs(pivot.x - (lo + hi) / 2) < 1e-4 and abs(pivot.x - 1.75) < 1e-4, (pivot, lo, hi)  # expected 1.75
    assert _world_verts(ob) == before, "vertices stay where they were"


def test_separate_maya_group():
    _clear()
    cube = _create('CUBE', 0.0)
    sphere = _create('SPHERE', 3.0)
    _select(cube, sphere)
    bpy.ops.allset.combine()
    ob = bpy.context.active_object
    before = sorted(_world_verts(ob))
    assert bpy.ops.allset.separate() == {'FINISHED'}
    grp = bpy.data.objects["pCube2"]
    kids = sorted(c.name for c in grp.children)
    assert grp.type == 'EMPTY' and kids == ["polySurface1", "polySurface2"], (grp.type, kids)
    after = sorted(sum((_world_verts(bpy.data.objects[k]) for k in kids), []))
    assert after == before
    for k in kids:   # translate 0, pivot at the world origin
        piece = bpy.data.objects[k]
        assert tuple(piece.location) == (0, 0, 0), (k, tuple(piece.location))
        assert piece.matrix_world.translation.length < 1e-5, (k, piece.matrix_world.translation)
    assert {o.name for o in bpy.context.selected_objects} == set(kids)
    _select(bpy.data.objects["polySurface1"])
    assert bpy.ops.allset.separate() == {'CANCELLED'}, "one shell"


def test_mirror_maya_defaults():
    """Cut + World + X + direction -: the +X half is copied to -X and merged at x = 0."""
    _clear()
    cube = _create('CUBE', 0.25)      # x from -0.25 to 0.75
    _select(cube)
    assert bpy.ops.allset.mirror() == {'FINISHED'}
    bpy.context.view_layer.update()
    xs = [round((cube.matrix_world @ v.co).x, 4) for v in cube.data.vertices]
    assert min(xs) == -0.75 and max(xs) == 0.75, (min(xs), max(xs))
    assert len(cube.data.vertices) == 12, "cut at 0, mirrored, border merged (8 + 8 - 4)"
    # Y (Maya up) = Blender Z, Combine off = a new object
    _clear()
    cube = _create('CUBE', 0.0)
    cube.location.z = 2.0
    _select(cube)
    bpy.ops.allset.mirror(axis='Y', cut=False, combine=False)
    meshes = sorted(o.name for o in bpy.context.scene.objects if o.type == 'MESH')
    assert meshes == ["pCube1", "pCube2"], meshes
    copy = bpy.data.objects["pCube2"]
    zs = [(copy.matrix_world @ v.co).z for v in copy.data.vertices]
    assert abs(max(zs) + 1.5) < 1e-4 and abs(min(zs) + 2.5) < 1e-4, (min(zs), max(zs))
    # Object position + Z axis = Blender -Y through the origin
    _clear()
    cube = _create('CUBE', 0.0)
    cube.location.y = 5.0
    _select(cube)
    bpy.ops.allset.mirror(position='OBJECT', axis='Z', direction='POSITIVE', cut=True)
    ys = sorted({round((cube.matrix_world @ v.co).y, 4) for v in cube.data.vertices})
    assert ys == [4.5, 5.0, 5.5], ys


def test_mirror_option_box_routes_to_dialog():
    m = import_module(kit.MODULE + ".marking.modal")
    assert "option_box" in bpy.ops.allset.mirror.get_rna_type().properties
    assert "Mesh/Mirror" in import_module(kit.MODULE + ".ui.menu_data").OPTION_BOXES
    assert callable(m.run_action)


def test_boolean_maya_order():
    _clear()
    a = _create('CUBE', 0.0)
    b = _create('CUBE', 0.5)
    _select(a, b, active=b)           # Maya: a first, then b
    assert bpy.ops.allset.boolean(operation='DIFFERENCE') == {'FINISHED'}
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    assert meshes == [a], [o.name for o in meshes]
    xs = [(a.matrix_world @ v.co).x for v in a.data.vertices]
    assert max(xs) <= 0.0 + 1e-4 and min(xs) >= -0.5 - 1e-4, (min(xs), max(xs))


def _three_cubes():
    """Unit cubes A at 0, B at x + 0.5, C at y + 0.5, selected A, B, then C (active)."""
    _clear()
    a = _create('CUBE', 0.0)
    b = _create('CUBE', 0.5)
    c = _create('CUBE', 0.0)
    c.location.y = 0.5
    assert a.name < b.name, (a.name, b.name)
    _select(a, b, c, active=c)
    bpy.context.view_layer.update()
    return a, b, c


def _area_bbox(ob):
    mw = ob.matrix_world
    area = sum(p.area for p in ob.data.polygons) * abs(mw.determinant()) ** (2 / 3)
    pts = [mw @ v.co for v in ob.data.vertices]
    box = tuple(round(f(p[i] for p in pts), 4) for f in (min, max) for i in range(3))
    return round(area, 4), box


def test_boolean_three_objects():
    """Maya: the first selected object against the union of the others, one result (issue #284)."""
    cases = {   # operation: (result object index, area, bbox)
        'UNION': (0, 10.0, (-0.5, -0.5, -0.5, 1.0, 1.0, 0.5)),            # A u B u C
        'DIFFERENCE': (0, 2.5, (-0.5, -0.5, -0.5, 0.0, 0.0, 0.5)),        # A - (B u C)
        'DIFFERENCE_BA': (None, 8.0, (-0.5, -0.5, -0.5, 1.0, 1.0, 0.5)),  # (B u C) - A
        'INTERSECT': (0, 5.5, (-0.5, -0.5, -0.5, 0.5, 0.5, 0.5)),         # A n (B u C)
    }
    for operation, (index, area, box) in cases.items():
        obs = _three_cubes()
        assert bpy.ops.allset.boolean.poll(), operation
        assert bpy.ops.allset.boolean(operation=operation) == {'FINISHED'}, operation
        meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
        assert len(meshes) == 1, (operation, [o.name for o in meshes])
        if index is not None:
            assert meshes[0] is obs[index], operation
        got = _area_bbox(meshes[0])
        assert abs(got[0] - area) < 1e-3 and got[1] == box, (operation, got)
        assert bpy.context.view_layer.objects.active is meshes[0] and meshes[0].select_get()


def test_soft_select_maya_units():
    _clear()
    _create('CUBE')
    ts = bpy.context.scene.tool_settings
    ts.proportional_size = 1.0
    taphold.maya_soft_radius(bpy.context)
    k = units.maya_unit()
    assert abs(ts.proportional_size - 5.0 * k) < 1e-9, "factory radius 5"
    sc = bpy.context.scene
    assert abs(sc.allset_soft_radius - 5.0) < 1e-6
    sc.allset_soft_radius = 2.0
    assert abs(ts.proportional_size - 2.0 * k) < 1e-9
    taphold.maya_soft_radius(bpy.context)
    assert abs(sc.allset_soft_radius - 2.0) < 1e-6, "a radius the user set is kept"
    # cm scene (Maya Workflow Kit template units): 5 Maya units = 5 cm
    us = sc.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'CENTIMETERS', 1.0
    ts.proportional_size = 1.0
    taphold.maya_soft_radius(bpy.context)
    assert abs(ts.proportional_size - 0.05) < 1e-9 and abs(sc.allset_soft_radius - 5.0) < 1e-6
    us.length_unit = 'METERS'
    bpy.ops.allset.soft_select_reset()
    assert abs(ts.proportional_size - 5.0) < 1e-9 and not ts.use_proportional_connected


def test_menus_shelf_marking():
    m = menu_map.MAP
    assert m["Mesh/Combine"] == "allset.combine" and m["Mesh/Separate"] == "allset.separate"
    assert m["Mesh/Mirror"] == "allset.mirror"
    assert m["Mesh/Booleans/Difference (A - B)"] == ("allset.boolean", {"operation": 'DIFFERENCE'})
    assert shelf_map.BY_COMMAND["CombinePolygons"][0] == "allset.combine"
    assert shelf_map.BY_COMMAND["MirrorPolygonGeometry"][0] == "allset.mirror"
    actions = [a for menu in mm.MENUS.values() for _n, a in getattr(menu, "items", lambda: [])()] \
        if False else []
    src = open(mm.__file__, encoding="utf-8").read()
    assert '"object.join"' not in src and "_mod('MIRROR')" not in src


def test_mtk_extrude_adds_faces():
    _clear()
    cube = _create('CUBE')
    _select(cube)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='FACE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    cube.data.polygons[0].select = True
    bpy.ops.object.mode_set(mode='EDIT')
    assert bpy.ops.allset.extrude() == {'FINISHED'}   # the MTK button = polyExtrudeFace
    bpy.ops.object.mode_set(mode='OBJECT')
    assert len(cube.data.polygons) == 10, len(cube.data.polygons)
