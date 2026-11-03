"""Edit Mesh > Bevel that leaves soft edges gives the object Maya's smooth normals: a display-only "Maya Normals"
Weighted Normal modifier (each face weighted by its area times its corner angle), kept by Delete History and not
listed in the Channel Box INPUTS. A bevel with only hard edges adds nothing."""

from importlib import import_module

import bmesh
import bpy

import kit

cb = import_module(kit.MODULE + ".ui.channel_box")
display = import_module(kit.MODULE + ".operators.display")
extrude = import_module(kit.MODULE + ".operators.extrude")


def _fresh():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    extrude.clear()


def _bevel_cube(**props):
    assert bpy.ops.allset.create(kind='CUBE') == {'FINISHED'}
    ob = bpy.context.view_layer.objects.active
    if bpy.context.mode != 'EDIT_MESH':
        bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bm = bmesh.from_edit_mesh(ob.data)
    for e in bm.edges:
        e.select = False
    bm.edges.ensure_lookup_table()
    bm.edges[0].select = True
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.bevel(**props) == {'FINISHED'}
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob


def test_soft_bevel_gets_maya_normals():
    _fresh()
    ob = _bevel_cube(segments=4)
    md = ob.modifiers.get(display.NORMALS_MOD_NAME)
    assert md is not None and md.type == 'WEIGHTED_NORMAL'
    assert md.mode == 'FACE_AREA_WITH_ANGLE' and md.weight == 50 and md.keep_sharp
    assert md not in cb._inputs(ob)
    # the corner normals between the round strip's faces are smooth (not one face's normal)
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).to_mesh()
    tilted = [n.vector for n in me.corner_normals if 0.2 < abs(n.vector.normalized().z) < 0.98
              and 0.2 < max(abs(n.vector.x), abs(n.vector.y))]
    ob.evaluated_get(dg).to_mesh_clear()
    assert tilted


def test_hard_bevel_adds_nothing():
    _fresh()
    ob = _bevel_cube(segments=1)
    assert ob.modifiers.get(display.NORMALS_MOD_NAME) is None


def test_delete_history_keeps_maya_normals():
    _fresh()
    ob = _bevel_cube(segments=4)
    for o in bpy.context.view_layer.objects:
        o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob
    assert bpy.ops.allset.delete_history() == {'FINISHED'}
    assert ob.modifiers.get(display.NORMALS_MOD_NAME) is not None
