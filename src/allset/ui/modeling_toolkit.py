# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Modeling Toolkit: the third editor of the sidebar dock (docs/steps/step_63.md 「계획」 1).

Order of Maya's tab: selection mode
(Multi-Component, Object / Vertex / Edge / Face / UV), "N face selected", Pick/Marquee · Drag ·
Tweak/Marquee, Highlight Backfaces, Highlight Nearest Component, Camera Based Selection, Symmetry,
Selection / Transform Constraint, ▸Soft Selection, ▾Mesh, ▾Components, ▾Tools. Buttons run the same
actions as Maya's menus (``allset.menu_item`` with the Maya menu path); items Blender has no
equivalent for are greyed with their notice (ui/notices.py).
"""

import bpy
from bpy.props import BoolProperty, FloatProperty

from . import notices

MESH = (("Combine", "Mesh/Combine", 'AUTOMERGE_ON'), ("Separate", "Mesh/Separate", 'MOD_EXPLODE'),
        ("Smooth", "Mesh/Smooth", 'MOD_SUBSURF'), ("Boolean", "Mesh/Booleans/Union", 'MOD_BOOLEAN'))
COMPONENTS = (("Extrude", None, 'FACESEL'), ("Bevel", "Edit Mesh/Bevel", 'MOD_BEVEL'),
              ("Bridge", "Edit Mesh/Bridge", 'MOD_LATTICE'), ("Add Divisions", "Edit Mesh/Add Divisions", 'MESH_GRID'))
TOOLS = (("Multi-Cut", "Mesh Tools/Multi-Cut", 'SCULPTMODE_HLT'), ("Target Weld", "Mesh Tools/Target Weld", 'AUTOMERGE_OFF'),
         ("Connect", "Edit Mesh/Connect", 'MOD_EDGESPLIT'), ("Quad Draw", "Mesh Tools/Quad Draw", 'MESH_DATA'))
# Maya's three selection styles = Blender select tools
PICK = (("Pick/Marquee", "builtin.select_box"), ("Drag", "builtin.select_circle"), ("Tweak/Marquee", "builtin.select"))
COMPONENT_ICONS = (("VERT", 'VERTEXSEL', 0), ("EDGE", 'EDGESEL', 1), ("FACE", 'FACESEL', 2))
UNIT = ("vertex", "edge", "face")

# Greyed rows: Maya options without a Blender counterpart (notices keyed like Maya menu paths)
GREY = {
    "Modeling Toolkit/Highlight Backfaces": (
        "X-ray", "Blender does not highlight back faces separately: use X-ray (Alt+Z) to see and pick them."),
    "Modeling Toolkit/Selection Constraint": (
        "Select menu", "Blender has no selection constraint: use Select > Select Loops / Linked / Similar."),
    "Modeling Toolkit/Transform Constraint": (
        "Edge / Vertex Slide", "Blender has no transform constraint: slide along edges with G G (Edge / Vertex Slide)."),
    "Modeling Toolkit/UV": (
        "UV Editor", "UV components are edited in the UV Editor (Windows > Modeling Editors > UV Editor)."),
    "Modeling Toolkit/Soft Selection/Global": (
        "Volume / Surface", "Blender's proportional editing works on the selected mesh only (no Global / Object falloff)."),
}
# Real Maya menu items: their notices also show in the menus (ui/notices.NOTICES). Target Weld got its tool
# in step 64.
MENU_NOTICES = {}
NOTE = "Maya's colour falloff on the vertices: Blender shows the radius as a circle"


def _mesh_mode(context):
    return context.mode == 'EDIT_MESH'


def _selected_count(context):
    """Maya's "N face selected" line: the count in the current component type (edit mode stats)."""
    ts = context.scene.tool_settings
    mode = list(ts.mesh_select_mode)
    i = 2 if mode[2] and not (mode[0] or mode[1]) else 1 if mode[1] and not mode[0] else 0
    obs = [o for o in context.objects_in_mode_unique_data if o.type == 'MESH'] \
        if hasattr(context, "objects_in_mode_unique_data") else []
    totals = ("total_vert_sel", "total_edge_sel", "total_face_sel")
    n = sum(getattr(o.data, totals[i]) for o in obs)
    return n, UNIT[i]


def _button(layout, label, path, icon):
    if path is None or path not in _menu_map().MAP:
        op = layout.operator("allset.menu_unavailable", text=label, icon=icon)
    else:
        op = layout.operator("allset.menu_item", text=label, icon=icon)
    op.item = path or f"Modeling Toolkit/{label}"


def _menu_map():
    from . import menu_map
    return menu_map


def _grey(layout, key, text):
    row = layout.row()
    row.enabled = False
    row.operator("allset.menu_unavailable", text=text, emboss=False).item = key


# --- soft selection in Maya units ----------------------------------------------------------------

def _units():
    from ..operators import units
    return units


def _radius_get(self):
    return self.tool_settings.proportional_size / _units().maya_unit(self)


def _radius_set(self, value):
    self.tool_settings.proportional_size = max(1e-6, value * _units().maya_unit(self))


class ALLSET_OT_soft_select_reset(bpy.types.Operator):
    """Reset soft selection to Maya's factory settings (radius 5 Maya units, Volume, smooth falloff)"""
    bl_idname = "allset.soft_select_reset"
    bl_label = "Reset Soft Selection"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ..operators import taphold
        ts = context.scene.tool_settings
        ts.proportional_size = taphold.MAYA_SOFT_RADIUS * _units().maya_unit(context.scene)
        ts.use_proportional_connected = False
        ts.proportional_edit_falloff = 'SMOOTH'
        return {'FINISHED'}


class ALLSET_OT_soft_falloff_mode(bpy.types.Operator):
    """Maya soft select falloff mode: Volume (by distance) or Surface (along the connected surface)"""
    bl_idname = "allset.soft_falloff_mode"
    bl_label = "Falloff Mode"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    surface: BoolProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        context.scene.tool_settings.use_proportional_connected = self.surface
        return {'FINISHED'}


def draw_soft(layout, context):
    """Maya Soft Selection (Modeling Toolkit and the Tool Settings dock, step 106)."""
    from . import notices
    ts = context.scene.tool_settings
    row = layout.row(align=True)
    # One Maya setting for object and component mode (operators/soft_select.py, issue #15).
    row.prop(context.scene, "allset_soft_select", text="Soft Select")
    notices.tip(row, NOTE)          # Blender explanation as a tooltip, not a sentence (step 106)
    col = layout.column(align=True)
    col.active = context.scene.allset_soft_select
    col.prop(context.scene, "allset_soft_radius")
    row = col.row(align=True)
    row.label(text="Falloff mode")
    row.operator(ALLSET_OT_soft_falloff_mode.bl_idname, text="Volume",
                 depress=not ts.use_proportional_connected).surface = False
    row.operator(ALLSET_OT_soft_falloff_mode.bl_idname, text="Surface",
                 depress=ts.use_proportional_connected).surface = True
    sub = row.row(align=True)
    sub.enabled = False
    sub.operator("allset.menu_unavailable", text="Global").item = "Modeling Toolkit/Soft Selection/Global"
    col.prop(ts, "proportional_edit_falloff", text="Falloff curve")
    col.operator(ALLSET_OT_soft_select_reset.bl_idname, text="Reset")


# --- panel -----------------------------------------------------------------------------------------

def _camera_based_get(self):
    from .. import preferences
    return not preferences.get().select_through


def _camera_based_set(self, value):
    from .. import preferences
    preferences.get().select_through = not value


def _nearest_get(self):
    from .. import preferences
    return preferences.get().preselect_highlight


def _nearest_set(self, value):
    from .. import preferences
    preferences.get().preselect_highlight = value


def _grid(layout, items, context):
    grid = layout.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
    for label, path, icon in items:
        if label == "Extrude":
            grid.operator("allset.extrude", text=label, icon=icon)   # polyExtrudeFace (step 65)
        else:
            _button(grid, label, path, icon)


def _section(layout, idname, label, default_closed=False):
    header, body = layout.panel(idname, default_closed=default_closed)
    header.label(text=label)
    return body


def draw(layout, context):
    wm = context.window_manager
    # selection mode: Multi-Component + Object / Vertex / Edge / Face / UV
    edit = _mesh_mode(context)
    sel = list(context.scene.tool_settings.mesh_select_mode)
    multi = layout.row()
    multi.operator("allset.component_mode", text="Multi-Component",
                   depress=edit and all(sel)).type = 'MULTI'
    row = layout.row(align=True)
    row.scale_x = row.scale_y = 1.3
    row.operator("allset.select_mode", text="", icon='OBJECT_DATAMODE',
                 depress=context.mode == 'OBJECT').mode = 'OBJECT'
    for comp, icon, i in COMPONENT_ICONS:
        row.operator("allset.component_mode", text="", icon=icon,
                     depress=edit and sel[i] and not all(sel)).type = comp
    uv = row.row(align=True)
    uv.enabled = False
    uv.operator("allset.menu_unavailable", text="", icon='UV').item = "Modeling Toolkit/UV"
    if edit:
        n, unit = _selected_count(context)
        row = layout.row()
        row.alignment = 'CENTER'
        plural = {"vertex": "vertices"}.get(unit, unit + "s") if n != 1 else unit
        row.label(text=f"{n} {plural} selected")

    tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False) if context.workspace else None
    col = layout.column(align=True)
    for label, idname in PICK:
        col.operator("wm.tool_set_by_id", text=label, depress=tool is not None and tool.idname == idname,
                     icon='RADIOBUT_ON' if tool is not None and tool.idname == idname else 'RADIOBUT_OFF',
                     emboss=False).name = idname
    _grey(layout, "Modeling Toolkit/Highlight Backfaces", "Highlight Backfaces")
    layout.prop(wm, "allset_mtk_nearest", text="Highlight Nearest Component")
    layout.prop(wm, "allset_mtk_camera_based", text="Camera Based Selection")
    split = layout.split(factor=0.4)
    split.label(text="Symmetry")
    from .status_line import draw_symmetry
    draw_symmetry(split, context)
    _grey(layout, "Modeling Toolkit/Selection Constraint", "Selection Constraint: Off")
    _grey(layout, "Modeling Toolkit/Transform Constraint", "Transform Constraint: Off")

    body = _section(layout, "ALLSET_mtk_soft", "Soft Selection", default_closed=True)
    if body:
        draw_soft(body, context)
    body = _section(layout, "ALLSET_mtk_mesh", "Mesh")
    if body:
        _grid(body, MESH, context)
    body = _section(layout, "ALLSET_mtk_components", "Components")
    if body:
        _grid(body, COMPONENTS, context)
    body = _section(layout, "ALLSET_mtk_tools", "Tools")
    if body:
        _grid(body, TOOLS, context)
    from ..operators import quad_draw
    if tool is not None and tool.idname == quad_draw.TOOL and edit:
        from . import mesh_tools_poly
        body = _section(layout, "ALLSET_mtk_quad_draw", "Quad Draw Options")
        if body:
            mesh_tools_poly.draw_quad_draw(body, context)
            live = _section(body, "ALLSET_mtk_quad_live", "Live Constraint Options", default_closed=True)
            if live:
                mesh_tools_poly.draw_live(live, context)
            body.operator("allset.poly_tools_reset", text="Reset Settings").kind = 'QUAD_DRAW'
            shortcuts = _section(body, "ALLSET_mtk_quad_shortcuts", "Keyboard/Mouse Shortcuts", default_closed=True)
            if shortcuts:
                mesh_tools_poly.draw_shortcuts(shortcuts, mesh_tools_poly.QUAD_DRAW_SHORTCUTS)


# Drawn by the dock's Modeling Toolkit tab (channel_box.ALLSET_PT_dock_modeling_toolkit, step 99).
classes = (ALLSET_OT_soft_select_reset, ALLSET_OT_soft_falloff_mode)


def register():
    notices.PANEL_NOTICES.update(GREY)
    notices.NOTICES.update(MENU_NOTICES)
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.allset_soft_radius = FloatProperty(
        name="Falloff radius", description="Soft selection radius in Maya units (Blender: Proportional Size)",
        get=_radius_get, set=_radius_set, min=0.0, soft_max=100.0, precision=3)
    wm = bpy.types.WindowManager
    wm.allset_mtk_camera_based = BoolProperty(
        name="Camera Based Selection", get=_camera_based_get, set=_camera_based_set,
        description="Marquee selects only components facing the camera (Maya Workflow Kit preference "
                    "\"Marquee Selects Hidden Components\" off)")
    wm.allset_mtk_nearest = BoolProperty(
        name="Highlight Nearest Component", get=_nearest_get, set=_nearest_set,
        description="Highlight the component under the mouse before clicking (Maya Workflow Kit preference)")


def unregister():
    wm = bpy.types.WindowManager
    del wm.allset_mtk_nearest
    del wm.allset_mtk_camera_based
    del bpy.types.Scene.allset_soft_radius
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    for key in GREY:
        notices.PANEL_NOTICES.pop(key, None)
    for key in MENU_NOTICES:
        notices.NOTICES.pop(key, None)
