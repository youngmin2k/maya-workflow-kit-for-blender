"""#288: Alt+LMB stays the kit's tumble through Maya mode switches, disable / enable, an update reload, another
keyconfig preset, user key edits and file loads; the active keyconfig's own items (and Blender's axis snap while
rotating) are off only while Maya mode is on.

Background Blender leaves the default keyconfig empty, so it is filled from Blender's keymap data first."""

from importlib import import_module

import addon_utils
import bpy

import kit
from rt60_dump import populate

AUTO_ENABLE = False

ALT_LMB = ('LEFTMOUSE', 'PRESS', False, 0, 0, 1, 0, 'NONE')    # _event_sig order: type value any shift ctrl alt oskey


def _kcs():
    return bpy.context.window_manager.keyconfigs


def _keymap():
    return import_module(kit.MODULE + ".keymap")


def _switch():
    return import_module(kit.MODULE + ".switch")


def _passing():
    """The kit's first-place items that always hand the event on when they don't apply."""
    return set(import_module(kit.MODULE + ".keymap.maya_patches").PASS_THROUGH_FIRST)


def first_alt_lmb(km_name="3D View"):
    """idname of the first active item of the merged keymap one Alt+LMB press could run (pass-through items
    skipped)."""
    km_mod = _keymap()
    _kcs().update()
    km = _kcs().user.keymaps[km_name]
    passing = _passing()
    for kmi in km.keymap_items:
        if kmi.idname in passing:
            continue
        if kmi.active and km_mod.same_press(km_mod._event_sig(kmi), ALT_LMB):
            return kmi.idname
    return None


def earlier_alt_lmb():
    """Active Alt+LMB items of keymaps that run before "3D View" in the 3D View's main region."""
    km_mod = _keymap()
    out = []
    passing = _passing()
    for name in ("Object Mode", "Object Non-modal", "3D View Generic", "Frames", "Screen", "Window",
                 "3D View Tool: Tweak", "3D View Tool: Select Box"):
        km = _kcs().user.keymaps.get(name)
        for kmi in (km.keymap_items if km is not None else ()):
            if kmi.active and kmi.idname not in passing and km_mod.same_press(km_mod._event_sig(kmi), ALT_LMB):
                out.append((name, kmi.idname, kmi.value))
    return out


def snap_items(kc=None):
    km = (kc or _kcs().active).keymaps.get("View3D Rotate Modal")
    return [kmi.active for kmi in km.keymap_items if kmi.propvalue.startswith("AXIS_SNAP")] if km else []


def blender_items_on(kc=None):
    km = (kc or _kcs().active).keymaps["3D View"]
    return [kmi.active for kmi in km.keymap_items]


def assert_maya(tag):
    assert _keymap().is_applied(), tag
    assert first_alt_lmb() == "allset.tumble", (tag, first_alt_lmb())
    assert not earlier_alt_lmb(), (tag, earlier_alt_lmb())
    assert not any(blender_items_on()), (tag, "Blender's own 3D View items still on")
    snaps = snap_items()
    assert snaps and not any(snaps), (tag, "axis snap while tumbling", snaps)


def assert_blender(tag):
    assert not _keymap().is_applied(), tag
    assert all(blender_items_on()), (tag, "Blender's own 3D View items left off")
    snaps = snap_items()
    assert snaps and all(snaps), (tag, snaps)
    assert first_alt_lmb() != "allset.tumble", tag


def test_switch_round_trips_keep_the_tumble():
    populate()
    kit.enable()
    try:
        assert_maya("first on")
        sw = _switch()
        for i in range(3):
            sw.set_mode(False)
            assert_blender(f"off {i}")
            sw.set_mode(True, layout=False)
            assert_maya(f"on {i}")
        # the Maya button again while Maya mode is on: nothing doubles
        sw.set_mode(True, layout=False)
        assert_maya("on twice")
        n = sum(1 for k in _kcs().addon.keymaps["3D View"].keymap_items if k.idname == "allset.tumble")
        assert n == 1, n
        # a deferred switch (the switch operator) and back
        sw.request(False)
        sw._apply_pending()
        assert_blender("request off")
        sw.request(True, layout=False)
        sw._apply_pending()
        assert_maya("request on")
    finally:
        kit.disable()
    assert_blender("disabled")


def test_disable_enable_and_update_reload():
    populate()
    kit.enable()
    try:
        assert_maya("enabled")
        kit.disable()
        assert_blender("disabled")
        kit.enable(maya=False)
        prefs = bpy.context.preferences.addons[kit.MODULE].preferences
        assert not prefs.maya_mode or _keymap().is_applied()
        kit.maya_mode_on()
        assert_maya("enabled again")
        # an update / reload: disabled and enabled without changing the saved add-on list
        addon_utils.disable(kit.MODULE, default_set=False)
        assert not any(k.idname == "allset.tumble" for km in _kcs().addon.keymaps for k in km.keymap_items)
        addon_utils.enable(kit.MODULE, default_set=False)
        if not _keymap().is_applied():
            kit.maya_mode_on()
        assert_maya("after reload")
    finally:
        kit.disable()
    assert_blender("disabled at the end")


def test_other_preset_and_back():
    populate()
    kit.enable()
    km_mod = _keymap()
    default = _kcs().active
    other = _kcs().new("Issue 288 Preset")
    km = other.keymaps.new("3D View", space_type='VIEW_3D')
    km.keymap_items.new("view3d.rotate", 'LEFTMOUSE', 'PRESS', alt=True)
    rot = other.keymaps.new("View3D Rotate Modal", modal=True)
    try:
        _kcs().active = other
        km_mod._watch()
        assert not km.keymap_items[0].active, "the new preset's Alt+LMB rotate is still on"
        assert first_alt_lmb() == "allset.tumble", first_alt_lmb()
        assert all(blender_items_on(default)), "the previous preset got its items back"
        _kcs().active = default
        km_mod._watch()
        assert km.keymap_items[0].active
        assert_maya("back to Blender's preset")
    finally:
        _kcs().active = default
        _kcs().remove(other)
        km_mod._watch()
        kit.disable()
    del rot


def test_user_key_edits_and_switch():
    populate()
    kit.enable()
    try:
        sw = _switch()
        # an unrelated edit in the 3D View keymap while Maya mode is on
        _kcs().update()
        km = _kcs().user.keymaps["3D View"]
        frame = next(k for k in km.keymap_items if k.idname == "allset.dolly")
        frame.type = 'BUTTON5MOUSE'
        _kcs().update()
        assert km.is_user_modified
        assert_maya("unrelated edit")
        sw.set_mode(False)
        assert first_alt_lmb() != "allset.tumble"
        sw.set_mode(True, layout=False)
        assert_maya("unrelated edit, after off / on")
        # the same edit made in Blender mode, then Maya mode
        sw.set_mode(False)
        _kcs().update()
        km = _kcs().user.keymaps["3D View"]
        move = next(k for k in km.keymap_items if k.idname == "view3d.move" and k.type == 'MIDDLEMOUSE')
        move.type = 'BUTTON4MOUSE'
        _kcs().update()
        sw.set_mode(True, layout=False)
        assert first_alt_lmb() == "allset.tumble", first_alt_lmb()
        assert not earlier_alt_lmb(), earlier_alt_lmb()
        # Alt+LMB itself: a key the user moves elsewhere stays moved, Restore brings the Maya key back
        km = _kcs().user.keymaps["3D View"]
        tumble = next(k for k in km.keymap_items if k.idname == "allset.tumble")
        tumble.type = 'BUTTON7MOUSE'
        _kcs().update()
        assert first_alt_lmb() is None or first_alt_lmb() != "allset.tumble"
        sw.set_mode(False)
        sw.set_mode(True, layout=False)
        km = _kcs().user.keymaps["3D View"]
        tumble = next(k for k in km.keymap_items if k.idname == "allset.tumble")
        assert tumble.type == 'BUTTON7MOUSE', "the user's own edit is kept"
        km.restore_item_to_default(tumble)
        _kcs().update()
        assert first_alt_lmb() == "allset.tumble", first_alt_lmb()
    finally:
        for km in _kcs().user.keymaps:
            if km.is_user_modified:
                km.restore_to_default()
        kit.disable()


def test_file_loads_keep_the_tumble():
    populate()
    kit.enable()
    try:
        bpy.ops.wm.read_homefile(use_empty=True)
        assert_maya("after a file load")
        import_module(kit.MODULE + ".first_start").new_maya_scene()
        assert_maya("after a new Maya scene")
    finally:
        kit.disable()
