# SPDX-License-Identifier: GPL-3.0-or-later
"""How many panel toolbar groups fit the 3D View tool header (Maya's » overflow, #52; no bpy, tested headless).

Blender's header layout can't report where it put an item, so the widths are Blender's layout rules at
effective UI scale 1.0 / 1.25 / 1.5: an icon button is one widget
unit U = floor(18 s + 0.5) + 2 pixel_size wide, items of the (non-aligned) header row are ``floor(5 s)`` apart, the
row starts ``floor(0.4 U)`` in, a ``ui_units_x = k`` sub-row is ``floor(k U)`` wide.
"""

import math

BAR_UNITS = 0.5      # the group separator ("bar" icon label)
MORE_UNITS = 1.5     # the » popover button (a fixed-width sub-row)
SLACK = 2            # px kept free at the right end


def unit(scale, pixel_size=1.0):
    """Blender's widget unit (UI_UNIT_X) in px."""
    return int(math.floor(18.0 * scale + 0.5)) + 2 * max(1, int(pixel_size))


def spacing(scale):
    """Space between the items of a non-aligned header row, px."""
    return int(5.0 * scale)


def px(units, u):
    return int(units * u)


def group_widths(groups, u):
    """Px width of each group's aligned button row; ``groups`` = lists of unit widths (1 = an icon button)."""
    return [sum(px(w, u) for w in g) for g in groups]


def starts(groups, scale, pixel_size=1.0):
    """Region x of each group's first button (after its bar), as Blender lays the toolbar out."""
    u, s = unit(scale, pixel_size), spacing(scale)
    x = px(0.4, u)
    out = []
    for w in group_widths(groups, u):
        x += px(BAR_UNITS, u) + s
        out.append(x)
        x += w + s
    return out


def fit(groups, width, scale, pixel_size=1.0):
    """Number of leading groups shown in a header ``width`` px wide; the rest go to the » button."""
    u, s = unit(scale, pixel_size), spacing(scale)
    lead = px(0.4, u)
    right = lead + SLACK
    more = s + px(MORE_UNITS, u)
    x = lead
    ends = []
    for w in group_widths(groups, u):
        x += px(BAR_UNITS, u) + s + w
        ends.append(x)
        x += s
    if not ends or ends[-1] + right <= width:
        return len(ends)
    n = 0
    while n < len(ends) and ends[n] + more + right <= width:
        n += 1
    return n


def fit_widths(widths, width, scale, pixel_size=1.0):
    """Number of leading items (px ``widths``, one header row item each) shown in a row ``width`` px wide when the
    rest go behind a right-aligned » button."""
    u, s = unit(scale, pixel_size), spacing(scale)
    lead = px(0.4, u)
    right = lead + SLACK
    more = s + px(MORE_UNITS, u)
    x = lead
    ends = []
    for w in widths:
        x += w
        ends.append(x)
        x += s
    if not ends or ends[-1] + right <= width:
        return len(ends)
    n = 0
    while n < len(ends) and ends[n] + more + right <= width:
        n += 1
    return n


def more_x(width, scale, pixel_size=1.0):
    """Region x range of the » button (right-aligned)."""
    u = unit(scale, pixel_size)
    x1 = width - px(0.4, u)
    return x1 - px(MORE_UNITS, u), x1
