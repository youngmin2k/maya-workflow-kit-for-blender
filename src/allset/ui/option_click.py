# SPDX-License-Identifier: GPL-3.0-or-later
"""A click on the option box ❒ of a Maya menu item opens its option window (#82).

Blender runs a menu item's operator with EXEC and tells Python nothing about the popup menu (no region, no rect:
``context.region`` in ``Menu.draw`` is the region the menu was called from, ``Screen`` has no popup
regions, a screenshot taken in ``execute`` already shows the menu closed). Two things are known, though:
- where the click was: a nested ``INVOKE_DEFAULT`` call inside ``execute`` gets the window's latest event, the
  LEFTMOUSE release on the row (``ALLSET_OT_click_point``);
- where a Maya pulldown sits: the kit lays out the top bar itself (every menu button has ``ui_units_x``,
  ``status_line.menu_bar_widths``), Blender opens a pulldown with its left edge on the button's left edge and a
  submenu against its parent's right edge, every row's text starts ``TEXT_UNITS`` from the menu edge and the kit's
  label + hotkey + ❒ texts are right-aligned (``menu_sets.item_texts``), so the ❒ ends at menu left + text start +
  the aligned text width (checked on screenshots at UI scale 1.0 / 1.25, ``tests/test_step183_option_click.py`` +
  ``tests/gui/gui_step183_option_click.py``).
So the ❒ zone of a row is known for menus opened from the Maya menu bar (and their submenus); anywhere else
(hotbox, marking menus, the » overflow, editor menu bars, a torn-off menu) the item keeps the press-and-hold /
Shift / Ctrl+click.
"""

import bpy

# In widget units (toolbar_fit.unit)
from .. import compat, i18n
LEAD_UNITS = compat.MENU_BAR_LEAD_UNITS   # top bar region left -> first Maya menu button (4.5 1.48, 5.x 1.25)
TEXT_UNITS = 1.6         # menu edge -> item text (menu padding + icon column)
PAD_SUB_UNITS = 1.6      # widest text -> menu right edge when the menu has submenu rows (arrow column)
PAD_UNITS = 1.28         # ... without submenu rows
ZONE_LEFT_UNITS = 0.5    # the click zone starts this far left of the ❒ glyph (Maya's box is a square cell)

_OPEN = {}    # window pointer -> {top menu label: top bar region x, or None when drawn somewhere else}
_CLICK = {}


def _unit(context):
    from .toolbar_fit import unit
    system = context.preferences.system
    return unit(system.ui_scale or 1.0, system.pixel_size)


def note_draw(context, top_label):
    """Called by every top Maya menu's draw: was it opened from the Maya menu bar of this window?"""
    window = getattr(context, "window", None)
    if window is None:
        return
    from . import status_line
    area, region = getattr(context, "area", None), getattr(context, "region", None)
    top = status_line._top_bars.get(window.as_pointer())
    ok = (area is not None and top is not None and region is not None and region.type == 'HEADER'
          and area.as_pointer() == top.as_pointer())
    _OPEN.setdefault(window.as_pointer(), {})[top_label] = region.x if ok else None


def _items_of(path):
    """(items, prefix, top label) of the Maya menu at ``path`` ("Create" or "Create/Polygon Primitives")."""
    from . import menu_data, menu_sets
    top = path.split("/")[0]
    entry = next((m for m in menu_data.MENUS.values() if m[0] == top), None)
    if entry is None:
        return None
    items = entry[3]
    if path == top:
        return items, top, top
    try:
        node = menu_sets._find(items, top, path)
    except KeyError:
        return None
    return menu_sets.sub_items(path, node), path, None


def rows(path):
    """[(drawn text, is a submenu row)] of the Maya menu at ``path`` — the texts ``menu_sets._menu_class`` draws."""
    from . import maya_dock, menu_map, menu_sets
    got = _items_of(path)
    if got is None or not got[0]:
        return None
    items, prefix, top_label = got
    kids = menu_sets.menu_rows(items, prefix)       # labels in the interface language
    plain = [(p, it[0], p in menu_sets.OPTION_BOXES) for p, it in kids
             if p is not None and not (menu_sets.sub_items(p, it) and p not in menu_map.MAP)]
    texts = menu_sets.item_texts(plain)
    out = [(maya_dock.TEAR_LINE, False)]
    for p, it in kids:
        if p is None:
            if len(it) > 1 and it[1]:
                out.append((i18n.iface(it[1]), False))   # drawn by Blender, translated
        elif menu_sets.sub_items(p, it) and p not in menu_map.MAP:
            out.append((it[0] + (menu_sets.BOX_MARK if p in menu_sets.OPTION_BOXES else ""), True))
        else:
            out.append((texts[p], False))
    blender = menu_map.BLENDER_MENU.get(top_label) if top_label else None
    if blender:
        out.append((i18n.iface(blender[1]), True))
    return out, texts


def width(path, u, size=None):
    """Menu width in px (``u`` = widget unit): text start + widest text + right padding."""
    from . import menu_sets
    got = rows(path)
    if got is None:
        return None
    size = size or menu_sets.font_size()
    out, _texts = got
    widest = max(menu_sets.text_width(t, size) for t, _sub in out)
    pad = PAD_SUB_UNITS if any(sub for _t, sub in out) else PAD_UNITS
    return int(TEXT_UNITS * u + widest + pad * u)


def top_left(context, label):
    """Window x of the Maya menu bar button ``label`` (None: not drawn there by the kit's layout this time)."""
    from . import menu_sets, status_line
    window = context.window
    region_x = _OPEN.get(window.as_pointer(), {}).get(label)
    if region_x is None or status_line.status_line_shown(context) is False:
        return None          # opened elsewhere, or the bar also holds the menu set field (not modelled)
    names, n = status_line.shown_menus(window)
    labels = [getattr(getattr(bpy.types, menu_sets.menu_idname(nm), None), "bl_label", nm) for nm in names]
    if label not in labels[:n] or n < len(names):
        return None          # in the » overflow menu, or the bar is cut (the » button changes the layout)
    widths, _fixed, _more = status_line.menu_bar_widths(context, list(names), False)
    i = labels.index(label)
    return region_x + int(LEAD_UNITS * _unit(context)) + sum(widths[:i])


def box_zone(context, path):
    """(zone x0, zone x1, menu left, menu right) in window px for the ❒ of menu item ``path``, or None."""
    from . import menu_sets
    parts = path.split("/")
    if len(parts) < 2 or context.window is None:
        return None
    u = _unit(context)
    size = menu_sets.font_size(context)
    left = top_left(context, parts[0])
    if left is None:
        return None
    win_w = context.window.width
    w = width(parts[0], u, size)
    if w is None:
        return None
    left = min(left, win_w - w)
    for k in range(2, len(parts)):          # submenus: against the parent's right edge, else its left
        sub = "/".join(parts[:k])
        sw = width(sub, u, size)
        if sw is None:
            return None
        left = left + w if left + w + sw <= win_w else left - sw
        w = sw
    got = rows("/".join(parts[:-1]))
    if got is None or path not in got[1]:
        return None
    text = got[1][path]
    if not text.endswith(menu_sets.BOX_MARK.strip()):
        return None
    end = left + TEXT_UNITS * u + menu_sets.text_width(text, size)
    glyph = menu_sets.text_width(menu_sets.BOX_MARK.strip(), size)
    return end - glyph - ZONE_LEFT_UNITS * u, left + w, left, left + w


class ALLSET_OT_click_point(bpy.types.Operator):
    """Where the last click went (called with INVOKE from inside an EXEC operator: the window's latest event)"""
    bl_idname = "allset.click_point"
    bl_label = "Click Point"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        _CLICK["at"] = (event.mouse_x, event.mouse_y, event.type)
        return {'FINISHED'}

    def execute(self, context):
        return {'CANCELLED'}


def on_box(context, path):
    """True when the menu item ``path`` was clicked on its ❒ (a menu of the Maya menu bar, left mouse button)."""
    if bpy.app.background or getattr(context, "window", None) is None:
        return False
    zone = box_zone(context, path)
    if zone is None:
        return False
    _CLICK.clear()
    try:
        bpy.ops.allset.click_point('INVOKE_DEFAULT')
    except RuntimeError:
        return False
    at = _CLICK.get("at")
    if at is None or at[2] != 'LEFTMOUSE':
        return False
    x0, x1, left, right = zone
    if not left <= at[0] <= right:
        return False         # the click isn't where the model puts the menu: trust nothing, run the command
    return x0 <= at[0] <= x1


classes = (ALLSET_OT_click_point,)
