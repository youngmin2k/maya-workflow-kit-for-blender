# SPDX-License-Identifier: GPL-3.0-or-later
"""Export / Import of the kit's own settings to one JSON file (#275).

Maya users carry their settings between machines and versions (Maya's Hotkey Editor exports a hotkey set, shelves
are files). The kit keeps its settings in three places: the add-on preferences (stored by Blender with its
preferences, option window values included), the kit hotkey changes (Blender keymap edits of the kit's add-on items)
and files in the extension's user folder (user shelves, marking menus). Disabling and enabling the kit or updating
it keeps all of them; removing it, or starting a new Blender without its previous settings, does not. One settings
file carries them over:

``{"format": FORMAT, "version": VERSION, "kit_version": "...", "preferences": {...}, "hotkeys": [...],
"shelves": {...}, "marking_menus": {...}}`` — every part is optional.

- preferences: only the settings that differ from a fresh install (``maya_mode`` stays out: the Maya / Blender switch
  is not a setting to carry);
- hotkeys: the kit hotkeys the user changed, by Maya command + context; they need Maya mode on (the kit's keys exist
  only then): imported with Maya mode off, they wait in the extension's user folder and are given the next time
  Maya mode starts;
- shelves / marking_menus: the stored documents as they are.

Importing replaces the parts that are in the file and chosen in the dialog; kit hotkeys the file doesn't name keep
their current key. Nothing in the file is run, and Blender's own preferences are never written.
"""

import json
import os

import bpy
from bpy.props import BoolProperty, StringProperty

from . import preferences, switch

FORMAT = "maya-workflow-kit-settings"
VERSION = 1
DEFAULT_NAME = "maya_workflow_kit_settings.json"
PARTS = ("preferences", "hotkeys", "shelves", "marking_menus")
SKIP_PREFS = frozenset(("maya_mode",))
MODIFIERS = ("ctrl", "alt", "shift", "oskey")


def _kit_version():
    import addon_utils
    for mod in addon_utils.modules():
        if mod.__name__ == __package__:
            return ".".join(str(v) for v in addon_utils.module_bl_info(mod).get("version", ()))
    return ""


# --- preferences ------------------------------------------------------------------------------------------------

def _plain(value):
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, (bool, int, float, str)):
        return value
    return list(value)                          # vector values


def export_preferences(prefs):
    return {name: _plain(getattr(prefs, name)) for name in preferences._names()
            if name not in SKIP_PREFS and prefs.is_property_set(name)}


def import_preferences(prefs, data):
    """Write the file's settings; a setting the file leaves out goes back to its default. Returns (done, skipped)."""
    done, skipped = [], []
    for name in preferences._names():
        if name in SKIP_PREFS:
            continue
        if name not in data:
            if prefs.is_property_set(name):
                prefs.property_unset(name)
            continue
        value = data[name]
        try:
            if name == 'inview_layouts':
                from .ui.in_view_editor import validate_layouts
                validate_layouts(value)
            flag = getattr(prefs.bl_rna.properties[name], "is_enum_flag", False)
            setattr(prefs, name, set(value) if flag else value)
            done.append(name)
        except (TypeError, ValueError, AttributeError):
            skipped.append(name)                # changed type or lost an enum item since the file was written
    skipped += [n for n in data if n not in done and n not in skipped and n not in SKIP_PREFS]
    from .ui import in_view_editor
    try:
        in_view_editor.persist_layouts(bpy.context, prefs=prefs)
        in_view_editor.clear()
    except OSError:
        skipped.append('inview_layouts')
    return done, skipped


# --- hotkeys ----------------------------------------------------------------------------------------------------

def _hotkey_editor():
    from .ui import hotkey_editor
    return hotkey_editor


def export_hotkeys(context):
    """[{context, command, maya_key, key: {type, ctrl, alt, shift, oskey}}] of the changed kit hotkeys."""
    he = _hotkey_editor()
    out = []
    for row in he.changed_rows(context):
        _km, kmi = he.editable_item(context, row)
        ev = he.item_event(kmi)
        out.append({"context": row["context"], "command": row["command"], "maya_key": row["maya_key"],
                    "key": {"type": ev["type"], **{m: bool(ev.get(m)) for m in MODIFIERS}}})
    return out


def import_hotkeys(context, items):
    """Give the named kit hotkeys the file's keys. Returns (done, skipped [(command, reason)])."""
    he = _hotkey_editor()
    by_name = {}
    for row in he.rows():
        if row["editable"]:
            by_name.setdefault((row["context"], row["command"]), row)
    types = {i.identifier for i in bpy.types.KeyMapItem.bl_rna.properties["type"].enum_items}
    done, skipped = 0, []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("key"), dict):
            continue
        name = (item.get("context"), item.get("command"))
        row, key = by_name.get(name), item["key"]
        if row is None:
            skipped.append((name[1], "no kit hotkey for this command"))
            continue
        if key.get("type") not in types:
            skipped.append((name[1], f"unknown key {key.get('type')!r}"))
            continue
        ok, _clash = he.assign(context, row, {"type": key["type"], **{m: bool(key.get(m)) for m in MODIFIERS}})
        if ok:
            done += 1
        else:
            skipped.append((name[1], "the kit key can't be changed here"))
    if done or items:
        he.refresh(context)
    return done, skipped


# --- files in the extension's user folder -----------------------------------------------------------------------

def _read(path):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _write(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def _shelf_path():
    from .ui import shelf
    return shelf.store_path()


def _menus_path():
    from .marking import user_menus
    return user_menus.store_path()


def _reload_files():
    """Maya mode on: show the imported shelves / marking menus now (Maya mode off reads the files when it starts)."""
    if not switch.is_on():
        return
    from .ui import shelf
    from . import marking
    from .marking import user_menus
    shelf.reload_user()
    user_menus.load()
    marking.apply_user_menus()
    wm = bpy.context.window_manager
    for window in wm.windows if wm else ():
        for area in window.screen.areas:
            area.tag_redraw()


def _pending_path():
    return os.path.join(os.path.dirname(_shelf_path()), "pending_hotkeys.json")


def has_pending():
    return os.path.isfile(_pending_path())


def apply_pending(context):
    """Maya mode just started: give the hotkeys an import made with Maya mode off. Returns the number given (None =
    nothing was waiting)."""
    path = _pending_path()
    data = _read(path)
    if data is None:
        if os.path.isfile(path):
            os.remove(path)
        return None
    try:
        context.window_manager.keyconfigs.update()     # the kit's keys were just added: the user items follow
        items = data.get("hotkeys") if isinstance(data, dict) else None
        done, skipped = import_hotkeys(context, items) if isinstance(items, list) else (0, [])
        for name, reason in skipped[:20]:
            print(f"Settings import: hotkey {name}: {reason}")
    finally:
        os.remove(path)
    return done


# --- the file ---------------------------------------------------------------------------------------------------

def collect(context, parts=PARTS):
    """The settings document. Returns (document, notes about parts left out)."""
    data = {"format": FORMAT, "version": VERSION, "kit_version": _kit_version()}
    notes = []
    if "preferences" in parts:
        data["preferences"] = export_preferences(preferences.get(context))
    if "hotkeys" in parts:
        if switch.is_on():
            data["hotkeys"] = export_hotkeys(context)
        else:
            notes.append("hotkeys left out: the kit hotkeys exist only in Maya mode")
    if "shelves" in parts:
        shelves = _read(_shelf_path())
        if isinstance(shelves, dict):
            data["shelves"] = shelves
    if "marking_menus" in parts:
        menus = _read(_menus_path())
        if isinstance(menus, dict):
            data["marking_menus"] = menus
    return data, notes


def check(data):
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("not a Maya Workflow Kit settings file")
    if not isinstance(data.get("version"), int) or data["version"] > VERSION:
        raise ValueError("written by a newer Maya Workflow Kit: update the kit to import it")


def apply(context, data, parts=PARTS):
    """Import the chosen parts of a checked document. Returns a list of result lines."""
    check(data)
    lines = []
    if "preferences" in parts and isinstance(data.get("preferences"), dict):
        done, skipped = import_preferences(preferences.get(context), data["preferences"])
        lines.append(f"{len(done)} setting(s)" + (f", {len(skipped)} unknown" if skipped else ""))
    if "hotkeys" in parts and isinstance(data.get("hotkeys"), list):
        if switch.is_on():
            done, skipped = import_hotkeys(context, data["hotkeys"])
            for name, reason in skipped[:20]:
                print(f"Settings import: hotkey {name}: {reason}")
            lines.append(f"{done} hotkey(s)" + (f", {len(skipped)} left out" if skipped else ""))
        else:
            _write(_pending_path(), {"hotkeys": data["hotkeys"]})
            lines.append(f"{len(data['hotkeys'])} hotkey(s) kept for Maya mode (given when Maya mode starts)")
    if "shelves" in parts and isinstance(data.get("shelves"), dict) \
            and isinstance(data["shelves"].get("shelves"), list):
        _write(_shelf_path(), data["shelves"])
        lines.append(f"{len(data['shelves']['shelves'])} user shelf(s)")
    if "marking_menus" in parts and isinstance(data.get("marking_menus"), dict):
        _write(_menus_path(), data["marking_menus"])
        lines.append("marking menus")
    _reload_files()
    return lines


def export_file(context, path, parts=PARTS):
    data, notes = collect(context, parts)
    _write(path, data)
    return data, notes


def import_file(context, path, parts=PARTS):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return apply(context, data, parts)


# --- operators --------------------------------------------------------------------------------------------------

def _say(op, text):
    if switch.is_on():
        from . import results
        results.result(op, text)
    else:
        print("Maya Workflow Kit:", text)


class _Parts:
    preferences: BoolProperty(name="Preferences", default=True,
                              description="The kit's preferences, option window values included")
    hotkeys: BoolProperty(name="Hotkeys", default=True, description="The kit hotkeys you changed (Maya mode on)")
    shelves: BoolProperty(name="Shelves", default=True, description="User shelves and buttons added to shelves")
    marking_menus: BoolProperty(name="Marking Menus", default=True,
                                description="Marking menus you edited or made")
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def parts(self):
        return tuple(p for p in PARTS if getattr(self, p))


class ALLSET_OT_settings_export(_Parts, bpy.types.Operator):
    """Save the kit's settings (preferences, changed hotkeys, shelves, marking menus) to a file, to import them
    after a reinstall or on another computer"""
    bl_idname = "allset.settings_export"
    bl_label = "Export Settings..."
    bl_options = {'INTERNAL'}

    filepath: StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'})
    check_existing: BoolProperty(default=True, options={'HIDDEN'})

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = DEFAULT_NAME
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        path = bpy.path.ensure_ext(self.filepath, ".json")
        try:
            data, notes = export_file(context, path, self.parts())
        except OSError as exc:
            self.report({'ERROR'}, f"Could not write {path}: {exc}")
            return {'CANCELLED'}
        for note in notes:
            self.report({'WARNING'}, note)
        _say(self, f"Exported settings to {os.path.basename(path)}")
        return {'FINISHED'}


class ALLSET_OT_settings_import(_Parts, bpy.types.Operator):
    """Load kit settings exported with Export Settings (only settings are read; nothing in the file is run)"""
    bl_idname = "allset.settings_import"
    bl_label = "Import Settings..."
    bl_options = {'INTERNAL'}

    filepath: StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        try:
            lines = import_file(context, self.filepath, self.parts())
        except (OSError, ValueError) as exc:
            self.report({'ERROR'}, f"Could not import {os.path.basename(self.filepath)}: {exc}")
            return {'CANCELLED'}
        _say(self, "Imported " + ("; ".join(lines) if lines else "nothing"))
        return {'FINISHED'}


classes = (ALLSET_OT_settings_export, ALLSET_OT_settings_import)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
