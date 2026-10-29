# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Quad Draw (Mesh Tools > Quad Draw, Ctrl+Shift+Q): retopology on a live surface (docs/steps/step_144_poly.md
「계획」 5, GitHub #30).

The kit tool ``allset.quad_draw_tool`` (edit mode, ui/mesh_tools_poly.py) edits one mesh — the selected one, or a new
empty ``polySurfaceN`` (``allset.quad_draw_start``) — on the Make Live mesh list, or Maya's construction plane
when no surface is live. Unrelated visible meshes never participate.

- click = a dot on the surface; press-drag on a dot / vertex / edge / face = move it along the surface (Auto-weld:
  eligible points snap during the drag and weld on release); middle-drag = move too;
- Shift+click = fill: the polygon of the dots / border vertices around the mouse (4, else 3); Shift+drag = relax brush;
- Ctrl+click on an edge = edge loop there (new vertices on the surface);
- Ctrl+Shift+click = delete the dot / vertex / edge / face under the mouse;
- Tab held + drag from a border edge = extend it by a quad (Extend: Edge / Loop / Border), from a border vertex with two
  border edges = the quad of the vertex, its two border neighbours and the mouse point (an inner corner, #180), from
  empty space = a strip of quads Quad Strip Width pixels wide;
- hover previews (Shift: the fill, Ctrl: the loop, Ctrl+Shift: what goes, Tab: the border edge).
Pure parts (``fill_order``, ``fill_face``, ``extend_edges``, ``corner_quad``, ``strip_pairs``, ``relax``,
``delete_at``) are tested headless
(tests/test_step144_poly.py).
"""

import itertools
import math

import bmesh
import bpy
import gpu
from bpy.props import BoolProperty
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from . import mesh_tools, multi_cut, poly_draw, preselect

TOOL = "allset.quad_draw_tool"
DOT_LAYER = "allset_dot"   # int vertex layer: 1 = a Quad Draw dot (a loose vertex until a face uses it)
DRAG_PX = 4.0           # a press that moves less than this is a click
BRUSH_PX = 50.0         # relax brush radius [K]
RELAX_STEP = 0.5        # share of the way to the neighbours' average per brush move [K]
DOT_RGB = (0.26, 1.0, 0.64)        # Maya selection green #43ffa3 for the dots [I]
FILL_RGB = (0.26, 1.0, 0.64)
LOOP_RGB = (1.0, 0.55, 0.1)
DELETE_RGB = (1.0, 0.2, 0.2)
DOT_SIZE = 8.0
LINE_PX = 2.0


# --- pure: fill ---------------------------------------------------------------------------------------

def _inside(poly, p):
    """Point-in-polygon (even-odd) in 2D."""
    x, y = p
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1:
            inside = not inside
    return inside


def _area(poly):
    return 0.5 * sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1]))


def _simple(poly):
    """No two non-adjacent sides cross."""
    n = len(poly)

    def cross(a, b, c, d):
        def orient(p, q, r):
            return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return orient(a, b, c) * orient(a, b, d) < 0 and orient(c, d, a) * orient(c, d, b) < 0
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            if cross(poly[i], poly[(i + 1) % n], poly[j], poly[(j + 1) % n]):
                return False
    return True


def fill_order(xy, mouse, nearest=6, banned=()):
    """Maya Shift+click fill: indices (counter-clockwise on screen) of the 4 points of ``xy`` — else 3 — around
    ``mouse``, chosen among the ``nearest`` closest: the polygon must contain the mouse, be simple, and not be a set in
    ``banned`` (frozensets of indices, e.g. existing faces); the smallest such polygon wins. None if there is none."""
    order = sorted(range(len(xy)), key=lambda i: math.hypot(xy[i][0] - mouse[0], xy[i][1] - mouse[1]))[:nearest]
    for n in (4, 3):
        best = None
        for combo in itertools.combinations(order, n):
            if frozenset(combo) in banned:
                continue
            cx = sum(xy[i][0] for i in combo) / n
            cy = sum(xy[i][1] for i in combo) / n
            ring = sorted(combo, key=lambda i: math.atan2(xy[i][1] - cy, xy[i][0] - cx))
            poly = [tuple(xy[i]) for i in ring]
            area = _area(poly)
            if area <= 1e-6 or not _simple(poly) or not _inside(poly, mouse):
                continue
            if best is None or area < best[0]:
                best = (area, ring)
        if best is not None:
            return best[1]
    return None


def fill_face(bm, ring):
    """The fill polygon: ``ring`` items are BMVerts or local Vectors (new vertices), counter-clockwise as seen by the
    viewer (= Blender's front side). The face is flipped if it runs along a shared edge the same way as its neighbour
    (consistent normals). Returns the face or None."""
    verts = [r if isinstance(r, bmesh.types.BMVert) else bm.verts.new(r) for r in ring]
    if len(set(verts)) < 3 or bm.faces.get(verts) is not None:
        return None
    try:
        face = bm.faces.new(verts)
    except ValueError:
        return None
    flips = keeps = 0
    for loop in face.loops:
        for other in loop.edge.link_loops:
            if other.face is face:
                continue
            if other.vert is loop.vert:
                flips += 1
            else:
                keeps += 1
    if flips > keeps:
        face.normal_flip()
    face.normal_update()
    _indices(bm)
    return face


def _indices(bm):
    bm.verts.index_update()
    bm.edges.index_update()
    bm.faces.index_update()
    bm.normal_update()


# --- pure: extend / strip -------------------------------------------------------------------------------

def edge_loop(edge):
    """The edge loop through ``edge``: across each 4-edge vertex to the edge that shares no face with the last one
    (stops at borders, poles and where it closes)."""
    out, seen = [edge], {edge}
    for start in edge.verts:
        e, cur = edge, start
        while len(cur.link_edges) == 4:
            faces = set(e.link_faces)
            nxt = [x for x in cur.link_edges if x is not e and not set(x.link_faces) & faces]
            if len(nxt) != 1 or nxt[0] in seen:
                break
            e = nxt[0]
            seen.add(e)
            out.append(e)
            cur = e.other_vert(cur)
    return out


def border_loop(edge):
    """Border edges connected to border ``edge`` along the border (one open or closed chain)."""
    out, todo = {edge}, [edge]
    while todo:
        e = todo.pop()
        for v in e.verts:
            for e2 in v.link_edges:
                if e2.is_boundary and e2 not in out:
                    out.add(e2)
                    todo.append(e2)
    return list(out)


def border_chain(edge):
    """Boundary edge loop, stopping at corners/poles instead of turning around the entire border."""
    out, seen = [edge], {edge}
    for start in edge.verts:
        cur, previous = start, edge
        while len(cur.link_edges) == 3:
            candidates = [e for e in cur.link_edges if e.is_boundary and e is not previous]
            if len(candidates) != 1 or candidates[0] in seen:
                break
            previous = candidates[0]
            seen.add(previous)
            out.append(previous)
            cur = previous.other_vert(cur)
    return out


def extend_edges(bm, edges, offset, positions=None, created=None):
    """Tab+drag: a quad on each border edge, its far side = the edge's vertices moved by ``offset(co) -> new co``
    (shared between neighbouring edges). Returns the new faces."""
    new = {}
    faces = []
    for e in edges:
        if not e.is_valid or not e.is_boundary:
            continue
        b, a = poly_draw.edge_start(e)       # against the bordering face's winding
        for v in (a, b):
            if v not in new:
                co=positions[v.index] if positions is not None else offset(v.co.copy())
                new[v] = bm.verts.new(co)
                if created is not None:
                    created[v.index]=new[v]
        try:
            faces.append(bm.faces.new((b, a, new[a], new[b])))
        except ValueError:
            pass
    _indices(bm)
    return faces


def corner_neighbours(v):
    """(A, B): the other ends of the two border edges at border vertex ``v`` (in the winding a face appended there
    needs), or None when ``v`` doesn't have exactly two border edges."""
    border = [e for e in v.link_edges if e.is_boundary]
    if len(border) != 2:
        return None
    first, second = border
    start, end = poly_draw.edge_start(first)
    a = first.other_vert(v)
    b = second.other_vert(v)
    # the new face runs along ``first`` as edge_start says: A -> V when it starts at A, else V -> A (then reversed)
    return (a, b) if start is a else (b, a)


def corner_quad(bm, v, co):
    """Tab+drag from border vertex ``v`` (Maya 2026 Quad Draw, Autodesk's help "Extend edges with Quad Draw": with
    the Edge extend option a vertex can be dragged to create a polygon): the quad A, V, B, N of ``v``, its two border
    neighbours and a new vertex at local ``co``. Only where that quad fills the open side of ``v`` (an inner corner):
    at an outer corner or a straight border it would fold over the faces there, and nothing is made (delegated,
    [I]). Returns the face or None."""
    pair = corner_neighbours(v)
    if pair is None:
        return None
    a, b = pair
    n = sum((f.normal for f in v.link_faces), Vector())
    if n.length < 1e-9:
        return None
    n.normalize()

    def flat(p):
        d = p - v.co
        return d - n * d.dot(n)
    pa, pb, pn = flat(a.co), flat(b.co), flat(co)
    # N on the far side of A-B from V, and a convex quad A V B N seen along the normal
    ab = pb - pa
    side_v = ab.cross(-pa).dot(n)
    side_n = ab.cross(pn - pa).dot(n)
    if side_v * side_n >= 0:
        return None
    ring = [Vector(), pa, pn, pb]           # V, A, N, B in order around the quad
    turns = [(ring[(i + 1) % 4] - ring[i]).cross(ring[(i + 2) % 4] - ring[(i + 1) % 4]).dot(n) for i in range(4)]
    if not (all(t > 1e-12 for t in turns) or all(t < -1e-12 for t in turns)):
        return None
    if any(f.calc_center_median() is not None and _inside_quad(flat(f.calc_center_median()), ring, n)
           for f in v.link_faces):
        return None                          # the quad would lie over a face at V
    nv = bm.verts.new(co)
    try:
        face = bm.faces.new((a, v, b, nv))
    except ValueError:
        bm.verts.remove(nv)
        return None
    _indices(bm)
    return face


def _inside_quad(p, ring, n):
    signs = [(ring[(i + 1) % 4] - ring[i]).cross(p - ring[i]).dot(n) for i in range(4)]
    return all(x > 0 for x in signs) or all(x < 0 for x in signs)


def strip_pairs(path, width):
    """Tab+drag in empty space: (left, right) screen points every ``width`` pixels along ``path`` (a list of screen
    points), ``width`` apart across the path. Needs a path at least ``width`` long."""
    pts = [path[0]]
    acc = 0.0
    for a, b in zip(path, path[1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if seg < 1e-9:
            continue
        t = 0.0
        while acc + (seg - t) >= width:
            t += width - acc
            acc = 0.0
            pts.append((a[0] + (b[0] - a[0]) * t / seg, a[1] + (b[1] - a[1]) * t / seg))
        acc += seg - t
    if len(pts) < 2:
        return []
    out = []
    for k, p in enumerate(pts):
        q0 = pts[max(0, k - 1)]
        q1 = pts[min(len(pts) - 1, k + 1)]
        dx, dy = q1[0] - q0[0], q1[1] - q0[1]
        n = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / n * width / 2, dx / n * width / 2
        out.append(((p[0] + nx, p[1] + ny), (p[0] - nx, p[1] - ny)))
    return out


def strip_faces(bm, pairs):
    """Quads between consecutive (left, right) local points; winding: counter-clockwise for a path seen from the
    viewer going left to right on screen with left = +normal side (callers pass screen-ordered pairs)."""
    faces = []
    prev = None
    for left, right in pairs:
        cur = (bm.verts.new(left), bm.verts.new(right))
        if prev is not None:
            faces.append(bm.faces.new((prev[1], cur[1], cur[0], prev[0])))
        prev = cur
    _indices(bm)
    return faces


# --- pure: relax / delete -------------------------------------------------------------------------------

def relax(bm, verts, mode='AUTO_LOCK', step=RELAX_STEP, project=None):
    """Maya Quad Draw relax on ``verts``: each moves ``step`` of the way to its neighbours' average (border vertices
    along the border only). ``mode``: AUTO_LOCK = border vertices stay when an inner one is among ``verts``,
    INTERIOR = only inner vertices, BORDER = only border ones. ``project(co) -> co`` puts them back on the surface.
    Returns the moved vertices."""
    verts = [v for v in verts if v.is_valid and v.link_edges]
    inner = [v for v in verts if not v.is_boundary]
    border = [v for v in verts if v.is_boundary]
    if mode == 'INTERIOR' or (mode == 'AUTO_LOCK' and inner):
        moving = inner
    elif mode == 'ALL':
        moving = verts
    elif mode == 'BORDER':
        moving = border
    else:
        moving = border
    targets = {}
    for v in moving:
        if v.is_boundary and mode != 'ALL':
            nb = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
        else:
            nb = [e.other_vert(v) for e in v.link_edges]
        if not nb:
            continue
        avg = sum((u.co for u in nb), Vector()) / len(nb)
        targets[v] = v.co.lerp(avg, step)
    for v, co in targets.items():
        v.co = project(co) if project else co
    return list(targets)


def delete_at(bm, kind, index):
    """Ctrl+Shift+click: delete the face; an edge (inside: dissolved into one face; on the border: its face goes);
    a vertex (inside: dissolved; on the border: with its faces). True if something went."""
    seq = {'VERT': bm.verts, 'EDGE': bm.edges, 'FACE': bm.faces}[kind]
    seq.ensure_lookup_table()
    if index >= len(seq):
        return False
    el = seq[index]
    if kind == 'FACE':
        bmesh.ops.delete(bm, geom=[el], context='FACES')
    elif kind == 'EDGE':
        if len(el.link_faces) == 2:
            bmesh.ops.dissolve_edges(bm, edges=[el], use_verts=True)
        elif el.link_faces:
            bmesh.ops.delete(bm, geom=list(el.link_faces), context='FACES')
        else:
            bmesh.ops.delete(bm, geom=[el], context='EDGES')
    else:
        if el.link_faces and not el.is_boundary and len(el.link_edges) > 2:
            bmesh.ops.dissolve_verts(bm, verts=[el])
        else:
            bmesh.ops.delete(bm, geom=[el], context='VERTS')
    _indices(bm)
    return True


def delete_loop(bm, edge_index):
    """Ctrl+Shift+click an edge: its edge loop goes (inner edges dissolve; a border edge takes its faces)."""
    bm.edges.ensure_lookup_table()
    edge = bm.edges[edge_index]
    if len(edge.link_faces) != 2:
        return delete_at(bm, 'EDGE', edge_index)
    loop = [e for e in edge_loop(edge) if len(e.link_faces) == 2]
    bmesh.ops.dissolve_edges(bm, edges=loop, use_verts=True)
    _indices(bm)
    return True


def weld_target(xy, moved, mouse_xy, radius, exclude=()):
    """Index of the vertex whose screen point is within ``radius`` of ``mouse_xy`` (closest), not ``moved`` and not
    in ``exclude``; None if none (Auto-weld)."""
    best = None
    for i, p in enumerate(xy):
        if i == moved or i in exclude or p is None:
            continue
        d = math.hypot(p[0] - mouse_xy[0], p[1] - mouse_xy[1])
        if d <= radius and (best is None or d < best[0]):
            best = (d, i)
    return best[1] if best else None


# --- reference surface ----------------------------------------------------------------------------------

def reference_objects(context):
    """Only explicitly live meshes constrain Quad Draw; otherwise use the construction plane."""
    from . import live
    return live.objects(context.scene)


def surface_offset(context):
    """Offset in Blender units, from the Maya-style scene length-unit field."""
    s = poly_draw.settings(context)
    if not s.qd_offset_on or s.qd_surface_offset == 0:
        return 0.0
    from . import units
    return s.qd_surface_offset * units.maya_unit(context.scene)


def _surface_point(context, hit):
    if hit is None:
        return None
    s = poly_draw.settings(context)
    return hit[0] + hit[1] * surface_offset(context) if s.qd_offset_on else hit[0]


def surface_hit(context, region, rv3d, mouse, refs=None):
    """World point of the reference surface under ``mouse``, or None."""
    refs = reference_objects(context) if refs is None else refs
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse)
    ray = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse).normalized()
    from . import live
    hit = live.ray_hit(context, origin, ray, refs, poly_draw.settings(context).qd_snap_backfaces)
    return _surface_point(context, hit)


def place_point(context, region, rv3d, mouse, refs=None):
    """Where a dot goes: the surface under the mouse; with no reference surface at all, Maya's construction plane."""
    refs = reference_objects(context) if refs is None else refs
    if refs:
        return surface_hit(context, region, rv3d, mouse, refs)
    return poly_draw.construction_point(context, region, rv3d, mouse)


def project_point(context, w, refs=None, region=None, rv3d=None):
    """The closest reference surface point to world ``w`` (``w`` itself without a surface)."""
    refs = reference_objects(context) if refs is None else refs
    # Screen-ray projection follows the visible side of thin/folded surfaces. A nearest-only
    # query can jump to an unrelated sheet behind the point during relax/extend.
    from . import live
    nearest = None
    if refs and region is not None and rv3d is not None:
        base = w
        if surface_offset(context):
            # Project from the surface foot, not from an already offset point.
            # Reusing its shifted screen position adds a sideways drift each time.
            nearest = live.nearest(context, w, refs)
            if nearest is not None:
                base = nearest[0]
        xy = _screen_xy(region, rv3d, base)
        if xy is not None:
            hit = surface_hit(context, region, rv3d, xy, refs)
            if hit is not None:
                return hit
    hit = nearest if nearest is not None else live.nearest(context, w, refs)
    return _surface_point(context, hit) if hit else w


# --- live state -----------------------------------------------------------------------------------------

STATE = {"ob": None, "preview": None, "snap": [], "created": None, "overlays": {}, "timer": False}
_pick_projection = None
_fill_projection = None


def reset_preview():
    STATE["preview"] = None
    STATE["snap"] = []


def edit_object(context):
    ob = context.edit_object
    return ob if ob is not None and ob.type == 'MESH' else None


def tool_active(context):
    return context.mode == 'EDIT_MESH' and preselect.tool_id(context) == TOOL


def _ui_scale(context):
    return context.preferences.system.ui_scale or 1.0


def _screen_xy(region, rv3d, w):
    p = view3d_utils.location_3d_to_region_2d(region, rv3d, w)
    return (p.x, p.y) if p is not None else None


def dot_layer(bm, create=False):
    """The int vertex layer that marks Quad Draw dots (made first: a new layer invalidates element references)."""
    lay = bm.verts.layers.int.get(DOT_LAYER)
    if lay is None and create:
        lay = bm.verts.layers.int.new(DOT_LAYER)
    return lay


def dots(bm):
    """Maya's dots: loose vertices Quad Draw placed (no edge yet). Being vertices, they undo with the mesh."""
    lay = dot_layer(bm)
    if lay is None:
        return []
    return [v for v in bm.verts if v[lay] and not v.link_edges]


def add_dot(bm, co):
    """A dot at local ``co``; returns the vertex."""
    lay = dot_layer(bm, create=True)
    v = bm.verts.new(co)
    v[lay] = 1
    v.select = False
    _indices(bm)
    return v


def clear_dots(bm):
    """Remove every dot (Clear Dots, leaving the tool). Returns how many went."""
    gone = dots(bm)
    for v in gone:
        bm.verts.remove(v)
    if gone:
        _indices(bm)
    return len(gone)


def _reference_visible(context, region, rv3d, point, refs, clearance=0):
    """Reject the far sheet of a live reference, allowing coarse-face display sag."""
    if not refs:
        return True
    from . import live
    xy = _screen_xy(region, rv3d, point)
    if xy is None:
        return False
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, xy)
    delta = point-origin
    distance = delta.length
    if distance < 1e-12:
        return True
    hit = live.ray_hit(context, origin, delta/distance, refs, True)
    offset = abs(surface_offset(context))
    return not hit or (hit[0]-origin).length >= distance-max(1e-5,distance*1e-7)-offset*1.1-clearance


def component_at(context, region, rv3d, mouse, ob, edges_only=False):
    """('VERT', i) / ('EDGE', i, t) / ('FACE', i, local co) of ``ob`` under the mouse (dots are vertices), or None."""
    global _pick_projection
    c = next((c for candidate, c in preselect.caches(context) if candidate == ob), None)
    if c is None:
        return None
    key = (region.width, region.height, tuple(map(tuple, rv3d.perspective_matrix)), _ui_scale(context))
    if _pick_projection is None or _pick_projection[0] is not c or _pick_projection[1] != key:
        xy, front = preselect.project(c.co, rv3d.perspective_matrix, region.width, region.height)
        # A large vertex hit zone steals short edges and small faces. Compute a
        # local radius once per view, retaining the wider Ctrl-loop edge zone.
        import numpy as np
        shortest = np.full(len(xy), np.inf)
        if len(c.edges):
            lengths = np.linalg.norm(xy[c.edges[:,0]]-xy[c.edges[:,1]], axis=1)
            np.minimum.at(shortest, c.edges[:,0], lengths)
            np.minimum.at(shortest, c.edges[:,1], lengths)
        radius = np.minimum(8.0*_ui_scale(context), shortest*.22)
        radius = np.maximum(3.0*_ui_scale(context), radius)
        _pick_projection = c, key, xy, front, radius
    _, _, xy, front, radius = _pick_projection
    cs = [(ob, c)]
    xray = preselect._xray(context.space_data)
    scale = _ui_scale(context)
    refs = reference_objects(context)
    import numpy as np
    if not edges_only:
        distance2 = ((xy - mouse)**2).sum(axis=1)
        near = np.flatnonzero(c.vok & front & (distance2 <= radius**2))
        for j in near[np.argsort(distance2[near])]:
            i = int(j)
            point = Vector(c.co[i])
            if not multi_cut._occluded(cs, region, rv3d, point, xray) and _reference_visible(context,region,rv3d,point,refs):
                return 'VERT', i
    if len(c.edges):
        distance, ts = preselect.segment_distance(mouse, xy[c.edges[:, 0]], xy[c.edges[:, 1]])
        ok = c.eok & front[c.edges[:, 0]] & front[c.edges[:, 1]]
        tolerance = multi_cut.EDGE_PX*scale if edges_only else 5.0*scale
        near = np.flatnonzero(ok & (distance <= tolerance))
        for j in near[np.argsort(distance[near])]:
            i = int(j)
            a, b = (Vector(c.co[k]) for k in c.edges[i])
            point = a.lerp(b,float(ts[i]))
            if not multi_cut._occluded(cs, region, rv3d, point, xray) and _reference_visible(context,region,rv3d,point,refs,(a-b).length*.5):
                return 'EDGE', i, multi_cut.ray_edge_t(region, rv3d, a, b, mouse)
    if not edges_only:
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse)
        hit = c.ray(origin, direction)
        if hit is not None:
            point = origin + direction.normalized()*hit[0]
            f = c.bm.faces[hit[1]]
            clearance = max(((Vector(c.co[e.verts[0].index])-Vector(c.co[e.verts[1].index])).length for e in f.edges),default=0)*.5
            if _reference_visible(context,region,rv3d,point,refs,clearance):
                return 'FACE', hit[1], tuple(c.inv @ point)
    return None


def fill_candidates(bm):
    """Vertices a fill can use: dots, border vertices and vertices on no face yet."""
    return [v for v in bm.verts if not v.hide and (v.is_boundary or not v.link_faces)]


def fill_plan(context, region, rv3d, mouse, ob):
    """(ring of vertex indices, world points) for a Shift+click at ``mouse``, or None."""
    global _fill_projection
    from .quad_draw_fill import ScreenFill
    c = next((c for candidate,c in preselect.caches(context) if candidate==ob),None)
    if c is None:
        return None
    key=(region.width,region.height,tuple(map(tuple,rv3d.perspective_matrix)))
    if _fill_projection is None or _fill_projection[0] is not c or _fill_projection[1]!=key:
        xy,front=preselect.project(c.co,rv3d.perspective_matrix,region.width,region.height)
        allowed=[not v.hide and bool(front[v.index]) and (v.is_boundary or not v.link_faces) for v in c.bm.verts]
        counts=[len(e.link_faces) for e in c.bm.edges]
        faces=[tuple(v.index for v in f.verts) for f in c.bm.faces if not f.hide and all(front[v.index] for v in f.verts)]
        _fill_projection=c,key,ScreenFill(xy,allowed,c.edges,counts,faces,world=c.co)
    screen=_fill_projection[2]
    refs=reference_objects(context)
    def visible(i):
        point=Vector(c.co[i])
        if multi_cut._occluded([(ob,c)],region,rv3d,point,False):
            return False
        return _reference_visible(context,region,rv3d,point,refs)
    ring=screen.plan(mouse,visible)
    if ring is None:
        return None
    return list(ring),[Vector(c.co[i]) for i in ring]


def apply_fill(ob, ring):
    """Make the fill face through vertex indices ``ring`` (``fill_plan``); its dots become plain vertices. Returns the
    face or None."""
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    verts = [bm.verts[i] for i in ring]
    face = fill_face(bm, verts)
    if face is None:
        return None
    lay = dot_layer(bm)
    for v in face.verts:
        if lay is not None:
            v[lay] = 0
    for el in (*bm.verts, *bm.edges, *bm.faces):
        el.select = False
    bmesh.update_edit_mesh(ob.data)
    preselect.invalidate()
    return face


# --- drawing --------------------------------------------------------------------------------------------

_handles = []


def _lines(region, pts, rgb, px, alpha=1.0):
    if len(pts) < 2:
        return
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    shader.uniform_float("viewportSize", (region.width, region.height))
    shader.uniform_float("lineWidth", px)
    shader.uniform_float("color", (*rgb, alpha))
    batch_for_shader(shader, 'LINES', {"pos": pts}).draw(shader)


def _points(pts, rgb, px):
    if not pts:
        return
    shader = gpu.shader.from_builtin('POINT_UNIFORM_COLOR')
    gpu.state.point_size_set(px)
    shader.uniform_float("color", (*rgb, 1.0))
    batch_for_shader(shader, 'POINTS', {"pos": pts}).draw(shader)


def _ring_lines(pts):
    pts = [tuple(p) for p in pts]
    return [q for a, b in zip(pts, pts[1:] + pts[:1]) for q in (a, b)]


def _draw_view():
    context = bpy.context
    try:
        if not tool_active(context):
            return
        from ..ui import toolbox
        if toolbox.is_toolbox(context.space_data):
            return
        region = context.region
        scale = _ui_scale(context)
        from . import quad_draw_overlay
        quad_draw_overlay.draw(context)
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')
        pv = STATE["preview"]
        _points([tuple(p) for p in STATE["snap"]], FILL_RGB, DOT_SIZE*1.5*scale)
        if pv is not None:
            kind, data = pv
            if kind == 'FILL':
                _lines(region, _ring_lines(data), FILL_RGB, LINE_PX * scale)
            elif kind == 'LOOP':
                _lines(region, [tuple(p) for s in data for p in s], LOOP_RGB, LINE_PX * scale)
            elif kind in ('DELETE', 'TAB'):
                rgb = DELETE_RGB if kind == 'DELETE' else LOOP_RGB
                pts = [tuple(p) for p in data]
                if len(pts) == 1:
                    _points(pts, rgb, DOT_SIZE * 1.5 * scale)
                elif len(pts) == 2:
                    _lines(region, pts, rgb, LINE_PX * 2 * scale)
                else:
                    _lines(region, _ring_lines(pts), rgb, LINE_PX * 2 * scale)
            elif kind == 'EXTEND':
                _lines(region, [tuple(p) for p in data], FILL_RGB, LINE_PX * scale)
        ob = edit_object(context)
        if ob is not None:
            mw = ob.matrix_world
            bm = bmesh.from_edit_mesh(ob.data)     # keep the wrapper alive while its vertices are read
            _points([tuple(mw @ v.co) for v in dots(bm)], DOT_RGB, DOT_SIZE * scale)
        gpu.state.blend_set('NONE')
    except (ReferenceError, AttributeError, IndexError, ValueError, KeyError):
        pass


def _draw_pixel():
    context = bpy.context
    try:
        if not tool_active(context):
            return
        from ..ui import toolbox
        if toolbox.is_toolbox(context.space_data):
            return
        from . import quad_draw_overlay
        quad_draw_overlay.draw_front(context)
        pv = STATE["preview"]
        if pv is None or pv[0] != 'BRUSH':
            return
        region = context.region
        cx, cy, r = pv[1]
        pts = [(cx + r * math.cos(a * math.tau / 48), cy + r * math.sin(a * math.tau / 48), 0.0) for a in range(48)]
        gpu.state.blend_set('ALPHA')
        _lines(region, [q for a, b in zip(pts, pts[1:] + pts[:1]) for q in (a, b)], FILL_RGB, 1.5, 0.8)
        gpu.state.blend_set('NONE')
    except (ReferenceError, AttributeError, IndexError, ValueError):
        pass


def _redraw(context):
    if context.area is not None:
        context.area.tag_redraw()


def _view_ok(context):
    r = context.region
    return r is not None and r.type == 'WINDOW' and context.region_data is not None


def _mouse(event):
    return (event.mouse_region_x, event.mouse_region_y)


# --- hover --------------------------------------------------------------------------------------------

def _component_points(ob, comp):
    bm = bmesh.from_edit_mesh(ob.data)
    mw = ob.matrix_world
    kind, i = comp[0], comp[1]
    if kind == 'VERT':
        bm.verts.ensure_lookup_table()
        return [mw @ bm.verts[i].co]
    if kind == 'EDGE':
        bm.edges.ensure_lookup_table()
        return [mw @ v.co for v in bm.edges[i].verts]
    bm.faces.ensure_lookup_table()
    return [mw @ v.co for v in bm.faces[i].verts]


def corner_vertex_at(context, region, rv3d, mouse, ob):
    """Index of a border vertex of ``ob`` with two border edges under ``mouse`` (Tab+drag makes a quad there), or
    None."""
    comp = component_at(context, region, rv3d, mouse, ob)
    if comp is None or comp[0] != 'VERT':
        return None
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    if comp[1] >= len(bm.verts) or corner_neighbours(bm.verts[comp[1]]) is None:
        return None
    return comp[1]


def _corner_points(ob, vi):
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    v = bm.verts[vi]
    mw = ob.matrix_world
    return [(mw @ v.co, mw @ e.other_vert(v).co) for e in v.link_edges if e.is_boundary]


def update_hover(context, region, rv3d, mouse, ctrl, shift, tab=False):
    ob = edit_object(context)
    STATE["preview"] = None
    STATE['hover_component'] = None
    if ob is None:
        return
    if tab:
        vi = corner_vertex_at(context, region, rv3d, mouse, ob)
        if vi is not None:
            STATE["preview"] = ('EXTEND', [p for seg in _corner_points(ob, vi) for p in seg])
            return
        bm_edge = poly_draw.border_edge_at(context, region, rv3d, mouse, ob)
        if bm_edge is not None:
            STATE["preview"] = ('TAB', _component_points(ob, ('EDGE', bm_edge)))
        return
    if shift and not ctrl:
        plan = fill_plan(context, region, rv3d, mouse, ob)
        if plan is not None:
            STATE["preview"] = ('FILL', plan[1])
        return
    if ctrl and not shift:
        comp = component_at(context, region, rv3d, mouse, ob, edges_only=True)
        if comp is not None:
            segs = multi_cut.loop_segments(bmesh.from_edit_mesh(ob.data), comp[1], comp[2])
            mw = ob.matrix_world
            STATE["preview"] = ('LOOP', [(mw @ a, mw @ b) for a, b in segs])
        return
    comp = component_at(context, region, rv3d, mouse, ob)
    if comp is not None:
        STATE["preview"] = ('DELETE' if ctrl else 'HOVER', _component_points(ob, comp))
        STATE['hover_component'] = (ob.name, *comp[:2])


def _mods(event):
    ctrl = event.ctrl or (event.type in {'LEFT_CTRL', 'RIGHT_CTRL'} and event.value == 'PRESS')
    if event.type in {'LEFT_CTRL', 'RIGHT_CTRL'} and event.value == 'RELEASE':
        ctrl = False
    shift = event.shift or (event.type in {'LEFT_SHIFT', 'RIGHT_SHIFT'} and event.value == 'PRESS')
    if event.type in {'LEFT_SHIFT', 'RIGHT_SHIFT'} and event.value == 'RELEASE':
        shift = False
    return bool(ctrl), bool(shift)


class ALLSET_OT_quad_draw_hover(bpy.types.Operator):
    """Quad Draw hover preview (passes the event on)"""
    bl_idname = "allset.quad_draw_hover"
    bl_label = "Quad Draw Preview"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def invoke(self, context, event):
        if _view_ok(context):
            ctrl, shift = _mods(event)
            try:
                update_hover(context, context.region, context.region_data, _mouse(event), ctrl, shift)
            except (ReferenceError, ValueError, IndexError, KeyError):
                STATE["preview"] = None
            _redraw(context)
        return {'PASS_THROUGH'}


# --- the main modal -------------------------------------------------------------------------------------

def _weld_px(context):
    s = poly_draw.settings(context)
    return float(s.qd_weld_px) if s.qd_auto_weld and not context.scene.allset_soft_select else None



class ALLSET_OT_quad_draw(bpy.types.Operator):
    """Maya Quad Draw: click = dot on the surface, drag = move a dot / vertex / edge / face along the surface,
    Shift+click = fill a polygon, Shift+drag = relax, Ctrl+click = edge loop, Ctrl+Shift+click = delete"""
    bl_idname = "allset.quad_draw"
    bl_label = "Quad Draw"
    bl_options = {'REGISTER', 'UNDO'}

    middle: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'}, description="Middle-drag: only move what is under the mouse")

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        if not _view_ok(context) or event.alt:
            return {'PASS_THROUGH'}
        ob = edit_object(context)
        if ob is None:
            return {'PASS_THROUGH'}
        self._ob = ob.name
        region, rv3d = context.region, context.region_data
        mouse = _mouse(event)
        self._press = mouse
        self._refs = reference_objects(context)
        self._moved = False
        self._grab = None
        # Maya's Keyboard/Mouse Shortcuts
        if event.ctrl and event.shift and self.middle:
            self._mode = 'MOVE'                 # Ctrl+Shift+MMB: drag an edge = tweak its edge loop
            self._grab = self._grab_loop(context, mouse)
            if self._grab is None:
                return {'PASS_THROUGH'}
            self._new_dot = False
        elif event.ctrl and event.shift:
            self._mode = 'DELETE'               # click / drag across faces = delete; an edge = its edge loop
            if self._delete(context, mouse) is None:
                return {'CANCELLED'}
        elif event.ctrl:
            return self._loop(context, mouse, center=self.middle)   # Ctrl+MMB = centred loop
        elif event.shift:
            self._mode = 'SHIFT'                # click = fill (LMB), drag = relax (MMB: the highlighted points)
            self._fill_plan=fill_plan(context,region,rv3d,mouse,ob) if not self.middle else None
        else:
            self._mode = 'MOVE'
            self._grab = self._grab_at(context, mouse)
            if self._grab is None:
                if self.middle:
                    return {'PASS_THROUGH'}
                w = place_point(context, region, rv3d, mouse, self._refs)
                if w is None:
                    self.report({'INFO'}, "Quad Draw: click on the live surface")
                    return {'CANCELLED'}
                bm = bmesh.from_edit_mesh(ob.data)
                v = add_dot(bm, ob.matrix_world.inverted_safe() @ w)
                bmesh.update_edit_mesh(ob.data)
                preselect.invalidate()
                self._depth = w.copy()
                self._grab = ('MESH', [v.index], [w], w)
                self._new_dot = True
            else:
                self._new_dot = False
        # Hover owns a snapshot of the pre-press coordinates. The modal consumes mouse
        # moves, so the hover operator cannot refresh that marker while dragging.
        STATE["preview"] = None
        STATE["snap"] = []
        self._snap = None
        if self._grab is not None and _weld_px(context) is not None:
            from .quad_draw_weld import Magnet
            self._snap = Magnet(context,ob,self._grab[1])
        context.window_manager.modal_handler_add(self)
        _redraw(context)
        return {'RUNNING_MODAL'}

    # -- grabbing
    def _grab_at(self, context, mouse):
        region, rv3d = context.region, context.region_data
        ob = bpy.data.objects[self._ob]
        comp = component_at(context, region, rv3d, mouse, ob)
        if comp is None:
            return None
        bm = bmesh.from_edit_mesh(ob.data)
        if comp[0] == 'VERT':
            bm.verts.ensure_lookup_table()
            verts = [bm.verts[comp[1]]]
        elif comp[0] == 'EDGE':
            bm.edges.ensure_lookup_table()
            verts = list(bm.edges[comp[1]].verts)
        else:
            bm.faces.ensure_lookup_table()
            verts = list(bm.faces[comp[1]].verts)
        mw = ob.matrix_world
        start = surface_hit(context, region, rv3d, mouse, self._refs) if self._refs else None
        if start is None:
            start = sum((mw @ v.co for v in verts), Vector()) / len(verts)
        self._depth = start.copy()
        return ('MESH', [v.index for v in verts], [mw @ v.co for v in verts], start)

    def _drag_to(self, context, mouse):
        STATE["preview"] = None
        STATE["snap"] = []
        region, rv3d = context.region, context.region_data
        _k, idx, starts, start = self._grab
        ob = bpy.data.objects[self._ob]
        bm = bmesh.from_edit_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        inv = ob.matrix_world.inverted_safe()
        if self._refs:
            # Preserve the cursor-to-component offset. No screen-plane fallback when the
            # cursor leaves a live surface: keep the last valid point until it re-enters.
            delta = Vector(mouse) - Vector(self._press)
            anchors = getattr(self, '_surface_anchors', None)
            if anchors is None:
                anchors = starts
                if surface_offset(context):
                    from . import live
                    anchors = []
                    for original in starts:
                        hit = live.nearest(context, original, self._refs)
                        anchors.append(hit[0] if hit is not None else original)
                self._surface_anchors = anchors
            news = []
            for i, original in zip(idx, anchors):
                xy = _screen_xy(region, rv3d, original)
                hit = surface_hit(context, region, rv3d, Vector(xy)+delta, self._refs) if xy else None
                news.append(hit if hit is not None else ob.matrix_world @ bm.verts[i].co)
        else:
            hit = view3d_utils.region_2d_to_location_3d(region, rv3d, mouse, self._depth)
            delta = hit - start
            news = [s + delta for s in starts]
        snap=getattr(self,'_snap',None)
        if snap is not None:
            proposed,pairs=snap.query(context,region,rv3d,dict(zip(idx,news)))
            news=[proposed[i] for i in idx]
            STATE["snap"]=[snap.co[t] for t in pairs.values()]
        for i, w in zip(idx, news):
            bm.verts[i].co = inv @ w
        bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)

    # -- one-shot actions
    def _delete(self, context, mouse, faces_only=False):
        """Ctrl+Shift+LMB: the dot / vertex / face under the mouse; an edge = its edge loop. While dragging only faces
        go. Returns what went or None."""
        region, rv3d = context.region, context.region_data
        ob = bpy.data.objects[self._ob]
        comp = component_at(context, region, rv3d, mouse, ob)
        if comp is None or (faces_only and comp[0] != 'FACE'):
            return None
        bm = bmesh.from_edit_mesh(ob.data)
        if comp[0] == 'EDGE':
            delete_loop(bm, comp[1])
        else:
            delete_at(bm, comp[0], comp[1])
        bmesh.update_edit_mesh(ob.data)
        preselect.invalidate()
        self._deleted = True
        STATE["preview"] = None
        _redraw(context)
        return comp[0]

    def _grab_loop(self, context, mouse):
        region, rv3d = context.region, context.region_data
        ob = bpy.data.objects[self._ob]
        comp = component_at(context, region, rv3d, mouse, ob, edges_only=True)
        if comp is None:
            return None
        bm = bmesh.from_edit_mesh(ob.data)
        bm.edges.ensure_lookup_table()
        verts = list({v for e in edge_loop(bm.edges[comp[1]]) for v in e.verts})
        mw = ob.matrix_world
        start = surface_hit(context, region, rv3d, mouse, self._refs) if self._refs else None
        if start is None:
            start = sum((mw @ v.co for v in verts), Vector()) / len(verts)
        self._depth = start.copy()
        return ('MESH', [v.index for v in verts], [mw @ v.co for v in verts], start)

    def _loop(self, context, mouse, center=False):
        region, rv3d = context.region, context.region_data
        ob = bpy.data.objects[self._ob]
        comp = component_at(context, region, rv3d, mouse, ob, edges_only=True)
        if comp is None:
            return {'CANCELLED'}
        bm = bmesh.from_edit_mesh(ob.data)
        before = set(bm.verts)
        bm.edges.ensure_lookup_table()
        t = 0.5 if center else min(max(comp[2], 0.001), 0.999)
        mesh_tools.insert_loop(bm, bm.edges[comp[1]], t)
        if self._refs:
            mw, inv = ob.matrix_world, ob.matrix_world.inverted_safe()
            for v in bm.verts:
                if v not in before:
                    v.co = inv @ project_point(context, mw @ v.co, self._refs, region, rv3d)
        _indices(bm)
        bmesh.update_edit_mesh(ob.data)
        preselect.invalidate()
        STATE["preview"] = None
        _redraw(context)
        return {'FINISHED'}

    def _relax_at(self, context, mouse):
        region, rv3d = context.region, context.region_data
        ob = bpy.data.objects[self._ob]
        bm = bmesh.from_edit_mesh(ob.data)
        mw, inv = ob.matrix_world, ob.matrix_world.inverted_safe()
        r = BRUSH_PX * _ui_scale(context)
        verts = []
        if self.middle:      # Shift+MMB: only the highlighted component's points
            comp = component_at(context, region, rv3d, mouse, ob)
            if comp is not None:
                for kind, seq in (('VERT', bm.verts), ('EDGE', bm.edges), ('FACE', bm.faces)):
                    if comp[0] == kind:
                        seq.ensure_lookup_table()
                        el = seq[comp[1]]
                        verts = [el] if kind == 'VERT' else list(el.verts)
        else:
            for v in bm.verts:
                xy = _screen_xy(region, rv3d, mw @ v.co)
                if xy is not None and math.hypot(xy[0] - mouse[0], xy[1] - mouse[1]) <= r:
                    verts.append(v)
        refs = self._refs

        def project(co):
            return inv @ project_point(context, mw @ co, refs, region, rv3d) if refs else co
        mode = poly_draw.settings(context).qd_relax
        if mode == 'AUTO_LOCK':
            if verts and not hasattr(self, '_relax_lock'):
                seed = min(verts, key=lambda v: (Vector(_screen_xy(region, rv3d, mw @ v.co))-Vector(mouse)).length_squared)
                self._relax_lock = 'BORDER' if seed.is_boundary else 'INTERIOR'
            mode = getattr(self, '_relax_lock', 'AUTO_LOCK')
        relax(bm, verts, mode, project=project)
        bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
        STATE["preview"] = ('BRUSH', (mouse[0], mouse[1], r))

    # -- modal
    def modal(self, context, event):
        if not tool_active(context) or not _view_ok(context) or bpy.data.objects.get(self._ob) is None:
            STATE["preview"] = None
            STATE["snap"] = []
            self._snap = None
            return {'CANCELLED'}
        mouse = _mouse(event)
        button = 'MIDDLEMOUSE' if self.middle else 'LEFTMOUSE'
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            if not self._moved and math.hypot(mouse[0] - self._press[0], mouse[1] - self._press[1]) >= DRAG_PX:
                self._moved = True
            if self._mode == 'DELETE':
                self._delete(context, mouse, faces_only=True)     # drag across faces
            elif self._moved:
                if self._mode == 'SHIFT':
                    self._relax_at(context, mouse)
                else:
                    self._drag_to(context, mouse)
                _redraw(context)
            return {'RUNNING_MODAL'}
        if event.type == button and event.value == 'RELEASE':
            return self._release(context, mouse)
        if event.type == 'ESC' and event.value == 'PRESS':
            return self._cancel(context)
        return {'RUNNING_MODAL'}

    def _release(self, context, mouse):
        region, rv3d = context.region, context.region_data
        ob = bpy.data.objects[self._ob]
        STATE["preview"] = None
        if self._mode == 'DELETE':
            return {'FINISHED'}
        if self._mode == 'SHIFT':
            if self._moved or self.middle:
                if not self._moved:
                    return {'CANCELLED'}
                preselect.invalidate()
                _redraw(context)
                return {'FINISHED'}
            plan = self._fill_plan
            if plan is None or apply_fill(ob, plan[0]) is None:
                self.report({'INFO'}, "Quad Draw: Shift+click between 3 or 4 dots / border vertices to fill")
                _redraw(context)
                return {'CANCELLED'}
            _redraw(context)
            return {'FINISHED'}
        if not self._moved and not self._new_dot:
            return {'CANCELLED'}
        if self._moved:
            self._drag_to(context,mouse)
        bm = bmesh.from_edit_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        if self._snap is not None:
            self._snap.commit(bm,{i:bm.verts[i] for i in self._grab[1]})
            self._snap = None
            _indices(bm)
        STATE["snap"] = []
        self._surface_anchors = None
        bmesh.update_edit_mesh(ob.data)
        preselect.invalidate()
        _redraw(context)
        return {'FINISHED'}

    def _cancel(self, context):
        STATE["snap"] = []
        self._snap = None
        self._surface_anchors = None
        ob = bpy.data.objects.get(self._ob)
        if self._grab is not None and ob is not None:
            bm = bmesh.from_edit_mesh(ob.data)
            bm.verts.ensure_lookup_table()
            if getattr(self, "_new_dot", False):
                bm.verts.remove(bm.verts[self._grab[1][0]])
                _indices(bm)
            else:
                inv = ob.matrix_world.inverted_safe()
                for i, w in zip(self._grab[1], self._grab[2]):
                    bm.verts[i].co = inv @ w
            bmesh.update_edit_mesh(ob.data)
        STATE["preview"] = None
        _redraw(context)
        return {'CANCELLED'}


# --- Tab: extend / quad strip ---------------------------------------------------------------------------

class ALLSET_OT_quad_draw_tab(bpy.types.Operator):
    """Quad Draw Tab: while Tab is held, drag from a border edge to extend it, or in empty space to draw a strip of
    quads"""
    bl_idname = "allset.quad_draw_tab"
    bl_label = "Quad Draw Extend"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return tool_active(context)

    def invoke(self, context, event):
        if not _view_ok(context) or edit_object(context) is None:
            return {'PASS_THROUGH'}
        self._ob = edit_object(context).name
        self._drag = None
        self._snap = None
        self._new_ids = {}
        self._done = False
        self._refs = reference_objects(context)
        update_hover(context, context.region, context.region_data, _mouse(event), False, False, tab=True)
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set("Quad Draw: hold Tab and drag a border edge to extend it, a corner "
                                          "vertex to fill the corner, or drag in empty space for a strip of quads")
        _redraw(context)
        return {'RUNNING_MODAL'}

    def _end(self, context, result):
        STATE["preview"] = None
        STATE["snap"] = []
        self._snap = None
        context.workspace.status_text_set(None)
        _redraw(context)
        return result

    def modal(self, context, event):
        if not tool_active(context) or not _view_ok(context) or bpy.data.objects.get(self._ob) is None:
            return self._end(context, {'CANCELLED'})
        region, rv3d = context.region, context.region_data
        mouse = _mouse(event)
        if event.type == 'TAB':
            if event.value == 'RELEASE':
                if self._drag is not None:
                    self._commit(context, mouse)
                return self._end(context, {'FINISHED'} if self._done else {'CANCELLED'})
            return {'RUNNING_MODAL'}      # key repeat
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            if self._drag is None:
                update_hover(context, region, rv3d, mouse, False, False, tab=True)
            else:
                self._update_drag(context, mouse)
            _redraw(context)
            return {'RUNNING_MODAL'}
        if event.type in {'LEFTMOUSE', 'MIDDLEMOUSE'} and event.value == 'PRESS' and self._drag is None:
            ob = bpy.data.objects[self._ob]
            mode = poly_draw.settings(context).qd_extend
            vi = corner_vertex_at(context, region, rv3d, mouse, ob) if event.type == 'LEFTMOUSE' and mode == 'EDGE' else None
            if vi is not None:
                # a border vertex: the quad of it, its two border neighbours and the mouse point (#180)
                self._button = event.type
                self._drag = ('CORNER', vi)
                bm=bmesh.from_edit_mesh(ob.data)
                bm.verts.ensure_lookup_table()
                a,b=corner_neighbours(bm.verts[vi])
                self._new_ids={None:len(bm.verts)}
                self._start_snap(context,[ob.matrix_world@bm.verts[vi].co],[(a.index,vi,b.index,len(bm.verts))])
                return {'RUNNING_MODAL'}
            ei = poly_draw.border_edge_at(context, region, rv3d, mouse, ob)
            if ei is None and event.type == 'MIDDLEMOUSE':
                return {'RUNNING_MODAL'}        # Maya Tab+MMB in empty space resizes strips: not in the kit
            self._button = event.type
            if ei is not None:
                bm = bmesh.from_edit_mesh(ob.data)
                bm.edges.ensure_lookup_table()
                edge = bm.edges[ei]
                mode = 'LOOP' if event.type == 'MIDDLEMOUSE' else mode
                loop = border_loop(edge) if mode == 'BORDER' else border_chain(edge) if mode == 'LOOP' else [edge]
                start = surface_hit(context, region, rv3d, mouse, self._refs) if self._refs else None
                if start is None:
                    mw = ob.matrix_world
                    start = mw @ ((edge.verts[0].co + edge.verts[1].co) / 2)
                self._drag = ('EXTEND', [e.index for e in loop], start)
                ids=sorted({v.index for e in loop for v in e.verts})
                self._new_ids={i:len(bm.verts)+k for k,i in enumerate(ids)}
                faces=[]
                for e in loop:
                    b,a=poly_draw.edge_start(e)
                    faces.append((b.index,a.index,self._new_ids[a.index],self._new_ids[b.index]))
                bm.verts.ensure_lookup_table()
                self._start_snap(context,[ob.matrix_world@bm.verts[i].co for i in ids],faces)
            else:
                self._drag = ('STRIP', [mouse])
            return {'RUNNING_MODAL'}
        if event.type == getattr(self, "_button", 'LEFTMOUSE') and event.value == 'RELEASE' \
                and self._drag is not None:
            self._commit(context, mouse)
            self._drag = None
            self._snap = None
            STATE["snap"] = []
            return {'RUNNING_MODAL'}
        if event.type == 'ESC' and event.value == 'PRESS':
            return self._end(context, {'FINISHED'} if self._done else {'CANCELLED'})
        return {'RUNNING_MODAL'} if self._drag is not None else {'PASS_THROUGH'}

    def _start_snap(self,context,extra,faces):
        self._snap=None
        if _weld_px(context) is not None:
            from .quad_draw_weld import Magnet
            ob=bpy.data.objects[self._ob]
            self._snap=Magnet(context,ob,self._new_ids.values(),extra,faces)

    def _snap_points(self,context,points):
        STATE["snap"]=[]
        snap=getattr(self,'_snap',None)
        if snap is None:
            return points
        proposed={self._new_ids[i]:p for i,p in points.items()}
        proposed,pairs=snap.query(context,context.region,context.region_data,proposed)
        STATE["snap"]=[snap.co[t] for t in pairs.values()]
        return {i:proposed[self._new_ids[i]] for i in points}

    def _extend_positions(self,context,mouse):
        ob=bpy.data.objects[self._ob]
        bm=bmesh.from_edit_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        offset=self._offset_fn(context,mouse)
        return self._snap_points(context,{i:ob.matrix_world@offset(bm.verts[i].co) for i in self._new_ids})

    def _offset_fn(self, context, mouse):
        region, rv3d = context.region, context.region_data
        ob = bpy.data.objects[self._ob]
        mw, inv = ob.matrix_world, ob.matrix_world.inverted_safe()
        start = self._drag[2]
        hit = surface_hit(context, region, rv3d, mouse, self._refs) if self._refs else None
        if hit is None:
            hit = view3d_utils.region_2d_to_location_3d(region, rv3d, mouse, start)
        delta = hit - start
        refs = self._refs

        def offset(co):
            w = mw @ co + delta
            return inv @ (project_point(context, w, refs, region, rv3d) if refs else w)
        return offset

    def _corner_point(self, context, mouse):
        """World point under the mouse for a corner quad: on the reference surface, else in the view plane through
        the vertex."""
        region, rv3d = context.region, context.region_data
        ob = bpy.data.objects[self._ob]
        bm = bmesh.from_edit_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        at = ob.matrix_world @ bm.verts[self._drag[1]].co
        hit = place_point(context, region, rv3d, mouse, self._refs) if self._refs else None
        point=hit if hit is not None else view3d_utils.region_2d_to_location_3d(region, rv3d, mouse, at)
        return self._snap_points(context,{None:point})[None]

    def _update_drag(self, context, mouse):
        if self._drag[0] == 'CORNER':
            ob = bpy.data.objects[self._ob]
            p = self._corner_point(context, mouse)
            STATE["preview"] = ('EXTEND', [q for a, b in _corner_points(ob, self._drag[1]) for q in (b, p)])
            return
        if self._drag[0] == 'STRIP':
            self._drag[1].append(mouse)
            pairs = strip_pairs(self._drag[1], poly_draw.settings(context).qd_strip_width * _ui_scale(context))
            region, rv3d = context.region, context.region_data
            pts = []
            for left, right in pairs:
                a = view3d_utils.region_2d_to_location_3d(region, rv3d, left, self._depth(context))
                b = view3d_utils.region_2d_to_location_3d(region, rv3d, right, self._depth(context))
                pts += [a, b]
            STATE["preview"] = ('EXTEND', pts)
            return
        positions = self._extend_positions(context, mouse)
        ob = bpy.data.objects[self._ob]
        bm = bmesh.from_edit_mesh(ob.data)
        bm.edges.ensure_lookup_table()
        mw = ob.matrix_world
        segs = []
        for i in self._drag[1]:
            if i < len(bm.edges):
                b, a = poly_draw.edge_start(bm.edges[i])
                pa, pb = positions[a.index], positions[b.index]
                segs += [mw @ a.co, pa, pa, pb, pb, mw @ b.co]
        STATE["preview"] = ('EXTEND', segs)

    def _depth(self, context):
        hit = surface_hit(context, context.region, context.region_data, self._drag[1][0], self._refs) \
            if self._refs else None
        return hit if hit is not None else context.scene.cursor.location

    def _commit(self, context, mouse):
        region, rv3d = context.region, context.region_data
        ob = bpy.data.objects[self._ob]
        bm = bmesh.from_edit_mesh(ob.data)
        inv = ob.matrix_world.inverted_safe()
        if self._drag[0] == 'CORNER':
            bm.verts.ensure_lookup_table()
            before = set(bm.verts)
            face = corner_quad(bm, bm.verts[self._drag[1]], inv @ self._corner_point(context, mouse))
            faces = [face] if face is not None else []
            if faces and self._snap is not None:
                new=next(v for v in face.verts if v not in before)
                self._snap.commit(bm,{self._new_ids[None]:new})
                _indices(bm)
        elif self._drag[0] == 'EXTEND':
            bm.edges.ensure_lookup_table()
            edges = [bm.edges[i] for i in self._drag[1] if i < len(bm.edges)]
            positions=self._extend_positions(context,mouse)
            created={}
            faces = extend_edges(bm,edges,None,{i:inv@p for i,p in positions.items()},created)
            if faces and self._snap is not None:
                self._snap.commit(bm,{self._new_ids[i]:v for i,v in created.items()})
                _indices(bm)
        else:
            path = self._drag[1] + [mouse]
            pairs = strip_pairs(path, poly_draw.settings(context).qd_strip_width * _ui_scale(context))
            local = []
            for left, right in pairs:
                a = place_point(context, region, rv3d, left, self._refs)
                b = place_point(context, region, rv3d, right, self._refs)
                if a is None or b is None:
                    break
                local.append((inv @ a, inv @ b))
            faces = strip_faces(bm, local) if len(local) >= 2 else []
        bmesh.update_edit_mesh(ob.data)
        preselect.invalidate()
        self._done = self._done or bool(faces)


class ALLSET_OT_quad_draw_clear_dots(bpy.types.Operator):
    """Remove every Quad Draw dot (Maya Tool Settings: Clear Dots)"""
    bl_idname = "allset.quad_draw_clear_dots"
    bl_label = "Clear Dots"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return edit_object(context) is not None

    def execute(self, context):
        ob = edit_object(context)
        bm = bmesh.from_edit_mesh(ob.data)
        if not clear_dots(bm):
            return {'CANCELLED'}
        bmesh.update_edit_mesh(ob.data)
        preselect.invalidate()
        STATE["preview"] = None
        for area in context.screen.areas if context.screen else ():
            area.tag_redraw()
        return {'FINISHED'}


class ALLSET_OT_quad_draw_exit(bpy.types.Operator):
    """Leave Quad Draw for the Select tool (Maya Esc / Q)"""
    bl_idname = "allset.quad_draw_exit"
    bl_label = "Exit Quad Draw"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return tool_active(context)

    def execute(self, context):
        STATE["preview"] = None
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box", space_type='VIEW_3D')
        return {'FINISHED'}


# --- start: the mesh to edit, the view, the watcher -----------------------------------------------------

def _retopology_on(context):
    """Show the edited mesh over the surface (Blender's Retopology overlay) in this window's 3D views; the previous
    value comes back when the tool is left (``_watch``)."""
    from .. import live_refs
    screen = context.window.screen if context.window else None
    for area in screen.areas if screen else ():
        if area.type != 'VIEW_3D':
            continue
        space = area.spaces.active
        ov = space.overlay
        if not hasattr(ov, "show_retopology"):
            return
        ptr = live_refs.pointer(space)
        if ptr not in STATE["overlays"]:
            STATE["overlays"][ptr] = ov.show_retopology, ov.show_faces, ov.retopology_offset
        ov.show_retopology = True
    sync_overlays()


def sync_overlays(context=None):
    """Keep the native cage depth behind the custom display; restore on exit."""
    from .. import live_refs
    if context is not None and context.space_data.as_pointer() not in STATE['overlays']:
        # A .blend may reopen with Quad Draw already active, bypassing Start.
        # Capture that viewport before changing it, and arm normal exit cleanup.
        _retopology_on(context)
        ob = edit_object(context)
        name = ob.name if ob else None
        if STATE['ob'] != name:
            STATE['created'] = None
        STATE.update(ob=name, timer=True)
        if not bpy.app.timers.is_registered(_watch):
            bpy.app.timers.register(_watch, first_interval=0.5)
        return
    for ptr, (_shown, faces, offset) in STATE["overlays"].items():
        _w, _a, space = live_refs.find_space(ptr)
        if space is not None:
            ov = space.overlay
            wanted = faces and not poly_draw.settings().qd_mesh_color_on
            if ov.show_faces != wanted:
                ov.show_faces = wanted
            # Even 0.01 is large on centimetre-scale meshes. An unshifted native
            # prepass avoids competing with the custom display at every scale.
            # The compositor retains the saved offset; exit restores it below.
            if ov.retopology_offset != 0.0:
                ov.retopology_offset = 0.0


def _restore_overlays():
    from .. import live_refs
    for ptr, (shown, faces, offset) in list(STATE["overlays"].items()):
        _w, _a, space = live_refs.find_space(ptr)
        if space is not None:
            space.overlay.show_retopology = shown
            space.overlay.show_faces = faces
            space.overlay.retopology_offset = offset
    STATE["overlays"].clear()
    global _pick_projection, _fill_projection
    _pick_projection = None
    _fill_projection = None
    STATE["snap"] = []
    from . import quad_draw_overlay
    quad_draw_overlay.clear()


def _active_anywhere():
    wm = bpy.context.window_manager
    for win in wm.windows if wm else ():
        try:
            tool = win.workspace.tools.from_space_view3d_mode('EDIT_MESH', create=False)
        except (AttributeError, TypeError, RuntimeError):
            continue
        if tool is not None and tool.idname == TOOL and bpy.context.mode == 'EDIT_MESH':
            return True
    return False


def _watch():
    """While Quad Draw is the tool, nothing; once left: overlays back, an untouched new mesh removed, dots gone."""
    try:
        if _active_anywhere():
            return 0.5
    except (ReferenceError, AttributeError):
        pass
    _restore_overlays()
    STATE["preview"] = None
    _drop_dots(STATE["ob"])
    name = STATE["created"]
    STATE["created"] = None
    ob = bpy.data.objects.get(name) if name else None
    if ob is not None and ob.mode != 'EDIT' and ob.type == 'MESH' and not ob.data.vertices:
        me = ob.data
        bpy.data.objects.remove(ob)
        if me.users == 0:
            bpy.data.meshes.remove(me)
    STATE["timer"] = False
    return None


def _drop_dots(name):
    """Leaving Quad Draw clears its dots and the dot layer (Maya's dots live only in the tool) [K]."""
    ob = bpy.data.objects.get(name) if name else None
    if ob is None or ob.type != 'MESH':
        return
    me = ob.data
    if ob.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(me)
        clear_dots(bm)
        lay = dot_layer(bm)
        if lay is not None:
            bm.verts.layers.int.remove(lay)
        bmesh.update_edit_mesh(me)
        return
    if DOT_LAYER not in me.attributes:
        return
    bm = bmesh.new()
    bm.from_mesh(me)
    if clear_dots(bm):
        bm.to_mesh(me)
    bm.free()
    attr = me.attributes.get(DOT_LAYER)
    if attr is not None:
        me.attributes.remove(attr)


def new_target(context):
    """A new empty mesh ``polySurfaceN`` at the origin, selected and in edit mode (Quad Draw with nothing to edit)."""
    from . import mesh_maya
    if context.view_layer.objects.active is not None and context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    me = bpy.data.meshes.new(poly_draw.BASE_NAME)
    ob = bpy.data.objects.new(poly_draw.BASE_NAME, me)
    context.view_layer.active_layer_collection.collection.objects.link(ob)
    mesh_maya._maya_rename(ob, poly_draw.BASE_NAME)
    for other in context.selected_objects:
        other.select_set(False)
    ob.select_set(True)
    context.view_layer.objects.active = ob
    return ob


def pick_target(context):
    """The mesh Quad Draw edits: the edited / selected mesh unless it is the live surface; else None (make one)."""
    from . import live
    ob = context.active_object
    if ob is not None and ob.type == 'MESH' and not live.contains(context.scene, ob) and (ob.mode == 'EDIT' or ob.select_get()):
        return ob
    return None


class ALLSET_OT_quad_draw_start(bpy.types.Operator):
    """Maya Mesh Tools > Quad Draw: draw a new mesh on the live surface (or edit the selected mesh)"""
    bl_idname = "allset.quad_draw_start"
    bl_label = "Quad Draw Tool"
    bl_options = {'REGISTER', 'UNDO'}

    option_box: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        from . import material
        ob = pick_target(context)
        from . import maya_errors
        if maya_errors.refuse_hidden(self, ob):        # Blender can't edit a hidden mesh (#187)
            return {'CANCELLED'}
        if ob is None:
            ob = new_target(context)
            material.give_default(ob)
            STATE["created"] = ob.name
        if context.mode != 'EDIT_MESH' or context.edit_object is not ob:
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            from . import live
            for other in context.selected_objects:
                if other is not ob:
                    other.select_set(False)
            for reference in live.objects(context.scene):
                reference.select_set(False)
            ob.select_set(True)
            context.view_layer.objects.active = ob
            bpy.ops.object.mode_set(mode='EDIT')
        STATE["ob"] = ob.name
        try:
            bpy.ops.wm.tool_set_by_id(name=TOOL, space_type='VIEW_3D')
        except RuntimeError as ex:
            self.report({'ERROR'}, str(ex).strip())
            return {'CANCELLED'}
        if context.window is not None:
            _retopology_on(context)
            if not bpy.app.background:
                from ..ui import maya_dock
                maya_dock.show(context, 'MODELING_TOOLKIT')
        if not STATE["timer"]:
            STATE["timer"] = True
            bpy.app.timers.register(_watch, first_interval=0.5)
        if self.option_box:
            poly_draw._open_tool_settings()
        return {'FINISHED'}


classes = (ALLSET_OT_quad_draw_hover, ALLSET_OT_quad_draw, ALLSET_OT_quad_draw_tab, ALLSET_OT_quad_draw_clear_dots,
           ALLSET_OT_quad_draw_exit, ALLSET_OT_quad_draw_start)


def register_handlers():
    if not _handles:
        _handles.append(bpy.types.SpaceView3D.draw_handler_add(_draw_view, (), 'WINDOW', 'POST_VIEW'))
        _handles.append(bpy.types.SpaceView3D.draw_handler_add(_draw_pixel, (), 'WINDOW', 'POST_PIXEL'))


def unregister_handlers():
    while _handles:
        bpy.types.SpaceView3D.draw_handler_remove(_handles.pop(), 'WINDOW')
    if bpy.app.timers.is_registered(_watch):
        bpy.app.timers.unregister(_watch)
    STATE.update(ob=None, preview=None, created=None, timer=False)
    _restore_overlays()
