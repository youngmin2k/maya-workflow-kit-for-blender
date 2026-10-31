# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya UV Editor Select / Edit commands.

Maya's commands work on every component of the hilited meshes of the current component mask
(UV Editor Select menu).
Kit mask: UV Sync Selection on = the mesh select mode (vertex / edge / face);
off = the UV Editor's own mode (vertex = Maya UV, edge, face; island = Maya UV Shell). Candidates are the faces the UV
Editor shows (uv_display.shown_faces). A "UV" = the loops of one vertex sharing one coordinate (Maya's UV id).

- Back-Facing / Front-Facing: a UV is back (front) when a face with
  negative (positive) UV winding area uses it; faces = faces all of whose UVs are, edges = face sides whose two UVs
  are, vertices = vertices with such a UV. So a clockwise quad between two counter-clockwise ones of its shell is
  front-facing too (strips 'fold', 'maj_mid', 'maj5').
- Texture Borders: components on UV shell borders (a face side no other face shares
  across with the same UVs: mesh borders + seams); faces = faces with such a side. UV Shell mask: Maya selects
  nothing (unsupported).
- Non-Overlapping (all meshes together): faces whose UV area meets no other face's
  (touching edges don't count); edges whose UV segments cross / lie along another edge's (shared or touching ends
  don't count); UVs / vertices with no other UV at the same place. UV Shell mask: every face outside the shells of
  overlapping faces.
- Unmapped Faces (= Mesh > Cleanup's zero map area test, 1e-6): faces with UV area < 1e-6, i.e. deleted
  UVs (the kit's Delete UVs collapses them to (0, 0), uv_shells.DELETED), UVs on a point or a line, tiny faces;
  Face component mode, selection replaced (nothing found: Maya's warning, selection cleared).
- To Connected Faces: faces touching the selection (= ``cmds.polyListComponentConversion(toFace=True)``:
  vertices -> their faces, edges -> the faces beside them, UVs -> the faces using them, faces stay).
- Unpin All (UVEditorUnpinAll): every UV pin of the meshes off.
"""

import bmesh
import bpy
from bpy.props import EnumProperty

from .. import compat, undo_steps
from . import uv_tools
from .component import select_only

EPS = uv_tools.EPS
AREA_TOL = 1e-6          # Maya 2026's Select Unmapped Faces tolerance
OVERLAP_AREA = 1e-10     # UV area shared by two faces that counts as an overlap
_TINY = 1e-12


# --- reading -------------------------------------------------------------------------------------------

def shown_faces(bm, synced):
    return [f for f in bm.faces if not f.hide and (synced or f.select)]


def mask(ts):
    """Maya component mask of the kit state: 'VERT' / 'EDGE' / 'FACE' / 'UV' / 'SHELL'."""
    from . import uv_shell_select
    if uv_shell_select.flag(bpy.context) and ts.use_uv_select_sync:      # Maya's UV Shell mask
        return 'SHELL'
    if ts.use_uv_select_sync:
        sv, se, sf = ts.mesh_select_mode
        return 'FACE' if sf and not (sv or se) else 'EDGE' if se and not sv else 'VERT'
    if compat.uv_island_mode(ts):
        return 'SHELL'
    return {'EDGE': 'EDGE', 'FACE': 'FACE'}.get(ts.uv_select_mode, 'UV')


def uv_area(face, uv):
    """Signed UV area (shoelace over the face corners): > 0 = counter-clockwise."""
    pts = [lp[uv].uv for lp in face.loops]
    a = 0.0
    for i, p in enumerate(pts):
        q = pts[(i + 1) % len(pts)]
        a += p.x * q.y - q.x * p.y
    return a / 2


def uv_groups(faces, uv):
    """Maya UVs of ``faces``: {loop: group id} (same vertex + same coordinate) and the groups' loop lists."""
    of, groups = {}, []
    by_vert = {}
    for f in faces:
        for lp in f.loops:
            p = lp[uv].uv
            gid = None
            for g in by_vert.get(lp.vert, ()):
                q = groups[g][0][uv].uv
                if abs(p.x - q.x) <= EPS and abs(p.y - q.y) <= EPS:
                    gid = g
                    break
            if gid is None:
                gid = len(groups)
                groups.append([])
                by_vert.setdefault(lp.vert, []).append(gid)
            groups[gid].append(lp)
            of[lp] = gid
    return of, groups


def _from_groups(kind, faces, of, groups, flagged):
    """Components of ``kind`` made from the flagged Maya UVs (faces: all their UVs, edges: both side UVs)."""
    if kind in ('FACE', 'SHELL'):
        return {f for f in faces if all(of[lp] in flagged for lp in f.loops)}
    if kind == 'EDGE':
        return {lp.edge for f in faces for lp in f.loops
                if of[lp] in flagged and of[lp.link_loop_next] in flagged}
    if kind == 'VERT':
        return {groups[g][0].vert for g in flagged}
    return {lp for g in flagged for lp in groups[g]}


# --- Back-Facing / Front-Facing ----------------------------------------------------------------------

def facing(kind, faces, uv, front):
    of, groups = uv_groups(faces, uv)
    flagged = set()
    for f in faces:
        a = uv_area(f, uv)
        if (a > _TINY) if front else (a < -_TINY):
            flagged.update(of[lp] for lp in f.loops)
    return _from_groups(kind, faces, of, groups, flagged)


# --- Texture Borders -----------------------------------------------------------------------------------

def border_sides(faces, uv):
    """Loops whose face side is a UV shell border: no other candidate face shares that edge with the same UVs."""
    shown = set(faces)
    out = []
    for f in faces:
        for lp in f.loops:
            joined = False
            for g in lp.edge.link_faces:
                if g is f or g not in shown:
                    continue
                if all(uv_tools._same(uv_tools._uv_at(f, v, uv), uv_tools._uv_at(g, v, uv)) for v in lp.edge.verts):
                    joined = True
                    break
            if not joined:
                out.append(lp)
    return out


def texture_borders(kind, faces, uv):
    sides = border_sides(faces, uv)
    if kind == 'FACE':
        return {lp.face for lp in sides}
    if kind == 'EDGE':
        return {lp.edge for lp in sides}
    if kind == 'VERT':
        return {v for lp in sides for v in lp.edge.verts}
    of, groups = uv_groups(faces, uv)
    flagged = {of[x] for lp in sides for x in (lp, lp.link_loop_next)}
    return {lp for g in flagged for lp in groups[g]}


# --- Overlapping ---------------------------------------------------------------------------------------

def _cells(items, size):
    """Uniform grid: {cell: [item index]} for items given as (lo_u, lo_v, hi_u, hi_v) boxes."""
    grid = {}
    for i, (u0, v0, u1, v1) in enumerate(items):
        for cx in range(int(u0 // size), int(u1 // size) + 1):
            for cy in range(int(v0 // size), int(v1 // size) + 1):
                grid.setdefault((cx, cy), []).append(i)
    return grid


def _pairs(boxes):
    if not boxes:
        return set()
    span = max(max(b[2] for b in boxes) - min(b[0] for b in boxes),
               max(b[3] for b in boxes) - min(b[1] for b in boxes), 1e-6)
    size = max(span / max(len(boxes) ** 0.5, 1.0), 1e-6)
    out = set()
    for ids in _cells(boxes, size).values():
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                a, b = boxes[ids[x]], boxes[ids[y]]
                if a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]:
                    out.add((ids[x], ids[y]))
    return out


def _box(pts):
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _clip(subject, clip):
    """Sutherland-Hodgman: ``subject`` polygon clipped by the convex counter-clockwise ``clip``."""
    out = list(subject)
    for i in range(len(clip)):
        a, b = clip[i], clip[(i + 1) % len(clip)]
        inp, out = out, []
        if not inp:
            break
        for j in range(len(inp)):
            p, q = inp[j], inp[(j + 1) % len(inp)]
            pin, qin = _cross(a, b, p) >= 0, _cross(a, b, q) >= 0
            if pin:
                out.append(p)
            if pin != qin:
                dp, dq = _cross(a, b, p), _cross(a, b, q)
                t = dp / (dp - dq)
                out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    return out


def _poly_area(pts):
    return abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                   for i in range(len(pts)))) / 2 if len(pts) >= 3 else 0.0


def overlapping_faces(tris):
    """``tris``: [(face, ((u, v) x 3))]: faces whose UV triangles share area with another face's."""
    norm = []
    for f, t in tris:
        if _cross(*t) < 0:
            t = (t[0], t[2], t[1])
        norm.append((f, t))
    hit = set()
    boxes = [_box(t) for _f, t in norm]
    for i, j in _pairs(boxes):
        (fa, ta), (fb, tb) = norm[i], norm[j]
        if fa is fb or (fa in hit and fb in hit):
            continue
        if abs(_cross(*ta)) <= _TINY or abs(_cross(*tb)) <= _TINY:
            continue
        if _poly_area(_clip(ta, tb)) > OVERLAP_AREA:
            hit.update((fa, fb))
    return hit


def _segments_cross(p, q, r, s):
    """Proper crossing, or collinear overlap of positive length; touching ends / T-junctions don't count."""
    d1, d2, d3, d4 = _cross(r, s, p), _cross(r, s, q), _cross(p, q, r), _cross(p, q, s)
    tol = 1e-12
    if abs(d1) <= tol and abs(d2) <= tol:              # collinear: overlap length along the longer axis
        ax = 0 if abs(q[0] - p[0]) >= abs(q[1] - p[1]) else 1
        a0, a1 = sorted((p[ax], q[ax]))
        b0, b1 = sorted((r[ax], s[ax]))
        return min(a1, b1) - max(a0, b0) > EPS
    return ((d1 > tol and d2 < -tol) or (d1 < -tol and d2 > tol)) and \
        ((d3 > tol and d4 < -tol) or (d3 < -tol and d4 > tol))


def overlapping_edges(segs):
    """``segs``: [(edge, (u, v), (u, v))] (one per distinct UV segment): edges with a crossing segment."""
    hit = set()
    boxes = [_box((a, b)) for _e, a, b in segs]
    for i, j in _pairs(boxes):
        (ea, a0, a1), (eb, b0, b1) = segs[i], segs[j]
        if ea is eb:
            continue
        if _segments_cross(a0, a1, b0, b1):
            hit.update((ea, eb))
    return hit


def overlapping_points(points):
    """``points``: [(key, (u, v))]: keys sharing a place (within EPS) with another key."""
    order = sorted(range(len(points)), key=lambda i: points[i][1][0])
    hit = set()
    for x, i in enumerate(order):
        pu, pv = points[i][1]
        for j in order[x + 1:]:
            qu, qv = points[j][1]
            if qu - pu > EPS:
                break
            if abs(qv - pv) <= EPS:
                hit.update((points[i][0], points[j][0]))
    return hit


def _tris(bm, faces):
    chosen = set(faces)
    return [(tri[0].face, tri) for tri in bm.calc_loop_triangles() if tri[0].face in chosen]


def non_overlapping(kind, meshes, overlapping=False):
    """meshes: [(bm, uv, faces)]: the Maya result per mesh, every mesh compared with every other (perObject 0).
    Returns [set] in ``meshes`` order."""
    if kind in ('FACE', 'SHELL'):
        tris = [(f, tuple(tuple(lp[uv].uv) for lp in tri)) for bm, uv, faces in meshes for f, tri in _tris(bm, faces)]
        hit = overlapping_faces(tris)
        out = []
        for bm, uv, faces in meshes:
            if kind == 'SHELL':
                over = set()
                for isl in uv_tools.islands(bm, uv, faces):
                    if hit & set(isl):
                        over.update(isl)
            else:
                over = hit & set(faces)
            out.append({f for f in faces if (f in over) == overlapping})
        return out
    if kind == 'EDGE':
        segs, seen = [], set()
        for bm, uv, faces in meshes:
            for f in faces:
                for lp in f.loops:
                    a, b = tuple(lp[uv].uv), tuple(lp.link_loop_next[uv].uv)
                    key = (id(bm), lp.edge.index) + tuple(sorted((tuple(round(c, 6) for c in a),
                                                                  tuple(round(c, 6) for c in b))))
                    if key not in seen:
                        seen.add(key)
                        segs.append((lp.edge, a, b))
        hit = overlapping_edges(segs)
        return [{lp.edge for f in faces for lp in f.loops if (lp.edge in hit) == overlapping}
                for _bm, _uv, faces in meshes]
    per = []
    points = []
    for m, (bm, uv, faces) in enumerate(meshes):
        of, groups = uv_groups(faces, uv)
        per.append((of, groups))
        points += [((m, g), tuple(ls[0][uv].uv)) for g, ls in enumerate(groups)]
    hit = overlapping_points(points)
    out = []
    for m, (bm, uv, faces) in enumerate(meshes):
        of, groups = per[m]
        flagged = {g for g in range(len(groups)) if ((m, g) in hit) == overlapping}
        if kind == 'VERT':
            # a vertex is overlapping when any of its UVs is
            bad = {groups[g][0].vert for g in range(len(groups)) if (m, g) in hit}
            verts = {groups[g][0].vert for g in range(len(groups))}
            out.append(bad if overlapping else verts - bad)
        else:
            out.append({lp for g in flagged for lp in groups[g]})
    return out


# --- Unmapped Faces / To Connected Faces ---------------------------------------------------------------

def unmapped_faces(faces, uv):
    if uv is None:
        return set(faces)
    return {f for f in faces if abs(uv_area(f, uv)) < AREA_TOL}


def connected_faces(bm, uv, ts):
    """Faces touching the selection (polyListComponentConversion -tf), among the shown faces."""
    synced = ts.use_uv_select_sync
    shown = shown_faces(bm, synced)
    kind = mask(ts)
    if synced:
        if kind == 'FACE':
            return {f for f in shown if f.select}
        if kind == 'EDGE':
            return {f for f in shown for e in f.edges if e.select}
        return {f for f in shown if any(v.select for v in f.verts)}
    if uv is None:
        return set()
    if kind in ('FACE', 'SHELL'):
        return set(uv_tools.selected_faces(bm, uv, False))
    if kind == 'EDGE':
        edges = {lp.edge for f in shown for lp in f.loops if compat.uv_edge_selected(lp, uv)}
        return {f for f in shown if any(e in edges for e in f.edges)}
    of, groups = uv_groups(shown, uv)
    picked = {of[lp] for f in shown for lp in f.loops if compat.uv_vert_selected(lp, uv)}
    return {f for f in shown if any(of[lp] in picked for lp in f.loops)}


def contained_faces(bm, uv, ts):
    """Faces the selection contains: all their UVs (vertices) selected."""
    synced = ts.use_uv_select_sync
    shown = shown_faces(bm, synced)
    if synced:
        return {f for f in shown if f.select}
    if uv is None:
        return set()
    return {f for f in shown if all(compat.uv_vert_selected(lp, uv) for lp in f.loops)}


# --- applying a result -----------------------------------------------------------------------------------

def apply(bm, uv, ts, kind, elems):
    """Replace the selection with ``elems`` of ``kind`` ('VERT' / 'EDGE' / 'FACE' / 'UV' loops / 'SHELL' faces)."""
    if ts.use_uv_select_sync:
        select_only(bm, kind if kind in ('VERT', 'EDGE', 'FACE') else 'FACE', elems)
        return
    shown = shown_faces(bm, False)
    for f in shown:
        compat.set_uv_face_selected(f, uv, False)
    if kind in ('FACE', 'SHELL'):
        for f in elems:
            compat.set_uv_face_selected(f, uv, True)
    elif kind == 'EDGE':
        for f in shown:
            for lp in f.loops:
                if lp.edge in elems:
                    compat.set_uv_edge_selected(lp, uv, True)
                    compat.set_uv_vert_selected(lp, uv, True)
                    compat.set_uv_vert_selected(lp.link_loop_next, uv, True)
    else:
        for lp in elems:
            compat.set_uv_vert_selected(lp, uv, True)
        for f in shown:
            for lp in f.loops:
                if lp in elems and lp.link_loop_next in elems:
                    compat.set_uv_edge_selected(lp, uv, True)


def _meshes(context):
    return [o for o in getattr(context, "objects_in_mode_unique_data", ()) or () if o.type == 'MESH']


def _poll(context):
    return context.mode == 'EDIT_MESH'


class _SelectOp:
    bl_options = {'REGISTER', 'UNDO'}
    poll = classmethod(lambda cls, context: _poll(context))
    empty = "Nothing to select"

    def rule(self, kind, bm, uv, faces):
        raise NotImplementedError

    def execute(self, context):
        ts = context.scene.tool_settings
        kind = mask(ts)
        out = []
        for ob in _meshes(context):
            bm = bmesh.from_edit_mesh(ob.data)
            uv = bm.loops.layers.uv.active
            if uv is None:
                continue
            out.append((ob, bm, uv, self.rule(kind, bm, uv, shown_faces(bm, ts.use_uv_select_sync))))
        if not out:
            self.report({'WARNING'}, "Select a mesh with UVs")
            return {'CANCELLED'}
        for ob, bm, uv, elems in out:
            apply(bm, uv, ts, kind, elems)
            bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
        return {'FINISHED'}


@undo_steps.no_redo_panel
class ALLSET_OT_uv_select_facing(_SelectOp, bpy.types.Operator):
    """Maya UV Editor Select > Back-Facing / Front-Facing: the components of faces whose UVs wind clockwise
    (back) or counter-clockwise (front)"""
    bl_idname = "allset.uv_select_facing"
    bl_label = "Select Facing UVs"

    front: bpy.props.BoolProperty(name="Front-Facing", default=False, options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        return ("Select the components of front-facing UV faces (counter-clockwise winding)" if props.front else
                "Select the components of back-facing UV faces (clockwise winding)")

    def rule(self, kind, bm, uv, faces):
        return facing(kind, faces, uv, self.front)


@undo_steps.no_redo_panel
class ALLSET_OT_uv_select_texture_borders(_SelectOp, bpy.types.Operator):
    """Maya UV Editor Select > Texture Borders: every component on the borders of UV shells"""
    bl_idname = "allset.uv_select_texture_borders"
    bl_label = "Select Texture Borders"

    def execute(self, context):
        if mask(context.scene.tool_settings) == 'SHELL':
            # Maya Texture Borders: no result for the UV Shell mask, the selection stays
            self.report({'WARNING'}, "Texture Borders works on UVs, vertices, edges or faces (not UV shells)")
            return {'CANCELLED'}
        return super().execute(context)

    def rule(self, kind, bm, uv, faces):
        return texture_borders(kind, faces, uv)


@undo_steps.no_redo_panel
class ALLSET_OT_uv_select_non_overlapping(bpy.types.Operator):
    """Maya UV Editor Select > Non-Overlapping: every component that shares no UV space with another"""
    bl_idname = "allset.uv_select_non_overlapping"
    bl_label = "Select Non-Overlapping UVs"
    bl_options = {'REGISTER', 'UNDO'}

    poll = classmethod(lambda cls, context: _poll(context))

    def execute(self, context):
        ts = context.scene.tool_settings
        kind = mask(ts)
        meshes = []
        for ob in _meshes(context):
            bm = bmesh.from_edit_mesh(ob.data)
            uv = bm.loops.layers.uv.active
            if uv is not None:
                meshes.append((ob, bm, uv, shown_faces(bm, ts.use_uv_select_sync)))
        if not meshes:
            self.report({'WARNING'}, "Select a mesh with UVs")
            return {'CANCELLED'}
        res = non_overlapping(kind, [(bm, uv, faces) for _ob, bm, uv, faces in meshes])
        for (ob, bm, uv, _faces), elems in zip(meshes, res):
            apply(bm, uv, ts, kind, elems)
            bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
        return {'FINISHED'}


@undo_steps.no_redo_panel
class ALLSET_OT_uv_select_unmapped(bpy.types.Operator):
    """Maya UV Editor Select > Unmapped Faces: the faces without UV area (deleted UVs collapse to (0, 0))"""
    bl_idname = "allset.uv_select_unmapped"
    bl_label = "Select Unmapped Faces"
    bl_options = {'REGISTER', 'UNDO'}

    poll = classmethod(lambda cls, context: _poll(context))

    def execute(self, context):
        obs = _meshes(context)
        if not obs:
            return {'CANCELLED'}
        ts = context.scene.tool_settings
        # Maya: component mode, face mask
        uv_tools.forget_mesh_selection()
        uv_tools.set_component(context, 'FACE')
        found = 0
        for ob in obs:
            bm = bmesh.from_edit_mesh(ob.data)
            faces = unmapped_faces([f for f in bm.faces if not f.hide], bm.loops.layers.uv.active)
            select_only(bm, 'FACE', faces)
            found += len(faces)
            bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
        ts.mesh_select_mode = (False, False, True)
        if not found:
            self.report({'WARNING'}, "No unmapped faces to select.")      # Maya's warning text
        return {'FINISHED'}


@undo_steps.no_redo_panel
class ALLSET_OT_uv_to_connected_faces(bpy.types.Operator):
    """Maya UV Editor Select > Convert Selection > To Connected Faces: the faces that share the selected
    components"""
    bl_idname = "allset.uv_to_connected_faces"
    bl_label = "To Connected Faces"
    bl_options = {'REGISTER', 'UNDO'}

    poll = classmethod(lambda cls, context: _poll(context))

    def execute(self, context):
        ts = context.scene.tool_settings
        out = []
        for ob in _meshes(context):
            bm = bmesh.from_edit_mesh(ob.data)
            uv = bm.loops.layers.uv.active
            out.append((ob, bm, uv, connected_faces(bm, uv, ts)))
        if not any(r[3] for r in out):
            self.report({'WARNING'}, "Select components to convert")
            return {'CANCELLED'}
        synced = ts.use_uv_select_sync
        if synced:
            ts.mesh_select_mode = (False, False, True)
        elif not compat.uv_island_mode(ts):
            ts.uv_select_mode = 'FACE'        # the mode first: a UV select-mode change flushes the selection
        for ob, bm, uv, faces in out:
            if synced or uv is not None:
                apply(bm, uv, ts, 'FACE', faces)
            bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
        return {'FINISHED'}


class ALLSET_OT_uv_unpin_all(bpy.types.Operator):
    """Maya UV Editor Edit > Unpin All: every pinned UV of the meshes unpinned"""
    bl_idname = "allset.uv_unpin_all"
    bl_label = "Unpin All"
    bl_options = {'UNDO'}

    poll = classmethod(lambda cls, context: _poll(context))

    def execute(self, context):
        for ob in _meshes(context):
            bm = bmesh.from_edit_mesh(ob.data)
            uv = bm.loops.layers.uv.active
            if uv is None:
                continue
            for f in bm.faces:
                for lp in f.loops:
                    if lp[uv].pin_uv:          # BMLoopUV.pin_uv in 4.5 and 5.x (compat.py:158)
                        lp[uv].pin_uv = False
            bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
        return {'FINISHED'}


FILTERS = (('CONNECTED', "Connected Faces", "Show only the faces connected to the selected UVs"),
           ('CONTAINED', "Contained Faces", "Show only the faces whose UVs are all selected"))


class ALLSET_OT_uv_filter_faces(bpy.types.Operator):
    """Maya UV Editor Select > Filter Selection > Connected / Contained Faces: show only the faces of the
    selection in the UV Editor (again = show all)"""
    bl_idname = "allset.uv_filter_faces"
    bl_label = "Filter Selection"
    bl_options = {'UNDO'}

    kind: EnumProperty(items=FILTERS, name="Faces", default='CONNECTED', options={'SKIP_SAVE'})

    poll = classmethod(lambda cls, context: _poll(context))

    @classmethod
    def description(cls, context, props):
        return next(d for k, _l, d in FILTERS if k == props.kind)

    def execute(self, context):
        from ..ui import uv_display
        ts = context.scene.tool_settings
        rule = connected_faces if self.kind == 'CONNECTED' else contained_faces
        if not uv_display.set_filter(context, self.kind, lambda bm, uv: rule(bm, uv, ts)):
            self.report({'WARNING'}, "Select UVs to filter by")
            return {'CANCELLED'}
        return {'FINISHED'}


classes = (ALLSET_OT_uv_select_facing, ALLSET_OT_uv_select_texture_borders, ALLSET_OT_uv_select_non_overlapping,
           ALLSET_OT_uv_select_unmapped, ALLSET_OT_uv_to_connected_faces, ALLSET_OT_uv_unpin_all,
           ALLSET_OT_uv_filter_faces)
