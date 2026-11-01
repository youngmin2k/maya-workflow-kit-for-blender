"""The Channel Box in component mode (Maya: the shape, the CVs line / table, INPUTS — no transform rows) and the
RMB list's DG Traversal / Inputs / Outputs submenus, following Maya 2022.
"""

from importlib import import_module

import bmesh
import bpy

import kit
from test_step135_channel_box import Recorder

cb = import_module(kit.MODULE + ".ui.channel_box")
cb_points = import_module(kit.MODULE + ".ui.cb_points")
creation_inputs = import_module(kit.MODULE + ".ui.creation_inputs")
mm = import_module(kit.MODULE + ".marking.menus")
modal = import_module(kit.MODULE + ".marking.modal")
rmb_nodes = import_module(kit.MODULE + ".marking.rmb_nodes")
notices = import_module(kit.MODULE + ".ui.notices")

TRANSFORM_LABELS = ("Translate X", "Rotate X", "Scale X", "Visibility")


def _fresh():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    cb.reset_open()
    bpy.context.window_manager.allset_cb_points = False


def _cube():
    assert bpy.ops.allset.create(kind='CUBE') == {'FINISHED'}
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    ob = bpy.context.view_layer.objects.active
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    return ob


def _edit(ob, mode, indices):
    """Edit mode, select mode ``mode`` (VERT / EDGE / FACE), exactly ``indices`` selected."""
    bpy.context.view_layer.objects.active = ob
    if ob.mode != 'EDIT':
        bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type=mode)
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(ob.data)
    seq = {"VERT": bm.verts, "EDGE": bm.edges, "FACE": bm.faces}[mode]
    seq.ensure_lookup_table()
    for i in indices:
        seq[i].select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)


def _draw():
    rec = Recorder()
    cb.ALLSET_PT_channel_box.body(rec, bpy.context)
    return rec


def _texts(rec):
    return [t for k, t, _a, _p in rec.log if k in ("label", "operator")]


def _shape_field(rec):
    return [a for k, _t, a, _p in rec.log if k == "prop" and len(a) > 1 and a[1] == "name"]


def test_object_mode_keeps_transform_rows():
    _fresh()
    ob = _cube()
    rec = _draw()
    assert rec.ops("allset.cb_select_channel") or any(t in str(rec.log) for t in TRANSFORM_LABELS)
    assert "SHAPES" in rec.texts("label")
    assert _shape_field(rec)[0][0] == ob, "object mode: the lead's name"


def test_vertices_selected_shape_cvs_inputs():
    _fresh()
    ob = _cube()
    _edit(ob, 'VERT', [0, 1, 3])
    assert cb.component_mode(ob)
    rec = _draw()
    texts = _texts(rec)
    assert _shape_field(rec)[0][0] == ob.data, "Maya: the shape's name (cb165/cb_vtx_three.png)"
    assert "SHAPES" not in texts, "no SHAPES header in component mode"
    assert not rec.ops("allset.cb_select_channel"), "no Translate / Rotate / Scale / Visibility rows"
    assert "CVs (click to show)" in texts, texts
    assert texts.index("CVs (click to show)") < texts.index("INPUTS"), "CVs line above INPUTS"
    node = cb.history_node(creation_inputs.prim_history.node_of(ob)[1]["name"])
    assert [p.node for p in rec.ops("allset.cb_node_toggle")] == [node], "INPUTS polyCube1 like object mode"


def test_cvs_table_lists_selected_points_and_edits():
    _fresh()
    ob = _cube()
    _edit(ob, 'VERT', [0, 1, 3])
    assert bpy.ops.allset.cb_points_toggle() == {'FINISHED'}
    rec = _draw()
    texts = _texts(rec)
    assert "CVs (click to hide)" in texts
    assert ["X", "Y", "Z"] == [t for t in texts if t in ("X", "Y", "Z")]
    assert [t for t in texts if t in ("0", "1", "3")] == ["0", "1", "3"], "one row per selected point (index)"
    props = bpy.context.scene.allset_cb_points
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    v = bm.verts[1]
    unit = bpy.context.scene.unit_settings
    shown = float(props.p1_x)
    assert abs(shown * (0.01 if unit.length_unit == 'CENTIMETERS' and unit.scale_length == 1.0 else 1.0)
               - v.co.x) < 1e-6 or abs(shown - v.co.x) < 1e-6, (props.p1_x, v.co.x)
    old = v.co.x
    props.p1_x = "+=1"
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    assert bm.verts[1].co.x > old, "typing moves the vertex (relative entry like Maya)"
    # the table stays open for the next selection (cb_vtx_one_after_cv.png)
    _edit(ob, 'VERT', [2])
    assert "CVs (click to hide)" in _texts(_draw())
    bpy.ops.allset.cb_points_toggle()
    assert "CVs (click to show)" in _texts(_draw())


def test_edges_faces_no_cvs_line_nothing_selected_empty():
    _fresh()
    ob = _cube()
    for mode, idx in (('EDGE', [0, 1]), ('FACE', [1])):
        _edit(ob, mode, idx)
        texts = _texts(_draw())
        assert "INPUTS" in texts and not any(t.startswith("CVs") for t in texts), (mode, texts)
        assert not _draw().ops("allset.cb_select_channel")
    _edit(ob, 'VERT', [])
    texts = _texts(_draw())
    assert not any(t in texts for t in ("INPUTS", "SHAPES")), "Maya: nothing selected = empty Channel Box"
    bpy.ops.object.mode_set(mode='OBJECT')
    assert "SHAPES" in _texts(_draw()), "back in object mode: the transform view again"


def test_modifier_inputs_in_component_mode():
    _fresh()
    ob = _cube()
    md = ob.modifiers.new("Bend", 'SIMPLE_DEFORM')
    _edit(ob, 'FACE', [2])
    rec = _draw()
    assert cb.mod_node(md) in [p.node for p in rec.ops("allset.cb_node_toggle")]


# --- RMB DG Traversal / Inputs / Outputs -------------------------------------------------------------------------

def _menu(ob):
    menu = mm.with_object_name(mm.RMB_MESH, ob.name)
    return mm.with_nodes(menu, rmb_nodes.nodes(ob))


def _sub(menu, label):
    return dict(e for e in menu.items if e != mm.DIVIDER)[label]


def _labels(sub):
    return ["-" if e == mm.DIVIDER else e[0] for e in sub.items]


def test_static_lists_are_not_greyed():
    for label in ("DG Traversal", "Inputs", "Outputs"):
        action = _sub(mm.RMB_MESH, label)
        assert isinstance(action, mm.NodeList) and not mm.is_greyed(action), label
        assert modal.poll_action(action), label
        assert f"RMB_MESH/{label}" not in notices.MARKING


def test_inputs_outputs_plain_cube_like_maya():
    _fresh()
    ob = _cube()
    menu = _menu(ob)
    node = creation_inputs.prim_history.node_of(ob)[1]
    # rmb_plain_Inputs.png
    assert _labels(_sub(menu, "Inputs")) == ["Select All Inputs", "Enable All Inputs", "Disable All Inputs", "-",
                                             "Poly Cube", "-", "All Inputs..."], _labels(_sub(menu, "Inputs"))
    assert "Poly Cube" in _sub(menu, "Inputs").options, "Maya option box = Attribute Editor"
    # rmb_plain_Outputs.png
    assert _labels(_sub(menu, "Outputs")) == ["Select All Outputs", "Enable All Outputs", "Disable All Outputs", "-",
                                              "All Outputs..."]
    trav = _sub(menu, "DG Traversal")
    lab = _labels(trav)
    assert lab[0] == f"Select {ob.name}" and lab[1:3] == ["-", "History"], lab
    assert ob.data.name in lab and "Future" in lab, lab
    assert "initialShadingGroup" in lab, "the default material's shading group is in the future (lambert1)"
    shape_sub = dict(e for e in trav.items if e != mm.DIVIDER)[ob.data.name]
    assert _labels(shape_sub)[0] == f"Select {ob.data.name}"
    assert node["name"] in _labels(shape_sub), "the shape's history lists polyCube1 (rmb_plain_DG_Traversal)"


def test_pick_input_node_opens_it_in_channel_box():
    _fresh()
    ob = _cube()
    md = ob.modifiers.new("Bend", 'SIMPLE_DEFORM')
    inputs = _sub(_menu(ob), "Inputs")
    rows = {e[0]: e[1] for e in inputs.items if e != mm.DIVIDER}
    assert list(rows)[3:5] == ["Non Linear", "Poly Cube"], list(rows)   # Simple Deform = Maya nonLinear (bend)
    action = rows["Non Linear"]
    assert action[0] == "allset.mm_node"
    bpy.context.view_layer.objects.active = None
    ob.select_set(False)
    assert bpy.ops.allset.mm_node(**action[1]) == {'FINISHED'}
    assert bpy.context.view_layer.objects.active == ob and ob.select_get(), "select -add: the object is the lead"
    assert cb.is_open(ob, cb.mod_node(md)), "the picked node opens under INPUTS (cb_hist_pick_extrude.png)"
    assert bpy.context.window_manager.allset_ae_tab == "M:" + md.name, "the Attribute Editor follows"


def test_enable_disable_all_inputs():
    _fresh()
    ob = _cube()
    md = ob.modifiers.new("Bend", 'SIMPLE_DEFORM')
    con = ob.constraints.new('COPY_LOCATION')
    assert bpy.ops.allset.mm_node_all(object=ob.name, action='DISABLE') == {'FINISHED'}
    assert not md.show_viewport and not md.show_render and not con.enabled
    assert bpy.ops.allset.mm_node_all(object=ob.name, action='ENABLE') == {'FINISHED'}
    assert md.show_viewport and md.show_render and con.enabled
    assert bpy.ops.allset.mm_node_all(object=ob.name, action='SELECT') == {'FINISHED'}
    assert cb.is_open(ob, cb.mod_node(md)) and cb.is_open(ob, cb.con_node(ob, con))


def test_outputs_list_users_of_the_object():
    _fresh()
    cube = _cube()
    target = bpy.data.objects.new("locator1", None)
    bpy.context.scene.collection.objects.link(target)
    con = cube.constraints.new('COPY_LOCATION')
    con.target = target
    md = cube.modifiers.new("Hook", 'HOOK')
    md.object = target
    data = rmb_nodes.nodes(target)
    labels = [e[0] for e in data["outputs"]]
    assert labels == ["Hook", "Copy Location"] or len(labels) == 2, labels
    outs = _sub(mm.with_nodes(mm.RMB_MESH, data), "Outputs")
    rows = [e for e in outs.items if e != mm.DIVIDER and e[1][0] == "allset.mm_node"]
    assert all(r[1][1]["object"] == cube.name for r in rows), "the node lives on the cube"
    assert bpy.ops.allset.mm_node(**rows[0][1][1]) == {'FINISHED'}
    assert bpy.context.view_layer.objects.active == cube
    assert bpy.ops.allset.mm_node_all(object=target.name, future=True, action='DISABLE') == {'FINISHED'}
    assert not md.show_viewport and not con.enabled


def test_traversal_select_replaces():
    _fresh()
    a = _cube()
    b = _cube()
    for o in (a, b):
        o.select_set(True)
    trav = _sub(_menu(a), "DG Traversal")
    action = trav.items[0][1]
    assert bpy.ops.allset.mm_node(**action[1]) == {'FINISHED'}
    assert [o.name for o in bpy.context.selected_objects] == [a.name], "select -r <object>"


def test_node_table_and_label_ops():
    _fresh()
    ob = _cube()
    assert bpy.ops.allset.mm_node_label() == {'CANCELLED'}
    rec = Recorder()
    op = rmb_nodes.ALLSET_OT_mm_node_table
    fake = type("F", (), {"layout": rec, "object": ob.name, "future": False})()
    op.draw(fake, bpy.context)
    assert any("List of input operations" in t for t in rec.texts("label"))
    assert any("Poly Cube" in (t or "") for t in rec.texts("operator"))


def test_object_mode_inputs_with_modifier_keep_creation_node():
    _fresh()
    ob = _cube()
    md = ob.modifiers.new("Bend", 'SIMPLE_DEFORM')
    nodes = [p.node for p in _draw().ops("allset.cb_node_toggle")]
    node = cb.history_node(creation_inputs.prim_history.node_of(ob)[1]["name"])
    assert nodes == [cb.mod_node(md), node], nodes


def test_lattice_points_cvs_table():
    _fresh()
    bpy.ops.object.add(type='LATTICE')
    ob = bpy.context.active_object
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    bpy.ops.object.mode_set(mode='EDIT')
    for i, p in enumerate(ob.data.points):
        p.select = i in (1, 5)
    assert cb.component_mode(ob)
    rec = _draw()
    assert "CVs (click to show)" in _texts(rec), _texts(rec)
    bpy.ops.allset.cb_points_toggle()
    texts = _texts(_draw())
    assert [t for t in texts if t in ("1", "5")] == ["1", "5"], texts
    props = bpy.context.scene.allset_cb_points
    p5 = ob.data.points[5].co_deform
    assert abs(float(props.p1_x) - p5.x) < 1e-6, (props.p1_x, p5.x)      # lattice space, a plain number
    old_z = p5.z
    props.p1_z = "+=0.25"
    z = ob.data.points[5].co_deform.z
    assert abs(z - (old_z + 0.25)) < 1e-6, (old_z, z)
    bpy.ops.object.mode_set(mode='OBJECT')
    assert abs(ob.data.points[5].co_deform.z - z) < 1e-6, "the typed value stays after edit mode"
    bpy.ops.object.mode_set(mode='EDIT')
    for p in ob.data.points:
        p.select = False
    assert "CVs (click to hide)" not in _texts(_draw()), "nothing selected: no CVs line"
    bpy.ops.allset.cb_points_toggle()
