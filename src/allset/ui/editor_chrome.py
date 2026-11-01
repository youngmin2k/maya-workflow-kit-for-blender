# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya editor chrome for the Graph Editor, Dope Sheet and UV Editor.

Maya 2022's editors:

- menu bars: Graph Editor Edit / View / Select / Curves / Keys / Tangents / List / Show / Help, Dope Sheet the same
  without Select, UV Editor Edit / Create / Select / Cut/Sew / Modify / Tools / View / Image / Textures / UV Sets /
  Help (structure ``editor_menu_data``, actions ``editor_menu_map``, classes built by ``menu_sets``);
- icon rows under them (Maya's control names; order kept, Maya icons not copied);
- the Graph Editor's outliner lists the object and its attributes "Translate X" (red) / "Translate Y" (green), no
  Action / group rows.

Blender: ``GRAPH_HT_header.draw`` and ``DOPESHEET_HT_header.draw`` are swapped while the kit is on (restored on
unregister, ``tests/kit.py`` snapshots them); the UV Editor's header / tool header go through the ``ui/shelf.py``
``IMAGE_HT_header`` wrapper. Graph Editor and Dope Sheet areas have a single header row (no tool header region), so
the icon row follows the menus on it; the UV Editor's tool header is Maya's second row. Blender's own editor menus
stay in a "Blender" menu at the end of the bar.
"""

import re
import types

import blf
import bpy
import gpu
from bpy.props import BoolProperty, IntProperty, StringProperty
from gpu_extras.batch import batch_for_shader

from .. import live_refs
from . import editor_menu_data, graph_layers, menu_map, menu_sets

GE, DS, UV = "Graph Editor", "Dope Sheet", "UV Editor"


def enabled(context):
    """Maya editor chrome follows the Panel Menus preference (Maya menus in editor headers)."""
    from .. import preferences
    try:
        return preferences.get(context).maya_panel_menus
    except (KeyError, AttributeError):    # add-on prefs gone (disable in progress) / a context without preferences
        return False


def is_graph(space):
    return space is not None and space.type == 'GRAPH_EDITOR' and space.mode == 'FCURVES'


def is_dope(space):
    return space is not None and space.type == 'DOPESHEET_EDITOR' and space.mode in {'DOPESHEET', 'ACTION'}


def is_uv(space):
    return space is not None and space.type == 'IMAGE_EDITOR' and space.mode == 'UV'


# --- menu bars ---------------------------------------------------------------------------------------------------

BLENDER_MENUS = {GE: "GRAPH_MT_editor_menus", DS: "DOPESHEET_MT_editor_menus", UV: "IMAGE_MT_editor_menus",
                 # Hypershade / Script Editor windows
                 "Hypershade": "NODE_MT_editor_menus", "Script Editor": "INFO_MT_editor_menus"}


def _blender_menu_class(editor):
    def draw(self, context):
        layout = self.layout
        if editor == DS:
            layout.prop(context.space_data, "ui_mode", text="")
            layout.separator()
        getattr(bpy.types, BLENDER_MENUS[editor]).draw(self, context)
    idname = "ALLSET_MT_ed_blender_" + editor.replace(" ", "").lower()
    return type(idname, (bpy.types.Menu,), {"bl_idname": idname, "bl_label": "Blender", "draw": draw,
                                             "__doc__": f"Blender's own {editor} menus"})


def _bar_class(editor):
    def draw(self, context):
        draw_menu_bar(self.layout, context, editor)
    idname = "ALLSET_MT_ed_bar_" + editor.replace(" ", "").lower()
    return type(idname, (bpy.types.Menu,), {"bl_idname": idname, "bl_label": "Menus", "draw": draw,
                                             "__doc__": f"The Maya {editor} menus folded into one menu"})


_BLENDER = {ed: _blender_menu_class(ed) for ed in BLENDER_MENUS}
_BAR = {ed: _bar_class(ed) for ed in BLENDER_MENUS}


def draw_menu_bar(layout, context, editor):
    for i, (title, _items) in enumerate(editor_menu_data.EDITORS[editor]):
        layout.menu(menu_sets.editor_menu_idname(editor, i), text=title)
    if editor in _BLENDER:
        layout.menu(_BLENDER[editor].bl_idname, text="Blender")


def draw_menus(layout, context, editor):
    if context.area is None or context.area.show_menus:
        draw_menu_bar(layout.row(align=True), context, editor)
    else:
        layout.menu(_BAR[editor].bl_idname, text="", icon='COLLAPSEMENU')


# --- icon rows -----------------------------------------------------------------------------------------------------
# (Maya control name, Blender icon, action or None, Maya tooltip). An action is a menu_map value
# (incl. ("prop", ...)); "|" = separator, "STATS" = the selected key's time / value fields, "IMAGE" / "UVMAP" = the
# UV Editor's texture field / UV set. Unmapped buttons draw greyed with their notice (NOTICES below).

def _t(kind):
    return ("allset.set_tangent", {"kind": kind})


def _inf(side, mode):
    return ("allset.curve_infinity", {"side": side, "mode": mode})


GRAPH_ICONS = (
    ("directKeyTool", 'RESTRICT_SELECT_OFF', None, "Move Nearest Picked Key Tool"),
    ("insertKeyTool", 'KEY_HLT', "allset.insert_key_tool", "Insert Keys Tool"),
    ("latticeDeformKeyTool", 'MOD_LATTICE', None, "Lattice Deform Keys"),
    ("regionSelectKeyTool", 'FULLSCREEN_ENTER', "transform.resize", "Region Tool: Scale or move keys"),
    ("retimeKeyTool", 'TIME', "allset.retime_tool", "Retime Tool: scale and ripple keys"),
    "|",
    # Maya's curve sculpting group (the w / e / r key tools are keys and Edit > Transformation Tools items)
    ("sculptKeyGrabTool", 'MOUSE_LMB_DRAG', None, "Grab Keys Tool"),
    ("sculptKeySmoothTool", 'SMOOTHCURVE', "graph.smooth", "Smooth Keys"),
    ("sculptKeySmearTool", 'MOUSE_MMB_DRAG', None, "Smear Keys Tool"),
    ("sculptKeyReduceTool", 'MOD_DECIM', "graph.decimate", "Reduce Keys"),
    "|", "STATS", "|",
    ("frameAllButton", 'ZOOM_ALL', ("allset.graph_frame", {"mode": 'ALL'}), "Frame all"),
    ("frameRangeButton", 'PREVIEW_RANGE', "anim.scene_range_frame", "Frame playback range"),
    ("centerCurrentTimeButton", 'CENTER_ONLY', "allset.graph_center_time", "Scroll the view so the current time sits in the middle"),
    "|",
    ("autoTanButton", 'HANDLE_AUTOCLAMPED', _t("AUTO"), "Auto tangents"),
    ("autoeaseTanButton", 'HANDLE_AUTOCLAMPED', _t("AUTO"), "Auto Ease tangents"),
    ("automixTanButton", 'HANDLE_AUTOCLAMPED', _t("AUTO"), "Auto Mix tangents"),
    ("autocustomTanButton", 'HANDLE_AUTOCLAMPED', _t("AUTO"), "Auto Custom tangents"),
    ("splineTanButton", 'IPO_BEZIER', _t("SPLINE"), "Spline tangents"),
    ("clampedTanButton", 'HANDLE_AUTO', _t("CLAMPED"), "Clamped tangents"),
    ("linearTanButton", 'IPO_LINEAR', _t("LINEAR"), "Linear tangents"),
    ("flatTanButton", 'IPO_SINE', _t("FLAT"), "Flat tangents"),
    ("stepTanButton", 'IPO_CONSTANT', _t("STEPPED"), "Stepped tangents"),
    ("plateauTanButton", 'IPO_EASE_IN_OUT', _t("PLATEAU"), "Plateau tangents"),
    "|",
    ("graphEdDefaultTanInButton", 'TRIA_LEFT', ("submenu", "Tangents/Default In Tangent"), "Default in tangent"),
    ("graphEdDefaultTanOutButton", 'TRIA_RIGHT', ("submenu", "Tangents/Default Out Tangent"), "Default out tangent"),
    "|",
    ("bufferSnapButton", 'GHOST_ENABLED', "allset.buffer_snapshot", "Buffer curve snapshot"),
    ("bufferSwapButton", 'GHOST_DISABLED', "allset.buffer_swap", "Swap buffer curves"),
    "|",
    ("breakTanButton", 'HANDLE_FREE', _t("BREAK"), "Break tangents"),
    ("unifyTanButton", 'HANDLE_ALIGNED', _t("UNIFY"), "Unify tangents"),
    ("freeTanButton", 'UNLOCKED', ("allset.tangent_weight_lock", {"lock": False}), "Free tangent length"),
    ("lockTanButton", 'LOCKED', ("allset.tangent_weight_lock", {"lock": True}), "Lock tangent length"),
    "|",
    ("OutlineEdloadToggleButton", 'LINKED', ("prop", "window_manager.allset_auto_load", {}),
     "Auto load Graph Editor on selection"),
    ("OutlineEdreloadButton", 'FILE_REFRESH', ("allset.graph_list", {"action": "LOAD"}), "Load the selected objects"),
    "|",
    # Maya's drag constraint button: on = a middle drag moves freely, off = along the first direction
    ("switchConstrainedDragStateButton", 'VIEW_PAN', ("prop", "addon_prefs.graph_unconstrained_drag", {}),
     "Unconstrained drag"),
    ("timeSnapButton", 'SNAP_ON', ("prop", "tool_settings.use_snap_anim", {}), "Time snap"),
    ("valueSnapButton", 'SNAP_INCREMENT', None, "Value snap"),
    "|",
    ("graphEditorAbsoluteViewIconButton", 'FCURVE', ("prop", "space_data.use_normalization", {"value": False}),
     "Absolute view"),
    ("graphEditorStackedViewIconButton", 'ALIGN_JUSTIFY', ("allset.graph_view_mode", {"mode": "STACKED"}),
     "Stacked view"),
    ("graphEditorNormalizedViewIconButton", 'NORMALIZE_FCURVES',
     ("prop", "space_data.use_normalization", {"value": True}), "Normalized view"),
    ("renormalizeCurvesButton", 'RECOVER_LAST', ("prop", "space_data.use_auto_normalization", {}),
     "Re-normalize curves"),
    "|",
    ("curvesPreInfinityCycleButton", 'LOOP_BACK', _inf("PRE", "CYCLE"), "Pre-infinity cycle"),
    ("curvesPreInfinityCycleOffsetButton", 'FRAME_PREV', _inf("PRE", "CYCLE_OFFSET"), "Pre-infinity cycle with offset"),
    ("curvesPostInfinityCycleButton", 'LOOP_FORWARDS', _inf("POST", "CYCLE"), "Post-infinity cycle"),
    ("curvesPostInfinityCycleOffsetButton", 'FRAME_NEXT', _inf("POST", "CYCLE_OFFSET"),
     "Post-infinity cycle with offset"),
    "|",
    # Maya 2026: the editor buttons at the right end are Graph Editor / Dope Sheet / Time Editor
    # in both editors (Maya 2022: Trax Editor for the Time Editor)
    ("getGraphEditorButton", 'GRAPH', ("allset.open_editor", {"ui_type": 'FCURVES'}), "Open the Graph Editor"),
    ("getDopeSheetButton", 'ACTION', ("allset.open_editor", {"ui_type": 'DOPESHEET'}), "Open the Dope Sheet"),
    ("getCTEButton", 'NLA', ("allset.open_editor", {"ui_type": 'NLA_EDITOR'}), "Open the Time Editor"),
)

# Maya 2026 Dope Sheet tools: Select keys / Move Tool / Scale Tool / Insert Keys Tool (Maya 2022: select, move
# nearest picked key, insert)
DOPE_ICONS = (
    ("selectTool", 'RESTRICT_SELECT_OFF', None, "Select keys"),
    ("moveTool", 'ORIENTATION_CURSOR', ("transform.transform", {"mode": 'TIME_TRANSLATE'}), "Move Tool"),
    ("scaleTool", 'FULLSCREEN_ENTER', ("transform.transform", {"mode": 'TIME_SCALE'}), "Scale Tool"),
    ("insertKeyTool", 'KEY_HLT', "action.keyframe_insert", "Insert Keys Tool"),
    "|", "STATS", "|",
    ("frameAllButton", 'ZOOM_ALL', "action.view_all", "Frame all"),
    ("frameRangeButton", 'PREVIEW_RANGE', "anim.scene_range_frame", "Frame playback range"),
    ("centerCurrentTimeButton", 'TIME', "action.view_frame", "Scroll the view so the current time sits in the middle"),
    "|",
    ("hierButton", 'OUTLINER', ("prop", "window_manager.allset_hierarchy_below", {}), "Show the hierarchy below"),
    "|",
    ("OutlineEdloadToggleButton", 'LINKED', ("prop", "window_manager.allset_auto_load", {}),
     "Auto load Dope Sheet on selection"),
    ("OutlineEdreloadButton", 'FILE_REFRESH', ("allset.graph_list", {"action": "LOAD"}), "Load the selected objects"),
    "|",
    ("dopeSheetTimeSnapButton", 'SNAP_ON', ("prop", "tool_settings.use_snap_anim", {}), "Time snap"),
    "|",
    ("getGraphEditorButton", 'GRAPH', ("allset.open_editor", {"ui_type": 'FCURVES'}), "Open the Graph Editor"),
    ("getDopeSheetButton", 'ACTION', ("allset.open_editor", {"ui_type": 'DOPESHEET'}), "Open the Dope Sheet"),
    ("getCTEButton", 'NLA', ("allset.open_editor", {"ui_type": 'NLA_EDITOR'}), "Open the Time Editor"),
)

_UVE = "space_data.uv_editor"
UV_ICONS = (
    ("viewUVWireframeButton", 'SHADING_WIRE', ("prop", f"{_UVE}.show_faces", {"value": False}),
     "Display the UVs as wireframe"),
    ("viewShadeUVButton", 'SHADING_SOLID', ("prop", f"{_UVE}.show_faces", {"value": True}),
     "Shade the UV shells"),
    ("distortionButton", 'MOD_UVPROJECT', ("prop", f"{_UVE}.show_stretch", {}), "Display UV distortion"),
    "|",
    ("toggleTextureBorderButton", 'MOD_EDGESPLIT', ("prop", "window_manager.allset_uv_texture_borders", {}), "Display texture borders"),
    ("toggleShellBorderButton", 'MESH_DATA', ("prop", "window_manager.allset_uv_shell_borders", {}), "Display shell borders"),
    "|",
    ("gridDisplayButton", 'GRID', ("prop", "space_data.overlay.show_grid_background", {}), "Display the grid"),
    ("isolateViewSelectButton", 'HIDE_OFF', "allset.uv_isolate", "Isolate select"),
    "|",
    ("snapShotButton", 'IMAGE_DATA', "uv.export_layout", "UV snapshot"),
    "|",
    ("checkeredButton", 'TEXTURE', "allset.checker_toggle", "Checker tiling"),
    "IMAGE",
    ("imageChannelButton", 'IMAGE_RGB_ALPHA', ("channels", "space_data.display_channels", {}), "Image channels"),
    ("dimmerButton", 'LIGHT', None, "Dim the image"),
    "|", "UVMAP",
)

def _hsg(action):
    return ("allset.hs_graph", {"action": action})


# Maya Hypershade graph toolbar (Maya's control names + tooltips); actions run in the Hypershade's graph (ui/hypershade.py)
HS_GRAPH_ICONS = (
    ("showUpstreamButton", 'BACK', _hsg("UPSTREAM"), "Input connections"),
    ("showUpAndDownstreamButton", 'ARROW_LEFTRIGHT', _hsg("BOTH"), "Input and output connections"),
    ("showDownstreamButton", 'FORWARD', _hsg("DOWNSTREAM"), "Output connections"),
    "|",
    ("clearGraphButton", 'X', None, "Clear graph"),
    ("addSelectedButton", 'ADD', None, "Add selected nodes to graph"),
    ("removeSelectedButton", 'REMOVE', None, "Remove selected nodes from graph"),
    ("rearrangeGraphButton", 'NODETREE', None, "Rearrange graph"),
    ("graphMaterialsButton", 'MATERIAL', ("allset.hs_edit", {"action": "FROM_OBJECT"}),
     "Graph materials on selected objects"),
    "|",
    ("LODSimpleModeButton", 'COLLAPSEMENU', _hsg("COLLAPSE"), "Hide attributes on selected nodes"),
    ("LODConnectedModeButton", 'LINKED', _hsg("CONNECTED"), "Show connected attributes on selected nodes"),
    ("LODShowAllButton", 'ALIGN_JUSTIFY', _hsg("SHOW_ALL"), "Show primary attributes on selected nodes"),
    ("LODShowCustomButton", 'PRESET', None, "Show attributes from custom attribute view"),
    ("attrFilterToggleButton", 'FILTER', None, "Toggle the display of the attribute filter field on selected nodes"),
    ("swatchSizeToggleButton", 'IMAGE_PLANE', _hsg("PREVIEW"), "Toggle the icon swatch size of selected nodes to "
     "small/large"),
    "|",
    ("tabsRLCTButton", 'LOOP_BACK', None, "Restore last closed tab"),
)
ICONS = {GE: GRAPH_ICONS, DS: DOPE_ICONS, UV: UV_ICONS, "Hypershade": HS_GRAPH_ICONS}

# Notices of the greyed icon buttons (same form as ui/notices.NOTICES)
NOTICES = {
    "directKeyTool": ("Drag a key", "Blender's Graph Editor / Dope Sheet always move the key under the mouse when you "
                      "drag it: no tool to pick."),
    "selectTool": ("Click / box select", "Blender selects keys with a click or a box drag: no tool to pick."),
    "latticeDeformKeyTool": ("Scale (S)", "Blender has no lattice for keys: scale the selected keys with S."),
    "sculptKeyGrabTool": ("Move keys (G)", "Blender has no brush that drags keys: select keys and move them with G "
                          "(proportional editing for a soft pull)."),
    "sculptKeySmearTool": ("Move keys (G)", "Blender has no smear brush for keys: move the selected keys with G and "
                           "proportional editing."),
    "valueSnapButton": ("Snap", "Blender snaps keys to frames only (Edit > Snap, time snap button)."),
    "toggleTextureBorderButton": ("Seams", "Blender draws seams in the 3D View, not texture borders here."),
    "toggleShellBorderButton": ("Select Linked", "Blender doesn't draw shell borders in the UV Editor: select a "
                                "shell with Select > Select Linked."),
    "isolateViewSelectButton": ("Hide", "Blender isolates UVs by hiding the rest (H / Shift+H)."),
    "clearGraphButton": ("Pin", "Blender's graph always shows the whole material: pin another material to change "
                         "what it shows."),
    "addSelectedButton": ("Pin", "Blender's graph shows one material's whole network: nodes can't be added to it "
                          "from elsewhere."),
    "removeSelectedButton": ("Hide attributes", "Blender's graph shows the whole network: collapse nodes instead."),
    "rearrangeGraphButton": ("Move nodes", "Blender has no automatic node layout: move nodes with G."),
    "LODShowCustomButton": ("Not in Blender", "Blender has no custom attribute views on nodes."),
    "attrFilterToggleButton": ("Not in Blender", "Blender's nodes have no attribute filter field."),
    "tabsRLCTButton": ("Not in Blender", "Blender's graph has one tab (one material at a time)."),
    "dimmerButton": ("Image field", "Blender doesn't dim the image: pick no image in the header field to hide it."),
}


def _icon_spec(editor, key):
    return next((it for it in ICONS[editor] if isinstance(it, tuple) and it[0] == key), None)


def _submenu(editor, sub):
    return menu_sets.SUBMENU_IDS.get(f"{editor}/{sub}")


def draw_icons(layout, context, editor):
    row = layout.row(align=True)
    for it in ICONS[editor]:
        if it == "|":
            row.separator()
            row = layout.row(align=True)
        elif it == "STATS":
            scene = context.scene
            sub = layout.row(align=True)
            sub.label(text="Stats")
            col = sub.row(align=True)
            col.ui_units_x = 3.5
            col.prop(scene, "allset_key_time", text="")
            col = sub.row(align=True)
            col.ui_units_x = 3.5
            col.prop(scene, "allset_key_value", text="")
        elif it == "IMAGE":
            sima = context.space_data
            layout.template_ID(sima, "image", new="image.new", open="image.open")
        elif it == "UVMAP":
            ob = context.edit_object
            if ob is not None and ob.type == 'MESH' and ob.data.uv_layers.active is not None:
                sub = layout.row()
                sub.ui_units_x = 5
                sub.prop(ob.data.uv_layers.active, "name", text="", icon='GROUP_UVS')
        else:
            _draw_icon(row, context, editor, it)


def _draw_icon(row, context, editor, it):
    key, icon, action, _tip = it
    if action is None:
        row.operator(ALLSET_OT_editor_icon_unavailable.bl_idname, text="", icon=icon).key = f"{editor}|{key}"
        return
    if action[0] == "submenu":
        idname = _submenu(editor, action[1])
        if idname:
            row.menu(idname, text="", icon=icon)
        return
    if action[0] in ("prop", "channels"):
        owner, attr = menu_sets.prop_owner(context, action[1])
        if owner is None:
            row.operator(ALLSET_OT_editor_icon_unavailable.bl_idname, text="", icon=icon).key = f"{editor}|{key}"
            return
        if action[0] == "channels":
            row.prop(owner, attr, text="", icon_only=True)
            return
        props = action[2]
        if "value" not in props:
            row.prop(owner, attr, text="", icon=icon, toggle=True)
            return
        current = getattr(owner, attr)
        value = props["value"]
        on = abs(current - value) < 1e-6 if isinstance(value, float) else current == value
        op = row.operator(menu_sets.ALLSET_OT_menu_set_value.bl_idname, text="", icon=icon, depress=on)
        op.target, op.value = action[1], repr(value)
        return
    on = _toggle_state(context, key)
    row.operator(ALLSET_OT_editor_icon.bl_idname, text="", icon=icon, depress=bool(on)).key = f"{editor}|{key}"


def _toggle_state(context, key):
    """Pressed state of icon buttons that run a toggle operator (Maya iconTextCheckBox), None otherwise."""
    if key == "checkeredButton":
        from ..operators import menu_items
        return menu_items.checker_on(context)
    return None


class ALLSET_OT_editor_icon(bpy.types.Operator):
    """Maya editor icon-row button"""
    bl_idname = "allset.editor_icon"
    bl_label = "Editor Button"
    bl_options = {'INTERNAL'}

    key: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        editor, _sep, key = props.key.partition("|")
        it = _icon_spec(editor, key) if editor in ICONS else None
        if it is None:
            return ""
        s = menu_map.normalize(it[2])
        target = f"\nBlender: {s[1]}" if s and s[0] in ("op", "v3d") else ""
        return f"Maya: {it[3]}{target}"

    def execute(self, context):
        editor, _sep, key = self.key.partition("|")
        it = _icon_spec(editor, key) if editor in ICONS else None
        if it is None or it[2] is None:
            return {'CANCELLED'}
        from ..marking.modal import run_action
        try:
            run_action(context, it[2])
        except RuntimeError as ex:
            self.report({'WARNING'}, str(ex).strip().splitlines()[-1])
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_editor_icon_unavailable(bpy.types.Operator):
    """Maya editor button without a Blender counterpart (always greyed out)"""
    bl_idname = "allset.editor_icon_unavailable"
    bl_label = "Not Available"
    bl_options = {'INTERNAL'}

    key: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return False

    @classmethod
    def description(cls, context, props):
        editor, _sep, key = props.key.partition("|")
        it = _icon_spec(editor, key) if editor in ICONS else None
        tip = it[3] if it else key
        sub, line = NOTICES.get(key, ("", "Not in this Blender editor."))
        return f"Maya: {tip} (greyed)  →  {sub}\n{line}" if sub else f"Maya: {tip} (greyed)\n{line}"

    def execute(self, context):
        return {'CANCELLED'}


# --- Stats fields: the selected key's time / value (Maya Graph Editor / Dope Sheet icon row) -----------------------

def _kind(fc):
    tail = fc.data_path.rsplit(".", 1)[-1]
    return "LENGTH" if tail in {"location", "delta_location"} else \
        "ROTATION" if tail in {"rotation_euler", "delta_rotation_euler"} else "NONE"


def selected_points(context):
    """[(fcurve, keyframe point)] selected in the editor the context belongs to (Graph Editor / Dope Sheet)."""
    out = []
    for fc in getattr(context, "editable_fcurves", None) or ():
        out += [(fc, kp) for kp in fc.keyframe_points if kp.select_control_point]
    return out


def _stats_get(field):
    def get(scene):
        from . import cb_entry
        pts = selected_points(bpy.context)
        if not pts:
            return ""
        values = {round(kp.co.x if field == "time" else kp.co.y, 6) for _fc, kp in pts}
        if len(values) > 1:
            return "-"          # Maya shows a blank field for several values; "-" = mixed
        fc, kp = pts[0]
        if field == "time":
            return cb_entry.fmt_number(kp.co.x)
        return cb_entry.format_value(kp.co.y, _kind(fc), scene)
    return get


def _stats_set(field):
    def set_(scene, text):
        from . import cb_entry
        for fc, kp in selected_points(bpy.context):
            old = kp.co.x if field == "time" else kp.co.y
            try:
                new = cb_entry.parse_entry(text, old, "NONE" if field == "time" else _kind(fc), scene)
            except (ValueError, TypeError):
                return
            d = new - old
            axis = 0 if field == "time" else 1
            for v in (kp.co, kp.handle_left, kp.handle_right):
                v[axis] += d
            fc.update()
    return set_


# --- Graph Editor channel list (Maya outliner pane: node rows, "Translate X" rows) --------------------------------
# Maya lists DAG nodes with their animated attributes under them: objects, joints (= pose bones;
# their curves live on the armature object as ``pose.bones["joint1"].location``) and the
# blendShape node of a mesh (= its shape-key datablock, ``rig_tools`` names it blendShapeN; its curves are the Key
# ID's ``key_blocks["smile"].value``, one row per target, Maya's attribute = the target name). #96.

MAYA_ATTR = {"location": "Translate", "rotation_euler": "Rotate", "scale": "Scale", "rotation_quaternion": "Rotate",
             "delta_location": "Delta Translate", "delta_rotation_euler": "Delta Rotate", "delta_scale": "Delta Scale"}
# One-value attributes: Maya visibility = hide_viewport; hide_render has no Maya transform attribute,
# the closest is the shape's render stat Primary Visibility.
MAYA_SCALAR = {"hide_render": "Primary Visibility"}
AXES = "XYZ"
# Attribute name colours in the Graph Editor outliner, like Maya (Translate X red,
# Translate Y green; Z blue by the same rule as the manipulator / theme axis colours), other attributes light grey.
AXIS_COLOR = ((0.9, 0.25, 0.25, 1.0), (0.25, 0.85, 0.25, 1.0), (0.35, 0.55, 1.0, 1.0))
TEXT = (0.85, 0.85, 0.85, 1.0)
BACK = (0.267, 0.267, 0.267, 1.0)        # outliner pane #444444
SELECT = (0.322, 0.522, 0.651, 1.0)      # selection blue #5285a6 (kit-drawn pane: fixed colours, any theme)
THUMB = (0.36, 0.36, 0.36, 1.0)          # Maya scroll bar thumb (right of the rows)
_expanded = {}                           # node key -> bool (Maya shows attributes expanded)
_scroll = {}                             # area pointer -> first row shown
# Rows the user picked in this outliner (Maya highlights only those, not every attribute of a selected node), valid
# while the scene selection is the one they were picked under.
_picked = {"ids": set(), "sig": None}
_BONES = 'pose.bones["'
_SHAPES = 'key_blocks["'


def _maya_names():
    """Attribute -> Maya name: the Channel Box's names first (one table), then MAYA_ATTR / MAYA_SCALAR."""
    from . import channel_box
    names, scalar = dict(MAYA_ATTR), dict(MAYA_SCALAR)
    for _key, label, path, idx, _kind in channel_box.MAIN:
        if idx < 0:
            scalar[path] = label
        else:
            names.setdefault(path, label.rsplit(" ", 1)[0])
    return names, scalar


def attr_label(fc):
    """Maya name of an F-curve's attribute: "Translate X", "Visibility", custom properties and blend shape targets
    by name."""
    path, idx = fc.data_path, fc.array_index
    if path.startswith(_SHAPES) and path.endswith('"].value'):
        return bpy.utils.unescape_identifier(path[len(_SHAPES):-len('"].value')])
    if path.endswith("]") and '["' in path:
        return path.rsplit('["', 1)[1].rstrip('"]')
    tail = path.rsplit(".", 1)[-1]
    names, scalar = _maya_names()
    if tail in scalar:
        return scalar[tail]
    if tail in names:
        name = names[tail]
        if tail == "rotation_quaternion":
            return f"{name} {'WXYZ'[idx]}"
        return f"{name} {AXES[idx]}" if idx < 3 else name
    return tail.replace("_", " ").title() + (f" {AXES[idx]}" if idx < 3 and fc.array_index else "")


def attr_color(fc):
    tail = fc.data_path.rsplit(".", 1)[-1]
    if tail in MAYA_ATTR and tail != "rotation_quaternion" and fc.array_index < 3:
        return AXIS_COLOR[fc.array_index]
    return TEXT


def object_curves(ob):
    """The object's own F-curves (its action's slot), Blender order."""
    from .. import compat
    return compat.id_fcurves(ob)


def data_curves(ob):
    """Curves of the object's data-block (Maya shape node attributes: a light's intensity, a camera's focal length):
    Maya's node row draws its shape's animated channels too. Shape keys have their own row."""
    from .. import compat
    data = getattr(ob, "data", None)
    return compat.id_fcurves(data) if isinstance(data, bpy.types.ID) else []


def shape_key(ob):
    """The object's shape-key datablock (Maya blendShape node) when it is animated, else None."""
    from .. import compat
    key = getattr(getattr(ob, "data", None), "shape_keys", None)
    return key if key is not None and compat.id_fcurves(key) else None


def _bone_name(path):
    """``pose.bones["joint1"].location`` -> "joint1" (None for other paths)."""
    if not path.startswith(_BONES):
        return None
    end = path.find('"]', len(_BONES))
    while end > 0 and path[end - 1] == "\\":      # an escaped quote inside the name
        end = path.find('"]', end + 1)
    return bpy.utils.unescape_identifier(path[len(_BONES):end]) if end > 0 else None


def split_object_curves(ob):
    """(the object's own curves, [(pose bone, its curves)] in the armature's bone order): joints are Maya nodes."""
    own, by_bone = [], {}
    bones = ob.pose.bones if ob.type == 'ARMATURE' and ob.pose is not None else None
    for fc in object_curves(ob):
        name = _bone_name(fc.data_path) if bones is not None else None
        pb = bones.get(name) if name is not None else None
        if pb is None:
            own.append(fc)
        else:
            by_bone.setdefault(pb.name, []).append(fc)
    return own, [(pb, by_bone[pb.name]) for pb in (bones or ()) if pb.name in by_bone]


def character_curves(scene, ks):
    """F-curves a character set's members (its own and its subcharacters' attributes) have (#104)."""
    from .. import compat
    from ..operators import character_sets
    out = []
    for p in character_sets.all_paths(scene, ks):
        if p.id is None:
            continue
        for fc in compat.id_fcurves(p.id):
            if fc.data_path == p.data_path and (p.use_entire_array or fc.array_index == p.array_index)                     and fc not in out:
                out.append(fc)
    return out


def node_name(node):
    return node.bl_label if isinstance(node, bpy.types.KeyingSet) else node.name


def node_curves(node):
    """F-curves of one outliner node: an object (without its joints'), a pose bone, a shape-key datablock or a
    character set."""
    from .. import compat
    if isinstance(node, bpy.types.KeyingSet):
        return character_curves(bpy.context.scene, node)
    if isinstance(node, bpy.types.Collection):       # a kit set (Show > Objects > Sets)
        from ..operators import sets
        return [fc for ob in sets.members(node, bpy.context.scene) for fc in maya_order(split_object_curves(ob)[0])]
    if isinstance(node, bpy.types.PoseBone):
        return dict((pb.name, c) for pb, c in split_object_curves(node.id_data)[1]).get(node.name, [])
    if isinstance(node, bpy.types.Key):
        return compat.id_fcurves(node)
    return split_object_curves(node)[0]


def node_key(node):
    """Identity of a node row (``_expanded`` / picks): object name, ("JOINT", armature, bone), ("SHAPES", key)."""
    if isinstance(node, bpy.types.PoseBone):
        return ("JOINT", node.id_data.name, node.name)
    if isinstance(node, bpy.types.Key):
        return ("SHAPES", node.name)
    if isinstance(node, bpy.types.KeyingSet):
        return ("CHARACTER", node.bl_label)
    if isinstance(node, bpy.types.Collection):
        return ("SET", node.name)
    return node.name


def row_id(row):
    kind, node, fc = row
    if kind in graph_layers.KINDS:
        return graph_layers.row_id(row)
    if kind in ("UP_SDK", "UP_CURVE"):       # Show Upstream Curves rows: one per label under the node
        return (node_key(node), kind, fc.data_path, fc.array_index, _up_label.get((kind, fc.as_pointer()), ""))
    return node_key(node) if kind != "ATTR" else (node_key(node), fc.data_path, fc.array_index)


def listed_objects(context, space):
    """Objects the Maya list shows as rows: the loaded list, else the selection with Auto Load (keyed or not, step
    281), else all animated ones (also by shape keys / data-block curves); plus Hierarchy Below (Dope Sheet), narrowed by Show > Objects, by name. Driven
    channels count like keyed ones (Maya lists a driven-key / expression
    channel)."""
    ds = space.dopesheet
    base = row_objects(context, space)
    if base is not None:
        # #192: Maya lists every loaded / auto-loaded node, keyed or not (a bare node row until it is keyed)
        base = set(base)
        obs = [ob for ob in context.scene.objects if ob in base]
    else:
        obs = [ob for ob in context.scene.objects
               if (ob.animation_data and (ob.animation_data.action or ob.animation_data.drivers))
               or shape_key(ob) is not None or data_curves(ob)]
    if not ds.show_hidden:
        obs = [ob for ob in obs if ob.visible_get()]
    return sorted(obs, key=lambda o: o.name)


# --- List > Load / Add Selected Objects, Auto Load, Pin Channel, Show filters (#110) --------------------
# Maya 2022: Auto Load Selected Objects is on by
# default and the list follows the selection; unchecking it freezes the list shown then; Load / Add Selected Objects
# are greyed while Auto Load is on (the kit's poll fails) and replace / append the frozen list (nothing selected =
# empty list), Auto Load stays off. Maya's first Add right after a Load drops the loaded objects — the kit appends
# (looks like a Maya bug). Pin Channel pins the highlighted rows (a node row = all its channels; nothing
# highlighted = nothing pinned); pinned channels stay listed under their node, below the listed nodes. Show >
# Attributes / Objects check items list only the checked kinds (several = union). Show Upstream Curves (on by default)
# lists a driven-key channel's SDK curve and the driver's own curve under it. Pins / filters are one state for every
# editor (Maya keeps pins per editor).
#
# Blender: a Graph Editor / Dope Sheet draws the objects its own filters let through (Only Show Selected, the
# Collection filter ``dopesheet.filter_collection``). A list Blender's selection filter can't express (loaded, plus
# pinned owners / hierarchy / upstream curve owners / character members, only IK handles) is a kit collection
# (ID prop ``allset_list``, no scene, fake user: one per editor, saved with the file like Maya's panel state) set as
# that editor's Collection filter, Only Show Selected off; its members follow the rules from graph_view's 0.25 s
# timer (``sync``). Curves Blender then draws that the Maya list doesn't show (unpinned curves of a pinned curve's
# node, joints not loaded, attributes filtered out) are hidden (``fc.hide``) and shown again when they're listed
# (``_kit_hidden``). Driven channels (driver curves: Maya driven key / expression) are listed like keyed ones: Blender
# draws drivers only in the Graph Editor's Drivers mode, so those rows have no curve in F-Curve mode.

LIST_MARK = "allset_list"      # kit list collection marker
LOADED = "allset_loaded"       # loaded object names (absent = no loaded list)
BONES = "allset_bones"         # loaded joints "armature\tbone" (an armature without entries = all its joints)
AUTO = "allset_auto"           # Auto Load state while Only Show Selected is off for the kit list
ATTR_FILTERS = ("hidden", "anim_curve", "expression", "driven_key", "user_defined")
_pinned = set()                # ATTR row ids of pinned channels (Maya Pin Channel; session state)
_kit_hidden = set()            # (id kind, id name, data path, index) of curves the kit hid


def _ds(space):
    return getattr(space, "dopesheet", None)


def _is_dope_space(space):
    return getattr(space, "type", "") == 'DOPESHEET_EDITOR'


def kit_list(space):
    """The editor's kit list collection, or None (Blender's own filters)."""
    coll = getattr(_ds(space), "filter_collection", None)
    return coll if coll is not None and coll.get(LIST_MARK) else None


def loaded_names(space):
    coll = kit_list(space)
    names = coll.get(LOADED) if coll is not None else None
    return None if names is None else list(names)


def auto_load(space):
    """Maya Auto Load Selected Objects: Blender's Only Show Selected, or the kit list's remembered state."""
    ds = _ds(space)
    if ds is None:
        return False
    if ds.show_only_selected:
        return True
    coll = kit_list(space)
    return bool(coll is not None and coll.get(LOADED) is None and coll.get(AUTO, False))


def _wm_flag(name):
    return bool(getattr(bpy.context.window_manager, name, False))


def attr_filters():
    """The checked Show > Attributes filters (Maya: none checked = every animated attribute)."""
    return {f for f in ATTR_FILTERS if _wm_flag("allset_attr_" + f)}


def _selected_objects(context):
    return [ob for ob in context.scene.objects if ob.select_get()]


def _descendants(obs):
    out, seen = [], set()
    for ob in obs:
        for child in ob.children_recursive:
            if child not in seen:
                seen.add(child)
                out.append(child)
    return out


def _path_index(path):
    """``location[0]`` -> ("location", 0); other paths keep index 0 (custom properties end in ``"]``)."""
    m = re.match(r"^(.*)\[(\d+)\]$", path)
    return (m.group(1), int(m.group(2))) if m else (path, 0)


def sdk_target(fc):
    """(driver ID, its data path, index) a kit SDK driver curve reads (variable ``sdk``), else None."""
    from ..operators import driven_key
    if isinstance(fc.id_data, bpy.types.Action):
        return None
    var = next((v for v in fc.driver.variables if v.name == driven_key.VAR), None)
    if var is None or not var.targets or var.targets[0].id is None:
        return None
    t = var.targets[0]
    path, idx = _path_index(t.data_path)
    return t.id, path, idx


def upstream_rows(node, fc):
    """Maya Show Upstream Curves rows under a driven-key channel: the SDK curve
    labelled by its input ("> pCube1.User A") = the driver curve itself, then the driver attribute's own anim curve
    ("pCube1.User A") when it is keyed. [(kind, fcurve, label)]."""
    tgt = sdk_target(fc)
    if tgt is None:
        return []
    owner, path, idx = tgt
    label = attr_label(types.SimpleNamespace(data_path=path, array_index=idx))
    bone = _bone_name(path)
    name = f"{bone if bone is not None else owner.name}.{label}"
    out = [("UP_SDK", fc, "> " + name)]
    own = next((c for c in object_curves(owner) if c.data_path == path and c.array_index == idx), None)
    if own is not None:
        out.append(("UP_CURVE", own, name))
    return out


def _object_kinds():
    """The checked kit Show > Objects items (Maya: checked = only nodes of those types)."""
    return {k for k, flag in (("ik", "allset_show_ik_handles"), ("sets", "allset_show_sets"),
                              ("characters", "allset_show_characters")) if _wm_flag(flag)}


def row_objects(context, space):
    """Objects the Maya list is made of (None = every object): loaded, else selected with Auto Load, plus Hierarchy
    Below (Dope Sheet). A checked Show > Objects item lists only nodes of that type:
    IkHandles keeps the IK handles (kit IK handles = IK constraint targets, operators/by_type.py), Sets / Characters
    alone list no objects (their nodes come from ``listed_nodes``)."""
    names = loaded_names(space)
    if names is not None:
        obs = [ob for ob in (bpy.data.objects.get(n) for n in names) if ob is not None]
    elif auto_load(space):
        obs = _selected_objects(context)
    else:
        obs = None
    if obs is not None and _is_dope_space(space) and _wm_flag("allset_hierarchy_below"):
        # Maya shows the descendants' keys in the object's own rows without listing them; Blender's C Dope Sheet
        # list can't merge another object's keys into a row, so the kit lists the descendants
        obs = obs + [o for o in _descendants(obs) if o not in obs]
    kinds = _object_kinds()
    if "ik" in kinds:
        from ..operators import by_type
        handles = by_type.ik_handles(context.scene)
        obs = handles if obs is None else [o for o in obs if o in handles]
    elif kinds:
        obs = []
    flt = attr_filters()
    if flt and _is_dope_space(space):
        # Blender's Dope Sheet channel list can't drop single channels (fc.hide is Graph Editor only, drivers are
        # no Dope Sheet channels): the attribute filters keep the objects with a matching attribute
        obs = [o for o in (context.scene.objects if obs is None else obs) if _has_attr(o, flt)]
    if obs is not None:
        in_scene = set(context.scene.objects)
        obs = [o for o in obs if o in in_scene]
    return obs


def _has_attr(ob, flt):
    own, joints = split_object_curves(ob)
    if filter_curves(ob, own + node_drivers(ob), flt):
        return True
    if any(filter_curves(pb, curves + node_drivers(pb), flt) for pb, curves in joints):
        return True
    key = shape_key(ob)
    return bool(key is not None and filter_curves(key, object_curves(key) + node_drivers(key), flt))


def _character_members(context):
    from ..operators import character_sets
    out = []
    for ks in character_sets.characters(context.scene):
        for p in character_sets.all_paths(context.scene, ks):
            if isinstance(p.id, bpy.types.Object) and p.id not in out:
                out.append(p.id)
    return out


def drawn_objects(context, space):
    """Objects Blender must draw for this editor (None = every object): the list's objects plus the owners of
    pinned curves, of upstream curves (Graph Editor) and the members of listed character nodes (a set node has no
    channels)."""
    obs = row_objects(context, space)
    if obs is None:
        return None
    extra = []
    if not _is_dope_space(space):
        extra += [n.id_data if isinstance(n, bpy.types.PoseBone) else n for n in _pinned_nodes()
                  if isinstance(n, (bpy.types.Object, bpy.types.PoseBone))]
        extra += [owner for owner, _fc in upstream_curves(context, space) if isinstance(owner, bpy.types.Object)]
    if _object_kinds() & {"sets", "characters"}:
        extra += _character_members(context)
    in_scene = set(context.scene.objects)
    return obs + [o for o in dict.fromkeys(extra) if o not in obs and o in in_scene]


def needs_kit_list(context, space):
    """Can Blender's own filters show this list (all, or exactly the selection)? Else the kit list."""
    if loaded_names(space) is not None or "ik" in _object_kinds():
        return True
    obs = drawn_objects(context, space)
    return obs is not None and (not auto_load(space) or set(obs) != set(_selected_objects(context)))


def _new_list():
    coll = bpy.data.collections.new(".AllsetList")
    coll.use_fake_user = True          # in no scene: kept in the file like Maya's editor panel state
    coll[LIST_MARK] = 1
    return coll


def _drop_list(coll):
    if coll is not None and coll.get(LIST_MARK) and coll.users <= 1:
        bpy.data.collections.remove(coll)


def sync_space(context, space):
    """Put Blender's filters of one Graph Editor / Dope Sheet in step with its Maya list; True when changed."""
    ds = _ds(space)
    if ds is None:
        return False
    coll = kit_list(space)
    if coll is None and getattr(ds, "filter_collection", None) is not None:
        return False                   # the user's own Collection filter: left alone
    if not needs_kit_list(context, space):
        if coll is None:
            return False
        auto = coll.get(LOADED) is None and bool(coll.get(AUTO, False))
        ds.filter_collection = None
        ds.show_only_selected = auto
        _drop_list(coll)
        return True
    changed = False
    if coll is None:
        auto = bool(ds.show_only_selected)
        coll = _new_list()
        coll[AUTO] = auto
        ds.filter_collection = coll
        changed = True
    if ds.show_only_selected:
        if coll.get(LOADED) is None:
            coll[AUTO] = True
        ds.show_only_selected = False
        changed = True
    obs = drawn_objects(context, space)
    want = set(context.scene.objects if obs is None else obs)
    have = set(coll.objects)
    for ob in have - want:
        coll.objects.unlink(ob)
    for ob in want - have:
        coll.objects.link(ob)
    return changed or want != have


def set_auto_load(context, space, on):
    """Maya Auto Load on: the list follows the selection (a loaded list is dropped); off: the list shown now is
    frozen (Maya's locked copy: selecting other objects no longer changes it)."""
    ds = _ds(space)
    if ds is None:
        return
    if not on:
        if auto_load(space):
            load_selected(context, space)
        return
    coll = kit_list(space)
    if coll is not None:
        if LOADED in coll:
            del coll[LOADED]
        if BONES in coll:
            del coll[BONES]
        coll[AUTO] = bool(on)
        ds.show_only_selected = False
    else:
        ds.show_only_selected = bool(on)
    sync_space(context, space)


def _selected_bones(context):
    from . import channel_box
    out = []
    for ob in _selected_objects(context):
        if ob.type == 'ARMATURE' and ob.mode == 'POSE' and ob.pose is not None:
            out += [f"{ob.name}\t{pb.name}" for pb in ob.pose.bones if channel_box.bone_selected(pb)]
    return out


def load_selected(context, space, add=False):
    """Maya List > Load Selected Objects (``add`` = Add Selected Objects): a fixed list, Auto Load off."""
    ds = _ds(space)
    if ds is None:
        return []
    names = loaded_names(space)
    bones = list(kit_list(space).get(BONES, ())) if names is not None else []
    if add and names is None:          # adding to the list shown now
        names = [ob.name for ob in listed_objects(context, space)]
    if not add or names is None:
        names, bones = [], []
    sel = _selected_objects(context)
    names += [ob.name for ob in sel if ob.name not in names]
    bones += [b for b in _selected_bones(context) if b not in bones]
    if not add:
        bones = _selected_bones(context)
    coll = kit_list(space) or _new_list()
    coll[LOADED] = names
    coll[BONES] = bones
    coll[AUTO] = False
    ds.filter_collection = coll
    ds.show_only_selected = False
    sync_space(context, space)
    return names


def _bone_loaded(space, pb):
    """Is this joint in the loaded list (an armature loaded without joints: all of them)?"""
    coll = kit_list(space)
    if coll is None or coll.get(LOADED) is None:
        return True
    bones = list(coll.get(BONES, ()))
    arm = pb.id_data.name
    mine = [b for b in bones if b.split("\t", 1)[0] == arm]
    return not mine or f"{arm}\t{pb.name}" in mine


def _node_of_key(key):
    """Node of a row id's node key (objects / joints / blendShape nodes), None when gone."""
    if isinstance(key, str):
        return bpy.data.objects.get(key)
    if key[0] == "JOINT":
        arm = bpy.data.objects.get(key[1])
        return arm.pose.bones.get(key[2]) if arm is not None and arm.pose is not None else None
    if key[0] == "SHAPES":
        return bpy.data.shape_keys.get(key[1])
    return None


def _in_scene(node):
    ob = node.id_data if isinstance(node, bpy.types.PoseBone) else node
    return not isinstance(ob, bpy.types.Object) or ob.name in bpy.context.scene.objects


def _pinned_nodes():
    out = []
    for key in dict.fromkeys(rid[0] for rid in _pinned):
        node = _node_of_key(key)
        if node is not None and _in_scene(node):
            out.append(node)
    return out


def is_pinned(node, fc):
    return (node_key(node), fc.data_path, fc.array_index) in _pinned


# Show > Attributes kinds of a curve (Maya attribute filters): keyed curves are "Driven by Anim Curve", kit SDK
# drivers (variable ``sdk``) "Driven by Driven Key", scripted drivers "Driven by Expression", custom properties
# "User Defined", Channel Box hidden channels (Channel Control / Hide Selected, ``channel_box.HIDDEN_PROP``) "Hidden".

def _channel_tail(node, fc):
    path = fc.data_path
    if isinstance(node, bpy.types.PoseBone):
        head = node.path_from_id()
        path = path[len(head):].lstrip(".") if path.startswith(head) else path
    return path


def is_driver(fc):
    """A driver curve (Maya: an attribute driven by a driven key / expression), not an action's keyed curve."""
    return not isinstance(fc.id_data, bpy.types.Action)


def _character_routed(node):
    """{(data path, index)} of the node's channels that are character members (index -1 = whole array): Maya routes
    a character member's curve through the character node, so it is not "Driven by Anim Curve"."""
    from ..operators import character_sets
    owner = node.id_data if isinstance(node, bpy.types.PoseBone) else node
    scene = bpy.context.scene
    out = set()
    for ks in character_sets.characters(scene):
        for p in ks.paths:
            if p.id == owner:
                out.add((p.data_path, -1 if p.use_entire_array else p.array_index))
    return out


def curve_kinds(node, fc, driver=None, routed=()):
    """Maya Show > Attributes kinds of a curve: a keyed curve is "anim_curve" unless it is
    a character member (``routed``); a kit SDK driver is "driven_key" and "anim_curve" (its input is the SDK anim
    curve), another scripted driver "expression"."""
    from . import channel_box
    kinds = set()
    if is_driver(fc) if driver is None else driver:
        from ..operators import driven_key
        if any(v.name == driven_key.VAR for v in fc.driver.variables):
            kinds |= {"driven_key", "anim_curve"}
        elif fc.driver.type == 'SCRIPTED':
            kinds.add("expression")
    elif (fc.data_path, fc.array_index) not in routed and (fc.data_path, -1) not in routed:
        kinds.add("anim_curve")
    tail = _channel_tail(node, fc)
    key = None
    if tail.startswith('["') and tail.endswith('"]'):
        kinds.add("user_defined")
        key = channel_box.CUSTOM_PREFIX + bpy.utils.unescape_identifier(tail[2:-2])
    else:
        key = next((c[0] for c in channel_box.MAIN if c[2] == tail and (c[3] < 0 or c[3] == fc.array_index)), None)
    owner = node if isinstance(node, (bpy.types.Object, bpy.types.PoseBone)) else None
    if key is not None and owner is not None and channel_box.is_hidden(owner, key):
        kinds.add("hidden")
    return kinds


def node_drivers(node):
    """Driver curves of a node (Maya attributes driven by an expression / driven key)."""
    if isinstance(node, bpy.types.KeyingSet):
        return []
    owner = node.id_data if isinstance(node, bpy.types.PoseBone) else node
    ad = getattr(owner, "animation_data", None)
    if ad is None:
        return []
    out = []
    for fc in ad.drivers:
        name = _bone_name(fc.data_path) if isinstance(owner, bpy.types.Object) else None
        if isinstance(node, bpy.types.PoseBone):
            if name == node.name:
                out.append(fc)
        elif name is None or owner.type != 'ARMATURE':
            out.append(fc)
    return out


def filter_curves(node, curves, flt=None):
    """The node's curves (keyed and driver curves) the checked attribute filters list: none checked = all, several
    = their union (Maya); pinned curves always."""
    flt = attr_filters() if flt is None else flt
    if not flt:
        return list(curves)
    routed = _character_routed(node) if "anim_curve" in flt and not isinstance(node, bpy.types.KeyingSet) else ()
    return [fc for fc in curves if is_pinned(node, fc) or curve_kinds(node, fc, routed=routed) & flt]


# Maya lists a node's attributes in its attribute order (translate, rotate, scale, visibility, then the rest, e.g.
# custom attributes / blend shape targets), not in the order they were keyed.
ATTR_ORDER = ("location", "rotation_euler", "rotation_quaternion", "scale", "hide_viewport", "hide_render")


def maya_order(curves):
    def key(fc):
        tail = fc.data_path.rsplit(".", 1)[-1]
        return (ATTR_ORDER.index(tail) if tail in ATTR_ORDER else len(ATTR_ORDER), fc.array_index)
    return sorted(curves, key=key)      # stable: other attributes keep Blender's order


def listed_nodes(context, space):
    """[(kind, node, curves)]: per listed object its own row (also without curves, a bare node row like Maya;
    its curves include its data-block's = Maya shape channels), its joints (with Only
    Show Selected only the selected ones, in any mode: Blender's Graph Editor draws no curves of unselected bones
    then, gui_step150_outliner), its blendShape node. A node's curves are its keyed and its driven
    (driver) channels: Maya lists a driven-key / expression channel too. A checked Show >
    Objects > Sets / Characters lists only those nodes: kit sets as rows without channels (a Maya set row has
    none), character sets (a character is a set) with their member channels; kit sets and characters can't be
    selected like Maya's, so every one is listed."""
    from . import channel_box
    out = []
    flt = attr_filters()
    kinds = _object_kinds()
    if kinds & {"sets", "characters"}:
        from ..operators import character_sets
        for ks in character_sets.characters(context.scene):
            curves = filter_curves(ks, character_curves(context.scene, ks), flt)
            if curves:
                out.append(("CHARACTER", ks, curves))
    if "sets" in kinds:
        from ..operators import sets
        out += [("SET", coll, []) for coll in sets.all_sets()]
    auto = auto_load(space)

    def add(kind, node, curves):
        curves = filter_curves(node, curves, flt)
        if curves:
            out.append((kind, node, curves))
    for ob in listed_objects(context, space):
        own, joints = split_object_curves(ob)
        start = len(out)
        add("OBJECT", ob, maya_order(own + node_drivers(ob)) + data_curves(ob))
        for pb, curves in joints:
            if auto and not channel_box.bone_selected(pb) or not _bone_loaded(space, pb):
                continue
            add("JOINT", pb, maya_order(curves + node_drivers(pb)))
        key = shape_key(ob)
        if key is not None:
            add("SHAPES", key, object_curves(key) + node_drivers(key))
        if len(out) == start and not flt and not joints:      # keyed joints: the joints are the Maya nodes
            out.append(("OBJECT", ob, []))     # Maya lists the node before it has keys (a bare node row)
    # pinned channels stay listed under their node whatever the list / selection is now, the node below the listed
    # ones (Maya Pin Channel)
    shown = {node_key(n) for _k, n, _c in out}
    for node in _pinned_nodes():
        if node_key(node) in shown:
            continue
        curves = [fc for fc in node_curves(node) if is_pinned(node, fc)]
        if curves:
            kind = "JOINT" if isinstance(node, bpy.types.PoseBone) else \
                "SHAPES" if isinstance(node, bpy.types.Key) else "OBJECT"
            out.append((kind, node, curves))
    return out


def rows(context, space):
    """[(kind, node, fcurve)] of the Maya list: a node row (OBJECT / JOINT / SHAPES / CHARACTER / SET), then its
    ATTR rows while expanded; under a driven-key ATTR row its Show Upstream Curves rows (UP_SDK, UP_CURVE)."""
    out = []
    flt = (space.dopesheet.filter_text or "").lower()
    up = shows_upstream(space)
    for kind, node, curves in listed_nodes(context, space):
        out.append((kind, node, None))
        if _expanded.get(node_key(node), True):
            for fc in curves:
                if flt and flt not in fc.data_path.lower() and flt not in attr_label(fc).lower():
                    continue
                out.append(("ATTR", node, fc))
                if up and is_driver(fc):
                    for kind2, ufc, label in upstream_rows(node, fc):
                        _up_label[(kind2, ufc.as_pointer())] = label
                        out.append((kind2, node, ufc))
            if kind == "OBJECT":         # the other selected animation layers' rows
                out += graph_layers.outliner_rows(context.scene, node)
    return out


ATTR_KINDS = ("ATTR", "UP_SDK", "UP_CURVE")      # channel rows (the rest are node rows)
_up_label = {}                                   # (row kind, fcurve pointer) -> upstream row label


def shows_upstream(space, flt=None):
    """Graph Editor List > Show Upstream Curves (on by default, like Maya): upstream rows show unless an attribute filter
    other than Driven by Driven Key is checked (Driven by Anim Curve hides them)."""
    flt = attr_filters() if flt is None else flt
    return (not _is_dope_space(space) and _wm_flag("allset_show_upstream")
            and (not flt or "driven_key" in flt))


def upstream_curves(context, space):
    """[(driver ID, its keyed curve)] the listed driven-key channels' upstream rows show (Blender must draw them)."""
    if not shows_upstream(space):
        return []
    out = []
    for _kind, node, curves in listed_nodes(context, space):
        for fc in curves:
            if is_driver(fc):
                tgt = sdk_target(fc)
                for kind2, ufc, _label in upstream_rows(node, fc):
                    if kind2 == "UP_CURVE" and tgt is not None:
                        out.append((tgt[0], ufc))
    return out


def listed_curves(context, space):
    return [fc for _kind, _node, curves in listed_nodes(context, space) for fc in curves] + \
        [fc for _owner, fc in upstream_curves(context, space)]


def node_selected(context, kind, node):
    """Is the row's node selected in the scene (Maya loads the selection into the Graph Editor highlighted)?"""
    from . import channel_box
    if kind == "JOINT":
        arm = node.id_data
        return channel_box.bone_selected(node) if arm.mode == 'POSE' else arm.select_get()
    if kind == "CHARACTER":
        from ..operators import character_sets
        return node in character_sets.picked(context)
    if kind == "SHAPES":
        return any(o.select_get() for o in context.scene.objects
                   if getattr(getattr(o, "data", None), "shape_keys", None) == node)
    if kind == "SET":
        return False            # a set node is highlighted only when picked in the list
    return node.select_get()


def selection_sig(context):
    """Scene selection (objects + pose-mode joints) the outliner picks belong to."""
    from . import channel_box
    sig = []
    for ob in context.scene.objects:
        if ob.select_get():
            sig.append(ob.name)
        if ob.type == 'ARMATURE' and ob.mode == 'POSE' and ob.pose is not None:
            sig += [(ob.name, pb.name) for pb in ob.pose.bones if channel_box.bone_selected(pb)]
    return tuple(sig)


def picked_ids(context, all_rows):
    """The user's picks that still name a listed row, or an empty set (none yet / the scene selection changed)."""
    if _picked["sig"] != selection_sig(context):
        return set()
    return _picked["ids"] & {row_id(r) for r in all_rows}


def highlighted(kind, rid, selected, picked):
    """Maya: once rows were picked in the outliner exactly those are highlighted; before that the selected nodes
    (never their attribute rows — Blender selects every F-curve of a selected object, so ``fc.select`` is not
    the highlight). Clicking an attribute un-highlights its node like Maya's outliner."""
    if picked:
        return rid in picked
    return kind not in ATTR_KINDS and selected


def metrics(region):
    """(top of the first row, row height) in region pixels: Blender keeps its search field at the top."""
    s = bpy.context.preferences.system.ui_scale or 1.0     # 0 in background
    return region.height - round(24 * s), round(20 * s)


def visible_rows(region):
    top, h = metrics(region)
    return max(1, int(top // h)) if h > 0 else 1


def clamp_scroll(offset, n_rows, n_visible):
    """First row shown: 0 .. the last full page (a list that fits doesn't scroll)."""
    return max(0, min(int(offset), n_rows - n_visible))


def _area_ptr(context):
    area = getattr(context, "area", None)
    return area.as_pointer() if area is not None else 0


def scroll_offset(context, region, n_rows):
    return clamp_scroll(_scroll.get(_area_ptr(context), 0), n_rows, visible_rows(region))


def row_at(context, region, y):
    top, h = metrics(region)
    if y > top:
        return None
    rs = rows(context, context.space_data)
    k = int((top - y) // h) + scroll_offset(context, region, len(rs))
    return rs[k] if 0 <= k < len(rs) else None


def _rect(x0, y0, x1, y1, color):
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {"pos": ((x0, y0), (x1, y0), (x1, y1), (x0, y0), (x1, y1), (x0, y1))})
    shader.uniform_float("color", color)
    batch.draw(shader)


PIN = (0.85, 0.85, 0.85, 1.0)
PIN_OFF = (0.55, 0.55, 0.55, 1.0)


def _draw_pin(x, y, s, pinned):
    """Maya's pin icon left of a channel row's name: an upright push-pin on a
    pinned row (head, plate, needle), a grey sideways one on the others."""
    if pinned:
        _rect(x - 2 * s, y + 1 * s, x + 2 * s, y + 6 * s, PIN)
        _rect(x - 4 * s, y, x + 4 * s, y + 1.5 * s, PIN)
        _rect(x - 0.5 * s, y - 5 * s, x + 0.5 * s, y, PIN)
    else:
        _rect(x - 6 * s, y - 2 * s, x - 1 * s, y + 2 * s, PIN_OFF)
        _rect(x - 1 * s, y - 3.5 * s, x + 0.5 * s, y + 3.5 * s, PIN_OFF)
        _rect(x + 0.5 * s, y - 0.5 * s, x + 6 * s, y + 0.5 * s, PIN_OFF)


def draw_channels():
    context = bpy.context
    space, region = context.space_data, context.region
    if not (is_graph(space) and enabled(context)) or region is None:
        return
    top, h = metrics(region)
    s = context.preferences.system.ui_scale
    pins = getattr(context.window_manager, "allset_show_pins", True)      # Maya 2026 View > Show Pins
    gpu.state.blend_set('ALPHA')
    _rect(0, 0, region.width, top, BACK)
    font = 0
    blf.size(font, 12 * s)
    all_rows = rows(context, space)
    picked = picked_ids(context, all_rows)
    first = scroll_offset(context, region, len(all_rows))
    y = top
    for row in all_rows[first:]:
        if y < 0:
            break
        kind, node, fc = row
        if kind in graph_layers.KINDS:          # another selected animation layer (ui/graph_layers.py)
            graph_layers.draw_row(row, y, h, s, font, region.width)
            y -= h
            continue
        sel = highlighted(kind, row_id(row), kind not in ATTR_KINDS and node_selected(context, kind, node), picked)
        if sel:
            _rect(0, y - h, region.width, y, SELECT)
        if kind in ("UP_SDK", "UP_CURVE"):       # Show Upstream Curves rows, indented under their channel
            blf.color(font, *(attr_color(fc) if kind == "UP_SDK" else TEXT))
            blf.position(font, 66 * s, y - h + 6 * s, 0)
            blf.draw(font, _up_label.get((kind, fc.as_pointer()), ""))
            if pins:
                _draw_pin(56 * s, y - h / 2, s, False)
        elif kind != "ATTR":
            sign = "−" if _expanded.get(node_key(node), True) else "+"
            blf.color(font, *TEXT)
            blf.position(font, 6 * s, y - h + 6 * s, 0)
            blf.draw(font, sign)
            blf.position(font, 22 * s, y - h + 6 * s, 0)
            blf.draw(font, node_name(node))
        else:
            blf.color(font, *attr_color(fc))
            blf.position(font, 44 * s, y - h + 6 * s, 0)
            blf.draw(font, attr_label(fc))
            if pins:
                _draw_pin(34 * s, y - h / 2, s, is_pinned(node, fc))
        y -= h
    n_vis = visible_rows(region)
    if len(all_rows) > n_vis:       # Maya's scroll bar at the right edge: thumb = the shown part of the list
        span = top / len(all_rows)
        x1 = region.width - 2 * s
        _rect(x1 - 6 * s, top - (first + n_vis) * span, x1, top - first * span, THUMB)
    gpu.state.blend_set('NONE')


def show_rows(context, chosen):
    """Maya: the curves of the selected outliner rows are shown and selected, the others hidden (pinned curves stay
    shown)."""
    for _kind, node, curves in listed_nodes(context, context.space_data):
        for fc in curves:
            on = fc in chosen
            fc.select = on
            fc.hide = not (on or is_pinned(node, fc))
    for _owner, fc in upstream_curves(context, context.space_data):
        on = fc in chosen
        fc.select = on
        fc.hide = not on


def pick_row(context, row, ctrl=False, shift=False):
    """A click on an outliner row: remember the picked rows (the highlight) and show / select their curves. Ctrl
    toggles, Shift adds, a plain click replaces."""
    space = context.space_data
    all_rows = rows(context, space)
    kind, node, fc = row
    rid = row_id(row)
    listed = {node_key(n): c for _k, n, c in listed_nodes(context, space)}
    picked = set(listed.get(node_key(node), ()) if kind not in ATTR_KINDS else [fc])
    current = {c for c in listed_curves(context, space) if c.select and not c.hide}
    ids = picked_ids(context, all_rows)
    if ctrl:
        chosen, ids = current ^ picked, ids ^ {rid}
    elif shift:
        chosen, ids = current | picked, ids | {rid}
    else:
        chosen, ids = picked, {rid}
    _picked["ids"], _picked["sig"] = ids, selection_sig(context)
    show_rows(context, chosen)
    return chosen


class ALLSET_OT_graph_channel_click(bpy.types.Operator):
    """Maya Graph Editor outliner: click a node (all its curves) or an attribute (that curve); Ctrl toggles,
    Shift adds; the +/- sign folds the attributes"""
    bl_idname = "allset.graph_channel_click"
    bl_label = "Graph Editor Outliner Click"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.region is not None and context.region.type == 'CHANNELS' and is_graph(context.space_data)

    def invoke(self, context, event):
        if not enabled(context):
            return {'PASS_THROUGH'}
        region = context.region
        if event.mouse_region_y > metrics(region)[0]:
            return {'PASS_THROUGH'}       # Blender's search field
        row = row_at(context, region, event.mouse_region_y)
        if row is None:
            return {'FINISHED'}
        kind, node, _fc = row
        if kind in graph_layers.KINDS:          # that layer becomes the last picked one
            graph_layers.activate_row(context, row)
            return {'FINISHED'}
        s = context.preferences.system.ui_scale
        if kind not in ATTR_KINDS and event.mouse_region_x < 18 * s:
            key = node_key(node)
            _expanded[key] = not _expanded.get(key, True)
            region.tag_redraw()
            return {'FINISHED'}
        pick_row(context, row, ctrl=event.ctrl, shift=event.shift)
        for area in context.screen.areas:
            if area.type == 'GRAPH_EDITOR':
                area.tag_redraw()
        return {'FINISHED'}


def _channels_region(context):
    region = getattr(context, "region", None)
    if region is not None and region.type == 'CHANNELS':
        return region
    area = getattr(context, "area", None)
    return next((r for r in area.regions if r.type == 'CHANNELS'), None) if area is not None else None


class ALLSET_OT_graph_channel_scroll(bpy.types.Operator):
    """Scroll the Maya Graph Editor outliner by rows (positive = down the list)"""
    bl_idname = "allset.graph_channel_scroll"
    bl_label = "Graph Editor Outliner Scroll"

    delta: IntProperty(name="Rows", description="Rows to scroll, positive = down the list", default=3,
                       options={'SKIP_SAVE'})

    def execute(self, context):
        space = getattr(context, "space_data", None)
        region = _channels_region(context)
        if not (is_graph(space) and enabled(context)) or region is None:
            return {'PASS_THROUGH'}     # no Maya Graph Editor here: Blender's own channel scrolling
        n = len(rows(context, space))
        ptr = _area_ptr(context)
        old = scroll_offset(context, region, n)
        _scroll[ptr] = clamp_scroll(old + self.delta, n, visible_rows(region))
        region.tag_redraw()
        return {'FINISHED'}

    def invoke(self, context, event):
        # a wheel item: only over the outliner pane itself (the curve area keeps Blender's zoom)
        region = getattr(context, "region", None)
        if region is None or region.type != 'CHANNELS':
            return {'PASS_THROUGH'}
        return self.execute(context)


# --- keeping Blender's drawing in step with the Maya list ----------------------------------------------------------

def editor_spaces(context):
    """[(window, area, space)] of every Maya Graph Editor (F-Curves) and Dope Sheet (not the Timeline)."""
    out = []
    for w in context.window_manager.windows:
        if w.screen is None:
            continue
        for a in w.screen.areas:
            sp = a.spaces.active
            if is_graph(sp) or is_dope(sp):
                out.append((w, a, sp))
    return out


def _curve_key(owner, fc):
    return ("KEY" if isinstance(owner, bpy.types.Key) else "OBJECT", owner.name, fc.data_path, fc.array_index)


def _resolve_curve(key):
    kind, name, path, idx = key
    owner = (bpy.data.shape_keys if kind == "KEY" else bpy.data.objects).get(name)
    if owner is None:
        return None
    return next((fc for fc in object_curves(owner) if fc.data_path == path and fc.array_index == idx), None)


def _drawn_curves(context, space):
    """{curve key: fcurve} Blender draws in this Graph Editor (by object; joints only selected ones while Blender's
    Only Show Selected filters them)."""
    from . import channel_box
    obs = drawn_objects(context, space)
    if obs is None:
        obs = list(context.scene.objects)
    native_auto = bool(_ds(space).show_only_selected)
    out = {}
    for ob in obs:
        for fc in object_curves(ob):
            if native_auto and ob.type == 'ARMATURE' and ob.pose is not None:
                name = _bone_name(fc.data_path)
                pb = ob.pose.bones.get(name) if name is not None else None
                if pb is not None and not channel_box.bone_selected(pb):
                    continue
            out[_curve_key(ob, fc)] = fc
        key = shape_key(ob)
        if key is not None:
            for fc in object_curves(key):
                out[_curve_key(key, fc)] = fc
    return out


def sync_hidden(context, spaces):
    """Hide the curves Blender draws that no Maya list shows; show again the ones the kit hid once listed. Only
    while a kit list, an attribute filter or a pin is in play (or the kit still has curves hidden)."""
    graphs = [sp for sp in spaces if is_graph(sp)]
    active = _pinned or attr_filters() or any(kit_list(sp) is not None for sp in graphs)
    if not (active or _kit_hidden):
        return 0
    want, listed = {}, set()
    for sp in graphs if active else ():
        drawn = _drawn_curves(context, sp)
        shown = {fc.as_pointer() for fc in listed_curves(context, sp)}
        for key, fc in drawn.items():
            if fc.as_pointer() in shown:
                listed.add(key)
            else:
                want[key] = fc
    n = 0
    for key, fc in want.items():
        if key not in listed and not fc.hide:
            fc.hide = True
            _kit_hidden.add(key)
            n += 1
    for key in list(_kit_hidden):
        if key in want and key not in listed:
            continue
        _kit_hidden.discard(key)
        fc = _resolve_curve(key)
        if fc is not None and fc.hide:
            fc.hide = False
            n += 1
    return n


def sync(context):
    """Every Graph Editor / Dope Sheet: Blender's filters follow its Maya list (graph_view's timer, menu items)."""
    if not enabled(context):
        return
    found = list(editor_spaces(context))
    spaces = [sp for _w, _a, sp in found]
    changed = False
    for window, area, sp in found:
        if (is_graph(sp) or is_dope(sp)) and setup_toolbar_row(window, area):
            changed = True
    for sp in spaces:
        changed |= sync_space(context, sp)
    changed |= bool(sync_hidden(context, spaces))
    if changed:
        _redraw_editors(context)


def _redraw_editors(context):
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type in {'GRAPH_EDITOR', 'DOPESHEET_EDITOR'}:
                area.tag_redraw()


def release_all():
    """Disable: every editor back to Blender's own filters, kit lists removed, hidden curves shown, pins dropped."""
    try:
        spaces = [sp for _w, _a, sp in editor_spaces(bpy.context)]
    except (AttributeError, ReferenceError):
        spaces = []
    for sp in spaces:
        coll = kit_list(sp)
        if coll is not None:
            auto = coll.get(LOADED) is None and bool(coll.get(AUTO, False))
            sp.dopesheet.filter_collection = None
            sp.dopesheet.show_only_selected = auto
    for coll in [c for c in bpy.data.collections if c.get(LIST_MARK)]:
        bpy.data.collections.remove(coll)
    for key in _kit_hidden:
        fc = _resolve_curve(key)
        if fc is not None:
            fc.hide = False
    _kit_hidden.clear()
    _pinned.clear()
    release_toolbar_rows()


class ALLSET_OT_graph_list(bpy.types.Operator):
    """Maya List > Load Selected Objects (replace the list) / Add Selected Objects (add to it): the list stays
    when the selection changes (only while Auto Load Selected Objects is off)"""
    bl_idname = "allset.graph_list"
    bl_label = "Load Selected Objects"
    bl_options = {'UNDO'}

    action: bpy.props.EnumProperty(items=(("LOAD", "Load", "Load the selected objects"),
                                          ("ADD", "Add", "Add the selected objects")),
                                   default="LOAD", options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        # Maya greys Load / Add Selected Objects while Auto Load is on
        space = getattr(context, "space_data", None)
        if _ds(space) is None:
            return False
        if auto_load(space):
            cls.poll_message_set("Auto Load Selected Objects is on")
            return False
        return True

    def execute(self, context):
        load_selected(context, context.space_data, add=self.action == "ADD")
        _redraw_editors(context)
        return {'FINISHED'}


def _target_rows(context, space):
    """[(node, fcurve)] a channel command (Pin / Unpin Channel) acts on: the highlighted outliner rows, a node row =
    all its channels; nothing highlighted = nothing (Maya). The highlight is the one drawn:
    the rows picked in the list, else the selected nodes' rows."""
    all_rows = rows(context, space)
    picked = picked_ids(context, all_rows)
    out = []
    for kind, node, curves in listed_nodes(context, space):
        nk = node_key(node)
        whole = highlighted(kind, nk, node_selected(context, kind, node), picked)
        for fc in curves:
            if whole or (nk, fc.data_path, fc.array_index) in picked:
                out.append((node, fc))
    return out


class ALLSET_OT_graph_pin(bpy.types.Operator):
    """Maya Curves > Pin Channel / Unpin Channel: pinned curves stay listed and drawn whatever is selected"""
    bl_idname = "allset.graph_pin"
    bl_label = "Pin Channel"
    bl_options = {'UNDO'}

    pin: BoolProperty(default=True, options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return is_graph(getattr(context, "space_data", None))

    def execute(self, context):
        targets = _target_rows(context, context.space_data)
        if not targets:
            self.report({'WARNING'}, "No channels selected.")
            return {'CANCELLED'}
        ids = {(node_key(n), fc.data_path, fc.array_index) for n, fc in targets}
        if self.pin:
            _pinned.update(ids)
        else:
            _pinned.difference_update(ids)
        sync(context)
        _redraw_editors(context)
        return {'FINISHED'}


class ALLSET_OT_graph_attr_clear(bpy.types.Operator):
    """Clear the attribute filters: every animated attribute is listed again (Maya Show > Attributes > Clear
    Below)"""
    bl_idname = "allset.graph_attr_clear"
    bl_label = "Clear Below"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return _ds(getattr(context, "space_data", None)) is not None

    def execute(self, context):
        context.space_data.dopesheet.filter_text = ""
        wm = context.window_manager
        for f in ATTR_FILTERS:
            setattr(wm, "allset_attr_" + f, False)
        return {'FINISHED'}


def _auto_get(_wm):
    return auto_load(getattr(bpy.context, "space_data", None))


def _auto_set(_wm, value):
    space = getattr(bpy.context, "space_data", None)
    if _ds(space) is not None:
        set_auto_load(bpy.context, space, value)
        _redraw_editors(bpy.context)


def _filters_changed(_self, context):
    try:
        sync(context)
    except (AttributeError, ReferenceError, RuntimeError):
        pass
    _redraw_editors(context)


# (WindowManager property, label, Maya annotation) of the Show / List check items
FLAGS = (
    ("allset_attr_hidden", "Hidden", "List only hidden attributes (Channel Box hidden channels)"),
    ("allset_attr_anim_curve", "Driven by Anim Curve", "List only keyed attributes"),
    ("allset_attr_expression", "Driven by Expression", "List only attributes driven by an expression (scripted "
     "driver)"),
    ("allset_attr_driven_key", "Driven by Driven Key", "List only attributes driven by a Set Driven Key"),
    ("allset_attr_user_defined", "User Defined", "List only user-defined attributes (custom properties)"),
    ("allset_show_ik_handles", "IkHandles", "List only IK handles"),
    ("allset_show_sets", "Sets", "List only the sets and character sets"),
    ("allset_show_upstream", "Show Upstream Curves", "Under a driven-key channel also list its driven key curve "
     "and the driver's own curve"),
    ("allset_hierarchy_below", "Hierarchy Below", "Also show the keys of the listed objects' children (the kit lists "
     "them as rows)"),
    ("allset_show_pins", "Show Pins", "Show or hide the pin buttons next to the outliner rows"),
)
# On by default, like Maya: Show Upstream Curves checked; View > Show Pins checked
FLAGS_ON = {"allset_show_upstream", "allset_show_pins"}


# --- header draws ------------------------------------------------------------------------------------------------

_orig = {}


def toolbar_row(area):
    """True when the editor's footer is shown at the top: it holds Maya's toolbar row under the menu bar."""
    if area is None or not getattr(area.spaces.active, "show_region_footer", False):
        return False
    return any(r.type == 'FOOTER' and r.alignment == 'TOP' for r in area.regions)


def _graph_header(self, context):
    if not (enabled(context) and is_graph(context.space_data)):
        return _orig["graph"](self, context)
    layout = self.layout
    layout.template_header()
    draw_menus(layout, context, GE)
    if not toolbar_row(context.area):
        draw_icons(layout, context, GE)
    layout.separator_spacer()
    layout.popover(panel="GRAPH_PT_filters", text="", icon='FILTER')


def _dope_header(self, context):
    if not (enabled(context) and is_dope(context.space_data)):
        return _orig["dope"](self, context)
    layout = self.layout
    layout.template_header()
    draw_menus(layout, context, DS)
    if not toolbar_row(context.area):
        draw_icons(layout, context, DS)
    layout.separator_spacer()
    layout.popover(panel="DOPESHEET_PT_filters", text="", icon='FILTER')


# #192: Maya's Graph Editor / Dope Sheet keep the toolbar on its own row under the menu bar (on one row with
# the menus the tangent buttons ran past the right edge of a ~750 px editor). Blender gives these editors one header,
# but their footer (playback controls in 5.x) can sit at the top under it: in a Maya editor the footer is shown, put on
# top and draws the toolbar. Timeline mode keeps Blender's footer.
def _graph_footer(self, context):
    if not (enabled(context) and is_graph(context.space_data)):
        return _orig["graph_foot"](self, context)
    draw_icons(self.layout, context, GE)


def _dope_footer(self, context):
    if not (enabled(context) and is_dope(context.space_data)):
        return _orig["dope_foot"](self, context)
    draw_icons(self.layout, context, DS)


_set_up = set()          # area pointers given the Maya toolbar row this session (a later user choice is kept)


def _flip_footer(window, area):
    region = next((r for r in area.regions if r.type == 'FOOTER'), None)
    if region is None:
        return False
    try:
        with bpy.context.temp_override(window=window, area=area, region=region):
            return 'FINISHED' in bpy.ops.screen.region_flip()
    except (RuntimeError, TypeError, ReferenceError):
        return False


def setup_toolbar_row(window, area):
    """Maya Graph Editor / Dope Sheet layout of one editor, once per session: toolbar row on top; the Graph Editor
    draws tangent handles on selected keys only (Maya View > Tangents factory = On Active Keys)."""
    key = area.as_pointer()
    if key in _set_up:
        return False
    _set_up.add(key)
    space = area.spaces.active
    if space.type == 'GRAPH_EDITOR':
        space.use_only_selected_keyframe_handles = True
    if toolbar_row(area):
        return False
    space.show_region_footer = True
    if all(r.alignment != 'TOP' for r in area.regions if r.type == 'FOOTER'):
        _flip_footer(window, area)
    return True


def release_toolbar_rows():
    """Maya mode off: the footers the kit put on top go back to Blender's place (bottom, hidden)."""
    try:
        wins = list(bpy.context.window_manager.windows)
    except (AttributeError, ReferenceError):
        return
    for window in wins:
        for area in window.screen.areas:
            sp = area.spaces.active
            if not (is_graph(sp) or is_dope(sp)) or not toolbar_row(area):
                continue
            _flip_footer(window, area)
            sp.show_region_footer = False
    _set_up.clear()


def draw_uv_header(self, context):
    """UV Editor header row (Maya menu bar); False = not a Maya UV Editor (draw Blender's)."""
    if not (enabled(context) and is_uv(context.space_data)):
        return False
    layout = self.layout
    layout.template_header()
    draw_menus(layout, context, UV)
    return True


def draw_uv_tool_header(self, context):
    """UV Editor tool header = Maya's icon row, then Blender's pivot / snapping / soft select."""
    if not (enabled(context) and is_uv(context.space_data)):
        return False
    layout = self.layout
    draw_icons(layout, context, UV)
    layout.separator_spacer()
    bpy.types.IMAGE_HT_header.draw_xform_template(layout, context)
    return True


HEADERS = (("graph", "GRAPH_HT_header", _graph_header), ("dope", "DOPESHEET_HT_header", _dope_header),
           ("graph_foot", "GRAPH_HT_playback_controls", _graph_footer),
           ("dope_foot", "DOPESHEET_HT_playback_controls", _dope_footer))


def own_draw(cls):
    """The class's own draw: the first of its draw functions once something appended to it (bpy_types
    _GenericUI), else ``draw``."""
    return getattr(cls.draw, "_draw_funcs", [cls.draw])[0]


def patch_headers():
    """Swap only the class's own draw (the first draw function), so UI appended to the header by others (e.g. the
    kit's Graph Editor toolbar) keeps drawing after it."""
    for key, name, fn in HEADERS:
        funcs = getattr(bpy.types, name)._dyn_ui_initialize()
        if key not in _orig:
            _orig[key] = funcs[0]
        funcs[0] = fn


def unpatch_headers():
    for key, name, _fn in HEADERS:
        if key in _orig:
            getattr(bpy.types, name)._dyn_ui_initialize()[0] = _orig.pop(key)


# --- opening an editor the Maya way ----------------------------------------------------------------------------

def frame_playback_range(context, area):
    """Horizontal view = the playback range from frame 1 (Maya: no frame 0 / out-of-range area at the left)."""
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if region is None or region.width < 2:
        return False
    with context.temp_override(window=context.window, area=area, region=region):
        if area.type == 'GRAPH_EDITOR':
            bpy.ops.graph.view_all()
        bpy.ops.anim.scene_range_frame()
        sc = context.scene
        start = sc.frame_preview_start if sc.use_preview_range else sc.frame_start
        lo, _ = region.view2d.region_to_view(0, 0)
        hi, _ = region.view2d.region_to_view(region.width, 0)
        per_px = (hi - lo) / region.width if hi > lo else 0
        if per_px > 0:
            dx = int(round(((start - 0.5) - lo) / per_px))
            if dx:
                bpy.ops.view2d.pan(deltax=dx, deltay=0)
    return True


def prepare_later(window, ui_type, tries=60):
    """After ``allset.open_editor``: frame the playback range (Graph Editor / Dope Sheet), fold the Dope Sheet to
    object rows (Maya Dopesheet Summary + objects), show the UV Editor's tool header and UV Toolkit. From a timer:
    a new window's regions have no size inside the operator."""
    state = {"n": tries}
    ptr = window.as_pointer()

    def tick():
        window = live_refs.window(ptr)     # the pointer, looked up each tick: a closed window crashes (#36)
        if window is None:
            return None
        try:
            area = window.screen.areas[0]
            if area.ui_type != ui_type:
                return None
            space = area.spaces.active
            ctx = bpy.context
            with ctx.temp_override(window=window, area=area):
                if ui_type == 'UV':
                    space.show_region_tool_header = True
                    space.show_region_toolbar = False
                    from ..operators.menu_extras import sidebar_tab_later
                    from .uv_toolkit import CATEGORY
                    sidebar_tab_later(window, CATEGORY)
                    return None
                space.show_region_ui = False    # Maya's Graph Editor / Dope Sheet have no side panel
                if not frame_playback_range(ctx, area):
                    state["n"] -= 1
                    return 0.05 if state["n"] > 0 else None
                if ui_type == 'DOPESHEET':
                    chan = next((r for r in area.regions if r.type == 'CHANNELS'), None)
                    if chan is not None:
                        with ctx.temp_override(window=window, area=area, region=chan):
                            bpy.ops.anim.channels_collapse(all=True)
                    space.dopesheet.show_expanded_summary = True     # Dopesheet Summary open, objects folded
                area.tag_redraw()
        except (ReferenceError, AttributeError, IndexError, RuntimeError):
            return None
        return None

    bpy.app.timers.register(tick, first_interval=0.05)


# --- registration --------------------------------------------------------------------------------------------------

classes = (ALLSET_OT_editor_icon, ALLSET_OT_editor_icon_unavailable, ALLSET_OT_graph_channel_click,
           ALLSET_OT_graph_channel_scroll, ALLSET_OT_graph_list, ALLSET_OT_graph_pin, ALLSET_OT_graph_attr_clear,
           *_BLENDER.values(), *_BAR.values())
_handle = []


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.allset_key_time = StringProperty(
        name="Key Time", description="Maya Stats: the selected keys' time (type a frame, +=5 to move them)",
        get=_stats_get("time"), set=_stats_set("time"))
    bpy.types.Scene.allset_key_value = StringProperty(
        name="Key Value", description="Maya Stats: the selected keys' value (display units, +=5 / *=2 work)",
        get=_stats_get("value"), set=_stats_set("value"))
    bpy.types.WindowManager.allset_show_characters = BoolProperty(
        name="Characters", description="List only the character sets with their member attributes (Maya Show > "
        "Objects > Characters)", default=False, options={'SKIP_SAVE'}, update=_filters_changed)
    for name, label, tip in FLAGS:
        setattr(bpy.types.WindowManager, name, BoolProperty(
            name=label, description=f"Maya: {tip}", default=name in FLAGS_ON, options={'SKIP_SAVE'},
            update=_filters_changed))
    bpy.types.WindowManager.allset_auto_load = BoolProperty(
        name="Auto Load Selected Objects", description="Maya: the list follows the selection (off: Load / Add "
        "Selected Objects keep a fixed list)", get=_auto_get, set=_auto_set, options={'SKIP_SAVE'})
    patch_headers()
    _handle.append(bpy.types.SpaceGraphEditor.draw_handler_add(draw_channels, (), 'CHANNELS', 'POST_PIXEL'))
    graph_layers.register()


def unregister():
    graph_layers.unregister()
    while _handle:
        bpy.types.SpaceGraphEditor.draw_handler_remove(_handle.pop(), 'CHANNELS')
    unpatch_headers()
    del bpy.types.Scene.allset_key_time
    del bpy.types.Scene.allset_key_value
    del bpy.types.WindowManager.allset_show_characters
    release_all()
    for name, _label, _tip in FLAGS:
        delattr(bpy.types.WindowManager, name)
    del bpy.types.WindowManager.allset_auto_load
    _expanded.clear()
    _up_label.clear()
    _scroll.clear()
    _picked["ids"], _picked["sig"] = set(), None
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
