# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Tool Settings: Reset Tool and the dock's Maya sections.

Maya's Tool Settings window has the tool name, Reset Tool / Tool Help above the active tool's options.
The kit's Tool Settings is a dock
left of the viewport (``ui/tool_dock.py``: a Properties editor on its Tool tab) that draws ``ALLSET_PT_tool_settings``:
the head row, then for the Move / Rotate / Scale tools Maya's sections in Maya's order with Maya's rows bound to kit
state (Maya 2022's rows; rows the kit can't do are greyed with a tooltip).
Other tools keep Blender's tool panels under the head row; the Reset Tool row is also prepended to
``VIEW3D_PT_active_tool`` for Blender's own Tool tab / popups.
Reset = the active tool's operator options back to their defaults (every operator of the tool's keymap) and, for
the Move / Rotate / Scale tools, the default tool options like Maya: axis World / Object / Object, the
manipulator at the lead object's pivot, Step Snap off and rotate snap 15
degrees (S3), Smart Duplicate / Smart Extrude at their defaults (Move tool).
"""

import math

import bpy

from .. import results
from ..operators.edge_loops import INSERT_TOOL, OFFSET_TOOL, SLIDE_TOOL
from ..operators.mesh_tools import CREASE_TOOL, TARGET_WELD_TOOL
from ..operators.poly_draw import APPEND_TOOL, CREATE_TOOL
from ..operators.quad_draw import TOOL as QUAD_DRAW_TOOL
from .manipulator import KINDS, SLOT, active_tool

# Default axis per tool, like Maya; the same values tools/make_startup.py writes into the template.
MAYA_AXIS = {'TRANSLATE': 'GLOBAL', 'ROTATE': 'LOCAL', 'RESIZE': 'LOCAL'}
MAYA_PIVOT = 'ACTIVE_ELEMENT'
MAYA_ROTATE_STEP = math.radians(15.0)
# A tool whose keymap name can't be resolved still resets its main operator.
TOOL_OPERATORS = {"builtin.move": ("transform.translate",), "builtin.rotate": ("transform.rotate",),
                  "builtin.scale": ("transform.resize",), "builtin.select_box": ("view3d.select_box",),
                  "builtin.select_lasso": ("view3d.select_lasso",), "builtin.select_circle": ("view3d.select_circle",),
                  "builtin.loop_cut": ("mesh.loopcut_slide",), "builtin.edge_slide": ("transform.edge_slide",)}

# the other tools with Maya Tool Settings sections. Maya tool
# (Maya runTimeCommand) -> Blender tool; sections as in Maya 2022.
TOOLS = {"builtin.select_box": 'SELECT', "builtin.select": 'SELECT',               # SelectTool (Marquee / Tweak)
         "builtin.select_lasso": 'LASSO', "builtin.select_circle": 'PAINT_SELECT',  # LassoTool, ArtPaintSelectTool
         # SplitEdgeRingTool, SlideEdgeTool, the kit tools of ui/mesh_tools_loop.py
         INSERT_TOOL: 'INSERT_EDGE_LOOP', SLIDE_TOOL: 'SLIDE_EDGE', OFFSET_TOOL: 'OFFSET_EDGE_LOOP',
         TARGET_WELD_TOOL: 'TARGET_WELD', CREASE_TOOL: 'CREASE',                    # MergeVertexTool, PolyCreaseTool
         # the kit's QuadDrawTool / CreatePolygonTool / AppendToPolygonTool (ui/mesh_tools_poly.py)
         QUAD_DRAW_TOOL: 'QUAD_DRAW', CREATE_TOOL: 'CREATE_POLYGON', APPEND_TOOL: 'APPEND_POLYGON'}
POLY_KINDS = ('QUAD_DRAW', 'CREATE_POLYGON', 'APPEND_POLYGON')
LOOP_KINDS = ('INSERT_EDGE_LOOP', 'OFFSET_EDGE_LOOP', 'SLIDE_EDGE')     # kit edge loop tools
_LOOP_SETTINGS = {'INSERT_EDGE_LOOP': 'INSERT', 'OFFSET_EDGE_LOOP': 'OFFSET', 'SLIDE_EDGE': 'SLIDE'}
KIND_OF = {**KINDS, **TOOLS}
MANIP = ('TRANSLATE', 'ROTATE', 'RESIZE')


def tool_operators(context, tool):
    """Operator idnames of the tool's keymap (``ToolDef.keymap``), else ``TOOL_OPERATORS``."""
    ids = list(TOOL_OPERATORS.get(tool.idname, ()))
    try:
        from bl_ui.space_toolsystem_common import ToolSelectPanelHelper
        cls = ToolSelectPanelHelper._tool_class_from_space_type('VIEW_3D')
        item, _index = cls._tool_get_by_id(context, tool.idname)
    except (AttributeError, TypeError):
        item = None
    names = getattr(item, "keymap", None) or ()
    # the merged keymaps (user = active keyconfig + add-on items: the Maya items live in the add-on one)
    keymaps = context.window_manager.keyconfigs.user.keymaps if context.window_manager.keyconfigs.user else {}
    for name in names if isinstance(names, (tuple, list)) else ():
        km = keymaps.get(name) if isinstance(name, str) else None
        for kmi in (km.keymap_items if km else ()):
            if kmi.idname not in ids:
                ids.append(kmi.idname)
    return ids


def reset_operator_properties(props):
    """Unset every option: the operator uses its defaults again. Returns how many were set."""
    n = 0
    for prop in props.bl_rna.properties:
        name = prop.identifier
        if name == "rna_type" or prop.is_readonly:
            continue
        if props.is_property_set(name):
            props.property_unset(name)
            n += 1
    return n


def reset_maya_options(context, kind):
    """Default options of the Move / Rotate / Scale tool, like Maya."""
    from ..operators import snap_align
    scene = context.scene
    ts = scene.tool_settings
    scene.transform_orientation_slots[SLOT[kind]].type = MAYA_AXIS[kind]
    ts.transform_pivot_point = MAYA_PIVOT
    snap_align.set_step_snap(ts, kind, 'OFF')
    if kind == 'ROTATE':
        ts.snap_angle_increment_3d = MAYA_ROTATE_STEP
    if kind == 'RESIZE':
        from .. import preferences
        preferences.get(context).prevent_negative_scale = True
    if kind == 'TRANSLATE':
        from .. import preferences
        prefs = preferences.get(context)
        prefs.transform_constraint = 'NONE'
        for name in ("smart_duplicate", "smart_extrude"):
            setattr(prefs, name, prefs.bl_rna.properties[name].default)


def reset_tool(context):
    """Reset the active tool. Returns (tool idname, number of operator options unset) or None without a tool."""
    tool = active_tool(context)
    if tool is None:
        return None
    n = 0
    for idname in tool_operators(context, tool):
        try:
            props = tool.operator_properties(idname)
        except (RuntimeError, TypeError, ValueError):
            continue
        n += reset_operator_properties(props)
    kind = KIND_OF.get(tool.idname)
    if kind in MANIP:
        reset_maya_options(context, kind)
    elif kind is not None:
        reset_kind_defaults(context, kind, tool)
    from ..operators import multi_cut
    if tool.idname == multi_cut.TOOL:       # Multi-Cut keeps its Maya options on the scene
        multi_cut.reset_settings(multi_cut.mesh_tools.settings(context))
    return tool.idname, n


def reset_kind_defaults(context, kind, tool=None):
    """Default values like Maya where they differ from the Blender tool's defaults:
    Paint Selection = Select + Add to current selection; Target Weld = Target, Preserve UVs on; Crease = Absolute."""
    if kind == 'PAINT_SELECT':
        _paint_add[0] = True
        props = _op_props(tool or active_tool(context), "view3d.select_circle")
        if props is not None:
            props.mode = 'ADD'
    elif kind in POLY_KINDS:
        from ..operators import poly_draw
        poly_draw.reset_settings(poly_draw.settings(context), {'QUAD_DRAW': 'QUAD_DRAW', 'CREATE_POLYGON': 'CREATE',
                                                              'APPEND_POLYGON': 'APPEND'}[kind])
    elif kind in LOOP_KINDS:
        from ..operators import edge_loops
        edge_loops.reset_settings(edge_loops.settings(context), _LOOP_SETTINGS[kind])
    elif kind in ('TARGET_WELD', 'CREASE'):
        from ..operators import mesh_tools
        s = mesh_tools.settings(context)
        for name in (("weld_merge_to", "weld_preserve_uvs") if kind == 'TARGET_WELD' else ("crease_mode",)):
            setattr(s, name, s.bl_rna.properties[name].default)


def _op_props(tool, idname):
    if tool is None:
        return None
    try:
        return tool.operator_properties(idname)
    except (RuntimeError, TypeError, ValueError, KeyError):
        return None


class ALLSET_OT_reset_tool(bpy.types.Operator):
    """Put the active tool's options back to their defaults (Maya Tool Settings: Reset Tool)"""
    bl_idname = "allset.reset_tool"
    bl_label = "Reset Tool"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return active_tool(context) is not None

    def execute(self, context):
        got = reset_tool(context)
        if got is None:
            return {'CANCELLED'}
        results.result(self, f"Reset {got[0].split('.')[-1].replace('_', ' ').title()} tool")
        for area in context.screen.areas if context.screen else ():
            area.tag_redraw()
        return {'FINISHED'}


def draw_reset_row(self, context):
    """Prepended to the active tool panel: Maya's Reset Tool button above the tool's options (not in the Tool
    Settings dock, whose own head row has it)."""
    if active_tool(context) is None or in_dock(context):
        return
    self.layout.operator(ALLSET_OT_reset_tool.bl_idname, icon='LOOP_BACK')


# --- Tool Settings dock: Maya sections -------------------------------------------------------------
# Section order, default open state and rows as in Maya 2022 (Move / Rotate / Scale Tool Settings).
# Rows without kit state are greyed with a tooltip (TS_NOTICES).

TOOL_NAMES = {'TRANSLATE': "Move Tool", 'ROTATE': "Rotate Tool", 'RESIZE': "Scale Tool",
              # Maya 2022 Tool Settings titles
              'SELECT': "Select Tool", 'LASSO': "Lasso Tool", 'PAINT_SELECT': "Paint Selection Tool",
              'INSERT_EDGE_LOOP': "Insert Edge Loop Tool", 'SLIDE_EDGE': "Slide Edge Tool",
              'TARGET_WELD': "Target Weld Tool", 'CREASE': "Crease Tool", 'QUAD_DRAW': "Quad Draw Tool",
              # Maya 2022 Tool Settings titles
              'CREATE_POLYGON': "Create Polygon Tool", 'APPEND_POLYGON': "Append To Polygon Tool",
              'OFFSET_EDGE_LOOP': "Offset Edge Loop Tool"}
SETTINGS = {'TRANSLATE': "Move Settings", 'ROTATE': "Rotate Settings", 'RESIZE': "Scale Settings"}
SELECTING = ('SELECT', 'LASSO')
# (key, title, open by default: True / False / the kinds where it starts open, kinds that have it). One order for
# every tool (Maya's order within each tool: ts106 / ts129 widget y).
SECTIONS = (
    ("settings", None, True, MANIP),
    ("joint_orient", "Joint Orient Settings", False, ('TRANSLATE',)),
    ("move_snap", "Move Snap Settings", False, ('TRANSLATE',)),
    ("lasso", "Lasso Settings", True, ('LASSO',)),
    ("brush", "Brush", True, ('PAINT_SELECT',)),
    ("paint_ops", "Paint Operations", True, ('PAINT_SELECT',)),
    ("stroke", "Stroke", False, ('PAINT_SELECT',)),
    ("stylus", "Stylus Pressure", False, ('PAINT_SELECT',)),
    ("attr_maps", "Attribute Maps", False, ('PAINT_SELECT',)),
    ("paint_display", "Display", False, ('PAINT_SELECT',)),
    ("description", "Description", True, (*LOOP_KINDS, 'TARGET_WELD', 'CREASE', 'CREATE_POLYGON', 'APPEND_POLYGON')),
    ("tool", "Settings", True, (*LOOP_KINDS, 'TARGET_WELD', 'CREASE', *POLY_KINDS)),
    ("slide_snap", "Snapping Settings", True, ('SLIDE_EDGE',)),
    ("live", "Live Constraint Options", False, ('QUAD_DRAW',)),
    ("shortcuts", "Keyboard/Mouse Shortcuts", False, ('TARGET_WELD', *POLY_KINDS)),
    ("selection", "Common Selection Options", ('SELECT',), (*MANIP, 'SELECT')),
    ("soft", "Soft Selection", False, (*MANIP, *SELECTING)),
    ("symmetry", "Symmetry Settings", False, (*MANIP, *SELECTING)),
    ("smart_duplicate", "Smart Duplicate Settings", False, MANIP),
)
# Maya Rotate / Scale Center (rotate_ts / scale_ts) -> Blender pivot point (Default = the manipulator at
# the lead's pivot, the kit's default MAYA_PIVOT like Maya; Object = each object's own pivot; Manip = where the component
# pivot edit put the manipulator, the 3D cursor; Selection = the selection's centre).
CENTERS = {'ROTATE': (("Default", 'ACTIVE_ELEMENT'), ("Object", 'INDIVIDUAL_ORIGINS'), ("Manip", 'CURSOR'),
                      ("Selection", 'BOUNDING_BOX_CENTER')),
           'RESIZE': (("Default", 'ACTIVE_ELEMENT'), ("Object", 'INDIVIDUAL_ORIGINS'), ("Manip", 'CURSOR'))}

TS = "Tool Settings"
TS_NOTICES = {
    f"{TS}/Tool Help": ("Blender's tool tooltips", "Hover a tool for its help; Blender's manual is under Help"),
    f"{TS}/Bake Pivot Orientation": ("Modify > Bake Pivot",
                                     "The kit keeps a turned pivot as the Maya Pivot orientation; bake it from the menu"),
    f"{TS}/Show Orientation Handle": ("always shown", "The kit's pivot edit always shows its orientation ring"),
    f"{TS}/Transform Constraint": ("the Move tool's Transform Constraint",
                                   "Edge / Surface slide works with the Move tool; rotate and scale stay free"),
    f"{TS}/Tweak Mode": ("the Tweak select tool",
                         "Blender's Tweak tool (Q) drags the component under the mouse without selecting it first"),
    f"{TS}/Automatically Orient Joints": ("Skeleton > Orient Joint",
                                          "Bones are not re-oriented while they move; orient them afterwards"),
    f"{TS}/Retain component spacing": ("always on", "Blender snapping always keeps the selection's spacing"),
    f"{TS}/Snap to live polygon": ("Make Live", "Blender snaps to the live surface with the Face snap"),
    f"{TS}/Drag": ("Paint Selection Tool",
                   "Blender's drag-to-paint selection is the Paint Selection Tool (Tool Box), not a style of this tool"),
    f"{TS}/Automatic camera-based selection": ("Camera-based selection",
                                               "Turn camera-based selection on or off yourself"),
    f"{TS}/Highlight backfaces": ("X-ray (Alt+Z)", "Blender highlights only what it can select"),
    f"{TS}/Highlight affected": ("Soft Select falloff circle", "Blender draws the soft selection radius, not colours"),
    f"{TS}/Selection Constraint": ("Select > Select Loops / Linked", "No selection constraint in Blender"),
    f"{TS}/Geometry Type": ("Copy", "Shift+drag always makes a copy (Duplicate Special makes instances)"),
    f"{TS}/Modify Translation": ("off", "Blender's rotate never moves the objects' positions"),
    f"{TS}/Free Rotate": ("the white ring / trackball",
                          "Blender's rotate manipulator has the free trackball rotation built in"),
}
# greyed rows of the other tools (Maya 2022 rows) -> (substitute, one line).
_SPACE = "Blender's selection tools work in screen space"
TS_NOTICES.update({f"{TS}/{k}": v for k, v in {
    "Lasso/Open": ("Closed lasso", "Blender's lasso always closes the shape from the last point to the first"),
    "Lasso/Accurate": ("screen position", "Blender's lasso picks components by their screen position"),
    "Lasso/Fast": ("screen position", "Blender's lasso picks components by their screen position"),
    "Paint/Radius(L)": ("one radius", "Blender's paint selection has one radius, no lower stylus radius"),
    "Paint/Profile": ("hard circle", "Blender's paint selection brush is a hard circle"),
    "Paint/Rotate to stroke": ("round brush", "The round brush has no direction to rotate"),
    "Paint/Toggle": ("Ctrl+click", "Blender's paint selection can only select or unselect; toggle with Ctrl+click"),
    "Paint/Screen projection": ("always on", _SPACE),
    "Paint/Reflection": ("Mesh Symmetry", "Blender's paint selection doesn't mirror; select the other side too"),
    "Paint/Stamp spacing": ("continuous", "Blender's paint selection selects along the whole stroke"),
    "Paint/Stroke commands": ("Script Editor", "Blender's brush runs no MEL commands before or after a stroke"),
    "Paint/Stylus pressure": ("no pressure", "Blender's paint selection ignores tablet pressure"),
    "Paint/Attribute Maps": ("no attribute maps", "Blender can't paint a selection into or out of an image"),
    "Paint/Draw brush": ("always drawn", "Blender always draws the paint selection circle"),
    "Insert Edge Loop/Use Equal Multiplier": ("always on", "Several new loops are always evenly spaced"),
    "Insert Edge Loop/Auto complete": ("always on", "The new loop always runs around the whole edge ring"),
    "Insert Edge Loop/Fix Quads": ("Edit Mesh > Connect", "The new loop stops where the ring isn't quads"),
    "Target Weld/MMB": ("Merge To: Center", "Middle-drag isn't bound: set Merge To to Center and drag with the left button"),
    "Crease/Extend to creased components": ("Select Similar",
                                            "Select the creased edges with Select > Select Similar > Crease first"),
}.items()})


def in_dock(context):
    """A Properties Tool tab that isn't a Maya panel's dock area (ui/maya_dock.py)."""
    space = getattr(context, "space_data", None)
    if space is None or space.type != 'PROPERTIES':
        return False
    from . import hypershade, marked_window, maya_dock, reference_editor
    return (maya_dock.area_role(context) is None and hypershade.context_pane(context) is None
            and not reference_editor.context_pane(context) and marked_window.context_kind(context) is None)


def tool_kind(context):
    """The active tool's kind when it has Maya sections ('TRANSLATE' / 'ROTATE' / 'RESIZE' and the other kinds of
    ``TOOLS``), else None (Blender's tool panels are drawn)."""
    tool = active_tool(context)
    return KIND_OF.get(tool.idname) if tool is not None else None


def tool_label(context, tool):
    """(label, icon_value) of a tool as its toolbar button shows it."""
    kind = KIND_OF.get(tool.idname)
    try:
        from bl_ui.space_toolsystem_common import ToolSelectPanelHelper
        cls = ToolSelectPanelHelper._tool_class_from_space_type('VIEW_3D')
        item, _index = cls._tool_get_by_id(context, tool.idname)
        icon = ToolSelectPanelHelper._icon_value_from_icon_handle(item.icon) if item and item.icon else 0
        label = item.label if item else ""
    except (AttributeError, TypeError):
        label, icon = "", 0
    if kind is not None:
        label = TOOL_NAMES[kind]
    elif label and not label.endswith("Tool"):
        label += " Tool"
    return label or tool.idname.split(".")[-1].replace("_", " ").title(), icon


def _grey(layout, item, text="", check=None, icon=None):
    """A Maya row the kit can't do: shown greyed, its tooltip says why (TS_NOTICES)."""
    row = layout.row(align=True)
    row.enabled = False
    flat = check is not None or icon is not None
    if flat:
        row.alignment = 'LEFT'          # Maya check boxes: box and text from the left
    if icon is None:
        icon = 'NONE' if check is None else ('CHECKBOX_HLT' if check else 'CHECKBOX_DEHLT')
    row.operator("allset.menu_unavailable", text=text or item, icon=icon, emboss=not flat).item = f"{TS}/{item}"
    return row


def _labelled(layout, label):
    """Maya's label column (right-aligned text, then the control)."""
    split = layout.split(factor=0.42, align=True)
    left = split.row()
    left.alignment = 'RIGHT'
    left.label(text=label)
    return split.row(align=True)


def _check_op(layout, op, text, on, **props):
    row = layout.row(align=True)
    row.alignment = 'LEFT'
    o = row.operator(op, text=text, icon='CHECKBOX_HLT' if on else 'CHECKBOX_DEHLT', emboss=False)
    for k, v in props.items():
        setattr(o, k, v)
    return o


def draw_head(layout, context, tool):
    """Maya's Tool Settings head: tool icon + name, Reset Tool, Tool Help."""
    label, icon = tool_label(context, tool)
    row = layout.row(align=True)
    name = row.row()
    if icon:
        name.label(text=label, icon_value=icon)
    else:
        name.label(text=label)
    btn = row.row(align=True)
    btn.operator(ALLSET_OT_reset_tool.bl_idname, text="Reset Tool")
    _grey(btn, "Tool Help")


def draw_settings(layout, context, kind):
    """Move / Rotate / Scale Settings (Maya's rows)."""
    from ..operators import pivot_menu, snap_align
    scene = context.scene
    ts = scene.tool_settings
    _labelled(layout, "Axis Orientation:").prop(scene.transform_orientation_slots[SLOT[kind]], "type", text="")
    layout.separator(factor=0.5)
    row = _labelled(layout, "Pivot:")
    editing = pivot_menu.pivot_editing(context)
    row.operator("allset.pivot_toggle", text="Edit Pivot", depress=editing)
    row.operator("allset.pivot_reset", text="Reset")
    col = _labelled(layout, "").column(align=True)
    for option, text in (("SNAP_POS", "Position"), ("SNAP_ORI", "Orientation"), ("PIN", "Pin Component Pivot")):
        _check_op(col, "allset.pivot_option", text, pivot_menu.option(option, context), option=option)
    _grey(col, "Bake Pivot Orientation", check=False)
    _grey(col, "Show Orientation Handle", check=True)
    if kind in CENTERS:
        row = _labelled(layout, "Rotate Center:" if kind == 'ROTATE' else "Scale Center:")
        grid = row.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
        for text, value in CENTERS[kind]:
            op = grid.operator("wm.context_set_enum", text=text, depress=ts.transform_pivot_point == value)
            op.data_path, op.value = "scene.tool_settings.transform_pivot_point", value
        if kind == 'ROTATE':
            _grey(_labelled(layout, ""), "Modify Translation", check=False)
    layout.separator(factor=0.5)
    row = _labelled(layout, "Transform Constraint:")
    if kind == 'TRANSLATE':
        from .. import preferences
        row.enabled = context.mode == 'EDIT_MESH'
        row.prop(preferences.get(context), "transform_constraint", text="")
    else:
        _grey(row, "Transform Constraint", text="Off")
    row = _labelled(layout, "Step Snap:")
    mode = snap_align.step_snap_mode(ts, kind)
    for m in ('OFF', 'RELATIVE', 'ABSOLUTE'):
        cell = row.row(align=True)
        # Move offers Absolute only with World axes (like Maya)
        cell.enabled = m != 'ABSOLUTE' or snap_align.absolute_offered(scene, kind)
        op = cell.operator("allset.step_snap", text=m.title(), depress=mode == m)
        op.kind, op.mode = kind, m
    if kind == 'ROTATE':
        _labelled(layout, "").prop(ts, "snap_angle_increment_3d", text="Step")
    elif kind == 'RESIZE':
        _labelled(layout, "").label(text="Step: 0.1")
    else:
        # Blender's increment is the grid step: 1 Maya unit in the Maya Workflow Kit template.
        _labelled(layout, "").label(text="Step: one grid unit", icon='SNAP_INCREMENT')
    _labelled(layout, "Preserve Children:").prop(ts, "use_transform_skip_children", text="")
    _labelled(layout, "Preserve UVs:").prop(ts, "use_transform_correct_face_attributes", text="")
    _grey(_labelled(layout, "Tweak Mode:"), "Tweak Mode", text=" ", check=False)
    if kind == 'ROTATE':
        _grey(_labelled(layout, "Free Rotate:"), "Free Rotate", text=" ", check=True)
    if kind == 'RESIZE':
        from .. import preferences
        row = layout.row()
        row.enabled = context.mode == 'EDIT_MESH'
        row.prop(preferences.get(context), 'prevent_negative_scale')


def draw_selection(layout, context):
    """Common Selection Options (Marquee / Drag, camera-based selection, highlights, selection constraint)."""
    wm = context.window_manager
    row = _labelled(layout, "Selection Style:")
    row.label(text="Marquee", icon='RADIOBUT_ON')
    _labelled(layout, "").prop(wm, "allset_mtk_camera_based", text="Camera-based selection")
    _grey(_labelled(layout, ""), "Drag", icon='RADIOBUT_OFF')
    col = _labelled(layout, "").column(align=True)
    _grey(col, "Automatic camera-based selection", check=False)
    _grey(col, "Highlight backfaces", check=True)
    col.prop(wm, "allset_mtk_nearest", text="Highlight nearest component")
    _grey(col, "Highlight affected", check=False)
    _grey(_labelled(layout, "Selection Constraint:"), "Selection Constraint", text="Off")


def draw_symmetry_section(layout, context):
    from .status_line import draw_symmetry
    row = _labelled(layout, "Symmetry:")
    draw_symmetry(row, context)
    row.operator("allset.symmetry", text="Reset").mode = "OFF"


def draw_smart_duplicate(layout, context):
    from .. import preferences
    prefs = preferences.get(context)
    col = _labelled(layout, "").column(align=True)
    col.prop(prefs, "smart_extrude", text="Shift+Drag to Extrude Components")
    col.prop(prefs, "smart_duplicate", text="Shift+Drag to Duplicate Objects")
    _grey(_labelled(layout, "Geometry Type:"), "Geometry Type", text="Copy")


def draw_section(layout, context, key, kind):
    if key == "settings":
        draw_settings(layout, context, kind)
    elif key == "joint_orient":
        _grey(layout, "Automatically Orient Joints", check=False)
    elif key == "move_snap":
        _grey(_labelled(layout, ""), "Retain component spacing", check=True)
        _grey(_labelled(layout, "Snap to live polygon:"), "Snap to live polygon", text="Face center", check=False)
    elif key == "selection":
        draw_selection(layout, context)
    elif key == "soft":
        from .modeling_toolkit import draw_soft
        draw_soft(layout, context)
    elif key == "symmetry":
        draw_symmetry_section(layout, context)
    elif key == "smart_duplicate":
        draw_smart_duplicate(layout, context)
    elif key in OTHER_SECTIONS:
        OTHER_SECTIONS[key](layout, context, kind)


# --- the other tools' sections -------

def _radio(layout, text, on, option, value):
    """A Maya radio button bound through allset.ts_option."""
    op = layout.operator(ALLSET_OT_ts_option.bl_idname, text=text, icon='RADIOBUT_ON' if on else 'RADIOBUT_OFF',
                         emboss=False)
    op.option, op.value = option, value
    return op


def _fixed(layout, text, on=True):
    """A Maya radio / check value Blender always has: drawn set, not clickable."""
    row = layout.row()
    row.alignment = 'LEFT'
    row.label(text=text, icon='RADIOBUT_ON' if on else 'RADIOBUT_OFF')


def _lines(layout, *lines):
    col = layout.column(align=True)
    for line in lines:
        col.label(text=line)


def draw_lasso(layout, context, kind):
    """Lasso Settings: Draw style Closed (Open greyed), Component selection (greyed; Fast by default, like Maya)."""
    row = _labelled(layout, "Draw style:")
    _grey(row, "Lasso/Open", text="Open", icon='RADIOBUT_OFF')
    _fixed(row, "Closed")
    row = _labelled(layout, "Component selection:")
    _grey(row, "Lasso/Accurate", text="Accurate", icon='RADIOBUT_OFF')
    _grey(row, "Lasso/Fast", text="Fast", icon='RADIOBUT_ON')


def _circle_props(context):
    return _op_props(active_tool(context), "view3d.select_circle")


def draw_brush(layout, context, kind):
    """Brush: Radius(U) = Blender's circle radius (pixels), the rest greyed."""
    from . import notices
    props = _circle_props(context)
    row = _labelled(layout, "Radius(U):")
    if props is not None:
        row.prop(props, "radius", text="")
    notices.tip(row, "Maya's radius is in scene units, Blender's paint selection in screen pixels")
    _grey(_labelled(layout, "Radius(L):"), "Paint/Radius(L)", text="0.0010")
    _grey(_labelled(layout, "Profile:"), "Paint/Profile", text="Soft")
    _grey(_labelled(layout, ""), "Paint/Rotate to stroke", text="Rotate to stroke", check=True)


def paint_operation(props):
    """'SELECT' / 'UNSELECT' from Blender's circle select mode (Maya Paint operation)."""
    return 'UNSELECT' if props is not None and props.mode == 'SUB' else 'SELECT'


def draw_paint_ops(layout, context, kind):
    """Paint Operations: Select / Unselect (+ Add to current selection) = Blender's select mode, Select All /
    Unselect All / Toggle All."""
    props = _circle_props(context)
    op = paint_operation(props)
    row = _labelled(layout, "Paint operation:")
    _radio(row, "Select", op == 'SELECT', "paint_op", "SELECT")
    _radio(row, "Unselect", op == 'UNSELECT', "paint_op", "UNSELECT")
    _grey(_labelled(layout, ""), "Paint/Toggle", text="Toggle", icon='RADIOBUT_OFF')
    sub = _labelled(layout, "").row()
    sub.active = op == 'SELECT'
    _check_op(sub, ALLSET_OT_ts_option.bl_idname, "Add to current selection",
              props is not None and props.mode == 'ADD', option="paint_add", value="")
    row = layout.row(align=True)
    for text, value in (("Select All", 'SELECT'), ("Unselect All", 'DESELECT'), ("Toggle All", 'INVERT')):
        o = row.operator(ALLSET_OT_ts_option.bl_idname, text=text)
        o.option, o.value = "select_all", value


def draw_stroke(layout, context, kind):
    col = _labelled(layout, "").column(align=True)
    _grey(col, "Paint/Screen projection", text="Screen projection", check=True)
    _grey(col, "Paint/Reflection", text="Reflection", check=False)
    _grey(_labelled(layout, "Stamp spacing:"), "Paint/Stamp spacing", text="0.100")
    _grey(_labelled(layout, "Before / after stroke:"), "Paint/Stroke commands", text="-")


def draw_stylus(layout, context, kind):
    _grey(_labelled(layout, ""), "Paint/Stylus pressure", text="Stylus pressure", check=False)


def draw_attr_maps(layout, context, kind):
    _grey(_labelled(layout, "Map name:"), "Paint/Attribute Maps", text="Import... / Export...")


def draw_paint_display(layout, context, kind):
    _grey(_labelled(layout, ""), "Paint/Draw brush", text="Draw brush", check=True)


DESCRIPTIONS = {   # the kit's own words for what the tool does here
    'INSERT_EDGE_LOOP': ("Click an edge and drag to place a new edge loop",
                         "across the edge ring."),
    'SLIDE_EDGE': ("Select an edge loop or path, then drag", "to slide it along the neighbouring edges."),
    'TARGET_WELD': ("Drag a vertex or edge onto the target.", "The selected vertices or edges are merged."),
    'CREASE': ("Crease edges / vertices between hard and smooth:", "select them, then middle-drag left / right."),
}


def draw_description(layout, context, kind):
    if kind in POLY_KINDS:
        from . import mesh_tools_poly
        mesh_tools_poly.draw_description(layout, kind)
        return
    if kind in LOOP_KINDS:
        from . import mesh_tools_loop
        mesh_tools_loop.draw_description(layout, kind)
        return
    _lines(layout, *DESCRIPTIONS.get(kind, ()))


def edge_loop_position(context):
    """Maya Insert Edge Loop "Maintain position" of the kit tool (Scene.allset_loop_tools)."""
    from ..operators import edge_loops
    return edge_loops.settings(context).iel_position


MAYA_EDGE_LOOPS = 2     # Maya Number of edge loops (ts129 insert_edge_loop)


def set_edge_loop_position(context, value):
    from ..operators import edge_loops
    if value not in {k for k, _n, _d in edge_loops.INSERT_POSITIONS}:
        return False
    edge_loops.settings(context).iel_position = value
    return True


def _draw_loop(kind):
    def draw(layout, context):     # the kit loop tools' Maya fields (ui/mesh_tools_loop.py)
        from . import mesh_tools_loop as mtl
        {'INSERT_EDGE_LOOP': mtl.draw_insert, 'OFFSET_EDGE_LOOP': mtl.draw_offset,
         'SLIDE_EDGE': mtl.draw_slide}[kind](layout, context)
    return draw


def _draw_target_weld(layout, context):
    from ..operators import mesh_tools
    s = mesh_tools.settings(context)
    _labelled(layout, "Merge To:").prop(s, "weld_merge_to", expand=True)
    _labelled(layout, "Preserve UVs:").prop(s, "weld_preserve_uvs", text="")


def _draw_crease(layout, context):
    from ..operators import mesh_tools
    _labelled(layout, "Mode:").prop(mesh_tools.settings(context), "crease_mode", expand=True)
    _grey(_labelled(layout, "Selection:"), "Crease/Extend to creased components",
          text="Extend to creased components", check=False)


def _draw_poly(kind):
    def draw(layout, context):     # the kit tools' Maya fields (ui/mesh_tools_poly.py)
        from . import mesh_tools_poly as mtp
        {'QUAD_DRAW': mtp.draw_quad_draw, 'CREATE_POLYGON': mtp.draw_create,
         'APPEND_POLYGON': mtp.draw_append}[kind](layout, context)
    return draw


def draw_tool(layout, context, kind):
    {'TARGET_WELD': _draw_target_weld, 'CREASE': _draw_crease, **{k: _draw_loop(k) for k in LOOP_KINDS},
     **{k: _draw_poly(k) for k in POLY_KINDS}}[kind](layout, context)


def draw_slide_snap(layout, context, kind):
    from . import mesh_tools_loop
    mesh_tools_loop.draw_slide_snap(layout, context)


def draw_live(layout, context, kind):
    from . import mesh_tools_poly
    mesh_tools_poly.draw_live(layout, context)


def keymap_rows(context, name):
    """[(keys, operator name)] of a tool keymap as Blender uses it (the user keyconfig = active keyconfig + add-on
    items, where the Maya items are; empty in -b)."""
    kc = context.window_manager.keyconfigs.user
    km = kc.keymaps.get(name) if kc is not None else None
    out = []
    for kmi in (km.keymap_items if km is not None else ()):
        if not kmi.active:
            continue
        try:
            label = getattr(getattr(bpy.ops, kmi.idname.split(".")[0]), kmi.idname.split(".")[1]).get_rna_type().name
        except (AttributeError, IndexError, KeyError):
            label = kmi.idname
        out.append((kmi.to_string(), label))
    return out


def draw_shortcuts(layout, context, kind):
    if kind == 'TARGET_WELD':
        split = layout.split(factor=0.42)
        split.label(text="LMB")
        split.label(text="Drag to merge components")
        _grey(layout, "Target Weld/MMB", text="MMB: drag to merge components to center")
        return
    from . import mesh_tools_poly as mtp
    mtp.draw_shortcuts(layout, {'QUAD_DRAW': mtp.QUAD_DRAW_SHORTCUTS, 'CREATE_POLYGON': mtp.CREATE_SHORTCUTS,
                                'APPEND_POLYGON': mtp.APPEND_SHORTCUTS}[kind])


OTHER_SECTIONS = {"lasso": draw_lasso, "brush": draw_brush, "paint_ops": draw_paint_ops, "stroke": draw_stroke,
                  "stylus": draw_stylus, "attr_maps": draw_attr_maps, "paint_display": draw_paint_display,
                  "description": draw_description, "tool": draw_tool, "slide_snap": draw_slide_snap,
                  "live": draw_live, "shortcuts": draw_shortcuts}

_paint_add = [True]    # Maya "Add to current selection" kept while Unselect is picked (factory: on)


def _select_all(context, action):
    if context.mode == 'EDIT_MESH':
        return bpy.ops.mesh.select_all(action=action)
    if context.mode == 'OBJECT':
        return bpy.ops.object.select_all(action=action)
    return {'CANCELLED'}


def apply_option(context, option, value):
    """Set a Maya Tool Settings value on Blender's tool properties. True when it applied."""
    tool = active_tool(context)
    if option in ("paint_op", "paint_add"):
        props = _op_props(tool, "view3d.select_circle")
        if props is None:
            return False
        if option == "paint_add":
            if props.mode == 'SUB':
                return False
            _paint_add[0] = props.mode != 'ADD'
            props.mode = 'ADD' if _paint_add[0] else 'SET'
        elif value == 'UNSELECT':
            props.mode = 'SUB'
        else:
            props.mode = 'ADD' if _paint_add[0] else 'SET'
        return True
    if option == "select_all":
        return 'FINISHED' in _select_all(context, value)
    if option == "iel_position":
        return set_edge_loop_position(context, value)
    if option == "slide_mode":
        from ..operators import edge_loops
        edge_loops.settings(context).slide_mode = 'ABSOLUTE' if value == 'ABSOLUTE' else 'RELATIVE'
        return True
    return False


class ALLSET_OT_ts_option(bpy.types.Operator):
    """Set this Maya tool option"""
    bl_idname = "allset.ts_option"
    bl_label = "Tool Option"
    bl_options = {'INTERNAL', 'UNDO'}

    option: bpy.props.StringProperty(options={'SKIP_SAVE'})
    value: bpy.props.StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        if not apply_option(context, self.option, self.value):
            return {'CANCELLED'}
        for area in context.screen.areas if context.screen else ():
            area.tag_redraw()
        return {'FINISHED'}


def sections(kind):
    """[(key, title, open)] of the tool kind, in Maya's order."""
    return [(key, title or SETTINGS[kind], is_open if isinstance(is_open, bool) else kind in is_open)
            for key, title, is_open, kinds in SECTIONS if kind in kinds]


def draw_dock(layout, context):
    from . import paint_weights
    if paint_weights.active(context):
        paint_weights.draw(layout, context)
        return
    tool = active_tool(context)
    if tool is None:
        layout.label(text="No tool settings in this mode")
        return
    draw_head(layout, context, tool)
    kind = KIND_OF.get(tool.idname)
    if kind is None:
        return    # Blender's own tool panels follow (dock_tabs hides them only for tools with Maya sections)
    for key, title, is_open in sections(kind):
        header, body = layout.panel(f"allset_ts_{kind.lower()}_{key}", default_closed=not is_open)
        header.label(text=title)
        if body is not None:
            draw_section(body.column(), context, key, kind)


class ALLSET_PT_tool_settings(bpy.types.Panel):
    """Maya Tool Settings (the Properties Tool tab of the dock)"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"
    bl_label = "Tool Settings"
    bl_options = {'HIDE_HEADER'}
    bl_order = -100

    @classmethod
    def poll(cls, context):
        return in_dock(context)    # never in a 3D View sidebar (the Maya dock there is the Channel Box / AE)

    def draw(self, context):
        from . import maya_dock, tool_dock
        if tool_dock.is_dock(context.area):     # the kit's dock (not a user's Properties editor): Maya's handle
            maya_dock.draw_handle(self.layout)
        draw_dock(self.layout, context)


def hides_blender_panels(context):
    """True in the Tool Settings dock while the Maya sections replace Blender's tool panels (dock_tabs)."""
    return in_dock(context) and (context.mode == 'PAINT_WEIGHT' or tool_kind(context) is not None)


classes = (ALLSET_OT_reset_tool, ALLSET_OT_ts_option, ALLSET_PT_tool_settings)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_PT_active_tool.prepend(draw_reset_row)
    from . import notices
    notices.PANEL_NOTICES.update(TS_NOTICES)


def unregister():
    from . import notices
    for key in TS_NOTICES:
        notices.PANEL_NOTICES.pop(key, None)
    bpy.types.VIEW3D_PT_active_tool.remove(draw_reset_row)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
