# SPDX-License-Identifier: GPL-3.0-or-later
"""Rows of the Maya viewport panel menus (``ui/panel_menus.py``), the panel toolbar (``ui/panel_toolbar.py``) and the
greyed Status Line widgets (``ui/status_line.py``) as plain data — no ``bpy`` — so ``tools/menu_count.py``,
``tools/menu_consistency.py`` and the step-101 notice rules can walk them like the main menus (step 177; until then
these 36 + 9 greyed items were outside every count, research audit 12 BS2 / BS6, docs/steps/step_173_remaining.md §4).

Item paths (``allset.menu_unavailable`` ``item``, ``notices.PANEL_MENU`` keys): ``Panel menu/<menu>/<sub>/<label>``,
``Panel toolbar/<label>``, ``Status Line/<tooltip>``. Rows: see ``ui/panel_menus.py``.
"""


def _sep(label=""):
    return ("sep", label)


def _grey(label):
    return ("grey", label)


def _run(label, op, **props):
    return ("run", label, op, props)


def _tool(label, idname):
    return _run(label, "wm.tool_set_by_id", name=idname)


def _view(label, view):
    return _run(label, "allset.hb_view", view=view)


VIEW = [
    ("set", "SELECT_CAMERA", "Select Camera"),
    ("set", "CAMERA_LOCK", "Lock Camera"),
    _sep(),
    _run("Undo View Change", "allset.view_history", direction='UNDO'),
    _run("Redo View Change", "allset.view_history", direction='REDO'),
    _sep("Tumble Behaviour"),
    ("set", "TUMBLE_SELECTION", "Around Most Recent Selection"),
    ("set", "TUMBLE_COI", "Around Center of Interest"),
    _sep("Change View"),
    _run("Align Camera To Polygon", "view3d.view_axis", type='TOP', align_active=True),
    _run("Center View of Selection", "allset.center_view_selection"),   # step 177: Maya viewFit -c
    _run("Default View", "allset.view_home"),
    _run("Frame All", "allset.frame", selected=False),
    _run("Frame Selection", "allset.frame", selected=True),
    ("menu", "View Along Axis", "ALLSET_MT_panel_view_axis"),
    _sep(),
    _run("Camera Attribute Editor...", "allset.camera_attribute_editor"),   # step 177: showPanelCameraEditor
    ("menu", "Camera Tools", "ALLSET_MT_panel_camera_tools"),
    _sep(),
    _grey("View Sequence Time"),
]

# Maya viewSet -vx = seen from +X (Maya 2022 panel View menu); axis names as Blender's
# (X = X, Y = Y, Z = Z: decision 5, docs/steps/step_37.md).
VIEW_AXIS = [_view("X", 'RIGHT'), _view("Y", 'BACK'), _view("Z", 'TOP'),
             _view("-X", 'LEFT'), _view("-Y", 'FRONT'), _view("-Z", 'BOTTOM')]

CAMERA_TOOLS = [
    # step 177: Maya's camera tools (ui/camera_tools.py: LMB drag tumbles / tracks / dollies until another tool)
    _tool("Tumble Tool", "allset.tumble_tool"), _tool("Track Tool", "allset.track_tool"),
    _tool("Dolly Tool", "allset.dolly_tool"),
    _run("Zoom Tool", "view3d.zoom_border"),
    _grey("2D Pan/Zoom Tool"),
    _tool("Grease Pencil Tool", "builtin.annotate"),     # the panel toolbar's Grease Pencil button (Annotate)
    _sep(),
    _run("Roll Tool", "view3d.view_roll", type='ANGLE', angle=0.2618),
    _grey("Azimuth Elevation Tool"), _grey("Yaw-Pitch Tool"),
    _run("Fly Tool", "view3d.fly"),
    _run("Walk Tool", "view3d.walk"),
]

SHADING = [
    ("set", "SHADE_WIRE", "Wireframe"),
    ("set", "SHADE_SMOOTH", "Smooth Shade All"),
    _grey("Smooth Shade Selected Items"),
    _grey("Flat Shade All"),
    _grey("Flat Shade Selected Items"),
    _grey("Bounding Box"),
    _grey("Points"),
    _sep(),
    ("set", "DEFAULT_MATERIAL", "Use Default Material"),
    ("prop", "overlay", "show_wireframes", "Wireframe on Shaded"),
    ("prop", "shading", "show_xray", "X-Ray"),
    ("prop", "overlay", "show_xray_bone", "X-Ray Joints"),
    _grey("X-Ray Active Components"),
    _sep(),
    _grey("Interactive Shading"),
    _sep(),
    ("prop", "shading", "show_backface_culling", "Backface Culling"),
    _grey("Smooth Wireframe"),
    _sep(),
    ("set", "HW_TEXTURE", "Hardware Texturing"),
    _grey("Hardware Fog"),
    ("prop", "shading", "use_dof", "Depth of Field"),
    _sep(),
    ("set", "APPLY_ALL", "Apply Current to All"),
    _sep(),
    _run("Restore Modeling Display", "allset.restore_modeling_display"),
]

LIGHTING = [
    ("set", "LIGHT_DEFAULT", "Use Default Lighting"),
    ("set", "LIGHT_ALL", "Use All Lights"),
    _grey("Use Selected Lights"),
    ("set", "LIGHT_FLAT", "Use Flat Lighting"),
    _grey("Use No Lights"),
    _sep(),
    _grey("Two Sided Lighting"),
    ("prop", "shading", "show_shadows", "Shadows"),
]

# Maya object type -> SpaceView3D.show_object_viewport_<type> (None = no Blender filter, "@" = an overlay flag,
# "!" = a kit ``set`` key: ui/panel_menus.state / apply, step 189).
SHOW_TYPES = (
    ("Controllers", None), ("NURBS Curves", "!SHOW_NURBS_CURVES"), ("NURBS Surfaces", "surf"),
    ("NURBS CVs", None), ("NURBS Hulls", None), ("Polygons", "mesh"), ("Subdiv Surfaces", None),
    ("Planes", None), ("Lights", "light"), ("Cameras", "camera"), ("Image Planes", "!SHOW_IMAGE_PLANES"),
    ("Joints", "armature"), ("IK Handles", "!SHOW_IK_HANDLES"), ("Deformers", "lattice"), ("Dynamics", None),
    ("Particle Instancers", None), ("Fluids", "volume"), ("Hair Systems", "curves"),
    ("Follicles", None), ("nCloths", None), ("nParticles", None), ("nRigids", None),
    ("Dynamic Constraints", None), ("Locators", "empty"), ("Dimensions", None),
    ("Pivots", "@show_object_origins"), ("Handles", None), ("Texture Placements", None),
    ("Strokes", None), ("Motion Trails", "@show_motion_paths"), ("Plugin Shapes", None),
    ("Clip Ghosts", None), ("Grease Pencil", "grease_pencil"),
)
ALL_TYPES = ("mesh", "curve", "surf", "meta", "font", "curves", "pointcloud", "volume", "armature",
             "lattice", "empty", "grease_pencil", "camera", "light", "speaker", "light_probe")


def _show_row(label, target):
    if target is None:
        return _grey(label)
    if target.startswith("@"):
        return ("prop", "overlay", target[1:], label)
    if target.startswith("!"):
        return ("set", target[1:], label)
    return ("prop", "space", f"show_object_viewport_{target}", label)


SHOW = [
    ("menu", "Isolate Select", "ALLSET_MT_panel_isolate"),
    _sep(),
    ("set", "SHOW_ALL", "All"),
    ("set", "SHOW_NONE", "None"),
    _sep(),
    *[_show_row(label, t) for label, t in SHOW_TYPES],
    _sep(),
    ("prop", "space", "show_gizmo", "Manipulators"),
    ("set", "GRID", "Grid"),               # Maya grid (ui/maya_grid.py, step 45)
    ("prop", "overlay", "show_text", "HUD"),
    _grey("Hold-Outs"),
    ("set", "SELECTION_HILITE", "Selection Highlighting"),   # kit wire + Blender outline (step 262)
]

ISOLATE = [
    _run("View Selected", "allset.isolate"),          # step 164: with the children
]

RENDERER = [
    ("set", "RENDER_VP2", "Viewport 2.0"),
    _grey("Legacy Default Viewport"),
    _grey("Legacy High Quality Viewport"),
    _sep(),
    ("set", "RENDER_ENGINE", "{engine}"),   # Maya lists render overrides here (Arnold)
]

PANELS = [
    ("menu", "Perspective", "ALLSET_MT_panel_perspective"),
    _grey("Stereo"),
    ("menu", "Orthographic", "ALLSET_MT_panel_orthographic"),
    _run("Look Through Selected", "allset.panel_look_through"),
    _grey("Camera Set"),
    _sep(),
    ("menu", "Panel", "ALLSET_MT_panel_panel"),
    _grey("Hypergraph Panel"),
    ("menu", "Layouts", "ALLSET_MT_panel_layouts"),
    _grey("Saved Layouts"),
    _sep(),
    _run("Tear Off...", "allset.open_editor", ui_type='VIEW_3D'),
    _run("Tear Off Copy...", "allset.open_editor", ui_type='VIEW_3D'),
    _sep(),
    _grey("Panel Editor..."),
]

PANEL_TYPES = (("Outliner", 'OUTLINER'), ("Graph Editor", 'FCURVES'), ("Dope Sheet", 'DOPESHEET'),
               ("Node Editor", 'ShaderNodeTree'), ("UV Editor", 'UV'), ("Model Panel", 'VIEW_3D'),
               ("Script Editor", 'TEXT_EDITOR'))

LAYOUTS = [
    ("set", "LAYOUT_SINGLE", "Single Perspective View"),
    ("set", "LAYOUT_FOUR", "Four View"),
]

# The menu bar, in Maya 2022's order.
BAR = (("View", "ALLSET_MT_panel_view"), ("Shading", "ALLSET_MT_panel_shading"),
       ("Lighting", "ALLSET_MT_panel_lighting"), ("Show", "ALLSET_MT_panel_show"),
       ("Renderer", "ALLSET_MT_panel_renderer"), ("Panels", "ALLSET_MT_panel_panels"))


# (glyph, kind, data, label): kind "set" = panel_menus.ALLSET_OT_panel_set key, "prop" = (owner, prop) on the view,
# "run" = (operator, props) run in the view, "grey" = no Blender equivalent (the label explains it).
#
# Step 129 (#10): every Maya toggle (a check button on Maya's panel toolbar; ``checkable`` in _top113.json) is a
# toggle here too — "set" keys are drawn with ``toggle=True`` so Wireframe / Smooth Shade All / Use All Lights turn
# off to Maya's off state (panel_menus.TOGGLE_OFF); camera buttons act on the camera the view looks through and are
# disabled in Blender's persp / ortho views (Maya disables Lock Camera there too). Table: docs/steps/step_129_viewport.md.
TOOLBAR = (
    (("cam_select", "set", "SELECT_CAMERA", "Select Camera"),
     ("cam_lock", "set", "CAMERA_LOCK", "Lock Camera"),
     ("cam_attr", "run", ("allset.camera_attribute_editor", {}), "Camera Attributes"),   # step 177
     ("bookmark", "grey", None, "Bookmarks"),
     ("image_plane", "run", ("allset.create", {"kind": 'IMAGE_PLANE'}), "Image Plane"),
     ("pan_zoom", "grey", None, "2D Pan/Zoom"),
     ("grease", "run", ("wm.tool_set_by_id", {"name": "builtin.annotate"}), "Grease Pencil (Blender: Annotate tool)")),
    (("grid", "set", "GRID", "Grid"),
     ("film_gate", "set", "FILM_GATE", "Film Gate"),
     ("res_gate", "grey", None, "Resolution Gate"),
     ("gate_mask", "set", "GATE_MASK", "Gate Mask"),
     ("field_chart", "grey", None, "Field Chart"),
     ("safe_action", "set", "SAFE_ACTION", "Safe Action"),
     ("safe_title", "set", "SAFE_TITLE", "Safe Title")),
    (("wire", "set", "SHADE_WIRE", "Wireframe"),
     ("smooth", "set", "SHADE_SMOOTH", "Smooth Shade All"),
     ("default_mat", "set", "DEFAULT_MATERIAL", "Use Default Material"),
     ("wire_on_shaded", "prop", ("overlay", "show_wireframes"), "Wireframe on Shaded"),
     ("textured", "set", "HW_TEXTURE", "Textured"),
     ("all_lights", "set", "LIGHT_ALL", "Use All Lights"),
     ("shadows", "prop", ("shading", "show_shadows"), "Shadows")),
    (("ssao", "prop", ("shading", "show_cavity"), "Screen Space Ambient Occlusion (Blender: cavity)"),
     ("motion_blur", "grey", None, "Motion Blur"),
     ("aa", "grey", None, "Multisample Anti-aliasing"),
     ("dof", "prop", ("shading", "use_dof"), "Depth of Field")),
    (("isolate", "set", "ISOLATE", "Isolate Select"),
     ("xray", "prop", ("shading", "show_xray"), "X-Ray"),
     ("xray_comp", "grey", None, "X-Ray Active Components"),
     ("xray_joints", "prop", ("overlay", "show_xray_bone"), "X-Ray Joints")),
)


# Menu idname -> label path under "Panel menu/" (menus built at run time — Perspective / Orthographic / Panel list
# cameras and editors — have no greyed rows and are not walked).
MENUS = {
    "ALLSET_MT_panel_view": ("View", VIEW),
    "ALLSET_MT_panel_view_axis": ("View/View Along Axis", VIEW_AXIS),
    "ALLSET_MT_panel_camera_tools": ("View/Camera Tools", CAMERA_TOOLS),
    "ALLSET_MT_panel_shading": ("Shading", SHADING),
    "ALLSET_MT_panel_lighting": ("Lighting", LIGHTING),
    "ALLSET_MT_panel_show": ("Show", SHOW),
    "ALLSET_MT_panel_isolate": ("Show/Isolate Select", ISOLATE),
    "ALLSET_MT_panel_renderer": ("Renderer", RENDERER),
    "ALLSET_MT_panel_panels": ("Panels", PANELS),
    "ALLSET_MT_panel_layouts": ("Panels/Layouts", LAYOUTS),
}
MENU_PREFIX, TOOLBAR_PREFIX = "Panel menu/", "Panel toolbar/"

# The Status Line's greyed widgets (ui/status_line.py ``_grey``; tests/test_step177_panel_menus.py checks the drawn set).
STATUS_LINE = ("Status Line/Select by hierarchy", "Status Line/Select by handle object type",
               "Status Line/Select by dynamic object type", "Status Line/Snap to projected center",
               "Status Line/Snap to view planes", "Status Line/Render Setup",
               "Status Line/Pause Viewport 2.0", "Status Line/Show or hide the Character Controls")


# Maya runTimeCommand of panel rows whose command is one (Maya panel menus):
# tools/menu_consistency.py compares these with the main / editor / marking menus.
COMMANDS = {"Tumble Tool": "TumbleTool", "Track Tool": "TrackTool", "Dolly Tool": "DollyTool",
            "Center View of Selection": "CenterViewOfSelection", "Default View": "GoToDefaultView"}


def path_label(label):
    """A label as a path part: a "/" in it ("2D Pan/Zoom Tool") becomes U+2215 so paths still split on "/"."""
    return label.replace("/", "∕")


def item_path(idname, label):
    """``allset.menu_unavailable`` item of a greyed row ``label`` in menu ``idname``."""
    prefix = f"{MENU_PREFIX}{MENUS[idname][0]}/" if idname in MENUS else MENU_PREFIX
    return prefix + path_label(label)


def toolbar_path(label):
    return TOOLBAR_PREFIX + path_label(label)


def leaves():
    """[(family, path, working)] of every panel menu row that is a command (not a submenu / separator), every panel
    toolbar button and every greyed Status Line widget. family = "Panel menus" / "Panel toolbar" / "Status Line"."""
    out = []
    for idname, (_prefix, rows) in MENUS.items():
        for row in rows:
            if row[0] in ("sep", "menu"):
                continue
            label = row[1] if row[0] in ("grey", "run") else row[-1]
            out.append(("Panel menus", item_path(idname, label), row[0] != "grey"))
    for group in TOOLBAR:
        for _glyph, kind, _data, label in group:
            out.append(("Panel toolbar", toolbar_path(label), kind != "grey"))
    out += [("Status Line greys", p, False) for p in STATUS_LINE]
    return out
