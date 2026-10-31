"""#56: marking menu lists / boxes are never cut by an area border. Blender draws the borders between
editors after every region, so the engine keeps rows and radial boxes off the border bands (``edges``): a row goes
below a horizontal band (one column, like Maya), the next column starts only at the window bottom, lists and boxes
move sideways off vertical bands (engine, no bpy UI). GUI: tests/gui/gui_step136_edges.py."""

from importlib import import_module
from types import SimpleNamespace

import kit

engine = import_module(kit.MODULE + ".marking.engine")
mm = import_module(kit.MODULE + ".marking.menus")
draw = import_module(kit.MODULE + ".marking.draw")

# The Maya Workflow Kit layout at UI scale 1.25 in a 1600 x 900 window: window pixels.
AREAS = [(356, 93, 773, 679), (0, 775, 1600, 56), (0, 834, 1600, 33), (0, 29, 1600, 61), (0, 93, 90, 679),
         (93, 93, 260, 679), (1132, 93, 468, 679)]
VIEW = SimpleNamespace(x=356, y=93, width=773, height=615)        # main 3D View WINDOW region
WINDOW = SimpleNamespace(screen=SimpleNamespace(areas=[SimpleNamespace(x=x, y=y, width=w, height=h)
                                                       for x, y, w, h in AREAS]))
K = 1.25
P = engine.Params().scaled(K)


def measure(text):
    return 7.0 * K * len(text)


BOUNDS = draw.window_bounds(WINDOW, VIEW)
EDGES = draw.window_edges(WINDOW, VIEW)
MENUS = tuple(mm.MENUS)
CROSSED = []   # layouts with rows on a vertical border (reported by the test)   # RMB (RMB_MESH), Shift+RMB, Ctrl+RMB, tool options, hotbox zones, UV, ...


def _abs(center, it):
    cx, cy = center
    return (it.rect[0] + cx, it.rect[1] + cy, it.rect[2] + cx, it.rect[3] + cy)


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _inside(r, b=BOUNDS):
    return b[0] - 1e-6 <= r[0] and r[2] <= b[2] + 1e-6 and b[1] - 1e-6 <= r[1] and r[3] <= b[3] + 1e-6


def _session(menu, origin):
    return engine.Session(menu, origin, 0.0, measure, P, None, BOUNDS, EDGES)


def _origins():
    # all over the main view, and close to each of its edges
    xs = (12, 60, 200, VIEW.width / 2, VIEW.width - 200, VIEW.width - 60, VIEW.width - 12)
    ys = (8, 30, 80, 150, 300, VIEW.height - 150, VIEW.height - 60, VIEW.height - 10)
    return [(float(x), float(y)) for x in xs for y in ys]


def _check_layout(lay, center, what):
    rects = [(it, _abs(center, it)) for it in lay.items]
    out = [it.label for it, r in rects if not _inside(r)]
    assert not out, (what, "outside the window", out)
    rows = [(it, r) for it, r in rects if it.kind == "list"]
    horizontal = [e for e in EDGES if e[2] - e[0] >= e[3] - e[1]]
    cut = [(it.label, r, e) for it, r in rects for e in horizontal if _overlap(r, e)]
    assert not cut, (what, "on a horizontal area border", cut[:3])
    cut = [(it.label, r, e) for it, r in rects if it.kind == "radial" for e in EDGES if _overlap(r, e)]
    assert not cut, (what, "radial box on an area border", cut[:3])
    # A vertical border line may cross list rows only when the list needs more columns than the free spans between
    # the window's vertical borders hold side by side (RMB at mid height: 4 columns); then rows of one column at most.
    columns = {}
    for it, r in rows:
        columns.setdefault(round(r[0]), []).append(r)
    crossed = {round(r[0]) for it, r in rows for e in EDGES if _overlap(r, e)}
    if crossed:
        assert len(columns) >= 3 and len(crossed) == 1, (what, "rows on a vertical border", sorted(crossed))
        CROSSED.append(what)
    radial = [r for it, r in rects if it.kind == "radial"]
    clash = [(it.label, r) for it, r in rows for b in radial if _overlap(r, b)]
    assert not clash, (what, "list over the ring", clash[:2])
    # Maya's order: down each column, columns left to right
    order = [it.key for it, _r in sorted(rows, key=lambda p: (round(p[1][0]), -p[1][3]))]
    assert order == sorted(order), (what, "row order", order)


def test_window_edges():
    horizontal = [e for e in EDGES if e[2] - e[0] >= e[3] - e[1]]
    # View / Time Slider border: area gap 90..93 (window), 2 px rim each side + 1, across the whole window
    tl = [e for e in horizontal if e[1] < 0 < e[3]]
    assert tl and tl[0][0] <= BOUNDS[0] and tl[0][2] >= BOUNDS[2], tl
    assert tl[0][1] == 90 - 3 - VIEW.y and tl[0][3] == 93 + 3 - VIEW.y, tl
    vertical = [e for e in EDGES if e[2] - e[0] < e[3] - e[1]]
    # Outliner | view and view | dock borders
    assert any(e[0] < 0 < e[2] for e in vertical) and any(e[0] < VIEW.width < e[2] for e in vertical), vertical


def test_rmb_and_shift_menus_never_on_a_border():
    for name in MENUS:
        menu = mm.with_object_name(mm.MENUS[name], "pCube1")
        for origin in _origins():
            s = _session(menu, origin)
            # the ring stays at the press point (only the list moves)
            assert s.center == origin, (s.center, origin)
            _check_layout(s.layout, s.center, (name, origin))
    total = len(MENUS) * len(_origins())
    print("step136 layouts", total, "with rows on a vertical border", len(CROSSED), sorted(set(CROSSED))[:20])
    assert len(CROSSED) <= total // 50, CROSSED


def test_list_cascades_never_on_a_border():
    menu = mm.with_object_name(mm.RMB_MESH, "pCube1")
    for origin in _origins():
        s = _session(menu, origin)
        for row in [it for it in s.layout.items if it.kind == "list" and it.sub is not None and it.enabled]:
            s._pop_to(0)
            x0, y0, x1, y1 = _abs(s.stack[0][1], row)
            s.move((x0 + x1) / 2, (y0 + y1) / 2, 0.5)
            if len(s.stack) == 2:
                lay, center = s.stack[1]
                _check_layout(lay, center, ("cascade", row.label, origin))


def test_row_below_the_band_keeps_one_column():
    # Low in the view: the list runs over the View / Time Slider border into the Time Slider. The row that would
    # straddle the border goes below it; the column only wraps at the window bottom.
    menu = mm.with_object_name(mm.RMB_MESH, "pCube1")
    s = _session(menu, (VIEW.width / 2, 220.0))
    rows = sorted((it for it in s.layout.items if it.kind == "list"), key=lambda it: it.key)
    band = next(e for e in EDGES if e[1] < 0 < e[3])
    first_col = [it for it in rows if abs(it.rect[0] - rows[0].rect[0]) < 1e-6]
    over = [it for it in first_col if s.center[1] + it.rect[3] <= band[1] + 1e-6]
    assert over, "the first column continues under the border"
    above = [it for it in first_col if s.center[1] + it.rect[1] >= band[3] - 1e-6]
    assert above and above[-1].key < over[0].key


def test_without_edges_unchanged():
    menu = mm.RMB_MESH
    for origin in ((400.0, 300.0), (400.0, 60.0), (20.0, 500.0)):
        a = engine.Session(menu, origin, 0.0, measure, P, None, BOUNDS)
        b = engine.Session(menu, origin, 0.0, measure, P, None, BOUNDS, ())
        assert [i.rect for i in a.layout.items] == [i.rect for i in b.layout.items]
