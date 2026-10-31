# SPDX-License-Identifier: GPL-3.0-or-later
"""Graph Editor value axis in display units (#66).

Blender's Graph Editor draws F-curve values as stored and converts only rotations (C ``ANIM_unit_mapping_get_factor``),
so in the Maya Workflow Kit scene (cm shown, ``scale_length`` 1) a 5 cm Translate X curve reads
0.00 - 0.05 while the Channel Box and the Maya Graph Editor read 0 - 5. When every curve the Graph Editor shows is a length property, the kit writes Blender's value
numbers again as ``value / units.maya_unit()`` on the same grid lines; mixed units (length + rotation / scale) keep
Blender's numbers, one axis can't carry two units.

Blender 4.5 draws those numbers in the WINDOW region's *overlay* (``graph_main_region_draw_overlay`` ->
``UI_view2d_draw_scale_y__values``, Blender source space_graph.cc:352-358, view2d_draw.cc:340-400), which is drawn
after every Python POST_PIXEL handler of the region: a POST_PIXEL cover stays under them.
The only Python drawing that comes after a region overlay is a window-manager draw cursor
(``WindowManager.draw_cursor_add``, wm_draw ``wm_paintcursor_draw``), which Blender draws for the region under the
mouse only. So:

* a POST_PIXEL handler on the Graph Editor WINDOW region (``_snapshot``) works out Blender's labels for the current
  view and keeps the region pixels of the label strip as they are before the overlay (a texture);
* the draw cursor (``_cursor``) pastes those pixels back over Blender's label boxes and writes the display-unit
  labels in Blender's style (default font 11 pt, ``wcol_scroll.text`` with a ``TH_BACK`` outline, x = 8 px).

The relabel therefore shows while the mouse is in the Graph Editor's curve area (where one reads values) and stays
after the mouse leaves its window from there; with the mouse over another region of that window Blender's numbers
come back (remaining, step doc). Draw cursors make every mouse move redraw the window, so the cursor is only
registered while a Graph Editor is open (``_sync`` timer).
"""

import math

import bpy

from .. import live_refs

# Blender 4.5 view2d_draw.cc:65-67 ``continuous_value_scales``: the label step is the first one at least
# ``view2d_grid_spacing_min`` x UI scale pixels apart (``select_major_distance``, view2d_draw.cc:40-61).
STEPS = (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000,
         50000, 100000)
TEXT_POINTS = 11.0          # UI_DEFAULT_TEXT_POINTS = BLF_draw_default's size (blf_default.cc:23-55)
X_OFFSET = 8.0              # draw_vertical_scale_indicators: xpos = (rect.xmin + 8) x UI scale
RECT_YMIN = 15.0            # space_graph.cc:356: label rect y from 15 x UI scale ...
SCRUB_MARGIN = 23.0         # ... to winy - UI_TIME_SCRUB_MARGIN_Y (23 x UI scale, UI_view2d.hh:471)
MIN_HEIGHT = 26 * 1.1       # UI_ANIM_MINY (HEADERY x 1.1): a lower region draws no numbers


# --- bpy-free maths ---------------------------------------------------------------------------------------------

def major_step(px_per_unit, min_px):
    """Blender's value label / major grid step for ``px_per_unit`` pixels per view unit."""
    if px_per_unit <= 0:
        return STEPS[0]
    for d in STEPS:
        if px_per_unit * d >= min_px:
            return d
    return STEPS[-1]


def tick_indices(lo, hi, step):
    """Integers n with lo <= n x step <= hi (``get_parallel_lines_draw_steps``, offset 0)."""
    if lo >= hi or step <= 0:
        return []
    first = math.ceil(lo / step)
    last = math.floor(hi / step)
    return list(range(first, last + 1)) if last >= first else []


def blender_label(value, step):
    """Blender's number for a tick at ``value`` (``view_to_string__value``, view2d_draw.cc:428-444)."""
    if step >= 1.0:
        return "%d" % int(value)
    if step >= 0.1:
        return "%.1f" % value
    if step >= 0.01:
        return "%.2f" % value
    return "%.3f" % value


def _nice(x):
    """x snapped to k x 10^e with k in 1, 2, 5 (the steps Blender picks), None when it isn't one: a decimal unit
    ratio keeps Blender's format."""
    if x <= 0:
        return None
    e = math.floor(math.log10(x) + 1e-9)
    k = x / 10 ** e
    for n in (1, 2, 5, 10):
        if abs(k - n) < 1e-6 * n:
            return n * 10.0 ** e
    return None


def display_label(n, step, unit):
    """The label of tick ``n`` (value n x step in Blender units) in display units of ``unit`` BU each."""
    dstep = step / unit
    nice = _nice(dstep)
    if nice is not None:
        # Blender's format on the display step; round, not Blender's int() truncation (2.9999 -> "2")
        value = n * nice
        if nice >= 1.0:
            text = "%d" % round(value)
        elif nice >= 0.1:
            text = "%.1f" % value
        elif nice >= 0.01:
            text = "%.2f" % value
        else:
            text = "%.3f" % value
    else:
        # inch / foot ratios: enough decimals for three significant digits of the step
        value = n * dstep
        dec = max(0, 2 - math.floor(math.log10(dstep)))
        text = ("%.*f" % (dec, value)).rstrip("0").rstrip(".") if dec else "%d" % round(value)
    return text[1:] if text.startswith("-") and text[1:].strip("0.") == "" else text     # no "-0.00"


def all_length(units):
    """True when there are curves and every one is a length property ('LENGTH' RNA unit)."""
    units = list(units)
    return bool(units) and all(u == 'LENGTH' for u in units)


def labels(lo, hi, px_per_unit, min_px, unit):
    """[(view value, Blender text, display text)] for a label range lo..hi (view units)."""
    step = major_step(px_per_unit, min_px)
    return [(n * step, blender_label(n * step, step), display_label(n, step, unit))
            for n in tick_indices(lo, hi, step)]


# --- curves --------------------------------------------------------------------------------------------------------

_ID_COLLECTIONS = ("objects", "meshes", "curves", "armatures", "lights", "cameras", "materials", "worlds",
                   "shape_keys", "scenes", "node_groups", "lattices", "metaballs", "grease_pencils",
                   "textures", "particles", "speakers")


def _owners():
    """{action pointer: [IDs animated by it]} (a 4.5 F-curve's id_data is its Action, not the animated ID)."""
    out = {}
    for name in _ID_COLLECTIONS:
        for idb in getattr(bpy.data, name, ()):
            ad = getattr(idb, "animation_data", None)
            act = ad.action if ad is not None else None
            if act is not None:
                out.setdefault(act.as_pointer(), []).append(idb)
    return out


def path_unit(owner, data_path):
    """RNA unit of ``owner.<data_path>`` ('LENGTH', 'ROTATION', 'NONE', ...), None if it doesn't resolve."""
    if not data_path or data_path.endswith('"]'):      # custom property: no unit
        return 'NONE' if data_path else None
    base, _, prop = data_path.rpartition(".")
    try:
        holder = owner.path_resolve(base) if base else owner
    except (ValueError, AttributeError):
        return None
    rna = getattr(holder, "bl_rna", None)
    p = rna.properties.get(prop) if rna is not None else None
    return p.unit if p is not None else None


def curve_units(fcurves):
    """RNA unit per F-curve; an unresolved curve counts as 'NONE'."""
    owners = None
    out = []
    for fc in fcurves:
        idb = fc.id_data
        cands = [idb]
        if isinstance(idb, bpy.types.Action):
            if owners is None:
                owners = _owners()
            cands = owners.get(idb.as_pointer(), [])
        unit = None
        for c in cands:
            unit = path_unit(c, fc.data_path)
            if unit is not None:
                break
        out.append(unit or 'NONE')
    return out


def factor(context):
    """BU per display unit when this Graph Editor's numbers should be relabelled, else None."""
    space = context.space_data
    if space is None or space.type != 'GRAPH_EDITOR' or space.mode != 'FCURVES' or space.use_normalization:
        return None
    from ..operators import units
    try:
        k = units.maya_unit(context.scene)
    except AttributeError:
        return None
    if not k or abs(k - 1.0) < 1e-9:
        return None
    fcs = getattr(context, "visible_fcurves", None)
    if not fcs or not all_length(curve_units(fcs)):
        return None
    return k


# --- drawing -------------------------------------------------------------------------------------------------------

# region pointer -> {"items": [(x, baseline, Blender text width, height, display text)], "box": (x0, y0, x1, y1) of
# the strip read back, "tex": its GPUTexture, "pixels": the same as numpy rows (tests), "pad": box margin}
_SNAP = {}
_handles = []
_cursor_handle = []


def _scale():
    return bpy.context.preferences.system.ui_scale or 1.0


def _font(s):
    import blf
    blf.size(0, TEXT_POINTS * s)
    return 0


def layout(region, k):
    """Blender's labels of this region as [(x, baseline y, Blender text, display text)] in region pixels."""
    import blf
    s = _scale()
    if region.height < MIN_HEIGHT * s:
        return []
    v2d = region.view2d
    y0 = v2d.region_to_view(0, 0)[1]
    y1 = v2d.region_to_view(0, 1000)[1]
    if y1 <= y0:
        return []
    ppu = 1000.0 / (y1 - y0)
    ymin, ymax = RECT_YMIN * s, region.height - SCRUB_MARGIN * s
    lo, hi = v2d.region_to_view(0, ymin)[1], v2d.region_to_view(0, ymax)[1]
    min_px = bpy.context.preferences.view.view2d_grid_spacing_min * s
    rows = labels(lo, hi, ppu, min_px, k)
    if len(rows) >= region.height:
        return []
    font = _font(s)
    y_off = blf.dimensions(font, "0")[1] / 2.0 - bpy.context.preferences.system.pixel_size
    out = []
    for value, btext, dtext in rows:
        y = (value - y0) * ppu      # view_to_region_y without int rounding
        if y - y_off >= ymin and y + y_off <= ymax:
            out.append((X_OFFSET * s, y - y_off, btext, dtext))
    return out


def _snapshot():
    """POST_PIXEL: remember the labels and the strip pixels under them (before Blender's overlay)."""
    context = bpy.context
    region = context.region
    if region is None:
        return
    ptr = region.as_pointer()
    k = factor(context)
    rows = layout(region, k) if k else []
    if not rows:
        _SNAP.pop(ptr, None)
        return
    import blf
    import gpu
    import numpy as np
    s = _scale()
    font = _font(s)
    h = blf.dimensions(font, "0")[1]
    pad = 2 + math.ceil(s)            # outline + anti-aliasing around Blender's glyphs
    items = []
    x1 = 0
    for x, base, btext, dtext in rows:
        w = blf.dimensions(font, btext)[0]
        items.append((x, base, w, h, dtext))
        x1 = max(x1, x + w)
    bx0 = 0
    by0 = max(0, int(min(i[1] for i in items) - pad - 1))
    bx1 = min(region.width, int(math.ceil(x1 + pad + 1)))
    by1 = min(region.height, int(math.ceil(max(i[1] + i[3] for i in items) + pad + 1)))
    if bx1 <= bx0 or by1 <= by0:
        _SNAP.pop(ptr, None)
        return
    try:
        buf = gpu.state.active_framebuffer_get().read_color(bx0, by0, bx1 - bx0, by1 - by0, 4, 0, 'UBYTE')
    except ValueError:
        _SNAP.pop(ptr, None)
        return
    px = np.array(buf.to_list(), dtype=np.float32).reshape(by1 - by0, bx1 - bx0, 4) / 255.0
    # pasted as they are: the draw cursor draws into the window framebuffer, where 'IMAGE' doesn't convert
    # (an sRGB -> linear round trip comes out dark)
    px[..., 3] = 1.0
    data = gpu.types.Buffer('FLOAT', px.size, px.ravel())
    tex = gpu.types.GPUTexture((bx1 - bx0, by1 - by0), format='RGBA32F', data=data)
    _SNAP[ptr] = {"items": items, "box": (bx0, by0, bx1, by1), "tex": tex, "pad": pad, "pixels": px}


def _theme_colours():
    th = bpy.context.preferences.themes[0]
    text = tuple(th.user_interface.wcol_scroll.text)
    back = tuple(th.graph_editor.space.back)
    return (*text[:3], 1.0), (*back[:3], 1.0)


def _cursor(*_args):
    """Draw cursor (after the region overlay): Blender's label boxes back to the pre-overlay pixels, our labels."""
    context = bpy.context
    region = context.region
    if region is None:
        return
    snap = _SNAP.get(region.as_pointer())
    if snap is None:
        return
    from ..marking import draw as mdraw
    if mdraw.ACTIVE:        # a marking menu drawn over the strip would get holes
        return
    import blf
    import gpu
    from gpu_extras.batch import batch_for_shader
    ox, oy = region.x, region.y      # the draw cursor draws in window pixels
    bx0, by0, bx1, by1 = snap["box"]
    bw, bh = bx1 - bx0, by1 - by0
    pad = snap["pad"]
    pos, uv = [], []
    for x, base, w, h, _t in snap["items"]:
        x0, y0 = max(bx0, x - pad), max(by0, base - pad)
        x1, y1 = min(bx1, x + w + pad), min(by1, base + h + pad)
        x0, y0, x1, y1 = math.floor(x0), math.floor(y0), math.ceil(x1), math.ceil(y1)
        quad = ((x0, y0), (x1, y0), (x1, y1), (x0, y0), (x1, y1), (x0, y1))
        pos += [(ox + a, oy + b) for a, b in quad]
        uv += [((a - bx0) / bw, (b - by0) / bh) for a, b in quad]
    # the window projection of a draw cursor is shifted by Blender's 0.375 px pixel offset (GLA_PIXEL_OFS), which
    # resamples the pasted pixels and blurs glyphs: draw with an exact pixel ortho (crisp like Blender's own labels,
    # pixel exact)
    import mathutils
    _vx, _vy, vw, vh = gpu.state.viewport_get()
    gpu.matrix.push_projection()
    gpu.matrix.load_projection_matrix(mathutils.Matrix(
        ((2 / vw, 0, 0, -1), (0, 2 / vh, 0, -1), (0, 0, -1, 0), (0, 0, 0, 1))))
    if pos:
        sh = gpu.shader.from_builtin('IMAGE')
        batch = batch_for_shader(sh, 'TRIS', {"pos": pos, "texCoord": uv})
        sh.bind()
        sh.uniform_sampler("image", snap["tex"])
        batch.draw(sh)
    text, back = _theme_colours()
    font = _font(_scale())
    blf.color(font, *text)
    blf.enable(font, blf.SHADOW)
    blf.shadow(font, 6, *back)         # 6 = outline (FontShadowType::Outline)
    blf.shadow_offset(font, 0, 0)
    for x, base, _w, _h, t in snap["items"]:
        blf.position(font, ox + round(x), oy + round(base), 0)
        blf.draw(font, t)
    blf.disable(font, blf.SHADOW)
    gpu.matrix.pop_projection()


def _sync():
    """Draw cursor only while a Graph Editor is open (a draw cursor redraws the window on every mouse move)."""
    areas = [a for w in live_refs.windows() for a in w.screen.areas if a.type == 'GRAPH_EDITOR']
    if areas and not _cursor_handle:
        _cursor_handle.append(bpy.context.window_manager.draw_cursor_add(_cursor, (), 'GRAPH_EDITOR', 'WINDOW'))
    elif not areas and _cursor_handle:
        bpy.context.window_manager.draw_cursor_remove(_cursor_handle.pop())
    live = {r.as_pointer() for a in areas for r in a.regions}
    for ptr in [p for p in _SNAP if p not in live]:
        del _SNAP[ptr]
    return 0.5


def register():
    _handles.append(bpy.types.SpaceGraphEditor.draw_handler_add(_snapshot, (), 'WINDOW', 'POST_PIXEL'))
    bpy.app.timers.register(_sync, first_interval=0.1, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(_sync):
        bpy.app.timers.unregister(_sync)
    while _cursor_handle:
        bpy.context.window_manager.draw_cursor_remove(_cursor_handle.pop())
    while _handles:
        bpy.types.SpaceGraphEditor.draw_handler_remove(_handles.pop(), 'WINDOW')
    _SNAP.clear()
