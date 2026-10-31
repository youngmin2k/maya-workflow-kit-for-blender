"""Release check helper: does installing Maya Workflow Kit leave the user's own setup alone?

Runs inside a background Blender on the release sandbox (tools/release_check.py), without
--factory-startup so the sandbox preferences load like a user's:

    blender -b --python tools/release_probe.py -- seed  OUT.json   # a "user" setup, saved
    blender -b --python tools/release_probe.py -- check OUT.json   # what is there now
    blender -b --python tools/release_probe.py -- disable OUT.json # disable the kit, save, snapshot
    ... -- enable / make / remove OUT.json      # enable, Make Blender Maya, Remove from inside Blender
    ... -- offline_org OUT.json                 # switch off non-file:// remote repositories (repo_check)

ALLSET_REPO names the repository the kit is in (default user_default; tools/repo_check.py: mayakit).

``seed`` installs and enables a user add-on (a legacy add-on file), changes input preferences
and the theme the way a user might, saves the preferences and writes a snapshot; ``check`` only
writes the snapshot. release_check.py compares them (an install must not
delete add-ons or change the user's keymap settings).
"""

import hashlib
import json
import os
import sys

import addon_utils
import bpy

PROBE = "user_probe_addon"
PROBE_SOURCE = '''bl_info = {"name": "User Probe Add-on", "blender": (4, 2, 0), "category": "Development"}


def register():
    pass


def unregister():
    pass
'''
# input preferences a user might have changed (the kit's "Make Blender Maya" changes some of
# these on purpose; installing must not)
INPUTS = ("use_mouse_emulate_3_button", "view_rotate_method", "use_zoom_to_mouse", "invert_mouse_zoom",
          "use_mouse_depth_navigate", "use_auto_perspective", "use_rotate_around_active", "view_zoom_method",
          "view_zoom_axis", "invert_zoom_wheel", "drag_threshold_mouse", "use_numeric_input_advanced")
VIEW = ("ui_scale", "show_splash", "font_path_ui", "show_tooltips_python")


def _assert_sandbox():
    config = bpy.utils.user_resource('CONFIG')
    assert os.path.normcase(os.path.join("tmp", "release_env")) in os.path.normcase(config), config


def _theme_hash():
    h = hashlib.sha256()

    def walk(obj, depth=0):
        if depth > 6:
            return
        for p in obj.bl_rna.properties:
            if p.identifier in ("rna_type", "filepath"):
                continue
            v = getattr(obj, p.identifier)
            if p.type == 'POINTER' and v is not None and hasattr(v, "bl_rna"):
                walk(v, depth + 1)
            elif p.type in ('FLOAT', 'INT', 'BOOLEAN', 'ENUM', 'STRING'):
                if hasattr(v, "__len__") and not isinstance(v, str):
                    v = [round(x, 4) if isinstance(x, float) else x for x in v]
                elif isinstance(v, float):
                    v = round(v, 4)
                h.update(f"{p.identifier}={v};".encode())
    walk(bpy.context.preferences.themes[0])
    return h.hexdigest()


def snapshot():
    prefs = bpy.context.preferences
    scripts = bpy.utils.user_resource('SCRIPTS')
    return {
        "addons": sorted(a.module for a in prefs.addons),
        "probe_file": os.path.isfile(os.path.join(scripts, "addons", PROBE + ".py")),
        "active_keyconfig": prefs.keymap.active_keyconfig,
        "inputs": {n: repr(getattr(prefs.inputs, n)) for n in INPUTS},
        "undo_steps": prefs.edit.undo_steps,
        "view": {n: repr(getattr(prefs.view, n)) for n in VIEW},
        "theme": _theme_hash(),
        "blender": bpy.app.version_string,
        "kit_version": _kit_version(),
        "repos": sorted(r.module for r in prefs.extensions.repos),
    }


def _kit_version():
    """Version of the installed kit package (any repository), "" when not installed."""
    import re
    for repo in bpy.context.preferences.extensions.repos:
        path = os.path.join(repo.directory, "allset", "blender_manifest.toml")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                m = re.search(r'^version\s*=\s*"([^"]+)"', fh.read(), re.M)
            return m.group(1) if m else "?"
    return ""


def seed():
    prefs = bpy.context.preferences
    addons = os.path.join(bpy.utils.user_resource('SCRIPTS', path="addons", create=True))
    with open(os.path.join(addons, PROBE + ".py"), "w", encoding="utf-8") as fh:
        fh.write(PROBE_SOURCE)
    bpy.utils.refresh_script_paths()
    addon_utils.enable(PROBE, default_set=True)
    prefs.inputs.use_mouse_emulate_3_button = True
    prefs.inputs.view_rotate_method = 'TRACKBALL'
    prefs.inputs.use_zoom_to_mouse = True
    prefs.view.show_tooltips_python = True
    prefs.edit.undo_steps = 64
    prefs.themes[0].view_3d.grid = (0.9, 0.1, 0.1, 1.0)
    bpy.ops.wm.save_userpref()


def main():
    _assert_sandbox()
    mode, out = sys.argv[sys.argv.index("--") + 1:][:2]
    if mode == "seed":
        seed()
    elif mode == "make":
        # Make Blender Maya (theme, splash, density ...), saved like a user would leave it
        from importlib import import_module
        kit = next(a.module for a in bpy.context.preferences.addons if a.module.endswith(".allset"))
        import_module(kit + ".welcome").opt_in(open_layout=False)   # Maya mode on + Make Blender Maya
        bpy.ops.wm.save_userpref()
    elif mode == "remove":
        # Preferences > Extensions > Remove in a running session (the add-on's code runs: disable,
        # then the files go). `blender --command extension remove` never loads add-ons.
        repo = os.environ.get("ALLSET_REPO", "user_default")   # tools/repo_check.py: its own repository
        # repo_index counts enabled repositories only ($S\addons_core\bl_pkg\bl_extension_ops.py:811-830)
        from bl_pkg.bl_extension_ops import extension_repos_read
        repo_index = next(i for i, r in enumerate(extension_repos_read()) if r.module == repo)
        bpy.ops.extensions.package_uninstall(repo_index=repo_index, pkg_id="allset")
        bpy.ops.wm.save_userpref()
    elif mode == "offline_org":
        # tools/repo_check.py syncs only its own file:// repository: the built-in extensions.blender.org
        # repository is switched off in that sandbox so no test touches the network.
        for repo in bpy.context.preferences.extensions.repos:
            if repo.use_remote_url and not repo.remote_url.startswith("file://"):
                repo.enabled = False
        bpy.ops.wm.save_userpref()
    elif mode == "enable":
        repo = os.environ.get("ALLSET_REPO", "user_default")
        addon_utils.enable(f"bl_ext.{repo}.allset", default_set=True)
        bpy.ops.wm.save_userpref()
    elif mode == "disable":
        kit = next(a.module for a in bpy.context.preferences.addons if a.module.endswith(".allset"))
        addon_utils.disable(kit, default_set=True)
        bpy.ops.wm.save_userpref()
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(snapshot(), fh, indent=1)


main()
