# SPDX-License-Identifier: GPL-3.0-or-later
"""Set Driven Key window drawn in the dock under the Channel Box.

Layout of Maya's window: a "Driver" bar, node list |
attribute list; a "Driven" bar, node list | attribute list; buttons Key · Load Driver · Load Driven · Close.
Drawn by the Layer Editor panel while the window is open (its place in the dock), so the Channel Box stays
above it for posing. The lists are fixed-height scrolling UILists like Maya's (all ten channels in plain
rows pushed the buttons out of the sidebar in a GUI shot).
"""

import bpy

from ..operators import driven_key as sdk

ROWS = 4
MIN_ROWS = 2
BAR = "Driver", "Driven"
HELP = ("Pose in the Channel Box, then Key",)
# #77: at UI scale 1.5 the window ran out of the dock under a full Channel Box (Load Driver / Load Driven /
# Key below the region's bottom, GUI shot). The lists give up rows (down to MIN_ROWS) so the buttons stay in the dock:
# UI units the window needs besides its list rows (separator, the two bars, the lists' grips and spacing, the 2 x 2
# button grid; the help line only when there is room), checked on GUI shots at UI scale 1.0 / 1.25 / 1.5.
FIXED_UNITS = 9.0
HELP_UNITS = 1.2
_room = {}          # dock area pointer -> UI units under the Channel Box (maya_dock draw, the same redraw)


def remember_room(context, cb_units):
    """The Channel Box above took ``cb_units`` (its ``body`` estimate) of the dock region: what is left is ours."""
    area, region = context.area, context.region
    if area is None or region is None or cb_units is None or region.height <= 1:
        return
    from . import channel_box
    from .toolbar_fit import unit
    system = context.preferences.system
    u = unit(system.ui_scale or 1.0, system.pixel_size)
    _room[area.as_pointer()] = region.height / u - cb_units - channel_box.PANE_TOP


def list_rows(room):
    """Rows of each list when ``room`` UI units are left (None: unknown = 4)."""
    if room is None:
        return ROWS
    return max(MIN_ROWS, min(ROWS, int((room - FIXED_UNITS) / 2)))


class ALLSET_UL_sdk_attrs(bpy.types.UIList):
    """Attribute rows: a click picks (Driven: Ctrl adds); selected rows are drawn pressed."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0):
        driver = active_propname == "driver_items_index"
        selected = item.key == data.driver_attr if driver else item.key in sdk.driven_keys(data)
        op = layout.operator("allset.sdk_pick", text=item.label, emboss=selected, depress=selected)
        op.which, op.key = ('DRIVER' if driver else 'DRIVEN'), item.key

    def draw_filter(self, context, layout):
        pass


class ALLSET_UL_sdk_nodes(bpy.types.UIList):
    """Driven node rows (the node whose attributes the right list shows is pressed). A loaded object's
    blendShape and constraint nodes follow it (Maya: any keyable attribute can be driven)."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0):
        node = sdk.item_node(item)
        selected = index == data.driven_index
        op = layout.operator("allset.sdk_pick", text=sdk.node_label(node) if node is not None else "?",
                             emboss=selected, depress=selected)
        op.which, op.index = 'NODE', index

    def draw_filter(self, context, layout):
        pass


def _bar(layout, text):
    box = layout.box()
    box.scale_y = 0.6
    box.label(text=text)


def draw(layout, context):
    st = sdk.state(context)
    room = _room.get(context.area.as_pointer()) if context.area is not None else None
    rows = list_rows(room)
    layout.separator(type='LINE')
    _bar(layout, BAR[0])
    split = layout.split(factor=0.5, align=True)
    left = split.box().column(align=True)
    drv = sdk.driver_node(st)
    if drv is not None:
        left.label(text=sdk.node_label(drv))
    split.template_list("ALLSET_UL_sdk_attrs", "driver", st, "driver_items", st, "driver_items_index",
                        rows=rows, maxrows=rows)

    _bar(layout, BAR[1])
    split = layout.split(factor=0.5, align=True)
    split.template_list("ALLSET_UL_sdk_nodes", "driven_nodes", st, "driven", st, "driven_index",
                        rows=rows, maxrows=rows)
    split.template_list("ALLSET_UL_sdk_attrs", "driven", st, "driven_items", st, "driven_items_index",
                        rows=rows, maxrows=rows)

    # Maya's one button row (Key · Load Driver · Load Driven · Close) as a 2 x 2 grid in the same reading
    # order: four buttons in one sidebar row cut "Load Driver" to "Load Dr..." (GUI shot).
    grid = layout.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
    grid.operator("allset.sdk_key", text="Key")
    grid.operator("allset.sdk_load", text="Load Driver").which = 'DRIVER'
    grid.operator("allset.sdk_load", text="Load Driven").which = 'DRIVEN'
    grid.operator("allset.sdk_close", text="Close")
    if room is None or room - FIXED_UNITS - 2 * rows >= HELP_UNITS:
        from . import chrome
        chrome.wrapped(layout, HELP, alignment='LEFT')


classes = (ALLSET_UL_sdk_attrs, ALLSET_UL_sdk_nodes)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    _room.clear()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
