"""Delete / Backspace on components deletes right away, the Maya way.

Faces -> faces (and their unused edges/vertices) gone; edges -> non-border edges dissolved
with their 2-edge vertices cleaned up; vertices -> dissolved.
"""

from importlib import import_module

import bmesh
import bpy

import kit

component = import_module(kit.MODULE + ".operators.component")


def _cube(mode):
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.mesh.primitive_cube_add()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type=mode)
    bpy.ops.mesh.select_all(action='DESELECT')
    return bpy.context.active_object


def _counts(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    return len(bm.verts), len(bm.edges), len(bm.faces)


def _select(ob, kind, indices):
    bm = bmesh.from_edit_mesh(ob.data)
    seq = {"VERT": bm.verts, "EDGE": bm.edges, "FACE": bm.faces}[kind]
    seq.ensure_lookup_table()
    for i in indices:
        seq[i].select = True
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)


def test_keymap_binds_delete_and_backspace():
    km = kit.maya_kc().keymaps["Mesh"]
    for key in ('DEL', 'BACK_SPACE'):
        plain = [k.idname for k in km.keymap_items if k.active and k.type == key and k.value == 'PRESS'
                 and not (k.ctrl or k.shift or k.alt or k.oskey)]
        assert plain == ["allset.delete_components"], (key, plain)
        ctrl = [k.idname for k in km.keymap_items if k.active and k.type == key and k.ctrl]
        assert ctrl == ["mesh.dissolve_mode"], (key, ctrl)
    obj = kit.maya_kc().keymaps["Object Mode"]
    assert any(k.type == 'DEL' and k.idname.startswith("object.delete") for k in obj.keymap_items), \
        "object mode Delete unchanged"


def test_delete_all_faces():
    ob = _cube('FACE')
    bpy.ops.mesh.select_all(action='SELECT')
    assert bpy.ops.allset.delete_components() == {'FINISHED'}
    assert _counts(ob) == (0, 0, 0), _counts(ob)


def test_delete_one_face_keeps_the_rest():
    ob = _cube('FACE')
    _select(ob, "FACE", [0])
    bpy.ops.allset.delete_components()
    assert _counts(ob) == (8, 12, 5), _counts(ob)
    bm = bmesh.from_edit_mesh(ob.data)
    assert not any(el.select for el in bm.verts), "nothing selected afterwards"


def test_delete_edge_dissolves_and_cleans_vertices():
    ob = _cube('EDGE')
    _select(ob, "EDGE", [0])
    bpy.ops.allset.delete_components()
    # two quads merge into one face; the edge's end vertices keep 2 edges each -> cleaned up
    assert _counts(ob) == (6, 9, 5), _counts(ob)


def test_border_edge_is_kept():
    ob = _cube('FACE')
    _select(ob, "FACE", [0])
    bpy.ops.allset.delete_components()        # open box: border edges now
    bpy.ops.mesh.select_mode(type='EDGE')
    bm = bmesh.from_edit_mesh(ob.data)
    border = next(e for e in bm.edges if len(e.link_faces) == 1)
    border.select = True
    bmesh.update_edit_mesh(ob.data)
    before = _counts(ob)
    assert bpy.ops.allset.delete_components() == {'CANCELLED'}
    assert _counts(ob) == before


def test_delete_vertex_dissolves():
    ob = _cube('VERT')
    _select(ob, "VERT", [0])
    bpy.ops.allset.delete_components()
    # corner vertex and its 3 edges go; the 3 faces around it merge into one
    assert _counts(ob) == (7, 9, 4), _counts(ob)


def test_nothing_selected_cancels():
    ob = _cube('FACE')
    assert bpy.ops.allset.delete_components() == {'CANCELLED'}
    assert _counts(ob) == (8, 12, 6)
    bpy.ops.object.mode_set(mode='OBJECT')
