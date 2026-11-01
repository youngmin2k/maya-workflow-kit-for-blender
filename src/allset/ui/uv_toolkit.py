# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya UV Toolkit: a "UV Toolkit" tab in the UV Editor sidebar.

Order of Maya's toolkit: component icons (Vertex · Edge ·
Face | UV · UV Shell), "N object selected", Pick/Marquee · Drag · Tweak/Marquee, Symmetry, Selection / Transform
Constraint, All · Clear · Inverse, then the folded sections Pinning · Select By Type · Soft Selection · Transform · Create ·
Cut and Sew · Unfold · Align and Snap · Arrange and Layout · UV Sets. Buttons run the UV Editor menu items through
``allset.menu_item`` (same command, undo step and option box as the menu) or the kit's toolkit-only commands
(operators/uv_toolkit_ops.py); items Blender has no counterpart for are greyed with a notice. Stack Similar Shells
matches shells of the same shape onto each other.
"""

import math

import bpy

from .. import i18n
from . import notices

CATEGORY = "UV Toolkit"
PICK = (("Pick/Marquee", "builtin.select_box"), ("Drag", "builtin.select_circle"), ("Tweak/Marquee", "builtin.select"))
COMPONENTS = (("VERTEX", 'VERTEXSEL', "Vertex"), ("EDGE", 'EDGESEL', "Edge"), ("FACE", 'FACESEL', "Face"))
UVE = "UV Editor"
# button label, UV Editor menu path (relative ones under UV Editor/)
CREATE = ((i18n.mark("Automatic"), "UV/Automatic"), (i18n.mark("Best Plane"), "UV/Best Plane"),
          (i18n.mark("Camera-based"), "UV/Camera-based"), (i18n.mark("Contour Stretch"), "UV/Contour Stretch"),
          (i18n.mark("Cylindrical"), "UV/Cylindrical"), (i18n.mark("Normal-based"), f"{UVE}/Create/Normal-based"),
          (i18n.mark("Planar"), "UV/Planar"), (i18n.mark("Spherical"), "UV/Spherical"))
SELECT_BY_TYPE = (i18n.mark("Back-Facing"), i18n.mark("Front-Facing"), i18n.mark("Overlapping"), i18n.mark("Non-Overlapping"),
                  i18n.mark("Texture Borders"), (i18n.mark("Unmapped"), "Unmapped Faces"))
CUT_SEW = ((i18n.mark("Auto Seams"), "Cut/Sew/Auto Seams"), (i18n.mark("Cut"), "Cut/Sew/Cut"),
           (i18n.mark("Split"), "Cut/Sew/Split"), (i18n.mark("Sew"), "Cut/Sew/Sew"),
           (i18n.mark("Create Shell"), "Cut/Sew/Create UV Shell"),
           (i18n.mark("Create Shell (Grid)"), "Cut/Sew/Create Shell (Grid)"),
           (i18n.mark("Move and Sew"), "Cut/Sew/Move and Sew"),
           (i18n.mark("Stitch Together"), "Cut/Sew/Stitch Together"), (i18n.mark("Merge"), "Cut/Sew/Merge"))
SNAP = ((i18n.mark("Linear Align"), "Modify/Linear Align"), (i18n.mark("Match Grid"), "Modify/Match Grid"),
        (i18n.mark("Match UVs"), "Modify/Match UVs"), (i18n.mark("Snap Together"), "Modify/Snap Together"),
        (i18n.mark("Snap and Stack"), "Modify/Snap and Stack"))
ARRANGE = ((i18n.mark("Distribute"), "Modify/Distribute Shells"),
           (i18n.mark("Gather Shells"), "Modify/Gather Shells"), (i18n.mark("Layout Along"), "Modify/Layout Along"),
           (i18n.mark("Normalize"), "Modify/Normalize"), (i18n.mark("Orient Shells"), "Modify/Orient Shells"),
           (i18n.mark("Orient to Edges"), "Modify/Orient Shells to Edges"),
           (i18n.mark("Randomize"), "Modify/Randomize Shells"), (i18n.mark("Stack"), "Modify/Stack Shells"),
           (i18n.mark("Stack and Orient"), "Modify/Stack and Orient Shells"),
           (i18n.mark("Stack Similar"), "Modify/Stack Similar Shells"),
           (i18n.mark("Unstack"), "Modify/Unstack Shells"), (i18n.mark("Unitize"), "Modify/Unitize"))
ALIGN = (('U', 'MIN', i18n.mark("Min U")), ('U', 'AVG', i18n.mark("Avg U")), ('U', 'MAX', i18n.mark("Max U")),
         ('V', 'MIN', i18n.mark("Min V")), ('V', 'AVG', i18n.mark("Avg V")), ('V', 'MAX', i18n.mark("Max V")))

GREY = {
    "UV Toolkit/Symmetry": (
        "Mirror UVs", "Blender has no UV symmetry selection: select one side, then UV > Mirror."),
    "UV Toolkit/Selection Constraint": (
        "Select menu", "Blender has no UV selection constraint: use Select > Select Linked / Select Split."),
    "UV Toolkit/Transform Constraint": (
        "Snapping", "Blender has no UV transform constraint: use snapping (UV Editor header magnet)."),
}


def _grey(layout, key, text):
    row = layout.row()
    row.enabled = False
    row.operator("allset.menu_unavailable", text=text, emboss=False).item = key


def _item(layout, path, text):
    """A UV Editor menu item: the same command, undo step and option box as the menu."""
    layout.operator("allset.menu_item", text=text).item = path


def _grid(layout, rows, columns=2):
    """Buttons ``columns`` to a row, in reading order (left to right, then down)."""
    col = layout.column(align=True)
    for i in range(0, len(rows), columns):
        row = col.row(align=True)
        for text, path in rows[i:i + columns]:
            _item(row, path if path.startswith(("UV/", UVE)) else f"{UVE}/{path}", text)


def _section(layout, idname, label, default_closed=True):
    header, body = layout.panel(idname, default_closed=default_closed)
    header.label(text=label)
    return body


def current_component(context):
    from ..operators import uv_shell_select
    if uv_shell_select.active(context):
        return 'SHELL'
    ts = context.scene.tool_settings
    if not ts.use_uv_select_sync:
        from .. import compat
        if compat.uv_island_mode(ts):
            return 'SHELL'
        return {'EDGE': 'UV_EDGE', 'FACE': 'UV_FACE'}.get(ts.uv_select_mode, 'UV')
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
        for mode, icon in (('UV', 'UV_VERTEXSEL'), ('UV_EDGE', 'UV_EDGESEL'), ('UV_FACE', 'UV_FACESEL')):
            row.operator("allset.uv_component", text="", icon=icon, depress=comp == mode).mode = mode
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
            _grid(body, [(it, f"Select/{it}") if isinstance(it, str) else (it[0], f"Select/{it[1]}")
                         for it in SELECT_BY_TYPE])
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
            _grid(body, CREATE)
        body = _section(layout, "ALLSET_uvtk_cut", "Cut and Sew", default_closed=False)
        if body:
            _grid(body, CUT_SEW)
            body.operator("allset.cut_sew_tool_set", text="3D Cut and Sew Tool")
        body = _section(layout, "ALLSET_uvtk_unfold", "Unfold", default_closed=False)
        if body:
            row = body.row(align=True)
            row.operator("allset.uv_unfold", text="Unfold")
            _item(row, f"{UVE}/Modify/Optimize", "Optimize")
            row = body.row(align=True)
            row.operator("allset.uv_unfold_along", text="Unfold Along U").axis = 'U'
            row.operator("allset.uv_unfold_along", text="Unfold Along V").axis = 'V'
            tk = context.scene.allset_uv_toolkit
            from ..operators import uv_toolkit_ops
            split = body.split(factor=0.6, align=True)
            op = split.operator("allset.uv_straighten_uvs", text="Straighten UVs")
            op.axis, op.tolerance = uv_toolkit_ops.straighten_axis(context), tk.straighten_tolerance
            row = split.row(align=True)
            row.prop(tk, "straighten_u", toggle=True)
            row.prop(tk, "straighten_v", toggle=True)
            body.prop(tk, "straighten_tolerance")
            row = body.row(align=True)
            _item(row, f"{UVE}/Modify/Straighten Shell", "Straighten Shell")
            _item(row, f"{UVE}/Modify/Straighten Border", "Straighten Border")
        body = _section(layout, "ALLSET_uvtk_align", "Align and Snap")
        if body:
            for i in (0, 3):
                row = body.row(align=True)
                for axis, where, label in ALIGN[i:i + 3]:
                    op = row.operator("allset.uv_align_to", text=label)
                    op.axis, op.where = axis, where
            _grid(body, SNAP)
        body = _section(layout, "ALLSET_uvtk_layout", "Arrange and Layout", default_closed=False)
        if body:
            body.operator("allset.uv_layout", text="Layout")
            body.prop(s, "shell_padding", text="Shell Padding (px)")
            _grid(body, ARRANGE)
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
