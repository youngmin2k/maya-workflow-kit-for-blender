# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Outliner: a kit skeleton's row reads its root joint's name (Issue #155 H1-6).

Maya 2026: a new skeleton is ``joint1`` in the Outliner and in the Channel Box — a joint is one DAG node, there is no
skeleton node above it. The kit's skeleton is an
armature object ``skeleton<N>`` holding the joints as bones (operators/joints.py), and Blender's C Outliner shows the
object name. Renaming the object after its root joint would put an object and a bone of the same name in the scene
(the kit's ``maya.cmds`` look-up, FBX nodes and many rig tools find nodes by name; 100+ test references), so the kit
draws the label instead: a WINDOW POST_PIXEL handler finds the rows whose text is the armature
object's name and paints the root joint's name over it. Python can't ask Blender where a row is (rows of expanded
objects move the rest), so a row is recognised by its pixels: Blender's text of the object name is rendered offscreen
with the same font and compared with the row's ink; a row that doesn't match keeps Blender's text. Clicks still
reach Blender's rows; Blender's own rename field (double-click / F2) still shows the object name.

Which objects: armatures the kit named (``skeleton<N>``, ``joints.SKELETON_BASE``) with at least one root bone —
a user-named armature or a Rigify rig keeps its own name. With several root joints the first one names the row.
"""

from hashlib import blake2b
import bpy

_handle = [None]
_refs = {}          # (text, font size, row height) -> (width, baseline, ink mask (numpy bool, bottom row first))
_rows = {}          # region -> (layout/name signature, {row: (pixel digest/position, hits)})
INK = 48            # channel difference from the row background that counts as text
MATCH = 0.72        # share of the ink (union) both pictures have
DX = 4              # px the Blender name may sit off the expected column
DY = 3              # px the Blender baseline may sit off the reference's
SEEN = {}           # region pointer -> [(object name, label drawn)] of the last draw (GUI tests read it)


def label(ob, live_objects=None):
    """The name the Maya Outliner row of ``ob`` shows instead of the object's: its first root joint, or None."""
    from ..operators import joints
    from ..operators import live
    if ob is not None and ob in (live.objects(bpy.context.scene) if live_objects is None else live_objects):
        return ob.name
    if ob is None or ob.type != 'ARMATURE' or not ob.name.startswith(joints.SKELETON_BASE):
        return None
    tail = ob.name[len(joints.SKELETON_BASE):].split(".")[0]
    if tail and not tail.isdigit():
        return None
    roots = [b for b in ob.data.bones if b.parent is None]
    if not roots:
        return None
    return min(roots, key=joints.child_order_key).name


def _unit(prefs):
    return int(int(18.0 * prefs.system.ui_scale + 0.5) + 2 * prefs.system.pixel_size)


def _font_size(prefs):
    styles = prefs.ui_styles
    points = getattr(styles[0].widget, "points", 11.0) if len(styles) else 11.0
    return points * prefs.system.ui_scale


def _ref(text, size, height):
    """``text`` drawn with the UI font at ``size`` in a ``height`` px row: (width, baseline, ink mask)."""
    key = (text, round(size, 2), height)
    got = _refs.get(key)
    if got is not None:
        return got
    import blf
    import gpu
    import numpy as np
    from mathutils import Matrix
    blf.size(0, size)
    w = int(blf.dimensions(0, text)[0]) + 4
    base = int(round((height - blf.dimensions(0, "x")[1]) / 2.0))   # x-height centred; DY absorbs the rest
    viewport, scissor = gpu.state.viewport_get(), gpu.state.scissor_get()
    off = gpu.types.GPUOffScreen(w, height)
    try:
        with off.bind():
            fb = gpu.state.active_framebuffer_get()
            fb.clear(color=(0.0, 0.0, 0.0, 1.0))
            gpu.matrix.push_projection()
            gpu.matrix.push()
            try:
                gpu.matrix.load_identity()
                gpu.matrix.load_projection_matrix(Matrix(((2.0 / w, 0, 0, -1.0), (0, 2.0 / height, 0, -1.0),
                                                          (0, 0, 1.0, 0), (0, 0, 0, 1.0))))
                gpu.state.blend_set('ALPHA')
                blf.color(0, 1.0, 1.0, 1.0, 1.0)
                blf.position(0, 1, base, 0)
                blf.draw(0, text)
            finally:
                gpu.matrix.pop()
                gpu.matrix.pop_projection()
            px = np.array(fb.read_color(0, 0, w, height, 4, 0, 'UBYTE').to_list(), dtype=np.int16)
    finally:
        off.free()
        # Freeing the temporary framebuffer can restore the full-window GPU
        # viewport instead of this editor's. Restore the editor state explicitly
        # so the first cold glyph lookup does not draw labels outside its region.
        gpu.state.viewport_set(*viewport)
        gpu.state.scissor_set(*scissor)
    got = (w, base, px.reshape(height, w, 4)[..., 0] > 90)
    _refs[key] = got
    while len(_refs) > 256:
        del _refs[next(iter(_refs))]
    return got


def _ink(lines, bg):
    """Ink mask of pixel lines (numpy int16 (h, w, 4)) against the background colour ``bg``."""
    import numpy as np
    mask = np.abs(lines[..., :3] - np.asarray(bg[:3], dtype=np.int16)).max(axis=-1) > INK
    # A selected row's horizontal highlight borders are not glyph strokes.
    mask[np.count_nonzero(mask, axis=1) > lines.shape[1] * .8] = False
    return mask


def _background(lines):
    """Row fill, excluding the selected-row border and glyphs by majority colour."""
    import numpy as np
    colors, counts = np.unique(lines[len(lines)//2, :, :3], axis=0, return_counts=True)
    return tuple(int(c) for c in colors[counts.argmax()])


def _extent(cols, x0, x1):
    """(first, last) column with ink in [x0, x1), or None."""
    import numpy as np
    x0, x1 = max(0, x0), min(len(cols), x1)
    if x1 <= x0:
        return None
    xs = np.flatnonzero(cols[x0:x1])
    return (x0 + int(xs[0]), x0 + int(xs[-1])) if len(xs) else None


def match(ink, ref, x, extent=None):
    """Match glyph bounds first, then compare nearby translations instead of every pixel offset."""
    import numpy as np
    h, w = ref.shape
    best = (0.0, 0, 0)
    tolerance_x = max(DX, round(h * .25))
    tolerance_y = max(DY, round(h * .25))
    ref_x = _extent(ref.any(axis=0), 0, w)
    if ref_x is None:
        return best
    if extent is None:
        extent = _extent(ink.any(axis=0), x+ref_x[0]-tolerance_x, x+ref_x[1]+tolerance_x+1)
    if extent is None:
        return best
    shifts_x = {extent[i]-x-ref_x[i]+offset for i in (0, 1) for offset in (-1, 0, 1)}
    ref_y = np.flatnonzero(ref.any(axis=1))
    for dx in sorted(d for d in shifts_x if abs(d) <= tolerance_x):
        x0 = x + dx
        if x0 < 0 or x0 + w > ink.shape[1]:
            continue
        win = ink[:, x0:x0 + w]
        win_y = np.flatnonzero(win.any(axis=1))
        if not len(win_y):
            continue
        shifts_y = {int(win_y[i]-ref_y[i])+offset for i in (0, -1) for offset in (-1, 0, 1)}
        for dy in sorted(d for d in shifts_y if abs(d) <= tolerance_y):
            r = np.zeros_like(win)
            if dy > 0:
                r[dy:, :] = ref[:h - dy, :]
            elif dy < 0:
                r[:h + dy, :] = ref[-dy:, :]
            else:
                r[:, :] = ref
            union = np.count_nonzero(win | r)
            if union:
                s = np.count_nonzero(win & r) / union
                if s > best[0]:
                    best = (s, dx, dy)
    return best


def find_rows(rows, width, u, lead, names, size):
    """[(row k, depth, dx, dy, name)] of the rows (``rows`` = {k: numpy int16 (u, width, 4), bottom line first})
    whose text is one of ``names``: the same ink as Blender's text of that name (the best of the names: skeleton1
    and skeleton2 differ in one glyph), nothing right after it."""
    found = []
    tolerance_x = max(DX, round(u * .25))
    for k, lines in rows.items():
        bg = _background(lines)
        ink = _ink(lines, bg)
        cols = ink.any(axis=0)
        best = None
        for name in names:
            w, _base, ref = _ref(name, size, u)
            ref_ext = _extent(ref.any(axis=0), 0, w)
            if ref_ext is None:
                continue
            for depth in range(0, 8):
                x = int(lead + (depth + 2.25) * u)
                if x + w > width:
                    break
                ext = _extent(cols, x + ref_ext[0] - tolerance_x - 1, x + ref_ext[1] + tolerance_x + 2)
                if ext is None or abs(ext[0] - (x + ref_ext[0])) > tolerance_x or abs(ext[1] - (x + ref_ext[1])) > tolerance_x:
                    continue
                s, dx, dy = match(ink, ref, x, ext)
                if s < MATCH or (best is not None and s <= best[0]):
                    continue
                end = x + dx + ref_ext[1]
                if _extent(cols, end + 2, end + 2 + int(0.5 * u)) is not None:   # skeleton10 for skeleton1
                    continue
                best = (s, (k, depth, dx, dy, name))
        if best is not None:
            found.append(best[1])
    return found


_named_cache = {}


def _named(context, live_objects):
    """{object name: label} for the rows drawn over; kept per view layer until the structure or the live set changes
    (#191: every Outliner redraw walked every object)."""
    from .outliner import structure_version
    key = (structure_version(), frozenset(o.name for o in live_objects))
    vl = context.view_layer.as_pointer()
    got = _named_cache.get(vl)
    if got is not None and got[0] == key:
        return got[1]
    named = {}
    for ob in context.view_layer.objects:
        lab = label(ob, live_objects) if ob is not None else None
        if lab is not None:
            named[ob.name] = lab
    _named_cache[vl] = (key, named)
    return named


def draw():
    context = bpy.context
    space, region = context.space_data, context.region
    if region is None or space is None:
        return
    from .maya_outliner import is_maya_outliner
    if not is_maya_outliner(space):
        return
    SEEN[region.as_pointer()] = []
    from ..operators import live
    live_objects = set(live.objects(context.scene))
    named = _named(context, live_objects)
    if not named:
        _rows.pop(region.as_pointer(), None)
        return
    import math
    import blf
    import gpu
    import numpy as np
    from gpu_extras.batch import batch_for_shader
    prefs = context.preferences
    u = _unit(prefs)
    lead = 0.0 if not getattr(space, "show_mode_column", True) else u
    size = _font_size(prefs)
    v2d = region.view2d
    fb = gpu.state.active_framebuffer_get()
    width = region.width
    try:
        # One bounded readback is much cheaper than synchronizing with the GPU
        # twice per visible row when several references are live.
        pixels = np.asarray(fb.read_color(0, 0, width, region.height, 4, 0, 'UBYTE'),
                            dtype=np.uint8).reshape(region.height, width, 4)
    except ValueError:
        return

    def bottom_of(k):
        return int(round(v2d.view_to_region(0, -(k + 1) * u, clip=False)[1]))

    k_lo = max(0, int(math.floor(-v2d.region_to_view(0, region.height - 1)[1] / u)))
    k_hi = int(math.floor(-v2d.region_to_view(0, 0)[1] / u))
    # Candidate name spans at each depth. Restriction icons (monitor, eye,
    # camera, selectability) can be to the right of the name: the last ink in
    # the whole row is not necessarily the last letter of its label.
    spans = []
    for name in named:
        w, _base, ref = _ref(name, size, u)
        ext = _extent(ref.any(axis=0), 0, w)
        if ext is None:
            continue
        for depth in range(0, 8):
            x = int(lead + (depth + 2.25) * u)
            if x + w <= width:
                spans.append((x + ext[0], x + ext[1]))
    reach = max(DX, round(u * .25)) + 3
    rows = {}
    for k in range(k_lo, k_hi + 1):
        y0 = bottom_of(k)
        lo, hi = max(0, y0), min(region.height, y0 + u)
        if hi <= lo or not 0 <= y0 + u // 2 < region.height:
            continue
        mid = pixels[y0+u//2:y0+u//2+1]
        bg = _background(mid)
        cols = _ink(mid, bg)[0]
        if not any(cols[max(0, a-reach):min(width, b+reach+1)].any() for a, b in spans):
            continue
        if lo == y0 and hi == y0+u:
            lines = pixels[lo:hi]
        else:
            # A scrolled row can have a visible name even when its border is clipped.
            lines = np.empty((u, width, 4), dtype=np.uint8)
            lines[:] = (*bg, 255)
            lines[lo-y0:hi-y0] = pixels[lo:hi]
        rows[k] = lines
    key = region.as_pointer()
    signature = (width, u, lead, size, tuple(named))
    cached = _rows.get(key)
    previous = cached[1] if cached and cached[0] == signature else {}
    current, hits = {}, []
    for k, lines in rows.items():
        digest = (bottom_of(k), blake2b(lines, digest_size=16).digest())
        got = previous.get(k)
        found = got[1] if got and got[0] == digest else find_rows({k: lines}, width, u, lead, list(named), size)
        current[k] = (digest, found)
        hits.extend(found)
    _rows[key] = (signature, current)
    while len(_rows) > 32:
        del _rows[next(iter(_rows))]
    SEEN[region.as_pointer()] = [(h[4], named[h[4]]) for h in hits]
    if not hits:
        return
    from mathutils import Matrix
    with fb.bind():
        gpu.matrix.push_projection()
        gpu.matrix.push()
        try:
            gpu.matrix.load_identity()
            gpu.matrix.load_projection_matrix(Matrix(((2.0/width, 0, 0, -1),
                (0, 2.0/region.height, 0, -1), (0, 0, 1, 0), (0, 0, 0, 1))))
            # Readbacks/offscreen glyph rendering may leave a full-window viewport even
            # though the active framebuffer is this editor's region texture.
            gpu.state.viewport_set(0, 0, region.width, region.height)
            gpu.state.scissor_set(0, 0, region.width, region.height)
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            for k, depth, dx, dy, name in hits:
                lines = rows[k]
                bg = _background(lines)
                w, base, _mask = _ref(name, size, u)
                x = int(lead + (depth + 2.25) * u) + dx
                y0 = bottom_of(k)
                band = lines[:, max(0, x):min(width, x + w), :3]
                diff = np.abs(band - np.asarray(bg, dtype=np.int16)).sum(axis=-1)
                if diff.size and diff.max() > INK:
                    iy, ix = np.unravel_index(int(diff.argmax()), diff.shape)
                    text_rgb = tuple(int(c) for c in band[iy, ix])
                else:
                    text_rgb = (220, 220, 220)
                gpu.state.blend_set('NONE')
                x0, x1 = x - 1, x + w + 2
                batch = batch_for_shader(shader, 'TRIS', {"pos": [(x0, y0 + 1), (x1, y0 + 1), (x1, y0 + u - 1),
                                                                  (x0, y0 + u - 1)]}, indices=[(0, 1, 2), (0, 2, 3)])
                shader.uniform_float("color", (bg[0] / 255.0, bg[1] / 255.0, bg[2] / 255.0, 1.0))
                batch.draw(shader)
                gpu.state.blend_set('ALPHA')
                blf.size(0, size)
                color = live.COLOR if bpy.data.objects.get(name) in live_objects else tuple(c/255 for c in text_rgb)
                blf.color(0, *color, 1.0)
                blf.position(0, x + 1, y0 + base + dy, 0)
                blf.draw(0, named[name])
            gpu.state.blend_set('NONE')
        finally:
            gpu.matrix.pop()
            gpu.matrix.pop_projection()



def register():
    _handle[0] = bpy.types.SpaceOutliner.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL')


def unregister():
    if _handle[0] is not None:
        bpy.types.SpaceOutliner.draw_handler_remove(_handle[0], 'WINDOW')
        _handle[0] = None
    _refs.clear()
    _rows.clear()
    SEEN.clear()
