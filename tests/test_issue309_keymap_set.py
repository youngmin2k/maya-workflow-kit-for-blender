"""#309: Keyboard = Maya / Blender in the add-on preferences. Blender takes the kit's Maya keys out (the active
Blender keymap works alone) while Maya mode, its layout, menus and tools stay; Maya puts the keys back."""

from importlib import import_module

import bpy

import kit

keymap = import_module(kit.MODULE + ".keymap")
switch = import_module(kit.MODULE + ".switch")


def _prefs():
    return bpy.context.preferences.addons[kit.MODULE].preferences


def _addon_ids():
    kc = bpy.context.window_manager.keyconfigs.addon
    return [k.idname for km in kc.keymaps for k in km.keymap_items]


def _kit_items():
    """Kit items of the add-on keyconfig other than the switch shortcut and the kit tools' own keymaps (a tool's
    keymap belongs to the tool, like Blender's tools)."""
    kc = bpy.context.window_manager.keyconfigs.addon
    return [(km.name, k.idname) for km in kc.keymaps if " Tool: " not in km.name for k in km.keymap_items
            if k.idname.startswith("allset.") and k.idname != "allset.switch_mode"]


def _kit_count():
    return len(_kit_items())


def _switched_off():
    """Items of the active keyconfig the kit switched off (in memory) for the Maya keys."""
    return len(keymap._state["off"])


def test_default_is_maya():
    assert _prefs().keymap_set == 'MAYA'
    assert keymap.is_applied() and _kit_count() > 100 and _switched_off() > 0
    assert "allset.new_maya_scene" in _addon_ids()


def test_blender_keys_and_back():
    p = _prefs()
    before = _kit_count()
    p.keymap_set = 'BLENDER'
    try:
        assert not keymap.is_applied()
        assert _kit_count() == 0, _kit_items()[:10]
        assert _switched_off() == 0, "the active keymap's own items are all back on"
        assert "allset.switch_mode" in _addon_ids(), "the Maya / Blender switch shortcut stays"
        # Maya mode itself (layout, menus, tools) stays
        assert p.maya_mode and switch._registered[0]
        assert hasattr(bpy.types, "ALLSET_OT_new_maya_scene")
        assert hasattr(bpy.types, "ALLSET_MT_prefs_edit")
    finally:
        p.keymap_set = 'MAYA'
    assert keymap.is_applied() and _kit_count() == before and _switched_off() > 0


def test_blender_keys_survive_a_mode_switch():
    p = _prefs()
    p.keymap_set = 'BLENDER'
    try:
        switch.set_mode(False, layout=False)
        assert not keymap.is_applied()
        switch.set_mode(True, layout=False)
        assert p.maya_mode and not keymap.is_applied() and _kit_count() == 0
    finally:
        p.keymap_set = 'MAYA'
    assert keymap.is_applied() and _kit_count() > 100


def test_choice_off_in_blender_mode_changes_nothing():
    p = _prefs()
    switch.set_mode(False, layout=False)
    try:
        p.keymap_set = 'BLENDER'
        p.keymap_set = 'MAYA'
        assert not keymap.is_applied() and _kit_count() == 0
    finally:
        switch.set_mode(True, layout=False)
    assert keymap.is_applied()


def test_disable_leaves_nothing_with_blender_keys():
    _prefs().keymap_set = 'BLENDER'
    kit.disable()
    assert not any(i.startswith("allset.") for i in _addon_ids())
    kit.enable()
    assert _prefs().keymap_set == 'MAYA', "a fresh preferences entry (the factory test session keeps no backup)"
    assert keymap.is_applied()
