"""Step 109: every Maya shelf button in its slot (greyed with a notice when unmapped), Sculpting brushes,
Curves / Surfaces and FX buttons, Maya-style icons.

"""

import os
from importlib import import_module

import bpy
import numpy as np

import kit

shelf = import_module(kit.MODULE + ".ui.shelf")
shelf_data = import_module(kit.MODULE + ".ui.shelf_data")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")
shelf_icons = import_module(kit.MODULE + ".ui.shelf_icons")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
notices = import_module(kit.MODULE + ".ui.notices")
curve_tools = import_module(kit.MODULE + ".operators.curve_tools")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# factory shelf button counts (step 269)
EXPECTED_COUNTS = {"Curves": 14, "Surfaces": 24, "Polygons": 37, "Sculpting": 26, "UVEditing": 12, "Rigging": 18,
               "Animation": 15, "Rendering": 26, "FX": 29, "FXCaching": 10}


def _fresh():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.curves):
        for d in list(coll):
            coll.remove(d)


def _select(*obs):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1]


def _circle(radius=1.0, z=0.0):
    bpy.ops.curve.primitive_nurbs_circle_add(radius=radius, location=(0, 0, z))
    return bpy.context.active_object


def _evaluated_faces(ob):
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    try:
        return len(me.polygons)
    finally:
        ev.to_mesh_clear()


# --- slots, counts, notices -------------------------------------------------------------------


def test_drawn_mapped_at_least_150():
    mapped = {name: len(shelf.factory_buttons(name)) for name, _l, _b in shelf_data.SHELVES}
    total = sum(mapped.values())
    print("mapped per shelf", mapped, "total", total, "/", sum(EXPECTED_COUNTS.values()))
    assert total >= 150, mapped
    # FX: the Emitter button is greyed like nParticles > Create Emitter (Blender particles come from a mesh)
    assert mapped["Sculpting"] >= 19 and mapped["Curves"] + mapped["Surfaces"] >= 24 and mapped["FX"] >= 12, mapped


def test_every_greyed_button_has_a_notice():
    missing = [(name, label) for name, _l, _b in shelf_data.SHELVES
               for _i, label, action, _icon in shelf.all_buttons(name)
               if action is None and shelf.button_notice(name, label) is None]
    assert not missing, missing
    paths = {p for p, _it in menu_sets.iter_items()}
    bad = {k: v for k, v in shelf_map.MENU.items() if v not in paths}
    assert not bad, bad
    labels = {f"{n}/{lab}" for n, _l, bs in shelf_data.SHELVES for lab, _c in bs}
    assert not set(shelf_map.MENU) - labels, set(shelf_map.MENU) - labels
    assert not set(shelf_map.NOTICES) - labels, set(shelf_map.NOTICES) - labels
    # A shelf-only notice is only for buttons no Maya menu has.
    assert not set(shelf_map.NOTICES) & set(shelf_map.MENU)


def test_menu_and_shelf_agree():
    """A button mapped through MENU runs exactly that menu item's action."""
    for key, path in shelf_map.MENU.items():
        name, label = key.split("/", 1)
        cmd = next(c for lab, c in next(b for n, _l, b in shelf_data.SHELVES if n == name) if lab == label)
        hit = shelf_map.lookup(name, label, cmd)
        if hit is not None and cmd not in shelf_map.BY_COMMAND and key not in shelf_map.BY_LABEL:
            assert hit[0] == menu_map.MAP[path], key


def test_icon_buttons_include_greyed_slots():
    bpy.ops.allset.shelf_select(shelf="Sculpting")
    cur, buttons = shelf.icon_buttons(bpy.context)
    assert cur == "Sculpting" and len(buttons) == 26
    assert buttons[0][1] == "Sculpt Tool" and buttons[0][3]
    by = {b[1]: b[3] for b in buttons}
    assert by["Bulge Tool"] and by["Freeze Tool"] and by["Smooth Tool"]
    assert not by["Imprint Tool"] and not by["Convert To Frozen"]
    bpy.ops.allset.shelf_select(shelf="Polygons")


def test_greyed_click_and_tooltip_show_the_notice():
    i = next(i for i, lab, a, _ic in shelf.all_buttons("Surfaces") if lab == "Trim Tool")
    assert bpy.ops.allset.shelf_button(shelf="Surfaces", index=i) == {'CANCELLED'}
    assert notices.current().startswith("Trim Tool: "), notices.current()
    tip = shelf.button_tooltip("Surfaces", "Trim Tool", False)
    assert "(Maya shelf, greyed)" in tip and notices.category("Surfaces/Trim Tool")[0] in tip, tip
    tip = shelf.button_tooltip("Rendering", "Render Diagnostics", False)
    assert "Info editor" in tip, tip
    # Mapped with a different Blender result: the tooltip says what Blender does.
    tip = shelf.button_tooltip("Surfaces", "Planar", True)
    assert "Blender: Filled 2D curve" in tip, tip


def test_sculpting_tools_are_blender_brushes():
    want = {"Smooth Tool": "Smooth", "Relax Tool": "Relax Slide", "Grab Tool": "Grab", "Pinch Tool": "Pinch/Magnify",
            "Flatten Tool": "Flatten/Contrast", "Scrape Tool": "Scrape/Fill", "Fill Tool": "Fill/Deepen",
            "Smear Tool": "Smear", "Bulge Tool": "Inflate/Deflate", "Freeze Tool": "Mask",
            "Spray Tool": "Draw Sharp", "Repeat Tool": "Layer"}
    by = {lab: a for _i, lab, a, _ic in shelf.all_buttons("Sculpting")}
    for label, brush in want.items():
        kind, target, props = menu_map.normalize(by[label])
        assert target == "allset.sculpt_tool" and props["brush"] == brush, (label, by[label])


def test_sculpt_button_activates_the_brush():
    _fresh()
    bpy.ops.mesh.primitive_cube_add()
    i = next(i for i, lab, _a, _ic in shelf.all_buttons("Sculpting") if lab == "Bulge Tool")
    res = bpy.ops.allset.shelf_button(shelf="Sculpting", index=i)
    assert res == {'FINISHED'}, res
    assert bpy.context.mode == 'SCULPT'
    brush = bpy.context.tool_settings.sculpt.brush
    assert brush is not None and brush.name == "Inflate/Deflate", brush
    bpy.ops.object.mode_set(mode='OBJECT')


# --- Curves / Surfaces ----------------------------------------------------------------------

def test_planar_fills_a_closed_curve():
    _fresh()
    c = _circle(2.0)
    assert bpy.ops.allset.surface_planar() == {'FINISHED'}
    ob = bpy.data.objects["planarTrimmedSurface1"]
    assert ob.data is not c.data and ob.data.dimensions == '2D' and ob.data.fill_mode == 'BOTH'
    assert _evaluated_faces(ob) > 0
    assert "nurbsCircle1" in bpy.data.objects or c.name in bpy.data.objects     # the curve is kept


def test_planar_needs_closed_curves():
    _fresh()
    bpy.ops.curve.primitive_nurbs_curve_add()
    assert bpy.ops.allset.surface_planar() == {'CANCELLED'}


def test_loft_two_circles():
    _fresh()
    a = _circle(1.0, 0.0)
    b = _circle(1.0, 5.0)
    _select(a, b)
    assert bpy.ops.allset.loft() == {'FINISHED'}
    ob = bpy.data.objects["loftedSurface1"]
    assert ob.type == 'SURFACE', ob.type                 # a NURBS surface since step 181
    sp = ob.data.splines[0]
    assert sp.use_cyclic_u and sp.point_count_v == 4, (sp.use_cyclic_u, sp.point_count_v)   # 2 curves: 1 cubic span
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    try:
        zs = [ob.matrix_world @ v.co for v in me.vertices]
        assert abs(min(p.z for p in zs)) < 1e-4 and abs(max(p.z for p in zs) - 5.0) < 1e-4
    finally:
        ev.to_mesh_clear()
    assert ob.active_material is not None          # lambert1, like a Maya shape (step 100)


def test_extrude_sweeps_profile_along_path():
    _fresh()
    prof = _circle(0.5)
    bpy.ops.curve.primitive_nurbs_path_add()
    path = bpy.context.active_object
    _select(prof, path)
    assert bpy.ops.allset.surface_extrude() == {'FINISHED'}
    ob = bpy.data.objects["extrudedSurface1"]
    assert ob.type == 'SURFACE' and ob.data is not path.data and ob.data is not prof.data
    assert _evaluated_faces(ob) > 0


def test_bevel_plus_makes_a_mesh_and_keeps_the_curve():
    _fresh()
    c = _circle(2.0)
    assert bpy.ops.allset.bevel_plus() == {'FINISHED'}
    ob = bpy.data.objects["bevelPolygon1"]
    assert ob.type == 'MESH' and len(ob.data.polygons) > 0
    assert c.name in bpy.data.objects
    k = 1.0
    depth = ob.dimensions.z
    want = (curve_tools.EXTRUDE_DEPTH + 2 * curve_tools.BEVEL_DEPTH) * k
    assert abs(depth - want) < 1e-3, (depth, want)
    assert abs(ob.dimensions.x - 4.0) < 0.05, ob.dimensions       # bevel inside the curve: outline stays


def test_offset_curve_follows_maya_direction():
    _fresh()
    data = bpy.data.curves.new("line", 'CURVE')
    data.dimensions = '3D'
    sp = data.splines.new('POLY')
    sp.points.add(1)
    sp.points[0].co = (0, 0, 0, 1)
    sp.points[1].co = (4, 0, 0, 1)
    line = bpy.data.objects.new("line", data)
    bpy.context.collection.objects.link(line)
    _select(line)
    assert bpy.ops.allset.offset_curve() == {'FINISHED'}
    ob = bpy.data.objects["offsetNurbsCurve1"]
    ys = {round(p.co.y, 4) for p in ob.data.splines[0].points}
    # Maya: a line along +X (normal Maya +Y) moved to Maya -Z = Blender +Y by the distance 1.
    assert ys == {1.0}, ys


def test_sweep_mesh_is_an_8_sided_tube():
    _fresh()
    bpy.ops.curve.primitive_nurbs_path_add()
    path = bpy.context.active_object
    assert bpy.ops.allset.sweep_mesh() == {'FINISHED'}
    ob = bpy.data.objects["sweep1"]
    assert ob.type == 'MESH' and path.name in bpy.data.objects
    ring = [v for v in ob.data.vertices]
    assert len(ring) % curve_tools.SWEEP_SIDES == 0, len(ring)


def test_nurbs_square_cube_cone():
    _fresh()
    assert bpy.ops.allset.create(kind='NURBS_SQUARE') == {'FINISHED'}
    grp = bpy.data.objects["nurbsSquare1"]
    assert sorted(c.name for c in grp.children) == sorted(
        f"{s}nurbsSquare1" for s in ("top", "left", "bottom", "right"))
    top = bpy.data.objects["topnurbsSquare1"]
    assert {round(p.co.y, 3) for p in top.data.splines[0].points} == {-0.5}    # Maya +Z = Blender -Y
    assert bpy.ops.allset.create(kind='NURBS_CUBE') == {'FINISHED'}
    cube = bpy.data.objects["nurbsCube1"]
    assert len(cube.children) == 6
    def cvs(name):   # step 129: Maya builds the patches in place (CVs), the part transforms stay at the origin
        return [p.co for p in bpy.data.objects[name].data.splines[0].points]
    assert {round(p.z, 4) for p in cvs("topnurbsCube1")} == {0.5}
    assert {round(p.y, 4) for p in cvs("leftnurbsCube1")} == {-0.5}      # Maya left = +Z side
    assert {round(p.x, 4) for p in cvs("frontnurbsCube1")} == {0.5}      # Maya front = +X side
    assert bpy.ops.allset.create(kind='NURBS_CONE') == {'FINISHED'}
    cone = bpy.data.objects["nurbsCone1"]
    pts = [p.co for sp in cone.data.splines for p in sp.points]
    top_z = max(p.z for p in pts)
    assert all(abs(p.x) < 1e-6 and abs(p.y) < 1e-6 for p in pts if abs(p.z - top_z) < 1e-6)


def test_pencil_and_add_points():
    _fresh()
    assert bpy.ops.allset.pencil_curve() == {'FINISHED'}
    ob = bpy.context.active_object
    assert ob.name == "curve1" and ob.type == 'CURVE' and bpy.context.mode == 'EDIT_CURVE'
    bpy.ops.object.mode_set(mode='OBJECT')
    _fresh()
    bpy.ops.curve.primitive_nurbs_curve_add()
    assert bpy.ops.allset.add_points() == {'FINISHED'}
    ob = bpy.context.active_object
    assert bpy.context.mode == 'EDIT_CURVE'
    bpy.ops.object.mode_set(mode='OBJECT')
    pts = ob.data.splines[0].points
    assert pts[len(pts) - 1].select and not pts[0].select


# --- FX ---------------------------------------------------------------------------------------

def test_fluid_container_button_is_the_menu_item():
    # the 3D Fluid Container with Emitter button runs its menu item (Fluids > 3D Container = Blender's Quick Smoke)
    action, _icon = shelf_map.lookup("FX", "3D Fluid Container with Emitter", "Create3DContainerEmitter")
    assert action == "allset.fluid_quick_smoke", action


def test_fluid_collide_and_ncloth_display():
    _fresh()
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    assert bpy.ops.allset.fluid_collide() == {'FINISHED'}
    assert next(m for m in cube.modifiers if m.type == 'FLUID').fluid_type == 'EFFECTOR'
    bpy.ops.mesh.primitive_plane_add()
    plane = bpy.context.active_object
    cloth = plane.modifiers.new("Cloth", 'CLOTH')
    assert bpy.ops.allset.ncloth_display(mesh='INPUT') == {'FINISHED'} and not cloth.show_viewport
    assert bpy.ops.allset.ncloth_display(mesh='CURRENT') == {'FINISHED'} and cloth.show_viewport


# --- icons ------------------------------------------------------------------------------------

def test_icons_use_maya_hues_and_fade_when_greyed():
    # step 131: hues of Maya 2022's icons
    assert shelf_icons.SHELF_COLOURS["Polygons"] == shelf_icons.SHELF_COLOURS["Sculpting"]
    assert shelf_icons.SHELF_COLOURS["Curves"] == shelf_icons.SHELF_COLOURS["Surfaces"]
    r, g, b = shelf_icons.SHELF_COLOURS["Curves"]
    assert b > r and round(b * 255) == 0xcb
    px = shelf_icons.draw("Polygon Cube", "Polygons")
    opaque = px[px[..., 3] > 0.99][:, :3]
    hue = np.array(shelf_icons.SHELF_COLOURS["Polygons"])
    assert (np.abs(opaque - hue).max(axis=1) < 0.02).any(), "the cube's front face is Maya's orange"
    grey = shelf_icons.draw("Trim Tool", "Surfaces", greyed=True)
    assert grey[..., 3].max() <= shelf_icons.GREYED_ALPHA + 1e-6
    assert np.allclose(grey[..., 0], grey[..., 1]) and np.allclose(grey[..., 1], grey[..., 2])
    tools = shelf_icons.draw("Merge", "Polygons")
    light = np.array(shelf_icons.LIGHT)
    assert (np.abs(tools[tools[..., 3] > 0.99][:, :3] - light).max(axis=1) < 0.02).any(), "tool parts in grey"
    tools = [lab for lab, _c in next(b for n, _l, b in shelf_data.SHELVES if n == "Sculpting") if lab.endswith(" Tool")]
    sculpt = {shelf_icons.draw(lab, "Sculpting").round(2).tobytes() for lab in tools}
    assert len(sculpt) == len(tools), (len(sculpt), len(tools))     # step 131: every brush its own picture
    # step 131: Maya's dark outline round the shapes, UV tools green
    outline = np.array(shelf_icons.DARK)
    assert (np.abs(px[px[..., 3] > 0.5][:, :3] - outline).max(axis=1) < 0.03).any(), "dark outline"
    uv = shelf_icons.draw("Planar Mapping", "UVEditing")
    assert (np.abs(uv[uv[..., 3] > 0.99][:, :3] - np.array(shelf_icons.GREEN)).max(axis=1) < 0.03).any(), "UV green"
