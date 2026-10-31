"""LOOP lane (GitHub #31): Insert Edge Loop, Offset Edge Loop and Slide Edge as Maya tools.
GUI: tests/gui/gui_step144_loop.py. Every expected number below is what
Maya gives on the same meshes (polySplitRing / polyDuplicateEdge /
polySlideEdge), plus the Tool Settings / window defaults."""

from importlib import import_module

import bmesh
import bpy
from mathutils import Vector

import kit

el = import_module(kit.MODULE + ".operators.edge_loops")
ow = import_module(kit.MODULE + ".operators.option_windows")
owe = import_module(kit.MODULE + ".operators.option_windows_edit")
ui_loop = import_module(kit.MODULE + ".ui.mesh_tools_loop")
ts_mod = import_module(kit.MODULE + ".ui.tool_settings")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
marking = import_module(kit.MODULE + ".marking.menus")
notices = import_module(kit.MODULE + ".ui.notices")
command_line = import_module(kit.MODULE + ".command_line")


def _r(v):
    return tuple(round(c, 4) + 0.0 for c in v)


def strip(scale=1.0):
    """The test strip: 3 quads along x, ring edges at x = -1.5 / -0.5 / 0.5 / 1.5 from
    y = -0.5 up to 0.5 / 1.0 / 1.5 / 2.0. Ring edges are made bottom -> top (verts[0] = bottom, Maya's first
    vertex)."""
    bm = bmesh.new()
    bottom = [bm.verts.new(Vector((x, -0.5, 0)) * scale) for x in (-1.5, -0.5, 0.5, 1.5)]
    top = [bm.verts.new(Vector((x, 0.5 + 0.5 * k, 0)) * scale) for k, x in enumerate((-1.5, -0.5, 0.5, 1.5))]
    for b, t in zip(bottom, top):
        bm.edges.new((b, t))
    for i in range(3):
        bm.faces.new((bottom[i], bottom[i + 1], top[i + 1], top[i]))
    return bm


def grid():
    """Maya's grid: polyPlane 4 x 4 in XY with the column x = 1 moved to x = 0.5."""
    bm = bmesh.new()
    xs, ys = (-2.0, -1.0, 0.0, 0.5, 2.0), (-2.0, -1.0, 0.0, 1.0, 2.0)
    v = [[bm.verts.new((x, y, 0)) for x in xs] for y in ys]
    for j in range(4):
        for i in range(4):
            bm.faces.new((v[j][i], v[j][i + 1], v[j + 1][i + 1], v[j + 1][i]))
    return bm


def ring_edge(bm, x):
    return next(e for e in bm.edges if all(abs(v.co.x - x) < 1e-6 for v in e.verts))


def column(bm, x, ylo=-9.0, yhi=9.0):
    return [e for e in bm.edges if all(abs(v.co.x - x) < 1e-6 for v in e.verts)
            and min(v.co.y for v in e.verts) >= ylo - 1e-6 and max(v.co.y for v in e.verts) <= yhi + 1e-6]


def new_verts(bm, before):
    return sorted(_r(v.co) for v in bm.verts if _r(v.co) not in before)


def face_sizes(bm):
    return sorted(len(f.verts) for f in bm.faces)


def coords(bm):
    return {_r(v.co) for v in bm.verts}


# --- Insert Edge Loop (polySplitRing) ---------------------------------------------------------------------


def test_insert_multiple_loops_ignore_the_click():
    for n, fracs in ((1, (0.5,)), (2, (1 / 3, 2 / 3)), (3, (0.25, 0.5, 0.75))):
        bm = strip()
        before = coords(bm)
        el.insert_loops(bm, ring_edge(bm, -0.5), 0.1, 'MULTIPLE', count=n)
        want = sorted(_r((x, -0.5 + f * length, 0.0)) for x, length in ((-1.5, 1.0), (-0.5, 1.5), (0.5, 2.0),
                                                                        (1.5, 2.5)) for f in fracs)
        assert new_verts(bm, before) == want, (n, new_verts(bm, before))
        assert face_sizes(bm) == [4] * (3 * (n + 1))
        bm.free()


def test_ring_stops_at_non_quads():
    bm = strip()
    tri_top = bm.verts.new((2.5, -0.5, 0))
    bm.faces.new((next(v for v in bm.verts if _r(v.co) == (1.5, -0.5, 0.0)), tri_top,
                  next(v for v in bm.verts if _r(v.co) == (1.5, 2.0, 0.0))))
    items, faces, closed = el.ring(ring_edge(bm, -0.5), ring_edge(bm, -0.5).verts[0])
    assert len(items) == 4 and len(faces) == 3 and not closed
    bm.free()


# --- Offset Edge Loop (polyDuplicateEdge) ------------------------------------------------------------------


def test_offset_refuses_border_edges():
    bm = grid()
    border = [e for e in bm.edges if e.is_boundary and all(abs(v.co.x + 2) < 1e-6 for v in e.verts)]
    assert el.offset_loops(bm, border, 0.5) is None
    bm.free()


# --- Slide Edge (polySlideEdge) ----------------------------------------------------------------------------

def _slide(bm, edges, f, absolute, towards_x):
    frame = el.slide_frame(edges)
    origins = {v: v.co.copy() for v in bm.verts}
    v0, (wa, wb) = next(iter(frame.items()))
    side = 0 if (wa.co.x - v0.co.x) * towards_x > 0 else 1
    for v, co in el.slide_positions(frame, origins, side, f, absolute).items():
        v.co = co


def test_slide_a_whole_loop_moves_each_vertex_once():
    bm = grid()
    loop = column(bm, 0.0)
    _slide(bm, loop, 0.3, False, +1)
    assert {round(v.co.x, 4) for e in loop for v in e.verts} == {0.15}
    bm.free()
    bm = grid()
    loop = column(bm, 0.0)
    _slide(bm, loop, 0.3, True, -1)
    assert {round(v.co.x, 4) for e in loop for v in e.verts} == {-0.3}     # 0.3 x the shortest left side edge (1)
    bm.free()


def test_snap_points_and_tolerance():
    assert el.snap(0.46) == 0.5 and el.snap(0.35) == 0.35 and el.snap(0.04) == 0.0 and el.snap(0.97) == 1.0
    assert el.snap(0.24, points=3) == 0.25 and el.snap(0.3, points=3, tolerance=0.01) == 0.3


# --- tools, menus, Tool Settings, windows -----------------------------------------------------------------

def _tool_ids(mode):
    from bl_ui.space_toolsystem_common import ToolSelectPanelHelper
    from bl_ui.space_toolsystem_toolbar import VIEW3D_PT_tools_active
    return [it.idname for it, _i in ToolSelectPanelHelper._tools_flatten_with_tool_index(
        VIEW3D_PT_tools_active.tools_from_context(bpy.context, mode)) if it is not None]


def test_menus_marking_and_help_are_the_kit_tools():
    assert menu_map.MAP["Mesh Tools/Insert Edge Loop"] == ("tool", el.INSERT_TOOL, True)
    assert menu_map.MAP["Mesh Tools/Offset Edge Loop"] == ("tool", el.OFFSET_TOOL, True)
    assert menu_map.MAP["Mesh Tools/Slide Edge"] == ("tool", el.SLIDE_TOOL, True)
    text = repr([m.radial for m in vars(marking).values() if isinstance(m, marking.MarkingMenu)]
                + [m.items for m in vars(marking).values() if isinstance(m, marking.MarkingMenu)])
    assert "builtin.loop_cut" not in text and "builtin.edge_slide" not in text
    for tool in (el.INSERT_TOOL, el.OFFSET_TOOL, el.SLIDE_TOOL):
        assert command_line.help_for_tool(tool), tool
    assert menu_sets.option_kind("Mesh Tools/Slide Edge") == "tool"
    assert menu_sets.option_kind("Mesh Tools/Offset Edge Loop") == "window"
    assert menu_sets.option_kind("Mesh Tools/Insert Edge Loop") == "window"


def test_tools_and_keymaps_registered_and_removed():
    edit = _tool_ids('EDIT_MESH')
    assert {el.INSERT_TOOL, el.OFFSET_TOOL, el.SLIDE_TOOL} <= set(edit), edit
    kms = bpy.context.window_manager.keyconfigs.addon.keymaps
    want = {"Insert Edge Loop Tool": ("allset.insert_edge_loop", 'LEFTMOUSE'),
            "Offset Edge Loop Tool": ("allset.offset_edge_loop", 'LEFTMOUSE'),
            "Slide Edge Tool": ("allset.slide_edge", 'MIDDLEMOUSE')}
    for label, (op, button) in want.items():
        km = kms.get(f"3D View Tool: Edit Mesh, {label}")
        assert km is not None, label
        items = [(k.idname, k.type, k.value, k.ctrl, k.shift, k.alt) for k in km.keymap_items]
        assert (op, button, 'PRESS', False, False, False) in items, items
    kit.disable()
    try:
        assert el.INSERT_TOOL not in _tool_ids('EDIT_MESH')
        assert kms.get("3D View Tool: Edit Mesh, Slide Edge Tool") is None
        assert not hasattr(bpy.types.Scene, "allset_loop_tools")
        assert not any(me.name.startswith(el.PRE_MESH) for me in bpy.data.meshes)
    finally:
        kit.enable()
    assert el.SLIDE_TOOL in _tool_ids('EDIT_MESH')


def test_tool_settings_defaults_sections_and_reset():
    assert ts_mod.KIND_OF[el.INSERT_TOOL] == 'INSERT_EDGE_LOOP'
    assert ts_mod.KIND_OF[el.OFFSET_TOOL] == 'OFFSET_EDGE_LOOP'
    assert ts_mod.KIND_OF[el.SLIDE_TOOL] == 'SLIDE_EDGE'
    assert "builtin.loop_cut" not in ts_mod.KIND_OF and "builtin.edge_slide" not in ts_mod.KIND_OF
    s = el.settings()
    for kind in el.SETTINGS:
        el.reset_settings(s, kind)
    want = {"iel_position": 'RELATIVE', "iel_loops": 2, "iel_edge_flow": False, "iel_adjust_flow": 1.0,
            "iel_smoothing": 30.0,
            "oel_position": 'RELATIVE', "oel_delete_edge": True, "oel_edge_flow": False, "oel_adjust_flow": 1.0,
            "oel_smoothing": 180.0, "oel_offset": 0.5,
            "slide_mode": 'RELATIVE', "slide_snap": True, "slide_snap_points": 1}
    assert {k: getattr(s, k) for k in want} == want
    assert abs(s.slide_snap_tolerance - 0.1) < 1e-6
    s.iel_loops, s.oel_smoothing, s.slide_snap = 5, 10.0, False
    for kind in ('INSERT_EDGE_LOOP', 'OFFSET_EDGE_LOOP', 'SLIDE_EDGE'):
        ts_mod.reset_kind_defaults(bpy.context, kind)
    assert (s.iel_loops, s.oel_smoothing, s.slide_snap) == (2, 180.0, True)
    assert [t for _k, t, _o in ts_mod.sections('SLIDE_EDGE')] == ["Description", "Settings", "Snapping Settings"]
    assert [t for _k, t, _o in ts_mod.sections('OFFSET_EDGE_LOOP')] == ["Description", "Settings"]
    assert ts_mod.TOOL_NAMES['OFFSET_EDGE_LOOP'] == "Offset Edge Loop Tool"
    for key in ui_loop.GREY:
        assert key in notices.PANEL_NOTICES, key


def test_offset_edge_loop_window_is_maya_s():
    w = ow.find_path("Mesh Tools/Offset Edge Loop")
    assert w is not None and w.key == "offset_edge_loop"
    assert (w.title, w.action, w.apply_text) == ("Offset Edge Loop Options", "Enter Tool And Close", "Enter Tool")
    assert [(f.name, f.label, f.default) for f in w.fields] == [
        ("delete_edge", "", True), ("edge_flow", "", False), ("adjust_edge_flow", "Adjust Edge Flow:", 1.0),
        ("smoothing", "Smoothing angle:", 180.0), ("maintain", "Maintain position:", "Relative distance from edge")]
    s = owe.offset_edge_loop_options(bpy.context, {**w.defaults(), "maintain": "Equal distance from edge",
                                                   "smoothing": 45.0, "delete_edge": False})
    assert (s.oel_position, s.oel_smoothing, s.oel_delete_edge) == ('EQUAL', 45.0, False)
    el.reset_settings(s, 'OFFSET')
    assert ow.find_path("Mesh Tools/Insert Edge Loop").key == "insert_edge_loop"


def _edit_grid():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    me = bpy.data.meshes.new("loopGrid")
    bm = grid()
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("loopGrid", me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    return ob


def test_operators_exec_and_undo_step():
    ob = _edit_grid()
    bm = bmesh.from_edit_mesh(ob.data)
    e = column(bm, 0.0, -1, 0)[0]
    bm.edges.index_update()
    res = bpy.ops.allset.insert_edge_loop('EXEC_DEFAULT', object=ob.name, edge=e.index, weight=0.5)
    assert res == {'FINISHED'}
    bm = bmesh.from_edit_mesh(ob.data)
    assert len(bm.verts) == 30, len(bm.verts)                       # a loop through the 5-edge ring
    # the selected new loop -> Offset Edge Loop on the selection (RMB To Edge Loop and Duplicate path)
    assert bpy.ops.allset.offset_edge_loop('EXEC_DEFAULT', offset=0.5) == {'FINISHED'}
    bm = bmesh.from_edit_mesh(ob.data)
    assert len(bm.verts) == 40, len(bm.verts)
    # Slide the selected (offset) loops: nothing selected -> Maya's warning, CANCELLED
    bpy.ops.mesh.select_all(action='DESELECT')
    assert bpy.ops.allset.slide_edge('EXEC_DEFAULT', factor=0.5) == {'CANCELLED'}
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.data.objects.remove(ob)
