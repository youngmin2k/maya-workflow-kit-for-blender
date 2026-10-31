"""Maya framing fit (0.95 of the visible part of the view) and hotbox rows kept
out from under the sidebar."""

import math
from importlib import import_module

from mathutils import Matrix, Quaternion, Vector

import kit

framing = import_module(kit.MODULE + ".operators.framing")
engine = import_module(kit.MODULE + ".marking.engine")

SIZE = (1100, 700)


def _persp_win(lens=35.0, size=SIZE, near=0.01, far=1000.0):
    # Blender viewport: sensor 36 mm on the wider axis (AUTO fit).
    w, h = size
    half_w = near * 18.0 / lens
    half_h = half_w * h / w
    return Matrix(((near / half_w, 0, 0, 0), (0, near / half_h, 0, 0),
                   (0, 0, -(far + near) / (far - near), -2 * far * near / (far - near)),
                   (0, 0, -1, 0)))


def _ortho_win(dist, size=SIZE, far=1000.0):
    w, h = size
    half_w = dist
    half_h = half_w * h / w
    return Matrix(((1 / half_w, 0, 0, 0), (0, 1 / half_h, 0, 0), (0, 0, -2 / (2 * far), 0), (0, 0, 0, 1)))


def _rot():
    return Quaternion((1, 0, 0), math.radians(60)) @ Quaternion((0, 0, 1), math.radians(30))


def _cube(half=0.5, at=(0, 0, 0)):
    return [Vector(at) + Vector((x, y, z)) for x in (-half, half) for y in (-half, half) for z in (-half, half)]


def _proj_bounds(loc, dist, win, rot, pts, size=SIZE):
    persp = win @ framing.view_matrix(loc, rot, dist)
    pp = [framing.project(persp, p, size) for p in framing.box_corners(pts)]
    assert all(p is not None for p in pp)
    return min(p.x for p in pp), min(p.y for p in pp), max(p.x for p in pp), max(p.y for p in pp)


def _check_fit(b, rect, factor=framing.FIT, persp=False):
    x0, y0, x1, y1 = rect
    assert b[0] >= x0 - 0.5 and b[2] <= x1 + 0.5 and b[1] >= y0 - 0.5 and b[3] <= y1 + 0.5, (b, rect)
    ratio = max((b[2] - b[0]) / (x1 - x0), (b[3] - b[1]) / (y1 - y0))
    if persp:
        # Maya's perspective viewFit leaves more room than the fit factor (box centre aimed at, its half
        # extents across the view fill the factor at the near side's depth; tests/test_step258_view.py)
        assert 0.5 < ratio < factor, ratio
        return
    assert abs(ratio - factor) < 0.01, ratio
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    assert abs(cx - (x0 + x1) / 2) < 1.0 and abs(cy - (y0 + y1) / 2) < 1.0, (cx, cy)


def test_view_matrix_convention():
    # Camera at loc + rot @ (0, 0, dist), looking down its -Z: the target sits at (0, 0, -dist).
    vm = framing.view_matrix(Vector((1, 2, 3)), Quaternion(), 10.0)
    assert (vm @ Vector((1, 2, 3))) == Vector((0, 0, -10))


def test_perspective_fit_whole_region():
    win, rot, pts = _persp_win(), _rot(), _cube()
    rect = (0, 0, SIZE[0], SIZE[1])
    loc, dist = framing.fit(pts, rot, win, 1.0, False, SIZE, rect)
    _check_fit(_proj_bounds(loc, dist, win, rot, pts), rect, persp=True)
    # Blender's own view_selected put this cube at ~1.07 (dogfood): it must be farther now.
    assert dist > 1.5, dist


def test_perspective_fit_excludes_sidebar():
    win, rot, pts = _persp_win(), _rot(), _cube(0.5, (2, -1, 0.3))
    rect = framing.visible_rect((0, 0, SIZE[0], SIZE[1]), [(SIZE[0] - 350, 0, 350, SIZE[1])])
    assert rect == (0, 0, SIZE[0] - 350, SIZE[1]), rect
    loc, dist = framing.fit(pts, rot, win, 5.0, False, SIZE, rect)
    _check_fit(_proj_bounds(loc, dist, win, rot, pts), rect, persp=True)


def test_ortho_fit():
    rot, pts = Quaternion(), _cube(1.0)   # top view
    dist0 = 10.0
    win0 = _ortho_win(dist0)
    rect = (0, 0, SIZE[0], SIZE[1])
    loc, dist = framing.fit(pts, rot, win0, dist0, True, SIZE, rect)
    win = framing.window_matrix_at(win0, dist0, dist, True)
    _check_fit(_proj_bounds(loc, dist, win, rot, pts), rect)


def test_single_point_gets_a_box():
    corners = framing.box_corners([Vector((3, 0, 0))])
    xs = sorted({c.x for c in corners})
    assert xs == [3 - framing.MIN_HALF, 3 + framing.MIN_HALF]
    win, rot, pts = _persp_win(), _rot(), [Vector((3, 0, 0))]
    loc, dist = framing.fit(pts, rot, win, 1.0, False, SIZE, (0, 0, *SIZE))
    assert math.isfinite(dist)
    _check_fit(_proj_bounds(loc, dist, win, rot, pts), (0, 0, *SIZE), persp=True)


def test_visible_rect_cases():
    win = (100, 50, 1000, 600)
    assert framing.visible_rect(win, []) == (0, 0, 1000, 600)
    # toolbar on the left (overlapping), sidebar on the right
    r = framing.visible_rect(win, [(100, 50, 40, 600), (800, 50, 300, 600)])
    assert r == (40, 0, 700, 600), r
    # transparent header + tool header on top (wide regions cut from the top)
    r = framing.visible_rect(win, [(100, 626, 1000, 24), (100, 602, 1000, 24)])
    assert r == (0, 0, 1000, 552), r
    # quad view: a sidebar starting left of the right-hand view's centre still cuts its right side
    assert framing.visible_rect((661, 94, 660, 387), [(971, 94, 350, 773)]) == (0, 0, 310, 387)
    # regions that don't overlap the window (Region Overlap off) change nothing
    assert framing.visible_rect(win, [(1100, 50, 300, 600), (100, 650, 1000, 26)]) == (0, 0, 1000, 600)
    # a sidebar almost as wide as the view: keep the whole region
    assert framing.visible_rect(win, [(170, 50, 470, 600), (640, 50, 460, 600)]) == (0, 0, 1000, 600)


def test_hotbox_rows_stay_in_bounds():
    rows = [[("a", "File"), ("b", "Edit"), ("c", "Create"), ("d", "Select"), ("e", "Modify")]]
    measure = lambda s: 10.0 * len(s)  # noqa: E731
    bounds = (0, 0, 700, 600)
    lay = engine.HotboxLayout(rows, (650.0, 300.0), measure, bounds=bounds)
    assert max(r[2] for r, _k, _l in lay.labels) <= 700 + 1e-6
    lay = engine.HotboxLayout(rows, (20.0, 300.0), measure, bounds=bounds)
    assert min(r[0] for r, _k, _l in lay.labels) >= 0
    # a row wider than the visible part wraps onto two rows, order kept
    narrow = engine.HotboxLayout(rows, (150.0, 300.0), measure, bounds=(0, 0, 250, 600))
    assert [k for _r, k, _l in narrow.labels] == list("abcde")
    assert len({r[1] for r, _k, _l in narrow.labels}) == 2
    assert all(0 <= r[0] and r[2] <= 250 for r, _k, _l in narrow.labels)
    free = engine.HotboxLayout(rows, (350.0, 300.0), measure, bounds=bounds)
    ref = engine.HotboxLayout(rows, (350.0, 300.0), measure)
    assert [r for r, _k, _l in free.labels] == [r for r, _k, _l in ref.labels], "centred rows don't move"


def _kmis(km, type, **mods):
    km = kit.maya_kc().keymaps[km]
    want = {"shift": False, "ctrl": False, "alt": False, **mods}
    return [k for k in km.keymap_items if k.active and k.type == type and k.value == 'PRESS'
            and all(getattr(k, m) == v for m, v in want.items()) and not k.oskey]


def test_frame_keys():
    f = _kmis("3D View", "F")
    assert [k.idname for k in f] == ["allset.frame"] and f[0].properties.selected
    cf = _kmis("3D View", "F", ctrl=True, shift=True)
    assert [k.idname for k in cf] == ["allset.frame_all_views"]
    assert cf[0].properties.selected and cf[0].properties.children
    assert [k.idname for k in _kmis("3D View", "F", shift=True)] == ["allset.frame_all_views"]
