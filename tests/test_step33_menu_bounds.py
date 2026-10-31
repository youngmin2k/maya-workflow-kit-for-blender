"""Marking menus and the hotbox stay inside the visible region (engine, no bpy UI).
GUI: tests/gui/gui_step33_menu_bounds.py."""

from importlib import import_module

import kit

engine = import_module(kit.MODULE + ".marking.engine")
mm = import_module(kit.MODULE + ".marking.menus")

B = (0.0, 0.0, 1000.0, 600.0)


def measure(text):
    return 7.0 * len(text)


def _abs(s, it):
    cx, cy = s.center
    return (it.rect[0] + cx, it.rect[1] + cy, it.rect[2] + cx, it.rect[3] + cy)


def _inside(r, b=B):
    return b[0] - 1e-6 <= r[0] and r[2] <= b[2] + 1e-6 and b[1] - 1e-6 <= r[1] and r[3] <= b[3] + 1e-6


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _check(menu, origin, bounds=B):
    s = engine.Session(menu, origin, 0.0, measure, None, None, bounds)
    rects = [(it, _abs(s, it)) for it in s.layout.items]
    out = [it.label for it, r in rects if not _inside(r, bounds)]
    assert not out, (menu.name, origin, out)
    radial = [r for it, r in rects if it.kind == "radial"]
    rows = [r for it, r in rects if it.kind == "list"]
    clash = [(a, b) for a in rows for b in radial if _overlap(a, b)]
    assert not clash, (menu.name, origin, clash[:2])
    # the ring stays at the press point (only the list moves)
    assert s.center == origin, (s.center, origin)
    assert s.press == origin
    return s


def test_centre_layout_unchanged():
    free = engine.Session(mm.RMB_MESH, (500.0, 300.0), 0.0, measure)
    fit = engine.Session(mm.RMB_MESH, (500.0, 300.0), 0.0, measure, None, None, (0, -2000, 1000, 2000))
    assert [i.rect for i in free.layout.items] == [i.rect for i in fit.layout.items]


def test_rmb_list_kept_on_screen_near_edges():
    for origin in ((500.0, 120.0), (500.0, 40.0), (500.0, 560.0), (960.0, 300.0), (30.0, 300.0),
                   (970.0, 30.0), (20.0, 580.0)):
        _check(mm.RMB_MESH, origin)


def test_list_goes_above_or_beside_the_ring():
    s = _check(mm.RMB_MESH, (500.0, 120.0))
    rows = [_abs(s, it) for it in s.layout.items if it.kind == "list"]
    north = _abs(s, s.layout.radial["N"])
    beside = all(r[0] >= _abs(s, s.layout.radial["E"])[2] or r[2] <= _abs(s, s.layout.radial["W"])[0]
                 for r in rows)
    assert all(r[1] >= north[3] for r in rows) or beside, "above the ring or beside it"


def test_other_menus_near_edges():
    for name in ("RMB_EMPTY", "SHIFT_OBJECT", "OPT_MOVE",
                 "CTRL_CONVERT", "SHIFT_FACE"):
        for origin in ((500.0, 20.0), (980.0, 580.0), (10.0, 10.0)):
            _check(mm.MENUS[name], origin)


def test_radial_submenu_in_place_stays_inside():
    # Ctrl+RMB "To Vertices" (W) opens a radial submenu at the pointer.
    s = engine.Session(mm.MENUS["CTRL_CONVERT"], (150.0, 40.0), 0.0, measure, None, None, B)
    w = s.layout.radial["W"]
    p = s.params
    cx, cy = s.center          # = the press point
    s.move(cx - p.radius - 5, cy, 0.3)
    assert len(s.stack) == 2 and w.sub is not None
    for it in s.layout.items:
        assert _inside(_abs(s, it)), it.label


def test_hotbox_rows_inside_near_the_top():
    from types import SimpleNamespace  # noqa: F401
    rows = [[(f"m{r}{i}", f"Menu {r}-{i}") for i in range(6)] for r in range(4)]
    centre = (500.0, 560.0)
    hb = engine.HotboxLayout(rows, centre, measure, bounds=B)
    assert all(_inside(r) for r, _k, _l in hb.labels), "rows inside"
    assert not any(_overlap(r, hb.center_rect) for r, _k, _l in hb.labels), "rows clear of the centre box"
    assert max(r[3] for r, _k, _l in hb.labels) < hb.center_rect[1], "moved under the centre box"
    # Room above: rows stay above as before.
    hb = engine.HotboxLayout(rows, (500.0, 200.0), measure, bounds=B)
    assert min(r[1] for r, _k, _l in hb.labels) > hb.center_rect[3]
