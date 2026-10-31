"""Lane A (#99): the marking-menu ring has Maya-style geometry — radius 55, diagonal boxes with their corner
on the diagonal, boxes 21 px high and text + 2 x 25 px wide, the submenu arrow inside the right padding, the list
21 px under the ring. Numbers of the object marking menu and the Shift+RMB menu.
Engine only (no bpy UI)."""

from importlib import import_module

import kit

engine = import_module(kit.MODULE + ".marking.engine")
mm = import_module(kit.MODULE + ".marking.menus")

PRESS = (815, 458)     # press point (pixel, y down) in both menus

# Text ink widths (px) and expected box outer rects (x0, y0, x1, y1 border pixels, y down).
INK_14 = {"Edge": 26, "Object Mode": 69, "Vertex": 33, "UV": 15, "Vertex Face": 59, "Multi": 28, "Face": 24}
EXPECTED_14 = {"N": (776, 393, 853, 413), "NE": (854, 419, 975, 439), "W": (676, 448, 760, 468),
           "E": (870, 448, 936, 468), "SW": (665, 477, 776, 497), "SE": (854, 477, 933, 497),
           "S": (777, 503, 852, 523)}
INK_15 = {"Create Polygon Tool": 107, "Plane": 29, "Disc": 22, "Cylinder": 45, "Sphere": 36, "Cone": 28,
          "Torus": 29, "Cube": 28}
EXPECTED_15 = {"N": (734 - 1, 393, 895 + 1, 413), "NW": (691, 419, 776, 439), "NE": (854, 419, 931, 439),
           "W": (660, 448, 760, 468), "E": (870, 448, 962, 468), "SW": (693, 477, 776, 497),
           "SE": (854, 477, 939, 497), "S": (773, 503, 856, 523)}
LIST_TOP_14 = 545      # list body top border (y down)


ADVANCE = 2.0          # text advance (what blf measures) ~ ink width + the side bearings


def _measure(ink):
    def measure(text):
        t = text.strip()
        return float(ink[t]) + ADVANCE if t in ink else 7.0 * len(text)
    return measure


def _maya_rect(rect):
    """Kit rect (relative to the press point, y up; its sides = the outer sides of the 1 px border) -> the Maya border
    pixel centres (x0, y0, x1, y1, y down), the press point being the centre of the press pixel."""
    x0, y0, x1, y1 = rect
    return (PRESS[0] + x0 + 0.5, PRESS[1] - y1 + 0.5, PRESS[0] + x1 - 0.5, PRESS[1] - y0 - 0.5)


def _compare(menu, ink, maya, tol):
    lay = engine.Layout(menu, _measure(ink), engine.Params())
    assert set(lay.radial) == set(maya), (sorted(lay.radial), sorted(maya))
    bad = []
    for key, want in maya.items():
        got = _maya_rect(lay.radial[key].rect)
        if any(abs(g - w) > t for g, w, t in zip(got, want, tol)):
            bad.append((key, lay.radial[key].label, [round(g, 1) for g in got], want))
    assert not bad, bad
    return lay


def test_params_are_maya():
    p = engine.Params()
    assert (p.radius, p.ring_h, p.ring_pad, p.ring_opt, p.ring_list_gap) == (55.0, 21.0, 25.0, 5.0, 21.0)
    q = p.scaled(1.25)
    assert (q.radius, q.ring_h, q.ring_pad, q.ring_list_gap) == (68.75, 26.25, 31.25, 26.25), "x UI scale"
    assert (q.item_h, q.pad) == (p.item_h * 1.25, p.pad * 1.25), "list rows / hotbox labels keep their sizes"


def test_rmb_object_ring_matches_maya_14():
    # Every border within 1 px vertically, 1.6 px horizontally (the text advance is estimated from the ink).
    lay = _compare(mm.with_object_name(mm.RMB_MESH, "pCube1"), INK_14, EXPECTED_14, (1.6, 1.0, 1.6, 1.0))
    r = lay.radial
    # the anchored sides, exactly
    assert abs(r["E"].rect[0] - 55) < 1e-6 and abs(r["W"].rect[2] + 55) < 1e-6
    assert abs((r["N"].rect[1] + r["N"].rect[3]) / 2 - 55) < 1e-6 and abs((r["S"].rect[1] + r["S"].rect[3]) / 2 + 55) < 1e-6
    d = 55 * 2 ** -0.5
    assert abs(r["NE"].rect[0] - d) < 1e-6 and abs(r["NE"].rect[3] - d) < 1e-6, "NE corner on the diagonal"
    assert abs(r["SW"].rect[2] + d) < 1e-6 and abs(r["SW"].rect[1] + d) < 1e-6, "SW corner on the diagonal"
    assert all(abs(it.rect[3] - it.rect[1] - 21) < 1e-6 for it in r.values()), "21 px boxes"


def test_shift_rmb_ring_matches_maya_15():
    # all 8 directions, option boxes (+5 px) on every box
    lay = _compare(mm.SHIFT_DEFAULT, INK_15, EXPECTED_15, (1.6, 1.0, 1.6, 1.0))
    rects = [it.rect for it in lay.radial.values()]
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert a[2] <= b[0] + 1e-6 or b[2] <= a[0] + 1e-6 or a[3] <= b[1] + 1e-6 or b[3] <= a[1] + 1e-6, (a, b)


def test_widths_follow_text_not_ring_max():
    """Each box is sized to its text (UV 67 px, Object Mode 122 px): text + 2 x 25 (+ 5 with an option box)."""
    lay = engine.Layout(mm.RMB_MESH, _measure(INK_14), engine.Params())
    for key, it in lay.radial.items():
        assert abs((it.rect[2] - it.rect[0]) - (INK_14[it.label] + ADVANCE + 50)) < 1e-6, (key, it.rect)
    lay = engine.Layout(mm.SHIFT_DEFAULT, _measure(INK_15), engine.Params())
    for it in lay.radial.values():
        assert it.option and abs((it.rect[2] - it.rect[0]) - (INK_15[it.label] + ADVANCE + 55)) < 1e-6, it


def test_uv_is_a_submenu_with_the_arrow_in_the_padding():
    label, action = mm.RMB_MESH.radial["E"]
    assert label == "UV" and engine.Layout.has_arrow(action), "Maya: UV has a submenu arrow"
    assert engine.Layout.ring_text(label, action) == "UV", "the arrow doesn't widen the box"
    assert not engine.Layout.has_arrow(mm.RMB_MESH.radial["N"][1])
    assert engine.Layout.has_arrow(("menu", "X")), "a Blender menu opens as a submenu too"
    # flick E past the ring: the submenu opens in place, E = UV, S = UV Shell (Maya's RMB marking menu)
    s = engine.Session(mm.RMB_MESH, (500.0, 400.0), 0.0, lambda t: 7.0 * len(t))
    s.move(530.0, 400.0, 0.05)
    s.move(560.0, 400.0, 0.1)
    assert len(s.stack) == 2, "UV submenu open"
    x, y = s.center
    assert s.release(x + 60.0, y, 0.2)[1].action == ("allset.uv_component", {"mode": 'UV'})
    s = engine.Session(mm.RMB_MESH, (500.0, 400.0), 0.0, lambda t: 7.0 * len(t))
    s.move(530.0, 400.0, 0.05)
    s.move(560.0, 400.0, 0.1)
    x, y = s.center
    assert s.release(x, y - 60.0, 0.2)[1].action == ("allset.uv_component", {"mode": 'SHELL'})


def test_list_starts_21_px_under_the_ring():
    lay = engine.Layout(mm.with_object_name(mm.RMB_MESH, "pCube1"), _measure(INK_14), engine.Params())
    rows = [it for it in lay.items if it.kind == "list"]
    top = max(it.rect[3] for it in rows)
    assert abs((PRESS[1] - top) - LIST_TOP_14) <= 1, (PRESS[1] - top, LIST_TOP_14)
    assert abs(top - (lay.radial["S"].rect[1] - 21)) < 1e-6



def test_fit_ring_keeps_centre_and_bounds():
    """The Maya-sized ring near a corner: boxes slide inside without moving the centre."""
    bounds = (0.0, 0.0, 400.0, 300.0)
    measure = lambda t: 7.0 * len(t)
    for origin in ((20.0, 20.0), (380.0, 280.0), (200.0, 150.0)):
        s = engine.Session(mm.SHIFT_DEFAULT, origin, 0.0, measure, None, None, bounds)
        assert s.center == origin           # list taller than the window: the ring stays, boxes slide
        for it in s.layout.radial.values():
            r = it.rect
            assert r[0] + origin[0] >= -1e-6 and r[2] + origin[0] <= 400 + 1e-6, (origin, it, r)
            assert r[1] + origin[1] >= -1e-6 and r[3] + origin[1] <= 300 + 1e-6, (origin, it, r)
