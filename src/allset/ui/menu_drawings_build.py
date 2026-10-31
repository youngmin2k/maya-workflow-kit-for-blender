# SPDX-License-Identifier: GPL-3.0-or-later
"""Kit menu pictures for Create, Curves, Surfaces, Skeleton and Skin (#54) — see ``menu_drawings``."""

import math

import numpy as np

from .menu_drawings import RED, TAN, blob, icon
from .menu_drawings_mesh import dashed_line, dashed_ring, hex_cube, ibeam, minus, page, vsq
from .menu_drawings_select import cv_sq
from .shelf_icons import (DARK, LAV, LIGHT, ORANGE, WHITE, _hex, arrow, bezier, bone, cone, cylinder, face_grid, hgrad,
                          human, lerp, nosign, pencil, plus, shade, shirt, sphere_colour, wave_pts)

CURVE = _hex("#4aa8d8")
NURBS = _hex("#6a9ad0")
FILLET = _hex("#3aa83a")
VOL = _hex("#b4b4b4")


# --- shared parts -----------------------------------------------------------------------------

def nsheet(cv, q, col=NURBS, ol=True):
    cv.fill(cv.m_poly(q), hgrad(cv, min(p[0] for p in q), max(p[0] for p in q), col, 0.35, -0.25), ol=ol)


def curved_sheet(cv, x0, y0, w=20, h=16, bend=5, col=NURBS):
    top = bezier((x0, y0 + bend), (x0 + w * 0.4, y0 - bend), (x0 + w * 0.6, y0 + bend), (x0 + w, y0), 12)
    bot = [(x + h * 0.25, y + h) for x, y in reversed(top)]
    nsheet(cv, top + bot, col)
    return top, bot


def joint(cv, x, y, r=2.6, col=LIGHT):
    cv.circle(x, y, r, col, ol=True)


def chain(cv, pts, col=LIGHT, r=3.2):
    for a, b in zip(pts, pts[1:]):
        bone(cv, a, b, r, col)
    joint(cv, *pts[-1], r * 0.7, col)


def weight_square(cv, x0, y0, x1, y1, ol=True):
    t = np.clip(((cv.x - x0) + (cv.y - y0)) / max(x1 - x0 + y1 - y0, 1), 0, 1)
    col = np.stack([shade(LAV, -0.75)[i] + (shade(LAV, 0.2)[i] - shade(LAV, -0.75)[i]) * t for i in range(3)], -1)
    cv.fill(cv.m_rect(x0, y0, x1, y1), col, ol=ol)


def stitches(cv, p0, p1, n=4, col=RED):
    for i in range(n):
        x, y = lerp(p0, p1, (i + 0.5) / n)
        cv.line((x - 2.5, y - 3), (x + 2.5, y + 3), 1.4, col)


def axes3(cv, cx, cy, s=7.0, col=LIGHT):
    arrow(cv, (cx, cy), (cx, cy - s), w=1.8, col=col, head=3.5)
    arrow(cv, (cx, cy), (cx + s, cy), w=1.8, col=col, head=3.5)
    cv.line((cx, cy), (cx - s * 0.6, cy + s * 0.6), 1.8, col, ol=True)


def capsule(cv, p0, p1, r, col=LAV, w=1.6):
    cv.fill(cv.m_capsule_ring(p0, p1, r, w), col, ol=True)


def gear(cv, cx, cy, r, col=ORANGE, teeth=8):
    m = cv.m_circle(cx, cy, r * 0.78)
    ang = np.arctan2(cv.y - cy, cv.x - cx)
    tooth = (np.cos(ang * teeth) > 0.2) & cv.m_circle(cx, cy, r)
    cv.fill((m | tooth) & ~cv.m_circle(cx, cy, r * 0.35), col, ol=True)


def star(cv, cx, cy, r0, r1, n, col=ORANGE, rot=-90):
    pts = []
    for k in range(2 * n):
        a = math.radians(rot + 180 * k / n)
        r = r1 if k % 2 == 0 else r0
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    cv.poly(pts, col, ol=True)


# --- Create -----------------------------------------------------------------------------------

@icon("Create/Adobe(R) Illustrator(R) Object...")
def i_create_ai(cv):
    cv.rect(3, 3, 29, 29, shade(LIGHT, 0.2), ol=True)
    cv.text("AI", (0.2, 0.2, 0.2), 6.5, 9.5, cell=2.0, bold=False)


@icon("Create/Annotation...")
def i_create_annotation(cv):
    cv.frame(2, 2, 22, 17, 1.4, LIGHT, ol=True)
    ibeam(cv, 9, 5, 14)
    hex_cube(cv, 23, 22, 8, CURVE)


@icon("Create/Construction Plane")
def i_construction_plane(cv):
    q = [(2, 24), (14, 16), (30, 18), (18, 27)]
    cv.poly(q, LIGHT, ol=True)
    face_grid(cv, q, 2, DARK)
    pencil(cv, (14, 20), (28, 4), w=5, col=_hex("#48a9b4"))


@icon("Create/Curve Tools/CV Curve Tool")
def i_cv_curve_tool(cv):
    for a, b in (((5, 27), (10, 6)), ((10, 6), (22, 6)), ((22, 6), (27, 27))):
        dashed_line(cv, a, b, 1.0, LIGHT, dash=2.0)
    cv.polyline(bezier((5, 27), (10, 6), (22, 6), (27, 27), 24), 2.0, CURVE, ol=True)
    for p in ((5, 27), (10, 6), (22, 6), (27, 27)):
        vsq(cv, p[0], p[1], 2.0, LIGHT)


@icon("Create/Curve Tools/Two Point Circular Arc")
def i_two_point_arc(cv):
    cv.fill(cv.m_ring(16, 17, 11, 2.2) & cv.m_angle(16, 17, 150, 330), CURVE, ol=True)
    vsq(cv, 7, 24, 2.4, LIGHT)
    vsq(cv, 26, 8, 2.4, LIGHT)
    cv.circle(17, 17, 1.8, WHITE, ol=True)


@icon("Create/Measure Tools/Arc Length Tool")
def i_arc_length(cv):
    cv.text("L", LIGHT, 2, 2, ol=True)
    cv.polyline(bezier((10, 28), (16, -6), (22, 34), (30, 6), 24), 2.0, CURVE, ol=True)
    cv.line((15, 20), (15, 30), 1.4, LIGHT)
    cv.line((29, 20), (29, 30), 1.4, LIGHT)
    arrow(cv, (22, 25), (16.5, 25), w=1.4, head=3)
    arrow(cv, (22, 25), (27.5, 25), w=1.4, head=3)


@icon("Create/Measure Tools/Distance Tool")
def i_distance_tool(cv):
    cv.line((5, 3), (5, 17), 1.8, CURVE)
    cv.line((27, 3), (27, 17), 1.8, CURVE)
    arrow(cv, (16, 10), (7.5, 10), w=1.8, head=4)
    arrow(cv, (16, 10), (24.5, 10), w=1.8, head=4)
    cv.text("T", LIGHT, 13.5, 21, ol=True)


@icon("Create/Measure Tools/Parameter Tool")
def i_parameter_tool(cv):
    cv.polyline(bezier((4, 24), (12, 0), (20, 12), (30, 2), 24), 2.0, CURVE, ol=True)
    cv.line((8, 4), (16, 14), 1.6, LIGHT, ol=True)
    cv.line((16, 4), (8, 14), 1.6, LIGHT, ol=True)
    cv.text("U", LIGHT, 20, 21, ol=True)


@icon("Create/Polygon Primitives/Gear")
def i_poly_gear(cv):
    gear(cv, 16, 16, 13)


@icon("Create/Polygon Primitives/Helix")
def i_poly_helix(cv):
    for k in range(4):
        y = 7 + k * 6
        cv.fill(cv.m_ering(16, y, 11, 3.2, 3.0) & (cv.y >= y - 0.5), shade(ORANGE, -0.15), ol=True)
        cv.fill(cv.m_ering(16, y + 1.5, 11, 3.2, 3.0) & (cv.y < y + 1.5), ORANGE, ol=True)


@icon("Create/Polygon Primitives/Pipe")
def i_poly_pipe(cv):
    cylinder(cv, 16, 8, 24, 12, 5, ORANGE, wire=4)
    cv.fill(cv.m_ellipse(16, 8, 7, 2.6), shade(ORANGE, -0.55))


@icon("Create/Polygon Primitives/Prism")
def i_poly_prism(cv):
    cv.poly([(3, 20), (11, 7), (16, 25)], shade(ORANGE, 0.2), ol=True)
    cv.poly([(11, 7), (24, 4), (29, 22), (16, 25)], ORANGE, ol=True)
    cv.line((17.5, 5.5), (22.5, 23.5), 1.2, DARK)


@icon("Create/Polygon Primitives/Pyramid")
def i_poly_pyramid(cv):
    cv.poly([(16, 3), (5, 22), (16, 28)], shade(ORANGE, 0.15), ol=True)
    cv.poly([(16, 3), (16, 28), (27, 22)], shade(ORANGE, -0.15), ol=True)
    cv.line((16, 3), (16, 28), 1.0, DARK)


@icon("Create/Polygon Primitives/Soccer Ball")
def i_poly_soccer(cv):
    cv.fill(cv.m_circle(16, 16, 13), sphere_colour(cv, 16, 16, 13, ORANGE, amb=0.85, dif=0.3), ol=True)
    for cx, cy, r in ((16, 16, 3.6), (16, 6, 2.6), (25, 13, 2.6), (22, 24, 2.6), (10, 24, 2.6), (7, 13, 2.6)):
        pts = [(cx + r * math.cos(math.radians(-90 + 72 * k)), cy + r * math.sin(math.radians(-90 + 72 * k)))
               for k in range(5)]
        cv.fill(cv.m_poly(pts) & cv.m_circle(16, 16, 12.5), shade(ORANGE, -0.5))


@icon("Create/Polygon Primitives/Spherical Harmonics")
def i_poly_harmonics(cv):
    star(cv, 16, 17, 7.5, 14, 5)


@icon("Create/Polygon Primitives/Ultra Shape")
def i_poly_ultra(cv):
    star(cv, 16, 16, 8.5, 14, 6)


@icon("Create/Volume Primitives/Cone")
def i_volume_cone(cv):
    cone(cv, 16, 3, 24, 11, 4.5, VOL)
    dashed_line(cv, (16, 3), (16, 28), 1.0, DARK, dash=2.0)
    cv.fill(cv.m_ering(16, 24, 11, 4.5, 1.0) & (cv.y < 24), DARK, alpha=0.6)


@icon("Create/Volume Primitives/Cube")
def i_volume_cube(cv):
    hex_cube(cv, 16, 16, 14, VOL)
    for a, b in (((16, 2), (16, 30)), ((4, 9), (28, 23)), ((28, 9), (4, 23))):
        dashed_line(cv, a, b, 1.0, DARK, dash=2.0)


@icon("Create/Volume Primitives/Sphere")
def i_volume_sphere(cv):
    cv.fill(cv.m_circle(16, 16, 13.5), sphere_colour(cv, 16, 16, 13.5, VOL, amb=0.85, dif=0.3), ol=True)
    dashed_ring(cv, 16, 16, 9, 1.0, DARK, n=10)
    cv.fill(cv.m_ering(16, 16, 13, 4, 1.0), DARK, alpha=0.6)


# --- Curves -----------------------------------------------------------------------------------

@icon("Curves/Align")
def i_curves_align(cv):
    cv.polyline(bezier((4, 3), (9, 3), (8, 12), (8, 14), 12), 2.2, CURVE, ol=True)
    cv.polyline(bezier((8, 18), (8, 22), (6, 29), (12, 29), 12), 2.2, CURVE, ol=True)
    arrow(cv, (22, 3), (22, 13), w=2.2, head=4)
    arrow(cv, (22, 29), (22, 19), w=2.2, head=4)


@icon("Curves/CV Hardness")
def i_cv_hardness(cv):
    cv.polyline([(3, 18), (14, 18), (14, 29)], 2.2, LIGHT, ol=True)
    cv.polyline(bezier((17, 4), (26, 4), (28, 6), (28, 15), 12), 2.2, CURVE, ol=True)


@icon("Curves/Cut")
def i_curves_cut(cv):
    cv.polyline(bezier((3, 10), (12, 4), (18, 28), (29, 20), 24), 2.2, CURVE, ol=True)
    cv.line((5, 27), (27, 5), 2.0, LIGHT, ol=True)


@icon("Curves/Duplicate Surface Curves")
def i_dup_surface_curves(cv):
    cv.fill(cv.m_rect(3, 16, 25, 29) & ~cv.m_ellipse(14, 29, 7, 8), CURVE, ol=True)
    cv.fill(cv.m_ring(14, 16, 9, 1.8) & (cv.y <= 16), LIGHT, ol=True)
    cv.polyline([(3, 10), (3, 2), (25, 2), (25, 6)], 1.4, LIGHT)
    arrow(cv, (27, 16), (27, 4), w=2.2, head=4.5)


@icon("Curves/Extend/Extend Curve On Surface")
def i_extend_on_surface(cv):
    cv.poly([(16, 2), (29, 14), (16, 27), (3, 14)], CURVE, ol=True)
    cv.polyline(bezier((4, 20), (6, 30), (14, 26), (16, 16), 16), 2.0, LIGHT, ol=True)
    arrow(cv, (12, 18), (21, 9), w=2.2, head=4.5)
    cv.line((19, 20), (29, 12), 1.6, LIGHT, ol=True)


@icon("Curves/Fillet")
def i_curves_fillet(cv):
    cv.polyline([(5, 28), (16, 3), (27, 28)], 2.0, LIGHT, ol=True)
    cv.fill(cv.m_ring(16, 24, 8, 2.2) & (cv.y <= 22), CURVE, ol=True)
    vsq(cv, 8, 21, 2.2, LIGHT)
    vsq(cv, 24, 21, 2.2, LIGHT)


@icon("Curves/Fit B-spline")
def i_fit_bspline(cv):
    cv.polyline([(3, 22), (9, 6), (20, 26), (29, 10)], 2.0, LIGHT, ol=True)
    cv.polyline(bezier((3, 16), (12, 4), (18, 30), (29, 16), 24), 2.2, CURVE, ol=True)


@icon("Curves/Intersect")
def i_curves_intersect(cv):
    cv.polyline(bezier((2, 10), (12, 2), (18, 22), (30, 14), 24), 2.0, CURVE, ol=True)
    cv.polyline(bezier((2, 24), (12, 30), (18, 6), (30, 2), 24), 2.0, CURVE, ol=True)
    cv.frame(9, 11, 15, 17, 1.2, WHITE, ol=True)
    cv.frame(18, 6, 24, 12, 1.2, WHITE, ol=True)


@icon("Curves/Move Seam")
def i_move_seam(cv):
    cv.ring(13, 14, 10, 2.4, CURVE, ol=True)
    vsq(cv, 22, 19, 2.4, LIGHT)
    from .menu_drawings_mesh import cursor_white
    cursor_white(cv, 21, 16, 0.95, col=WHITE)


@icon("Curves/Offset/Offset Curve On Surface")
def i_offset_on_surface(cv):
    cv.poly([(14, 2), (28, 15), (14, 28), (1, 15)], CURVE, ol=True)
    for r, col in ((10, LIGHT), (6.5, shade(CURVE, 0.5)), (3.5, LIGHT)):
        cv.fill(cv.m_ring(17, 22, r + 1, 1.8) & (cv.y <= 22), col)


@icon("Curves/Open/Close")
def i_open_close(cv):
    cv.fill(cv.m_ring(10, 21, 7, 2.4) & ~cv.m_angle(10, 21, 280, 350), CURVE, ol=True)
    cv.ring(23, 9, 6.5, 2.4, CURVE, ol=True)


@icon("Curves/Project Tangent")
def i_project_tangent(cv):
    cv.polyline(bezier((3, 28), (8, 28), (10, 5), (17, 5), 16), 2.2, LIGHT, ol=True)
    cv.polyline(bezier((17, 5), (24, 5), (22, 26), (30, 26), 16), 2.2, CURVE, ol=True)


@icon("Curves/Reverse Direction")
def i_reverse_direction(cv):
    cv.polyline(bezier((12, 4), (16, 10), (16, 22), (12, 28), 16), 2.2, LIGHT, ol=True)
    cv.polyline(bezier((22, 10), (26, 14), (26, 22), (23, 28), 16), 2.2, CURVE, ol=True)
    vsq(cv, 23, 5, 2.2, LIGHT)
    vsq(cv, 12, 18, 2.0, LIGHT)


# --- Surfaces ---------------------------------------------------------------------------------

@icon("Surfaces/Align")
def i_surf_align(cv):
    curved_sheet(cv, 10, 6, 18, 18)
    curved_sheet(cv, 2, 3, 16, 16, col=WHITE)
    nsheet(cv, [(6, 20), (18, 18), (20, 29), (8, 30)], FILLET)


@icon("Surfaces/Attach Without Moving")
def i_attach_without_moving(cv):
    curved_sheet(cv, 8, 10, 20, 16)
    nsheet(cv, [(2, 18), (16, 14), (18, 22), (4, 26)], TAN)
    cv.fill(cv.m_ering(10, 8, 6, 5, 2.6), LIGHT, ol=True)


@icon("Surfaces/Bevel")
def i_surf_bevel(cv):
    hex_cube(cv, 16, 16, 14, _hex("#5aaed4"))
    cv.poly([(16, 14), (27, 8), (27, 11), (16, 17), (5, 11), (5, 8)], LIGHT, ol=True)
    cv.line((16, 17), (16, 30), 2.0, LIGHT)


def _birail(cv, n):
    for k in range(n):
        x = 5 + k * (20 / max(n - 1, 1))
        cv.fill(cv.m_ellipse(x + 2, 15 + k * 1.5, 5, 9), hgrad(cv, x - 3, x + 7, NURBS, 0.35, -0.3), ol=True)
    cv.polyline(bezier((2, 6), (10, 2), (20, 8), (30, 6), 16), 1.4, DARK)
    cv.polyline(bezier((4, 26), (12, 30), (22, 26), (30, 28), 16), 1.4, DARK)


@icon("Surfaces/Birail/Birail 2 Tool")
def i_birail2(cv):
    _birail(cv, 2)


@icon("Surfaces/Birail/Birail 3+ Tool")
def i_birail3(cv):
    _birail(cv, 4)


@icon("Surfaces/Booleans/Difference Tool")
def i_surf_bool_difference(cv):
    cv.fill(cv.m_circle(19, 12, 10) & ~cv.m_circle(12, 20, 10), _hex("#5aaed4"), ol=True)
    dashed_ring(cv, 12, 20, 10, 1.6)


@icon("Surfaces/Booleans/Intersection Tool")
def i_surf_bool_intersection(cv):
    dashed_ring(cv, 14, 17, 12, 1.6)
    cv.fill(cv.m_circle(14, 17, 10) & cv.m_circle(19, 13, 10), _hex("#5aaed4"), ol=True)


@icon("Surfaces/Booleans/Union Tool")
def i_surf_bool_union(cv):
    cv.circle(16, 16, 13, _hex("#5aaed4"), ol=True)
    dashed_ring(cv, 14, 18, 8, 1.4, shade(_hex("#5aaed4"), -0.45))


@icon("Surfaces/Boundary")
def i_surf_boundary(cv):
    q = bezier((5, 16), (12, 4), (20, 8), (27, 4), 12) + bezier((27, 18), (22, 28), (14, 22), (7, 28), 12)
    nsheet(cv, q)
    cv.polyline(q + [q[0]], 1.6, WHITE)


@icon("Surfaces/Duplicate NURBS Patch")
def i_dup_patch(cv):
    curved_sheet(cv, 8, 12, 20, 15)
    nsheet(cv, [(4, 6), (17, 4), (19, 17), (6, 19)], TAN)
    cv.rect(9, 9, 13, 13, (0.2, 0.2, 0.2))


@icon("Surfaces/Move Seam")
def i_surf_move_seam(cv):
    cylinder(cv, 16, 5, 22, 10, 4, NURBS)
    dashed_line(cv, (16, 9), (16, 26), 1.4, RED, dash=2.0)
    cv.fill(cv.m_ering(16, 25, 13, 4, 2.0) & (cv.y > 25), RED, ol=True)
    cv.poly([(2, 23), (6, 24), (3, 28)], RED, ol=True)
    cv.poly([(30, 23), (26, 24), (29, 28)], RED, ol=True)


@icon("Surfaces/Offset")
def i_surf_offset(cv):
    curved_sheet(cv, 9, 10, 20, 16)
    curved_sheet(cv, 4, 4, 18, 16, col=TAN)
    arrow(cv, (26, 10), (30, 4), w=1.6, col=RED, head=3)
    arrow(cv, (5, 28), (2, 22), w=1.6, col=RED, head=3)


@icon("Surfaces/Reverse Direction")
def i_surf_reverse(cv):
    cv.poly([(6, 6), (26, 10), (26, 30), (6, 26)], NURBS, ol=True)
    cv.poly([(6, 6), (26, 10), (6, 26)], TAN)
    cv.line((2, 30), (30, 2), 1.4, (0.1, 0.1, 0.1))
    cv.polyline([(10, 22), (10, 8), (16, 16), (16, 4)], 1.4, RED)
    arrow(cv, (22, 16), (22, 28), w=1.6, col=RED, head=3.5)


@icon("Surfaces/Round Tool")
def i_round_tool(cv):
    cv.rect(2, 2, 30, 30, _hex("#2a5a8a"), ol=True)
    cv.fill(cv.m_rect(4, 4, 28, 28) & ~(cv.m_rect(15, 15, 28, 28) & ~cv.m_circle(15, 15, 13)), NURBS)
    cv.fill(cv.m_ring(15, 15, 6, 3.0) & (cv.x >= 15) & (cv.y >= 15), WHITE)
    dashed_line(cv, (4, 13), (14, 13), 1.4, RED, dash=1.5)
    dashed_line(cv, (13, 4), (13, 14), 1.4, RED, dash=1.5)


@icon("Surfaces/Square")
def i_surf_square(cv):
    cv.frame(2, 4, 30, 28, 1.6, RED, ol=True)
    cylinder(cv, 16, 10, 20, 8, 3, NURBS)
    for a, b in (((4, 10), (10, 13)), ((28, 10), (22, 13)), ((4, 22), (10, 20)), ((28, 22), (22, 20))):
        cv.line(a, b, 1.2, WHITE)


def _stitch_sheets(cv):
    nsheet(cv, [(10, 3), (28, 8), (24, 30), (6, 25)])
    cv.line((14, 4), (10, 28), 1.0, shade(NURBS, -0.5))


@icon("Surfaces/Stitch/Global Stitch")
def i_global_stitch(cv):
    _stitch_sheets(cv)
    stitches(cv, (16, 6), (12, 28), 5)
    cv.line((6, 4), (10, 10), 1.4, RED)


@icon("Surfaces/Stitch/Stitch Edges Tool")
def i_stitch_edges(cv):
    _stitch_sheets(cv)
    stitches(cv, (14, 8), (11, 26), 4)
    cv.polyline([(14, 8), (16, 14), (13, 20), (11, 26)], 1.4, TAN)


@icon("Surfaces/Stitch/Stitch Surface Points")
def i_stitch_points(cv):
    _stitch_sheets(cv)
    stitches(cv, (14, 8), (11, 26), 3)
    for p in ((15, 9), (13, 17), (12, 24)):
        cv_sq(cv, *p, 1.6)


@icon("Surfaces/Surface Editing/Break Tangent")
def i_break_tangent(cv):
    cv.poly([(3, 20), (14, 6), (18, 18), (7, 30)], shade(NURBS, 0.3), ol=True)
    cv.poly([(14, 6), (29, 10), (29, 22), (18, 18)], NURBS, ol=True)


@icon("Surfaces/Surface Editing/Smooth Tangent")
def i_smooth_tangent(cv):
    top = bezier((3, 20), (10, 6), (14, 4), (29, 10), 16)
    bot = [(x + 4, y + 10) for x, y in reversed(top)]
    cv.fill(cv.m_poly(top + bot), hgrad(cv, 3, 33, NURBS, 0.4, -0.3), ol=True)


def _fillet_base(cv):
    cv.poly([(2, 20), (18, 12), (30, 20), (14, 30)], NURBS, ol=True)


@icon("Surfaces/Surface Fillet/Circular Fillet")
def i_circular_fillet(cv):
    _fillet_base(cv)
    cv.fill(cv.m_ering(16, 19, 10, 4.5, 3.0), FILLET, ol=True)
    cylinder(cv, 16, 3, 17, 6.5, 2.6, NURBS)


@icon("Surfaces/Surface Fillet/Fillet Blend Tool")
def i_fillet_blend(cv):
    _fillet_base(cv)
    cv.poly([(8, 16), (18, 4), (26, 10), (22, 19)], FILLET, ol=True)
    cv.poly([(18, 4), (26, 2), (30, 8), (26, 10)], NURBS, ol=True)


@icon("Surfaces/Surface Fillet/Freeform Fillet")
def i_freeform_fillet(cv):
    _fillet_base(cv)
    cv.fill(cv.m_ellipse(17, 19, 9, 5) | cv.m_ellipse(13, 15, 6, 6), FILLET, ol=True)
    cylinder(cv, 18, 3, 14, 6, 2.6, NURBS)


# --- Skeleton ---------------------------------------------------------------------------------

CHAIN = [(18, 5), (7, 14), (14, 26)]


@icon("Skeleton/Assume Preferred Angle")
def i_assume_preferred(cv):
    chain(cv, CHAIN)
    cv.fill(cv.m_ring(13, 16, 13, 2.4) & cv.m_angle(13, 16, 300, 70), LAV, ol=True)
    cv.poly([(16, 29), (23, 24), (24, 31)], LAV, ol=True)


@icon("Skeleton/Connect Joint")
def i_connect_joint(cv):
    bone(cv, (24, 4), (14, 13), 3.0, LIGHT)
    bone(cv, (12, 15), (20, 27), 3.0, LIGHT)
    cv.poly([(12, 15), (22, 7), (18, 13)], LAV, ol=True)
    joint(cv, 12, 15, 2.8, LAV)


@icon("Skeleton/Create IK Spline Handle")
def i_ik_spline(cv):
    chain(cv, CHAIN)
    cv.fill(cv.m_ring(30, 16, 13, 2.2) & cv.m_angle(30, 16, 120, 240), LAV, ol=True)


@icon("Skeleton/Disconnect Joint")
def i_disconnect_joint(cv):
    bone(cv, (26, 4), (18, 12), 3.0, LIGHT)
    bone(cv, (9, 17), (17, 28), 3.0, LAV)


@icon("Skeleton/Insert Joints")
def i_insert_joints(cv):
    bone(cv, (16, 6), (4, 24), 4.5, LIGHT)
    plus(cv, 23, 23, s=5.5, w=3.0, col=LAV)


@icon("Skeleton/Mirror Joints")
def i_mirror_joints(cv):
    bone(cv, (10, 10), (5, 27), 4, LAV)
    bone(cv, (22, 10), (27, 27), 4, LAV)
    dashed_line(cv, (16, 1), (16, 31), 2.0, LIGHT, dash=2.5)


@icon("Skeleton/Orient Joint")
def i_orient_joint(cv):
    bone(cv, (20, 6), (5, 25), 4.5, LIGHT)
    arrow(cv, (20, 14), (28, 25), w=2.2, col=LAV, head=4.5)


@icon("Skeleton/Remove Joints")
def i_remove_joints(cv):
    chain(cv, CHAIN, r=3.0)
    minus(cv, 25, 16, s=5, w=3.0, col=LAV)


@icon("Skeleton/Reroot Skeleton")
def i_reroot(cv):
    human(cv, 16, 16, 1.0, LIGHT)
    cv.rect(13, 11, 19, 17, LAV, ol=True)


@icon("Skeleton/Set Preferred Angle")
def i_set_preferred(cv):
    chain(cv, CHAIN)
    cv.fill(cv.m_ring(13, 16, 13, 2.0) & cv.m_angle(13, 16, 300, 70) &
            ((np.degrees(np.arctan2(cv.y - 16, cv.x - 13)) % 30) < 16), LAV, ol=True)


# --- Skin -------------------------------------------------------------------------------------

@icon("Skin/Copy Skin Weights")
def i_copy_skin_weights(cv):
    page(cv, 4, 2, 20, 21, LIGHT)
    page(cv, 12, 10, 28, 30, LIGHT)
    weight_square(cv, 14, 15, 26, 28, ol=False)


def _influence(cv):
    blob(cv, 14, 14, 5, LAV)
    for k in range(3):
        y = 20 + k * 3.5
        cv.polyline(wave_pts(3, 25, y, 1.2, 1.0), 2.2, LIGHT, ol=True)
    cv.fill(cv.m_ring(14, 14, 9, 1.4) & (cv.y < 9), LIGHT)


@icon("Skin/Edit Influences/Add Influence")
def i_add_influence(cv):
    _influence(cv)
    plus(cv, 25, 6, s=5, w=2.6)


@icon("Skin/Edit Influences/Remove Influence")
def i_remove_influence(cv):
    _influence(cv)
    nosign(cv, 25, 6, r=5, w=1.8)


@icon("Skin/Edit Influences/Set Max Influences...")
def i_max_influences(cv):
    for a in (200, 240, 280, 320):
        ra = math.radians(a)
        bone(cv, (16 + 12 * math.cos(ra), 22 + 12 * math.sin(ra)), (16, 22), 2.6, LIGHT)
    cv.frame(3, 24, 8, 29, 1.2, LIGHT, ol=True)
    joint(cv, 16, 26, 2.4, LIGHT)


@icon("Skin/Export Weight Maps...")
def i_export_weights(cv):
    cv.frame(3, 5, 25, 29, 1.4, LAV, ol=True)
    weight_square(cv, 5, 7, 23, 27, ol=False)
    cv.rect(17, 2, 25, 10, LIGHT)
    arrow(cv, (19, 6), (30, 6), w=2.2, head=4)


@icon("Skin/Import Weights Maps...")
def i_import_weights(cv):
    cv.frame(3, 5, 25, 29, 1.4, LAV, ol=True)
    weight_square(cv, 5, 7, 23, 27, ol=False)
    cv.rect(17, 2, 25, 10, LIGHT)
    arrow(cv, (30, 6), (20, 6), w=2.2, head=4)


@icon("Skin/Go to Bind Pose")
def i_bind_pose(cv):
    human(cv, 16, 17, 1.05, LAV)
    human(cv, 16, 17, 0.75, (0.27, 0.27, 0.27), ol=False)


@icon("Skin/Interactive Bind Skin", "Skin/Interactive Bind Skin Tool")
def i_interactive_bind(cv):
    capsule(cv, (7, 9), (17, 23), 6)
    cv.fill(cv.m_ering(12, 16, 7, 3, 1.2, rot=-55), LAV)
    axes3(cv, 21, 14, 8)


@icon("Skin/Move Skinned Joints")
def i_move_skinned_joints(cv):
    capsule(cv, (8, 12), (16, 24), 6, LIGHT)
    bone(cv, (8, 12), (15, 22), 2.8, LAV)
    axes3(cv, 21, 12, 8)


@icon("Skin/Smooth Skin Weights")
def i_smooth_skin_weights(cv):
    weight_square(cv, 3, 3, 18, 18)
    weight_square(cv, 12, 12, 29, 29)


@icon("Skin/Substitute Geometry")
def i_substitute_geometry(cv):
    human(cv, 8, 12, 0.55, LIGHT)
    cv.fill(cv.m_ring(20, 13, 6, 2.0) & (cv.y <= 13), LIGHT, ol=True)
    cv.poly([(23, 12), (29, 12), (26, 16)], LIGHT, ol=True)
    shirt(cv, 22, 25, 0.55, LIGHT, ol=True)


@icon("Skin/Unbind Skin")
def i_unbind_skin(cv):
    cv.polyline([(16, 4), (5, 16), (16, 28)], 5.0, LAV, ol=True)
    cv.polyline([(16, 4), (5, 16), (16, 28)], 2.2, (0.27, 0.27, 0.27))
    bone(cv, (26, 8), (17, 17), 2.6, LIGHT)
    bone(cv, (17, 17), (23, 25), 2.4, LIGHT)
