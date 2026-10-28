# SPDX-License-Identifier: GPL-3.0-or-later
"""Patches that turn Industry Compatible data into the "Maya" keyconfig.

``IC:<line>`` = ``$S\\presets\\keyconfig\\keymap_data\\industry_compatible_data.py``.
Plan and rationale: docs/steps/step_2.md (1-4), docs/steps/step_3.md (5-8),
docs/steps/step_4.md (9-13), docs/steps/step_10.md (16), docs/steps/step_11.md (17),
docs/steps/step_16.md (18), docs/steps/step_18.md (19), docs/steps/step_20.md (20),
docs/steps/step_22.md (21), docs/steps/step_24.md (22), docs/steps/step_27.md (23), docs/steps/step_28.md (24).

``ADDED`` lists every binding this module adds; tests use it for the
shadowing check and docs/keymap_mapping.md is cross-checked against it.
"""

from . import patch
from .patch import KeyconfigData, make_event

# (km_name, idname, event, props, shadows) for every binding added below.
# ``shadows``: keymaps allowed to bind the same event in the same editor
# (intentional: e.g. paint modes keep their own X/B).
ADDED = []


# Operators that return PASS_THROUGH when they don't apply, so they may sit in
# front of another item with the same event in the same keymap.
PASS_THROUGH_FIRST = ("allset.pivot_pick", "allset.cb_virtual_slider", "allset.cb_hover", "allset.weight_numbers_hover", "allset.cb_scroll","allset.time_range_drag", "allset.manip_ctrl", "allset.manip_duplicate", "allset.manip_press",
                      "allset.select_priority", "allset.select_through", "allset.toolbox_guard", "allset.time_scrub",
                      "allset.time_slider_menu", "allset.outliner_set_click", "allset.outliner_set_menu",
                      "allset.graph_channel_click", "allset.graph_channel_scroll", "allset.script_run",
                      "allset.dock_strip_click",
                      "allset.hs_swatch_drag", "allset.shelf_scroll",
                      "allset.select_2d_click", "allset.select_2d_box", "allset.graph_layer_pick",
                      "allset.uv_shell_pick", "allset.uv_shell_box")


def _add(kd, km_name, idname, event, props=None, shadows=(), first=False):
    kd.add(km_name, idname, event, props, first=first)
    ADDED.append((km_name, idname, event, dict(props or {}), tuple(shadows)))


# --- 1. Selection modifiers ----------------------------------------------
# Maya: Shift = toggle, Ctrl = deselect, Ctrl+Shift = add, for click and
# marquee (research/maya/interaction.md:68-70). Order of variants:
# (shift, ctrl) = none, Shift, Ctrl, Ctrl+Shift.

def _click(plain, toggle, deselect, add):
    return [((False, False), plain), ((True, False), toggle),
            ((False, True), deselect), ((True, True), add)]


# Operators with a real ``deselect`` option (research/blender/operators.json).
_CLICK_EXACT = _click({"deselect_all": True}, {"toggle": True},
                      {"deselect": True}, {"extend": True})

# Step 170 (GUI-measured, research/maya/re/select_mods_170.md): Maya's Outliner is a Qt list — plain = replace,
# Shift = range from the anchor, Ctrl = toggle, Ctrl+Shift = add the range. Blender's item_activate does that with
# extend / extend_range (the anchor is Blender's active element).
_OUTLINER_CLICK = _click({"extend": False, "extend_range": False, "deselect_all": True},
                         {"extend": False, "extend_range": True, "deselect_all": True},
                         {"extend": True, "extend_range": False, "deselect_all": True},
                         {"extend": True, "extend_range": True, "deselect_all": True})
# Graph Editor (measured): Shift toggles; Ctrl+click acts like a plain click; Ctrl+Shift adds — the plain / Ctrl /
# Ctrl+Shift rules that Blender's clickselect lacks are applied by allset.select_2d_click placed first (patch below);
# these items are what runs if that operator passes through.
_GRAPH_CLICK = _click({"extend": False, "deselect_all": True},
                      {"extend": True}, {"extend": False, "deselect_all": True}, {"extend": True})
# NLA (not measured in step 170): the step 2 rule, every modifier toggles
_NLA_CLICK = _click({"extend": False, "deselect_all": True}, {"extend": True}, {"extend": True}, {"extend": True})
# Dope Sheet (measured): Shift toggles, Ctrl deselects, Ctrl+Shift adds (select_2d_click)
_DOPE_CLICK = _click({"extend": False, "deselect_all": True},
                     {"extend": True}, {"extend": True}, {"extend": True})

_BOX = _click({"mode": "SET"}, {"mode": "XOR"}, {"mode": "SUB"}, {"mode": "ADD"})
# uv / graph / action select_box have no XOR: their Shift box runs as SET and allset.select_2d_box (first, PASS_THROUGH)
# toggles what it caught against the selection before (step 170). Outliner / NLA keep Shift = add.
_BOX_SET_XOR = _click({"mode": "SET"}, {"mode": "SET"}, {"mode": "SUB"}, {"mode": "ADD"})
_BOX_NO_XOR = _click({"mode": "SET"}, {"mode": "ADD"}, {"mode": "SUB"}, {"mode": "ADD"})

# node.select has a real deselect / toggle (measured 4.5): Maya exactly. Node Ctrl+drag stays Blender's node.link
# (detach links from a socket): no Ctrl marquee there (step 86, delegated).
_NODE_CLICK = _click({"deselect_all": True, "select_passthrough": True}, {"toggle": True},
                     {"deselect": True}, {"extend": True})
_NODE_BOX = [v for v in _BOX_NO_XOR if v[0] != (False, True)]

SELECT_RULES = (
    # idname, event value, variants, props kept from IC's plain item
    ("view3d.select", "CLICK", _CLICK_EXACT, ()),          # IC "3D View" (dump), viewport
    ("view3d.select", "PRESS", _CLICK_EXACT, ()),          # "3D View Tool: Tweak"
    ("uv.select", "CLICK", _CLICK_EXACT, ()),              # "UV Editor"
    ("uv.select", "PRESS", _CLICK_EXACT, ()),              # "Image Editor Tool: Uv, Tweak"
    ("outliner.item_activate", "CLICK", _OUTLINER_CLICK, ()),
    ("graph.clickselect", "PRESS", _GRAPH_CLICK, ("column", "curves")),
    ("view3d.select_box", "CLICK_DRAG", _BOX, ("tweak",)),
    ("uv.select_box", "CLICK_DRAG", _BOX_SET_XOR, ("tweak",)),
    ("outliner.select_box", "CLICK_DRAG", _BOX_NO_XOR, ("tweak",)),
    ("graph.select_box", "CLICK_DRAG", _BOX_SET_XOR, ("tweak", "axis_range")),
    # step 86 (docs/steps/step_86.md 「계획」 1): Dope Sheet, NLA, Node Editor
    ("action.clickselect", "PRESS", _DOPE_CLICK, ("column", "channel")),
    ("nla.click_select", "PRESS", _NLA_CLICK, ()),
    ("node.select", "PRESS", _NODE_CLICK, ()),
    ("action.select_box", "CLICK_DRAG", _BOX_SET_XOR, ("tweak", "axis_range", "wait_for_input")),
    ("nla.select_box", "CLICK_DRAG", _BOX_NO_XOR, ("tweak", "axis_range", "wait_for_input")),
    ("node.select_box", "CLICK_DRAG", _NODE_BOX, ("tweak",)),
)


SELECT_CTRL_SHIFT_REMOVED = (("Dopesheet", "action.select_leftright"), ("NLA Editor", "nla.select_leftright"),
                             ("Node Editor", "node.select_link_viewer"))


def patch_selection(kd):
    # IC:935 Ctrl+Shift+LMB = select keys left/right of the frame; Maya has no
    # such binding and Ctrl+Shift click must add to the selection.
    kd.remove("Graph Editor", "graph.select_leftright", type="LEFTMOUSE",
              shift=True, ctrl=True)
    # step 86: the same Ctrl+Shift+LMB in the Dope Sheet / NLA, and Node Editor Ctrl+Shift+click = link to viewer
    for km, idname in SELECT_CTRL_SHIFT_REMOVED:
        kd.remove(km, idname, type="LEFTMOUSE", shift=True, ctrl=True)
    touched = {}
    for idname, value, variants, keep in SELECT_RULES:
        kms = kd.rewrite_modifier_set(idname, value, variants, keep_props=keep)
        if not kms:
            if not patch.STRICT:   # another Blender's IC data (step 53)
                patch.DRIFT.append(f"selection patch: {idname} {value} not found")
                continue
            raise LookupError(f"selection patch: {idname} {value} not found in IC data")
        touched[(idname, value)] = kms
    patch_select_2d(kd, touched)
    return touched


# Step 170: first-place operators that apply the measured Maya rule around Blender's own selection
# (operators/select_2d.py). (keymap family key, editor, [(shift, ctrl, rule)]) for clicks; boxes: Shift = XOR.
SELECT_2D_CLICKS = ((("graph.clickselect", "PRESS"), 'GRAPH', ((False, False, 'KEEP'), (False, True, 'CTRL'),
                                                               (True, True, 'ADD'))),
                    (("action.clickselect", "PRESS"), 'DOPE', ((False, True, 'DESELECT'), (True, True, 'ADD'))),
                    (("outliner.item_activate", "CLICK"), 'OUTLINER', ((False, True, 'TOGGLE'),)))
SELECT_2D_BOXES = ((("graph.select_box", "CLICK_DRAG"), 'GRAPH'), (("action.select_box", "CLICK_DRAG"), 'DOPE'),
                   (("uv.select_box", "CLICK_DRAG"), 'UV'))


SELECT_2D_KEYMAPS = set()      # keymaps that got a select_2d box item (tests: their shadowing stacks)


def patch_select_2d(kd, touched):
    for key, editor, variants in SELECT_2D_CLICKS:
        for km in touched.get(key, ()):
            if km not in ("Graph Editor", "Dopesheet", "Outliner"):          # tool keymaps keep Blender's items
                continue
            for shift, ctrl, rule in variants:
                _add(kd, km, "allset.select_2d_click", make_event("LEFTMOUSE", key[1], shift=shift, ctrl=ctrl),
                     {"editor": editor, "rule": rule}, shadows=(km, "Screen", "View2D"), first=True)
    for key, editor in SELECT_2D_BOXES:
        for km in touched.get(key, ()):
            _add(kd, km, "allset.select_2d_box", make_event("LEFTMOUSE", "CLICK_DRAG", shift=True),
                 {"editor": editor}, shadows=(km,), first=True)
            SELECT_2D_KEYMAPS.add(km)


# --- 2. 4/5/6/7 display modes ---------------------------------------------
# Maya: 4 wireframe, 5 shaded, 6 shaded+textured, 7 all lights
# (research/maya/interaction.md:174-177; hotkeys_default.json "4".."7").

DISPLAY_KEYS = (("FOUR", "WIREFRAME"), ("FIVE", "SHADED"),
                ("SIX", "TEXTURED"), ("SEVEN", "LIGHTS"))


def patch_display(kd):
    # IC:3458-3459 "Object Non-modal": 4 = object mode, 5 = mode pie.
    kd.remove("Object Non-modal", "object.mode_set", type="FOUR")
    kd.remove("Object Non-modal", "wm.call_menu_pie", type="FIVE")
    for key, mode in DISPLAY_KEYS:
        _add(kd, "3D View", "allset.display_mode", make_event(key), {"mode": mode})
    # Losing 4 = object mode leaves no quick way out of edit mode; Maya's F8
    # toggles object <-> last component mode (research/maya/interaction.md:73).
    # allset.toggle_sel_mode = editmode_toggle + Maya's in-view message (step 72).
    _add(kd, "Object Non-modal", "allset.toggle_sel_mode", make_event("F8"))


# --- 3. Ctrl+G group --------------------------------------------------------
# Maya Ctrl+G = group under common parent, pivot at origin
# (research/maya/concepts.md:89-91). IC Ctrl+G = move to collection (IC:2547; Blender 5.x: the same as a
# wm.call_menu of OBJECT_MT_move_to_collection, step 53), so the item is removed whatever its operator.

def patch_group(kd):
    for km in ("Object Mode", "Outliner"):
        kd.remove(km, None, type="G", ctrl=True)
        _add(kd, km, "allset.group", make_event("G", ctrl=True))


# --- 4. Space reserved for the hotbox ---------------------------------------
# Maya Space = hotbox (research/maya/hotkeys_default.json "Space" ShowHotbox),
# implemented in step 10; until then Space does nothing in other editors.
# Playback moves to Maya's Alt+V (PlaybackToggle) and Alt+Shift+V (GoToMinFrame).

def patch_space(kd):
    kd.remove("Frames", "screen.animation_play", type="SPACE")  # IC:2258
    _add(kd, "Frames", "screen.animation_play", make_event("V", alt=True))
    _add(kd, "Frames", "screen.frame_jump", make_event("V", alt=True, shift=True), {"end": False})


# --- 5. Hold keys: X/C/V/J snapping ------------------------------------------
# Maya: snapping only while the key is held, Shift variants identical
# (research/maya/interaction.md:141-143; hotkeys_default.json x/X, c/C, v/V, j).
# Paint/sculpt modes keep their own X (brush color flip): they are checked
# before "3D View", so the hold never runs there.
_PAINT_MODES = ("Sculpt", "Vertex Paint", "Image Paint", "Weight Paint")

HOLD_KEYS = (("X", "grid"), ("C", "curve"), ("V", "point"), ("J", "step"))


def patch_hold_snap(kd):
    kd.remove("3D View", "wm.context_toggle", type="X")                 # IC:780 snap toggle
    kd.remove("3D View", "wm.call_menu_pie", type="X", shift=True)      # snap pie
    kd.remove("3D View", "wm.call_menu_pie", type="V")                  # view pie
    for km in ("Object Mode", "Mesh", "Curve", "Curves", "Armature", "Metaball"):
        kd.remove(km, "wm.tool_set_by_id", type="C")                     # cursor tool
    for key, name in HOLD_KEYS:
        for shift in (False, True):
            _add(kd, "3D View", "allset.hold", make_event(key, shift=shift), {"name": name},
                 shadows=_PAINT_MODES)


# --- 6. B soft select (tap toggle, hold + LMB drag radius) ------------------
# research/maya/interaction.md:155-156.

def patch_soft_select(kd):
    for km in ("Object Mode", "Mesh", "Curve", "Curves", "Metaball", "Lattice", "Particle"):
        kd.remove(km, "wm.context_toggle", type="B")                     # IC:2517, IC:3066
    _add(kd, "3D View", "allset.tap_hold", make_event("B"), {"binding": "soft_select"},
         shadows=_PAINT_MODES)


# --- 7. A tap / hold, D hold pivot, Insert pivot toggle ---------------------
# A: research/maya/interaction.md:27 (tap = FrameAll, hold = marking menu).
# D / Insert: interaction.md:124-125 (pivot edit while held / toggle).

def patch_tap_hold_and_pivot(kd):
    kd.remove("3D View", "view3d.view_all", type="A")
    _add(kd, "3D View", "allset.tap_hold", make_event("A"), {"binding": "select_all"},
         shadows=("Sculpt",))
    kd.remove("Object Mode", "wm.tool_set_by_id", type="D")              # IC:121 annotate
    _add(kd, "Object Mode", "allset.hold", make_event("D"), {"name": "pivot"})
    _add(kd, "Object Mode", "allset.pivot_toggle", make_event("INSERT"))
    # Pivot picking precedes normal/cursor selection only during custom pivot edit.
    for km in ("3D View", "3D View Tool: Cursor"):
        _add(kd, km, "allset.pivot_pick", make_event("LEFTMOUSE", any=True), first=True)


# --- 8. Arrow-key pick-walk (object mode) -----------------------------------
# research/maya/interaction.md:76 (Maya default hotkeys). IC puts Left/Right frame
# stepping into each mode keymap (IC:93-97 _template_items_animation); only
# Object Mode's copy is replaced. Maya steps frames with Alt+,/. (step 7).

PICK_WALK_KEYS = (("UP_ARROW", "UP"), ("DOWN_ARROW", "DOWN"),
                  ("LEFT_ARROW", "LEFT"), ("RIGHT_ARROW", "RIGHT"))


def patch_pick_walk(kd):
    kd.remove("Object Mode", "object.select_more", type="UP_ARROW")
    kd.remove("Object Mode", "object.select_less", type="DOWN_ARROW")
    kd.remove("Object Mode", "screen.frame_offset", type="LEFT_ARROW")
    kd.remove("Object Mode", "screen.frame_offset", type="RIGHT_ARROW")
    for key, direction in PICK_WALK_KEYS:
        _add(kd, "Object Mode", "allset.pick_walk", make_event(key, repeat=True),
             {"direction": direction})


# --- 9. Camera: ortho tumble lock, framing in all views ----------------------
# research/maya/interaction.md:40 (Alt+LMB tumble), :192-195 (Shift+F / Shift+A).

def patch_camera(kd):
    kd.remove("3D View", "view3d.rotate", type="LEFTMOUSE", alt=True)       # IC:674
    _add(kd, "3D View", "allset.tumble", make_event("LEFTMOUSE", alt=True))
    # Alt+RMB dolly reads the drag itself: Blender's zoom axis is a preference the kit no longer sets (#51, step 130)
    kd.remove("3D View", "view3d.zoom", type="RIGHTMOUSE", alt=True)       # IC:433 (ic_4_5)
    _add(kd, "3D View", "allset.dolly", make_event("RIGHTMOUSE", alt=True),
         shadows=("Image Paint", "Vertex Paint", "Sculpt"))     # their Alt+RMB stencil control stays, as before
    # UV / Image Editor: the same left / right dolly instead of IC image.view_zoom (Zoom Axis preference; step 141 B4).
    # Graph Editor / Dope Sheet keep View2D view2d.zoom: it zooms each axis by its own drag (right = in), no
    # preference involved (delegated, docs/steps/step_141_keys.md).
    kd.remove("Image", "image.view_zoom", type="RIGHTMOUSE", alt=True)
    _add(kd, "Image", "allset.dolly_2d", make_event("RIGHTMOUSE", alt=True), shadows=("View2D",))  # Image runs first
    kd.remove("3D View", "view3d.view_center_pick", type="F", shift=True)
    _add(kd, "3D View", "allset.frame_all_views", make_event("F", shift=True), {"selected": True})
    # Step 17: Maya fit (factor 0.95, sidebar excluded) for F and Ctrl+Shift+F (with children);
    # A tap goes through taphold.SelectAllBinding (research/maya/interaction.md:191-196).
    kd.remove("3D View", "view3d.view_selected", type="F")                  # IC:681
    _add(kd, "3D View", "allset.frame", make_event("F"), {"selected": True})
    _add(kd, "3D View", "allset.frame_all_views", make_event("F", shift=True, ctrl=True),
         {"selected": True, "children": True})
    kd.remove("3D View", "view3d.view_all", type="A", shift=True)
    _add(kd, "3D View", "allset.frame_all_views", make_event("A", shift=True), {"selected": False},
         shadows=("Sculpt",))


# --- 10. View-change undo: [ ] and Alt+Z / Alt+Y ----------------------------
# research/maya/interaction.md:48 (Maya default hotkeys). IC [ ] = select_hierarchy
# (IC:2506-2512), replaced by the arrow pick-walk in step 3. Paint modes keep
# [ ] for brush size.

def patch_view_history(kd):
    kd.remove("Object Mode", "object.select_hierarchy", type="LEFT_BRACKET")
    kd.remove("Object Mode", "object.select_hierarchy", type="RIGHT_BRACKET")
    for ev, direction in ((make_event("LEFT_BRACKET"), "UNDO"), (make_event("RIGHT_BRACKET"), "REDO"),
                          (make_event("Z", alt=True), "UNDO"), (make_event("Y", alt=True), "REDO")):
        _add(kd, "3D View", "allset.view_history", ev, {"direction": direction},
             shadows=_PAINT_MODES + ("Armature",))


# --- 11. Space tap = four views, Ctrl+Space = full screen -------------------
# research/maya/interaction.md:248-249. Space hold = hotbox (step 10).

# Space = hotbox (step 9; tap = pane toggle, Maya 2022 hotbox). Also in the editors
# the hotbox South zone switches a pane to, so the hotbox can switch it back; Space is
# free there since patch_space (IC used it only in "Frames"). Not in text editors.
HOTBOX_KEYMAPS = ("3D View", "Outliner", "Graph Editor", "Dopesheet", "Node Editor", "Image")


def patch_space_tap(kd):
    for km in HOTBOX_KEYMAPS:
        _add(kd, km, "allset.hotbox", make_event("SPACE"))
    _add(kd, "Screen", "screen.screen_full_area", make_event("SPACE", ctrl=True),
         {"use_hide_panels": True})


# --- 12. 1/2/3 smooth mesh preview -------------------------------------------
# research/maya/interaction.md:166-172. IC 1/2/3 = component modes
# (IC:2558-2563 Object Mode, IC:164-177 Mesh), now on F9-F11.

SMOOTH_KEYS = (("ONE", 1), ("TWO", 2), ("THREE", 3))


def patch_smooth_preview(kd):
    for key, level in SMOOTH_KEYS:
        kd.remove("Object Mode", "object.mode_set_with_submode", type=key)
        kd.remove("Mesh", "mesh.select_mode", type=key)
        for km in ("Object Mode", "Mesh"):
            _add(kd, km, "allset.smooth_preview", make_event(key), {"level": level})


# --- 13. F7/F9/F10/F11 component modes ---------------------------------------
# research/maya/interaction.md:73-74. F8 = editmode_toggle (patch 2).

COMPONENT_KEYS = (("F9", "VERT"), ("F10", "EDGE"), ("F11", "FACE"), ("F7", "MULTI"))


def patch_component_keys(kd):
    for key, comp in COMPONENT_KEYS:
        _add(kd, "Object Non-modal", "allset.component_mode", make_event(key), {"type": comp})


# --- 14. Channel Box MMB virtual slider ---------------------------------------
# research/maya/channel_box.md:73-78. Tool keymaps run before "3D View" and IC
# gives Move/Rotate/Scale/Transform an MMB drag (IC:3823-3858), so the slider
# goes first in those; it passes through when no channel is selected.

SLIDER_TOOL_KEYMAPS = ("3D View Tool: Move", "3D View Tool: Rotate", "3D View Tool: Scale",
                       "3D View Tool: Transform")


def patch_cb_slider(kd):
    for km in SLIDER_TOOL_KEYMAPS:
        _add(kd, km, "allset.cb_virtual_slider", make_event("MIDDLEMOUSE"), first=True,
             shadows=(km,))
    _add(kd, "Object Mode", "allset.cb_virtual_slider", make_event("MIDDLEMOUSE"))
    # Channel Box rows: drag over names / fields selects a range (the dock is a Properties editor, step 116;
    # ui/channel_box.ALLSET_OT_cb_hover, docs/steps/step_129_cb.md 「계획」 #6)
    _add(kd, "Property Editor", "allset.cb_hover", make_event("MOUSEMOVE", "ANY", any=True), first=True)
    # Paint Skin Weights numeric labels around the brush need the pointer (ui/weight_numbers.py, step 224)
    _add(kd, "Weight Paint", "allset.weight_numbers_hover", make_event("MOUSEMOVE", "ANY", any=True), first=True)
    # The Channel Box part of the dock scrolls by itself, the Layer Editor below stays (Maya's fixed split, step 135
    # #55); passes through outside an overflowing Channel Box
    for wheel in ("WHEELUPMOUSE", "WHEELDOWNMOUSE"):
        # the region's "View2D Buttons List" handler runs before "Property Editor" (buttons_main_region_init adds
        # it first) and scrolls the whole region on the wheel, so the item sits first in that keymap
        _add(kd, "View2D Buttons List", "allset.cb_scroll", make_event(wheel), first=True,
             shadows=("View2D Buttons List",))   # first + PASS_THROUGH over view2d.scroll_up / _down
    # Maya's vertical tab strip on the dock's right edge (step 142, #78; ui/maya_dock.draw_strip): drawn, not buttons,
    # so a click there reaches the keymaps; first in the region's earliest keymap (its scroller sits on that edge)
    _add(kd, "View2D Buttons List", "allset.dock_strip_click", make_event("LEFTMOUSE"), first=True,
         shadows=("View2D Buttons List", "Property Editor", "Screen"))   # PASS_THROUGH off the strip
    # Hypershade Browser: MMB-drag a material swatch onto an object = assign it (step 162, ui/hs_drag.py); the region's
    # view2d.pan / scroller_activate take MMB PRESS in this keymap, so the item goes first and passes through off a
    # swatch
    _add(kd, "View2D Buttons List", "allset.hs_swatch_drag", make_event("MIDDLEMOUSE"), first=True,
         shadows=("View2D Buttons List",))


# --- 15. Marking menus (pies) and Q/W/E/R hold + LMB (docs/steps/step_8.md 「계획」 2-4) ----
# research/maya/hotkeys_and_menus.md §5.1 (:227-243). IC's RMB context menus in these
# modes give way to the Maya marking menus; Shift+RMB 3D cursor goes (no 3D cursor in Maya).

MM_KEYMAPS = (("Object Mode", "VIEW3D_MT_object_context_menu"),
              ("Mesh", "VIEW3D_MT_edit_mesh_context_menu"),
              ("Curve", "VIEW3D_MT_edit_curve_context_menu"))
MM_EVENTS = (("RMB", {}), ("SHIFT_RMB", {"shift": True}), ("CTRL_RMB", {"ctrl": True}),
             ("TOOL_OPTIONS", {"shift": True, "ctrl": True}))
# Modes whose IC keymap sets the Q/W/E/R tools (IC _template_items_tool_select etc.).
TOOL_KEY_KEYMAPS = ("Object Mode", "Mesh", "Curve", "Armature", "Pose", "Metaball", "Lattice", "Curves")
TOOL_KEYS = (("Q", "tool_select"), ("W", "tool_move"), ("E", "tool_rotate"), ("R", "tool_scale"))


def patch_marking_menus(kd):
    for km, menu in MM_KEYMAPS:
        kd.remove(km, "wm.call_menu", type="RIGHTMOUSE")
        for trigger, mods in MM_EVENTS:
            _add(kd, km, "allset.marking_menu", make_event("RIGHTMOUSE", **mods), {"trigger": trigger})
    kd.remove("3D View", "view3d.cursor3d", type="RIGHTMOUSE", shift=True)
    kd.remove("3D View", "transform.translate", type="RIGHTMOUSE", value="CLICK_DRAG", shift=True)
    for km in TOOL_KEY_KEYMAPS:
        for key, binding in TOOL_KEYS:
            kd.remove(km, "wm.tool_set_by_id", type=key)
            _add(kd, km, "allset.tap_hold", make_event(key), {"binding": binding})


# --- 16. Scene concepts: P / Shift+P, Shift+D, Ctrl+Shift+D, Alt+Shift+D (docs/steps/step_10.md) ----
# research/maya/hotkeys_default.json: p Parent, P Unparent, D DuplicateWithTransform,
# Ctrl+D (capital) DuplicateSpecial, Alt+D (capital) DeleteHistory (concepts.md:68, :98).
# IC Object Mode P / Shift+P = object.parent_set / parent_clear.

def patch_concepts(kd):
    kd.remove("Object Mode", "object.parent_set", type="P")
    kd.remove("Object Mode", "object.parent_clear", type="P", shift=True)
    for km in ("Object Mode", "Outliner"):
        _add(kd, km, "allset.parent", make_event("P"))
        _add(kd, km, "allset.unparent", make_event("P", shift=True))
    # Ctrl+D: Maya Duplicate = in place, subtree, Maya names (docs/steps/step_19.md); IC
    # duplicate_move would name the copy pCube1.001 and start a move.
    kd.remove("Object Mode", "object.duplicate_move", type="D", ctrl=True)
    _add(kd, "Object Mode", "allset.duplicate", make_event("D", ctrl=True))
    # Component mode Ctrl+D (#17, step 129): Maya's Duplicate there copies nothing ("No object(s) to duplicate",
    # GUI-measured, docs/steps/step_129_audit_p1.md); IC mesh.duplicate_move copied the faces inside the mesh.
    kd.remove("Mesh", "mesh.duplicate_move", type="D", ctrl=True)
    _add(kd, "Mesh", "allset.component_command", make_event("D", ctrl=True), {"item": "Edit/Duplicate"})
    _add(kd, "Object Mode", "allset.duplicate_with_transform", make_event("D", shift=True))
    _add(kd, "Object Mode", "allset.duplicate_special", make_event("D", shift=True, ctrl=True))
    _add(kd, "Object Mode", "allset.delete_history", make_event("D", shift=True, alt=True))


# --- 17. Ctrl+A Attribute Editor / Channel Box, Ctrl+Shift+A / Alt+D (docs/steps/step_11.md) ----
# research/maya/hotkeys_default.json: Ctrl+a ShowAttributeEditorOrChannelBox, Ctrl+A (capital)
# SelectAll, Alt+d SelectNone. IC Object Mode Ctrl+A / Ctrl+Shift+A = select all / none.

def patch_attribute_editor(kd):
    kd.remove("Object Mode", "object.select_all", type="A", ctrl=True)
    kd.remove("Object Mode", "object.select_all", type="A", ctrl=True, shift=True)
    _add(kd, "Object Mode", "allset.ae_toggle", make_event("A", ctrl=True))
    _add(kd, "Object Mode", "object.select_all", make_event("A", ctrl=True, shift=True),
         {"action": 'SELECT'})
    _add(kd, "Object Mode", "allset.select_none", make_event("D", alt=True))
    # Ctrl+a is a global Maya hotkey (no editor context binds Ctrl+a, hotkeys_default.json): in every component /
    # pose mode IC's Ctrl+A select-all gives way to the AE / CB swap and Ctrl+Shift+A selects all (#65, step 141).
    for km, idname in CTRL_A_MODES:
        kd.remove(km, idname, type="A", ctrl=True)
        _add(kd, km, "allset.ae_toggle", make_event("A", ctrl=True))
        if km == "Mesh":                                         # Ctrl+Shift+A: patch_mesh_components
            continue
        if km != "Paint Vertex Selection (Weight, Vertex)":     # IC has no Ctrl+Shift+A there
            kd.remove(km, idname, type="A", ctrl=True, shift=True)
        _add(kd, km, idname, make_event("A", ctrl=True, shift=True), {"action": 'SELECT'})
    # Alt+D clears joints, latent bone selection, and the active object, releasing
    # pose/edit mode so the next click can select any object.
    _add(kd, "Pose", "allset.select_none", make_event("D", alt=True))
    for km in ("Curve", "Armature", "Metaball", "Lattice", "Curves", "Point Cloud"):
        _add(kd, km, "allset.select_none", make_event("D", alt=True))


# Keymaps whose Ctrl+A is IC select-all (keymap/ic_4_5.py; same in ic_5_0 – ic_5_2). Text / Console / Font /
# File Browser keep their text-style select-all; the 2D animation editors follow since step 150.
CTRL_A_MODES = (("Mesh", "mesh.select_all"), ("Pose", "pose.select_all"), ("Curve", "curve.select_all"),
                ("Armature", "armature.select_all"), ("Metaball", "mball.select_all"),
                ("Lattice", "lattice.select_all"), ("Particle", "particle.select_all"),
                ("Curves", "curves.select_all"), ("Sculpt Curves", "curves.select_all"),
                ("Point Cloud", "pointcloud.select_all"),
                ("Paint Face Mask (Weight, Vertex, Texture)", "paint.face_select_all"),
                ("Paint Vertex Selection (Weight, Vertex)", "paint.vert_select_all"),
                ("UV Editor", "uv.select_all"),
                # step 150 (#96): the 2D animation editors too — Maya's Ctrl+a is global (Graph Editor / Dope Sheet
                # included); IC Ctrl+A there = select all keys / channels, Ctrl+Shift+A = deselect
                ("Graph Editor", "graph.select_all"), ("Dopesheet", "action.select_all"),
                ("NLA Editor", "nla.select_all"), ("Animation Channels", "anim.channels_select_all"))


# --- 18. Undo / redo, visibility, isolate, invert (docs/steps/step_16.md 「계획」) ------------
# research/maya/interaction.md:220-221 (z / Shift+Z / Ctrl+Y), :233-240 (h, Ctrl+H, Alt+H,
# Shift+H, Ctrl+Shift+H, Ctrl+Alt+H, Ctrl+1), :76 (Ctrl+Shift+I).

# Editor keymaps run before "Screen": their z = zoom/viewer border would hide the undo.
_Z_BORDERS = (("3D View", "view3d.zoom_border"), ("View2D", "view2d.zoom_border"),
              ("Image", "image.view_zoom_border"), ("Node Editor", "node.viewer_border"))

VISIBILITY_KEYS = (("H", {}, "TOGGLE"), ("H", {"ctrl": True}, "HIDE"),
                   ("H", {"alt": True}, "HIDE_UNSELECTED"), ("H", {"shift": True}, "SHOW_SELECTED"),
                   ("H", {"ctrl": True, "shift": True}, "SHOW_LAST"))


def patch_undo_visibility(kd):
    for km, idname in _Z_BORDERS:
        kd.remove(km, idname, type="Z")
    _add(kd, "Screen", "ed.undo", make_event("Z"))
    _add(kd, "Screen", "ed.redo", make_event("Z", shift=True))
    _add(kd, "Screen", "ed.redo", make_event("Y", ctrl=True))

    # Object Mode: IC Ctrl+H hide, Shift+H hide unselected, Alt+H reveal (IC Object Mode).
    kd.remove("Object Mode", "object.hide_view_set", type="H", ctrl=True)
    kd.remove("Object Mode", "object.hide_view_set", type="H", shift=True)
    kd.remove("Object Mode", "object.hide_view_clear", type="H", alt=True)
    for key, mods, action in VISIBILITY_KEYS:
        _add(kd, "Object Mode", "allset.visibility", make_event(key, **mods), {"action": action})
    # Mesh components: hidden components can't be selected in Blender, so the "show"
    # keys reveal everything (and select it). IC Shift+H / Alt+H = hide unselected / reveal.
    kd.remove("Mesh", "mesh.hide", type="H", shift=True)
    kd.remove("Mesh", "mesh.reveal", type="H", alt=True)
    _add(kd, "Mesh", "mesh.hide", make_event("H", alt=True), {"unselected": True})
    for mods in ({"shift": True}, {"ctrl": True, "shift": True}, {"ctrl": True, "alt": True}):
        _add(kd, "Mesh", "mesh.reveal", make_event("H", **mods))

    # Ctrl+1 isolate select: local view without moving the camera; again = back.
    kd.remove("Mesh", "mesh.select_mode", type="ONE", ctrl=True)
    # step 164: isolating a group shows its children (Maya isolate select, research/maya/re/dag_164.md)
    _add(kd, "3D View", "allset.isolate", make_event("ONE", ctrl=True), shadows=("Sculpt",))
    # Maya Delete takes the selected hierarchy with it (dag_164.md "Delete"); Blender's leaves the children
    for key in ("DEL", "BACK_SPACE"):
        kd.remove("Object Mode", "object.delete", type=key)
        _add(kd, "Object Mode", "allset.delete", make_event(key))
        kd.remove("Outliner", "outliner.delete", type=key)
        _add(kd, "Outliner", "outliner.delete", make_event(key), {"hierarchy": True})

    _add(kd, "Object Mode", "object.select_all", make_event("I", ctrl=True, shift=True),
         {"action": 'INVERT'})
    _add(kd, "Mesh", "mesh.select_all", make_event("I", ctrl=True, shift=True), {"action": 'INVERT'})


# --- 19. Mesh component keys (docs/steps/step_18.md 「계획」) -------------------------------
# research/maya/interaction.md:75 (Ctrl+Shift+A / Alt+D), :79 (Ctrl+F9-F11 convert), :82 (> <,
# Ctrl: along loop), :124-129 (D component pivot); Maya default hotkeys Ctrl+E extrude, Ctrl+B bevel.

CONVERT_KEYS = (("F9", "VERT"), ("F10", "EDGE"), ("F11", "FACE"))


def patch_mesh_components(kd):
    kd.remove("Mesh", "wm.tool_set_by_id", type="D")                       # annotate tool
    _add(kd, "Mesh", "allset.hold", make_event("D"), {"name": "component_pivot"})
    # Insert = the same pivot edit as a toggle (research/maya/interaction.md:125, docs/steps/step_77.md)
    _add(kd, "Mesh", "allset.pivot_toggle", make_event("INSERT"))
    # step 243 (#160): D held / Insert on joints in Edit mode = Maya Preserve Children (move the joint only;
    # research/maya/re/joint_rig_2026_joint_math.md §3 `move -pcp`)
    kd.remove("Armature", "wm.tool_set_by_id", type="D")                   # annotate tool
    _add(kd, "Armature", "allset.hold", make_event("D"), {"name": "preserve_children"})
    _add(kd, "Armature", "allset.pivot_toggle", make_event("INSERT"))
    kd.remove("Mesh", "mesh.select_all", type="A", ctrl=True, shift=True)   # IC: deselect
    _add(kd, "Mesh", "mesh.select_all", make_event("A", ctrl=True, shift=True), {"action": 'SELECT'})
    _add(kd, "Mesh", "allset.select_none", make_event("D", alt=True))
    kd.remove("Mesh", "wm.tool_set_by_id", type="E", ctrl=True)            # extrude tool
    # Maya polyExtrudeFace: zero-length extrusion + manipulator / In-View Editor (step 65); edges and
    # vertices = polyExtrudeEdge / polyExtrudeVertex at once (step 139). Ctrl+B = polyBevel3 at once.
    _add(kd, "Mesh", "allset.extrude", make_event("E", ctrl=True))
    kd.remove("Mesh", "wm.tool_set_by_id", type="B", ctrl=True)            # bevel tool
    _add(kd, "Mesh", "allset.bevel", make_event("B", ctrl=True))
    _add(kd, "Mesh", "mesh.select_more", make_event("PERIOD", shift=True, repeat=True))
    _add(kd, "Mesh", "mesh.select_less", make_event("COMMA", shift=True, repeat=True))
    _add(kd, "Mesh", "mesh.select_next_item", make_event("PERIOD", shift=True, ctrl=True, repeat=True))
    _add(kd, "Mesh", "mesh.select_prev_item", make_event("COMMA", shift=True, ctrl=True, repeat=True))
    for key, comp in CONVERT_KEYS:
        _add(kd, "Mesh", "allset.convert_selection", make_event(key, ctrl=True), {"type": comp})
    # Maya double-click = loop, Shift+double-click = the run between two picks (issue #22, operators/loop_pick.py);
    # IC's own double-click loop picks (Shift = add the loop) give way, Ctrl (deselect the loop) stays
    for shift in (False, True):
        kd.remove("Mesh", "mesh.loop_select", type="LEFTMOUSE", value="DOUBLE_CLICK", shift=shift)
        _add(kd, "Mesh", "allset.loop_pick", make_event("LEFTMOUSE", value="DOUBLE_CLICK", shift=shift),
             {"between": shift}, shadows=("Screen",))


# --- 20. Key / frame stepping: . , Alt+. Alt+, (docs/steps/step_20.md 「계획」 1) -----------------
# Maya factory hotkeys (NextKey, PreviousKey, NextFrame, PreviousFrame) via docs/keymap_mapping.md.
# "Frames" is in nearly every editor; the 3D View / Image pies on . , go (pivot and orientation stay
# in the headers). The Outliner (show active) and Clip Editor (pivot pie) keep their own . first.

def patch_key_stepping(kd):
    kd.remove("3D View", "wm.call_menu_pie", type="PERIOD")      # pivot pie
    kd.remove("3D View", "wm.call_menu_pie", type="COMMA")       # orientation pie
    kd.remove("Image", "wm.call_menu_pie", type="PERIOD")        # UV pivot pie
    keep = ("Outliner", "Clip Editor")
    _add(kd, "Frames", "screen.keyframe_jump", make_event("PERIOD"), {"next": True}, shadows=keep)
    _add(kd, "Frames", "screen.keyframe_jump", make_event("COMMA"), {"next": False}, shadows=keep)
    _add(kd, "Frames", "screen.frame_offset", make_event("PERIOD", alt=True, repeat=True), {"delta": 1})
    _add(kd, "Frames", "screen.frame_offset", make_event("COMMA", alt=True, repeat=True), {"delta": -1})


# --- 21. Shift+drag a manipulator = Smart Duplicate (docs/steps/step_22.md 「계획」) ----------------
# research/maya/interaction.md:107. The C transform gizmo runs gizmogroup.gizmo_tweak
# from these keymaps for any Shift/Ctrl (IC:3703-3721); our item goes first, duplicates the selection
# and passes the same event on, so the gizmo moves the copies. Shift held during a transform was
# Blender's precision (IC:3611-3612): Maya has none, so precision moves to Alt (delegated).

GIZMO_KEYMAPS = ("Generic Gizmo Maybe Drag", "Generic Gizmo Drag")


def patch_manip_duplicate(kd):
    for km in GIZMO_KEYMAPS:
        _add(kd, km, "allset.manip_duplicate", make_event("LEFTMOUSE", "PRESS", shift=True),
             first=True)
        # Step 261 (#175): IC's gizmo_tweak CLICK_DRAG allows no Shift (IC:107-110, unlike
        # blender_default.py:500-503 any_except("alt")), and a CLICK_DRAG carries the press's
        # modifiers (wm_event_system.cc 4.5 :3644), so the real Shift+drag matched no gizmo item and
        # the copy / extrusion was taken back. Shift "any"; Ctrl / Alt stay as IC has them.
        found = kd.find(km, "gizmogroup.gizmo_tweak", type="LEFTMOUSE", value="CLICK_DRAG")
        if not found:
            if not patch.STRICT:
                patch.DRIFT.append(f"{km}: no item gizmogroup.gizmo_tweak CLICK_DRAG")
                continue
            raise LookupError(f"{km}: no item gizmogroup.gizmo_tweak CLICK_DRAG")
        for item in found:
            item[1]["shift"] = -1


# --- 22. Delete / Backspace on components (docs/steps/step_24.md 「계획」) ------------------------
# Maya deletes the selected faces / edges / vertices right away (runtime_commands.json Delete,
# DeleteEdge, DeleteVertex); IC opens the Delete menu (IC:3061-3062). Ctrl+Delete / Ctrl+Backspace
# keep IC's mesh.dissolve_mode = Maya DeletePolyElements (Maya factory hotkeys).

def patch_component_delete(kd):
    for key in ("DEL", "BACK_SPACE"):
        kd.remove("Mesh", "wm.call_menu", type=key)
        _add(kd, "Mesh", "allset.delete_components", make_event(key))


# --- 23. Manipulator size, smoothing level, default view, wireframe on shaded -------------------
# Maya factory hotkeys = Shift++ -, PgUp/PgDn, 0, Home, Alt+5
# via docs/keymap_mapping.md; docs/steps/step_27.md 「계획」.

def patch_view_keys(kd):
    for ev, factor in ((make_event("EQUAL"), 1.25), (make_event("EQUAL", shift=True), 1.25),
                       (make_event("MINUS"), 0.8)):
        _add(kd, "3D View", "allset.manip_size", ev, {"factor": factor})
    # Text edit mode keeps Home = line start (Font keymap runs first).
    _add(kd, "3D View", "allset.view_home", make_event("HOME"), shadows=("Font",))
    _add(kd, "3D View", "wm.context_toggle", make_event("FIVE", alt=True),
         {"data_path": "space_data.overlay.show_wireframes"})
    for km in ("Object Mode", "Mesh"):
        _add(kd, km, "allset.smooth_level", make_event("PAGE_UP", repeat=True), {"delta": 1})
        _add(kd, km, "allset.smooth_level", make_event("PAGE_DOWN", repeat=True), {"delta": -1})
        _add(kd, km, "allset.smooth_preview", make_event("ZERO"), {"level": 1})


# --- 24. MMB drag = the last picked manipulator handle (docs/steps/step_28.md 「계획」) ------------
# research/maya/interaction.md:103 (manipsRememberActiveHandle). A plain LMB press on the gizmo
# remembers the handle (after the drag); the tool keymaps' MMB press (IC: free transform) uses it.
# The Channel Box MMB slider (patch 14) stays in front.

MMB_TOOLS = (("3D View Tool: Move", "transform.translate", 'TRANSLATE'),
             ("3D View Tool: Rotate", "transform.rotate", 'ROTATE'),
             ("3D View Tool: Scale", "transform.resize", 'RESIZE'))


def patch_active_handle(kd):
    for km in GIZMO_KEYMAPS:
        _add(kd, km, "allset.manip_press", make_event("LEFTMOUSE", "PRESS"), first=True)
    for km, idname, mode in MMB_TOOLS:
        items = kd.items(km)
        old = kd.find(km, idname, type="MIDDLEMOUSE")
        if not old:
            if not patch.STRICT:
                patch.DRIFT.append(f"{km}: no MMB {idname}")
                continue
            raise LookupError(f"{km}: no MMB {idname}")
        at = next(i for i, it in enumerate(items) if it is old[0])
        kd.remove(km, idname, type="MIDDLEMOUSE")
        item = kd.add(km, "allset.manip_mmb", make_event("MIDDLEMOUSE"), {"mode": mode})
        items.remove(item)
        items.insert(at, item)      # same place: after the Channel Box slider
        ADDED.append((km, "allset.manip_mmb", make_event("MIDDLEMOUSE"), {"mode": mode}, (km,)))


# --- 25. Shift+T Assign New Material (docs/steps/step_29.md) -------------------------------------
# Maya factory hotkey, research/maya/hotkeys_and_menus.md:135. IC binds Shift+T only in the
# Dope Sheet.

def patch_materials(kd):
    for km in ("Object Mode", "Mesh"):
        _add(kd, km, "allset.assign_new_material", make_event("T", shift=True))


# --- 26. Marquee selects occluded components (docs/steps/step_30.md 「계획」 1) -----------------
# Maya optionVar selectPrefUseDepth false (research/maya/interaction.md:68). In front of every LMB drag
# box / lasso item of the select tools (and their fallbacks under Move/Rotate/Scale): sets the
# view's X-ray flag for the drag, then PASS_THROUGH to view3d.select_box / select_lasso.
SELECT_DRAG_KEYMAPS = ("3D View Tool: Select Box", "3D View Tool: Select Box (fallback)",
                       "3D View Tool: Select Lasso", "3D View Tool: Select Lasso (fallback)")


def patch_select_through(kd):
    for km in SELECT_DRAG_KEYMAPS:
        for shift, ctrl in ((False, False), (True, False), (False, True), (True, True)):
            _add(kd, km, "allset.select_through",
                 make_event("LEFTMOUSE", "CLICK_DRAG", shift=shift, ctrl=ctrl), first=True,
                 shadows=(km,))   # in front of the select item on purpose (PASS_THROUGH)


# Step 256 (#172): Maya UV Shell selection (operators/uv_shell_select.py) — a click picks the whole UV shell, a box /
# lasso grows to shells; in front of the click / drag select items of the 3D View and the UV Editor, PASS_THROUGH
# unless the UV Shell mask is on (research/maya/re/uv_shell_select_256.md §2, §7).
UV_SHELL_CLICK_KEYMAPS = ("3D View", "UV Editor")
UV_SHELL_DRAG_KEYMAPS = SELECT_DRAG_KEYMAPS + ("Image Editor Tool: Uv, Select Box",
                                              "Image Editor Tool: Uv, Select Box (fallback)",
                                              "Image Editor Tool: Uv, Select Lasso",
                                              "Image Editor Tool: Uv, Select Lasso (fallback)")


def patch_uv_shell_select(kd):
    mods = ((False, False), (True, False), (False, True), (True, True))
    for km in UV_SHELL_CLICK_KEYMAPS:
        for shift, ctrl in mods:
            _add(kd, km, "allset.uv_shell_pick", make_event("LEFTMOUSE", "CLICK", shift=shift, ctrl=ctrl),
                 first=True, shadows=(km,))   # in front of view3d.select / uv.select on purpose (PASS_THROUGH)
    for km in UV_SHELL_DRAG_KEYMAPS:
        for shift, ctrl in mods:
            _add(kd, km, "allset.uv_shell_box", make_event("LEFTMOUSE", "CLICK_DRAG", shift=shift, ctrl=ctrl),
                 first=True, shadows=(km,))   # always PASS_THROUGH: Blender's box runs, the kit grows it after


# Step 49: a click under the Tool Box column's tools reaches that narrow 3D View's WINDOW region,
# where view3d.select would deselect everything (it deselects hidden object types too). The guard
# swallows the click there and passes it through everywhere else (ui/toolbox.py).
def patch_toolbox_guard(kd):
    for shift, ctrl in ((False, False), (True, False), (False, True), (True, True)):
        _add(kd, "3D View", "allset.toolbox_guard", make_event("LEFTMOUSE", "CLICK", shift=shift, ctrl=ctrl),
             first=True, shadows=("3D View",))   # in front of view3d.select on purpose (PASS_THROUGH)


# Step 76: Maya selection priority (research/maya/interaction.md:74) — in front of the object-mode click
# select items ("3D View" CLICK, Tweak tool PRESS); passes through outside object mode and when no IK
# handle / joint / curve is under the mouse (operators/select_priority.py).
SELECT_PRIORITY_ITEMS = (("3D View", "CLICK"), ("3D View Tool: Tweak", "PRESS"))


def patch_select_priority(kd):
    for km, value in SELECT_PRIORITY_ITEMS:
        for shift, ctrl in ((False, False), (True, False), (False, True), (True, True)):
            _add(kd, km, "allset.select_priority", make_event("LEFTMOUSE", value, shift=shift, ctrl=ctrl),
                 first=True, shadows=(km,))   # in front of view3d.select on purpose (PASS_THROUGH)


# --- 27. Maya key batch (docs/steps/step_35.md 「계획」) -------------------------------------------
# Ctrl+Alt+LMB box zoom (interaction.md:43), Ctrl+T Universal Manipulator, Y last non-sacred
# tool, Ctrl+Shift+X Multi-Cut / Ctrl+Shift+Q Quad Draw, F2-F6 menu sets
# (IC's 3D View F2 right / F3 top / F4 camera / F5 orbit go, F1 and Ctrl+F1-F3 stay),
# Return: IC's 3D View rename popover goes (Blender modal tools confirm with their own Return).

# Editors whose own F2-F6 keys stay (they run before Screen): Image / UV zoom ratios, File Browser rename.
MENU_SET_SHADOWS = ("Image", "File Browser")


def patch_key_batch(kd):
    # Blender 5.x IC binds Ctrl+Alt+LMB in Sculpt mode too: there the sculpt stroke wins (Maya has no such
    # mode; step 53).
    _add(kd, "3D View", "allset.box_zoom", make_event("LEFTMOUSE", ctrl=True, alt=True), shadows=("Sculpt",))
    for km in ("Object Mode", "Mesh"):
        _add(kd, km, "wm.tool_set_by_id", make_event("T", ctrl=True), {"name": "builtin.transform"})
        _add(kd, km, "allset.last_tool", make_event("Y"))
        _add(kd, km, "allset.menu_tool", make_event("X", shift=True, ctrl=True),
             {"tool": "allset.multi_cut_tool", "edit": True})     # step 129: the kit Multi-Cut tool
        _add(kd, km, "allset.quad_draw_start", make_event("Q", shift=True, ctrl=True))   # step 144: kit Quad Draw
    kd.remove("3D View", "view3d.view_axis", type="F2")
    kd.remove("3D View", "view3d.view_axis", type="F3")
    kd.remove("3D View", "view3d.view_camera", type="F4")
    kd.remove("3D View", "view3d.view_orbit", type="F5")
    kd.remove("3D View", "wm.call_panel", type="RET")
    for key, set_id in (('F2', 'modelingMenuSet'), ('F3', 'riggingMenuSet'), ('F4', 'animationMenuSet'),
                        ('F5', 'dynamicsMenuSet'), ('F6', 'renderingMenuSet')):
        _add(kd, "Screen", "allset.menu_set", make_event(key), {"set": set_id},
             shadows=MENU_SET_SHADOWS)


# --- 28. Component pick-walk, Alt+Shift axis-locked navigation (docs/steps/step_39.md 「계획」) ------
# Arrows in edit mode walk vertices / edges / faces (Maya factory arrow keys, Maya pick-walk); IC's Up/Down
# grow/shrink go (Maya: Shift+> / <, step 18). Alt+Shift+LMB / MMB = tumble / track on one axis
# (interaction.md:46); IC's Alt+Shift+LMB click-select toggle goes (a PRESS item would hide it anyway).

AXIS_LOCK_SHADOWS = ("Weight Paint", "Paint Face Mask (Weight, Vertex, Texture)",
                     "Paint Vertex Selection (Weight, Vertex)")


def patch_component_pick_walk(kd):
    kd.remove("Mesh", "mesh.select_more", type="UP_ARROW")
    kd.remove("Mesh", "mesh.select_less", type="DOWN_ARROW")
    for key, direction in PICK_WALK_KEYS:
        _add(kd, "Mesh", "allset.pick_walk_component", make_event(key, repeat=True),
             {"direction": direction})
    kd.remove("3D View", "view3d.select", type="LEFTMOUSE", value="CLICK", shift=True, alt=True)
    # Paint modes keep their own Alt+Shift+LMB select (they run before 3D View).
    _add(kd, "3D View", "allset.view_axis_lock", make_event("LEFTMOUSE", shift=True, alt=True),
         {"mode": "TUMBLE"}, shadows=AXIS_LOCK_SHADOWS)
    _add(kd, "3D View", "allset.view_axis_lock", make_event("MIDDLEMOUSE", shift=True, alt=True),
         {"mode": "TRACK"})


# --- 30. Joints = pose bones (docs/steps/step_55.md 「계획」 2) ---------------------------------
# Maya has no pose mode: picking a joint selects it (research/maya/workflows/rigging.md:136). Ctrl+Tab =
# pose mode toggle (Blender's default key for it; posemode_toggle returns PASS_THROUGH unless an
# armature is active, tmp/probe55, so Screen's Ctrl+Tab still gets the event); the Channel Box MMB
# slider works on joints.

def patch_pose_joints(kd):
    _add(kd, "Object Non-modal", "object.posemode_toggle", make_event("TAB", ctrl=True), shadows=("Screen",))
    _add(kd, "Pose", "allset.cb_virtual_slider", make_event("MIDDLEMOUSE"))


# --- 31. Time Slider and keys (docs/steps/step_56.md 「계획」 1-5) ---------------------------------
# research/maya/workflows/animation.md §5. The timeline is a Dope Sheet mode: the Maya Time Slider
# mouse (LMB time, Shift+LMB range, MMB time + notice, RMB menu) goes first in "Dopesheet" and passes
# through in the Dope Sheet. K (Time Dragger, Maya factory hotkey) is global ("Screen"); editor keymaps
# run first, so their plain K goes: Mesh knife tool cycle (IC:3074; Multi-Cut = Ctrl+Shift+X) and
# Dope Sheet select_column (IC:1435). "User Interface" / Outliner K only act over a button / row.
# S (Maya Set Key) = every keyable channel, not IC's LocRotScale (IC:2463, :2536).

TIME_SLIDER_SHADOWS = ("Dopesheet", "View2D", "Screen")   # Screen: the step 73 Range Slider click


def patch_time_slider(kd):
    for shift in (False, True):
        _add(kd, "Dopesheet", "allset.time_scrub", make_event("LEFTMOUSE", shift=shift), {"range": shift},
             first=True, shadows=TIME_SLIDER_SHADOWS)
    _add(kd, "Dopesheet", "allset.time_scrub", make_event("MIDDLEMOUSE"), {"notice": True}, first=True,
         shadows=TIME_SLIDER_SHADOWS)
    _add(kd, "Dopesheet", "allset.time_slider_menu", make_event("RIGHTMOUSE"), first=True,
         shadows=TIME_SLIDER_SHADOWS)
    # Range Slider bar (step 73): a click on the empty label in the timeline header reaches the window
    # keymaps; the operator passes through anywhere but over the bar ui/range_bar.py drew.
    # Every editor keymap that uses the click runs first (intended: only unhandled clicks get here).
    for value in ("PRESS", "DOUBLE_CLICK"):
        under = tuple(n for n in kd.keymap_names() if n != "Screen" and kd.find(n, type="LEFTMOUSE", value=value))
        _add(kd, "Screen", "allset.range_bar_drag", make_event("LEFTMOUSE", value=value), shadows=under)
    kd.remove("Mesh", "wm.tool_set_by_id", type="K")
    kd.remove("Dopesheet", "action.select_column", type="K")
    _add(kd, "Screen", "allset.tap_hold", make_event("K"), {"binding": "time_drag"},
         shadows=("User Interface", "Outliner"))
    for km in ("Object Mode", "Pose"):
        kd.remove(km, "anim.keyframe_insert_by_name", type="S")
        _add(kd, km, "allset.set_key", make_event("S"))
        # Shift+W / E / R (step 151, #100): IC's keyframe_insert_by_name reports "Successfully added ... keying set";
        # the kit keys the Channel Box channels silently like Maya's SetKeyTranslate / Rotate / Scale
        for key, channels in (("W", "TRANSLATE"), ("E", "ROTATE"), ("R", "SCALE")):
            kd.remove(km, "anim.keyframe_insert_by_name", type=key, shift=True)
            _add(kd, km, "allset.set_key", make_event(key, shift=True), {"channels": channels})


# --- 32. Joints: pose-mode pick-walk, P / Shift+P (docs/steps/step_57.md 「계획」 3) ----------------------
# Maya arrows walk joints like objects (pickWalk, research/maya/workflows/rigging.md:24); IC Pose
# arrows = select_hierarchy (IC:2453-2459) and frame_offset Left/Right (frames are Alt+, / Alt+., step 20).
# Maya P parents joints keeping their place: IC Pose P = object.parent_set (IC:2434), Armature
# P / Shift+P = armature.parent_set / parent_clear menus (IC:3099-3100).

def patch_joints(kd):
    kd.remove("Pose", "pose.select_hierarchy", type="UP_ARROW")
    kd.remove("Pose", "pose.select_hierarchy", type="DOWN_ARROW")
    kd.remove("Pose", "screen.frame_offset", type="LEFT_ARROW")     # frames: Alt+, / Alt+. (step 20)
    kd.remove("Pose", "screen.frame_offset", type="RIGHT_ARROW")
    for key, direction in PICK_WALK_KEYS:
        _add(kd, "Pose", "allset.pick_walk_joint", make_event(key, repeat=True), {"direction": direction})
    kd.remove("Pose", "object.parent_set", type="P")
    kd.remove("Armature", "armature.parent_set", type="P")
    kd.remove("Armature", "armature.parent_clear", type="P", shift=True)
    for km in ("Pose", "Armature"):
        _add(kd, km, "allset.parent_joint", make_event("P"))
        _add(kd, km, "allset.unparent_joint", make_event("P", shift=True))


# --- 33. Multi-Cut: since step 129 a kit tool (operators/multi_cut.py, ui/mesh_tools.py) whose own tool keymap has
# Maya's Ctrl / Shift / Backspace handling, so Blender's knife keeps its own keys (the step 64 knife patches are gone).


# --- 34. UV workflow (docs/steps/step_66.md 「계획」 1-3) -------------------------------------------
# research/maya/workflows/uv.md §1-2; Maya UV Editor factory keys (docs/keymap_mapping.md
# UV Editor rows), F12 / Alt+F12. IC's UV Editor: Shift+X = snap pie (IC:613),
# Ctrl+L = select_linked (IC:599), RMB = context menu (IC:614); Maya has no shell-select key there.
UV_KM = "UV Editor"


def patch_uv(kd):
    kd.remove(UV_KM, "wm.call_menu", type="RIGHTMOUSE")
    for trigger, mods in (("RMB", {}), ("SHIFT_RMB", {"shift": True})):
        _add(kd, UV_KM, "allset.marking_menu", make_event("RIGHTMOUSE", **mods), {"trigger": trigger})
    kd.remove(UV_KM, "wm.call_menu_pie", type="X", shift=True)
    kd.remove(UV_KM, "uv.select_linked", type="L", ctrl=True)
    _add(kd, UV_KM, "allset.uv_cut", make_event("X", shift=True))
    _add(kd, UV_KM, "allset.uv_sew", make_event("S", shift=True))
    _add(kd, UV_KM, "allset.uv_unfold", make_event("U", ctrl=True))
    _add(kd, UV_KM, "allset.uv_layout", make_event("L", ctrl=True))
    for km in ("Object Mode", "Mesh"):
        _add(kd, km, "allset.uv_component", make_event("F12"), {"mode": 'UV'},
             shadows=("Screen",))      # step 214: Screen F12 = Blender render, Maya's F12 wins in the 3D View
        _add(kd, km, "allset.uv_component", make_event("F12", alt=True), {"mode": 'SHELL'})


# --- 36. Scene files (docs/steps/step_69.md 「계획」 1-3) --------------------------------------------------
# Maya default hotkeys Ctrl+O / Ctrl+S / Ctrl+Shift+S / Ctrl+Alt+S / Ctrl+R. IC binds the first four in "Window"
# (IC:194-199): replaced in place by the kit's (file dialogs start in the project's scenes folder; Ctrl+Alt+S =
# Maya's Increment and Save rule shot_v001 -> shot_v001.0001, not Blender's shot_v002). Ctrl+R = Create Reference;
# editor keymaps that bind Ctrl+R themselves keep it there (they run first).

SCENE_KEYS = (
    ("wm.open_mainfile", "allset.open_scene", {"ctrl": True}, "O"),
    ("wm.save_mainfile", "allset.save_scene", {"ctrl": True}, "S"),
    ("wm.save_as_mainfile", "allset.save_scene_as", {"ctrl": True, "shift": True}, "S"),
    ("wm.save_mainfile", "allset.increment_save", {"ctrl": True, "alt": True}, "S"),
)


def patch_scene_files(kd):
    for ic, kit, mods, key in SCENE_KEYS:
        kd.remove("Window", ic, type=key, **mods)
        _add(kd, "Window", kit, make_event(key, **mods))
    # Ctrl+N = Maya New Scene (Maya hotkey NewScene): IC's wm.read_homefile opens Blender's default file since step 130 removed
    # the app template copy; the kit's new_maya_scene reads the Maya layout file like File > New Scene (#44).
    kd.remove("Window", "wm.read_homefile", type="N", ctrl=True)
    _add(kd, "Window", "allset.new_maya_scene", make_event("N", ctrl=True), shadows=("Text",))  # Text: new text
    # Ctrl+R stays refresh / reload where an editor binds it (they run before Window items).
    _add(kd, "Window", "allset.create_reference", make_event("R", ctrl=True),
         shadows=("Image Generic", "File Browser", "File Browser Main", "Sequencer"))


# --- 37. Graph Editor keys, Shift+S tangent marking menu (docs/steps/step_70.md 「계획」 2-3) ----------------
# Maya default hotkeys: Graph Editor G = FramePlaybackRange, D = TangentAuto, Shift+S hold =
# KeyframeTangentMarkingMenu. G / D go in "Graph Editor" (it runs before Screen's G = repeat_last);
# Shift+S replaces IC's keyframe_insert menu in Object Mode / Pose (IC:2462, 2535) and is added to the Graph Editor
# and Dope Sheet. Mesh / UV Shift+S (UV Sew, step 66) stay.

def patch_graph_keys(kd):
    _add(kd, "Graph Editor", "anim.scene_range_frame", make_event("G"), shadows=("Screen",))   # over repeat_last
    _add(kd, "Graph Editor", "allset.set_tangent", make_event("D"), {"kind": "AUTO"})
    for km in ("Object Mode", "Pose"):
        kd.remove(km, "anim.keyframe_insert", type="S", shift=True)
    for km in ("Object Mode", "Pose", "Graph Editor", "Dopesheet"):
        _add(kd, km, "allset.tap_hold", make_event("S", shift=True), {"binding": "key_tangent"})


# --- 38. Key batch 2 (docs/steps/step_78.md) ------------------------------------------------------------
# Graph Editor 1/2/3, Shift+Q / Alt+Q select tool marking menus, Ctrl+Alt+Left/Right
# Spin Edge, Shift+G repeat at the mouse, Ctrl+Shift+C camera from view (Maya default hotkeys).
# IC has none of these events in these keymaps; same-event IC items elsewhere stay (editor keymaps run first):
# Shift+Q in Grease Pencil modes, Shift+G select similar / grouped in Armature, Metaball, Grease Pencil.
SELECT_MM_KEYMAPS = ("Object Mode", "Mesh")
REPEAT_SHADOWS = ("Armature", "Metaball", "Grease Pencil Selection")
SELECT_MM_KEYS = (({"shift": True}, "select_component"), ({"alt": True}, "select_polygon"))   # marking.SELECT_BINDINGS
GRAPH_VIEW_KEYS = (("ONE", "ABSOLUTE"), ("TWO", "STACKED"), ("THREE", "NORMALIZED"))


def patch_key_batch_2(kd):
    for key, mode in GRAPH_VIEW_KEYS:
        _add(kd, "Graph Editor", "allset.graph_view_mode", make_event(key), {"mode": mode})
    for km in SELECT_MM_KEYMAPS:
        for mods, binding in SELECT_MM_KEYS:
            _add(kd, km, "allset.tap_hold", make_event("Q", **mods), {"binding": binding})
    _add(kd, "Mesh", "mesh.edge_rotate", make_event("LEFT_ARROW", ctrl=True, alt=True), {"use_ccw": True})
    _add(kd, "Mesh", "mesh.edge_rotate", make_event("RIGHT_ARROW", ctrl=True, alt=True), {"use_ccw": False})
    _add(kd, "3D View", "allset.repeat_at_mouse", make_event("G", shift=True), shadows=REPEAT_SHADOWS)
    _add(kd, "Object Mode", "allset.camera_from_view", make_event("C", shift=True, ctrl=True))


# --- 38. Outliner MMB drag (docs/steps/step_82.md 「계획」 2) ------------------------------------------
# Maya parents / reorders / unparents with an MMB drag in the Outliner (step_82.md 「근거」); Blender's Outliner has
# no MMB item (IC "Outliner"), only View2D's MMB scroller_activate (IC:323), which passes through off the scroll
# bars and runs first. Alt+MMB pans (IC View2D, = Maya). "View2D Buttons List" (MMB pan) belongs to button-list
# regions (header / sidebar), not the Outliner tree. LMB drag stays Blender's (operators/outliner_drag.py redoes its
# drop the Maya way).

def patch_outliner_drag(kd):
    _add(kd, "Outliner", "allset.outliner_drag", make_event("MIDDLEMOUSE"), shadows=("View2D", "View2D Buttons List"))


# --- 39. Insert / nudge / select keys (docs/steps/step_83.md 「계획」 4) ------------------------------------
# Maya global keys (Maya factory hotkeys). "Screen" so they work over the 3D View, Graph Editor,
# Dope Sheet and Time Slider; the operators read the editor under the mouse. Editor / mode keymaps with the same
# event run first and keep it (Weight Paint / Grease Pencil / Mask Alt+I, Animation Channels Ctrl+Shift+W, Text
# Ctrl+Shift+E, the UI colour-ramp eyedropper Alt+I).
INSERT_KEY_KEYS = (("I", {"alt": True}, {"channels": "ALL"}),
                   ("W", {"ctrl": True, "shift": True}, {"channels": "TRANSLATE"}),
                   ("E", {"ctrl": True, "shift": True}, {"channels": "ROTATE"}),
                   ("R", {"ctrl": True, "shift": True}, {"channels": "SCALE"}))
KEY_STEP_SHADOWS = ("User Interface", "Mask Editing", "Weight Paint", "Grease Pencil Paint Mode",
                    "Grease Pencil Edit Mode", "Grease Pencil Sculpt Mode", "Grease Pencil Weight Paint",
                    "Grease Pencil Vertex Paint", "Animation Channels", "Text",
                    # Blender 5.x IC only (step 118): Draw Mode Alt+I / Ctrl+Shift+E, Sequencer Ctrl+Shift+R
                    "Grease Pencil Draw Mode", "Sequencer")


def patch_key_insert(kd):
    for key, mods, props in INSERT_KEY_KEYS:
        _add(kd, "Screen", "allset.insert_key", make_event(key, **mods), props, shadows=KEY_STEP_SHADOWS)
    for key, delta in (("NINE", -1), ("ZERO", 1)):
        _add(kd, "Screen", "allset.nudge_keys", make_event(key, shift=True, repeat=True), {"delta": delta},
             shadows=KEY_STEP_SHADOWS)
    for key, direction in (("COMMA", "PREVIOUS"), ("PERIOD", "NEXT")):
        _add(kd, "Screen", "allset.select_key", make_event(key, ctrl=True, alt=True), {"direction": direction},
             shadows=KEY_STEP_SHADOWS)


# --- 40. Time Slider range drag (docs/steps/step_84.md 「계획」 2) ---------------------------------------------
# A press on the highlighted range moves / scales its keys; anywhere else it passes through to time_scrub (step 56),
# so it goes in front of it (added after patch_time_slider: ``first`` puts the latest item first).
# The Maya Workflow Kit Time Slider row (29 px at 1.25) is all Blender's scrub strip, whose "Time Scrub" keymap (LMB =
# anim.change_frame, blender_default.py:1171-1183) runs before "Dopesheet"; IC has no "Time Scrub", so Blender used
# its default one (measured with --debug-handlers). The Maya keyconfig gets its own: change_frame kept, the range
# drag and step 56's time_scrub (a click drops the range) in front; both pass through outside the Time Slider.
TIME_SCRUB_KM = ("Time Scrub", {"space_type": 'EMPTY', "region_type": 'WINDOW'})


def patch_time_range(kd):
    _add(kd, "Dopesheet", "allset.time_range_drag", make_event("LEFTMOUSE"), first=True, shadows=TIME_SLIDER_SHADOWS)
    kd.ensure(*TIME_SCRUB_KM, [("anim.change_frame", make_event("LEFTMOUSE"), None)])
    shadows = (*TIME_SLIDER_SHADOWS, "Time Scrub")
    _add(kd, "Time Scrub", "allset.time_scrub", make_event("LEFTMOUSE"), first=True, shadows=shadows)
    _add(kd, "Time Scrub", "allset.time_range_drag", make_event("LEFTMOUSE"), first=True, shadows=shadows)


# --- 41. Manipulator Ctrl+LMB axis = plane, Shift+MMB = closest axis (docs/steps/step_85.md 「계획」 1-3) ----------
# Ctrl+LMB sits first in the gizmo keymaps (only over a highlighted gizmo; passes through off the kit manipulator's
# axis / Move centre handles). Shift+MMB goes in the Move / Scale tool keymaps (3D View has no Shift+MMB item; IC
# pans with Alt+MMB): a short modal reads the first movement, picks the axis and starts the transform (a CLICK_DRAG
# item never got the simulated MMB drag, step_85.md).

def patch_manip_ctrl(kd):
    for km in GIZMO_KEYMAPS:
        _add(kd, km, "allset.manip_ctrl", make_event("LEFTMOUSE", "PRESS", ctrl=True), first=True)
    for km, _idname, mode in MMB_TOOLS:
        if mode == 'ROTATE':
            continue
        _add(kd, km, "allset.manip_mmb_auto", make_event("MIDDLEMOUSE", "PRESS", shift=True), {"mode": mode},
             shadows=(km,))


# --- 42. View keys 3 (docs/steps/step_87.md 「계획」 2) --------------------------------------------------------
# Maya factory hotkeys Alt+p, Alt+a, Alt+arrows, `, backslash. All in "3D View" (Maya's model
# panel); the same events elsewhere belong to other editors / modes, whose keymaps run first.
VIEW3_SHADOWS = ("Sculpt", "Font", "Text", "File Browser", "Sequencer", "Clip", "Node Editor", "Grease Pencil Selection")
PIXEL_MOVE_KEYS = (("UP_ARROW", 0, 1), ("DOWN_ARROW", 0, -1), ("LEFT_ARROW", -1, 0), ("RIGHT_ARROW", 1, 0))


def patch_view_keys_3(kd):
    _add(kd, "3D View", "allset.cycle_display", make_event("A", alt=True), shadows=VIEW3_SHADOWS)
    _add(kd, "3D View", "allset.camera_mode_toggle", make_event("P", alt=True), shadows=VIEW3_SHADOWS)
    for key, dx, dy in PIXEL_MOVE_KEYS:
        _add(kd, "3D View", "allset.pixel_move", make_event(key, alt=True, repeat=True), {"dx": dx, "dy": dy},
             shadows=VIEW3_SHADOWS)
    kd.remove("Object Non-modal", "object.transfer_mode", type="ACCENT_GRAVE")
    _add(kd, "3D View", "allset.tweak_hold", make_event("ACCENT_GRAVE"), shadows=VIEW3_SHADOWS)
    _add(kd, "3D View", "allset.pan_zoom_hold", make_event("BACK_SLASH"), shadows=VIEW3_SHADOWS)


# --- 43. Global key batch 4 (docs/steps/step_90.md 「계획」 2) ----------------------------------------------
# Maya factory hotkeys Ctrl+x, Alt+x, Alt+backslash, Alt+1/2/4, Ctrl+` / Shift+~ /
# Ctrl+Shift+~). Ctrl+X exists only in other editors / modes (Text, Console, Font, Grease Pencil edit); Alt+X was IC's
# X-ray toggle; the rest were free. Plain ` stays step 87's tweak hold.
CUT_SHADOWS = ("Text", "Console", "Font", "Grease Pencil Edit Mode")
SHOW_KEYS = (("ONE", "CURVES"), ("TWO", "POLYGONS"), ("FOUR", "IMAGE_PLANES"))


def patch_global_keys_4(kd):
    for km in ("Object Mode", "Outliner"):
        _add(kd, km, "allset.cut", make_event("X", ctrl=True), shadows=CUT_SHADOWS)
    # Blender's paste leaves no active object after a cut: the kit paste makes the first pasted node the lead.
    _add(kd, "Object Mode", "allset.paste", make_event("V", ctrl=True), shadows=("3D View",))
    kd.remove("3D View", "view3d.toggle_xray", type="X", alt=True)
    _add(kd, "3D View", "view3d.walk", make_event("X", alt=True), shadows=VIEW3_SHADOWS)
    _add(kd, "Screen", "allset.playback_range_anim", make_event("BACK_SLASH", alt=True))
    for key, kind in SHOW_KEYS:
        _add(kd, "3D View", "allset.toggle_show", make_event(key, alt=True), {"kind": kind}, shadows=VIEW3_SHADOWS)
    for km in ("Object Mode", "Mesh"):
        _add(kd, km, "allset.smooth_proxy", make_event("ACCENT_GRAVE", ctrl=True), {"action": "TOGGLE"})
        _add(kd, km, "allset.smooth_proxy", make_event("ACCENT_GRAVE", shift=True), {"action": "BOTH"})
    _add(kd, "Object Mode", "allset.smooth_proxy", make_event("ACCENT_GRAVE", ctrl=True, shift=True),
         {"action": "CREATE"})



# --- 44. Graph Editor key batch (docs/steps/step_92.md 「계획」 2) ------------------------------------------
# Maya factory hotkeys t = GraphEditorFrameCenterView, Alt+/ = SnapTimeToSelection toggle, i hold =
# Insert Key tool; Maya binds it globally, it only means something in the Graph Editor: research/maya/workflows/
# animation.md:142). None of these events is bound in the Graph Editor keymaps (measured).

def patch_graph_keys_2(kd):
    _add(kd, "Graph Editor", "allset.graph_center_time", make_event("T"))
    _add(kd, "Graph Editor", "allset.snap_time_toggle", make_event("SLASH", alt=True))
    _add(kd, "Graph Editor", "allset.insert_key_tool", make_event("I"))

# --- 45. Outliner set rows (docs/steps/step_96.md 「계획」 3) -------------------------------------------------
# The kit draws Maya's set rows under Blender's Outliner tree (ui/outliner_sets.py); clicks / RMB on them must win
# over Blender's item_activate (LMB CLICK, any modifier) and context menus (RMB PRESS) in the same keymap, so these
# go first and pass through off the set rows.

def patch_outliner_sets(kd):
    _add(kd, "Outliner", "allset.outliner_set_click", make_event("LEFTMOUSE", "CLICK", any=True), first=True,
         shadows=("Outliner",))
    _add(kd, "Outliner", "allset.outliner_set_menu", make_event("RIGHTMOUSE"), first=True, shadows=("Outliner",))


# --- 46. Render slots (docs/steps/step_97.md) --------------------------------------------------------------------
# Keep Image = a Blender render slot (ui/render_view.py, step 67), compared with J / Alt+J like Blender
# ($S\presets\keyconfig\keymap_data\blender_default.py:2009-2011); IC's Image keymap has no J, so the kit's tip
# had no key behind it.

def patch_render_slots(kd):
    _add(kd, "Image", "image.cycle_render_slot", make_event("J"))
    _add(kd, "Image", "image.cycle_render_slot", make_event("J", alt=True), {"reverse": True})


# --- 47. Graph Editor outliner rows (docs/steps/step_104.md 「계획」 5) ---------------------------------------------
# The kit draws Maya's outliner pane (object + "Translate X" rows) over the Graph Editor's channel region
# (ui/editor_chrome.py); presses on it go first in "Animation Channels" (Blender's channels_click is a PRESS item, a
# handled press sends no CLICK) and pass through over Blender's search field.

def patch_graph_outliner(kd):
    _add(kd, "Animation Channels", "allset.graph_channel_click", make_event("LEFTMOUSE", any=True),
         first=True, shadows=("Animation Channels",))
    # step 150 (#96): the wheel scrolls the kit's rows (ui/editor_chrome.py keeps the offset). In the channel region
    # the wheel goes to "View2D" and never reaches "Animation Channels" (measured with --debug-handlers), so the items
    # sit first in View2D; the operator passes through anywhere but a kit Graph Editor's outliner pane.
    for wheel, delta in (("WHEELUPMOUSE", -3), ("WHEELDOWNMOUSE", 3)):
        _add(kd, "View2D", "allset.graph_channel_scroll", make_event(wheel), {"delta": delta}, first=True,
             shadows=("View2D", "View2D Buttons List"))
    # step 204: a click on a curve the kit draws for another selected animation layer (ui/graph_layers.py) makes that
    # layer the editable one (Maya edits every selected layer's curves; Blender one action per object); it passes
    # through when no such curve is under the mouse
    _add(kd, "Graph Editor", "allset.graph_layer_pick", make_event("LEFTMOUSE"), first=True,
         shadows=("Graph Editor", "Screen", "View2D"))


def patch_shelf_scroll(kd):
    # step 167: Maya's wheel over the shelf icons scrolls one row (research/maya/re/shelf_overflow_167.md); the shelf
    # row is an Image Editor, so the items sit first in "Image" and pass through in every other image editor
    for wheel, delta in (("WHEELUPMOUSE", -1), ("WHEELDOWNMOUSE", 1)):
        _add(kd, "Image", "allset.shelf_scroll", make_event(wheel), {"delta": delta}, first=True,
             shadows=("Image", "View2D"))     # both pass through outside their own region


# --- 48. Script Editor execute (docs/steps/step_105.md 「계획」 3) ---------------------------------------------------
# Maya: Ctrl+Enter executes (input kept), numpad Enter executes the whole tab and clears it. Only in the kit's Script
# Editor window (ui/script_editor.py); elsewhere the Text Editor's own keys stay (PASS_THROUGH).

def patch_script_editor(kd):
    # IC renders on Ctrl+Enter from "Screen Editing", a window keymap checked before every editor's (measured with
    # --debug-handlers: the Script Editor's Ctrl+Enter rendered, "No camera found"). Maya has no Ctrl+Enter render
    # (Render > Render Current Frame has no default hotkey; Ctrl+Alt+Enter render animation stays IC's).
    kd.remove("Screen Editing", "render.render", type="RET", ctrl=True, alt=False)
    # Blender 5.x IC adds Alt+F12 / Ctrl+Alt+F12 sequencer-scene renders there too (5.2 IC:299-302, step 118): they
    # took the UV Editor's Maya Alt+F12 (UV Shell, Maya factory hotkey). Not in 4.5's IC data.
    for ctrl in (False, True):
        if kd.find("Screen Editing", "render.render", type="F12", alt=True, ctrl=ctrl):
            kd.remove("Screen Editing", "render.render", type="F12", alt=True, ctrl=ctrl)
    _add(kd, "Text", "allset.script_run", make_event("RET", ctrl=True), first=True, shadows=("Text",))
    # Screen's numpad Enter = file.execute (file browsers only): the Text item runs first in a Text Editor anyway
    _add(kd, "Text", "allset.script_run", make_event("NUMPAD_ENTER"), {"clear": True}, first=True,
         shadows=("Text", "Screen"))



# --- 49. Key batch 3: wrong daily keys, missing keys (docs/steps/step_107.md 「계획」) ---------------------------------
# Maya factory hotkeys: Alt+r ToggleReflection, Ctrl+i, F1 Help, Alt+c ToggleColorFeedback,
# m ModifyDisplacement, Ctrl+PgUp / PgDn PickWalkIn / Out, Ctrl+, PrevSkinPaintMode,
# Ctrl+m / Shift+M / Ctrl+Shift+M menu bars, Alt+b, paint u / n / Alt+f / Ctrl+Alt+c / v,
# sculpt Ctrl+0-9, f, b, m, Shift+U, Ctrl+Shift+I, Graph Editor h / j, Time Slider
# bookmarks, Ctrl+f, Ctrl+Shift+% Use Default Material, UV Editor 7 / 5.

MODE_KEYMAPS = ("Object Mode", "Mesh", "Pose", "Curve", "Curves", "Armature", "Metaball", "Lattice", "Particle",
                "Paint Face Mask (Weight, Vertex, Texture)", "Paint Vertex Selection (Weight, Vertex)")
SCULPT_BRUSHES = (("ZERO", "Mask"), ("ONE", "Draw"), ("TWO", "Smooth"), ("THREE", "Relax Slide"), ("FOUR", "Grab"),
                  ("FIVE", "Pinch/Magnify"), ("SIX", "Flatten/Contrast"), ("SEVEN", "Blob"), ("EIGHT", "Draw Sharp"),
                  ("NINE", "Layer"))
SCULPT_LIBRARY = "brushes/essentials_brushes-mesh_sculpt.blend/Brush/"
SEARCH_SHADOWS = ("Property Editor", "Outliner", "Graph Editor Generic", "Node Editor", "Dopesheet", "NLA Generic",
                  "Text Generic", "Animation Channels", "Image Paint", "Vertex Paint", "Weight Paint", "Sculpt",
                  "Grease Pencil Weight Paint",
                  "Preferences", "Preferences_nav")   # Blender 5.x: Ctrl+F filter in Preferences (step 118)
BOOKMARK_KEYS = (("T", {"alt": True}, "allset.bookmark_create", {}),
                 ("T", {"alt": True, "shift": True}, "allset.bookmark_create", {"quick": True}),
                 ("QUOTE", {}, "screen.marker_jump", {"next": True}),
                 ("SEMI_COLON", {}, "screen.marker_jump", {"next": False}),
                 ("BACK_SLASH", {"shift": True}, "allset.bookmark_frame", {"which": "CURRENT"}),
                 ("QUOTE", {"shift": True}, "allset.bookmark_frame", {"which": "NEXT"}),
                 ("SEMI_COLON", {"shift": True}, "allset.bookmark_frame", {"which": "PREVIOUS"}))


def _props_of(kd, km, idname, **ev):
    """Properties of the first matching item (to copy IC's radial-control settings onto a Maya key)."""
    found = kd.find(km, idname, **ev)
    return patch.props_dict(found[0][2]) if found else {}


def _remove_where(kd, km, predicate, **ev):
    if km not in kd.keymap_names():
        return []
    items = kd.items(km)
    found = [it for it in kd.find(km, **ev) if predicate(it)]
    items[:] = [it for it in items if not any(it is f for f in found)]
    return found


def patch_key_batch_3(kd):
    # Alt+R: IC clear scale -> Maya reflection (symmetry) toggle
    kd.remove("Object Mode", "object.scale_clear", type="R", alt=True)
    kd.remove("Pose", "pose.scale_clear", type="R", alt=True)
    # (weight paint has its own Alt+R = Maya's paint Reflection toggle, step 218)
    _add(kd, "3D View", "allset.symmetry", make_event("R", alt=True), {"mode": "TOGGLE"},
         shadows=(*VIEW3_SHADOWS, "Weight Paint"))
    # Ctrl+I: IC invert in the 3D modes (Maya Ctrl+I = next intermediate object; Ctrl+Shift+I still inverts)
    for km in MODE_KEYMAPS:
        _remove_where(kd, km, lambda it: it[0].endswith("select_all"), type="I", ctrl=True)
    # F1: Maya Help = Blender's manual for the button under the mouse
    kd.remove("3D View", "view3d.view_axis", type="F1")
    kd.remove("Image", "image.view_zoom_ratio", type="F1")
    _add(kd, "Window", "wm.doc_view_manual_ui_context", make_event("F1"))
    # Alt+C: IC loop cut tool -> Maya colour feedback while painting skin weights
    kd.remove("Mesh", "wm.tool_set_by_id", type="C", alt=True)
    _add(kd, "Weight Paint", "allset.color_feedback", make_event("C", alt=True))
    # m: IC Measure tool in every 3D mode -> Maya displacement / strength drag (sculpt)
    for km in MODE_KEYMAPS:
        _remove_where(kd, km, lambda it: it[0] == "wm.tool_set_by_id"
                      and patch.props_dict(it[2]).get("name") == "builtin.measure", type="M")
    # Ctrl+PgUp / PgDn: IC workspace cycle -> Maya pick-walk in / out (down / up the hierarchy)
    kd.remove("Screen", "screen.workspace_cycle", type="PAGE_UP", ctrl=True)
    kd.remove("Screen", "screen.workspace_cycle", type="PAGE_DOWN", ctrl=True)
    for km, op in (("Object Mode", "object.select_hierarchy"), ("Pose", "pose.select_hierarchy")):
        _add(kd, km, op, make_event("PAGE_UP", ctrl=True), {"direction": "CHILD", "extend": False})
        _add(kd, km, op, make_event("PAGE_DOWN", ctrl=True), {"direction": "PARENT", "extend": False})
    # Ctrl+,: IC Preferences (Maya on Windows opens them from Windows > Settings/Preferences only)
    kd.remove("Screen", "screen.userpref_show", type="COMMA", ctrl=True)

    # menu bars and background
    _add(kd, "Screen", "allset.main_menubar_toggle", make_event("M", ctrl=True), shadows=("Grease Pencil Edit Mode",))
    _add(kd, "Screen", "wm.context_toggle", make_event("M", shift=True), {"data_path": "area.show_menus"},
         shadows=("Sequencer",))
    _add(kd, "3D View", "wm.context_toggle", make_event("M", ctrl=True, shift=True),
         {"data_path": "space_data.show_region_header"}, shadows=VIEW3_SHADOWS)
    _add(kd, "3D View", "allset.cycle_background", make_event("B", alt=True), shadows=VIEW3_SHADOWS)
    _add(kd, "3D View", "allset.panel_set", make_event("FIVE", ctrl=True, shift=True), {"key": "DEFAULT_MATERIAL"},
         shadows=VIEW3_SHADOWS)
    # editors with their own Ctrl+F (find / filter, paint radial controls) keep it
    _add(kd, "Screen", "wm.search_menu", make_event("F", ctrl=True), shadows=SEARCH_SHADOWS)

    # skin weight painting
    size = _props_of(kd, "Weight Paint", "wm.radial_control", type="S")
    weight = _props_of(kd, "Weight Paint", "wm.radial_control", type="F", ctrl=True)
    kd.remove("Weight Paint", "wm.radial_control", type="U")
    kd.remove("Weight Paint", "wm.call_asset_shelf_popover", type="B")
    _add(kd, "Weight Paint", "wm.call_menu", make_event("U"), {"name": "ALLSET_MT_paint_operation"})
    _add(kd, "Weight Paint", "wm.radial_control", make_event("N"), weight)
    _add(kd, "Weight Paint", "wm.radial_control", make_event("B"), size, shadows=("3D View",))
    # step 218 (research/maya/re/maya2026_paint_skin_weights.md:113-129): Alt+F = Maya Flood, Ctrl+Alt+C / V = copy /
    # paste vertex weights, Ctrl+. / Ctrl+, = next / previous Skin Paint Mode, Alt+R = reflection (X mirror)
    _add(kd, "Weight Paint", "allset.flood_weights", make_event("F", alt=True))
    _add(kd, "Weight Paint", "allset.paint_copy_vertex_weights", make_event("C", ctrl=True, alt=True))
    _add(kd, "Weight Paint", "allset.paint_paste_vertex_weights", make_event("V", ctrl=True, alt=True))
    _add(kd, "Weight Paint", "allset.skin_paint_mode", make_event("PERIOD", ctrl=True), {"step": 1})
    _add(kd, "Weight Paint", "allset.skin_paint_mode", make_event("COMMA", ctrl=True), {"step": -1})
    _add(kd, "Weight Paint", "allset.paint_reflection", make_event("R", alt=True), shadows=("3D View",))
    _add(kd, "Mesh", "allset.copy_vertex_weights", make_event("C", ctrl=True, alt=True))
    _add(kd, "Mesh", "allset.paste_vertex_weights", make_event("V", ctrl=True, alt=True))

    # sculpting
    size = _props_of(kd, "Sculpt", "wm.radial_control", type="S")
    strength = _props_of(kd, "Sculpt", "wm.radial_control", type="U")
    for n in range(6):
        kd.remove("Sculpt", "object.subdivision_set", type=("ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE")[n],
                  ctrl=True)
    for key, brush in SCULPT_BRUSHES:
        _add(kd, "Sculpt", "brush.asset_activate", make_event(key, ctrl=True),
             {"asset_library_type": "ESSENTIALS", "relative_asset_identifier": SCULPT_LIBRARY + brush},
             shadows=("3D View",))
    kd.remove("Sculpt", "wm.call_asset_shelf_popover", type="B")
    _add(kd, "Sculpt", "wm.radial_control", make_event("B"), size, shadows=("3D View",))
    _add(kd, "Sculpt", "wm.radial_control", make_event("M"), strength)
    _add(kd, "Sculpt", "paint.mask_flood_fill", make_event("U", shift=True), {"mode": "VALUE", "value": 0.0})
    _add(kd, "Sculpt", "paint.mask_flood_fill", make_event("I", ctrl=True, shift=True), {"mode": "INVERT"})

    # Graph Editor lock / unlock channel
    _add(kd, "Graph Editor", "anim.channels_setting_enable", make_event("H"), {"type": "PROTECT"})
    _add(kd, "Graph Editor", "anim.channels_setting_disable", make_event("J"), {"type": "PROTECT"})

    # Maya 2026 Dope Sheet keys (measured in Maya 2026: g / t / h / j, like the Graph Editor's); a / f are IC's
    # action.view_all / view_selected. allset.dope_sheet_key fails its poll in the Timeline, so the Time Slider keeps
    # the window keys (g = Repeat Last)
    for key, action in (("G", 'RANGE'), ("T", 'CENTER'), ("H", 'LOCK'), ("J", 'UNLOCK')):
        _add(kd, "Dopesheet", "allset.dope_sheet_key", make_event(key), {"action": action},
             shadows=("Screen",) if key == "G" else ())

    # Time Slider bookmarks = timeline markers (operators/bookmarks.py)
    for key, mods, op, props in BOOKMARK_KEYS:
        _add(kd, "Screen", op, make_event(key, **mods), props, shadows=("Clip Editor", "Clip Graph Editor", "Curve"))

    # UV Editor display toggles
    _add(kd, "UV Editor", "wm.context_toggle", make_event("SEVEN"), {"data_path": "space_data.uv_editor.show_stretch"})
    # step 155 (Maya UV Editor factory keys; ui/uv_display.py, operators/uv_shells.py). IC's UV Editor 4 (island select
    # mode) and Ctrl+1 (vertex select mode) go: Maya's UV component keys are F9-F12 (Maya factory hotkeys).
    if kd.find("UV Editor", "uv.select_mode", type="FOUR"):
        kd.remove("UV Editor", "uv.select_mode", type="FOUR")
    else:       # 5.x IC: island picking is a toggle of tool_settings.use_uv_select_island on the same key
        kd.remove("UV Editor", "wm.context_toggle", type="FOUR")
    kd.remove("UV Editor", "mesh.select_mode", type="ONE", ctrl=True)
    for key, mode in (("FOUR", 'WIREFRAME'), ("FIVE", 'SHADED'), ("SIX", 'IMAGE'), ("EIGHT", 'SHELL_BORDERS'),
                      ("NINE", 'TEXTURE_BORDERS')):
        _add(kd, "UV Editor", "allset.uv_display", make_event(key), {"mode": mode})
    _add(kd, "UV Editor", "allset.uv_isolate", make_event("ONE", ctrl=True))
    _add(kd, "UV Editor", "allset.uv_delete", make_event("DEL"))
    _add(kd, "UV Editor", "allset.uv_create_shell", make_event("X", ctrl=True, shift=True))


# --- 50. Menu shortcuts (docs/steps/step_108.md 「계획」 3) --------------------------------------------------------
# Blender prints the keymap shortcut of a menu's ``wm.call_menu`` beside the item that opens it: File > Recent Files
# showed IC's "Shift Ctrl O" (a C menu, so no kit subclass can hide it). Maya has no Ctrl+Shift+O
# (research/maya/hotkeys_default.json); the recent files stay in File > Recent Files.

def patch_menu_shortcuts(kd):
    kd.remove("Window", "wm.call_menu", type="O", ctrl=True, shift=True)


def patch_repeat(kd):
    """Step 175: G = Maya repeat last, menu / shelf / marking commands too (operators/repeat_maya.py); Blender's
    screen.repeat_last only knows registered operators. Graph Editor G stays anim.scene_range_frame (step 70)."""
    kd.remove("Screen", "screen.repeat_last", type="G")
    _add(kd, "Screen", "allset.repeat_last", make_event("G"),
         shadows=("Graph Editor", "Dopesheet", "Grease Pencil Edit Mode"))   # their own G (frame range / grab) win
    # there; the Dope Sheet's g (step 269) steps aside in the Timeline, so the Time Slider still repeats


# --- 51. Blender's render keys with Maya's default light (step 214, #120) ------------------------------------------
# A UI render's render_* handlers run on the job thread (operators/default_light.py), so the light is added by a kit
# operator wrapping render.render. F12 / Ctrl+F12 = Blender's Render Image / Animation keys: their default-keyconfig
# items in "Screen" are switched off in Maya mode (Screen is a patched keymap), so the kit's go there. The 3D View's
# Object Mode / Mesh F12 (Maya's SelectUVMask, patch_uv) runs first there, and the UV Editor gets the same Maya F12
# (its keymap runs before Screen): F12 renders everywhere else. IC's Ctrl+Alt+Enter Render Animation (Screen Editing)
# is wrapped the same way.

def patch_blender_render(kd):
    _add(kd, "Screen", "allset.render_blender", make_event("F12"), {"use_viewport": True}, first=True,
         shadows=("Object Mode", "Mesh", UV_KM))   # Maya's F12 UV mask wins in the 3D View / UV Editor
    _add(kd, UV_KM, "allset.uv_component", make_event("F12"), {"mode": 'UV'}, shadows=("Screen",))
    _add(kd, "Screen", "allset.render_blender", make_event("F12", ctrl=True), {"animation": True, "use_viewport": True},
         first=True)
    if kd.remove("Screen Editing", "render.render", type="RET", ctrl=True, alt=True):
        _add(kd, "Screen Editing", "allset.render_blender", make_event("RET", ctrl=True, alt=True),
             {"animation": True, "use_viewport": True}, first=True)


PATCHES = (patch_selection, patch_display, patch_group, patch_space,
           patch_hold_snap, patch_soft_select, patch_tap_hold_and_pivot, patch_pick_walk,
           patch_camera, patch_view_history, patch_space_tap, patch_smooth_preview,
           patch_component_keys, patch_cb_slider, patch_marking_menus, patch_concepts,
           patch_attribute_editor, patch_undo_visibility,
           patch_mesh_components, patch_key_stepping, patch_manip_duplicate,
           patch_component_delete, patch_view_keys, patch_active_handle, patch_materials,
           patch_uv_shell_select, patch_select_through, patch_key_batch, patch_component_pick_walk,
           patch_toolbox_guard, patch_select_priority, patch_pose_joints, patch_time_slider, patch_joints, patch_uv,
           patch_scene_files, patch_graph_keys, patch_key_batch_2, patch_outliner_drag,
           patch_key_insert, patch_time_range, patch_manip_ctrl, patch_view_keys_3,
           patch_global_keys_4, patch_graph_keys_2, patch_outliner_sets, patch_render_slots,
           patch_graph_outliner, patch_shelf_scroll, patch_script_editor, patch_key_batch_3,
           patch_menu_shortcuts, patch_repeat, patch_blender_render)


def patch_weight_paint_exit(kd):
    """Maya's Q/W/E/R change the global tool, leaving weight painting."""
    for key, tool in (('Q', 'builtin.select_box'), ('W', 'builtin.move'),
                      ('E', 'builtin.rotate'), ('R', 'builtin.scale')):
        _remove_where(kd, 'Weight Paint', lambda it: it[0] == 'wm.tool_set_by_id', type=key)
        _add(kd, 'Weight Paint', 'allset.weight_paint_exit', make_event(key),
             {'tool': tool}, first=True, shadows=('3D View',))


PATCHES += (patch_weight_paint_exit,)


def apply(data):
    """Apply all patches to IC data in place and return it."""
    ADDED.clear()
    kd = KeyconfigData(data)
    for apply_patch in PATCHES:
        apply_patch(kd)
    return data
