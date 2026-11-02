# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya polyBevel3 (Edit Mesh > Bevel, Ctrl+B) at once, as an editable history node like the kit's extrusion
(#16).

- Defaults: Fraction 0.5, Offset As Fraction on, Offset 0.2, Segments 1, Depth 1 (Chamfer on, Mitering auto).
- Fraction is relative to one length for the whole selection: the shortest "slide" edge (an edge touching an end of a
  beveled edge), halved when both of its ends are used (two shells of different size get the same width). The width
  applied is 0.9999 x that (both modes).
- The profile: the circle touching both faces at the profile's ends, in equal angle steps; Depth moves each point
  toward the chord between the ends (1 = the arc, 0 = on the chord, -1 = mirrored), also on concave edges
  (``arc_points``). Blender's superellipse (``profile = t^2``, t = 0.5 + Depth x (sqrt(1/2) - 1/2)) stays where
  the profile runs at a slant to its edge, where two bevelled edges meet, and for Segments 1.
- Three or more bevelled edges at a corner: one polygon through the profiles' ends (``flat_corners``).
- Zero-length slide edges don't count, and what the bevel makes is merged within 0.0001 (Merge Vertices): the
  cap of a zero-length extrusion bevels into an inset (12/20/10, cap at 0.25), Fraction 1 merges (6/9/5).
- Faces bevel their edges; Maya leaves nothing selected afterwards. Vertex mode = Chamfer Vertex (Maya's Bevel
  on vertices chamfers them: 0.25 of each edge, no editable node here).
- Numbering (#149): kept vertices first in their old
  order, then the new vertices of each bevelled vertex, the bevelled vertices taken in the order the selected edges
  reach them (ascending Maya edge id, ends by ascending vertex id) and each one's new vertices in Maya's vertex ->
  edge order (``vertex_edges``; at a vertex that ends one bevelled edge, one new vertex on each of its other edges).
  Faces: old faces at no vertex that ends two or more bevelled edges, the bevel faces, old faces at such a vertex,
  corner and chain-end faces; in each group of old faces, a face whose vertex list starts at a chain end (and that
  doesn't hold that end's bevelled edge) comes last. Maya's edge ids = the mesh's edge index (``maya_edge_ids``)
  unless the caller passes them. A new vertex that Merge Vertices joins to an old one keeps the old one's number.
  Not renumbered: Segments > 1.
- Border edges (one face) are left out, like Maya.
"""

import math

import bmesh

from . import extrude

MERGE = 1e-4          # polyBevel3 Merge Vertices on, tolerance 0.0001 (default)
ZERO = 1e-6           # zero-length slide edges (a zero-length extrusion) don't limit the fraction
FIT = 0.9999          # bevel width = 0.9999 x the asked width (offset 0.1 -> 0.09999, fraction 0.5 -> 0.49995)
CHAMFER = 25.0        # Chamfer Vertex: 0.25 of each edge (unit cube and 4 x 1 x 2 box)
NEAR_LINE = 0.9       # |cos| of a slide edge's angle to the bevelled edge above this: it runs near that line
CORNER_SPLIT = 10.93  # degrees: two-edge corners whose dihedral angles differ less than this use ``corner_pairs``
TRIPLE_SPLIT = 1.0 / 1.1  # three-edge corners whose smallest / largest sin(dihedral / 2) is at least this use
                          # ``corner_triples``


def _slides(e, v):
    """The edges at ``v`` that lie in one of e's faces."""
    return [s for f in e.link_faces for s in v.link_edges if s is not e and f in s.link_faces]


def _half_sin(e, v):
    """sin(alpha / 2) of edge ``e`` at its vertex ``v``: alpha = the angle between its two slide edges at v seen along
    e (the dihedral angle of e's faces there). None when that is not defined."""
    d = e.other_vert(v).co - v.co
    if d.length <= ZERO or len(e.link_faces) != 2:
        return None
    d.normalize()
    slides = _slides(e, v)
    if len(slides) < 2:
        return None
    across = []
    for s in slides[:2]:
        x = s.other_vert(v).co - v.co
        x = x - d * x.dot(d)
        if x.length <= ZERO:
            return None
        across.append(x.normalized())
    half = math.acos(max(-1.0, min(1.0, across[0].dot(across[1])))) / 2.0
    return math.sin(half) if math.sin(half) > ZERO else None


def edge_half_sin(e, sel, corners=None):
    """One sin(alpha / 2) for a whole bevelled edge, like Maya: taken at its end where two or more bevelled edges
    meet (the smallest of theirs there; at a ``corner_pairs`` corner its ``hm``), else at its first vertex (the
    lower index)."""
    ends = sorted(e.verts, key=lambda x: (sum(1 for y in x.link_edges if y in sel) < 2, x.index))
    v = ends[0]
    if corners and v in corners and e in (corners[v]["P"], corners[v]["Q"]):
        return corners[v]["hm"]
    mine = [x for x in v.link_edges if x in sel]
    vals = [h for h in (_half_sin(x, v) for x in (mine if len(mine) >= 2 else [e])) if h is not None]
    return min(vals) if vals else None


def end_scale(e, v, sel, corners=None):
    """At a chain end ``v`` of bevelled edge ``e``: the edge's sin(alpha / 2) over v's own (1 where both agree: planar
    faces, no corner at the first vertex). Every new vertex at v moves out from v by this factor."""
    here, edge = _half_sin(e, v), edge_half_sin(e, sel, corners)
    if here is None or edge is None:
        return 1.0
    return edge / here


def terminal_moves(edges, corners=None):
    """#182: the ends of an open chain (or a lone edge) between two faces. At a vertex v that ends exactly
    one bevelled edge e, every other edge t at v that lies in no face of e gets its new vertex at
    d = W x sin(alpha / 2) / s_phi from v (alpha = the angle between e's two slide edges seen along e = the dihedral
    angle of e's faces, phi = the angle between t and e, s_phi = sin phi below 90 degrees, else 1): Maya keeps that
    point at W x sin(alpha / 2) from the bevelled edge. alpha is the edge's one angle (``edge_half_sin``); where it
    differs from v's own, the new vertices on the slide edges move out by the same factor (``end_scale``) — unless
    ``end_moves`` places them. Returns ([(v position, unit(t), k = d / W)], {t: [lengths / k]}, {vertices whose slide
    vertices moved}) — the second is what limits the width (``slide_limit``)."""
    sel = set(edges)
    moves, limits, scaled = [], {}, {}
    near = end_moves(edges, corners)[2]
    for v in {v for e in edges for v in e.verts}:
        mine = [e for e in v.link_edges if e in sel]
        if len(mine) != 1 or len(mine[0].link_faces) != 2:
            continue
        e = mine[0]
        d = (e.other_vert(v).co - v.co)
        if d.length <= ZERO:
            continue
        d.normalize()
        slides = _slides(e, v)
        here = _half_sin(e, v)
        if here is None:
            continue
        sin_half = edge_half_sin(e, sel, corners) or here
        scale = sin_half / here
        # an edge of a ``corner_pairs`` corner: Blender's offset at its far end drifts with the corner, Maya's doesn't
        paired = bool(corners) and any(e in (c["P"], c["Q"]) for c in corners.values())
        if (abs(scale - 1.0) > 1e-9 or paired) and v not in near:
            scaled[v] = scale
            for s in slides:
                off = s.other_vert(v).co - v.co
                u = off.normalized()
                sin_s = u.cross(d).length
                if sin_s > ZERO:
                    moves.append((v.co.copy(), u, scale / sin_s))
        for t in v.link_edges:
            if t is e or t in slides:
                continue
            off = t.other_vert(v).co - v.co
            if off.length <= ZERO:
                continue
            u = off.normalized()
            c = u.dot(d)
            s_phi = math.sqrt(max(0.0, 1.0 - c * c)) if c > 0.0 else 1.0
            if s_phi <= ZERO:
                continue
            k = sin_half / s_phi
            moves.append((v.co.copy(), u, k))
            limits.setdefault(t, []).append(off.length / k)
    return moves, limits, scaled


def end_moves(edges, corners=None):
    """Ends of an open chain (or a lone edge) between two faces where a slide edge runs near the bevelled edge's line
    (|cos| of their angle above 0.9: an n-gon cap's rim neighbour, a cone's rim). Each of the two slide edges s gets a
    direction S: the unit vector along s when s runs near the line, else that vector over sin(its angle to e) (the
    point a plain bevel uses, one width from e). Both new vertices go to v + W x c x S with one c for the vertex: the
    chord between the two faces' unit offsets over the distance between the two S seen along e, so the new edge
    across the end is as long as a plain bevel's there. Returns ([(v position, unit(s), k = distance along s / W,
    s's other vertex)], {s: [lengths / k]}, {vertex handled: (k, unit vector of its slide edge near the line)})."""
    sel = set(edges)
    moves, limits, done = [], {}, {}
    for v in {v for e in edges for v in e.verts}:
        mine = [e for e in v.link_edges if e in sel]
        if len(mine) != 1 or len(mine[0].link_faces) != 2:
            continue
        e = mine[0]
        d = e.other_vert(v).co - v.co
        if d.length <= ZERO:
            continue
        d.normalize()
        slides = [s for f in e.link_faces for s in v.link_edges if s is not e and f in s.link_faces]
        if len(slides) != 2 or slides[0] is slides[1]:
            continue
        units = [s.other_vert(v).co - v.co for s in slides]
        if any(u.length <= ZERO for u in units):
            continue
        units = [u.normalized() for u in units]
        across = [u - d * u.dot(d) for u in units]
        sins = [a.length for a in across]
        lines = [abs(u.dot(d)) > NEAR_LINE for u in units]
        if min(sins) <= ZERO or not any(lines):
            continue
        dirs = [u if line else u / sin for u, sin, line in zip(units, sins, lines)]
        gap = ((dirs[0] - d * dirs[0].dot(d)) - (dirs[1] - d * dirs[1].dot(d))).length
        chord = (across[0] / sins[0] - across[1] / sins[1]).length * end_scale(e, v, sel, corners)
        if gap <= ZERO or chord <= ZERO:
            continue
        near = [u for u, line in zip(units, lines) if line]
        done[v] = (chord / gap, near[0] if len(near) == 1 else None)
        for s, u, x in zip(slides, units, dirs):
            k = chord / gap * x.length
            moves.append((v.co.copy(), u, k, s.other_vert(v)))
            limits.setdefault(s, []).append(s.calc_length() / k)
    return moves, limits, done


def corner_pairs(edges, ids):
    """Corners like a box corner: vertex v has three edges, two of them bevelled (sharing face F) and one not (u3),
    and the dihedral angles of the two bevelled edges differ by less than ``CORNER_SPLIT``. P = the first bevelled
    edge in Maya's vertex -> edge order at v, Q the other; h = sin(dihedral / 2), s = sin(angle to u3);
    k_P = min(1, sqrt(s_P / s_Q)), k_Q = min(1, sqrt(s_Q / s_P)), hm = the smallest of h_P k_P, h_Q at Q's far end
    and the value that puts the new vertex on u3 exactly W below F. Like Maya:
    - each edge's width at its far end = W hm / h (``edge_half_sin`` gives hm);
    - the new corner in F lies on the bisector, W hm / (h_P k_P) from both edge lines;
    - the new vertex on u3 = the mean of where the two side faces' offset lines (W hm k / h from the edge) cross u3.
    Returns {v: {...}}; ids = {BMEdge: Maya edge id}."""
    sel = set(edges)
    out = {}
    if ids is None:
        return out
    for v in {v for e in edges for v in e.verts}:
        if len(v.link_edges) != 3 or any(len(e.link_faces) != 2 for e in v.link_edges):
            continue
        mine = [e for e in v.link_edges if e in sel]
        if len(mine) != 2:
            continue
        faces = set(mine[0].link_faces).intersection(mine[1].link_faces)
        order = vertex_edges(v, ids)
        if len(faces) != 1 or order is None:
            continue
        p, q = [e for e in order if e in sel]
        rest = [e for e in v.link_edges if e not in sel][0]
        units = [e.other_vert(v).co - v.co for e in (p, q, rest)]
        if any(u.length <= ZERO for u in units):
            continue
        up, uq, u3 = [u.normalized() for u in units]
        hp, hq = _half_sin(p, v), _half_sin(q, v)
        sp, sq = up.cross(u3).length, uq.cross(u3).length
        if hp is None or hq is None or sp <= ZERO or sq <= ZERO:
            continue
        if abs(math.degrees(2.0 * (math.asin(min(1.0, hp)) - math.asin(min(1.0, hq))))) >= CORNER_SPLIT:
            continue
        kp, kq = min(1.0, math.sqrt(sp / sq)), min(1.0, math.sqrt(sq / sp))
        half = math.acos(max(-1.0, min(1.0, up.dot(uq)))) / 2.0
        ray = up + uq
        normal = up.cross(uq)
        if ray.length <= ZERO or math.sin(half) <= ZERO or normal.length <= ZERO:
            continue
        # Q's angle at its far end (differs from v's when Q's side face is bent), and the new vertex on u3 never
        # goes deeper than W below F
        hq_far = _half_sin(q, q.other_vert(v)) or hq
        depth = (kp / (hp * sp) + kq / (hq * sq)) / 2.0 * abs(u3.dot(normal.normalized()))
        hm = min(hp * kp, hq_far, 1.0 / depth if depth > ZERO else hq_far)
        out[v] = {"P": p, "Q": q, "rest": rest, "hm": hm, "origin": v.co.copy(), "ray": ray.normalized(),
                  "k_ray": hm / (hp * kp) / math.sin(half), "u3": u3,
                  "k_u3": (hm / hp * kp / sp + hm / hq * kq / sq) / 2.0}
    return out


def corner_triples(edges, ids):
    """Corners where three bevelled edges meet (a box corner bevelled on all three edges) and their sin(dihedral / 2)
    values h stay close (smallest / largest at least ``TRIPLE_SPLIT``). Like Maya, each face's new corner lies on its
    bisector, W hm / h_first from both edge lines: hm = the smallest h, h_first = h of the face's edge that comes
    first in Maya's vertex -> edge order at v. Returns {v: {"origin", "faces": {face: (unit bisector, k_ray, k)}}}
    (k = hm / h_first: how far that corner sits, in widths; k_ray = k / sin(half the corner angle))."""
    sel = set(edges)
    out = {}
    if ids is None:
        return out
    for v in {v for e in edges for v in e.verts}:
        if len(v.link_edges) != 3 or any(e not in sel or len(e.link_faces) != 2 for e in v.link_edges):
            continue
        order = vertex_edges(v, ids)
        if order is None:
            continue
        hs = {e: _half_sin(e, v) for e in order}
        if any(h is None for h in hs.values()):
            continue
        hm = min(hs.values())
        if hm / max(hs.values()) < TRIPLE_SPLIT:
            continue
        faces = {}
        for i, a in enumerate(order):
            for b in order[i + 1:]:
                shared = set(a.link_faces).intersection(b.link_faces)
                if len(shared) != 1:
                    continue
                ua, ub = (a.other_vert(v).co - v.co), (b.other_vert(v).co - v.co)
                if ua.length <= ZERO or ub.length <= ZERO:
                    continue
                ua.normalize()
                ub.normalize()
                half = math.acos(max(-1.0, min(1.0, ua.dot(ub)))) / 2.0
                ray = ua + ub
                if ray.length <= ZERO or math.sin(half) <= ZERO:
                    continue
                k = hm / hs[a]
                faces[shared.pop()] = (ray.normalized(), k / math.sin(half), k)
        if len(faces) == 3:
            out[v] = {"origin": v.co.copy(), "faces": faces}
    return out


def _flat(f):
    """Every vertex of face ``f`` lies in its plane."""
    n, c = f.normal, f.calc_center_median()
    size = max((v.co - c).length for v in f.verts)
    return all(abs((v.co - c).dot(n)) <= 1e-6 * max(1.0, size) for v in f.verts)


def corner_offsets(edges, ids):
    """Absolute Offset (Offset As Fraction off): the same box corners as ``corner_pairs`` (any dihedral angles) with
    a flat F, not almost straight. P, Q, s as there; a side face may be bent: each edge's width at an end is
    W n_e / h there, n_e = sin(dihedral / 2) between the face normals of F and e's side face (1 for flat faces).
    Like Maya:
    - the new corner in F lies on the bisector, W c n_P / h_P from both edge lines,
      c = max(1, sqrt(2 / (1 + (s_P / s_Q)^2)));
    - the new vertex on u3 lies 4 W / (3 max(s_P, s_Q) + min(s_P, s_Q)) from v, times the mean of n / h of P and Q.
    Returns {v: {...}} with the keys ``bevel_edges`` moves by."""
    sel = set(edges)
    out = {}
    if ids is None:
        return out
    for v in {v for e in edges for v in e.verts}:
        if len(v.link_edges) != 3 or any(len(e.link_faces) != 2 for e in v.link_edges):
            continue
        mine = [e for e in v.link_edges if e in sel]
        if len(mine) != 2:
            continue
        faces = set(mine[0].link_faces).intersection(mine[1].link_faces)
        order = vertex_edges(v, ids)
        if len(faces) != 1 or order is None or not _flat(next(iter(faces))):
            continue
        p, q = [e for e in order if e in sel]
        top = next(iter(faces))
        scales = [_face_half_sin(e, top) for e in (p, q)]
        heres = [_half_sin(e, v) for e in (p, q)]
        if None in scales or None in heres:
            continue
        rest = [e for e in v.link_edges if e not in sel][0]
        units = [e.other_vert(v).co - v.co for e in (p, q, rest)]
        if any(u.length <= ZERO for u in units):
            continue
        up, uq, u3 = [u.normalized() for u in units]
        sp, sq = up.cross(u3).length, uq.cross(u3).length
        half = math.acos(max(-1.0, min(1.0, up.dot(uq)))) / 2.0
        ray = up + uq
        if sp <= ZERO or sq <= ZERO or ray.length <= ZERO or math.sin(half) <= ZERO or up.dot(uq) < -NEAR_LINE:
            continue       # an almost straight corner is ``corner_moves``' (an n-gon cap rim)
        c = max(1.0, math.sqrt(2.0 / (1.0 + (sp / sq) ** 2)))
        wp, wq = scales[0] / heres[0], scales[1] / heres[1]
        out[v] = {"origin": v.co.copy(), "ray": ray.normalized(), "k_ray": c * wp / math.sin(half), "u3": u3,
                  "k_u3": 4.0 / (3.0 * max(sp, sq) + min(sp, sq)) * (wp + wq) / 2.0,
                  "ends": _far_ends((p, q), v, sel, scales)}
    return out


def _newell(f):
    """The face's normal from all its vertices (a bent face's average plane)."""
    n = f.verts[0].co * 0.0
    loops = [x.vert.co for x in f.loops]
    for a, b in zip(loops, loops[1:] + loops[:1]):
        n += a.cross(b)
    return n.normalized() if n.length > ZERO else None


def _face_half_sin(e, top):
    """sin(dihedral / 2) of edge ``e`` from the normals of face ``top`` and e's other face."""
    other = [f for f in e.link_faces if f is not top]
    if len(other) != 1:
        return None
    a, b = _newell(top), _newell(other[0])
    if a is None or b is None:
        return None
    return math.cos(math.acos(max(-1.0, min(1.0, a.dot(b)))) / 2.0)


def _far_ends(pair, v, sel, scales=None):
    """At the other end of each edge of a corner (when it ends only that bevelled edge) Maya keeps both new vertices
    one width from the edge (times n / h there for a bent side face, ``scales`` = n per edge); Blender's drift with
    the corner. [(position, unit slide edge, k = 1 / sin)]."""
    out = []
    for i, e in enumerate(pair):
        w = e.other_vert(v)
        here = _half_sin(e, w) if scales else None
        f = scales[i] / here if here else 1.0
        if sum(1 for x in w.link_edges if x in sel) != 1:
            continue
        d = (v.co - w.co)
        if d.length <= ZERO:
            continue
        d.normalize()
        for s in _slides(e, w):
            u = s.other_vert(w).co - w.co
            if u.length <= ZERO:
                continue
            u.normalize()
            if u.cross(d).length > ZERO:
                out.append((w.co.copy(), u, f / u.cross(d).length))
    return out


def strip_limits(edges, ends):
    """A lone bevelled edge whose two ends both have a slide edge near its line, the two running outwards almost
    parallel (|cos| of their angle above 0.9: a rim edge of an n-gon cap with many sides): the width is limited to
    half the edge's length over k at its first vertex (the lower index), like Maya. ``ends`` = ``end_moves``' third
    result."""
    sel = set(edges)
    out = []
    for e in edges:
        if any(sum(1 for x in v.link_edges if x in sel) != 1 for v in e.verts):
            continue
        a, b = sorted(e.verts, key=lambda v: v.index)
        if a not in ends or b not in ends or ends[a][1] is None or ends[b][1] is None:
            continue
        if -ends[a][1].dot(ends[b][1]) > NEAR_LINE and ends[a][0] > ZERO:
            out.append(e.calc_length() / (2.0 * ends[a][0]))
    return out


def _corner(v, f, sel):
    """Two bevelled edges of face ``f`` meet at ``v``: their new corner moves into ``f`` along the bisector, W / sin(half
    the angle) from v. Returns (unit bisector, half the angle, limit): the limit is the distance to where the bisector
    leaves the face x sin(half the angle), halved when it leaves through a vertex whose own corner moves back along
    the same line (a whole n-gon rim). None when the corner is degenerate."""
    a, b = [e for e in v.link_edges if e in sel and f in e.link_faces][:2]
    ua = (a.other_vert(v).co - v.co)
    ub = (b.other_vert(v).co - v.co)
    if ua.length <= ZERO or ub.length <= ZERO:
        return None
    ua.normalize()
    ub.normalize()
    half = math.acos(max(-1.0, min(1.0, ua.dot(ub)))) / 2.0
    ray = ua + ub
    if ray.length <= ZERO or math.sin(half) <= ZERO:
        return None
    ray.normalize()
    side = ua.cross(ub).cross(ray)      # the ray's line in the face plane: points p with (p - v) . side = 0
    if side.length <= ZERO:
        return None
    best = None
    for loop in f.loops:
        p, q = loop.vert, loop.link_loop_next.vert
        if v in (p, q):
            continue
        sp, sq = (p.co - v.co).dot(side), (q.co - v.co).dot(side)
        if (sp > 0) == (sq > 0) and abs(sp) > ZERO and abs(sq) > ZERO:
            continue
        x = sp / (sp - sq) if abs(sp - sq) > ZERO else 0.0
        hit = p.co.lerp(q.co, x)
        t = (hit - v.co).dot(ray)
        if t > ZERO and (best is None or t < best[0]):
            end = p if x < 1e-4 else q if x > 1 - 1e-4 else None
            best = (t, end)
    if best is None:
        return None
    t, end = best
    shared = 2 if end is not None and sum(1 for e in end.link_edges if e in sel and f in e.link_faces) >= 2 else 1
    return ray, half, t * math.sin(half) / shared


def corners_of(edges):
    """{(vertex, face)} where two bevelled edges of the face meet."""
    sel = set(edges)
    out = set()
    for e in edges:
        for v in e.verts:
            for s in v.link_edges:
                if s is not e and s in sel:
                    out.update((v, f) for f in set(e.link_faces).intersection(s.link_faces))
    return out


def corner_moves(edges):
    """Corners of a face where two bevelled edges meet almost straight (|cos| of the angle above 0.9: an n-gon cap with
    many sides): Blender leaves the new corner on the old vertex, Maya moves it W / sin(half the angle) along the
    bisector like any other corner. [(v position, unit bisector, k = 1 / sin(half the angle))]."""
    sel = set(edges)
    out = []
    for v, f in corners_of(edges):
        got = _corner(v, f, sel)
        if got is not None and math.cos(2.0 * got[1]) < -NEAR_LINE:
            out.append((v.co.copy(), got[0], 1.0 / math.sin(got[1])))
    return out


def slide_limit(edges, corners=None, triples=None):
    """Maya's fraction base (a perpendicular width): the smallest of
    (a) slide edges — an edge at an end of a bevelled edge that lies in one of its faces: length x sin(angle to the
        bevelled edge) / (number of its ends a bevel slides along); at a chain end where a slide edge runs near the
        bevelled edge's line (``end_moves``) length / k there instead; the third edge of a ``corner_pairs`` corner
        length / k_u3 (where the new vertex on it sits);
    (b) terminal edges at the end of an open chain (``terminal_moves``): length x s_phi / sin(alpha / 2) / (number of
        its ends that are such chain ends);
    (c) corners where two bevelled edges of one face meet (``_corner``): the new corner slides along the bisector
        (at a ``corner_triples`` corner it sits k widths from the edges, so its limit is over k).

    #124: a cylinder cap's border ring
    has no face holding two ring edges, so Maya slides along the side / cap fan edges (length 1) — and the width is
    perpendicular, so the fan edges at 81 degrees to the ring give 0.49995 x sin 81 = 0.49379 (the side ring lands at
    y 1.5062, the cap ring at radius 0.5); an n-gon cap gives the same through (c). An edge in no face of the
    bevelled edge is no slide edge; at a chain end it is a terminal edge (part of a cap rim: the unbevelled rim
    neighbour)."""
    sel = set(edges)
    used = {}
    _moves, near, near_ends = end_moves(edges, corners)
    _moves, term, scaled = terminal_moves(edges, corners)
    for e in edges:
        faces = set(e.link_faces)
        d = (e.verts[1].co - e.verts[0].co).normalized()
        for v in e.verts:
            if v in near_ends:
                continue
            for s in v.link_edges:
                if s is e or s in sel or not faces.intersection(s.link_faces):
                    continue
                t = (s.other_vert(v).co - v.co)
                if corners and v in corners and s is corners[v]["rest"]:
                    # the new vertex on the third edge of a paired corner sits k_u3 widths along it
                    sin = 1.0 / corners[v]["k_u3"]
                else:
                    sin = t.normalized().cross(d).length / scaled.get(v, 1.0) if t.length > ZERO else 0.0
                ent = used.setdefault(s, [set(), math.inf])
                ent[0].add(v)
                ent[1] = min(ent[1], sin)
    caps = []
    for v, f in corners_of(edges):
        c = _corner(v, f, sel)
        if c is not None and c[2] > ZERO:
            k = triples[v]["faces"].get(f, (None, None, 1.0))[2] if triples and v in triples else 1.0
            caps.append(c[2] / k)
    for s in set(used) | set(near):
        if s.calc_length() <= ZERO:
            continue
        ends, sin = used.get(s, (set(), 1.0))
        lengths = near.get(s, []) + ([s.calc_length() * sin] if ends else [])
        caps.append(min(lengths) / (len(ends) + len(near.get(s, []))))
    caps += strip_limits(edges, near_ends)
    caps += [min(ls) / len(ls) for ls in term.values()]
    if caps:
        return min(caps)
    return min((e.calc_length() for e in sel), default=0.0)


def profile(depth):
    t = 0.5 + max(-1.0, min(1.0, depth)) * (math.sqrt(0.5) - 0.5)
    return max(0.0, min(1.0, t * t))


def width(edges, fraction=0.5, offset_as_fraction=True, offset=0.2, unit=1.0, corners=None, triples=None):
    if offset_as_fraction:
        return max(0.0, min(1.0, fraction)) * slide_limit(edges, corners, triples) * FIT
    return max(0.0, offset) * unit * FIT


# --- Maya numbering -----------------------------------------------------------------------------------

def maya_edge_ids(bm):
    """{BMEdge: Maya edge id}: the mesh's edge index (kit design). It is Maya's id wherever
    the kit made the edges: kit polyCube / polyCylinder are built with Maya's edge order (prim_shapes ``edges``) and
    kit extrusions sort their result into polyExtrudeFacet's order (extrude.renumber),
    Maya numbers a mesh made from a face list in face-corner order; bmesh's
    ``faces.new`` doesn't (it makes a face's closing edge first), so such a mesh needs its edges made in that order
    first. Elsewhere (other primitives, Blender's own tools, imports) Maya's ids are not known."""
    bm.edges.index_update()
    return {e: e.index for e in bm.edges}


def vertex_edges(v, ids):
    """Maya's vertex -> edge order (MItMeshVertex.getConnectedEdges): start at the edge with the highest Maya id (on
    a border: the border edge the face winding leaves v along), then each next edge = the edge coming into v in the
    face the current edge leaves v in. 477 / 477 vertices of 24 meshes match Maya.
    None for a vertex that isn't a single fan of faces."""
    nxt = {}
    for loop in v.link_loops:
        if loop.edge in nxt:
            return None
        nxt[loop.edge] = loop.link_loop_prev.edge
    edges = list(v.link_edges)
    if not edges:
        return None
    heads = [e for e in nxt if e not in set(nxt.values())]
    if len(heads) > 1:
        return None
    cur = heads[0] if heads else max(edges, key=lambda e: ids[e])
    out = [cur]
    while len(out) < len(edges):
        cur = nxt.get(cur)
        if cur is None or cur in out:
            return None
        out.append(cur)
    return out


def _face_between(v, e_out, e_in):
    for loop in v.link_loops:
        if loop.edge is e_out and loop.link_loop_prev.edge is e_in:
            return loop.face
    return None


def _slots(v, sel, ids):
    """The new vertices of bevelled vertex ``v`` in Maya's order, each as the set of old face indices it lies in;
    None where the order is unknown (two or more bevelled edges at a border vertex, one bevelled edge at a two-edge
    vertex)."""
    E = vertex_edges(v, ids)
    if E is None or any(e.is_wire for e in E):
        return None
    n = len(E)
    marks = [k for k in range(n) if E[k] in sel]
    if len(marks) == 1:
        if n < 3 or E[marks[0]].is_boundary:
            return None
        # one bevelled edge: a new vertex on every other edge at v (the two next to it, and at a chain end with more
        # edges the terminal ones too; on a border vertex its border edges), in E(v)'s list order
        return [frozenset(f.index for f in E[j].link_faces) for j in range(n) if j != marks[0]]
    if any(e.is_boundary for e in E):
        return None
    between = [_face_between(v, E[k], E[(k + 1) % n]) for k in range(n)]
    if None in between:
        return None
    out = []
    for i, k in enumerate(marks):      # one new vertex per wedge, the wedge after each bevelled edge in E(v)'s order
        span = (marks[(i + 1) % len(marks)] - k) % n or n
        out.append(frozenset(between[(k + j) % n].index for j in range(span)))
    return out


def _end_faces(v, sel):
    """At a vertex that ends one bevelled edge: the old faces that go after the other untouched faces, like Maya —
    those whose vertex list starts at ``v`` and that don't hold v's bevelled edge."""
    return [f for f in v.link_faces if f.loops[0].vert is v and not any(x in sel for x in f.edges if v in x.verts)]


def _plan(bm, edges, ids):
    """Maya's order of what the bevel will leave, as keys the result is matched to (None: unknown here)."""
    sel = set(edges)
    bm.verts.index_update()
    bm.faces.index_update()
    order, seen = [], set()
    for e in sorted(edges, key=lambda e: ids[e]):
        for v in sorted(e.verts, key=lambda v: v.index):
            if v not in seen:
                seen.add(v)
                order.append(v)
    slots, edge_faces, met, corners, moved = [], [], set(), [], []
    for v in order:
        s = _slots(v, sel, ids)
        if s is None or len(set(s)) != len(s):
            return None
        slots += [(v.index, key) for key in s]
        for e in vertex_edges(v, ids):      # a bevel face comes when its edge is first met in this walk
            if e in sel and e not in met:
                met.add(e)
                edge_faces.append(frozenset(x.index for x in e.verts))
        deg = sum(1 for e in v.link_edges if e in sel)
        if deg >= 3 or deg == 1:
            corners.append(v.index)
        if deg == 1:
            moved += sorted(f.index for f in _end_faces(v, sel) if f.index not in moved)
    # old faces at a vertex that ends two or more bevelled edges (along a bevelled edge, or only touching one: a
    # plane's faces round a loop)
    along = sorted({f.index for v in order if sum(1 for e in v.link_edges if e in sel) >= 2 for f in v.link_faces})
    return {"kept": [v.index for v in bm.verts if v not in seen], "slots": slots, "edge_faces": edge_faces,
            "corners": corners, "along": along, "moved": moved, "faces": len(bm.faces),
            "co": {v.index: v.co.copy() for v in order}}


def _renumber(bm, plan, old_verts, flay, made, new_verts, merged=False):
    """Sort the bevelled mesh into Maya's order. Vertices only when every one is matched; faces only when every face
    is (else they keep Blender's order). A kept vertex is the same BMVert as before (``old_verts``: BMVert -> old
    index); a new vertex is matched by the old faces it lies in, and among bevelled vertices with a wedge of the same
    faces by the nearest old position (bevel copies a neighbour's custom data onto new vertices, and sometimes onto
    vertices it doesn't touch, so vertex custom data carries no reliable source index)."""
    kept = {i: n for n, i in enumerate(plan["kept"])}
    by_key = {}
    for n, (v, key) in enumerate(plan["slots"]):
        by_key.setdefault(key, []).append((v, len(kept) + n))
    rank, owner = {}, {}
    for v in bm.verts:
        if v not in new_verts:
            src = old_verts.get(v)
            r = kept.get(src)
        else:
            cands = by_key.get(frozenset(f[flay] - 1 for f in v.link_faces if f not in made), ())
            if not cands:
                return
            src, r = min(cands, key=lambda c: (plan["co"][c[0]] - v.co).length_squared)
        if r is None:
            return
        rank[v] = r
        owner[v] = src
    if merged:      # Merge Vertices removed some new vertices: the rest close up in the same order
        if len(set(rank.values())) != len(rank):
            return
        rank = {v: n for n, v in enumerate(sorted(rank, key=lambda v: rank[v]))}
    if sorted(rank.values()) != list(range(len(bm.verts))):
        return
    made_owners = {f: frozenset(owner[v] for v in f.verts if owner[v] in plan["co"]) for f in made}
    bm.verts.sort(key=lambda v: rank[v])
    bm.verts.index_update()
    # old faces: those at no vertex that ends two or more bevelled edges, then (after the bevel faces) those at one;
    # in each group the faces listed in plan["moved"] come last, in that order
    late = {i: n for n, i in enumerate(plan["moved"])}
    along = {i: n for n, i in enumerate(sorted(plan["along"], key=lambda i: (i in late, late.get(i, i))))}
    plain = {i: n for n, i in enumerate(sorted((i for i in range(plan["faces"]) if i not in along),
                                               key=lambda i: (i in late, late.get(i, i))))}
    edge_rank = {key: n for n, key in enumerate(plan["edge_faces"])}
    corner_rank = {v: n for n, v in enumerate(plan["corners"])}
    frank = {}
    for f in bm.faces:
        if f in made:
            srcs = made_owners[f]
            if srcs in edge_rank:
                frank[f] = (1, edge_rank[srcs])
            elif len(srcs) == 1 and next(iter(srcs)) in corner_rank:
                frank[f] = (3, corner_rank[next(iter(srcs))])
            else:
                return
        else:
            i = f[flay] - 1
            frank[f] = (2, along[i]) if i in along else (0, plain[i])
    if len(set(frank.values())) != len(frank):
        return
    bm.faces.sort(key=lambda f: frank[f][0] * 1000000 + frank[f][1])
    bm.faces.index_update()


def bevel_edges(bm, edges, fraction=0.5, offset_as_fraction=True, offset=0.2, segments=1, depth=1.0, unit=1.0,
                edge_ids=None, chamfer=True, **_unused):
    """polyBevel3 on ``edges`` (bmesh). Returns the vertices the bevel made (empty: nothing done). ``edge_ids``
    ({BMEdge: Maya edge id}) replaces ``maya_edge_ids`` for a mesh whose Maya edge numbering the caller knows."""
    edges = [e for e in edges if e.is_valid and len(e.link_faces) == 2]      # like Maya: border edges stay
    ids = edge_ids if edge_ids is not None else maya_edge_ids(bm)
    pairs2 = corner_pairs(edges, ids) if int(segments) == 1 and offset_as_fraction else {}
    triples = corner_triples(edges, ids) if int(segments) == 1 and offset_as_fraction else {}
    w = width(edges, fraction, offset_as_fraction, offset, unit, pairs2, triples)
    if not edges or w <= 0.0:
        return []
    # Chamfer off: Maya keeps the old corner as one more profile point (Segments + 1 steps along the two faces)
    bseg = max(1, int(segments)) + (0 if chamfer else 1)
    plan = _plan(bm, edges, ids) if ids is not None and int(segments) == 1 and chamfer else None
    bm.edges.index_update()
    picked = [e.index for e in edges]
    # face source indices ride along as custom data (bevel copies them onto what it makes); added before elements are
    # collected again, since adding a layer can invalidate element references
    tlay = bm.verts.layers.int.new(".allset_bevel_made")
    flay = bm.faces.layers.int.new(".allset_bevel_src")
    # Segments > 1: an edge layer finds each edge's strip afterwards (an edge layer invalidates edge references, so
    # the Maya edge ids are carried over by index)
    elay = None
    if bseg > 1:
        by_index = {e.index: i for e, i in ids.items()} if ids is not None else None
        elay = bm.edges.layers.int.new(".allset_bevel_edge")
        bm.edges.ensure_lookup_table()
        if by_index is not None:
            ids = {bm.edges[k]: i for k, i in by_index.items()}
    bm.verts.index_update()
    old_verts = {v: v.index for v in bm.verts}
    for f in bm.faces:
        f[flay] = f.index + 1
    bm.edges.ensure_lookup_table()
    edges = [bm.edges[i] for i in picked]
    if elay is not None:
        for i, e in enumerate(edges):
            e[elay] = i + 1      # bevel copies it onto the two outer edges of the edge's strip
    verts = {v for e in edges for v in e.verts}
    # old positions of the bevelled vertices with the number of bevelled edges there
    hubs = [(v.co.copy(), sum(1 for e in v.link_edges if e in edges)) for v in verts]
    hub_frames = hub_profile_frames(edges, verts)
    overs = [] if offset_as_fraction else past_ends(edges, w, spokes=True)
    # Offset As Fraction only: with an absolute Offset Maya leaves that vertex at W along the edge, as Blender does
    pairs2 = corner_pairs(edges, ids) if pairs2 else {}      # the elements were collected again
    triples = corner_triples(edges, ids) if triples else {}
    moves = [m + (None,) for m in terminal_moves(edges, pairs2)[0]] if int(segments) == 1 and offset_as_fraction else []
    # an end whose slide edge runs near the bevelled edge's line: Maya's offsets there, in both modes
    moves += end_moves(edges, pairs2)[0] if int(segments) == 1 else []
    offsets = corner_offsets(edges, ids) if int(segments) == 1 and not offset_as_fraction else {}
    moves += [m + (None,) for c in offsets.values() for m in c["ends"]]
    pair_moves = [(c["origin"], c["ray"], c["k_ray"], c["u3"], c["k_u3"])
                  for c in list(pairs2.values()) + list(offsets.values())]
    corners = corner_moves(edges) if int(segments) == 1 else []
    ret = bmesh.ops.bevel(bm, geom=list(edges) + list(verts), offset=w, offset_type='OFFSET',
                          segments=bseg, profile=profile(depth), affect='EDGES',
                          clamp_overlap=False, loop_slide=True)
    made = [v for v in ret["verts"] if v.is_valid]
    # Blender puts a chain end's new vertex on a terminal edge at W along it; Maya (Fraction) at W x k. The
    # new vertex is the one on that edge's line next to its far vertex (Blender doesn't put it on the edge when the
    # edge runs almost along the bevelled one), else the nearest made vertex on the line
    made_set = set(made)
    for origin, unit_dir, k, far in moves:
        best = None
        if far is not None and far.is_valid and far not in verts:
            for x in (e.other_vert(far) for e in far.link_edges):
                if x in made_set:
                    off = x.co - origin
                    gap = (off - unit_dir * off.dot(unit_dir)).length
                    if best is None or gap < best[0]:
                        best = (gap, x)
        if best is None:
            for v in made:
                off = v.co - origin
                s = off.dot(unit_dir)
                if s > 1e-7 and (off - unit_dir * s).length < 1e-5 and (best is None or s < best[0]):
                    best = (s, v)
        if best is not None:
            best[1].co = origin + unit_dir * (w * k)
    for origin, ray, k in corners:
        target = origin + ray * (w * k)
        best = min(made, key=lambda x: (x.co - target).length_squared, default=None)
        if best is not None and (best.co - origin).length < 1e-6:
            best.co = target
    for origin, ray, k_ray, u3, k_u3 in pair_moves:
        # the new corner = the made vertex nearest the bisector; the new vertex on u3 = the one nearest that line
        for line, k in ((ray, k_ray), (u3, k_u3)):
            def gap(x, line=line, k=k):
                off = x.co - origin
                near = 0.0 < off.dot(line) < 3.0 * w * max(1.0, k)
                return (off - line * off.dot(line)).length if near else math.inf
            best = min(made, key=gap, default=None)
            if best is not None and gap(best) < 0.5 * w:
                best.co = origin + line * (w * k)
    for c in triples.values():
        # each face's new corner = the made vertex nearest its bisector
        origin = c["origin"]
        for ray, k_ray, _k in c["faces"].values():
            def gap(x, ray=ray, origin=origin, k_ray=k_ray):
                off = x.co - origin
                near = 0.0 < off.dot(ray) < 3.0 * w * max(1.0, k_ray)
                return (off - ray * off.dot(ray)).length if near else math.inf
            best = min(made, key=gap, default=None)
            if best is not None and gap(best) < 0.5 * w:
                best.co = origin + ray * (w * k_ray)
    for far, origin, unit_dir, slide in overs:
        # the made vertex on that edge's line, at or near its far vertex
        def off_line(x, origin=origin, unit_dir=unit_dir):
            o = x.co - origin
            t = o.dot(unit_dir)
            return (o - unit_dir * t).length if t > 1e-6 else math.inf
        hit = min(made, key=lambda x: (off_line(x), (x.co - far).length_squared), default=None)
        if hit is not None and off_line(hit) < 1e-5:
            hit.co = origin + unit_dir * slide
    if not chamfer:
        corner_kept(bm, elay, {f for f in ret["faces"] if f.is_valid}, bseg, hubs)
    elif bseg > 1:
        true_arcs(bm, elay, {f for f in ret["faces"] if f.is_valid}, bseg, depth, hubs, hub_frames, w)
        made = flat_corners(bm, made, hubs)
    near = set(made)
    for v in made:
        near.update(e.other_vert(v) for e in v.link_edges)
    # Maya merges what the bevel made onto coincident vertices (a zero-length extrusion's sides, Fraction 1): every
    # group of vertices linked by gaps within the tolerance becomes one vertex at the group's mean (Fraction 1:
    # 0.49995 between 0.5 and 0.4999; four inner corners 0.0001 apart meet in the middle)
    made_set = set(made)
    pairs = merge_groups(list(near), made_set, MERGE * 1.001)
    if pairs:
        bmesh.ops.weld_verts(bm, targetmap=pairs)
    for v in near:
        if v.is_valid:
            v[tlay] = 1
    if plan is not None:
        _renumber(bm, plan, old_verts, flay, {f for f in ret["faces"] if f.is_valid}, {v for v in made if v.is_valid},
                  merged=bool(pairs))
    bm.verts.index_update()
    tracked = [v.index for v in bm.verts if v[tlay]]
    bm.verts.layers.int.remove(tlay)
    bm.faces.layers.int.remove(flay)
    if elay is not None:
        bm.edges.layers.int.remove(elay)
    bm.verts.ensure_lookup_table()
    extrude.deselect_all(bm)
    bm.select_flush_mode()
    bm.normal_update()
    return [bm.verts[i] for i in tracked]


def past_ends(edges, w, spokes=False):
    """Absolute Offset, slides longer than their side edge: Blender stops the new vertex at the side edge's far vertex, Maya goes on
    along that edge's line by width / sin(angle to the bevelled edge), past the mesh. With ``spokes`` (an absolute
    Offset) the new vertex on an edge in neither of the bevelled edge's faces (a cap fan's spoke) is always put at the
    width along it. Only at an
    end with one bevelled edge. Returns [(far vertex position, origin, unit direction, slide)]."""
    sel = set(edges)
    out = []
    for e in edges:
        for v in e.verts:
            if sum(1 for x in v.link_edges if x in sel) != 1:
                continue
            d = (e.other_vert(v).co - v.co)
            if d.length <= ZERO:
                continue
            d.normalize()
            sides = _slides(e, v)
            others = [x for x in v.link_edges if x is not e and x not in sides] if spokes else []
            for s in sides + others:
                if s in sel:
                    continue
                u = s.other_vert(v).co - v.co
                length = u.length
                if length <= ZERO:
                    continue
                u.normalize()
                if s in sides and abs(u.dot(d)) > NEAR_LINE:
                    continue      # a side edge near the bevelled edge's line: end_moves places that vertex
                sin = math.sqrt(max(0.0, 1.0 - u.dot(d) ** 2)) if s in sides else 1.0
                slide = w / sin
                # a spoke's vertex is always at the width (Blender moves it with a negative Depth)
                if slide > length * (1.0 + 1e-6) or s not in sides:
                    out.append((s.other_vert(v).co.copy(), v.co.copy(), u, slide))
    return out


def arc_points(p0, p1, n0, n1, segments, depth=1.0):
    """Maya's profile between the two width points ``p0`` / ``p1``: the circle touching face normal ``n0`` at p0
    and ``n1`` at p1, cut in equal angle steps; Depth d moves each arc point A from its foot Q on the chord p0-p1:
    Q + d (A - Q) (0 = on the chord, -1 = mirrored). Returns the ``segments - 1`` inner points."""
    chord = p1 - p0
    n0, n1 = n0.normalized(), n1.normalized()
    # the centre = where the lines p0 - t n0 and p1 - s n1 meet; None when they miss each other (a profile at a
    # slant to its edge: Blender's own profile is Maya's there) or the faces are parallel
    b = n0.dot(n1)
    den = 1.0 - b * b
    if den <= 1e-9 or chord.length <= ZERO:
        return None
    w0 = p0 - p1
    t = (w0.dot(n0) - b * w0.dot(n1)) / den
    s = (b * w0.dot(n0) - w0.dot(n1)) / den
    c0, c1 = p0 - n0 * t, p1 - n1 * s
    # a concave edge has its centre on the empty side (t, s < 0): the same circle, a fillet
    if t * s <= 0.0 or (c0 - c1).length > 1e-5 * chord.length:
        return None
    centre = (c0 + c1) / 2
    u0, u1 = p0 - centre, p1 - centre
    angle = u0.angle(u1, 0.0)
    d = chord.normalized()
    depth = max(-1.0, min(1.0, depth))
    out = []
    for k in range(1, segments):
        f = k / segments
        if angle <= 1e-9:
            a = p0.lerp(p1, f)
        else:
            sa = math.sin(angle)
            a = centre + u0 * (math.sin((1 - f) * angle) / sa) + u1 * (math.sin(f * angle) / sa)
        q = p0 + d * (a - p0).dot(d)
        out.append(q + (a - q) * depth)
    return out


def _strip_chains(rail, tag, elay, strip, segments):
    """Walk an edge's strip of bevel quads from its outer edge ``rail`` to the other outer edge (same ``tag``).
    Returns (chain at one end, chain at the other end, first outer edge, last outer edge) or None."""
    va, vb = rail.verts
    chain_a, chain_b = [va], [vb]
    cur, prev = rail, None
    for _ in range(segments):
        f = next((x for x in cur.link_faces if x in strip and x is not prev and len(x.verts) == 4), None)
        if f is None:
            return None
        a2 = next((e.other_vert(va) for e in f.edges if e is not cur and va in e.verts), None)
        b2 = next((e.other_vert(vb) for e in f.edges if e is not cur and vb in e.verts), None)
        nxt = next((e for e in f.edges if a2 in e.verts and b2 in e.verts), None) if a2 and b2 else None
        if nxt is None:
            return None
        va, vb, prev, cur = a2, b2, f, nxt
        chain_a.append(va)
        chain_b.append(vb)
        if cur[elay] == tag:
            return chain_a, chain_b, rail, cur
    return None


def _side_normal(rail, strip):
    """Normal of the old face next to an outer strip edge."""
    f = next((x for x in rail.link_faces if x not in strip), None)
    return f.normal.copy() if f is not None else None


def frame_points(v, e0, e1, segments, depth=1.0):
    """Maya's profile at an edge end with one or two bevelled edges: the arc for the angle e0-v-e1 taken in the
    plane (v, e0, e1), as point = v + a (e0 - v) + b (e1 - v) with (a, b) from the unit profile (a circle touching
    both unit legs at their ends, equal angle steps), Depth toward the chord. Also the join where two bevelled
    edges meet. Returns the ``segments - 1`` inner points or None."""
    u0, u1 = e0 - v, e1 - v
    if u0.length <= ZERO or u1.length <= ZERO:
        return None
    c = max(-1.0, min(1.0, u0.normalized().dot(u1.normalized())))
    theta = math.acos(c)
    if theta <= 1e-6 or theta >= math.pi - 1e-6:
        return None
    # unit legs l0 = (1, 0), l1 = (cos t, sin t); the circle touching both at their ends has its centre at
    # (1, tan(t / 2)); its radius turns from l0's end to l1's end through pi - t
    r = math.tan(theta / 2.0)
    sweep = math.pi - theta
    depth = max(-1.0, min(1.0, depth))
    out = []
    for k in range(1, segments):
        ang = sweep * k / segments
        px = 1.0 - r * math.sin(ang)
        py = r - r * math.cos(ang)
        # chord point (depth): foot on the chord from (1, 0) to (cos t, sin t)
        ax, ay = 1.0, 0.0
        bx, by = c, math.sin(theta)
        dx, dy = bx - ax, by - ay
        dl = math.hypot(dx, dy)
        t = ((px - ax) * dx + (py - ay) * dy) / (dl * dl)
        qx, qy = ax + dx * t, ay + dy * t
        px, py = qx + (px - qx) * depth, qy + (py - qy) * depth
        # back to leg coordinates: p = a l0 + b l1
        b = py / math.sin(theta)
        a = px - b * c
        out.append(v + u0 * a + u1 * b)
    return out


def hub_profile_frames(edges, verts):
    """{(rounded old vertex position, edge tag): (vertex, unit edge direction, mean sine)} where three or more
    bevelled edges meet. There the profile of a bevelled edge lies in the plane through its two ends and the point
    of the edge at width / s from the vertex, s = the mean of sin(angle between the edge and the other edge of the
    face at the vertex) over its two faces (the harmonic mean of where the neighbouring width lines cross it).
    Tags = index in ``edges`` + 1, as ``true_arcs`` sees them."""
    index = {e: i + 1 for i, e in enumerate(edges)}
    out = {}
    for v in verts:
        if sum(1 for e in v.link_edges if e in index) < 3:
            continue
        for e in v.link_edges:
            if e not in index:
                continue
            d = e.other_vert(v).co - v.co
            if d.length <= ZERO or len(e.link_faces) != 2:
                continue
            d.normalize()
            sines = []
            for f in e.link_faces:
                other = next((x for x in v.link_edges if x is not e and f in x.link_faces), None)
                if other is None:
                    break
                u = (other.other_vert(v).co - v.co).normalized()
                sines.append(math.sqrt(max(0.0, 1.0 - u.dot(d) ** 2)))
            if len(sines) == 2 and min(sines) > 1e-6:
                out[(_key(v.co), index[e])] = (v.co.copy(), d, (sines[0] + sines[1]) / 2.0)
    return out


def _key(co):
    return tuple(round(c, 5) for c in co)


def true_arcs(bm, elay, strip, segments, depth, hubs, hub_frames=None, w=0.0):
    """Segments > 1: Maya's profiles. At an end with one or two bevelled edges ``frame_points`` (the arc in the
    plane of the old vertex and the profile's ends); where three or more meet, the circle touching both faces
    (``arc_points``)."""
    rails = {}
    for e in bm.edges:
        if e[elay]:
            rails.setdefault(e[elay], []).append(e)
    for f in bm.faces:
        f.normal_update()

    def end_of(chain):
        if not hubs:
            return None
        mid = chain[len(chain) // 2].co
        return min(hubs, key=lambda x: (mid - x[0]).length_squared)

    for tag, rs in rails.items():
        if len(rs) != 2:
            continue
        walk = _strip_chains(rs[0], tag, elay, strip, segments)
        if walk is None:
            continue
        chain_a, chain_b, first, last = walk
        if len(chain_a) != segments + 1:
            continue
        n0, n1 = _side_normal(first, strip), _side_normal(last, strip)
        for chain in (chain_a, chain_b):
            p0, p1 = chain[0].co.copy(), chain[-1].co.copy()
            hub = end_of(chain)
            frame = (hub_frames or {}).get((_key(hub[0]), tag)) if hub is not None and hub[1] >= 3 else None
            corner = None
            if frame is not None and n0 is not None and n1 is not None and w > 0.0:
                v0, d, sine = frame
                t_pt = v0 + d * (w / sine)
                plane = (p1 - p0).cross(t_pt - p0)
                if plane.length > ZERO:
                    plane.normalize()
                    corner = _three_planes((n0, n0.dot(p0)), (n1, n1.dot(p1)), (plane, plane.dot(p0)))
            if hub is not None and hub[1] <= 2:
                pts = frame_points(hub[0], p0, p1, segments, depth)
            elif corner is not None:
                pts = frame_points(corner, p0, p1, segments, depth)
            elif n0 is not None and n1 is not None:
                pts = arc_points(p0, p1, n0, n1, segments, depth)
            else:
                pts = None
            if pts is not None:
                for v, p in zip(chain[1:-1], pts):
                    v.co = p


def corner_kept(bm, elay, strip, segments, hubs):
    """Chamfer off: each profile runs from its first end over the old corner to its other end (the line where the
    two faces meet), its points in equal steps along that path. ``segments`` = Blender's (Maya's + 1). Ends where
    two or more bevelled edges meet keep Blender's points."""
    rails = {}
    for e in bm.edges:
        if e[elay]:
            rails.setdefault(e[elay], []).append(e)
    for f in bm.faces:
        f.normal_update()
    for tag, rs in rails.items():
        if len(rs) != 2:
            continue
        walk = _strip_chains(rs[0], tag, elay, strip, segments)
        if walk is None:
            continue
        chain_a, chain_b, first, last = walk
        n0, n1 = _side_normal(first, strip), _side_normal(last, strip)
        if n0 is None or n1 is None or len(chain_a) != segments + 1:
            continue
        along = n0.cross(n1)
        if along.length <= ZERO:
            continue
        along.normalize()
        for chain in (chain_a, chain_b):
            mid = chain[len(chain) // 2].co
            if hubs and min(hubs, key=lambda h: (mid - h[0]).length_squared)[1] >= 2:
                continue
            p0, p1 = chain[0].co.copy(), chain[-1].co.copy()
            corner = _three_planes((n0, n0.dot(p0)), (n1, n1.dot(p1)), (along, along.dot((p0 + p1) / 2)))
            if corner is None:
                continue
            legs = (corner - p0).length, (p1 - corner).length
            total = legs[0] + legs[1]
            if total <= ZERO:
                continue
            for k, v in enumerate(chain[1:-1], 1):
                d = total * k / segments
                v.co = p0.lerp(corner, d / legs[0]) if d <= legs[0] else corner.lerp(p1, (d - legs[0]) / legs[1])


def _three_planes(a, b, c):
    """The point on three planes (normal, n . x) or None."""
    (na, da), (nb, db), (nc, dc) = a, b, c
    den = na.dot(nb.cross(nc))
    if abs(den) <= 1e-12:
        return None
    return (nb.cross(nc) * da + nc.cross(na) * db + na.cross(nb) * dc) / den


def merge_groups(verts, made_set, dist):
    """{vertex: target} for weld_verts: vertices linked by gaps <= ``dist`` (through each other) form one group,
    moved to the group's mean; the target is an old vertex when the group has one (it keeps its number)."""
    verts = [v for v in verts if v.is_valid]
    parent = {v: v for v in verts}

    def root(v):
        while parent[v] is not v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    for i, a in enumerate(verts):
        for b in verts[i + 1:]:
            if (a.co - b.co).length <= dist:
                ra, rb = root(a), root(b)
                if ra is not rb:
                    parent[rb] = ra
    groups = {}
    for v in verts:
        groups.setdefault(root(v), []).append(v)
    out = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        mean = sum((v.co for v in group), group[0].co * 0.0) / len(group)
        target = next((v for v in group if v not in made_set), group[0])
        for v in group:
            v.co = mean
            if v is not target:
                out[v] = target
    return out


def flat_corners(bm, made, hubs):
    """Where three or more bevelled edges meet, Maya closes the corner with one flat polygon through the ends of the
    edges' profiles (Segments 2 = a hexagon at a box corner, 3 = a 9-gon). Blender fills it with a patch of quads
    around inner vertices: those are dissolved. Returns ``made`` without them."""
    if not made or not any(n >= 3 for _co, n in hubs):
        return made
    made_set = set(made)
    # each new vertex belongs to the bevelled vertex it was made from: the nearest old position
    at = {v: min(range(len(hubs)), key=lambda i: (v.co - hubs[i][0]).length_squared) for v in made}
    inner = []
    for v in made:
        h = at[v]
        faces = list(v.link_faces)
        if hubs[h][1] >= 3 and len(faces) >= 3 and all(x in made_set and at[x] == h for f in faces for x in f.verts):
            inner.append(v)
    if not inner:
        return made
    bmesh.ops.dissolve_verts(bm, verts=inner)
    return [v for v in made if v.is_valid]


def chamfer_vertices(bm, verts):
    """Maya Chamfer Vertex (Ctrl+B in vertex mode): a face where each vertex was, 0.25 of each edge in."""
    verts = [v for v in verts if v.is_valid]
    if not verts:
        return []
    ret = bmesh.ops.bevel(bm, geom=verts, offset=CHAMFER, offset_type='PERCENT', segments=1, profile=0.5,
                          affect='VERTICES', clamp_overlap=False)
    extrude.deselect_all(bm)      # Maya selects only the polyChamfer node
    bm.select_flush_mode()
    bm.normal_update()
    return list(ret["verts"])


def world_scale(ob):
    """Object scale for World Space (Maya: the Offset in world units): the mean axis scale of the object."""
    if ob is None:
        return 1.0
    m = ob.matrix_world.to_3x3()
    s = abs(m.determinant()) ** (1.0 / 3.0)
    return s if s > ZERO else 1.0


def _build(bm, params, unit, ob=None):
    params = dict(params)
    if params.pop("world_space", False) and not params.get("offset_as_fraction", True):
        unit = unit / world_scale(ob)
    return bevel_edges(bm, [e for e in bm.edges if e.select], unit=unit, **params)


BEVEL = extrude.add_spec(extrude.Spec(
    'BEVEL', "polyBevel", ("fraction", "offset_as_fraction", "offset", "segments", "depth", "chamfer"),
    {"fraction": "Fraction", "offset_as_fraction": "Offset As Fraction", "offset": "Offset", "segments": "Segments",
     "depth": "Depth", "chamfer": "Chamfer"},
    {"fraction": 0.5, "offset_as_fraction": True, "offset": 0.2, "segments": 1, "depth": 1.0, "chamfer": True,
     "world_space": True},
    {"fraction": "NONE", "offset_as_fraction": "BOOL", "offset": "NONE", "segments": "INT", "depth": "NONE",
     "chamfer": "BOOL"},
    None, "bevel_edit", _build, node_type="polyBevel3", hidden=("world_space",), with_object=True))
