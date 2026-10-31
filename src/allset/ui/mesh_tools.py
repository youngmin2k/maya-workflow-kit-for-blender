# SPDX-License-Identifier: GPL-3.0-or-later
"""Target Weld and Crease Tool as Blender tools, and Maya's Multi-Cut Tool Settings.

- Target Weld (Maya Mesh Tools > Target Weld): LMB press on a
  vertex / edge starts ``allset.target_weld``; a press away from them falls back to the select tool.
- Crease Tool (Mesh Tools > Crease Tool): MMB drag = ``allset.crease_drag``; LMB selects (fallback).
- Multi-Cut: the kit tool ``allset.multi_cut_tool`` running
  ``allset.multi_cut`` (operators/multi_cut.py); its Tool Settings are Maya's.
Settings live in ``Scene.allset_mesh_tools`` (operators/mesh_tools.py).
"""

import bpy

from . import notices
from ..operators import cut_sew, mesh_tools, multi_cut

# Greyed Maya settings: (notice key, label) -> (substitute, one line)
GREY = {
    "Multi-Cut/Edge Flow": (
        "Edge Slide", "New loops are straight: Blender has no edge flow; slide them with G G (Edge Slide)."),
    "Multi-Cut/Color Settings": (
        "Preferences > Themes", "The cut colours are the kit's (yellow points, grey preview, orange loop)."),
    "Multi-Cut/Live Constraint Options": (
        "Make Live / Move", "Multi-Cut has no live constraint yet. Move new vertices onto Make Live surfaces with the Move centre/plane handles."),
    "Crease Tool/Extend to creased components": (
        "Select Similar", "Select the creased edges with Select > Select Similar > Crease first."),
}


def _grey(layout, key, text):
    row = layout.row()
    row.enabled = False
    row.operator("allset.menu_unavailable", text=text, emboss=False).item = key


class ALLSET_TL_target_weld(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'
    bl_idname = mesh_tools.TARGET_WELD_TOOL
    bl_label = "Target Weld"
    bl_description = ("Drag a vertex or edge onto the target to merge them (Maya Target Weld). "
                      "A selected vertex takes every selected vertex with it")
    bl_icon = "ops.transform.vert_slide"
    bl_widget = None
    bl_options = {'KEYMAP_FALLBACK'}
    bl_keymap = (("allset.target_weld", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),)

    @staticmethod
    def draw_settings(context, layout, tool):
        s = mesh_tools.settings(context)
        layout.prop(s, "weld_merge_to", expand=True)
        layout.prop(s, "weld_preserve_uvs")


class ALLSET_TL_crease(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'
    bl_idname = mesh_tools.CREASE_TOOL
    bl_label = "Crease Tool"
    bl_description = ("Crease the selected edges (vertices in vertex mode): middle-drag left = less, "
                      "right = more (Maya Crease Tool)")
    bl_icon = "ops.transform.shrink_fatten"
    bl_widget = None
    bl_options = {'KEYMAP_FALLBACK'}
    bl_keymap = (("allset.crease_drag", {"type": 'MIDDLEMOUSE', "value": 'PRESS'}, None),)

    @staticmethod
    def draw_settings(context, layout, tool):
        layout.prop(mesh_tools.settings(context), "crease_mode", expand=True)
        if context.region.type != 'TOOL_HEADER':
            _grey(layout, "Crease Tool/Extend to creased components", "Extend to creased components")


class ALLSET_TL_cut_sew(bpy.types.WorkSpaceTool):
    """Maya 3D Cut and Sew UV Tool: drag = cut, Ctrl+drag = sew, Shift+drag = select;
    x / s / d = Cut / Sew / Unfold + Layout (Maya hotkeys, tool context polyCutUV)."""
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'
    bl_idname = cut_sew.TOOL
    bl_label = "3D Cut and Sew UV Tool"
    bl_description = ("Drag along edges to cut the UVs there, Ctrl+drag to sew them, Shift+drag to select edges. "
                      "x = Cut, s = Sew, d = Unfold and Layout (Maya 3D Cut and Sew UV Tool)")
    bl_icon = "ops.mesh.knife_tool"
    bl_widget = None
    bl_options = {'KEYMAP_FALLBACK'}
    bl_keymap = (
        ("allset.cut_sew_stroke", {"type": 'LEFTMOUSE', "value": 'PRESS'}, {"properties": [("action", 'CUT')]}),
        ("allset.cut_sew_stroke", {"type": 'LEFTMOUSE', "value": 'PRESS', "ctrl": True},
         {"properties": [("action", 'SEW')]}),
        ("allset.cut_sew_stroke", {"type": 'LEFTMOUSE', "value": 'PRESS', "shift": True},
         {"properties": [("action", 'SELECT')]}),
        ("allset.uv_cut", {"type": 'X', "value": 'PRESS'}, {"properties": [("mesh_select", True)]}),
        ("allset.uv_sew", {"type": 'S', "value": 'PRESS'}, {"properties": [("mesh_select", True)]}),
        ("allset.uv_unfold_layout", {"type": 'D', "value": 'PRESS'}, None),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        layout.label(text="Drag: Cut  ·  Ctrl+drag: Sew  ·  Shift+drag: Select", icon='INFO')
        row = layout.row(align=True)
        row.operator("allset.uv_cut", text="Cut (x)").mesh_select = True
        row.operator("allset.uv_sew", text="Sew (s)").mesh_select = True
        row.operator("allset.uv_unfold_layout", text="Unfold + Layout (d)")


MULTI_CUT_SHORTCUTS = (
    ("Click edge / face / vertex", "place a cut point (drag: slide it along the edge)"),
    ("Shift", "snap the point to the Snap Step %"),
    ("Ctrl+click", "insert an edge loop (Ctrl+Shift: at the Snap Step)"),
    ("Ctrl+middle-click", "edge loop in the middle of the edge"),
    ("Backspace", "remove the last point"),
    ("Enter / right-click", "complete the cut (the tool stays)"),
    ("Esc", "drop the points; with none, leave the tool"),
    ("Drag across faces", "slice"),
)


def _hover_items():
    items = [("allset.multi_cut_hover", {"type": 'MOUSEMOVE', "value": 'ANY', "any": True}, None)]
    for key in ('LEFT_CTRL', 'RIGHT_CTRL', 'LEFT_SHIFT', 'RIGHT_SHIFT'):
        for value in ('PRESS', 'RELEASE'):
            items.append(("allset.multi_cut_hover", {"type": key, "value": value, "any": True}, None))
    return tuple(items)


class ALLSET_TL_multi_cut(bpy.types.WorkSpaceTool):
    """Maya Multi-Cut: points on edges / faces / vertices, Enter or RMB cuts,
    Ctrl = edge loop, Shift = Snap Step, Backspace, drag = slice. No select fallback: Maya's Multi-Cut LMB doesn't
    select."""
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'
    bl_idname = multi_cut.TOOL
    bl_label = "Multi-Cut"
    bl_description = ("Click edges, faces or vertices to place cut points, Enter or right-click to cut. "
                      "Ctrl+click = edge loop, Shift = Snap Step %, Backspace = remove the last point, "
                      "drag across faces = slice (Maya Multi-Cut)")
    bl_icon = "ops.mesh.knife_tool"
    bl_widget = None
    bl_keymap = (
        # loops first: one undo step each and Adjust Last Operation Position (the kit's multicut operator); they pass
        # through when no edge is under the mouse
        ("allset.multicut_loop", {"type": 'LEFTMOUSE', "value": 'PRESS', "ctrl": True}, None),
        ("allset.multicut_loop", {"type": 'LEFTMOUSE', "value": 'PRESS', "ctrl": True, "shift": True},
         {"properties": [("snap", True)]}),
        ("allset.multicut_loop", {"type": 'MIDDLEMOUSE', "value": 'PRESS', "ctrl": True},
         {"properties": [("center", True)]}),
        ("allset.multi_cut", {"type": 'LEFTMOUSE', "value": 'PRESS', "any": True}, None),
        ("allset.multi_cut_exit", {"type": 'ESC', "value": 'PRESS'}, None),
        *_hover_items(),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        s = mesh_tools.settings(context)
        if context.region.type == 'TOOL_HEADER':
            layout.prop(s, "snap_step", slider=True)
            return
        draw_multi_cut(layout, s)


def draw_multi_cut(layout, s):
    """Maya's Multi-Cut Tool Settings, Maya's order and factory values."""
    layout.prop(s, "snap_step", slider=True)
    box = layout.box()
    box.label(text="Cut / Insert Edge Loop Tool")
    box.prop(s, "smoothing_angle", slider=True)
    _grey(box, "Multi-Cut/Edge Flow", "Edge Flow")
    box.prop(s, "subdivisions", slider=True)
    box = layout.box()
    box.label(text="Slice Tool")
    box.prop(s, "ignore_backfaces")
    box.prop(s, "delete_faces")
    box.prop(s, "extract_faces")
    row = box.row(align=True)
    row.enabled = s.extract_faces          # Maya greys the offset while Extract Faces is off
    row.prop(s, "extract_offset", text="")
    box.label(text="Slice Along Plane:")
    box.row(align=True).prop(s, "slice_plane", expand=True)
    _grey(layout, "Multi-Cut/Color Settings", "Color Settings")
    _grey(layout, "Multi-Cut/Live Constraint Options", "Live Constraint Options")
    box = layout.box()
    box.label(text="Keyboard/Mouse Shortcuts")
    col = box.column(align=True)
    for key, what in MULTI_CUT_SHORTCUTS:
        col.label(text=f"{key}: {what}")


TOOLS = (ALLSET_TL_multi_cut, ALLSET_TL_target_weld, ALLSET_TL_crease, ALLSET_TL_cut_sew)


def active_tool_id(context):
    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
    except (AttributeError, TypeError, RuntimeError):
        return ""
    return tool.idname if tool is not None else ""


def register():
    notices.PANEL_NOTICES.update(GREY)
    for tool in TOOLS:
        bpy.utils.register_tool(tool, after={"builtin.knife"})


def unregister():
    for tool in reversed(TOOLS):
        bpy.utils.unregister_tool(tool)
    for key in GREY:
        notices.PANEL_NOTICES.pop(key, None)
