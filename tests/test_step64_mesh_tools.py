"""Target Weld, Crease Tool, Multi-Cut feel (Ctrl+click edge loop, Shift snap step).
GUI: tests/gui/gui_step64_mesh_tools.py."""

import math
from importlib import import_module

import bmesh
import bpy
from mathutils import Vector

import kit

mt = import_module(kit.MODULE + ".operators.mesh_tools")
ui_mt = import_module(kit.MODULE + ".ui.mesh_tools")
mtk = import_module(kit.MODULE + ".ui.modeling_toolkit")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")
notices = import_module(kit.MODULE + ".ui.notices")
mm = import_module(kit.MODULE + ".marking.menus")
command_line = import_module(kit.MODULE + ".command_line")
maya_patches = import_module(kit.MODULE + ".keymap.maya_patches")

TARGET_WELD = ("tool", "allset.target_weld_tool", True)
CREASE = ("tool", "allset.crease_tool", True)


def _cube():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.mesh.primitive_cube_add(size=2)
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    return ob


def _bm(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    for seq in (bm.verts, bm.edges, bm.faces):
        seq.ensure_lookup_table()
    return bm


def _select_mode(v, e, f):
    bpy.context.tool_settings.mesh_select_mode = (v, e, f)


def _deselect(bm):
    for seq in (bm.verts, bm.edges, bm.faces):
        for el in seq:
            el.select = False


def _vert_at(bm, co):
    return next(v for v in bm.verts if (v.co - Vector(co)).length < 1e-5)


def _edge(bm, a, b):
    va, vb = _vert_at(bm, a), _vert_at(bm, b)
    return next(e for e in va.link_edges if vb in e.verts)


# --- crease ------------------------------------------------------------------------------------------

def _corner(b, levels=2):
    """Subsurf (no limit surface) of a cube with every edge creased ``b``: x+y+z of the corner (3 = sharp)."""
    bpy.ops.mesh.primitive_cube_add(size=2)
    ob = bpy.context.active_object
    att = ob.data.attributes.new("crease_edge", 'FLOAT', 'EDGE')
    for e in ob.data.edges:
        att.data[e.index].value = b
    mod = ob.modifiers.new("s", 'SUBSURF')
    mod.levels, mod.use_limit_surface = levels, False
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).to_mesh()
    top = max(v.co.x + v.co.y + v.co.z for v in me.vertices)
    ob.evaluated_get(dg).to_mesh_clear()
    bpy.data.objects.remove(ob)
    return top


def test_crease_mapping_matches_blender_sharpness():
    """Blender OpenSubdiv sharpness = 10 * crease^2: Maya crease c (sharp for c levels) = sqrt(c/10)."""
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    assert abs(_corner(mt.maya_to_blender_crease(2.0) + 1e-4) - 3.0) < 1e-5, "Maya 2 = sharp after 2 levels"
    assert _corner(mt.maya_to_blender_crease(1.9)) < 3.0 - 1e-3, "Maya 1.9 is not"
    assert abs(_corner(mt.maya_to_blender_crease(1.0) + 1e-4, levels=1) - 3.0) < 1e-5, "Maya 1 = sharp after 1 level"
    assert mt.maya_to_blender_crease(10) == 1.0 and mt.maya_to_blender_crease(25) == 1.0
    assert mt.maya_to_blender_crease(0) == 0.0
    assert abs(mt.blender_to_maya_crease(mt.maya_to_blender_crease(2.5)) - 2.5) < 1e-9


def test_crease_drag_exec_absolute_relative_and_vertices():
    ob = _cube()
    _select_mode(False, True, False)
    bm = _bm(ob)
    _deselect(bm)
    e1, e2 = bm.edges[0], bm.edges[1]
    e1.select = e2.select = True
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.crease_drag(value=2.0, mode='ABSOLUTE') == {'FINISHED'}
    bm = _bm(ob)
    layer = bm.edges.layers.float.get("crease_edge")
    assert layer is not None
    assert all(abs(bm.edges[i][layer] - math.sqrt(0.2)) < 1e-6 for i in (0, 1))
    assert all(bm.edges[i][layer] == 0.0 for i in range(2, len(bm.edges)))
    assert bpy.ops.allset.crease_drag(value=1.0, mode='RELATIVE') == {'FINISHED'}
    bm = _bm(ob)
    layer = bm.edges.layers.float.get("crease_edge")
    assert abs(mt.blender_to_maya_crease(bm.edges[0][layer]) - 3.0) < 1e-6, "relative adds to Maya 2"
    # vertex mode creases vertices
    _select_mode(True, False, False)
    _deselect(bm)
    bm.verts[0].select = True
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.crease_drag(value=10.0, mode='ABSOLUTE') == {'FINISHED'}
    bm = _bm(ob)
    vl = bm.verts.layers.float.get("crease_vert")
    assert vl is not None and bm.verts[0][vl] == 1.0 and bm.verts[1][vl] == 0.0
    # nothing selected: Maya's "Select components to crease"
    _deselect(bm)
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.crease_drag(value=1.0) == {'CANCELLED'}
    assert mt.crease_kind((False, False, True)) == 'EDGE', "face mode creases the faces' edges"


# --- Target Weld ---------------------------------------------------------------------------------------

def test_target_weld_vertex_to_target_and_center():
    ob = _cube()
    _select_mode(True, False, False)
    bm = _bm(ob)
    _deselect(bm)
    src, dst = _vert_at(bm, (1, 1, 1)), _vert_at(bm, (1, -1, 1))
    assert bpy.ops.allset.target_weld(object=ob.name, element='VERT', source=src.index, target=dst.index,
                                        merge_to='TARGET') == {'FINISHED'}
    bm = _bm(ob)
    assert len(bm.verts) == 7
    assert any((v.co - Vector((1, -1, 1))).length < 1e-6 for v in bm.verts)
    assert not any((v.co - Vector((1, 1, 1))).length < 1e-6 for v in bm.verts)
    assert all(len(f.verts) >= 3 for f in bm.faces)
    # Center
    ob = _cube()
    bm = _bm(ob)
    _deselect(bm)
    src, dst = _vert_at(bm, (1, 1, 1)), _vert_at(bm, (1, -1, 1))
    assert bpy.ops.allset.target_weld(object=ob.name, element='VERT', source=src.index, target=dst.index,
                                        merge_to='CENTER') == {'FINISHED'}
    bm = _bm(ob)
    assert len(bm.verts) == 7 and any((v.co - Vector((1, 0, 1))).length < 1e-6 for v in bm.verts)


def test_target_weld_selected_vertex_brings_the_selection():
    """Maya: "All selected vertices or edges will be merged" when the dragged one is selected."""
    ob = _cube()
    _select_mode(True, False, False)
    bm = _bm(ob)
    _deselect(bm)
    a, c = _vert_at(bm, (1, 1, 1)), _vert_at(bm, (-1, 1, 1))
    dst = _vert_at(bm, (1, -1, 1))
    a.select = c.select = True
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.target_weld(object=ob.name, element='VERT', source=a.index, target=dst.index) \
        == {'FINISHED'}
    bm = _bm(ob)
    assert len(bm.verts) == 6, len(bm.verts)
    merged = _vert_at(bm, (1, -1, 1))
    assert merged.select, "the merged vertex stays selected"
    # an unselected source merges alone
    ob = _cube()
    bm = _bm(ob)
    _deselect(bm)
    a, c, dst = _vert_at(bm, (1, 1, 1)), _vert_at(bm, (-1, 1, 1)), _vert_at(bm, (1, -1, 1))
    c.select = True
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.target_weld(object=ob.name, element='VERT', source=a.index, target=dst.index) \
        == {'FINISHED'}
    assert len(_bm(ob).verts) == 7


def test_target_weld_edges():
    # opposite edges of the top face: both ends pair up (no crossing) -> 6 vertices, the top face collapses
    ob = _cube()
    bm = _bm(ob)
    src = _edge(bm, (1, 1, 1), (-1, 1, 1))
    dst = _edge(bm, (1, -1, 1), (-1, -1, 1))
    assert bpy.ops.allset.target_weld(object=ob.name, element='EDGE', source=src.index, target=dst.index) \
        == {'FINISHED'}
    bm = _bm(ob)
    assert len(bm.verts) == 6
    assert any((v.co - Vector((1, -1, 1))).length < 1e-6 for v in bm.verts)
    assert any((v.co - Vector((-1, -1, 1))).length < 1e-6 for v in bm.verts)
    # edges sharing a vertex: the shared vertex stays, the other ends merge (Center = half-way)
    ob = _cube()
    bm = _bm(ob)
    src = _edge(bm, (1, 1, 1), (-1, 1, 1))
    dst = _edge(bm, (1, 1, 1), (1, -1, 1))
    assert bpy.ops.allset.target_weld(object=ob.name, element='EDGE', source=src.index, target=dst.index,
                                        merge_to='CENTER') == {'FINISHED'}
    bm = _bm(ob)
    assert len(bm.verts) == 7
    assert any((v.co - Vector((0, 0, 1))).length < 1e-6 for v in bm.verts)
    # same edge / bad indices: nothing happens
    assert bpy.ops.allset.target_weld(object=ob.name, element='EDGE', source=0, target=0) == {'CANCELLED'}


# --- Multi-Cut ---------------------------------------------------------------------------------------

def test_snap_step():
    assert abs(mt.snap_factor(0.33, 10) - 0.3) < 1e-9
    assert abs(mt.snap_factor(0.36, 25) - 0.25) < 1e-9
    assert mt.snap_factor(0.02, 10) == 0.0, "a cut point may snap onto the vertex"
    assert abs(mt.snap_factor(0.02, 10, inner=True) - 0.1) < 1e-9, "a loop stays inside the edge"
    assert abs(mt.snap_factor(0.98, 10, inner=True) - 0.9) < 1e-9
    assert mt.snap_factor(0.3, 50, inner=True) == 0.5 and mt.snap_factor(0.9, 100, inner=True) == 0.5
    assert bpy.context.scene.allset_mesh_tools.snap_step == 10, "Snap Step % 10"


def test_multicut_loop_at_the_clicked_position():
    ob = _cube()
    bm = _bm(ob)
    e = _edge(bm, (-1, 1, -1), (-1, -1, -1))
    t = 0.25 if e.verts[0].co.y > 0 else 0.75      # 25 % from the y = +1 end
    assert bpy.ops.allset.multicut_loop(object=ob.name, edge=e.index, factor=t) == {'FINISHED'}
    bm = _bm(ob)
    assert (len(bm.verts), len(bm.edges), len(bm.faces)) == (12, 20, 10)
    new = sorted(tuple(round(c, 4) for c in v.co) for v in bm.verts if abs(abs(v.co.y) - 1) > 1e-4)
    assert new == [(-1, 0.5, -1), (-1, 0.5, 1), (1, 0.5, -1), (1, 0.5, 1)], new
    assert bpy.ops.allset.multicut_loop(object=ob.name, edge=e.index, factor=0.0) == {'CANCELLED'}


def test_multicut_ring_stops_at_triangles():
    ob = _cube()
    bm = _bm(ob)
    top = next(f for f in bm.faces if f.normal.z > 0.9)
    bmesh.ops.triangulate(bm, faces=[top])
    bmesh.update_edit_mesh(ob.data)
    bm = _bm(ob)
    e = _edge(bm, (-1, 1, -1), (-1, -1, -1))
    ring = mt.edge_ring(e, e.verts[0], 0.5)
    assert len(ring) == 4, "both directions end at the top triangles"
    assert bpy.ops.allset.multicut_loop(object=ob.name, edge=e.index, factor=0.5) == {'FINISHED'}
    bm = _bm(ob)
    assert len(bm.verts) == 12 and all(len(f.verts) <= 4 for f in bm.faces)


# --- tools, keys, menus ---------------------------------------------------------------------------------

def _tool_ids(mode='EDIT_MESH'):
    from bl_ui.space_toolsystem_common import ToolSelectPanelHelper
    from bl_ui.space_toolsystem_toolbar import VIEW3D_PT_tools_active
    return [it.idname for it, _i in ToolSelectPanelHelper._tools_flatten_with_tool_index(
        VIEW3D_PT_tools_active.tools_from_context(bpy.context, mode)) if it is not None]


def test_tools_registered_with_keymaps():
    ids = _tool_ids()
    assert "allset.target_weld_tool" in ids and "allset.crease_tool" in ids, ids
    assert ids.index("allset.target_weld_tool") > ids.index("builtin.knife")
    addon = bpy.context.window_manager.keyconfigs.addon
    weld = addon.keymaps.get("3D View Tool: Edit Mesh, Target Weld")
    crease = addon.keymaps.get("3D View Tool: Edit Mesh, Crease Tool")
    assert weld is not None and [(k.idname, k.type, k.value) for k in weld.keymap_items] == [
        ("allset.target_weld", 'LEFTMOUSE', 'PRESS')]
    assert crease is not None and [(k.idname, k.type, k.value) for k in crease.keymap_items] == [
        ("allset.crease_drag", 'MIDDLEMOUSE', 'PRESS')]
    _cube()
    bpy.ops.wm.tool_set_by_id(name="allset.target_weld_tool", space_type='VIEW_3D')
    tool = bpy.context.workspace.tools.from_space_view3d_mode('EDIT_MESH')
    assert tool.idname == "allset.target_weld_tool"
    assert "drag a vertex" in command_line.help_for_tool(tool.idname)
    assert "Ctrl+click" in command_line.help_for_tool("allset.multi_cut_tool")
    assert "middle-drag" in command_line.help_for_tool("allset.crease_tool")
    bpy.ops.wm.tool_set_by_id(name="builtin.select_box", space_type='VIEW_3D')
    kit.disable()
    try:
        assert "allset.target_weld_tool" not in _tool_ids()
        assert addon.keymaps.get("3D View Tool: Edit Mesh, Target Weld") is None
    finally:
        kit.enable()
    assert "allset.target_weld_tool" in _tool_ids()


def _items(km_name, etype, value='PRESS', shift=False, ctrl=False):
    km = kit.maya_kc().keymaps[km_name]
    return [(k.idname, {p: getattr(k.properties, p) for p in k.properties.keys()} if k.properties else {})
            for k in km.keymap_items if k.active and k.type == etype and k.value == value
            and k.shift == shift and k.ctrl == ctrl and not k.alt]


def _actions(menu, label, out):
    for _key, (lab, act) in getattr(menu, "radial", {}).items():
        if lab == label:
            out.append(act)
        if isinstance(act, mm.Sub):
            _actions(act, label, out)
    for it in getattr(menu, "items", ()) or ():
        if isinstance(it, tuple) and len(it) == 2:
            lab, act = it
            if lab == label:
                out.append(act)
            if isinstance(act, mm.Sub):
                _actions(act, label, out)
    return out


def test_menus_marking_menus_shelf_mtk():
    assert menu_map.MAP["Mesh Tools/Target Weld"] == TARGET_WELD
    assert menu_map.MAP["Mesh Tools/Crease Tool"] == CREASE
    assert shelf_map.BY_COMMAND["MergeVertexTool"][0] == TARGET_WELD, "Polygons shelf Target Weld"
    weld, crease = [], []
    for menu in (mm.SHIFT_OBJECT, mm.SHIFT_VERTEX, mm.SHIFT_EDGE, mm.SHIFT_FACE):
        _actions(menu, "Target Weld Tool", weld)
        _actions(menu, "Crease Tool", crease)
    assert len(weld) == 4 and all(a == TARGET_WELD for a in weld), weld
    assert len(crease) == 3 and all(a == CREASE for a in crease), crease
    assert ("Target Weld", "Mesh Tools/Target Weld", 'AUTOMERGE_OFF') in mtk.TOOLS
    assert "Mesh Tools/Target Weld" not in notices.NOTICES, "no longer greyed"
    sub, line = notices.NOTICES["Mesh Tools/Crease Tool"]
    assert "0-1" in line and "Maya" in line
    for key in ui_mt.GREY:
        assert key in notices.PANEL_NOTICES, key
