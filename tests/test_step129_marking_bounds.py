"""#5: dragging down through a marking menu's list keeps the menu open. A list row with a submenu
(Paint, Assign Favorite Material) opens it beside the row like a Qt cascade, the list stays up and hit-tested,
and moving on to another row closes the cascade again (engine, no bpy UI).
GUI: tests/gui/gui_step129_marking_bounds.py."""

from importlib import import_module

import kit

engine = import_module(kit.MODULE + ".marking.engine")
mm = import_module(kit.MODULE + ".marking.menus")

B = (0.0, 0.0, 1400.0, 1200.0)
O = (700.0, 1000.0)


def measure(text):
    return 7.0 * len(text)


def _session(origin=O):
    return engine.Session(mm.RMB_MESH, origin, 0.0, measure, None, None, B)


def _row(s, label, level=0):
    lay, (cx, cy) = s.stack[level]
    it = next(i for i in lay.items if i.label == label)
    return it, (cx + (it.rect[0] + it.rect[2]) / 2, cy + (it.rect[1] + it.rect[3]) / 2)


def _drag_down(s, x, y0, y1, step=4.0):
    y = y0
    while y >= y1:
        s.move(x, y, 0.5)
        y -= step


def test_drag_down_the_list_past_a_submenu_row():
    s = _session()
    paint, (px, py) = _row(s, "Paint")
    mat, (mx, my) = _row(s, "Material Attributes...")
    _drag_down(s, px, py + 30, py)
    assert len(s.stack) == 2 and s.layout.sub is paint.sub, "hovering Paint opens its cascade"
    _drag_down(s, px, py, my)
    assert len(s.stack) == 1, "moving on down the list closes the cascade"
    assert s.hover[0] is mat, ("the list row under the cursor is hovered", s.hover)
    res = s.release(mx, my, 0.6)
    assert res is not None and res[0] == "RUN" and res[1] is mat, res


def test_cascade_keeps_parent_rows_and_its_own_rows():
    s = _session()
    paint, (px, py) = _row(s, "Paint")
    s.move(px, py, 0.5)
    assert len(s.stack) == 2
    # back on the Paint row itself: the cascade stays and the opener counts as hovered
    s.move(px - 5, py, 0.5)
    assert len(s.stack) == 2 and s.hover[0] is paint
    layers = s.layers()
    assert [lay for lay, _c, _h in layers] == [s.stack[0][0], s.stack[1][0]], "parent menu still drawn"
    assert layers[0][2][0] is paint, "the opener row is highlighted in the parent"
    # into the cascade: its row is hovered and runs on release
    weights, (wx, wy) = _row(s, "Paint Skin Weights", level=1)
    s.move(wx, wy, 0.5)
    assert s.hover[0] is weights
    res = s.release(wx, wy, 0.6)
    assert res[0] == "RUN" and res[1] is weights


def test_cascade_to_another_cascade_row():
    s = _session()
    _paint, (px, py) = _row(s, "Paint")
    fav, (fx, fy) = _row(s, "Assign Favorite Material")
    s.move(px, py, 0.5)
    s.move(fx, fy, 0.5)
    assert len(s.stack) == 2 and s.layout.sub is fav.sub, "the other row's cascade replaces Paint's"


def test_radial_hover_while_cascade_open():
    s = _session()
    _paint, (px, py) = _row(s, "Paint")
    s.move(px, py, 0.5)
    north = s.stack[0][0].radial["N"]
    cx, cy = s.stack[0][1]
    s.move(cx + (north.rect[0] + north.rect[2]) / 2, cy + (north.rect[1] + north.rect[3]) / 2, 0.5)
    assert len(s.stack) == 1 and s.hover[0] is north


def test_click_mode_cascade_row_click_keeps_menu():
    s = _session()
    s.release(*O, 0.05)                  # quick click: the menu stays up
    assert s.mode == "CLICK"
    paint, (px, py) = _row(s, "Paint")
    s.move(px, py, 0.5)
    assert s.click(px, py, 0.6) is None and len(s.stack) == 2, "clicking the open cascade's row keeps it"
    mat, (mx, my) = _row(s, "Material Attributes...")
    s.move(mx, my, 0.7)
    res = s.click(mx, my, 0.8)
    assert res[0] == "RUN" and res[1] is mat


def test_radial_submenu_still_replaces_the_menu():
    # In-place radial submenus (Ctrl+RMB To Vertices) are not cascades: no fall-back to the parent.
    s = engine.Session(mm.MENUS["CTRL_CONVERT"], O, 0.0, measure, None, None, B)
    p = s.params
    s.move(O[0] - p.radius - 5, O[1], 0.3)
    assert len(s.stack) == 2
    assert len(s.layers()) == 1
