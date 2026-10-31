# SPDX-License-Identifier: GPL-3.0-or-later
"""One undo step per Maya command, and no Blender redo panel (#88 #92 #86).

A Python ``bpy.ops`` call without ``undo=True`` raises Blender's undo depth (wm_event_system.cc WM_operator_call_py),
so every operator a menu / shelf / marking-menu item runs pushes no undo step and is not registered. ``command``
pushes one step named after the Maya item once the outermost command finished; ``ed.undo_push`` ignores the depth
(ed_undo.cc ED_undo_push) and does nothing in background unless a script made an undo stack.

Blender opens Adjust Last Operation for the last registered REGISTER + UNDO operator that has a visible property or a
draw method (interface_region_hud.cc last_redo_poll, WM_operator_ui_poll). Maya has no such panel: ``no_redo_panel``
hides a class's properties (keymap items and Repeat Last still set them) for commands that stay registered.
"""

from contextlib import contextmanager

import bpy

_depth = [0]
_pushed = [False]          # the command's operator already pushed its own step (option box "redo" runs)


def push(label):
    try:
        bpy.ops.ed.undo_push(message=label or "Maya Command")
    except RuntimeError:          # no window manager context (a timer in a closing window)
        return
    from .command_line import undo_text       # Maya's "Undo: <command>" after Ctrl+Z names this step
    undo_text.pushed(label or "Maya Command")


def mark_pushed():
    """The operator was called with undo=True: it made its own step (and is registered for Adjust Last Operation)."""
    _pushed[0] = True


@contextmanager
def nested():
    """Run commands inside an operator that pushes its own undo step: no extra step from ``command``."""
    _depth[0] += 1
    try:
        yield
    finally:
        _depth[0] -= 1


def command(label, fn):
    """Run ``fn`` (a Maya command) and make it one undo step when it finished."""
    outer = _depth[0] == 0
    if outer:
        _pushed[0] = False
    _depth[0] += 1
    try:
        res = fn()
    finally:
        _depth[0] -= 1
    if outer and not _pushed[0] and isinstance(res, set) and 'FINISHED' in res:
        push(label)
    return res


def depth():
    return _depth[0]


def _hidden(deferred):
    fn = getattr(deferred, "function", None)
    kw = getattr(deferred, "keywords", None)
    if fn is None or kw is None:
        return deferred
    kw = dict(kw)
    kw["options"] = set(kw.get("options", set())) | {'HIDDEN'}
    return fn(**kw)


def no_redo_panel(cls):
    """Class decorator: every property hidden (inherited ones too), so Blender's redo panel has nothing to show; the
    class keeps REGISTER, so Repeat Last (Maya G) still repeats it with the same values."""
    from . import compat
    merged = {}
    for base in reversed(cls.__mro__):
        if base is object:
            continue
        merged.update(compat.own_annotations(base))
    cls.__annotations__ = {k: _hidden(v) for k, v in merged.items()}
    return cls
