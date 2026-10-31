# SPDX-License-Identifier: GPL-3.0-or-later
"""Kit menu pictures for Mesh, Edit Mesh, Mesh Tools and Mesh Display (#54) — see ``menu_drawings``."""

import math

import numpy as np

from .menu_drawings import VCOL, icon
from .shelf_icons import (DARK, KEY, LIGHT, ORANGE, WHITE, arrow, brush, cube, curved_arrow, face_grid, hgrad,
                          lerp, nosign, pencil, plus, shade, sphere_colour, sun, xmark)

GREYF = shade(LIGHT, -0.12)


# --- shared parts -----------------------------------------------------------------------------

def vset(cv, x=3, y=10, s=1.0):
    """Maya's colour set: four coloured vertex squares joined by grey edges (2 x 2)."""
    d, h = 11 * s, 2.2 * s
    pts = [(x + h, y + h), (x + h + d, y + h), (x + h, y + h + d), (x + h + d, y + h + d)]
    for a, b in ((0, 1), (0, 2), (1, 3), (2, 3)):
        cv.line(pts[a], pts[b], max(1.0, s), LIGHT)
    for p, col in zip(pts, VCOL):
        cv.rect(p[0] - h, p[1] - h, p[0] + h, p[1] + h, col, ol=True)
        if h >= 1.8:
            cv.rect(p[0] - h + 1, p[1] - h + 1, p[0] + h - 1, p[1] + h - 1, DARK)


def vsq(cv, x, y, h=2.2, col=ORANGE):
    """A vertex square (hollow, Maya's component mark)."""
    cv.rect(x - h, y - h, x + h, y + h, col, ol=True)
    cv.rect(x - h + 1, y - h + 1, x + h - 1, y + h - 1, DARK)


def normal_line(cv, p0, p1, col=ORANGE):
    """A vertex normal: dotted line from a vertex square ``p0`` out to ``p1``."""
    n = int(math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / 2.5)
    for i in range(1, n + 1):
        x, y = lerp(p0, p1, i / n)
        cv.rect(x - 0.75, y - 0.75, x + 0.75, y + 0.75, col)
    vsq(cv, *p0, 2.5, col)


def padlock(cv, x, y, open_=False):
    cv.rect(x, y + 6, x + 10, y + 14, LIGHT, ol=True)
    cv.rect(x + 4, y + 8.5, x + 6, y + 11.5, DARK)
    sx = x + (8 if open_ else 5)
    cv.fill(cv.m_ring(sx, y + 5, 4, 1.8) & (cv.y <= y + 5), LIGHT, ol=True)
    cv.rect(sx + 2.2, y + 5, sx + 4, y + 6.5, LIGHT)
    if not open_:
        cv.rect(sx - 4, y + 5, sx - 2.2, y + 6.5, LIGHT)


def sliders(cv, x, y, w=12, col=LIGHT):
    for yy, k in ((y, 0.65), (y + 4.5, 0.3)):
        cv.line((x, yy), (x + w, yy), 1.2, col, cap=False)
        cv.rect(x + w * k - 1.5, yy - 1.8, x + w * k + 1.5, yy + 1.8, col, ol=True)


def quilt(cv, cx, cy, s=1.0, col=ORANGE, base=LIGHT):
    """Maya's mesh patch: a grey diamond plane with orange diamond faces on it."""
    cv.poly([(cx, cy - 7 * s), (cx + 13 * s, cy), (cx, cy + 7 * s), (cx - 13 * s, cy)], base, ol=True)
    for dx, dy in ((-6, 0), (6, 0), (0, -3.5), (0, 3.5)):
        x, y = cx + dx * s, cy + dy * s
        cv.poly([(x, y - 2.6 * s), (x + 4.6 * s, y), (x, y + 2.6 * s), (x - 4.6 * s, y)], col)


def hex_cube(cv, cx=16, cy=17, r=12.5, col=LIGHT, wire=False):
    """An iso cube seen corner-on (hexagon) with its three visible faces."""
    top = [(cx, cy - r), (cx + r * 0.87, cy - r * 0.5), (cx, cy), (cx - r * 0.87, cy - r * 0.5)]
    left = [(cx - r * 0.87, cy - r * 0.5), (cx, cy), (cx, cy + r), (cx - r * 0.87, cy + r * 0.5)]
    right = [(cx, cy), (cx + r * 0.87, cy - r * 0.5), (cx + r * 0.87, cy + r * 0.5), (cx, cy + r)]
    if wire:
        for q in (top, left, right):
            cv.polyline(q + [q[0]], 1.4, col, ol=True)
    else:
        for q, k in ((top, 0.25), (left, 0.0), (right, -0.25)):
            cv.poly(q, shade(col, k), ol=True)
    return top, left, right


def minus(cv, cx, cy, s=5.0, w=2.6, col=LIGHT):
    cv.line((cx - s, cy), (cx + s, cy), w, col, ol=True, cap=False)


def asterisk(cv, cx, cy, s=5.0, w=2.2, col=LIGHT, n=3):
    m = np.zeros((cv.n, cv.n), bool)
    for k in range(n):
        a = math.pi * k / n + math.pi / 2
        m |= cv.m_line((cx - s * math.cos(a), cy - s * math.sin(a)), (cx + s * math.cos(a), cy + s * math.sin(a)), w)
    cv.fill(m, col, ol=True)


def down_arrow(cv, x, y0, y1, col=LIGHT):
    arrow(cv, (x, y0), (x, y1), w=2.6, col=col, head=5)


def ibeam(cv, x, y0, y1, col=LIGHT):
    m = cv.m_line((x, y0), (x, y1), 1.4) | cv.m_line((x - 2.5, y0), (x + 2.5, y0), 1.4) | \
        cv.m_line((x - 2.5, y1), (x + 2.5, y1), 1.4)
    cv.fill(m, col, ol=True)


def shiny_ball(cv, cx, cy, r, col=(0.25, 0.25, 0.25), spec=0.9):
    cv.fill(cv.m_circle(cx, cy, r), sphere_colour(cv, cx, cy, r, col, amb=0.6, dif=0.9, spec=spec, power=18), ol=True)


def cursor_white(cv, x, y, s=1.0, col=LIGHT):
    pts = [(0, 0), (0, 13), (3.5, 10), (6, 15), (8, 14), (5.8, 9.5), (10, 9.5)]
    cv.poly([(x + a * s, y + b * s) for a, b in pts], col, ol=True)


def dashed_ring(cv, cx, cy, r, w=1.6, col=LIGHT, n=12):
    m = cv.m_ring(cx, cy, r, w)
    ang = (np.degrees(np.arctan2(cv.y - cy, cv.x - cx)) % 360) // (180 / n)
    cv.fill(m & (ang % 2 == 0), col, ol=True)


def dashed_line(cv, p0, p1, w=1.4, col=LIGHT, dash=2.5):
    n = max(1, int(math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / dash))
    for i in range(0, n, 2):
        cv.line(lerp(p0, p1, i / n), lerp(p0, p1, min(1, (i + 1) / n)), w, col, cap=False)


def squares(cv, x, y, n, m, s, col, gap=1.0, ol=True):
    for i in range(n):
        for j in range(m):
            cv.rect(x + i * s, y + j * s, x + (i + 1) * s - gap, y + (j + 1) * s - gap, col, ol=ol)


def diamond(cv, cx, cy, rx, ry, col, ol=True):
    cv.poly([(cx, cy - ry), (cx + rx, cy), (cx, cy + ry), (cx - rx, cy)], col, ol=ol)


def clipboard(cv, x0, y0, x1, y1, col=ORANGE):
    cv.rect(x0, y0, x1, y1, col, ol=True)
    cv.rect((x0 + x1) / 2 - 3, y0 - 1.5, (x0 + x1) / 2 + 3, y0 + 1.5, LIGHT, ol=True)


def page(cv, x0, y0, x1, y1, col=ORANGE):
    cv.poly([(x0, y0), (x1 - 4, y0), (x1, y0 + 4), (x1, y1), (x0, y1)], col, ol=True)
    cv.poly([(x1 - 4, y0), (x1, y0 + 4), (x1 - 4, y0 + 4)], shade(col, -0.35))


def numbered_diamond(cv, cx=16, cy=16, r=8):
    """Maya's vertex order picture: a split diamond with its corners numbered 0 top, 1 left, 2 right, 3 bottom."""
    ry = r * 0.8
    diamond(cv, cx, cy, r, ry, ORANGE)
    cv.line((cx - r, cy), (cx + r, cy), 1.4, DARK)
    for ch, (x, y) in zip("0123", ((cx - 2.5, cy - ry - 8), (cx - r - 6.5, cy - 3.5), (cx + r + 1.5, cy - 3.5),
                                  (cx - 2.5, cy + ry + 1))):
        cv.text(ch, LIGHT, x, y, ol=True)


def proxy_cube(cv, cx=14, cy=18, r=11):
    hex_cube(cv, cx, cy, r, LIGHT, wire=True)
    hex_cube(cv, cx, cy + 1, r * 0.55, ORANGE)


def sparkle(cv, cx, cy, s=3.0):
    cv.poly([(cx, cy - s), (cx + s * 0.3, cy - s * 0.3), (cx + s, cy), (cx + s * 0.3, cy + s * 0.3), (cx, cy + s),
             (cx - s * 0.3, cy + s * 0.3), (cx - s, cy), (cx - s * 0.3, cy - s * 0.3)], LIGHT, ol=True)


def grid_frame(cv, x0=3, y0=3, x1=29, y1=29):
    cv.frame(x0, y0, x1, y1, 1.6, LIGHT, ol=True)
    cv.line(((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1), 1.4, LIGHT)
    cv.line((x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2), 1.4, LIGHT)


# --- Mesh Display -----------------------------------------------------------------------------

@icon("Mesh Display/Apply Color")
def i_apply_color(cv):
    vset(cv, 2, 2)
    cursor_white(cv, 17, 15)


@icon("Mesh Display/Assign Existing Set")
def i_assign_existing_set(cv):
    quilt(cv, 14, 23, 1.0)
    quilt(cv, 14, 15, 0.8, col=shade(ORANGE, 0.15), base=shade(LIGHT, -0.2))
    down_arrow(cv, 26, 2, 13)


@icon("Mesh Display/Assign New Set")
def i_assign_new_set(cv):
    cv.polyline([(14, 13), (26, 20), (14, 27), (2, 20), (14, 13)], 1.2, LIGHT)
    for p, col in zip(((14, 15.5), (22, 20), (6, 20), (14, 24.5)), VCOL):
        vsq(cv, *p, 1.8, col)
    down_arrow(cv, 26, 2, 13)


@icon("Mesh Display/Average")
def i_average_normals(cv):
    cv.line((7, 3), (7, 15), 1.2, LIGHT)
    cv.line((13, 27), (29, 27), 1.2, LIGHT)
    normal_line(cv, (7, 26), (25, 8))


@icon("Mesh Display/Color Material Channel/Ambient")
def i_cmc_ambient(cv):
    vset(cv, 2, 12)
    sun(cv, 24, 8, 3.8, 5, 7.5, n=8, w=1.6, col=LIGHT)


@icon("Mesh Display/Color Material Channel/Ambient+Diffuse")
def i_cmc_ambient_diffuse(cv):
    vset(cv, 2, 12)
    for k in range(8):
        a = 2 * math.pi * k / 8
        cv.line((24 + 5.5 * math.cos(a), 8 + 5.5 * math.sin(a)), (24 + 7.5 * math.cos(a), 8 + 7.5 * math.sin(a)), 1.4,
                LIGHT)
    cv.circle(24, 8, 4.8, LIGHT, ol=True)
    cv.fill(cv.m_circle(24, 8, 4.8) & (cv.x > 24), (0.2, 0.2, 0.2))


@icon("Mesh Display/Color Material Channel/Diffuse")
def i_cmc_diffuse(cv):
    vset(cv, 2, 12)
    cv.fill(cv.m_circle(24, 8, 7), sphere_colour(cv, 24, 8, 7, (0.75, 0.75, 0.75), amb=0.3, dif=0.9), ol=True)


@icon("Mesh Display/Color Material Channel/Emission")
def i_cmc_emission(cv):
    vset(cv, 2, 12)
    cv.ring(24, 8, 6.5, 1.6, LIGHT, ol=True)
    cv.line((24, 0.5), (24, 15.5), 1.6, LIGHT)
    cv.line((16.5, 8), (31.5, 8), 1.6, LIGHT)
    cv.circle(24, 8, 3.2, WHITE, ol=True)


@icon("Mesh Display/Color Material Channel/None")
def i_cmc_none(cv):
    vset(cv, 2, 12)
    nosign(cv, 24, 8, r=6.5, w=1.8)


@icon("Mesh Display/Color Material Channel/Specular")
def i_cmc_specular(cv):
    vset(cv, 2, 12)
    shiny_ball(cv, 24, 8, 7, col=(0.12, 0.12, 0.12), spec=1.0)


@icon("Mesh Display/Color Set Editor")
def i_color_set_editor(cv):
    cv.rect(2, 3, 30, 29, LIGHT, ol=True)
    cv.rect(2, 3, 30, 7, shade(LIGHT, -0.35))
    cv.rect(4, 9, 28, 27, (0.3, 0.3, 0.3))
    vset(cv, 7, 11, 0.95)


@icon("Mesh Display/Conform")
def i_conform(cv):
    hex_cube(cv, 16, 17, 13)
    for p0, p1 in (((16, 2), (16, 11)), ((4, 24), (11, 20)), ((28, 24), (21, 20))):
        arrow(cv, p0, p1, w=1.6, col=ORANGE, head=3.5)


@icon("Mesh Display/Create Empty Set")
def i_create_empty_set(cv):
    vset(cv, 2, 12)
    plus(cv, 24, 8, s=6, w=3.0)


@icon("Mesh Display/Delete Current Set")
def i_delete_current_set(cv):
    vset(cv, 2, 12)
    minus(cv, 24, 8, s=6, w=3.0)


@icon("Mesh Display/Edit Assigned Set")
def i_edit_assigned_set(cv):
    quilt(cv, 14, 22, 1.0)
    pencil(cv, (14, 18), (29, 3), w=5)


@icon("Mesh Display/Harden Edge")
def i_harden_edge(cv):
    cv.poly([(10, 3), (22, 6), (22, 20), (10, 16)], LIGHT, ol=True)
    for i, x in enumerate((14, 18.5, 23, 27.5)):
        cv.poly([(x - 2, 14 + i), (x + 2.5, 12 + i), (x + 2.5, 29), (x - 2, 29)], shade(ORANGE, -0.2 * (i % 2)), ol=True)


@icon("Mesh Display/Lock Normals")
def i_lock_normals(cv):
    normal_line(cv, (22, 27), (5, 10))
    padlock(cv, 17, 2)


@icon("Mesh Display/Unlock Normals")
def i_unlock_normals(cv):
    normal_line(cv, (22, 27), (5, 10))
    padlock(cv, 14, 2, open_=True)


def _blend(cv, mark):
    vset(cv, 1, 1, 0.62)
    vset(cv, 13, 15, 0.82)
    mark()


@icon("Mesh Display/Material Blend Setting/Add")
def i_mbs_add(cv):
    _blend(cv, lambda: plus(cv, 25, 7, s=5.5, w=3.0))


@icon("Mesh Display/Material Blend Setting/Average")
def i_mbs_average(cv):
    def mark():
        cv.line((20, 13), (30, 2), 2.2, LIGHT, ol=True)
        cv.circle(21.5, 3.5, 2.2, LIGHT, ol=True)
        cv.circle(28.5, 11.5, 2.2, LIGHT, ol=True)
    _blend(cv, mark)


@icon("Mesh Display/Material Blend Setting/Divide")
def i_mbs_divide(cv):
    def mark():
        minus(cv, 25, 7.5, s=5.5, w=2.4)
        cv.circle(25, 2.5, 1.8, LIGHT, ol=True)
        cv.circle(25, 12.5, 1.8, LIGHT, ol=True)
    _blend(cv, mark)


@icon("Mesh Display/Material Blend Setting/Modulate 2x")
def i_mbs_modulate(cv):
    def mark():
        asterisk(cv, 19, 7, s=4.5, w=2.0)
        cv.text("2", LIGHT, 25, 3, ol=True, bold=True)
    _blend(cv, mark)


@icon("Mesh Display/Material Blend Setting/Multiply")
def i_mbs_multiply(cv):
    _blend(cv, lambda: asterisk(cv, 25, 7, s=6, w=2.6))


@icon("Mesh Display/Material Blend Setting/Overwrite")
def i_mbs_overwrite(cv):
    _blend(cv, lambda: curved_arrow(cv, 24, 11, 6.5, 190, 330, w=2.4, head=4.5))


@icon("Mesh Display/Material Blend Setting/Subtract")
def i_mbs_subtract(cv):
    _blend(cv, lambda: minus(cv, 25, 7, s=6, w=3.0))


@icon("Mesh Display/Modify Current Set")
def i_modify_current_set(cv):
    vset(cv, 2, 12)
    pencil(cv, (14, 18), (29, 3), w=5)


@icon("Mesh Display/Paint Vertex Color Tool")
def i_paint_vertex_color(cv):
    vset(cv, 2, 12)
    brush(cv, (13, 19), (29, 3), w=3.2, col=LIGHT, bristle=shade(LIGHT, -0.15))


def _instance_rings(cv):
    for cx, cy, s in ((10, 20, 0.5), (20, 11, 0.55)):
        cv.ring(cx, cy, 8.5, 1.4, LIGHT, ol=True)
        vset(cv, cx - 6, cy - 6, s)


@icon("Mesh Display/Per Instance Sharing/Select Shared Instances")
def i_select_shared(cv):
    _instance_rings(cv)
    cursor_white(cv, 20, 15, 1.0)


@icon("Mesh Display/Per Instance Sharing/Share Instances")
def i_share_instances(cv):
    _instance_rings(cv)
    cv.line((14, 15), (17, 18), 2.0, ORANGE, ol=True)


@icon("Mesh Display/Prelight (Maya)")
def i_prelight(cv):
    cv.polyline([(8, 4), (4, 4), (4, 26), (28, 26), (28, 4), (24, 4)], 1.6, LIGHT, ol=True)
    vset(cv, 9, 6, 0.8)
    cv.poly([(12, 26), (20, 26), (16, 31)], LIGHT, ol=True)


@icon("Mesh Display/Rename Current Set...")
def i_rename_current_set(cv):
    vset(cv, 2, 12)
    ibeam(cv, 25, 2, 14)


@icon("Mesh Display/Reverse")
def i_reverse_normals(cv):
    diamond(cv, 14, 12, 11, 6, LIGHT)
    diamond(cv, 20, 20, 11, 6, ORANGE)
    cv.line((14, 1), (14, 12), 1.6, LIGHT, ol=True)
    cv.line((20, 20), (20, 31), 1.6, ORANGE, ol=True)


@icon("Mesh Display/Set Keyframe for Vertex Color")
def i_key_vertex_color(cv):
    vset(cv, 2, 12)
    cv.line((17, 7), (31, 7), 2.0, LIGHT, ol=True, cap=False)
    cv.rect(22, 1, 26, 13, KEY, ol=True)


@icon("Mesh Display/Set Vertex Normal")
def i_set_vertex_normal(cv):
    normal_line(cv, (22, 27), (5, 10))
    sliders(cv, 16, 4, 13)


@icon("Mesh Display/Set to Face")
def i_set_to_face(cv):
    hex_cube(cv, 16, 16, 14)
    for p in ((7, 21), (25, 21), (16, 5)):
        cv.line((16, 16), p, 1.4, ORANGE)
    vsq(cv, 16, 16, 2.6)


@icon("Mesh Display/Soften Edge", "Mesh Display/Soften/Harden Edges")
def i_soften_edge(cv):
    cv.poly([(4, 3), (12, 6), (12, 25), (4, 22)], LIGHT, ol=True)
    cv.fill(cv.m_rect(13, 13, 29, 26) | cv.m_ellipse(21, 26, 8, 3.5), hgrad(cv, 13, 29, ORANGE, 0.2, -0.3))
    cv.fill(cv.m_ellipse(21, 13, 8, 3.5), shade(ORANGE, 0.35))


@icon("Mesh Display/Toggle Display Colors Attribute")
def i_toggle_display_colors(cv):
    vset(cv, 2, 12)
    sliders(cv, 17, 4, 13)


@icon("Mesh Display/Vertex Normal Edit Tool")
def i_vertex_normal_tool(cv):
    curved_arrow(cv, 16, 19, 10, 200, 520, w=2.2, head=4.5)
    cv.line((16, 2), (16, 20), 1.6, ORANGE, ol=True)
    vsq(cv, 16, 22, 3)


# --- Edit Mesh --------------------------------------------------------------------------------

@icon("Edit Mesh/Add Divisions")
def i_add_divisions(cv):
    diamond(cv, 14, 22, 12, 7, LIGHT)
    q = [(14, 8), (26, 15), (14, 22), (2, 15)]
    cv.poly(q, ORANGE, ol=True)
    face_grid(cv, q, 2, DARK)
    plus(cv, 25, 6, s=4.5, w=2.6)


@icon("Edit Mesh/Assign Invisible Faces")
def i_invisible_faces(cv):
    for i, j in ((0, 0), (0, 1), (1, 1)):
        cv.rect(4 + i * 12, 4 + j * 12, 15 + i * 12, 15 + j * 12, LIGHT, ol=True)
    for k in range(0, 11, 2):
        for x, y in ((17 + k, 4), (17 + k, 14), (17, 4 + k), (27, 4 + k)):
            cv.rect(x, y, x + 1, y + 1, ORANGE)


@icon("Edit Mesh/Average Vertices")
def i_average_vertices(cv):
    pts = [(2, 16), (8, 15), (14, 17), (3, 22), (9, 23), (13, 21), (2, 29), (8, 28), (14, 30)]
    for a, b in ((0, 1), (1, 2), (3, 4), (4, 5), (6, 7), (7, 8), (0, 3), (3, 6), (1, 4), (4, 7), (2, 5), (5, 8)):
        cv.line(pts[a], pts[b], 2.4, LIGHT, ol=True)
    squares(cv, 13, 3, 3, 3, 5.5, ORANGE)


@icon("Edit Mesh/Chamfer Vertices")
def i_chamfer_vertices(cv):
    hex_cube(cv, 16, 16, 14, ORANGE)
    cv.poly([(9, 13), (23, 13), (16, 24)], LIGHT, ol=True)


@icon("Edit Mesh/Connect", "Mesh Tools/Connect")
def i_connect(cv):
    top, left, right = cube(cv, 16, 8, 12, 15, ORANGE)
    for t in (0.33, 0.66):        # two edge loops round the box
        cv.line(lerp(right[0], right[1], t), lerp(right[3], right[2], t), 1.4, DARK)
        cv.line(lerp(top[0], top[1], t), lerp(top[3], top[2], t), 1.4, DARK)


@icon("Edit Mesh/Delete Edge/Vertex")
def i_delete_edge_vertex(cv):
    cv.line((10, 4), (10, 28), 1.4, LIGHT)
    for y in (5, 13, 21, 28):
        vsq(cv, 10, y, 2.6)
    xmark(cv, 23, 8, s=4.5, w=2.6)


@icon("Edit Mesh/Detach")
def i_detach(cv):
    top, left, right = cube(cv, 13, 10, 11, 13, LIGHT, faces=(0.2, 0.0, -0.2))
    cv.poly([(p[0] + 5, p[1] + 1) for p in right], ORANGE, ol=True)


@icon("Edit Mesh/Edit Edge Flow")
def i_edit_edge_flow(cv):
    cv.fill(cv.m_ring(5, 30, 25, 1.4) & (cv.x > 5) & (cv.y < 30), LIGHT)
    for p in ((5, 8), (13, 9), (20, 13), (25, 20), (27, 27)):
        vsq(cv, p[0], p[1], 2.4)
    cv.polyline([(5, 8), (13, 9), (20, 13), (25, 20), (27, 27)], 1.2, ORANGE)


@icon("Edit Mesh/Flip")
def i_flip(cv):
    cv.poly([(15, 3), (15, 21), (5, 21)], LIGHT, ol=True)
    cv.poly([(17, 3), (27, 21), (17, 21)], ORANGE, ol=True)
    cv.fill(cv.m_ering(16, 23, 11, 5, 1.8) & (cv.y > 23) & (cv.x < 24), LIGHT, ol=True)
    cv.poly([(29, 23), (22, 25), (24, 30)], LIGHT, ol=True)


@icon("Edit Mesh/Poke")
def i_poke(cv):
    cv.rect(3, 13, 17, 27, LIGHT, ol=True)
    cv.rect(13, 3, 29, 19, ORANGE, ol=True)
    cv.line((13, 3), (29, 19), 1.4, DARK)
    cv.line((29, 3), (13, 19), 1.4, DARK)


@icon("Edit Mesh/Project Curve on Mesh")
def i_project_curve(cv):
    cv.rect(3, 11, 21, 29, ORANGE, ol=True)
    cv.fill(cv.m_ring(3, 29, 15, 1.4) & cv.m_rect(3, 11, 21, 29), shade(ORANGE, 0.45))
    cv.ring(22, 10, 7.5, 1.8, LIGHT, ol=True)


@icon("Edit Mesh/Reorder Vertices")
def i_reorder_vertices(cv):
    numbered_diamond(cv, 16, 16, 10)


@icon("Edit Mesh/Spin Edge Backward")
def i_spin_backward(cv):
    cv.fill(cv.m_ring(16, 16, 12, 2.6) & cv.m_angle(16, 16, 245, 180), ORANGE, ol=True)
    cv.poly([(5, 10), (11, 3), (12, 12)], ORANGE, ol=True)
    cv.line((11, 21), (21, 11), 1.4, LIGHT)


@icon("Edit Mesh/Spin Edge Forward")
def i_spin_forward(cv):
    cv.fill(cv.m_ring(16, 16, 12, 2.6) & cv.m_angle(16, 16, 0, 295), ORANGE, ol=True)
    cv.poly([(27, 10), (21, 3), (20, 12)], ORANGE, ol=True)
    cv.line((11, 11), (21, 21), 1.4, LIGHT)


@icon("Edit Mesh/Split Mesh with Projected Curve")
def i_split_projected(cv):
    cv.rect(3, 11, 21, 29, ORANGE, ol=True)
    cv.fill(cv.m_circle(20, 12, 8) & cv.m_rect(3, 11, 21, 29), LIGHT)
    dashed_ring(cv, 20, 12, 8.5, 1.6)


@icon("Edit Mesh/Symmetrize")
def i_symmetrize(cv):
    cv.fill(cv.m_ellipse(16, 16, 12, 13), hgrad(cv, 4, 28, LIGHT, 0.2, -0.3), ol=True)
    cv.fill(cv.m_ellipse(16, 16, 7, 13) & (cv.x < 16), ORANGE)
    cv.fill(cv.m_ellipse(16, 16, 7, 13) & (cv.x >= 16), shade(ORANGE, -0.2))
    for y in range(1, 31, 4):
        cv.rect(15.5, y, 16.5, y + 2, DARK)


@icon("Edit Mesh/Transform")
def i_transform_components(cv):
    for i, x in enumerate((3, 10, 17, 24)):
        cv.poly([(x, 4 + abs(i - 1.5) * 2), (x + 6, 4 + abs(i - 1.5) * 2 - 1), (x + 6, 16), (x, 16)],
                LIGHT if i in (1, 2) else ORANGE, ol=True)
    arrow(cv, (11, 20), (4, 28), w=2.4, head=4.5)
    arrow(cv, (21, 20), (28, 28), w=2.4, head=4.5)


@icon("Edit Mesh/Wedge")
def i_wedge(cv):
    for k in range(3):
        a0 = math.radians(-20 + k * 30)
        a1 = math.radians(-20 + (k + 1) * 30)
        p = [(10, 22), (10 + 18 * math.cos(a0), 22 + 9 * math.sin(a0)), (10 + 18 * math.cos(a1), 22 + 9 * math.sin(a1))]
        cv.poly(p, shade(LIGHT, -0.1 * k), ol=True)
    cv.poly([(3, 18), (12, 6), (16, 14), (10, 22)], ORANGE, ol=True)


# --- Mesh Tools -------------------------------------------------------------------------------

@icon("Mesh Tools/Append to Polygon")
def i_append_polygon(cv):
    squares(cv, 6, 2, 2, 2, 9, LIGHT)
    cv.rect(6, 20, 15, 26, ORANGE, ol=True)
    vsq(cv, 7, 26, 2.2)
    vsq(cv, 15, 28, 2.2)


@icon("Mesh Tools/Crease Tool", "Mesh/Smooth Proxy/Crease Tool", "Windows/Modeling Editors/Crease Sets")
def i_crease(cv):
    cv.circle(14, 18, 11, ORANGE, ol=True)
    vsq(cv, 26, 6, 2.8, LIGHT)


@icon("Mesh Tools/Create Polygon")
def i_create_polygon(cv):
    cv.poly([(6, 4), (19, 25), (6, 26)], ORANGE, ol=True)
    for p in ((6, 4), (19, 25), (6, 26), (14, 15)):
        vsq(cv, p[0], p[1], 2.2)
    dashed_line(cv, (14, 15), (27, 6))
    dashed_line(cv, (27, 6), (19, 25))
    vsq(cv, 27, 6, 2.0)


@icon("Mesh Tools/Insert Edge Loop")
def i_insert_edge_loop(cv):
    grid_frame(cv)
    cv.line((9, 3), (9, 29), 2.0, ORANGE)
    for y in (12, 20):
        cv.rect(7, y, 11, y + 1, (0.27, 0.27, 0.27))


@icon("Mesh Tools/Make Hole")
def i_make_hole(cv):
    diamond(cv, 15, 15, 13, 13, ORANGE)
    cv.circle(15, 15, 6, (0.27, 0.27, 0.27))
    cv.fill(cv.m_circle(22, 22, 6.5), sphere_colour(cv, 22, 22, 6.5, LIGHT, amb=0.8, dif=0.3), ol=True)


@icon("Mesh Tools/Offset Edge Loop")
def i_offset_edge_loop(cv):
    cv.frame(3, 3, 29, 29, 1.6, LIGHT, ol=True)
    cv.line((16, 3), (16, 29), 1.4, LIGHT)
    for x in (10, 22):
        dashed_line(cv, (x, 4), (x, 28), 2.0, ORANGE, dash=3.0)


@icon("Mesh Tools/Paint Reduce Weights")
def i_paint_reduce(cv):
    squares(cv, 2, 2, 4, 4, 3.5, ORANGE, gap=0.8, ol=False)
    cv.rect(12, 14, 26, 29, LIGHT, ol=True)
    squares(cv, 20, 20, 2, 2, 4, ORANGE, gap=1, ol=False)
    brush(cv, (14, 15), (30, 2), w=3.0, col=LIGHT, bristle=shade(LIGHT, -0.2))


@icon("Mesh Tools/Paint Transfer Attributes")
def i_paint_transfer(cv):
    sliders(cv, 3, 4, 14, ORANGE)
    brush(cv, (5, 28), (28, 9), w=3.4, col=LIGHT, bristle=shade(LIGHT, -0.2))


@icon("Mesh Tools/Slide Edge")
def i_slide_edge(cv):
    cv.frame(3, 5, 22, 29, 1.4, LIGHT, ol=True)
    cv.line((12.5, 5), (12.5, 29), 1.2, LIGHT)
    cv.line((3, 19), (12, 23), 1.2, LIGHT)
    cv.line((13, 23), (22, 23), 2.0, ORANGE)
    arrow(cv, (26, 15), (26, 2), w=2.4, head=4.5)
    arrow(cv, (26, 15), (26, 28), w=2.4, head=4.5)


# --- Mesh -------------------------------------------------------------------------------------

@icon("Mesh/Booleans/Difference (A - B)")
def i_bool_difference(cv):
    cv.fill(cv.m_circle(12, 12, 9.5) & ~cv.m_circle(19, 19, 9.5), ORANGE, ol=True)
    dashed_ring(cv, 19, 19, 9.5, 1.6)


@icon("Mesh/Booleans/Intersection")
def i_bool_intersection(cv):
    dashed_ring(cv, 13, 13, 11, 1.6)
    dashed_ring(cv, 19, 19, 11, 1.6)
    cv.fill(cv.m_circle(13, 13, 9.5) & cv.m_circle(19, 19, 9.5), ORANGE, ol=True)


@icon("Mesh/Booleans/Union")
def i_bool_union(cv):
    cv.fill(cv.m_circle(12, 12, 9.5) | cv.m_circle(19, 19, 9.5), ORANGE, ol=True)
    cv.fill(cv.m_ring(19, 19, 9.5, 1.2) & cv.m_circle(12, 12, 9) & (cv.x + cv.y < 31), shade(ORANGE, -0.35))


@icon("Mesh/Cleanup...")
def i_cleanup(cv):
    q = [(13, 9), (24, 19), (13, 30), (2, 19)]
    cv.poly(q, ORANGE, ol=True)
    face_grid(cv, q, 2, DARK)
    sparkle(cv, 24, 8, 4.5)
    sparkle(cv, 29, 2.5, 2.5)


@icon("Mesh/Clipboard Actions/Clear Clipboard")
def i_clear_clipboard(cv):
    clipboard(cv, 6, 5, 24, 28)
    xmark(cv, 25, 25, s=4, w=2.4)


@icon("Mesh/Clipboard Actions/Copy Attributes")
def i_copy_attributes(cv):
    page(cv, 4, 2, 19, 21)
    page(cv, 12, 10, 27, 30)


@icon("Mesh/Clipboard Actions/Paste Attributes")
def i_paste_attributes(cv):
    clipboard(cv, 7, 5, 25, 29)


@icon("Mesh/Fill Hole")
def i_fill_hole(cv):
    diamond(cv, 16, 16, 14, 14, LIGHT)
    cv.circle(16, 16, 6.5, ORANGE, ol=True)


@icon("Mesh/Quadrangulate")
def i_quadrangulate(cv):
    cv.rect(3, 13, 17, 28, LIGHT, ol=True)
    cv.poly([(3, 13), (17, 28), (3, 28)], shade(LIGHT, -0.3))
    cv.line((3, 13), (17, 28), 1.2, DARK)
    cv.rect(13, 3, 29, 19, ORANGE, ol=True)


@icon("Mesh/Separate")
def i_separate(cv):
    diamond(cv, 16, 11, 9, 5, LIGHT)
    diamond(cv, 16, 19, 9, 5, ORANGE)
    cv.fill(cv.m_ring(16, 15, 13, 1.6) & ((cv.x < 6) | (cv.x > 26)), LIGHT, ol=True)


@icon("Mesh/Smooth Proxy/Both Proxy and Subdiv Display")
def i_proxy_both(cv):
    proxy_cube(cv)
    from .shelf_icons import eye as _eye
    _eye(cv, 24, 7, s=6)


@icon("Mesh/Smooth Proxy/Remove Subdiv Proxy Mirror")
def i_proxy_remove_mirror(cv):
    proxy_cube(cv)
    xmark(cv, 25, 6, s=4, w=2.4)


@icon("Mesh/Smooth Proxy/Subdiv Proxy")
def i_subdiv_proxy(cv):
    proxy_cube(cv, 16, 17, 13)


@icon("Mesh/Smooth Proxy/Toggle Proxy Display")
def i_proxy_toggle(cv):
    hex_cube(cv, 11, 22, 8, LIGHT, wire=True)
    cv.poly([(24, 2), (29, 5), (29, 11), (24, 14), (19, 11), (19, 5)], ORANGE, ol=True)


@icon("Mesh/Transfer Attributes")
def i_transfer_attributes(cv):
    sliders(cv, 3, 4, 13)
    down_arrow(cv, 25, 2, 13)
    quilt(cv, 15, 23, 1.0, base=ORANGE, col=shade(ORANGE, 0.3))


@icon("Mesh/Transfer Shading Sets")
def i_transfer_shading(cv):
    shiny_ball(cv, 10, 9, 7.5, col=(0.4, 0.4, 0.4))
    down_arrow(cv, 25, 2, 13)
    quilt(cv, 15, 23, 1.0, base=ORANGE, col=shade(ORANGE, 0.3))


@icon("Mesh/Transfer Vertex Order")
def i_transfer_vertex_order(cv):
    numbered_diamond(cv, 14, 17, 6.5)
    page(cv, 22, 1, 30, 11, LIGHT)
    page(cv, 25, 4, 31, 13, LIGHT)


@icon("Mesh/Triangulate")
def i_triangulate(cv):
    cv.rect(3, 13, 17, 28, LIGHT, ol=True)
    cv.rect(13, 3, 29, 19, ORANGE, ol=True)
    cv.poly([(29, 3), (29, 19), (13, 19)], shade(ORANGE, -0.3))
    cv.line((13, 3), (29, 19), 1.4, DARK)
