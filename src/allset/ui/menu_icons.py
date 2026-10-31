# SPDX-License-Identifier: GPL-3.0-or-later
"""Kit-drawn icons on Maya menu items (issue #23).

Maya 2022 draws the shelf picture of a command beside its menu item (Create > Polygon Primitives, Mesh, Edit Mesh,
Deform ...). ``menu_icon_data.ICONS`` (tools/gen_menu_icons.py)
links such an item to the kit's own drawing of the same command: a shelf button (``shelf_icons``), a Status Line
glyph (``status_icons``), a Tool Box glyph (``kit_icons``) or, for items on no shelf, a menu-only drawing
(``menu_drawings``, #54). Items Maya shows without an icon, and items the kit has no drawing for, get none
(nothing of Maya's artwork).

Blender draws a menu item's icon at 16 px x UI scale; each picture is rasterised at exactly that size (the drawings
hint their edges to the target pixel grid) into a ``bpy.utils.previews`` image. Previews are made from a timer, a
few per tick, never while a menu draws; until a size is complete the menus draw no icons at all (or the previous
size's pictures after a UI scale change), so a menu never mixes rows with and without icons.
"""

import time

from . import menu_icon_data

_pcoll = []
_ready = [0]        # icon size whose previews are all made (0 = none yet)
_building = [0]     # icon size the timer is making
_todo = []
BUDGET = 0.02       # seconds of drawing per timer tick


def picture(pic, n):
    """(n, n, 4) RGBA float32 (top row first, straight alpha) of a ``menu_icon_data`` picture at ``n`` px."""
    kind = pic[0]
    if kind == "shelf":
        from . import shelf_icons
        _kind, shelf, label, index = pic
        return shelf_icons.draw(label, shelf, size=n, index=index)
    if kind == "status":
        from . import status_icons
        return status_icons.image(pic[1], n)
    if kind == "kit":
        from . import kit_icons
        return kit_icons.pixels(pic[1], n)
    if kind == "menu":
        from . import menu_drawings
        return menu_drawings.draw(pic[1], n)
    raise KeyError(pic)


def icon_px(context=None):
    """Pixel size Blender draws a menu item icon at (16 px x the effective UI scale; 0 scale in background = 1)."""
    import bpy
    s = (context or bpy.context).preferences.system.ui_scale or 1.0
    return max(16, int(round(16 * s)))


def _key(pic, n):
    return "/".join(str(p) for p in pic) + f"@{n}"


def _collection():
    if not _pcoll:
        import bpy.utils.previews
        _pcoll.append(bpy.utils.previews.new())
    return _pcoll[0]


def _make(pic, n):
    pc = _collection()
    key = _key(pic, n)
    pv = pc.get(key)
    if pv is None:
        flat = picture(pic, n)[::-1].ravel()       # Blender images are bottom row first
        pv = pc.new(key)
        pv.icon_size = (n, n)
        pv.icon_pixels_float = flat
        pv.image_size = (n, n)
        pv.image_pixels_float = flat
    return pv


def icon_value(path, context=None):
    """icon_value for Maya menu item ``path`` (0 = draw no icon: no kit picture, or not made yet)."""
    pic = menu_icon_data.ICONS.get(path)
    if pic is None:
        return 0
    import bpy
    n = icon_px(context)
    if bpy.app.background:          # tests: no timers run, no drawing to avoid
        return _make(pic, n).icon_id
    if _ready[0] != n:
        _schedule()
    if not _ready[0] or not _pcoll:
        return 0
    pv = _pcoll[0].get(_key(pic, _ready[0]))
    return pv.icon_id if pv is not None else 0


def _schedule():
    import bpy
    if not bpy.app.timers.is_registered(_tick):
        # persistent: a file load (the Maya layout opening right after Maya mode turns on) drops other timers
        bpy.app.timers.register(_tick, first_interval=0.0, persistent=True)


def _redraw():
    import bpy
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def _tick():
    """Make the previews of the current icon size, ``BUDGET`` seconds per tick."""
    try:
        n = icon_px()
        if _building[0] != n:
            _building[0] = n
            _todo[:] = sorted(set(menu_icon_data.ICONS.values()), key=repr)
        t0 = time.perf_counter()
        while _todo and time.perf_counter() - t0 < BUDGET:
            _make(_todo.pop(), n)
        if _todo:
            return 0.01
        _ready[0] = n
        _redraw()
    except Exception:       # a timer that raises is dropped; leave the menus without icons
        _todo.clear()
    return None


def register():
    import bpy
    if not bpy.app.background:
        _schedule()


def unregister():
    import bpy
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    _todo.clear()
    _ready[0] = _building[0] = 0
    if _pcoll:
        import bpy.utils.previews
        bpy.utils.previews.remove(_pcoll.pop())
