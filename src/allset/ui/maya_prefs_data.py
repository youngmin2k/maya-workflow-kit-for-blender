# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya 2022 Preferences window, page by page (Issue #121) — pure data, no bpy.

Category tree, page titles and control labels follow Maya 2022's
Preferences window. The kit never writes
Blender's preferences, so a page row is one of:

  ("pref", attr, label)                      a kit add-on preference (``preferences.get(context).<attr>``)
  ("scene", path, label)                     a value the kit keeps in the scene (``context.scene.<path>``)
  ("blender", label, section, path, note)    a Blender preference: shown read-only (``preferences.<path>``) with the
                                             Recommended setup note and a button that opens that Preferences section
  ("missing", label, note)                   a Maya control with no kit / Blender counterpart (greyed + the reason)

``MAYA_FACTORY`` = the default value of each scene row, like Maya (Edit > Restore Default Settings).
"""

# (key, label, depth, page title, sections) — sections = [(section title, [rows])]; order = Maya's list.
PAGES = (
    ("INTERFACE", "Interface", 0, "Interface: General Interface Preferences", [
        ("Interface", [
            ("pref", "menu_set", "Menu set"),
            ("pref", "maya_top_bar", "Show menubar: In main window"),
            ("pref", "maya_panel_menus", "Show menubar: In panels"),
            ("missing", "Show title bar", "Blender draws the operating system's title bar"),
            ("missing", "Command Line: Hold focus", "The kit's Command Line gives focus back after Enter"),
        ]),
        ("Marking Menus", [
            ("pref", "marking_menu_style", "Marking menus"),
            ("pref", "hotbox_style", "Hotbox"),
            ("pref", "hotbox_all_sets", "Hotbox: show all menu sets"),
        ]),
        ("Interface Scaling", [
            ("blender", "Interface scaling", 'INTERFACE', "view.ui_scale",
             "Recommended setup: Interface > Resolution Scale (Maya: use system setting)"),
        ]),
        ("Devices", [
            ("blender", "Mouse scroll wheel: invert zoom", 'NAVIGATION', "inputs.invert_zoom_wheel",
             "Recommended setup: Navigation > Zoom (Maya: wheel up zooms in)"),
        ]),
    ]),
    ("UI_ELEMENTS", "UI Elements", 1, "UI Elements: Set Which Elements Will Be Displayed", [
        ("Visible UI Elements", [
            ("pref", "show_status_line", "Status Line"),
            ("missing", "Shelf", "The shelf row is part of the Maya layout (Windows > Workspaces)"),
            ("missing", "Time Slider / Range Slider", "Part of the Maya layout's timeline"),
            ("pref", "show_command_line", "Command Line"),
            ("pref", "show_help_line", "Help Line"),
            ("pref", "maya_toolbox", "Tool Box"),
        ]),
        ("Panel Configurations", [
            ("pref", "maya_layout_on_open", "When opening: Restore saved layouts from file"),
            ("pref", "start_in_maya_layout", "Starting new scenes: Maya layout"),
        ]),
    ]),
    ("VIEWCUBE", "ViewCube", 1, "ViewCube: ViewCube Preferences", [
        ("ViewCube", [
            ("pref", "maya_viewcube", "Show the ViewCube"),
            ("pref", "view_navigation", "Navigation widget"),
            ("missing", "On-screen position / size / opacity", "Blender's navigation gizmo has fixed placement"),
        ]),
    ]),
    ("HELP", "Help", 1, "Help: Help Interface Preferences", [
        ("In-View Messages", [
            ("pref", "in_view_messages", "Enable"),
        ]),
        ("Popup Help", [
            ("blender", "Display ToolClips", 'INTERFACE', "view.show_tooltips",
             "Recommended setup: Interface > Tooltips"),
        ]),
    ]),
    ("DISPLAY", "Display", 0, "Display: General Display Preferences", [
        ("View", [
            ("pref", "maya_view_axis", "Axes: View axis"),
            ("pref", "maya_camera_names", "Camera names in the viewport"),
            ("pref", "maya_selection_wire", "Selection wireframe (lead green, others white)"),
            ("pref", "maya_component_colors", "Component colours"),
            ("pref", "maya_dock_colors", "Panel colours"),
            ("pref", "maya_uv_manipulator", "UV Editor manipulator"),
            ("pref", "lock_ortho_tumble", "Lock tumble in orthographic views"),
        ]),
    ]),
    ("KINEMATICS", "Kinematics", 1, "Kinematics: Kinematics Display Preferences", [
        ("Kinematics", [("missing", "Joint size / IK handle size", "Blender draws bones and empties at their own size")]),
    ]),
    ("MANIPULATORS", "Manipulators", 1, "Manipulators: Manipulator Display Preferences", [
        ("Manipulator Sizes", [
            ("blender", "Global scale", 'VIEWPORT', "view.gizmo_size",
             "Recommended setup: Viewport > Gizmo Size; = / - change the kit manipulator for the session"),
        ]),
    ]),
    ("NURBS", "NURBS", 1, "NURBS: NURBS Display Preferences", [
        ("NURBS", [("missing", "NURBS display for new objects", "Blender surfaces use their own display settings")]),
    ]),
    ("POLYGONS", "Polygons", 1, "Polygons: Polygon Display Preferences", [
        ("Polygons", [("missing", "Display for new objects", "Blender shows mesh overlays per viewport "
                                                             "(Overlays popover)")]),
    ]),
    ("SUBDIVS", "Subdivs", 1, "Subdivs: Subdivision Surface Display Preferences", [
        ("Subdivs", [("missing", "Subdivision surface display", "Maya subdiv surfaces don't exist in Blender")]),
    ]),
    ("FONT", "Font", 1, "Font: Font Preferences", [
        ("Font", [("blender", "Interface font", 'INTERFACE', "view.font_path_ui",
                   "Recommended setup: Interface > Text Rendering")]),
    ]),
    ("SETTINGS", "Settings", 0, "Settings: General Application Preferences", [
        ("World Coordinate System", [
            ("missing", "Up axis: Y", "Blender's up axis is Z (Maya Y = Blender Z)"),
        ]),
        ("Working Units", [
            ("scene", "unit_settings.length_unit", "Linear"),
            ("scene", "unit_settings.system_rotation", "Angular"),
            ("pref", "maya_units", "Maya units (1 BU = 1 cm)"),
        ]),
    ]),
    ("ANIMATION", "Animation", 1, "Animation: Animation Preferences", [
        ("Auto Key", [
            ("scene", "allset_auto_key", "Auto key"),
        ]),
        ("Tangents", [
            ("pref", "default_tangent_weight", "Default tangent weight"),
            ("pref", "default_in_tangent", "Default in tangent"),
            ("pref", "default_out_tangent", "Default out tangent"),
        ]),
        ("Graph Editor", [
            ("pref", "graph_auto_frame", "Auto frame"),
            ("pref", "graph_curve_names", "Curve name"),
            ("pref", "graph_key_size", "Key size"),
            ("pref", "graph_scale_manipulator", "Scale keys manipulator"),
            ("pref", "snap_time_to_selection", "Snap time to selection"),
        ]),
    ]),
    ("ASSETS", "Assets", 1, "Assets: Asset Preferences", [
        ("Assets", [("missing", "Assets", "Maya containers / assets: no Blender counterpart")]),
    ]),
    ("CACHED_PLAYBACK", "Cached Playback", 1, "Cached Playback: Cached Playback Preferences", [
        ("Cached Playback", [("missing", "Cached playback", "Blender caches simulations per modifier (Bake)")]),
    ]),
    ("CAMERAS", "Cameras", 1, "Camera: Default Camera Preferences", [
        ("Cameras", [("missing", "Near / far clip plane", "New kit cameras use near / far clip 0.1 / 10000 units")]),
    ]),
    ("COLOR_MANAGEMENT", "Color Management", 1, "Color Management: Color Management Preferences", [
        ("Color Management", [
            ("scene", "view_settings.view_transform", "View transform"),
            ("scene", "display_settings.display_device", "Display"),
        ]),
    ]),
    ("DYNAMICS", "Dynamics", 1, "Dynamics: Dynamics Preferences", [
        ("Dynamics", [("missing", "Run-up and caching", "Blender simulations cache per object (Bake)")]),
    ]),
    ("FILES_PROJECTS", "Files/Projects", 1, "Files/Projects: Project, Scene and File Settings", [
        ("Projects", [
            ("pref", "project_root", "Current project"),
        ]),
        ("Recent History Size", [
            ("blender", "Files", 'SAVE_LOAD', "filepaths.recent_files", "Recommended setup: Save & Load > Recent Files"),
        ]),
        ("AutoSave", [
            ("pref", "autosave_enable", "Enable"),
            ("pref", "autosave_interval", "Interval (minutes)"),
            ("pref", "autosave_limit", "Limit autosaves"),
            ("pref", "autosave_count", "Number of autosaves"),
            ("pref", "autosave_destination", "Destination"),
            ("pref", "autosave_folder", "Named folder"),
            ("blender", "Recovery auto save", 'SAVE_LOAD', "filepaths.use_auto_save_temporary_files",
             "Blender saves a recovery file (Save & Load > Auto Save)"),
        ]),
    ]),
    ("FILE_REFERENCES", "File References", 1, "File References: File Referencing Preferences", [
        ("File References", [("missing", "Reference load settings", "References load like Blender library links")]),
    ]),
    ("MODELING", "Modeling", 1, "Modeling: Modeling Preferences", [
        ("Polygons", [
            ("pref", "smart_extrude", "Smart command settings: extrude"),
            ("pref", "smart_duplicate", "Smart command settings: duplicate"),
            ("pref", "maya_naming", "Maya node names (pCube1 ...)"),
        ]),
    ]),
    ("NODE_EDITOR", "Node Editor", 1, "Node Editor: Node Editor Preferences", [
        ("Node Editor", [("missing", "Node Editor", "Blender's Shader Editor has its own settings")]),
    ]),
    ("RENDERING", "Rendering", 1, "Rendering: Rendering Preferences", [
        ("Rendering", [
            ("missing", "Test resolution", "Blender's Output properties > Resolution % sets the size of every render"),
            ("missing", "Enable default light", "Blender renders a scene with its own lights only"),
        ]),
    ]),
    ("SEARCH", "Search", 1, "Search: Search Preferences", [
        ("Search", [("missing", "Search", "Use Blender's menu search (F3)")]),
    ]),
    ("SELECTION", "Selection", 1, "Selection: Selection Preferences", [
        ("Modifiers", [
            ("pref", "preselect_highlight", "Preselection Highlight"),
            ("pref", "select_through", "Marquee selects hidden components"),
            ("missing", "Track selection order", "Blender keeps the active element only"),
        ]),
        ("Priority", [
            ("pref", "select_priority", "Selection priority"),
        ]),
    ]),
    ("SNAPPING", "Snapping", 1, "Snapping: Snapping Preferences", [
        ("Snapping", [("missing", "Snap tolerance", "Blender snaps within a fixed screen distance")]),
    ]),
    ("SOUND", "Sound", 1, "Sound: Sound Preferences", [
        ("Sound", [("blender", "Audio device", 'SYSTEM', "system.audio_device",
                    "Recommended setup: System > Sound")]),
    ]),
    ("TIME_SLIDER", "Time Slider", 1, "Time Slider: Animation Time Slider and Playback Preferences", [
        ("Time Slider", [
            ("scene", "render.fps", "Framerate"),
            ("scene", "frame_preview_start", "Playback start"),
            ("scene", "frame_preview_end", "Playback end"),
            ("scene", "frame_start", "Animation start"),
            ("scene", "frame_end", "Animation end"),
            ("pref", "cb_sync_timeline", "Channel Box Sync: Sync Timeline Display"),
            ("pref", "cb_sync_graph", "Channel Box Sync: Sync Selection in Graph Editor"),
        ]),
        ("Playback", [
            ("scene", "sync_mode", "Playback speed"),
            ("missing", "Looping", "Blender playback always loops (Continuous)"),
        ]),
    ]),
    ("UNDO", "Undo", 1, "Undo: Undo Queue Settings", [
        ("Undo", [
            ("blender", "Queue size", 'SYSTEM', "edit.undo_steps",
             "Recommended setup: System > Undo Steps = 256 (Maya: Infinite)"),
        ]),
    ]),
    ("GPU_CACHE", "GPU Cache", 1, "GPU Cache: GPU Cache Preferences", [
        ("GPU Cache", [("missing", "GPU cache", "Alembic caches import as Mesh Sequence Cache modifiers")]),
    ]),
    ("XGEN", "XGen", 1, "XGen: XGen Preferences", [
        ("XGen", [("missing", "XGen", "Use Blender hair curves")]),
    ]),
    ("SAVE_ACTIONS", "Save Actions", 1, "Save Actions: Save Actions Preferences", [
        ("Save Actions", [
            ("blender", "Save all preferences when Maya exits", 'SAVE_LOAD', "use_preferences_save",
             "Blender: Auto-Save Preferences (the hamburger menu at the bottom of Preferences)"),
        ]),
    ]),
    ("SECURITY", "Security", 0, "Security: Security Preferences", [
        ("Security", [("blender", "Auto run Python scripts", 'SAVE_LOAD', "filepaths.use_scripts_auto_execute",
                       "Recommended setup: Save & Load > Auto Run Python Scripts")]),
    ]),
    ("MEL", "MEL", 1, "MEL: MEL Security Preferences", [
        ("MEL", [("missing", "MEL", "MEL doesn't run in Blender; the Command Line runs Python (maya.cmds look-alike)")]),
    ]),
    ("PYTHON", "Python", 1, "Python: Python Security Preferences", [
        ("Python", [("blender", "Auto run Python scripts", 'SAVE_LOAD', "filepaths.use_scripts_auto_execute",
                     "Recommended setup: Save & Load > Auto Run Python Scripts")]),
    ]),
    ("PLUGINS", "Plugins", 1, "Plugins: Plug-in Security Preferences", [
        ("Plugins", [("missing", "Plug-in security", "Blender add-ons and extensions: Preferences > Get Extensions")]),
    ]),
    ("MODULES", "Modules", 0, "Modules: Module Preferences", [
        ("Modules", [("missing", "Modules", "Maya modules: Blender has extensions instead")]),
    ]),
    ("APPLICATIONS", "Applications", 0, "External Applications: Settings", [
        ("Applications", [("blender", "Image editor", 'FILE_PATHS', "filepaths.image_editor",
                           "Recommended setup: File Paths > Applications")]),
    ]),
)

KEYS = tuple(p[0] for p in PAGES)
BY_KEY = {p[0]: p for p in PAGES}

# Default values of the scene rows (Settings / Time Slider pages; units = the
# Maya Workflow Kit template's display units) — Edit > Restore Default Settings.
MAYA_FACTORY = {
    "unit_settings.length_unit": 'CENTIMETERS',
    "unit_settings.system_rotation": 'DEGREES',
    "allset_auto_key": False,
    "render.fps": 24,
    "frame_preview_start": 1,
    "frame_preview_end": 120,
    "frame_start": 1,
    "frame_end": 200,
    "sync_mode": 'NONE',            # Maya Playback speed "Play every frame"
}


def rows(kind=None):
    """Every row of every page (optionally only one kind), as (page key, section, row)."""
    out = []
    for key, _label, _depth, _title, sections in PAGES:
        for section, items in sections:
            for row in items:
                if kind is None or row[0] == kind:
                    out.append((key, section, row))
    return out


def label(row):
    return row[1] if row[0] in {"blender", "missing"} else row[2]
