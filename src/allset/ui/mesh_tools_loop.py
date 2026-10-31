# SPDX-License-Identifier: GPL-3.0-or-later
"""Insert Edge Loop, Offset Edge Loop and Slide Edge as kit tools (GitHub #31).

The tools run the modals of operators/edge_loops.py; their Maya Tool Settings (fields and factory values)
are drawn here, in Blender's tool header and in the kit's Tool Settings dock (ui/tool_settings.py
kinds INSERT_EDGE_LOOP / OFFSET_EDGE_LOOP / SLIDE_EDGE). The left button keeps Blender's selection where it
doesn't hit an edge (KEYMAP_FALLBACK), like Maya's tools that select with a click.
"""

import bpy

from . import notices
from ..operators import edge_loops

# Maya rows the kit can't honour -> (substitute, one line); keys are "Tool Settings/<tool>/<row>" (Insert Edge Loop's
# greyed rows are in ui/tool_settings.TS_NOTICES)
TS = "Tool Settings"
GREY = {
    f"{TS}/Offset Edge Loop/Start/End vertex offset": ("0", "The loop ends stay at their vertices"),
    f"{TS}/Offset Edge Loop/Press enter": ("Automatically", "The loops are made when you release the mouse"),
}

DESCRIPTIONS = {   # Maya's Description section, the kit's words
    'INSERT_EDGE_LOOP': ("To create a new path of edges across a mesh,", "click an edge and drag."),
    'OFFSET_EDGE_LOOP': ("To insert edge loops on both sides of an edge,", "click an edge and drag."),
    'SLIDE_EDGE': ("Select an edge loop or path and middle-drag", "to slide it along the neighbouring edges."),
}


def _row(layout, label):
    split = layout.split(factor=0.42, align=True)
    left = split.row()
    left.alignment = 'RIGHT'
    left.label(text=label)
    return split.row(align=True)


def _grey(layout, key, text, check=None):
    row = layout.row()
    row.enabled = False
    icon = 'NONE' if check is None else ('CHECKBOX_HLT' if check else 'CHECKBOX_DEHLT')
    row.operator("allset.menu_unavailable", text=text, icon=icon, emboss=False).item = key


def draw_insert(layout, context, header=False):
    s = edge_loops.settings(context)
    if header:
        layout.prop(s, "iel_position", text="")
        sub = layout.row()
        sub.active = s.iel_position == 'MULTIPLE'
        sub.prop(s, "iel_loops", text="Loops")
        return
    _row(layout, "Maintain position:").column(align=True).prop(s, "iel_position", expand=True)
    _grey(_row(layout, ""), f"{TS}/Insert Edge Loop/Use Equal Multiplier", "Use Equal Multiplier", check=True)
    row = _row(layout, "Number of edge loops:")
    row.active = s.iel_position == 'MULTIPLE'
    row.prop(s, "iel_loops", text="")
    col = _row(layout, "").column(align=True)
    _grey(col, f"{TS}/Insert Edge Loop/Auto complete", "Auto complete", check=True)
    _grey(col, f"{TS}/Insert Edge Loop/Fix Quads", "Fix Quads", check=True)
    _row(layout, "").prop(s, "iel_edge_flow")
    row = _row(layout, "Adjust Edge Flow:")
    row.active = s.iel_edge_flow
    row.prop(s, "iel_adjust_flow", text="")
    _row(layout, "Smoothing angle:").prop(s, "iel_smoothing", text="")


def draw_offset(layout, context, header=False):
    s = edge_loops.settings(context)
    if header:
        layout.prop(s, "oel_position", text="")
        layout.prop(s, "oel_delete_edge", text="Delete edge")
        return
    _row(layout, "").prop(s, "oel_delete_edge")
    _row(layout, "").prop(s, "oel_edge_flow")
    row = _row(layout, "Adjust Edge Flow:")
    row.active = s.oel_edge_flow
    row.prop(s, "oel_adjust_flow", text="")
    _grey(_row(layout, "Start/End vertex offset:"), f"{TS}/Offset Edge Loop/Start/End vertex offset", "0.0000")
    _row(layout, "Smoothing angle:").prop(s, "oel_smoothing", text="")
    col = _row(layout, "Tool completion:").column(align=True)
    col.label(text="Automatically", icon='RADIOBUT_ON')
    _grey(col, f"{TS}/Offset Edge Loop/Press enter", "Press enter")
    _row(layout, "Maintain position:").column(align=True).prop(s, "oel_position", expand=True)


def draw_slide(layout, context, header=False):
    s = edge_loops.settings(context)
    if header:
        layout.prop(s, "slide_mode", expand=True)
        layout.prop(s, "slide_snap")
        return
    _row(layout, "Mode:").column(align=True).prop(s, "slide_mode", expand=True)


def draw_slide_snap(layout, context):
    s = edge_loops.settings(context)
    _row(layout, "").prop(s, "slide_snap")
    for prop, label in (("slide_snap_points", "Snapping Points:"), ("slide_snap_tolerance", "Snapping Tolerance:")):
        row = _row(layout, label)
        row.active = s.slide_snap
        row.prop(s, prop, text="")


def draw_description(layout, kind):
    col = layout.column(align=True)
    for line in DESCRIPTIONS.get(kind, ()):
        col.label(text=line)


class ALLSET_TL_insert_edge_loop(bpy.types.WorkSpaceTool):
    """Maya Insert Edge Loop Tool: press on an edge = a loop there, drag = slide it, release = keep it."""
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'
    bl_idname = edge_loops.INSERT_TOOL
    bl_label = "Insert Edge Loop Tool"
    bl_description = ("Click an edge to insert an edge loop at that point; drag before releasing to slide it "
                      "(Maya Insert Edge Loop)")
    bl_icon = "ops.mesh.loopcut_slide"
    bl_widget = None
    bl_options = {'KEYMAP_FALLBACK'}
    bl_keymap = (("allset.insert_edge_loop", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),)

    @staticmethod
    def draw_settings(context, layout, tool):
        draw_insert(layout, context, header=context.region.type == 'TOOL_HEADER')


class ALLSET_TL_offset_edge_loop(bpy.types.WorkSpaceTool):
    """Maya Offset Edge Loop Tool: press-drag on an edge = a loop on each side of its edge loop."""
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'
    bl_idname = edge_loops.OFFSET_TOOL
    bl_label = "Offset Edge Loop Tool"
    bl_description = ("Click an edge and drag: new edge loops on both sides of its edge loop "
                      "(Maya Offset Edge Loop)")
    bl_icon = "ops.mesh.offset_edge_loops_slide"
    bl_widget = None
    bl_options = {'KEYMAP_FALLBACK'}
    bl_keymap = (("allset.offset_edge_loop", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),)

    @staticmethod
    def draw_settings(context, layout, tool):
        draw_offset(layout, context, header=context.region.type == 'TOOL_HEADER')


class ALLSET_TL_slide_edge(bpy.types.WorkSpaceTool):
    """Maya Slide Edge Tool: click selects edges, middle-drag slides them."""
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'
    bl_idname = edge_loops.SLIDE_TOOL
    bl_label = "Slide Edge Tool"
    bl_description = ("Select an edge loop or path, then middle-drag to slide it along the neighbouring edges "
                      "(Maya Slide Edge)")
    bl_icon = "ops.transform.edge_slide"
    bl_widget = None
    bl_options = {'KEYMAP_FALLBACK'}
    bl_keymap = (("allset.slide_edge", {"type": 'MIDDLEMOUSE', "value": 'PRESS'}, None),)

    @staticmethod
    def draw_settings(context, layout, tool):
        draw_slide(layout, context, header=context.region.type == 'TOOL_HEADER')


TOOLS = (ALLSET_TL_insert_edge_loop, ALLSET_TL_offset_edge_loop, ALLSET_TL_slide_edge)


def register():
    notices.PANEL_NOTICES.update(GREY)
    for tool in TOOLS:
        bpy.utils.register_tool(tool, after={"builtin.loop_cut"})


def unregister():
    for tool in reversed(TOOLS):
        bpy.utils.unregister_tool(tool)
    for key in GREY:
        notices.PANEL_NOTICES.pop(key, None)
