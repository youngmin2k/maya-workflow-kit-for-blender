# SPDX-License-Identifier: GPL-3.0-or-later
"""Add-on preferences (Preferences > Add-ons > Maya Workflow Kit).

Options for Maya units and parent mode
from step 10. Only this add-on's own settings live here: since step 130 no option writes Blender's
preferences (the navigation / undo / panel / auto key / theme / splash / density / font / wire presets are gone).
"""

import json
import os

import bpy

from . import i18n

# True while ``register()`` puts saved settings back (see ``restore_backup``): no update callback runs then, as at a
# normal start where Blender loads the saved values without calling them.
_restoring = [False]


def _quiet(fn):
    def update(self, context):
        if not _restoring[0]:
            fn(self, context)
    update.__name__ = fn.__name__
    return update


@_quiet
def _redraw_tools(_self, context):
    wm = getattr(context, 'window_manager', None)
    for window in wm.windows if wm else ():
        for area in window.screen.areas:
            area.tag_redraw()


class ALLSET_AddonPreferences(bpy.types.AddonPreferences):
    # Must equal the top-level package name: "bl_ext.<repo>.allset" as an
    # extension, "allset" as a legacy add-on.
    bl_idname = __package__

    # Set once "Maya" was activated automatically on first enable, so later
    # starts respect a different keymap the user picked (step 2).
    keymap_auto_activated: bpy.props.BoolProperty(options={'HIDDEN'})

    # Maya mode on/off (switch.py, step 60), kept across restarts. Off after install: enabling the
    # extension changes nothing until the user opts in (welcome dialog / button / switch; step 115).
    maya_mode: bpy.props.BoolProperty(name="Maya Mode", default=False, options={'HIDDEN'})
    # Edit-mode marquee/lasso also selects occluded components, like Maya.
    select_through: bpy.props.BoolProperty(
        name="Marquee Selects Hidden Components",
        description="In mesh edit mode, box and lasso selection also pick vertices, edges and faces "
                    "behind the surface, like Maya (Camera based selection off). X-ray is switched "
                    "on only while dragging",
        default=True)
    # Maya's Scale tool default: on
    prevent_negative_scale: bpy.props.BoolProperty(
        name="Prevent Negative Scale",
        description="Stop mesh component scaling at zero on every handle of the Maya Scale tool "
                    "(one axis, plane or centre); object scaling is not affected",
        default=True, update=_redraw_tools)
    # Maya Move tool Transform Constraint (default Off)
    transform_constraint: bpy.props.EnumProperty(
        name="Transform Constraint",
        description="In mesh edit mode the Move tool slides components along their edges or the surface",
        items=(('NONE', "Off", "Move components freely"),
               ('EDGE', "Edge", "Slide components along their edges"),
               ('SURFACE', "Surface", "Move components along the surface of the mesh")),
        default='NONE', update=_redraw_tools)
    uv_shell_preview: bpy.props.BoolProperty(
        name="UV Shell Pre-selection",
        description="In the UV Editor, while clicks pick whole UV shells, fill the shell under the mouse in the "
                    "pre-selection colour before you click",
        default=True)
    # Maya preSelectHilite true.
    preselect_highlight: bpy.props.BoolProperty(
        name="Pre-selection Highlight",
        description="In mesh edit mode (select and Move / Rotate / Scale tools), highlight the vertex, edge or face "
                    "under the mouse before clicking (Maya)",
        default=True)
    # Maya selectPrefPriorityMode "animation", ignoreSelectionPriority false.
    select_priority: bpy.props.BoolProperty(
        name="Selection Priority",
        description="In object mode, a click picks IK handles, then joints (armatures), then curves before meshes "
                    "under the mouse, like Maya's selection priority",
        default=True)
    # Step 217: bone collections = the rigger's "animator controls" set.
    pick_walk_skip_hidden_collections: bpy.props.BoolProperty(
        name="Pick Walk Skips Hidden Bone Collections",
        description="In Pose mode the arrow keys walk past bones whose bone collections are all hidden (Rigify MCH / "
                    "DEF / ORG bones), to the nearest shown parent, child or sibling; a generated Rigify rig follows "
                    "its controls' ORG hierarchy (upper_arm_fk.L Up = shoulder.L). Maya walks into hidden nodes: "
                    "bones hidden one by one (H) are still walked into, and an armature with controller tags "
                    "(Control > Tag As Controller) follows its controller hierarchy instead. Off: plain hierarchy",
        default=True)
    # PR #125 extras with no Maya counterpart (no Maya 2022-2027 viewport header has a mode picker or a pulse):
    # off by default.
    armature_mode_header: bpy.props.BoolProperty(
        name="Armature Mode Picker",
        description="Show an Object / Edit Joints / Pose Joints picker at the start of the main viewport header "
                    "while a skeleton is active (not part of Maya)",
        default=False)
    armature_mode_pulse: bpy.props.BoolProperty(
        name="Pulse Armature Mode",
        description="Softly pulse the viewport header's mode button while a skeleton is selected (not part of Maya)",
        default=False)
    # First start (step 42): welcome dialog shown once.
    welcome_done: bpy.props.BoolProperty(options={'HIDDEN'})
    # step 260 (#177): how often the welcome dialog opened without "Make Blender feel like Maya" being clicked
    welcome_shown: bpy.props.IntProperty(options={'HIDDEN'})

    start_in_maya_layout: bpy.props.BoolProperty(
        name="Start in Maya Layout",
        description="When Blender starts without a file in Maya mode, open a new scene in the Maya layout",
        default=False)

    # Step 138 (#63): Maya's UI doesn't come from the scene file: opening a file
    # shows the Maya layout (ui/scene_carry.py).
    maya_layout_on_open: bpy.props.BoolProperty(
        name="Keep Maya Layout When Opening Files",
        description="In Maya mode, a file opened in another layout is shown in the Maya layout (its own Maya layout "
                    "workspace when it has one). The file's other workspaces stay",
        default=True)

    lock_ortho_tumble: bpy.props.BoolProperty(
        name="Lock Tumble in Ortho Views",
        description="Alt+LMB does nothing in top/front/side orthographic views (Maya)",
        default=True)

    # Channel Box virtual slider.
    cb_speed: bpy.props.EnumProperty(
        name="Slider Speed", default='MEDIUM',
        items=(('SLOWEST', "Slowest", "x0.01"), ('SLOW', "Slow", "x0.1"),
               ('MEDIUM', "Medium", "x1"), ('FAST', "Fast", "x10")))
    cb_hyperbolic: bpy.props.BoolProperty(
        name="Hyperbolic", description="Value change accelerates with drag distance")

    # Create > Polygon Primitives > Interactive Creation / Exit On Completion (off / on by default, like Maya;
    # operators/interactive_create.py)
    interactive_creation: bpy.props.BoolProperty(
        name="Interactive Creation",
        description="Polygon primitives from the Create menu and shelf are drawn in a view: drag to place and size")
    exit_on_completion: bpy.props.BoolProperty(
        name="Exit On Completion", default=True,
        description="Interactive Creation switches to the Select tool after one primitive; off, the tool keeps drawing primitives")

    # Graph Editor View > Snap Time To Selection (default off; Alt+/ toggles it;
    # step 92).
    snap_time_to_selection: bpy.props.BoolProperty(
        name="Snap Time To Selection",
        description="Selecting keys in the Graph Editor moves the current time to the earliest selected key")
    # Graph Editor View > Auto Frame / Auto Frame Time / Curve Name (defaults: on / off / Never;
    # ui/graph_view.py, step 150).
    graph_auto_frame: bpy.props.BoolProperty(
        name="Auto Frame", default=True,
        description="When the selection changes, the Graph Editor refits its value axis to the curves it shows "
                    "(Maya View > Auto Frame)")
    # Dope Sheet View > Auto Frame (Maya displayAutoFitItem, factory off in the Dope Sheet; step 166)
    dope_auto_frame: bpy.props.BoolProperty(
        name="Dope Sheet Auto Frame",
        description="When the selection changes, the Dope Sheet frames all the keys it shows (Maya Dope Sheet "
                    "View > Auto Frame)")
    graph_auto_frame_time: bpy.props.BoolProperty(
        name="Auto Frame Time",
        description="When the selection changes, the Graph Editor also refits its time axis to the curves it shows "
                    "(Maya View > Auto Frame Time)")
    graph_curve_names: bpy.props.EnumProperty(
        name="Curve Name", default='NEVER',
        description="Write each curve's Maya name (pCube1.translateX) beside its last key in the Graph Editor",
        items=(('ALWAYS', "Always", "Name every curve"), ('NEVER', "Never", "No curve names"),
               ('ACTIVE', "Active Only", "Name the selected curves")))

    # Graph Editor L = value lines (zero line + the selected curves' lowest / highest value), toolbar Unconstrained
    # drag (on = middle drags move keys in time and value; off = the first move picks one axis)
    graph_value_lines: bpy.props.BoolProperty(
        name="Value Lines",
        description="Draw the zero line and the lowest / highest value of the selected curves in the Graph Editor")
    graph_unconstrained_drag: bpy.props.BoolProperty(
        name="Unconstrained Drag", default=True,
        description="Middle-mouse drags in the Graph Editor move keys in time and value; off, the first move "
                    "picks time or value")
    graph_scale_manipulator: bpy.props.BoolProperty(
        name="Scale Keys Manipulator", default=True,
        description="With the Scale Keys tool (r) the Graph Editor draws a box around the selected keys: drag a "
                    "side to scale them in time or value, a corner for both")

    # Graph Editor depth 2 (step 198): View > Show Buffer Curves (factory off),
    # Curves > Default Tangent Weight (factory Non-weighted), Retime Tool Snap On Frame (factory off), Edit > Set Curve
    # Colors... rules (Maya curveRGBColor: attribute name -> colour; JSON list of [attribute, r, g, b]).
    graph_show_buffers: bpy.props.BoolProperty(
        name="Show Buffer Curves",
        description="Draw each buffered curve's snapshot behind it in the Graph Editor (Maya View > Show Buffer Curves)")
    default_tangent_weight: bpy.props.EnumProperty(
        name="Default Tangent Weight", default='NON_WEIGHTED',
        items=(('NON_WEIGHTED', "Non-weighted Tangents", "New animation curves keep every tangent a third of the "
                "way to the next key"),
               ('WEIGHTED', "Weighted Tangents", "New animation curves have tangents whose length can change")),
        description="Tangent weight of new animation curves, keyed in any way (Maya Curves > Default Tangent Weight)")
    retime_snap_on_frame: bpy.props.BoolProperty(
        name="Snap On Frame",
        description="Retime markers and their drags land on whole frames (Maya Retime Tool setting)")
    curve_color_rules: bpy.props.StringProperty(
        name="Curve Colors", default="",
        description="Colour rules by attribute name (Maya Edit > Set Curve Colors...)")

    # Script Editor History menu (defaults:
    # Batch Render Messages / Line numbers in errors on,
    # the rest off, History Output Show Both). Read by command_line/runner.py (step 216).
    se_batch_render_messages: bpy.props.BoolProperty(
        name="Batch Render Messages", default=True,
        description="Show batch rendering messages in the Script Editor history (Maya; Blender's renders "
                    "write their messages to the system console)")
    se_echo_all: bpy.props.BoolProperty(
        name="Echo All Commands",
        description="Write every command run from a menu, shelf or marking menu into the Script Editor history "
                    "(as the Python call the kit runs)")
    se_line_numbers: bpy.props.BoolProperty(
        name="Line numbers in errors", default=True,
        description="Error messages name the script line the error happened on")
    se_stack_trace: bpy.props.BoolProperty(
        name="Show Stack Trace",
        description="An error writes the whole Python traceback into the Script Editor history")
    se_suppress_results: bpy.props.BoolProperty(
        name="Suppress Command Results", description="No \"# Result:\" lines in the Script Editor history")
    se_suppress_info: bpy.props.BoolProperty(
        name="Suppress Info Messages", description="No info messages in the Script Editor history")
    se_suppress_warnings: bpy.props.BoolProperty(
        name="Suppress Warning Messages", description="No warning messages in the Script Editor history")
    se_suppress_errors: bpy.props.BoolProperty(
        name="Suppress Error Messages", description="No error messages in the Script Editor history")
    se_suppress_stack_window: bpy.props.BoolProperty(
        name="Suppress Stack Window",
        description="Maya: no stack trace window on error (Blender has no such window: kept for Maya's menu)")
    se_suppress_dup_vars: bpy.props.BoolProperty(
        name="Suppress Duplicate Variable Messages",
        description="Maya: no warnings about redeclared MEL variables (the kit runs no MEL: kept for Maya's menu)")
    se_history_output: bpy.props.EnumProperty(
        name="History Output", default='BOTH',
        items=(('BOTH', "Show Both", "History lists MEL and Python results"),
               ('MEL', "Show MEL Only", "History lists MEL results only"),
               ('PYTHON', "Show Python Only", "History lists Python results only")))

    # Channel Box Channels > Sync Selection in Graph Editor / Sync Timeline Display (default off;
    # Maya Channel Box Channels menu, ui/cb_channels.py, step 158).
    cb_sync_graph: bpy.props.BoolProperty(
        name="Sync Selection in Graph Editor",
        description="Selecting channels in the Channel Box selects their curves, and S keys only the selected channels")
    cb_sync_timeline: bpy.props.BoolProperty(
        name="Sync Timeline Display",
        description="The Time Slider shows only the keys of the channels selected in the Channel Box")
    # Graph Editor Select > Curve / Key / In Tangent / Out Tangent (Maya selectType pick masks, factory all on;
    # Maya Graph Editor Select menu, operators/graph_key_menu.py, step 157).
    graph_select_curve: bpy.props.BoolProperty(
        name="Curve", default=True, description="Clicking or dragging in the Graph Editor can pick curves")
    graph_select_key: bpy.props.BoolProperty(
        name="Key", default=True, description="Clicking or dragging in the Graph Editor can pick keys")
    graph_select_in: bpy.props.BoolProperty(
        name="In Tangent", default=True, description="Clicking or dragging in the Graph Editor can pick in tangents")
    graph_select_out: bpy.props.BoolProperty(
        name="Out Tangent", default=True, description="Clicking or dragging in the Graph Editor can pick out tangents")
    # Tangents > Default In / Out Tangent (Maya keyTangent -global, factory Auto / Auto):
    # the tangents of the keys the kit sets (S, Shift+W/E/R, Channel Box keys, Auto Key). Blender's own preference
    # is never written (#40).
    default_in_tangent: bpy.props.EnumProperty(
        name="Default In Tangent", default='AUTO',
        items=(('AUTO', "Auto", "Maya Auto: Blender Auto Clamped"), ('SPLINE', "Spline", "Blender Auto"),
               ('LINEAR', "Linear", ""), ('CLAMPED', "Clamped", "Blender Auto Clamped"),
               ('FLAT', "Flat", "Level handles"), ('PLATEAU', "Plateau", "Blender Auto Clamped")),
        description="In tangent of the keys the kit sets (Maya Tangents > Default In Tangent)")
    default_out_tangent: bpy.props.EnumProperty(
        name="Default Out Tangent", default='AUTO',
        items=(('AUTO', "Auto", "Maya Auto: Blender Auto Clamped"), ('SPLINE', "Spline", "Blender Auto"),
               ('LINEAR', "Linear", ""), ('CLAMPED', "Clamped", "Blender Auto Clamped"),
               ('FLAT', "Flat", "Level handles"), ('PLATEAU', "Plateau", "Blender Auto Clamped"),
               ('STEPPED', "Stepped", "Blender Constant")),
        description="Out tangent of the keys the kit sets (Maya Tangents > Default Out Tangent)")

    # Top UI (step 7; Maya Windows > UI Elements).
    maya_top_bar: bpy.props.BoolProperty(
        name="Maya Menu Bar",
        description="Top bar shows the Maya menus, menu sets and Status Line instead of "
                    "Blender's menus and workspace tabs (Blender menus stay as submenus)",
        default=True)
    # Maya view furniture (step 46), in views whose Blender navigation gizmo is off.
    @_quiet
    def _update_navigation(self, context):
        from .ui import view_furniture
        if view_furniture._handle:       # Maya mode on (view_furniture registered)
            view_furniture.apply_navigation()

    maya_viewcube: bpy.props.BoolProperty(
        name="ViewCube", description="Maya ViewCube (or Blender's navigation gizmo, see Viewport Navigation) in "
                                     "the top right of the view", default=True, update=_update_navigation)
    # #209: Blender's navigation gizmo instead of the Maya ViewCube (ui/view_furniture.py)
    view_navigation: bpy.props.EnumProperty(
        name="Viewport Navigation",
        items=(('VIEWCUBE', "Maya ViewCube", "Maya ViewCube in the top right of the view (click a face to look "
                                             "along it)"),
               ('BLENDER', "Blender Navigation Gizmo", "Blender's navigation gizmo (axis ball, zoom / pan "
                                                        "buttons) in the top right of the view")),
        default='VIEWCUBE', update=_update_navigation,
        description="Navigation widget in the top right of the 3D View")
    maya_camera_names: bpy.props.BoolProperty(
        name="Camera Names", description="Maya camera name (persp, top -Y, ...) at the bottom of the view",
        default=True)
    @_quiet
    def _update_selection_wire(self, context):
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()

    @_quiet
    def _update_dock_colors(self, context):
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'PROPERTIES':
                    area.tag_redraw()

    # Maya wireframe on selected objects over shading (step 47).
    maya_selection_wire: bpy.props.BoolProperty(
        name="Selection Wireframe", description="Selected objects show their wireframe over shading, like "
                                                "Maya (lead light green, others white); in wireframe shading "
                                                "unselected objects are Maya's dark blue",
        default=True, update=_update_selection_wire)
    # Maya component colours in mesh edit mode (step 134).
    maya_component_colors: bpy.props.BoolProperty(
        name="Component Colors", description="Mesh edit mode shows Maya's component colors: light blue edges, "
                                              "purple / yellow vertices, orange edges and stippled faces",
        default=True, update=_update_selection_wire)
    # Maya grey docks (step 195): the dock areas are lifted from the theme's Properties grey to #444444
    maya_dock_colors: bpy.props.BoolProperty(
        name="Dock Colors", description="The Channel Box / Attribute Editor / Modeling Toolkit docks are drawn "
                                        "in Maya's lighter grey",
        default=True, update=_update_dock_colors)
    maya_view_axis: bpy.props.BoolProperty(
        name="View Axis", description="Maya axis triad in the bottom left of the view", default=True)
    # Maya in-view messages (on by default; step 72).
    in_view_messages: bpy.props.BoolProperty(
        name="In-View Messages", description="Short fading messages in the view when you group, hide, toggle "
                                             "object/component selection (F8), soft select or Make Live, like Maya",
        default=True)
    maya_panel_menus: bpy.props.BoolProperty(
        name="Panel Menus",
        description="3D View headers show Maya's panel menus (View, Shading, Lighting, Show, Renderer, "
                    "Panels) instead of Blender's (Blender menus stay as a submenu)",
        default=True)
    menu_set: bpy.props.EnumProperty(
        name="Menu Set", description="Maya menu set: which menus follow the common ones",
        items=lambda self, context: _menu_set_items(), default=0)
    show_status_line: bpy.props.BoolProperty(
        name="Status Line", description="Maya Status Line icons in the top bar", default=True)
    # Maya layout parity (step 49).
    maya_toolbox: bpy.props.BoolProperty(
        name="Maya Tool Box", description="3D View toolbars show Maya's Tool Box in every mode: Select, Lasso, "
                                          "Paint Select, Move, Rotate, Scale, the last other tool and quick layout "
                                          "buttons (other tools stay on keys, menus and the shelf)",
        default=True, update=_update_selection_wire)
    show_command_line: bpy.props.BoolProperty(
        name="Command Line", description="Python command line in the status bar", default=True)
    show_help_line: bpy.props.BoolProperty(
        name="Help Line", description="Maya-style help for the active tool in the status bar",
        default=True)

    # Marking menus and hotbox (step 9).
    marking_menu_style: bpy.props.EnumProperty(
        name="Marking Menus",
        description="How Maya marking menus are shown",
        items=(('ENGINE', "Maya Engine", "Maya-style marking menus: drag, flick, in-place submenus, "
                                          "option boxes"),
               ('PIE', "Blender Pies", "Blender pie menus (8 slots, submenus open new pies)")),
        default='ENGINE')
    hotbox_style: bpy.props.EnumProperty(
        name="Hotbox Style",
        items=(('ALL', "Zones and Menu Rows", ""), ('ZONES', "Zones Only", ""),
               ('CENTER', "Center Zone Only", "")),
        default='ALL')
    hotbox_all_sets: bpy.props.BoolProperty(
        name="Show All Menu Sets", description="Hotbox shows the menus of every menu set, not only "
                                               "the current one (on by default, like Maya)",
        default=True)

    # Shelf (step 12): current tab (factory file name or "USER:<name>").
    shelf_current: bpy.props.StringProperty(options={'HIDDEN'})

    # Maya project (operators/project.py, step 69): Blender has no projects, so the current
    # project folder and the Recent Projects list live here, like Maya keeps the workspace in its prefs.
    project_root: bpy.props.StringProperty(name="Current Project", subtype='DIR_PATH',
                                           description="Maya Workflow Kit project folder: file dialogs open in its scenes "
                                                       "folder, renders go to its images folder")
    recent_projects: bpy.props.StringProperty(options={'HIDDEN'})   # newline-separated, newest first
    # Autosave (operators/autosave.py): copies of the open scene in the project's autosave folder, like Maya's
    # Files/Projects > AutoSave. Blender's own auto save (a recovery file in the temp folder) is separate.
    autosave_enable: bpy.props.BoolProperty(
        name="Autosave", default=False,
        description="Save a copy of the scene every few minutes into the autosave folder (the scene's own file "
                    "is not touched)")
    autosave_interval: bpy.props.FloatProperty(
        name="Interval (minutes)", default=10.0, min=0.5, soft_max=120.0, precision=1,
        description="Minutes between autosaves")
    autosave_limit: bpy.props.BoolProperty(
        name="Limit Autosaves", default=False,
        description="Keep only the newest autosaves of each scene")
    autosave_count: bpy.props.IntProperty(
        name="Number of Autosaves", default=10, min=1, soft_max=100,
        description="How many autosaves of each scene are kept when Limit Autosaves is on")
    autosave_destination: bpy.props.EnumProperty(
        name="Autosave Destination", default='PROJECT',
        items=(('PROJECT', "Project", "The current project's autosave folder"),
               ('FOLDER', "Named Folder", "The folder set below")),
        description="Where autosaves go")
    autosave_folder: bpy.props.StringProperty(
        name="Autosave Folder", subtype='DIR_PATH',
        description="Autosave folder when the destination is Named Folder")
    # Maya option window values (operators/option_windows.py, step 103).
    option_settings: bpy.props.StringProperty(options={'HIDDEN'})   # JSON {window key: {field: value}}

    # Scene concepts (step 10).
    parent_mode: bpy.props.EnumProperty(
        name="Parent Mode", description="What P (Parent) does to the child's values",
        items=(('MAYA', "Maya", "Keep the world position and recompute the local values "
                                "relative to the parent (parent inverse = identity)"),
               ('BLENDER', "Blender", "Keep the local values; Blender stores a hidden parent "
                                      "inverse matrix")),
        default='MAYA')
    maya_naming: bpy.props.BoolProperty(
        name="Maya Naming", description="Create menu names objects pCube1 / pCubeShape1 "
                                        "(otherwise Blender names)",
        default=True)
    # On by default, like Maya.
    smart_duplicate: bpy.props.BoolProperty(
        name="Smart Duplicate", description="Shift+drag a Move/Rotate/Scale manipulator "
                                            "duplicates the selection and transforms the copy",
        default=True)
    # On by default, like Maya.
    smart_extrude: bpy.props.BoolProperty(
        name="Smart Extrude", description="Shift+drag a Move/Rotate/Scale manipulator on faces "
                                          "or edges extrudes them and transforms the new ones",
        default=True)

    @_quiet
    def _update_units(self, context):
        from .operators import units
        if self.maya_units:
            units.apply_file()
        else:
            units.restore_file()

    maya_units: bpy.props.BoolProperty(
        name="Maya Units (1 BU = 1 cm)",
        description="Scene unit scale 0.01 with centimetres and Maya camera clipping "
                    "(0.1 - 10000) for this file and new files. Physics, light falloff and "
                    "importers assume 1 BU = 1 m. Turning it off restores the previous values",
        default=False, update=_update_units)

    def draw(self, context):
        layout = self.layout
        draw_about(layout)
        box = layout.box()
        row = box.row()
        row.scale_y = 1.6
        if self.maya_mode:
            row.operator("allset.switch_mode", text="Switch to Blender", icon='BLENDER').mode = 'BLENDER'
        else:
            # Nothing is changed until the user asks for it (step 115): the same dialog as the first start.
            row.operator("allset.welcome", text="Make Blender feel like Maya", icon='EVENT_M')
            row.operator("allset.switch_mode", text="Maya Mode Only").mode = 'MAYA'
        box.label(text="Ctrl+Alt+Shift+M or the Maya / Blender switch at the right of the top bar switches at any time. "
                       "Blender's own preferences are never changed.", icon='INFO')
        from . import switch
        if switch.last_error[0]:
            _wrapped(box, switch.last_error[0])
        hint = undo_hint(context)
        emulate = emulate_hint(context)
        if hint or emulate:
            box.label(text="Recommended setup", icon='LOOP_BACK')
        for text in (hint, emulate):
            if text:
                _wrapped(box, text)
        row = box.row(align=True)
        row.operator("allset.settings_export", icon='EXPORT')
        row.operator("allset.settings_import", icon='IMPORT')
        if not self.maya_mode:
            return
        box = layout.box()
        row = box.row()
        row.scale_y = 1.4
        row.operator("allset.new_maya_scene", icon='FILE_NEW')
        row.operator("allset.maya_layout_here", icon='WORKSPACE')
        box.prop(self, "start_in_maya_layout")
        box.prop(self, "maya_layout_on_open")
        col = layout.column()
        col.prop(self, "lock_ortho_tumble")
        col.prop(self, "select_through")
        col.prop(self, "preselect_highlight")
        col.prop(self, "select_priority")
        col.prop(self, "pick_walk_skip_hidden_collections")
        col.prop(self, "armature_mode_header")
        col.prop(self, "armature_mode_pulse")

        box = layout.box()
        box.label(text="Scene Concepts")
        row = box.row()
        row.prop(self, "parent_mode")
        row.prop(self, "maya_naming")
        row = box.row()
        row.prop(self, "maya_units")
        row.prop(self, "smart_duplicate")
        row.prop(self, "smart_extrude")
        box.prop(self, "project_root")
        row = box.row()
        row.prop(self, "autosave_enable")
        sub = row.row()
        sub.active = self.autosave_enable
        sub.prop(self, "autosave_interval")
        sub.prop(self, "autosave_limit")
        num = sub.row()
        num.active = self.autosave_limit
        num.prop(self, "autosave_count", text="")
        row = box.row()
        row.active = self.autosave_enable
        row.prop(self, "autosave_destination", text="")
        folder = row.row()
        folder.active = self.autosave_destination == 'FOLDER'
        folder.prop(self, "autosave_folder", text="")

        box = layout.box()
        box.label(text="UI Elements")
        row = box.row()
        row.prop(self, "maya_top_bar")
        row.prop(self, "maya_panel_menus")
        row.prop(self, "menu_set", text="")
        row = box.row()
        row.prop(self, "marking_menu_style")
        row.prop(self, "hotbox_style", text="")
        row.prop(self, "hotbox_all_sets")
        row = box.row()
        row.prop(self, "show_status_line")
        row.prop(self, "show_command_line")
        row.prop(self, "show_help_line")
        row = box.row()
        row.prop(self, "maya_toolbox")
        row = box.row()
        row.prop(self, "maya_viewcube")
        row.prop(self, "view_navigation", text="")
        row.prop(self, "maya_camera_names")
        row.prop(self, "maya_view_axis")
        row.prop(self, "maya_selection_wire")
        row.prop(self, "maya_component_colors")
        box.prop(self, "maya_dock_colors")
        box.prop(self, "in_view_messages")


# Undo depth (step 141, B6): Maya's undo queue is infinite, Blender keeps 32 steps
# by default and the kit may not write Blender's preferences (step 130), so the kit only tells the user.
UNDO_RECOMMENDED = 256      # Blender's maximum
UNDO_HINT = ("Maya's undo is unlimited; Blender keeps {steps} steps. For long Maya-style sessions raise Edit > "
             "Preferences > System > Memory & Limits > Undo Steps to 256 (Blender's maximum).")


EMULATE_HINT = i18n.mark(
    "Emulate 3 Button Mouse is on (Preferences > Input): Blender turns Alt+left drag into a middle drag "
    "before any key map sees it. On Windows the kit still tumbles on Alt+LMB; elsewhere Maya's Alt+LMB "
    "tumble can't work, so turn it off for Maya navigation (Alt+MMB track and Alt+RMB dolly work "
    "either way).")


def emulate_hint(context=None):
    """Step 260 (#177): the Emulate 3 Button Mouse hint while that Blender preference is on, else None (read only:
    the kit never writes Blender's preferences, step 130). Blender converts Alt+LMB into a plain MMB without Alt
    (wm_event_system.cc wm_eventemulation)."""
    inputs = (context or bpy.context).preferences.inputs
    return EMULATE_HINT if getattr(inputs, "use_mouse_emulate_3_button", False) else None


def undo_hint(context=None):
    """The undo-depth hint while Blender's Undo Steps is below 256, else None (read only, nothing is written)."""
    steps = (context or bpy.context).preferences.edit.undo_steps
    return UNDO_HINT.format(steps=steps) if steps < UNDO_RECOMMENDED else None


ABOUT = ("Other tools give you one piece at a time: a pivot, a keymap, a shelf, a theme. Maya Workflow Kit brings the whole Maya "
         "workflow into Blender in one install: hotbox and marking menus, Channel Box, Attribute Editor, Outliner, "
         "menu sets, shelves, option windows, Freeze / History concepts, centimetre units and pCube1-style naming.")
TRADEMARK_NOTICE = (
    "Autodesk and Maya are registered trademarks or trademarks of Autodesk, Inc., and/or its subsidiaries and/or "
    "affiliates in the USA and/or other countries. This project is an independent, free and open-source (GPL) "
    "extension for Blender. It is not affiliated with, endorsed by, sponsored by, or otherwise approved by Autodesk, "
    "Inc. or the Blender Foundation. It contains no Autodesk code, icons, MEL scripts or other Autodesk assets; "
    "references to Maya are solely to describe compatibility and the intended audience.")


def _wrapped(layout, text, width=110):
    """``text`` in the interface language, in lines of about ``width`` characters (CJK characters count twice)."""
    from . import i18n
    col = layout.column(align=True)
    for line in i18n.wrap(i18n.iface(text), width):
        col.label(text=line, translate=False)


def draw_about(layout):
    """The About box of the preferences: what Maya Workflow Kit is, and the trademark notice."""
    box = layout.box()
    box.label(text="Maya Workflow Kit: the whole Maya workflow in Blender, in one install", icon='INFO')
    _wrapped(box, ABOUT)
    sub = box.column()
    sub.scale_y = 0.8
    sub.enabled = False
    _wrapped(sub, TRADEMARK_NOTICE)


_SET_ITEMS = []


def _menu_set_items():
    # Kept in a module list: Blender needs the enum item strings to stay referenced.
    if not _SET_ITEMS:
        from .ui import menu_sets
        _SET_ITEMS.extend(menu_sets.SET_ITEMS)
    return _SET_ITEMS


classes = (ALLSET_AddonPreferences,)

_register_classes, _unregister_classes = bpy.utils.register_classes_factory(classes)


# --- settings backup -------------------------------------------------------------------------------------------
# Blender deletes an add-on's preferences when the add-on is disabled from Preferences > Add-ons (and when it is
# removed): ``addon_utils.disable(default_set=True)`` removes its ``preferences.addons`` entry. An update keeps the
# entry. So every unregister copies the settings the user changed into ``preferences_backup.json`` in the
# extension's user folder, and a register that finds a fresh entry (no setting set) puts them back. A setting the
# user put back to its default stays there: the copy is taken at every unregister. Remove deletes the user folder and with it the copy;
# a --factory-startup session neither writes nor reads it.

BACKUP_FILE = "preferences_backup.json"


def _factory_startup():
    return bpy.app.factory_startup


def _backup_path():
    if _factory_startup():
        return None
    try:
        folder = bpy.utils.extension_path_user(__package__, create=True)
    except (ValueError, AttributeError):      # not installed as an extension (legacy add-on)
        return None
    return os.path.join(folder, BACKUP_FILE)


def _names():
    return [p.identifier for p in ALLSET_AddonPreferences.bl_rna.properties
            if p.identifier not in ("rna_type", "bl_idname")]


def _addon_prefs():
    addon = bpy.context.preferences.addons.get(__package__)
    return addon.preferences if addon is not None else None


def save_backup():
    """Write the settings that differ from a fresh install (the ones Blender stores) to the backup file."""
    try:
        p, path = _addon_prefs(), _backup_path()
        if p is None or not path:
            return
        data = {}
        for name in _names():
            if p.is_property_set(name):
                value = getattr(p, name)
                if isinstance(value, set):
                    value = sorted(value)
                elif not isinstance(value, (bool, int, float, str)):
                    value = list(value)       # vector values
                data[name] = value
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, sort_keys=True)
    except Exception as ex:                   # never stop the add-on from unregistering
        print("Maya Workflow Kit: could not back up the add-on preferences:", ex)


def restore_backup():
    """Put the backup back when Blender gave the add-on a fresh preferences entry. Returns the names restored."""
    done = []
    try:
        p, path = _addon_prefs(), _backup_path()
        if p is None or not path or not os.path.isfile(path):
            return done
        names = _names()
        if any(p.is_property_set(n) for n in names):
            return done                       # Blender kept the settings (start, update): they win
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return done
        _restoring[0] = True
        for name in names:
            if name in data:
                value = data[name]
                try:
                    flag = getattr(p.bl_rna.properties[name], "is_enum_flag", False)
                    setattr(p, name, set(value) if flag else value)
                    done.append(name)
                except (TypeError, ValueError, AttributeError):
                    pass                      # an option that changed type or lost an enum item since the backup
    except Exception as ex:
        print("Maya Workflow Kit: could not restore the add-on preferences:", ex)
    finally:
        _restoring[0] = False
    return done


def register():
    _register_classes()
    restore_backup()


def unregister():
    _unregister_classes()


def get(context=None):
    """Return this add-on's preferences instance."""
    context = context or bpy.context
    return context.preferences.addons[__package__].preferences
