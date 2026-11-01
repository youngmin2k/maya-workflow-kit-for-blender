# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya shelf button -> Blender action and Blender built-in icon.

Keys: the button's runTimeCommand (``shelf_data``), or "<shelf file>/<label>" for
buttons whose Maya command is a script rather than a runTimeCommand. Values: (action, icon) with the
action in ``ui/menu_map.py`` form (run by ``marking.modal.run_action``). Icons are
Blender's own (no Maya artwork); the shelf row draws kit-made
pictograms (``shelf_icons``).

Every factory button keeps its slot. ``MENU`` names the Maya menu
item that runs the same runTimeCommand: the button takes that item's
action (``menu_map.MAP``) or, when the item is greyed, its notice (``ui/notices.py``). Buttons that are in no
Maya menu carry their own notice in ``NOTICES``. Unmapped buttons are drawn greyed with the notice as tooltip.
"""

from .menu_map import MAP as _MENU_MAP, _con, _create, _dock, _mod


def _key(kind):
    # Translate / Rotate / Scale keys go through the kit's Set Key (the default tangents apply, like Maya)
    channels = {"Location": "TRANSLATE", "Rotation": "ROTATE", "Scaling": "SCALE"}.get(kind)
    if channels:
        return ("allset.set_key", {"channels": channels})
    return ("anim.keyframe_insert_by_name", {"type": kind})


def _shader(kind):
    return ("allset.shelf_material", {"kind": kind})


_CONSTRAINTS = {
    "ParentConstraint": (_con('CHILD_OF'), 'CON_CHILDOF'),
    "PointConstraint": (_con('COPY_LOCATION'), 'CON_LOCLIKE'),
    "OrientConstraint": (_con('COPY_ROTATION'), 'CON_ROTLIKE'),
    "ScaleConstraint": (_con('COPY_SCALE'), 'CON_SIZELIKE'),
    "AimConstraint": (_con('TRACK_TO'), 'CON_TRACKTO'),
}

BY_COMMAND = {
    # --- Curves, Surfaces ---
    "CreateNURBSCircle": (_create('NURBS_CIRCLE'), 'CURVE_NCIRCLE'),
    "EPCurveTool": ("allset.ep_curve_tool", 'CURVE_NCURVE'),
    "CreateBezierCurveTool": (_create('BEZIER_CURVE'), 'CURVE_BEZCURVE'),
    "InsertKnot": ("curve.subdivide", 'CURVE_PATH'),
    "CreateNURBSSphere": (_create('NURBS_SPHERE'), 'SURFACE_NSPHERE'),
    "CreateNURBSCylinder": (_create('NURBS_CYLINDER'), 'SURFACE_NCYLINDER'),
    "CreateNURBSPlane": (_create('NURBS_PLANE'), 'SURFACE_NSURFACE'),
    "CreateNURBSTorus": (_create('NURBS_TORUS'), 'SURFACE_NTORUS'),
    "OpenCloseSurfaces": ("curve.cyclic_toggle", 'MOD_CURVE'),
    # --- Poly Modeling ---
    "CreatePolygonSphere": (_create('SPHERE'), 'MESH_UVSPHERE'),
    "CreatePolygonCube": (_create('CUBE'), 'MESH_CUBE'),
    "CreatePolygonCylinder": (_create('CYLINDER'), 'MESH_CYLINDER'),
    "CreatePolygonCone": (_create('CONE'), 'MESH_CONE'),
    "CreatePolygonTorus": (_create('TORUS'), 'MESH_TORUS'),
    "CreatePolygonPlane": (_create('PLANE'), 'MESH_GRID'),
    "CreatePolygonDisc": (_create('DISC'), 'MESH_CIRCLE'),
    "CreatePolygonPlatonic": (_create('PLATONIC'), 'MESH_ICOSPHERE'),
    "CreatePolygonType": (_create('TEXT'), 'OUTLINER_OB_FONT'),
    "CenterPivot": ("allset.center_pivot", 'PIVOT_BOUNDBOX'),
    "DeleteHistory": ("allset.delete_history", 'MODIFIER_OFF'),
    "FreezeTransformations": ("allset.freeze_transform", 'FREEZE'),
    "CombinePolygons": ("allset.combine", 'AUTOMERGE_ON'),
    "ExtractFace": (("mesh.separate", {"type": 'SELECTED'}), 'MOD_EXPLODE'),
    "MirrorPolygonGeometry": ("allset.mirror", 'MOD_MIRROR'),
    "SmoothPolygon": (("item", "Mesh/Smooth"), 'MOD_SUBSURF'),     # the menu's polySmoothFace (#204)
    "ReducePolygon": (_mod('DECIMATE'), 'MOD_DECIM'),
    "PolyRemesh": (_mod('REMESH'), 'MOD_REMESH'),
    "PolyExtrude": (("v3d", "allset.extrude", {}), 'FACESEL'),     # polyExtrudeFace
    "BridgeOrFill": ("mesh.bridge_edge_loops", 'MOD_LATTICE'),
    "BevelPolygon": (("item", "Edit Mesh/Bevel"), 'MOD_BEVEL'),
    "PolyMerge": (("item", "Edit Mesh/Merge"), 'AUTOMERGE_OFF'),
    "MergeToCenter": (("mesh.merge", {"type": 'CENTER'}), 'PIVOT_MEDIAN'),
    "FlipTriangleEdge": ("mesh.edge_rotate", 'MOD_TRIANGULATE'),
    "DuplicateFace": (("v3d", "mesh.duplicate_move", {}), 'DUPLICATE'),
    "PolygonCollapse": ("mesh.edge_collapse", 'FULLSCREEN_EXIT'),
    "MultiCutTool": (("tool", "allset.multi_cut_tool", True), 'SCULPTMODE_HLT'),
    "MergeVertexTool": (("tool", "allset.target_weld_tool", True), 'AUTOMERGE_OFF'),   # Target Weld
    "QuadDrawTool": ("allset.quad_draw_start", 'MESH_DATA'),        # #30
    "TextureViewWindow": (("allset.hb_pane", {"ui_type": 'UV'}), 'UV'),
    "SetCutSewUVTool": ("allset.cut_sew_tool_set", 'UV_EDGESEL'),
    # --- Sculpting ---
    "SetMeshSculptTool": (("object.mode_set", {"mode": 'SCULPT'}), 'SCULPTMODE_HLT'),
    # --- Rigging ---
    "CreateLocator": (_create('LOCATOR'), 'EMPTY_AXIS'),
    "JointTool": ("allset.joint_tool", 'OUTLINER_OB_ARMATURE'),
    "IKHandleTool": ("allset.ik_handle", 'CON_KINEMATIC'),
    "SmoothBindSkin": ("allset.bind_skin", 'MOD_ARMATURE'),
    "ArtPaintSkinWeightsTool": ("allset.paint_skin_weights", 'WPAINT_HLT'),
    "CreateBlendShape": ("allset.blend_shape", 'SHAPEKEY_DATA'),
    "SetDrivenKey": ("allset.sdk_window", 'DRIVER'),
    "QuickRigEditor": ("allset.quick_rig", 'OUTLINER_OB_ARMATURE'),
    "CreateLattice": (("object.add", {"type": 'LATTICE'}), 'OUTLINER_OB_LATTICE'),
    **_CONSTRAINTS,
    "SetKey": ("anim.keyframe_insert", 'KEY_HLT'),
    "PoleVectorConstraint": ("allset.pole_vector", 'CON_KINEMATIC'),     # Rigging and Animation shelves
    # --- Animation ---
    "PlayblastWindow": (("v3d", "allset.playblast", {}), 'RENDER_ANIMATION'),
    "CreateMotionTrail": ("object.paths_calculate", 'ANIM_DATA'),
    "BakeSimulation": ("allset.bake_simulation", 'ACTION'),
    "SetKeyAnimated": (_key("Available"), 'KEYINGSET'),
    "SetKeyTranslate": (_key("Location"), 'CON_LOCLIKE'),
    "SetKeyRotate": (_key("Rotation"), 'CON_ROTLIKE'),
    "SetKeyScale": (_key("Scaling"), 'CON_SIZELIKE'),
    # --- Rendering ---
    "CreateDirectionalLight": (_create('DIRECTIONAL_LIGHT'), 'LIGHT_SUN'),
    "CreatePointLight": (_create('POINT_LIGHT'), 'LIGHT_POINT'),
    "CreateSpotLight": (_create('SPOT_LIGHT'), 'LIGHT_SPOT'),
    "CreateAreaLight": (_create('AREA_LIGHT'), 'LIGHT_AREA'),
    "CreateCameraOnly": (_create('CAMERA'), 'OUTLINER_OB_CAMERA'),
    "BatchRender": (("allset.render", {"animation": True}), 'RENDER_ANIMATION'),     # Render > Batch Render
    "RenderSequence": (("allset.render", {"animation": True}), 'RENDER_RESULT'),
    "Art3dPaintTool": ("paint.texture_paint_toggle", 'TPAINT_HLT'),
    "ShowShadingGroupAttributeEditor": (_dock('ATTRIBUTE_EDITOR'), 'MATERIAL'),   # Edit Material Attributes
    # --- FX ---
    # Blender's own simulation operators (Emitter and the fluid container follow their menu items, MENU)
    "NEmitFromObject": (("object.modifier_add", {"type": 'PARTICLE_SYSTEM', "use_selected_objects": True}),
                        'PARTICLE_DATA'),
    "makeCollideNCloth": (("object.modifier_add", {"type": 'COLLISION', "use_selected_objects": True}), 'MOD_PHYSICS'),
    "CreateHairOptions": ("object.curves_empty_hair_add", 'CURVES_DATA'),
    "InteractivePlayback": ("screen.animation_play", 'PLAY'),
    # --- FX Caching (Blender point caches) ---
    "CreateFluidCache": (("allset.ncache", {"action": 'CREATE', "kind": 'FLUID'}), 'FILE_CACHE'),
    "fluidDeleteCache": (("allset.ncache", {"action": 'DELETE', "kind": 'FLUID'}), 'TRASH'),
    "deleteNclothCache": (("allset.ncache", {"action": 'DELETE', "kind": 'NOBJECT'}), 'TRASH'),
}

BY_LABEL = {
    "UVEditing/Planar Mapping": (("v3d", "uv.project_from_view", {}), 'UV_FACESEL'),
    "UVEditing/Cylindrical Mapping": (("v3d", "uv.cylinder_project", {}), 'MESH_CYLINDER'),
    "UVEditing/Spherical Mapping": (("v3d", "uv.sphere_project", {}), 'MESH_UVSPHERE'),
    "UVEditing/Automatic Mapping": (("item", "UV/Automatic"), 'UV_DATA'),
    "Rendering/Standard Surface Material": (_shader('STANDARD_SURFACE'), 'MATERIAL'),
    "Rendering/Lambert Material": (_shader('LAMBERT'), 'SHADING_SOLID'),
    "Rendering/Blinn Material": (_shader('BLINN'), 'SHADING_RENDERED'),
    "Rendering/Phong Material": (_shader('PHONG'), 'SHADING_TEXTURE'),
    "Rendering/Surface Material": (_shader('SURFACE'), 'LIGHT'),
    # Maya shader kinds (operators/material.MATERIALS)
    "Rendering/Anisotropic Material": (_shader('ANISOTROPIC'), 'MATERIAL'),
    "Rendering/Phong E Material": (_shader('PHONG_E'), 'MATERIAL'),
    "Rendering/Layered Material": (_shader('LAYERED'), 'MATERIAL'),
    "Rendering/Ramp Material": (_shader('RAMP'), 'MATERIAL'),
    "Rendering/Use Background": (_shader('USE_BACKGROUND'), 'MATERIAL'),
    "FX/Create nCloth": (("object.modifier_add", {"type": 'CLOTH', "use_selected_objects": True}), 'MOD_CLOTH'),
    "FX/Remove nCloth": ("allset.fx_remove_ncloth", 'X'),
    "FXCaching/Create New Cache": (("allset.ncache", {"action": 'CREATE', "kind": 'NOBJECT'}), 'FILE_CACHE'),
}

# Shelf button -> the Maya menu item with the same runTimeCommand.
# Mapped items lend their action, greyed ones their notice.
_SCULPT = ("Smooth", "Relax", "Grab", "Pinch", "Flatten", "Foamy", "Spray", "Repeat", "Imprint", "Wax", "Scrape",
           "Fill", "Knife", "Smear", "Bulge", "Amplify", "Freeze", "Smooth Target", "Clone Target", "Mask Target",
           "Erase Target")
_HAIR = {"Current Position": "Display/Current Position", "Start Position": "Display/Start Position",
         "Rest Position": "Display/Rest Position", "Current and Start": "Display/Current and Start",
         "Current and Rest": "Display/Current and Rest", "From Current": "Set Start Position/From Current",
         "Scale Hair Tool": "Scale Hair Tool", "Make Selected Curves Dynamic": "Make Selected Curves Dynamic",
         "Paint Hair Tool Options": "Paint Hair Follicles",
         **{f"To {t}": f"Convert Selection/To {t}" for t in (
             "Hair Systems", "Follicles", "Start Curves", "Rest Curves", "Start Curve End CVs",
             "Rest Curve End CVs")}}
MENU = {
    # Curves, Surfaces (one Curves / Surfaces shelf in Maya 2022, two shelves in Maya 2026)
    "Curves/NURBS Square": "Create/NURBS Primitives/Square",
    "Surfaces/NURBS Cube": "Create/NURBS Primitives/Cube",
    "Surfaces/NURBS Cone": "Create/NURBS Primitives/Cone",
    "Curves/Pencil Curve Tool": "Create/Curve Tools/Pencil Curve Tool",
    "Curves/Three Point Circular Arc": "Create/Curve Tools/Three Point Circular Arc",
    "Curves/Attach Curves": "Curves/Attach",
    "Curves/Detach Curves": "Curves/Detach",
    "Curves/Extend Curve": "Curves/Extend/Extend Curve",
    "Curves/Offset Curve": "Curves/Offset/Offset Curve",
    "Curves/Rebuild Curve": "Curves/Rebuild",
    "Curves/Add Points Tool": "Curves/Add Points Tool",
    "Surfaces/Revolve": "Surfaces/Revolve",          # a NURBS revolve (was the Screw modifier)
    "Surfaces/Loft": "Surfaces/Loft",
    "Surfaces/Planar": "Surfaces/Planar",
    "Surfaces/Extrude": "Surfaces/Extrude",
    "Surfaces/Birail 1 Tool": "Surfaces/Birail/Birail 1 Tool",
    "Surfaces/Bevel Plus": "Surfaces/Bevel Plus",
    "Surfaces/Project Curve on Surface": "Surfaces/Project Curve on Surface",
    "Surfaces/Intersect Surfaces": "Surfaces/Intersect",
    "Surfaces/Trim Tool": "Surfaces/Trim Tool",
    "Surfaces/Untrim Surfaces": "Surfaces/Untrim",
    "Surfaces/Attach Surfaces": "Surfaces/Attach",
    "Surfaces/Detach Surfaces": "Surfaces/Detach",
    "Surfaces/Insert Isoparms": "Surfaces/Insert Isoparms",
    "Surfaces/Extend Surfaces": "Surfaces/Extend",
    "Surfaces/Rebuild Surfaces": "Surfaces/Rebuild",
    "Surfaces/Sculpt Geometry Tool": "Surfaces/Sculpt Geometry Tool",
    "Surfaces/Surface Editing Tool": "Surfaces/Surface Editing/Surface Editing Tool",
    # Poly Modeling
    "Polygons/Super Ellipse": "Create/Polygon Primitives/Super Ellipse",
    "Polygons/Sweep Mesh": "Create/Sweep Mesh",
    "Polygons/SVG": "Create/SVG",
    "Polygons/Content Browser": "Windows/Content Browser",
    "Polygons/Retopologize": "Mesh/Retopologize",
    "Polygons/Circularize": "Edit Mesh/Circularize",
    "Polygons/Difference (A - B)": "Mesh/Booleans/Difference (A - B)",     # Maya 2026 shelf
    "Polygons/Smart Extrude": "Edit Mesh/Smart Extrude",                   # Maya 2026 shelf
    # UV Editing (Maya 2026: the UV buttons of the 2022 Poly Modeling shelf plus four more)
    "UVEditing/Contour Stretch": "UV/Contour Stretch",
    "UVEditing/3D Grab UV Tool": "UV/3D Grab UV Tool",
    "UVEditing/Auto Seams": "UV/Auto Seams",
    "UVEditing/Cut UV Edges": "UV/Cut UV Edges",
    "UVEditing/Delete UVs": "UV/Delete UVs",
    "UVEditing/UV Set Editor": "UV/UV Set Editor",
    # Sculpting (Mesh Tools > Sculpting Tools = the essentials brushes)
    **{f"Sculpting/{t} Tool": f"Mesh Tools/Sculpting Tools/{t} Tool" for t in _SCULPT},
    "Sculpting/Base Meshes": "Windows/Content Browser",       # Maya opens the Content Browser on its meshes
    "Sculpting/Shape Editor": "Windows/Animation Editors/Shape Editor",
    "Sculpting/Pose Editor": "Windows/Animation Editors/Pose Editor",
    # Rigging / Animation
    "Rigging/Human IK": "Windows/Animation Editors/HumanIK",
    "Rigging/Create Cluster": "Deform/Cluster",
    "Animation/Motion Trail Editor": "Visualize/Motion Trail Editor",     # Maya 2026 shelf
    "Animation/Ghost Selected": "Visualize/Ghost Selected",
    "Animation/Unghost Selected": "Visualize/Unghost Selected",
    "Animation/Open Ghosting Editor": "Visualize/Ghosting Editor",
    # Rendering
    "Rendering/Ambient Light": "Create/Lights/Ambient Light",
    "Rendering/Volume Light": "Create/Lights/Volume Light",
    "Rendering/Shading Map": "Hypershade/Create/Materials/Shading Map",
    "Rendering/Cancel Batch Render": "Render/Cancel Batch Render",
    "Rendering/Show Batch Render": "Render/Show Batch Render",
    # FX
    "FX/Emitter": "nParticles/Create Emitter",
    "FX/3D Fluid Container with Emitter": "Fluids/3D Container",
    "FX/2D Fluid Container with Emitter": "Fluids/2D Container",
    "FX/Emit Fluid from Object": "Fluids/Add/Edit Contents/Emit from Object",
    "FX/Make Collide": "Fluids/Make Collide",
    **{f"FX/{label}": f"nHair/{path}" for label, path in _HAIR.items()},
    "FX/Display Input Mesh": "nCloth/Display Input Mesh",
    "FX/Display Current Mesh": "nCloth/Display Current Mesh",
    # FX Caching
    "FXCaching/Set Initial State": "Fields/Solvers/Initial State/Set Initial State",
    "FXCaching/Clear Initial State": "Fields/Solvers/Initial State/Clear Initial State",
    "FXCaching/Enable All Caches On Selected": "nCache/Enable All Caches on Selected",
    "FXCaching/Disable All Caches On Selected": "nCache/Disable All Caches on Selected",
    "FXCaching/Merge Caches": "nCache/Merge Caches",
    "FXCaching/Replace Cache Frame": "nCache/Replace Cache Frame",
}

# Buttons with no Maya menu item: (Blender substitute, one line), like ui/notices.NOTICES.
NOTICES = {
    "Curves/Curve Editing Tool": (
        "Curve edit mode", "Blender has no curve editing manipulator: edit the curve's points in Edit Mode (Tab)."),
    "Sculpting/Convert To Frozen": (
        "Sculpt mode Mask", "Blender masks are painted in Sculpt mode (Mask brush, Mask menu); there is no "
        "conversion from a component selection."),
    "Rendering/Render Diagnostics": (
        "Info editor", "Blender reports render problems in the Info editor and the status bar; there is no "
        "diagnostics window."),
    # Maya 2026 shelf; the kit's Maya materials have no openPBRSurface kind
    "Rendering/OpenPBR Surface Material": (
        "Standard Surface Material", "Maya Workflow Kit has no OpenPBR Surface material: use the Standard Surface "
        "Material button (a Principled BSDF material)."),
}


def menu_path(shelf, label):
    """The Maya menu item behind a shelf button (``MENU``), or None."""
    return MENU.get(f"{shelf}/{label}")


def lookup(shelf, label, command):
    """(action, icon) for a factory button, or None (greyed)."""
    if command and command in BY_COMMAND:
        return BY_COMMAND[command]
    hit = BY_LABEL.get(f"{shelf}/{label}")
    if hit is not None:
        return hit
    path = menu_path(shelf, label)
    action = _MENU_MAP.get(path) if path else None
    return (action, 'DOT') if action is not None else None
