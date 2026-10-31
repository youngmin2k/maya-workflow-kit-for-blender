"""The add-on preferences come back after Preferences > Add-ons off / on.

Blender deletes an add-on's preferences entry on ``addon_utils.disable(default_set=True)``; the kit copies the
settings the user changed into its extension user folder on unregister and puts them back when register finds a
fresh entry. Test sessions run with --factory-startup, where the copy is off, so this file switches that check off
for its own enable / disable cycles.
"""

import json
import os
from importlib import import_module

import bpy

import kit

AUTO_ENABLE = False

prefs_mod = import_module(kit.MODULE + ".preferences")


class _UserSession:
    """Run as a normal (not --factory-startup) session; the backup file is removed before and after."""

    def __enter__(self):
        self.keep = prefs_mod._factory_startup
        prefs_mod._factory_startup = lambda: False
        self.path = prefs_mod._backup_path()
        assert self.path, "no backup path (not installed as an extension?)"
        self.folder = os.path.dirname(self.path)
        if os.path.isfile(self.path):
            os.remove(self.path)
        self.before = _files(self.folder)
        return self

    def __exit__(self, *exc):
        if kit.is_enabled():
            kit.disable()
        prefs_mod._factory_startup = self.keep
        if os.path.isfile(self.path):
            os.remove(self.path)


def _files(folder):
    out = set()
    for root, _dirs, files in os.walk(folder):
        out |= {os.path.relpath(os.path.join(root, f), folder) for f in files}
    return out


def _prefs():
    return bpy.context.preferences.addons[kit.MODULE].preferences


def _change(p):
    p.select_through = False
    p.cb_speed = next(i.identifier for i in p.bl_rna.properties["cb_speed"].enum_items if i.identifier != p.cb_speed)
    p.curve_color_rules = "step289 marker"
    return {"select_through": p.select_through, "cb_speed": p.cb_speed, "curve_color_rules": p.curve_color_rules}


def test_settings_survive_disable_enable():
    with _UserSession() as s:
        kit.enable(maya=False)
        want = _change(_prefs())
        kit.disable()                       # Blender drops the preferences entry here
        assert os.path.isfile(s.path), "no backup written on disable"
        with open(s.path, encoding="utf-8") as fh:
            data = json.load(fh)
        assert {k: data.get(k) for k in want} == want, data
        kit.enable(maya=False)
        p = _prefs()
        assert {k: getattr(p, k) for k in want} == want, {k: getattr(p, k) for k in want}
        assert not p.maya_mode               # never switched on in this session, so still off


def test_maya_mode_comes_back_on():
    with _UserSession():
        kit.enable(maya=True)
        assert _prefs().maya_mode
        kit.disable()
        kit.enable(maya=False)
        assert _prefs().maya_mode, "Maya mode was on before the add-on was switched off"
        switch = import_module(kit.MODULE + ".switch")
        assert switch._registered[0], "Maya mode modules not registered after the restore"


def test_a_setting_put_back_to_default_stays_default():
    with _UserSession():
        kit.enable(maya=False)
        p = _prefs()
        want = _change(p)
        p.property_unset("select_through")   # back to its default
        p.cb_speed = p.bl_rna.properties["cb_speed"].default
        kit.disable()
        kit.enable(maya=False)
        p = _prefs()
        assert p.select_through is True and p.cb_speed == p.bl_rna.properties["cb_speed"].default, \
            (p.select_through, p.cb_speed)
        assert p.curve_color_rules == want["curve_color_rules"]


def test_all_settings_reset_restores_nothing():
    with _UserSession():
        kit.enable(maya=False)
        p = _prefs()
        _change(p)
        for name in prefs_mod._names():
            p.property_unset(name)
        kit.disable()
        kit.enable(maya=False)
        p = _prefs()
        assert not any(p.is_property_set(n) for n in prefs_mod._names()), \
            [n for n in prefs_mod._names() if p.is_property_set(n)]


def test_saved_settings_win_over_the_backup():
    """An update or a normal start keeps Blender's entry: a stale backup never overwrites it."""
    with _UserSession() as s:
        kit.enable(maya=False)
        _change(_prefs())
        prefs_mod.save_backup()
        _prefs().curve_color_rules = "newer"
        assert prefs_mod.restore_backup() == []
        assert _prefs().curve_color_rules == "newer"
        assert os.path.isfile(s.path)


def test_restore_runs_no_update_callback():
    with _UserSession() as s:
        kit.enable(maya=False)
        _prefs().maya_units = True             # its update changes the open file's units
        kit.disable()
        units_before = (bpy.context.scene.unit_settings.scale_length, bpy.context.scene.unit_settings.length_unit)
        kit.enable(maya=False)
        assert _prefs().maya_units
        assert (bpy.context.scene.unit_settings.scale_length,
                bpy.context.scene.unit_settings.length_unit) == units_before
        assert os.path.isfile(s.path)


def test_only_the_backup_file_is_written_in_the_user_folder():
    with _UserSession() as s:
        ext_root = os.path.normcase(os.path.abspath(bpy.utils.extension_path_user(kit.MODULE)))
        assert os.path.normcase(os.path.abspath(s.path)).startswith(ext_root + os.sep), (s.path, ext_root)
        kit.enable(maya=False)
        _change(_prefs())
        kit.disable()
        kit.enable(maya=False)
        kit.disable()
        assert _files(s.folder) - s.before == {prefs_mod.BACKUP_FILE}, _files(s.folder) - s.before


def test_factory_startup_writes_and_reads_nothing():
    assert bpy.app.factory_startup, "test sessions run with --factory-startup"
    assert prefs_mod._backup_path() is None
    kit.enable(maya=False)
    try:
        _change(_prefs())
    finally:
        kit.disable()
    folder = bpy.utils.extension_path_user(kit.MODULE)
    assert not os.path.isfile(os.path.join(folder, prefs_mod.BACKUP_FILE))
    kit.enable(maya=False)
    try:
        assert _prefs().select_through is True
    finally:
        kit.disable()
