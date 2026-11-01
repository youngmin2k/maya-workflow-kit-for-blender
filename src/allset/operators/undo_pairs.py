# SPDX-License-Identifier: GPL-3.0-or-later
"""Undo steps the kit adds right after one of Blender's, taken back and brought back together with it.

Some kit work can only run after Blender has pushed the undo step of the user's action: Auto Key keys a transform
once it ended, the Maya joint pick finishes a box selection after Blender's box select. The kit's step then comes
right after Blender's, and one Ctrl+Z would take back only the kit's part (the key, the joint pick) — the user
presses again and again. Maya makes such a command one undo chunk.

``push`` pushes the kit's step paired with the step before it: it writes a new id into
``Scene.allset_undo_pair_step`` first, so every step remembers the newest paired step at its time. When an Undo
leaves a paired step and lands on the step before it, the kit takes one more Undo (from a timer: the undo system is
busy in its own handlers); when a Redo lands on that step on its way back to the paired step, one more Redo. A
``check`` callable tells whether the landed state really is the user's action (Auto Key: the scene holds the keyed
values); without one the pair is always taken together.
"""

from contextlib import nullcontext

import bpy
from bpy.app.handlers import persistent

_steps = {}            # paired step id -> (id of the step before it, check or None)
_marks = []            # one per user undo, newest last: the paired step id it went past (0 = none)
_extra = {"want": None, "running": False, "count": 0}
_before = [0]          # step id when the undo / redo started
_user_moves = [0]      # user undo / redo presses (an extra step is dropped when another press came first)


def step_id(scene):
    return int(getattr(scene, "allset_undo_pair_step", 0) or 0)


def push(scene, label, check=None):
    """Push the kit's step ``label``, paired with the step before it."""
    prev = step_id(scene)
    new = max([prev] + list(_steps)) + 1
    try:
        scene.allset_undo_pair_step = new
        bpy.ops.ed.undo_push(message=label)
    except (RuntimeError, AttributeError, TypeError):
        return
    _steps[new] = (prev, check)


def extra_running():
    """The kit is taking the extra undo / redo step (other undo handlers ignore it)."""
    return _extra["running"]


def wanted():
    """The extra step waiting for its timer: 'UNDO', 'REDO' or None."""
    return _extra["want"]


def _ok(step, scene):
    check = step[1]
    if check is None:
        return True
    try:
        return bool(check(scene))
    except (ReferenceError, AttributeError, KeyError, TypeError, ValueError):
        return False


def _want(direction):
    _extra["want"] = direction
    _extra["count"] = _user_moves[0]
    if not bpy.app.timers.is_registered(run_extra):
        bpy.app.timers.register(run_extra, first_interval=0.0)


def run_extra():
    """Take the extra step now (the timer; tests call it directly)."""
    direction, _extra["want"] = _extra["want"], None
    if direction is None or _extra["count"] != _user_moves[0]:
        return None
    wm = bpy.context.window_manager
    # Blender empties the registered operators on undo / redo: one there now ran after it (Adjust Last Operation
    # re-runs its operator through an undo), so the user is somewhere else
    if wm is None or len(wm.operators):
        return None
    window = bpy.context.window or next(iter(wm.windows), None)
    _extra["running"] = True
    try:
        with bpy.context.temp_override(window=window) if window is not None else nullcontext():
            if direction == 'UNDO':
                bpy.ops.ed.undo()
            else:
                bpy.ops.ed.redo()
    except (RuntimeError, ReferenceError):
        pass
    finally:
        _extra["running"] = False
    return None


@persistent
def _on_pre(scene, *_args):
    if _extra["running"]:
        return
    _user_moves[0] += 1
    _before[0] = step_id(scene)


@persistent
def _on_undo_post(scene, *_args):
    if _extra["running"]:
        return
    left, here = _before[0], step_id(scene)
    step = _steps.get(left)
    if left != here and step is not None and step[0] == here and _ok(step, scene):
        _marks.append(left)               # the kit's step was taken back: take back the user's action too
        _want('UNDO')
    else:
        _marks.append(0)


@persistent
def _on_redo_post(scene, *_args):
    if _extra["running"]:
        return
    mark = _marks.pop() if _marks else 0
    step = _steps.get(mark)
    if step is not None and step_id(scene) == step[0] and _ok(step, scene):
        _want('REDO')                     # the user's action is back: the kit's part comes with it


@persistent
def reset(*_args):
    _steps.clear()
    _marks.clear()
    _extra["want"] = None


_HANDLERS = (("undo_pre", _on_pre), ("redo_pre", _on_pre), ("undo_post", _on_undo_post),
             ("redo_post", _on_redo_post), ("load_post", reset))


def register():
    bpy.types.Scene.allset_undo_pair_step = bpy.props.IntProperty(options={'HIDDEN'})
    for name, fn in _HANDLERS:
        lst = getattr(bpy.app.handlers, name)
        if fn not in lst:
            lst.append(fn)


def unregister():
    for name, fn in _HANDLERS:
        lst = getattr(bpy.app.handlers, name)
        while fn in lst:
            lst.remove(fn)
    if bpy.app.timers.is_registered(run_extra):
        bpy.app.timers.unregister(run_extra)
    reset()
    del bpy.types.Scene.allset_undo_pair_step
