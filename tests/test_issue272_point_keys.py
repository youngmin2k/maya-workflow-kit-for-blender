"""Issue #272: S with components selected keys their positions, like Maya — mesh vertices (edges / faces: the
vertices they use), NURBS curve / surface CVs, Bezier points and lattice points get X / Y / Z keys on the object
data. In object mode S keeps keying the object's channels. One undo removes the keys, and keyed vertices of a mesh
in edit mode follow their keys when the time changes."""

from importlib import import_module

import bmesh
import bpy

import kit

compat = import_module(kit.MODULE + ".compat")
point_keys = import_module(kit.MODULE + ".operators.point_keys")


def _fresh():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.curves, bpy.data.lattices, bpy.data.actions):
        for d in list(coll):
            if d.users == 0:
                coll.remove(d)
    bpy.context.scene.frame_set(1)


def _only(ob):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


def _set_key():
    return bpy.ops.allset.set_key('EXEC_DEFAULT', True)     # True: an undo step like the S key


def _curves(idd):
    return sorted((fc.data_path, fc.array_index) for fc in compat.id_fcurves(idd))


def _cube_in_edit(select=(2, 5)):
    _fresh()
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    _only(ob)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.tool_settings.mesh_select_mode = (True, False, False)
    bm = bmesh.from_edit_mesh(ob.data)
    for v in bm.verts:
        v.select = v.index in select
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    return ob


def test_vertices_are_keyed_on_x_y_z():
    ob = _cube_in_edit((2, 5))
    assert _set_key() == {'FINISHED'}
    want = sorted((f"vertices[{i}].co", a) for i in (2, 5) for a in range(3))
    assert _curves(ob.data) == want, _curves(ob.data)
    assert ob.animation_data is None or not _curves(ob), _curves(ob)        # no object channels in component mode
    assert bpy.context.mode == 'EDIT_MESH'


def test_edit_mode_moves_are_keyed_and_follow_time():
    ob = _cube_in_edit((2,))
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    z0 = bm.verts[2].co.z
    assert _set_key() == {'FINISHED'}
    bpy.context.scene.frame_set(10)
    bm.verts[2].co.z = z0 + 3.0                         # moved in the edit copy only
    bmesh.update_edit_mesh(ob.data)
    assert _set_key() == {'FINISHED'}
    fc = next(f for f in compat.id_fcurves(ob.data) if f.data_path == "vertices[2].co" and f.array_index == 2)
    assert [round(k.co.y, 4) for k in fc.keyframe_points] == [round(z0, 4), round(z0 + 3.0, 4)]
    bpy.context.scene.frame_set(1)                      # still in edit mode: the vertex goes back with the time
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    assert abs(bm.verts[2].co.z - z0) < 1e-5, bm.verts[2].co
    bpy.context.scene.frame_set(10)
    assert abs(bm.verts[2].co.z - (z0 + 3.0)) < 1e-5, bm.verts[2].co
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.scene.frame_set(1)
    assert abs(ob.data.vertices[2].co.z - z0) < 1e-5     # and the mesh plays it in object mode
    bpy.context.scene.frame_set(10)
    assert abs(ob.data.vertices[2].co.z - (z0 + 3.0)) < 1e-5


def test_edges_and_faces_key_their_vertices():
    ob = _cube_in_edit(())
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    face = bm.faces[0]
    face.select_set(True)
    verts = sorted(v.index for v in face.verts)
    bmesh.update_edit_mesh(ob.data)
    assert _set_key() == {'FINISHED'}
    assert sorted({p for p, _a in _curves(ob.data)}) == sorted(f"vertices[{i}].co" for i in verts)


def test_nothing_selected_keys_nothing():
    ob = _cube_in_edit(())
    assert _set_key() == {'CANCELLED'}
    assert ob.data.animation_data is None or not _curves(ob.data)


def test_object_mode_s_still_keys_the_object():
    _fresh()
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    _only(ob)
    assert _set_key() == {'FINISHED'}
    paths = {p for p, _a in _curves(ob)}
    assert {"location", "rotation_euler", "scale"} <= paths, paths
    assert not any(p.startswith("vertices[") for p in paths)


def test_nurbs_curve_cvs():
    _fresh()
    bpy.ops.curve.primitive_nurbs_curve_add()
    ob = bpy.context.active_object
    _only(ob)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.curve.select_all(action='DESELECT')
    ob.data.splines[0].points[1].select = True
    assert _set_key() == {'FINISHED'}
    assert _curves(ob.data) == [("splines[0].points[1].co", a) for a in range(3)]   # X / Y / Z, not the weight
    pt = ob.data.splines[0].points[1]
    z0 = pt.co.z
    bpy.context.scene.frame_set(10)
    pt.co.z = z0 + 2.0
    assert _set_key() == {'FINISHED'}
    bpy.context.scene.frame_set(1)
    assert abs(ob.data.splines[0].points[1].co.z - z0) < 1e-5


def test_bezier_points_key_the_point_and_handles():
    _fresh()
    bpy.ops.curve.primitive_bezier_curve_add()
    ob = bpy.context.active_object
    _only(ob)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.curve.select_all(action='DESELECT')
    bp = ob.data.splines[0].bezier_points[0]
    bp.select_control_point = True
    ob.data.splines[0].bezier_points[1].select_right_handle = True
    assert _set_key() == {'FINISHED'}
    paths = {p for p, _a in _curves(ob.data)}
    want = {"splines[0].bezier_points[0].co", "splines[0].bezier_points[0].handle_left",
            "splines[0].bezier_points[0].handle_right", "splines[0].bezier_points[1].handle_right"}
    assert paths == want, paths


def test_surface_cvs():
    _fresh()
    bpy.ops.surface.primitive_nurbs_surface_surface_add()
    ob = bpy.context.active_object
    _only(ob)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.curve.select_all(action='DESELECT')
    ob.data.splines[0].points[5].select = True
    assert bpy.context.mode == 'EDIT_SURFACE'
    assert _set_key() == {'FINISHED'}
    assert _curves(ob.data) == [("splines[0].points[5].co", a) for a in range(3)]


def test_lattice_points():
    _fresh()
    bpy.ops.object.add(type='LATTICE')
    ob = bpy.context.active_object
    _only(ob)
    bpy.ops.object.mode_set(mode='EDIT')
    for i, p in enumerate(ob.data.points):
        p.select = i == 3
    assert _set_key() == {'FINISHED'}
    assert _curves(ob.data) == [("points[3].co_deform", a) for a in range(3)]


def test_one_undo_removes_the_keys():
    ob = _cube_in_edit((1,))
    name = ob.data.name
    bpy.ops.ed.undo_push(message="start")
    assert _set_key() == {'FINISHED'}
    assert _curves(bpy.data.meshes[name])
    bpy.ops.ed.undo()
    me = bpy.data.meshes[name]
    assert me.animation_data is None or not _curves(me), _curves(me)
    assert bpy.context.mode == 'EDIT_MESH'


def test_s_is_bound_in_component_modes():
    kms = kit.maya_kc().keymaps
    for km in ("Mesh", "Curve", "Lattice"):
        items = [it for it in kms[km].keymap_items
                 if it.idname == "allset.set_key" and it.type == 'S' and it.value == 'PRESS'
                 and not (it.shift or it.ctrl or it.alt) and it.active]
        assert items, km


def test_frame_handler_is_removed_on_disable():
    assert point_keys._on_frame in bpy.app.handlers.frame_change_post
    kit.disable()
    assert not any(getattr(h, "__module__", "").endswith("point_keys") for h in bpy.app.handlers.frame_change_post)
    kit.enable()


def test_time_slider_ticks_show_selected_point_keys():
    """Component mode: the Time Slider ticks include the keys of the selected points (and only those)."""
    time_slider = import_module(kit.MODULE + ".ui.time_slider")
    ob = _cube_in_edit((2,))
    assert _set_key() == {'FINISHED'}
    bpy.context.scene.frame_set(7)
    _cube_select(ob, (5,))
    assert _set_key() == {'FINISHED'}
    bpy.context.scene.frame_set(1)
    assert ob in time_slider.tick_nodes(bpy.context)          # what the Time Slider draws ticks for
    assert [f for f, _b in time_slider.key_frames([ob])] == [7.0]
    _cube_select(ob, (2, 5))
    assert [f for f, _b in time_slider.key_frames([ob])] == [1.0, 7.0]
    _cube_select(ob, (0,))
    assert time_slider.key_frames([ob]) == []


def _cube_select(ob, select):
    bm = bmesh.from_edit_mesh(ob.data)
    for v in bm.verts:
        v.select = v.index in select
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)


# --- Auto Key in component mode, Shift+W / E / R, Channel Box CVs colours ------------------------------------------

def _auto_key_flush():
    auto_key = import_module(kit.MODULE + ".operators.auto_key")
    bpy.context.view_layer.update()              # depsgraph_update_post notes the edited object
    if bpy.app.timers.is_registered(auto_key._flush):
        bpy.app.timers.unregister(auto_key._flush)
    auto_key._flush()


def _vert_keys(me, i, axis):
    fc = _find(me, f"vertices[{i}].co", axis)
    return None if fc is None else [round(k.co.x) for k in fc.keyframe_points]


def _find(idd, path, index):
    return next((f for f in compat.id_fcurves(idd) if f.data_path == path and f.array_index == index), None)


def _move_selected(ob, dz):
    bm = bmesh.from_edit_mesh(ob.data)
    for v in bm.verts:
        if v.select:
            v.co.z += dz
    bmesh.update_edit_mesh(ob.data)


def test_auto_key_keys_only_keyed_points_on_changed_axes():
    """Maya Auto Key in component mode: moving points keys only the points that already have keys, and only the
    axes whose value changed."""
    scene = bpy.context.scene
    ob = _cube_in_edit((2,))
    assert _set_key() == {'FINISHED'}                 # vertex 2 keyed at frame 1
    scene.frame_set(10)
    _cube_select(ob, (2, 5))
    scene.allset_auto_key = True
    try:
        _move_selected(ob, 1.0)
        _auto_key_flush()
    finally:
        scene.allset_auto_key = False
    me = ob.data
    assert _vert_keys(me, 2, 2) == [1, 10], _vert_keys(me, 2, 2)
    assert _vert_keys(me, 2, 0) == [1] and _vert_keys(me, 2, 1) == [1]
    assert _vert_keys(me, 5, 2) is None                # an unkeyed point stays unkeyed
    scene.frame_set(1)                                 # the move is kept at 10, frame 1 plays the old position
    bm = bmesh.from_edit_mesh(me)
    bm.verts.ensure_lookup_table()
    z1 = bm.verts[2].co.z
    scene.frame_set(10)
    assert abs(bm.verts[2].co.z - (z1 + 1.0)) < 1e-5


def test_auto_key_off_keys_no_points():
    scene = bpy.context.scene
    ob = _cube_in_edit((2,))
    assert _set_key() == {'FINISHED'}
    scene.frame_set(10)
    scene.allset_auto_key = False
    _move_selected(ob, 1.0)
    _auto_key_flush()
    assert _vert_keys(ob.data, 2, 2) == [1]


def test_auto_key_on_lattice_points():
    scene = bpy.context.scene
    _fresh()
    bpy.ops.object.add(type='LATTICE')
    ob = bpy.context.active_object
    _only(ob)
    bpy.ops.object.mode_set(mode='EDIT')
    for i, p in enumerate(ob.data.points):
        p.select = i == 0
    assert _set_key() == {'FINISHED'}
    scene.frame_set(5)
    scene.allset_auto_key = True
    try:
        ob.data.points[0].co_deform.x += 0.25
        ob.data.update_tag()
        _auto_key_flush()
    finally:
        scene.allset_auto_key = False
    fc = _find(ob.data, "points[0].co_deform", 0)
    assert [round(k.co.x) for k in fc.keyframe_points] == [1, 5]
    fc = _find(ob.data, "points[0].co_deform", 1)
    assert [round(k.co.x) for k in fc.keyframe_points] == [1]


def test_shift_w_e_r_key_nothing_in_component_mode():
    """Maya: points have no translate / rotate / scale, so Shift+W / E / R set no key in component mode (silently)."""
    ob = _cube_in_edit((2,))
    for ch in ("TRANSLATE", "ROTATE", "SCALE"):
        assert bpy.ops.allset.set_key('EXEC_DEFAULT', True, channels=ch) == {'CANCELLED'}
    assert ob.animation_data is None or not _curves(ob), _curves(ob)
    assert ob.data.animation_data is None or not _curves(ob.data), _curves(ob.data)


def test_cvs_table_states_follow_point_keys():
    """The Channel Box CVs table draws keyed points in the key colour: a key at this frame, or only a curve."""
    ob = _cube_in_edit((2,))
    assert _set_key() == {'FINISHED'}
    paths = [("vertices[2].co", 0), ("vertices[2].co", 2), ("vertices[5].co", 0)]
    states = point_keys.point_states(ob, paths, 1)
    assert states == {("vertices[2].co", 0): 'KEYED', ("vertices[2].co", 2): 'KEYED'}, states
    states = point_keys.point_states(ob, paths, 4)
    assert states[("vertices[2].co", 0)] == 'ANIMATED'
    channel_box = import_module(kit.MODULE + ".ui.channel_box")
    assert channel_box.state_alert('KEYED') and channel_box.state_alert('ANIMATED')
