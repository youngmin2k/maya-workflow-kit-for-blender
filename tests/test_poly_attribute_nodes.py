"""Editable Bridge/Subdivide preserve their pre-operation input and boundary data."""
from importlib import import_module

import bmesh
import bpy
import kit

poly = import_module(kit.MODULE+'.operators.poly_attribute_nodes')
ex = import_module(kit.MODULE+'.operators.extrude')


def fingerprint(bm):
    return sorted(tuple(round(c, 5) for c in vertex.co) for vertex in bm.verts), sorted(len(f.verts) for f in bm.faces)


def rings():
    bm = bmesh.new()
    for z in (0, 2):
        verts = [bm.verts.new((x, y, z)) for x, y in ((-1,-1), (1,-1), (1,1), (-1,1))]
        # Adjacent quads make the selected ring a boundary rather than a loose wire.
        outside = [bm.verts.new((x*2, y*2, z)) for x, y in ((-1,-1), (1,-1), (1,1), (-1,1))]
        for i in range(4):
            bm.faces.new((verts[i], verts[(i+1)%4], outside[(i+1)%4], outside[i]))
        for i in range(4):
            bm.edges.get((verts[i], verts[(i+1)%4])).select_set(True)
    return bm


def test_bridge_divisions_build_quad_strips():
    for cuts in (0, 1, 3):
        bm = rings()
        before = len(bm.faces)
        tracked = poly.bridge(bm, {'divisions':cuts, 'twist':0}, 1)
        assert tracked and len(bm.faces)-before == 4*(cuts+1)
        assert all(len(face.verts) == 4 for face in bm.faces)
        bm.free()


def test_subdivide_matches_native_bmesh_baseline():
    for cuts in (1, 2, 3):
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=2, y_segments=2, size=1)
        for edge in bm.edges:
            edge.select_set(True)
        other = bm.copy()
        poly.subdivide(bm, {'divisions':cuts, 'smoothness':0}, 1)
        bmesh.ops.subdivide_edges(other, edges=list(other.edges), cuts=cuts, smooth=0, use_grid_fill=True)
        assert fingerprint(bm) == fingerprint(other)
        bm.free()
        other.free()


def test_bridge_faces_removes_caps_and_keeps_side_quads():
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2)
    from mathutils import Matrix
    bmesh.ops.create_cube(bm, size=2, matrix=Matrix.Translation((0, 0, 4)))
    bm.normal_update()
    for face in bm.faces:
        face.select_set(abs(face.normal.z) > .9 and 0 < face.calc_center_median().z < 4)
    tracked = poly.bridge(bm, {'divisions': 0, 'twist': 0, 'use_faces': True}, 1)
    assert tracked and len(bm.faces) == 14
    assert all(len(face.verts) == 4 for face in bm.faces)
    bm.free()


def test_editable_node_rebuilds_from_original_input():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    mesh = bpy.data.meshes.new('attribute_bridge')
    bm = rings()
    bm.to_mesh(mesh)
    bm.free()
    ob = bpy.data.objects.new('attribute_bridge', mesh)
    bpy.context.scene.collection.objects.link(ob)
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.scene.tool_settings.mesh_select_mode = (False, True, False)
    assert bpy.ops.allset.bridge(divisions=0) == {'FINISHED'}
    record = ex.active(bpy.context)[1]
    assert record.spec is poly.BRIDGE
    assert ex.set_params(bpy.context, divisions=2) == {'FINISHED'}
    assert len(bmesh.from_edit_mesh(mesh).faces) == 20
    assert ex.set_params(bpy.context, divisions=0) == {'FINISHED'}
    assert len(bmesh.from_edit_mesh(mesh).faces) == 12


def test_failed_node_restores_mesh_and_keeps_previous_history():
    ob, previous = ex.active(bpy.context)
    bm = bmesh.from_edit_mesh(ob.data)
    before = fingerprint(bm)
    def fail(mesh, params, unit):
        mesh.verts.new((999, 0, 0))
        raise ValueError('injected build failure')
    spec = ex.Spec('FAILURE_PROBE', 'failure', (), {}, {}, {}, None, 'none', fail)
    try:
        ex.record_new(bpy.context, ob, bm, spec, {}, 1)
    except ValueError:
        pass
    else:
        raise AssertionError('the injected error must propagate')
    assert fingerprint(bm) == before
    assert ex.RECORDS[ob.name] is previous and previous.pre is not None
