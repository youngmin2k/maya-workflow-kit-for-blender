"""Maya 3D Cut and Sew UV Tool — stroke sampling, shell borders, cut / sew on a cube (islands), the tool and
its keys, the menu / shelf / marking menu / UV Toolkit entries, Unfold + Layout.
GUI: tests/gui/gui_step79_cut_sew.py."""

from importlib import import_module

import bmesh
import bpy

import kit

cs = import_module(kit.MODULE + ".operators.cut_sew")
uv_tools = import_module(kit.MODULE + ".operators.uv_tools")
preselect = import_module(kit.MODULE + ".operators.preselect")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")
menus = import_module(kit.MODULE + ".marking.menus")
notices = import_module(kit.MODULE + ".ui.notices")

KM = "3D View Tool: Edit Mesh, 3D Cut and Sew UV Tool"


def test_stroke_points():
    pts = cs.stroke_points((0, 0), (10, 0), step=4)
    assert pts[-1] == (10, 0) and len(pts) == 3, pts
    assert all(abs(b[0] - a[0]) <= 4 for a, b in zip([(0, 0)] + pts, pts))
    assert cs.stroke_points((5, 5), (5, 5)) == [(5.0, 5.0)]


def test_near_end():
    assert cs.near_end((0, 0), (3, 4), (100, 0), px=6)
    assert not cs.near_end((50, 5), (0, 0), (100, 0), px=6)
    assert not cs.near_end((0, 0), None, (100, 0), px=6)


def _cube():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    return ob


def _top_edges(bm):
    top = max(bm.faces, key=lambda f: f.calc_center_median().z)
    return list(top.edges)


def test_cut_and_sew_the_top_face():
    ob = _cube()
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.verify()
    n0 = len(uv_tools.islands(bm, uv))
    assert n0 == 1, f"Blender's cube UVs are one cross-shaped shell ({n0})"
    borders0 = len(cs.border_edges(bm, uv))
    assert cs.apply(bm, uv, _top_edges(bm), "CUT") == 4
    assert len(uv_tools.islands(bm, uv)) == 2, "the top face is its own shell"
    assert len(cs.border_edges(bm, uv)) > borders0, "its edges are shell borders now"
    assert cs.apply(bm, uv, _top_edges(bm), "SEW") >= 1
    assert len(uv_tools.islands(bm, uv)) == 1, "sewn back"
    assert not any(e.seam for e in _top_edges(bm))
    bmesh.update_edit_mesh(ob.data)


def test_select_action_only_selects():
    ob = _cube()
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.verify()
    for e in bm.edges:
        e.select_set(False)
    cs.apply(bm, uv, _top_edges(bm), "SELECT")
    assert sum(e.select for e in bm.edges) == 4 and len(uv_tools.islands(bm, uv)) == 1


def test_tool_and_keys():
    from bl_ui.space_toolsystem_common import ToolSelectPanelHelper
    from bl_ui.space_toolsystem_toolbar import VIEW3D_PT_tools_active
    ids = [it.idname for it, _i in ToolSelectPanelHelper._tools_flatten_with_tool_index(
        VIEW3D_PT_tools_active.tools_from_context(bpy.context, 'EDIT_MESH')) if it is not None]
    assert cs.TOOL in ids, ids
    km = bpy.context.window_manager.keyconfigs.addon.keymaps.get(KM)
    assert km is not None, [k.name for k in bpy.context.window_manager.keyconfigs.addon.keymaps if "Tool" in k.name]
    got = {(k.type, k.ctrl, k.shift, k.idname, getattr(k.properties, "action", None)) for k in km.keymap_items}
    want = {('LEFTMOUSE', False, False, "allset.cut_sew_stroke", 'CUT'),
            ('LEFTMOUSE', True, False, "allset.cut_sew_stroke", 'SEW'),
            ('LEFTMOUSE', False, True, "allset.cut_sew_stroke", 'SELECT'),
            ('X', False, False, "allset.uv_cut", None), ('S', False, False, "allset.uv_sew", None),
            ('D', False, False, "allset.uv_unfold_layout", None)}
    assert want <= got, got
    assert cs.TOOL.startswith(preselect.SELECT_TOOLS), "pre-selection shows the edge a press cuts"


def test_entries():
    assert menu_map.MAP["UV/3D Cut and Sew UV Tool"] == "allset.cut_sew_tool_set"
    assert "UV/3D Cut and Sew UV Tool" not in notices.NOTICES
    assert shelf_map.BY_COMMAND["SetCutSewUVTool"][0] == "allset.cut_sew_tool_set"
    for name in ("SHIFT_UV", "SHIFT_UV_SHELL"):
        assert menus.MENUS[name].radial["NW"] == ("3D Cut and Sew UV Tool", "allset.cut_sew_tool_set"), name


def test_tool_set_needs_a_view_and_unfold_layout_runs():
    ob = _cube()
    bpy.ops.object.mode_set(mode='OBJECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    assert bpy.ops.allset.cut_sew_tool_set.poll()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.verify()
    cs.apply(bm, uv, _top_edges(bm), "CUT")
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.uv_unfold_layout() == {'FINISHED'}
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.verify()
    us = [l[uv].uv for f in bm.faces for l in f.loops]
    assert all(-1e-4 <= u.x <= 1 + 1e-4 and -1e-4 <= u.y <= 1 + 1e-4 for u in us), "laid out in 0-1"
    assert len(uv_tools.islands(bm, uv)) == 2
