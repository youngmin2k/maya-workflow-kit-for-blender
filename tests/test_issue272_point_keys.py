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
