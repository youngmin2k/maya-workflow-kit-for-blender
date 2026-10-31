# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya UV Editor heads-up displays: View > Heads-Up Display > Isolate Select / UV Position / UV Statistics.

Maya:
all three are on in the factory UV Editor. Kit drawing: text #cfcfcf, ~10 px caps, 5 px from
the view's left / right edge, baseline 7 px above its bottom; a second line 20 px higher.

- UV Statistics, bottom right: "(a/b) UV shells, (c/d) overlapping UVs, (e/f) reversed UVs" — first number = among
  the selected components, second = over the objects (Maya counts objects selected as objects; Blender's edit-mode
  objects are always selected, so the kit always shows the totals). Shells are Maya's: faces sharing
  any UV, a corner is enough. Overlapping UVs = UVs lying exactly on
  a UV of another shell (stacked shells counted 8, a partly overlapping shell 0), reversed UVs = UVs of
  faces whose UV winding is clockwise.
- UV Position, bottom left: "U:  <u> V:  <v>" = centre of the selected UVs' bounding box (UVs 0.1 0.1 0.3 0.5 ->
  0.3), 3 decimals without trailing zeros; nothing when nothing is selected.
- Isolate Select: "Isolated Selection (Ctrl + 1)" centred one line above the bottom while the view is isolated.
"""

import time

import blf
import bmesh
import bpy
from bpy.props import BoolProperty

from ..operators import uv_arrays, uv_shells
from .. import compat

TEXT_RGB = (0.81, 0.81, 0.81)        # #cfcfcf (HUD text)
FONT_PX = 10                         # HUD caps ~7 px high
MARGIN_PX = 5
BASELINE_PX = 7
LINE_PX = 20
ISOLATE_TEXT = "Isolated Selection (Ctrl + 1)"
REFRESH_S = 0.25                     # statistics are recomputed at most this often (or after a depsgraph update)
STACK_EPS = 1e-6                     # "overlapping" = the same position (kit cuts sit uv_tools.NUDGE apart)

_handle = []
_cache = {"at": 0.0, "key": None, "value": None, "last": None}


# --- pure helpers (tests/test_step206_uv.py) ---------------------------------------------------------------------

def fmt(x):
    """Maya HUD number: 3 decimals, trailing zeros dropped (0.2, 0.123, 0.165)."""
    s = "%.3f" % x
    s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def position_text(points):
    if not points:
        return ""
    us = [p[0] for p in points]
    vs = [p[1] for p in points]
    return "U:  %s V:  %s" % (fmt((min(us) + max(us)) / 2), fmt((min(vs) + max(vs)) / 2))


def statistics_text(sel_shells, shells, sel_overlap, overlap, sel_reversed, reversed_):
    return "(%d/%d) UV shells, (%d/%d) overlapping UVs, (%d/%d) reversed UVs" % (
        sel_shells, shells, sel_overlap, overlap, sel_reversed, reversed_)


def _signed_area(face, uv):
    ls = face.loops
    a = 0.0
    for i in range(len(ls)):
        p, q = ls[i][uv].uv, ls[(i + 1) % len(ls)][uv].uv
        a += p.x * q.y - q.x * p.y
    return a * 0.5


def maya_shells(faces, pts):
    """{face: shell id} the way Maya counts shells (polyEvaluate -uvShell):
    faces sharing any UV are one shell, a shared corner is enough (Blender's islands need a shared edge)."""
    parent = {f: f for f in faces}

    def find(x):
        while parent[x] is not x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for p in pts:
        for l in p[1:]:
            a, b = find(p[0].face), find(l.face)
            if a is not b:
                parent[b] = a
    roots = {}
    return {f: roots.setdefault(find(f), len(roots)) for f in faces}


def mesh_statistics(bm, uv, synced):
    """(shells, selected shells, overlapping UVs, selected, reversed UVs, selected, selected UV coordinates)."""
    faces = [f for f in bm.faces if not f.hide and (synced or f.select)]
    if not faces:
        return 0, 0, 0, 0, 0, 0, []
    uv_shells._index_loops(bm)
    pts = uv_shells.uv_points(bm, uv, [l for f in faces for l in f.loops])
    owner = maya_shells(faces, pts)

    def picked(l):
        return l.vert.select if synced else compat.uv_vert_selected(l, uv)

    sel = [any(picked(l) for l in p) for p in pts]
    shells_sel = {owner[l.face] for p, s in zip(pts, sel) if s for l in p}
    # overlapping: a UV at the same spot as a UV of another shell
    cells = {}
    for i, p in enumerate(pts):
        c = p[0][uv].uv
        cells.setdefault((round(c.x / STACK_EPS), round(c.y / STACK_EPS)), []).append(i)
    over = set()
    for ids in cells.values():
        if len({owner[pts[i][0].face] for i in ids}) > 1:
            over.update(ids)
    rev_faces = {f for f in faces if _signed_area(f, uv) < 0.0}
    rev = {i for i, p in enumerate(pts) if any(l.face in rev_faces for l in p)}
    coords = [tuple(p[0][uv].uv) for p, s in zip(pts, sel) if s]
    return (len(set(owner.values())), len(shells_sel), len(over), sum(1 for i in over if sel[i]), len(rev),
            sum(1 for i in rev if sel[i]), coords)


def _edit_meshes(context):
    obs = getattr(context, "objects_in_mode_unique_data", None) or ()
    return [o for o in obs if o.type == 'MESH']


def collect(context):
    """Statistics over every mesh in edit mode, cached for REFRESH_S (numpy, operators/uv_arrays.py)."""
    synced = context.scene.tool_settings.use_uv_select_sync
    key = (synced, tuple(o.as_pointer() for o in _edit_meshes(context)))
    now = time.monotonic()
    if _cache["key"] == key:
        if _cache["value"] is not None and now - _cache["at"] < REFRESH_S:
            return _cache["value"]
    if uv_arrays.editing_now(context.window_manager):
        # a UV drag runs: keep the last numbers, never read the mesh now (crash fix, operators/uv_arrays.py)
        return _cache["last"] if _cache["key"] == key and _cache["last"] is not None else ("", "")
    # after a depsgraph update the arrays are shared with the border drawing (uv_display); the REFRESH_S re-read
    # reads afresh (a selection change does not always send a depsgraph update)
    shared = _cache["value"] is None
    tot = [0] * 6
    coords = []
    depsgraph = context.view_layer.depsgraph
    for ob in _edit_meshes(context):
        bm = bmesh.from_edit_mesh(ob.data)
        uv = bm.loops.layers.uv.active
        if uv is None:
            continue
        got = uv_arrays.statistics(uv_arrays.read(ob, bm, uv, depsgraph, cached=shared), bm, uv, synced, STACK_EPS)
        for i in range(6):
            tot[i] += got[i]
        coords += got[6]
    value = (statistics_text(tot[1], tot[0], tot[3], tot[2], tot[5], tot[4]), position_text(coords))
    _cache.update(at=now, key=key, value=value, last=value)
    return value


# --- drawing -----------------------------------------------------------------------------------------------------

def _draw():
    context = bpy.context
    wm = context.window_manager
    if not (wm.allset_uv_hud_statistics or wm.allset_uv_hud_position or wm.allset_uv_hud_isolate):
        return
    space = context.space_data
    region = context.region
    try:
        if space is None or space.mode != 'UV' or context.mode != 'EDIT_MESH':
            return
        scale = context.preferences.system.ui_scale or 1.0
        font = 0
        blf.size(font, FONT_PX * scale * 1.15)
        blf.color(font, *TEXT_RGB, 1.0)
        base = BASELINE_PX * scale
        margin = MARGIN_PX * scale
        stats, pos = ("", "")
        if wm.allset_uv_hud_statistics or wm.allset_uv_hud_position:
            stats, pos = collect(context)
        if wm.allset_uv_hud_statistics and stats:
            w = blf.dimensions(font, stats)[0]
            blf.position(font, region.width - margin - w, base, 0)
            blf.draw(font, stats)
        if wm.allset_uv_hud_position and pos:
            blf.position(font, margin, base, 0)
            blf.draw(font, pos)
        if wm.allset_uv_hud_isolate and getattr(wm, "allset_uv_isolate", False):
            w = blf.dimensions(font, ISOLATE_TEXT)[0]
            blf.position(font, (region.width - w) / 2, base + LINE_PX * scale, 0)
            blf.draw(font, ISOLATE_TEXT)
    except (ReferenceError, AttributeError, ValueError):
        _cache["value"] = None


@bpy.app.handlers.persistent
def _invalidate(_scene=None, _depsgraph=None):
    _cache["value"] = None
    uv_arrays.invalidate()


def _redraw(_self, context):
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'IMAGE_EDITOR':
                area.tag_redraw()


PROPS = (
    ("allset_uv_hud_isolate", "Isolate Select", "Maya UV Editor HUD: 'Isolated Selection' while the view is isolated"),
    ("allset_uv_hud_position", "UV Position", "Maya UV Editor HUD: centre of the selected UVs (bottom left)"),
    ("allset_uv_hud_statistics", "UV Statistics",
     "Maya UV Editor HUD: UV shells, overlapping UVs and reversed UVs, selected / total (bottom right)"),
)


def register():
    wm = bpy.types.WindowManager
    for name, label, tip in PROPS:
        setattr(wm, name, BoolProperty(name=label, description=tip, default=True, update=_redraw))
    _handle.append(bpy.types.SpaceImageEditor.draw_handler_add(_draw, (), 'WINDOW', 'POST_PIXEL'))
    bpy.app.handlers.depsgraph_update_post.append(_invalidate)


def unregister():
    if _invalidate in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_invalidate)
    while _handle:
        bpy.types.SpaceImageEditor.draw_handler_remove(_handle.pop(), 'WINDOW')
    wm = bpy.types.WindowManager
    for name, _l, _t in PROPS:
        if hasattr(wm, name):
            delattr(wm, name)
    _cache.update(at=0.0, key=None, value=None, last=None)
