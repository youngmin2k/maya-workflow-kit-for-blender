# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Graph Editor / Dope Sheet / UV Editor / UV Toolkit menu items -> Blender actions.

Keys are ``editor_menu_data`` paths ("Graph Editor/Keys/Insert Key Tool"); values use ``menu_map``'s forms plus
``("prop", "<context path>")`` = a Maya check item drawn as Blender's own check box (``{"value": v}`` = one choice
of a radio collection). ``menu_map`` merges ``MAP`` into its own, so the menu rules (every leaf mapped or greyed
with a notice) cover these menus too. Menu structure: Maya 2026's editor menus
; Blender counterparts checked in 4.5.
"""

import math

_MANUAL = "https://docs.blender.org/manual/en/4.5/"
_API = "https://docs.blender.org/api/4.5/"
_NOTES = "https://developer.blender.org/docs/release_notes/4.5/"
_PKG = __package__.rpartition(".")[0]


def _url(url):
    return ("wm.url_open", {"url": url})


def _prop(path, value=None):
    return ("prop", path, {} if value is None else {"value": value})


def _tangent(kind, side="BOTH"):
    return ("allset.set_tangent", {"kind": kind, "side": side})


def _infinity(side, mode):
    return ("allset.curve_infinity", {"side": side, "mode": mode})


def _key(action):
    return ("allset.key_edit", {"action": action})


def _uv_tool(idname):
    return ("wm.tool_set_by_id", {"name": idname, "space_type": 'IMAGE_EDITOR'})


# Maya tangent labels -> set_tangent kinds (operators/time_keys.TANGENTS). Maya's Auto variants
# (Auto Span / Ease / Mix / Custom) are one Blender auto handle (Auto Clamped): notices in ui/notices.py.
# Maya 2026 labels the first one "Auto Span" (Maya 2022: "Auto Span (Legacy)").
TANGENT_KINDS = {"Spline": "SPLINE", "Linear": "LINEAR", "Clamped": "CLAMPED", "Stepped": "STEPPED",
                 "Stepped Next": "STEPPED_NEXT", "Flat": "FLAT", "Fixed": "FIXED", "Plateau": "PLATEAU"}
AUTO_KINDS = ("Auto Span", "Auto Ease", "Auto Mix", "Auto Custom")

# Default In / Out Tangent: kit add-on prefs the kit's own keys use (operators/graph_key_menu.after_insert);
# Blender's preference is never written (store review, #40 / #43). Maya's Auto variants are one Auto.
_PREFS_ANIMATION = ("screen.userpref_show", {"section": 'ANIMATION'})
DEFAULT_TANGENT_LABELS = {**{label: 'AUTO' for label in AUTO_KINDS}, "Spline": 'SPLINE', "Clamped": 'CLAMPED',
                          "Plateau": 'PLATEAU', "Linear": 'LINEAR', "Flat": 'FLAT', "Stepped": 'STEPPED'}


def _tangents_menu(ed):
    m = {f"{ed}/Tangents/Auto/{label}": _tangent("AUTO") for label in AUTO_KINDS}
    m.update({f"{ed}/Tangents/{label}": _tangent(kind) for label, kind in TANGENT_KINDS.items()})
    for side, sub in (("IN", "In Tangent"), ("OUT", "Out Tangent")):
        m.update({f"{ed}/Tangents/{sub}/Auto/{label}": _tangent("AUTO", side) for label in AUTO_KINDS})
        m.update({f"{ed}/Tangents/{sub}/{label}": _tangent(kind, side) for label, kind in TANGENT_KINDS.items()})
    for sub, pref in (("Default In Tangent", "default_in_tangent"), ("Default Out Tangent", "default_out_tangent")):
        m.update({f"{ed}/Tangents/{sub}/{label}": _prop(f"addon_prefs.{pref}", kind)
                  for label, kind in DEFAULT_TANGENT_LABELS.items()
                  if not (label == "Stepped" and sub == "Default In Tangent")})   # Maya has no stepped in-tangent
    m[f"{ed}/Tangents/Break Tangents"] = _tangent("BREAK")
    m[f"{ed}/Tangents/Unify Tangents"] = _tangent("UNIFY")
    return m


def _channel_commands(ed, menu, graph):
    """Bake / Mute / Lock: the Graph Editor's Curves menu, the Dope Sheet's Channels menu (Maya 2026)."""
    return {
        f"{ed}/{menu}/Bake Channel": "graph.bake_keys" if graph else "action.bake_keys",
        f"{ed}/{menu}/Mute Channel": ("anim.channels_setting_enable", {"type": 'MUTE'}),
        f"{ed}/{menu}/Unmute Channel": ("anim.channels_setting_disable", {"type": 'MUTE'}),
        f"{ed}/{menu}/Lock Channel": ("anim.channels_setting_enable", {"type": 'PROTECT'}),
        f"{ed}/{menu}/Unlock Channel": ("anim.channels_setting_disable", {"type": 'PROTECT'}),
    }


def _curves_menu(ed, graph):
    m = _channel_commands(ed, "Curves", graph)
    for side, sub in (("PRE", "Pre Infinity"), ("POST", "Post Infinity")):
        for label, mode in (("Cycle", "CYCLE"), ("Cycle with Offset", "CYCLE_OFFSET"), ("Oscillate", "OSCILLATE"),
                            ("Linear", "LINEAR"), ("Constant", "CONSTANT")):
            m[f"{ed}/Curves/{sub}/{label}"] = _infinity(side, mode)
    m.update({
        f"{ed}/Curves/Simplify Curve": "graph.clean" if graph else "action.clean",
        f"{ed}/Curves/Key Reducer Filter": "graph.decimate" if graph else "action.clean",
    })
    if graph:
        m.update({
            f"{ed}/Curves/Isolate Curve": ("graph.hide", {"unselected": True}),
            f"{ed}/Curves/Smooth Filter (Butterworth)": "graph.butterworth_smooth",
            f"{ed}/Curves/Smooth Filter (Gaussian)": "graph.gaussian_smooth",
            f"{ed}/Curves/Euler Filter": "graph.euler_filter",
            f"{ed}/Curves/Resample Curve": "graph.bake_keys",
        })
    else:
        # Maya's Dope Sheet runs the Graph Editor's curve commands (the same commands)
        m.update({f"{ed}/Curves/{label}": ("allset.dope_graph_op", {"command": cmd}) for label, cmd in (
            ("Isolate Curve", 'ISOLATE'), ("Smooth Filter (Butterworth)", 'BUTTERWORTH'),
            ("Smooth Filter (Gaussian)", 'GAUSSIAN'), ("Euler Filter", 'EULER'), ("Resample Curve", 'RESAMPLE'))})
    return m


def _edit_menu(ed, graph):
    move = "transform.translate" if graph else ("transform.transform", {"mode": 'TIME_TRANSLATE'})
    scale = "transform.resize" if graph else ("transform.transform", {"mode": 'TIME_SCALE'})
    m = {
        f"{ed}/Edit/Undo": "ed.undo",
        f"{ed}/Edit/Redo": "ed.redo",
        f"{ed}/Edit/Cut": _key("CUT"),
        f"{ed}/Edit/Copy": _key("COPY"),
        f"{ed}/Edit/Paste": _key("PASTE"),
        f"{ed}/Edit/Delete": _key("DELETE"),
        f"{ed}/Edit/Scale": scale,
        f"{ed}/Edit/Transformation Tools/Move Keys Tool":
            ("prop", "window_manager.allset_graph_key_tool", {"value": 'MOVE'}) if graph else move,
        f"{ed}/Edit/Transformation Tools/Scale Keys Tool":
            ("prop", "window_manager.allset_graph_key_tool", {"value": 'SCALE'}) if graph else scale,
        f"{ed}/Edit/Snap": ("graph.snap" if graph else "action.snap", {"type": 'NEAREST_FRAME'}),
    }
    if graph:
        m.update({
            f"{ed}/Edit/Change Curve Color": ("allset.curve_color", {"action": 'CHANGE'}),
            f"{ed}/Edit/Remove Curve Color": ("allset.curve_color", {"action": 'REMOVE'}),
            f"{ed}/Edit/Preferences": ("screen.userpref_show", {"section": 'ANIMATION'}),
        })
    else:
        # Maya 2026's Dope Sheet tool list; Insert Keys = the Dope Sheet toolbar's Insert Keys button
        m[f"{ed}/Edit/Transformation Tools/Insert Keys"] = "action.keyframe_insert"
    return m


def _keys_menu(ed, graph):
    m = {
        f"{ed}/Keys/Convert to Key": _key("TO_KEY") if graph else ("action.keyframe_type", {"type": 'KEYFRAME'}),
        f"{ed}/Keys/Convert to Breakdown": _key("TO_BREAKDOWN") if graph else
        ("action.keyframe_type", {"type": 'BREAKDOWN'}),
        # the editor's curves after the current time (Maya Add / Remove Inbetween), per-key mute =
        # graph_key_menu
        f"{ed}/Keys/Add Inbetween": ("allset.graph_inbetween", {"delta": "ADD"}),
        f"{ed}/Keys/Remove Inbetween": ("allset.graph_inbetween", {"delta": "REMOVE"}),
        f"{ed}/Keys/Mute Key": ("allset.mute_key", {"mute": True}),
        f"{ed}/Keys/Unmute Key": ("allset.mute_key", {"mute": False}),
    }
    if graph:
        m[f"{ed}/Keys/Insert Key Tool"] = "allset.insert_key_tool"
    # Maya 2026 Keys > Remove Key > Redundant Keys ("removes keys with similar values") = Blender's Clean Keyframes;
    # the other Remove Key items are greyed with notices (ui/notices.py)
    m[f"{ed}/Keys/Remove Key/Redundant Keys"] = "graph.clean" if graph else "action.clean"
    return m


# Maya Show > Objects / Attributes = Blender's dope sheet filters (the Graph Editor and Dope Sheet share them).
_DS = "space_data.dopesheet"
SHOW_OBJECTS = {"Geometry": "show_meshes", "Polygon Objects": "show_meshes", "NURBS Objects": "show_curves",
                "GPU Cache": "show_cache_files", "Cameras": "show_cameras", "Joints": "show_armatures",
                # a Blender subdivision surface is a mesh with a Subdivision modifier
                "Subdiv Objects": "show_meshes"}
# Maya attribute groups -> the channel name filter (Blender names: Location / Rotation / Scale)
SHOW_ATTRIBUTES = {"Translate": "Location", "Rotate": "Rotation", "Scale": "Scale", "Scale Rotate Translate": "",
                   "Keyable": ""}


# #110: the kit's Show / List check items (WindowManager flags, ui/editor_chrome.FLAGS)
SHOW_ATTRIBUTE_FLAGS = {"Hidden": "hidden", "Driven by Anim Curve": "anim_curve",
                        "Driven by Expression": "expression", "Driven by Driven Key": "driven_key",
                        "User Defined": "user_defined"}
_WM = "window_manager"


def _list_show_menus(ed):
    m = {
        # Auto Load = Blender's Only Show Selected unless the kit keeps the list (ui/editor_chrome.py)
        f"{ed}/List/Auto Load Selected Objects": _prop(f"{_WM}.allset_auto_load"),
        f"{ed}/List/Load Selected Objects": ("allset.graph_list", {"action": "LOAD"}),
        f"{ed}/List/Add Selected Objects": ("allset.graph_list", {"action": "ADD"}),
        f"{ed}/Show/Objects/IkHandles": _prop(f"{_WM}.allset_show_ik_handles"),
        f"{ed}/Show/Objects/Sets": _prop(f"{_WM}.allset_show_sets"),
        f"{ed}/Show/Objects/Characters": _prop(f"{_WM}.allset_show_characters"),
        f"{ed}/Show/Invert Shown": _prop(f"{_DS}.use_filter_invert"),
        # Maya's Show All also unchecks every attribute filter
        f"{ed}/Show/Show All": "allset.graph_attr_clear",
        # Maya's Clear Below leaves no entry checked = nothing filtered (ui/graph_view.py)
        f"{ed}/Show/Objects/Clear Below": "allset.graph_show_clear",
        f"{ed}/Show/Attributes/Clear Below": "allset.graph_attr_clear",
    }
    m.update({f"{ed}/Show/Objects/{label}": _prop(f"{_DS}.{attr}") for label, attr in SHOW_OBJECTS.items()})
    # the Graph Editor's kit outliner filters its rows; Blender's Dope Sheet channel list can't drop single
    # channels, so there they keep the objects with such an attribute (ui/editor_chrome.row_objects)
    m.update({f"{ed}/Show/Attributes/{label}": _prop(f"{_WM}.allset_attr_{flag}")
              for label, flag in SHOW_ATTRIBUTE_FLAGS.items()})
    # Maya 2026: Show Animated Shapes is an All / One / None expand choice (Maya 2022: one check item); All =
    # Blender's shape key channels shown, One / None greyed with notices
    m[f"{ed}/List/Show Animated Shapes/All"] = _prop(f"{_DS}.show_shapekeys")
    if ed == "Graph Editor":
        m[f"{ed}/List/Show Upstream Curves"] = _prop(f"{_WM}.allset_show_upstream")
        m[f"{ed}/Curves/Pin Channel"] = ("allset.graph_pin", {"pin": True})
        m[f"{ed}/Curves/Unpin Channel"] = ("allset.graph_pin", {"pin": False})
    else:
        m[f"{ed}/List/Hierarchy Below"] = _prop(f"{_WM}.allset_hierarchy_below")
    m.update({f"{ed}/Show/Attributes/{label}": _prop(f"{_DS}.filter_text", text)
              for label, text in SHOW_ATTRIBUTES.items()})
    return m


def _depth2(ed):
    """Items Maya has in both the Graph Editor and the Dope Sheet menus (same annotations)."""
    return {
        f"{ed}/Edit/Transformation Tools/Retime Tool": "allset.retime_tool",
        f"{ed}/Edit/Select Unsnapped": "allset.select_unsnapped",
        f"{ed}/Edit/Set Curve Colors...": "allset.curve_colors",
        f"{ed}/Curves/Default Tangent Weight/Non-weighted Tangents": _prop("addon_prefs.default_tangent_weight",
                                                                         'NON_WEIGHTED'),
        f"{ed}/Curves/Default Tangent Weight/Weighted Tangents": _prop("addon_prefs.default_tangent_weight",
                                                                     'WEIGHTED'),
        f"{ed}/Curves/Non-weighted Tangents": ("allset.curve_weights", {"weighted": False}),
        f"{ed}/Curves/Weighted Tangents": ("allset.curve_weights", {"weighted": True}),
        f"{ed}/Tangents/Lock Tangent Length": ("allset.tangent_weight_lock", {"lock": True}),
        f"{ed}/Tangents/Free Tangent Length": ("allset.tangent_weight_lock", {"lock": False}),
    }


def _help_menu(ed, page):
    return {
        f"{ed}/Help/Search": _url(_MANUAL),
        f"{ed}/Help/Find Menu": "wm.search_menu",
        f"{ed}/Help/Maya Help": _url(_MANUAL),
        f"{ed}/Help/What's New/List of What's New": _url(_NOTES),
        f"{ed}/Help/Help on {ed}": _url(_MANUAL + page),
        f"{ed}/Help/MEL Command Reference": _url(_API),
        f"{ed}/Help/Python Command Reference": _url(_API),
        f"{ed}/Help/Node and Attribute Reference": _url(_API + "bpy.types.html"),
        f"{ed}/Help/Maya Home Page": _url("https://www.blender.org/"),
    }


GE, DS, UV = "Graph Editor", "Dope Sheet", "UV Editor"
_SP = "space_data"

MAP = {
    # --- Graph Editor (Maya's menus) ---
    **_edit_menu(GE, True),
    f"{GE}/View/Frame/Frame All": ("allset.graph_frame", {"mode": 'ALL'}),
    f"{GE}/View/Frame/Frame Selection": ("allset.graph_frame", {"mode": 'SELECTED'}),
    f"{GE}/View/Frame/Frame Playback Range": "anim.scene_range_frame",
    f"{GE}/View/Center Current Time": "allset.graph_center_time",
    f"{GE}/View/Infinity": _prop(f"{_SP}.show_extrapolation"),
    # kit modes (ui/graph_view.py); defaults like Maya: Auto Frame on, Auto Frame Time off, Curve Name Never
    f"{GE}/View/Auto Frame": _prop("addon_prefs.graph_auto_frame"),
    f"{GE}/View/Auto Frame Time": _prop("addon_prefs.graph_auto_frame_time"),
    f"Dope Sheet/View/Auto Frame": _prop("addon_prefs.dope_auto_frame"),      # (off by default, like Maya)
    f"{GE}/View/Curve Name/Always": _prop("addon_prefs.graph_curve_names", 'ALWAYS'),
    f"{GE}/View/Curve Name/Never": _prop("addon_prefs.graph_curve_names", 'NEVER'),
    f"{GE}/View/Curve Name/Active Only": _prop("addon_prefs.graph_curve_names", 'ACTIVE'),
    # Blender's "Only Selected Curve Keyframes" is a preference (#43): open it, don't write it
    f"{GE}/View/Keys/Always": _PREFS_ANIMATION,
    f"{GE}/View/Keys/Active Only": _PREFS_ANIMATION,
    f"{GE}/View/Tangents/Always": _prop(f"{_SP}.use_only_selected_keyframe_handles", False),
    f"{GE}/View/Tangents/Never": _prop(f"{_SP}.show_handles", False),
    f"{GE}/View/Tangents/On Active Keys": _prop(f"{_SP}.use_only_selected_keyframe_handles", True),
    f"{GE}/View/Theme/Color Preferences": ("screen.userpref_show", {"section": 'THEMES'}),
    f"{GE}/View/Absolute View": _prop(f"{_SP}.use_normalization", False),
    f"{GE}/View/Stacked View": ("allset.graph_view_mode", {"mode": "STACKED"}),
    f"{GE}/View/Normalized View": _prop(f"{_SP}.use_normalization", True),
    f"{GE}/View/Renormalize": _prop(f"{_SP}.use_auto_normalization"),
    f"{GE}/View/Show Pins": _prop(f"{_WM}.allset_show_pins"),     # Maya 2026; the kit outliner's pin icons
    # Maya's Select menu sets what a click / drag picks (selectType)
    f"{GE}/Select/All": ("allset.graph_select_type", {"preset": "ALL"}),
    f"{GE}/Select/Only Curve": ("allset.graph_select_type", {"preset": "ONLY_CURVE"}),
    f"{GE}/Select/Curve": _prop("addon_prefs.graph_select_curve"),
    f"{GE}/Select/Key": _prop("addon_prefs.graph_select_key"),
    f"{GE}/Select/In Tangent": _prop("addon_prefs.graph_select_in"),
    f"{GE}/Select/Out Tangent": _prop("addon_prefs.graph_select_out"),
    f"{GE}/Select/Snap time to selection": _prop("addon_prefs.snap_time_to_selection"),
    # #105: Graph Editor depth 2 (Dope Sheet twins below)
    **_depth2(GE),
    f"{GE}/View/Show Buffer Curves": _prop("addon_prefs.graph_show_buffers"),
    f"{GE}/Curves/Buffer Curve/Snapshot": "allset.buffer_snapshot",
    f"{GE}/Curves/Swap Buffer Curve": "allset.buffer_swap",
    f"{GE}/Keys/Add Key Tool": "allset.add_key_tool",
    **_curves_menu(GE, True),
    **_keys_menu(GE, True),
    **_tangents_menu(GE),
    **_list_show_menus(GE),
    f"{GE}/Curves/Reorder Rotation...": "allset.reorder_rotation",    # Maya 2026; same command as Modify menu
    **_help_menu(GE, "editors/graph_editor/index.html"),

    # --- Dope Sheet (Maya's menus; Maya 2026 has no Curves / Tangents menu here, a Channels menu instead) ---
    **_edit_menu(DS, False),
    f"{DS}/View/Frame All": "action.view_all",
    f"{DS}/View/Frame Selection": "action.view_selected",
    f"{DS}/View/Frame Playback Range": "anim.scene_range_frame",
    f"{DS}/View/Center Current Time": "action.view_frame",
    f"{DS}/View/Dope Sheet Summary": _prop(f"{_DS}.show_summary"),
    **_channel_commands(DS, "Channels", False),
    **_keys_menu(DS, False),
    **_list_show_menus(DS),
    f"{DS}/Edit/Select Unsnapped": "allset.select_unsnapped",
    **_help_menu(DS, "editors/dope_sheet/index.html"),

    # --- UV Editor (textureWindow menus); kit UV commands ---
    f"{UV}/Edit/Copy": "uv.copy",
    f"{UV}/Edit/Paste": "uv.paste",
    f"{UV}/Edit/Pin Selection": "uv.pin",
    f"{UV}/Edit/Invert Pinning": ("uv.pin", {"invert": True}),
    f"{UV}/Edit/Unpin Selection": ("uv.pin", {"clear": True}),
    f"{UV}/Create/Assign Checker Shader": "allset.checker_shader",
    f"{UV}/Create/Automatic": "allset.uv_automatic",
    f"{UV}/Create/Best Plane": "allset.uv_planar",          # same actions as the main UV menu (U2)
    f"{UV}/Create/Contour Stretch": "allset.uv_contour",
    f"{UV}/Create/Camera-based": ("v3d", "uv.project_from_view", {}),
    f"{UV}/Create/Normal-based": "allset.uv_planar",
    f"{UV}/Create/Cylindrical": ("v3d", "uv.cylinder_project", {}),
    f"{UV}/Create/Planar": "allset.uv_planar",
    f"{UV}/Create/Spherical": ("v3d", "uv.sphere_project", {}),
    f"{UV}/Select/All": ("uv.select_all", {"action": 'SELECT'}),
    f"{UV}/Select/Clear": ("uv.select_all", {"action": 'DESELECT'}),
    f"{UV}/Select/Inverse": ("uv.select_all", {"action": 'INVERT'}),
    **{f"{UV}/Select/Components/{label}": ("allset.uv_component", {"mode": mode})
       for label, mode in (("Vertex", "VERTEX"), ("Edge", "EDGE"), ("Face", "FACE"), ("UV", "UV"),
                           ("UV Shell", "SHELL"))},
    f"{UV}/Select/Overlapping": "uv.select_overlap",
    f"{UV}/Select/Shortest Edge Path Tool": "uv.shortest_path_select",
    f"{UV}/Select/Grow": "uv.select_more",
    f"{UV}/Select/Shrink": "uv.select_less",
    **{f"{UV}/Select/Convert Selection/{label}": ("allset.uv_component", {"mode": mode})
       for label, mode in (("To Vertices", "VERTEX"), ("To Edges", "EDGE"), ("To Faces", "FACE"), ("To UVs", "UV"),
                           ("To UV Shell", "SHELL"))},
    # the main Select menu's conversions (operators/select_convert.py; with UV Sync Selection off they read
    # the selected UVs as their vertices)
    **{f"{UV}/Select/{label}": ("allset.select_convert", {"kind": kind})
       for label, kind in (("Grow Along Loop", 'GROW_LOOP'), ("Shrink Along Loop", 'SHRINK_LOOP'),
                           ("Convert Selection/To Vertex Perimeter", 'VERTEX_PERIMETER'),
                           ("Convert Selection/To Edge Perimeter", 'EDGE_PERIMETER'),
                           ("Convert Selection/To Face Path", 'FACE_PATH'),
                           ("Convert Selection/To Face Perimeter", 'FACE_PERIMETER'),
                           ("Convert Selection/To UV Shell Border", 'UV_SHELL_BORDER'),
                           ("Convert Selection/To UV Perimeter", 'UV_PERIMETER'),
                           ("Convert Selection/To UV Edge Loop", 'UV_EDGE_LOOP'))},
    f"{UV}/Cut/Sew/Cut": "allset.uv_cut",
    f"{UV}/Cut/Sew/Sew": "allset.uv_sew",
    f"{UV}/Cut/Sew/Merge": "allset.uv_merge",     # Maya polyMergeUV
    f"{UV}/Cut/Sew/Move and Sew": "allset.uv_move_sew",
    f"{UV}/Cut/Sew/Create UV Shell": "allset.uv_create_shell",
    f"{UV}/Cut/Sew/Stitch Together": "uv.stitch",
    f"{UV}/Modify/Align": ("uv.align", {"axis": 'ALIGN_AUTO'}),
    f"{UV}/Modify/Flip": ("transform.mirror", {"constraint_axis": (True, False, False)}),
    f"{UV}/Modify/Linear Align": ("uv.align", {"axis": 'ALIGN_S'}),
    f"{UV}/Modify/Match UVs": "uv.remove_doubles",
    f"{UV}/Modify/Rotate": ("transform.rotate", {"value": -math.pi / 2}),
    f"{UV}/Modify/Unitize": "uv.reset",
    f"{UV}/Modify/Gather Shells": "uv.pack_islands",
    f"{UV}/Modify/Layout": "allset.uv_layout",
    f"{UV}/Modify/Orient Shells": "allset.uv_orient_shells",
    f"{UV}/Modify/Orient Shells to Edges": "allset.uv_orient_edges",
    f"{UV}/Modify/Stack Shells": "allset.uv_stack",
    f"{UV}/Modify/Stack and Orient Shells": ("allset.uv_stack", {"orient": 'ORIENT'}),
    f"{UV}/Modify/Snap and Stack": "allset.uv_snap_stack",
    f"{UV}/Modify/Snap Together": "allset.uv_snap_together",
    f"{UV}/Modify/Unstack Shells": "allset.uv_unstack",
    f"{UV}/Modify/Distribute Shells": "allset.uv_distribute",
    f"{UV}/Modify/Normalize": "allset.uv_normalize",
    f"{UV}/Edit/Delete": "allset.uv_delete",
    f"{UV}/Tools/Move UV Shell": "allset.uv_move_shell",
    f"{UV}/View/Toggle Shell Borders": ("allset.uv_display", {"mode": 'SHELL_BORDERS'}),
    f"{UV}/View/Texture Borders": _prop("window_manager.allset_uv_texture_borders"),
    # Shaded = faces shown + coloured by UV winding, Wireframe = no faces (opacity 0 still drew fills)
    f"{UV}/View/Shaded": _prop("window_manager.allset_uv_face_colors", True),
    f"{UV}/View/Wireframe": _prop("window_manager.allset_uv_face_colors", False),
    f"{UV}/View/Isolate Select/View Selected": "allset.uv_isolate",
    f"{UV}/Image/Display": ("allset.uv_display", {"mode": 'IMAGE'}),
    f"{UV}/Modify/Randomize Shells": "uv.randomize_uv_transform",
    f"{UV}/Modify/Optimize": "uv.minimize_stretch",
    f"{UV}/Modify/Straighten Shell": "uv.follow_active_quads",
    f"{UV}/Modify/Straighten UVs": ("uv.align", {"axis": 'ALIGN_S'}),
    f"{UV}/Modify/Unfold": "allset.uv_unfold",
    # Maya-style UV commands (operators/uv_modify.py)
    f"{UV}/Modify/Map Border": "allset.uv_map_border",
    f"{UV}/Modify/Straighten Border": "allset.uv_straighten_border",
    f"{UV}/Modify/Match Grid": "allset.uv_match_grid",
    f"{UV}/Modify/Layout Along": "allset.uv_layout_along",
    f"{UV}/Modify/Stack Similar Shells": "allset.uv_stack_similar",
    f"{UV}/Modify/Distribute UVs": "allset.uv_distribute_uvs",
    # selection / isolate (operators/uv_select_178.py, ui/uv_display.py)
    f"{UV}/Select/Unmapped Faces": "allset.uv_select_unmapped",
    f"{UV}/Select/Back-Facing": ("allset.uv_select_facing", {"front": False}),
    f"{UV}/Select/Front-Facing": ("allset.uv_select_facing", {"front": True}),
    f"{UV}/Select/Texture Borders": "allset.uv_select_texture_borders",
    f"{UV}/Select/Non-Overlapping": "allset.uv_select_non_overlapping",
    f"{UV}/Select/Filter Selection/Connected Faces": ("allset.uv_filter_faces", {"kind": 'CONNECTED'}),
    f"{UV}/Select/Filter Selection/Contained Faces": ("allset.uv_filter_faces", {"kind": 'CONTAINED'}),
    f"{UV}/Select/Convert Selection/To Connected Faces": "allset.uv_to_connected_faces",
    f"{UV}/Edit/Unpin All": "allset.uv_unpin_all",
    f"{UV}/View/Isolate Select/Add Selected": ("allset.uv_isolate_edit", {"action": 'ADD'}),
    f"{UV}/View/Isolate Select/Remove Selected": ("allset.uv_isolate_edit", {"action": 'REMOVE'}),
    f"{UV}/View/Isolate Select/Remove All": ("allset.uv_isolate_edit", {"action": 'CLEAR'}),
    f"{UV}/Tools/Hide UV Toolkit": _prop(f"{_SP}.show_region_ui"),
    f"{UV}/Tools/Select": _uv_tool("builtin.select_box"),
    f"{UV}/Tools/Move": _uv_tool("builtin.move"),
    f"{UV}/Tools/Rotate": _uv_tool("builtin.rotate"),
    f"{UV}/Tools/Scale": _uv_tool("builtin.scale"),
    f"{UV}/Tools/Tweak": _uv_tool("builtin.select"),
    f"{UV}/Tools/Smooth": _uv_tool("sculpt.uv_sculpt_relax"),
    f"{UV}/Tools/Optimize": _uv_tool("sculpt.uv_sculpt_relax"),
    f"{UV}/Tools/Grab": _uv_tool("sculpt.uv_sculpt_grab"),
    f"{UV}/Tools/Pinch": _uv_tool("sculpt.uv_sculpt_pinch"),
    f"{UV}/View/UV Distortion": _prop(f"{_SP}.uv_editor.show_stretch"),
    f"{UV}/View/Grid": _prop(f"{_SP}.overlay.show_grid_background"),
    f"{UV}/View/Toolbar": _prop(f"{_SP}.show_region_toolbar"),
    f"{UV}/View/Frame All": "image.view_all",
    f"{UV}/View/Frame Selection": "image.view_selected",
    f"{UV}/Image/RGB": _prop(f"{_SP}.display_channels", 'COLOR'),
    f"{UV}/Image/RGBA": _prop(f"{_SP}.display_channels", 'COLOR_ALPHA'),
    f"{UV}/Image/Alpha": _prop(f"{_SP}.display_channels", 'ALPHA'),
    f"{UV}/Image/Pixel Snap": _prop(f"{_SP}.uv_editor.pixel_round_mode", 'CORNER'),
    f"{UV}/Image/UV Snapshot...": "uv.export_layout",
    f"{UV}/Textures/Checker Map": "allset.checker_toggle",
    f"{UV}/UV Sets/UV Set Editor": ("allset.open_editor", {"ui_type": 'PROPERTIES', "tab": 'DATA'}),
    f"{UV}/UV Sets/Copy UVs to UV Set/Copy into New UV Set": "mesh.uv_texture_add",
    f"{UV}/UV Sets/Create Empty UV Set": "mesh.uv_texture_add",
    f"{UV}/UV Sets/Delete Current UV Set": "mesh.uv_texture_remove",
    # operators/uv_206.py, ui/uv_hud.py
    f"{UV}/Cut/Sew/Auto Seams": "allset.uv_auto_seams",
    f"{UV}/Cut/Sew/Create Shell (Grid)": "allset.uv_grid_shell",
    f"{UV}/Cut/Sew/Split": "allset.uv_split",
    f"{UV}/Modify/Cycle": "allset.uv_cycle",
    f"{UV}/View/Heads-Up Display/Isolate Select": _prop("window_manager.allset_uv_hud_isolate"),
    f"{UV}/View/Heads-Up Display/UV Position": _prop("window_manager.allset_uv_hud_position"),
    f"{UV}/View/Heads-Up Display/UV Statistics": _prop("window_manager.allset_uv_hud_statistics"),
    f"{UV}/UV Sets/Rename Current UV Set...": "allset.uv_set_rename",
    f"{UV}/UV Sets/Copy UVs to UV Set/map1": ("allset.uv_set_copy_to", {"target": "map1"}),
    f"{UV}/UV Sets/map1": ("allset.uv_set_current", {"target": "map1"}),
    **_help_menu(UV, "editors/uv/index.html"),
    "UV Toolkit/Help/Help on UV Toolkit": _url(_MANUAL + "modeling/meshes/uv/index.html"),
}

# --- Hypershade, Script Editor -------------------------------------------------------------------
HS, SE = "Hypershade", "Script Editor"
_HS_MATERIALS = {"Anisotropic": 'ANISOTROPIC', "Blinn": 'BLINN', "Lambert": 'LAMBERT', "Layered Shader": 'LAYERED',
                 "Phong": 'PHONG', "Phong E": 'PHONG_E', "Ramp Shader": 'RAMP', "Standard Surface": 'STANDARD_SURFACE',
                 "Surface Shader": 'SURFACE', "Use Background": 'USE_BACKGROUND'}
_HS_LIGHTS = {"Directional Light": 'DIRECTIONAL_LIGHT', "Point Light": 'POINT_LIGHT', "Spot Light": 'SPOT_LIGHT',
              "Area Light": 'AREA_LIGHT'}


def _hs_edit(action):
    return ("allset.hs_edit", {"action": action})


def _editor(ui_type):
    return ("allset.open_editor", {"ui_type": ui_type})


# Hypershade Create menu node types -> Blender shader nodes (added to the current material's graph)
HS_NODES = {
    "2D Textures/Checker": 'ShaderNodeTexChecker', "2D Textures/File": 'ShaderNodeTexImage',
    "2D Textures/Fractal": 'ShaderNodeTexNoise', "2D Textures/Noise": 'ShaderNodeTexNoise',
    "2D Textures/Simplex Noise": 'ShaderNodeTexNoise', "2D Textures/Ramp": 'ShaderNodeValToRGB',
    "2D Textures/Water": 'ShaderNodeTexWave', "2D Textures/Grid": 'ShaderNodeTexBrick',
    "2D Textures/Movie": 'ShaderNodeTexImage', "2D Textures/PSD File": 'ShaderNodeTexImage',
    "3D Textures/Brownian": 'ShaderNodeTexNoise', "3D Textures/Cloud": 'ShaderNodeTexNoise',
    "3D Textures/Solid Fractal": 'ShaderNodeTexNoise', "3D Textures/Volume Noise": 'ShaderNodeTexNoise',
    "3D Textures/Marble": 'ShaderNodeTexWave', "3D Textures/Wood": 'ShaderNodeTexWave',
    "3D Textures/Granite": 'ShaderNodeTexVoronoi', "3D Textures/Leather": 'ShaderNodeTexVoronoi',
    "3D Textures/Rock": 'ShaderNodeTexVoronoi',
    "Environment Textures/Env Sphere": 'ShaderNodeTexEnvironment',
    "Layered Texture": 'ShaderNodeMix',
    "General Utilities/Bump 2d": 'ShaderNodeBump', "General Utilities/Bump 3d": 'ShaderNodeBump',
    "Math Utilities/Operation/Multiply Divide": 'ShaderNodeVectorMath',
    "Math Utilities/Operation/Plus Minus Average": 'ShaderNodeVectorMath',
    "General Utilities/Reverse": 'ShaderNodeInvert', "General Utilities/Set Range": 'ShaderNodeMapRange',
    "General Utilities/2d Placement": 'ShaderNodeMapping', "General Utilities/3d Placement": 'ShaderNodeMapping',
    "General Utilities/Sampler Info": 'ShaderNodeNewGeometry', "Math Utilities/Transformation/Vector Product": 'ShaderNodeVectorMath',
    "Math Utilities/Transformation/Distance Between": 'ShaderNodeVectorMath', "General Utilities/Condition": 'ShaderNodeMath',
    "Math Linear Utilities/Operation/Add Double Linear": 'ShaderNodeMath',
    "Math Linear Utilities/Operation/Mult Double Linear": 'ShaderNodeMath',
    "Scalar Utilities/Float Constant": 'ShaderNodeValue', "Scalar Utilities/Float Math": 'ShaderNodeMath',
    "Scalar Utilities/Unit Conversion": 'ShaderNodeMath', "Scalar Utilities/Blend Two Attr": 'ShaderNodeMix',
    "Color Utilities/Blend Colors": 'ShaderNodeMix', "Color Utilities/Channels": 'ShaderNodeSeparateColor',
    "Color Utilities/Clamp": 'ShaderNodeClamp', "Color Utilities/Color Constant": 'ShaderNodeRGB',
    "Color Utilities/Color Math": 'ShaderNodeMix', "Color Utilities/Contrast": 'ShaderNodeBrightContrast',
    "Color Utilities/Gamma Correct": 'ShaderNodeGamma', "Color Utilities/Hsv To Rgb": 'ShaderNodeCombineColor',
    "Color Utilities/Rgb To Hsv": 'ShaderNodeSeparateColor', "Color Utilities/Luminance": 'ShaderNodeRGBToBW',
    "Color Utilities/Remap Value": 'ShaderNodeMapRange', "Color Utilities/Remap Color": 'ShaderNodeRGBCurve',
    "Color Utilities/Remap Hsv": 'ShaderNodeHueSaturation',
    # #123: Blender nodes that do the same job (ui/notices.py names the Blender node in the tooltip)
    "General Utilities/Uv Chooser": 'ShaderNodeUVMap', "Particle Utilities/Particle Sampler": 'ShaderNodeParticleInfo',
    "Environment Textures/Env Ball": 'ShaderNodeTexEnvironment',
    "Environment Textures/Env Cube": 'ShaderNodeTexEnvironment', "Environment Textures/Env Sky": 'ShaderNodeTexSky',
    "Color Utilities/Color Composite": 'ShaderNodeMix', "Color Utilities/Color Correct": 'ShaderNodeHueSaturation',
    "Scalar Utilities/Float Composite": 'ShaderNodeMath', "Scalar Utilities/Float Correct": 'ShaderNodeMapRange',
    "2D Textures/Mountain": 'ShaderNodeTexNoise', "3D Textures/Stucco": 'ShaderNodeTexNoise',
}
# #123: Maya materials Blender builds from other nodes (operators/render_more.py EXTRA_KINDS)
HS_EXTRA = {"Volumetric Materials/Volume Shader": 'VOLUME_SHADER', "Volumetric Materials/Volume Fog": 'VOLUME_FOG',
            "Volumetric Materials/Light Fog": 'LIGHT_FOG', "Volumetric Materials/Env Fog": 'ENV_FOG',
            "Materials/Hair Physical Shader": 'HAIR_PHYSICAL', "Materials/Hair Tube Shader": 'HAIR_TUBE',
            "Materials/Usd Preview Surface": 'USD_PREVIEW', "Materials/Shading Map": 'SHADING_MAP'}


# Maya 2026 Math Utilities nodes -> (Blender shader node, its operation or ""); Math Linear Utilities has the same
# nodes as "<name> Double Linear". Matrix, quaternion and time nodes have no shader counterpart (notices).
_M, _V = 'ShaderNodeMath', 'ShaderNodeVectorMath'
HS_MATH = {
    "Comparison/Equal": (_M, 'COMPARE'), "Comparison/Greater Than": (_M, 'GREATER_THAN'),
    "Comparison/Less Than": (_M, 'LESS_THAN'), "Comparison/Max": (_M, 'MAXIMUM'), "Comparison/Min": (_M, 'MINIMUM'),
    "Operation/Absolute": (_M, 'ABSOLUTE'), "Operation/Average": (_M, 'ADD'), "Operation/Divide": (_M, 'DIVIDE'),
    "Operation/Inverse Lerp": ('ShaderNodeMapRange', ""), "Operation/Lerp": ('ShaderNodeMix', ""),
    "Operation/Log": (_M, 'LOGARITHM'), "Operation/Modulo": (_M, 'MODULO'), "Operation/Multiply": (_M, 'MULTIPLY'),
    "Operation/Power": (_M, 'POWER'), "Operation/Subtract": (_M, 'SUBTRACT'), "Operation/Sum": (_M, 'ADD'),
    "Rounding/Ceil": (_M, 'CEIL'), "Rounding/Clamp Range": ('ShaderNodeClamp', ""), "Rounding/Floor": (_M, 'FLOOR'),
    "Rounding/Round": (_M, 'ROUND'), "Rounding/Smooth Step": ('ShaderNodeMapRange', ""),
    "Rounding/Truncate": (_M, 'TRUNC'),
    "Transformation/Cross Product": (_V, 'CROSS_PRODUCT'), "Transformation/Dot Product": (_V, 'DOT_PRODUCT'),
    "Transformation/Length": (_V, 'LENGTH'), "Transformation/Normalize": (_V, 'NORMALIZE'),
    "Transformation/Rotate Vector": ('ShaderNodeVectorRotate', ""),
    "Trigonometry/Acos": (_M, 'ARCCOSINE'), "Trigonometry/Asin": (_M, 'ARCSINE'), "Trigonometry/Atan": (_M, 'ARCTANGENT'),
    "Trigonometry/Atan 2": (_M, 'ARCTAN2'), "Trigonometry/Cos": (_M, 'COSINE'), "Trigonometry/Sin": (_M, 'SINE'),
    "Trigonometry/Tan": (_M, 'TANGENT'), "Trigonometry/Pi": ('ShaderNodeValue', ""),
}


def _hs_nodes():
    out = {f"{HS}/Create/{label}": ("allset.hs_node", {"node_type": node, "label": label.rsplit("/", 1)[-1]})
           for label, node in HS_NODES.items()}
    for label, (node, op) in HS_MATH.items():
        group, name = label.split("/")
        pairs = [(f"Math Utilities/{label}", name)]
        if name != "Pi":            # no linear Pi node
            pairs.append((f"Math Linear Utilities/{group}/{name} Double Linear", f"{name} Double Linear"))
        for path, maya in pairs:
            props = {"node_type": node, "label": maya}
            if op:
                props["operation"] = op
            out[f"{HS}/Create/{path}"] = ("allset.hs_node", props)
    return out


MAP.update({
    f"{HS}/File/Import...": "allset.file_import",
    f"{HS}/Edit/Delete": _hs_edit("DELETE"),
    f"{HS}/Edit/Delete Unused Nodes": _hs_edit("DELETE_UNUSED"),
    f"{HS}/Edit/Delete All by Type/Shading Groups and Materials": _hs_edit("DELETE_MATERIALS"),
    f"{HS}/Edit/Delete All by Type/Lights": ("allset.delete_by_type", {"type": 'LIGHTS', "all": True}),
    f"{HS}/Edit/Delete All by Type/Cameras and Image Planes": ("allset.delete_by_type",
                                                               {"type": 'CAMERAS', "all": True}),
    f"{HS}/Edit/Select Objects with Materials": _hs_edit("SELECT_OBJECTS"),
    f"{HS}/Edit/Select Materials from Objects": _hs_edit("FROM_OBJECT"),
    f"{HS}/Edit/Duplicate/Shading Network": _hs_edit("DUPLICATE"),
    f"{HS}/Edit/Duplicate/Without Network": _hs_edit("DUPLICATE"),
    f"{HS}/View/Frame All": ("allset.hs_graph", {"action": "FRAME_ALL"}),
    f"{HS}/View/Frame Selected": ("allset.hs_graph", {"action": "FRAME_SELECTED"}),
    **{f"{HS}/View/{label}": _prop("window_manager.allset_hs_swatch", key)
       for label, key in (("As Icons", 'ICONS'), ("As List", 'LIST'), ("As Small Swatches", 'SMALL'),
                          ("As Medium Swatches", 'MEDIUM'), ("As Large Swatches", 'LARGE'),
                          ("As Extra Large Swatches", 'XLARGE'))},
    **{f"{HS}/View/{label}": _prop("window_manager.allset_hs_sort", key)
       for label, key in (("By Name", 'NAME'), ("By Type", 'TYPE'), ("By Time", 'TIME'))},
    f"{HS}/View/Reverse Order": _prop("window_manager.allset_hs_reverse"),
    **{f"{HS}/Create/Materials/{label}": ("allset.hs_create", {"kind": kind}) for label, kind in _HS_MATERIALS.items()},
    **{f"{HS}/Create/Lights/{label}": ("allset.create", {"kind": kind}) for label, kind in _HS_LIGHTS.items()},
    **{f"{HS}/Create/{label}": ("allset.hs_create_extra", {"kind": kind}) for label, kind in HS_EXTRA.items()},
    f"{HS}/Create/Camera": ("allset.create", {"kind": 'CAMERA'}),
    f"{HS}/Create/Rendering/Render Layer": "scene.view_layer_add",
    f"{HS}/Create/Create Render Node...": ("wm.call_menu", {"name": "NODE_MT_add"}),
    f"{HS}/Graph/Graph Materials on Selected Objects": _hs_edit("FROM_OBJECT"),
    f"{HS}/Graph/Input and Output Connections": ("allset.hs_graph", {"action": "BOTH"}),
    f"{HS}/Graph/Input Connections": ("allset.hs_graph", {"action": "UPSTREAM"}),
    f"{HS}/Graph/Output Connections": ("allset.hs_graph", {"action": "DOWNSTREAM"}),
    **{f"{HS}/Window/{label}": "allset.hypershade"
       for label in ("Browser...", "Property Editor...", "Material Viewer...", "Create...")},
    f"{HS}/Window/Render View...": "render.view_show",
    f"{HS}/Window/Outliner...": _editor('OUTLINER'),
    f"{HS}/Window/UV Editor...": _editor('UV'),
    f"{HS}/Window/Graph Editor...": _editor('FCURVES'),
    f"{HS}/Window/Attribute Spread Sheet...": _editor('SPREADSHEET'),
    **_help_menu(HS, "render/shader_nodes/index.html"),
    f"{HS}/Help/Help on Shader Library": _url(_MANUAL + "render/materials/index.html"),

    f"{SE}/File/Open Script...": "text.open",
    f"{SE}/File/Save Script...": "text.save_as",
    f"{SE}/Edit/Undo": "ed.undo",
    f"{SE}/Edit/Redo": "ed.redo",
    f"{SE}/Edit/Cut": "text.cut",
    f"{SE}/Edit/Copy": "text.copy",
    f"{SE}/Edit/Paste": "text.paste",
    f"{SE}/Edit/Select All": "text.select_all",
    f"{SE}/Edit/Goto line...": "text.jump",
    f"{SE}/Edit/Search and Replace...": "text.start_find",
    f"{SE}/Edit/Indent Selection": "text.indent",
    f"{SE}/Edit/Unindent Selection": "text.unindent",
    f"{SE}/Edit/Clear History": ("allset.script_clear", {"what": "HISTORY"}),
    f"{SE}/Edit/Clear Input": ("allset.script_clear", {"what": "INPUT"}),
    f"{SE}/Edit/Clear All": ("allset.script_clear", {"what": "ALL"}),
    # History menu = Maya scriptEditorInfo options as add-on preferences (command_line/runner.py)
    f"{SE}/History/Batch Render Messages": _prop("addon_prefs.se_batch_render_messages"),
    f"{SE}/History/Echo All Commands": _prop("addon_prefs.se_echo_all"),
    f"{SE}/History/Line numbers in errors": _prop("addon_prefs.se_line_numbers"),
    f"{SE}/History/Show Stack Trace": _prop("addon_prefs.se_stack_trace"),
    f"{SE}/History/History Output/Show Both": _prop("addon_prefs.se_history_output", 'BOTH'),
    f"{SE}/History/History Output/Show MEL Only": _prop("addon_prefs.se_history_output", 'MEL'),
    f"{SE}/History/History Output/Show Python Only": _prop("addon_prefs.se_history_output", 'PYTHON'),
    f"{SE}/History/Suppress Command Results": _prop("addon_prefs.se_suppress_results"),
    f"{SE}/History/Suppress Info Messages": _prop("addon_prefs.se_suppress_info"),
    f"{SE}/History/Suppress Warning Messages": _prop("addon_prefs.se_suppress_warnings"),
    f"{SE}/History/Suppress Error Messages": _prop("addon_prefs.se_suppress_errors"),
    f"{SE}/History/Suppress Duplicate Variable Messages": _prop("addon_prefs.se_suppress_dup_vars"),
    f"{SE}/History/Suppress Stack Window": _prop("addon_prefs.se_suppress_stack_window"),
    f"{SE}/Command/Show line numbers": _prop("space_data.show_line_numbers"),
    f"{SE}/Command/Use tabs for indent": _prop("space_data.text.indentation", 'TABS'),
    f"{SE}/Command/Command Completion": "text.autocomplete",
    f"{SE}/Command/Execute": "allset.script_run",
    f"{SE}/Tabs/New Tab...": ("allset.script_tab", {"new": True}),
    f"{SE}/Tabs/Delete Tab": "text.unlink",
    **_help_menu(SE, "editors/text_editor.html"),
    f"{SE}/Help/Help on MEL": _url(_API),
    f"{SE}/Help/Help on Python": _url(_API + "info_quickstart.html"),
})


# the Reference Editor (operators/references.py; literal: no bpy imports)
RE = "Reference Editor"


def _ref(action):
    return ("allset.reference_cmd", {"action": action})


MAP.update({
    f"{RE}/File/Create Reference...": "allset.create_reference",
    f"{RE}/File/Import Objects from Reference": _ref("IMPORT"),
    f"{RE}/File/Export Selection ...": "allset.file_export_selection",
    f"{RE}/File/Export to Offline File...": ("allset.reference_offline", {"mode": "EXPORT"}),
    f"{RE}/File/Assign Offline File...": ("allset.reference_offline", {"mode": "ASSIGN"}),
    f"{RE}/File/List Reference Edits...": _ref("LIST"),
    f"{RE}/File/Clean Up Reference": _ref("CLEAN"),
    f"{RE}/File/Select File Contents": _ref("SELECT"),
    f"{RE}/Reference/Reload Reference": _ref("RELOAD"),
    f"{RE}/Reference/Unload Reference": _ref("UNLOAD"),
    f"{RE}/Reference/Load Related References": _ref("LOAD_RELATED"),
    f"{RE}/Reference/Unload Related References": _ref("UNLOAD_RELATED"),
    f"{RE}/Reference/Duplicate Reference": _ref("DUPLICATE"),
    f"{RE}/Reference/Replace Reference": "allset.reference_replace",
    f"{RE}/Reference/Recently Replaced Files": ("menu", "ALLSET_MT_reference_recent"),
    f"{RE}/Reference/Remove Reference": _ref("REMOVE"),
    f"{RE}/Reference/Lock Reference": _ref("LOCK"),
    f"{RE}/Reference/Unlock Reference": _ref("UNLOCK"),
    **_help_menu(RE, "files/linked_libraries/index.html"),
})
MAP.update(_hs_nodes())


# Component / Shape / Connection Editor windows (ui/component_editor.py, shape_editor.py,
# connection_editor.py; literal: no bpy imports)
CE, SH, CN = "Component Editor", "Shape Editor", "Connection Editor"
MAP.update({
    f"{SH}/Edit/Deselect All": ("allset.shape_pick", {"key": ""}),
    f"{SH}/Create/Blend Shape Deformer": "allset.shape_create",
    f"{SH}/Create/Add Target": "allset.shape_add_target",
    f"{SH}/Create/Add Selection as Target": "allset.shape_add_selection",
    f"{SH}/Shapes/Duplicate Target": "allset.shape_duplicate",
    f"{SH}/Shapes/Flip Target": "allset.shape_flip",
    f"{SH}/Shapes/Mirror Target": ("allset.shape_mirror", {"direction": "POSITIVE"}),
    f"{SH}/Shapes/Key": "allset.shape_key",
    f"{SH}/Shapes/Reset": "allset.shape_reset",
    # #137: in-between and combination targets (operators/blend_shapes_227.py)
    f"{SH}/Create/Add In-Between Target": "allset.shape_add_inbetween",
    f"{SH}/Create/Add Selection as In-Between Target": ("allset.shape_add_inbetween", {"selection": True}),
    f"{SH}/Create/Add Combination Target": "allset.shape_add_combination",
    f"{SH}/Create/Add Selection as Combination Target": ("allset.shape_add_combination", {"mode": "SELECTION"}),
    f"{SH}/Shapes/Set as Combination Target": ("allset.shape_add_combination", {"mode": "SET"}),
    **_help_menu(SH, "animation/shape_keys/index.html"),
    f"{SH}/Help/Help on Shape Authoring": _url(_MANUAL + "animation/shape_keys/index.html"),

    f"{CE}/Options/Auto Update": _prop("window_manager.allset_ce_auto_update"),
    f"{CE}/Options/Hide Zero Columns": _prop("window_manager.allset_ce_hide_zero"),
    f"{CE}/Layout/Load Selected Components": "allset.ce_load",
    f"{CE}/Layout/Show All Columns": _prop("window_manager.allset_ce_hide_zero", False),
    **_help_menu(CE, "modeling/meshes/editing/mesh/vertex.html"),

    f"{CN}/Options/Auto-connect": _prop("window_manager.allset_cn_auto"),
    f"{CN}/Options/Channel Names/Nice": _prop("window_manager.allset_cn_names", "NICE"),
    f"{CN}/Options/Channel Names/Long": _prop("window_manager.allset_cn_names", "LONG"),
    f"{CN}/Options/Channel Names/Short": _prop("window_manager.allset_cn_names", "SHORT"),
    **_help_menu(CN, "animation/drivers/index.html"),
})
MAP.pop(f"{SH}/Help/Help on {SH}", None)    # Maya titles it Help on Shape Authoring


# Change Rotation Interp / Key Sync / Peak Removal / Select Curve Nodes (operators/graph_curves_203.py);
# Maya 2026's Dope Sheet has no Curves menu / Select Curve Nodes
# (literal here: tools/menu_count.py loads the menu maps without bpy)
_ROT_MODES = {"Independent Euler": "NONE", "Synchronized Euler": "EULER", "Quaternion Slerp": "SLERP",
              "Quaternion Cubic": "SQUAD", "Quaternion Tangent Dependent": "TANGENT"}
for _ed in (GE,):
    MAP.update({f"{_ed}/Curves/Change Rotation Interp/{label}": ("allset.rotation_interp", {"mode": mode})
                for label, mode in _ROT_MODES.items()})
    MAP[f"{_ed}/Curves/Key Sync Filter"] = "allset.key_sync_filter"
    MAP[f"{_ed}/Curves/Peak Removal Filter"] = "allset.peak_removal_filter"
    MAP[f"{_ed}/Edit/Select Curve Nodes"] = "allset.select_curve_nodes"

# Maya greys these while their state forbids them (List > Load / Add Selected Objects while Auto Load is on):
# menu_sets.draw_item draws them with Blender's poll instead of the always-enabled
# allset.menu_item route
GREY_ON_POLL = {f"{ed}/List/{label}" for ed in (GE, DS) for label in ("Load Selected Objects", "Add Selected Objects")}
