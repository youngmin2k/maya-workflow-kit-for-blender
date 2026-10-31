"""Tool Box double-click opens Tool Settings (#3); Maya Tool Settings sections for the
Tool Box select tools (#29) and the Mesh Tools tools (#28)."""


from importlib import import_module
from types import SimpleNamespace

import bpy

import kit
from test_step106_tool_settings_ae import Recorder

ts_mod = import_module(kit.MODULE + ".ui.tool_settings")
toolbox = import_module(kit.MODULE + ".ui.toolbox")
tool_dock = import_module(kit.MODULE + ".ui.tool_dock")
dock_tabs = import_module(kit.MODULE + ".ui.dock_tabs")
notices = import_module(kit.MODULE + ".ui.notices")
mesh_ops = import_module(kit.MODULE + ".operators.mesh_tools")

# Default Tool Settings: section titles in display order and which start open
MAYA = {
    'SELECT': [("Common Selection Options", True), ("Soft Selection", False), ("Symmetry Settings", False)],
    'LASSO': [("Lasso Settings", True), ("Soft Selection", False), ("Symmetry Settings", False)],
    'PAINT_SELECT': [("Brush", True), ("Paint Operations", True), ("Stroke", False), ("Stylus Pressure", False),
                     ("Attribute Maps", False), ("Display", False)],
    'INSERT_EDGE_LOOP': [("Description", True), ("Settings", True)],
    'SLIDE_EDGE': [("Description", True), ("Settings", True), ("Snapping Settings", True)],
    'TARGET_WELD': [("Description", True), ("Settings", True), ("Keyboard/Mouse Shortcuts", False)],
    'CREASE': [("Description", True), ("Settings", True)],
    'QUAD_DRAW': [("Settings", True), ("Live Constraint Options", False), ("Keyboard/Mouse Shortcuts", False)],
}
TOOLS = {"builtin.select_box": 'SELECT', "builtin.select": 'SELECT', "builtin.select_lasso": 'LASSO',
         "builtin.select_circle": 'PAINT_SELECT', "allset.insert_edge_loop_tool": 'INSERT_EDGE_LOOP',
         "allset.slide_edge_tool": 'SLIDE_EDGE', "allset.target_weld_tool": 'TARGET_WELD',   # kit tools
         "allset.crease_tool": 'CREASE', "allset.quad_draw_tool": 'QUAD_DRAW'}     # the kit Quad Draw
NAMES = {'SELECT': "Select Tool", 'LASSO': "Lasso Tool", 'PAINT_SELECT': "Paint Selection Tool",
         'INSERT_EDGE_LOOP': "Insert Edge Loop Tool", 'SLIDE_EDGE': "Slide Edge Tool", 'TARGET_WELD': "Target Weld Tool",
         'CREASE': "Crease Tool", 'QUAD_DRAW': "Quad Draw Tool"}


def _mode(mode):
    ob = bpy.context.view_layer.objects.active
    if ob is None:
        bpy.ops.mesh.primitive_cube_add()
        ob = bpy.context.active_object
    if bpy.context.mode != mode:
        bpy.ops.object.mode_set(mode='EDIT' if mode == 'EDIT_MESH' else 'OBJECT')


def _props(identifier, **values):
    return SimpleNamespace(bl_rna=SimpleNamespace(identifier=identifier), **values)


FAKE = ("allset.insert_edge_loop_tool", "allset.slide_edge_tool", "allset.quad_draw_tool")
_REAL_ACTIVE = ts_mod.active_tool


class FakeTool:
    """Tool operator properties as Blender's tools hold them (defaults read with bpy.ops ... get_rna_type)."""

    def __init__(self, idname):
        self.idname = idname
        self._ops = {
            "mesh.loopcut_slide": SimpleNamespace(
                MESH_OT_loopcut=_props("MESH_OT_loopcut", number_cuts=1, smoothness=0.0),
                TRANSFORM_OT_edge_slide=_props("TRANSFORM_OT_edge_slide", use_even=False, correct_uv=True)),
            "transform.edge_slide": _props("TRANSFORM_OT_edge_slide", use_even=False, correct_uv=True),
        }

    def operator_properties(self, op):
        return self._ops[op]


def _set_tool(idname, mode='EDIT_MESH'):
    """The real tool (select tools). Edit-mode mesh tools can't be set in -b (their keymaps are built by functions
    that need a keyconfig, and ``WorkSpaceTool.setup`` crashes there): they get a stand-in (``FakeTool``)."""
    _mode(mode)
    if idname in FAKE:
        fake = FakeTool(idname)
        ts_mod.active_tool = lambda c: fake
        return fake
    ts_mod.active_tool = _REAL_ACTIVE
    bpy.ops.wm.tool_set_by_id(name=idname, space_type='VIEW_3D')
    tool = bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=False)
    assert tool is not None and tool.idname == idname, (idname, tool and tool.idname)
    return tool


def _draw(kind):
    rec = Recorder()
    for key, _title, _open in ts_mod.sections(kind):
        ts_mod.draw_section(rec, bpy.context, key, kind)
    return rec


def test_tools_have_kinds_and_maya_names():
    for idname, kind in TOOLS.items():
        assert ts_mod.KIND_OF.get(idname) == kind, idname
        assert ts_mod.TOOL_NAMES[kind] == NAMES[kind]
    # Move / Rotate / Scale unchanged
    assert ts_mod.KIND_OF["builtin.move"] == 'TRANSLATE'


def test_sections_follow_maya():
    for kind, expected in MAYA.items():
        got = [(title, is_open) for _key, title, is_open in ts_mod.sections(kind)]
        assert got == expected, (kind, got)
    # the shared Common Selection Options stays closed for Move
    assert ("Common Selection Options", False) in [(t, o) for _k, t, o in ts_mod.sections('TRANSLATE')]


def test_select_tool_rows():
    _set_tool("builtin.select_box")
    rec = _draw('SELECT')
    assert "Selection Style:" in rec.texts("label") and "Symmetry:" in rec.texts("label")
    props = rec.texts("prop")
    assert "Camera-based selection" in props and "Highlight nearest component" in props and "Soft Select" in props


def test_lasso_rows():
    _set_tool("builtin.select_lasso")
    rec = _draw('LASSO')
    labels, ops = rec.texts("label"), rec.texts("operator")
    assert "Draw style:" in labels and "Component selection:" in labels
    assert "Open" in ops and "Fast" in ops      # greyed Maya options
    assert "Soft Select" in rec.texts("prop")


def test_paint_select_rows_and_options():
    tool = _set_tool("builtin.select_circle")
    props = tool.operator_properties("view3d.select_circle")
    rec = _draw('PAINT_SELECT')
    owners = {(kw["_args"][0].bl_rna.identifier, kw["_args"][1]) for k, _t, kw in rec.log
              if k == "prop" and len(kw["_args"]) > 1}
    assert ("VIEW3D_OT_select_circle", "radius") in owners, owners
    ops = rec.texts("operator")
    for text in ("Select", "Unselect", "Add to current selection", "Select All", "Unselect All", "Toggle All"):
        assert text in ops, (text, ops)
    # paint operation radio -> Blender's select mode
    bpy.ops.allset.ts_option(option="paint_op", value="UNSELECT")
    assert props.mode == 'SUB'
    bpy.ops.allset.ts_option(option="paint_op", value="SELECT")
    assert props.mode == 'ADD'                  # Maya: Add to current selection is on
    bpy.ops.allset.ts_option(option="paint_add", value="")
    assert props.mode == 'SET'
    bpy.ops.allset.ts_option(option="paint_add", value="")
    assert props.mode == 'ADD'
    props.mode = 'SET'
    assert bpy.ops.allset.reset_tool() == {'FINISHED'}
    assert props.mode == 'ADD', props.mode      # default: Select + Add to current selection


def _owners(rec):
    return {(kw["_args"][0].bl_rna.identifier, kw["_args"][1]) for k, _t, kw in rec.log
            if k == "prop" and len(kw["_args"]) > 1}


def test_insert_edge_loop_maintain_position():
    """LOOP: the rows are the kit Insert Edge Loop tool's settings (Scene.allset_loop_tools)."""
    _set_tool("allset.insert_edge_loop_tool")
    s = bpy.context.scene.allset_loop_tools
    assert ts_mod.edge_loop_position(bpy.context) == 'RELATIVE'
    bpy.ops.allset.ts_option(option="iel_position", value="EQUAL")
    assert s.iel_position == 'EQUAL'
    bpy.ops.allset.ts_option(option="iel_position", value="MULTIPLE")
    assert s.iel_position == 'MULTIPLE' and s.iel_loops == 2       # Maya Number of edge loops 2
    rec = _draw('INSERT_EDGE_LOOP')
    assert "Maintain position:" in rec.texts("label")
    assert {("ALLSET_PG_loop_tools", n) for n in ("iel_position", "iel_loops", "iel_edge_flow", "iel_smoothing")} \
        <= _owners(rec)
    assert bpy.ops.allset.reset_tool() == {'FINISHED'}
    assert s.iel_position == 'RELATIVE'


def test_slide_edge_mode():
    _set_tool("allset.slide_edge_tool")
    s = bpy.context.scene.allset_loop_tools
    bpy.ops.allset.ts_option(option="slide_mode", value="ABSOLUTE")
    assert s.slide_mode == 'ABSOLUTE'
    bpy.ops.allset.ts_option(option="slide_mode", value="RELATIVE")
    assert s.slide_mode == 'RELATIVE'
    rec = _draw('SLIDE_EDGE')
    assert "Mode:" in rec.texts("label")
    assert {("ALLSET_PG_loop_tools", n) for n in ("slide_mode", "slide_snap", "slide_snap_points",
                                                  "slide_snap_tolerance")} <= _owners(rec)


def test_target_weld_and_crease_bind_kit_settings():
    s = mesh_ops.settings(bpy.context)
    rec = _draw('TARGET_WELD')
    owners = {(kw["_args"][0].bl_rna.identifier, kw["_args"][1]) for k, _t, kw in rec.log
              if k == "prop" and len(kw["_args"]) > 1}
    assert {("ALLSET_PG_mesh_tools", "weld_merge_to"), ("ALLSET_PG_mesh_tools", "weld_preserve_uvs")} <= owners
    rec = _draw('CREASE')
    owners = {(kw["_args"][0].bl_rna.identifier, kw["_args"][1]) for k, _t, kw in rec.log
              if k == "prop" and len(kw["_args"]) > 1}
    assert ("ALLSET_PG_mesh_tools", "crease_mode") in owners
    s.weld_merge_to, s.weld_preserve_uvs, s.crease_mode = 'CENTER', False, 'RELATIVE'
    ts_mod.reset_kind_defaults(bpy.context, 'TARGET_WELD')
    ts_mod.reset_kind_defaults(bpy.context, 'CREASE')
    assert (s.weld_merge_to, s.weld_preserve_uvs, s.crease_mode) == ('TARGET', True, 'ABSOLUTE')


def test_quad_draw_rows_are_live():
    """The kit Quad Draw's Maya rows are real settings now (Scene.allset_poly_tools), not greyed Poly Build
    stand-ins; the shortcuts section lists Maya's keys."""
    _set_tool("allset.quad_draw_tool")
    rec = _draw('QUAD_DRAW')
    greyed = {p.item for p in rec.ops("allset.menu_unavailable")}
    assert "Tool Settings/Quad Draw/Auto-weld" not in greyed
    owners = {(kw["_args"][0].bl_rna.identifier, kw["_args"][1]) for k, _t, kw in rec.log
              if k == "prop" and len(kw["_args"]) > 1}
    assert {("ALLSET_PG_poly_tools", "qd_auto_weld"), ("ALLSET_PG_poly_tools", "qd_relax")} <= owners, owners
    assert len(rec.texts("label")) >= 10                             # Keyboard/Mouse Shortcuts rows


def test_greyed_rows_have_tooltips():
    paths = set()
    for idname, kind in TOOLS.items():
        if kind in ('TARGET_WELD', 'CREASE'):
            rec = _draw(kind)
        else:
            _set_tool(idname, 'EDIT_MESH')
            rec = _draw(kind)
        paths |= {p.item for p in rec.ops("allset.menu_unavailable")}
    assert len(paths) >= 20, paths
    for path in paths:
        text = notices.tooltip(path, mapped=False)
        assert text and "\n" in text, path


def test_dock_hides_blender_panels_for_these_tools():
    ctx = SimpleNamespace(region=SimpleNamespace(type='WINDOW'), space_data=SimpleNamespace(type='PROPERTIES'),
                          mode='EDIT_MESH', area=None)
    saved = ts_mod.active_tool
    try:
        for idname in TOOLS:
            ts_mod.active_tool = lambda c, i=idname: SimpleNamespace(idname=i)
            assert dock_tabs._hidden(ctx), idname
        ts_mod.active_tool = lambda c: SimpleNamespace(idname="builtin.knife")   # Multi-Cut: Blender's panel stays
        assert not dock_tabs._hidden(ctx)
    finally:
        ts_mod.active_tool = saved


def test_double_click_detection():
    # a toolbar button's operator sees the toolbar's context member (its region is the view's WINDOW, like a key's)
    tools = SimpleNamespace(region=SimpleNamespace(type='WINDOW'), space_data=SimpleNamespace(type='VIEW_3D'),
                            preferences=bpy.context.preferences, window=None,
                            **{toolbox.TOOLBAR_MEMBER: SimpleNamespace(type='VIEW_3D')})
    keys = SimpleNamespace(region=SimpleNamespace(type='WINDOW'), space_data=SimpleNamespace(type='VIEW_3D'),
                           preferences=bpy.context.preferences, window=None)
    limit = bpy.context.preferences.inputs.mouse_double_click_time / 1000.0
    toolbox._last_click[:] = [None, 0.0]
    assert not toolbox.note_tool_click(tools, "builtin.select_lasso", now=10.0)
    assert toolbox.note_tool_click(tools, "builtin.select_lasso", now=10.0 + limit * 0.5)   # double click
    assert not toolbox.note_tool_click(tools, "builtin.select_lasso", now=10.0 + limit * 0.6)   # a third click: new
    assert not toolbox.note_tool_click(tools, "builtin.move", now=20.0)
    assert not toolbox.note_tool_click(tools, "builtin.move", now=20.0 + limit * 1.5)    # too slow
    assert not toolbox.note_tool_click(tools, "builtin.rotate", now=30.0)
    assert not toolbox.note_tool_click(tools, "builtin.scale", now=30.1)                 # another tool
    assert not toolbox.note_tool_click(keys, "builtin.move", now=40.0)                   # W W: keys never open it
    assert not toolbox.note_tool_click(keys, "builtin.move", now=40.1)


def test_activate_by_id_wrapped_while_enabled():
    from bl_ui import space_toolsystem_common as stc
    assert getattr(stc.activate_by_id, "_allset_wrapped", False)
    kit.disable()
    try:
        assert not getattr(stc.activate_by_id, "_allset_wrapped", False)
    finally:
        kit.enable()
    assert getattr(stc.activate_by_id, "_allset_wrapped", False)


def test_show_keeps_an_existing_dock():
    # a Tool Settings dock that is already open anywhere (docked or torn off) is only redrawn
    space = SimpleNamespace(type='PROPERTIES', show_region_header=False, context='TOOL')
    area = SimpleNamespace(type='PROPERTIES', spaces=SimpleNamespace(active=space), tag_redraw=lambda: None,
                           as_pointer=lambda: 1)
    win = SimpleNamespace(screen=SimpleNamespace(areas=[area]))
    ctx = SimpleNamespace(window_manager=SimpleNamespace(windows=[win]), window=None, screen=None)
    assert tool_dock.show(ctx) is area
