"""#52: the Maya panel toolbar fits the 3D View tool header — groups that don't fit go into Maya's »
overflow popover. Widths from 1 px mouse sweeps at UI scale 1.0 / 1.25 / 1.5; GUI side:
tests/gui/gui_step129_panel_toolbar.py."""

from importlib import import_module

import bpy

import kit

fit = import_module(kit.MODULE + ".ui.toolbar_fit")
pt = import_module(kit.MODULE + ".ui.panel_toolbar")

# first-button x of each group (region-local px) in a 963 px tool header
STARTS = {
    1.0: (23, 183, 343, 503, 603, 703),
    1.25: (28, 227, 426, 625, 749, 873),
    1.5: (32, 263, 494, 725, 869),
}


def test_layout_rules_match_the_header():
    assert [fit.unit(s) for s in (1.0, 1.25, 1.5)] == [20, 25, 29]
    assert fit.unit(2.0, 2.0) == 40         # Blender's pixel size is 2 from scale 2
    groups = pt.fit_groups()
    for scale, xs in STARTS.items():
        got = tuple(fit.starts(groups, scale)[:len(xs)])
        assert got == xs, (scale, got, xs)


def test_fit_in_the_963_px_header():
    """963 px (the main viewport of the Maya layout in a 1600 px window): the colour management section never fits,
    at 1.5 the X-ray group goes too; a wide view shows everything and no »."""
    groups = pt.fit_groups()
    assert fit.fit(groups, 963, 1.0) == 5
    assert fit.fit(groups, 963, 1.25) == 5
    assert fit.fit(groups, 963, 1.5) == 4
    assert fit.fit(groups, 3000, 1.25) == len(groups)
    assert fit.fit(groups, 40, 1.25) == 0


def test_fit_leaves_room_for_the_more_button():
    groups = pt.fit_groups()
    for scale in (1.0, 1.25, 1.5, 2.0):
        u, s = fit.unit(scale), fit.spacing(scale)
        widths = fit.group_widths(groups, u)
        for width in range(100, 2400, 7):
            n = fit.fit(groups, width, scale)
            if n == len(groups):
                end = fit.starts(groups, scale)[-1] + widths[-1]
                assert end + fit.px(0.4, u) <= width, (scale, width)
                continue
            if n:
                end = fit.starts(groups, scale)[n - 1] + widths[n - 1]
                assert end + s <= fit.more_x(width, scale)[0], (scale, width, n)
            # one more group would not have fitted next to the »
            nxt = fit.starts(groups, scale)[n] + widths[n]
            assert nxt + s > fit.more_x(width, scale)[0] - fit.SLACK, (scale, width, n)


def test_every_button_is_in_the_bar_or_the_popover():
    groups = pt.fit_groups()
    assert len(groups) == len(pt.TOOLBAR) + 1
    assert "more" in pt.GLYPHS
    assert pt.ALLSET_PT_panel_toolbar_more.bl_idname in dir(bpy.types)
    # outside a tool header (no width): everything is shown
    assert pt.shown_groups(bpy.context) == len(groups)
