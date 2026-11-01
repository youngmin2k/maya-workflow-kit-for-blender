# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Outliner chrome on Blender's Outliner.

Maya's Outliner has a menu bar Display / Show / Help and a search field.
Outliners set up the Maya way (the Maya Workflow Kit layout and Windows > Outliner:
View Layer mode, no collection rows, no object contents; ``is_maya_outliner``) get that header:
``OUTLINER_HT_header.draw`` is swapped while the kit is enabled and restored on unregister; other
Outliners draw as usual. The rows themselves are Blender's (the C list): Maya's grey camera rows
(persp/top/front/side) and default sets have no Blender objects behind them.
"""

import bpy

from . import chrome, own_draw

HELP_URL = "https://docs.blender.org/manual/en/5.2/editors/outliner/index.html"
MENU_BAR = (("Display", "ALLSET_MT_outliner_display"), ("Show", "ALLSET_MT_outliner_show"),
            ("Help", "ALLSET_MT_outliner_help"))


def is_maya_outliner(space):
    return (space is not None and space.type == 'OUTLINER' and space.display_mode == 'VIEW_LAYER'
            and not space.use_filter_collection and not space.use_filter_object_content)


def setup(space):
    """Maya Outliner filters (DAG only, from the world; no eye / mode column: Maya hides with H)."""
    space.display_mode = 'VIEW_LAYER'
    space.use_filter_object_content = False
    space.use_filter_collection = False
    space.use_filter_children = True
    space.show_restrict_column_render = False
    space.show_restrict_column_hide = False
    space.show_mode_column = False      # Maya has no mode column (Blender shows it in edit mode)
    space.use_sort_alpha = False        # Maya lists the DAG in creation order, startup cameras first


class ALLSET_MT_outliner_display(bpy.types.Menu):
    """Maya Outliner Display menu"""
    bl_label = "Display"

    def draw(self, context):
        sp, lay = context.space_data, self.layout
        lay.prop(sp, "use_filter_children", text="Children (DAG Hierarchy)")
        lay.prop(sp, "use_sort_alpha", text="Sort Alphabetically")
        lay.prop(sp, "show_restrict_column_hide", text="Visibility Column")
        lay.separator()
        # Maya Display > Shapes: turning shapes on makes this a Blender Outliner again (contents shown)
        lay.prop(sp, "use_filter_object_content", text="Shapes")


class ALLSET_MT_outliner_show(bpy.types.Menu):
    """Maya Outliner Show menu: object type filters"""
    bl_label = "Show"

    def draw(self, context):
        sp, lay = context.space_data, self.layout
        lay.prop(sp, "use_filter_object", text="Objects")
        col = lay.column()
        col.active = sp.use_filter_object
        for prop, label in (("use_filter_object_mesh", "Geometry"), ("use_filter_object_armature", "Joints"),
                            ("use_filter_object_empty", "Groups / Locators"), ("use_filter_object_light", "Lights"),
                            ("use_filter_object_camera", "Cameras"), ("use_filter_object_others", "Others")):
            col.prop(sp, prop, text=label)


class ALLSET_MT_outliner_help(bpy.types.Menu):
    bl_label = "Help"

    def draw(self, context):
        self.layout.operator("wm.url_open", text="Help on Outliner").url = HELP_URL


def _draw(self, context):
    space = context.space_data
    if not is_maya_outliner(space):
        return own_draw.original("OUTLINER_HT_header", _draw)(self, context)
    layout = self.layout
    from . import maya_dock      # Maya's dotted handle: tear the Outliner off / dock it back
    layout.operator("allset.dock_handle", text=maya_dock.HANDLE[:8], emboss=False)
    chrome.menu_bar(layout, MENU_BAR)
    layout.prop(space, "filter_text", text="", icon='VIEWZOOM', placeholder="Search...")


classes = (ALLSET_MT_outliner_display, ALLSET_MT_outliner_show, ALLSET_MT_outliner_help)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    own_draw.swap("OUTLINER_HT_header", _draw)   # Blender's own draw only


def unregister():
    own_draw.restore("OUTLINER_HT_header", _draw)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
