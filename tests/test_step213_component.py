"""Maya's Component Editor — Smooth Skins weights table with
Hold / Hide Zero Columns / Interactive normalisation (Maya's rule), Polygons positions in Maya units, cell
edits through the Scene proxies (undoable), Auto Update and the window's classes / properties."""

from importlib import import_module

import bpy

import kit

ce = import_module(kit.MODULE + ".ui.component_editor")
mw = import_module(kit.MODULE + ".ui.marked_window")
units = import_module(kit.MODULE + ".operators.units")

TOL = 1e-6
NAMES = ["joint1", "joint2", "joint3"]
# vertex 0..3 bottom ring, 4..7 top ring of a 4-sided tube (Maya numbers: joint3 weighs nothing on these vertices)
POINTS = [(1, 0, 0), (0, 1, 0), (-1, 0, 0), (0, -1, 0), (1, 0, 2), (0, 1, 2), (-1, 0, 2), (0, -1, 2)]
FACES = [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
WEIGHTS = [[0.962, 0.038, 0.0]] * 4 + [[0.8, 0.2, 0.0]] * 4


def _close(a, b, tol=TOL):
    assert len(a) == len(b) and all(abs(x - y) < tol for x, y in zip(a, b)), f"{a} != {b}"


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.armatures):
        for d in list(coll):
            coll.remove(d)
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'METERS', 1.0


def _scene(cm=False):
    _clear()
    if cm:
        us = bpy.context.scene.unit_settings
        us.system, us.length_unit, us.scale_length = 'METRIC', 'CENTIMETERS', 1.0
    data = bpy.data.armatures.new("skeleton1")
    arm = bpy.data.objects.new("skeleton1", data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    prev = None
    for k, z in enumerate((0.0, 1.0, 2.0)):
        eb = data.edit_bones.new(NAMES[k])
        eb.head, eb.tail = (0, 0, z), (0, 0, z + 1.0)
        if prev is not None:
            eb.parent = prev
        prev = eb
    bpy.ops.object.mode_set(mode='OBJECT')
    me = bpy.data.meshes.new("pCylinderShape1")
    import_module(kit.MODULE + ".compat").mesh_from_pydata(me, POINTS, [], FACES)   # 5.0.1 .select_edge
    ob = bpy.data.objects.new("pCylinder1", me)
    bpy.context.scene.collection.objects.link(ob)
    for n in NAMES:
        ob.vertex_groups.new(name=n)
    for vi, row in enumerate(WEIGHTS):
        for n, w in zip(NAMES, row):
            if w > 0.0:
                ob.vertex_groups[n].add([vi], w, 'REPLACE')
    md = ob.modifiers.new("skinCluster1", 'ARMATURE')
    md.object = arm
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    return ob


def _select_verts(ob, indices):
    for v in ob.data.vertices:
        v.select = v.index in indices
    for e in (*ob.data.edges, *ob.data.polygons):     # entering edit mode flushes face / edge selection down
        e.select = False
    ob.data.update()


def _weights(ob, vi):
    out = [0.0] * len(NAMES)
    for g in ob.data.vertices[vi].groups:
        n = ob.vertex_groups[g.group].name
        if n in NAMES:
            out[NAMES.index(n)] = g.weight
    return out


# --- the normalisation rule -----------------------------------------------------------------------------------

def test_normalize_matches_maya():
    _close(ce.normalize([0.8, 0.2, 0.0], 0, 0.5), [0.5, 0.5, 0.0])
    _close(ce.normalize([0.5, 0.5, 0.0], 2, 0.3), [0.35, 0.35, 0.3])
    _close(ce.normalize([0.5, 0.5, 0.0], 0, 1.0), [1.0, 0.0, 0.0])
    _close(ce.normalize([0.5, 0.5, 0.0], 0, 1.7), [1.0, 0.0, 0.0])          # clamped to [0, 1]
    _close(ce.normalize([0.5, 0.5, 0.0], 0, -1.0), [0.0, 1.0, 0.0])


def test_normalize_hold_and_empty_others():
    # Hold (lock_weight) keeps joint2; joint3 takes the rest of 1 - w
    _close(ce.normalize([0.5, 0.2, 0.3], 0, 0.4, locked={1}), [0.4, 0.2, 0.4])
    # a held influence can't be pushed: w is limited to 1 - held
    _close(ce.normalize([0.5, 0.2, 0.3], 0, 0.9, locked={1}), [0.8, 0.2, 0.0])
    # the others weigh nothing: the rest is shared equally by the unheld others
    _close(ce.normalize([1.0, 0.0, 0.0], 0, 0.5), [0.5, 0.25, 0.25])
    # nothing to rebalance: only the edited cell changes
    _close(ce.normalize([0.5, 0.5], 0, 0.3, locked={1}), [0.3, 0.5])


# --- table ----------------------------------------------------------------------------------------------------------

def test_smooth_skins_table():
    ob = _scene()
    _select_verts(ob, {5, 0, 1})
    tab = ce.table(bpy.context, "SMOOTH_SKINS", hide_zero=False)
    assert tab["columns"] == NAMES + ["Total"], tab["columns"]
    (shape, rows), = tab["shapes"]
    assert shape == "pCylinderShape1", shape
    assert [r["label"] for r in rows] == ["vtx[0]", "vtx[1]", "vtx[5]"], rows
    _close(rows[0]["values"], [0.962, 0.038, 0.0, 1.0], 1e-5)
    _close(rows[2]["values"], [0.8, 0.2, 0.0, 1.0], 1e-5)
    assert tab["hold"] == [False, False, False], tab["hold"]
    # Hide Zero Columns: joint3 weighs nothing on the shown vertices (hidden, like Maya)
    tab = ce.table(bpy.context, "SMOOTH_SKINS", hide_zero=True)
    assert tab["columns"] == ["joint1", "joint2", "Total"], tab["columns"]
    assert len(tab["shapes"][0][1][0]["values"]) == 3
    assert ce.cell_text(0.962) == "0.962" and ce.cell_text(1.0) == "1.000"


def test_edit_mode_rows_follow_bmesh_selection():
    ob = _scene()
    _select_verts(ob, set())
    bpy.ops.object.mode_set(mode='EDIT')
    import bmesh
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    for i in (7, 2):
        bm.verts[i].select = True
    tab = ce.table(bpy.context, "POLYGONS", hide_zero=True)
    got = [r["label"] for r in tab["shapes"][0][1]] if tab["shapes"] else tab
    assert got == ["vtx[2]", "vtx[7]"], got
    bpy.ops.object.mode_set(mode='OBJECT')


def test_no_skin_no_skin_rows():
    ob = _scene()
    ob.modifiers.remove(ob.modifiers[0])
    _select_verts(ob, {0})
    assert ce.table(bpy.context, "SMOOTH_SKINS", hide_zero=True)["shapes"] == []
    assert len(ce.table(bpy.context, "POLYGONS", hide_zero=True)["shapes"]) == 1


def test_polygons_in_maya_units():
    ob = _scene(cm=True)
    assert abs(units.maya_unit(bpy.context.scene) - 0.01) < 1e-12
    _select_verts(ob, {4})
    tab = ce.table(bpy.context, "POLYGONS", hide_zero=True)
    assert tab["columns"][:3] == ["vertex.x", "vertex.y", "vertex.z"], tab["columns"]
    row = tab["shapes"][0][1][0]
    _close(row["values"][:3], [100.0, 0.0, 200.0], 1e-4)       # 1 m = 100 cm (Maya units)


# --- proxies and edits ----------------------------------------------------------------------------------------------

def test_position_edit_round_trip_and_undo():
    ob = _scene(cm=True)
    _select_verts(ob, {4})
    ce.rebuild(bpy.context)
    cell = ce.cell(bpy.context.scene, ob.name, 4, "z")
    assert cell is not None and abs(cell.value - 200.0) < 1e-4
    bpy.ops.ed.undo_push(message="before")
    cell.value = 1.0
    bpy.ops.ed.undo_push(message="edit")
    assert abs(ob.data.vertices[4].co.z - 0.01) < 1e-7, ob.data.vertices[4].co
    assert abs(cell.value - 1.0) < 1e-5
    bpy.ops.ed.undo()
    ob = bpy.data.objects["pCylinder1"]
    assert abs(ob.data.vertices[4].co.z - 2.0) < 1e-6, ob.data.vertices[4].co


def test_position_edit_in_edit_mode():
    ob = _scene()
    _select_verts(ob, {1})
    bpy.ops.object.mode_set(mode='EDIT')
    ce.rebuild(bpy.context)
    ce.cell(bpy.context.scene, ob.name, 1, "x").value = 0.25
    import bmesh
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    assert abs(bm.verts[1].co.x - 0.25) < 1e-7
    bpy.ops.object.mode_set(mode='OBJECT')
    assert abs(ob.data.vertices[1].co.x - 0.25) < 1e-7


def test_weight_edit_round_trip_hold_and_undo():
    ob = _scene()
    _select_verts(ob, {4, 5})
    ce.rebuild(bpy.context)
    sc = bpy.context.scene
    bpy.ops.ed.undo_push(message="before")
    ce.cell(sc, ob.name, 4, "joint1").value = 0.5          # [0.8, 0.2, 0] -> [0.5, 0.5, 0] (CE5)
    bpy.ops.ed.undo_push(message="weight")
    _close(_weights(ob, 4), [0.5, 0.5, 0.0], 1e-6)
    _close(_weights(ob, 5), [0.8, 0.2, 0.0], 1e-6)          # other vertices untouched
    ce.cell(sc, ob.name, 4, "joint3").value = 0.3          # -> [0.35, 0.35, 0.3]
    bpy.ops.ed.undo_push(message="weight 2")
    _close(_weights(ob, 4), [0.35, 0.35, 0.3], 1e-6)
    # Hold joint2 through its proxy: then joint1 edits only take from joint3
    hold = ce.hold(sc, ob.name, "joint2")
    assert hold is not None and hold.value is False
    hold.value = True
    assert ob.vertex_groups["joint2"].lock_weight
    ce.cell(sc, ob.name, 4, "joint1").value = 0.65
    bpy.ops.ed.undo_push(message="weight 3")
    _close(_weights(ob, 4), [0.65, 0.35, 0.0], 1e-6)
    tab = ce.table(bpy.context, "SMOOTH_SKINS", hide_zero=False)
    assert tab["hold"][1] is True
    bpy.ops.ed.undo()
    ob = bpy.data.objects["pCylinder1"]
    _close(_weights(ob, 4), [0.35, 0.35, 0.3], 1e-6)


def test_weight_edit_in_edit_mode():
    ob = _scene()
    _select_verts(ob, {0})
    bpy.ops.object.mode_set(mode='EDIT')
    ce.rebuild(bpy.context)
    ce.cell(bpy.context.scene, ob.name, 0, "joint2").value = 0.5
    bpy.ops.object.mode_set(mode='OBJECT')
    _close(_weights(ob, 0), [0.5, 0.5, 0.0], 1e-6)


def test_auto_update_follows_selection():
    ob = _scene()
    wm = bpy.context.window_manager
    assert wm.allset_ce_auto_update is True and wm.allset_ce_hide_zero is True
    _select_verts(ob, {0})
    ce.rebuild(bpy.context)
    assert ce.cell(bpy.context.scene, ob.name, 3, "x") is None
    _select_verts(ob, {0, 3})
    assert ce.needs_rebuild(bpy.context)
    ce.rebuild(bpy.context)
    assert not ce.needs_rebuild(bpy.context)
    assert ce.cell(bpy.context.scene, ob.name, 3, "x") is not None
    bpy.ops.allset.ce_load()
    assert ce.cell(bpy.context.scene, ob.name, 0, "joint1") is not None


def test_classes_registered():
    for name in ("ALLSET_OT_component_editor", "ALLSET_OT_ce_load", "ALLSET_OT_ce_close", "ALLSET_PT_component_editor"):
        assert hasattr(bpy.types, name), name
    assert hasattr(bpy.types.Scene, "allset_ce")
    assert {k for k, _lab in ce.TABS} >= {"SMOOTH_SKINS", "POLYGONS"} and len(ce.TABS) == 8
    assert "COMPONENT_EDITOR" in mw.KINDS


def test_unregister_leaves_nothing():
    kit.disable()
    try:
        for name in ("ALLSET_PT_component_editor", "ALLSET_OT_component_editor"):
            assert not hasattr(bpy.types, name), name
        assert not hasattr(bpy.types.Scene, "allset_ce")
        for name in ("allset_ce_auto_update", "allset_ce_hide_zero", "allset_ce_tab"):
            assert not hasattr(bpy.types.WindowManager, name), name
        assert ce._on_depsgraph not in bpy.app.handlers.depsgraph_update_post
    finally:
        kit.enable()
