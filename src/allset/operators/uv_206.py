# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya UV Editor depth 2: Cut/Sew > Auto Seams / Create Shell (Grid) / Split, Modify > Cycle and
the UV Sets items Rename Current UV Set / Copy UVs to UV Set > map1 / map1.

Rules follow Maya.
Maya UVs are kit points (operators/uv_shells.uv_points: loops of one vertex sharing a
coordinate); a Maya cut that leaves the UVs where they are can't be told apart from no cut in Blender (islands are
made from shared coordinates), so a split UV moves uv_tools.NUDGE towards its own faces (same convention as
Cut / Create UV Shell).

- Cycle: the first face of the selection (faces, else faces touching the selection) is cut
  out (CutUVs on its edges), then its vertices are walked from the lowest vertex id: the face's edges in Maya edge-id
  order, each edge as (lower id, higher id); next = the first edge whose lower end is the current vertex (and whose
  higher end isn't the previous one), else the first whose higher end is. Each UV takes the previous walked vertex's
  UV, the first the last's. Maya edge ids = creation order over the faces (corner k -> k+1), verified on every
  test mesh.
- Split: selection -> edges (UVs / vertices: every edge of their faces at that vertex;
  faces: their edges), then polyMapCut on them: at each end vertex the UV splits into the fans the cut edges separate.
- Create Shell (Grid) (polyUVRectangle): the two lowest selected vertices must be
  opposite corners of a rectangle of quads; its UVs become the uniform grid i / I, j / J over 0-1 (3D spacing and
  the old UVs don't matter), cut from the rest. Origin = the lower vertex id; U runs along the first edge (corner k -> k
  + 1, k = 0..3) of the origin's region face that contains the origin.
- Auto Seams (u3dAutoSeam -s 0 -p 1, Unfold3D): Maya keeps every existing cut and adds seams until a shell can be
  unfolded; its edge choice is Unfold3D's. Kit rule: cut graph of each shell (dual spanning tree, then
  dangling edges pruned) = the loops a torus / pipe needs and a path joining several borders; a closed genus-0 shell
  (cube, sphere, cylinder with caps) gets Maya's shape: one shortest path between its two farthest vertices.
"""

import heapq

import bmesh
import bpy
from bpy.props import StringProperty
from mathutils import Vector

from .. import compat, results, undo_steps
from . import uv_tools
from .uv_shells import _index_loops, _meshes, _poll
from .uv_tools import EPS, NUDGE, islands, sync

NO_FACE = "No face selected. Select a face and try again."    # Maya's warning text


def _same(a, b):
    return abs(a.x - b.x) <= EPS and abs(a.y - b.y) <= EPS


# --- Maya edge ids ---------------------------------------------------------------------------------------------

def maya_edge_ids(faces):
    """{frozenset(vertex index pair): Maya edge id} for faces given as vertex-index lists in face order: Maya numbers
    edges as the faces create them, corner k -> k + 1."""
    ids = {}
    for f in faces:
        n = len(f)
        for k in range(n):
            key = frozenset((f[k], f[(k + 1) % n]))
            if key not in ids:
                ids[key] = len(ids)
    return ids


def bm_edge_ids(bm):
    return maya_edge_ids([[v.index for v in f.verts] for f in bm.faces])


# --- Cycle ---------------------------------------------------------------------------

def cycle_walk(face_verts, edge_ids):
    """Vertex order Maya's Cycle UVs walks for one face (vertex indices)."""
    n = len(face_verts)
    pairs = [tuple(sorted((face_verts[k], face_verts[(k + 1) % n]))) for k in range(n)]
    pairs.sort(key=lambda p: edge_ids[frozenset(p)])
    left = [p[0] for p in pairs]
    right = [p[1] for p in pairs]

    def other(a, b, end, prev):
        for i in range(len(a)):
            if a[i] == end and b[i] != prev:
                return b[i]
        return -1

    v, prev, out = min(face_verts), -1, []
    while len(out) < n:
        out.append(v)
        lv = other(left, right, v, prev)
        rv = other(right, left, v, prev)
        if lv == -1 and rv == -1:
            return []
        prev, v = v, (lv if lv != -1 and prev != lv else rv)
    return out


def cycle_face(face, uv, edge_ids):
    walk = cycle_walk([v.index for v in face.verts], edge_ids)
    if len(walk) != len(face.verts):
        return False
    old = {l.vert.index: l[uv].uv.copy() for l in face.loops}
    new = {walk[i]: old[walk[i - 1]] for i in range(len(walk))}
    for e in face.edges:                      # CutUVs on the face's edges first: it becomes its own shell
        e.seam = True
    for l in face.loops:
        l[uv].uv = new[l.vert.index]
    return True


def _picked_faces(bm, uv, synced, uv_mode):
    """Faces of the selection the Maya way (faces, else faces touching the selected components)."""
    shown = [f for f in bm.faces if not f.hide and (synced or f.select)]
    if synced:
        own = [f for f in shown if f.select]
        return own or [f for f in shown if any(v.select for v in f.verts)]
    if uv_mode == 'FACE':
        own = [f for f in shown if all(compat.uv_vert_selected(l, uv) for l in f.loops)]
        if own:
            return own
    return [f for f in shown if any(compat.uv_vert_selected(l, uv) for l in f.loops)]


# --- polyMapCut (Split, Auto Seams) ------------------------------------------------------------------------------

def _fan_edges(loop):
    return (loop.edge, loop.link_loop_prev.edge)


def map_cut(bm, uv, edges, keep=()):
    """Maya polyMapCut on ``edges``: seams on them, and at every end vertex each UV splits into the fans the cut
    edges separate; every fan but one (one touching a face of ``keep``, else the one with the lowest loop index) moves
    NUDGE towards its faces. Returns how many UVs were added."""
    keep = set(keep)
    cut = set(edges)
    for e in cut:
        e.seam = True
    _index_loops(bm)
    added = 0
    for v in {v for e in cut for v in e.verts}:
        loops = [l for l in v.link_loops if not l.face.hide]
        groups = []
        for l in loops:
            for g in groups:
                if _same(g[0][uv].uv, l[uv].uv):
                    g.append(l)
                    break
            else:
                groups.append([l])
        for g in groups:
            if len(g) < 2:
                continue
            parent = {l: l for l in g}

            def find(x):
                while parent[x] is not x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            by_face = {l.face: l for l in g}
            for l in g:
                for e in _fan_edges(l):
                    if e in cut:
                        continue
                    for f in e.link_faces:
                        o = by_face.get(f)
                        if o is not None and o is not l:
                            ra, rb = find(l), find(o)
                            if ra is not rb:
                                parent[rb] = ra
            pieces = {}
            for l in g:
                pieces.setdefault(find(l), []).append(l)
            if len(pieces) < 2:
                continue
            ordered = sorted(pieces.values(), key=lambda ls: (not any(x.face in keep for x in ls),
                                                              min(x.index for x in ls)))
            c = ordered[0][0][uv].uv.copy()
            for piece in ordered[1:]:
                centre = Vector((0.0, 0.0))
                n = 0
                for l in piece:
                    for fl in l.face.loops:
                        centre += fl[uv].uv
                        n += 1
                d = centre / max(n, 1) - c
                d = d.normalized() * NUDGE if d.length > 1e-9 else Vector((NUDGE, 0.0))
                for l in piece:
                    l[uv].uv = c + d
                added += 1
    return added


def split_edges(bm, uv, synced, uv_mode):
    """polySplitTextureUV's PolySelectConvert 2: the selection as edges."""
    if synced:
        if 'FACE' in bm.select_mode and any(f.select for f in bm.faces):
            return {e for f in bm.faces if f.select and not f.hide for e in f.edges}
        if 'EDGE' in bm.select_mode and any(e.select for e in bm.edges):
            return {e for e in bm.edges if e.select and not e.hide}
        return {e for v in bm.verts if v.select and not v.hide for e in v.link_edges if not e.hide}
    shown = [f for f in bm.faces if f.select and not f.hide]
    if uv_mode == 'FACE':
        return {e for f in shown if all(compat.uv_vert_selected(l, uv) for l in f.loops) for e in f.edges}
    if uv_mode == 'EDGE':
        return {l.edge for f in shown for l in f.loops if compat.uv_edge_selected(l, uv)}
    return {e for f in shown for l in f.loops if compat.uv_vert_selected(l, uv) for e in _fan_edges(l)}


# --- Create Shell (Grid) (polyUVRectangle) -----------------------------------------------------------------------

def _u_and_v(corners, a):
    """Neighbours of ``a`` in a quad (vertex list): U = along the first edge k -> k + 1 holding ``a``."""
    k = corners.index(a)
    if k == 0:
        return corners[1], corners[3]
    return corners[k - 1], corners[(k + 1) % 4]


def rect_coords(faces, a, b):
    """polyUVRectangle on quads given as vertex lists (index = face id): {face id: {vertex: (i, j)}} of the
    rectangle with corners ``a`` (origin, lower id) and ``b``, plus (I, J); None when they aren't opposite corners
    of a rectangle of quads. Pure (tests run it on Maya's meshes)."""
    by_vert = {}
    for fi, f in enumerate(faces):
        for v in f:
            by_vert.setdefault(v, []).append(fi)
    edge_faces = {}
    for fi, f in enumerate(faces):
        for k in range(len(f)):
            edge_faces.setdefault(frozenset((f[k], f[(k + 1) % len(f)])), []).append(fi)
    for f0 in sorted(by_vert.get(a, ())):
        if len(faces[f0]) != 4:
            continue
        cs = faces[f0]
        un, vn = _u_and_v(cs, a)
        opp = cs[(cs.index(a) + 2) % 4]
        coords = {f0: {a: (0, 0), un: (1, 0), vn: (0, 1), opp: (1, 1)}}
        queue = [f0]
        while queue:
            g = queue.pop(0)
            gc = faces[g]
            for k in range(4):
                p, q = gc[k], gc[(k + 1) % 4]
                s = gc[(k + 3) % 4]           # p's other neighbour in g
                for h in edge_faces.get(frozenset((p, q)), ()):
                    if h == g or h in coords or len(faces[h]) != 4:
                        continue
                    hc = faces[h]
                    ip, iq = hc.index(p), hc.index(q)
                    pn = hc[(ip - 1) % 4] if hc[(ip - 1) % 4] != q else hc[(ip + 1) % 4]
                    qn = hc[(iq - 1) % 4] if hc[(iq - 1) % 4] != p else hc[(iq + 1) % 4]
                    P, Q, S = coords[g][p], coords[g][q], coords[g][s]
                    w = (P[0] - S[0], P[1] - S[1])
                    coords[h] = {p: P, q: Q, pn: (P[0] + w[0], P[1] + w[1]), qn: (Q[0] + w[0], Q[1] + w[1])}
                    queue.append(h)
        target = None
        for g in coords:                      # BFS order: the nearest copy of b (a wrapped grid has several)
            if b in coords[g]:
                target = coords[g][b]
                break
        if target is None or target[0] <= 0 or target[1] <= 0:
            continue
        I, J = target
        region = {g: c for g, c in coords.items()
                  if all(0 <= x <= I and 0 <= y <= J for x, y in c.values())}
        if len(region) == I * J:
            return region, (I, J)
    return None


def grid_shell(bm, uv, a, b):
    """Create Shell (Grid) between BMVerts ``a`` and ``b`` (order free). Returns the number of faces changed."""
    if a.index > b.index:
        a, b = b, a
    shown = [f for f in bm.faces if not f.hide]
    got = rect_coords([[v.index for v in f.verts] for f in shown], a.index, b.index)
    if got is None:
        return 0
    region, (I, J) = got
    picked = {shown[g]: c for g, c in region.items()}
    for f, c in picked.items():
        for l in f.loops:
            i, j = c[l.vert.index]
            l[uv].uv = Vector((i / I, j / J))
    border = {e for f in picked for e in f.edges if any(g not in picked and not g.hide for g in e.link_faces)}
    map_cut(bm, uv, border, keep=picked)       # where the grid lands on a neighbour's UV the cut must still split
    return len(picked)


def grid_vertices(bm, uv, synced):
    """The two lowest selected vertices (UVs / edges / faces count by their vertices, like Maya)."""
    if synced:
        vs = [v for v in bm.verts if v.select and not v.hide]
    else:
        vs = list({l.vert for f in bm.faces if f.select and not f.hide for l in f.loops
                   if compat.uv_vert_selected(l, uv)})
    vs.sort(key=lambda v: v.index)
    return vs[:2]


# --- Auto Seams --------------------------------------------------------------------------------------------------

def _node(face, vert, uv):
    """A shell vertex = mesh vertex + its UV in that face (one vertex can sit twice on a shell's border)."""
    c = uv_tools._uv_at(face, vert, uv)
    return (vert.index, round(c.x / EPS), round(c.y / EPS))


def _shell_graph(shell, uv):
    """(interior edges {edge: node pair}, border sides [node pair]) of a shell: interior = both faces in the shell
    and sharing their UVs; a border side per face for every other edge."""
    fs = set(shell)
    inner, border = {}, []
    for f in shell:
        for e in f.edges:
            link = [g for g in e.link_faces if g in fs]
            a, b = e.verts
            if len(link) == 2 and all(_same(uv_tools._uv_at(link[0], v, uv), uv_tools._uv_at(link[1], v, uv))
                                      for v in e.verts):
                inner[e] = (_node(f, a, uv), _node(f, b, uv))
            else:
                border.append((_node(f, a, uv), _node(f, b, uv)))
    return inner, border


def _shortest_path(edges, start, goal):
    adj = {}
    for e in edges:
        a, b = e.verts
        w = (a.co - b.co).length
        adj.setdefault(a, []).append((b, w, e))
        adj.setdefault(b, []).append((a, w, e))
    best = {start: 0.0}
    back = {}
    heap = [(0.0, start.index, start)]
    while heap:
        d, _i, v = heapq.heappop(heap)
        if v is goal:
            break
        if d > best.get(v, 1e30):
            continue
        for o, w, e in adj.get(v, ()):
            nd = d + w
            if nd < best.get(o, 1e30) - 1e-12:
                best[o] = nd
                back[o] = (v, e)
                heapq.heappush(heap, (nd, o.index, o))
    path, v = [], goal
    while v is not start and v in back:
        v, e = back[v]
        path.append(e)
    return path


def _farthest(verts, origin):
    return max(verts, key=lambda v: ((v.co - origin.co).length, -v.index))


def shell_seams(shell, uv):
    """Edges Auto Seams cuts in one shell (kit rule, see module doc)."""
    inner, border = _shell_graph(shell, uv)
    fs = set(shell)
    # dual spanning tree from the face nearest the shell's centre
    centre = sum((f.calc_center_median() for f in shell), Vector()) / len(shell)
    root = min(shell, key=lambda f: ((f.calc_center_median() - centre).length, f.index))
    seen, tree, queue = {root}, set(), [root]
    while queue:
        f = queue.pop(0)
        for e in sorted(f.edges, key=lambda e: e.index):
            if e not in inner:
                continue
            for g in e.link_faces:
                if g in fs and g not in seen:
                    seen.add(g)
                    tree.add(e)
                    queue.append(g)
    graph = set(inner) - tree
    degree = {}
    for pair in [inner[e] for e in graph] + border:
        for n in pair:
            degree[n] = degree.get(n, 0) + 1
    changed = True
    while changed:
        changed = False
        for e in sorted(graph, key=lambda e: e.index):
            if any(degree[n] == 1 for n in inner[e]):
                graph.discard(e)
                for n in inner[e]:
                    degree[n] -= 1
                changed = True
    if graph or border:
        return graph
    # closed genus 0: one shortest path between the two farthest vertices (Maya: cube corner to corner, sphere over a
    # pole, capped cylinder rim + side)
    verts = sorted({v for f in shell for v in f.verts}, key=lambda v: v.index)
    if len(verts) < 3:
        return set()
    a = _farthest(verts, verts[0])
    b = _farthest(verts, a)
    return set(_shortest_path(inner, a, b))


def auto_seams(bm, uv, faces):
    """Auto Seams on ``faces`` (their shells): returns the edges cut."""
    cut = set()
    for shell in islands(bm, uv, faces):
        cut |= shell_seams(shell, uv)
    if cut:
        map_cut(bm, uv, cut)
    return cut


# --- operators ---------------------------------------------------------------------------------------------------

class _UVOp:
    bl_options = {'REGISTER', 'UNDO'}
    poll = classmethod(lambda cls, context: _poll(context))
    empty = "Select UVs"

    def run(self, context, bm, uv, synced, uv_mode):
        raise NotImplementedError

    def execute(self, context):
        synced = sync(context)
        uv_mode = context.scene.tool_settings.uv_select_mode
        done = 0
        for ob in _meshes(context):
            bm = bmesh.from_edit_mesh(ob.data)
            uv = bm.loops.layers.uv.verify()
            bm.faces.ensure_lookup_table()
            got = self.run(context, bm, uv, synced, uv_mode)
            if got:
                done += got
                bmesh.update_edit_mesh(ob.data)
            if done and self.one_object:
                break
        if not done:
            self.report({'WARNING'}, self.empty)
            return {'CANCELLED'}
        return {'FINISHED'}

    one_object = False


@undo_steps.no_redo_panel
class ALLSET_OT_uv_cycle(_UVOp, bpy.types.Operator):
    """Rotate the UVs of the selected face one vertex (Maya Modify > Cycle)"""
    bl_idname = "allset.uv_cycle"
    bl_label = "Cycle"
    empty = NO_FACE
    one_object = True

    def run(self, context, bm, uv, synced, uv_mode):
        faces = _picked_faces(bm, uv, synced, uv_mode)
        if not faces:
            return 0
        faces.sort(key=lambda f: f.index)
        if len(faces) > 1:
            self.report({'WARNING'}, "Multiple faces selected.  Using f[%d]" % faces[0].index)
        return 1 if cycle_face(faces[0], uv, bm_edge_ids(bm)) else 0


@undo_steps.no_redo_panel
class ALLSET_OT_uv_split(_UVOp, bpy.types.Operator):
    """Split the selected UVs so each face around them gets its own (Maya Cut/Sew > Split)"""
    bl_idname = "allset.uv_split"
    bl_label = "Split"
    empty = "Select UVs, edges or faces"

    def run(self, context, bm, uv, synced, uv_mode):
        edges = split_edges(bm, uv, synced, uv_mode)
        if not edges:
            return 0
        map_cut(bm, uv, edges)
        return len(edges)


@undo_steps.no_redo_panel
class ALLSET_OT_uv_grid_shell(_UVOp, bpy.types.Operator):
    """Lay the quads between two selected corner vertices out as a grid shell over 0-1 (Maya Cut/Sew > Create Shell
    (Grid))"""
    bl_idname = "allset.uv_grid_shell"
    bl_label = "Create Shell (Grid)"
    empty = "Select two vertices at opposite corners of a rectangle of quads"
    one_object = True

    def run(self, context, bm, uv, synced, uv_mode):
        vs = grid_vertices(bm, uv, synced)
        if len(vs) < 2:
            return 0
        return grid_shell(bm, uv, vs[0], vs[1])


@undo_steps.no_redo_panel
class ALLSET_OT_uv_auto_seams(_UVOp, bpy.types.Operator):
    """Cut seams so each UV shell can be unfolded (Maya Cut/Sew > Auto Seams; unfold afterwards)"""
    bl_idname = "allset.uv_auto_seams"
    bl_label = "Auto Seams"
    empty = "No seams needed: every shell can already be unfolded"

    def run(self, context, bm, uv, synced, uv_mode):
        shown = [f for f in bm.faces if not f.hide and (synced or f.select)]
        picked = [f for f in shown if f.select] if synced else []
        if not synced and uv_mode == 'FACE':
            picked = [f for f in shown if all(compat.uv_vert_selected(l, uv) for l in f.loops)]
        cut = auto_seams(bm, uv, picked or [f for f in bm.faces if not f.hide])
        if cut:
            results.result(self, "Auto Seams: %d edges cut" % len(cut))
        return len(cut)


def _uv_layers(context):
    return [ob.data.uv_layers for ob in _meshes(context) if ob.data.uv_layers]


def _layer(layers, name):
    return layers.get(name) or (layers[0] if len(layers) else None)


class ALLSET_OT_uv_set_rename(bpy.types.Operator):
    """Rename the current UV set (Maya UV Sets > Rename Current UV Set...)"""
    bl_idname = "allset.uv_set_rename"
    bl_label = "Rename Current UV Set"
    bl_options = {'UNDO'}
    name: StringProperty(name="New UV set name", default="")

    @classmethod
    def poll(cls, context):
        return bool(_uv_layers(context))

    def invoke(self, context, event):
        layers = _uv_layers(context)[0]
        self.name = layers.active.name if layers.active else ""
        return context.window_manager.invoke_props_dialog(self, title="Rename Current UV Set", confirm_text="OK")

    def execute(self, context):
        name = self.name.strip()
        if not name:
            self.report({'WARNING'}, "Enter a UV set name")
            return {'CANCELLED'}
        for layers in _uv_layers(context):
            if layers.active:
                layers.active.name = name
        return {'FINISHED'}


def _edit_safe(context, fn):
    """Run ``fn`` on mesh data outside edit mode (UV layer data is stale / empty in edit mode)."""
    was_edit = context.mode == 'EDIT_MESH'
    if was_edit:
        bpy.ops.object.mode_set(mode='OBJECT')
    try:
        return fn()
    finally:
        if was_edit:
            bpy.ops.object.mode_set(mode='EDIT')


@undo_steps.no_redo_panel
class ALLSET_OT_uv_set_copy_to(bpy.types.Operator):
    """Copy the current UV set's UVs into another UV set (Maya UV Sets > Copy UVs to UV Set > <set>)"""
    bl_idname = "allset.uv_set_copy_to"
    bl_label = "Copy UVs to UV Set"
    bl_options = {'REGISTER', 'UNDO'}
    target: StringProperty(name="UV set", default="map1", options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return bool(_uv_layers(context))

    def execute(self, context):
        obs = [ob for ob in _meshes(context) if ob.data.uv_layers] or \
              [ob for ob in context.selected_objects if ob.type == 'MESH' and ob.data.uv_layers]

        def copy():
            n = 0
            for ob in obs:
                layers = ob.data.uv_layers
                src, dst = layers.active, _layer(layers, self.target)
                if src is None or dst is None or src == dst:
                    continue
                buf = [0.0] * (2 * len(src.data))
                src.data.foreach_get("uv", buf)
                dst.data.foreach_set("uv", buf)
                n += 1
            return n

        if not _edit_safe(context, copy):
            self.report({'WARNING'}, "The current UV set is already %s" % self.target)
            return {'CANCELLED'}
        return {'FINISHED'}


@undo_steps.no_redo_panel
class ALLSET_OT_uv_set_current(bpy.types.Operator):
    """Make this UV set the current one (Maya UV Sets > <set>)"""
    bl_idname = "allset.uv_set_current"
    bl_label = "Current UV Set"
    bl_options = {'REGISTER', 'UNDO'}
    target: StringProperty(name="UV set", default="map1", options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return bool(_uv_layers(context))

    def execute(self, context):
        for layers in _uv_layers(context):
            lay = _layer(layers, self.target)
            if lay is not None:
                layers.active = lay
                lay.active_render = True
        return {'FINISHED'}


classes = (ALLSET_OT_uv_cycle, ALLSET_OT_uv_split, ALLSET_OT_uv_grid_shell, ALLSET_OT_uv_auto_seams,
           ALLSET_OT_uv_set_rename, ALLSET_OT_uv_set_copy_to, ALLSET_OT_uv_set_current)
