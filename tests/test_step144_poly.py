"""Step 144 POLY lane (GitHub #30): Quad Draw, Create Polygon, Append to Polygon as Maya tools.
Plan: docs/steps/step_144_poly.md; GUI: tests/gui/gui_step144_poly.py. Maya Tool Settings defaults
(Maya 2022 Tool Settings)."""

import math
from importlib import import_module

import bmesh
import bpy
from mathutils import Vector

import kit

pd = import_module(kit.MODULE + ".operators.poly_draw")
qd = import_module(kit.MODULE + ".operators.quad_draw")
ui_poly = import_module(kit.MODULE + ".ui.mesh_tools_poly")
ts_mod = import_module(kit.MODULE + ".ui.tool_settings")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")
notices = import_module(kit.MODULE + ".ui.notices")
command_line = import_module(kit.MODULE + ".command_line")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)


def _counts(bm):
    return len(bm.verts), len(bm.edges), len(bm.faces)


SQUARE = [(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)]


# --- Create Polygon -------------------------------------------------------------------------------------

def test_polygon_points_divisions_and_planar():
    assert len(pd.polygon_points(SQUARE)) == 4
    pts = pd.polygon_points(SQUARE, divisions=2)
    assert len(pts) == 8 and (pts[1] - Vector((1, 0, 0))).length < 1e-9, pts      # every edge split in two
    assert len(pd.polygon_points(SQUARE + [(0, 0, 0)])) == 4, "a repeated first point is dropped"
    bent = [(0, 0, 0), (1, 0, 0.2), (1, 1, 0), (0, 1, 0.2)]
    flat = pd.polygon_points(bent, planar=True)
    n = pd.newell_normal(flat)
    assert max(abs((p - flat[0]).dot(n)) for p in flat) < 1e-9, "Keep new faces planar"
    kept = pd.polygon_points(bent, planar=False)
    assert abs(kept[1].z - 0.2) < 1e-6


def test_polygon_uvs_normalize_and_unitize():
    uv = pd.polygon_uvs(SQUARE, 'NORMALIZE')
    us, vs = [u for u, _v in uv], [v for _u, v in uv]
    assert min(us) == 0 and abs(max(us) - 1) < 1e-9 and abs(max(vs) - 0.5) < 1e-9, uv    # aspect kept
    uv = pd.polygon_uvs(SQUARE, 'UNITIZE')
    assert [tuple(round(c, 6) for c in p) for p in uv] != [], uv
    assert all(0 <= c <= 1 for p in uv for c in p)
    assert pd.polygon_uvs(SQUARE, 'NONE') is None


def test_build_polygon_is_one_ngon_with_map1():
    bm = bmesh.new()
    pts = [(math.cos(a), math.sin(a), 0) for a in (k * math.tau / 5 for k in range(5))]
    face = pd.build_polygon(bm, pts)
    assert face is not None and _counts(bm) == (5, 5, 1)
    assert bm.loops.layers.uv.active.name == "map1"
    assert face.normal.z > 0.99, "points counter-clockwise from above = normal up (Maya / Blender front)"
    bm.free()


def test_create_polygon_object_is_polysurface_n():
    _clear()
    s = pd.settings()
    pd.reset_settings(s, 'CREATE')
    pts = [Vector(p) + Vector((3, 4, 0)) for p in SQUARE]
    ob = pd.create_polygon_object(bpy.context, pts)
    assert ob.name == "polySurface1" and ob.data.name == "polySurfaceShape1", (ob.name, ob.data.name)
    assert (len(ob.data.vertices), len(ob.data.polygons)) == (4, 1)
    assert tuple(ob.location) == (0, 0, 0), "vertices in world space, pivot at the origin"
    assert min(v.co.x for v in ob.data.vertices) == 3
    assert ob.data.materials[0] is not None and ob.data.materials[0].get("allset_default"), "lambert1"
    assert bpy.context.view_layer.objects.active is ob and ob.select_get()
    s.cp_divisions = 3
    ob2 = pd.create_polygon_object(bpy.context, pts)
    assert ob2.name == "polySurface2" and len(ob2.data.vertices) == 12
    assert not ob.select_get(), "only the new polygon is selected"
    pd.reset_settings(s, 'CREATE')
    assert s.cp_divisions == 1
    assert pd.create_polygon_object(bpy.context, pts[:2]) is None, "fewer than 3 points: nothing"


# --- Append to Polygon ----------------------------------------------------------------------------------

def _open_box():
    """A 2-unit cube without its top face: 8 v / 12 e / 5 f, the 4 top edges are the border."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    top = next(f for f in bm.faces if f.calc_center_median().z > 0.9)
    bmesh.ops.delete(bm, geom=[top], context='FACES_ONLY')
    bm.normal_update()
    for seq in (bm.verts, bm.edges, bm.faces):
        seq.index_update()
        seq.ensure_lookup_table()
    return bm


def _border(bm):
    return [e for e in bm.edges if e.is_boundary]


def _consistent(bm):
    """Every manifold edge is used once in each direction."""
    for e in bm.edges:
        if len(e.link_loops) == 2:
            a, b = e.link_loops
            if a.vert is b.vert:
                return False
    return True


def test_append_face_on_a_border_edge_and_points():
    bm = _open_box()
    edge = _border(bm)[0]
    a, b = edge.verts
    out = (a.co + b.co) / 2
    out.z += 1.5
    face = pd.append_face(bm, [('EDGE', edge.index), ('POINT', a.co + Vector((0, 0, 1.5))),
                               ('POINT', b.co + Vector((0, 0, 1.5)))], planar=False)
    assert face is not None and _counts(bm) == (10, 15, 6), _counts(bm)
    assert edge in face.edges, "the new face shares the clicked border edge"
    assert _consistent(bm), "wound against the face it borders"
    bm.free()


def test_append_between_two_border_edges_closes_the_box():
    bm = _open_box()
    border = _border(bm)
    first = border[0]
    opposite = next(e for e in border if not set(e.verts) & set(first.verts))
    face = pd.append_face(bm, [('EDGE', first.index), ('EDGE', opposite.index)])
    assert face is not None and _counts(bm) == (8, 12, 6), _counts(bm)
    assert not _border(bm) and _consistent(bm)
    assert face.calc_center_median().z > 0.9 and face.normal.z > 0.99, "the lid faces out like the box"
    bm.free()


def test_append_divisions_split_only_new_edges():
    bm = _open_box()
    edge = _border(bm)[0]
    a, b = edge.verts
    up = Vector((0, 0, 1))
    face = pd.append_face(bm, [('EDGE', edge.index), ('POINT', a.co + up), ('POINT', b.co + up)],
                          divisions=2, planar=False)
    assert face is not None and len(face.verts) == 7, len(face.verts)     # 4 corners + 3 new edges split in two
    assert edge in face.edges
    bm.free()


def test_append_needs_three_points():
    bm = _open_box()
    assert pd.append_face(bm, [('EDGE', _border(bm)[0].index)]) is None
    assert _counts(bm) == (8, 12, 5)
    bm.free()


# --- Quad Draw: pure ----------------------------------------------------------------------------------

SCREEN_SQUARE = [(0, 0), (100, 0), (100, 100), (0, 100), (300, 300), (-200, 50)]


def test_fill_order_picks_the_four_around_the_mouse():
    ring = qd.fill_order(SCREEN_SQUARE, (50, 50))
    assert sorted(ring) == [0, 1, 2, 3], ring
    poly = [SCREEN_SQUARE[i] for i in ring]
    assert qd._area(poly) > 0, "counter-clockwise on screen"
    assert qd.fill_order(SCREEN_SQUARE, (2000, 2000)) is None
    tri = qd.fill_order([(0, 0), (100, 0), (50, 100)], (50, 30))
    assert sorted(tri) == [0, 1, 2]
    ring = qd.fill_order(SCREEN_SQUARE[:4], (60, 40), banned={frozenset((0, 1, 2, 3))})
    assert ring is not None and len(ring) == 3, "an existing face's 4 points: the triangle around the mouse"


def test_fill_face_from_dots_and_neighbour_winding():
    bm = bmesh.new()
    f1 = qd.fill_face(bm, [Vector((0, 0, 0)), Vector((1, 0, 0)), Vector((1, 1, 0)), Vector((0, 1, 0))])
    assert f1 is not None and f1.normal.z > 0.99
    v1 = next(v for v in bm.verts if v.co == Vector((1, 0, 0)))
    v2 = next(v for v in bm.verts if v.co == Vector((1, 1, 0)))
    # the next quad given clockwise (as if seen from below): flipped to agree with its neighbour
    f2 = qd.fill_face(bm, [v1, Vector((2, 0, 0)), Vector((2, 1, 0)), v2][::-1])
    assert f2 is not None and f2.normal.z > 0.99 and _consistent(bm)
    assert qd.fill_face(bm, list(f1.verts)) is None, "no second face on the same vertices"
    bm.free()


def _plane(n=1, size=1.0):
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=n, y_segments=n, size=size)
    for seq in (bm.verts, bm.edges, bm.faces):
        seq.index_update()
        seq.ensure_lookup_table()
    return bm


def test_extend_edges_edge_and_loop():
    bm = _plane()
    edge = next(e for e in bm.edges if all(v.co.x > 0.9 for v in e.verts))
    faces = qd.extend_edges(bm, [edge], lambda co: co + Vector((1, 0, 0)))
    assert len(faces) == 1 and _counts(bm) == (6, 7, 2) and _consistent(bm)
    assert all(f.normal.z > 0.99 for f in bm.faces)
    bm.free()
    bm = _plane()
    loop = qd.border_loop(bm.edges[0])
    assert len(loop) == 4
    faces = qd.extend_edges(bm, loop, lambda co: co * 2)
    assert len(faces) == 4 and _counts(bm) == (8, 12, 5) and _consistent(bm), _counts(bm)
    bm.free()


def _l_shape():
    """A 2 x 2 grid (z up) without its +x -y quad: the centre vertex is the inner (concave) corner of an L."""
    bm = _plane(n=2, size=1.0)
    gone = next(f for f in bm.faces if f.calc_center_median().x > 0 and f.calc_center_median().y < 0)
    bmesh.ops.delete(bm, geom=[gone], context='FACES')
    for seq in (bm.verts, bm.edges, bm.faces):
        seq.index_update()
        seq.ensure_lookup_table()
    return bm


def test_corner_quad_fills_the_inner_corner():
    """#180, Maya 2026 Quad Draw (Autodesk's Quad Draw help, Extend: Tab-drag a border vertex): the vertex, its two
    border neighbours and the point under the mouse make the new quad."""
    bm = _l_shape()
    centre = min(bm.verts, key=lambda v: v.co.length)
    assert qd.corner_neighbours(centre) is not None
    face = qd.corner_quad(bm, centre, Vector((0.9, -0.9, 0.0)))
    assert face is not None and _counts(bm) == (9, 12, 4), _counts(bm)
    assert centre in face.verts and _consistent(bm)
    assert all(f.normal.z > 0.99 for f in bm.faces)
    bm.free()


def test_corner_quad_refuses_folded_faces():
    """An outer corner / a straight border / the mouse on the wrong side: no face (it would overlap or fold)."""
    bm = _l_shape()
    outer = max(bm.verts, key=lambda v: v.co.x - v.co.y * 0 + v.co.y)   # (+x, +y): a corner of one face
    assert qd.corner_quad(bm, outer, outer.co + Vector((0.5, 0.5, 0))) is None
    mid = next(v for v in bm.verts if abs(v.co.x) < 1e-6 and v.co.y > 0.9)    # middle of the top border
    assert qd.corner_quad(bm, mid, mid.co + Vector((0, 0.6, 0))) is None
    centre = min(bm.verts, key=lambda v: v.co.length)
    assert qd.corner_quad(bm, centre, Vector((-0.9, 0.9, 0.0))) is None        # over the existing faces
    assert _counts(bm) == (8, 10, 3), _counts(bm)
    bm.free()


def test_strip_pairs_and_faces():
    pairs = qd.strip_pairs([(0, 0), (100, 0)], 20)
    assert len(pairs) == 6, pairs
    (l0, r0), (l1, _r1) = pairs[0], pairs[1]
    assert abs(l0[1] - r0[1] - 20) < 1e-9 and abs(l1[0] - l0[0] - 20) < 1e-9
    assert qd.strip_pairs([(0, 0), (10, 0)], 20) == []
    bm = bmesh.new()
    faces = qd.strip_faces(bm, [(Vector((x, y1, 0)), Vector((x, y2, 0))) for (x, y1), (_x, y2) in
                                ((l, r) for l, r in pairs)])
    assert len(faces) == 5 and all(f.normal.z > 0.99 for f in faces) and _consistent(bm)
    bm.free()


def test_relax_auto_lock_and_modes():
    bm = _plane(2)
    centre = next(v for v in bm.verts if not v.is_boundary)
    centre.co += Vector((0.3, 0.2, 0))
    before = {v: v.co.copy() for v in bm.verts}
    moved = qd.relax(bm, list(bm.verts), 'AUTO_LOCK')
    assert moved == [centre] and centre.co.length < before[centre].length
    assert all(v.co == before[v] for v in bm.verts if v.is_boundary), "Auto-Lock keeps the border"
    border = [v for v in bm.verts if v.is_boundary]
    assert qd.relax(bm, border, 'AUTO_LOCK'), "only border vertices under the brush: they relax"
    assert qd.relax(bm, border, 'INTERIOR') == []
    flat = qd.relax(bm, [centre], 'AUTO_LOCK', project=lambda co: Vector((co.x, co.y, 5.0)))
    assert flat and abs(centre.co.z - 5.0) < 1e-9, "projected back on the surface"
    bm.free()


def test_delete_at_face_edge_vertex():
    bm = _plane(2)
    assert qd.delete_at(bm, 'FACE', 0) and len(bm.faces) == 3
    bm.free()
    bm = _plane(2)
    inner = next(e for e in bm.edges if len(e.link_faces) == 2)
    assert qd.delete_at(bm, 'EDGE', inner.index) and len(bm.faces) == 3, "an inner edge dissolves (2 faces -> 1)"
    bm.free()
    bm = _plane(2)
    centre = next(v for v in bm.verts if not v.is_boundary)
    assert qd.delete_at(bm, 'VERT', centre.index) and len(bm.faces) == 1
    bm.free()
    bm = _plane(1)
    assert qd.delete_at(bm, 'EDGE', 0) and len(bm.faces) == 0, "a border edge takes its face"
    bm.free()


def test_dots_are_flagged_loose_vertices():
    bm = bmesh.new()
    a = qd.add_dot(bm, Vector((0, 0, 0)))
    b = qd.add_dot(bm, Vector((1, 0, 0)))
    bm.verts.new((2, 0, 0))                              # a loose vertex the user made: not a dot
    assert set(qd.dots(bm)) == {a, b}
    assert a in qd.fill_candidates(bm)
    bm.edges.new((a, b))
    assert qd.dots(bm) == [], "a dot with an edge is a vertex"
    bm.free()
    bm = bmesh.new()
    for x in range(3):
        qd.add_dot(bm, Vector((x, 0, 0)))
    assert qd.clear_dots(bm) == 3 and not bm.verts
    bm.free()


def test_edge_loop_walks_across_quads():
    bm = _plane(3)
    inner = next(e for e in bm.edges if len(e.link_faces) == 2)
    loop = qd.edge_loop(inner)
    assert len(loop) == 3, len(loop)                     # a 3 x 3 grid: the loop crosses it, border to border
    xs = {round(v.co.x, 4) for e in loop for v in e.verts}
    ys = {round(v.co.y, 4) for e in loop for v in e.verts}
    assert len(xs) == 1 or len(ys) == 1, "a straight line"
    bm.free()


def test_delete_loop():
    bm = _plane(3)
    inner = next(e for e in bm.edges if len(e.link_faces) == 2)
    assert qd.delete_loop(bm, inner.index) and len(bm.faces) == 6, len(bm.faces)    # 9 faces, one loop of 3 gone
    bm.free()


def test_weld_target():
    xy = [(0, 0), (5, 0), (50, 0), None]
    assert qd.weld_target(xy, 0, (0, 0), 10) == 1
    assert qd.weld_target(xy, 0, (0, 0), 10, exclude={1}) is None
    assert qd.weld_target(xy, 2, (50, 0), 10) is None


# --- Quad Draw: on the scene ----------------------------------------------------------------------------

def test_reference_surface_and_projection():
    _clear()
    bpy.ops.mesh.primitive_uv_sphere_add(radius=2.0, segments=32, ring_count=16)
    sphere = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(size=0.5, location=(10, 0, 0))
    cube = bpy.context.active_object
    refs = qd.reference_objects(bpy.context)
    assert refs == [], "without a live surface Quad Draw uses the construction plane, like Maya"
    bpy.context.scene.allset_live = sphere
    try:
        assert qd.reference_objects(bpy.context) == [sphere]
        p = qd.project_point(bpy.context, Vector((0, 0, 5)))
        assert abs(p.length - 2.0) < 0.05, p
    finally:
        bpy.context.scene.allset_live = None


def test_quad_draw_target_and_fill_on_an_edit_mesh():
    _clear()
    bpy.ops.mesh.primitive_plane_add(size=10)
    ground = bpy.context.active_object
    bpy.context.scene.allset_live = ground
    try:
        ground.select_set(True)
        assert qd.pick_target(bpy.context) is None, "the live surface is never the edited mesh"
        ob = qd.new_target(bpy.context)
        assert ob.name == "polySurface1" and not ob.data.vertices
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(ob.data)
        ring = [qd.add_dot(bm, Vector(c)).index for c in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))]
        qd.add_dot(bm, Vector((5, 5, 0)))
        bmesh.update_edit_mesh(ob.data)
        face = qd.apply_fill(ob, ring)
        bm = bmesh.from_edit_mesh(ob.data)
        assert face is not None and len(qd.dots(bm)) == 1, "the 4 dots became the quad's vertices"
        qd.STATE["ob"] = ob.name
        qd._drop_dots(ob.name)
        bpy.ops.object.mode_set(mode='OBJECT')
        assert (len(ob.data.vertices), len(ob.data.polygons)) == (4, 1), "leaving the tool clears the last dot"
        assert qd.DOT_LAYER not in ob.data.attributes, "and the dot layer"
    finally:
        bpy.context.scene.allset_live = None
        qd.STATE["ob"] = None


# --- wiring: menus, shelf, hotkey, tools, settings ------------------------------------------------------

def _tool_ids(mode):
    from bl_ui.space_toolsystem_common import ToolSelectPanelHelper
    from bl_ui.space_toolsystem_toolbar import VIEW3D_PT_tools_active
    return [it.idname for it, _i in ToolSelectPanelHelper._tools_flatten_with_tool_index(
        VIEW3D_PT_tools_active.tools_from_context(bpy.context, mode)) if it is not None]


def test_menus_shelf_hotkey_are_the_kit_tools():
    assert menu_map.MAP["Mesh Tools/Quad Draw"] == "allset.quad_draw_start"
    assert menu_map.MAP["Mesh Tools/Create Polygon"] == "allset.create_polygon_start"
    assert menu_map.MAP["Mesh Tools/Append to Polygon"] == "allset.append_polygon_start"
    assert shelf_map.BY_COMMAND["QuadDrawTool"][0] == "allset.quad_draw_start"
    for km in ("Object Mode", "Mesh"):
        hot = [k.idname for k in kit.maya_kc().keymaps[km].keymap_items
               if k.active and k.type == 'Q' and k.ctrl and k.shift and not k.alt]
        assert hot == ["allset.quad_draw_start"], (km, hot)
    for tool in (qd.TOOL, pd.CREATE_TOOL, pd.APPEND_TOOL):
        assert command_line.help_for_tool(tool), tool
    assert "Poly Build" not in repr([menu_map.MAP.get(p) for p in
                                     ("Mesh Tools/Quad Draw", "Mesh Tools/Create Polygon",
                                      "Mesh Tools/Append to Polygon")])


def test_tools_and_keymaps_registered_and_removed():
    edit = _tool_ids('EDIT_MESH')
    assert {qd.TOOL, pd.CREATE_TOOL, pd.APPEND_TOOL} <= set(edit), edit
    assert pd.CREATE_TOOL in _tool_ids('OBJECT')
    kms = bpy.context.window_manager.keyconfigs.addon.keymaps
    km = kms.get("3D View Tool: Edit Mesh, Quad Draw")
    assert km is not None
    items = [(k.idname, k.type, k.value, k.any) for k in km.keymap_items]
    assert ("allset.quad_draw", 'LEFTMOUSE', 'PRESS', True) in items, items
    assert ("allset.quad_draw", 'MIDDLEMOUSE', 'PRESS', True) in items, "MMB with Ctrl / Shift / Ctrl+Shift"
    assert ("allset.quad_draw_tab", 'TAB', 'PRESS', False) in items
    assert any(i[:2] == ("allset.quad_draw_hover", 'MOUSEMOVE') for i in items)
    names = [k.name for k in kms]
    assert any("Create Polygon" in n for n in names) and any("Append to Polygon" in n for n in names), names
    kit.disable()
    try:
        assert qd.TOOL not in _tool_ids('EDIT_MESH') and pd.CREATE_TOOL not in _tool_ids('OBJECT')
        assert bpy.context.window_manager.keyconfigs.addon.keymaps.get("3D View Tool: Edit Mesh, Quad Draw") is None
        assert not hasattr(bpy.types.Scene, "allset_poly_tools")
    finally:
        kit.enable()
    assert qd.TOOL in _tool_ids('EDIT_MESH')


def test_tool_settings_kinds_defaults_and_reset():
    assert ts_mod.KIND_OF[qd.TOOL] == 'QUAD_DRAW'
    assert ts_mod.KIND_OF[pd.CREATE_TOOL] == 'CREATE_POLYGON'
    assert ts_mod.KIND_OF[pd.APPEND_TOOL] == 'APPEND_POLYGON'
    assert "builtin.poly_build" not in ts_mod.KIND_OF
    s = pd.settings()
    for kind in pd.SETTINGS:
        pd.reset_settings(s, kind)
    # Maya 2022 factory Tool Settings of Quad Draw / Create Polygon / Append to Polygon
    want = {"qd_auto_weld": True, "qd_weld_px": 10, "qd_relax": 'AUTO_LOCK', "qd_extend": 'EDGE',
            "qd_strip_width": 20, "qd_snap_backfaces": False,
            "cp_divisions": 1, "cp_limit_on": False, "cp_limit_points": 4, "cp_keep_planar": False,
            "cp_texture": 'NORMALIZE',
            "ap_divisions": 1, "ap_rotation_angle": 0.0, "ap_limit_on": False, "ap_limit_points": 4,
            "ap_keep_planar": False, "ap_texture": 'NORMALIZE'}
    assert {k: getattr(s, k) for k in want} == want
    s.qd_strip_width, s.cp_limit_points, s.cp_limit_on = 33, 5, True
    ts_mod.reset_kind_defaults(bpy.context, 'QUAD_DRAW')
    ts_mod.reset_kind_defaults(bpy.context, 'CREATE_POLYGON')
    assert (s.qd_strip_width, s.cp_limit_points, s.cp_limit_on) == (20, 4, False)
    assert [t for _k, t, _o in ts_mod.sections('CREATE_POLYGON')] == ["Description", "Settings",
                                                                      "Keyboard/Mouse Shortcuts"]
    assert ts_mod.TOOL_NAMES['APPEND_POLYGON'] == "Append To Polygon Tool"
    titles = [t for _k, t, _o in ts_mod.sections('QUAD_DRAW')]
    assert titles == ["Settings", "Live Constraint Options", "Keyboard/Mouse Shortcuts"], titles
    for key in ui_poly.GREY:
        assert key in notices.PANEL_NOTICES
