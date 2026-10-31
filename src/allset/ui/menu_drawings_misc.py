# SPDX-License-Identifier: GPL-3.0-or-later
"""Kit menu pictures for UV, Windows, Playback, Constrain, Key, Visualize, Edit, Texturing, Toon, Generate, Stereo and
Render (#54) — see ``menu_drawings``."""

import math

import numpy as np

from .menu_drawings import FGREEN, RED, TAN, blob, icon, prune_mark
from .menu_drawings_fx import example_box, trash
from .menu_drawings_mesh import cursor_white, dashed_ring, page, vsq
from .menu_drawings_select import OLIVE
from .shelf_icons import (DARK, GREEN, KEY, LAV, LIGHT, TEAL, WHITE, YELLOW, _hex, arrow, bezier,
                          brush, check, checker, curved_arrow, face_grid, hgrad, lerp, link, pencil, plus,
                          shade, sphere_colour, wave_pts, window, xmark)

ED_ORANGE = _hex("#e0683a")     # Maya's animation editor windows
UVG = GREEN
BRUSH_WOOD = _hex("#8a5a3a")
BRUSH_TIP = _hex("#e8e0c8")


def pfx_brush(cv, tip, end, w=3.0):
    brush(cv, tip, end, w=w, col=BRUSH_WOOD, bristle=BRUSH_TIP)


def toon_ball(cv, cx=16, cy=16, r=12, col=WHITE, outline=1.4, amb=0.9, dif=0.25):
    cv.fill(cv.m_circle(cx, cy, r + outline), (0.05, 0.05, 0.05))
    cv.fill(cv.m_circle(cx, cy, r), sphere_colour(cv, cx, cy, r, col, amb=amb, dif=dif))


def shade_split(cv, cx, cy, r, c0, c1, k=0.0):
    """A flat two-tone toon ball split along a diagonal (light upper left)."""
    cv.fill(cv.m_circle(cx, cy, r + 1.4), (0.05, 0.05, 0.05))
    m = cv.m_circle(cx, cy, r)
    cv.fill(m, c1)
    cv.fill(m & ((cv.x - cx) + (cv.y - cy) < k * r), c0)


# --- UV ---------------------------------------------------------------------------------------

def uv_checker(cv, x, y, s=9):
    checker(cv, x, y, s=s, n=3)


@icon("UV/Assign Checker Shader")
def i_uv_checker_shader(cv):
    q = [(3, 13), (16, 5), (29, 13), (16, 21)]
    cv.poly(q, OLIVE, ol=True)
    face_grid(cv, q, 2, (0.25, 0.24, 0.18))
    cv.rect(17, 17, 30, 30, WHITE, ol=True)
    check(cv, 23.5, 23.5, s=4.5, w=2.2, col=FGREEN)


@icon("UV/Auto Seams")
def i_uv_auto_seams(cv):
    cv.polyline([(5, 28), (5, 4), (24, 4), (24, 14)], 1.4, UVG, ol=True)
    for p in ((14, 12), (6, 26), (20, 26)):         # seams fanning out of a cut point
        cv.line((14, 4), p, 1.2, LIGHT)
    cv.circle(24, 23, 6.5, LIGHT, ol=True)
    cv.text("A", DARK, 21.5, 19.5)


@icon("UV/Best Plane")
def i_uv_best_plane(cv):
    cv.poly([(3, 18), (14, 13), (25, 18), (14, 23)], LIGHT, ol=True)
    cv.poly([(3, 11), (14, 5), (25, 11), (14, 16)], UVG, ol=True)
    uv_checker(cv, 20, 20)


@icon("UV/Camera-based")
def i_uv_camera(cv):
    cv.rect(10, 3, 22, 12, LIGHT, ol=True)
    cv.poly([(22, 7.5), (29, 3), (29, 12)], LIGHT, ol=True)
    cv.poly([(4, 21), (15, 15), (15, 27)], UVG, ol=True)
    cv.poly([(15, 15), (19, 18), (19, 25), (15, 27)], shade(UVG, -0.3))
    uv_checker(cv, 20, 20)


@icon("UV/Cut UV Edges")
def i_uv_cut(cv):
    cv.rect(9, 3, 14, 29, UVG, ol=True)
    cv.rect(18, 3, 23, 29, UVG, ol=True)
    arrow(cv, (12, 16), (3, 16), w=2.6, head=5)
    arrow(cv, (20, 16), (29, 16), w=2.6, head=5)


@icon("UV/Sew UV Edges")
def i_uv_sew(cv):
    cv.rect(4, 3, 9, 29, UVG, ol=True)
    cv.rect(23, 3, 28, 29, UVG, ol=True)
    arrow(cv, (9, 16), (16, 16), w=2.6, head=5)
    arrow(cv, (23, 16), (16.5, 16), w=2.6, head=5)


@icon("UV/Delete UVs")
def i_uv_delete(cv):
    cv.polyline([(6, 12), (18, 12), (18, 25), (6, 25), (6, 12)], 1.2, LIGHT)
    for p in ((6, 12), (18, 12), (6, 25), (18, 25), (12, 12), (12, 25)):
        vsq(cv, p[0], p[1], 2.2, UVG)
    xmark(cv, 25, 6, s=4.5, w=2.6)


@icon("UV/Merge UVs")
def i_uv_merge(cv):
    cv.frame(4, 6, 28, 26, 1.4, LIGHT, ol=True)
    cv.line((4, 16), (28, 16), 1.2, LIGHT)
    for p in ((5, 16), (27, 16)):
        vsq(cv, p[0], p[1], 2.0, LIGHT)
    vsq(cv, 16, 16, 3.0, UVG)


@icon("UV/Normal-Based")
def i_uv_normal(cv):
    cv.poly([(3, 15), (17, 8), (29, 15), (17, 22)], UVG, ol=True)
    cv.line((17, 2), (17, 15), 2.2, LIGHT, ol=True)
    uv_checker(cv, 20, 20)


@icon("UV/Split UVs")
def i_uv_split(cv):
    cv.polyline([(14, 30), (14, 14), (30, 14)], 1.4, LIGHT, ol=True)
    cv.polyline([(2, 18), (18, 18), (18, 2)], 1.4, LIGHT, ol=True)
    arrow(cv, (20, 12), (29, 3), w=2.4, head=5)
    arrow(cv, (12, 20), (3, 29), w=2.4, col=UVG, head=5)


@icon("UV/UV Set Editor")
def i_uv_set_editor(cv):
    def body(x0, y0, x1, y1):
        cv.frame(x0 + 4, y0, x1, y1 - 4, 1.2, WHITE)
        cv.rect(x0, y0 + 4, x1 - 6, y1, shade(UVG, -0.2))
        cv.frame(x0, y0 + 4, x1 - 6, y1, 1.2, WHITE)
        checker(cv, x0 + 4, y0 + 8, s=8, n=3)
    window(cv, 2, 2, 30, 30, UVG, body, title=LIGHT)


# --- Windows ----------------------------------------------------------------------------------

def _ed(cv, col, body, title=LIGHT):
    window(cv, 2, 4, 30, 28, col, body, title=title)


@icon("Windows/Animation Editors/Dope Sheet")
def i_win_dope_sheet(cv):
    def body(x0, y0, x1, y1):
        cv.rect(x0 + 1, y0 + 2, x1 - 1, y1 - 2, (0.25, 0.25, 0.25))
        for i in range(5):
            for j in range(2):
                cv.rect(x0 + 3 + i * 4.5, y0 + 4 + j * 6, x0 + 4.5 + i * 4.5, y0 + 7 + j * 6, LIGHT)
    _ed(cv, ED_ORANGE, body)


@icon("Windows/Animation Editors/Graph Editor")
def i_win_graph_editor(cv):
    def body(x0, y0, x1, y1):
        cv.polyline(bezier((x0 + 1, y1 - 3), (x0 + 8, y0 - 6), (x0 + 12, y1 + 6), (x1 - 1, y0 + 2), 20), 2.2, LIGHT,
                    ol=True)
    _ed(cv, ED_ORANGE, body)


@icon("Windows/Animation Editors/Time Editor")
def i_win_time_editor(cv):
    def body(x0, y0, x1, y1):
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        cv.circle(cx, cy, 7, LIGHT, ol=True)
        cv.line((cx, cy), (cx, cy - 5), 1.4, DARK)
        cv.line((cx, cy), (cx + 3.5, cy), 1.4, DARK)
    _ed(cv, ED_ORANGE, body)


@icon("Windows/Animation Editors/Trax Editor")
def i_win_trax(cv):
    def body(x0, y0, x1, y1):
        cv.rect(x0 + 1, y0 + 2, x0 + 15, y0 + 7, LIGHT, ol=True)
        cv.rect(x0 + 8, y0 + 11, x1 - 1, y0 + 16, LIGHT, ol=True)
    _ed(cv, ED_ORANGE, body)


@icon("Windows/General Editors/Hypergraph: Connections", "Windows/General Editors/Hypergraph: Hierarchy")
def i_win_hypergraph(cv):
    def body(x0, y0, x1, y1):
        cv.rect(x0, y0, x1, y1, (0.22, 0.22, 0.22))
        for k, (x, y) in enumerate(((x0 + 2, y0 + 2), (x0 + 7, y0 + 7), (x0 + 12, y0 + 12))):
            cv.rect(x, y, x + 8, y + 4, TEAL)
            if k:
                cv.polyline([(x - 3, y - 1), (x - 3, y + 2), (x, y + 2)], 1.0, LIGHT)
    _ed(cv, LIGHT, body, title=shade(LIGHT, -0.3))


@icon("Windows/General Editors/Script Editor")
def i_win_script_editor(cv):
    window(cv, 4, 2, 28, 30, LIGHT, None, title=shade(LIGHT, -0.4))     # "{;}" in a grey window
    cv.polyline([(13, 11), (11, 12), (11, 15), (9.5, 16.5), (11, 18), (11, 21), (13, 22)], 1.4, DARK)
    cv.polyline([(19, 11), (21, 12), (21, 15), (22.5, 16.5), (21, 18), (21, 21), (19, 22)], 1.4, DARK)
    cv.rect(15.3, 13, 16.7, 14.4, DARK)
    cv.rect(15.3, 18, 16.7, 19.4, DARK)
    cv.rect(15.3, 19.4, 16, 21, DARK)


@icon("Windows/Home")
def i_win_home(cv):
    cv.poly([(16, 4), (29, 16), (25, 16), (25, 28), (19, 28), (19, 20), (13, 20), (13, 28), (7, 28), (7, 16), (3, 16)],
            LIGHT, ol=True)


@icon("Windows/Modeling Editors/XGen Editor", "Generate/XGen Editor")
def i_win_xgen(cv):
    def body(x0, y0, x1, y1):
        cv.line((x0 + 3, y0 + 1), (x1 - 3, y1 - 1), 3.0, (0.2, 0.2, 0.2))
        cv.line((x1 - 3, y0 + 1), (x0 + 3, y1 - 1), 3.0, (0.2, 0.2, 0.2))
    _ed(cv, _hex("#4cae5a"), body)


# --- Playback ---------------------------------------------------------------------------------

def tri(cv, x, y, s, d=1, col=LIGHT):
    cv.poly([(x, y - s), (x + d * s * 1.2, y), (x, y + s)], col, ol=True)


def bar(cv, x, y, h, col=LIGHT, w=2.2):
    cv.rect(x - w / 2, y - h, x + w / 2, y + h, col, ol=True)


@icon("Playback/Backward")
def i_pb_backward(cv):
    tri(cv, 22, 16, 9, -1)


@icon("Playback/Play")
def i_pb_play(cv):
    tri(cv, 10, 16, 9, 1)


@icon("Playback/Next Frame")
def i_pb_next_frame(cv):
    tri(cv, 10, 16, 7, 1)
    bar(cv, 21, 16, 7)


@icon("Playback/Prev Frame")
def i_pb_prev_frame(cv):
    tri(cv, 22, 16, 7, -1)
    bar(cv, 11, 16, 7)


@icon("Playback/Next Key")
def i_pb_next_key(cv):
    tri(cv, 8, 16, 7, 1)
    cv.line((21, 5), (21, 27), 1.2, LIGHT)
    bar(cv, 21, 16, 7, KEY, w=3.2)


@icon("Playback/Prev Key")
def i_pb_prev_key(cv):
    tri(cv, 24, 16, 7, -1)
    cv.line((11, 5), (11, 27), 1.2, LIGHT)
    bar(cv, 11, 16, 7, KEY, w=3.2)


@icon("Playback/Play Range End")
def i_pb_range_end(cv):
    tri(cv, 4, 16, 6, 1)
    tri(cv, 13, 16, 6, 1)
    bar(cv, 24, 16, 7)


@icon("Playback/Play Range Start")
def i_pb_range_start(cv):
    tri(cv, 28, 16, 6, -1)
    tri(cv, 19, 16, 6, -1)
    bar(cv, 8, 16, 7)


def _loop(cv, cx=14, cy=14):
    cv.fill(cv.m_capsule_ring((cx - 5, cy), (cx + 5, cy), 7, 2.4) & ~cv.m_rect(cx - 2, cy + 4, cx + 3, cy + 8), LIGHT,
            ol=True)
    cv.poly([(cx - 3, cy + 6), (cx + 1, cy + 2.5), (cx + 1, cy + 9.5)], LIGHT, ol=True)


@icon("Playback/Playback Looping/Continuous")
def i_pb_continuous(cv):
    _loop(cv, 16, 16)


@icon("Playback/Playback Looping/Once")
def i_pb_once(cv):
    _loop(cv, 12, 12)
    cv.circle(23, 23, 6.5, LIGHT, ol=True)
    cv.text("1", DARK, 20.5, 19.5)


@icon("Playback/Playback Looping/Oscillate")
def i_pb_oscillate(cv):
    _loop(cv, 12, 12)
    cv.circle(23, 23, 7.5, (0.2, 0.2, 0.2), ol=True)
    cv.ring(23, 23, 7.5, 1.4, LIGHT)
    arrow(cv, (23, 20.5), (17.5, 20.5), w=1.4, head=3, ol=False)
    arrow(cv, (23, 25.5), (28.5, 25.5), w=1.4, head=3, ol=False)


@icon("Playback/Stop")
def i_pb_stop(cv):
    cv.rect(7, 7, 25, 25, _hex("#d03a3a"), ol=True)


# --- Constrain --------------------------------------------------------------------------------

def _axes_l(cv):
    cv.polyline([(5, 4), (5, 27), (27, 27)], 2.0, LIGHT, ol=True)


@icon("Constrain/Geometry")
def i_con_geometry(cv):
    cv.fill(cv.m_ellipse(13, 18, 9, 11, -20), hgrad(cv, 4, 22, LIGHT, 0.2, -0.3), ol=True)
    blob(cv, 9, 20, 5.5, LAV)
    link(cv, 24, 8, 1.05)


@icon("Constrain/Motion Paths/Attach to Motion Path")
def i_con_motion_path(cv):
    _axes_l(cv)
    cv.poly([(8, 18), (14, 13), (21, 21), (15, 26)], LAV, ol=True)
    link(cv, 24, 8, 1.05)


@icon("Constrain/Motion Paths/Flow Path Object")
def i_con_flow_path(cv):
    _axes_l(cv)
    for k in range(3):
        cv.fill(cv.m_ring(5, 27, 17 - k * 4, 3.0) & (cv.x > 6) & (cv.y < 26), shade(LAV, -0.15 * k), ol=True)
    link(cv, 24, 8, 1.05)


@icon("Constrain/Motion Paths/Set Motion Path Key")
def i_con_path_key(cv):
    _axes_l(cv)
    blob(cv, 11, 21, 5, LAV)
    cv.line((16, 9), (30, 9), 1.6, LIGHT, ol=True)
    cv.rect(21.5, 3, 24, 15, LIGHT, ol=True)


@icon("Constrain/Normal")
def i_con_normal(cv):
    cv.poly([(16, 12), (29, 20), (16, 28), (3, 20)], LIGHT, ol=True)
    for p0, p1 in (((16, 12), (16, 3)), ((4, 20), (4, 14)), ((16, 28), (16, 22))):
        cv.line(p0, p1, 1.6, LAV, ol=True)
    link(cv, 24, 8, 1.05)


@icon("Constrain/Point On Poly")
def i_con_point_on_poly(cv):
    cv.poly([(16, 12), (29, 20), (16, 28), (3, 20)], LIGHT, ol=True)
    cv.frame(13, 17, 19, 23, 1.6, LAV, ol=True)
    link(cv, 24, 8, 1.05)


@icon("Constrain/Tangent")
def i_con_tangent(cv):
    cv.polyline(bezier((5, 29), (6, 8), (22, 8), (24, 29), 20), 2.0, LIGHT, ol=True)
    cv.line((4, 8), (14, 8), 1.2, LIGHT)
    vsq(cv, 4, 8, 1.6, LIGHT)
    vsq(cv, 14, 8, 2.2, LIGHT)
    link(cv, 24, 8, 1.05)


# --- Key > Scene Time Warp --------------------------------------------------------------------

def _time_warp(cv, cx=13, cy=17):
    for r in (12, 9):
        cv.ring(cx, cy, r, 1.4, LAV, ol=True)
    cv.circle(cx, cy, 6.5, LIGHT, ol=True)
    cv.line((cx, cy), (cx, cy - 4.5), 1.2, DARK)
    cv.line((cx, cy), (cx + 3.5, cy), 1.2, DARK)


@icon("Key/Scene Time Warp/Add Scene Time Warp")
def i_tw_add(cv):
    _time_warp(cv)
    plus(cv, 25, 6, s=5, w=2.6)


@icon("Key/Scene Time Warp/Delete Scene Time Warp")
def i_tw_delete(cv):
    _time_warp(cv)
    xmark(cv, 25, 6, s=4, w=2.6)


@icon("Key/Scene Time Warp/Enable Scene Time Warp")
def i_tw_enable(cv):
    _time_warp(cv)
    cv.frame(19, 1, 30, 12, 1.4, LIGHT, ol=True)
    check(cv, 24.5, 6.5, s=4, w=2.0)


@icon("Key/Scene Time Warp/Select Scene Time Warp")
def i_tw_select(cv):
    _time_warp(cv)
    cursor_white(cv, 19, 16, 1.0)


# --- Visualize --------------------------------------------------------------------------------

def runner(cv, cx, cy, s=1.0, col=LIGHT):
    """A running figure (Maya's animation snapshot pictures)."""
    cv.circle(cx + 2 * s, cy - 9 * s, 2.6 * s, col, ol=True)
    for a, b in (((cx + 1 * s, cy - 6 * s), (cx - 1 * s, cy + 2 * s)), ((cx - 1 * s, cy + 2 * s), (cx + 4 * s, cy + 6 * s)),
                 ((cx + 4 * s, cy + 6 * s), (cx + 3 * s, cy + 11 * s)), ((cx - 1 * s, cy + 2 * s), (cx - 5 * s, cy + 10 * s)),
                 ((cx + 1 * s, cy - 5 * s), (cx + 6 * s, cy - 1 * s)), ((cx + 1 * s, cy - 5 * s), (cx - 5 * s, cy - 2 * s))):
        cv.line(a, b, 2.6 * s, col, ol=True)


@icon("Visualize/Create Animated Sweep")
def i_vis_sweep(cv):
    for k in range(3):
        y = 10 + k * 7
        for x in range(4 + k, 22 - k, 4):
            cv.rect(x, y + 0.5 * math.sin(x), x + 2.5, y + 2.5, LAV, ol=True)
    arrow(cv, (18, 7), (29, 7), w=2.2, head=4)


@icon("Visualize/Create Animation Snapshot")
def i_vis_snapshot(cv):
    for k in range(3):
        cv.rect(3 + k * 3, 12, 5 + k * 3, 26, LAV, alpha=0.5 + 0.2 * k)
    runner(cv, 20, 16)


@icon("Visualize/Create Turntable...")
def i_vis_turntable(cv):
    cv.fill(cv.m_ellipse(16, 20, 12, 4.5), LAV, ol=True)
    cv.fill(cv.m_rect(4, 20, 28, 25) | cv.m_ellipse(16, 25, 12, 4.5), shade(LAV, -0.3))
    cv.fill(cv.m_ellipse(16, 20, 12, 4.5), LAV)
    cv.rect(8, 2, 15, 8, LIGHT, ol=True)
    cv.poly([(15, 5), (19, 2), (19, 8)], LIGHT, ol=True)
    cv.fill(cv.m_ering(20, 25, 8, 4, 2.0) & (cv.y > 25), LIGHT, ol=True)


@icon("Visualize/Update Snapshot")
def i_vis_update_snapshot(cv):
    curved_arrow(cv, 9, 9, 6, 180, 420, w=2.0, head=4)
    for k in range(2):
        cv.rect(6 + k * 3, 17, 8 + k * 3, 28, LAV, alpha=0.6 + 0.2 * k)
    runner(cv, 21, 17)


# --- Edit > LOD -------------------------------------------------------------------------------

def _lod(cv, col=_hex("#78c8f0"), grid=(0.15, 0.15, 0.15)):
    for (x, y), n in zip(((2, 2), (17, 2), (2, 17), (17, 17)), (1, 2, 3, 4)):
        cv.rect(x, y, x + 13, y + 13, col, ol=True)
        for i in range(1, n):
            cv.line((x + 13 * i / n, y), (x + 13 * i / n, y + 13), 1.0, grid)
            cv.line((x, y + 13 * i / n), (x + 13, y + 13 * i / n), 1.0, grid)


@icon("Edit/LOD (Level of Detail)/Create LOD Group", "Edit/LOD (Level of Detail)/Generate LOD Meshes")
def i_lod_group(cv):
    _lod(cv)


@icon("Edit/LOD (Level of Detail)/Ungroup LOD Group")
def i_lod_ungroup(cv):
    _lod(cv, (0.42, 0.42, 0.42), (0.3, 0.3, 0.3))
    trash(cv, 11, 9, 1.0)


# --- Texturing --------------------------------------------------------------------------------

def psd(cv, mark=None):
    cv.rect(10, 3, 30, 18, WHITE, ol=True)
    cv.rect(11.5, 4.5, 28.5, 16.5, _hex("#2a6ad0"))
    cv.fill(cv.m_ellipse(22, 17, 9, 7) & cv.m_rect(11.5, 4.5, 28.5, 16.5), _hex("#3aa04a"))
    cv.fill(cv.m_ellipse(25, 14, 5, 6) & cv.m_rect(11.5, 4.5, 28.5, 16.5), _hex("#d8c840"))
    cv.text("PSD", WHITE, 2, 22, ol=True)
    cv.line((24, 18), (24, 26), 1.2, LIGHT)
    cv.line((24, 26), (31, 26), 1.2, LIGHT)
    cv.rect(22.5, 24.5, 25.5, 27.5, YELLOW, ol=True)


def tex_ball(cv, cx=15, cy=17, r=10):
    m = cv.m_circle(cx, cy, r)
    dx, dy = (cv.x - cx) / r, (cv.y - cy) / r
    u = np.arctan2(dx, np.sqrt(np.clip(1 - dx * dx - dy * dy, 0, 1))) * 4 / math.pi
    v = np.arcsin(np.clip(dy, -1, 1)) * 4 / math.pi
    cell = ((np.floor(u * 1.5) + np.floor(v * 1.5)) % 2).astype(bool)
    shade_px = sphere_colour(cv, cx, cy, r, (1, 1, 1), amb=0.75, dif=0.35)
    cv.fill(m, np.where(cell[..., None], shade_px * 0.15, shade_px), ol=True)


def yellow_star(cv, cx, cy):
    for a in range(0, 180, 45):
        ra = math.radians(a)
        cv.line((cx - 4.5 * math.cos(ra), cy - 4.5 * math.sin(ra)), (cx + 4.5 * math.cos(ra), cy + 4.5 * math.sin(ra)),
                1.8, _hex("#e8e040"), ol=True)


@icon("Texturing/Create PSD Network...")
def i_psd_create(cv):
    psd(cv)
    yellow_star(cv, 6, 6)


@icon("Texturing/Edit PSD Network...")
def i_psd_edit(cv):
    psd(cv)
    pencil(cv, (8, 12), (2, 1), w=3.5, col=_hex("#e0a040"))


@icon("Texturing/Update PSD Networks")
def i_psd_update(cv):
    psd(cv)
    curved_arrow(cv, 6, 8, 5, 200, 470, w=2.0, col=FGREEN, head=3.5)


@icon("Texturing/Create Texture Reference Object")
def i_texref_create(cv):
    tex_ball(cv, 16, 19, 11)
    yellow_star(cv, 6, 6)


@icon("Texturing/Delete Texture Reference Object")
def i_texref_delete(cv):
    tex_ball(cv, 13, 13, 10)
    trash(cv, 18, 17)


@icon("Texturing/Select Texture Reference Object")
def i_texref_select(cv):
    tex_ball(cv, 13, 13, 10)
    prune_mark(cv, 19, 16)


@icon("Texturing/NURBS Texture Placement Tool")
def i_nurbs_texture_placement(cv):
    cv.poly([(2, 22), (14, 8), (30, 12), (18, 28)], _hex("#5a8ac8"), ol=True)
    q = [(6, 12), (20, 4), (26, 18), (12, 26)]
    cv.poly(q, WHITE, ol=True)
    for i in range(4):
        for j in range(4):
            if (i + j) % 2:
                a, b, c, d = q
                p = [lerp(lerp(a, b, (i + s) / 4), lerp(d, c, (i + s) / 4), (j + t) / 4)
                     for s, t in ((0, 0), (1, 0), (1, 1), (0, 1))]
                cv.poly(p, (0.08, 0.08, 0.08))


# --- Toon -------------------------------------------------------------------------------------

@icon("Toon/Assign Fill Shader/Circle Highlight")
def i_toon_circle_highlight(cv):
    cv.fill(cv.m_circle(16, 16, 13), sphere_colour(cv, 16, 16, 13, _hex("#d02a2a"), amb=0.8, dif=0.3, bands=2))
    cv.circle(10, 10, 3.5, _hex("#ffb0b0"))


@icon("Toon/Assign Fill Shader/Dark Profile")
def i_toon_dark_profile(cv):
    shade_split(cv, 16, 16, 11.5, WHITE, (0.75, 0.75, 0.75), 0.3)
    cv.ring(16, 16, 13, 2.6, (0.05, 0.05, 0.05))


@icon("Toon/Assign Fill Shader/Light Angle Two Tone")
def i_toon_light_angle(cv):
    m = cv.m_circle(16, 16, 13)
    cv.fill(m, (0.6, 0.6, 0.6))
    cv.fill(m & ((cv.x - 16) + (cv.y - 16) < 0), WHITE)


@icon("Toon/Assign Fill Shader/Rim Light")
def i_toon_rim_light(cv):
    cv.circle(16, 16, 13, WHITE)
    cv.circle(16, 16, 11, (0.2, 0.2, 0.2))
    cv.fill(cv.m_circle(16, 16, 11) & ((cv.x - 16) + (cv.y - 16) < -2), (0.45, 0.45, 0.45))


@icon("Toon/Assign Fill Shader/Shaded Brightness Three Tone")
def i_toon_three_tone(cv):
    m = cv.m_circle(16, 16, 13)
    s = (cv.x - 16) + (cv.y - 16)
    cv.fill(m, _hex("#8a1a1a"))
    cv.fill(m & (s < 4), _hex("#d84a4a"))
    cv.fill(m & (s < -10), _hex("#f0c0a8"))


@icon("Toon/Assign Fill Shader/Shaded Brightness Two Tone")
def i_toon_two_tone(cv):
    m = cv.m_circle(16, 16, 13)
    cv.fill(m, (0.62, 0.62, 0.62))
    cv.fill(m & ((cv.x - 16) + (cv.y - 16) < -6), (0.92, 0.92, 0.92))


@icon("Toon/Assign Fill Shader/Solid Color")
def i_toon_solid(cv):
    cv.circle(16, 16, 13, WHITE)


@icon("Toon/Assign Paint Effects Brush to Toon Lines")
def i_toon_pfx_brush(cv):
    toon_ball(cv, 14, 17, 10, outline=2.4)
    pfx_brush(cv, (14, 22), (30, 3))


@icon("Toon/Convert Toon To Polygons")
def i_toon_to_poly(cv):
    toon_ball(cv, 10, 9, 7.5, outline=2.0)
    arrow(cv, (6, 20), (13, 27), w=2.2, col=RED, head=4.5)
    cv.ring(22, 22, 8.5, 3.0, TAN, ol=True)
    cv.circle(22, 22, 5.5, WHITE)


@icon("Toon/Create Modifier", "Generate/Create Modifier")
def i_toon_modifier(cv):
    cv.fill(cv.m_ellipse(16, 22, 10, 9) & (cv.y > 14), sphere_colour(cv, 16, 18, 12, WHITE, amb=0.9, dif=0.2), ol=True)
    cv.rect(9, 12, 23, 16, (0.1, 0.1, 0.1))
    cv.fill(cv.m_ering(16, 14, 12, 4, 1.6), _hex("#2aa83a"))
    cv.fill(cv.m_ering(16, 13, 7, 12, 1.6), _hex("#d02a2a"))
    cv.fill(cv.m_ering(16, 13, 4.5, 12, 1.6), _hex("#2a3ad0"))


@icon("Toon/Get Toon Example...")
def i_toon_example(cv):
    def body(x0, y0, x1, y1):
        for y in (y0 + 5, y0 + 14):
            cv.ring((x0 + x1) / 2, y, 3.5, 1.4, (0.25, 0.25, 0.25))
    example_box(cv, body)


def _line_attr(cv, kind):
    if kind == "border":
        cv.fill(cv.m_ering(13, 9, 10, 4, 3.0), _hex("#e0602a"), ol=True)
        cv.fill(cv.m_rect(3, 9, 23, 22) | cv.m_ellipse(13, 22, 10, 4), WHITE, ol=True)
        cv.fill(cv.m_ellipse(13, 9, 8, 2.5), (0.1, 0.1, 0.1))
    elif kind == "crease":
        cv.fill(cv.m_rect(3, 9, 23, 22) | cv.m_ellipse(13, 22, 10, 4), WHITE, ol=True)
        cv.fill(cv.m_ering(13, 15, 10, 4, 3.0), _hex("#e0602a"))
        cv.fill(cv.m_ellipse(13, 9, 10, 4), (0.1, 0.1, 0.1))
        cv.fill(cv.m_ellipse(13, 9, 8, 2.5), WHITE)
    elif kind == "profile":
        cv.fill(cv.m_rect(3, 9, 23, 22) | cv.m_ellipse(13, 22, 10, 4), _hex("#e0602a"), ol=True)
        cv.fill(cv.m_rect(5, 10, 21, 21) | cv.m_ellipse(13, 21, 8, 3), WHITE)
        cv.fill(cv.m_ellipse(13, 9, 8, 2.5), (0.1, 0.1, 0.1))
    elif kind == "offset":
        cv.ring(12, 13, 9, 2.2, (0.05, 0.05, 0.05))
        toon_ball(cv, 11, 12, 5.5, outline=0.6)
    elif kind == "opacity":
        cv.circle(13, 13, 11, (0.05, 0.05, 0.05), alpha=0.45)
        toon_ball(cv, 13, 13, 8.5, outline=0.6)
    elif kind == "width":
        toon_ball(cv, 13, 13, 8, outline=3.2)
    pfx_brush(cv, (14, 27), (30, 8))


@icon("Toon/Paint Line Attributes/Border Color")
def i_toon_border_color(cv):
    _line_attr(cv, "border")


@icon("Toon/Paint Line Attributes/Crease Color")
def i_toon_crease_color(cv):
    _line_attr(cv, "crease")


@icon("Toon/Paint Line Attributes/Line Offset")
def i_toon_line_offset(cv):
    _line_attr(cv, "offset")


@icon("Toon/Paint Line Attributes/Line Opacity")
def i_toon_line_opacity(cv):
    _line_attr(cv, "opacity")


@icon("Toon/Paint Line Attributes/Line Width")
def i_toon_line_width(cv):
    _line_attr(cv, "width")


@icon("Toon/Paint Line Attributes/Profile Color")
def i_toon_profile_color(cv):
    _line_attr(cv, "profile")


@icon("Toon/Reverse Surfaces")
def i_toon_reverse(cv):
    toon_ball(cv, 11, 10, 7.5, outline=1.8)
    cv.circle(22, 21, 9, _hex("#8a3ac8"))
    toon_ball(cv, 22, 21, 6.5, outline=0.6)
    arrow(cv, (12, 23), (4, 28), w=1.8, col=RED, head=3.5)
    arrow(cv, (8, 26), (15, 21), w=1.8, col=RED, head=3.5)


# --- Generate ---------------------------------------------------------------------------------

def frond(cv, x0, y0, h=18, col=_hex("#3aa84a")):
    cv.polyline(bezier((x0, y0), (x0 + 1, y0 - h * 0.5), (x0 - 1, y0 - h * 0.8), (x0 + 2, y0 - h), 12), 1.6, col, ol=True)


def groom_tile(cv):
    q = [(3, 24), (15, 18), (29, 24), (17, 30)]
    cv.poly(q, LIGHT, ol=True)
    face_grid(cv, q, 2, DARK)


@icon("Generate/Convert XGen Primitives to Polygons...")
def i_xgen_to_poly(cv):
    cv.polyline(bezier((4, 4), (9, 14), (4, 22), (12, 28), 16), 1.6, LIGHT, ol=True)
    cv.line((3, 28), (14, 28), 1.6, LIGHT, ol=True)
    arrow(cv, (9, 16), (18, 16), w=2.4, head=4.5)
    for k in range(3):
        cv.poly([(20 + k, 4 + k * 8), (29, 2 + k * 8), (27, 9 + k * 8), (21, 10 + k * 8)], _hex("#3aa84a"), ol=True)


@icon("Generate/Create Description...")
def i_xgen_description(cv):
    groom_tile(cv)
    for x in (12, 16, 20):
        frond(cv, x, 24, 16)
    plus(cv, 7, 7, s=4.5, w=2.4)


@icon("Generate/Create Interactive Groom Splines")
def i_groom_splines(cv):
    groom_tile(cv)
    for x in (12, 16):
        frond(cv, x, 24, 16)
    plus(cv, 7, 7, s=4.5, w=2.4)
    cv.ring(24, 9, 5.5, 1.6, _hex("#3aa84a"), ol=True)
    cv.line((23, 14), (22, 24), 1.4, LIGHT)


@icon("Generate/Flip Tube Direction")
def i_flip_tube(cv):
    cv.line((6, 6), (13, 29), 3.0, _hex("#3aa84a"), ol=True)
    cv.line((26, 6), (19, 29), 3.0, _hex("#3aa84a"), ol=True)
    arrow(cv, (16, 5), (8, 5), w=1.8, col=RED, head=3.5)
    arrow(cv, (16, 5), (24, 5), w=1.8, col=RED, head=3.5)


@icon("Generate/Get Brush...")
def i_get_brush(cv):
    for x, col in ((12, _hex("#3a7ad0")), (19, _hex("#e8e0c8"))):
        cv.line((x, 15), (x + 2, 3), 2.4, BRUSH_WOOD, ol=True)
        cv.fill(cv.m_ellipse(x + 2, 4, 2, 3.5), col, ol=True)
    cv.fill(cv.m_rect(8, 14, 24, 28) | cv.m_ellipse(16, 28, 8, 2.5), hgrad(cv, 8, 24, (0.45, 0.45, 0.45), 0.2, -0.5),
            ol=True)
    cv.fill(cv.m_ellipse(16, 14, 8, 2.5), (0.15, 0.15, 0.15))


@icon("Generate/Interactive Groom Editor")
def i_groom_editor(cv):
    def body(x0, y0, x1, y1):
        for k in range(5):
            x = x0 + 2 + k * 4.5
            cv.polyline(bezier((x, y1), (x, y1 - 6), (x + 2 * (k - 2), y0 + 4), (x + 2 * (k - 2), y0), 10), 1.6,
                        (0.15, 0.3, 0.15))
    _ed(cv, _hex("#4cae5a"), body)


@icon("Generate/Make Collide")
def i_pfx_make_collide(cv):
    blob(cv, 18, 27, 9)
    cv.polyline(bezier((4, 2), (12, 4), (4, 14), (14, 18), 16), 2.4, BRUSH_WOOD, ol=True)
    cv.polyline([(14, 14), (19, 19), (29, 7)], 2.6, FGREEN, ol=True)


@icon("Generate/Make Paintable")
def i_make_paintable(cv):
    blob(cv, 9, 18, 5.5, _hex("#9a4ad8"))
    blob(cv, 14, 7, 4)
    blob(cv, 17, 26, 3.5)
    pfx_brush(cv, (13, 18), (29, 3))


@icon("Generate/Paint Effects Tool")
def i_paint_effects_tool(cv):
    cv.polyline(bezier((14, 3), (2, 10), (16, 20), (6, 28), 20), 2.0, LIGHT, ol=True)
    pfx_brush(cv, (11, 26), (29, 8))


def _template(cv):
    page(cv, 4, 3, 22, 28, WHITE)
    for y in (9, 13, 17):
        cv.line((12, y), (19, y), 1.2, DARK)
        cv.rect(8, y - 1, 10, y + 1, DARK)
    cv.polyline(wave_pts(6, 20, 23, 1.5, 1.0), 1.2, DARK)


@icon("Generate/Reset Template Brush")
def i_reset_template_brush(cv):
    _template(cv)
    curved_arrow(cv, 24, 7, 5, 200, 470, w=2.0, col=FGREEN, head=3.5)
    pfx_brush(cv, (17, 28), (30, 15), w=2.6)


@icon("Generate/Template Brush Settings...")
def i_template_brush_settings(cv):
    page(cv, 6, 2, 28, 30, WHITE)
    for y in (8, 12, 16):
        cv.line((14, y), (25, y), 1.2, DARK)
        cv.rect(10, y - 1, 12, y + 1, DARK)
    cv.polyline(wave_pts(8, 26, 23, 2.0, 1.0), 1.4, DARK)


# --- Stereo / Render --------------------------------------------------------------------------

@icon("Stereo/Make Links", "Stereo/Break Links", "Stereo/Editors/Custom Multi Rig...",
      "Stereo/Editors/Custom Stereo Rig...")
def i_stereo(cv):
    toon_ball(cv, 11, 11, 8.5, outline=1.6)
    cv.circle(21, 21, 9, (0.05, 0.05, 0.05))
    cv.fill(cv.m_circle(21, 21, 7.6), sphere_colour(cv, 21, 21, 7.6, _hex("#7ac0ec"), amb=0.8, dif=0.3))
    pencil(cv, (20, 22), (30, 10), w=3.5, col=_hex("#e0a040"))


@icon("Render/Export Pre-Compositing")
def i_export_precomp(cv):
    cv.fill(cv.m_rect(3, 3, 29, 29), sphere_colour(cv, 16, 16, 20, _hex("#c8bca0"), amb=0.6, dif=0.6), ol=True)
    for a in range(45, 360, 90):
        ra = math.radians(a)
        cv.line((16 + 5 * math.cos(ra), 16 + 5 * math.sin(ra)), (16 + 15 * math.cos(ra), 16 + 15 * math.sin(ra)), 1.6,
                (0.1, 0.1, 0.1))
    cv.frame(11, 11, 21, 21, 1.4, (0.1, 0.1, 0.1))
