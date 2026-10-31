# SPDX-License-Identifier: GPL-3.0-or-later
"""Project autosave, like Maya's Preferences > Files/Projects > AutoSave (Issue #254).

Blender's own auto save writes one recovery file per session into the system temp folder. The kit autosave instead
saves a copy of the open scene into the current project's ``autosave`` folder (or a named folder) every N minutes:

- ``<scene>.0001.blend``, ``<scene>.0002.blend`` ... (one past the highest number already there; ``untitled`` for a
  scene that was never saved);
- with "Limit autosaves" on, the oldest copies of that scene go once there are more than the set number;
- the copy is written with ``save_as_mainfile(copy=True)``: the open file keeps its own path and unsaved state;
- nothing is written while the scene is unchanged since the last autosave / save / open, while a modal tool or a
  render runs (it tries again a few seconds later), or in a background (``-b``) session.

The settings are kit add-on preferences (``autosave_*``), shown on the Maya Preferences window's Files/Projects page.
"""

import os
import re
import time

import bpy
from bpy.app.handlers import persistent

POLL = 5.0              # seconds between checks of the interval
RETRY = 5.0             # wait after a check that was blocked by a modal tool / render
UNTITLED = "untitled"
EXT = ".blend"
JOBS = ('RENDER', 'RENDER_PREVIEW', 'OBJECT_BAKE', 'COMPOSITE')

_state = {"last": None, "changed": False, "saving": False, "last_path": ""}


def _prefs(context=None):
    from .. import preferences
    try:
        return preferences.get(context)
    except (KeyError, AttributeError):
        return None


def saving():
    """True while the kit writes an autosave copy (other save handlers can skip it)."""
    return _state["saving"]


def folder(context=None):
    """The folder autosave copies go to: ``<current project>/autosave`` or the named folder."""
    prefs = _prefs(context)
    if prefs is not None and prefs.autosave_destination == 'FOLDER' and prefs.autosave_folder:
        return os.path.abspath(bpy.path.abspath(prefs.autosave_folder))
    from . import project
    return os.path.join(project.current_root(context), "autosave")


def scene_stem(filepath=None):
    """The file name the copies are numbered under: the open file's name, ``untitled`` for a new scene."""
    path = bpy.data.filepath if filepath is None else filepath
    if not path:
        return UNTITLED
    return os.path.splitext(os.path.basename(path))[0] or UNTITLED


def _pattern(stem):
    return re.compile(r"^" + re.escape(stem) + r"\.(\d+)" + re.escape(EXT) + r"$", re.IGNORECASE)


def copies(directory, stem):
    """[(number, path)] of the autosave copies of ``stem`` in ``directory``, oldest (lowest number) first."""
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    pat = _pattern(stem)
    out = []
    for name in names:
        m = pat.match(name)
        if m and os.path.isfile(os.path.join(directory, name)):
            out.append((int(m.group(1)), os.path.join(directory, name)))
    out.sort()
    return out


def next_path(directory, stem):
    """``<stem>.NNNN.blend`` one past the highest number in ``directory``."""
    existing = copies(directory, stem)
    n = existing[-1][0] + 1 if existing else 1
    return os.path.join(directory, f"{stem}.{n:04d}{EXT}")


def prune(directory, stem, keep):
    """Remove the oldest copies of ``stem`` beyond ``keep``; the removed paths."""
    existing = copies(directory, stem)
    removed = []
    for _n, path in existing[:max(0, len(existing) - max(1, keep))]:
        try:
            os.remove(path)
            removed.append(path)
        except OSError:
            pass
    return removed


def busy(context=None):
    """True while a modal operator (a tool drag, a file browser ...) or a render / bake job runs."""
    context = context or bpy.context
    wm = context.window_manager
    # the kit's click listeners hold no scene edits and stay up all session: they don't count
    from ..modal_listeners import tool_running
    if wm and tool_running(wm):
        return True
    for job in JOBS:
        try:
            if bpy.app.is_job_running(job):
                return True
        except (TypeError, ValueError, AttributeError):
            pass
    return False


def reset(now=None):
    """Start the interval again (enable, file open / save)."""
    _state["last"] = time.monotonic() if now is None else now
    _state["changed"] = False


def write_copy(context=None, path=None):
    """Save a copy of the open scene to ``path`` (default: the next autosave name); the path or None."""
    context = context or bpy.context
    directory = folder(context)
    if path is None:
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as ex:
            print(f"Autosave: can't make {directory}: {ex}")
            return None
        path = next_path(directory, scene_stem())
    wm = context.window_manager
    window = wm.windows[0] if wm is not None and len(wm.windows) else None
    _state["saving"] = True
    try:
        if window is not None:
            with context.temp_override(window=window):
                res = bpy.ops.wm.save_as_mainfile(filepath=path, copy=True, check_existing=False)
        else:
            res = bpy.ops.wm.save_as_mainfile(filepath=path, copy=True, check_existing=False)
    except RuntimeError as ex:
        print(f"Autosave: {path} not written: {ex}")
        return None
    finally:
        _state["saving"] = False
    if 'FINISHED' not in res or not os.path.isfile(path):
        return None
    _state["last_path"] = path
    return path


def tick(context=None, now=None, allow_background=False):
    """One check: autosave when it is on, the interval has passed and the scene changed.

    Returns (saved path or None, seconds until the next check)."""
    context = context or bpy.context
    prefs = _prefs(context)
    if prefs is None or not prefs.autosave_enable:
        _state["last"] = None
        return None, POLL
    if bpy.app.background and not allow_background:
        return None, POLL
    now = time.monotonic() if now is None else now
    if _state["last"] is None:          # just switched on: the interval starts now
        reset(now)
        return None, POLL
    if now - _state["last"] < prefs.autosave_interval * 60.0:
        return None, POLL
    if not (_state["changed"] and bpy.data.is_dirty):
        _state["last"] = now            # nothing new to keep: wait another interval
        return None, POLL
    if busy(context):
        return None, RETRY
    path = write_copy(context)
    _state["last"] = now
    if path is None:
        return None, POLL
    _state["changed"] = False
    if prefs.autosave_limit:
        prune(os.path.dirname(path), scene_stem(), prefs.autosave_count)
    _report(path)
    return path, POLL


def _report(path):
    print(f"Autosave: {path}")
    try:
        from ..command_line import show_result
        show_result(f"Autosaved {os.path.basename(path)}")
    except Exception:       # the status bar may be gone (closing window); the copy is written anyway
        pass


def _timer():
    try:
        _path, wait = tick()
    except Exception as ex:     # a timer that raises is dropped by Blender: keep autosave alive
        print(f"Autosave: {ex}")
        wait = POLL
    return wait


@persistent
def _on_change(*_args):
    if not _state["saving"]:
        _state["changed"] = True


@persistent
def _on_save_post(*_args):
    if not _state["saving"]:        # the user's own save: that state is kept already
        prefs = _prefs()
        if prefs is not None and prefs.autosave_enable:
            reset()


@persistent
def _on_load_post(*_args):
    prefs = _prefs()
    if prefs is not None and prefs.autosave_enable:
        reset()
    else:
        _state["last"] = None
        _state["changed"] = False


_HANDLERS = (("depsgraph_update_post", _on_change), ("undo_post", _on_change), ("redo_post", _on_change),
             ("save_post", _on_save_post), ("load_post", _on_load_post))


def register():
    for name, fn in _HANDLERS:
        lst = getattr(bpy.app.handlers, name)
        if fn not in lst:
            lst.append(fn)
    _state.update(last=None, changed=False, saving=False)
    if not bpy.app.timers.is_registered(_timer):
        bpy.app.timers.register(_timer, first_interval=POLL, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(_timer):
        bpy.app.timers.unregister(_timer)
    for name, fn in _HANDLERS:
        lst = getattr(bpy.app.handlers, name)
        if fn in lst:
            lst.remove(fn)
    _state.update(last=None, changed=False, saving=False)
