"""The Maya pivot concept, snapping and the Maya-shaped manipulator, checked headless."""

import math
from importlib import import_module

import bpy
from mathutils import Matrix, Vector

import kit

pivot = import_module(kit.MODULE + ".operators.pivot")
hold = import_module(kit.MODULE + ".operators.hold")
freeze = import_module(kit.MODULE + ".operators.freeze")
manipulator = import_module(kit.MODULE + ".ui.manipulator")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
snap_align = import_module(kit.MODULE + ".operators.snap_align")

TOL = 1e-4


def _fresh():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)
    ts = bpy.context.scene.tool_settings
    ts.use_transform_data_origin = ts.use_transform_skip_children = False
    for slot in bpy.context.scene.transform_orientation_slots:
        try:
            slot.type = 'DEFAULT'
        except TypeError:
            slot.type = 'GLOBAL'
    bpy.context.scene.transform_orientation_slots[0].type = 'GLOBAL'


def _cube(name="pCube1", loc=(0, 0, 0)):
    me = bpy.data.meshes.new(name + "Shape")
    v = [(x, y, z) for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    me.from_pydata(v, [], f)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    return ob


def _select(*obs, active=None):
    bpy.context.view_layer.update()
    for o in bpy.data.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = active or obs[-1]


def _world_verts(ob):
    bpy.context.view_layer.update()
    return [ob.matrix_world @ v.co for v in ob.data.vertices]


def _same_points(a, b):
    return all((p - q).length < TOL for p, q in zip(a, b))


def _origin_transform(op, **kw):
    """Run a transform with Affect Only Origins (+ Parents), like D held, then the kit rewrite."""
    ts = bpy.context.scene.tool_settings
    hold.set_pivot_mode(ts, True)
    pivot.process()                   # baseline
    snaps = {ob.name: pivot.snapshot(ob) for ob in bpy.context.selected_objects}
    getattr(bpy.ops.transform, op)(**kw)
    bpy.context.view_layer.update()
    turned = None
    for ob in bpy.context.selected_objects:
        axes = pivot.rewrite(ob, snaps[ob.name])
        turned = axes if axes is not None else turned
    if turned is not None:
        pivot.set_custom_orientation(bpy.context, turned)
    hold.set_pivot_mode(ts, False)
    pivot.stop()
    bpy.context.view_layer.update()
    return turned


# --- pivot (P1-P9) -----------------------------------------------------------------------------

def test_pivot_move_keeps_translate_geometry_children():
    _fresh()
    ob = _cube(loc=(1, 0, 0))
    child = bpy.data.objects.new("locator1", None)
    bpy.context.scene.collection.objects.link(child)
    child.parent = ob
    child.location = (2, 0, 0)
    _select(ob)
    before = _world_verts(ob)
    child_w = child.matrix_world.copy()
    _origin_transform("translate", value=(0.5, 0.5, 0.5))
    assert (Vector(ob.location) - Vector((1, 0, 0))).length < TOL, f"translate changed: {ob.location[:]}"
    assert (Vector(ob.delta_location) - Vector((0.5, 0.5, 0.5))).length < TOL, ob.delta_location[:]
    assert (ob.matrix_world.translation - Vector((1.5, 0.5, 0.5))).length < TOL
    assert _same_points(before, _world_verts(ob)), "geometry moved"
    assert (child.matrix_world.translation - child_w.translation).length < TOL, "child moved"
    # P1: rotating afterwards turns about the new pivot
    ob.rotation_euler.z = math.radians(90)
    bpy.context.view_layer.update()
    assert (ob.matrix_world.translation - Vector((1.5, 0.5, 0.5))).length < TOL


def test_pivot_rotate_becomes_custom_orientation_then_bake():
    _fresh()
    ob = _cube(loc=(1, 0, 0))
    _select(ob)
    before = _world_verts(ob)
    turned = _origin_transform("rotate", value=math.radians(45), orient_axis='Z')
    assert turned is not None, "pivot orientation not detected"
    assert Vector(ob.rotation_euler).length < TOL, f"rotate channels changed: {ob.rotation_euler[:]}"
    assert _same_points(before, _world_verts(ob)), "geometry moved"
    assert pivot.PROP in ob, "custom pivot orientation not stored on the object"
    slot = bpy.context.scene.transform_orientation_slots[pivot.MOVE_SLOT]
    assert slot.type == pivot.ORIENT_NAME, slot.type
    m = slot.custom_orientation.matrix.copy()
    assert abs(abs(Vector(m.col[0]).dot(Vector((1, 0, 0)))) - math.cos(math.radians(45))) < 1e-3, m
    # Bake Pivot: orientation into rotate, geometry stays, axis mode back to Object (P8)
    bpy.ops.allset.bake_pivot()
    assert abs(abs(ob.rotation_euler.z) - math.radians(45)) < 1e-3, ob.rotation_euler[:]
    bpy.context.view_layer.update()
    got = ob.matrix_world.to_3x3().normalized()
    assert all(abs(got[i][j] - m[i][j]) < 1e-3 for i in range(3) for j in range(3)), (got, m)
    assert _same_points(before, _world_verts(ob)), "bake moved the geometry"
    assert pivot.PROP not in ob
    assert slot.type == 'LOCAL', slot.type


def test_reset_and_match_pivots():
    _fresh()
    a = _cube("pCube1", loc=(1, 0, 0))
    b = _cube("pCube2", loc=(-3, 0, 0))
    _select(a)
    before = _world_verts(a)
    freeze.shift_pivot(a, Vector((2, 2, 0)))
    bpy.context.view_layer.update()
    bpy.ops.allset.reset_pivot()
    bpy.context.view_layer.update()
    assert Vector(a.delta_location).length < TOL and (Vector(a.location) - Vector((1, 0, 0))).length < TOL
    assert _same_points(before, _world_verts(a))
    # Match Pivots: a's pivot onto b's (last selected), translate and geometry stay (P7)
    freeze.shift_pivot(b, Vector((0, 0.5, 1)))
    bpy.context.view_layer.update()
    _select(a, b, active=b)
    bpy.ops.allset.match_pivots()
    bpy.context.view_layer.update()
    assert (a.matrix_world.translation - b.matrix_world.translation).length < TOL
    assert (Vector(a.location) - Vector((1, 0, 0))).length < TOL
    assert _same_points(before, _world_verts(a))


def test_freeze_keeps_pivot_after_pivot_move():
    _fresh()
    ob = _cube(loc=(2, 1, 0))
    _select(ob)
    _origin_transform("translate", value=(0.5, 0, 0))
    bpy.ops.allset.freeze_transform()
    bpy.context.view_layer.update()
    assert Vector(ob.location).length < TOL
    assert (ob.matrix_world.translation - Vector((2.5, 1, 0))).length < TOL   # P4


def test_pivot_point_per_mode():
    ts = bpy.context.scene.tool_settings
    ts.transform_pivot_point = 'ACTIVE_ELEMENT'
    assert pivot.maya_pivot_point(ts, 'EDIT_MESH') and ts.transform_pivot_point == 'BOUNDING_BOX_CENTER'
    assert pivot.maya_pivot_point(ts, 'OBJECT') and ts.transform_pivot_point == 'ACTIVE_ELEMENT'
    ts.transform_pivot_point = 'CURSOR'      # a user choice stays
    assert not pivot.maya_pivot_point(ts, 'EDIT_MESH') and ts.transform_pivot_point == 'CURSOR'
    ts.transform_pivot_point = 'MEDIAN_POINT'


def test_hold_pivot_mode_skips_children_and_restores():
    ts = bpy.context.scene.tool_settings
    ts.use_transform_data_origin = ts.use_transform_skip_children = False
    hold.begin(ts, "pivot")
    assert ts.use_transform_data_origin and ts.use_transform_skip_children
    hold.end(ts, "pivot")
    assert not ts.use_transform_data_origin and not ts.use_transform_skip_children
    pivot.stop()


# --- snapping (S2-S11) ----------------------------------------------------------------------------

def test_hold_snap_uses_manipulator_centre():
    ts = bpy.context.scene.tool_settings
    ts.snap_target = 'CLOSEST'
    hold.begin(ts, "grid")
    assert ts.snap_target == 'CENTER' and set(ts.snap_elements) == {'GRID'}
    hold.end(ts, "grid")
    assert ts.snap_target == 'CLOSEST'


def test_snap_point_to_point_objects_and_vertices():
    _fresh()
    a = _cube("pCube1")
    b = _cube("pCube2", loc=(4, 1, 0))
    b.rotation_euler.z = math.radians(30)
    bpy.context.view_layer.update()
    # object mode: pivot onto pivot
    _select(a, b, active=b)
    assert snap_align.snap_points(bpy.context, 1)
    bpy.context.view_layer.update()
    assert (a.matrix_world.translation - b.matrix_world.translation).length < TOL
    # vertices: a's vertex 0 onto b's vertex 7 (S9: translation only)
    a.location = (0, 0, 0)
    bpy.context.view_layer.update()
    src = [a.matrix_world @ a.data.vertices[0].co]
    dst = [b.matrix_world @ b.data.vertices[7].co]
    m = snap_align.points_transform(src, dst)
    a.matrix_world = m @ a.matrix_world
    bpy.context.view_layer.update()
    assert ((a.matrix_world @ a.data.vertices[0].co) - dst[0]).length < TOL
    assert Vector(a.rotation_euler).length < TOL


def test_snap_two_and_three_points_rotate():
    src = [Vector((0, 0, 0)), Vector((1, 0, 0)), Vector((0, 1, 0))]
    rot = Matrix.Rotation(math.radians(30), 4, 'Z')
    dst = [Vector((3, 1, 0)) + (rot @ p) for p in src]
    for n in (2, 3):
        m = snap_align.points_transform(src[:n], dst[:n])
        for p, q in zip(src[:n], dst[:n]):
            assert ((m @ p) - q).length < 1e-4, (n, m @ p, q)
    # 3 points with a tilt
    rot2 = Matrix.Rotation(math.radians(20), 4, 'X') @ rot
    dst = [Vector((3, 1, 0)) + (rot2 @ p) for p in src]
    m = snap_align.points_transform(src, dst)
    for p, q in zip(src, dst):
        assert ((m @ p) - q).length < 1e-4


def test_align_objects_mid_x_average():
    _fresh()
    a = _cube("pCube1", loc=(0, 0, 0))
    c = _cube("pCube3", loc=(-3, 2, 1))
    c.scale = (2, 3, 1)
    bpy.context.view_layer.update()
    _select(a, c, active=c)
    snap_align.align_objects(bpy.context, axes=(True, False, False), mode='MID')
    bpy.context.view_layer.update()
    ca = snap_align.bbox_world(a)
    cc = snap_align.bbox_world(c)
    mid = lambda bb: (bb[0].x + bb[1].x) / 2
    assert abs(mid(ca) - mid(cc)) < TOL and abs(mid(ca) - (-1.5)) < TOL, (mid(ca), mid(cc))
    assert abs(c.location.y - 2) < TOL and abs(a.location.y) < TOL   # other axes untouched (S11)


def test_make_live():
    _fresh()
    p = _cube("pPlane1")
    _select(p)
    ts = bpy.context.scene.tool_settings
    before = (ts.use_snap, set(ts.snap_elements))
    bpy.ops.allset.make_live()
    assert bpy.context.scene.allset_live == p
    assert p.hide_select and not p.select_get()
    assert (ts.use_snap, set(ts.snap_elements)) == before
    for o in bpy.data.objects:
        o.select_set(False)
    bpy.ops.allset.make_live()
    assert bpy.context.scene.allset_live is None and not p.hide_select
    assert (ts.use_snap, set(ts.snap_elements)) == before


# --- manipulator (M1-M7) ----------------------------------------------------------------------

def test_tools_use_the_maya_manipulator():
    from bl_ui.space_toolsystem_toolbar import VIEW3D_PT_tools_active
    from bl_ui.space_toolsystem_common import ToolSelectPanelHelper
    for mode in ('OBJECT', 'EDIT_MESH', 'EDIT_CURVE', 'EDIT_SURFACE'):
        widgets = {it.idname: it.widget for it, _i in
                   ToolSelectPanelHelper._tools_flatten_with_tool_index(VIEW3D_PT_tools_active._tools[mode])
                   if it is not None}
        for idname in ("builtin.move", "builtin.rotate", "builtin.scale"):
            assert widgets[idname] == manipulator.GROUP, (mode, idname, widgets[idname])
        assert widgets["builtin.transform"] == "VIEW3D_GGT_xform_gizmo", mode
    for mode in ('POSE',):
        widgets = {it.idname: it.widget for it, _i in
                   ToolSelectPanelHelper._tools_flatten_with_tool_index(VIEW3D_PT_tools_active._tools[mode])
                   if it is not None}
        assert widgets.get("builtin.move") == "VIEW3D_GGT_xform_gizmo", mode


def test_shapes_and_centre():
    for kind in ('ARROW', 'SCALE_AXIS', 'PLANE', 'CENTER', 'CENTER_CUBE', 'PIVOT_CENTER', 'PIVOT_RING'):
        draw, pick = manipulator.shapes(kind)
        assert draw and pick[1], kind
        for t, verts in draw + [pick]:
            assert len(verts) % (2 if t == 'LINES' else 3) == 0, (kind, t)
    tip = max(v[2] for t, verts in manipulator.shapes('ARROW')[0] for v in verts)
    assert abs(tip - 1.0) < 1e-6      # arrow length = 1 unit
    pts = [Vector((-0.183, -0.5, 0.683)), Vector((0.683, -0.5, 0.183)), Vector((0.683, 0.5, 0.183))]
    bb = manipulator.center_of(pts, None, 'BOUNDING_BOX_CENTER', Vector())
    assert (bb - Vector((0.25, 0.0, 0.433))).length < 1e-3       # P10 (Maya manip position)
    act = manipulator.center_of(pts, pts[2], 'ACTIVE_ELEMENT', Vector())
    assert act == pts[2]
    med = manipulator.center_of(pts, None, 'MEDIAN_POINT', Vector())
    assert abs(med.x - 0.3943) < 1e-3


def test_rotate_gimbal_rings():
    """Gimbal rings: the last applied Euler axis stays the parent's, earlier ones turn with the later rotations."""
    import math
    ob = bpy.data.objects.new("gimbal_probe", None)
    bpy.context.scene.collection.objects.link(ob)
    try:
        ob.rotation_mode = 'XYZ'
        ob.rotation_euler = (0.3, math.pi / 2, 0.0)
        bpy.context.view_layer.update()
        g = manipulator.gimbal_axes(ob)
        assert (g.col[2] - Vector((0, 0, 1))).length < 1e-6, g.col[2]       # Z: applied last
        assert (g.col[1] - Vector((0, 1, 0))).length < 1e-6, g.col[1]       # Y: turned by Z only (0)
        assert (g.col[0] - Vector((0, 0, -1))).length < 1e-6, g.col[0]      # X: turned by Y 90 deg onto -Z
        ob.rotation_mode = 'QUATERNION'
        bpy.context.view_layer.update()
        q = manipulator.gimbal_axes(ob)
        own = ob.matrix_world.to_3x3().normalized()
        assert all((q.col[i] - own.col[i]).length < 1e-6 for i in range(3))
    finally:
        bpy.data.objects.remove(ob)
    assert set(manipulator.TOOLS.values()) == {'TRANSLATE', 'ROTATE', 'RESIZE'}


def test_rotate_ring_front_half():
    """A ring is drawn / picked on the viewer's half only; a ring facing the view stays whole."""
    from mathutils import Matrix
    m = Matrix.Translation((1.0, 2.0, 3.0)) @ Matrix.Scale(2.0, 4)
    arcs = manipulator.front_arcs(m, Vector((0.0, -1.0, 0.0)))
    assert len(arcs) == 1, len(arcs)
    pts = arcs[0]
    assert all(p.y - 2.0 <= 0.02 * 2.0 + 1e-6 for p in pts)
    assert min(p.y for p in pts) < 2.0 - 1.99                     # reaches the near side
    assert abs(min(p.x for p in pts) - (1.0 - 2.0)) < 0.05 and abs(max(p.x for p in pts) - 3.0) < 0.05
    whole = manipulator.front_arcs(m, Vector((0.0, 0.0, 1.0)))
    assert len(whole) == 1 and len(whole[0]) == manipulator.RING_STEPS + 1
    # the front half straddles angle 0: one arc, not two
    wrap = manipulator.front_arcs(m, Vector((1.0, 0.0, 0.0)))
    assert len(wrap) == 1 and all(p.x >= 1.0 - 0.05 for p in wrap[0])


def test_orientation_slots_per_tool():
    scene = bpy.context.scene
    slots = scene.transform_orientation_slots
    slots[0].type = 'GLOBAL'
    slots[2].type = 'LOCAL'
    assert manipulator.slot_type(scene, 'ROTATE') == 'LOCAL'
    slots[1].type = 'DEFAULT'
    assert manipulator.slot_type(scene, 'TRANSLATE') == 'GLOBAL'


# --- menus (S8) ---------------------------------------------------------------------------------

def test_modify_menu_pivot_and_align_sections():
    modify = next(m for m in menu_sets.menu_data.MENUS.values() if m[0] == "Modify")
    items = [it[0] for _p, it in menu_sets.children(modify[3], "Modify") if it[0] != "-"]
    sub = {it[0]: it for it in modify[3]}          # the submenus follow Maya 2026
    items += [it[0] for it in sub["Snap Align Objects"][1]]
    i_match = items.index("Match Transformations")
    i_pivot = items.index("Center Pivot")
    i_align = items.index("Snap Align Objects")
    assert "Match Pivots" in [it[0] for it in sub["Match Transformations"][1]]
    assert i_match < i_pivot < i_align, items
    assert "Bake Pivot" in items
    assert menu_map.MAP["Modify/Bake Pivot"] == "allset.bake_pivot"
    assert menu_map.MAP["Modify/Match Transformations/Match Pivots"] == "allset.match_pivots"
    for label in ("Point to Point", "2 Points to 2 Points", "3 Points to 3 Points", "Align Objects"):
        assert f"Modify/Snap Align Objects/{label}" in menu_map.MAP, label
    assert menu_map.MAP["Modify/Snap Together Tool"] == "allset.snap_together"
    assert menu_map.MAP["Modify/Make Live"] == "allset.make_live"


def test_move_tool_keeps_select_fallback():
    """The Maya manipulator group keeps the tool's select fallback (marquee in empty space)."""
    area = next((a for a in bpy.context.screen.areas if a.type == 'VIEW_3D'), None)
    if area is None:
        return
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
        tool = bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=False)
        assert tool.widget == manipulator.GROUP, tool.widget
        assert tool.idname_fallback == "builtin.select", repr(tool.idname_fallback)
