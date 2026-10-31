# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya framing math (F, A, Shift+F, Shift+A, Ctrl+Shift+F): fit a bounding box into
the visible part of a 3D view with Maya's fit factor.

Maya: F frames the selection (no children), Ctrl+Shift+F
with children, A everything; fit factor 0.95. Blender's view_selected fits a
sphere into the region width only, so a cube overfills a wide 35 mm view and part of it
sits under the sidebar.

Pure ``mathutils`` (no bpy): the view matrix is rebuilt from location / rotation / distance
(``RegionView3D.update`` does not exist in 4.5, so ``perspective_matrix`` would be stale);
the window matrix is the region's current one (perspective: independent of the distance;
orthographic: its extent scales with the distance).
"""

from mathutils import Matrix, Vector

FIT = 0.95       # Maya fit factor
MIN_HALF = 0.5   # half size around a single point (locator, light), Maya units


def view_matrix(loc, rot, dist):
    """RegionView3D.view_matrix for view_location / view_rotation / view_distance."""
    cam = Matrix.Translation(loc) @ rot.to_matrix().to_4x4() @ Matrix.Translation((0.0, 0.0, dist))
    return cam.inverted()


def window_matrix_at(win0, dist0, dist, ortho):
    if not ortho or dist0 <= 0.0:
        return win0
    k = dist0 / dist
    return Matrix.Diagonal((k, k, 1.0, 1.0)) @ win0


def project(persp, p, size):
    """Region pixel position of world point ``p`` (None behind the eye)."""
    v = persp @ Vector((p[0], p[1], p[2], 1.0))
    if v.w <= 1e-9:
        return None
    return Vector(((v.x / v.w * 0.5 + 0.5) * size[0], (v.y / v.w * 0.5 + 0.5) * size[1]))


def box_corners(points, min_half=MIN_HALF):
    """8 corners of the axis-aligned box around ``points`` (padded if it is a point)."""
    lo = Vector((min(p[0] for p in points), min(p[1] for p in points), min(p[2] for p in points)))
    hi = Vector((max(p[0] for p in points), max(p[1] for p in points), max(p[2] for p in points)))
    if max(hi - lo) < 1e-6:
        lo -= Vector((min_half,) * 3)
        hi += Vector((min_half,) * 3)
    return [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]


def _bounds(persp, corners, size):
    pts = [project(persp, c, size) for c in corners]
    if any(p is None for p in pts):
        return None
    xs, ys = [p.x for p in pts], [p.y for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def fit(points, rot, win0, dist0, ortho, size, rect, factor=FIT, min_half=MIN_HALF):
    """(view_location, view_distance) that fit ``points`` into ``rect`` (region pixels).

    ``rect`` = (x0, y0, x1, y1), the visible part of the region; the box fills ``factor``
    of it on its tighter axis and is centred in it. ``size`` = region (width, height).
    """
    corners = box_corners(points, min_half)
    centre = sum(corners, Vector()) / 8.0
    radius = max((c - centre).length for c in corners)
    tx, ty = (rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0
    hw, hh = (rect[2] - rect[0]) / 2.0 * factor, (rect[3] - rect[1]) / 2.0 * factor
    right, up = rot @ Vector((1.0, 0.0, 0.0)), rot @ Vector((0.0, 1.0, 0.0))

    def persp_at(loc, d):
        return window_matrix_at(win0, dist0, d, ortho) @ view_matrix(loc, rot, d)

    def offset(loc, d):
        """Projected box centre minus the target, and the bounds (None when a corner is behind the eye)."""
        b = _bounds(persp_at(loc, d), corners, size)
        if b is None:
            return None, None
        return Vector(((b[0] + b[2]) / 2.0 - tx, (b[1] + b[3]) / 2.0 - ty)), b

    def centred(d):
        """Pan at distance ``d`` until the projected box is centred in the visible rect (sidebar excluded):
        (view location, box bounds or None). Newton steps on the observed response (the box's near and far
        corners move by different amounts in perspective, so one unit at the centre's depth over- or
        undershoots), halved while the error grows."""
        loc = centre.copy()
        err, b = offset(loc, d)
        eps = max(radius, 1e-6) * 1e-3
        for _i in range(24):
            if err is None:
                return loc, None
            if abs(err.x) < 0.25 and abs(err.y) < 0.25:
                break
            ex, _ = offset(loc + right * eps, d)
            ey, _ = offset(loc + up * eps, d)
            if ex is None or ey is None:
                break
            jx, jy = (ex - err) / eps, (ey - err) / eps
            det = jx.x * jy.y - jy.x * jx.y
            if abs(det) < 1e-12:
                break
            sr = (err.x * jy.y - jy.x * err.y) / det
            su = (jx.x * err.y - err.x * jx.y) / det
            step = 1.0
            while step > 1e-3:
                cand = loc - right * (sr * step) - up * (su * step)
                e2, b2 = offset(cand, d)
                if e2 is not None and e2.length < err.length:
                    loc, err, b = cand, e2, b2
                    break
                step *= 0.5
            else:
                break
        return loc, b

    def scale(d):
        b = centred(d)[1]
        if b is None:
            return float("inf")
        return max((b[2] - b[0]) / (2.0 * hw), (b[3] - b[1]) / (2.0 * hh))

    if not ortho and win0[0][0] > 0.0 and win0[1][1] > 0.0:
        # Maya viewFit in perspective (Maya 2026 for fitFactor 1.0 / 0.95 / 0.9): the camera stands back from
        # the box centre by the box's half depth
        # along the view plus the distance at which the box's half extents across the view (the axis-aligned box
        # projected on the view's right / up axes) fill the field of view times the fit factor. The field of view is
        # the visible rect's (sidebars excluded). Maya aims the camera at the box centre: the centre is put on the
        # visible rect's middle.
        fwd = rot @ Vector((0.0, 0.0, -1.0))
        lo_c, hi_c = corners[0], corners[-1]
        half = (hi_c - lo_c) / 2.0

        def extent(axis):
            return abs(axis.x) * half.x + abs(axis.y) * half.y + abs(axis.z) * half.z
        tan_w = (rect[2] - rect[0]) / max(size[0], 1.0) / win0[0][0]
        tan_h = (rect[3] - rect[1]) / max(size[1], 1.0) / win0[1][1]
        d = extent(fwd) + max(extent(right) / tan_w, extent(up) / tan_h) / factor
        ndc_x = (rect[0] + rect[2]) / max(size[0], 1.0) - 1.0
        ndc_y = (rect[1] + rect[3]) / max(size[1], 1.0) - 1.0
        loc = centre - right * (ndc_x * d / win0[0][0]) - up * (ndc_y * d / win0[1][1])
        return loc, d

    # Distance search on the centred box: refitting the distance and panning in turns oscillated for a box much
    # wider than deep in a narrow perspective view (A with a far child: the view ended off by 100+ px).
    lo, hi = radius * 1e-3, max(dist0, radius * 4.0)
    while scale(hi) > 1.0 and hi < radius * 1e7:
        hi *= 2.0
    for _i in range(48):
        mid = (lo * hi) ** 0.5
        if scale(mid) > 1.0:
            lo = mid
        else:
            hi = mid
    return centred(hi)[0], hi


def visible_rect(window_region, others):
    """Region-local (x0, y0, x1, y1) of ``window_region`` not covered by overlapping
    regions (``others``: (x, y, width, height) in window coordinates — sidebar, toolbar,
    transparent headers when Region Overlap is on). A region at least half as wide as the
    view and less than half as tall cuts from the top or bottom, any other from the side its
    centre is on."""
    wx, wy, ww, wh = window_region
    x0, y0, x1, y1 = wx, wy, wx + ww, wy + wh
    for rx, ry, rw, rh in others:
        if rw <= 1 or rh <= 1:
            continue
        # overlap with what is still visible
        ox0, oy0, ox1, oy1 = max(rx, x0), max(ry, y0), min(rx + rw, x1), min(ry + rh, y1)
        if ox0 >= ox1 or oy0 >= oy1:
            continue
        if rw >= ww / 2.0 and rh < wh / 2.0:   # header-like: top or bottom
            if ry + rh / 2.0 >= wy + wh / 2.0:
                y1 = min(y1, ry)
            else:
                y0 = max(y0, ry + rh)
        elif rx + rw / 2.0 >= wx + ww / 2.0:
            x1 = min(x1, rx)
        else:
            x0 = max(x0, rx + rw)
    if x1 - x0 < ww * 0.25 or y1 - y0 < wh * 0.25:   # nearly covered: keep the whole region
        x0, y0, x1, y1 = wx, wy, wx + ww, wy + wh
    return (x0 - wx, y0 - wy, x1 - wx, y1 - wy)
