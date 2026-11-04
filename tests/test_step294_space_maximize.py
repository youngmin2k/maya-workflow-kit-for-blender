"""Issue #214: a Space tap maximizes / restores the panel under the mouse whatever editor it is.

The four view is the 2 x 2 block of areas inside the rect recorded on the screen, so a panel turned into a Graph
Editor, a render view or an Outliner is still one of the four (no second split). Here the pure parts: finding the
block and the one panel by places. Splitting / joining needs a window: tests/gui/gui_step294_space_maximize.py.
"""

from importlib import import_module
from types import SimpleNamespace

import kit

four_view = import_module(kit.MODULE + ".ui.four_view")
taphold = import_module(kit.MODULE + ".operators.taphold")


def check(ok, msg):
    if not ok:
        raise AssertionError(msg)


def area(x, y, w, h, kind='FCURVES'):
    space = SimpleNamespace(type=kind, show_region_toolbar=True, show_region_header=True, show_region_ui=False,
                            show_object_viewport_mesh=True)
    return SimpleNamespace(x=x, y=y, width=w, height=h, type=kind, spaces=SimpleNamespace(active=space))


class FakeScreen(dict):
    def __init__(self, areas, st=None):
        super().__init__()
        self.areas = areas
        if st is not None:
            four_view._save_state(self, st)


def layout():
    """A Maya-like screen: Tool Box-free columns around a four view with 2 px borders and uneven middle edges."""
    tl, tr = area(40, 302, 400, 300), area(442, 302, 500, 300, 'VIEW_3D')
    bl, br = area(40, 100, 460, 200, 'OUTLINER'), area(502, 100, 440, 200, 'IMAGE_EDITOR')
    outliner = area(0, 100, 38, 502, 'OUTLINER')
    dock = area(944, 100, 300, 502, 'PROPERTIES')
    timeline = area(0, 0, 1244, 98, 'DOPESHEET_EDITOR')
    return (tl, tr, bl, br), [outliner, tl, tr, bl, br, dock, timeline]


def test_grid_by_places_any_editor():
    (tl, tr, bl, br), every = layout()
    got = four_view.grids(every)
    check(len(got) == 1, f"one 2 x 2 block, got {len(got)}")
    check(got[0] == {"top": tl, "persp": tr, "front": bl, "side": br}, got)
    check(four_view.grids([tl, tr, bl]) == [], "three areas are no block")


def test_block_follows_the_recorded_rect():
    (tl, tr, bl, br), every = layout()
    whole = list(four_view.union(four_view.rect(a) for a in (tl, tr, bl, br)))
    screen = FakeScreen(every, {"on": True, "rect": whole})
    check(four_view.block(screen) == {"top": tl, "persp": tr, "front": bl, "side": br}, "block with mixed editors")
    check(four_view.is_four(screen), "a Graph Editor / Outliner / render view panel is still a four view")
    # the dock got wider since: the block is still found
    moved = [whole[0], whole[1], whole[2] + 120, whole[3]]
    check(four_view.block(FakeScreen(every, {"on": True, "rect": moved})), "an edge moved")
    # a 2 x 2 block somewhere else is not the four view
    far = [2000, 2000, 2400, 2400]
    check(not four_view.block(FakeScreen(every, {"on": True, "rect": far})), "a block elsewhere")
    check(not four_view.is_four(FakeScreen(every, {"on": False, "rect": whole})), "off")


def test_wide_borders_at_a_large_ui_scale():
    """Issue #302: at UI scale 2 the borders between the four panels are 9 px; the block is still one four view."""
    tl, tr = area(40, 309, 400, 300), area(449, 309, 500, 300, 'VIEW_3D')
    bl, br = area(40, 100, 460, 200), area(509, 100, 440, 200)
    check(four_view.grids([tl, tr, bl, br], gap=6) == [], "a fixed 6 px tolerance misses 9 px borders")
    import bpy
    view = bpy.context.preferences.view
    old = view.ui_scale
    try:
        view.ui_scale = 2.0
        scale = bpy.context.preferences.system.ui_scale
        check(four_view.border_gap() >= four_view.GAP * scale, f"tolerance follows the UI scale ({scale})")
        if scale >= 1.5:
            check(len(four_view.grids([tl, tr, bl, br])) == 1, "found at UI scale 2")
    finally:
        view.ui_scale = old
    check(four_view.border_gap() >= four_view.GAP, "never below the scale-1 tolerance")


def test_single_panel_by_the_recorded_rect():
    _four, every = layout()
    one = area(40, 100, 902, 502, 'FCURVES')
    screen = FakeScreen([every[0], one, every[5], every[6]], {"on": False, "rect": [40, 100, 942, 602]})
    check(four_view.single(screen) is one, "the Graph Editor left alone is the layout's panel")
    check(four_view.block(screen) == {}, "no four view")
    check(four_view.single(FakeScreen([every[0], one], {"on": False})) is None, "no rect: no panel known")
    check(four_view.single(FakeScreen([every[0], one], {"on": True, "rect": [40, 100, 942, 602]})) is None,
          "while the four view is on there is no single panel")
    small = area(40, 100, 200, 502)
    check(four_view.best([small], [40, 100, 942, 602]) is None, "an area covering less than half is not it")


def test_overlap_and_union():
    check(four_view.overlap((0, 0, 10, 10), (5, 5, 20, 20)) == 25, "overlap")
    check(four_view.overlap((0, 0, 10, 10), (10, 0, 20, 10)) == 0, "touching edges")
    check(four_view.union([(0, 0, 1, 1), (5, -2, 6, 3)]) == (0, -2, 6, 3), "union")


def test_space_is_the_hotbox_key_only():
    check("space" not in taphold.binding_names(), "no tap-hold binding for Space (the hotbox handles the tap)")
