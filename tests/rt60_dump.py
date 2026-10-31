"""What "the user's Blender setup" is for the switch round trip: every preference value, the
user keyconfig (with the user's key edits), the active keyconfig, the theme as XML, the
enabled add-ons. The kit's own add-on entry is left out (it stays installed in Blender mode)."""

import os
import tempfile

import bpy

import kit


def theme_xml():
    try:
        import rna_xml
    except ImportError:
        import _rna_xml as rna_xml
    fd, path = tempfile.mkstemp(suffix=".xml")
    os.close(fd)
    try:
        rna_xml.xml_file_write(bpy.context.preferences, path,
                               (("themes[0]", "Theme"), ("ui_styles[0]", "ThemeStyle")))
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    finally:
        os.remove(path)


def walk(struct, prefix="", out=None, depth=0):
    """kit._walk with enum-flag sets sorted (their order is not stable)."""
    out = {} if out is None else out
    for prop in struct.bl_rna.properties:
        ident = prop.identifier
        if ident == "rna_type" or depth > 6:
            continue
        value = getattr(struct, ident)
        key = f"{prefix}{ident}"
        if prop.type == 'POINTER':
            if value is not None:
                walk(value, key + ".", out, depth + 1)
        elif prop.type == 'COLLECTION':
            for i, item in enumerate(value):
                walk(item, f"{key}[{i}].", out, depth + 1)
        elif isinstance(value, set):
            out[key] = repr(tuple(sorted(value)))
        elif isinstance(value, float):
            out[key] = repr(round(value, 5))
        elif isinstance(value, (str, int, bool)):
            out[key] = repr(value)
        else:
            out[key] = repr(tuple(round(v, 5) if isinstance(v, float) else v for v in value))
    return out


def keymaps(kc):
    out = []
    for km in kc.keymaps:
        for kmi in km.keymap_items:
            if kmi.idname.startswith("allset."):
                continue   # The kit's own switch shortcut stays in Blender mode (by design)
            out.append(f"{km.name}|{kmi.idname}|{kmi.type}|{kmi.value}|{kmi.ctrl}{kmi.shift}{kmi.alt}"
                       f"|{kmi.active}|{kmi.is_user_modified}")
    return out


def populate():
    """Background Blender leaves the default keyconfig empty
    (``-b``): fill it from Blender's keymap data so the user keyconfig
    (default + the user's saved key edits) exists like in the UI."""
    kcs = bpy.context.window_manager.keyconfigs
    km = kcs.default.keymaps.get("Object Mode")
    if km is None or len(km.keymap_items) == 0:
        import sys
        from bl_keymap_utils.io import keyconfig_init_from_data
        path = bpy.utils.system_resource('SCRIPTS', path="presets/keyconfig/keymap_data")
        if path not in sys.path:
            sys.path.insert(0, path)
        import blender_default
        keyconfig_init_from_data(kcs.default, blender_default.generate_keymaps(blender_default.Params()))
    kcs.update()


def edit_user_key():
    """The user's own key edit: Object Mode delete on F9."""
    populate()
    kcs = bpy.context.window_manager.keyconfigs
    km = kcs.user.keymaps["Object Mode"]
    kmi = next(k for k in km.keymap_items if k.idname == "object.delete")
    kmi.type = 'F9'
    kcs.update()


def dump():
    populate()
    prefs = bpy.context.preferences
    values = {}
    for name in ("view", "edit", "inputs", "system", "filepaths", "keymap", "experimental", "apps"):
        struct = getattr(prefs, name, None)
        if struct is not None:
            values.update({f"{name}.{k}": v for k, v in walk(struct).items()})
    for k in [k for k in values if k in ("system.ui_scale", "system.pixel_size", "system.ui_line_width")]:
        values.pop(k)   # window dependent (0 in background)
    kcs = bpy.context.window_manager.keyconfigs
    return {
        "values": values,
        "active_keyconfig": kcs.active.name if kcs.active else "",
        "keyconfigs": sorted(k.name for k in kcs),
        "user_keymaps": keymaps(kcs.user),
        "theme_xml": theme_xml(),
        "theme_filepath": prefs.themes[0].filepath,
        "theme_name": prefs.themes[0].name,
        "addons": sorted(a.module for a in prefs.addons if a.module != kit.MODULE),
    }
