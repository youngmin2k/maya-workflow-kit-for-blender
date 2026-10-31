# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya UV Toolkit: a "UV Toolkit" tab in the UV Editor sidebar.

Order of Maya's toolkit: component icons (Vertex · Edge ·
Face | UV · UV Shell), "N object selected", Pick/Marquee · Drag · Tweak/Marquee, Symmetry, Selection / Transform
Constraint, All · Clear · Inverse, then the folded sections Pinning · Select By Type · Soft Selection · Transform · Create ·
Cut and Sew · Unfold · Align and Snap · Arrange and Layout · UV Sets. Buttons run the kit's Maya commands
(operators/uv_tools.py) or Blender's UV operators; items Blender has no counterpart for are greyed with a notice.
"""

import math

import bpy

from . import notices

CATEGORY = "UV Toolkit"
PICK = (("Pick/Marquee", "builtin.select_box"), ("Drag", "builtin.select_circle"), ("Tweak/Marquee", "builtin.select"))
COMPONENTS = (("VERTEX", 'VERTEXSEL', "Vertex"), ("EDGE", 'EDGESEL', "Edge"), ("FACE", 'FACESEL', "Face"))
CREATE = ("Automatic", "Planar", "Cylindrical", "Spherical", "Camera-based")

GREY = {
    "UV Toolkit/Symmetry": (
        "Mirror UVs", "Blender has no UV symmetry selection: select one side, then UV > Mirror."),
    "UV Toolkit/Selection Constraint": (
        "Select menu", "Blender has no UV selection constraint: use Select > Select Linked / Select Split."),
    "UV Toolkit/Transform Constraint": (
        "Snapping", "Blender has no UV transform constraint: use snapping (UV Editor header magnet)."),
    "UV Toolkit/Select By Type/Back-Facing": (
        "Select Overlap", "Blender can't select back-facing UVs directly: Select Overlap finds stacked shells."),
    "UV Toolkit/Select By Type/Texture Borders": (
        "Seams", "Shell borders are seams in Blender: Select > Select Linked, or mark seams from islands."),
    "UV Toolkit/Unfold/Straighten": (
        "Follow Active Quads", "Blender straightens a grid of quads from the active one: UV > Follow Active Quads."),
}


def _grey(layout, key, text):
    row = layout.row()
    row.enabled = False
    row.operator("allset.menu_unavailable", text=text, emboss=False).item = key


def _section(layout, idname, label, default_closed=True):
    header, body = layout.panel(idname, default_closed=default_closed)
    header.label(text=label)
    return body


def current_component(context):
    ts = context.scene.tool_settings
    if not ts.use_uv_select_sync:
        from .. import compat
        return 'SHELL' if compat.uv_island_mode(ts) else 'UV'
    v, e, f = ts.mesh_select_mode
    return 'FACE' if f and not (v or e) else 'EDGE' if e and not v else 'VERTEX'


def _tool_id(context):
    try:
        tool = context.workspace.tools.from_space_image_mode('UV', create=False)
    except (AttributeError, TypeError):
        return ""
    return tool.idname if tool else ""


class ALLSET_PT_uv_toolkit(bpy.types.Panel):
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = CATEGORY
    bl_label = "UV Toolkit"
    bl_options = {'HIDE_HEADER'}

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space is not None and space.mode == 'UV'

    def draw(self, context):
        layout = self.layout
        editing = context.mode == 'EDIT_MESH'
        comp = current_component(context) if editing else None
        from . import editor_menu_data, menu_sets
        bar = layout.row(align=True)    # the toolkit's own menu bar: Options / Help
        for i, (title, _items) in enumerate(editor_menu_data.EDITORS["UV Toolkit"]):
            bar.menu(menu_sets.editor_menu_idname("UV Toolkit", i), text=title)
        row = layout.row(align=True)
        row.scale_x = row.scale_y = 1.3
        for mode, icon, label in COMPONENTS:
            row.operator("allset.uv_component", text="", icon=icon, depress=comp == mode).mode = mode
        row.separator()
        row.operator("allset.uv_component", text="", icon='UV_VERTEXSEL', depress=comp == 'UV').mode = 'UV'
        row.operator("allset.uv_component", text="", icon='UV_ISLANDSEL', depress=comp == 'SHELL').mode = 'SHELL'
        n = len([o for o in getattr(context, "objects_in_mode_unique_data", ()) if o.type == 'MESH'])
        layout.label(text=f"{n} object{'s' if n != 1 else ''} selected" if editing else "No mesh in edit mode")
        col = layout.column(align=True)
        tid = _tool_id(context)
        for label, tool in PICK:
            op = col.operator("wm.tool_set_by_id", text=label, depress=tid == tool,
                              icon='RADIOBUT_ON' if tid == tool else 'RADIOBUT_OFF')
            op.name, op.space_type = tool, 'IMAGE_EDITOR'
        for name in ("Symmetry", "Selection Constraint", "Transform Constraint"):
            _grey(layout, f"UV Toolkit/{name}", f"{name}: Off")
        row = layout.row(align=True)
        for label, action in (("All", 'SELECT'), ("Clear", 'DESELECT'), ("Inverse", 'INVERT')):
            row.operator("uv.select_all", text=label).action = action
        if not editing:
            return
        self._sections(layout, context)

    def _sections(self, layout, context):
        s = context.scene.allset_uv
        ts = context.scene.tool_settings
        body = _section(layout, "ALLSET_uvtk_pin", "Pinning")
        if body:
            row = body.row(align=True)
            row.operator("uv.pin", text="Pin")
            row.operator("uv.pin", text="Unpin").clear = True
            row.operator("uv.pin", text="Invert").invert = True
        body = _section(layout, "ALLSET_uvtk_type", "Select By Type")
        if body:
            body.operator("uv.select_overlap", text="Overlapping")
            _grey(body, "UV Toolkit/Select By Type/Back-Facing", "Back-Facing")
            _grey(body, "UV Toolkit/Select By Type/Texture Borders", "Texture Borders")
        body = _section(layout, "ALLSET_uvtk_soft", "Soft Selection")
        if body:
            body.prop(ts, "use_proportional_edit", text="Soft Select")
            sub = body.column()
            sub.active = ts.use_proportional_edit
            sub.prop(ts, "proportional_size", text="Falloff radius (UV)")
            sub.prop(ts, "proportional_edit_falloff", text="Falloff curve")
        body = _section(layout, "ALLSET_uvtk_transform", "Transform")
        if body:
            box = body.column(align=True)
            box.label(text="Texel Density (px/unit)")
            box.prop(s, "map_size")
            row = box.row(align=True)
            row.prop(s, "texel_density", text="")
            row.operator("allset.uv_texel_get", text="Get")
            row.operator("allset.uv_texel_set", text="Set")
            row = body.row(align=True)
            op = row.operator("transform.mirror", text="Flip U")
            op.constraint_axis = (True, False, False)
            op = row.operator("transform.mirror", text="Flip V")
            op.constraint_axis = (False, True, False)
            row = body.row(align=True)
            row.operator("transform.rotate", text="Rotate -90").value = -math.pi / 2
            row.operator("transform.rotate", text="Rotate +90").value = math.pi / 2
        body = _section(layout, "ALLSET_uvtk_create", "Create")
        if body:
            grid = body.grid_flow(columns=2, align=True)
            for label in CREATE:
                grid.operator("allset.menu_item", text=label).item = f"UV/{label}"
        body = _section(layout, "ALLSET_uvtk_cut", "Cut and Sew", default_closed=False)
        if body:
            row = body.row(align=True)
            row.operator("allset.uv_cut", text="Cut")
            row.operator("allset.uv_sew", text="Sew")
            row = body.row(align=True)
            row.operator("allset.uv_create_shell", text="Create UV Shell")
            row.operator("allset.uv_move_sew", text="Move and Sew")
            body.operator("allset.cut_sew_tool_set", text="3D Cut and Sew Tool")
        body = _section(layout, "ALLSET_uvtk_unfold", "Unfold", default_closed=False)
        if body:
            row = body.row(align=True)
            row.operator("allset.uv_unfold", text="Unfold")
            row.operator("uv.minimize_stretch", text="Optimize")
            _grey(body, "UV Toolkit/Unfold/Straighten", "Straighten")
        body = _section(layout, "ALLSET_uvtk_align", "Align and Snap")
        if body:
            row = body.row(align=True)
            row.operator("uv.align", text="Align U").axis = 'ALIGN_X'
            row.operator("uv.align", text="Align V").axis = 'ALIGN_Y'
            row = body.row(align=True)
            row.operator("allset.uv_snap_together", text="Snap Together")
            row.operator("allset.uv_snap_stack", text="Snap and Stack")
        body = _section(layout, "ALLSET_uvtk_layout", "Arrange and Layout", default_closed=False)
        if body:
            body.operator("allset.uv_layout", text="Layout")
            body.prop(s, "shell_padding", text="Shell Padding (px)")
            row = body.row(align=True)
            row.operator("allset.uv_orient_shells", text="Orient Shells")
            row.operator("allset.uv_orient_edges", text="Orient to Edges")
            row = body.row(align=True)
            row.operator("allset.uv_stack", text="Stack")
            row.operator("allset.uv_unstack", text="Unstack")
            row = body.row(align=True)
            row.operator("allset.uv_distribute", text="Distribute")
            row.operator("allset.uv_normalize", text="Normalize")
        ob = context.edit_object
        body = _section(layout, "ALLSET_uvtk_sets", "UV Sets")
        if body and ob is not None and ob.type == 'MESH':
            me = ob.data
            body.template_list("MESH_UL_uvmaps", "", me, "uv_layers", me.uv_layers, "active_index", rows=2)


classes = (ALLSET_PT_uv_toolkit,)


def register():
    notices.PANEL_NOTICES.update(GREY)
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    for key in GREY:
        notices.PANEL_NOTICES.pop(key, None)
