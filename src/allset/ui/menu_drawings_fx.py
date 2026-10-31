# SPDX-License-Identifier: GPL-3.0-or-later
"""Kit menu pictures for Effects, Fields / Solvers, Fluids, nParticles, nConstraint, nHair, nCache and Cache (
#54) — see ``menu_drawings``."""

import math

import numpy as np

from .menu_drawings import FGREEN, RED, TAN, blob, ghost_balls, icon, paint_mark, prune_mark
from .menu_drawings_mesh import cursor_white, dashed_line, padlock
from .shelf_icons import (BLUE, DARK, LIGHT, SALMON, WHITE, _hex, arrow, bezier, brush, cube, face_grid, hgrad, lerp,
                          plus, shade, shirt, sphere_colour, wave_pts)

CELL = _hex("#8fd2f2")        # Maya geometry cache frames
STRIP = _hex("#e6e6e6")
FILM = (0.13, 0.13, 0.13)
SEA = _hex("#2f6db0")
SEA_LIGHT = _hex("#7cc0ea")
PURPLE_DISC = _hex("#8a4cc8")
RDISC = _hex("#c83a3a")
GDISC = _hex("#3aa04a")
HAIR = _hex("#a87440")


# --- shared parts -----------------------------------------------------------------------------

def letter_ball(cv, cx, cy, r, ch, col=BLUE):
    """Maya's field / solver ball: a lit ball with a white letter."""
    blob(cv, cx, cy, r, col)
    cv.text(ch, WHITE, cx - 2.5, cy - 3.5, ol=True, bold=True)


def green_arrow(cv, p0, p1, w=2.0, head=4.5):
    arrow(cv, p0, p1, w=w, col=FGREEN, head=head)


def pin(cv, cx, cy, s=1.0):
    """A bowling pin (Maya's rigid body pictures)."""
    m = cv.m_ellipse(cx, cy + 7 * s, 4.2 * s, 7 * s) | cv.m_ellipse(cx, cy - 4 * s, 2.4 * s, 4 * s) | \
        cv.m_rect(cx - 1.6 * s, cy - 2 * s, cx + 1.6 * s, cy + 2 * s)
    cv.fill(m, hgrad(cv, cx - 4 * s, cx + 4 * s, WHITE, 0.1, -0.35), ol=True)
    cv.fill(cv.m_rect(cx - 2.6 * s, cy - 1 * s, cx + 2.6 * s, cy + 0.2 * s) & m, RED)
    cv.fill(cv.m_rect(cx - 3 * s, cy + 1.2 * s, cx + 3 * s, cy + 2.2 * s) & m, RED)


def bang(cv, cx, cy, h=10.0, col=RED):
    """An exclamation mark."""
    cv.poly([(cx - 1.8, cy - h / 2), (cx + 1.8, cy - h / 2), (cx + 0.9, cy + h / 2 - 3.5), (cx - 0.9, cy + h / 2 - 3.5)],
            col, ol=True)
    cv.circle(cx, cy + h / 2 - 0.8, 1.4, col, ol=True)


def trash(cv, x, y, s=1.0):
    """A dark trash can (delete)."""
    cv.rect(x - 0.5 * s, y, x + 9.5 * s, y + 2 * s, (0.3, 0.3, 0.3), ol=True)
    cv.rect(x + 3 * s, y - 1.5 * s, x + 6 * s, y, (0.3, 0.3, 0.3))
    cv.poly([(x, y + 2 * s), (x + 9 * s, y + 2 * s), (x + 8 * s, y + 12 * s), (x + 1 * s, y + 12 * s)], (0.25, 0.25, 0.25),
            ol=True)
    for k in (2.8, 4.5, 6.2):
        cv.line((x + k * s, y + 4 * s), (x + k * s, y + 10 * s), 0.8, (0.55, 0.55, 0.55), cap=False)


def example_box(cv, body):
    """Maya's Get Example: a grey server tower beside a light panel showing the content."""
    cv.rect(2, 4, 11, 28, LIGHT, ol=True)
    cv.rect(2, 4, 11, 7, shade(LIGHT, -0.3))
    for y in (10, 13):
        cv.rect(4, y, 9, y + 1, DARK)
    cv.rect(12, 7, 30, 28, WHITE, ol=True)
    body(13, 8, 29, 27)


def gstrip(cv, x0, y0, x1, y1, cells=3, cell=CELL, col=FILM, frames=None):
    """Maya's cache: a dark film strip with light sprocket holes and big frames; ``frames`` = per-cell colours."""
    cv.rect(x0, y0, x1, y1, col, ol=True)
    for i in range(int((x1 - x0 - 1) // 3)):
        x = x0 + 1.5 + i * 3
        cv.rect(x, y0 + 0.8, x + 1.2, y0 + 1.8, STRIP)
        cv.rect(x, y1 - 1.8, x + 1.2, y1 - 0.8, STRIP)
    cw = (x1 - x0 - 1) / cells
    for i in range(cells):
        c = frames[i] if frames else cell
        cv.rect(x0 + 1 + i * cw, y0 + 2.6, x0 + (i + 1) * cw, y1 - 2.6, c)


def floppy(cv, x, y, s=1.0):
    cv.rect(x, y, x + 10 * s, y + 10 * s, (0.3, 0.3, 0.3), ol=True)
    cv.rect(x + 2 * s, y, x + 8 * s, y + 3.5 * s, LIGHT)
    cv.rect(x + 2 * s, y + 6 * s, x + 8 * s, y + 10 * s, WHITE)


def red_plus(cv, cx, cy, s=3.5):
    plus(cv, cx, cy, s=s, w=2.0, col=WHITE)
    cv.fill(cv.m_line((cx - s + 0.8, cy), (cx + s - 0.8, cy), 1.0, cap=False) |
            cv.m_line((cx, cy - s + 0.8), (cx, cy + s - 0.8), 1.0, cap=False), RED)


def red_arrow_bend(cv, p0, p1, p2):
    """A red elbow arrow p0 -> p1 -> p2 (Maya's export / import / attach)."""
    cv.line(p0, p1, 1.6, RED, cap=False)
    arrow(cv, p1, p2, w=1.6, col=RED, head=3.5, ol=False)


def ocean_disc(cv, cx=16, cy=16, r=13):
    cv.fill(cv.m_circle(cx, cy, r), sphere_colour(cv, cx, cy, r, SEA_LIGHT, amb=0.8, dif=0.4), ol=True)
    m = cv.m_circle(cx, cy, r) & (cv.y > cy - 1)
    cv.fill(m, SEA)
    for k, y in enumerate((cy + 1, cy + 5)):
        cv.fill(cv.m_polyline(wave_pts(cx - r, cx + r, y, 1.2, 2.0, k), 1.2) & cv.m_circle(cx, cy, r - 0.5), WHITE)


def cloud(cv, cx, cy, s=1.0, col=WHITE):
    m = cv.m_circle(cx - 4 * s, cy + 1 * s, 4 * s) | cv.m_circle(cx + 1 * s, cy - 2 * s, 5 * s) | \
        cv.m_circle(cx + 5.5 * s, cy + 1.5 * s, 3.5 * s) | cv.m_rect(cx - 4 * s, cy + 1 * s, cx + 5.5 * s, cy + 5 * s)
    cv.fill(m, col, ol=True)


def tile_plane(cv, cx, cy, s=1.0, col=WHITE):
    """Maya's nCloth patch: a grey-white 2 x 2 tile diamond with dark seams."""
    q = [(cx, cy - 6 * s), (cx + 10 * s, cy), (cx, cy + 6 * s), (cx - 10 * s, cy)]
    cv.poly(q, col, ol=True)
    face_grid(cv, q, 2, (0.35, 0.35, 0.35), w=1.0)
    return q


def nc_mark(cv, cx, cy, r=8.0):
    """Maya's dynamic constraint: a grey ring with a red exclamation mark."""
    cv.ring(cx, cy, r, 1.8, LIGHT, ol=True)
    bang(cv, cx, cy - 1, r * 1.5)


def red_dots(cv, pts):
    for x, y in pts:
        cv.rect(x - 1, y - 1, x + 1, y + 1, RED)


def disc(cv, cx, cy, r, ch, col):
    """Hair state disc: a coloured lit ball with a white letter (C / S / R)."""
    cv.fill(cv.m_circle(cx, cy, r), sphere_colour(cv, cx, cy, r, col, amb=0.75, dif=0.45, spec=0.5, power=12), ol=True)
    cv.text(ch, WHITE, cx - 2.5, cy - 3.5, ol=True, bold=True)


def strands(cv, x0, y0, n=3, col=HAIR, h=22, lean=10, gap=3.0, w=1.6):
    for i in range(n):
        x = x0 + i * gap
        cv.polyline(bezier((x, y0), (x + lean * 0.2, y0 - h * 0.5), (x + lean * 0.5, y0 - h * 0.9), (x + lean, y0 - h), 20),
                    w, shade(col, 0.15 * (i % 2)), ol=True)


def hair_curve(cv, pts, w=2.2, col=_hex("#4aa8d8")):
    cv.polyline(pts, w, col, ol=True)


def particle_box(cv, balls):
    cv.rect(3, 3, 29, 29, (0.27, 0.27, 0.27), ol=True)
    cv.fill(cv.m_rect(4, 4, 28, 28), hgrad(cv, 4, 28, (0.5, 0.5, 0.5), 0.1, -0.4))
    balls()


# --- Effects ----------------------------------------------------------------------------------

@icon("Effects/Fire")
def i_fire(cv):
    m = cv.m_ellipse(16, 13, 8, 6) | cv.m_poly([(8.5, 12), (15, 1), (23.5, 12)]) | \
        cv.m_poly([(9, 13), (5, 4), (13, 9)]) | cv.m_poly([(23, 13), (27, 5), (19, 9)])
    cv.fill(m, hgrad(cv, 6, 26, _hex("#e8901e"), 0.3, -0.3), ol=True)
    cv.fill(cv.m_ellipse(16, 14, 4, 3.5) | cv.m_poly([(12.5, 13), (16, 6), (19.5, 13)]), _hex("#f6d040"))
    blob(cv, 16, 22, 7)


@icon("Effects/Fireworks")
def i_fireworks(cv):
    for (cx, cy, r, col) in ((12, 14, 7, _hex("#d040d8")), (23, 8, 6, _hex("#e0602a")), (11, 5, 4, _hex("#40c8e8"))):
        for k in range(10):
            a = 2 * math.pi * k / 10
            cv.line((cx, cy), (cx + r * math.cos(a), cy + r * math.sin(a)), 1.2, col)
    blob(cv, 20, 23, 7)


@icon("Effects/Flow/Create Curve Flow")
def i_curve_flow(cv):
    pts = bezier((3, 27), (14, 26), (6, 6), (28, 4), 30)
    cv.polyline(pts, 2.0, _hex("#5a8ac8"), ol=True)
    for t, r in ((0.05, 2.6), (0.25, 2.2), (0.45, 2.4), (0.6, 2.0), (0.8, 2.2), (0.95, 1.8)):
        x, y = pts[int(t * 29)]
        cv.circle(x + 3, y - 2, r, FGREEN, ol=True)


def _flow_sheet(cv):
    q = [(4, 26), (12, 4), (28, 6), (22, 28)]
    cv.fill(cv.m_poly(q), hgrad(cv, 4, 28, BLUE, 0.35, -0.2), ol=True)


@icon("Effects/Flow/Create Surface Flow")
def i_surface_flow(cv):
    _flow_sheet(cv)
    for x, y in ((12, 22), (15, 16), (18, 10), (20, 19), (23, 13)):
        cv.circle(x, y, 2.2, FGREEN, ol=True)


@icon("Effects/Flow/Delete Selected Flow")
def i_delete_flow(cv):
    _flow_sheet(cv)
    for x, y in ((10, 20), (13, 14), (16, 9)):
        cv.circle(x, y, 2.0, LIGHT, ol=True)
    trash(cv, 19, 17)


@icon("Effects/Get Effects Asset...", "nParticles/Get nParticle Example...")
def i_get_effects(cv):
    def body(x0, y0, x1, y1):
        for x, y in ((15, 11), (20, 14), (25, 11), (16, 19), (24, 21), (19, 24)):
            cv.circle(x, y, 2.2, FGREEN, ol=True)
    example_box(cv, body)


@icon("Effects/Lightning")
def i_lightning(cv):
    for pts in (((14, 2), (11, 9), (16, 12), (12, 20)), ((20, 3), (23, 9), (19, 13), (24, 18)), ((4, 14), (9, 17), (6, 22))):
        cv.polyline(list(pts), 1.6, _hex("#56b4f0"), ol=True)
    blob(cv, 16, 23, 7)


@icon("Effects/Shatter")
def i_shatter(cv):
    q = [(16, 7), (30, 16), (16, 25), (2, 16)]
    cv.poly(q, BLUE, ol=True)
    for a, b in (((9, 12), (17, 17)), ((17, 17), (24, 12)), ((17, 17), (14, 22)), ((12, 9), (9, 12)), ((17, 17), (23, 20))):
        cv.line(a, b, 1.4, shade(BLUE, -0.55))


@icon("Effects/Smoke")
def i_smoke(cv):
    for k, (cx, cy, r) in enumerate(((12, 9, 7), (20, 7, 6), (17, 14, 7))):
        cv.circle(cx, cy, r, shade(LIGHT, -0.1 * k), alpha=0.7)
    blob(cv, 16, 23, 7)


# --- Fields / Solvers -------------------------------------------------------------------------

@icon("Fields/Solvers/Air")
def i_air(cv):
    for k in range(3):
        a = 2 * math.pi * k / 3 - math.pi / 2
        cx, cy = 16 + 7 * math.cos(a), 16 + 7 * math.sin(a)
        cv.fill(cv.m_ellipse(cx, cy, 8, 4.5, math.degrees(a) + 30), hgrad(cv, 4, 28, FGREEN, 0.3, -0.3), ol=True)
    cv.circle(16, 16, 2.2, shade(FGREEN, -0.3), ol=True)


@icon("Fields/Solvers/Assign to Selected")
def i_assign_field(cv):
    letter_ball(cv, 10, 10, 7.5, "F")
    green_arrow(cv, (18, 10), (30, 10))
    cv.ring(12, 24, 5.5, 1.8, LIGHT, ol=True)
    cv.ring(20, 24, 5.5, 1.8, LIGHT, ol=True)


@icon("Fields/Solvers/Create Active Rigid Body")
def i_active_rigid(cv):
    pin(cv, 9, 13, 1.0)
    pin(cv, 18, 11, 0.9)
    blob(cv, 23, 23, 6)


@icon("Fields/Solvers/Create Barrier Constraint", "Fields/Solvers/Create Hinge Constraint",
      "Fields/Solvers/Create Nail Constraint", "Fields/Solvers/Create Pin Constraint",
      "Fields/Solvers/Create Spring Constraint")
def i_rigid_constraint(cv):
    pin(cv, 12, 14, 1.2)
    bang(cv, 26, 10, 16)


@icon("Fields/Solvers/Create Passive Rigid Body")
def i_passive_rigid(cv):
    pin(cv, 9, 13, 1.0)
    pin(cv, 15, 13, 0.9)
    ghost_balls(cv, (13, 25), (24, 8), 5.5)


@icon("Fields/Solvers/Drag")
def i_drag(cv):
    for k in range(4):
        cv.fill(cv.m_ering(10 + k * 2.5, 18 + k * 1.2, 7 - k, 9 - k * 1.5, 1.0), FGREEN)
    letter_ball(cv, 21, 12, 8.5, "D")


@icon("Fields/Solvers/Gravity")
def i_gravity(cv):
    letter_ball(cv, 16, 8, 7, "G")
    for x, y0 in ((5, 8), (16, 16), (27, 8)):
        green_arrow(cv, (x, y0), (x, 30), w=1.8, head=4)


@icon("Fields/Solvers/Newton")
def i_newton(cv):
    letter_ball(cv, 10, 10, 8, "N")
    cv.line((17, 17), (29, 29), 1.6, FGREEN, ol=True)
    for t in (0.35, 0.8):
        x, y = lerp((17, 17), (29, 29), t)
        cv.poly([(x - 2.5, y - 2.5), (x + 3, y - 1), (x - 1, y + 3)], FGREEN, ol=True)


@icon("Fields/Solvers/Radial")
def i_radial(cv):
    for k in range(8):
        a = 2 * math.pi * k / 8
        arrow(cv, (16 + 7 * math.cos(a), 16 + 7 * math.sin(a)), (16 + 14.5 * math.cos(a), 16 + 14.5 * math.sin(a)),
              w=1.6, head=3.5)
    cv.circle(16, 16, 5.5, SALMON, ol=True)


@icon("Fields/Solvers/Turbulence")
def i_turbulence(cv):
    for x, y, ph in ((4, 6, 0), (18, 5, 1), (3, 24, 2), (19, 25, 3), (2, 15, 1.5), (24, 15, 0.5)):
        cv.polyline(wave_pts(x, x + 8, y, 1.8, 1.5, ph), 1.4, RED)
    blob(cv, 16, 16, 5.5)


@icon("Fields/Solvers/Uniform")
def i_uniform(cv):
    letter_ball(cv, 11, 16, 8.5, "F")
    green_arrow(cv, (20, 16), (31, 16), w=2.2)


@icon("Fields/Solvers/Use Selected as Source")
def i_selected_source(cv):
    letter_ball(cv, 10, 21, 8, "F")
    green_arrow(cv, (18, 21), (30, 21), w=2.0)
    cv.frame(19, 2, 29, 12, 1.4, FGREEN, ol=True)
    blob(cv, 24, 7, 3.5)
    cv.line((19, 12), (14, 15), 1.2, FGREEN)


@icon("Fields/Solvers/Volume Axis")
def i_volume_axis(cv):
    cv.fill(cv.m_ering(7, 16, 4, 10, 1.4), LIGHT)
    cv.fill(cv.m_ering(25, 16, 4, 10, 1.4), LIGHT)
    cv.line((7, 6), (25, 6), 1.2, LIGHT)
    cv.line((7, 26), (25, 26), 1.2, LIGHT)
    green_arrow(cv, (4, 16), (30, 16), w=1.8, head=4)
    for x in (12, 19):
        green_arrow(cv, (x, 16), (x, 7), w=1.6, head=3.5)
        green_arrow(cv, (x, 16), (x, 25), w=1.6, head=3.5)


@icon("Fields/Solvers/Vortex")
def i_vortex(cv):
    for k in range(3):
        a0 = k * 120
        m = cv.m_ring(16, 16, 14 - k * 0.5, 2.2) & cv.m_angle(16, 16, a0, a0 + 70)
        m |= cv.m_ring(16, 16, 9.5, 2.0) & cv.m_angle(16, 16, a0 + 60, a0 + 120)
        cv.fill(m, FGREEN, ol=True)
    blob(cv, 16, 16, 5.5)


# --- Fluids -----------------------------------------------------------------------------------

@icon("Fluids/Add Dynamic Locator/Surface")
def i_fluid_locator(cv):
    ocean_disc(cv, 17, 17, 13)
    for a in (0, 60, 120):
        ra = math.radians(a)
        cv.line((7 - 5 * math.cos(ra), 7 - 5 * math.sin(ra)), (7 + 5 * math.cos(ra), 7 + 5 * math.sin(ra)), 2.0,
                FGREEN, ol=True)


@icon("Fluids/Add Preview Plane", "Fluids/Create Wake")
def i_preview_plane(cv):
    for dy, k in ((7, -0.25), (0, 0.0)):
        q = [(4, 14 + dy), (18, 5 + dy), (29, 12 + dy), (15, 21 + dy)]
        cv.fill(cv.m_poly(q), hgrad(cv, 4, 29, shade(SEA_LIGHT, k), 0.2, -0.4), ol=True)
    for k in (0, 1):
        cv.fill(cv.m_ering(17, 13, 6 + k * 4, 3 + k * 2, 1.0) & cv.m_poly([(4, 14), (18, 5), (29, 12), (15, 21)]),
                shade(SEA_LIGHT, 0.4))


@icon("Fluids/Add/Edit Contents/Emitter")
def i_fluid_emitter(cv):
    cv.rect(2, 2, 30, 30, _hex("#3a8ad0"), ol=True)
    cv.rect(4, 4, 28, 28, _hex("#d6ecf8"))
    cloud(cv, 14, 18, 1.4, LIGHT)
    cv.ring(14, 11, 5, 1.6, DARK)
    cv.line((14, 6), (14, 16), 1.2, DARK)
    cv.line((9, 11), (19, 11), 1.2, DARK)
    cv.line((17, 15), (26, 24), 2.4, LIGHT, ol=True)


@icon("Fluids/Add/Edit Contents/Initial States...")
def i_fluid_initial(cv):
    def body(x0, y0, x1, y1):
        cv.rect(x0 + 2, y0 + 1, x1 - 2, y1 - 1, (0.2, 0.2, 0.2))
        cv.rect(x0 + 5, y0 + 4, x1 - 5, y1 - 4, SEA_LIGHT)
        cv.text("1", (0.1, 0.1, 0.1), (x0 + x1) / 2 - 2.5, (y0 + y1) / 2 - 3.5)
    example_box(cv, body)


@icon("Fluids/Add/Edit Contents/Paint Fluids Tool")
def i_paint_fluids(cv):
    cv.circle(13, 14, 11, _hex("#cfe8f6"), ol=True)
    cloud(cv, 12, 13, 1.2, WHITE)
    brush(cv, (12, 26), (29, 6), w=3.2, col=_hex("#8a5a3a"), bristle=_hex("#e8e0c8"))


@icon("Fluids/Create Boat/Make Motor Boat")
def i_motor_boat(cv):
    cv.poly([(2, 18), (24, 18), (30, 13), (26, 24), (6, 25)], WHITE, ol=True)
    cv.poly([(2, 18), (24, 18), (22, 21), (4, 21)], _hex("#3a8ad0"))
    cv.poly([(9, 18), (13, 11), (21, 11), (24, 18)], LIGHT, ol=True)
    cv.rect(14, 12.5, 20, 15.5, _hex("#3a8ad0"))
    cv.polyline(wave_pts(2, 30, 27, 1.0, 2.0), 1.4, SEA_LIGHT)


@icon("Fluids/Edit Fluid Resolution")
def i_fluid_resolution(cv):
    top, left, right = cube(cv, 16, 8, 12.5, 15, SEA_LIGHT, faces=(0.35, 0.0, -0.25))
    for q in (top, left, right):
        face_grid(cv, q, 2, WHITE, w=1.0)


@icon("Fluids/Extend Fluid")
def i_extend_fluid(cv):
    cv.rect(3, 2, 29, 30, WHITE, ol=True)
    for i in range(4):
        for j in range(5):
            cv.rect(4.5 + i * 6.2, 3.5 + j * 5.2, 9.5 + i * 6.2, 7.5 + j * 5.2,
                    shade(SEA_LIGHT, -0.3 if (i + j) % 3 == 0 else 0.0))


@icon("Fluids/Get Example.../Fluid")
def i_example_fluid(cv):
    def body(x0, y0, x1, y1):
        for y in (y0 + 2, y0 + 11):
            cv.rect(x0 + 3, y, x1 - 3, y + 7, SEA_LIGHT, ol=True)
    example_box(cv, body)


@icon("Fluids/Get Example.../Ocean/Pond")
def i_example_ocean(cv):
    ocean_disc(cv, 12, 16, 11)
    for k, col in enumerate((WHITE, _hex("#40d0e8"), SEA)):
        cv.rect(24, 3 + k * 9, 31, 10 + k * 9, col, ol=True)


@icon("Fluids/Ocean")
def i_ocean(cv):
    ocean_disc(cv, 16, 16, 14)


# --- nParticles -------------------------------------------------------------------------------

@icon("nParticles/Create Options/Balls")
def i_np_balls(cv):
    def balls():
        for (x, y, c) in ((9, 9, BLUE), (16, 8, _hex("#c84a8a")), (23, 9, BLUE), (10, 17, _hex("#c83a4a")),
                          (18, 16, BLUE), (24, 20, _hex("#c84a8a")), (11, 24, BLUE), (19, 24, BLUE)):
            blob(cv, x, y, 3.4, c)
    particle_box(cv, balls)


@icon("nParticles/Create Options/Cloud")
def i_np_cloud(cv):
    def balls():
        for x in (9, 16, 23):
            for y in (9, 16, 23):
                cv.fill(cv.m_circle(x, y, 3.6), sphere_colour(cv, x, y, 3.6, LIGHT, amb=0.6, dif=0.5), alpha=0.75)
    particle_box(cv, balls)


@icon("nParticles/Create Options/Point")
def i_np_point(cv):
    def balls():
        for x, y in ((8, 8), (15, 10), (23, 7), (11, 15), (20, 16), (8, 23), (16, 22), (24, 24)):
            cv.rect(x - 1.5, y - 1.5, x + 1.5, y + 1.5, _hex("#6aa8e0"))
    particle_box(cv, balls)


@icon("nParticles/Create Options/Thick Cloud")
def i_np_thick_cloud(cv):
    def balls():
        for x in (9, 16, 23):
            for y in (9, 16, 23):
                cv.fill(cv.m_circle(x, y, 4.2), sphere_colour(cv, x, y, 4.2, WHITE, amb=0.9, dif=0.3))
    particle_box(cv, balls)


@icon("nParticles/Create Options/Water")
def i_np_water(cv):
    def balls():
        for x in (9, 16, 23):
            for y in (9, 16, 23):
                cv.fill(cv.m_circle(x, y, 3.8), sphere_colour(cv, x, y, 3.8, _hex("#2a78d0"), amb=0.7, dif=0.5), alpha=0.7)
    particle_box(cv, balls)


@icon("nParticles/Create Springs")
def i_springs(cv):
    for k in range(5):
        y = 6 + k * 4.5
        cv.fill(cv.m_ering(16, y, 9, 2.6, 2.0) & ((cv.y > y) if k % 2 else (cv.y <= y + 3)), FGREEN, ol=True)
    cv.fill(cv.m_ellipse(13, 28, 9, 2.0), (0.2, 0.2, 0.2), alpha=0.7)


@icon("nParticles/Fill Object")
def i_fill_object(cv):
    top, left, right = cube(cv, 15, 14, 11, 11, WHITE, faces=(0.1, -0.05, -0.2))
    for x, y in ((10, 20), (14, 23), (18, 21), (12, 26), (17, 26), (21, 24)):
        cv.circle(x, y, 1.4, SALMON)
    cv.poly([(18, 2), (28, 6), (26, 12), (17, 9)], LIGHT, ol=True)


@icon("nParticles/Goal")
def i_goal(cv):
    blob(cv, 9, 7, 5)
    cv.fill(cv.m_circle(25, 18, 5), sphere_colour(cv, 25, 18, 5, (0.35, 0.35, 0.35)), ol=True)
    cv.fill(cv.m_ring(17, 24, 9, 2.4) & cv.m_angle(17, 24, 180, 300), FGREEN, ol=True)
    arrow(cv, (19, 16), (23, 15), w=2.4, col=FGREEN, head=4.5)


@icon("nParticles/Instancer")
def i_instancer(cv):
    for cx, top, bot, rx in ((10, 6, 27, 6), (22, 3, 20, 5)):
        cone_m = cv.m_poly([(cx, top), (cx + rx, bot), (cx - rx, bot)])
        cv.fill(cone_m, hgrad(cv, cx - rx, cx + rx, TAN, 0.3, -0.35), ol=True)
    blob(cv, 10, 23, 4)
    blob(cv, 22, 16, 3.5)


@icon("nParticles/Make Collide")
def i_np_collide(cv):
    ghost_balls(cv, (6, 26), (18, 17), 5.5)
    cv.polyline([(8, 10), (13, 14), (26, 4)], 2.6, FGREEN, ol=True)
    blob(cv, 24, 14, 6)


@icon("nParticles/Paint Soft Body Weights Tool")
def i_paint_soft_body(cv):
    for y in (6, 15, 24):
        cv.line((14, y), (20, y), 1.2, LIGHT)
        cv.frame(20, y - 2.5, 30, y + 2.5, 1.2, LIGHT, ol=True)
    brush(cv, (4, 27), (17, 6), w=3.2, col=LIGHT, bristle=shade(LIGHT, -0.2))


@icon("nParticles/Particle Collision Event Editor")
def i_collision_events(cv):
    arrow(cv, (6, 14), (16, 4), w=2.6, col=FGREEN, head=5)
    arrow(cv, (26, 18), (17, 28), w=2.6, col=FGREEN, head=5)
    blob(cv, 12, 20, 5)
    blob(cv, 21, 12, 5)


@icon("nParticles/Particle Tool", "nParticles/nParticle Tool")
def i_particle_tool(cv):
    for x, y, r in ((5, 6, 1.4), (11, 4, 1.2), (9, 11, 1.6), (4, 17, 1.3), (15, 9, 1.3), (6, 26, 1.6), (13, 27, 1.2)):
        cv.circle(x, y, r, SALMON)
    cv.circle(12, 19, 4.5, SALMON, ol=True)
    cv.line((17, 18), (28, 5), 3.2, LIGHT, ol=True)
    cv.poly([(13, 23), (17, 16), (20, 19)], LIGHT, ol=True)


@icon("nParticles/Per-Point Emission Rates")
def i_point_emission(cv):
    pts = bezier((6, 28), (30, 22), (2, 10), (24, 4), 30)
    cv.polyline(pts, 1.6, _hex("#7ab4e0"), ol=True)
    for i in (6, 15, 27):
        x, y = pts[i]
        cv.rect(x - 1.8, y - 1.8, x + 1.8, y + 1.8, _hex("#e8e040"), ol=True)
        for dx, dy in ((4, -3), (5, 2), (-4, -4)):
            cv.circle(x + dx, y + dy, 1.4, FGREEN)


@icon("nParticles/Soft Body")
def i_soft_body(cv):
    for k, x in enumerate((8, 12, 17)):
        cv.circle(x, 18, 8, SALMON, alpha=0.35 + 0.3 * k)
    cv.fill(cv.m_ring(23, 10, 6, 2.6) & cv.m_angle(23, 10, 180, 60), LIGHT, ol=True)


@icon("nParticles/Use Selected Emitter")
def i_selected_emitter(cv):
    for x, y in ((4, 6), (8, 9), (5, 14), (10, 16), (7, 21), (12, 4)):
        cv.circle(x, y, 1.8, FGREEN, ol=True)
    cv.ring(21, 10, 6.5, 1.4, LIGHT, ol=True)
    cv.line((21, 3), (21, 17), 1.2, LIGHT)
    cv.line((14, 10), (28, 10), 1.2, LIGHT)
    cv.ring(15, 25, 5, 1.6, LIGHT, ol=True)
    cv.ring(22, 25, 5, 1.6, LIGHT, ol=True)


# --- nConstraint ------------------------------------------------------------------------------

@icon("nConstraint/Add Members")
def i_nc_add(cv):
    nc_mark(cv, 17, 19, 10)
    red_plus(cv, 6, 6, 4)


@icon("nConstraint/Attract to Matching Mesh")
def i_nc_attract(cv):
    cv.poly([(4, 26), (24, 26), (28, 20), (8, 20)], WHITE, ol=True)
    cv.poly([(8, 12), (22, 4), (28, 6), (14, 14)], FGREEN, ol=True)
    for a, b in (((6, 25), (9, 13)), ((26, 21), (27, 7)), ((16, 24), (16, 11))):
        dashed_line(cv, a, b, 1.4, RED, dash=1.5)


@icon("nConstraint/Component", "nConstraint/Component to Component")
def i_nc_component(cv):
    tile_plane(cv, 16, 16, 1.3)
    red_dots(cv, [(10, 13), (16, 16), (22, 19), (16, 10), (22, 13)])


@icon("nConstraint/Disable Collision")
def i_nc_disable_collision(cv):
    cv.poly([(10, 8), (30, 4), (22, 14), (14, 12)], WHITE, ol=True)
    cv.poly([(14, 12), (22, 14), (26, 20), (16, 16)], LIGHT, ol=True)
    green_arrow(cv, (9, 2), (9, 16), w=2.2, head=4.5)
    blob(cv, 9, 23, 6)


@icon("nConstraint/Exclude Collide Pairs")
def i_nc_exclude(cv):
    cv.poly([(4, 8), (18, 4), (22, 12), (8, 14)], WHITE, ol=True)
    green_arrow(cv, (8, 2), (8, 16), w=2.0, head=4)
    blob(cv, 9, 23, 5.5)
    blob(cv, 20, 21, 6)
    cv.polyline([(18, 10), (22, 13), (30, 3)], 2.6, FGREEN, ol=True)


@icon("nConstraint/Force Field")
def i_nc_force_field(cv):
    cv.fill(cv.m_rect(4, 6, 28, 26), hgrad(cv, 4, 28, WHITE, 0.2, -0.45), ol=True)
    for y in (6, 22):
        tile_plane(cv, 18, y + 1, 0.7)
    arrow(cv, (8, 16), (8, 7), w=2.0, col=RED, head=3.5)
    arrow(cv, (8, 16), (8, 25), w=2.0, col=RED, head=3.5)
    green_arrow(cv, (25, 9), (25, 15), w=1.8, head=3.5)
    green_arrow(cv, (25, 23), (25, 17), w=1.8, head=3.5)


@icon("nConstraint/Point to Surface")
def i_nc_point_surface(cv):
    tile_plane(cv, 18, 10, 1.1)
    red_dots(cv, [(13, 12), (20, 15), (24, 11)])
    blob(cv, 15, 23, 7)


@icon("nConstraint/Remove Dynamic Constraint")
def i_nc_remove_constraint(cv):
    pts = shirt(cv, 14, 14, 0.95, WHITE, ol=True)
    for p in pts[8:11]:
        cv.rect(p[0] - 1.5, p[1] - 1.5, p[0] + 1.5, p[1] + 1.5, _hex("#e8e040"), ol=True)
    cv.poly([(16, 24), (26, 18), (30, 23), (20, 29)], _hex("#3a8ad0"), ol=True)
    cv.poly([(16, 24), (20, 22), (24, 27), (20, 29)], _hex("#f0e8b0"))


@icon("nConstraint/Remove Members")
def i_nc_remove(cv):
    nc_mark(cv, 13, 13, 10)
    trash(cv, 20, 18)


@icon("nConstraint/Replace Members")
def i_nc_replace(cv):
    cv.ring(11, 21, 8, 1.6, (0.5, 0.5, 0.5))
    nc_mark(cv, 21, 12, 8.5)
    cv.fill(cv.m_ring(10, 10, 6, 1.8) & cv.m_angle(10, 10, 180, 330), RED, ol=True)
    cv.poly([(3, 9), (7, 9), (5, 13)], RED, ol=True)


@icon("nConstraint/Select Members")
def i_nc_select(cv):
    nc_mark(cv, 13, 13, 10)
    prune_mark(cv, 19, 16)


@icon("nConstraint/Slide on Surface")
def i_nc_slide(cv):
    tile_plane(cv, 18, 10, 1.1)
    red_dots(cv, [(12, 13), (19, 16), (25, 12)])
    blob(cv, 16, 22, 6.5)
    cv.fill(cv.m_ering(14, 25, 9, 3.5, 1.8) & (cv.y > 25), RED, ol=True)


@icon("nConstraint/Tearable Surface")
def i_nc_tearable(cv):
    cv.poly([(6, 4), (26, 4), (29, 28), (20, 28), (16, 12), (12, 28), (3, 28)], WHITE, ol=True)
    cv.fill(cv.m_poly([(16, 4), (26, 4), (29, 28), (20, 28), (16, 12)]), shade(WHITE, -0.25))
    cv.line((16, 4), (16, 11), 1.0, (0.4, 0.4, 0.4))


@icon("nConstraint/Transform Constraint")
def i_nc_transform(cv):
    tile_plane(cv, 18, 22, 1.1)
    for p in ((10, 20), (16, 17), (23, 19)):
        cv.rect(p[0] - 1.6, p[1] - 1.6, p[0] + 1.6, p[1] + 1.6, _hex("#e8e040"), ol=True)
        dashed_line(cv, p, (16, 6), 1.2, RED, dash=1.5)
    for a in (0, 60, 120):
        ra = math.radians(a)
        cv.line((16 - 4.5 * math.cos(ra), 5 - 4.5 * math.sin(ra)), (16 + 4.5 * math.cos(ra), 5 + 4.5 * math.sin(ra)),
                1.8, FGREEN, ol=True)


@icon("nConstraint/Weld Adjacent Borders")
def i_nc_weld(cv):
    cv.poly([(4, 16), (14, 10), (20, 14), (10, 20)], FGREEN, ol=True)
    cv.poly([(10, 20), (20, 14), (28, 19), (18, 25)], WHITE, ol=True)
    dashed_line(cv, (2, 22), (30, 13), 1.6, RED, dash=2.0)


@icon("nConstraint/nConstraint Membership Tool")
def i_nc_membership(cv):
    nc_mark(cv, 11, 11, 8.5)
    nc_mark(cv, 20, 21, 9)


# --- nHair ------------------------------------------------------------------------------------

@icon("nHair/Assign Paint Effects Brush to Hair")
def i_hair_pfx_brush(cv):
    cv.polyline(bezier((4, 28), (6, 16), (14, 12), (12, 2), 20), 1.8, _hex("#2a7a3a"), ol=True)
    for x, y, a in ((7, 18, 30), (12, 10, -30), (6, 8, 40), (13, 20, -40)):
        cv.fill(cv.m_ellipse(x, y, 4, 1.8, a), _hex("#4cb04a"), ol=True)
    brush(cv, (15, 27), (30, 10), w=3.0, col=_hex("#8a5a3a"), bristle=_hex("#e8e0c8"))


@icon("nHair/Convert Selection/To Current Positions")
def i_hair_to_current(cv):
    hair_curve(cv, bezier((14, 24), (30, 30), (32, 8), (20, 12), 24))
    disc(cv, 13, 18, 9, "C", PURPLE_DISC)
    arrow(cv, (2, 2), (9, 8), w=2.2, col=RED, head=4)


@icon("nHair/Convert Selection/To Start and Rest End CVs")
def i_hair_to_end_cvs(cv):
    cv.fill(cv.m_circle(12, 19, 9.5), sphere_colour(cv, 12, 19, 9.5, RDISC, amb=0.75, dif=0.45), ol=True)
    cv.fill(cv.m_circle(12, 19, 9.5) & (cv.x > 12), sphere_colour(cv, 12, 19, 9.5, GDISC, amb=0.75, dif=0.45))
    hair_curve(cv, bezier((16, 14), (24, 6), (30, 16), (28, 26), 20), w=1.6)
    for p in ((22, 9), (28, 26), (19, 13)):
        cv.rect(p[0] - 1.6, p[1] - 1.6, p[0] + 1.6, p[1] + 1.6, WHITE, ol=True)
    arrow(cv, (2, 2), (8, 8), w=2.0, col=RED, head=3.5)


@icon("nHair/Delete Entire Hair System")
def i_hair_delete_system(cv):
    strands(cv, 3, 30, 4, h=26, lean=14, gap=3.0)
    trash(cv, 20, 17)


@icon("nHair/Delete Hair")
def i_hair_delete(cv):
    cv.rect(2, 2, 30, 30, WHITE)
    cv.polyline(bezier((4, 26), (14, 24), (12, 6), (28, 5), 24), 2.0, HAIR, ol=True)
    trash(cv, 19, 17)


@icon("nHair/Display/All Curves")
def i_hair_all_curves(cv):
    disc(cv, 9, 9, 7, "C", PURPLE_DISC)
    disc(cv, 23, 9, 7, "S", GDISC)
    disc(cv, 16, 22, 7, "R", RDISC)


@icon("nHair/Get Hair Example...")
def i_hair_example(cv):
    def body(x0, y0, x1, y1):
        for k in range(3):
            cv.polyline(bezier((x0 + 1, y0 + 4 + k * 5), (x0 + 8, y0 + 2 + k * 5), (x0 + 10, y0 + 10 + k * 5),
                               (x1, y0 + 6 + k * 5), 16), 1.4, HAIR)
    example_box(cv, body)


# Curves > ... and nHair > Modify Curves > ... are one command with one Maya picture
CURVE = _hex("#4aa8d8")


@icon("Curves/Bend", "nHair/Modify Curves/Bend")
def i_mod_bend(cv):
    cv.fill(cv.m_ring(30, 30, 25, 2.4) & (cv.x <= 30) & (cv.y <= 30), CURVE, ol=True)


@icon("Curves/Curl", "nHair/Modify Curves/Curl")
def i_mod_curl(cv):
    pts = [(6 + 18 * t + 4 * math.cos(2 * math.pi * 2.2 * t), 26 - 18 * t - 6 * math.sin(2 * math.pi * 2.2 * t))
           for t in np.linspace(0, 1, 60)]
    cv.polyline(pts, 2.2, CURVE, ol=True)


@icon("Curves/Lock Length", "nHair/Modify Curves/Lock Length")
def i_mod_lock(cv):
    cv.line((4, 23), (26, 23), 2.4, CURVE, ol=True)
    cv.rect(3, 18, 5, 28, LIGHT, ol=True)
    cv.rect(26, 18, 28, 28, LIGHT, ol=True)
    padlock(cv, 19, 1)


@icon("Curves/Unlock Length", "nHair/Modify Curves/Unlock Length")
def i_mod_unlock(cv):
    cv.line((3, 23), (29, 23), 2.4, CURVE, ol=True)
    padlock(cv, 17, 1, open_=True)


@icon("Curves/Scale Curvature", "nHair/Modify Curves/Scale Curvature")
def i_mod_scale_curvature(cv):
    cv.polyline(bezier((7, 27), (10, 2), (22, 2), (25, 27), 24), 2.4, CURVE, ol=True)
    cv.polyline([(3, 20), (3, 29), (12, 29)], 2.0, LIGHT, ol=True)
    cv.polyline([(20, 3), (29, 3), (29, 12)], 2.0, LIGHT, ol=True)


@icon("Curves/Smooth", "nHair/Modify Curves/Smooth")
def i_mod_smooth(cv):
    cv.polyline(wave_pts(3, 29, 11, 4.5, 1.0), 2.4, LIGHT, ol=True)
    cv.polyline(wave_pts(3, 29, 23, 2.0, 1.0), 2.4, CURVE, ol=True)


@icon("Curves/Straighten", "nHair/Modify Curves/Straighten")
def i_mod_straighten(cv):
    cv.polyline(wave_pts(3, 29, 11, 4.5, 1.0), 2.4, LIGHT, ol=True)
    cv.line((3, 24), (29, 24), 2.4, CURVE, ol=True)


@icon("nHair/Paint Hair Textures/Baldness")
def i_hair_baldness(cv):
    cv.fill(cv.m_ellipse(12, 13, 9, 11), sphere_colour(cv, 12, 13, 11, _hex("#e0b090"), amb=0.7, dif=0.4), ol=True)
    cv.rect(8, 11, 10, 13, DARK)
    cv.rect(14, 11, 16, 13, DARK)
    brush(cv, (14, 28), (30, 9), w=3.0, col=_hex("#8a5a3a"), bristle=_hex("#e8e0c8"))


@icon("nHair/Paint Hair Textures/Hair Color")
def i_hair_color(cv):
    for k, col in enumerate((_hex("#e8dca0"), (0.15, 0.15, 0.15), HAIR, _hex("#d06030"))):
        cv.polyline(bezier((4 + k * 3, 2), (8 + k * 3, 12), (12 + k * 2, 18), (10 + k * 4, 28), 16), 1.8, col, ol=True)
    brush(cv, (16, 28), (30, 9), w=3.0, col=_hex("#8a5a3a"), bristle=_hex("#e8e0c8"))


@icon("nHair/Paint Hair Textures/Specular Color")
def i_hair_specular(cv):
    for (i, j), col in zip(((0, 0), (1, 0), (0, 1), (1, 1)), (_hex("#e8e040"), GDISC, CELL, _hex("#e06a6a"))):
        cv.rect(8 + i * 8, 2 + j * 8, 15 + i * 8, 9 + j * 8, col, ol=True)
    cv.circle(6, 24, 3.5, WHITE, ol=True)
    brush(cv, (12, 29), (28, 15), w=3.0, col=_hex("#8a5a3a"), bristle=_hex("#e8e0c8"))


@icon("nHair/Set Rest Position/From Start")
def i_hair_rest_from_start(cv):
    disc(cv, 9, 8, 6, "S", (0.45, 0.45, 0.45))
    disc(cv, 20, 20, 9, "R", RDISC)
    arrow(cv, (6, 16), (12, 20), w=2.0, col=RED, head=3.5)


@icon("nHair/Set Start Position/From Rest")
def i_hair_start_from_rest(cv):
    disc(cv, 9, 8, 6, "R", (0.45, 0.45, 0.45))
    disc(cv, 20, 20, 9, "S", GDISC)
    arrow(cv, (6, 16), (12, 20), w=2.0, col=RED, head=3.5)


@icon("nHair/Transplant Hair")
def i_transplant_hair(cv):
    blob(cv, 20, 26, 9)
    cv.polyline(bezier((4, 2), (8, 8), (14, 12), (18, 20), 16), 2.2, HAIR, ol=True)
    cv.polyline(bezier((22, 4), (26, 8), (30, 14), (30, 20), 16), 1.6, LIGHT, ol=True)
    cv.fill(cv.m_ring(20, 12, 5, 1.8) & cv.m_angle(20, 12, 200, 360), RED, ol=True)
    cv.poly([(23, 13), (27, 12), (25, 16)], RED, ol=True)


# --- nCache (grey frames) ---------------------------------------------------------------------

NFRAME = _hex("#868686")


def nstrip(cv, x0, y0, x1, y1, cells=3, frames=None):
    gstrip(cv, x0, y0, x1, y1, cells, cell=NFRAME, frames=frames)
    cw = (x1 - x0 - 2) / cells
    for i in range(cells):
        cv.rect(x0 + 2.5 + i * cw, y0 + 4.5, x0 + 4 + i * cw, y1 - 4.5, WHITE)


@icon("nCache/Append to Cache")
def i_nc_append(cv):
    nstrip(cv, 2, 10, 26, 22)
    red_plus(cv, 25, 21, 4.5)


@icon("nCache/Attach Cache...")
def i_nc_attach(cv):
    floppy(cv, 3, 2, 1.0)
    nstrip(cv, 10, 14, 31, 26)
    red_arrow_bend(cv, (8, 12), (8, 20), (15, 20))


@icon("nCache/Create Particle Disk Cache")
def i_nc_particle_disk(cv):
    floppy(cv, 18, 1, 1.0)
    gstrip(cv, 3, 14, 29, 27, 3, cell=WHITE)
    for i in range(3):
        for dx, dy in ((0, 0), (3, 2), (-1, 3)):
            cv.circle(7 + i * 8.3 + dx, 18 + dy, 1.5, FGREEN)
    red_plus(cv, 7, 7, 4.5)


@icon("nCache/Delete Cache Frame")
def i_nc_delete_frame(cv):
    nstrip(cv, 2, 8, 26, 20)
    cv.frame(17.5, 11, 25, 17, 1.0, RED)
    trash(cv, 18, 18)


@icon("Cache/Geometry Cache/Paint Cache Weights Tool", "nCache/Paint Cache Weights Tool")
def i_paint_cache_weights(cv):
    gstrip(cv, 3, 2, 29, 14)
    paint_mark(cv, 17, 24)


@icon("nCache/Replace Caches/Maya Fluid")
def i_nc_replace_fluid(cv):
    gstrip(cv, 3, 14, 29, 26, 3, cell=SEA_LIGHT)
    cv.rect(11, 4, 19, 17, WHITE, ol=True)


@icon("nCache/Replace Caches/nObject")
def i_nc_replace_object(cv):
    nstrip(cv, 2, 3, 24, 15)
    gstrip(cv, 8, 15, 30, 27, 3, cell=WHITE)


@icon("nCache/Transfer Cache To Input Mesh")
def i_nc_transfer(cv):
    nstrip(cv, 2, 2, 26, 14)
    red_arrow_bend(cv, (6, 14), (6, 24), (12, 24))
    q = [(21, 15), (31, 21), (21, 29), (11, 23)]
    cv.poly(q, TAN, ol=True)
    face_grid(cv, q, 2, shade(TAN, -0.5))


# --- Cache > Geometry Cache (blue frames) -----------------------------------------------------

@icon("Cache/Geometry Cache/Append to Cache")
def i_gc_append(cv):
    gstrip(cv, 2, 10, 26, 22, 3, frames=(CELL, CELL, (0.5, 0.5, 0.5)))
    red_plus(cv, 25, 21, 4.5)


@icon("Cache/Geometry Cache/Create New Cache")
def i_gc_create(cv):
    gstrip(cv, 3, 14, 29, 26)
    red_plus(cv, 8, 6, 4.5)


@icon("Cache/Geometry Cache/Delete Cache")
def i_gc_delete(cv):
    gstrip(cv, 2, 6, 26, 18, 3, frames=((0.2, 0.2, 0.2),) * 3)
    for i in range(3):
        cv.frame(3.5 + i * 8, 9.5, 9.5 + i * 8, 14.5, 1.0, RED)
    trash(cv, 18, 17)


@icon("Cache/Geometry Cache/Delete Cache Frame")
def i_gc_delete_frame(cv):
    gstrip(cv, 2, 6, 26, 18, 3, frames=(CELL, CELL, (0.2, 0.2, 0.2)))
    cv.frame(19.5, 9.5, 25, 14.5, 1.0, RED)
    trash(cv, 18, 17)


@icon("Cache/Geometry Cache/Delete History Ahead of Cache")
def i_gc_delete_history(cv):
    cv.fill(cv.m_rect(2, 12, 26, 24), np.stack([np.clip(CELL[i] * (cv.y - 6) / 18, 0, 1) for i in range(3)], -1))
    cv.circle(16, 6, 4.5, LIGHT, ol=True)
    cv.line((16, 6), (16, 3.5), 1.0, DARK)
    cv.line((16, 6), (18, 6), 1.0, DARK)
    trash(cv, 18, 17)


@icon("Cache/Geometry Cache/Disable All Caches On Selected")
def i_gc_disable(cv):
    gstrip(cv, 2, 6, 30, 18, 3, frames=((0.45, 0.45, 0.45),) * 3, col=(0.3, 0.3, 0.3))
    cursor_white(cv, 17, 14, 1.0, col=WHITE)


@icon("Cache/Geometry Cache/Enable All Caches On Selected")
def i_gc_enable(cv):
    gstrip(cv, 2, 6, 30, 18, 3, frames=(GDISC,) * 3)
    for i in range(3):
        cv.rect(4 + i * 9, 10, 9 + i * 9, 14, _hex("#c8f0c8"))
    cursor_white(cv, 17, 14, 1.0, col=WHITE)


@icon("Cache/Geometry Cache/Export Cache")
def i_gc_export(cv):
    gstrip(cv, 2, 2, 28, 14, 3, frames=(CELL, WHITE, CELL))
    red_arrow_bend(cv, (13, 14), (13, 24), (21, 24))
    cv.rect(22, 18, 30, 29, WHITE, ol=True)


@icon("Cache/Geometry Cache/Import Cache...")
def i_gc_import(cv):
    cv.rect(2, 2, 10, 13, WHITE, ol=True)
    red_arrow_bend(cv, (10, 6), (17, 6), (17, 17))
    gstrip(cv, 4, 16, 30, 28, 3, frames=(CELL, WHITE, CELL))


@icon("Cache/Geometry Cache/Merge Caches")
def i_gc_merge(cv):
    gstrip(cv, 2, 2, 24, 13, 3, frames=((0.4, 0.45, 0.5),) * 3, col=(0.25, 0.28, 0.32))
    gstrip(cv, 8, 19, 30, 30, 3, frames=((0.4, 0.45, 0.5),) * 3, col=(0.25, 0.28, 0.32))
    gstrip(cv, 5, 10, 27, 22)


@icon("Cache/Geometry Cache/Replace Cache")
def i_gc_replace(cv):
    gstrip(cv, 2, 3, 24, 15)
    gstrip(cv, 8, 15, 30, 27, 3, cell=WHITE)


@icon("Cache/Geometry Cache/Replace Cache Frame")
def i_gc_replace_frame(cv):
    gstrip(cv, 2, 14, 30, 26, 3, frames=(CELL, WHITE, CELL))
    cv.rect(12, 3, 20, 17, WHITE, ol=True)
