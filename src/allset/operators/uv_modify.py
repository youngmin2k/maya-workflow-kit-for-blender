# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya UV Editor Modify commands.

Distribute UVs, Match Grid, Layout Along, Stack Similar Shells, Map Border and Straighten Border, with the default
options. Shells and Maya UVs (points: loops of one vertex sharing one coordinate, ordered by first loop index = Maya's UV
index for meshes built face by face) come from operators/uv_shells.py. Modify > Symmetrize is not here: Maya's
symmetrizeUV only acts after the Symmetrize UV tool's seam pick.
"""

import math

import bmesh
import bpy
from bpy.props import EnumProperty
from mathutils import Vector

from .. import compat, undo_steps
from . import uv_shells
from .uv_shells import _index_loops, _meshes, shells, target_shells, uv_points
from .uv_tools import sync, uv_bounds

GRID = 256                 # Match Grid factory: polyGridUV 256 256 1
STACK_TOLERANCE = 0.1      # Stack Similar factory: stackSimilarToleranceOptVar 0.1
GAP_TOLERANCE = 5          # Straighten Border factory: -gt 5


# --- Maya UVs ------------------------------------------------------------------------------------------------

def all_points(bm, uv):
    """Every Maya UV of the mesh (lists of loops), Maya UV-index order, and loop -> UV index."""
    pts = uv_points(bm, uv, [l for f in bm.faces if not f.hide for l in f.loops])
    return pts, {l: i for i, ls in enumerate(pts) for l in ls}


def _selected(loop, uv, synced):
    return loop.vert.select if synced else compat.uv_vert_selected(loop, uv)


def selected_ids(bm, uv, synced, pts):
    """Indices of the selected Maya UVs (any of its loops selected, on a face the UV Editor shows)."""
    return [i for i, ls in enumerate(pts)
            if any((synced or l.face.select) and _selected(l, uv, synced) for l in ls)]


def _get(pt, uv):
    return pt[0][uv].uv.copy()


def _set(pt, uv, p):
    for l in pt:
        l[uv].uv = p


# --- Distribute UVs ----------------------------------------------------------------------

def _round_off(value, precision=8):
    """Maya's rounding: scientific-looking values become 0, else round half away from zero."""
    if "e" in _mel_str(value):
        value = 0.0
    sign = (value > 0) - (value < 0)
    return math.trunc(value * 10 ** precision + sign * 0.5) / 10 ** precision


def _mel_str(value):
    """Float -> string as Maya writes it (10 significant digits, 1.0/3 -> "0.3333333333", 14.0 -> "14")."""
    return "%.10g" % value


def distribute_uvs(items, axis=0):
    """Maya Distribute UVs, factory Distance = bounding box: the selected UVs (``items`` = [(name, uv layer, point)]
    in selection order) sorted by position along ``axis`` — Maya sorts the strings "<pos + offset> <name>", so ties
    go by name — keep the first, and step the others by width / (count - 1)."""
    n = len(items)
    if n < 2:
        return 0
    vals = [_get(p, uv)[axis] for _, uv, p in items]
    step = (max(vals) - min(vals)) / (n - 1)
    offset = 5.0
    for v in vals:
        if v < offset:
            offset += v
    keyed = []
    for (name, uv, p), v in zip(items, vals):
        s = _mel_str(_round_off(v + offset))
        if "." not in s:
            s += ".0"
        keyed.append((s + " " + name, uv, p))
    order = [(uv, p) for _k, uv, p in sorted(keyed, key=lambda kp: kp[0])]
    if _get(order[0][1], order[0][0])[axis] > _get(order[-1][1], order[-1][0])[axis]:
        order.reverse()
    last = _get(order[0][1], order[0][0])[axis]
    for uv, p in order[1:]:
        q = _get(p, uv)
        q[axis] = last + step
        _set(p, uv, q)
        last = p[0][uv].uv[axis]          # read back (float32)
    return n


# --- Match Grid -------------------------------------------------------------------------------

def _grid_u(x, cell):
    """Match Grid u rule: nearer grid line (the upper one on a tie), then half a cell inward = the cell centre."""
    lo, hi = math.floor(x / cell) * cell, math.ceil(x / cell) * cell
    return lo + cell / 2 if x - lo < hi - x else hi - cell / 2


def _grid_v(y, cell):
    """Match Grid v rule: like u, but an exact tie (y on a grid line) takes the lower line."""
    lo, hi = math.floor(y / cell) * cell, math.ceil(y / cell) * cell
    return lo + cell / 2 if y - lo <= hi - y else hi - cell / 2


def match_grid(points, uv, grid_u=GRID, grid_v=GRID):
    cu, cv = 1.0 / max(1, abs(grid_u)), 1.0 / max(1, abs(grid_v))
    for p in points:
        q = _get(p, uv)
        _set(p, uv, Vector((_grid_u(q.x, cu), _grid_v(q.y, cv))))
    return len(points)


# --- shell borders -----------------------------------------------------------------------------------------------

def _shared(l, island_set, uv):
    """True if another face of the shell continues the UVs across this loop's edge."""
    a, b = l.vert, l.link_loop_next.vert
    pa, pb = l[uv].uv, l.link_loop_next[uv].uv
    for g in l.edge.link_faces:
        if g is l.face or g not in island_set:
            continue
        la = next(m for m in g.loops if m.vert is a)
        lb = next(m for m in g.loops if m.vert is b)
        if (la[uv].uv - pa).length <= 1e-5 and (lb[uv].uv - pb).length <= 1e-5:
            return True
    return False


def border_cycles(island, uv, where):
    """The shell's border loops as lists of Maya UV indices, in face-winding order (counter-clockwise for a shell
    that isn't flipped); ``where`` = loop -> UV index."""
    fs = set(island)
    nxt = {}
    for f in island:
        for l in f.loops:
            if not _shared(l, fs, uv):
                nxt.setdefault(where[l], []).append(where[l.link_loop_next])
    cycles, used = [], set()
    for start in sorted(nxt):
        for first in nxt[start]:
            if (start, first) in used:
                continue
            cyc, a, b = [start], start, first
            while (a, b) not in used:
                used.add((a, b))
                if b == start:
                    break
                cyc.append(b)
                a = b
                b = next((c for c in nxt.get(a, ()) if (a, c) not in used), start)
            cycles.append(cyc)
    return cycles


def outer_cycle(island, uv, where):
    cyc = border_cycles(island, uv, where)
    return max(cyc, key=len) if cyc else []


# --- Map Border (default options like Maya: Square) ---------------------------------------------------------------

def _square(t):
    """Point at perimeter parameter t in [0, 4) on the unit square, counter-clockwise from (0, 0)."""
    t %= 4.0
    if t < 1:
        return Vector((t, 0.0))
    if t < 2:
        return Vector((1.0, t - 1))
    if t < 3:
        return Vector((3 - t, 1.0))
    return Vector((0.0, 4 - t))


def map_border(groups, uv, pts, where):
    """Every border UV of each shell onto the 0-1 square: start = the border UV with the lowest index at (0, 0),
    counter-clockwise along the border, spaced by the 3D lengths of the border edges; inner UVs stay."""
    done = 0
    for g in groups:
        cyc = outer_cycle(g, uv, where)
        if len(cyc) < 3:
            continue
        k = cyc.index(min(cyc))
        cyc = cyc[k:] + cyc[:k]
        co = [pts[i][0].vert.co for i in cyc]
        lens = [(co[(j + 1) % len(co)] - co[j]).length for j in range(len(co))]
        total = sum(lens)
        if total <= 0:
            continue
        acc = 0.0
        for j, i in enumerate(cyc):
            _set(pts[i], uv, _square(4.0 * acc / total))
            acc += lens[j]
        done += 1
    return done


# --- Straighten Border (polyStraightenUVBorder -c 0 -pl 1 -bo 0 -gt 5) ----------------------------------------------

def straighten_chains(cycle, chosen, gap=GAP_TOLERANCE):
    """Chains (lists of positions in ``cycle``) to straighten: runs of selected border UVs joined across gaps of up to
    ``gap`` unselected UVs; a chain needs one selected border edge (two adjacent selected UVs); a chain that closes the
    whole border is left alone."""
    n = len(cycle)
    sel = [cycle[j] in chosen for j in range(n)]
    if not any(sel) or all(sel):
        return []
    s0 = next(j for j in range(n) if not sel[j])      # start the walk on an unselected UV
    runs = []                                          # [start, end] positions (cyclic, relative to s0)
    j = 0
    while j < n:
        if sel[(s0 + j) % n]:
            k = j
            while k + 1 < n and sel[(s0 + k + 1) % n]:
                k += 1
            runs.append([j, k])
            j = k + 1
        else:
            j += 1
    merged = [[runs[0][0], runs[0][1], runs[0][1] > runs[0][0]]]
    for a, b in runs[1:]:
        if a - merged[-1][1] - 1 <= gap:
            merged[-1][1] = b
            merged[-1][2] = merged[-1][2] or b > a
        else:
            merged.append([a, b, b > a])
    wrap = (n - merged[-1][1] - 1) + merged[0][0]       # unselected UVs between the last chain and the first
    if wrap <= gap:
        if len(merged) == 1:
            return []                                   # the chain closes the whole border loop
        last = merged.pop()
        merged[0] = [last[0], merged[0][1] + n, last[2] or merged[0][2]]
    return [[(s0 + j) % n for j in range(a, b + 1)] for a, b, has_edge in merged if has_edge and b > a]


def straighten(cycle, chains, pts, uv):
    """Each chain onto the segment between its end UVs, spaced by the chain's own UV lengths (preserve length 1,
    curvature 0, blend 0)."""
    done = 0
    for ch in chains:
        ps = [_get(pts[cycle[j]], uv) for j in ch]
        cum = [0.0]
        for a, b in zip(ps, ps[1:]):
            cum.append(cum[-1] + (b - a).length)
        if cum[-1] <= 0:
            continue
        p0, p1 = ps[0], ps[-1]
        for j, c in zip(ch[1:-1], cum[1:-1]):
            _set(pts[cycle[j]], uv, p0 + (p1 - p0) * (c / cum[-1]))
        done += 1
    return done


# --- Layout Along (default options like Maya) -------------------------------------------------------------------------

def _signed_area(island, uv):
    a = 0.0
    for f in island:
        ps = [l[uv].uv for l in f.loops]
        a += sum(ps[i - 1].x * ps[i].y - ps[i].x * ps[i - 1].y for i in range(len(ps))) / 2
    return a


def _transform(island, uv, fn):
    for ls in uv_points(None, uv, [l for f in island for l in f.loops]):
        _set(ls, uv, fn(_get(ls, uv)))


def layout_along(groups, uv, direction='U'):
    """Maya Layout Along U: flipped shells are flipped back (mirror in v), a shell wider than tall turns 90 degrees
    clockwise, the shells go left to right by height (tallest first; ties by shell order), bottoms on v = 0, no gap,
    one scale for all so the row fits the 0-1 square. V = that row turned 90 degrees counter-clockwise, each shell's
    left side on u = 0."""
    if not groups:
        return 0
    for g in groups:
        if _signed_area(g, uv) < 0:
            _transform(g, uv, lambda p: Vector((p.x, -p.y)))
        lo, hi = uv_bounds(g, uv)
        if hi.x - lo.x > hi.y - lo.y:
            _transform(g, uv, lambda p: Vector((p.y, -p.x)))
    sizes = {id(g): uv_bounds(g, uv) for g in groups}
    order = sorted(groups, key=lambda g: -round(sizes[id(g)][1].y - sizes[id(g)][0].y, 6))
    total_w = sum(sizes[id(g)][1].x - sizes[id(g)][0].x for g in groups)
    max_h = max(sizes[id(g)][1].y - sizes[id(g)][0].y for g in groups)
    big = max(total_w, max_h)
    s = 1.0 / big if big > 1e-12 else 1.0
    u = 0.0
    for g in order:
        lo, hi = sizes[id(g)]
        x0 = u
        _transform(g, uv, lambda p, lo=lo, x0=x0: Vector((x0 + (p.x - lo.x) * s, (p.y - lo.y) * s)))
        u += (hi.x - lo.x) * s
    if direction == 'V':
        for g in groups:
            _transform(g, uv, lambda p: Vector((-p.y, p.x)))
        u_min = min(uv_bounds(g, uv)[0].x for g in groups)
        width = max(uv_bounds(g, uv)[1].x for g in groups) - u_min
        for g in groups:
            d = u_min - uv_bounds(g, uv)[0].x + width
            _transform(g, uv, lambda p, d=d: Vector((p.x + d, p.y)))
    return len(groups)


# --- Stack Similar Shells (default tolerance 0.1) --------------------------------------------------------------------

def _signature(cycle, pts, uv):
    """Border features of a shell (Stack Similar): per border UV the length to the previous one,
    the previous-to-next length and the cross product of the unit vectors to both neighbours."""
    ps = [_get(pts[i], uv) for i in cycle]
    n = len(ps)
    lens, tri, cross = [], [], []
    for j in range(n):
        a, p, b = ps[j - 1], ps[j], ps[(j + 1) % n]
        lens.append((p - a).length)
        tri.append((b - a).length)
        va, vb = a - p, b - p
        if va.length > 0:
            va = va / va.length
        if vb.length > 0:
            vb = vb / vb.length
        cross.append(va.x * vb.y - va.y * vb.x)
    return ps, lens, tri, cross, sum(lens)


def _match_shift(target, cand, tolerance):
    """Shift k so cand's border UV (j + k) matches target's UV j, or None (no mirror match: Maya leaves mirrored
    shells)."""
    _tp, tl, tt, tc, tper = target
    _cp, cl, ct, cc, cper = cand
    n = len(tl)
    if len(cl) != n or cper <= 0:
        return None
    r = tper / cper
    lim_len, lim_cross = tolerance / 2, tolerance
    for k in range(n):
        ok = True
        for j in range(n):
            i = (j + k) % n
            dl = (tl[j] - cl[i] * r) / (tl[j] + cl[i] * r) if tl[j] + cl[i] * r else 0.0
            dt = (tt[j] - ct[i] * r) / (tt[j] + ct[i] * r) if tt[j] + ct[i] * r else 0.0
            if abs(dl) > lim_len or abs(dt) > lim_len or abs(tc[j] - cc[i]) > lim_cross:
                ok = False
                break
        if ok:
            return k
    return None


def stack_similar(groups, uv, pts, where, tolerance=STACK_TOLERANCE):
    """Each selected shell whose border matches an earlier selected shell's (same UV count, lengths within 5 %,
    corner turns within 0.1 after scaling by the perimeter ratio) moves onto it: translate + rotate + uniform scale
    (perimeter ratio), the first matched border UVs land on each other."""
    if len(groups) < 2:
        return 0
    kept = []
    moved = 0
    for g in groups:
        cyc = outer_cycle(g, uv, where)
        if len(cyc) < 3:
            continue
        sig = _signature(cyc, pts, uv)
        if sig[4] < 1e-4:
            continue
        hit = None
        for tsig in kept:
            k = _match_shift(tsig, sig, tolerance)
            if k is not None:
                hit = (tsig, k)
                break
        if hit is None:
            kept.append(sig)
            continue
        tsig, k = hit
        n = len(sig[0])
        ta, tb = tsig[0][0], tsig[0][1]
        ca, cb = sig[0][k], sig[0][(k + 1) % n]
        scale = tsig[4] / sig[4]
        vt, vc = tb - ta, cb - ca
        ang = math.atan2(vt.y, vt.x) - math.atan2(vc.y, vc.x)
        c, s = math.cos(ang), math.sin(ang)

        def fn(p, ca=ca, ta=ta, c=c, s=s, scale=scale):
            d = p - ca
            return ta + Vector((c * d.x - s * d.y, s * d.x + c * d.y)) * scale
        _transform(g, uv, fn)
        moved += 1
    return moved


# --- operators -----------------------------------------------------------------------------------------------------

class _ModOp(uv_shells._ShellOp):
    def run_points(self, context, ob, bm, uv, synced, pts, where):
        raise NotImplementedError

    def run(self, context, bm, uv, synced):
        pts, where = all_points(bm, uv)
        return self.run_points(context, self._ob, bm, uv, synced, pts, where)

    def execute(self, context):
        done = 0
        synced = sync(context)
        self._fallback = not uv_shells.uv_tools.picked_anywhere(context)
        for ob in _meshes(context):
            bm = bmesh.from_edit_mesh(ob.data)
            uv = bm.loops.layers.uv.verify()
            _index_loops(bm)
            self._ob = ob
            got = self.run(context, bm, uv, synced)
            if got:
                done += got
                bmesh.update_edit_mesh(ob.data)
        if not done:
            self.report({'WARNING'}, self.empty)
            return {'CANCELLED'}
        return {'FINISHED'}


def picked_shells(bm, uv, synced):
    """Shells with a whole face in the selection (Maya maps / straightens nothing for a lone inner UV)."""
    every = shells(bm, uv)
    if synced:
        picked = {f for f in bm.faces if f.select}
    else:
        picked = {f for f in bm.faces if f.select and all(compat.uv_vert_selected(l, uv) for l in f.loops)}
    return [g for g in every if picked & set(g)]


@undo_steps.no_redo_panel
class ALLSET_OT_uv_distribute_uvs(_ModOp, bpy.types.Operator):
    """Space the selected UVs evenly between the outermost ones (Maya Distribute UVs)"""
    bl_idname = "allset.uv_distribute_uvs"
    bl_label = "Distribute UVs"
    empty = "Select two or more UVs"

    axis: EnumProperty(items=[('U', "U", ""), ('V', "V", "")], default='U', options={'SKIP_SAVE'})

    def execute(self, context):
        synced = sync(context)
        items, edited = [], []
        for ob in _meshes(context):
            bm = bmesh.from_edit_mesh(ob.data)
            uv = bm.loops.layers.uv.verify()
            _index_loops(bm)
            pts, _where = all_points(bm, uv)
            ids = selected_ids(bm, uv, synced, pts)
            if ids:
                edited.append((ob, bm, uv))
                items += [("%s.map[%d]" % (ob.name, i), uv, pts[i]) for i in ids]
        if len(items) < 2:
            self.report({'WARNING'}, self.empty)
            return {'CANCELLED'}
        distribute_uvs(items, 0 if self.axis == 'U' else 1)
        for ob, _bm, _uv in edited:
            bmesh.update_edit_mesh(ob.data)
        return {'FINISHED'}


@undo_steps.no_redo_panel
class ALLSET_OT_uv_match_grid(_ModOp, bpy.types.Operator):
    """Move each selected UV to the centre of its 1/256 grid cell (default 256 x 256, pixel
    centres; Maya Match Grid)"""
    bl_idname = "allset.uv_match_grid"
    bl_label = "Match Grid"
    empty = "Select UVs"

    def run_points(self, context, ob, bm, uv, synced, pts, where):
        return match_grid([pts[i] for i in selected_ids(bm, uv, synced, pts)], uv)


@undo_steps.no_redo_panel
class ALLSET_OT_uv_layout_along(_ModOp, bpy.types.Operator):
    """Lay the selected shells out in one row along U, tallest first, scaled to fit the 0-1 square (Maya Layout
    Along)"""
    bl_idname = "allset.uv_layout_along"
    bl_label = "Layout Along"
    empty = "Select UV shells"

    direction: EnumProperty(items=[('U', "U", ""), ('V', "V", "")], default='U', options={'SKIP_SAVE'})

    def run_points(self, context, ob, bm, uv, synced, pts, where):
        return layout_along(target_shells(bm, uv, synced, self._fallback), uv, self.direction)


@undo_steps.no_redo_panel
class ALLSET_OT_uv_stack_similar(_ModOp, bpy.types.Operator):
    """Stack every selected shell that has the same shape as an earlier one onto it (Maya Stack Similar Shells)"""
    bl_idname = "allset.uv_stack_similar"
    bl_label = "Stack Similar Shells"
    empty = "No similar UV shells in the selection"

    def run_points(self, context, ob, bm, uv, synced, pts, where):
        return stack_similar(target_shells(bm, uv, synced, self._fallback), uv, pts, where)


@undo_steps.no_redo_panel
class ALLSET_OT_uv_map_border(_ModOp, bpy.types.Operator):
    """Put the border UVs of the selected shells on the 0-1 square, spaced by the 3D edge lengths (Maya Map Border,
    factory Square)"""
    bl_idname = "allset.uv_map_border"
    bl_label = "Map Border"
    empty = "Select faces of a UV shell"

    def run_points(self, context, ob, bm, uv, synced, pts, where):
        return map_border(picked_shells(bm, uv, synced), uv, pts, where)


@undo_steps.no_redo_panel
class ALLSET_OT_uv_straighten_border(_ModOp, bpy.types.Operator):
    """Line up the selected border UVs between the two end ones (Maya Straighten Border; gaps of up to 5 UVs are
    filled)"""
    bl_idname = "allset.uv_straighten_border"
    bl_label = "Straighten Border"
    empty = "Select a run of border UVs (an open part of a shell border)"

    def run_points(self, context, ob, bm, uv, synced, pts, where):
        chosen = set(selected_ids(bm, uv, synced, pts))
        if not chosen:
            return 0
        done = 0
        for g in shells(bm, uv):
            for cyc in border_cycles(g, uv, where):
                done += straighten(cyc, straighten_chains(cyc, chosen), pts, uv)
        return done


classes = (ALLSET_OT_uv_distribute_uvs, ALLSET_OT_uv_match_grid, ALLSET_OT_uv_layout_along, ALLSET_OT_uv_stack_similar,
           ALLSET_OT_uv_map_border, ALLSET_OT_uv_straighten_border)
