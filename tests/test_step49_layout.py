"""Maya layout parity — Tool Box, dock-only sidebar, Help + Command row, the Maya Workflow Kit template's
areas. GUI: tests/gui/gui_step49_layout.py."""

import sys
from importlib import import_module
from pathlib import Path

import bpy
from bl_ui.space_toolsystem_toolbar import VIEW3D_PT_tools_active as TOOLBAR

import kit

ROOT = Path(__file__).resolve().parent.parent
toolbox = import_module(kit.MODULE + ".ui.toolbox")
dock_tabs = import_module(kit.MODULE + ".ui.dock_tabs")
maya_dock = import_module(kit.MODULE + ".ui.maya_dock")
tool_keys = import_module(kit.MODULE + ".operators.tool_keys")
command_line = import_module(kit.MODULE + ".command_line")
status_line = import_module(kit.MODULE + ".ui.status_line")
preferences = import_module(kit.MODULE + ".preferences")


def _ids(items):
    return [None if t is None else t.idname for t in items]


def _blender_items(mode):
    return list(toolbox._saved["tools_from_context"].__func__(TOOLBAR, bpy.context, mode))


def _view3d():
    area = next(a for a in bpy.context.window.screen.areas if a.type == 'VIEW_3D')
    return area, {r.type: r for r in area.regions}


# --- Tool Box --------------------------------------------------------------------------------

def test_toolbox_same_tools_in_object_and_edit_modes():
    want = list(toolbox.MAYA_TOOLS) + [None]
    for mode in ('OBJECT', 'EDIT_MESH', 'EDIT_CURVE', 'EDIT_ARMATURE', 'POSE', 'EDIT_LATTICE'):
        got = toolbox.maya_tools(_blender_items(mode), mode)
        assert got is not None and _ids(got) == want, (mode, _ids(got or []))


def test_toolbox_last_tool_slot():
    tool_keys.LAST['EDIT_MESH'] = "builtin.knife"
    try:
        got = _ids(toolbox.maya_tools(_blender_items('EDIT_MESH'), 'EDIT_MESH'))
        assert got[-1] == "builtin.knife" and got[-2] is None, got
        tool_keys.LAST['EDIT_MESH'] = "builtin.move"   # sacred tools never take the slot
        assert _ids(toolbox.maya_tools(_blender_items('EDIT_MESH'), 'EDIT_MESH'))[-1] is None
    finally:
        tool_keys.LAST.clear()


def test_toolbox_falls_back_where_maya_tools_are_missing():
    assert toolbox.maya_tools(_blender_items('PAINT_TEXTURE'), 'PAINT_TEXTURE') is None


def test_only_drawing_is_filtered():
    """wm.tool_set_by_id looks tools up via tools_from_context: outside the toolbar draw every tool
    stays reachable (the shelf's Multi-Cut, Quad Draw, keys)."""
    full = [t.idname for t in toolbox._flat(TOOLBAR.tools_from_context(bpy.context, 'EDIT_MESH'))]
    assert "builtin.knife" in full and "builtin.poly_build" in full
    toolbox._drawing[0] = True
    try:
        drawn = _ids(TOOLBAR.tools_from_context(bpy.context))
    finally:
        toolbox._drawing[0] = False
    assert drawn[:6] == list(toolbox.MAYA_TOOLS), drawn
    # a prepend / append pair around Blender's own toolbar draw
    names = [getattr(f, '__name__', '') for f in TOOLBAR.draw._draw_funcs]
    assert names[0] == '_draw_begin' and names[-1] == '_draw_end', names


def test_is_toolbox_matches_generator():
    import itertools
    from types import SimpleNamespace
    sys.path.insert(0, str(ROOT / "tools"))
    import make_startup
    for flags in itertools.product((False, True), repeat=4):
        space = SimpleNamespace(type='VIEW_3D', show_region_toolbar=flags[0], show_region_header=flags[1],
                                show_region_ui=flags[2], show_object_viewport_mesh=flags[3])
        assert toolbox.is_toolbox(space) == make_startup.is_toolbox_space(space), flags
    assert toolbox.is_toolbox(SimpleNamespace(type='VIEW_3D', show_region_toolbar=True, show_region_header=False,
                                              show_region_ui=False, show_object_viewport_mesh=False))


# --- the viewport sidebar is Blender's again (Maya panels are their own areas) -------------------------

def test_viewport_sidebar_has_no_maya_panel():
    area, regions = _view3d()
    assert dock_tabs._wrapped, "Blender's Tool panels are wrapped (hidden in the Maya dock areas)"
    with bpy.context.temp_override(area=area, region=regions['UI']):
        assert bpy.types.VIEW3D_PT_view3d_properties.poll(bpy.context), "Blender's View tab is not hidden"
        assert not bpy.types.ALLSET_PT_maya_dock.poll(bpy.context), "no Maya panel in the viewport sidebar"
    # a popup of the same panel (Status Line Tool Settings: wm.call_panel) is not hidden
    with bpy.context.temp_override(area=area, region=regions['WINDOW']):
        assert bpy.types.VIEW3D_PT_active_tool.poll(bpy.context)


# --- Help Line + Command Line row ------------------------------------------------------------------

def test_status_bar_is_help_and_command_row():
    assert command_line.draw_status_bar in bpy.types.STATUSBAR_HT_header.draw._draw_funcs   # own draw swapped (115)
    # widths at 1600 px (Help Line 675, Command Line 915) in 20 px units
    assert command_line.HELP_UNITS * 20 == 675 and command_line.COMMAND_UNITS * 20 == 915


# --- Maya Workflow Kit template ------------------------------------------------------------------------------

def test_template_is_maya_general():
    path = ROOT / "src" / "allset" / "app_template" / "Maya_Workflow_Kit" / "startup.blend"
    bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=True)
    screen = bpy.data.workspaces["General"].screens[0]
    areas = list(screen.areas)
    width = max(a.x + a.width for a in areas)
    by = {}
    for a in areas:
        sp = a.spaces.active
        if toolbox.is_toolbox(sp):
            by["toolbox"] = a
        elif a.type == 'VIEW_3D':
            by["view"] = a
        elif a.type == 'IMAGE_EDITOR':
            by["strip"] = a
        else:
            by[a.ui_type] = a
    assert set(by) == {"toolbox", "view", "strip", "OUTLINER", "TIMELINE", "PROPERTIES"}, sorted(by)
    # full-width rows: Status Line + Shelf on top, Time + Range Slider at the bottom
    for key in ("strip", "TIMELINE"):
        assert by[key].x == 0 and by[key].width == width, (key, by[key].x, by[key].width)
    # left to right: Tool Box | Outliner | view | Maya tab stack (its own area)
    assert by["toolbox"].x < by["OUTLINER"].x < by["view"].x < by["PROPERTIES"].x
    assert by["PROPERTIES"].x + by["PROPERTIES"].width == width
    assert maya_dock.role(by["PROPERTIES"]) == 'STACK' and not by["view"].spaces.active.show_region_ui
    tb = by["toolbox"].spaces.active
    assert not any(getattr(tb, n) for n in dir(tb) if n.startswith("show_object_viewport_")), \
        "no object type is visible (clicks under the tools select nothing)"
    # Range Slider = the timeline header, under the Time Slider (WINDOW)
    regions = {r.type: r for r in by["TIMELINE"].regions}
    assert regions['HEADER'].y < regions['WINDOW'].y
    st = by["TIMELINE"].spaces.active
    assert not st.show_region_channels and st.show_region_ui   # sidebar = Time Slider buttons
    assert [a for a in areas if a.type == 'PROPERTIES'] == [by["PROPERTIES"]]


def test_attribute_editor_toggle_uses_dock_without_properties():
    """Run after the template is open: no Properties area, the Status Line AE button switches the dock."""
    wm = bpy.context.window_manager
    screen = bpy.context.window.screen
    assert status_line._properties_area(screen) is None
    wm.allset_dock = 'CHANNEL_BOX'
    assert bpy.ops.allset.editor_toggle(editor='ATTRIBUTE') == {'FINISHED'}
    assert wm.allset_dock == 'ATTRIBUTE_EDITOR'
    assert status_line.editor_shown(screen, "ATTRIBUTE")
