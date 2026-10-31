# SPDX-License-Identifier: GPL-3.0-or-later
"""Kit-drawn pictures for Maya menu items that have no shelf button (issue #54).

A Maya menu item gets the kit drawing of the shelf button / Status Line / Tool Box glyph of the same command
(``menu_icon_data``). Maya 2022 also draws an icon on many items that are on no shelf (Deform deformers, Mesh Display,
Effects, Fields, Edit Mesh / Mesh Tools tools ...). This module draws those, from scratch, in the shelf's vocabulary
(``shelf_icons``: one hue per kind, dark outline, light from the upper left, tool parts light grey, the action mark
small in a corner) and following each Maya icon's subject, colour and composition as described by looking at it
(no Maya pixels, no traced coordinates).

``@icon(path, ...)`` registers a drawing under its first Maya menu path (the picture's name); further paths are
items Maya shows with the same picture. ``tools/gen_menu_icons.py`` reads the decorators (ast) and writes
``("menu", name)`` pictures into ``menu_icon_data.ICONS``. Pure numpy, no bpy at import.
"""

import math

import numpy as np

from .shelf_icons import (BLUE, DARK, LAV, LIGHT, WHITE, YELLOW, Canvas, _hex, arrow, bezier, bone, brush, checker,
                          cube, curved_arrow, cylinder, face_grid, film_strip, hgrad, lerp, plus, shade, sphere_colour,
                          wave_pts, xmark)

RED = _hex("#c8323a")         # Maya's action red (arrows, paint ring, prune cursor)
PURPLE = _hex("#a548c8")      # intermediate-object balls
TAN = _hex("#b8a46c")         # wires, tan balls
FGREEN = _hex("#3fa046")      # field arrows / turbulence green
VCOL = (_hex("#e0705a"), _hex("#d8c83c"), _hex("#4a9ad8"), _hex("#4ab45a"))    # colour-set vertex squares

DRAWINGS = {}       # name (first path) -> fn(cv)
PATHS = {}          # Maya menu path -> name


def icon(*paths):
    def deco(fn):
        DRAWINGS[paths[0]] = fn
        for p in paths:
            PATHS[p] = paths[0]
        return fn
    return deco


def draw(name, size=32):
    """``size`` x ``size`` RGBA float32 (straight alpha, top row first) of drawing ``name``."""
    cv = Canvas(size)
    DRAWINGS[name](cv)
    return cv.result()


# --- shared parts -----------------------------------------------------------------------------

def blob(cv, cx, cy, r, col=BLUE, alpha=1.0):
    """A lit ball (Maya's deformer / particle sphere)."""
    cv.fill(cv.m_circle(cx, cy, r), sphere_colour(cv, cx, cy, r, col, amb=0.7, dif=0.5, spec=0.5, power=12), alpha)


def ghost_balls(cv, p0, p1, r, n=3, col=BLUE):
    """A ball moving from ``p0`` to ``p1`` with fading copies behind it (jiggle, passive bodies)."""
    for i in range(n):
        t = i / (n - 1)
        blob(cv, *lerp(p0, p1, t), r, col, alpha=0.25 + 0.75 * t ** 2)


def paint_mark(cv, cx=21, cy=24):
    """Maya's paint tool mark: a brush dipping into a red ring (lower right)."""
    cv.fill(cv.m_ering(cx, cy, 8.5, 4.2, 2.0), RED, ol=True)
    brush(cv, (cx - 2, cy + 1), (cx + 9, cy - 13), w=2.6, col=_hex("#8a5a3a"), bristle=_hex("#e8e0c8"))


def prune_mark(cv, x=19, y=17):
    """Maya's prune / pick mark: a red pointer at the lower right."""
    pts = [(0, 0), (0, 12), (3, 9.5), (5.5, 14), (7.5, 13), (5.5, 8.5), (9.5, 8.5)]
    cv.poly([(x + a, y + b) for a, b in pts], RED, ol=True)


def sheet(cv, pts, col=BLUE):
    """A curved surface sheet given as top edge points (left to right) dropped by ``h``."""
    cv.poly(pts, col, ol=True)


def wire_sheet(cv, dx=0, dy=0):
    """Maya's wire deformer subject: a curled blue sheet with a tan wire across it."""
    top = bezier((4 + dx, 12 + dy), (10 + dx, 6 + dy), (18 + dx, 14 + dy), (27 + dx, 7 + dy), 16)
    bot = bezier((24 + dx, 25 + dy), (16 + dx, 30 + dy), (9 + dx, 22 + dy), (2 + dx, 27 + dy), 16)
    cv.fill(cv.m_poly(top + bot), hgrad(cv, 2 + dx, 27 + dx, BLUE, 0.25, -0.3))
    cv.line((1 + dx, 14 + dy), (30 + dx, 10 + dy), 1.8, TAN, ol=True)


def cylinder_pair(cv, x, col=BLUE):
    cylinder(cv, x, 3, 12, 4, 1.8, col)
    cylinder(cv, x, 19, 28, 4, 1.8, col)


def cluster_balls(cv, dx=0, dy=0, r=5.0):
    for x, y in ((14, 5), (8, 13), (17, 14)):
        blob(cv, x + dx, y + dy, r)


def lattice_cage(cv, col=BLUE, x0=3, y0=3, s=1.0):
    f = [(x0, y0 + 9 * s), (x0 + 17 * s, y0 + 9 * s), (x0 + 17 * s, y0 + 26 * s), (x0, y0 + 26 * s)]
    b = [(x0 + 8 * s, y0), (x0 + 25 * s, y0), (x0 + 25 * s, y0 + 17 * s), (x0 + 8 * s, y0 + 17 * s)]
    for q in (b, f):
        face_grid(cv, q, 2, col, w=1.0)
    for p, q in zip(f, b):
        cv.line(p, q, 1.0, col)


def sculpt_box(cv, dx=0, dy=0):
    cube(cv, 14 + dx, 9 + dy, 11, 12, BLUE)
    blob(cv, 17 + dx, 18 + dy, 4.5, shade(BLUE, -0.15))


def shrink_wrap(cv, dx=0, dy=0, r=8.5):
    cv.poly([(5 + dx, 14 + dy), (20 + dx, 6 + dy), (30 + dx, 22 + dy), (14 + dx, 30 + dy)], shade(BLUE, -0.05), ol=True)
    blob(cv, 15 + dx, 13 + dy, r)


def membership_balls(cv):
    blob(cv, 9, 14, 5, TAN)
    cylinder(cv, 19, 3, 13, 4.5, 2, BLUE)
    blob(cv, 17, 19, 4.5, PURPLE)


def jiggle_ball(cv, dx=0, dy=0):
    ghost_balls(cv, (24 + dx, 6 + dy), (12 + dx, 15 + dy), 6.5)


def soft_plane(cv):
    q = [(16, 15), (29, 22), (16, 29), (3, 22)]
    cv.poly(q, _hex("#5aaed4"))
    face_grid(cv, q, 2, DARK)
    for p in ((9.5, 22), (22.5, 22), (16, 25.5)):
        cv.rect(p[0] - 1.5, p[1] - 1.5, p[0] + 1.5, p[1] + 1.5, LIGHT, ol=True)
    cv.line((16, 20), (16, 9), 1.6, LIGHT, ol=True)
    arrow(cv, (16, 12), (16, 2), w=2.2, head=4)


# --- Deform -----------------------------------------------------------------------------------

@icon("Deform/Display Intermediate Objects")
def i_display_intermediate(cv):
    cylinder_pair(cv, 7)
    cylinder_pair(cv, 25)
    blob(cv, 7, 15.5, 3.2, PURPLE)
    blob(cv, 25, 15.5, 3.2, PURPLE)
    cv.line((11, 15.5), (21, 15.5), 1.6, RED, cap=False)
    for x, s in ((11, 1), (21, -1)):
        cv.poly([(x, 15.5), (x + 3 * s, 13), (x + 3 * s, 18)], RED)


@icon("Deform/Hide Intermediate Objects")
def i_hide_intermediate(cv):
    cylinder_pair(cv, 7)
    cylinder_pair(cv, 25)
    xmark(cv, 16, 15.5, s=4.0, w=2.4, col=RED)


@icon("Deform/Edit Membership Tool")
def i_edit_membership(cv):
    cv.ring(15, 14, 12.5, 2.0, LIGHT, ol=True)
    membership_balls(cv)
    arrow(cv, (23, 23), (30, 30), w=2.2, col=RED, head=4.5)


@icon("Deform/Jiggle/Jiggle Deformer")
def i_jiggle(cv):
    ghost_balls(cv, (25, 7), (10, 22), 7.5)


@icon("Deform/Jiggle/Jiggle Disk Cache")
def i_jiggle_cache(cv):
    jiggle_ball(cv, -4, -2)
    film_strip(cv, 11, 18, 31, 30, _hex("#e8e8e8"), cells=3, cell_col=_hex("#7cc8ec"))


@icon("Deform/Jiggle/Jiggle Disk Cache Attributes")
def i_jiggle_cache_attr(cv):
    jiggle_ball(cv, -6, 0)
    film_strip(cv, 11, 20, 31, 31, _hex("#e8e8e8"), cells=2, cell_col=_hex("#7cc8ec"))
    cv.rect(20, 1, 31, 15, LIGHT, ol=True)
    for i, y in enumerate((4.5, 8, 11.5)):
        cv.line((22, y), (29, y), 1.0, DARK, cap=False)
        cv.rect(23 + 2.5 * i - 1, y - 1.5, 23 + 2.5 * i + 1, y + 1.5, DARK)


@icon("Deform/Mirror Deformer Weights", "Skin/Mirror Skin Weights")
def i_mirror_weights(cv):
    cv.rect(3, 4, 29, 28, LAV, ol=True)
    for side in (-1, 1):
        x0, x1 = (5, 15) if side < 0 else (17, 27)
        t = np.clip(np.abs(cv.x - 16) / 11, 0, 1)
        g = np.stack([shade(LAV, -0.7)[i] + (shade(LAV, 0.3)[i] - shade(LAV, -0.7)[i]) * t for i in range(3)], -1)
        cv.fill(cv.m_rect(x0, 6, x1, 26), g)
    for y in range(2, 30, 4):
        cv.rect(15.5, y, 16.5, y + 2, WHITE)


@icon("Deform/Nonlinear/Bend")
def i_nl_bend(cv):
    pts = bezier((9, 30), (9, 14), (14, 8), (24, 7), 24)
    cv.polyline(pts, 6.0, LAV, ol=True)
    cv.polyline(pts, 2.0, shade(LAV, 0.4))
    curved_arrow(cv, 26, 22, 11, 190, 265, w=2.4, head=4.5)


@icon("Deform/Nonlinear/Flare")
def i_nl_flare(cv):
    cv.poly([(12, 9), (20, 9), (28, 29), (4, 29)], BLUE)
    cv.fill(cv.m_poly([(16, 9), (20, 9), (28, 29), (16, 29)]), shade(BLUE, -0.25))
    cv.poly([(12, 9), (20, 9), (19, 7), (13, 7)], shade(BLUE, 0.5))
    arrow(cv, (9, 18), (3, 4), w=2.0, col=RED, head=4)
    arrow(cv, (23, 18), (29, 4), w=2.0, col=RED, head=4)


@icon("Deform/Nonlinear/Sine")
def i_nl_sine(cv):
    q = [(16, 13), (30, 20), (16, 27), (2, 20)]
    cv.poly(q, BLUE, ol=True)
    cv.poly([(2, 20), (16, 27), (16, 30), (2, 23)], shade(BLUE, -0.2))
    cv.poly([(16, 27), (30, 20), (30, 23), (16, 30)], shade(BLUE, -0.4))
    for rx in (4, 8, 11.5):
        cv.fill(cv.m_ering(16, 20, rx, rx * 0.5, 1.0) & cv.m_poly(q), shade(BLUE, 0.4))
    cv.line((16, 2), (16, 20), 1.6, PURPLE)


@icon("Deform/Nonlinear/Squash")
def i_nl_squash(cv):
    cube(cv, 16, 18, 12, 6, BLUE)
    cv.line((16, 2), (16, 9), 1.8, RED, cap=False)
    cv.poly([(16, 15), (12.5, 9), (19.5, 9)], RED)


@icon("Deform/Nonlinear/Twist")
def i_nl_twist(cv):
    cv.poly([(8, 6), (22, 3), (24, 14), (10, 17)], shade(BLUE, 0.3), ol=True)
    cv.poly([(10, 17), (24, 14), (27, 21), (13, 25)], BLUE, ol=True)
    cv.poly([(4, 10), (8, 6), (10, 17), (6, 20)], shade(BLUE, -0.3), ol=True)
    curved_arrow(cv, 16, 21, 9, 20, 160, w=2.2, col=RED, head=4)


@icon("Deform/Nonlinear/Wave")
def i_nl_wave(cv):
    top = wave_pts(5, 27, 12, 2.5, 1.0)
    cv.fill(cv.m_poly(top + [(27, 29), (5, 29)]), hgrad(cv, 5, 27, BLUE, 0.3, -0.3))
    cv.polyline(top, 1.0, shade(BLUE, 0.6))
    cv.polyline(wave_pts(8, 26, 5, 2.0, 1.0, math.pi), 1.8, RED, ol=True)
    cv.poly([(29, 2), (24, 2), (27, 7)], RED, ol=True)


@icon("Deform/Paint Weights/Blend Shape")
def i_pw_blend(cv):
    blob(cv, 11, 8, 5.5)
    blob(cv, 6, 17, 4.5)
    paint_mark(cv)


@icon("Deform/Paint Weights/Cluster")
def i_pw_cluster(cv):
    cluster_balls(cv, -3, -1, 4.6)
    paint_mark(cv)


@icon("Deform/Paint Weights/Jiggle")
def i_pw_jiggle(cv):
    ghost_balls(cv, (20, 4), (9, 12), 6)
    paint_mark(cv)


@icon("Deform/Paint Membership")
def i_pw_membership(cv):
    blob(cv, 6, 10, 4, TAN)
    cylinder(cv, 14, 2, 10, 3.5, 1.5, BLUE)
    blob(cv, 12, 15, 3.5, PURPLE)
    cv.rect(2, 1, 5, 4, YELLOW, ol=True)
    paint_mark(cv)


@icon("Deform/Paint Weights/ShrinkWrap")
def i_pw_shrinkwrap(cv):
    cv.poly([(2, 10), (14, 3), (22, 14), (9, 21)], shade(BLUE, -0.05), ol=True)
    blob(cv, 11, 9, 6.5)
    paint_mark(cv)


@icon("Deform/Paint Weights/Texture Deformer")
def i_pw_texture(cv):
    for i, (x, y) in enumerate(((3, 14), (9, 19), (14, 13), (7, 9))):
        cv.poly([(x, y), (x + 7, y - 3), (x + 10, y + 2), (x + 3, y + 5)], shade(LAV, -0.1 * i), ol=True)
    cv.line((14, 14), (26, 3), 2.6, LIGHT, ol=True)
    cv.poly([(10, 13), (16, 10), (18, 16), (12, 19)], LIGHT, ol=True)
    checker(cv, 21, 21, s=9, n=3)


@icon("Deform/Paint Weights/Wire")
def i_pw_wire(cv):
    top = bezier((2, 9), (7, 4), (12, 10), (19, 5), 12)
    bot = bezier((17, 19), (11, 22), (7, 16), (1, 19), 12)
    cv.fill(cv.m_poly(top + bot), hgrad(cv, 1, 19, BLUE, 0.25, -0.3))
    cv.line((0, 10), (22, 7), 1.6, TAN, ol=True)
    paint_mark(cv)


@icon("Deform/Point On Curve")
def i_point_on_curve(cv):
    pts = bezier((3, 22), (8, 10), (12, 30), (29, 18), 30)
    cv.polyline(pts, 2.0, _hex("#7ab4e0"), ol=True)
    cv.rect(10, 18, 14.5, 22.5, YELLOW, ol=True)
    for a in (0, 60, 120):
        ra = math.radians(a)
        cv.line((24 - 5 * math.cos(ra), 9 - 5 * math.sin(ra)), (24 + 5 * math.cos(ra), 9 + 5 * math.sin(ra)), 2.0,
                FGREEN, ol=True)


@icon("Deform/Pose Space Deformation/Create Pose Interpolator")
def i_pose_interpolator(cv):
    bone(cv, (8, 9), (16, 22), 4.2)
    bone(cv, (16, 22), (11, 30), 3.0)
    cv.line((16, 22), (26, 22), 1.6, LAV)
    plus(cv, 23, 8, s=5, w=2.6)


@icon("Deform/Prune Membership/Cluster")
def i_prune_cluster(cv):
    cluster_balls(cv, -2, 0, 5.5)
    prune_mark(cv)


@icon("Deform/Prune Membership/Lattice")
def i_prune_lattice(cv):
    lattice_cage(cv, _hex("#7ab4e0"), 2, 2, 0.95)
    prune_mark(cv)


@icon("Deform/Prune Membership/Sculpt")
def i_prune_sculpt(cv):
    sculpt_box(cv, -2, 0)
    prune_mark(cv)


@icon("Deform/Prune Membership/Wire")
def i_prune_wire(cv):
    wire_sheet(cv, -2, -3)
    prune_mark(cv)


@icon("Deform/Sculpt")
def i_sculpt_deformer(cv):
    sculpt_box(cv, 2, -1)
    cv.fill(cv.m_ering(16, 22, 14, 5, 2.0) & ~cv.m_rect(5, 10, 28, 22), FGREEN, ol=True)


@icon("Deform/ShrinkWrap")
def i_shrinkwrap(cv):
    shrink_wrap(cv, -1, -1, 9.5)


@icon("Deform/Soft Modification Tool", "Modify/Transformation Tools/Soft Modification Tool")
def i_soft_mod(cv):
    soft_plane(cv)


@icon("Deform/Texture")
def i_texture_deformer(cv):
    cube(cv, 18, 13, 11, 12, BLUE)
    for y in (15, 19, 23):
        cv.polyline(wave_pts(8, 28, y, 1.2, 2.0), 1.0, shade(BLUE, 0.5))
    checker(cv, 3, 3, s=10, n=2)


@icon("Deform/Wire")
def i_wire(cv):
    wire_sheet(cv)


@icon("Deform/Wrap")
def i_wrap(cv):
    cylinder(cv, 16, 7, 25, 10, 4, _hex("#7ab4e0"), wire=5, edge=shade(BLUE, -0.4))
    curved_arrow(cv, 16, 12, 13, 340, 520, w=2.0, col=RED, head=4)


@icon("Deform/Wrinkle")
def i_wrinkle(cv):
    cv.poly([(8, 4), (29, 8), (24, 29), (3, 25)], shade(BLUE, -0.2))
    for i in range(5):
        t = i / 5
        a, b = lerp((8, 4), (3, 25), t + 0.05), lerp((29, 8), (24, 29), t + 0.05)
        cv.line(a, b, 2.2, shade(BLUE, 0.35))
    cv.polyline([(8, 4), (29, 8), (24, 29), (3, 25), (8, 4)], 1.6, RED, ol=True)


# The other menus' drawings live in sibling modules that register through ``icon`` above.
from . import (menu_drawings_mesh, menu_drawings_fx, menu_drawings_select, menu_drawings_build,  # noqa: E402,F401
               menu_drawings_misc)
