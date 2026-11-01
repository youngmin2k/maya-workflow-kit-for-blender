# SPDX-License-Identifier: GPL-3.0-or-later
"""Kit windows reopen where they were (#203).

Maya keeps every window's last size and place (top / left edge, width, height) under the window's name and opens
the window there again. The kit's floating windows (Hypershade, Render
Settings, Script Editor, the editors of Windows > ...) are ``screen.area_dupli`` copies of an area, and Blender
gives a new window exactly the size and place of the area it copies; Python can't move or resize a window. So:

- while a kit window is open, a timer keeps its last rect (``Window.x / y / width / height``, screen px) per kind,
  saved in ``window_places.json`` in the extension's user folder (not in the .blend, kept across files and
  sessions);
- opening that kind again carves an area of the remembered size and place out of the largest area of the window
  the command runs in (one split per tick: Blender lays areas out only between ticks), runs the opening command
  again, which copies that piece into the new window, and closes the pieces, so the main layout is as it was. A remembered rect is first fitted inside that area: the kit can only place a window over
  the window it opens from, which also brings a window that was on another monitor or off the
  screen back into view.

``open_window(context, area, kind)`` in ``operators/menu_extras.py`` is the one place every kit window opens.
"""

import json
import os

import bpy

from .. import live_refs

FILE = "window_places.json"
MIN_MARGIN = 40          # px: a margin smaller than this is not split off (the window grows by it instead)
MIN_SIZE = 120           # px: smallest window the kit reopens
TICK = 0.5               # s between rect samples of the open kit windows
# px a carved piece may differ from its target: each split's border takes ~2 px, and a place with margins on all
# four sides is cut twice per axis (Blender 5.2: 340 x 120 carved to 338 x 116, 3 px higher).
# More than that is a failed carve, and the window copies the whole area instead.
CARVE_SLACK = 6

_places = {}             # kind -> [x, y, width, height] (screen px, bottom-left origin)
_tracked = {}            # window pointer -> kind
_state = {"loaded": False, "dirty": False}


# --- storage ---------------------------------------------------------------------------------------------------

def _package():
    return __package__.rpartition(".")[0]


def path():
    try:
        folder = bpy.utils.extension_path_user(_package(), create=True)
    except (ValueError, AttributeError):      # not installed as an extension (legacy add-on)
        return None
    return os.path.join(folder, FILE)


def load():
    _state["loaded"] = True
    p = path()
    if not p or not os.path.isfile(p):
        return
    try:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return
    if isinstance(data, dict):
        for kind, rect in data.items():
            if isinstance(rect, list) and len(rect) == 4 and all(isinstance(v, int) for v in rect):
                _places[kind] = rect


def save():
    p = path()
    if not p:
        return
    try:
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(_places, fh, indent=1, sort_keys=True)
        _state["dirty"] = False
    except OSError as ex:
        print("Maya Workflow Kit: could not save window places:", ex)


def place(kind):
    """The remembered rect of ``kind`` or None."""
    if not _state["loaded"]:
        load()
    return _places.get(kind)


def remember(kind, rect):
    if not _state["loaded"]:
        load()                      # what is on disk first, then this rect over it
    rect = [int(v) for v in rect]
    if _places.get(kind) != rect:
        _places[kind] = rect
        _state["dirty"] = True


# --- maths (no bpy) ------------------------------------------------------------------------------------------------

def fit(rect, bounds, min_size=MIN_SIZE):
    """``rect`` (x, y, w, h) moved / shrunk to lie inside ``bounds`` (x, y, w, h); None when bounds are too small."""
    bx, by, bw, bh = bounds
    if bw < min_size or bh < min_size:
        return None
    x, y, w, h = rect
    w = max(min_size, min(w, bw))
    h = max(min_size, min(h, bh))
    x = max(bx, min(x, bx + bw - w))
    y = max(by, min(y, by + bh - h))
    return (x, y, w, h)


def snap_margins(rect, bounds, margin=MIN_MARGIN):
    """Margins thinner than ``margin`` are given to the window (an area can't be that thin)."""
    x, y, w, h = rect
    bx, by, bw, bh = bounds
    if x - bx < margin:
        w, x = w + (x - bx), bx
    if (bx + bw) - (x + w) < margin:
        w = bx + bw - x
    if y - by < margin:
        h, y = h + (y - by), by
    if (by + bh) - (y + h) < margin:
        h = by + bh - y
    return (x, y, w, h)


def cuts(rect, bounds):
    """The splits that carve ``rect`` out of ``bounds``: [(direction, coordinate)] in window px — left, right
    (VERTICAL at x), bottom, top (HORIZONTAL at y), only where a margin is left."""
    x, y, w, h = rect
    bx, by, bw, bh = bounds
    out = []
    if x > bx:
        out.append(('VERTICAL', x))
    if x + w < bx + bw:
        out.append(('VERTICAL', x + w))
    if y > by:
        out.append(('HORIZONTAL', y))
    if y + h < by + bh:
        out.append(('HORIZONTAL', y + h))
    return out


def carved(got, rect, slack=CARVE_SLACK):
    """True when the piece ``got`` (x, y, w, h) is the carved ``rect`` (within the split borders)."""
    return all(abs(g - t) <= slack for g, t in zip(got, rect))


def target_in_window(kind, window, area):
    """The remembered rect of ``kind`` in ``window``-relative px, fitted inside ``area``; None = no place."""
    rect = place(kind)
    if rect is None:
        return None
    rel = (rect[0] - window.x, rect[1] - window.y, rect[2], rect[3])
    bounds = (area.x, area.y, area.width, area.height)
    fitted = fit(rel, bounds)
    return snap_margins(fitted, bounds) if fitted is not None else None


# --- carving and opening -------------------------------------------------------------------------------------------

def _rect(a):
    return (a.x, a.y, a.width, a.height)


def _contains(a, px, py):
    return a.x <= px < a.x + a.width and a.y <= py < a.y + a.height


def _area(window, ptr):
    return next((a for a in window.screen.areas if a.as_pointer() == ptr), None)


def dupli(context, window, area):
    before = set(context.window_manager.windows[:])
    with context.temp_override(window=window, area=area):
        bpy.ops.screen.area_dupli('INVOKE_DEFAULT')
    new = [w for w in context.window_manager.windows if w not in before]
    return new[0] if new else None


def calling_operator():
    """The kit operator whose execute / invoke is opening the window (to run it again once the place is
    carved), or None."""
    import sys
    frame = sys._getframe(2)
    while frame is not None:
        op = frame.f_locals.get("self")
        if isinstance(op, bpy.types.Operator) and op.bl_idname.startswith("ALLSET_OT_"):
            return op
        frame = frame.f_back
    return None


class _Carve:
    """Splits ``area`` one cut per tick (Blender lays the areas out only between ticks) until one piece covers the
    target rect, then runs the opening operator again, which copies that piece (``open_at``), and closes the pieces
    afterwards."""

    def __init__(self, kind, window, area, rect, op_call):
        self.kind, self.rect, self.call = kind, rect, op_call
        self.win, self.source = window.as_pointer(), area.as_pointer()
        self.piece, self.made, self.last = area.as_pointer(), [], None
        self.todo = cuts(rect, _rect(area))
        self.wait = 0

    def _window(self):
        return live_refs.window(self.win)

    def tick(self):
        window = self._window()
        if window is None:
            _pending.pop(self.kind, None)
            return None
        piece = _area(window, self.piece)
        if piece is None:
            return self.finish(window, ok=False)
        if self.last is not None:
            new = _area(window, self.last)
            if new is not None and new.width == 0 and self.wait < 20:     # not laid out yet
                self.wait += 1
                return TICK_FAST
            cx, cy = self.rect[0] + self.rect[2] / 2, self.rect[1] + self.rect[3] / 2
            piece = next((a for a in (piece, new) if a is not None and _contains(a, cx, cy)), piece)
            self.piece, self.last = piece.as_pointer(), None
        while self.todo:
            direction, at = self.todo.pop(0)
            span = (piece.x, piece.width) if direction == 'VERTICAL' else (piece.y, piece.height)
            factor = (at - span[0]) / span[1] if span[1] else 0
            if not 0.02 < factor < 0.98:
                continue
            before = {a.as_pointer() for a in window.screen.areas}
            with bpy.context.temp_override(window=window, screen=window.screen, area=piece):
                bpy.ops.screen.area_split(direction=direction, factor=factor)
            new = [a for a in window.screen.areas if a.as_pointer() not in before]
            if new:
                self.last = new[0].as_pointer()
                self.made.append(self.last)
                self.wait = 0
            return TICK_FAST
        got = _rect(piece)
        ok = carved(got, self.rect)
        return self.finish(window, ok)

    def finish(self, window, ok):
        _pending.pop(self.kind, None)
        _ready[self.kind] = self.piece if ok else None
        source = _area(window, self.source) or max(window.screen.areas, key=lambda a: a.width * a.height)
        idname, kwargs = self.call
        module, _sep, name = idname.partition("_OT_")
        op = getattr(getattr(bpy.ops, module.lower()), name)
        try:
            with bpy.context.temp_override(window=window, screen=window.screen, area=source):
                try:
                    op('EXEC_DEFAULT', **kwargs)
                except RuntimeError:
                    op('INVOKE_DEFAULT', **kwargs)
        except (RuntimeError, TypeError) as ex:
            print("Maya Workflow Kit: reopening a window failed:", ex)
        finally:
            _ready.pop(self.kind, None)
        made = list(self.made)
        ptr = self.win
        bpy.app.timers.register(lambda: _close_later(ptr, made), first_interval=TICK_FAST)
        return None


def _close_later(win_ptr, made):
    window = live_refs.window(win_ptr)
    if window is None:
        return None
    for ptr in reversed(made):
        a = _area(window, ptr)
        if a is None:
            continue
        with bpy.context.temp_override(window=window, screen=window.screen, area=a):
            try:
                bpy.ops.screen.area_close()
            except RuntimeError as ex:
                print("Maya Workflow Kit: area close failed:", ex)
    return None


TICK_FAST = 0.02
_pending = {}            # kind -> _Carve running
_ready = {}              # kind -> pointer of the carved piece while the operator runs again (None = plain)
_deferred = [False]


def deferred():
    """True right after ``open_at`` returned None because the window opens on a later tick."""
    return _deferred[0]


def reopening(kind):
    """True while the opening operator runs again to copy the carved piece of ``kind`` (its first run did the rest
    of its work already)."""
    return kind in _ready


def open_at(context, area, kind):
    """A new window copying ``area``: at the remembered place of ``kind`` when there is one. When that place
    first has to be carved out of ``area``, None is returned (``deferred()`` True) and the calling kit operator
    runs again once the piece is ready."""
    _deferred[0] = False
    window = context.window
    if kind in _ready:                         # the second run: copy the carved piece
        ptr = _ready[kind]
        piece = _area(window, ptr) if ptr else None
        new = dupli(context, window, piece or area)
    else:
        rect = target_in_window(kind, window, area) if kind and not bpy.app.background else None
        op = calling_operator() if rect is not None and rect != _rect(area) else None
        if op is not None and kind not in _pending:
            carve = _pending[kind] = _Carve(kind, window, area, rect, (op.bl_idname, op.as_keywords()))
            bpy.app.timers.register(carve.tick, first_interval=0.0)
            _deferred[0] = True
            return None
        if kind in _pending:
            _deferred[0] = True
            return None
        new = dupli(context, window, area)
    if new is not None and kind:
        track(new, kind)
    return new


# --- tracking open kit windows ---------------------------------------------------------------------------------------

def track(window, kind):
    _tracked[window.as_pointer()] = kind
    remember(kind, (window.x, window.y, window.width, window.height))
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=TICK, persistent=True)


def _tick():
    for ptr, kind in list(_tracked.items()):
        w = live_refs.window(ptr)
        if w is None:
            del _tracked[ptr]          # closed: its last rect stays remembered
            continue
        remember(kind, (w.x, w.y, w.width, w.height))
    if _state["dirty"]:
        save()
    return TICK if _tracked else None


def register():
    _state["loaded"] = False
    _places.clear()


def unregister():
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    if _state["dirty"]:
        save()
    _tracked.clear()
