"""Step 2: the generated "Maya" keyconfig (docs/steps/step_2.md)."""

import json
import sys
from pathlib import Path

import bpy

import kit

# Pure-data helpers from the installed extension (imported, not re-registered).
from importlib import import_module  # noqa: E402
ic_data = import_module(kit.MODULE + ".keymap.ic_data")
maya_patches = import_module(kit.MODULE + ".keymap.maya_patches")
mapping = import_module(kit.MODULE + ".keymap.mapping")
patch = import_module(kit.MODULE + ".keymap.patch")

KC_NAME = "Maya-style"


def _kc():
    return kit.maya_kc()


def _kmis(km_name, idname, type, value="PRESS", shift=False, ctrl=False, alt=False):
    km = _kc().keymaps[km_name]
    return [k for k in km.keymap_items
            if k.idname == idname and k.type == type and k.value == value
            and k.shift == shift and k.ctrl == ctrl and k.alt == alt and not k.oskey]


def _one(km_name, idname, type, value="PRESS", **mods):
    found = _kmis(km_name, idname, type, value, **mods)
    assert len(found) == 1, f"{km_name}: {idname} {type} {value} {mods} -> {len(found)} items"
    return found[0]


def _any_event(km_name, type, value="PRESS", shift=False, ctrl=False, alt=False):
    km = _kc().keymaps[km_name]
    return [k.idname for k in km.keymap_items if k.active and k.type == type and k.value == value
            and k.shift == shift and k.ctrl == ctrl and k.alt == alt and not k.oskey]


def test_maya_keymap_is_full_and_active_keyconfig_unchanged():
    kcs = bpy.context.window_manager.keyconfigs
    assert kcs.active.name == "Blender" and KC_NAME not in kcs, (kcs.active.name, [k.name for k in kcs])
    n = sum(len(km.keymap_items) for km in _kc().keymaps)
    assert len(_kc().keymaps) >= 240 and n > 2000, (len(_kc().keymaps), n)


# --- selection rules: Shift=toggle, Ctrl=deselect, Ctrl+Shift=add ----------

def test_viewport_click_select():
    for km, value in (("3D View", "CLICK"), ("3D View Tool: Tweak", "PRESS")):
        p = _one(km, "view3d.select", "LEFTMOUSE", value).properties
        assert p.deselect_all and not p.toggle and not p.deselect and not p.extend, km
        assert _one(km, "view3d.select", "LEFTMOUSE", value, shift=True).properties.toggle, km
        assert _one(km, "view3d.select", "LEFTMOUSE", value, ctrl=True).properties.deselect, km
        p = _one(km, "view3d.select", "LEFTMOUSE", value, shift=True, ctrl=True).properties
        assert p.extend and not p.toggle and not p.deselect, km


def test_uv_click_select():
    km = "UV Editor"
    assert _one(km, "uv.select", "LEFTMOUSE", "CLICK", shift=True).properties.toggle
    assert _one(km, "uv.select", "LEFTMOUSE", "CLICK", ctrl=True).properties.deselect
    p = _one(km, "uv.select", "LEFTMOUSE", "CLICK", shift=True, ctrl=True).properties
    assert p.extend and not p.toggle


def test_box_select_modes():
    exact = {(False, False): "SET", (True, False): "XOR", (False, True): "SUB", (True, True): "ADD"}
    # outliner select_box has no XOR mode: Shift adds (workaround). uv / graph run the Shift box as SET and
    # allset.select_2d_box (first) toggles it Maya's way (step 170, tests/test_step170_select_mods.py).
    no_xor = {**exact, (True, False): "ADD"}
    set_xor = {**exact, (True, False): "SET"}
    cases = (("3D View Tool: Select Box", "view3d.select_box", exact),
             ("3D View Tool: Select Box (fallback)", "view3d.select_box", exact),
             ("Image Editor Tool: Uv, Select Box", "uv.select_box", set_xor),
             ("Image Editor Tool: Uv, Select Box (fallback)", "uv.select_box", set_xor),
             ("Outliner", "outliner.select_box", no_xor),
             ("Graph Editor", "graph.select_box", set_xor))
    for km, idname, want in cases:
        for (shift, ctrl), mode in want.items():
            kmi = _one(km, idname, "LEFTMOUSE", "CLICK_DRAG", shift=shift, ctrl=ctrl)
            assert kmi.properties.mode == mode, (km, shift, ctrl, kmi.properties.mode)


def test_outliner_and_graph_click_select():
    # Step 170 (measured in Maya): Outliner Shift = range, Ctrl = toggle, Ctrl+Shift = add range; Graph Editor
    # Shift / Ctrl+Shift toggle in Blender's item (Ctrl+Shift "add only" by allset.select_2d_click), Ctrl = plain
    for (shift, ctrl), (extend, rng) in (((True, False), (False, True)), ((False, True), (True, False)),
                                         ((True, True), (True, True))):
        p = _one("Outliner", "outliner.item_activate", "LEFTMOUSE", "CLICK", shift=shift, ctrl=ctrl).properties
        assert (p.extend, p.extend_range) == (extend, rng), (shift, ctrl)
    for shift, ctrl, extend in ((True, False, True), (False, True, False), (True, True, True)):
        assert _one("Graph Editor", "graph.clickselect", "LEFTMOUSE", "PRESS",
                    shift=shift, ctrl=ctrl).properties.extend == extend, (shift, ctrl)
    assert not _one("Outliner", "outliner.item_activate", "LEFTMOUSE", "CLICK").properties.extend
    assert not _one("Graph Editor", "graph.clickselect", "LEFTMOUSE", "PRESS").properties.extend


# --- 4/5/6/7, F8 ------------------------------------------------------------

def test_display_keys():
    for key, mode in maya_patches.DISPLAY_KEYS:
        assert _one("3D View", "allset.display_mode", key).properties.mode == mode
        assert _any_event("Object Non-modal", key) == [], key
    assert _one("Object Non-modal", "allset.toggle_sel_mode", "F8")


# --- Ctrl+G -----------------------------------------------------------------

def test_group_keys():
    for km in ("Object Mode", "Outliner"):
        assert _any_event(km, "G", ctrl=True) == ["allset.group"], km


# --- Space free, playback on Alt+V ------------------------------------------

def test_space_is_free_for_hotbox():
    for km in ("Window", "Screen", "Frames", "3D View Generic", "Object Mode",
               "Object Non-modal", "Mesh"):
        assert _any_event(km, "SPACE") == [], (km, _any_event(km, "SPACE"))
    # Step 9: Space = hotbox (tap = four views / maximize) in 3D View and the panel editors.
    for km in ("3D View", "Outliner", "Graph Editor", "Dopesheet", "Node Editor", "Image"):
        assert _any_event(km, "SPACE") == ["allset.hotbox"], (km, _any_event(km, "SPACE"))
    assert _one("Frames", "screen.animation_play", "V", alt=True)
    assert not _one("Frames", "screen.frame_jump", "V", alt=True, shift=True).properties.end


# --- conflicts ---------------------------------------------------------------

def _conflicts(data):
    out = set()
    for km_name, _args, content in data:
        for pair in patch.conflicts(content["items"]):
            out.add(patch.conflict_signature(km_name, pair))
    return out


def test_no_new_conflicts_within_keymaps():
    base = _conflicts(ic_data.generate())
    # Declared pass-through items placed in front on purpose (maya_patches.PASS_THROUGH_FIRST).
    maya = {c for c in _conflicts(maya_patches.apply(ic_data.generate()))
            if c[2] not in maya_patches.PASS_THROUGH_FIRST}
    new = sorted(maya - base, key=str)
    assert not new, "new conflicts:\n" + "\n".join(map(str, new))


# Keymaps that can handle an event in the same place as the patched keymap.
_VIEW3D_STACK = ("Window", "Screen", "Frames", "3D View", "3D View Generic", "Object Mode",
                 "Object Non-modal", "Mesh", "Curve", "Curves", "Armature", "Pose", "Metaball",
                 "Lattice", "Particle", "Font", "Sculpt", "Weight Paint", "Vertex Paint",
                 "Image Paint", "Grease Pencil")
# Object Mode items only run in object mode, where other mode keymaps are inactive.
_OBJECT_MODE_STACK = ("Window", "Screen", "Frames", "3D View", "3D View Generic",
                      "Object Mode", "Object Non-modal")
_STACKS = {"3D View": _VIEW3D_STACK, "Object Mode": _OBJECT_MODE_STACK,
           "Object Non-modal": _VIEW3D_STACK,
           # Step 129: the Maya dock is a Properties editor (Channel Box row hover / drag)
           "Property Editor": ("Window", "Screen", "Property Editor", "View2D Buttons List"),
           # Step 135: Channel Box wheel scroll (the region's View2D Buttons List handler runs first)
           "View2D Buttons List": ("Window", "Screen", "View2D Buttons List", "Property Editor"),
           # 3D View edit/pose modes: the mode keymap on top of the 3D View ones (step 8 adds
           # RMB marking menus and Q/W/E/R to them).
           **{km: ("Window", "Screen", "Frames", "3D View", "3D View Generic", km, "Object Non-modal")
              for km in ("Mesh", "Curve", "Curves", "Armature", "Pose", "Metaball", "Lattice")},
           "Screen": None,
           **{km: (km,) for km in maya_patches.SLIDER_TOOL_KEYMAPS},
           "Outliner": ("Window", "Screen", "Outliner", "View2D", "View2D Buttons List"),
           # Step 9 hotbox editors (Space): the editor keymap plus the global ones.
           **{km: ("Window", "Screen", "Frames", km, "View2D")
              for km in ("Graph Editor", "Dopesheet", "Node Editor", "Image")},
           # Step 22: gizmo keymaps run from the gizmo map handler, ahead of the region keymaps.
           **{km: (km,) for km in maya_patches.GIZMO_KEYMAPS},
           # Step 30: select tool keymaps (only active with that tool, ahead of the editor keymaps).
           **{km: (km,) for km in maya_patches.SELECT_DRAG_KEYMAPS},
           # Step 76: the Tweak tool keymap (only active with that tool, ahead of the editor keymaps).
           "3D View Tool: Tweak": ("3D View Tool: Tweak",),
           "3D View Tool: Cursor": ("3D View Tool: Cursor",),
           # Step 66: the UV Editor (an Image Editor in UV mode).
           maya_patches.UV_KM: ("Window", "Screen", "Frames", maya_patches.UV_KM, "Image", "Image Generic", "View2D"),
           # Step 84: the scrub strip of the Dope Sheet / Graph Editor / Time Slider (its own keymap, kit-made).
           "Time Scrub": ("Window", "Screen", "Frames", "Time Scrub", "Dopesheet", "View2D"),
           # Step 69: Window items (file keys) run after every editor keymap.
           "Window": None,
           # Step 104: the Graph Editor's channel region (the kit's Maya outliner rows over it).
           "Animation Channels": ("Window", "Screen", "Frames", "Animation Channels", "View2D", "View2D Buttons List"),
           # Step 105: the Text Editor (the kit Script Editor's input pane).
           "Text": ("Window", "Screen", "Screen Editing", "Text Generic", "Text"),
           # Step 107: paint / sculpt mode keymaps (the mode keymap on top of the 3D View ones).
           **{km: ("Window", "Screen", "Frames", "3D View", "3D View Generic", km, "Object Non-modal")
              for km in ("Weight Paint", "Sculpt")},
           # Step 141: the other modes where Ctrl+A was IC select-all (Ctrl+A = AE / CB swap there now).
           **{km: ("Window", "Screen", "Frames", "3D View", "3D View Generic", km, "Object Non-modal")
              for km in ("Particle", "Point Cloud", "Sculpt Curves", "Paint Face Mask (Weight, Vertex, Texture)",
                         "Paint Vertex Selection (Weight, Vertex)")},
           # Step 150: the outliner wheel sits first in View2D (checked before Animation Channels in that region).
           "View2D": ("Window", "Screen", "Frames", "View2D", "View2D Buttons List", "Animation Channels"),
           # Step 150: Ctrl+A = AE / CB swap in the NLA Editor too (the other 2D animation editors are above).
           "NLA Editor": ("Window", "Screen", "Frames", "NLA Editor", "NLA Generic", "View2D"),
           # Step 214: IC's window-level render keys (checked before every editor keymap)
           "Screen Editing": None,
           "Frames": None}  # None = every non-modal keymap (Frames is in most editors)


def test_added_bindings_not_shadowed():
    data = maya_patches.apply(ic_data.generate())
    assert maya_patches.ADDED, "no added bindings recorded"
    problems = []
    # step 170: select tool keymaps that got a Maya marquee item are only active with that tool (own stack)
    stacks = {**_STACKS, **{km: (km,) for km in maya_patches.SELECT_2D_KEYMAPS if km not in _STACKS},
              **{km: (km,) for km in maya_patches.UV_SHELL_DRAG_KEYMAPS if km not in _STACKS}}
    for km, idname, ev, _props, shadows in maya_patches.ADDED:
        stack = stacks[km]
        k = patch.event_key(ev)
        for km_name, args, content in data:
            if args.get("modal") or (stack is not None and km_name not in stack):
                continue
            if km_name in shadows:  # declared intentional (maya_patches._add)
                continue
            for it in content["items"]:
                if patch.event_key(it[1]) == k and not (km_name == km and it[0] == idname):
                    problems.append(f"{km} {idname} {ev} <-> {km_name} {it[0]}")
    assert not problems, "\n".join(problems)


# --- mapping table ------------------------------------------------------------

def test_mapping_rows_are_bound():
    hk_path = Path(kit.maya_data("maya", "hotkeys_default.json"))
    hotkeys = json.loads(hk_path.read_text(encoding="utf-8"))["hotkeys"]
    assert len(hotkeys) == 495, len(hotkeys)   # Maya 2026 (468 in 2022)
    kd = patch.KeyconfigData(maya_patches.apply(ic_data.generate()))
    checked, bad = 0, []
    for hk in hotkeys:
        mapping.maya_event(hk)  # every Maya key converts
        entry = mapping.entry_for(hk)
        if hk["platform"] != "mac-only" and entry and entry["check"]:
            checked += 1
            if not mapping.check_entry(kd, hk, entry):
                bad.append(hk["display"])
    assert checked >= 20 and not bad, (checked, bad)


def test_disable_leaves_keyconfigs_alone():
    """Step 130: no keyconfig of the kit's own, the active one never changes; disable removes every Maya item."""
    kcs = bpy.context.window_manager.keyconfigs
    active = kcs.active.name
    kit.disable()
    try:
        assert KC_NAME not in kcs, [k.name for k in kcs]
        assert kcs.active.name == active
        assert not [k for km in kcs.addon.keymaps for k in km.keymap_items if k.idname.startswith("allset.")]
    finally:
        kit.enable()
    assert kcs.active.name == active and KC_NAME not in kcs
