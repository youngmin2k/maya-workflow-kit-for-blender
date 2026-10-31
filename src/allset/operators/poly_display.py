# SPDX-License-Identifier: GPL-3.0-or-later
"""Display > Polygons, the items that are not check boxes.

Maya sets polygon display on the selected meshes (polyOptions); Blender keeps it on each 3D View's overlays, drawn on
the meshes in edit mode. Both act on the 3D View the menu reads (``ui/status_line.view3d_space``).

- Normals Size...: Maya's small floating window with the normal length slider (polyOptions -sizeNormal), which
  changes the normals while it is dragged and stays open until it is closed. The kit window (``ui/marked_window``,
  like the Game Exporter) shows the overlay's Normal Size (``View3DOverlay.normals_length``, Blender units) through
  ``WindowManager.allset_normals_size``, so the 3D View follows the slider; OK closes it. A popup dialog would close
  at the first click outside it. Blender's own slider stops at 0.01 (soft min, 2 decimals); the kit's goes down to
  0.001 with 3 decimals (user request: small meshes need shorter normals).
- Reset Display: Maya puts the polygon display options back to their defaults = the overlays this menu sets, back to
  Blender 5.2's factory values.
- Vertex Size... / Edge Width...: Blender theme preferences (3D Viewport > Vertex Size / Edge Width). The kit opens
  Preferences > Themes with its search field set to the setting (Blender 5.2 lists the theme sections folded), and
  never writes the preference itself (#43).
"""

import bpy
from bpy.props import FloatProperty, StringProperty

from .. import results

# Blender 5.2 factory startup, Layout 3D View: (overlay or shading, property, value)
FACTORY = (
    ("overlay", "show_face_normals", False),
    ("overlay", "show_vertex_normals", False),
    ("overlay", "show_split_normals", False),
    ("overlay", "normals_length", 0.1),
    ("overlay", "show_edge_sharp", True),
    ("overlay", "show_edge_crease", True),
    ("overlay", "show_edge_seams", True),
    ("overlay", "show_face_center", False),
    ("shading", "show_backface_culling", False),
)

KIND = "NORMALS_SIZE"          # ui/marked_window.KINDS
PLACE = f"marked:{KIND}"       # the window's name in ui/window_places (marked_window.open_window names it so)
WINDOW_PX = (340, 120)         # first-open window size at UI scale 1 (Maya's window is one slider row)
WINDOW_MARGIN_PX = 60          # from the top left corner of the largest area (more than window_places.MIN_MARGIN)


def _space(op, context):
    from ..ui.status_line import view3d_space
    space = view3d_space(context)
    if space is None:
        op.report({'WARNING'}, "No 3D View to display polygons in")
    return space


def first_place(context):
    """The window's rect (screen px) the first time it opens: small, at the top left of the largest area. Later
    opens reuse the place it was left at (``ui/window_places``); a plain area copy would be as big as that area."""
    window = context.window
    area = max(window.screen.areas, key=lambda a: a.width * a.height, default=None)
    if area is None:
        return None
    scale = context.preferences.system.ui_scale or 1.0
    w, h = int(WINDOW_PX[0] * scale), int(WINDOW_PX[1] * scale)
    return (window.x + area.x + WINDOW_MARGIN_PX, window.y + area.y + area.height - h - WINDOW_MARGIN_PX, w, h)


class ALLSET_OT_normals_size(bpy.types.Operator):
    """Maya Display > Polygons > Normals Size: the length of the face and vertex normals drawn in the 3D View"""
    bl_idname = "allset.normals_size"
    bl_label = "Normals Size"

    def execute(self, context):
        from ..ui import marked_window, window_places
        if context.window is None or _space(self, context) is None:
            return {'CANCELLED'}
        if window_places.place(PLACE) is None:
            rect = first_place(context)
            if rect is not None:
                window_places.remember(PLACE, rect)
        if marked_window.open_window(context, KIND) is None:
            if not window_places.deferred():     # opens on a later tick (#203)
                self.report({'ERROR'}, "Could not open the Normals Size window")
            return {'CANCELLED'}
        return {'FINISHED'}


SIZE_PROP = "allset_normals_size"      # WindowManager: the window's slider
SIZE_SOFT_MIN = 0.001
SIZE_PRECISION = 3


def _get_size(_wm):
    from ..ui.status_line import view3d_space
    space = view3d_space(bpy.context)
    return space.overlay.normals_length if space is not None else 0.1


def _set_size(_wm, value):
    from ..ui.status_line import view3d_space
    space = view3d_space(bpy.context)
    if space is not None:
        space.overlay.normals_length = value


def draw(layout, context):
    """The Normals Size window: the slider (live in the 3D View), then OK."""
    from ..ui.status_line import view3d_space
    space = view3d_space(context)
    if space is None:
        layout.label(text="No 3D View to display polygons in")
    else:
        layout.prop(context.window_manager, SIZE_PROP, text="Normals Size", slider=True)
        layout.label(text="Blender draws normals on meshes in edit mode.")
    layout.operator("allset.marked_window_close", text="OK")


class ALLSET_PT_normals_size(bpy.types.Panel):
    bl_idname = "ALLSET_PT_normals_size"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"            # = drawn by the Properties Tool tab
    bl_label = "Normals Size"
    bl_options = {'HIDE_HEADER'}
    bl_order = -300

    @classmethod
    def poll(cls, context):
        from ..ui import marked_window
        return marked_window.context_kind(context) == KIND

    def draw(self, context):
        draw(self.layout, context)


class ALLSET_OT_poly_display_reset(bpy.types.Operator):
    """Maya Display > Polygons > Reset Display: normals, edge and face display back to their defaults"""
    bl_idname = "allset.poly_display_reset"
    bl_label = "Reset Display"

    def execute(self, context):
        space = _space(self, context)
        if space is None:
            return {'CANCELLED'}
        for owner, prop, value in FACTORY:
            setattr(getattr(space, owner), prop, value)
        results.result(self, "Polygon display reset")
        return {'FINISHED'}


def search_preferences(text, tries=20):
    """Put ``text`` in the search field of the open Preferences window (it opens after the operator returns)."""
    state = {"n": tries}

    def tick():
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'PREFERENCES':
                    area.spaces.active.search_filter = text
                    area.tag_redraw()
                    return None
        state["n"] -= 1
        return 0.05 if state["n"] > 0 else None
    bpy.app.timers.register(tick, first_interval=0.0)


class ALLSET_OT_theme_setting(bpy.types.Operator):
    """Open Preferences > Themes on one 3D Viewport setting (Maya's Vertex Size / Edge Width are Blender theme
    preferences)"""
    bl_idname = "allset.theme_setting"
    bl_label = "Theme Setting"

    name: StringProperty(name="Setting", options={'SKIP_SAVE'})

    def execute(self, context):
        bpy.ops.screen.userpref_show('INVOKE_DEFAULT', section='THEMES')
        if self.name:
            search_preferences(self.name)
        return {'FINISHED'}


classes = (ALLSET_OT_normals_size, ALLSET_PT_normals_size, ALLSET_OT_poly_display_reset, ALLSET_OT_theme_setting)


def register_props():
    bpy.types.WindowManager.allset_normals_size = FloatProperty(
        name="Normals Size", description="Length of the normals drawn in the 3D View (Blender units)",
        min=0.00001, max=100000.0, soft_min=SIZE_SOFT_MIN, soft_max=2.0, precision=SIZE_PRECISION, step=1,
        get=_get_size, set=_set_size)


def unregister_props():
    if hasattr(bpy.types.WindowManager, SIZE_PROP):
        delattr(bpy.types.WindowManager, SIZE_PROP)
