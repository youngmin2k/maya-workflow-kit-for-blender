# SPDX-License-Identifier: GPL-3.0-or-later
"""Kit-drawn toolbar pictures for the Graph Editor and Dope Sheet (#277).

The kit's own drawings, one per toolbar button, in the Status Line / panel toolbar style (``status_icons``: grey line
art, teal accents, dark outline, numpy at the icon size). Each picture shows what its button does: tangent buttons
draw the curve shape the tangent gives around a teal key, key tools draw keys with the tool's motion, view buttons
draw how the curves are laid out. Keyed by the editor button's name (``editor_chrome.ICONS``); Dope Sheet buttons
with the same name and meaning share a picture.
"""

from . import status_icons
from .status_icons import DARK, DIM, GREY, LIGHT, ORANGE, TEAL, TEAL_LIGHT

W = 0.08          # stroke
KEY = 0.10        # key dot radius
PREFIX = "ge_"


# --- parts ---------------------------------------------------------------------------------------------------------

def bez(p0, p1, p2, p3, n=20):
    """Points of a cubic Bezier."""
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append((u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
                    u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]))
    return out


def key(cv, x, y, colour=TEAL, r=KEY):
    cv.circle(x, y, r, colour)


def diamond(cv, x, y, r, colour):
    cv.poly([(x, y - r), (x + r, y), (x, y + r), (x - r, y)], colour)


def arrow_head(cv, x, y, dx, dy, s, colour):
    """A filled triangle pointing along (dx, dy) with its tip at (x, y)."""
    px, py = -dy, dx
    bx, by = x - dx * s, y - dy * s
    cv.poly([(x, y), (bx + px * s * 0.6, by + py * s * 0.6), (bx - px * s * 0.6, by - py * s * 0.6)], colour)


def harrow(cv, x0, x1, y, colour, both=True, s=0.16):
    cv.line(x0 + (s if both else 0), y, x1 - s, y, W, colour)
    arrow_head(cv, x1, y, 1, 0, s, colour)
    if both:
        arrow_head(cv, x0, y, -1, 0, s, colour)


def varrow(cv, x, y0, y1, colour, s=0.16):
    """Arrow from y0 to y1 (tip at y1)."""
    d = 1 if y1 > y0 else -1
    cv.line(x, y0, x, y1 - d * s, W, colour)
    arrow_head(cv, x, y1, 0, d, s, colour)


def brackets(cv, x0, y0, x1, y1, L, colour, w=W):
    for cx, sx in ((x0, 1), (x1, -1)):
        for cy, sy in ((y0, 1), (y1, -1)):
            cv.line(cx, cy, cx + sx * L, cy, w, colour)
            cv.line(cx, cy, cx, cy + sy * L, w, colour)


def window(cv):
    """An editor window: frame + title bar."""
    cv.frame(0.04, 0.10, 0.96, 0.90, 0.07, GREY)
    cv.rect(0.04, 0.10, 0.96, 0.26, GREY)


def rows(cv, x0, x1, ys, colour=GREY):
    for y in ys:
        cv.line(x0, y, x1, y, W, colour)


def wave(cv, x0, x1, yc, amp, colour, w=W, periods=1.0, n=28):
    import math
    pts = [(x0 + (x1 - x0) * i / n, yc - amp * math.sin(2 * math.pi * periods * i / n)) for i in range(n + 1)]
    cv.polyline(pts, w, colour)


def handle(cv, x, y, dx, dy, colour=LIGHT, r=0.06):
    """A tangent handle line from the key at (x, y) to (x + dx, y + dy) with its round end."""
    cv.line(x, y, x + dx, y + dy, 0.05, colour)
    cv.circle(x + dx, y + dy, r, colour)


def padlock(cv, x, y, s, colour, open_=False):
    cv.rect(x - s * 0.5, y, x + s * 0.5, y + s * 0.7, colour)
    cv.ring(x + (s * 0.22 if open_ else 0), y, s * 0.30, 0.06, colour, 0, 180)


def magnet_small(cv, colour=GREY):
    cv.ring(0.36, 0.40, 0.24, 0.13, colour, 0, 180)
    cv.line(0.18, 0.40, 0.18, 0.62, 0.13, colour)
    cv.line(0.54, 0.40, 0.54, 0.62, 0.13, colour)
    cv.rect(0.12, 0.58, 0.24, 0.68, TEAL)
    cv.rect(0.48, 0.58, 0.60, 0.68, TEAL)


# --- key tools -------------------------------------------------------------------------------------------------------

def g_key_nearest_tool(cv):
    """Move the nearest picked key: a curve, the key and the pointer on it."""
    cv.polyline(bez((0.04, 0.80), (0.20, 0.20), (0.40, 0.20), (0.56, 0.50)), W, GREY)
    key(cv, 0.30, 0.34)
    status_icons.arrow_cursor(cv, 0.44, 0.40, 0.52)


def g_key_insert_tool(cv):
    """Insert keys: a curve with a new key and a plus."""
    cv.polyline(bez((0.04, 0.88), (0.30, 0.20), (0.62, 0.95), (0.96, 0.62)), W, GREY)
    key(cv, 0.42, 0.60, TEAL, 0.12)
    cv.rect(0.62, 0.06, 0.70, 0.40, LIGHT)
    cv.rect(0.49, 0.19, 0.83, 0.27, LIGHT)


def g_key_lattice_tool(cv):
    """Lattice over keys: a 3 x 3 cage around a curve."""
    for t in (0.08, 0.50, 0.92):
        cv.line(t, 0.08, t, 0.92, 0.05, GREY)
        cv.line(0.08, t, 0.92, t, 0.05, GREY)
    for x in (0.08, 0.50, 0.92):
        for y in (0.08, 0.50, 0.92):
            cv.rect(x - 0.06, y - 0.06, x + 0.06, y + 0.06, LIGHT)
    cv.polyline(bez((0.10, 0.80), (0.35, 0.10), (0.65, 0.90), (0.90, 0.22)), W, TEAL)


def g_key_region_tool(cv):
    """Region tool: a box around keys with scale handles on its sides."""
    for i in range(4):
        x = 0.16 + i * 0.19
        cv.rect(x, 0.12, x + 0.10, 0.18, GREY)
        cv.rect(x, 0.82, x + 0.10, 0.88, GREY)
    for i in range(4):
        y = 0.16 + i * 0.19
        cv.rect(0.12, y, 0.18, y + 0.10, GREY)
        cv.rect(0.82, y, 0.88, y + 0.10, GREY)
    for x, y in ((0.10, 0.50), (0.90, 0.50), (0.50, 0.10), (0.50, 0.90)):
        cv.rect(x - 0.07, y - 0.07, x + 0.07, y + 0.07, LIGHT)
    key(cv, 0.36, 0.60)
    key(cv, 0.62, 0.40)


def g_key_retime_tool(cv):
    """Retime: two time markers and the span between them stretched."""
    cv.line(0.20, 0.06, 0.20, 0.94, W, TEAL)
    cv.line(0.80, 0.06, 0.80, 0.94, W, TEAL)
    cv.poly([(0.10, 0.06), (0.30, 0.06), (0.20, 0.20)], TEAL)
    cv.poly([(0.70, 0.06), (0.90, 0.06), (0.80, 0.20)], TEAL)
    harrow(cv, 0.28, 0.72, 0.56, GREY)


def g_key_grab_tool(cv):
    """Grab brush: a brush ring lifting the curve."""
    cv.polyline(bez((0.04, 0.88), (0.36, 0.88), (0.40, 0.40), (0.50, 0.40)) +
                bez((0.50, 0.40), (0.60, 0.40), (0.64, 0.88), (0.96, 0.88))[1:], W, GREY)
    cv.ring(0.50, 0.40, 0.22, 0.06, TEAL)
    varrow(cv, 0.50, 0.30, 0.02, LIGHT, 0.12)


def g_key_smooth(cv):
    """Smooth: a jagged curve becoming a calm one."""
    cv.polyline([(0.04, 0.50), (0.12, 0.20), (0.20, 0.78), (0.28, 0.24), (0.36, 0.70), (0.44, 0.46)], W, DIM)
    wave(cv, 0.44, 0.96, 0.46, 0.14, GREY, periods=0.5)
    cv.ring(0.70, 0.46, 0.24, 0.06, TEAL)


def g_key_smear_tool(cv):
    """Smear: a brush ring dragging streaks behind it."""
    cv.ring(0.66, 0.50, 0.22, 0.06, TEAL)
    for y, x0 in ((0.32, 0.18), (0.50, 0.04), (0.68, 0.18)):
        cv.line(x0, y, 0.42, y, 0.06, GREY)


def g_key_reduce(cv):
    """Reduce: many keys becoming a few."""
    for i in range(5):
        cv.circle(0.10 + i * 0.20, 0.18, 0.07, DIM)
    varrow(cv, 0.50, 0.30, 0.58, GREY, 0.12)
    key(cv, 0.18, 0.80, TEAL, 0.11)
    key(cv, 0.82, 0.80, TEAL, 0.11)
    cv.line(0.18, 0.80, 0.82, 0.80, 0.05, GREY)


# --- framing ---------------------------------------------------------------------------------------------------------

def g_frame_all(cv):
    """Frame all: corner marks around a curve."""
    brackets(cv, 0.06, 0.06, 0.94, 0.94, 0.26, GREY)
    cv.polyline(bez((0.22, 0.72), (0.38, 0.12), (0.58, 0.90), (0.78, 0.30)), W, TEAL)


def g_frame_range(cv):
    """Frame playback range: the range's two ends pulled out to the sides."""
    cv.line(0.06, 0.14, 0.06, 0.86, W, GREY)
    cv.line(0.94, 0.14, 0.94, 0.86, W, GREY)
    cv.rect(0.24, 0.30, 0.76, 0.70, TEAL)
    arrow_head(cv, 0.12, 0.50, -1, 0, 0.10, LIGHT)
    arrow_head(cv, 0.88, 0.50, 1, 0, 0.10, LIGHT)


def g_center_time(cv):
    """Center current time: the time line in the middle, arrows moving the view to it."""
    cv.line(0.50, 0.04, 0.50, 0.96, W, ORANGE)
    cv.rect(0.40, 0.04, 0.60, 0.20, ORANGE)
    arrow_head(cv, 0.38, 0.62, 1, 0, 0.16, GREY)
    cv.line(0.04, 0.62, 0.26, 0.62, W, GREY)
    arrow_head(cv, 0.62, 0.62, -1, 0, 0.16, GREY)
    cv.line(0.74, 0.62, 0.96, 0.62, W, GREY)


# --- tangents (curve shape around a teal key) ------------------------------------------------------------------------

def g_tan_auto(cv):
    """Auto: a smooth hump whose top sits on the key."""
    cv.polyline(bez((0.04, 0.86), (0.24, 0.30), (0.34, 0.30), (0.50, 0.30)) +
                bez((0.50, 0.30), (0.66, 0.30), (0.76, 0.30), (0.96, 0.86))[1:], W, GREY)
    key(cv, 0.50, 0.30)
    cv.rect(0.28, 0.06, 0.72, 0.12, TEAL_LIGHT)


def g_tan_auto_ease(cv):
    """Auto ease: the curve eases out of one key and into the next."""
    cv.polyline(bez((0.14, 0.82), (0.50, 0.82), (0.50, 0.22), (0.86, 0.22)), W, GREY)
    key(cv, 0.14, 0.82)
    key(cv, 0.86, 0.22)
    cv.line(0.04, 0.82, 0.14, 0.82, 0.05, LIGHT)
    cv.line(0.86, 0.22, 0.96, 0.22, 0.05, LIGHT)


def g_tan_auto_mix(cv):
    """Auto mix: a straight part blending into a rounded part."""
    cv.polyline([(0.04, 0.86), (0.44, 0.40)], W, GREY)
    cv.polyline(bez((0.44, 0.40), (0.58, 0.24), (0.80, 0.24), (0.96, 0.50)), W, GREY)
    key(cv, 0.44, 0.40)
    cv.rect(0.60, 0.70, 0.94, 0.94, TEAL_LIGHT)
    cv.rect(0.66, 0.76, 0.88, 0.88, DARK)


def g_tan_auto_custom(cv):
    """Auto custom: a smooth curve with a weight slider under the key."""
    cv.polyline(bez((0.04, 0.60), (0.24, 0.12), (0.62, 0.12), (0.96, 0.46)), W, GREY)
    key(cv, 0.40, 0.22)
    cv.line(0.10, 0.84, 0.90, 0.84, 0.06, DIM)
    cv.rect(0.56, 0.72, 0.68, 0.96, TEAL_LIGHT)


def g_tan_spline(cv):
    """Spline: a flowing S through three keys."""
    pts = bez((0.06, 0.70), (0.20, 0.10), (0.36, 0.10), (0.50, 0.50))
    pts += bez((0.50, 0.50), (0.64, 0.90), (0.80, 0.90), (0.94, 0.30))[1:]
    cv.polyline(pts, W, GREY)
    key(cv, 0.06, 0.70)
    key(cv, 0.50, 0.50)
    key(cv, 0.94, 0.30)


def g_tan_clamped(cv):
    """Clamped: the curve stops at the key's value, no overshoot past the limit line."""
    for x in (0.06, 0.26, 0.46, 0.66, 0.86):
        cv.line(x, 0.20, x + 0.10, 0.20, 0.05, DIM)
    cv.polyline(bez((0.06, 0.88), (0.40, 0.88), (0.30, 0.20), (0.62, 0.20)), W, GREY)
    cv.line(0.62, 0.20, 0.96, 0.20, W, GREY)
    key(cv, 0.62, 0.20)
    key(cv, 0.06, 0.88)


def g_tan_linear(cv):
    """Linear: straight lines from key to key."""
    pts = [(0.06, 0.84), (0.40, 0.18), (0.66, 0.66), (0.94, 0.30)]
    cv.polyline(pts, W, GREY)
    for x, y in pts:
        key(cv, x, y, TEAL, 0.09)


def g_tan_flat(cv):
    """Flat: level handles on both keys, the curve between them."""
    cv.polyline(bez((0.24, 0.78), (0.52, 0.78), (0.48, 0.22), (0.76, 0.22)), W, GREY)
    cv.line(0.04, 0.78, 0.44, 0.78, 0.05, LIGHT)
    cv.line(0.56, 0.22, 0.96, 0.22, 0.05, LIGHT)
    key(cv, 0.24, 0.78)
    key(cv, 0.76, 0.22)


def g_tan_stepped(cv):
    """Stepped: the value holds, then jumps."""
    cv.polyline([(0.04, 0.84), (0.36, 0.84), (0.36, 0.50), (0.66, 0.50), (0.66, 0.16), (0.96, 0.16)], W, GREY)
    key(cv, 0.06, 0.84)
    key(cv, 0.36, 0.50)
    key(cv, 0.66, 0.16)


def g_tan_plateau(cv):
    """Plateau: a rise that stays level across the top keys."""
    cv.polyline(bez((0.04, 0.88), (0.20, 0.88), (0.18, 0.30), (0.34, 0.30)), W, GREY)
    cv.line(0.34, 0.30, 0.66, 0.30, W, GREY)
    cv.polyline(bez((0.66, 0.30), (0.82, 0.30), (0.80, 0.88), (0.96, 0.88)), W, GREY)
    key(cv, 0.34, 0.30)
    key(cv, 0.66, 0.30)


def g_tan_default_in(cv):
    """Default in tangent: the curve coming into the key, the in side marked."""
    cv.polyline(bez((0.04, 0.88), (0.20, 0.60), (0.36, 0.40), (0.62, 0.40)), W, TEAL)
    cv.line(0.62, 0.40, 0.96, 0.40, 0.05, DIM)
    key(cv, 0.62, 0.40, LIGHT, 0.11)
    arrow_head(cv, 0.40, 0.78, 1, 0, 0.16, GREY)
    cv.line(0.06, 0.78, 0.26, 0.78, W, GREY)


def g_tan_default_out(cv):
    """Default out tangent: the curve leaving the key, the out side marked."""
    cv.line(0.04, 0.40, 0.38, 0.40, 0.05, DIM)
    cv.polyline(bez((0.38, 0.40), (0.64, 0.40), (0.80, 0.60), (0.96, 0.88)), W, TEAL)
    key(cv, 0.38, 0.40, LIGHT, 0.11)
    arrow_head(cv, 0.94, 0.20, 1, 0, 0.16, GREY)
    cv.line(0.60, 0.20, 0.80, 0.20, W, GREY)


# --- buffer curves ---------------------------------------------------------------------------------------------------

def g_buffer_snapshot(cv):
    """Buffer snapshot: the curve and a grey copy kept beside it."""
    cv.polyline(bez((0.04, 0.84), (0.28, 0.20), (0.56, 0.20), (0.80, 0.70)), 0.06, DIM)
    cv.polyline(bez((0.20, 0.70), (0.44, 0.06), (0.72, 0.06), (0.96, 0.56)), W, TEAL)
    cv.rect(0.56, 0.70, 0.96, 0.96, GREY)
    cv.circle(0.76, 0.83, 0.07, DARK)


def g_buffer_swap(cv):
    """Swap buffer curves: two curves trading places."""
    cv.polyline(bez((0.04, 0.34), (0.30, 0.04), (0.60, 0.04), (0.96, 0.30)), W, TEAL)
    cv.polyline(bez((0.04, 0.66), (0.30, 0.96), (0.60, 0.96), (0.96, 0.70)), 0.06, DIM)
    varrow(cv, 0.36, 0.30, 0.70, LIGHT, 0.12)
    varrow(cv, 0.64, 0.70, 0.30, LIGHT, 0.12)


# --- tangent handles -------------------------------------------------------------------------------------------------

def g_tan_break(cv):
    """Break tangents: the two handles of a key bent apart."""
    handle(cv, 0.50, 0.66, -0.40, -0.48, GREY)
    handle(cv, 0.50, 0.66, 0.40, -0.20, TEAL_LIGHT)
    key(cv, 0.50, 0.66, TEAL, 0.12)
    cv.rect(0.40, 0.86, 0.60, 0.96, ORANGE)


def g_tan_unify(cv):
    """Unify tangents: both handles on one straight line through the key."""
    handle(cv, 0.50, 0.50, -0.40, 0.30, GREY)
    handle(cv, 0.50, 0.50, 0.40, -0.30, GREY)
    key(cv, 0.50, 0.50, TEAL, 0.12)


def g_tan_free_length(cv):
    """Free tangent length: a handle that can stretch."""
    cv.line(0.10, 0.70, 0.62, 0.70, 0.05, GREY)
    key(cv, 0.14, 0.70)
    harrow(cv, 0.58, 0.96, 0.70, LIGHT, both=True, s=0.12)
    padlock(cv, 0.34, 0.24, 0.30, GREY, open_=True)


def g_tan_lock_length(cv):
    """Lock tangent length: a handle with a closed lock."""
    cv.line(0.10, 0.70, 0.90, 0.70, 0.05, GREY)
    key(cv, 0.14, 0.70)
    cv.circle(0.86, 0.70, 0.07, LIGHT)
    padlock(cv, 0.52, 0.24, 0.32, TEAL)


# --- outliner list -------------------------------------------------------------------------------------------------

def g_list_auto_load(cv):
    """Auto load: the list follows the selection by itself (list rows + a turning arrow)."""
    rows(cv, 0.06, 0.48, (0.24, 0.50, 0.76))
    cv.ring(0.72, 0.50, 0.20, 0.08, TEAL, 30, 330)
    arrow_head(cv, 0.90, 0.40, 0.2, -1, 0.14, TEAL)


def g_list_load(cv):
    """Load the selected objects: an arrow into the list."""
    rows(cv, 0.44, 0.94, (0.24, 0.50, 0.76))
    harrow(cv, 0.04, 0.40, 0.50, TEAL, both=False, s=0.16)
    cv.rect(0.04, 0.40, 0.14, 0.60, TEAL)


# --- drag / snap -----------------------------------------------------------------------------------------------------

def g_constrained_drag(cv):
    """Unconstrained drag: free four-way arrows."""
    cv.line(0.50, 0.14, 0.50, 0.86, W, GREY)
    cv.line(0.14, 0.50, 0.86, 0.50, W, GREY)
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        arrow_head(cv, 0.50 + dx * 0.46, 0.50 + dy * 0.46, dx, dy, 0.16, GREY)
    cv.circle(0.50, 0.50, 0.11, TEAL)


def g_time_snap(cv):
    """Time snap: a magnet over whole-frame ticks."""
    magnet_small(cv)
    for i in range(4):
        x = 0.10 + i * 0.26
        cv.line(x, 0.80, x, 0.96, 0.06, GREY if i else TEAL_LIGHT)
    cv.line(0.06, 0.96, 0.94, 0.96, 0.05, GREY)


def g_value_snap(cv):
    """Value snap: a magnet beside whole-value ticks."""
    magnet_small(cv)
    for i in range(4):
        y = 0.10 + i * 0.26
        cv.line(0.80, y, 0.96, y, 0.06, GREY)
    cv.line(0.96, 0.06, 0.96, 0.94, 0.05, GREY)


# --- curve views -----------------------------------------------------------------------------------------------------

def g_view_absolute(cv):
    """Absolute view: curves of different sizes on one shared scale."""
    wave(cv, 0.04, 0.96, 0.50, 0.40, GREY)
    wave(cv, 0.04, 0.96, 0.50, 0.12, TEAL, periods=2.0)


def g_view_stacked(cv):
    """Stacked view: each curve in its own band."""
    wave(cv, 0.06, 0.94, 0.20, 0.10, GREY)
    cv.line(0.04, 0.37, 0.96, 0.37, 0.04, DIM)
    wave(cv, 0.06, 0.94, 0.53, 0.10, TEAL, periods=2.0)
    cv.line(0.04, 0.70, 0.96, 0.70, 0.04, DIM)
    wave(cv, 0.06, 0.94, 0.85, 0.10, GREY, periods=1.5)


def g_view_normalized(cv):
    """Normalized view: every curve scaled between the same two limits."""
    for y in (0.12, 0.88):
        for x in (0.04, 0.30, 0.56, 0.82):
            cv.line(x, y, x + 0.14, y, 0.05, DIM)
    wave(cv, 0.06, 0.94, 0.50, 0.36, GREY)
    wave(cv, 0.06, 0.94, 0.50, 0.36, TEAL, periods=0.5)


def g_renormalize(cv):
    """Re-normalize: the limits fitted again (two limit marks and a turning arrow)."""
    cv.line(0.04, 0.12, 0.44, 0.12, 0.06, DIM)
    cv.line(0.04, 0.88, 0.44, 0.88, 0.06, DIM)
    wave(cv, 0.04, 0.44, 0.50, 0.36, GREY, periods=0.5)
    cv.ring(0.72, 0.50, 0.20, 0.08, TEAL, 120, 60)
    arrow_head(cv, 0.62, 0.34, -0.6, 0.8, 0.14, TEAL)


# --- infinity --------------------------------------------------------------------------------------------------------

def _rise(cv, x0, y0, colour, w=W):
    """One cycle of the curve: an eased rise 0.44 wide, 0.30 high, starting at (x0, y0)."""
    cv.polyline(bez((x0, y0), (x0 + 0.22, y0), (x0 + 0.22, y0 - 0.30), (x0 + 0.44, y0 - 0.30)), w, colour)


def _infinity(cv, pre, offset):
    """The keyed curve (grey, teal keys) and one repeat (teal) before / after it; with offset the repeat continues
    from the curve's end value instead of jumping back."""
    x_key, x_rep = (0.52, 0.08) if pre else (0.08, 0.52)
    _rise(cv, x_key, 0.64, GREY)
    key(cv, x_key, 0.64, TEAL, 0.08)
    key(cv, x_key + 0.44, 0.34, TEAL, 0.08)
    shift = (0.30 if pre else -0.30) if offset else 0.0
    _rise(cv, x_rep, 0.64 + shift, TEAL_LIGHT, 0.06)
    if pre:
        arrow_head(cv, 0.04, 0.10, -1, 0, 0.12, LIGHT)
        cv.line(0.12, 0.10, 0.40, 0.10, 0.06, LIGHT)
    else:
        arrow_head(cv, 0.96, 0.10, 1, 0, 0.12, LIGHT)
        cv.line(0.60, 0.10, 0.88, 0.10, 0.06, LIGHT)


def g_pre_cycle(cv):
    """Pre-infinity cycle: the curve repeated before its first key."""
    _infinity(cv, True, False)


def g_pre_cycle_offset(cv):
    """Pre-infinity cycle with offset: the repeat before the first key ends where the curve starts."""
    _infinity(cv, True, True)


def g_post_cycle(cv):
    """Post-infinity cycle: the curve repeated after its last key."""
    _infinity(cv, False, False)


def g_post_cycle_offset(cv):
    """Post-infinity cycle with offset: the repeat after the last key starts where the curve ends."""
    _infinity(cv, False, True)


# --- editors ---------------------------------------------------------------------------------------------------------

def g_open_graph_editor(cv):
    window(cv)
    cv.polyline(bez((0.14, 0.80), (0.34, 0.30), (0.62, 0.92), (0.86, 0.36)), 0.07, TEAL)


def g_open_dope_sheet(cv):
    window(cv)
    for y, xs in ((0.44, (0.22, 0.52)), (0.70, (0.36, 0.76))):
        for x in xs:
            diamond(cv, x, y, 0.09, TEAL)


def g_open_time_editor(cv):
    window(cv)
    cv.rect(0.12, 0.36, 0.58, 0.52, TEAL)
    cv.rect(0.38, 0.62, 0.88, 0.78, TEAL_LIGHT)


# --- Dope Sheet tools ------------------------------------------------------------------------------------------------

def g_key_select_tool(cv):
    """Select keys: the pointer on a key."""
    diamond(cv, 0.30, 0.30, 0.20, TEAL)
    status_icons.arrow_cursor(cv, 0.42, 0.40, 0.54)


def g_key_move_tool(cv):
    """Move keys in time: keys with a left-right arrow."""
    diamond(cv, 0.30, 0.30, 0.14, TEAL)
    diamond(cv, 0.70, 0.30, 0.14, TEAL)
    harrow(cv, 0.04, 0.96, 0.74, GREY)


def g_key_scale_tool(cv):
    """Scale keys in time: keys pushed apart from a pivot line."""
    cv.line(0.50, 0.06, 0.50, 0.94, 0.05, LIGHT)
    diamond(cv, 0.30, 0.34, 0.12, TEAL)
    diamond(cv, 0.70, 0.34, 0.12, TEAL)
    harrow(cv, 0.58, 0.96, 0.74, GREY, both=False, s=0.14)
    arrow_head(cv, 0.04, 0.74, -1, 0, 0.14, GREY)
    cv.line(0.16, 0.74, 0.42, 0.74, W, GREY)


def g_hierarchy_below(cv):
    """Hierarchy below: a parent with its children."""
    cv.rect(0.06, 0.06, 0.34, 0.30, TEAL)
    cv.line(0.20, 0.30, 0.20, 0.82, 0.07, GREY)
    for y in (0.48, 0.82):
        cv.line(0.20, y, 0.50, y, 0.07, GREY)
        cv.rect(0.50, y - 0.11, 0.94, y + 0.11, GREY)


def g_dope_time_snap(cv):
    g_time_snap(cv)


GLYPHS = {name[2:]: fn for name, fn in globals().items() if name.startswith("g_")}


def name(key):
    """``status_icons`` glyph name of an editor button."""
    return PREFIX + key


def icon_value(editor, key):
    """icon_value of the kit picture of button ``key`` (0 = none: the button keeps Blender's icon)."""
    if key not in GLYPHS or name(key) not in status_icons.EXTRA:
        return 0
    import bpy
    if bpy.app.background:
        return 0
    return status_icons.icon(name(key))


def register():
    for key_, fn in GLYPHS.items():
        status_icons.EXTRA[name(key_)] = fn


def unregister():
    for key_ in GLYPHS:
        status_icons.EXTRA.pop(name(key_), None)
