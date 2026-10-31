# SPDX-License-Identifier: GPL-3.0-or-later
"""``maya.cmds.file`` of the kit's look-alike (Issue #115): -new / -open / -rename / -save and the
-query flags scripts use (-sceneName, -shortName, -modified).

Maya's behaviour: ``file -rename`` only names the scene (returns the path),
``file -save`` writes it (returns the path), ``file -new`` returns "untitled", ``file -open`` returns the path, and
-new / -open on a modified scene without -force raise "Unsaved changes". The script goes on in the new scene.

Blender form: the kit can't read or write Maya files, so a ``.ma`` / ``.mb`` path becomes the same path with
``.blend``. New = the Maya Workflow Kit scene (the kit's ``startup.blend``: cm, Maya views), loaded
like Open with ``load_ui=False`` so the windows — Script Editor included — stay, as in Maya. Loading a file from a
Run Script is synchronous (the script's next line sees the new file); ``runner.run_text`` already
copes with its own Text being gone afterwards.
"""

import os

import bpy

from .cmds_shim import _Flags

MAYA_EXTENSIONS = (".ma", ".mb")
_state = {"name": ""}        # a -rename not saved yet (Blender can't name an unsaved file)


def blend_path(path):
    """``scene1.ma`` -> ``scene1.blend``; other paths as they are, with forward slashes like Maya."""
    path = str(path).replace("\\", "/")
    root, ext = os.path.splitext(path)
    return root + ".blend" if ext.lower() in MAYA_EXTENSIONS else path


def scene_name():
    return _state["name"] or bpy.data.filepath.replace("\\", "/")


def _check_unsaved(force):
    if bpy.data.is_dirty and not force:
        raise RuntimeError("Unsaved changes. Save the scene first, or use force=True.")


_window = {"ptr": 0}         # the window a script loaded a file from (see ``script_window``)


def _load(path):
    """A file read leaves the running script's context without window / screen (the next
    command had no ``selected_objects``; a ``temp_override`` around the load doesn't bring them back), so the window
    is remembered and every later cmds call runs in it (``cmds_shim._guarded``)."""
    _state["name"] = ""
    win = bpy.context.window
    _window["ptr"] = win.as_pointer() if win is not None else 0
    if path is None:
        from .. import app_template
        bpy.ops.wm.read_homefile(filepath=app_template.STARTUP, load_ui=False)
    else:
        bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)


def script_window():
    """The window to run a cmds call in when the context has none (after a load), else None."""
    wm = bpy.context.window_manager
    if bpy.context.window is not None or wm is None or not wm.windows:
        return None
    from .. import live_refs
    return live_refs.window(_window["ptr"]) or wm.windows[0]


def file(*args, **kwargs):  # noqa: A001 - Maya's command name
    f = _Flags("file", kwargs)
    query = f.get("query", "q", False)
    new = f.get("new", "new", False)
    open_ = f.get("open", "o", False)
    save = f.get("save", "s", False)
    rename = f.get("rename", "rn")
    force = f.get("force", "f", False)
    sn = f.get("sceneName", "sn", False)
    shn = f.get("shortName", "shn", False)
    modified = f.get("modified", "mf", False)
    f.get("type", "typ")
    f.get("prompt", "pmt", True)
    f.get("options", "op")
    f.get("ignoreVersion", "iv", False)
    f.done()
    if query:
        if sn or shn:
            name = scene_name()
            return os.path.basename(name) if shn else name
        if modified:
            return bool(bpy.data.is_dirty)
        raise TypeError("file -query needs -sceneName, -shortName or -modified")
    if rename is not None:
        _state["name"] = blend_path(rename)
        return _state["name"]
    if new:
        _check_unsaved(force)
        _load(None)
        return "untitled"
    if open_:
        if not args:
            raise RuntimeError("file -open needs a file name")
        path = blend_path(args[0])
        if not os.path.isfile(path):
            raise RuntimeError(f"File not found: {path}")
        _check_unsaved(force)
        _load(path)
        return bpy.data.filepath.replace("\\", "/")
    if save:
        target = _state["name"] or bpy.data.filepath
        if not target:
            raise RuntimeError("The scene has no name: use cmds.file(rename=path) first")
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=target)
        _state["name"] = ""
        return bpy.data.filepath.replace("\\", "/")
    raise TypeError("file: use new, open, save, rename or query")


__all__ = ["file", "blend_path", "scene_name"]
