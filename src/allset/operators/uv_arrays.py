# SPDX-License-Identifier: GPL-3.0-or-later
"""UV Editor read-outs in numpy (#170 #172): the per-redraw data of the UV HUD (ui/uv_hud.py) and the shell
/ texture borders (ui/uv_display.py) without Python loops over every BMesh loop.

On a 48 400-face sphere in the UV Editor (Blender 4.5, Maya layout) the Python versions took
1.2-1.9 s per redraw after every mesh or selection change, so one click in the UV Editor froze Blender ~3 s, a shell
drag 12 s and Cut UV Edges 36 s (Windows reports "Not responding" after 5 s). These are the same rules on arrays:

- topology + UVs: the evaluated edit mesh's ``to_mesh()`` (62 k faces in 8 ms) when no modifier is shown
  in edit mode (then it is the cage; same element order as the BMesh), else one BMesh pass;
- selection / hidden flags: always from the BMesh (the evaluated mesh's selection may lag).

``uv_points`` = uv_shells.uv_points (same vertex, coordinates within uv_tools.EPS, first-fit in loop-index order),
``maya_shells`` = uv_hud.maya_shells (faces sharing any UV), ``border_loops`` = uv_display.border_segments (an edge
side is a border unless another shown face has the same UVs at both of its ends). tests/test_step254_uv_speed.py
checks each against the Python version.
"""

from itertools import chain

import numpy as np

from .. import compat
from .uv_tools import EPS


class Arrays:
    """One edit mesh: faces F, loops L (face order), verts V."""
    __slots__ = ("loop_start", "loop_total", "corner_vert", "corner_edge", "corner_face", "corner_next", "uv",
                 "face_hide", "face_sel", "vert_sel", "edge_seam", "_uv_sel")

    def uv_sel(self, bm, uv, shown):
        """Per-loop UV selection (UV Sync off), read from the BMesh for the loops of ``shown`` faces only."""
        if self._uv_sel is None:
            out = np.zeros(len(self.corner_vert), bool)
            faces = np.nonzero(shown)[0]
            if len(faces):
                bm.faces.ensure_lookup_table()
                fs = bm.faces
                picked = np.fromiter(chain.from_iterable(
                    (compat.uv_vert_selected(l, uv) for l in fs[i].loops) for i in faces.tolist()),
                    bool, int(self.loop_total[faces].sum()))
                out[_face_loops(self, faces)] = picked
            self._uv_sel = out
        return self._uv_sel


def _face_loops(a, faces):
    """Loop indices of ``faces`` (ascending face order -> ascending loop order)."""
    starts, totals = a.loop_start[faces], a.loop_total[faces]
    if not len(faces):
        return np.zeros(0, np.int64)
    offs = np.repeat(starts - np.cumsum(totals) + totals, totals)
    return np.arange(int(totals.sum())) + offs


def _finish(a, n_loops):
    a.corner_face = np.repeat(np.arange(len(a.loop_start)), a.loop_total)
    nxt = np.arange(1, n_loops + 1)
    ends = a.loop_start + a.loop_total - 1
    nxt[ends] = a.loop_start
    a.corner_next = nxt
    a._uv_sel = None
    return a


def _read_evaluated(ob, depsgraph, bm, uv_name):
    ev = ob.evaluated_get(depsgraph)
    me = ev.to_mesh()
    try:
        if (len(me.polygons) != len(bm.faces) or len(me.vertices) != len(bm.verts)
                or len(me.edges) != len(bm.edges)):
            return None
        layer = me.uv_layers.get(uv_name)
        if layer is None:
            return None
        nf, nl = len(me.polygons), len(me.loops)
        a = Arrays()

        def ints(coll, name, n):     # int32 buffers: foreach_get converts other dtypes item by item (slow)
            buf = np.empty(n, np.int32)
            coll.foreach_get(name, buf)
            return buf.astype(np.int64)
        a.loop_start = ints(me.polygons, "loop_start", nf)
        a.loop_total = ints(me.polygons, "loop_total", nf)
        # the corner attributes read faster than MeshLoop.vertex_index / edge_index (12 vs 22-32 ms on 240 k loops),
        # the UV attribute's "vector" faster than MeshUVLoop.uv (0.1 vs 12 ms)
        attrs = me.attributes
        cv, ce, uva = attrs.get(".corner_vert"), attrs.get(".corner_edge"), attrs.get(uv_name)
        a.corner_vert = ints(cv.data, "value", nl) if cv is not None else ints(me.loops, "vertex_index", nl)
        a.corner_edge = ints(ce.data, "value", nl) if ce is not None else ints(me.loops, "edge_index", nl)
        co = np.empty(nl * 2, np.float32)
        if uva is not None and uva.domain == 'CORNER' and uva.data_type == 'FLOAT2':
            uva.data.foreach_get("vector", co)
        else:
            layer.data.foreach_get("uv", co)
        a.uv = co.reshape(-1, 2).astype(np.float64)
        return _finish(a, nl)
    finally:
        ev.to_mesh_clear()


def _read_bmesh(bm, uv):
    bm.verts.index_update()
    bm.edges.index_update()
    faces = bm.faces
    a = Arrays()
    a.loop_total = np.fromiter((len(f.loops) for f in faces), np.int64, len(faces))
    a.loop_start = np.cumsum(a.loop_total) - a.loop_total
    nl = int(a.loop_total.sum())
    loops = [l for f in faces for l in f.loops]
    a.corner_vert = np.fromiter((l.vert.index for l in loops), np.int64, nl)
    a.corner_edge = np.fromiter((l.edge.index for l in loops), np.int64, nl)
    a.uv = np.fromiter(chain.from_iterable(l[uv].uv for l in loops), np.float64, 2 * nl).reshape(-1, 2)
    return _finish(a, nl)


# Kit UV Editor draw handlers that walked the edit BMesh while a UV transform ran crashed Blender (heap corruption /
# access violation in tbbmalloc, 6 of 6 runs on 4.5.4 and 5.2.2 with 0.5.0: UV Editing workspace, W drag of faces or a
# shell; Python stack always uv_display.border_segments or uv_hud -> uv_shells._index_loops; none with the kit's UV
# draw options off, #170 #172). So while one of these modals runs the handlers touch neither the
# BMesh nor the evaluated mesh.
EDIT_MODALS = ("TRANSFORM_OT", "UV_OT", "SCULPT_OT", "MESH_OT")


def editing_now(wm):
    """A transform / UV / mesh modal operator runs in some window (the edit mesh is being changed)."""
    try:
        return any(op.bl_idname.startswith(EDIT_MODALS) for w in wm.windows for op in w.modal_operators)
    except (AttributeError, ReferenceError):
        return True


_shared = {}     # (object, mesh, uv layer) pointers -> Arrays, until the next depsgraph update (invalidate)


def invalidate():
    _shared.clear()


def read(ob, bm, uv, depsgraph=None, evaluated=True, cached=False):
    """Arrays of ``ob``'s edit mesh (``bm`` = its BMesh, ``uv`` its active BMesh UV layer); ``cached``: shared by
    the UV Editor draw handlers until ``invalidate`` (their depsgraph handlers call it)."""
    me = ob.data
    key = (ob.as_pointer(), me.as_pointer(), uv.name, len(bm.faces), len(bm.verts), me.total_vert_sel,
           me.total_face_sel)
    if cached and key in _shared:
        return _shared[key]
    a = _read(ob, bm, uv, depsgraph, evaluated)
    if cached:
        _shared[key] = a
    return a


def _read(ob, bm, uv, depsgraph, evaluated):
    a = None
    if evaluated and depsgraph is not None and not any(
            md.show_viewport and md.show_in_editmode for md in ob.modifiers):
        a = _read_evaluated(ob, depsgraph, bm, uv.name)
    if a is None:
        a = _read_bmesh(bm, uv)
    a.face_hide = np.fromiter((f.hide for f in bm.faces), bool, len(bm.faces))
    a.face_sel = np.fromiter((f.select for f in bm.faces), bool, len(bm.faces))
    a.vert_sel = np.fromiter((v.select for v in bm.verts), bool, len(bm.verts))
    a.edge_seam = np.fromiter((e.seam for e in bm.edges), bool, len(bm.edges))
    return a


def shown_faces(a, synced):
    """Faces the UV Editor draws (uv_display.shown_faces): unhidden, and selected unless UV Sync is on."""
    return ~a.face_hide & (True if synced else a.face_sel)


# --- Maya UVs and shells ------------------------------------------------------------------------------------

def uv_points(a, loops):
    """Maya UVs of ``loops`` (ascending loop indices): (point id per loop, first loop of each point); points are
    numbered by their first loop index like uv_shells.uv_points."""
    n = len(loops)
    if not n:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    v = a.corner_vert[loops]
    order = np.lexsort((loops, v))
    sv, su = v[order], a.uv[loops][order]
    start = np.r_[0, np.nonzero(np.diff(sv))[0] + 1]
    sizes = np.diff(np.r_[start, n])
    rank = np.arange(n) - np.repeat(start, sizes)
    founder = np.empty(n, np.int64)
    is_founder = np.zeros(n, bool)
    for j in range(int(rank.max()) + 1):
        left = np.nonzero(rank == j)[0]
        for r in range(j):          # first-fit against the earlier UVs of the vertex, in the order they were made
            if not len(left):
                break
            prev = left - (j - r)
            d = su[left] - su[prev]
            ok = is_founder[prev] & (np.hypot(d[:, 0], d[:, 1]) <= EPS)
            founder[left[ok]] = prev[ok]
            left = left[~ok]
        founder[left] = left
        is_founder[left] = True
    first_sorted = loops[order]            # loop index per sorted position
    roots = np.nonzero(is_founder)[0]
    roots = roots[np.argsort(first_sorted[roots], kind="stable")]
    pid_of_root = np.empty(n, np.int64)
    pid_of_root[roots] = np.arange(len(roots))
    pid = np.empty(n, np.int64)
    pid[order] = pid_of_root[founder]
    return pid, first_sorted[roots]


def components(n, a, b):
    """Connected component label per node 0..n-1 for the edges (a[i], b[i]) (min-label hooking + pointer jumping)."""
    lab = np.arange(n)
    while True:
        la, lb = lab[a], lab[b]
        diff = la != lb
        if not diff.any():
            return lab
        np.minimum.at(lab, np.maximum(la[diff], lb[diff]), np.minimum(la[diff], lb[diff]))
        while True:
            nxt = lab[lab]
            if np.array_equal(nxt, lab):
                break
            lab = nxt


def statistics(a, bm, uv, synced, stack_eps):
    """uv_hud.mesh_statistics on arrays: (shells, selected shells, overlapping UVs, selected, reversed UVs, selected,
    selected UV coordinates)."""
    shown = shown_faces(a, synced)
    faces = np.nonzero(shown)[0]
    if not len(faces):
        return 0, 0, 0, 0, 0, 0, []
    loops = _face_loops(a, faces)
    pid, first = uv_points(a, loops)
    npts = len(first)
    lface = a.corner_face[loops]
    # shells: faces joined through a shared UV (Maya polyEvaluate -uvShell)
    lab = components(len(a.loop_start), lface, a.corner_face[first][pid])
    shell_of_face = lab
    shells = np.unique(shell_of_face[faces])
    picked = a.vert_sel[a.corner_vert[loops]] if synced else a.uv_sel(bm, uv, shown)[loops]
    psel = np.zeros(npts, bool)
    np.logical_or.at(psel, pid, picked)
    shells_sel = np.unique(shell_of_face[lface[psel[pid]]])
    # overlapping: a UV at the same spot (stack_eps cells) as a UV of another shell
    c = a.uv[first]
    cells = np.round(c / stack_eps).astype(np.int64)
    # one int64 key per cell / (cell, shell) pair: np.unique(axis=0) sorts rows far slower
    cx, cy = cells[:, 0] - cells[:, 0].min(), cells[:, 1] - cells[:, 1].min()
    _u, cell = np.unique(cx * (int(cy.max()) + 1) + cy, return_inverse=True)
    cell = cell.reshape(-1)
    pshell = shell_of_face[a.corner_face[first]]
    pairs = np.unique(cell * (int(pshell.max()) + 1) + pshell) // (int(pshell.max()) + 1)
    per_cell = np.bincount(pairs, minlength=len(_u))
    over = per_cell[cell] > 1
    # reversed: UVs of faces whose UV winding is clockwise
    p, q = a.uv[loops], a.uv[a.corner_next[loops]]
    cross = p[:, 0] * q[:, 1] - q[:, 0] * p[:, 1]
    area = np.zeros(len(a.loop_start))
    np.add.at(area, lface, cross)
    rev_loop = area[lface] * 0.5 < 0.0
    prev = np.zeros(npts, bool)
    np.logical_or.at(prev, pid, rev_loop)
    coords = [tuple(x) for x in c[psel].tolist()]
    return (len(shells), len(shells_sel), int(over.sum()), int((over & psel).sum()), int(prev.sum()),
            int((prev & psel).sum()), coords)


# --- shell borders ------------------------------------------------------------------------------------------

def _same(p, q):
    return (np.abs(p[:, 0] - q[:, 0]) <= EPS) & (np.abs(p[:, 1] - q[:, 1]) <= EPS)


def _joined(a, i, k):
    """Loop i's edge side continues into loop k's face with the same UVs at both ends (uv_tools._uv_at rule)."""
    nx = a.corner_next
    flip = a.corner_vert[k] == a.corner_vert[nx[i]]
    ka = np.where(flip, nx[k], k)
    kb = np.where(flip, k, nx[k])
    return (a.corner_face[i] != a.corner_face[k]) & _same(a.uv[i], a.uv[ka]) & _same(a.uv[nx[i]], a.uv[kb])


def border_loops(a, shown):
    """Ascending loop indices (of ``shown`` faces) whose edge side is a shell border."""
    loops = _face_loops(a, np.nonzero(shown)[0])
    if not len(loops):
        return loops
    e = a.corner_edge[loops]
    order = np.argsort(e, kind="stable")
    se, sl = e[order], loops[order]
    start = np.r_[0, np.nonzero(np.diff(se))[0] + 1]
    sizes = np.diff(np.r_[start, len(se)])
    joined = np.zeros(len(sl), bool)
    two = start[sizes == 2]
    if len(two):
        i, k = sl[two], sl[two + 1]
        joined[two] = _joined(a, i, k)
        joined[two + 1] = _joined(a, k, i)
    for s, z in zip(start[sizes > 2].tolist(), sizes[sizes > 2].tolist()):   # non-manifold edges: every pair
        grp = sl[s:s + z]
        for m in range(z):
            others = np.delete(grp, m)
            joined[s + m] = bool(_joined(a, np.full(len(others), grp[m]), others).any())
    seam = getattr(a, "edge_seam", None)
    if seam is not None and len(seam):
        joined &= ~seam[se]          # a cut edge (seam) is a border at once, though the shell holds together
    return np.sort(sl[~joined])


def border_points(a, shown):
    """float32 (2N x 2) UV line points of the shell borders (uv_display.segments_of)."""
    b = border_loops(a, shown)
    pts = np.empty((2 * len(b), 2), np.float32)
    pts[0::2] = a.uv[b]
    pts[1::2] = a.uv[a.corner_next[b]]
    return pts

