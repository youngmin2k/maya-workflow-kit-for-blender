"""Quad Draw's live constraints, display settings and Maya option behaviour."""
from importlib import import_module
import bmesh
import bpy
from mathutils import Color, Vector
import kit

qd = import_module(kit.MODULE + '.operators.quad_draw')
pd = import_module(kit.MODULE + '.operators.poly_draw')
live = import_module(kit.MODULE + '.operators.live')


def fresh():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    live.set_objects(bpy.context.scene, [])
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    pd.reset_settings(pd.settings(), 'QUAD_DRAW')


def test_no_live_uses_grid_instead_of_unrelated_visible_meshes():
    fresh()
    bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 0, 5))
    assert qd.reference_objects(bpy.context) == []
    live.set_objects(bpy.context.scene, [bpy.context.object])
    assert len(qd.reference_objects(bpy.context)) == 1


def test_offset_is_applied_along_surface_normal_and_resets():
    fresh()
    bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 0, 2))
    live.set_objects(bpy.context.scene, [bpy.context.object])
    s = pd.settings()
    s.qd_offset_on, s.qd_surface_offset = True, 0.125
    p = qd.project_point(bpy.context, Vector((0, 0, 3)))
    assert abs(p.z - 2.125) < 1e-5, p
    s.qd_mesh_color, s.qd_mesh_alpha, s.qd_wire_overlay = (1, 0, 0), .2, False
    pd.reset_settings(s, 'QUAD_DRAW')
    assert not s.qd_offset_on and s.qd_mesh_alpha == .75 and s.qd_wire_overlay
    display=Color(s.qd_mesh_color).from_scene_linear_to_srgb()
    assert tuple(round(v*255) for v in display)==(1,172,255),tuple(display)


def test_offset_follows_scene_length_units_and_unit_scale():
    fresh()
    us=bpy.context.scene.unit_settings
    saved=us.system,us.length_unit,us.scale_length
    s=pd.settings();s.qd_offset_on=True;s.qd_surface_offset=.1
    try:
        us.system='METRIC'
        for length,scale,distance in (('CENTIMETERS',1,.001),('CENTIMETERS',.01,.1),
                                      ('MILLIMETERS',1,.0001),('METERS',1,.1)):
            us.length_unit=length;us.scale_length=scale
            point=qd._surface_point(bpy.context,(Vector(),Vector((0,0,1))))
            assert abs(point.z-distance)<1e-7,(length,scale,point)
        us.length_unit='CENTIMETERS';us.scale_length=1
        s.qd_surface_offset=-.1
        assert abs(qd.surface_offset(bpy.context)+.001)<1e-8
        s.qd_offset_on=False
        assert qd.surface_offset(bpy.context)==0
    finally:
        us.system,us.length_unit,us.scale_length=saved


def test_all_relax_includes_interior_and_boundary_neighbours():
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=3, y_segments=3, size=1)
    bm.normal_update()
    verts = list(bm.verts)
    inner = next(v for v in verts if not v.is_boundary)
    corner = min(verts, key=lambda v: v.co.x + v.co.y)
    inner.co.x += .13
    before = {v: v.co.copy() for v in verts}
    moved = qd.relax(bm, verts, 'ALL')
    assert inner in moved and corner in moved
    assert (corner.co - before[corner]).length > .01
    bm.free()


def test_extend_loop_stops_at_corners_border_continues():
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=3, y_segments=3, size=1)
    bm.normal_update()
    edge = next(e for e in bm.edges if e.is_boundary)
    assert len(qd.border_chain(edge)) == 3
    assert len(qd.border_loop(edge)) == 12
    bm.free()


def test_soft_selection_disables_auto_weld():
    s = bpy.context.scene
    previous = s.allset_soft_select
    try:
        s.allset_soft_select = True
        assert qd._weld_px(bpy.context) is None
        s.allset_soft_select = False
        assert qd._weld_px(bpy.context) is not None
    finally:
        s.allset_soft_select = previous
