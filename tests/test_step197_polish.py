"""#104: small Maya polish batch — result field after Undo, overlays under the hotbox, character-set and
NURBS display menus wired up, Mesh > Cleanup... a leaf."""

from importlib import import_module

import bpy

import kit

command_line = import_module(kit.MODULE + ".command_line")
undo_text = import_module(kit.MODULE + ".command_line.undo_text")
mdraw = import_module(kit.MODULE + ".marking.draw")
view_message = import_module(kit.MODULE + ".ui.view_message")


def _field():
    return command_line._result["text"]


def _start():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.ed.undo_push(message="test start")
    for ob in bpy.context.scene.objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = bpy.context.scene.objects[0]


def test_a_new_command_replaces_undo_text():
    """G4: "Undo: Group" stayed through P / Delete / Ctrl+E; Maya replaces it."""
    _start()
    assert bpy.ops.allset.group('EXEC_DEFAULT', True) == {'FINISHED'}
    bpy.ops.ed.undo()
    assert _field() == "Undo: Group", _field()
    bpy.ops.object.location_clear('EXEC_DEFAULT', True)    # a registered command without a result
    undo_text._on_depsgraph()                               # = the depsgraph update after it
    assert _field() == "", _field()
    # undo still names it
    bpy.ops.ed.undo()
    assert _field() == "Undo: Clear Location", _field()
    # a command with a result writes its result over the undo text
    assert bpy.ops.allset.group('EXEC_DEFAULT', True) == {'FINISHED'}
    assert _field().startswith("Result: group"), _field()


def test_redo_text_is_replaced_too():
    _start()
    bpy.ops.object.location_clear('EXEC_DEFAULT', True)
    bpy.ops.ed.undo()
    bpy.ops.ed.redo()
    assert _field() == "Redo: Clear Location", _field()
    bpy.ops.object.scale_clear('EXEC_DEFAULT', True)
    undo_text._on_depsgraph()
    assert _field() == "", _field()


def test_a_result_text_is_kept_by_later_scans():
    _start()
    command_line.show_result("Result: group1")
    bpy.ops.object.location_clear('EXEC_DEFAULT', True)
    undo_text._on_depsgraph()
    assert _field() == "Result: group1", _field()    # only stale Undo / Redo text is cleared


def test_f8_names_its_step_and_clears_undo_text():
    _start()
    cube = next(ob for ob in bpy.context.scene.objects if ob.type == 'MESH')
    bpy.context.view_layer.objects.active = cube
    bpy.ops.object.location_clear('EXEC_DEFAULT', True)
    bpy.ops.ed.undo()
    assert _field().startswith("Undo: "), _field()
    with bpy.context.temp_override(active_object=cube, object=cube):
        assert bpy.ops.allset.toggle_sel_mode('EXEC_DEFAULT', True) == {'FINISHED'}
    assert _field() == "", _field()
    bpy.ops.object.mode_set(mode='OBJECT')


def test_menu_up_follows_active():
    mdraw.ACTIVE.clear()
    assert not mdraw.menu_up()
    mdraw.ACTIVE.update(hotbox=True)
    try:
        assert mdraw.menu_up()
    finally:
        mdraw.ACTIVE.clear()


# --- (4) Mesh > Cleanup... = a Maya leaf with Cleanup Options -------------------------------------------------

menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")
option_windows = import_module(kit.MODULE + ".operators.option_windows")


def _cube():
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.mesh.primitive_cube_add()
    return bpy.context.object


def test_cleanup_is_a_leaf_with_maya_window():
    assert menu_map.MAP["Mesh/Cleanup..."] == "allset.poly_cleanup"
    w = option_windows._BY_KEY["poly_cleanup"]
    assert w.title == "Cleanup Options" and w.action == "Cleanup"
    assert "Mesh/Cleanup..." in w.paths
    d = w.defaults()      # Maya Cleanup Options factory values
    assert d["operation"] == "Cleanup matching polygons" and d["scope"] == "Apply to selected objects"
    assert not any(d[k] for k in ("quads", "nsided", "concave", "holes", "nonplanar", "lamina", "nonmanifold",
                                   "zero_edge", "zero_face", "zero_map"))
    assert d["edge_tol"] == d["face_tol"] == d["map_tol"] == 0.00001


def test_cleanup_factory_values_change_nothing():
    ob = _cube()
    n = len(ob.data.polygons)
    assert bpy.ops.allset.poly_cleanup('EXEC_DEFAULT') == {'FINISHED'}
    assert len(ob.data.polygons) == n


def test_cleanup_triangulates_quads_and_selects():
    ob = _cube()
    assert bpy.ops.allset.poly_cleanup('EXEC_DEFAULT', operation='SELECT', quads=True) == {'FINISHED'}
    assert bpy.context.mode == 'EDIT_MESH'
    bpy.ops.object.mode_set(mode='OBJECT')
    assert sum(p.select for p in ob.data.polygons) == 6
    assert len(ob.data.polygons) == 6                      # select only: geometry untouched
    assert bpy.ops.allset.poly_cleanup('EXEC_DEFAULT', quads=True) == {'FINISHED'}
    assert len(ob.data.polygons) == 12 and all(len(p.vertices) == 3 for p in ob.data.polygons)
    assert command_line._result["text"].startswith(f"Result: {ob.name}.f[0:5]"), command_line._result["text"]


def test_cleanup_removes_lamina_and_zero_length_edges():
    bpy.ops.object.select_all(action='DESELECT')
    me = bpy.data.meshes.new("lamina")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (2, 0, 0), (2, 1, 0)], [],
                   [(0, 1, 2, 3), (1, 4, 5, 2), (3, 2, 1, 0), (0, 1, 2, 3), (2, 5, 4, 1), (1, 4, 5, 2), (0, 3, 2, 1)])
    ob = bpy.data.objects.new("lamina", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    n = len(ob.data.polygons)
    assert n > 2, n                                        # Blender may already merge identical corner lists
    assert bpy.ops.allset.poly_cleanup('EXEC_DEFAULT', lamina=True) == {'FINISHED'}
    assert len(ob.data.polygons) == 2, len(ob.data.polygons)   # one face per vertex set
    ob2 = _cube()
    ob2.data.vertices[0].co = ob2.data.vertices[1].co.copy()     # a zero-length edge (if 0-1 is an edge)
    edge01 = any(set(e.vertices) == {0, 1} for e in ob2.data.edges)
    nv = len(ob2.data.vertices)
    assert bpy.ops.allset.poly_cleanup('EXEC_DEFAULT', zero_edge=True) == {'FINISHED'}
    if edge01:
        assert len(ob2.data.vertices) == nv - 1


def test_cleanup_concave_finds_reflex_faces_only():
    import bmesh
    me = bpy.data.meshes.new("concave")
    bm = bmesh.new()
    vs = [bm.verts.new(c) for c in ((0, 0, 0), (2, 0, 0), (2, 2, 0), (1, 0.5, 0), (0, 2, 0))]   # arrow: reflex at 3
    bm.faces.new(vs)
    sq = [bm.verts.new(c) for c in ((3, 0, 0), (4, 0, 0), (4, 1, 0), (3, 1, 0))]
    bm.faces.new(sq)
    pc = import_module(kit.MODULE + ".operators.poly_cleanup")
    o = {k: False for k in ("quads", "nsided", "concave", "holes", "nonplanar", "lamina", "nonmanifold",
                             "zero_edge", "zero_face", "zero_map")}
    o.update(concave=True, edge_tol=1e-5, face_tol=1e-5, map_tol=1e-5, nonmanifold_type='NORMALS')
    bm.normal_update()
    tri = pc.find(bm, o)[0]
    assert [len(f.verts) for f in tri] == [5], tri
    bm.free()
    bpy.data.meshes.remove(me)


# --- (5) character sets wired up ------------------------------------------------------------------------------

editor_menu_map = import_module(kit.MODULE + ".ui.editor_menu_map")


def test_no_stale_character_set_notices():
    texts = [v[1] for v in notices.NOTICES.values()] + [v[1] for v in notices.CATEGORIES.values()]
    assert not [t for t in texts if "no character sets" in t], "stale notice"
    assert "Windows/Relationship Editors/Character Sets" not in notices.NOTICES
    assert menu_map.MAP["Windows/Relationship Editors/Character Sets"][1] == "allset.character_editor"
    assert "Graph Editor/Show/Objects/Characters" not in notices.NOTICES
    assert "Dope Sheet/Show/Objects/Characters" not in notices.NOTICES   # members in the Dope Sheet


def test_graph_outliner_lists_character_nodes():
    editor_chrome = import_module(kit.MODULE + ".ui.editor_chrome")
    ob = _cube()
    ob.keyframe_insert("location", index=0, frame=1)
    ob.keyframe_insert("location", index=1, frame=1)
    scene = bpy.context.scene
    ks = scene.keying_sets.new(idname="character1", name="character1")
    ks.paths.add(ob, "location", index=0)
    curves = editor_chrome.character_curves(scene, ks)
    assert [(c.data_path, c.array_index) for c in curves] == [("location", 0)]
    assert editor_chrome.node_key(ks) == ("CHARACTER", "character1")
    assert editor_chrome.node_name(ks) == "character1"

    class Space:
        class dopesheet:
            show_only_selected = False
            show_hidden = True
            filter_text = ""
    wm = bpy.context.window_manager
    wm.allset_show_characters = False
    assert not [n for n in editor_chrome.listed_nodes(bpy.context, Space) if n[0] == "CHARACTER"]
    wm.allset_show_characters = True
    try:
        nodes = editor_chrome.listed_nodes(bpy.context, Space)
        assert nodes[0][0] == "CHARACTER" and nodes[0][1] == ks
    finally:
        wm.allset_show_characters = False


def test_character_editor_operator_runs():
    assert hasattr(bpy.types, "ALLSET_PT_character_editor")
    compat = import_module(kit.MODULE + ".compat")
    assert compat.has_op(bpy.ops.allset, "character_editor")


# --- (3) AE rows wrap instead of cutting text -----------------------------------------------------------------

def test_ae_rows_wrap_to_region_width():
    ae = import_module(kit.MODULE + ".ui.attribute_editor")

    class Ctx:
        class region:
            width = 280
        preferences = bpy.context.preferences
        area = None
        space_data = None
    labels = ["pCube1", "pCubeShape1", "initialShadingGroup", "lambert1"]
    rows = ae.wrap_rows(Ctx, labels)
    assert len(rows) >= 2 and sorted(i for r in rows for i in r) == [0, 1, 2, 3]
    Ctx.region.width = 2000
    assert ae.wrap_rows(Ctx, labels) == [[0, 1, 2, 3]]

    class NoRegion:
        region = None
    assert ae.wrap_rows(NoRegion, labels) == [[0, 1, 2, 3]]
