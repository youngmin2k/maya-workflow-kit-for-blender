# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya menu item -> Blender action (step 7).

Key = label path in ``menu_data.MENUS`` ("Create/Polygon Primitives/Cube"),
starting with the menu *label*, so the Deform and Constrain menus that
Modeling, Rigging and Animation share map once. Value:

- ``"op.id"`` or ``("op.id", {props})``: drawn as that operator (its poll
  greys the item out where Blender can't run it, e.g. edit-mode commands in
  object mode);
- ``("v3d", "op.id", {props})``: needs a 3D View region; run through
  ``allset.menu_run`` in the largest 3D View;
- ``("tool", "builtin.id", edit)``: switch the active tool, entering mesh edit
  mode first when ``edit``;
- ``("menu", "MENU_ID")``: a Blender menu as the submenu.
- ``("prop", "context.path", {"value": v})``: a Maya check / radio item drawn as that Blender property (step 104;
  without ``value`` a check box, with it one choice of a radio collection).

Items not listed are drawn greyed out. ``EXTRA`` adds items Maya builds at run
time (not in the static menu data), e.g. Modify's Pivot section.
"""

import math

def _create(kind):
    # Default size at the origin like Maya, Maya names (operators/create.py).
    return ("allset.create", {"kind": kind})


_PRIMS = {label: _create(kind) for label, kind in (
    ("Sphere", 'SPHERE'), ("Cube", 'CUBE'), ("Cylinder", 'CYLINDER'), ("Cone", 'CONE'),
    ("Torus", 'TORUS'), ("Plane", 'PLANE'), ("Polygon Disc", 'DISC'),   # step 219: Maya 2026 label
    ("Platonic Solid", 'PLATONIC'),
    ("Pyramid", 'PYRAMID'), ("Prism", 'PRISM'), ("Pipe", 'PIPE'), ("Helix", 'HELIX'), ("Gear", 'GEAR'),
    ("Soccer Ball", 'SOCCER_BALL'), ("Super Ellipse", 'SUPER_ELLIPSE'), ("Spherical Harmonics", 'SPHERICAL_HARMONICS'),
    ("Ultra Shape", 'ULTRA_SHAPE'))}   # step 190: the last seven


def _deformer(kind):
    # Maya Deform menu deformer (operators/deformers.py, step 144)
    return ("allset.deformer", {"kind": kind})


def _del(kind, all_=False):
    return ("allset.delete_by_type", {"type": kind, "all": all_})


_DELETE_BY_TYPE = {"History": 'HISTORY', "Non-Deformer History": 'NON_DEFORMER_HISTORY',
                   "Channels": 'CHANNELS', "Static Channels": 'STATIC_CHANNELS',
                   "Constraints": 'CONSTRAINTS', "Motion Paths": 'MOTION_PATHS',
                   "Rigid Bodies": 'RIGID_BODIES'}
_DELETE_ALL_ONLY = {"Joints": 'JOINTS', "Lattices": 'LATTICES', "Cameras": 'CAMERAS',
                    "Lights": 'LIGHTS', "Image Planes": 'IMAGE_PLANES', "Clusters": 'CLUSTERS', "IK Handles": 'IK_HANDLES',
                    "Nonlinears": 'NONLINEARS', "Particles": 'PARTICLES',
                    # step 202 (#109): the kit's wire / nCloth / nParticle / nRigid nodes (operators/by_type.py)
                    "Wires": 'WIRES', "nCloths": 'NCLOTHS', "nParticles": 'NPARTICLES', "nRigids": 'NRIGIDS'}


def _mod(kind):
    return ("object.modifier_add", {"type": kind})


def _mod_selected(kind):
    # Blender's modifier_add on every selected object, not only the active one
    return ("object.modifier_add", {"type": kind, "use_selected_objects": True})


def _field(kind):
    return ("object.effector_add", {"type": kind})


def _con(kind):
    # Maya order (targets, then the constrained node); on the active joint in pose mode (step 62)
    return ("allset.constrain", {"type": kind})


def _sel(kind):
    # Maya Select menu conversions (step 141, operators/select_convert.py)
    return ("allset.select_convert", {"kind": kind})


def _editor(ui_type):
    # A Blender editor in a new window, like a Maya editor window (operators/menu_extras.py).
    return ("allset.open_editor", {"ui_type": ui_type})


def _dock(dock):
    return ("v3d", "allset.dock_show", {"dock": dock})


def _hud(data_path):
    return ("v3d", "wm.context_toggle", {"data_path": data_path})


def _kit_pref(prop):
    """Toggle one of this add-on's preferences (Maya HUD options are global)."""
    pkg = __package__.rpartition(".")[0]
    return ("wm.context_toggle", {"data_path": f'preferences.addons["{pkg}"].preferences.{prop}'})


# Windows > ... Editors: Maya fills these submenus at run time (Maya's labels).
# Items listed in
# CHILDREN without an action here draw greyed (step 34).
_WINDOW_EDITORS = {
    "General Editors/Attribute Editor": _dock('ATTRIBUTE_EDITOR'),
    "General Editors/Channel Box / Layer Editor": _dock('CHANNEL_BOX'),
    "General Editors/Tool Settings": ("allset.editor_toggle", {"editor": 'TOOL_SETTINGS'}),
    "General Editors/Attribute Spread Sheet": _editor('SPREADSHEET'),
    "General Editors/Display Layer Editor": ("v3d", "allset.dock_show", {"dock": 'CHANNEL_BOX', "le_tab": 'DISPLAY'}),
    "General Editors/Script Editor": "allset.script_editor",
    "Modeling Editors/UV Editor": _editor('UV'),
    "Modeling Editors/Modeling Toolkit": _dock('MODELING_TOOLKIT'),          # step 63
    "Animation Editors/Graph Editor": _editor('FCURVES'),
    "Animation Editors/Time Editor": _editor('NLA_EDITOR'),
    "Animation Editors/Trax Editor": _editor('NLA_EDITOR'),
    "Animation Editors/Camera Sequencer": _editor('SEQUENCE_EDITOR'),
    "Animation Editors/Dope Sheet": _editor('DOPESHEET'),
    "Animation Editors/Expression Editor": _editor('DRIVERS'),
    # step 54: near substitutes with a notice (ui/notices.py, PLAN W3)
    # step 188: Maya's Animation Layers relationship editor = the Layer Editor's Anim tab (kit NLA layers)
    "Relationship Editors/Animation Layers": ("v3d", "allset.dock_show", {"dock": 'CHANNEL_BOX', "le_tab": 'ANIM'}),
    # step 197 (#104): character sets are real since step 187 (operators/character_sets.py)
    "Relationship Editors/Character Sets": ("v3d", "allset.character_editor", {}),
    "General Editors/Hypergraph: Hierarchy": ("allset.hypergraph", {}),   # kit-drawn node graph (#232)
    "General Editors/Hypergraph: Connections": _editor('DRIVERS'),
    "Rendering Editors/Hypershade": "allset.hypershade",                 # step 67: browser + graph + AE
    # step 219 (Maya 2026 Windows menu): Blender engines in Maya's places
    "LookdevX Graph Editor": "allset.hypershade",                        # Maya shading graph -> Shader Editor
    "Bifrost Graph Editor": _editor('GeometryNodeTree'),                   # Bifrost graph -> Geometry Nodes
    "Rendering Editors/Light Editor": "allset.light_editor",             # an Outliner window of the lights
    "Rendering Editors/Render View": "render.view_show",
    "Rendering Editors/Render Settings": "allset.render_settings",
    "Rendering Editors/Shading Group Attributes": ("v3d", "allset.material_attributes", {}),
    "Relationship Editors/Display Layers": _dock('CHANNEL_BOX'),
}

MAP = {
    # --- File ---
    "File/New Scene": "allset.new_maya_scene",     # the Maya layout file bundled in the extension (step 130)
    # step 69: file dialogs start in the project's scenes folder (operators/project.py)
    "File/Open Scene...": "allset.open_scene",
    "File/Save Scene": "allset.save_scene",
    "File/Save Scene As...": "allset.save_scene_as",
    "File/Increment and Save": "allset.increment_save",          # step 34
    "File/Save Preferences": "wm.save_userpref",
    "File/Optimize Scene Size": "outliner.orphans_purge",
    # step 102: one Maya file dialog (Files of type + Options, cm / Y-up presets; operators/file_io.py)
    "File/Import...": "allset.file_import",
    "File/Export All...": "allset.file_export_all",
    "File/Export Selection...": "allset.file_export_selection",
    "File/Create Reference...": "allset.create_reference",           # step 69 (link + override + ns:)
    "File/Reference Editor": "allset.reference_editor",              # step 209 (ui/reference_editor.py)
    "File/Export to Offline File...": ("allset.reference_offline", {"mode": "EXPORT"}),   # step 209: edits -> JSON
    "File/Assign Offline File...": ("allset.reference_offline", {"mode": "ASSIGN"}),
    "File/Project Window": "allset.project_window",
    "File/Set Project...": "allset.set_project",
    "File/Recent Projects": ("menu", "ALLSET_MT_recent_projects"),
    "File/Recent Files": ("menu", "TOPBAR_MT_file_open_recent"),
    "File/Exit": "wm.quit_blender",
    # --- Edit ---
    "Edit/Undo": "ed.undo",
    "Edit/Redo": "ed.redo",
    "Edit/Repeat": "allset.repeat_last",                                  # step 175
    "Edit/Recent Commands List": ("menu", "ALLSET_MT_recent_commands"),
    "Edit/Cut": "allset.cut",                              # copy + delete (step 90)
    "Edit/Copy": ("v3d", "view3d.copybuffer", {}),
    "Edit/Paste": ("v3d", "allset.paste", {}),
    # Maya Delete Keys = every key of the selection (step 56; Time Slider RMB Delete = this frame / range); the
    # Key menu Cut / Copy / Snap run with the default options like Maya (Time range All); option boxes and
    # saved settings: operators/option_windows_edit.py
    "Edit/Keys/Delete Keys": ("v3d", "anim.keyframe_clear_v3d", {"confirm": False}),
    "Edit/Keys/Cut Keys": ("allset.time_keys", {"action": "CUT", "time_range": 'ALL'}),
    "Edit/Keys/Copy Keys": ("allset.time_keys", {"action": "COPY", "time_range": 'ALL'}),
    "Edit/Keys/Paste Keys": ("allset.time_keys", {"action": "PASTE"}),
    "Edit/Keys/Bake Simulation": "allset.bake_simulation",          # step 217 L18
    # step 140: Scale Keys defaults to factor 1 (a no-op), so a plain click opens the window
    "Edit/Keys/Scale Keys": "allset.opt_scale_keys",
    "Edit/Delete": "allset.delete",                              # step 164: with the hierarchy
    "Edit/Ungroup": "allset.ungroup",                            # step 34
    "Edit/Delete by Type/History": "allset.delete_history",
    "Edit/Delete by Type/Non-Deformer History": ("allset.delete_history", {"non_deformer": True}),
    **{f"Edit/Delete by Type/{k}": _del(v) for k, v in _DELETE_BY_TYPE.items()
       if v not in ('HISTORY', 'NON_DEFORMER_HISTORY')},
    **{f"Edit/Delete All by Type/{k}": _del(v, True)
       for k, v in {**_DELETE_BY_TYPE, **_DELETE_ALL_ONLY}.items()},
    "Edit/Duplicate": "allset.duplicate",                     # step 19: Maya names, in place
    "Edit/Duplicate Special": "allset.duplicate_special",
    "Edit/Duplicate with Transform": "allset.duplicate_with_transform",
    "Edit/Group": "allset.group",
    "Edit/Parent": "allset.parent",
    "Edit/Unparent": "allset.unparent",
    # --- Create ---
    **{f"Create/Polygon Primitives/{k}": v for k, v in _PRIMS.items()},
    "Create/Polygon Primitives/Interactive Creation": ("prop", "addon_prefs.interactive_creation", {}),
    "Create/Polygon Primitives/Exit On Completion": ("prop", "addon_prefs.exit_on_completion", {}),
    "Create/NURBS Primitives/Sphere": _create('NURBS_SPHERE'),
    "Create/NURBS Primitives/Cylinder": _create('NURBS_CYLINDER'),
    "Create/NURBS Primitives/Plane": _create('NURBS_PLANE'),
    "Create/NURBS Primitives/Torus": _create('NURBS_TORUS'),
    "Create/NURBS Primitives/Circle": _create('NURBS_CIRCLE'),
    "Create/Lights/Directional Light": _create('DIRECTIONAL_LIGHT'),
    "Create/Lights/Point Light": _create('POINT_LIGHT'),
    "Create/Lights/Spot Light": _create('SPOT_LIGHT'),
    "Create/Lights/Area Light": _create('AREA_LIGHT'),
    "Create/Lights/Dome Light": "allset.dome_light",                # step 276 (#201): the World environment
    "Create/Cameras": _create('CAMERA'),
    "Create/Curve Tools/CV Curve Tool": "allset.cv_curve_tool",            # step 156: operators/curve_draw.py
    "Create/Curve Tools/EP Curve Tool": "allset.ep_curve_tool",
    "Create/Curve Tools/Three Point Circular Arc": "allset.arc3_tool",
    "Create/Curve Tools/Two Point Circular Arc": "allset.arc2_tool",
    "Create/Curve Tools/Bezier Curve Tool": _create('BEZIER_CURVE'),
    "Create/Polygon Type": _create('TEXT'),                 # step 54: Maya units (W5)
    "Create/Free Image Plane": _create('IMAGE_PLANE'),
    "Create/Locator": _create('LOCATOR'),
    "Create/Annotation...": ("tool", "builtin.annotate", False),
    "Create/Measure Tools/Distance Tool": ("tool", "builtin.measure", False),
    "Create/Empty Group": _create('EMPTY_GROUP'),
    "Create/Sets/Set": "allset.create_set",                       # step 96: kit sets (operators/sets.py)
    "Create/Sets/Quick Select Set...": "allset.create_quick_select_set",
    # --- Select ---
    "Select/All": ("object.select_all", {"action": 'SELECT'}),
    "Select/Quick Select Sets": ("menu", "ALLSET_MT_quick_select_sets"),   # step 96
    "Select/All by Type/Joints": ("object.select_by_type", {"type": 'ARMATURE'}),
    # step 166: the kit's own IK handles / clusters (operators/by_type.py), particle systems, rigid bodies
    **{f"Select/All by Type/{label}": ("allset.select_all_by_type", {"type": kind})
       for label, kind in (("IK Handles", 'IK_HANDLES'), ("Clusters", 'CLUSTERS'), ("Particles", 'PARTICLES'),
                           ("Rigid Bodies", 'RIGID_BODIES'), ("Wires", 'WIRES'), ("nCloths", 'NCLOTHS'),
                           ("nParticles", 'NPARTICLES'), ("nRigids", 'NRIGIDS'))},      # step 202: the last four
    "Select/All by Type/Lattices": ("object.select_by_type", {"type": 'LATTICE'}),
    "Select/All by Type/Transforms": ("object.select_by_type", {"type": 'EMPTY'}),
    "Select/All by Type/Geometry": ("object.select_by_type", {"type": 'MESH'}),
    "Select/All by Type/NURBS Curves": ("object.select_by_type", {"type": 'CURVE'}),
    "Select/All by Type/NURBS Surfaces": ("object.select_by_type", {"type": 'SURFACE'}),
    "Select/All by Type/Polygon Geometry": ("object.select_by_type", {"type": 'MESH'}),
    "Select/All by Type/Cameras": ("object.select_by_type", {"type": 'CAMERA'}),
    "Select/All by Type/Lights": ("object.select_by_type", {"type": 'LIGHT'}),
    "Select/Deselect All": ("object.select_all", {"action": 'DESELECT'}),
    "Select/Hierarchy": ("object.select_grouped", {"type": 'CHILDREN_RECURSIVE', "extend": True}),
    "Select/Inverse": ("object.select_all", {"action": 'INVERT'}),
    "Select/Similar": ("object.select_grouped", {"type": 'TYPE'}),
    "Select/Grow": "mesh.select_more",
    "Select/Shrink": "mesh.select_less",
    "Select/Object/Component": "allset.toggle_sel_mode",
    "Select/Components/Multi-Component": ("allset.component_mode", {"type": 'MULTI'}),
    "Select/Components/Vertex": ("allset.component_mode", {"type": 'VERT'}),
    "Select/Components/Edge": ("allset.component_mode", {"type": 'EDGE'}),
    "Select/Components/Face": ("allset.component_mode", {"type": 'FACE'}),
    "Select/Contiguous Edges": ("allset.select_loops", {"ring": False}),
    # Step 141: To Vertices / Edges / Faces = the components the
    # selection touches (Ctrl+F9-F11's operator), the other conversions operators/select_convert.py.
    "Select/Convert Selection/To Vertices": ("allset.convert_selection", {"type": 'VERT'}),
    "Select/Convert Selection/To Edges": ("allset.convert_selection", {"type": 'EDGE'}),
    "Select/Convert Selection/To Edge Loop": ("allset.select_loops", {"ring": False}),
    "Select/Convert Selection/To Edge Ring": ("allset.select_loops", {"ring": True}),
    "Select/Convert Selection/To Edge Perimeter": _sel('EDGE_PERIMETER'),
    "Select/Convert Selection/To Faces": ("allset.convert_selection", {"type": 'FACE'}),
    "Select/Convert Selection/To Face Perimeter": _sel('FACE_PERIMETER'),
    "Select/Convert Selection/To Shell": "mesh.select_linked",
    "Select/Convert Selection/To Vertex Perimeter": _sel('VERTEX_PERIMETER'),
    "Select/Convert Selection/To Face Path": _sel('FACE_PATH'),
    "Select/Convert Selection/To UVs": _sel('UVS'),
    "Select/Convert Selection/To UV Shell Border": _sel('UV_SHELL_BORDER'),
    "Select/Convert Selection/To UV Perimeter": _sel('UV_PERIMETER'),
    "Select/Convert Selection/To UV Edge Loop": _sel('UV_EDGE_LOOP'),
    "Select/Convert Selection/To Shell Border": _sel('SHELL_BORDER'),
    "Select/Grow Along Loop": _sel('GROW_LOOP'),
    "Select/Shrink Along Loop": _sel('SHRINK_LOOP'),
    "Select/Components/UV": ("allset.uv_component", {"mode": 'UV'}),           # the F12 / Alt+F12 keys (step 66)
    "Select/Components/UV Shell": ("allset.uv_component", {"mode": 'SHELL'}),
    # --- Modify ---
    "Modify/Transformation Tools/Move Tool": ("tool", "builtin.move", False),
    "Modify/Transformation Tools/Rotate Tool": ("tool", "builtin.rotate", False),
    "Modify/Transformation Tools/Scale Tool": ("tool", "builtin.scale", False),
    "Modify/Transformation Tools/Universal Manipulator": ("tool", "builtin.transform", False),
    "Modify/Transformation Tools/Move/Rotate/Scale Tool": ("tool", "builtin.transform", False),
    "Modify/Reset Transformations": "allset.reset_transform",
    "Modify/Freeze Transformations": "allset.freeze_transform",
    "Modify/Center Pivot": "allset.center_pivot",
    # step 59: pivot / align
    "Modify/Bake Pivot": "allset.bake_pivot",
    "Modify/Zero Pivot": "allset.reset_pivot",              # Maya 2026 ZeroPivot = xform -ztp (step 219)
    "Modify/Match Transformations/Match All Transforms": ("allset.match_transform", {"kind": 'ALL'}),
    "Modify/Match Transformations/Match Translation": ("allset.match_transform", {"kind": 'TRANSLATE'}),
    "Modify/Match Transformations/Match Rotation": ("allset.match_transform", {"kind": 'ROTATE'}),
    "Modify/Match Transformations/Match Scaling": ("allset.match_transform", {"kind": 'SCALE'}),
    "Modify/Match Transformations/Match Pivots": "allset.match_pivots",
    "Modify/Snap Align Objects/Point to Point": ("allset.snap_points", {"count": 1}),
    "Modify/Snap Align Objects/2 Points to 2 Points": ("allset.snap_points", {"count": 2}),
    "Modify/Snap Align Objects/3 Points to 3 Points": ("allset.snap_points", {"count": 3}),
    "Modify/Snap Align Objects/Align Objects": "allset.align_objects",
    "Modify/Snap Together Tool": "allset.snap_together",
    "Modify/Make Live": "allset.make_live",
    "Modify/Add Attribute...": "allset.add_attribute",     # Attributes section (EXTRA), step 62
    "Modify/Edit Attribute...": "allset.edit_attribute",
    "Modify/Delete Attribute...": "allset.delete_attribute",
    "Windows/Switch to Blender": ("allset.switch_mode", {"mode": 'BLENDER'}),
    "Modify/Convert/NURBS to Polygons": ("object.convert", {"target": 'MESH'}),
    # step 168: only the kit's smooth-preview modifiers are applied (Maya keeps skinCluster1
    # etc.); object.convert baked every modifier
    "Modify/Convert/Smooth Mesh Preview to Polygons": "allset.smooth_to_polygons",
    "Modify/Convert/Polygon Edges to Curve": ("object.convert", {"target": 'CURVE'}),
    "Modify/Convert/Type to Curves": ("object.convert", {"target": 'CURVE'}),
    "Modify/Convert/Instance to Object": "object.duplicates_make_real",
    # --- Display ---
    "Display/Grid": ("v3d", "allset.toggle_grid", {}),     # Maya grid (ui/maya_grid.py, step 45)
    # one Maya visibility = hide_viewport (operators/visibility.py, step 129 #26)
    "Display/Hide": ("allset.visibility", {"action": 'HIDE'}),
    "Display/Show": ("allset.visibility", {"action": 'SHOW_ALL'}),
    # step 248 (#165): joints = their skeleton's bone axes, objects = every selected one (operators/joint_display.py)
    "Display/Transform Display/Local Rotation Axes": "allset.local_rotation_axes",
    "Display/Frame All in All Views": ("allset.frame_all_views", {"selected": False}),
    "Display/Frame Selection in All Views": ("allset.frame_all_views", {"selected": True}),
    "Display/Frame Selection with Children in All Views": ("allset.frame_all_views",
                                                           {"selected": True, "children": True}),
    # --- Windows ---
    "Windows/Workspaces": ("menu", "ALLSET_MT_maya_workspaces"),     # step 160: the Maya workspaces + Reset (#81)
    # Maya raises a docked Outliner, else opens a floating one (ui/maya_dock.py, step 116)
    "Windows/Outliner": ("allset.panel_show", {"panel": 'OUTLINER'}),
    "Windows/Node Editor": _editor('ShaderNodeTree'),
    **{f"Windows/{path}": action for path, action in _WINDOW_EDITORS.items()},
    "Windows/UI Elements": ("menu", "ALLSET_MT_ui_elements"),
    # Settings/Preferences submenu (Maya 2026 Windows menu; step 120)
    "Windows/Settings/Preferences/Preferences": "allset.maya_preferences",   # step 215: kit window
    "Windows/Settings/Preferences/Hotkey Editor": "allset.hotkey_editor",   # step 215: Maya list + kit keys
    "Windows/Settings/Preferences/Color Settings": "allset.color_settings",   # viewport background
    "Windows/Settings/Preferences/Marking Menu Editor": "allset.marking_menu_editor",   # kit window
    "Windows/Settings/Preferences/Plug-in Manager": ("screen.userpref_show", {"section": 'ADDONS'}),
    "Windows/Playblast": ("v3d", "allset.playblast", {}),              # step 70: temp movie + player
    "Windows/Output Window": "wm.console_toggle",
    # --- Mesh (Modeling) ---
    "Mesh/Combine": "allset.combine",                     # Maya: new pCube2, centre pivot (step 63)
    "Mesh/Separate": "allset.separate",                   # object mode: polySurfaceN under a group
    "Mesh/Booleans/Union": ("allset.boolean", {"operation": 'UNION'}),
    "Mesh/Booleans/Difference (A - B)": ("allset.boolean", {"operation": 'DIFFERENCE'}),
    "Mesh/Booleans/Intersection": ("allset.boolean", {"operation": 'INTERSECT'}),
    # step 219: Maya 2026 Booleans (PolygonBooleanDifferenceBA = Difference B - A)
    "Mesh/Booleans/Difference (B - A)": ("allset.boolean", {"operation": 'DIFFERENCE_BA'}),
    "Mesh/Unsmooth": ("v3d", "mesh.unsubdivide", {}),        # UnsmoothPolygon -> Blender Un-Subdivide
    "Mesh/Fill Hole": "mesh.fill_holes",
    "Mesh/Reduce": _mod('DECIMATE'),
    "Mesh/Remesh": _mod('REMESH'),
    "Mesh/Smooth": "allset.smooth",            # real polySmoothFace geometry (step 139)
    "Mesh/Triangulate": _mod('TRIANGULATE'),
    "Mesh/Quadrangulate": "mesh.tris_convert_to_quads",
    "Mesh/Mirror": "allset.mirror",                       # applied, world plane; □ = Mirror Options
    "Mesh/Transfer Attributes": _mod('DATA_TRANSFER'),
    "Mesh/Smooth Proxy/Subdiv Proxy": _mod('SUBSURF'),
    # --- Edit Mesh ---
    "Edit Mesh/Add Divisions": "mesh.subdivide",
    "Edit Mesh/Bevel": ("v3d", "allset.bevel", {}),           # polyBevel3 at once, editable (step 139, #16)
    "Edit Mesh/Bridge": "mesh.bridge_edge_loops",
    "Edit Mesh/Collapse": "mesh.edge_collapse",
    "Edit Mesh/Connect": "allset.connect",      # = Mesh Tools > Connect (step 139)
    "Edit Mesh/Extrude": ("v3d", "allset.extrude", {}),       # polyExtrudeFace (step 65)
    "Edit Mesh/Smart Extrude": ("v3d", "allset.smart_extrude", {}),
    "Edit Mesh/Merge": "allset.merge",          # alwaysMergeTwoVertices (step 139)
    "Edit Mesh/Merge to Center": ("mesh.merge", {"type": 'CENTER'}),
    "Edit Mesh/Symmetrize": "allset.symmetrize",   # pick the seam edge first (step 139)
    "Edit Mesh/Average Vertices": "mesh.vertices_smooth",
    "Edit Mesh/Chamfer Vertices": ("v3d", "mesh.bevel", {"affect": 'VERTICES'}),
    "Edit Mesh/Delete Edge/Vertex": "mesh.dissolve_mode",
    "Edit Mesh/Flip Triangle Edge": "mesh.edge_rotate",
    "Edit Mesh/Spin Edge Backward": ("mesh.edge_rotate", {"use_ccw": True}),
    "Edit Mesh/Spin Edge Forward": ("mesh.edge_rotate", {"use_ccw": False}),
    "Edit Mesh/Duplicate": ("v3d", "mesh.duplicate_move", {}),
    "Edit Mesh/Extract": ("mesh.separate", {"type": 'SELECTED'}),
    "Edit Mesh/Poke": "mesh.poke",
    # --- Mesh Tools ---
    "Mesh Tools/Hide Modeling Toolkit": ("allset.editor_toggle", {"editor": 'MODELING_TOOLKIT'}),
    "Mesh Tools/Create Polygon": "allset.create_polygon_start",       # step 144: kit tool, a new polySurfaceN
    "Mesh Tools/Insert Edge Loop": ("tool", "allset.insert_edge_loop_tool", True),   # step 144: click = loop there
    "Mesh Tools/Multi-Cut": ("tool", "allset.multi_cut_tool", True),      # step 129
    "Mesh Tools/Offset Edge Loop": ("tool", "allset.offset_edge_loop_tool", True),   # step 144: drag = 2 loops
    "Mesh Tools/Quad Draw": "allset.quad_draw_start",                # step 144: kit tool on the live surface
    "Mesh Tools/Slide Edge": ("tool", "allset.slide_edge_tool", True),        # step 144: MMB drag slides
    "Mesh Tools/Target Weld": ("tool", "allset.target_weld_tool", True),     # step 64
    "Mesh Tools/Crease Tool": ("tool", "allset.crease_tool", True),
    # --- Mesh Display ---
    "Mesh Display/Average": "allset.average_normals",     # step 189: Maya distance rule (normals_maya.py)
    "Mesh Display/Conform": "mesh.normals_make_consistent",
    "Mesh Display/Reverse": "mesh.flip_normals",
    "Mesh Display/Set to Face": "allset.set_to_face_normal",
    "Mesh Display/Set Vertex Normal": "allset.set_vertex_normal",
    # Maya polySoftEdge: edges selected = those, object = every edge (step 101)
    "Mesh Display/Harden Edge": ("allset.soften_harden", {"angle": 0.0}),
    "Mesh Display/Soften Edge": ("allset.soften_harden", {"angle": 180.0}),
    "Mesh Display/Paint Vertex Color Tool": "paint.vertex_paint_toggle",
    # --- Curves ---
    "Curves/Open/Close": "curve.cyclic_toggle",
    "Curves/Insert Knot": "curve.subdivide",
    "Curves/Smooth": "allset.curve_smooth_curves",    # Maya smoothCurve on CVs, ends kept (step 196)
    "Curves/Reverse Direction": "curve.switch_direction",
    # --- Deform (Modeling, Rigging, Animation share it) ---
    "Deform/Blend Shape": "allset.blend_shape",          # targets, then the base (join_shapes, step 62)
    "Deform/Blend Shape#2/Add": "allset.blend_shape",
    # Maya deformers = kit-made modifiers + handles with Maya names and options (step 144, operators/deformers.py);
    # Solidify (Maya: keeps sections rigid; Blender's Solidify adds thickness) is greyed with a notice
    "Deform/Delta Mush": _deformer('DELTA_MUSH'),
    "Deform/Lattice": _deformer('LATTICE'),
    "Deform/Wrap": _deformer('WRAP'),
    "Deform/ShrinkWrap": _deformer('SHRINK_WRAP'),
    "Deform/Nonlinear/Wave": _deformer('WAVE'),
    "Deform/Texture": _deformer('TEXTURE'),
    "Deform/Paint Membership": "paint.weight_paint_toggle",
    # --- UV ---
    "UV/UV Editor": _editor('UV'),
    "UV/Planar": "allset.uv_planar",
    "UV/Normal-Based": "allset.uv_planar",
    "UV/Automatic": "allset.uv_automatic",      # Maya polyAutoProjection (step 139)
    "UV/Camera-based": ("v3d", "uv.project_from_view", {}),
    "UV/Cylindrical": ("v3d", "uv.cylinder_project", {}),
    "UV/Spherical": ("v3d", "uv.sphere_project", {}),
    "UV/Cut UV Edges": "allset.uv_cut",          # seam + shells apart in place (step 66)
    "UV/Sew UV Edges": "allset.uv_sew",
    "UV/3D Cut and Sew UV Tool": "allset.cut_sew_tool_set",   # step 79          # seam cleared + the smaller shell moved onto the edge
    "UV/Merge UVs": "allset.uv_merge",     # Maya polyMergeUV: per vertex within 0.01 (step 196)
    # --- Skeleton (Rigging) ---
    # step 187: Maya Character Sets on Blender Keying Sets (operators/character_sets.py)
    # step 217: controller tags on bones, followed by pose-mode pick walk (operators/controllers.py)
    "Control/Tag As Controller": "allset.tag_controller",
    "Control/Parent Controller": "allset.parent_controller",
    "Control/Create Character Set": "allset.character_create",
    "Control/Create Subcharacter Set": ("allset.character_create", {"sub": True}),
    "Control/Attribute Editor": "allset.character_attributes",
    "Control/Add to Character Set": ("allset.character_edit", {"add": True}),
    "Control/Remove from Character Set": ("allset.character_edit", {"add": False}),
    "Control/Merge Character Sets": "allset.character_merge",
    "Control/Select Character Set Node": ("menu", "ALLSET_MT_character_select_node"),
    "Control/Select Character Set Members": ("menu", "ALLSET_MT_character_select_members"),
    "Control/Set Current Character Set": ("menu", "ALLSET_MT_character_set_current"),
    # step 57: Joint Tool (click, click, Enter), option-box dialogs
    "Skeleton/Create Joints": "allset.joint_tool",
    "Skeleton/Quick Rig": "allset.quick_rig",              # Rigify (notice in ui/notices.py), step 62
    "Windows/Animation Editors/Quick Rig": "allset.quick_rig",
    "Skeleton/Mirror Joints": "allset.mirror_joints",
    "Skeleton/Orient Joint": "allset.orient_joint",
    # step 246 (#163): Maya's meaning (operators/skeleton_menu.py)
    "Skeleton/Remove Joints": "allset.remove_joint",
    "Skeleton/Disconnect Joint": "allset.disconnect_joint",
    "Skeleton/Create IK Handle": "allset.ik_handle",       # step 58: click start + end joint
    # --- Skin ---
    # step 58: any selection order, no parenting, Max Influences
    "Skin/Bind Skin": "allset.bind_skin",
    "Skin/Unbind Skin": "allset.unbind_skin",
    "Skin/Go to Bind Pose": "allset.go_to_bind_pose",                  # step 247: the pose stored at bind
    "Skin/Move Skinned Joints": "allset.move_skinned_joints",          # step 241 (#156): Edit mode, mesh kept
    "Skin/Paint Skin Weights": "allset.paint_skin_weights",
    "Skin/Mirror Skin Weights": "allset.mirror_skin_weights",
    "Skin/Copy Skin Weights": "allset.copy_skin_weights",
    "Skin/Copy Vertex Weights": "allset.copy_vertex_weights",
    "Skin/Paste Vertex Weights": "allset.paste_vertex_weights",
    "Skin/Edit Influences/Set Max Influences...": "allset.set_max_influences",   # step 247 (#164)
    "Skin/Smooth Skin Weights": "object.vertex_group_smooth",
    "Skin/Prune Small Weights": "allset.prune_small_weights",         # step 247: 0.01, all joints, renormalised
    "Skin/Normalize Weights/Normalize Weights": "object.vertex_group_normalize_all",
    # --- Constrain (Rigging, Animation): Maya selects targets first, the
    # constrained object last = Blender's active object.
    "Constrain/Parent": _con('CHILD_OF'),
    "Constrain/Point": _con('COPY_LOCATION'),
    "Constrain/Orient": _con('COPY_ROTATION'),
    "Constrain/Scale": _con('COPY_SCALE'),
    "Constrain/Aim": _con('TRACK_TO'),
    "Constrain/Pole Vector": "allset.pole_vector",
    "Constrain/Motion Paths/Attach to Motion Path": "allset.motion_path_attach",    # step 228 L8 (motion_path_228.py)
    "Constrain/Motion Paths/Set Motion Path Key": "allset.motion_path_key",        # step 228 L8
    "Constrain/Motion Paths/Flow Path Object": "allset.flow_path",     # step 228 L9 (flow_path_228.py)
    "Constrain/Geometry": _con('SHRINKWRAP'),
    # --- Key (Animation) ---
    # step 56: S = every keyable channel
    "Key/Set Key": "allset.set_key",
    "Key/Set Blend Shape Target Weight Keys": "allset.key_blend_shape_weights",   # step 218 L15b
    "Key/Set Key on Animated": ("anim.keyframe_insert_by_name", {"type": "Available"}),
    "Key/Set Breakdown Key": ("allset.set_key", {"breakdown": True}),
    "Key/Set Driven Key/Set...": "allset.sdk_window",      # step 62
    "Key/Set Driven Key/Go to Previous": ("allset.sdk_go", {"direction": 'PREVIOUS'}),
    "Key/Set Driven Key/Go to Next": ("allset.sdk_go", {"direction": 'NEXT'}),
    "Key/Insert Key": ("anim.keyframe_insert_by_name", {"type": "Available"}),
    "Key/Cut Keys": ("allset.time_keys", {"action": "CUT", "time_range": 'ALL'}),
    "Key/Copy Keys": ("allset.time_keys", {"action": "COPY", "time_range": 'ALL'}),
    "Key/Paste Keys": ("allset.time_keys", {"action": "PASTE"}),
    "Key/Snap Keys": ("allset.time_keys", {"action": "SNAP", "time_range": 'ALL'}),
    "Key/Hold Current Keys": ("anim.keyframe_insert_by_name", {"type": "Available"}),
    "Key/Set Key on Translate": ("allset.set_key", {"channels": "TRANSLATE"}),   # step 157: default tangents
    "Key/Set Key on Rotate": ("allset.set_key", {"channels": "ROTATE"}),   # step 157: default tangents
    "Key/Set Key on Scale": ("allset.set_key", {"channels": "SCALE"}),   # step 157: default tangents
    "Key/Delete Keys": ("v3d", "anim.keyframe_clear_v3d", {"confirm": False}),
    "Key/Bake Simulation": "allset.bake_simulation",  # step 217 L18
    # step 223 L14: Ik Blend = the handle property driving the IK constraint's Influence (operators/ik_fk.py)
    "Key/IK/FK Keys/Set IK/FK Key": "allset.ik_fk_key",
    "Key/IK/FK Keys/Enable IK Solver": ("prop", "window_manager.allset_ik_solver", {}),   # Maya check item (238)
    "Key/IK/FK Keys/Move IK to FK": "allset.move_ik_to_fk",
    "Key/Scale Keys": "allset.opt_scale_keys",
    # --- Playback ---
    "Playback/Playblast": ("v3d", "allset.playblast", {}),
    "Playback/Play": "screen.animation_play",
    "Playback/Backward": ("screen.animation_play", {"reverse": True}),
    "Playback/Stop": ("screen.animation_cancel", {"restore_frame": False}),
    "Playback/Next Key": ("screen.keyframe_jump", {"next": True}),
    "Playback/Prev Key": ("screen.keyframe_jump", {"next": False}),
    "Playback/Next Frame": ("screen.frame_offset", {"delta": 1}),
    "Playback/Prev Frame": ("screen.frame_offset", {"delta": -1}),
    "Playback/Play Range Start": ("screen.frame_jump", {"end": False}),
    "Playback/Play Range End": ("screen.frame_jump", {"end": True}),
    "Playback/Set Range to/Start/End": ("allset.time_set_range", {"mode": "START_END"}),
    "Playback/Set Range to/Min/Max": ("allset.time_set_range", {"mode": "MIN_MAX"}),
    "Playback/Set Range to/Selected": ("allset.time_set_range", {"mode": "SELECTED"}),
    "Playback/Playback Speed/Real-time": ("wm.context_set_enum", {"data_path": "scene.sync_mode",
                                                                   "value": "FRAME_DROP"}),
    # step 219: Maya 2026 Play Every Frame, Free / Max Real-time = Blender Play Every Frame (never above the fps)
    **{f"Playback/Playback Speed/Play Every Frame, {k}": ("wm.context_set_enum", {"data_path": "scene.sync_mode",
                                                                                  "value": "NONE"})
       for k in ("Free", "Max Real-time")},
    "Playback/Render Current Frame": "render.render",
    "Playback/Render Settings": "allset.render_settings",
    # --- Visualize ---
    "Visualize/Motion Trail Editor": "allset.motion_trail_editor",      # step 225 L21
    # step 171: snapshots + ghosting
    "Visualize/Create Animation Snapshot": "allset.animation_snapshot",
    "Visualize/Update Snapshot": "allset.update_snapshot",
    "Visualize/Ghosting Editor": "allset.opt_ghosting_editor",
    "Windows/Animation Editors/Ghosting Editor": "allset.opt_ghosting_editor",       # step 219 (Maya 2026)
    "Windows/Animation Editors/Motion Trail Editor": "allset.motion_trail_editor",
    "Visualize/Blue Pencil": ("v3d", "wm.tool_set_by_id", {"name": "builtin.annotate"}),   # Blender Annotate
    "Visualize/Ghost Selected": ("allset.ghost", {"action": "GHOST"}),
    "Visualize/Unghost Selected": ("allset.ghost", {"action": "UNGHOST"}),
    "Visualize/Unghost All": ("allset.ghost", {"action": "UNGHOST_ALL"}),
    # --- FX ---
    # Blender's own simulation operators, nothing rescaled (Blender simulates one unit as one metre)
    "nParticles/Emit from Object": _mod_selected('PARTICLE_SYSTEM'),
    "nParticles/Emit from Object#2": _mod_selected('PARTICLE_SYSTEM'),
    "nCloth/Create nCloth": _mod_selected('CLOTH'),
    "nCloth/Create Passive Collider": _mod_selected('COLLISION'),
    "nCloth/Remove nCloth": "allset.fx_remove_ncloth",
    "nCache/Create New Cache/nObject": ("allset.ncache", {"action": 'CREATE', "kind": 'NOBJECT'}),
    "nCache/Create New Cache/Maya Fluid": ("allset.ncache", {"action": 'CREATE', "kind": 'FLUID'}),
    "nCache/Delete Cache": ("allset.ncache", {"action": 'DELETE', "kind": 'ALL'}),
    "Fields/Solvers/Interactive Playback": "screen.animation_play",
    "nHair/Create Hair": "object.curves_empty_hair_add",
    "Fluids/3D Container": "allset.fluid_quick_smoke",
    "Fluids/Ocean": _mod('OCEAN'),
    # fields = Blender force field empties; Gravity / Uniform = a Wind field turned down / along +X
    "Fields/Solvers/Air": _field('WIND'),
    "Fields/Solvers/Drag": _field('DRAG'),
    "Fields/Solvers/Gravity": ("object.effector_add", {"type": 'WIND', "rotation": (math.pi, 0.0, 0.0)}),
    "Fields/Solvers/Newton": _field('FORCE'),
    "Fields/Solvers/Radial": _field('FORCE'),
    "Fields/Solvers/Turbulence": _field('TURBULENCE'),
    "Fields/Solvers/Uniform": ("object.effector_add", {"type": 'WIND', "rotation": (0.0, math.pi / 2, 0.0)}),
    "Fields/Solvers/Vortex": _field('VORTEX'),
    "Fields/Solvers/Create Active Rigid Body": ("rigidbody.objects_add", {"type": 'ACTIVE'}),
    "Fields/Solvers/Create Passive Rigid Body": ("rigidbody.objects_add", {"type": 'PASSIVE'}),
    "Fields/Solvers/Create Pin Constraint": ("rigidbody.connect", {"con_type": 'POINT'}),
    "Fields/Solvers/Create Hinge Constraint": ("rigidbody.connect", {"con_type": 'HINGE'}),
    "Fields/Solvers/Create Spring Constraint": ("rigidbody.connect", {"con_type": 'GENERIC_SPRING'}),
    "Effects/Fire": ("allset.fluid_quick_smoke", {"style": 'FIRE'}),
    "Effects/Smoke": "allset.fluid_quick_smoke",
    # --- Rendering ---
    # Materials (operators/material.py, step 29).
    "Lighting/Shading/Material Attributes": ("v3d", "allset.material_attributes", {}),
    # Maya 2026: Assign New Material is a submenu (favourites + New Material...) (step 219)
    "Lighting/Shading/Assign New Material/New Material...": "allset.assign_new_material",
    "Lighting/Shading/Assign Favorite Material": ("menu", "ALLSET_MT_assign_favorite_material"),
    "Lighting/Shading/Assign Existing Material": ("menu", "ALLSET_MT_assign_existing_material"),
    "Texturing/3D Paint Tool": "paint.texture_paint_toggle",
    "Render/Render Settings...": "allset.render_settings",
    # Render menu: Blender's own render (INVOKE opens Blender's Render window, Maya's Render View) through the scene
    # camera, at the Output properties size; Esc stops it.
    "Render/Render Using": ("menu", "ALLSET_MT_render_using"),
    "Render/Render Current Frame": "render.render",
    "Render/Redo Previous Render": "render.render",
    "Render/IPR Render Current Frame": "allset.ipr_toggle",
    "Render/Redo Previous IPR Render": "allset.ipr_toggle",
    "Render/Render Sequence": ("render.render", {"animation": True}),
    "Render/Test Resolution": ("menu", "ALLSET_MT_test_resolution"),     # Blender's Resolution %
    "Render/Batch Render": ("render.render", {"animation": True}),
    "Render/Show Batch Render": "render.view_show",
}

# Items Maya adds at run time, inserted after a data path: {after path: [item]} with
# items like menu_data's ((label,) or ("-", section label)). Modify's Pivot / Naming / Attributes
# sections now come from tools/gen_menu_data.py RUNTIME_LABELS (step 101).
EXTRA = {
    # The kit's own switch back to plain Blender (switch.py, step 60): found by the menu search too.
    "Windows/Settings/Preferences": [("Switch to Blender",)],
    # Dome Light (#201): renderers add it to Maya; here = Blender's World environment (operators/dome_light.py)
    "Create/Lights/Volume Light": [("-", ""), ("Dome Light",)],
}

# Submenus Maya builds at run time, so Maya's static menu structure has them as leaves (or with a
# placeholder child): {label path: [items like menu_data's]}. Their actions are in MAP.
CHILDREN = {
    # Step 219: the other run-time submenus (Windows > ... Editors, Modify > Match Transformations / Snap Align
    # Objects, Display > Heads Up Display) now come from the Maya 2026 menus in ui/menu_data.py.
    # Windows > Settings/Preferences (Maya 2026 Windows menu; Performance
    # Settings only with the legacy viewport, off by default; step 120)
    "Windows/Settings/Preferences": [
        ("Preferences",), ("-", ""), ("Hotkey Editor",), ("Color Settings",), ("Marking Menu Editor",),
        ("Shelf Editor",), ("Panel Editor",), ("-", ""), ("Plug-in Manager",)],
}
MAP.update({
    "Display/Heads Up Display/Poly Count": _hud("space_data.overlay.show_stats"),
    # Maya furniture (ui/view_furniture.py, step 46): global like Maya's HUD.
    "Display/Heads Up Display/Camera Names": _kit_pref("maya_camera_names"),
    "Display/Heads Up Display/View Axis": _kit_pref("maya_view_axis"),
    "Display/Heads Up Display/ViewCube": _kit_pref("maya_viewcube"),
})


def _props(tab):
    # A Properties window on one tab (Maya editors whose Blender counterpart is a Properties panel).
    return ("allset.open_editor", {"ui_type": 'PROPERTIES', "tab": tab})


def _url(url):
    return ("wm.url_open", {"url": url})


def _sculpt(brush):
    return ("allset.sculpt_tool", {"brush": brush})


_PROPORTIONAL = ("wm.context_toggle", {"data_path": "tool_settings.use_proportional_edit"})
_MANUAL = "https://docs.blender.org/manual/en/4.5/"
_API = "https://docs.blender.org/api/4.5/"
_NOTES = "https://developer.blender.org/docs/release_notes/4.5/"
_TUTORIALS = "https://www.blender.org/support/tutorials/"

# step 101: what Blender does cheaply. Items whose meaning differs carry a
# notice (ui/notices.py NOTICES).
MAP.update({
    # File
    "File/Archive Scene": "file.pack_all",
    "File/View Image...": _editor('IMAGE_EDITOR'),
    "File/View Sequence...": "render.play_rendered_anim",
    "File/Recent Increments": ("menu", "TOPBAR_MT_file_open_recent"),
    "File/Game Exporter": "allset.game_exporter",       # step 225 L24 (operators/game_exporter.py)
    "File/Send To Unity": "export_scene.fbx",
    "File/Send To Unreal": "export_scene.fbx",
    # Edit
    "Edit/Keys/Snap Keys": ("allset.time_keys", {"action": "SNAP", "time_range": 'ALL'}),
    "Edit/Delete All by Type/Shading Groups and Materials": "outliner.orphans_purge",
    # Create
    "Create/SVG": "import_curve.svg",
    "Create/Universal Scene Description (USD)": "wm.usd_import",
    # Select
    "Select/Shortest Edge Path Tool": "mesh.shortest_path_select",
    "Select/Convert Selection/To Contained Edges": ("mesh.select_mode", {"type": 'EDGE'}),
    "Select/Convert Selection/To Contained Faces": ("mesh.select_mode", {"type": 'FACE'}),
    "Select/Convert Selection/To UV Shell": ("mesh.select_linked", {"delimit": {'UV'}}),
    "Select/All CVs": ("curve.select_all", {"action": 'SELECT'}),
    "Select/First CV": "curve.de_select_first",
    "Select/Last CV": "curve.de_select_last",
    "Select/All by Type/Image Planes": ("object.select_by_type", {"type": 'EMPTY'}),
    # Modify
    "Modify/Transformation Tools/Proportional Modification Tool": _PROPORTIONAL,
    "Modify/Transformation Tools/Soft Modification Tool": _PROPORTIONAL,
    "Modify/Transformation Tools/Move Normal Tool": ("v3d", "transform.shrink_fatten", {}),
    "Modify/Prefix Hierarchy Names...": "allset.prefix_hierarchy",
    "Modify/Search and Replace Names...": "allset.search_replace_names",
    "Modify/Replace Objects": ("object.make_links_data", {"type": 'OBDATA'}),
    "Modify/Convert/NURBS Curve to Bezier": ("curve.spline_type_set", {"type": 'BEZIER'}),
    "Modify/Convert/Bezier Curve to NURBS": ("curve.spline_type_set", {"type": 'NURBS'}),
    # step 168: Modify leaves
    "Modify/Reorder Rotation...": "allset.reorder_rotation",     # step 229: Maya xform -roo -p
    "Modify/Paint Attributes Tool": "paint.weight_paint_toggle",  # Blender paints vertex group weights
    "Modify/Evaluate Nodes/Evaluate All": ("allset.evaluate_all", {"on": True}),
    "Modify/Evaluate Nodes/Ignore All": ("allset.evaluate_all", {"on": False}),
    **{f"Modify/Evaluate Nodes/{label}": ("prop", f"scene.allset_eval.{kind}", {})
       for label, kind in (("IK Solvers", "iksolver"), ("Constraints", "constraint"), ("Expressions", "expression"),
                           ("Fluids", "fluid"), ("nCloths", "ncloth"), ("nParticles", "nparticle"),
                           ("nRigids", "nrigid"), ("Particles", "particle"), ("Rigid Bodies", "rigidbody"),
                           ("Snapshots", "snapshot"))},
    **{f"Modify/Transformation Tools/Default Object Manipulator/{label}": ("allset.default_manip", {"value": i})
       for i, label in enumerate(("None", "Move", "Rotate", "Scale", "Transform"))},
    "Modify/Transformation Tools/Show Manipulator Tool": ("v3d", "allset.show_manipulator", {}),
    "Modify/Align Tool": "allset.align_tool",
    "Modify/Snap Align Objects/Position Along Curve": "allset.position_along_curve",
    "Modify/Convert/Geometry to Bounding Box": "allset.geometry_to_bbox",
    # Display
    # Blender's playback frame rate display is a preference (#43): open it, don't write it
    "Display/Heads Up Display/Frame Rate": ("screen.userpref_show", {"section": 'VIEWPORT'}),
    "Display/Heads Up Display/Object Details": _hud("space_data.overlay.show_stats"),
    "Display/Heads Up Display/Select Details": _hud("space_data.overlay.show_stats"),
    "Display/Toggle Show/Hide": ("allset.visibility", {"action": 'TOGGLE'}),
    "Display/Object Display/Template": ("allset.object_display", {"kind": 'TEMPLATE'}),
    "Display/Object Display/Untemplate": ("allset.object_display", {"kind": 'UNTEMPLATE'}),
    "Display/Object Display/Bounding Box": ("allset.object_display", {"kind": 'BBOX'}),
    "Display/Object Display/No Bounding Box": ("allset.object_display", {"kind": 'NO_BBOX'}),
    # Display > Polygons is Maya's submenu, no longer a leaf. Its check items are the overlays of the 3D View
    # the menu acts on ("view3d.", ui/status_line.view3d_space), drawn on meshes in edit mode; Maya's Standard /
    # Soft/Hard Edges pair = Blender's Sharp edge overlay off / on; Custom Polygon Display = Blender's edit-mode
    # overlay popover (the item this menu used to be). The rest is greyed with a notice (ui/notices.py).
    "Display/Polygons/Backface Culling": ("prop", "view3d.shading.show_backface_culling", {}),
    "Display/Polygons/Face Normals": ("prop", "view3d.overlay.show_face_normals", {}),
    "Display/Polygons/Vertex Normals": ("prop", "view3d.overlay.show_vertex_normals", {}),
    "Display/Polygons/Normals Size...": "allset.normals_size",
    "Display/Polygons/Standard Edges": ("prop", "view3d.overlay.show_edge_sharp", {"value": False}),
    "Display/Polygons/Soft/Hard Edges": ("prop", "view3d.overlay.show_edge_sharp", {"value": True}),
    "Display/Polygons/Hard Edges (color)": ("prop", "view3d.overlay.show_edge_sharp", {}),
    "Display/Polygons/Crease Edges": ("prop", "view3d.overlay.show_edge_crease", {}),
    "Display/Polygons/Texture Border Edges": ("prop", "view3d.overlay.show_edge_seams", {}),
    "Display/Polygons/Face Centers": ("prop", "view3d.overlay.show_face_center", {}),
    "Display/Polygons/Reset Display": "allset.poly_display_reset",
    "Display/Polygons/Custom Polygon Display": ("v3d", "wm.call_panel", {"name": "VIEW3D_PT_overlay_edit_mesh",
                                                                         "keep_open": True}),
    # Blender's vertex and edge sizes are theme preferences (#43): open them, searched for the setting, don't write them
    "Display/Polygons/Vertex Size...": ("allset.theme_setting", {"name": "Vertex Size"}),
    "Display/Polygons/Edge Width...": ("allset.theme_setting", {"name": "Edge Width"}),
    "Display/Animation": ("v3d", "wm.call_panel", {"name": "VIEW3D_PT_overlay_bones", "keep_open": True}),
    "Display/Animation/Joint Size...": "allset.joint_size",              # step 248: Maya jointDisplayScale
    "Display/Rendering": ("v3d", "wm.call_panel", {"name": "VIEW3D_PT_shading", "keep_open": True}),
    # step 226 (#136): Maya's Wireframe Color window (user palette 1-8 / RGB, Apply / Default / Close)
    "Display/Wireframe Color...": ("allset.wireframe_color", {}),
    # Windows
    # step 213 (#119, audit 16 NB12): the kit's Maya windows instead of Blender's Spreadsheet / Drivers editors
    "Windows/General Editors/Component Editor": ("allset.component_editor", {}),
    "Windows/General Editors/Connection Editor": ("allset.connection_editor", {}),
    "Windows/General Editors/File Path Editor": ("allset.open_editor", {"ui_type": 'OUTLINER',
                                                                          "display_mode": 'LIBRARIES'}),
    "Windows/General Editors/Command Shell": _editor('CONSOLE'),
    "Windows/Animation Editors/Shape Editor": ("allset.shape_editor", {}),
    # step 227 L16 (#137): Pose Space Deformation (operators/pose_space_227.py, ui/pose_editor.py)
    "Windows/Animation Editors/Pose Editor": ("allset.pose_editor", {}),
    "Deform/Pose Space Deformation/Pose Editor": ("allset.pose_editor", {}),
    "Deform/Pose Space Deformation/Create Pose Interpolator": ("allset.pose_interpolator_create", {}),
    "Windows/Rendering Editors/Render Setup": _props('VIEW_LAYER'),   # Maya 2026 (step 219)
    # Maya's Light Linking editors: Blender's Light Linking panel (Object Properties > Shading, active light)
    "Windows/Relationship Editors/Light Linking/Light-Centric": _props('OBJECT'),
    "Windows/Relationship Editors/Light Linking/Object-Centric": _props('OBJECT'),
    "Windows/Relationship Editors/Sets": _editor('OUTLINER'),
    "Windows/Content Browser": _editor('ASSETS'),
    # Mesh
    "Mesh/Conform": _mod('SHRINKWRAP'),
    "Mesh/Retopologize": "object.quadriflow_remesh",
    "Mesh/Transfer Shading Sets": ("object.make_links_data", {"type": 'MATERIAL'}),
    "Mesh/Cleanup...": "allset.poly_cleanup",   # Maya leaf + Cleanup Options window (step 197, #104)
    "Mesh/Smooth Proxy/Crease Tool": ("tool", "allset.crease_tool", True),
    "Mesh/Smooth Proxy/Toggle Proxy Display": ("allset.smooth_proxy", {"action": 'TOGGLE'}),
    "Mesh/Smooth Proxy/Both Proxy and Subdiv Display": ("allset.smooth_proxy", {"action": 'BOTH'}),
    # Edit Mesh
    "Edit Mesh/Detach": "allset.detach",
    "Edit Mesh/Transform": ("tool", "builtin.transform", True),
    "Edit Mesh/Flip": ("v3d", "transform.mirror", {"orient_type": 'LOCAL', "constraint_axis": (True, False, False)}),
    "Edit Mesh/Edit Edge Flow": "allset.edge_flow",
    "Edit Mesh/Wedge": "allset.wedge",
    "Edit Mesh/Split Mesh with Projected Curve": ("v3d", "mesh.knife_project", {}),
    # Mesh Tools (Sculpting Tools -> the essentials brushes)
    "Mesh Tools/Append to Polygon": "allset.append_polygon_start",   # step 144: border edge + points, Enter
    **{f"Mesh Tools/Sculpting Tools/{maya} Tool": _sculpt(brush) for maya, brush in (
        ("Sculpt", "Draw"), ("Smooth", "Smooth"), ("Relax", "Relax Slide"), ("Grab", "Grab"),
        ("Pinch", "Pinch/Magnify"), ("Flatten", "Flatten/Contrast"), ("Foamy", "Clay"), ("Wax", "Clay Strips"),
        ("Scrape", "Scrape/Fill"), ("Fill", "Fill/Deepen"), ("Knife", "Crease Sharp"), ("Smear", "Smear"),
        ("Bulge", "Inflate/Deflate"), ("Amplify", "Sharpen"), ("Freeze", "Mask"))},
    # Mesh Display
    "Mesh Display/Soften/Harden Edges": "allset.soften_harden",
    "Mesh Display/Lock Normals": "allset.lock_normals",     # step 189: only the selection (Maya)
    "Mesh Display/Unlock Normals": ("allset.lock_normals", {"unlock": True}),
    "Mesh Display/Vertex Normal Edit Tool": ("v3d", "transform.rotate_normal", {}),
    "Mesh Display/Create Empty Set": "geometry.color_attribute_add",
    "Mesh Display/Delete Current Set": "geometry.color_attribute_remove",
    # step 189: Maya colour commands (operators/color_sets_maya.py)
    "Mesh Display/Apply Color": "allset.apply_color",
    "Mesh Display/Rename Current Set...": "allset.color_set_rename",
    "Mesh Display/Modify Current Set": "allset.color_set_modify",
    "Mesh Display/Set Keyframe for Vertex Color": "allset.color_keyframe",
    "Mesh Display/Prelight (Maya)": "allset.prelight",
    "Mesh Display/Assign New Set": "allset.bake_set_assign_new",
    "Mesh Display/Assign Existing Set": "allset.bake_set_assign",
    "Mesh Display/Edit Assigned Set": "allset.bake_set_edit",
    "Mesh Display/Per Instance Sharing/Select Shared Instances": "allset.select_shared_instances",
    "Mesh Display/Color Set Editor": _props('DATA'),
    "Mesh Display/Toggle Display Colors Attribute": ("v3d", "wm.context_set_enum",
                                                     {"data_path": "space_data.shading.color_type",
                                                      "value": 'VERTEX'}),
    # Curves
    "Curves/Attach": "allset.curve_attach",          # step 156: operators/curves_maya.py (Maya-style)
    "Curves/Detach": "allset.curve_detach",
    "Curves/Rebuild": "allset.curve_rebuild",
    "Curves/Fillet": "allset.curve_fillet",
    "Curves/Cut": "allset.curve_cut",
    "Curves/Straighten": "allset.curve_straighten",
    "Curves/Move Seam": "allset.curve_move_seam",
    # step 207 (operators/curves_207.py)
    "Curves/Lock Length": ("allset.curve_lock_length", {"lock": True}),
    "Curves/Unlock Length": ("allset.curve_lock_length", {"lock": False}),
    "Curves/Bend": ("allset.curve_modify", {"kind": 'BEND'}),
    "Curves/Curl": ("allset.curve_modify", {"kind": 'CURL'}),
    "Curves/Scale Curvature": ("allset.curve_modify", {"kind": 'CURVATURE'}),
    "Curves/CV Hardness": "allset.curve_cv_hardness",
    "Curves/Fit B-spline": "allset.curve_fit_bspline",
    "Curves/Align": "allset.curve_align",
    "Curves/Duplicate Surface Curves": "allset.duplicate_surface_curves",
    "Curves/Intersect": "allset.curve_intersect",
    "Curves/Bezier Curves/Tangent Options/Uneven Anchor Tangents": ("curve.handle_type_set", {"type": 'ALIGNED'}),
    "Curves/Extend/Extend Curve": ("v3d", "curve.extrude_move", {}),
    "Curves/Smooth#2": "curve.smooth",
    "Curves/Bezier Curves/Anchor Presets/Bezier": ("curve.handle_type_set", {"type": 'ALIGNED'}),
    "Curves/Bezier Curves/Anchor Presets/Bezier Corner": ("curve.handle_type_set", {"type": 'FREE_ALIGN'}),
    "Curves/Bezier Curves/Anchor Presets/Corner": ("curve.handle_type_set", {"type": 'VECTOR'}),
    "Curves/Bezier Curves/Tangent Options/Smooth Anchor Tangents": ("curve.handle_type_set", {"type": 'ALIGNED'}),
    "Curves/Bezier Curves/Tangent Options/Break Anchor Tangents": ("curve.handle_type_set", {"type": 'FREE_ALIGN'}),
    "Curves/Bezier Curves/Tangent Options/Even Anchor Tangents": ("curve.handle_type_set", {"type": 'AUTOMATIC'}),
    # Surfaces: Maya NURBS surfaces as Blender NURBS surfaces (step 181, operators/surfaces_maya.py;
    # option windows operators/option_windows_surfaces.py)
    "Surfaces/Revolve": "allset.revolve",
    "Surfaces/Birail/Birail 1 Tool": "allset.birail1",
    "Surfaces/Boundary": ("allset.surface_boundary", {"kind": 'BOUNDARY'}),
    "Surfaces/Square": ("allset.surface_boundary", {"kind": 'SQUARE'}),
    "Surfaces/Duplicate NURBS Patch": "allset.duplicate_nurbs_patch",
    "Surfaces/Attach": "allset.surface_attach",
    "Surfaces/Detach": "allset.surface_detach",
    "Surfaces/Open/Close": "curve.cyclic_toggle",
    "Surfaces/Insert Isoparms": "allset.surface_insert_isoparm",
    "Surfaces/Rebuild": "allset.surface_rebuild",
    "Surfaces/Reverse Direction": "allset.surface_reverse",
    # Deform
    "Deform/Curve Warp": _deformer('CURVE_WARP'),
    "Deform/Proximity Wrap": _deformer('PROXIMITY_WRAP'),
    "Deform/Nonlinear/Bend": _deformer('BEND'),
    "Deform/Nonlinear/Flare": _deformer('FLARE'),
    "Deform/Nonlinear/Squash": _deformer('SQUASH'),
    "Deform/Nonlinear/Sine": _deformer('SINE'),
    "Deform/Blend Shape#2/Remove": "object.shape_key_remove",
    # Paint Weights > <deformer>: Weight Paint on that deformer's vertex group (step 144; Maya's paint tool
    # "<type>"); Tension / Wire / Jiggle have no Blender deformer (greyed)
    **{f"Deform/Paint Weights/{label}": ("allset.paint_deformer_weights", {"kind": kind}) for label, kind in (
        ("Blend Shape", "blendShape"), ("Cluster", "cluster"), ("Delta Mush", "deltaMush"),
        ("Proximity Wrap", "proximityWrap"), ("Lattice", "ffd"), ("ShrinkWrap", "shrinkWrap"),
        ("Nonlinear", "nonLinear"), ("Texture Deformer", "textureDeformer"))},
    "Deform/Mirror Deformer Weights": "object.vertex_group_mirror",
    # step 169: Wire as a kit deformer + its edit items, ShrinkWrap / Lattice edits,
    # Prune Membership, Point On Curve
    "Deform/Wire": _deformer('WIRE'),
    "Deform/Paint Weights/Wire": ("allset.paint_deformer_weights", {"kind": "wire"}),
    # step 205: Maya-style deformers (operators/deformers_205a.py / _205b.py)
    **{f"Deform/{label}": ("allset.deformer_tss", {"kind": kind})
       for label, kind in (("Tension", 'TENSION'), ("Solidify", 'SOLIDIFY'), ("Sculpt", 'SCULPT'))},
    "Deform/Prune Membership/Sculpt": "allset.prune_sculpt",
    "Deform/Morph": "allset.morph",
    "Deform/Jiggle/Jiggle Deformer": "allset.jiggle",
    **{f"Deform/Paint Weights/{label}": ("allset.paint_deformer_weights", {"kind": kind})
       for label, kind in (("Tension", "tension"), ("Jiggle", "jiggle"))},
    **{f"Deform/Wire#2/{label}": ("allset.wire_edit", {"action": action}) for label, action in (
        ("Add", "ADD"), ("Remove", "REMOVE"), ("Reset", "RESET"), ("Show Base Wire", "SHOW_BASE"),
        ("Parent Base Wire", "PARENT_BASE"))},
    "Deform/Wire#2/Wire Dropoff Locator": "allset.wire_dropoff_locator",
    **{f"Deform/ShrinkWrap#2/{label}": ("allset.shrink_wrap_edit", {"action": action}) for label, action in (
        ("Set Target", "SET_TARGET"), ("Remove Target", "REMOVE_TARGET"), ("Add surfaces", "ADD_SURFACES"),
        ("Remove surfaces", "REMOVE_SURFACES"))},
    "Deform/Lattice#2/Reset Lattice": ("allset.lattice_edit", {"action": 'RESET'}),
    "Deform/Lattice#2/Remove Lattice Tweaks": ("allset.lattice_edit", {"action": 'REMOVE_TWEAKS'}),
    **{f"Deform/Prune Membership/{label}": ("allset.prune_membership", {"kind": kind}) for label, kind in (
        ("Cluster", "cluster"), ("Lattice", "ffd"), ("Wire", "wire"))},
    "Deform/Point On Curve": "allset.point_on_curve",
    # UV
    "UV/UV Set Editor": _props('DATA'),
    "UV/Assign Checker Shader": "allset.checker_shader",
    "UV/Best Plane": "allset.uv_planar",
    "UV/Contour Stretch": "allset.uv_contour",    # Follow Active Quads + stretch to 0-1 (step 139)
    "UV/Split UVs": "allset.uv_split",        # SplitUV = polySplitTextureUV, like UV Editor Cut/Sew > Split (step 206)
    "UV/Auto Seams": "allset.uv_auto_seams",  # Maya UV > Auto Seams (step 206)
    # Generate (XGen -> hair curves)
    "Generate/Create Description...": "object.curves_empty_hair_add",
    "Generate/Create Interactive Groom Splines": "object.curves_empty_hair_add",
    # Skeleton / Skin / Constrain
    "Skeleton/Insert Joints": "allset.insert_joint_tool",          # step 246: click a joint, drag
    "Skeleton/Connect Joint": "allset.connect_joint",              # step 246: connect / parent mode (option box)
    # step 199 (#106): Maya's three skinCluster.normalizeWeights modes (operators/skin_tools_199.py)
    "Skin/Normalize Weights/Enable Weight Normalization": ("allset.skin_normalize_mode", {"mode": 'INTERACTIVE'}),
    "Skin/Normalize Weights/Disable Weight Normalization": ("allset.skin_normalize_mode", {"mode": 'NONE'}),
    "Skin/Normalize Weights/Enable Weight Post Normalization": ("allset.skin_normalize_mode", {"mode": 'POST'}),
    "Skin/Move Weights to Influences": "allset.move_skin_weights",
    "Skin/Export Weight Maps...": "allset.export_weight_maps",
    "Skin/Import Weights Maps...": "allset.import_weight_maps",
    "Skin/Substitute Geometry": "allset.substitute_geometry",
    "Skin/Bake Deformation to Skin Weights...": "allset.bake_deformation",
    # step 199 (#106, operators/constrain_199.py)
    "Constrain/Normal": "allset.normal_constraint",
    "Constrain/Tangent": "allset.tangent_constraint",
    "Constrain/Remove Target": "allset.remove_constraint_target",
    "Constrain/Set Rest Position": "allset.set_constraint_rest",
    "Constrain/Modify Constrained Axis...": "allset.modify_constraint_axes",
    "Constrain/Rivet": "object.vertex_parent_set",
    "Constrain/Closest Point": _con('SHRINKWRAP'),
    "Constrain/Point On Poly": _con('SHRINKWRAP'),
    # Key / Playback / Visualize
    "Key/Insert Key on Translate": ("anim.keyframe_insert_by_name", {"type": "Location"}),
    "Key/Insert Key on Rotate": ("anim.keyframe_insert_by_name", {"type": "Rotation"}),
    "Key/Insert Key on Scale": ("anim.keyframe_insert_by_name", {"type": "Scaling"}),
    "Playback/Select Next Key": ("screen.keyframe_jump", {"next": True}),
    "Playback/Select Previous Key": ("screen.keyframe_jump", {"next": False}),
    "Playback/Playback Looping/Continuous": ("allset.menu_note", {"item": "Playback/Playback Looping/Continuous"}),
    "Visualize/Time Slider Bookmarks": "marker.add",
    # Audio: sounds are Video Sequencer sound strips
    "Audio/Import Audio...": "allset.import_audio",
    "Audio/Import Audio Clip to Time Editor...": "allset.import_audio",
    "Audio/Mute": ("wm.context_toggle", {"data_path": "scene.use_audio"}),
    "Audio/Adjust Volume": _props('SCENE'),
    "Audio/Delete Sounds": "allset.delete_sounds",
    # FX
    "nParticles/Soft Body": _mod('SOFT_BODY'),
    "nParticles/Soft Body#2": _mod('SOFT_BODY'),
    "nParticles/Make Collide": _mod_selected('COLLISION'),
    # Rendering
    # Light / shadow linking = Blender's light linking operators: the active object is the light, the other
    # selected objects are linked (Include) or unlinked (Exclude)
    "Lighting/Shading/Light Linking Editor": _props('OBJECT'),
    "Lighting/Shading/Make Light Links": ("object.light_linking_receivers_link", {"link_state": 'INCLUDE'}),
    "Lighting/Shading/Break Light Links": ("object.light_linking_receivers_link", {"link_state": 'EXCLUDE'}),
    "Lighting/Shading/Select Objects Illuminated by Light": "object.light_linking_receivers_select",
    "Lighting/Shading/Make Shadow Links": ("object.light_linking_blockers_link", {"link_state": 'INCLUDE'}),
    "Lighting/Shading/Break Shadow Links": ("object.light_linking_blockers_link", {"link_state": 'EXCLUDE'}),
    "Lighting/Shading/Select Objects Shadowed by Light": "object.light_linking_blockers_select",
    "Toon/Assign Outline": ("v3d", "object.grease_pencil_add", {"type": 'LINEART_OBJECT'}),
    "Create/Cameras/Stereo Camera": "allset.stereo_camera",
    # Cache (Alembic / GPU cache = Alembic files; Geometry Cache = Alembic too, with a notice)
    "Cache/Alembic Cache/Open Alembic...": "wm.alembic_import",
    "Cache/Alembic Cache/Reference Alembic...": "wm.alembic_import",
    "Cache/Alembic Cache/Import Alembic...": "wm.alembic_import",
    "Cache/Alembic Cache/Export All to Alembic...": ("wm.alembic_export", {"selected": False}),
    # step 164: the kit's Export Selection dialog (Maya preset + the selection's descendants)
    "Cache/Alembic Cache/Export Selection to Alembic...": ("allset.file_export_selection", {"export_type": 'ABC'}),
    "Cache/Geometry Cache/Create New Cache": ("wm.alembic_export", {"selected": True}),
    "Cache/Geometry Cache/Import Cache...": "wm.alembic_import",
    "Cache/Geometry Cache/Export Cache": ("wm.alembic_export", {"selected": True}),
    "Cache/GPU Cache/Import...": "wm.alembic_import",
    "Cache/GPU Cache/Export All...": ("wm.alembic_export", {"selected": False}),
    "Cache/GPU Cache/Export Selection...": ("allset.file_export_selection", {"export_type": 'ABC'}),
    # Help -> Blender's documentation and community
    "Help/Search": _url(_MANUAL),
    "Help/Maya Help": _url(_MANUAL),
    "Help/Quick Tour": _url(_MANUAL + "getting_started/index.html"),
    "Help/Interactive Tutorials/Basic Skills": _url(_TUTORIALS),
    "Help/Interactive Tutorials/View All Interactive Tutorials...": _url(_TUTORIALS),
    "Help/YouTube Learning Channel": _url("https://www.youtube.com/@BlenderOfficial"),
    "Help/Scripting Reference/MEL Command Reference": _url(_API),
    "Help/Scripting Reference/Python Command Reference": _url(_API),
    "Help/Scripting Reference/Node and Attribute Reference": _url(_API + "bpy.types.html"),
    "Help/Services and Support/Release Notes Updates": _url(_NOTES),
    "Help/Services and Support/Support Center": _url("https://www.blender.org/support/"),
    "Help/Feedback/Report a Problem...": _url("https://projects.blender.org/blender/blender/issues"),
    "Help/Blender Extensions": _url("https://extensions.blender.org/"),
    "Help/About Maya": "wm.splash_about",
})

# Mapped items whose Blender operator needs component (edit) mode run the Maya way from object mode
# (step 101):
# ('ALL', select mode) = Maya acts on every component of the selected meshes; a string = Maya's warning.
OBJECT_MODE = {
    "Toon/Reverse Surfaces": ('ALL', 'FACE'),      # #123: reverses whole selected meshes like Maya's
    "Edit Mesh/Add Divisions": ('ALL', 'FACE'),
    "Edit Mesh/Collapse": ('ALL', 'FACE'),
    "Edit Mesh/Merge": ('ALL', 'VERT'),
    "Edit Mesh/Merge to Center": "polyMergeVert1 (Poly Merge Vert): No vertices were merged. Tolerance too large - "
                                 "no geometry left after merge",
    "Edit Mesh/Average Vertices": ('ALL', 'VERT'),
    "Edit Mesh/Poke": ('ALL', 'FACE'),
    "Edit Mesh/Circularize": ('ALL', 'VERT'),
    "Edit Mesh/Edit Edge Flow": ('ALL', 'EDGE'),
    "Edit Mesh/Bevel": ('ALL', 'EDGE'),
    "Edit Mesh/Chamfer Vertices": ('ALL', 'VERT'),
    "Edit Mesh/Bridge": "Invalid selection : polyBridgeEdge requires equal number of border edges to be selected "
                        "for source and target selection.",
    "Edit Mesh/Delete Edge/Vertex": "No Vertices / Edges have been selected for Delete!",
    "Edit Mesh/Extract": "polyChipOff works only on polygonal faces.",
    "Edit Mesh/Duplicate": "polyChipOff works only on polygonal faces.",
    "Edit Mesh/Detach": "No vertices or edges selected to detach.",
    "Edit Mesh/Wedge": "No faces selected to wedge. Select faces and one or more edges from the selected faces "
                       "to wedge about.",
    "Edit Mesh/Connect": "Can't perform polyConnectComponents1 on selection",
    "Edit Mesh/Symmetrize": "No components selected for Symmetrize.",     # Maya 2022 (step 139)
    "Edit Mesh/Flip Triangle Edge": "Select edges to flip.",
    "Edit Mesh/Spin Edge Backward": "Select edges to spin.",
    "Edit Mesh/Spin Edge Forward": "Select edges to spin.",
    # Step 136 (the Shift+RMB object menu runs these from object mode): PolyExtrude extrudes every face;
    # Mesh > Fill Hole / Quadrangulate act on the whole object, like Maya.
    "Edit Mesh/Extrude": ('ALL', 'FACE'),
    "Mesh/Fill Hole": ('ALL', 'EDGE'),
    "Mesh/Quadrangulate": ('ALL', 'FACE'),
    # Step 139 (U1): Maya's UV projections convert an object selection to all its faces
    # (Maya 2026); Automatic / Contour Stretch / Planar do that in their own operator.
    "UV/Cylindrical": ('ALL', 'FACE'),
    "UV/Spherical": ('ALL', 'FACE'),
}

# Edit / Select / Modify items run in component (mesh edit) mode the way Maya 2022 runs them there (step 129, #39 /
# #17 / #18; with pCube1.f[1] selected after F11):
# ("run", action) = this action instead of the object one; ("object", action) = back to object mode, then the
# action; ("owner", action) = the action on the objects whose components are selected, then back to component mode
# with the same components; ("warn", text) = Maya's warning, nothing done; ("none",) = no effect, like Maya.
_NO_DUPLICATE = "No object(s) to duplicate"
_NO_PARENT = "Cannot parent components or objects in the underworld."
EDIT_MODE = {
    "Select/All": ("run", ("mesh.select_all", {"action": 'SELECT'})),       # every face, still component mode
    "Select/Inverse": ("run", ("mesh.select_all", {"action": 'INVERT'})),
    "Select/Deselect All": ("run", "allset.select_none"),       # SelectNone: select -cl + object mode
    "Select/Hierarchy": ("none",),
    "Select/Similar": ("run", "mesh.select_similar"),           # SelectSimilar on components (step 136)
    "Edit/Delete": ("run", "allset.delete_components"),        # the Delete key (step 24)
    "Edit/Cut": ("run", "allset.delete_components"),           # deletes the components; nothing goes to the clipboard
    "Edit/Group": ("object", _create('EMPTY_GROUP')),          # Group on components = an empty group null1
    "Edit/Duplicate": ("warn", _NO_DUPLICATE),
    "Edit/Duplicate Special": ("warn", _NO_DUPLICATE),
    "Edit/Duplicate with Transform": ("owner", "allset.duplicate_with_transform"),   # pCube2, f[1] kept
    "Edit/Parent": ("warn", _NO_PARENT),
    "Edit/Unparent": ("warn", _NO_PARENT),
    "Modify/Freeze Transformations": ("none",),                # makeIdentity runs, Translate X stays
    "Modify/Reset Transformations": ("none",),
    "Edit/Delete by Type/History": ("none",),                  # delete -ch keeps polyExtrudeFace1 (#18)
}

# Step 109: Curves / Surfaces and FX commands built for the shelf, same in the
# menus. operators/curve_tools.py, operators/fx.py.
MAP.update({
    "Create/NURBS Primitives/Square": _create('NURBS_SQUARE'),
    "Create/NURBS Primitives/Cube": _create('NURBS_CUBE'),
    "Create/NURBS Primitives/Cone": _create('NURBS_CONE'),
    "Create/Curve Tools/Pencil Curve Tool": "allset.pencil_curve",
    "Create/Sweep Mesh": "allset.sweep_mesh",
    "Curves/Add Points Tool": ("v3d", "allset.add_points", {}),
    "Curves/Offset/Offset Curve": "allset.offset_curve",
    "Surfaces/Loft": "allset.loft",                 # step 181: a NURBS loft (was a mesh)
    "Surfaces/Planar": "allset.surface_planar",
    "Surfaces/Extrude": "allset.surface_extrude",   # step 181: a NURBS extrude (was a curve bevel)
    "Surfaces/Bevel Plus": "allset.bevel_plus",
    # Sculpting stamps Blender lacks: the keymap's step-107 substitutes (sculpt Ctrl+8 / Ctrl+9)
    "Mesh Tools/Sculpting Tools/Spray Tool": _sculpt("Draw Sharp"),
    "Mesh Tools/Sculpting Tools/Repeat Tool": _sculpt("Layer"),
    "Fluids/Add/Edit Contents/Emit from Object": "allset.fluid_quick_smoke",
    "Fluids/Make Collide": "allset.fluid_collide",
    "nCloth/Display Input Mesh": ("allset.ncloth_display", {"mesh": 'INPUT'}),
    "nCloth/Display Current Mesh": ("allset.ncloth_display", {"mesh": 'CURRENT'}),
    "nHair/Paint Hair Follicles": "allset.paint_hair_follicles",     # step 258: a mesh selection is valid (#152)
})

# Step 110: modeling / rigging commands with Maya's results;
# operators/poly_maya.py, operators/rig_maya.py, menu_items.nonlinear.
MAP.update({
    "Edit Mesh/Circularize": "allset.circularize",
    "Mesh Tools/Connect": "allset.connect",
    "Mesh Tools/Make Hole": "allset.make_hole",
    # step 159: Joint Labelling (operators/joint_labels.py): the first
    # Label Shoulder / Label Hip items are Maya's limb labels (FBIKLabelArm / Leg)
    "Skeleton/Joint Labelling/Add Joint Labels/Label Left": ("allset.joint_label", {"side": "LEFT"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Right": ("allset.joint_label", {"side": "RIGHT"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Center": ("allset.joint_label", {"side": "CENTER"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label None": ("allset.joint_label", {"type": "NONE"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Shoulder": ("allset.joint_label", {"type": "ARM"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Hip": ("allset.joint_label", {"type": "LEG"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Collar": ("allset.joint_label", {"type": "COLLAR"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Elbow": ("allset.joint_label", {"type": "ELBOW"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Foot": ("allset.joint_label", {"type": "FOOT"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Hand": ("allset.joint_label", {"type": "HAND"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Head": ("allset.joint_label", {"type": "HEAD"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Hip#2": ("allset.joint_label", {"type": "HIP"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Knee": ("allset.joint_label", {"type": "KNEE"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Neck": ("allset.joint_label", {"type": "NECK"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Root": ("allset.joint_label", {"type": "ROOT"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Shoulder#2": ("allset.joint_label", {"type": "SHOULDER"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Spine": ("allset.joint_label", {"type": "SPINE"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Thumb": ("allset.joint_label", {"type": "THUMB"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Index Finger": ("allset.joint_label", {"type": "INDEX_FINGER"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Middle Finger": ("allset.joint_label", {"type": "MIDDLE_FINGER"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Ring Finger": ("allset.joint_label", {"type": "RING_FINGER"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Pinky Finger": ("allset.joint_label", {"type": "PINKY_FINGER"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Extra Finger": ("allset.joint_label", {"type": "EXTRA_FINGER"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Finger": ("allset.joint_label", {"type": "FINGER"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Big Toe": ("allset.joint_label", {"type": "BIG_TOE"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Index Toe": ("allset.joint_label", {"type": "INDEX_TOE"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Middle Toe": ("allset.joint_label", {"type": "MIDDLE_TOE"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Ring Toe": ("allset.joint_label", {"type": "RING_TOE"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Pinky Toe": ("allset.joint_label", {"type": "PINKY_TOE"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Foot Thumb": ("allset.joint_label", {"type": "FOOT_THUMB"}),
    "Skeleton/Joint Labelling/Add Joint Labels/Label Toe": ("allset.joint_label", {"type": "TOE"}),
    "Skeleton/Joint Labelling/Toggle Selected Labels": "allset.joint_label_toggle",
    "Skeleton/Joint Labelling/Show All Labels": ("allset.joint_label_show_all", {"show": True}),
    "Skeleton/Joint Labelling/Hide All Labels": ("allset.joint_label_show_all", {"show": False}),
    "Skeleton/Joint Labelling/Rename Joints From Labels": "allset.rename_joints_from_labels",
    "Skeleton/Joint Labelling/Label Based on Joint Names": "allset.label_from_joint_names",
    "Skeleton/Enable Selected IK Handles": ("allset.ik_handle_enable", {"enable": True}),
    "Skeleton/Disable Selected IK Handles": ("allset.ik_handle_enable", {"enable": False}),
    # step 159: Maya deformerWeights XML (operators/deformer_weights.py)
    "Deform/Export Weights...": "allset.export_deformer_weights",
    "Deform/Import Weights...": "allset.import_deformer_weights",
    "Skin/Reset Default Weights": "allset.reset_skin_weights",     # step 159: closest distance bind weights
    "Skeleton/Reroot Skeleton": "allset.reroot_skeleton",
    "Skeleton/Set Preferred Angle": "allset.set_preferred_angle",
    "Skeleton/Assume Preferred Angle": "allset.assume_preferred_angle",
    "Skeleton/Create IK Spline Handle": "allset.ik_spline_handle",
    "Skin/Hammer Skin Weights": "allset.hammer_weights",
    "Skin/Edit Influences/Add Influence": "allset.add_influence",
    "Skin/Edit Influences/Remove Influence": "allset.remove_influence",
    "Skin/Edit Influences/Remove Unused Influences": "allset.remove_unused_influences",
    "Deform/Cluster": "allset.cluster",
    "Deform/Nonlinear/Twist": ("allset.deformer", {"kind": 'TWIST'}),     # step 144: operators/deformers.py
    "Deform/Soft Modification Tool": "allset.soft_mod",
    # step 205 lane P (operators/pins_205.py): Maya 2020+ matrix constraints, intermediate objects, wrap influences
    "Constrain/UV Pin": "allset.uv_pin",
    "Constrain/Proximity Pin": "allset.proximity_pin",
    "Deform/Display Intermediate Objects": ("allset.intermediate_objects", {"show": True}),
    "Deform/Hide Intermediate Objects": ("allset.intermediate_objects", {"show": False}),
    "Deform/Wrap#2/Add Influence": ("allset.wrap_influence", {"action": 'ADD'}),
    "Deform/Wrap#2/Remove Influence": ("allset.wrap_influence", {"action": 'REMOVE'}),
})

# Maya FX / Rendering items on Blender's own systems (#123, operators/fx_more.py and render_more.py); each has a
# notice saying which Blender feature it uses (ui/notices.py)
_NCLOTH_PAINT = {"Input Attract": 'INPUT_ATTRACT', "Stretch": 'STRETCH', "Compression": 'COMPRESSION',
                 "Bend": 'BEND', "Rest Length Scale": 'REST_LENGTH_SCALE'}
_TOON_FILLS = {"Solid Color": 'SOLID_COLOR', "Light Angle Two Tone": 'LIGHT_ANGLE_TWO_TONE',
               "Shaded Brightness Two Tone": 'SHADED_BRIGHTNESS_TWO_TONE',
               "Shaded Brightness Three Tone": 'SHADED_BRIGHTNESS_THREE_TONE', "Dark Profile": 'DARK_PROFILE',
               "Rim Light": 'RIM_LIGHT', "Circle Highlight": 'CIRCLE_HIGHLIGHT'}
MAP.update({
    "nParticles/Fill Object": "allset.fx_fill_object",
    "nParticles/Instancer": "allset.fx_instancer",
    "Fluids/Add/Edit Contents/Emitter": "allset.fluid_add_emitter",
    "Fluids/Edit Fluid Resolution": "allset.fluid_resolution",
    "nCloth/Rest Shape/Set Rest To Start Shape": ("allset.ncloth_rest", {"mode": 'START'}),
    "nCloth/Rest Shape/Connect Input Mesh to Rest Shape": ("allset.ncloth_rest", {"mode": 'START'}),
    "nCloth/Rest Shape/Connect Selected Mesh to Rest Shape": ("allset.ncloth_rest", {"mode": 'SELECTED'}),
    **{f"nCloth/Paint Vertex Properties/{label}": ("allset.ncloth_paint_vertex", {"attr": key})
       for label, key in _NCLOTH_PAINT.items()},
    # Hook to New Object (Edit Mode): Blender pins cloth vertices with a Pin Group
    "nConstraint/Transform Constraint": "object.hook_add_newob",
    "nCache/Create Particle Disk Cache": "allset.particle_disk_cache",
    "nCache/Edit Oversampling or Cache Settings...": _props('PHYSICS'),
    "Fields/Solvers/Volume Curve": "allset.fx_curve_field",
    "Fields/Solvers/Set Active Key": ("allset.fx_rigid_key", {"passive": False}),
    "Fields/Solvers/Set Passive Key": ("allset.fx_rigid_key", {"passive": True}),
    "Fields/Solvers/Break Rigid Body Connections": "allset.fx_break_rigid",
    "Fields/Solvers/Rigid Body Solver Attributes": _props('SCENE'),
    "Fields/Solvers/Create Rigid Body Solver": "allset.fx_rigid_world",
    # a Generic rigid body constraint with no limits (Disable Collisions on) between the selection and the active
    "Fields/Solvers/Set Rigid Body Interpenetration": ("rigidbody.connect", {"con_type": 'GENERIC',
                                                                             "connection_pattern": 'SELECTED_TO_ACTIVE'}),
    "Fields/Solvers/Use Selected as Source": "object.forcefield_toggle",
    "Effects/Flow/Create Curve Flow": "allset.fx_curve_field",
    "Lighting/Shading/Transfer Maps...": "allset.transfer_maps",
    **{f"Toon/Assign Fill Shader/{label}": ("allset.toon_fill", {"kind": key}) for label, key in _TOON_FILLS.items()},
    **{f"Toon/Set Camera Background Color/{cam}": ("allset.camera_background", {"camera": cam})
       for cam in ("persp", "front", "side", "top")},
})

# Blender's own menu kept at the end of the Maya menu with the same role.
BLENDER_MENU = {
    "File": ("TOPBAR_MT_file", "Blender File"),
    "Edit": ("TOPBAR_MT_edit", "Blender Edit"),
    "Windows": ("TOPBAR_MT_window", "Blender Window"),
    "Render": ("TOPBAR_MT_render", "Blender Render"),
    "Help": ("TOPBAR_MT_help", "Blender Help"),
}


# Graph Editor / Dope Sheet / UV Editor / UV Toolkit menu bars (step 104): their own module, same forms.
from .editor_menu_map import MAP as _EDITOR_MAP  # noqa: E402
from .editor_menu_map import GREY_ON_POLL  # noqa: E402,F401  (menu_sets.draw_item, step 203)

MAP.update(_EDITOR_MAP)

# Step 166: the same Maya command greyed in one menu while it works in another
# (tools/menu_consistency.py finds them: label + runTimeCommand / annotation) gets the working item's action.
# UV Editor Tools > Unfold / Cut / Sew / Pin are Maya's brush tools; the kit runs the command on the selection
# (Blender's UV editor has no unfold / cut / sew brush).
TWINS = {
    **{f"Key/{label}": f"Control/{label}" for label in (
        "Create Character Set", "Create Subcharacter Set", "Attribute Editor", "Add to Character Set",
        "Remove from Character Set", "Merge Character Sets", "Select Character Set Node", "Select Character Set Members",
        "Set Current Character Set")},
    "Hypershade/Edit/Select All by Type/Lights": "Select/All by Type/Lights",
    "UV/3D Grab UV Tool": "UV Editor/Tools/Grab",      # step 219: Maya 2026 UV menu item = the UV Editor Grab tool
    **{f"UV Editor/Select/Convert Selection/{label}": f"Select/Convert Selection/{label}"
       for label in ("To Contained Edges", "To Contained Faces", "To Edge Loop", "To Edge Ring")},
    "UV Editor/Tools/Unfold": "UV Editor/Modify/Unfold",
    "UV Editor/Tools/Cut": "UV Editor/Cut/Sew/Cut",
    "UV Editor/Tools/Sew": "UV Editor/Cut/Sew/Sew",
    "UV Editor/Tools/Pin": "UV Editor/Edit/Pin Selection",
    # step 189: runTimeCommand aliases (tools/menu_consistency.py module doc) — the main UV > Delete UVs runs
    # DeleteUVsWithoutHotkey = the marking menu's DeleteUVs (polyMapDel on the selected faces, Maya UV marking menu);
    # nHair > Modify Curves runs the Curves menu's SmoothHairCurves / StraightenCurves (Maya 2026 nHair menu)
    "nHair/Modify Curves/Smooth": "Curves/Smooth",
    "nHair/Modify Curves/Straighten": "Curves/Straighten",
    "nHair/Modify Curves/Lock Length": "Curves/Lock Length",          # step 207
    "nHair/Modify Curves/Unlock Length": "Curves/Unlock Length",          # step 207
    "nHair/Modify Curves/Bend": "Curves/Bend",          # step 207
    "nHair/Modify Curves/Curl": "Curves/Curl",          # step 207
    "nHair/Modify Curves/Scale Curvature": "Curves/Scale Curvature",          # step 207
    # #123: the same Blender action from the FX / Rendering / Hypershade menus
    "Effects/Collide with Effect": "Fluids/Make Collide",
    "Toon/Reverse Surfaces": "Mesh Display/Reverse",
    "Stereo/Create/Stereo Camera": "Create/Cameras/Stereo Camera",
    "Hypershade/Create/Image Plane": "Create/Free Image Plane",
    "Hypershade/Window/Connection Editor...": "Windows/General Editors/Connection Editor",
    "Hypershade/Window/Connect Selected...": "Windows/General Editors/Connection Editor",
    "Hypershade/Edit/Duplicate/With Connections to Network": "Hypershade/Edit/Duplicate/Shading Network",
    **{f"Lighting/Shading/Light Linking Editor/{mode}": f"Windows/Relationship Editors/Light Linking/{mode}"
       for mode in ("Light-Centric", "Object-Centric")},
}
MAP.setdefault("UV/Delete UVs", "allset.uv_delete")   # step 189 (audit 13 BS1): main menu twin of the UV marking menu
for _twin, _source in TWINS.items():
    if _twin not in MAP and _source in MAP:
        MAP[_twin] = MAP[_source]


def spec(path):
    """Normalised (kind, target, props) for a label path, or None if unmapped."""
    return normalize(MAP.get(path))


def normalize(value):
    """(kind, target, props) for a mapping value (also used by marking menus,
    which add ``("pie", MENU_ID)``); None stays None (greyed out)."""
    if value is None:
        return None
    if isinstance(value, str):
        return ("op", value, {})
    if value[0] == "v3d":
        return ("v3d", value[1], dict(value[2]))
    if value[0] == "tool":
        return ("tool", value[1], {"edit": value[2]})
    if value[0] in ("menu", "pie"):
        return (value[0], value[1], {})
    if value[0] == "prop":   # a Maya check / radio item = a Blender property (step 104)
        return ("prop", value[1], dict(value[2]))
    if value[0] == "item":   # a marking-menu entry that runs a main-menu item (step 136; marking/modal.run_action)
        return ("op", "allset.menu_item", {"item": value[1]})
    return ("op", value[0], dict(value[1]))
