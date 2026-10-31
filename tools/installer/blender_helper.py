"""Runs inside a background Blender for the Windows installer (tools/installer/allset_setup.ps1).

    blender -b --python blender_helper.py -- make   OUT.json   # Make Blender Maya (layout template, theme ...)
    blender -b --python blender_helper.py -- remove OUT.json   # uninstall the way Preferences > Remove does
    blender -b --python blender_helper.py -- status OUT.json   # what is installed / enabled

``remove`` runs inside Blender on purpose: the kit's unregister puts the user's keymap, theme and
preferences back before the files go. ``blender --command extension remove`` never loads add-ons and
can't do that. Writes {"ok": bool, "message": str, ...} to OUT.json.
No network, no other add-on touched.
"""

import json
import sys

import addon_utils
import bpy

PKG = "allset"


def kit_module():
    """bl_ext.<repo>.allset of the installed kit (enabled or not), else None."""
    for mod in addon_utils.modules(refresh=False):
        name = mod.__name__
        if name.startswith("bl_ext.") and name.endswith("." + PKG):
            return name
    return None


def status():
    module = kit_module()
    prefs = bpy.context.preferences
    return {"installed": module is not None, "module": module or "",
            "enabled": bool(module) and module in prefs.addons,
            "keyconfig": prefs.keymap.active_keyconfig,
            "config": bpy.utils.user_resource('CONFIG'),
            "blender": bpy.app.version_string}


def make():
    module = kit_module()
    if not module or module not in bpy.context.preferences.addons:
        return False, "Maya Workflow Kit is not enabled"
    from importlib import import_module
    import_module(module + ".welcome").opt_in(open_layout=False)   # Maya mode on + Make Blender Maya
    bpy.ops.wm.save_userpref()
    return True, "Make Blender Maya done"


def remove():
    module = kit_module()
    if not module:
        return True, "Maya Workflow Kit is not installed (nothing to remove)"
    repo = module.split(".")[1]
    # repo_index counts enabled repositories only ($S\addons_core\bl_pkg\bl_extension_ops.py:811-830)
    from bl_pkg.bl_extension_ops import extension_repos_read
    repo_index = next((i for i, r in enumerate(extension_repos_read()) if r.module == repo), None)
    if repo_index is None:
        return False, f"repository {repo} is disabled: enable it or remove Maya Workflow Kit in Preferences"
    bpy.ops.extensions.package_uninstall(repo_index=repo_index, pkg_id=PKG)
    bpy.ops.wm.save_userpref()
    return kit_module() is None, "Maya Workflow Kit removed, your Blender settings are back"


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    mode, out = (args + ["status", ""])[:2]
    result = {"mode": mode}
    try:
        if mode == "make":
            result["ok"], result["message"] = make()
        elif mode == "remove":
            result["ok"], result["message"] = remove()
        else:
            result["ok"], result["message"] = True, "status"
    except Exception as ex:   # reported to the installer, which shows it
        result["ok"], result["message"] = False, f"{type(ex).__name__}: {ex}"
    result.update(status())
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=1)
    print("ALLSET_HELPER", json.dumps(result))


main()
