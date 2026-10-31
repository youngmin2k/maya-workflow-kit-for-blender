# SPDX-License-Identifier: GPL-3.0-or-later
"""Menu / header draw helpers that never raise for a missing operator (#199).

``UILayout.operator`` returns None when Blender doesn't know the operator (not registered yet, or a Blender
version without it). Setting a property on that None raised AttributeError, and one such line in the tear-off row
emptied every Maya menu. ``op`` returns a stand-in that takes property writes silently instead, so the rest of the
menu still draws (Blender itself draws the unknown operator's button and prints its warning).
"""


class _NoProps:
    """Properties of an operator Blender doesn't know: writes are dropped, reads give None."""
    __slots__ = ()

    def __setattr__(self, name, value):
        pass

    def __getattr__(self, name):
        return None

    def __bool__(self):
        return False


NO_PROPS = _NoProps()


def op(layout, idname, **kwargs):
    """``layout.operator(idname, **kwargs)``; ``NO_PROPS`` instead of None when the operator is missing."""
    props = layout.operator(idname, **kwargs)
    return NO_PROPS if props is None else props


def op_hold(layout, idname, **kwargs):
    """``layout.operator_menu_hold(idname, **kwargs)`` with the same None guard as ``op``."""
    props = layout.operator_menu_hold(idname, **kwargs)
    return NO_PROPS if props is None else props
