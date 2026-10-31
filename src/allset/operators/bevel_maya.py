# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya polyBevel3 (Edit Mesh > Bevel, Ctrl+B) at once, as an editable history node like the kit's extrusion
(#16).

- Defaults: Fraction 0.5, Offset As Fraction on, Offset 0.2, Segments 1, Depth 1 (Chamfer on, Mitering auto).
- Fraction is relative to one length for the whole selection: the shortest "slide" edge (an edge touching an end of a
  beveled edge), halved when both of its ends are used (two shells of different size get the same width). The width
  applied is 0.9999 x that (both modes).
- The profile is Blender's superellipse with ``profile = t^2``, t = 0.5 + Depth x (sqrt(1/2) - 1/2): Depth 1 = the
  round arc (0.5), 0 = straight, -1 = the arc mirrored over the chord (exact for 2 segments).
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


def edge_half_sin(e, sel):
    """One sin(alpha / 2) for a whole bevelled edge, like Maya: taken at its end where two or more bevelled edges
    meet (the smallest of theirs there), else at its first vertex (the lower index)."""
    ends = sorted(e.verts, key=lambda x: (sum(1 for y in x.link_edges if y in sel) < 2, x.index))
    v = ends[0]
    mine = [x for x in v.link_edges if x in sel]
    vals = [h for h in (_half_sin(x, v) for x in (mine if len(mine) >= 2 else [e])) if h is not None]
    return min(vals) if vals else None


def end_scale(e, v, sel):
    """At a chain end ``v`` of bevelled edge ``e``: the edge's sin(alpha / 2) over v's own (1 where both agree: planar
    faces, no corner at the first vertex). Every new vertex at v moves out from v by this factor."""
    here, edge = _half_sin(e, v), edge_half_sin(e, sel)
    if here is None or edge is None:
        return 1.0
    return edge / here


def terminal_moves(edges):
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
    near = end_moves(edges)[2]
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
        sin_half = edge_half_sin(e, sel) or here
        scale = sin_half / here
        if abs(scale - 1.0) > 1e-9 and v not in near:
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


def end_moves(edges):
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
        chord = (across[0] / sins[0] - across[1] / sins[1]).length * end_scale(e, v, sel)
        if gap <= ZERO or chord <= ZERO:
            continue
        near = [u for u, line in zip(units, lines) if line]
        done[v] = (chord / gap, near[0] if len(near) == 1 else None)
        for s, u, x in zip(slides, units, dirs):
            k = chord / gap * x.length
            moves.append((v.co.copy(), u, k, s.other_vert(v)))
            limits.setdefault(s, []).append(s.calc_length() / k)
    return moves, limits, done


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


def slide_limit(edges):
    """Maya's fraction base (a perpendicular width): the smallest of
    (a) slide edges — an edge at an end of a bevelled edge that lies in one of its faces: length x sin(angle to the
        bevelled edge) / (number of its ends a bevel slides along); at a chain end where a slide edge runs near the
        bevelled edge's line (``end_moves``) length / k there instead;
    (b) terminal edges at the end of an open chain (``terminal_moves``): length x s_phi / sin(alpha / 2) / (number of
        its ends that are such chain ends);
    (c) corners where two bevelled edges of one face meet (``_corner``): the new corner slides along the bisector.

    #124: a cylinder cap's border ring
    has no face holding two ring edges, so Maya slides along the side / cap fan edges (length 1) — and the width is
    perpendicular, so the fan edges at 81 degrees to the ring give 0.49995 x sin 81 = 0.49379 (the side ring lands at
    y 1.5062, the cap ring at radius 0.5); an n-gon cap gives the same through (c). An edge in no face of the
    bevelled edge is no slide edge; at a chain end it is a terminal edge (part of a cap rim: the unbevelled rim
    neighbour)."""
    sel = set(edges)
    used = {}
    _moves, near, near_ends = end_moves(edges)
    _moves, term, scaled = terminal_moves(edges)
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
                sin = t.normalized().cross(d).length / scaled.get(v, 1.0) if t.length > ZERO else 0.0
                ent = used.setdefault(s, [set(), math.inf])
                ent[0].add(v)
                ent[1] = min(ent[1], sin)
    caps = [c[2] for c in (_corner(v, f, sel) for v, f in corners_of(edges)) if c is not None and c[2] > ZERO]
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


def width(edges, fraction=0.5, offset_as_fraction=True, offset=0.2, unit=1.0):
    if offset_as_fraction:
        return max(0.0, min(1.0, fraction)) * slide_limit(edges) * FIT
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
                edge_ids=None, **_unused):
    """polyBevel3 on ``edges`` (bmesh). Returns the vertices the bevel made (empty: nothing done). ``edge_ids``
    ({BMEdge: Maya edge id}) replaces ``maya_edge_ids`` for a mesh whose Maya edge numbering the caller knows."""
    edges = [e for e in edges if e.is_valid and len(e.link_faces) == 2]      # like Maya: border edges stay
    w = width(edges, fraction, offset_as_fraction, offset, unit)
    if not edges or w <= 0.0:
        return []
    ids = edge_ids if edge_ids is not None else maya_edge_ids(bm)
    plan = _plan(bm, edges, ids) if ids is not None and int(segments) == 1 else None
    bm.edges.index_update()
    picked = [e.index for e in edges]
    # face source indices ride along as custom data (bevel copies them onto what it makes); added before elements are
    # collected again, since adding a layer can invalidate element references
    tlay = bm.verts.layers.int.new(".allset_bevel_made")
    flay = bm.faces.layers.int.new(".allset_bevel_src")
    bm.verts.index_update()
    old_verts = {v: v.index for v in bm.verts}
    for f in bm.faces:
        f[flay] = f.index + 1
    bm.edges.ensure_lookup_table()
    edges = [bm.edges[i] for i in picked]
    verts = {v for e in edges for v in e.verts}
    # Offset As Fraction only: with an absolute Offset Maya leaves that vertex at W along the edge, as Blender does
    moves = [m + (None,) for m in terminal_moves(edges)[0]] if int(segments) == 1 and offset_as_fraction else []
    # an end whose slide edge runs near the bevelled edge's line: Maya's offsets there, in both modes
    moves += end_moves(edges)[0] if int(segments) == 1 else []
    corners = corner_moves(edges) if int(segments) == 1 else []
    ret = bmesh.ops.bevel(bm, geom=list(edges) + list(verts), offset=w, offset_type='OFFSET',
                          segments=max(1, int(segments)), profile=profile(depth), affect='EDGES',
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
    near = set(made)
    for v in made:
        near.update(e.other_vert(v) for e in v.link_edges)
    # Maya merges what the bevel made onto coincident vertices (a zero-length extrusion's sides, Fraction 1), at
    # their midpoint (Fraction 1: 0.49995 between 0.5 and 0.4999)
    pairs = bmesh.ops.find_doubles(bm, verts=list(near), dist=MERGE * 1.001)["targetmap"]
    made_set = set(made)
    # a new vertex merged onto an old one leaves the old one (and its number), like Maya
    pairs = {(t if v not in made_set and t in made_set else v): (v if v not in made_set and t in made_set else t)
             for v, t in pairs.items()}
    for v, target in pairs.items():
        target.co = (v.co + target.co) / 2
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
    bm.verts.ensure_lookup_table()
    extrude.deselect_all(bm)
    bm.select_flush_mode()
    bm.normal_update()
    return [bm.verts[i] for i in tracked]


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


def _build(bm, params, unit):
    return bevel_edges(bm, [e for e in bm.edges if e.select], unit=unit, **params)


BEVEL = extrude.add_spec(extrude.Spec(
    'BEVEL', "polyBevel", ("fraction", "offset_as_fraction", "offset", "segments", "depth"),
    {"fraction": "Fraction", "offset_as_fraction": "Offset As Fraction", "offset": "Offset", "segments": "Segments",
     "depth": "Depth"},
    {"fraction": 0.5, "offset_as_fraction": True, "offset": 0.2, "segments": 1, "depth": 1.0},
    {"fraction": "NONE", "offset_as_fraction": "BOOL", "offset": "NONE", "segments": "INT", "depth": "NONE"},
    None, "bevel_edit", _build, node_type="polyBevel3"))
