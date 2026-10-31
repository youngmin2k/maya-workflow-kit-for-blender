# SPDX-License-Identifier: GPL-3.0-or-later
"""UI references that outlive a timer tick (#36).

A ``bpy.types.Window`` (and the Screen / Area / Region / Space reached from it) kept across timer ticks is NOT
invalidated when its window closes: reading it afterwards dereferences freed memory and Blender crashes
(EXCEPTION_ACCESS_VIOLATION, no ReferenceError). Deferred callbacks therefore keep ``as_pointer()`` values and look
the live object up again on every tick with the helpers below; None = gone, stop.

Comparing pointers never dereferences the old object. A freed pointer can be reused by a new area / window
, which at worst points a retry at a newer object of the same kind.
"""

import bpy


def pointer(ref):
    """``ref.as_pointer()``, 0 for None."""
    return ref.as_pointer() if ref is not None else 0


def windows():
    wm = getattr(bpy.context, "window_manager", None)
    return list(wm.windows) if wm is not None else []


def window(ptr):
    """The open window whose pointer is ``ptr``, else None."""
    if not ptr:
        return None
    for w in windows():
        if w.as_pointer() == ptr:
            return w
    return None


def find_area(ptr, win=None):
    """(window, area) of the area whose pointer is ``ptr`` in ``win`` (a Window, a window pointer, or None = any
    open window); (None, None) when it is gone."""
    if not ptr:
        return None, None
    if isinstance(win, int):
        win = window(win)
        if win is None:
            return None, None
    for w in ([win] if win is not None else windows()):
        screen = w.screen
        if screen is None:
            continue
        for a in screen.areas:
            if a.as_pointer() == ptr:
                return w, a
    return None, None


def area(ptr, win=None):
    """The area whose pointer is ``ptr`` (see ``find_area``), else None."""
    return find_area(ptr, win)[1]


def region(area_, ptr):
    """The region of the live ``area_`` whose pointer is ``ptr``, else None."""
    if area_ is None or not ptr:
        return None
    return next((r for r in area_.regions if r.as_pointer() == ptr), None)


def find_space(ptr, win=None):
    """(window, area, space) of the space whose pointer is ``ptr`` (any space of an area, active or not) in ``win``
    (Window, window pointer or None = any open window); (None, None, None) when it is gone."""
    if not ptr:
        return None, None, None
    if isinstance(win, int):
        win = window(win)
        if win is None:
            return None, None, None
    for w in ([win] if win is not None else windows()):
        screen = w.screen
        if screen is None:
            continue
        for a in screen.areas:
            for s in a.spaces:
                if s.as_pointer() == ptr:
                    return w, a, s
    return None, None, None
