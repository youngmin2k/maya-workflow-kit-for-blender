# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Edit Mesh / Mesh Tools commands with Maya's results
(Connect / Merge / Smooth / Symmetrize too).
Circularize, Connect, Make Hole; Connect, Merge, Smooth, Symmetrize. Pure bmesh.
"""

import math

import bmesh
import bpy

from .. import results, undo_steps

CONNECT_WARNING = "Can't perform polyConnectComponents1 on selection"   # Maya's warning


# --- Circularize -------------------------------------------------------------------------------

def _ordered_loops(edges):
    """Closed loops among ``edges`` as ordered vertex lists (open chains are skipped)."""
    adj = {}
    for e in edges:
        a, b = e.verts
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    loops, seen = [], set()
    for start in adj:
        if start in seen or len(adj[start]) != 2:
            continue
        loop, prev, cur = [start], None, start
        ok = True
        while True:
            seen.add(cur)
            nxt = [v for v in adj[cur] if v is not prev]
            if len(adj[cur]) != 2 or not nxt:
                ok = False
                break
            prev, cur = cur, nxt[0]
            if cur is start:
                break
            loop.append(cur)
        if ok and len(loop) >= 3:
            loops.append(loop)
    return loops


def circularize_loop(verts, radial_offset=0.0, twist=0.0, even=True, ref=None):
    """Put an ordered vertex loop on a circle: centre = centroid, radius = mean distance (+ ``radial_offset``), evenly
    spaced keeping the loop's mean angular position (Maya polyCircularize defaults).
    Options: ``twist`` (radians) turns the loop
    right-handed about ``ref`` (the faces' normal), ``even`` off keeps each vertex's own angle about the centre.
    Returns the loop's normal (oriented like ``ref``) or None."""
    from mathutils import Vector
    n = len(verts)
    pts = [v.co.copy() for v in verts]
    c = sum(pts, Vector()) / n
    normal = Vector()
    for i in range(n):          # Newell normal
        a, b = pts[i], pts[(i + 1) % n]
        normal += Vector(((a.y - b.y) * (a.z + b.z), (a.z - b.z) * (a.x + b.x), (a.x - b.x) * (a.y + b.y)))
    if normal.length < 1e-12:
        return None
    normal.normalize()
    if ref is not None and ref.length > 1e-12 and normal.dot(ref) < 0:
        normal.negate()
    flat = [p - normal * (p - c).dot(normal) for p in pts]
    radius = sum((p - c).length for p in flat) / n + radial_offset
    u = flat[0] - c
    if u.length < 1e-12:
        u = next(((p - c) for p in flat if (p - c).length > 1e-12), None)
        if u is None:
            return None
    u.normalize()
    w = normal.cross(u)
    ang = [math.atan2((p - c).dot(w), (p - c).dot(u)) for p in flat]
    if even:
        turn = sum(math.remainder(ang[(i + 1) % n] - ang[i], math.tau) for i in range(n))
        s = 1.0 if turn >= 0 else -1.0
        step = s * math.tau / n
        off_x = sum(math.cos(ang[i] - step * i) for i in range(n))
        off_y = sum(math.sin(ang[i] - step * i) for i in range(n))
        off = math.atan2(off_y, off_x)
        ang = [off + step * i for i in range(n)]
    for v, t in zip(verts, ang):
        t += twist
        v.co = c + (u * math.cos(t) + w * math.sin(t)) * radius
    return normal


def circularize_loops(bm, mode, normal_offset=0.0, radial_offset=0.0, twist=0.0, even=True, divisions=0):
    """The loops Maya circularizes for the current selection: faces -> their border loops, edges / vertices ->
    closed loops of selected edges; ``mode`` 'ALL' = every border loop of the mesh. ``divisions`` first splits every
    loop edge (Maya Add Divisions: a 2-division octagon becomes 24 points, radius = their mean distance);
    ``normal_offset`` then moves the loop and the selected faces' inner vertices along the normal. Returns the loop
    count."""
    from mathutils import Vector

    def loop_edges():
        if mode == 'ALL':
            return [e for e in bm.edges if e.is_boundary]
        if mode == 'FACE':
            return [e for e in bm.edges if sum(f.select for f in e.link_faces) == 1]
        return [e for e in bm.edges if e.select]
    edges = loop_edges()
    if divisions > 0:
        loops0 = _ordered_loops(edges)
        on_loop = {e for lp in loops0 for i, v in enumerate(lp) for e in v.link_edges
                   if e.other_vert(v) is lp[(i + 1) % len(lp)]}
        # edge_split only adds vertices to the faces (subdivide_edges would cut corner patterns into them)
        for e in on_loop:
            a, b = e.verts
            cur, prev = e, a
            for k in range(divisions):
                _ne, nv = bmesh.utils.edge_split(cur, prev, 1.0 / (divisions + 1 - k))
                nv.select = True      # the split pieces keep the edge's selection (BM_edge_split copies it)
                cur = next(x for x in nv.link_edges if x.other_vert(nv) is b)
                prev = nv
        edges = loop_edges()
    loops = _ordered_loops(edges)
    faces = [f for f in bm.faces if f.select] if mode == 'FACE' else (list(bm.faces) if mode == 'ALL' else [])
    for loop in loops:
        ref = Vector()
        for v in loop:
            for f in v.link_faces:
                if mode != 'FACE' or f.select:
                    ref += f.normal
        normal = circularize_loop(loop, radial_offset, twist, even, ref)
        if normal is not None and normal_offset:
            inner = {v for f in faces for v in f.verts} if faces else set()
            for v in set(loop) | inner:
                v.co += normal * normal_offset
    return len(loops)


class ALLSET_OT_circularize(bpy.types.Operator):
    """Arrange the selected loop of components evenly on a circle (Maya Edit Mesh > Circularize)"""
    bl_idname = "allset.circularize"
    bl_label = "Circularize"
    bl_options = {'REGISTER', 'UNDO'}

    # Maya Polygon Circularize Options, factory values
    normal_offset: bpy.props.FloatProperty(name="Normal Offset", default=0.0, subtype='DISTANCE', unit='LENGTH',
                                           options={'SKIP_SAVE'})
    radial_offset: bpy.props.FloatProperty(name="Radial Offset", default=0.0, subtype='DISTANCE', unit='LENGTH',
                                           options={'SKIP_SAVE'})
    twist: bpy.props.FloatProperty(name="Twist", default=0.0, subtype='ANGLE', options={'SKIP_SAVE'})
    evenly_distribute: bpy.props.BoolProperty(name="Evenly Distribute", default=True, options={'SKIP_SAVE'})
    divisions: bpy.props.IntProperty(name="Add Divisions", default=0, min=0, soft_max=10, max=100,
                                     options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        sel = context.tool_settings.mesh_select_mode
        mode = 'FACE' if sel[2] else 'EDGE'
        total = 0
        for ob in context.objects_in_mode:
            bm = bmesh.from_edit_mesh(ob.data)
            # the whole mesh selected (object-mode menu run, menu_map.OBJECT_MODE): every border loop
            total += circularize_loops(bm, 'ALL' if all(e.select for e in bm.edges) else mode,
                                       self.normal_offset, self.radial_offset, self.twist, self.evenly_distribute,
                                       self.divisions)
            bmesh.update_edit_mesh(ob.data)
        if not total:
            self.report({'WARNING'}, "Select a closed loop of edges or vertices, or faces")
            return {'CANCELLED'}
        return {'FINISHED'}


# --- Connect -----------------------------------------------------------------------------------
# Maya Connect. Per face the points to join
# are its selected vertices and the midpoints of its selected edges; they are joined as a cycle in index order, a
# chord is skipped when its ends are neighbours on the face border or it crosses a chord already made. A selected
# edge whose face gets no chord is left alone (one edge -> nothing). Faces: the edges shared by two selected faces are
# cut at their midpoints; a strip end (one shared edge) whose neighbour has two or more continues to its opposite
# edge (three faces in a row -> a line through the row; two faces -> only the shared edge's midpoint).

def _border_pos(face, el):
    """Position of a vertex (2i) or an edge midpoint (2i + 1) along ``face``'s loop."""
    for i, loop in enumerate(face.loops):
        if loop.vert is el:
            return 2 * i
        if loop.edge is el:
            return 2 * i + 1
    return None


def _chords(face, points):
    """Pairs of ``points`` (BMVert / BMEdge of ``face``) to join, Maya's cycle with the skips above."""
    n2 = 2 * len(face.loops)
    pts = sorted(points, key=lambda p: (isinstance(p, bmesh.types.BMEdge), p.index))
    if len(pts) < 2:
        return []
    pairs = [(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts) if len(pts) > 2 else 1)]
    made = []
    for a, b in pairs:
        pa, pb = _border_pos(face, a), _border_pos(face, b)
        d = (pb - pa) % n2
        if d in (1, n2 - 1) or (pa % 2 == 0 and pb % 2 == 0 and d in (2, n2 - 2)):
            continue           # neighbours on the border: Maya adds nothing
        lo, hi = sorted((pa, pb))
        if any((lo < c < hi) != (lo < d2 < hi) and lo not in (c, d2) and hi not in (c, d2) for c, d2 in made):
            continue           # would cross a chord already made
        made.append((lo, hi))
        yield a, b


def _opposite_edge(face, edge):
    loops = list(face.loops)
    i = next(k for k, lp in enumerate(loops) if lp.edge is edge)
    return loops[(i + len(loops) // 2) % len(loops)].edge


def _loop_neighbour(v, e):
    """The vertex before ``v`` along the edge loop through edge ``e`` (the edge at ``v`` sharing no face with ``e``);
    None at poles / borders."""
    faces = set(e.link_faces)
    cand = [x for x in v.link_edges if x is not e and not faces & set(x.link_faces)]
    return cand[0].other_vert(v) if len(cand) == 1 else None


def _flow_point(a, b, t, adjust, pa=None, pb=None):
    """A point at ``t`` from ``a`` to ``b`` (BMVerts); with ``adjust`` (Maya Insert with edge flow) it follows a cubic
    through the loop neighbours: Hermite tangents 0.7 x (next - previous), the deviation from the straight edge times
    Adjust Edge Flow (fits Maya's polyConnectComponents on an 8 x 8 sphere within 1e-4)."""
    p1, p2 = a.co.copy(), b.co.copy()
    lin = p1.lerp(p2, t)
    if not adjust:
        return lin
    p0 = pa.co if pa is not None else 2 * p1 - p2
    p3 = pb.co if pb is not None else 2 * p2 - p1
    m1, m2 = 0.7 * (p2 - p0), 0.7 * (p3 - p1)
    t2, t3 = t * t, t * t * t
    h = (2 * t3 - 3 * t2 + 1) * p1 + (t3 - 2 * t2 + t) * m1 + (-2 * t3 + 3 * t2) * p2 + (t3 - t2) * m2
    return lin + (h - lin) * adjust


def _orient(jobs, split):
    """A start vertex per split edge so that the chords of a face pair points from the same side (Connect tool
    Slide / Segments): in face order, the end of the first edge faces the start of the second."""
    start, todo = {}, list(jobs)
    pending = True
    while pending:
        pending = False
        for f, a, b in todo:
            if not (isinstance(a, bmesh.types.BMEdge) and isinstance(b, bmesh.types.BMEdge)):
                continue
            la = next(lp for lp in f.loops if lp.edge is a)
            lb = next(lp for lp in f.loops if lp.edge is b)
            pairs = ((la.link_loop_next.vert, lb.vert), (la.vert, lb.link_loop_next.vert))
            if a in start and b not in start:
                start[b] = pairs[0][1] if start[a] is pairs[0][0] else pairs[1][1]
                pending = True
            elif b in start and a not in start:
                start[a] = pairs[0][0] if start[b] is pairs[0][1] else pairs[1][0]
                pending = True
            elif a not in start and b not in start:
                start[a] = a.verts[0]
                start[b] = pairs[0][1] if start[a] is pairs[0][0] else pairs[1][1]
                pending = True
    for e in split:
        start.setdefault(e, e.verts[0])
    return start


def connect(bm, mode, edge_flow=0.0, segments=1, slide=0.5):
    """Maya Connect on the selection (``mode`` 'VERT' / 'EDGE' / 'FACE'). Returns the number of new edges (0 = nothing
    to connect); the new edges end up selected. Options: ``edge_flow`` = Adjust Edge Flow with Insert with
    edge flow on (0 = off); Connect tool ``segments`` / ``slide`` (selected edges: n points per edge, centred on
    Slide)."""
    before = len(bm.edges)
    per_face = {}      # face -> points (BMVert / BMEdge)
    split = set()      # edges cut at their midpoints even without a chord (faces mode)
    if mode == 'FACE':
        sel = {f for f in bm.faces if f.select}
        inner = {e for f in sel for e in f.edges if len(e.link_faces) == 2 and all(x in sel for x in e.link_faces)}
        count = {f: sum(e in inner for e in f.edges) for f in sel}
        for f in sel:
            pts = [e for e in f.edges if e in inner]
            if len(pts) == 1:
                other = next(x for x in pts[0].link_faces if x is not f)
                if count[other] >= 2:
                    pts.append(_opposite_edge(f, pts[0]))
            per_face[f] = pts
        split = set(inner)
    else:
        if mode == 'VERT':
            items = [v for v in bm.verts if v.select]
        else:
            items = [e for e in bm.edges if e.select]
        for it in items:
            for f in it.link_faces:
                per_face.setdefault(f, []).append(it)
    jobs = [(f, a, b) for f, pts in per_face.items() for a, b in _chords(f, pts)]
    for f, a, b in jobs:
        for p in (a, b):
            if isinstance(p, bmesh.types.BMEdge):
                split.add(p)
    n_pts = max(1, int(segments)) if mode == 'EDGE' else 1
    fracs = [min(0.98, max(0.02, slide + ((k + 1) / (n_pts + 1) - 0.5))) for k in range(n_pts)] \
        if mode == 'EDGE' else [0.5]
    start = _orient(jobs, split)
    sides = []          # per job: the vertices of a and b on the same side of the face (before any split)
    for f, a, b in jobs:
        if isinstance(a, bmesh.types.BMEdge) and isinstance(b, bmesh.types.BMEdge):
            la = next(lp for lp in f.loops if lp.edge is a)
            lb = next(lp for lp in f.loops if lp.edge is b)
            near_a, near_b = la.link_loop_next.vert, lb.vert
            if start[a] is not near_a:
                near_a, near_b = la.vert, lb.link_loop_next.vert
            sides.append((near_a, near_b))
        else:
            sides.append(None)
    mids = {}
    for e in sorted(split, key=lambda e: e.index):
        a = start[e]
        b = e.other_vert(a)
        pa, pb = _loop_neighbour(a, e), _loop_neighbour(b, e)
        cos = [_flow_point(a, b, t, edge_flow, pa, pb) for t in fracs]
        pts, cur, done = [], e, 0.0
        for t, co in zip(fracs, cos):
            _ne, nv = bmesh.utils.edge_split(cur, a if not pts else pts[-1], (t - done) / (1.0 - done))
            nv.co = co
            pts.append(nv)
            cur = next(x for x in nv.link_edges if x.other_vert(nv) is b)
            done = t
        mids[e] = pts           # from the oriented start to the end
    new_edges = []
    mid = n_pts // 2
    for (f, a, b), side in zip(jobs, sides):
        if side is not None:
            pa_, pb_ = mids[a], mids[b]
            pairs = list(zip(pa_ if side[0] is start[a] else pa_[::-1], pb_ if side[1] is start[b] else pb_[::-1]))
        else:
            pairs = [(mids[a][mid] if isinstance(a, bmesh.types.BMEdge) else a,
                      mids[b][mid] if isinstance(b, bmesh.types.BMEdge) else b)]
        for va, vb in pairs:
            faces = [x for x in set(va.link_faces) & set(vb.link_faces)
                     if not any(vb in e.verts for e in va.link_edges if e in x.edges)]
            if not faces:
                continue
            _nf, loop = bmesh.utils.face_split(faces[0], va, vb)
            if loop is not None:
                new_edges.append(loop.edge)
    made = len(bm.edges) - before
    if made:
        for el in (*bm.verts, *bm.edges, *bm.faces):
            el.select = False
        for e in new_edges:
            e.select = True
        bm.select_flush_mode()
    return made


class ALLSET_OT_connect(bpy.types.Operator):
    """Connect the selected edges through their midpoints, the selected vertices across their faces, or the
    selected faces through their middles (Maya Edit Mesh / Mesh Tools > Connect)"""
    bl_idname = "allset.connect"
    bl_label = "Connect"
    bl_options = {'REGISTER', 'UNDO'}

    # Maya Connect Components Options  and the Mesh Tools > Connect
    # tool's Slide / Segments (:252-256); factory values
    insert_with_edge_flow: bpy.props.BoolProperty(name="Insert with edge flow", default=False, options={'SKIP_SAVE'})
    adjust_edge_flow: bpy.props.FloatProperty(name="Adjust Edge Flow", default=1.0, soft_min=-1.0, soft_max=2.0,
                                              options={'SKIP_SAVE'})
    segments: bpy.props.IntProperty(name="Segments", default=1, min=1, soft_max=10, max=100, options={'SKIP_SAVE'})
    slide: bpy.props.FloatProperty(name="Slide", default=0.5, min=0.0, max=1.0, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        v, e, f = context.tool_settings.mesh_select_mode
        mode = 'VERT' if v else ('EDGE' if e else 'FACE')
        made = 0
        for ob in context.objects_in_mode:
            bm = bmesh.from_edit_mesh(ob.data)
            made += connect(bm, mode, self.adjust_edge_flow if self.insert_with_edge_flow else 0.0,
                            self.segments, self.slide)
            bmesh.update_edit_mesh(ob.data)
        if not made:
            self.report({'WARNING'}, CONNECT_WARNING)
            return {'CANCELLED'}
        return {'FINISHED'}


# --- Make Hole ---------------------------------------------------------------------------------

MERGE_MODES = ("First", "Middle", "Second", "Project First", "Project Middle", "Project Second", "None")


def _hole_merge(target, stamp, mode):
    """Maya Make Hole Merge mode (polyMergeFacet -mergeMode): First / Middle /
    Second move the stamp, both, or the cut face so their centres meet; Project ... moves along the normal only, onto
    the first face's plane, the middle plane, or the stamp's plane; None leaves both."""
    from mathutils import Vector
    ct, cs = target.calc_center_median(), stamp.calc_center_median()
    if mode in ("First", "Middle", "Second"):
        d = cs - ct
        move_t, move_s = {"First": (Vector(), -d), "Middle": (d / 2, -d / 2), "Second": (d, Vector())}[mode]
    elif mode in ("Project First", "Project Middle", "Project Second"):
        n = (target.normal if mode != "Project Second" else stamp.normal).normalized()
        h = (cs - ct).dot(n)
        move_t, move_s = {"Project First": (Vector(), -n * h), "Project Middle": (n * h / 2, -n * h / 2),
                          "Project Second": (n * h, Vector())}[mode]
    else:
        return
    for v in target.verts:
        v.co += move_t
    for v in stamp.verts:
        v.co += move_s


def make_hole(bm, target, stamp, merge_mode="None"):
    """Cut ``stamp``'s outline into ``target`` (Maya Make Hole; factory merge mode None: the stamp keeps its position):
    both faces go, the two loops are bridged with quads. Returns the new faces."""
    _hole_merge(target, stamp, merge_mode)
    outer = list(target.edges)
    inner = list(stamp.edges)
    bmesh.ops.delete(bm, geom=[target, stamp], context='FACES_ONLY')
    res = bmesh.ops.bridge_loops(bm, edges=outer + inner)
    return res["faces"]


class ALLSET_OT_make_hole(bpy.types.Operator):
    """Cut the shape of the active (second) face as a hole into the other selected face of the same mesh
    (Maya Mesh Tools > Make Hole)"""
    bl_idname = "allset.make_hole"
    bl_label = "Make Hole"
    bl_options = {'REGISTER', 'UNDO'}

    merge_mode: bpy.props.EnumProperty(name="Merge mode", default="None", options={'SKIP_SAVE'},
                                       items=[(m, m, "") for m in MERGE_MODES])

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        ob = context.edit_object
        bm = bmesh.from_edit_mesh(ob.data)
        faces = [f for f in bm.faces if f.select]
        stamp = bm.faces.active if bm.faces.active in faces else None
        if len(faces) != 2 or stamp is None:
            self.report({'WARNING'}, "Select the face to cut, then the face whose shape makes the hole")
            return {'CANCELLED'}
        target = faces[0] if faces[1] is stamp else faces[1]
        if set(target.verts) & set(stamp.verts):
            self.report({'WARNING'}, "The two faces must not share vertices")
            return {'CANCELLED'}
        new = make_hole(bm, target, stamp, self.merge_mode)
        for f in new:
            f.select = True
        bmesh.update_edit_mesh(ob.data)
        return {'FINISHED'}


# --- Merge -------------------------------------------------------------------------------------
# polyMergeVert with the menu's factory options (distance 0.01, alwaysMergeTwoVertices on):
# vertices closer than the threshold merge to the mean of their cluster; exactly two selected vertices merge to their
# midpoint whatever the distance (even across the mesh, then non-manifold). Edge / face selections: the threshold only.

MERGE_THRESHOLD = 0.01


def merge(bm, verts, threshold, always_two=True):
    """Merge ``verts`` the Maya way (``threshold`` in mesh units). Returns the number of vertices removed."""
    verts = list(verts)
    if len(verts) < 2:
        return 0
    if always_two and len(verts) == 2:
        clusters = {verts[0]: [verts[0], verts[1]]}
    else:
        tmap = bmesh.ops.find_doubles(bm, verts=verts, dist=threshold)["targetmap"]
        clusters = {}
        for v, t in tmap.items():
            clusters.setdefault(t, [t]).append(v)
    if not clusters:
        return 0
    from mathutils import Vector
    targetmap = {}
    for t, vs in clusters.items():
        vs = list(dict.fromkeys(vs))
        t.co = sum((v.co for v in vs), Vector()) / len(vs)
        for v in vs:
            if v is not t:
                targetmap[v] = t
    before = len(bm.verts)
    bmesh.ops.weld_verts(bm, targetmap=targetmap)
    return before - len(bm.verts)


def merge_selection(bm, mode, threshold, always_two=True):
    if mode == 'VERT':
        verts = [v for v in bm.verts if v.select]
    else:      # Maya sews border edges within the threshold; a closed mesh's edges stay
        verts = list({v for e in bm.edges if e.select and e.is_boundary for v in e.verts})
        always_two = False
    return merge(bm, verts, threshold, always_two)


def _merge_values():
    """The Merge option window's saved values (Maya runs the menu item with its option values)."""
    from . import option_windows
    v = option_windows.saved("merge") or {}
    return v.get("threshold", MERGE_THRESHOLD), v.get("always_two", True)


class ALLSET_OT_merge(bpy.types.Operator):
    """Merge the selected vertices closer than the threshold to their centre; two vertices always merge
    (Maya Edit Mesh > Merge)"""
    bl_idname = "allset.merge"
    bl_label = "Merge"
    bl_options = {'REGISTER', 'UNDO'}

    threshold: bpy.props.FloatProperty(name="Threshold", default=MERGE_THRESHOLD, min=0.0, soft_max=10.0,
                                       precision=4, options={'SKIP_SAVE'})
    always_two: bpy.props.BoolProperty(name="Always merge for two vertices", default=True, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        from . import units
        if not self.properties.is_property_set("threshold") and not self.properties.is_property_set("always_two"):
            self.threshold, self.always_two = _merge_values()
        dist = self.threshold * units.maya_unit(context.scene)
        sel = context.tool_settings.mesh_select_mode
        mode = 'VERT' if sel[0] else 'EDGE'
        done = 0
        for ob in context.objects_in_mode:
            bm = bmesh.from_edit_mesh(ob.data)
            done += merge_selection(bm, mode, dist, self.always_two)
            bmesh.update_edit_mesh(ob.data)
        if not done:
            results.result(self, "No vertices were merged")
        return {'FINISHED'}


# --- Smooth ------------------------------------------------------------------------------------
# polySmoothFace with the menu's factory options (divisions 1, continuity 1, keep border / selection border,
# OpenSubdiv "sharp edges and corners"): Catmull-Clark on the chosen faces. A vertex moves
# only when all its faces are smoothed (mesh-border vertices along the border curve, corners stay); edges between two
# smoothed faces get the Catmull-Clark edge point, other edges their midpoint. Unsmoothed neighbours keep the new
# midpoints as extra vertices (Maya's n-gons).

def _smooth_once(bm, faces):
    from mathutils import Vector
    S = set(faces)
    fp = {f: f.calc_center_median() for f in S}
    edges = {e for f in S for e in f.edges}
    ep = {}
    for e in edges:
        a, b = e.verts[0].co, e.verts[1].co
        lf = e.link_faces
        if len(lf) == 2 and lf[0] in S and lf[1] in S:
            ep[e] = (a + b + fp[lf[0]] + fp[lf[1]]) / 4.0
        else:
            ep[e] = (a + b) / 2.0
    vp = {}
    for v in {v for f in S for v in f.verts}:
        lf = v.link_faces
        if not all(f in S for f in lf):
            continue
        if v.is_boundary:
            border = [e for e in v.link_edges if e.is_boundary]
            if len(border) == 2 and len(lf) > 1:
                o = [e.other_vert(v).co for e in border]
                vp[v] = v.co * 0.75 + (o[0] + o[1]) * 0.125
            continue
        n = len(v.link_edges)
        q = sum((fp[f] for f in lf), Vector()) / len(lf)
        r = sum(((e.verts[0].co + e.verts[1].co) / 2.0 for e in v.link_edges), Vector()) / n
        vp[v] = (q + 2.0 * r + (n - 3) * v.co) / n
    uv_layers = list(bm.loops.layers.uv)
    plan = []
    for f in S:
        loops = list(f.loops)
        uvs = [[lp[layer].uv.copy() for layer in uv_layers] for lp in loops]
        plan.append((f, [lp.vert for lp in loops], [lp.edge for lp in loops], uvs))
    mid = {}
    for e in sorted(edges, key=lambda e: e.index):
        _ne, nv = bmesh.utils.edge_split(e, e.verts[0], 0.5)
        mid[e] = nv
    new_faces = []
    for f, corners, f_edges, uvs in plan:
        n = len(corners)
        c = bm.verts.new(fp[f])
        cuv = [sum((u[k] for u in uvs), uvs[0][k] * 0) / n for k in range(len(uv_layers))]
        for i in range(n):
            prev = (i - 1) % n
            quad = (corners[i], mid[f_edges[i]], c, mid[f_edges[prev]])
            nf = bm.faces.new(quad, f)
            nf.select = True
            new_faces.append(nf)
            for k, layer in enumerate(uv_layers):
                ls = list(nf.loops)
                ls[0][layer].uv = uvs[i][k]
                ls[1][layer].uv = (uvs[i][k] + uvs[(i + 1) % n][k]) / 2.0
                ls[2][layer].uv = cuv[k]
                ls[3][layer].uv = (uvs[i][k] + uvs[prev][k]) / 2.0
    bmesh.ops.delete(bm, geom=[p[0] for p in plan], context='FACES_ONLY')
    for v, co in vp.items():
        v.co = co
    for e, v in mid.items():
        v.co = ep[e]
    return new_faces


def smooth(bm, faces, divisions=1):
    """Maya Smooth on ``faces`` (``divisions`` levels). Returns the new faces (selected)."""
    faces = list(faces)
    for _ in range(max(0, divisions)):
        if not faces:
            break
        faces = _smooth_once(bm, faces)
    bm.normal_update()
    return faces


def smooth_targets(bm):
    """The faces Maya smooths for the component selection: selected faces, else the faces of the selected edges,
    else of the selected vertices, else the whole mesh."""
    faces = [f for f in bm.faces if f.select]
    if faces:
        return faces
    edges = [e for e in bm.edges if e.select]
    if edges:
        return list({f for e in edges for f in e.link_faces})
    verts = [v for v in bm.verts if v.select]
    if verts:
        return list({f for v in verts for f in v.link_faces})
    return list(bm.faces)


# polySmoothFace history node (#204): Maya's Mesh > Smooth leaves polySmoothFace1 in Channel Box INPUTS with its
# Divisions editable. Like the kit's extrude / bevel nodes it is the last kit operation on the mesh (operators/extrude.py
# records), editable while the mesh is still its result, in component and object mode. The kit's Catmull-Clark has no
# Method / Continuity switch, so Divisions is its only row.

def _build_smooth(bm, params, unit):
    targets = smooth_targets(bm)
    for el in (*bm.verts, *bm.edges, *bm.faces):
        el.select = False
    faces = smooth(bm, targets, int(params["divisions"]))
    bm.select_flush_mode()
    return list({v for f in faces if f.is_valid for v in f.verts})


def _smooth_spec():
    from . import extrude
    return extrude.add_spec(extrude.Spec(
        'SMOOTH', "polySmoothFace", ("divisions",), {"divisions": "Divisions"}, {"divisions": 1},
        {"divisions": "INT"}, None, "smooth_edit", _build_smooth, in_view=False))


SMOOTH = _smooth_spec()


class ALLSET_OT_smooth(bpy.types.Operator):
    """Smooth the selected faces (component mode) or the selected meshes with real Catmull-Clark geometry
    (Maya Mesh > Smooth): change its Divisions in Channel Box INPUTS (polySmoothFace)"""
    bl_idname = "allset.smooth"
    bl_label = "Smooth"
    bl_options = {'REGISTER', 'UNDO'}

    divisions: bpy.props.IntProperty(name="Division levels", default=1, min=0, soft_max=4, max=6)

    @classmethod
    def poll(cls, context):
        if context.mode == 'EDIT_MESH':
            return True
        return context.mode == 'OBJECT' and any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        from . import extrude, units
        unit = units.maya_unit(context.scene)
        params = {"divisions": self.divisions}
        if context.mode == 'EDIT_MESH':
            for ob in context.objects_in_mode_unique_data:
                if ob.type != 'MESH':
                    continue
                bm = bmesh.from_edit_mesh(ob.data)
                if extrude.record_new(context, ob, bm, SMOOTH, params, unit) is None:
                    bmesh.update_edit_mesh(ob.data)
            return {'FINISHED'}
        done = set()
        for ob in context.selected_objects:
            if ob.type != 'MESH' or ob.data in done:
                continue
            done.add(ob.data)
            extrude.record_object(context, ob, SMOOTH, params, unit)
        return {'FINISHED'}


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_smooth_edit(bpy.types.Operator):
    """Change the last Smooth (Maya: edit the polySmoothFace node). Blender keeps no history, so only the last one
    can be changed"""
    bl_idname = "allset.smooth_edit"
    bl_label = "polySmoothFace"
    bl_options = {'REGISTER', 'UNDO'}

    divisions: bpy.props.IntProperty(name="Divisions", default=1, min=0, max=6, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode in {'EDIT_MESH', 'OBJECT'}

    def execute(self, context):
        from . import extrude, units
        params = {"divisions": self.divisions}
        if context.mode == 'OBJECT':
            ok = extrude.edit_from_object_mode(context, "smooth_edit", lambda _spec: params)
            return {'FINISHED'} if ok else {'CANCELLED'}
        unit = units.maya_unit(context.scene)
        done = 0
        for ob in context.objects_in_mode_unique_data:
            rec = extrude.RECORDS.get(ob.name)
            if rec is not None and rec.spec is SMOOTH and rec.pre is not None and (
                    rec.live or extrude.current(ob) is not None):
                done += bool(extrude.run(ob, rec, params, unit))
        return {'FINISHED'} if done else {'CANCELLED'}


# --- Symmetrize --------------------------------------------------------------------------------
# Maya 2022: with symmetry off (factory) Edit Mesh > Symmetrize enters "Select Symmetry
# Edge" ("Select a mesh edge for symmetry"), the mesh unchanged; the clicked edge = a topological symmetry seam, then
# each selected component's counterpart takes the mirrored position (the selected side drives; with both sides
# selected the side of the lowest-index selected vertex drives, Maya's -X side on a cube).
# Object mode / nothing selected: "No components selected for Symmetrize."

SYMMETRIZE_NO_COMPONENTS = "No components selected for Symmetrize."
SYMMETRIZE_PROMPT = "Select a mesh edge for symmetry"


def topo_mirror(bm, seam):
    """(vertex -> mirror vertex, vertex -> side 0 / 1) by walking both sides of ``seam`` face by face; None if the
    mesh isn't topologically symmetric about it."""
    if len(seam.link_faces) != 2:
        return None
    fa, fb = seam.link_faces
    m = {seam.verts[0]: seam.verts[0], seam.verts[1]: seam.verts[1]}
    side_f = {fa: 0, fb: 1}
    queue = [(fa, fb, seam, seam)]
    while queue:
        f, g, ea, eb = queue.pop()
        if len(f.loops) != len(g.loops):
            return None
        la = next(lp for lp in f.loops if lp.edge is ea)
        lb = next(lp for lp in g.loops if lp.edge is eb)
        if m.get(la.vert) is lb.link_loop_next.vert:
            a, b, back = la, lb.link_loop_next, True
        elif m.get(la.vert) is lb.vert:
            a, b, back = la, lb, False
        else:
            return None
        for _ in range(len(f.loops)):
            va, vb = a.vert, b.vert
            if m.get(va, vb) is not vb or m.get(vb, va) is not va:
                return None
            m[va], m[vb] = vb, va
            na = a.link_loop_next
            nb = b.link_loop_prev if back else b.link_loop_next
            e1 = a.edge
            e2 = nb.edge if back else b.edge
            if e1 is not e2:
                o1 = [x for x in e1.link_faces if x is not f]
                o2 = [x for x in e2.link_faces if x is not g]
                if len(o1) != len(o2):
                    return None
                if o1 and o1[0] not in side_f:
                    if o2[0] in side_f or o1[0] is o2[0]:
                        return None
                    side_f[o1[0]], side_f[o2[0]] = side_f[f], side_f[g]
                    queue.append((o1[0], o2[0], e1, e2))
            a, b = na, nb
    side = {}
    for f, s in side_f.items():
        for v in f.verts:
            if m.get(v) is not v:
                side[v] = s
    return m, side


def mirror_plane(bm, m, seam):
    """(point, unit normal) of the symmetry plane: fitted through the seam vertices (they map to themselves), else
    through the seam edge across its two faces."""
    import numpy as np
    from mathutils import Vector
    pts = [v.co for v, w in m.items() if v is w]
    c = sum(pts, Vector()) / len(pts)
    if len(pts) >= 3:
        a = np.array([p - c for p in pts], dtype=np.float64)
        w, vecs = np.linalg.eigh(a.T @ a)
        if w[1] > 1e-12:
            return c, Vector(vecs[:, 0]).normalized()
    d = (seam.verts[1].co - seam.verts[0].co).normalized()
    nrm = (seam.link_faces[0].normal + seam.link_faces[1].normal)
    return c, d.cross(nrm).normalized()


def symmetrize(bm, seam, selected):
    """Move the counterparts of ``selected`` vertices to their mirror positions about ``seam``. Returns the number
    of moved vertices, or None when the mesh isn't symmetric about that edge."""
    res = topo_mirror(bm, seam)
    if res is None:
        return None
    m, side = res
    src = [v for v in selected if v in side]
    if not src:
        return 0
    sides = {side[v] for v in src}
    drive = side[min(src, key=lambda v: v.index)] if len(sides) > 1 else sides.pop()
    c, n = mirror_plane(bm, m, seam)
    moved = 0
    for v in src:
        if side[v] != drive:
            continue
        w = m[v]
        w.co = v.co - 2.0 * (v.co - c).dot(n) * n
        moved += 1
    return moved


def _selected_verts(bm):
    return [v for v in bm.verts if v.select]


def _region_under(context, x, y):
    for area in context.window.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        for region in area.regions:
            if region.type == 'WINDOW' and region.x <= x < region.x + region.width \
                    and region.y <= y < region.y + region.height:
                from ..ui import toolbox
                if toolbox.is_toolbox(area.spaces.active):
                    return None
                return area, region
    return None


def pick_edge(context, region, rv3d, mouse):
    """(object, edge index) of the edit-mesh edge nearest ``mouse`` (region pixels) on screen, or None."""
    import numpy as np
    from . import preselect
    best = None
    scale = context.preferences.system.ui_scale or 1.0
    for ob in context.objects_in_mode_unique_data or ():
        if ob.type != 'MESH':
            continue
        bm = bmesh.from_edit_mesh(ob.data)
        bm.edges.ensure_lookup_table()
        mw = np.array(ob.matrix_world, dtype=np.float64)
        co = np.array([v.co[:] for v in bm.verts], dtype=np.float64).reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
        xy, front = preselect.project(co, rv3d.perspective_matrix, region.width, region.height)
        edges = np.array([(e.verts[0].index, e.verts[1].index) for e in bm.edges], dtype=np.int64).reshape(-1, 2)
        ok = np.array([not e.hide for e in bm.edges], dtype=bool)
        if len(edges):
            ok &= front[edges[:, 0]] & front[edges[:, 1]]
        i = preselect.pick_edge(xy, edges, ok, mouse, preselect.RADIUS_PX * scale, lambda i, t: True)
        if i is None:
            continue
        d, _t = preselect.segment_distance(mouse, xy[edges[[i], 0]], xy[edges[[i], 1]])
        if best is None or float(d[0]) < best[0]:
            best = (float(d[0]), ob, i)
    return None if best is None else (best[1], best[2])


class ALLSET_OT_symmetrize(bpy.types.Operator):
    """Click a mesh edge on the symmetry seam: the selected components' counterparts on the other side take their
    mirrored positions (Maya Edit Mesh > Symmetrize). Esc / right click cancels"""
    bl_idname = "allset.symmetrize"
    bl_label = "Symmetrize"
    bl_options = {'REGISTER', 'UNDO'}

    object_name: bpy.props.StringProperty(options={'SKIP_SAVE', 'HIDDEN'})
    edge: bpy.props.IntProperty(default=-1, options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.mode in ('EDIT_MESH', 'OBJECT')

    def _has_components(self, context):
        if context.mode != 'EDIT_MESH':
            return False
        return any(v.select for ob in context.objects_in_mode for v in bmesh.from_edit_mesh(ob.data).verts)

    def execute(self, context):
        if not self._has_components(context):
            self.report({'WARNING'}, SYMMETRIZE_NO_COMPONENTS)
            return {'CANCELLED'}
        ob = bpy.data.objects.get(self.object_name) if self.object_name else context.edit_object
        if ob is None or ob.mode != 'EDIT' or self.edge < 0:
            self.report({'WARNING'}, SYMMETRIZE_PROMPT)
            return {'CANCELLED'}
        bm = bmesh.from_edit_mesh(ob.data)
        bm.edges.ensure_lookup_table()
        if self.edge >= len(bm.edges):
            return {'CANCELLED'}
        moved = symmetrize(bm, bm.edges[self.edge], _selected_verts(bm))
        if moved is None:
            self.report({'WARNING'}, "The mesh is not topologically symmetric about that edge")
            return {'CANCELLED'}
        bmesh.update_edit_mesh(ob.data)
        return {'FINISHED'}

    def invoke(self, context, event):
        if self.edge >= 0:
            return self.execute(context)
        if not self._has_components(context):
            self.report({'WARNING'}, SYMMETRIZE_NO_COMPONENTS)
            return {'CANCELLED'}
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set(SYMMETRIZE_PROMPT)
        self._header = None
        if context.area is not None and context.area.type == 'VIEW_3D':
            context.area.header_text_set(SYMMETRIZE_PROMPT)
            self._header = context.area
        return {'RUNNING_MODAL'}

    def _end(self, context):
        context.workspace.status_text_set(None)
        if self._header is not None:
            try:
                self._header.header_text_set(None)
            except ReferenceError:
                pass

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._end(context)
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            hit = _region_under(context, event.mouse_x, event.mouse_y)
            if hit is None:
                return {'RUNNING_MODAL'}
            area, region = hit
            mouse = (event.mouse_x - region.x, event.mouse_y - region.y)
            with context.temp_override(area=area, region=region):
                found = pick_edge(context, region, region.data, mouse)
            if found is None:
                return {'RUNNING_MODAL'}       # Maya keeps waiting for an edge
            self._end(context)
            self.object_name, self.edge = found[0].name, found[1]
            return self.execute(context)
        return {'PASS_THROUGH'}


classes = (ALLSET_OT_circularize, ALLSET_OT_connect, ALLSET_OT_make_hole, ALLSET_OT_merge, ALLSET_OT_smooth,
           ALLSET_OT_smooth_edit, ALLSET_OT_symmetrize)
