# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya's Undo / Redo text in the Command Line result field.

Maya 2022: after Ctrl+Z / z / Edit > Undo the result field reads ``Undo: <undo chunk name>``
and after Shift+Z / Edit > Redo ``Redo: <name>`` — no ``//`` around it, normal text colour, and ``Undo: `` with
nothing after it when the chunk has no name. The chunk name is the command's name: the runtime command of a menu item
or hotkey (``Group``, ``CreatePolygonCube``), the typed text of a Command Line entry. The kit's result field kept the
last command's ``Result: group1`` after an undo (step-176 dogfood G2).

Blender gives Python no undo step names (``WindowManager.print_undo_steps`` only prints to the C stdout), so the kit
keeps its own list of step names in Blender's order, from what it can see being pushed:

- ``undo_steps.push`` (one step per Maya menu / shelf / marking-menu command, named after the item) and the
  Command Line entry (named by the typed text, like Maya);
- a kit operator that reports a result (``results.result``) at undo depth 0 with UNDO in its options: Blender pushes
  its step named after ``bl_label`` when it finishes;
- operators Blender registered (``WindowManager.operators``: REGISTER + UNDO operators run from keys, tools and
  buttons), read after every depsgraph update and before each kit push. Blender empties that list on undo / redo
  *before* ``undo_pre`` runs, so it can't be read from the undo handlers.

``undo_pre`` names the active step (the one Ctrl+Z takes back) and moves the position back, ``redo_pre`` moves forward
and names that step; ``undo_post`` / ``redo_post`` write the text. A step the kit never saw (an UNDO-only operator
that reports no result, a property edit in a button) is not in the list, so the text names the step before it; steps
from before the add-on started or before a file load read ``Undo: `` like Maya's nameless chunk. Adjust Last
Operation re-runs its operator through an undo: when a registered operator shows up right after the undo, the text
goes back to what it was.
"""

import bpy
from bpy.app.handlers import persistent

MAX_STEPS = 512

_stack = []            # step names, oldest first (Blender's undo order)
_pos = [-1]            # index of Blender's active step in _stack (-1 = before every known step)
_seen = set()          # wm.operators pointers already counted
_claimed = set()       # pointers ``operator_step`` counted before Blender registered them
_pending = [None]      # text to show in the post handler
_before = [None]       # (text, error) of the result field before the undo / redo


def reset():
    _stack.clear()
    _pos[0] = -1
    _seen.clear()
    _claimed.clear()
    _pending[0] = None
    _before[0] = None


def _add(name):
    _new_command()
    del _stack[_pos[0] + 1:]
    _stack.append(name or "")
    if len(_stack) > MAX_STEPS:
        del _stack[:len(_stack) - MAX_STEPS]
    _pos[0] = len(_stack) - 1


def _new_command():
    """A new undoable command ran: Maya's result field no longer shows the last ``Undo: <name>`` / ``Redo: <name>``
    (#104 — ``Undo: Group`` stayed through P / Delete / Ctrl+E). A command with a result writes it right
    after (``results.result``); one without leaves the field empty (Maya clears it for commands that return
    nothing)."""
    from . import _result, show_result
    if _result["text"].startswith(("Undo: ", "Redo: ")) or _result["text"] in ("Undo:", "Redo:"):
        show_result("")


def _registered():
    wm = bpy.context.window_manager
    try:
        return list(wm.operators) if wm is not None else []
    except (AttributeError, ReferenceError):
        return []


def _scan():
    """Count the operators Blender registered since the last look (each REGISTER + UNDO one pushed a step)."""
    ops = _registered()
    cur = {op.as_pointer() for op in ops}
    # Blender frees the oldest registered operators and reuses their addresses: keep only live pointers
    _seen.intersection_update(cur)
    for op in ops:
        p = op.as_pointer()
        if p in _seen:
            continue
        _seen.add(p)
        if p in _claimed:
            _claimed.discard(p)
            continue
        try:
            undo = 'UNDO' in op.bl_options
        except (AttributeError, ReferenceError):
            undo = False
        if undo:
            _add(op.name)


def pushed(name):
    """A kit ``ed.undo_push`` made a step called ``name`` (Maya's chunk name)."""
    _scan()
    _add(name)


def operator_step(op):
    """A kit operator reported a result: Blender pushes its step (named ``bl_label``) when it finishes, if it is the
    outer call of an UNDO operator."""
    from .. import undo_steps
    if undo_steps.depth() > 0:            # inside a Maya command: that command pushes the one step
        return
    try:
        if 'UNDO' not in op.bl_options:
            return
        name, p = op.bl_label, op.as_pointer()
    except (AttributeError, ReferenceError, TypeError):
        return
    if p in _seen or p in _claimed:       # a second result from the same run
        return
    _scan()
    _claimed.add(p)                       # it registers after it finishes: don't count it twice
    _add(name)


def _current():
    from . import _result
    return _result["text"], _result["error"]


def text_for_undo():
    _scan()
    name = _stack[_pos[0]] if 0 <= _pos[0] < len(_stack) else ""
    if _pos[0] >= 0:
        _pos[0] -= 1
    return f"Undo: {name}"


def text_for_redo():
    _scan()
    nxt = _pos[0] + 1
    name = ""
    if nxt < len(_stack):
        name = _stack[nxt]
        _pos[0] = nxt
    return f"Redo: {name}"


@persistent
def _on_undo_pre(*_args):
    _before[0] = _current()
    _pending[0] = text_for_undo()


@persistent
def _on_redo_pre(*_args):
    _before[0] = _current()
    _pending[0] = text_for_redo()


def _check_rerun():
    """Adjust Last Operation (and Blender's own undo-then-repeat) registers its operator again right after the undo:
    that was no user undo, so the result field goes back."""
    if _before[0] is not None and _registered():
        from . import show_result
        text, error = _before[0]
        show_result(text, error)
    _before[0] = None
    return None


@persistent
def _on_post(*_args):
    _seen.clear()                         # Blender emptied wm.operators
    _claimed.clear()
    text, _pending[0] = _pending[0], None
    if text is None:
        return
    from . import show_result
    show_result(text)
    if not bpy.app.background and not bpy.app.timers.is_registered(_check_rerun):
        bpy.app.timers.register(_check_rerun, first_interval=0.0)


@persistent
def _on_depsgraph(*_args):
    _scan()


@persistent
def _on_load(*_args):
    reset()


HANDLERS = (("undo_pre", _on_undo_pre), ("redo_pre", _on_redo_pre), ("undo_post", _on_post), ("redo_post", _on_post),
            ("load_post", _on_load), ("depsgraph_update_post", _on_depsgraph))


def register():
    reset()
    for name, fn in HANDLERS:
        lst = getattr(bpy.app.handlers, name)
        if fn not in lst:
            lst.append(fn)


def unregister():
    for name, fn in HANDLERS:
        lst = getattr(bpy.app.handlers, name)
        while fn in lst:
            lst.remove(fn)
    if bpy.app.timers.is_registered(_check_rerun):
        bpy.app.timers.unregister(_check_rerun)
    reset()
