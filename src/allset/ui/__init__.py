# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya-style UI: Channel Box, Layer Editor, Attribute Editor, Outliner (3D View
sidebar), menu bar + menu sets, Status Line (top bar), Shelf (strip under it), Time
Slider + Range Slider (Timeline header), viewport panel menus (3D View header), Maya grid, view furniture and selection wire (3D View),
Tool Box (3D View toolbar) and the Maya dock areas / floating panels (maya_dock).

Blender's Python UI can't replace every C-drawn part; the modules note where they work around it.
"""

from . import draw_safe  # noqa: F401  menu draws that survive a missing operator
from . import (attribute_editor, cb_channels, cb_points, workspaces, editor_chrome, file_project, script_editor, input_line, graph_editor, graph_units, graph_view, hypershade, render_view, channel_box, dock_tabs, layer_editor, maya_grid, maya_outliner, menu_sets, outliner_sets, notices, outliner,
               creation_inputs, in_view, manipulator, mesh_tools, modeling_toolkit, uv_toolkit, paint_weights, weight_numbers, panel_menus, camera_tools, set_driven_key, shelf, selection_wire, component_colors, status_line, time_slider,
               tool_settings, toolbox, view_furniture, view_message, range_bar, status_icons, kit_icons, panel_toolbar, maya_dock, soft_overlay, save_prompt, scene_carry, armature_mode_pulse)
from . import mesh_tools_poly  # #30
from . import mesh_tools_loop  # #31
from . import uv_display  # UV Editor display keys / Move UV Shell
from . import uv_shell_preview  # UV shell pre-selection highlight
from . import uv_hud  # UV Editor heads-up displays (Isolate Select / UV Position / UV Statistics)
from . import hs_drag  # Hypershade swatch MMB drag
from . import ghosting  # Maya ghosting (Visualize)
from . import reference_editor  # Maya Reference Editor window
from . import outliner_joints  # kit skeleton rows read their root joint (#155)
from . import outliner_order  # Maya Outliner order (startup cameras first, creation order)
from . import marked_window, component_editor, shape_editor, connection_editor  # #119
from . import hotkey_editor  # #121: Maya Hotkey Editor window
from . import maya_prefs  # #121: Maya Preferences window
from . import window_places  # #203: kit windows reopen at their last size and place
from . import smart_extrude
from . import interactive_tool  # Create > Polygon Primitives > Interactive Creation tool (#225)
from . import maya_joints  # joints drawn like Maya's in the Maya layout views
from . import hypergraph  # Hypergraph: Hierarchy window (#232)
from . import skin_tools  # Skin Tools window: skin weight layers
from . import ipr_window  # IPR in its own window
from . import graph_keys_draw  # bigger Graph Editor keys
from . import uv_manipulator  # Maya-style Move / Rotate / Scale handles in the UV Editor
from . import in_view_editor, attribute_fields, option_editor, bridge_editor
from . import trax_editor  # Trax Editor: NLA Editor with the Maya menu bar + clip library (#287)

_modules = (window_places, status_icons, kit_icons, notices, input_line, cb_points, channel_box, cb_channels, creation_inputs, layer_editor, attribute_editor, outliner, menu_sets, workspaces, file_project, status_line, shelf,
            time_slider, panel_menus, panel_toolbar, camera_tools, interactive_tool, maya_grid, view_furniture, selection_wire, maya_joints, component_colors, ghosting, toolbox, dock_tabs, maya_outliner, outliner_joints, outliner_sets, outliner_order,
            paint_weights, weight_numbers, manipulator, set_driven_key, modeling_toolkit, mesh_tools, mesh_tools_poly, mesh_tools_loop, in_view, uv_toolkit, uv_display, uv_shell_preview, uv_hud, uv_manipulator, hypershade, hs_drag, render_view, graph_editor, graph_units, graph_view, graph_keys_draw, editor_chrome, script_editor, reference_editor, marked_window, component_editor, shape_editor, connection_editor, hypergraph, hotkey_editor, maya_prefs, skin_tools, ipr_window,
            view_message, range_bar, tool_settings, maya_dock, soft_overlay, save_prompt, scene_carry, armature_mode_pulse, smart_extrude, trax_editor, in_view_editor, attribute_fields, option_editor, bridge_editor)


# Modules registered so far (#198 #199): a failed register takes these back and raises; unregister takes
# back exactly these, carrying on past a module that raises.
_done = []


def register():
    from .. import safe_reg
    safe_reg.register_all(_modules, _done)


def unregister():
    from .. import safe_reg
    safe_reg.unregister_all(_done)
