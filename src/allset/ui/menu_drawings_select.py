# SPDX-License-Identifier: GPL-3.0-or-later
"""Kit menu pictures for Select and Modify (#54) — see ``menu_drawings``."""

import math


from .menu_drawings import RED, blob, icon, prune_mark
from .menu_drawings_mesh import hex_cube, sliders, vsq
from .shelf_icons import (BLUE, DARK, LIGHT, ORANGE, TEAL, WHITE, _hex, arrow, bezier, brush, checker,
                          cylinder, face_grid, hgrad, lerp, shade, sphere_colour, wave_pts)

OLIVE = _hex("#8a8262")       # Maya's selection-conversion mesh patch
SEL_YELLOW = _hex("#f0e030")
UVBLUE = _hex("#5aa8e0")
CVBLUE = _hex("#7ab4e0")


# --- shared parts -----------------------------------------------------------------------------

PATCH = [(4, 19), (19, 13), (29, 21), (14, 28)]


def _bilerp(q, u, v):
    a, b, c, d = q
    top, bot = lerp(a, b, u), lerp(d, c, u)
    return lerp(top, bot, v)


def patch(cv, q=PATCH, n=2, col=OLIVE, ghost=True):
    """Maya's conversion picture: an olive mesh patch (n x n) seen from above, a faded copy floating over it."""
    if ghost:
        g = [(x, y - 9) for x, y in q]
        cv.poly(g, shade(col, -0.2), alpha=0.75)
    cv.poly(q, col, ol=True)
    face_grid(cv, q, n, (0.25, 0.24, 0.18), w=1.0)
    return q


def edge_lines(cv, q, n, col, w=1.4, which="all"):
    for i in range(0 if which == "all" else 1, n + 1 if which == "all" else n):
        t = i / n
        cv.line(_bilerp(q, t, 0), _bilerp(q, t, 1), w, col)
        cv.line(_bilerp(q, 0, t), _bilerp(q, 1, t), w, col)


def face_marks(cv, q, n, cells=None, frame=UVBLUE, fill=_hex("#c8946a")):
    for i in range(n):
        for j in range(n):
            if cells is not None and (i, j) not in cells:
                continue
            sub = [_bilerp(q, (i + a) / n, (j + b) / n) for a, b in ((0.12, 0.12), (0.88, 0.12), (0.88, 0.88), (0.12, 0.88))]
            cv.poly(sub, fill)
            cv.polyline(sub + [sub[0]], 1.0, frame)
            c = _bilerp(q, (i + 0.5) / n, (j + 0.5) / n)
            cv.rect(c[0] - 1.2, c[1] - 1.2, c[0] + 1.2, c[1] + 1.2, SEL_YELLOW)


def vert_marks(cv, q, n, h=1.5):
    for i in range(n + 1):
        for j in range(n + 1):
            p = _bilerp(q, i / n, j / n)
            cv.rect(p[0] - h, p[1] - h, p[0] + h, p[1] + h, SEL_YELLOW, ol=True)


def uv_patch(cv, q=PATCH, border=UVBLUE):
    cv.poly([(x, y - 9) for x, y in q], shade(OLIVE, -0.2), alpha=0.75)
    cv.poly(q, BLACK_UV, ol=True)
    for i in range(2):
        for j in range(2):
            if (i + j) % 2 == 0:
                cv.poly([_bilerp(q, (i + a) / 2, (j + b) / 2) for a, b in ((0, 0), (1, 0), (1, 1), (0, 1))], WHITE)
    cv.polyline(q + [q[0]], 1.4, border)


BLACK_UV = (0.08, 0.08, 0.08)


def s_curve(cv, col=CVBLUE, w=2.0):
    pts = bezier((6, 27), (32, 30), (0, 4), (27, 5), 30)
    cv.polyline(pts, w, col, ol=True)
    return pts


def cv_sq(cv, x, y, h=1.8):
    cv.rect(x - h, y - h, x + h, y + h, SEL_YELLOW, ol=True)
    cv.rect(x - h + 1, y - h + 1, x + h - 1, y + h - 1, DARK)


def nurbs_sheet(cv):
    q = [(9, 4), (27, 7), (24, 28), (4, 25)]
    cv.fill(cv.m_poly(q), hgrad(cv, 4, 27, _hex("#6a9ad0"), 0.35, -0.2), ol=True)
    cv.line(lerp(q[0], q[1], 0.5), lerp(q[3], q[2], 0.5), 1.0, shade(BLUE, -0.5))
    cv.line(lerp(q[0], q[3], 0.5), lerp(q[1], q[2], 0.5), 1.0, shade(BLUE, -0.5))
    return q


def red_arrow2(cv, p0, p1, p2):
    """Two red arrows pointing away from the middle (grow) or to it (shrink)."""
    arrow(cv, p0, p1, w=1.6, col=RED, head=3.5)
    arrow(cv, p0, p2, w=1.6, col=RED, head=3.5)


def conv_arrow(cv):
    """Maya's convert arrow: a grey arrow from the upper-left source to the lower-right result."""
    arrow(cv, (6, 16), (13, 23), w=2.2, head=4.5)


def poly_ball(cv, cx=22, cy=22, r=8.5):
    cv.fill(cv.m_circle(cx, cy, r), sphere_colour(cv, cx, cy, r, ORANGE, amb=0.8, dif=0.35), ol=True)
    for k in (-0.4, 0.4):
        cv.fill(cv.m_line((cx - r, cy + k * r), (cx + r, cy + k * r), 1.0) & cv.m_circle(cx, cy, r - 0.5), DARK)
    cv.fill(cv.m_ering(cx, cy, r * 0.45, r, 1.0) & cv.m_circle(cx, cy, r - 0.5), DARK)


def wire_ball(cv, cx=10, cy=9, r=7.5, col=LIGHT):
    cv.fill(cv.m_circle(cx, cy, r), sphere_colour(cv, cx, cy, r, col, amb=0.75, dif=0.35), ol=True)
    for k in (-0.4, 0.4):
        cv.fill(cv.m_line((cx - r, cy + k * r), (cx + r, cy + k * r), 1.0) & cv.m_circle(cx, cy, r - 0.5), DARK)
    cv.fill(cv.m_ering(cx, cy, r * 0.45, r, 1.0) & cv.m_circle(cx, cy, r - 0.5), DARK)


def teal_cube(cv, cx=22, cy=22, r=8.5):
    hex_cube(cv, cx, cy, r, TEAL, wire=True)
    hex_cube(cv, cx, cy + 0.5, r * 0.45, TEAL, wire=True)


def magnet(cv, cx, cy, r=6.0, col=LIGHT):
    m = (cv.m_ring(cx, cy, r, 3.0) & (cv.y <= cy)) | cv.m_rect(cx - r, cy, cx - r + 3, cy + 4) | \
        cv.m_rect(cx + r - 3, cy, cx + r, cy + 4)
    cv.fill(m, col, ol=True)


def teal_tri(cv, pts):
    cv.polyline(list(pts) + [pts[0]], 1.8, TEAL, ol=True)


def tri_head(cv, x, y, a, s=4.5, col=TEAL):
    """A solid manipulator arrow head at (x, y) pointing at angle ``a`` (degrees, screen)."""
    ra = math.radians(a)
    ux, uy = math.cos(ra), math.sin(ra)
    cv.poly([(x + ux * s, y + uy * s), (x - ux * s * 0.6 - uy * s * 0.75, y - uy * s * 0.6 + ux * s * 0.75),
             (x - ux * s * 0.6 + uy * s * 0.75, y - uy * s * 0.6 - ux * s * 0.75)], col, ol=True)


# --- Select -----------------------------------------------------------------------------------

@icon("Select/All CVs")
def i_all_cvs(cv):
    pts = s_curve(cv)
    for i in (0, 6, 12, 18, 24, 29):
        cv_sq(cv, *pts[i])


@icon("Select/CV Selection Boundary")
def i_cv_boundary(cv):
    q = nurbs_sheet(cv)
    for p in q:
        cv_sq(cv, *p)
    cv_sq(cv, *lerp(q[0], q[1], 0.5))


@icon("Select/Cluster Curve")
def i_cluster_curve(cv):
    pts = s_curve(cv)
    for i in (11, 13, 15, 17):
        cv_sq(cv, *pts[i], 1.6)


@icon("Select/Components/UV")
def i_select_uv(cv):
    cv.rect(4, 4, 28, 28, (0.55, 0.55, 0.55), ol=True)
    cv.circle(16, 16, 10, BLACK_UV)
    cv.fill(cv.m_circle(16, 16, 10) & (((cv.x < 16) & (cv.y < 16)) | ((cv.x >= 16) & (cv.y >= 16))), WHITE)
    for x, y in ((4, 4), (28, 4), (4, 28), (28, 28), (16, 4), (16, 28)):
        cv_sq(cv, x, y, 1.6)


@icon("Select/Components/Vertex Face")
def i_select_vertex_face(cv):
    for i in range(2):          # four faces round one vertex, each with its vertex-face corner marked
        for j in range(2):
            x, y = 3 + i * 14, 3 + j * 14
            cv.rect(x, y, x + 12, y + 12, UVBLUE, ol=True)
            cv.rect(x + 1.5, y + 1.5, x + 10.5, y + 10.5, _hex("#c8946a"))
            cx, cy = x + (4 if i else 8), y + (4 if j else 8)
            cv.rect(cx - 1.5, cy - 1.5, cx + 1.5, cy + 1.5, SEL_YELLOW, ol=True)


@icon("Select/Contiguous Edges")
def i_contiguous_edges(cv):
    cylinder(cv, 14, 6, 24, 11, 5, OLIVE)
    for x in (8, 14, 20):
        cv.line((x, 7), (x, 28), 1.0, (0.3, 0.3, 0.25))
    cv.line((15, 9), (17, 26), 2.0, WHITE)
    prune_mark(cv, 20, 16)


@icon("Select/Convert Selection/To Contained Edges")
def i_to_contained_edges(cv):
    q = patch(cv)
    edge_lines(cv, q, 2, ORANGE, 1.6, which="inner")


@icon("Select/Convert Selection/To Contained Faces")
def i_to_contained_faces(cv):
    q = patch(cv, n=3)
    face_marks(cv, q, 3, cells={(1, 1), (1, 0), (0, 1)})


@icon("Select/Convert Selection/To Edge Loop")
def i_to_edge_loop(cv):
    q = patch(cv, n=3, ghost=False)
    cv.line(_bilerp(q, 0.66, 0), _bilerp(q, 0.66, 1), 2.0, WHITE)
    cv.poly([(x, y - 9) for x, y in q], shade(OLIVE, -0.2), alpha=0.3)


@icon("Select/Convert Selection/To Shell Border", "Select/Convert Selection/To Edge Perimeter",
      "Select/Convert Selection/To Face Perimeter", "Select/Convert Selection/To UV Perimeter",
      "Select/Convert Selection/To Vertex Perimeter")
def i_to_perimeter(cv):
    cv.poly([(x, y - 9) for x, y in PATCH], shade(OLIVE, -0.2), alpha=0.75)
    cv.polyline(PATCH + [PATCH[0]], 2.2, SEL_YELLOW, ol=True)


@icon("Select/Convert Selection/To Edge Ring")
def i_to_edge_ring(cv):
    q = patch(cv, n=3, ghost=False)
    for u in (0.17, 0.5, 0.83):         # one edge across each face of a row
        cv.line(_bilerp(q, u, 0.33), _bilerp(q, u, 0.66), 2.0, WHITE)


@icon("Select/Convert Selection/To Edges")
def i_to_edges(cv):
    q = patch(cv)
    edge_lines(cv, q, 2, ORANGE, 1.4)


@icon("Select/Convert Selection/To Face Path")
def i_to_face_path(cv):
    q = [(6, 6), (20, 3), (24, 22), (10, 26)]
    cv.poly(q, OLIVE, ol=True)
    face_marks(cv, q, 3, cells={(0, 0), (1, 0), (1, 1), (2, 1), (2, 2)})
    prune_mark(cv, 20, 16)


@icon("Select/Convert Selection/To Faces")
def i_to_faces(cv):
    q = patch(cv)
    face_marks(cv, q, 2)


@icon("Select/Convert Selection/To Shell")
def i_to_shell(cv):
    cv.poly([(x, y - 9) for x, y in PATCH], shade(OLIVE, -0.2), alpha=0.75)
    cv.polyline(PATCH + [PATCH[0]], 1.8, WHITE, ol=True)
    edge_lines(cv, PATCH, 2, WHITE, 1.8, which="inner")


@icon("Select/Convert Selection/To UV Edge Loop")
def i_to_uv_edge_loop(cv):
    uv_patch(cv)
    cv.line(_bilerp(PATCH, 0.5, -0.05), _bilerp(PATCH, 0.5, 1.05), 2.6, SEL_YELLOW, ol=True)


@icon("Select/Convert Selection/To UV Shell")
def i_to_uv_shell(cv):
    uv_patch(cv)


@icon("Select/Convert Selection/To UV Shell Border")
def i_to_uv_shell_border(cv):
    uv_patch(cv, border=WHITE)
    cv.polyline(PATCH + [PATCH[0]], 2.2, WHITE)


@icon("Select/Convert Selection/To UVs")
def i_to_uvs(cv):
    uv_patch(cv)
    vert_marks(cv, PATCH, 2, 1.3)


@icon("Select/Convert Selection/To Vertex Faces")
def i_to_vertex_faces(cv):
    q = [(4, 14), (16, 9), (24, 15), (12, 21)]
    cv.poly(q, OLIVE, ol=True)
    face_grid(cv, q, 2, (0.25, 0.24, 0.18))
    q2 = [(10, 21), (20, 17), (26, 22), (16, 27)]
    cv.poly(q2, _hex("#c8946a"), ol=True)
    cv.polyline(q2 + [q2[0]], 1.2, UVBLUE)
    cv.rect(16.5, 20.5, 19.5, 23.5, SEL_YELLOW)


@icon("Select/Convert Selection/To Vertices")
def i_to_vertices(cv):
    q = patch(cv)
    vert_marks(cv, q, 2)


@icon("Select/First CV")
def i_first_cv(cv):
    pts = s_curve(cv)
    cv_sq(cv, *pts[0], 2.2)


@icon("Select/Last CV")
def i_last_cv(cv):
    pts = s_curve(cv)
    cv_sq(cv, *pts[-1], 2.2)


@icon("Select/Grow")
def i_grow(cv):
    q = [(3, 18), (17, 12), (29, 19), (15, 26)]
    cv.poly(q, OLIVE, ol=True)
    face_grid(cv, q, 3, (0.25, 0.24, 0.18))
    mid = [_bilerp(q, a, b) for a, b in ((0.33, 0.33), (0.66, 0.33), (0.66, 0.66), (0.33, 0.66))]
    cv.poly(mid, UVBLUE)
    red_arrow2(cv, (15, 8), (6, 11), (25, 4))


@icon("Select/Shrink")
def i_shrink(cv):
    q = [(3, 18), (17, 12), (29, 19), (15, 26)]
    cv.poly(q, (0.45, 0.45, 0.42), ol=True)
    face_grid(cv, q, 3, (0.25, 0.25, 0.25))
    arrow(cv, (5, 10), (13, 7), w=1.6, col=RED, head=3.5)
    arrow(cv, (26, 3), (17, 6), w=1.6, col=RED, head=3.5)


@icon("Select/Object/Component")
def i_object_component(cv):
    cv.fill(cv.m_circle(10, 10, 8), sphere_colour(cv, 10, 10, 8, OLIVE, amb=0.8, dif=0.5), ol=True)
    cv.line((4, 30), (29, 3), 1.4, (0.1, 0.1, 0.1))
    q = [(14, 22), (23, 18), (30, 23), (21, 28)]
    cv.poly(q, OLIVE, ol=True)
    face_grid(cv, q, 2, (0.25, 0.24, 0.18))


@icon("Select/Shortest Edge Path Tool")
def i_shortest_path(cv):
    q = [(6, 4), (22, 2), (26, 24), (8, 27)]
    cv.poly(q, OLIVE, ol=True)
    face_grid(cv, q, 3, (0.25, 0.24, 0.18))
    cv.line((4, 18), (25, 14), 1.8, WHITE)
    for p in ((4, 18), (25, 14)):
        cv_sq(cv, *p, 1.6)
    prune_mark(cv, 17, 16)


@icon("Select/Similar")
def i_similar(cv):
    for x in range(2, 22, 3):
        cv.rect(x, 2, x + 1.5, 3, WHITE)
        cv.rect(x, 28, x + 1.5, 29, WHITE)
    for y in range(2, 28, 3):
        cv.rect(2, y, 3, y + 1.5, WHITE)
        cv.rect(21, y, 22, y + 1.5, WHITE)
    cv.polyline([(8, 5), (8, 13), (16, 13)], 2.6, _hex("#9a4ad8"), ol=True)
    cv.polyline([(16, 16), (8, 16), (8, 24)], 2.6, _hex("#3ab04a"), ol=True)
    cv.polyline([(28, 10), (28, 18), (23, 18)], 2.6, UVBLUE, ol=True)
    prune_mark(cv, 21, 17)


@icon("Select/Surface Border")
def i_surface_border(cv):
    q = nurbs_sheet(cv)
    for t in (0, 0.5):
        for a, b in ((0, 1), (1, 2), (2, 3), (3, 0)):
            cv_sq(cv, *lerp(q[a], q[b], t), 1.5)


@icon("Select/Use Constraints...")
def i_use_constraints(cv):
    from .menu_drawings_fx import bang
    bang(cv, 6, 10, 15)
    q = [(10, 14), (24, 9), (30, 19), (16, 24)]
    cv.poly(q, OLIVE, ol=True)
    cv.polyline(q + [q[0]], 1.4, WHITE)
    face_grid(cv, q, 2, (0.25, 0.24, 0.18))
    prune_mark(cv, 20, 17)


# --- Modify -----------------------------------------------------------------------------------

@icon("Modify/Align Tool")
def i_align_tool(cv):
    cv.rect(9, 12, 14, 24, TEAL, ol=True)
    cv.rect(18, 4, 23, 24, TEAL, ol=True)
    cv.rect(3, 25, 29, 28, LIGHT, ol=True)
    for x in range(5, 29, 3):
        cv.rect(x, 25, x + 1, 26.5, DARK)


def _grey_cubes(cv):
    for x, y in ((6, 5), (12, 4), (9, 10)):
        hex_cube(cv, x, y, 4, LIGHT)


def _convert(cv, src, dst):
    src()
    conv_arrow(cv)
    dst()


@icon("Modify/Convert/Displacement to Polygons")
def i_conv_displacement(cv):
    _convert(cv, lambda: [hex_cube(cv, x, y, 4.5, LIGHT) for x, y in ((6, 6), (13, 5), (9.5, 11))], lambda: poly_ball(cv))


@icon("Modify/Convert/Displacement to Polygons with History")
def i_conv_displacement_history(cv):
    _convert(cv, lambda: [hex_cube(cv, x, y, 4.5, LIGHT) for x, y in ((6, 6), (13, 5), (9.5, 11))], lambda: poly_ball(cv))
    cv.circle(25, 6, 5, LIGHT, ol=True)
    cv.line((25, 6), (25, 2.5), 1.2, DARK)
    cv.line((25, 6), (28, 6), 1.2, DARK)


@icon("Modify/Convert/Fluid to Polygons")
def i_conv_fluid(cv):
    def src():
        for k in range(3):
            cv.polyline(wave_pts(3, 22, 4 + k * 4, 1.6, 1.0, k * 0.6), 1.4, LIGHT, ol=True)
    _convert(cv, src, lambda: poly_ball(cv))


@icon("Modify/Convert/Geometry to Bounding Box")
def i_conv_bbox(cv):
    _convert(cv, lambda: wire_ball(cv), lambda: hex_cube(cv, 22, 22, 8.5, ORANGE))


@icon("Modify/Convert/Instance to Object")
def i_conv_instance(cv):
    def src():
        cv.ring(11, 10, 9, 1.8, LIGHT, ol=True)
        cylinder(cv, 11, 6, 13, 4.5, 2, LIGHT)
    _convert(cv, src, lambda: cylinder(cv, 22, 16, 26, 7, 3, TEAL))


@icon("Modify/Convert/NURBS to Polygons")
def i_conv_nurbs_poly(cv):
    _convert(cv, lambda: blob(cv, 10, 9, 7.5, LIGHT), lambda: poly_ball(cv))


@icon("Modify/Convert/NURBS to Subdiv")
def i_conv_nurbs_subdiv(cv):
    _convert(cv, lambda: blob(cv, 10, 9, 7.5, LIGHT), lambda: teal_cube(cv))


def _pfx_brush(cv):
    brush(cv, (16, 21), (29, 4), w=3.2, col=LIGHT, bristle=shade(LIGHT, -0.2))


@icon("Modify/Convert/Paint Effects to Curves")
def i_conv_pfx_curves(cv):
    cv.polyline(bezier((5, 4), (5, 20), (22, 10), (20, 27), 24), 1.8, UVBLUE, ol=True)
    cv.frame(3, 2, 7.5, 6.5, 1.2, UVBLUE)
    cv.frame(18, 25, 22.5, 29.5, 1.2, UVBLUE)
    _pfx_brush(cv)


@icon("Modify/Convert/Paint Effects to NURBS")
def i_conv_pfx_nurbs(cv):
    cv.polyline(bezier((6, 4), (2, 18), (24, 12), (12, 28), 24), 4.5, UVBLUE, ol=True)
    _pfx_brush(cv)


@icon("Modify/Convert/Paint Effects to Polygons")
def i_conv_pfx_poly(cv):
    pts = bezier((6, 4), (2, 18), (24, 12), (12, 28), 24)
    cv.polyline(pts, 4.5, ORANGE, ol=True)
    for i in range(2, 24, 4):
        cv.rect(pts[i][0] - 0.5, pts[i][1] - 2, pts[i][0] + 0.5, pts[i][1] + 2, DARK)
    _pfx_brush(cv)


@icon("Modify/Convert/Polygon Edges to Curve")
def i_conv_edges_curve(cv):
    _convert(cv, lambda: wire_ball(cv), lambda: cv.polyline(bezier((18, 28), (28, 22), (16, 16), (28, 8), 20), 2.0,
                                                            UVBLUE, ol=True))


@icon("Modify/Convert/Polygons to Subdiv")
def i_conv_poly_subdiv(cv):
    _convert(cv, lambda: wire_ball(cv), lambda: teal_cube(cv))


@icon("Modify/Convert/Smooth Mesh Preview to Polygons")
def i_conv_smooth_preview(cv):
    def src():          # the smooth preview: a smooth grey ball in its wire cage
        hex_cube(cv, 10, 10, 8.5, LIGHT, wire=True)
        blob(cv, 10, 10, 6, LIGHT)
    _convert(cv, src, lambda: poly_ball(cv))


@icon("Modify/Convert/Subdiv to NURBS")
def i_conv_subdiv_nurbs(cv):
    _convert(cv, lambda: (hex_cube(cv, 10, 9, 7.5, LIGHT, wire=True), hex_cube(cv, 10, 9.5, 3.4, LIGHT, wire=True)),
             lambda: blob(cv, 22, 22, 8.5))


@icon("Modify/Convert/Subdiv to Polygons")
def i_conv_subdiv_poly(cv):
    _convert(cv, lambda: (hex_cube(cv, 10, 9, 7.5, LIGHT, wire=True), hex_cube(cv, 10, 9.5, 3.4, LIGHT, wire=True)),
             lambda: poly_ball(cv))


@icon("Modify/Convert/Texture to Geometry")
def i_conv_texture(cv):
    _convert(cv, lambda: checker(cv, 3, 3, s=11, n=3), lambda: poly_ball(cv))


@icon("Modify/Convert/nParticle to Polygons")
def i_conv_particles(cv):
    def src():
        for x, y, r in ((5, 5, 1.6), (11, 3, 1.3), (8, 10, 1.8), (15, 8, 1.4), (4, 13, 1.3), (13, 13, 1.2)):
            cv.circle(x, y, r, LIGHT, ol=True)
    _convert(cv, src, lambda: poly_ball(cv))


@icon("Modify/Make Live")
def i_make_live(cv):
    magnet(cv, 16, 15, 10)


@icon("Modify/Paint Attributes Tool")
def i_paint_attributes(cv):
    brush(cv, (5, 22), (24, 3), w=3.4, col=LIGHT, bristle=shade(LIGHT, -0.2))
    cv.frame(17, 16, 30, 21, 1.2, TEAL, ol=True)
    cv.line((16, 26), (30, 26), 1.2, TEAL)
    cv.rect(21, 24, 25, 28, TEAL, ol=True)


@icon("Modify/Paint Scripts Tool")
def i_paint_scripts(cv):
    cv.fill(cv.m_ering(16, 24, 13, 4.5, 1.6), TEAL, ol=True)
    brush(cv, (10, 23), (28, 4), w=3.4, col=LIGHT, bristle=shade(LIGHT, -0.2))


def _snap_hook(cv, x, y):
    cv.fill(cv.m_ring(x + 4, y + 4, 4, 1.8) & (cv.y <= y + 4), LIGHT, ol=True)
    cv.rect(x - 1, y + 4, x + 1, y + 7, LIGHT, ol=True)


@icon("Modify/Snap Align Objects/2 Points to 2 Points")
def i_snap_2pt(cv):
    _snap_hook(cv, 4, 2)
    teal_tri(cv, [(18, 12), (27, 27), (9, 27)])
    vsq(cv, 18, 8, 2.2, LIGHT)
    vsq(cv, 27, 27, 2.2, LIGHT)


@icon("Modify/Snap Align Objects/3 Points to 3 Points")
def i_snap_3pt(cv):
    _snap_hook(cv, 4, 2)
    cv.poly([(18, 12), (27, 27), (9, 27)], shade(TEAL, -0.3))
    teal_tri(cv, [(18, 12), (27, 27), (9, 27)])
    for p in ((18, 8), (27, 27), (9, 27)):
        vsq(cv, p[0], p[1], 2.2, LIGHT)


@icon("Modify/Snap Align Objects/Align Objects")
def i_snap_align_objects(cv):
    cv.rect(8, 14, 14, 26, TEAL, ol=True)
    cv.rect(18, 6, 24, 26, TEAL, ol=True)
    cv.line((3, 27), (29, 27), 1.6, LIGHT, ol=True)


@icon("Modify/Snap Align Objects/Point to Point")
def i_snap_point(cv):
    _snap_hook(cv, 4, 2)
    teal_tri(cv, [(16, 12), (27, 28), (5, 28)])
    vsq(cv, 16, 8, 2.2, LIGHT)


@icon("Modify/Snap Align Objects/Position Along Curve")
def i_snap_along_curve(cv):
    cv.polyline(wave_pts(2, 30, 24, 2.5, 1.0), 1.8, LIGHT, ol=True)
    cv.rect(8, 6, 13, 22, TEAL, ol=True)
    cv.rect(17, 9, 22, 25, TEAL, ol=True)


@icon("Modify/Snap Together Tool")
def i_snap_together(cv):
    magnet(cv, 17, 9, 6)
    cv.circle(10, 22, 6.5, TEAL, ol=True)
    cv.circle(23, 22, 6.5, TEAL, ol=True)


@icon("Modify/Transformation Tools/Move Normal Tool")
def i_move_normal(cv):
    cv.frame(13, 13, 19, 19, 1.4, LIGHT, ol=True)
    for p0, p1 in (((16, 13), (16, 8)), ((13, 19), (8, 23)), ((19, 19), (24, 23))):
        cv.line(p0, p1, 1.4, LIGHT, ol=True)
    cv.text("N", LIGHT, 13.5, 0.5, ol=True)
    cv.text("U", LIGHT, 1, 23, ol=True)
    cv.text("V", LIGHT, 25, 23, ol=True)


@icon("Modify/Transformation Tools/Move/Rotate/Scale Tool")
def i_move_rotate_scale(cv):
    cv.fill(cv.m_ring(16, 17, 10, 1.4) & cv.m_angle(16, 17, 200, 340), LIGHT, ol=True)
    cv.frame(13, 14, 19, 20, 1.4, TEAL, ol=True)
    tri_head(cv, 16, 5, -90)
    tri_head(cv, 6, 26, 135)
    tri_head(cv, 26, 26, 45)


@icon("Modify/Transformation Tools/Proportional Modification Tool")
def i_proportional(cv):
    cv.line((4, 3), (4, 11), 1.6, LIGHT)
    cv.line((28, 3), (28, 11), 1.6, LIGHT)
    arrow(cv, (16, 7), (6, 7), w=1.8, head=3.5)
    arrow(cv, (16, 7), (26, 7), w=1.8, head=3.5)
    q = [(16, 15), (30, 22), (16, 29), (2, 22)]
    cv.poly(q, _hex("#5aaed4"), ol=True)
    face_grid(cv, q, 2, DARK)
    tri_head(cv, 16, 18, -90, 4)


@icon("Modify/Transformation Tools/Show Manipulator Tool")
def i_show_manipulator(cv):
    cv.frame(13, 15, 19, 21, 1.4, LIGHT, ol=True)
    tri_head(cv, 16, 6, -90)
    tri_head(cv, 6, 27, 135)
    tri_head(cv, 26, 27, 45)
    cv.line((16, 15), (16, 9), 1.2, TEAL)
    sliders(cv, 21, 3, 9)


@icon("Modify/Transformation Tools/Type Manipulator")
def i_type_manipulator(cv):
    cv.text("T", LIGHT, 11, 9, cell=2.0, ol=True, bold=True)
    tri_head(cv, 16, 3, -90, 3.5)
    tri_head(cv, 16, 29, 90, 3.5)
    tri_head(cv, 3, 16, 180, 3.5)
    tri_head(cv, 29, 16, 0, 3.5)


@icon("Modify/Transformation Tools/Universal Manipulator")
def i_universal_manipulator(cv):
    hex_cube(cv, 16, 17, 9, TEAL)
    cv.fill(cv.m_ring(16, 17, 12, 1.4) & cv.m_angle(16, 17, 200, 340), LIGHT, ol=True)
    tri_head(cv, 16, 3, -90, 4)
    tri_head(cv, 4, 27, 145, 4)
    tri_head(cv, 28, 27, 35, 4)
