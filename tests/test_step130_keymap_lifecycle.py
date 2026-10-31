"""GitHub #46, #40: the Maya keymap never changes the active keyconfig or a keymap preference.

Maya items live in the add-on keyconfig; the active keyconfig's own items of the same keymaps are switched off in
memory while Maya mode is on and switched on again on Maya mode off / disable.
Background Blender leaves the default keyconfig empty, so it is filled from Blender's keymap data first
(rt60_dump.populate, like the switch round trip test).
"""

from importlib import import_module

import bpy

import kit
from rt60_dump import populate

AUTO_ENABLE = False


def _kcs():
    return bpy.context.window_manager.keyconfigs


def _flags(kc):
    return [(km.name, i, kmi.idname if not km.is_modal else kmi.propvalue, kmi.type, kmi.active)
            for km in kc.keymaps for i, kmi in enumerate(km.keymap_items)]


def _state():
    kcs = _kcs()
    return {
        "keyconfigs": sorted(k.name for k in kcs),
        "active": kcs.active.name,
        "stored": bpy.context.preferences.keymap.active_keyconfig,
        "active_items": _flags(kcs.active),
        "addon": sorted((km.name, k.idname, k.type, k.value) for km in kcs.addon.keymaps for k in km.keymap_items),
        "user_modified": sorted(km.name for km in kcs.user.keymaps if km.is_user_modified),
        "load_post": [getattr(f, "__module__", "") for f in bpy.app.handlers.load_post],
    }


def _keymap():
    return import_module(kit.MODULE + ".keymap")


def _diff(a, b):
    return [k for k in a if a[k] != b[k]]


def test_lifecycle_active_keyconfig_untouched():
    populate()
    before = _state()
    assert before["active"] == "Blender" and len(before["active_items"]) > 2000, len(before["active_items"])

    kit.enable(maya=False)
    try:
        alone = _state()
        alone["addon"] = [a for a in alone["addon"] if a[1] != "allset.switch_mode"]   # the switch's own shortcut
        assert not _diff(before, alone), _diff(before, alone)   # enabling alone: nothing else

        kit.maya_mode_on()
        km_mod = _keymap()
        _kcs().update()
        on = _state()
        assert km_mod.is_applied()
        assert on["active"] == before["active"] and on["stored"] == before["stored"], (on["active"], on["stored"])
        assert on["keyconfigs"] == before["keyconfigs"], "no keyconfig of the kit's own"
        assert on["user_modified"] == before["user_modified"], "no user keymap edit"
        assert len(on["addon"]) - len(before["addon"]) > 2000, "Maya items are add-on items"
        # the preset's own items of Maya keymaps are off (in memory), modal maps carry the Maya differences
        obj = _kcs().active.keymaps["Object Mode"]
        assert not [k for k in obj.keymap_items if k.active], "preset Object Mode items still on"
        assert bpy.app.timers.is_registered(km_mod._watch)
        # merged order = Maya order: the PASS_THROUGH-first item precedes Blender's click select
        user = [k.idname for k in _kcs().user.keymaps["3D View"].keymap_items
                if k.active and k.type == 'LEFTMOUSE' and k.value == 'CLICK' and not (k.shift or k.ctrl or k.alt)]
        data = next(km for km in km_mod.generate_data() if km[0] == "3D View")[2]["items"]
        want = [it[0] for it in data if it[1]["type"] == 'LEFTMOUSE' and it[1].get("value") == 'CLICK'
                and not any(it[1].get(m) for m in ("shift", "ctrl", "alt"))]
        assert user == want and user[0] == "allset.select_priority" and user[-1] == "view3d.select", (user, want)
        transform = _kcs().active.keymaps["Transform Modal Map"]
        assert any(k.active and k.propvalue == 'CANCEL' and k.type == 'RIGHTMOUSE' for k in transform.keymap_items)

        # the user picks another keyconfig: the Maya keymap follows it, the old one gets its items back
        other = _kcs().new("Lane K Test Preset")
        okm = other.keymaps.new("Object Mode")
        okm.keymap_items.new("object.delete", 'X', 'PRESS')
        default = _kcs().active
        try:
            _kcs().active = other
            km_mod._watch()
            assert not okm.keymap_items[0].active, "new active keyconfig not followed"
            assert _flags(default) == before["active_items"], "previous keyconfig not restored"
            _kcs().active = default
            km_mod._watch()
            assert okm.keymap_items[0].active
            assert not [k for k in default.keymaps["Object Mode"].keymap_items if k.active]
        finally:
            _kcs().active = default
            _kcs().remove(other)
            km_mod._watch()

        import_module(kit.MODULE + ".switch").set_mode(False)
        off = _state()
        assert not km_mod.is_applied() and not bpy.app.timers.is_registered(km_mod._watch)
        assert off["active_items"] == before["active_items"], "preset items not switched back on"
        assert not [a for a in off["addon"] if a[1].startswith("allset.") and a not in before["addon"]
                    and a[1] != "allset.switch_mode"], "Maya items left in the add-on keyconfig"
    finally:
        kit.disable()
    after = _state()
    d = _diff(before, after)
    assert not d, {k: (before[k], after[k]) for k in d} if "addon" not in d else d


def test_disable_in_maya_mode_restores_everything():
    populate()
    before = _state()
    kit.enable()
    assert _keymap().is_applied()
    kit.disable()
    d = _diff(before, _state())
    assert not d, d


def test_no_runtime_exec_of_keymap_data():
    """The IC data is static (tools/gen_ic_data.py); one file per Blender minor whose data changed."""
    ic = import_module(kit.MODULE + ".keymap.ic_data")
    assert ic.VERSIONS[0] == (5, 0), "no 4.5 data (the kit needs 5.0+)"
    assert ic.data_version((5, 0)) == (5, 0) and ic.data_version((5, 3)) == ic.VERSIONS[-1]
    assert ic.data_version((5, 1)) == (5, 1)
    data = ic.generate()
    assert len(data) >= 240 and data is not ic.generate()
