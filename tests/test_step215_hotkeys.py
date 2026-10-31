"""#121: Maya's Hotkey Editor (ui/hotkey_editor.py, keymap/hotkey_rows.py).

Rows = Maya's standard hotkeys (keymap/hotkey_data.py) joined with
keymap/mapping.py; a kit binding is changed on the ``keyconfigs.user`` item (Blender's keymap editor does the same),
restored with ``KeyMap.restore_item_to_default``; the kit writes no file. Background Blender leaves the default
keyconfig empty, so it is filled from Blender's keymap data first (rt60_dump.populate)."""

import os
from importlib import import_module

import bpy

import kit
from rt60_dump import populate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def m(name):
    return import_module(f"{kit.MODULE}.{name}")


def _he():
    return m("ui.hotkey_editor")


def _row(command, context="global"):
    return next(r for r in _he().rows() if r["command"] == command and r["context"] == context)


def _user_km(name):
    return bpy.context.window_manager.keyconfigs.user.keymaps[name]


def _active_on(km_name, type, **mods):
    out = []
    for k in _user_km(km_name).keymap_items:
        if k.active and k.type == type and all(bool(getattr(k, x)) == bool(mods.get(x))
                                               for x in ("ctrl", "alt", "shift", "oskey")):
            out.append(k.idname)
    return out


def _config_files():
    cfg = bpy.utils.user_resource('CONFIG')
    return sorted(os.listdir(cfg)) if os.path.isdir(cfg) else []


def _setup():
    populate()
    bpy.context.window_manager.keyconfigs.update()


def test_every_kit_row_has_a_live_binding():
    _setup()
    he = _he()
    ctx = bpy.context
    missing = []
    for r in he.rows():
        if r["editable"]:
            km, kmi = he.editable_item(ctx, r)
            if kmi is None:
                missing.append((r["command"], r["maya_key"], r["check"][:2]))
            else:
                assert he.kit_text(ctx, r) == r["maya_key"] or he.kit_text(ctx, r) != "—", r
    assert not missing, missing[:20]
    for r in he.rows():
        if r["status"] == "NO":
            assert he.kit_text(ctx, r) == "—"


def test_search_by_name_hotkey_and_category():
    hr = m("keymap.hotkey_rows")
    rows = hr.build_rows()
    names = lambda found: {r["command"] for r in found}   # noqa: E731
    assert "SelectToggleMode" in names(hr.search(rows, "selecttoggle"))
    assert "SelectToggleMode" in names(hr.search(rows, "Select Toggle"))
    assert not hr.search(rows, "nosuchcommandxyz")
    assert names(hr.search(rows, "F8", by="HOTKEY")) == {"SelectToggleMode"}, names(hr.search(rows, "F8", "HOTKEY"))
    assert "Undo" in names(hr.search(rows, "ctrl+z", by="HOTKEY"))
    assert "Undo" in names(hr.search(rows, "z", by="HOTKEY"))
    assert "Redo" not in names(hr.search(rows, "z", by="HOTKEY"))           # Shift+Z is another key
    assert "Redo" in names(hr.search(rows, "Shift+Z", by="HOTKEY"))
    assert "SelectComponentToolMarkingMenu" in names(hr.search(rows, "shift+q", by="HOTKEY"))
    assert hr.parse_hotkey("Ctrl+Shift+A") == {"ctrl": True, "shift": True, "type": "A"}
    assert hr.parse_hotkey("alt+[") == {"alt": True, "type": "LEFT_BRACKET"}
    assert hr.parse_hotkey("meta+q") is None
    assert hr.event_text({"type": "F6", "ctrl": True, "shift": True}) == "Ctrl+Shift+F6"
    cats = hr.categories(rows)
    assert "Menu items" in cats and "Editors" in cats and "Menu items > Common" in cats, cats[:10]
    common = hr.search(rows, category="Menu items > Common")
    menu = hr.search(rows, category="Menu items")
    assert 0 < len(common) < len(menu) < len(rows)
    assert all(r["category"].startswith("Menu items > Common") for r in common)
    assert "Undo" in names(hr.search(rows, "undo", category="Menu items > Common"))
    # the window's list follows the search properties
    _setup()
    wm = bpy.context.window_manager
    he = _he()
    wm.allset_hk_category = "ALL"
    wm.allset_hk_by = "NAME"
    wm.allset_hk_search = ""
    he.refresh(bpy.context)
    assert len(wm.allset_hk_rows) == len(rows)
    wm.allset_hk_search = "selecttoggle"        # update callback rebuilds
    assert [r.command for r in wm.allset_hk_rows] == ["SelectToggleMode"], [r.command for r in wm.allset_hk_rows]
    assert wm.allset_hk_rows[0].kit_key == "F8" and wm.allset_hk_rows[0].status == "Kit"
    wm.allset_hk_search = ""


def test_conflict_pure():
    hr = m("keymap.hotkey_rows")
    items = [("Screen", "Undo", {"type": "Z", "ctrl": True}), ("Screen", "Redo", {"type": "Z", "shift": True}),
             ("Window", "Any Z", {"type": "Z", "any": True, "value": "CLICK"})]
    assert hr.conflicts(items, {"type": "Z", "ctrl": True}) == [("Screen", "Undo")]
    assert hr.conflicts(items, {"type": "Z", "ctrl": True, "value": "CLICK"}) == [("Window", "Any Z")]
    assert hr.conflicts(items, {"type": "Y"}) == []


def test_rebind_restore_and_nothing_written():
    _setup()
    he = _he()
    ctx = bpy.context
    files = _config_files()
    row = _row("SelectToggleMode")
    assert _active_on("Object Non-modal", "F8") == ["allset.toggle_sel_mode"]
    r = bpy.ops.allset.hotkey_assign(row=row["index"], key="F6", ctrl=True)
    assert r == {'FINISHED'}, r
    assert _active_on("Object Non-modal", "F8") == [], _active_on("Object Non-modal", "F8")
    assert "allset.toggle_sel_mode" in _active_on("Object Non-modal", "F6", ctrl=True)
    assert _user_km("Object Non-modal").is_user_modified
    addon = bpy.context.window_manager.keyconfigs.addon.keymaps["Object Non-modal"]
    assert [(k.type, k.ctrl) for k in addon.keymap_items if k.idname == "allset.toggle_sel_mode"] == [("F8", 0)]
    assert he.kit_text(ctx, row) == "Ctrl+F6 *", he.kit_text(ctx, row)
    assert he.changed_rows(ctx) == [row]
    # search by hotkey also finds the kit's current key
    live = {row["index"]: he.live_events(ctx, row)}
    assert row in m("keymap.hotkey_rows").search(he.rows(), "ctrl+f6", "HOTKEY", live=live)
    # Maya mode off / on: Blender re-applies the user edit to the re-added add-on item
    keymap = m("keymap")
    keymap.deactivate()
    keymap.activate()
    bpy.context.window_manager.keyconfigs.update()
    assert he.kit_text(ctx, row) == "Ctrl+F6 *", he.kit_text(ctx, row)
    # Restore (Blender's Restore Item)
    assert bpy.ops.allset.hotkey_restore(row=row["index"]) == {'FINISHED'}
    assert _active_on("Object Non-modal", "F8") == ["allset.toggle_sel_mode"]
    assert he.kit_text(ctx, row) == "F8"
    assert not he.changed_rows(ctx)
    # two edits, Restore All
    frame = _row("FrameSelectedWithoutChildren")
    he.assign(ctx, row, {"type": "F6", "alt": True})
    he.assign(ctx, frame, {"type": "F", "alt": True, "shift": True})
    # sculptMeshCache SculptMeshFrame is the same kit item (3D View allset.frame) as FrameSelectedWithoutChildren
    assert {r["command"] for r in he.changed_rows(ctx)} == {"SelectToggleMode", "FrameSelectedWithoutChildren",
                                                            "SculptMeshFrame"}, he.changed_rows(ctx)
    assert he.restore_all(ctx) == 2
    assert not he.changed_rows(ctx)
    assert he.kit_text(ctx, frame) == frame["maya_key"]
    assert not any(km.is_user_modified for km in bpy.context.window_manager.keyconfigs.user.keymaps)
    assert _config_files() == files, (files, _config_files())   # the kit saved nothing


def test_conflict_warning_and_non_kit_rows():
    _setup()
    he = _he()
    ctx = bpy.context
    row = _row("SelectToggleMode")
    ok, clash = he.assign(ctx, row, {"type": "Z", "ctrl": True})     # Maya Undo's key (Screen ed.undo)
    try:
        assert ok and any(km == "Screen" for km, _n in clash), clash
        _km, kmi = he.editable_item(ctx, row)
        assert he.conflicts(ctx, row, he.item_event(kmi), exclude=kmi), "conflict shown in the details"
    finally:
        assert he.restore(ctx, row)
    ok, clash = he.assign(ctx, row, {"type": "F6", "ctrl": True, "alt": True, "shift": True})
    assert ok and not clash, clash
    assert he.restore(ctx, row)
    # Object Mode and Mesh items never run together: Ctrl+Shift+A (Object Mode select all) has no conflict
    sa = _row("SelectAll")
    _km, kmi = he.editable_item(ctx, sa)
    assert not he.conflicts(ctx, sa, he.item_event(kmi), exclude=kmi), he.conflicts(ctx, sa, he.item_event(kmi), kmi)
    no = next(r for r in he.rows() if r["status"] == "NO")
    assert he.assign(ctx, no, {"type": "F6"}) == (False, [])
    assert bpy.ops.allset.hotkey_assign(row=no["index"], key="F6") == {'CANCELLED'}


def test_window_kind_and_menu_item():
    mw = m("ui.marked_window")
    flags = mw.KINDS["HOTKEY_EDITOR"]
    assert len(flags) == 2
    others = [set(v) for k, v in mw.KINDS.items() if k != "HOTKEY_EDITOR"]
    others += [{f} for f in m("ui.maya_dock").ROLE_FLAGS.values()]
    others += [set(m("ui.hypershade").MARK), set(m("ui.reference_editor").MARK)]
    assert set(flags) not in others, flags
    props = bpy.types.SpaceProperties.bl_rna.properties
    assert all(f in props for f in flags), flags
    assert m("ui.menu_map").MAP["Windows/Settings/Preferences/Hotkey Editor"] == "allset.hotkey_editor"
    assert hasattr(bpy.types, "ALLSET_PT_hotkey_editor") and hasattr(bpy.types, "ALLSET_UL_hotkeys")


def test_disable_leaves_nothing():
    _setup()
    he = _he()
    he.assign(bpy.context, _row("SelectToggleMode"), {"type": "F6", "ctrl": True})
    he.restore_all(bpy.context)
    kit.disable()
    wm = bpy.types.WindowManager
    assert not any(hasattr(wm, p) for p in ("allset_hk_rows", "allset_hk_search", "allset_hk_capture"))
    assert not hasattr(bpy.types, "ALLSET_PT_hotkey_editor")
    assert not any(km.is_user_modified for km in bpy.context.window_manager.keyconfigs.user.keymaps)
    kit.enable()
