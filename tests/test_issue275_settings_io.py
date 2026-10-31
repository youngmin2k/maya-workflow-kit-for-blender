"""#275: Export / Import of the kit's settings (preferences with option window values, changed kit hotkeys, user
shelves, marking menus) to one JSON file, so they come back after a reinstall or on another computer."""

import json
import os
import tempfile
from importlib import import_module

import bpy

import kit
from rt60_dump import populate


def m(name):
    return import_module(f"{kit.MODULE}.{name}")


def _prefs():
    return bpy.context.preferences.addons[kit.MODULE].preferences


def _row(command, context="global"):
    return next(r for r in m("ui.hotkey_editor").rows() if r["command"] == command and r["context"] == context)


def _key(row):
    he = m("ui.hotkey_editor")
    _km, kmi = he.editable_item(bpy.context, row)
    return he.item_event(kmi), kmi.is_user_modified


class _Files:
    """Keep the user shelves / marking menus files of this session and put them back afterwards."""

    def __enter__(self):
        self.paths = [m("ui.shelf").store_path(), m("marking.user_menus").store_path()]
        self.keep = {p: open(p, encoding="utf-8").read() if os.path.isfile(p) else None for p in self.paths}
        self.tmp = tempfile.mkdtemp(prefix="allset275_")
        return self

    def __exit__(self, *exc):
        for p, text in self.keep.items():
            if text is None:
                if os.path.isfile(p):
                    os.remove(p)
            else:
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(text)
        m("ui.shelf").reload_user()
        m("marking.user_menus").load()
        m("marking").apply_user_menus()
        m("ui.hotkey_editor").restore_all(bpy.context)
        for name in m("preferences")._names():
            if name != "maya_mode":
                _prefs().property_unset(name)


def _change_everything():
    populate()
    ctx = bpy.context
    p = _prefs()
    p.curve_color_rules = "issue275 marker"
    p.select_through = False
    p.option_settings = json.dumps({"issue275": {"size": 3}})
    he = m("ui.hotkey_editor")
    ok, _ = he.assign(ctx, _row("SelectToggleMode"), {"type": "F9", "ctrl": True})
    assert ok
    shelf = m("ui.shelf")
    shelf.user_data()["shelves"].append({"name": "issue275", "buttons": [{"label": "x", "script": "", "icon": ""}]})
    shelf.save_user()
    um = m("marking.user_menus")
    doc = um.document()
    doc["custom"]["issue275menu"] = {"label": "issue275menu", "items": []}
    um.save()


def _reset_everything():
    ctx = bpy.context
    for name in m("preferences")._names():
        if name != "maya_mode":
            _prefs().property_unset(name)
    m("ui.hotkey_editor").restore_all(ctx)
    for p in (m("ui.shelf").store_path(), m("marking.user_menus").store_path()):
        if os.path.isfile(p):
            os.remove(p)
    m("ui.shelf").reload_user()
    m("marking.user_menus").load()


def test_export_then_import_brings_everything_back():
    sio = m("settings_io")
    with _Files() as f:
        _change_everything()
        path = os.path.join(f.tmp, "kit.json")
        assert bpy.ops.allset.settings_export(filepath=path) == {'FINISHED'}
        data = json.load(open(path, encoding="utf-8"))
        assert data["format"] == sio.FORMAT and data["version"] == sio.VERSION
        assert data["preferences"]["curve_color_rules"] == "issue275 marker"
        assert data["preferences"]["select_through"] is False
        assert json.loads(data["preferences"]["option_settings"]) == {"issue275": {"size": 3}}
        assert "maya_mode" not in data["preferences"]
        assert [h["command"] for h in data["hotkeys"]] == ["SelectToggleMode"], data["hotkeys"]
        assert data["hotkeys"][0]["key"] == {"type": "F9", "ctrl": True, "alt": False, "shift": False,
                                             "oskey": False}
        assert "issue275" in [s["name"] for s in data["shelves"]["shelves"]]
        assert "issue275menu" in data["marking_menus"]["custom"]

        _reset_everything()
        assert _prefs().curve_color_rules == "" and _prefs().select_through
        assert _key(_row("SelectToggleMode"))[0]["type"] == "F8"
        assert "issue275" not in [s["name"] for s in m("ui.shelf").user_data()["shelves"]]

        assert bpy.ops.allset.settings_import(filepath=path) == {'FINISHED'}
        p = _prefs()
        assert p.curve_color_rules == "issue275 marker" and not p.select_through
        assert json.loads(p.option_settings) == {"issue275": {"size": 3}}
        assert p.maya_mode
        ev, changed = _key(_row("SelectToggleMode"))
        assert (ev["type"], ev["ctrl"], changed) == ("F9", True, True), ev
        assert "issue275" in [s["name"] for s in m("ui.shelf").user_data()["shelves"]]
        assert "issue275menu" in m("marking.user_menus").document()["custom"]
        assert "issue275menu" in m("marking.menus").MENUS


def test_import_only_chosen_parts():
    with _Files() as f:
        _change_everything()
        path = os.path.join(f.tmp, "kit.json")
        bpy.ops.allset.settings_export(filepath=path)
        _reset_everything()
        bpy.ops.allset.settings_import(filepath=path, preferences=False, shelves=False, marking_menus=False)
        assert _prefs().curve_color_rules == ""
        assert "issue275" not in [s["name"] for s in m("ui.shelf").user_data()["shelves"]]
        assert _key(_row("SelectToggleMode"))[0]["type"] == "F9"


def test_hotkey_editor_export_and_import():
    with _Files() as f:
        _change_everything()
        path = os.path.join(f.tmp, "hotkeys.json")
        bpy.ops.allset.settings_export(filepath=path, preferences=False, shelves=False, marking_menus=False)
        data = json.load(open(path, encoding="utf-8"))
        assert set(data) == {"format", "version", "kit_version", "hotkeys"}, set(data)
        m("ui.hotkey_editor").restore_all(bpy.context)
        assert _key(_row("SelectToggleMode"))[0]["type"] == "F8"
        assert bpy.ops.allset.hotkey_import(filepath=path) == {'FINISHED'}
        assert _key(_row("SelectToggleMode"))[0]["type"] == "F9"


def test_bad_files_are_refused_and_unknown_entries_skipped():
    sio = m("settings_io")
    with _Files() as f:
        populate()
        bad = os.path.join(f.tmp, "bad.json")
        with open(bad, "w", encoding="utf-8") as fh:
            json.dump({"hello": 1}, fh)
        try:
            bpy.ops.allset.settings_import(filepath=bad)
        except RuntimeError as exc:            # an ERROR report raises in Python
            assert "not a Maya Workflow Kit settings file" in str(exc), exc
        else:
            raise AssertionError("a foreign file was imported")
        newer = {"format": sio.FORMAT, "version": sio.VERSION + 1}
        try:
            sio.apply(bpy.context, newer)
        except ValueError:
            pass
        else:
            raise AssertionError("a newer file was imported")
        lines = sio.apply(bpy.context, {
            "format": sio.FORMAT, "version": 1,
            "preferences": {"no_such_setting": 1, "cb_speed": "NO_SUCH_ITEM", "curve_color_rules": "ok"},
            "hotkeys": [{"context": "global", "command": "NoSuchCommand", "key": {"type": "F9"}},
                        {"context": "global", "command": "SelectToggleMode", "key": {"type": "NOT_A_KEY"}}]})
        assert _prefs().curve_color_rules == "ok"
        assert lines[0] == "1 setting(s), 2 unknown", lines
        assert lines[1] == "0 hotkey(s), 2 left out", lines
        assert _key(_row("SelectToggleMode"))[0]["type"] == "F8"


def test_maya_mode_off_keeps_files_and_preferences():
    sio = m("settings_io")
    with _Files() as f:
        _change_everything()
        path = os.path.join(f.tmp, "kit.json")
        bpy.ops.allset.settings_export(filepath=path)
        switch = m("switch")
        switch.set_mode(False, layout=False)
        try:
            data, notes = sio.collect(bpy.context)
            assert "hotkeys" not in data and notes, notes
            assert data["preferences"]["curve_color_rules"] == "issue275 marker"
            for name in m("preferences")._names():
                if name != "maya_mode":
                    _prefs().property_unset(name)
            lines = sio.import_file(bpy.context, path)
            assert _prefs().curve_color_rules == "issue275 marker"
            assert any("turn Maya mode on" in s for s in lines), lines
            assert not _prefs().maya_mode
        finally:
            switch.set_mode(True, layout=False)
