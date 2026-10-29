# SPDX-License-Identifier: GPL-3.0-or-later
"""Quad Draw, Create Polygon and Append to Polygon as kit tools (docs/steps/step_144_poly.md 「계획」, GitHub #30).

The tools run the modals of operators/quad_draw.py and operators/poly_draw.py; their Maya Tool Settings (fields and
factory values of Maya 2022) are drawn here, in Blender's tool header / Tool tab and in the kit's
Tool Settings dock (ui/tool_settings.py kinds QUAD_DRAW / CREATE_POLYGON / APPEND_POLYGON).
"""

import bpy

from . import notices
from ..operators import poly_draw, quad_draw

# Remaining Maya rows without a matching tool gesture:
# (notice key) -> (substitute, one line)
GREY = {
    "Append to Polygon/Rotation angle": ("Rotate afterwards", "Maya keeps this field greyed in the tool too"),
}

# Maya's Keyboard/Mouse Shortcuts section, as the kit does them.
QUAD_DRAW_SHORTCUTS = (
    ("(outside the quad mesh)", ""),
    ("LMB", "click to drop dots"),
    ("LMB / MMB", "drag to tweak dots"),
    ("Ctrl + Shift + LMB", "delete dots"),
    ("Tab + LMB", "drag to draw quad strips"),
    ("Shift + LMB", "click between dots to create geometry"),
    ("(inside the quad mesh)", ""),
    ("LMB / MMB", "drag to tweak components"),
    ("Ctrl + LMB", "click edge to insert loop"),
    ("Ctrl + MMB", "click edge to insert centred loop"),
    ("Shift + LMB", "drag to relax points"),
    ("Shift + MMB", "right: relax; left: undo within the stroke"),
    ("Tab + LMB", "drag to extend border edge (Extend: Loop = the border)"),
    ("Tab + MMB", "drag to extend border edge loop"),
    ("Ctrl + Shift + LMB", "click or drag across faces to delete"),
    ("Ctrl + Shift + LMB", "click edge to delete edge loop"),
    ("Ctrl + Shift + MMB", "drag edge to tweak edge loop"),
    ("Y", "reactivate the last Quad Draw tool"),
    ("Esc", "leave the tool"),
    ("Tab + MMB outside the mesh", "drag to resize quad strips"),
    ("Ctrl + Shift + RMB", "Quad Draw options marking menu"),
)
CREATE_SHORTCUTS = (
    ("Click", "place a point (drag to move it)"),
    ("Middle-drag", "move the last point"),
    ("Backspace / Delete", "remove the last point"),
    ("Enter", "complete the polygon (the tool stays)"),
    ("Esc", "drop the points; with none, leave the tool"),
)
APPEND_SHORTCUTS = (
    ("Click a border edge", "start the new face there"),
    ("Click", "place a point / add another border edge"),
    ("Backspace / Delete", "remove the last point"),
    ("Enter", "add the face (the tool stays)"),
    ("Esc", "drop the points; with none, leave the tool"),
)
# Description sections (the kit's words for what Maya's say)
DESCRIPTIONS = {
    'CREATE_POLYGON': ("Click to place each point of the polygon,", "then press Enter."),
    'APPEND_POLYGON': ("Click a border edge, then click to place points", "or click more border edges; Enter adds the face."),
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


def draw_quad_draw(layout, context, header=False):
    s = poly_draw.settings(context)
    if header:
        layout.prop(s, "qd_auto_weld", text="Auto-weld")
        layout.prop(s, "qd_relax", text="")
        layout.prop(s, "qd_extend", text="")
        return
    row = _row(layout, "Auto-weld:")
    row.prop(s, "qd_auto_weld", text="")
    sub = row.row(align=True)
    sub.active = s.qd_auto_weld
    sub.prop(s, "qd_weld_px", text="")
    _row(layout, "Relax:").prop(s, "qd_relax", text="")
    _row(layout, "Extend:").prop(s, "qd_extend", text="")
    _row(layout, "Quad Strip Width:").prop(s, "qd_strip_width", text="")
    _row(layout, "").operator("allset.quad_draw_clear_dots", text="Clear Dots")
    sym=context.scene.allset_symmetry
    if sym.about=='TOPOLOGY':
        row=layout.row(align=True);row.operator('allset.quad_draw_pick_seam',text='Pick Seam',icon='EYEDROPPER')
        row.prop(sym,'allow_partial',text='Partial')
        if not sym.on:
            layout.label(text='Symmetry off; pick a seam to enable',icon='INFO')
            return
        info=quad_draw.STATE.get('topology_info')
        ob=context.edit_object
        if info and ob is not None and info['object']==ob.name:
            layout.label(text=f"{info['paired']} pairs · {info['unmatched']} unpaired",icon='MOD_MIRROR' if info['paired'] else 'INFO')
            if info.get('message'):layout.label(text=info['message'],icon='INFO')
            elif info.get('hover_supported') is False:layout.label(text='Component outside matched region',icon='INFO')
        else:layout.label(text='Select a center edge to check symmetry',icon='INFO')


def draw_live(layout, context):
    """Live Constraint Options (black wire, cyan retopology tint, Mesh Alpha 0.75,
    Surface Offset off 0, Snap to Backfaces off)."""
    s = poly_draw.settings(context)
    row = _row(layout, "Wireframe Overlay:")
    row.prop(s, "qd_wire_overlay", text="")
    sub = row.row(); sub.active = s.qd_wire_overlay
    sub.prop(s, "qd_wire_color", text="")
    row = _row(layout, "Mesh Color:")
    row.prop(s, "qd_mesh_color_on", text="")
    sub = row.row(); sub.active = s.qd_mesh_color_on
    sub.prop(s, "qd_mesh_color", text="")
    _row(layout, "Mesh Alpha:").prop(s, "qd_mesh_alpha", text="", slider=True)
    unit=context.scene.unit_settings.length_unit
    unit={'CENTIMETERS':'cm','MILLIMETERS':'mm','METERS':'m','MICROMETERS':'µm','KILOMETERS':'km','INCHES':'in','FEET':'ft','MILES':'mi','THOU':'thou'}.get(unit,'BU')
    if context.scene.unit_settings.system=='NONE':unit='BU'
    row = _row(layout, f"Surface Offset ({unit}):")
    row.prop(s, "qd_offset_on", text="")
    sub = row.row(); sub.active = s.qd_offset_on
    sub.prop(s, "qd_surface_offset", text="")
    _row(layout, "Snap to Backfaces:").prop(s, "qd_snap_backfaces", text="")
    from ..operators import live
    _row(layout, "Live surface:").label(text=live.text(context.scene))


def _limit(layout, s, prefix):
    _row(layout, "").prop(s, f"{prefix}_limit_on")
    row = _row(layout, "Limit points to:")
    row.active = getattr(s, f"{prefix}_limit_on")
    row.prop(s, f"{prefix}_limit_points", text="")


def draw_create(layout, context, header=False):
    s = poly_draw.settings(context)
    if header:
        layout.prop(s, "cp_divisions")
        layout.prop(s, "cp_keep_planar")
        return
    _row(layout, "Divisions:").prop(s, "cp_divisions", text="")
    _row(layout, "").prop(s, "cp_keep_planar")
    _limit(layout, s, "cp")
    _row(layout, "Texture space:").column(align=True).prop(s, "cp_texture", expand=True)


def draw_append(layout, context, header=False):
    s = poly_draw.settings(context)
    if header:
        layout.prop(s, "ap_divisions")
        layout.prop(s, "ap_keep_planar")
        return
    _row(layout, "Divisions:").prop(s, "ap_divisions", text="")
    _grey(_row(layout, "Rotation angle:"), "Append to Polygon/Rotation angle", "0.0000")
    _row(layout, "").prop(s, "ap_keep_planar")
    _limit(layout, s, "ap")
    _row(layout, "Texture space:").column(align=True).prop(s, "ap_texture", expand=True)


def draw_description(layout, kind):
    col = layout.column(align=True)
    for line in DESCRIPTIONS.get(kind, ()):
        col.label(text=line)


def draw_shortcuts(layout, rows):
    col = layout.column(align=True)
    for key, what in rows:
        split = col.split(factor=0.42)
        split.label(text=key)
        split.label(text=what)


def _hover_items():
    items = [("allset.quad_draw_hover", {"type": 'MOUSEMOVE', "value": 'ANY', "any": True}, None)]
    for key in ('LEFT_CTRL', 'RIGHT_CTRL', 'LEFT_SHIFT', 'RIGHT_SHIFT'):
        for value in ('PRESS', 'RELEASE'):
            items.append(("allset.quad_draw_hover", {"type": key, "value": value, "any": True}, None))
    return tuple(items)


class ALLSET_TL_quad_draw(bpy.types.WorkSpaceTool):
    """Maya Quad Draw (docs/steps/step_144_poly.md): dots on the live surface, Shift = fill / relax, Ctrl = loop,
    Ctrl+Shift = delete, Tab+drag = extend / strip. No select fallback: Maya's Quad Draw LMB doesn't select."""
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'
    bl_idname = quad_draw.TOOL
    bl_label = "Quad Draw"
    bl_description = ("Click on the live surface to place dots, Shift+click between them to fill a quad. "
                      "Drag = move, Shift+drag = relax, Ctrl+click = edge loop, Ctrl+Shift+click = delete, "
                      "Tab+drag = extend a border / quad strip (Maya Quad Draw)")
    bl_icon = "ops.mesh.polybuild_hover"
    bl_widget = None
    bl_keymap = (
        ("allset.quad_draw", {"type": 'LEFTMOUSE', "value": 'PRESS', "any": True}, None),
        # MMB with any modifiers (Ctrl = centred loop, Shift = relax, Ctrl+Shift = tweak loop); Alt passes through
        ("allset.quad_draw", {"type": 'MIDDLEMOUSE', "value": 'PRESS', "any": True},
         {"properties": [("middle", True)]}),
        ("allset.quad_draw_tab", {"type": 'TAB', "value": 'PRESS'}, None),
        ("allset.quad_draw_options", {"type": 'RIGHTMOUSE', "value": 'PRESS', 'ctrl':True,'shift':True}, None),
        ("allset.quad_draw_exit", {"type": 'ESC', "value": 'PRESS'}, None),
        *_hover_items(),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        draw_quad_draw(layout, context, header=context.region.type == 'TOOL_HEADER')


def _create_keymap():
    return (
        ("allset.create_polygon", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
        ("allset.poly_tool_exit", {"type": 'ESC', "value": 'PRESS'}, None),
    )


class ALLSET_TL_create_polygon(bpy.types.WorkSpaceTool):
    """Maya Create Polygon (object mode)."""
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = poly_draw.CREATE_TOOL
    bl_label = "Create Polygon"
    bl_description = ("Click to place points, Enter to make a new polygon object. Backspace removes the last point, "
                      "middle-drag moves it (Maya Create Polygon)")
    bl_icon = "ops.mesh.polybuild_hover"
    bl_widget = None
    bl_keymap = _create_keymap()

    @staticmethod
    def draw_settings(context, layout, tool):
        draw_create(layout, context, header=context.region.type == 'TOOL_HEADER')


class ALLSET_TL_create_polygon_edit(bpy.types.WorkSpaceTool):
    """Maya Create Polygon (component mode: the polygon is still a new object)."""
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'
    bl_idname = poly_draw.CREATE_TOOL
    bl_label = "Create Polygon"
    bl_description = ALLSET_TL_create_polygon.bl_description
    bl_icon = "ops.mesh.polybuild_hover"
    bl_widget = None
    bl_keymap = _create_keymap()

    @staticmethod
    def draw_settings(context, layout, tool):
        draw_create(layout, context, header=context.region.type == 'TOOL_HEADER')


class ALLSET_TL_append_polygon(bpy.types.WorkSpaceTool):
    """Maya Append to Polygon."""
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'
    bl_idname = poly_draw.APPEND_TOOL
    bl_label = "Append to Polygon"
    bl_description = ("Click a border edge of the mesh, then place points or click another border edge; Enter adds "
                      "the face (Maya Append to Polygon)")
    bl_icon = "ops.mesh.polybuild_hover"
    bl_widget = None
    bl_keymap = (
        ("allset.append_polygon", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
        ("allset.poly_tool_exit", {"type": 'ESC', "value": 'PRESS'}, None),
    )

    @staticmethod
    def draw_settings(context, layout, tool):
        draw_append(layout, context, header=context.region.type == 'TOOL_HEADER')


TOOLS = (ALLSET_TL_quad_draw, ALLSET_TL_create_polygon, ALLSET_TL_create_polygon_edit, ALLSET_TL_append_polygon)


def register():
    notices.PANEL_NOTICES.update(GREY)
    for tool in TOOLS:
        after = {"builtin.poly_build"} if tool.bl_context_mode == 'EDIT_MESH' else None
        bpy.utils.register_tool(tool, after=after)


def unregister():
    for tool in reversed(TOOLS):
        bpy.utils.unregister_tool(tool)
    for key in GREY:
        notices.PANEL_NOTICES.pop(key, None)
