"""Maya Multi-Cut tool (GitHub #27, #28).
GUI: tests/gui/gui_step129_multi_cut.py. Cut counts = Maya polySplit."""

import math
from importlib import import_module

import bmesh
import bpy
from mathutils import Vector

import kit

mc = import_module(kit.MODULE + ".operators.multi_cut")
mt = import_module(kit.MODULE + ".operators.mesh_tools")
ui_mt = import_module(kit.MODULE + ".ui.mesh_tools")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")
notices = import_module(kit.MODULE + ".ui.notices")
mm = import_module(kit.MODULE + ".marking.menus")
command_line = import_module(kit.MODULE + ".command_line")

TOOL = ("tool", "allset.multi_cut_tool", True)


def _cube():
    """A Maya-style polyCube 1 x 1 x 1 as a bmesh (8 v / 12 e / 6 f)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for seq in (bm.verts, bm.edges, bm.faces):
        seq.index_update()
        seq.ensure_lookup_table()
    return bm


def _counts(bm):
    return len(bm.verts), len(bm.edges), len(bm.faces)


def _vert(bm, co):
    return next(v for v in bm.verts if (v.co - Vector(co)).length < 1e-5)


def _edge(bm, a, b):
    va, vb = _vert(bm, a), _vert(bm, b)
    return next(e for e in va.link_edges if vb in e.verts)


def _edge_point(bm, a, b, t_from_a):
    """('EDGE', i, t) with t from the edge's first vertex, given t counted from ``a``."""
    e = _edge(bm, a, b)
    t = t_from_a if (e.verts[0].co - Vector(a)).length < 1e-5 else 1.0 - t_from_a
    return ('EDGE', e.index, t)


# front face y = -0.5: corners (+-0.5, -0.5, +-0.5)
LB, LT, RB, RT = (-.5, -.5, -.5), (-.5, -.5, .5), (.5, -.5, -.5), (.5, -.5, .5)


def test_two_edge_points_match_maya_polysplit():
    bm = _cube()
    pts = [_edge_point(bm, LB, LT, 0.25), _edge_point(bm, RB, RT, 0.5)]
    edges = mc.cut(bm, pts)
    assert _counts(bm) == (10, 15, 7), _counts(bm)          # Maya: 8/12/6 -> 10/15/7
    assert len(edges) == 1
    assert any((v.co - Vector((-.5, -.5, -.25))).length < 1e-6 for v in bm.verts), "25 % from the first vertex"
    assert any((v.co - Vector((.5, -.5, 0))).length < 1e-6 for v in bm.verts)
    bm.free()


def test_face_point_becomes_a_vertex_inside_the_face():
    bm = _cube()
    f = next(f for f in bm.faces if abs(f.calc_center_median().y + 0.5) < 1e-6)
    pts = [_edge_point(bm, LB, LT, 0.5), ('FACE', f.index, (0.0, -0.5, 0.2)), _edge_point(bm, RB, RT, 0.5)]
    edges = mc.cut(bm, pts)
    assert _counts(bm) == (11, 16, 7), _counts(bm)
    assert len(edges) == 2
    assert any((v.co - Vector((0, -.5, .2))).length < 1e-6 for v in bm.verts)
    bm.free()


def test_start_on_a_vertex_and_points_on_one_edge():
    bm = _cube()
    v = _vert(bm, LB)
    pts = [('VERT', v.index), _edge_point(bm, RB, RT, 0.5)]
    assert len(mc.cut(bm, pts)) == 1
    assert _counts(bm) == (9, 14, 7), _counts(bm)
    bm.free()
    bm = _cube()                                       # two cuts that end on the same edge
    e_left = _edge_point(bm, LB, LT, 0.25)
    pts = [e_left, _edge_point(bm, RB, RT, 0.5), _edge_point(bm, LB, LT, 0.75)]
    assert len(mc.cut(bm, pts)) == 2
    assert _counts(bm) == (11, 17, 8), _counts(bm)
    ys = sorted(round(v.co.z, 6) for v in bm.verts if abs(v.co.x + .5) < 1e-6 and abs(v.co.y + .5) < 1e-6)
    assert ys == [-0.5, -0.25, 0.25, 0.5], ys
    bm.free()


def test_edge_end_is_the_vertex_and_points_must_share_a_face():
    bm = _cube()
    e = _edge(bm, LB, LT)
    assert mc.normalize(bm, ('EDGE', e.index, 0.0)) == ('VERT', e.verts[0].index)
    assert mc.normalize(bm, ('EDGE', e.index, 1.0)) == ('VERT', e.verts[1].index)
    first = [_edge_point(bm, LB, LT, 0.5)]
    assert mc.accepts(bm, first, _edge_point(bm, RB, RT, 0.5)), "same face"
    back = _edge_point(bm, (.5, .5, -.5), (.5, .5, .5), 0.5)
    assert not mc.accepts(bm, first, back), "back edge shares no face with the left front edge"
    assert not mc.accepts(bm, first, first[0]), "the same point again"
    bm.free()


def test_subdivisions_and_smoothing_angle():
    bm = _cube()
    edges = mc.cut(bm, [_edge_point(bm, LB, LT, 0.5), _edge_point(bm, RB, RT, 0.5)], subdivisions=3)
    assert len(edges) == 3 and _counts(bm) == (12, 17, 7), (len(edges), _counts(bm))
    assert all(e.smooth for e in edges), "Smoothing Angle 180: soft"
    assert mc.divided([Vector((0, 0, 0)), Vector((3, 0, 0))], 3)[1] == Vector((1, 0, 0))
    bm.free()


def test_loop_and_its_preview():
    bm = _cube()
    e = _edge(bm, LB, LT)
    segs = mc.loop_segments(bm, e.index, 0.3)
    assert len(segs) == 4, segs
    edges = mc.loop(bm, e.index, 0.3)
    assert len(edges) == 4 and _counts(bm) == (12, 20, 10), (len(edges), _counts(bm))
    bm.free()


def test_slice_plane_delete_and_extract():
    bm = _cube()
    cut = mc.slice_mesh(bm, Vector((0, 0, 0)), Vector((0, 0, 1)))
    assert len(cut) == 4 and _counts(bm) == (12, 20, 10), (len(cut), _counts(bm))
    bm.free()
    bm = _cube()
    mc.slice_mesh(bm, Vector((0, 0, 0)), Vector((0, 0, 1)), delete=True)
    assert max(v.co.z for v in bm.verts if v.link_faces) <= 1e-6, "faces above the plane deleted"
    bm.free()
    bm = _cube()
    mc.slice_mesh(bm, Vector((0, 0, 0)), Vector((0, 0, 1)), extract=Vector((0, 0, 1)))
    zs = sorted({round(v.co.z, 6) for v in bm.verts})
    assert zs == [-0.5, 0.0, 1.0, 1.5], zs
    bm.free()


def test_snap_step_on_edge_points():
    assert mc.snapped(('EDGE', 3, 0.33), 25, True) == ('EDGE', 3, 0.25)
    assert mc.snapped(('EDGE', 3, 0.33), 25, False) == ('EDGE', 3, 0.33)
    assert mc.snapped(('VERT', 3), 25, True) == ('VERT', 3)


def test_settings_maya_defaults_and_reset():
    s = bpy.context.scene.allset_mesh_tools
    want = {"snap_step": 10, "smoothing_angle": 180.0, "edge_flow": False, "subdivisions": 1,
            "ignore_backfaces": False, "delete_faces": False, "extract_faces": False, "slice_plane": 'NONE'}
    assert {k: getattr(s, k) for k in want} == want, "default values"
    assert tuple(s.extract_offset) == (0.5, 0.5, 0.5)
    s.snap_step, s.subdivisions, s.slice_plane = 25, 4, 'XY'
    mc.reset_settings(s)
    assert (s.snap_step, s.subdivisions, s.slice_plane) == (10, 1, 'NONE')


def _tool_ids():
    from bl_ui.space_toolsystem_common import ToolSelectPanelHelper
    from bl_ui.space_toolsystem_toolbar import VIEW3D_PT_tools_active
    return [it.idname for it, _i in ToolSelectPanelHelper._tools_flatten_with_tool_index(
        VIEW3D_PT_tools_active.tools_from_context(bpy.context, 'EDIT_MESH')) if it is not None]


def test_tool_keymap_and_unregister():
    assert "allset.multi_cut_tool" in _tool_ids()
    km = bpy.context.window_manager.keyconfigs.addon.keymaps.get("3D View Tool: Edit Mesh, Multi-Cut")
    assert km is not None
    items = [(k.idname, k.type, k.value, k.any, k.ctrl) for k in km.keymap_items]
    assert ("allset.multi_cut", 'LEFTMOUSE', 'PRESS', True, -1) in items, items     # any modifier
    assert ("allset.multicut_loop", 'MIDDLEMOUSE', 'PRESS', False, 1) in items, items   # Ctrl+MMB
    assert [i[0] for i in items[:3]] == ["allset.multicut_loop"] * 3, "loops ahead of the any-modifier LMB"
    assert ("allset.multi_cut_hover", 'MOUSEMOVE', 'ANY', True, -1) in items, items
    assert any(i[:2] == ("allset.multi_cut_exit", 'ESC') for i in items)
    kit.disable()
    try:
        assert "allset.multi_cut_tool" not in _tool_ids()
        assert bpy.context.window_manager.keyconfigs.addon.keymaps.get("3D View Tool: Edit Mesh, Multi-Cut") is None
        assert getattr(bpy.types, "ALLSET_OT_multi_cut", None) is None
    finally:
        kit.enable()
    assert "allset.multi_cut_tool" in _tool_ids()


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


def test_menu_shelf_marking_menu_hotkey_point_to_the_tool():
    assert menu_map.MAP["Mesh Tools/Multi-Cut"] == TOOL
    assert shelf_map.BY_COMMAND["MultiCutTool"][0] == TOOL
    cuts = []
    for menu in (mm.SHIFT_OBJECT, mm.SHIFT_VERTEX, mm.SHIFT_EDGE, mm.SHIFT_FACE):
        _actions(menu, "Multi-Cut", cuts)
    assert len(cuts) == 4 and all(a == TOOL for a in cuts), cuts
    km = kit.maya_kc().keymaps["Mesh"]
    hot = [(k.idname, k.properties.tool) for k in km.keymap_items
           if k.active and k.type == 'X' and k.ctrl and k.shift and not k.alt]
    assert hot == [("allset.menu_tool", "allset.multi_cut_tool")], hot
    assert "Backspace" in command_line.help_for_tool("allset.multi_cut_tool")
    for key in ui_mt.GREY:
        assert key in notices.PANEL_NOTICES, key


def test_knife_is_blender_again():
    """Multi-Cut is no longer the knife: there are no knife patches (Shift = Blender's ignore snap)."""
    kc = kit.maya_kc()
    modal = kc.keymaps["Knife Tool Modal Map"]
    shift = {k.propvalue for k in modal.keymap_items if k.type in ('LEFT_SHIFT', 'RIGHT_SHIFT')}
    assert not shift & {'SNAP_MIDPOINTS_ON', 'SNAP_MIDPOINTS_OFF'}, shift
    knife = kc.keymaps.get("3D View Tool: Edit Mesh, Knife")
    if knife is not None:
        assert not [k for k in knife.keymap_items if k.idname.startswith("allset.")]


def test_cut_operator_on_an_edit_mesh():
    """The modal's completion path: ``cut`` on an edit-mode mesh keeps it valid and updates the edit mesh."""
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.mesh.primitive_cube_add(size=1)
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    bm.edges.ensure_lookup_table()
    pts = [_edge_point(bm, LB, LT, 0.5), _edge_point(bm, RB, RT, 0.5)]
    mc.cut(bm, pts, 1, math.pi)
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.object.mode_set(mode='OBJECT')
    assert (len(ob.data.vertices), len(ob.data.edges), len(ob.data.polygons)) == (10, 15, 7)
