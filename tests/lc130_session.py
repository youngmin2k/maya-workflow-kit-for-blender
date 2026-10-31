"""One Blender session of the install / remove check (run by test_step130_lifecycle.py, not a test file).

    blender -b --python tests/lc130_session.py -- <out.json> <action> [<action> ...]

Runs with sandbox BLENDER_USER_* folders (the caller creates them under tmp/), WITHOUT --factory-startup so the saved
preferences of the previous session are read. Actions: save (the user saves the preferences), maya_cycle (Maya mode on,
Make Blender Maya, off), maya_on (Maya mode on + Make Blender Maya, left on), uninstall (Preferences > Extensions >
Remove from inside Blender: the add-on's code runs). Writes {"dump": tests/rt60_dump.dump(), "kit": enabled?}.
"""

import json
import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit  # noqa: E402
from rt60_dump import dump  # noqa: E402

for _kind in ('CONFIG', 'SCRIPTS', 'EXTENSIONS'):
    _path = os.path.abspath(bpy.utils.user_resource(_kind)).replace("\\", "/")
    assert "/tmp/" in _path, (_kind, _path)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    out, actions = argv[0], argv[1:]
    for action in actions:
        if action == "save":
            bpy.ops.wm.save_userpref()
        elif action in ("maya_cycle", "maya_on"):
            assert kit.is_enabled(), "installed with --enable"
            sw = import_module(kit.MODULE + ".switch")
            sw.set_mode(True)
            import_module(kit.MODULE + ".first_start").make(bpy.context, open_layout=False)
            if action == "maya_cycle":
                sw.set_mode(False)
        elif action == "uninstall":
            from bl_pkg.bl_extension_ops import extension_repos_read
            repo_index = next(i for i, r in enumerate(extension_repos_read()) if r.module == "user_default")
            bpy.ops.extensions.package_uninstall(repo_index=repo_index, pkg_id="allset")
        else:
            raise ValueError(action)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"dump": dump(), "kit": kit.is_enabled()}, fh)


main()
