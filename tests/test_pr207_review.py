# SPDX-License-Identifier: GPL-3.0-or-later
"""PR #207 follow-ups: Prevent Negative Scale on the kit Scale drag, D pivot editing keeps the selection, Smart
Extrude leaves no stray points on straight edges, Make Live drops deleted objects, the Status Line magnet turns
Make Live off, and the new drags open no Adjust Last Operation panel."""
from importlib import import_module
from types import SimpleNamespace

import bmesh
import bpy
from mathutils import Vector

import kit

ms = import_module(kit.MODULE + '.operators.manip_scale')
hold = import_module(kit.MODULE + '.operators.hold')
pivot = import_module(kit.MODULE + '.operators.pivot')
live = import_module(kit.MODULE + '.operators.live')
smart = import_module(kit.MODULE + '.operators.smart_extrude')


def _object_mode():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def _clear():
    _object_mode()
    for scene in bpy.data.scenes:
        live.set_objects(scene, [])
        scene.allset_live_history.clear()
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)


def _drag(clamp, d, mode='AXIS'):
    op = SimpleNamespace(_press=(0, 0), _mode=mode, _dir=Vector((1, 0)), _len=100.0, _depth0=1.0, _depth_tip=1.0,
                         _snap=False, _wpp=0.01, _radius=1.0, _clamp=clamp)
    return ms.drag_factor(op, d, 0)


def test_prevent_negative_scale_stops_the_kit_axis_drag_at_zero():
    assert _drag(False, -300) < 0.0                      # past zero: the plain drag flips
    assert _drag(True, -300) == 0.0                      # Prevent Negative Scale: flat, not flipped
    assert _drag(True, 50) == _drag(False, 50) > 0.0     # above zero both agree


def test_prevent_negative_scale_stops_plane_and_centre_handles_at_zero():
    """#261: the plane and centre handles stop at zero too, so components can be scaled onto the pivot."""
    for mode in ('PLANE', 'CENTER'):
        assert _drag(False, -300, mode) < 0.0, mode
        assert _drag(True, -300, mode) == 0.0, mode
        assert _drag(True, 30, mode) == _drag(False, 30, mode) > 0.0, mode


def test_clamp_is_on_for_every_handle_in_component_mode_only():
    prefs = import_module(kit.MODULE + '.preferences')
    cs = import_module(kit.MODULE + '.operators.component_scale')
    _clear()
    bpy.ops.mesh.primitive_cube_add()
    prefs.get(bpy.context).prevent_negative_scale = True
    bpy.ops.object.mode_set(mode='EDIT')
    assert cs.enabled(bpy.context)
    _object_mode()
    assert not cs.enabled(bpy.context), "object mode keeps negative scaling"


def test_d_pivot_edit_keeps_an_edge_selection():
    _clear()
    hold.unregister_cleanup()
    pivot.stop()
    bpy.ops.mesh.primitive_plane_add()
    ob = bpy.context.active_object
    ts = bpy.context.tool_settings
    ts.mesh_select_mode = (False, True, False)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(ob.data)
    bm.edges.ensure_lookup_table()
    for e in list(bm.edges)[:3]:                 # three edges of the quad: switching to all modes would add the face
        e.select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)

    def selection():
        b = bmesh.from_edit_mesh(ob.data)
        return tuple(tuple(i for i, e in enumerate(seq) if e.select) for seq in (b.verts, b.edges, b.faces))

    before = selection()
    assert before[2] == ()
    hold.COMPONENT.start(bpy.context)
    assert selection() == before, "starting the pivot edit grew the selection"
    hold.COMPONENT.finish(bpy.context)
    assert tuple(ts.mesh_select_mode) == (False, True, False)
    assert selection() == before, "ending the pivot edit left a grown selection"
    _object_mode()


def test_smart_extrude_hole_has_quad_walls():
    _clear()
    smart.clear()
    bpy.context.scene.unit_settings.system = 'NONE'
    bpy.context.tool_settings.transform_pivot_point = 'MEDIAN_POINT'
    for slot in bpy.context.scene.transform_orientation_slots:
        slot.type = 'GLOBAL'
    bpy.ops.mesh.primitive_cube_add(size=2)
    ob = bpy.context.object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='FACE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(ob.data)
    top = max(bm.faces, key=lambda f: f.calc_center_median().z)
    bmesh.ops.inset_region(bm, faces=[top], thickness=.5, depth=0, use_even_offset=True)
    inner = min((f for f in bm.faces if f.calc_center_median().z > .99), key=lambda f: f.calc_center_median().xy.length)
    inner.select_set(True)
    bm.faces.active = inner
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.smart_extrude(translation=(0, 0, -2.5), orientation='WORLD') == {'FINISHED'}
    bm = bmesh.from_edit_mesh(ob.data)
    # Maya: a hole through the cube = 16 vertices, 32 edges, 16 quads (no point left on a straight edge)
    assert (len(bm.verts), len(bm.edges), len(bm.faces)) == (16, 32, 16), (len(bm.verts), len(bm.edges), len(bm.faces))
    assert all(len(f.verts) == 4 for f in bm.faces)
    assert abs(bm.calc_volume() - 6.0) < 1e-5
    _object_mode()


def test_seam_points_keep_input_corners():
    """A point the input mesh had on a straight edge stays (only solver points go)."""
    topology = import_module(kit.MODULE + '.operators.smart_topology')
    bm = bmesh.new()
    a, m, b, c, d = (bm.verts.new(p) for p in ((0, 0, 0), (1, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)))
    bm.faces.new((a, m, b, c, d))
    bm.faces.new((m, a, bm.verts.new((0, -1, 0)), bm.verts.new((2, -1, 0)), b))
    assert topology.dissolve_seam_points(bm, {topology._key(m.co)}) == 0
    assert topology.dissolve_seam_points(bm, set()) == 1
    assert len(bm.verts) == 6
    bm.free()


def test_deleted_live_object_is_released():
    _clear()
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.object
    ob.name = "LiveGone"
    mesh_name = ob.data.name
    live.set_objects(bpy.context.scene, [ob])
    assert live.objects(bpy.context.scene) == [ob] and len(bpy.context.scene.allset_live_history) == 1
    with bpy.context.temp_override(selected_objects=[ob], active_object=None):
        assert bpy.ops.object.delete(use_global=False) == {'FINISHED'}
    live.sync()
    scene = bpy.context.scene
    assert len(scene.allset_live_objects) == 0 and len(scene.allset_live_history) == 0
    assert bpy.data.objects["LiveGone"].users == 0, "the live list still holds the deleted object"
    bpy.data.orphans_purge(do_recursive=True)
    assert "LiveGone" not in bpy.data.objects and mesh_name not in bpy.data.meshes


def test_status_line_magnet_turns_make_live_off():
    _clear()
    bpy.ops.mesh.primitive_cube_add()
    a = bpy.context.object
    bpy.ops.mesh.primitive_cube_add(location=(3, 0, 0))
    b = bpy.context.object
    live.set_objects(bpy.context.scene, [a])
    b.select_set(True)
    bpy.context.view_layer.objects.active = b
    assert bpy.ops.allset.make_live(toggle=True) == {'FINISHED'}
    assert live.objects(bpy.context.scene) == [], "Maya's magnet turns Make Live off whatever is selected"
    assert bpy.ops.allset.make_live(toggle=True) == {'FINISHED'}
    assert live.objects(bpy.context.scene) == [b]


def test_new_drags_open_no_adjust_last_operation():
    """Maya has no redo panel: the kit's new drags register (handle memory, undo) without a visible property."""
    for name in ("ALLSET_OT_pivot_translate", "ALLSET_OT_pivot_rotate", "ALLSET_OT_component_scale",
                 "ALLSET_OT_live_translate", "ALLSET_OT_live_list"):
        mod, op = name[:-len(name.split("_OT_")[1]) - 4].lower(), name.split("_OT_")[1]
        rna = getattr(getattr(bpy.ops, mod), op).get_rna_type()
        visible = [p.identifier for p in rna.properties if p.identifier != "rna_type" and not p.is_hidden]
        assert not visible, (name, visible)


def test_tool_key_ends_a_latched_pivot_edit():
    """Maya: picking a transform tool ends pivot editing that a D tap / Insert left on."""
    _clear()
    hold.unregister_cleanup()
    pivot.stop()
    bpy.ops.mesh.primitive_cube_add()
    ts = bpy.context.tool_settings
    ts.use_transform_data_origin = False
    hold.toggle_object_pivot(ts)
    assert ts.use_transform_data_origin
    hold.end_pivot_edit(bpy.context)
    assert not ts.use_transform_data_origin
    bpy.ops.object.mode_set(mode='EDIT')
    hold.COMPONENT.start(bpy.context, toggled=True)
    assert hold.COMPONENT.on
    hold.end_pivot_edit(bpy.context)
    assert not hold.COMPONENT.on
    _object_mode()
