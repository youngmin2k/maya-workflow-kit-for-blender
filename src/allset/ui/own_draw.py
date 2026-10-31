# SPDX-License-Identifier: GPL-3.0-or-later
"""Swap only a Blender UI class's *own* draw function.

Blender keeps a header / panel / menu's draw functions in a list once anything is appended or prepended to it
(``bpy_types._GenericUI._dyn_ui_initialize``, the mechanism ``append`` / ``prepend`` use). Where the kit has to draw
*instead of* Blender's content in its own areas (Maya strip, Maya Outliner header, status bar, ...), it replaces only
Blender's own entry in that list, never the class's ``draw`` attribute: other add-ons' appended / prepended UI keeps
drawing, and ``restore`` puts Blender's function back at the same place even if others extended the class after us.
The kit function falls back to Blender's own draw (``original``) outside the kit's areas.
"""

import bpy

_saved = {}   # (class name, kit function) -> Blender's own draw


def _funcs(cls_name):
    return getattr(bpy.types, cls_name)._dyn_ui_initialize()


def _own_index(cls_name, funcs):
    """Index of the class's own draw (something may have been prepended before it)."""
    for i, f in enumerate(funcs):
        if getattr(f, "__qualname__", "") == f"{cls_name}.draw":
            return i
    return 0


def swap(cls_name, fn):
    """Put ``fn`` where ``cls_name``'s own draw is; returns Blender's own draw."""
    key = (cls_name, fn)
    funcs = _funcs(cls_name)
    if key in _saved and fn in funcs:
        return _saved[key]
    i = _own_index(cls_name, funcs)
    _saved[key] = funcs[i]
    funcs[i] = fn
    return _saved[key]


def original(cls_name, fn):
    return _saved[(cls_name, fn)]


def restore(cls_name, fn):
    """Blender's own draw back in place of ``fn`` (wherever ``fn`` is now)."""
    own = _saved.pop((cls_name, fn), None)
    if own is None:
        return
    funcs = _funcs(cls_name)
    if fn in funcs:
        funcs[funcs.index(fn)] = own

