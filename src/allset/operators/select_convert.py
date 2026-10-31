# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Select menu / Ctrl+RMB (CTRL_CONVERT) conversions Blender has no operator for:
Grow / Shrink Along Loop, To Vertex / Edge / Face Perimeter, To Face Path, To Shell Border, To UV Shell Border,
To UVs, To UV Perimeter, To UV Edge Loop.

Every rule is Maya 2022's, checked on a 4 x 4 plane, a 6 x 6 plane and a cube.

- Grow Along Loop (PolySelectTraverse 5): a face / vertex / edge with a selected neighbour grows one step past each
  end of that line (faces: the face across the quad's opposite edge; vertices: through the selected edges between
  them); an isolated face / vertex grows to all its neighbours; an edge grows one edge along its loop at each end.
- Shrink Along Loop (PolySelectTraverse 6): the ends of every line go (a face whose neighbour on one side of a
  direction is selected and on the other not; an isolated face); edges whose loop continuation at an end is not
  selected go; vertices = the vertices of the shrunk edges between them (a 3 x 3 vertex block shrinks to nothing).
- Perimeters (convertToSelectionBorder / polySelectFacePerimeter): the region = the selected faces, else the faces
  the selection contains, else the faces it touches (vertices: their faces, edges: the edges' faces); its border
  edges, their vertices, all UVs of those vertices. Face Perimeter keeps a selection that contains no face.
- To Face Path (SelectFacePath): the edge rings of the touched edges, then the faces of those rings.
- To Shell Border: only when part of the selection is on an open border: then every
  border component (same type) of those shells; nothing otherwise. To UV Shell Border (polySelectBorderShell 1):
  the open-border components of the shells the selection touches (UVs: the UV shell border).
- To UVs (PolySelectConvert 4): faces -> their UVs; edges -> their UVs in the faces beside them; vertices -> every UV.

Blender has no UV component in the 3D View: a UV result is the UV Editor's selection with UV Sync Selection off
(the kit's Maya UV component, operators/uv_tools.set_component). In that state the selection *is* the UV
selection, so a conversion reads it as vertices (the selected UVs' vertices); sync off alone is Blender's factory
state, so ``uv_source`` decides.
"""

import bmesh
import bpy
from bpy.props import EnumProperty

from . import uv_tools
from .component import _MODES, select_only
from .. import compat

KINDS = (
    ('GROW_LOOP', "Grow Along Loop", "Grow the selected region along its loops (Maya Select > Grow Along Loop)"),
    ('SHRINK_LOOP', "Shrink Along Loop", "Shrink the selected region along its loops (Maya Select > Shrink Along "
                                         "Loop)"),
    ('VERTEX_PERIMETER', "To Vertex Perimeter", "The vertices on the perimeter of the selection"),
    ('EDGE_PERIMETER', "To Edge Perimeter", "The edges on the perimeter of the selection"),
    ('FACE_PERIMETER', "To Face Perimeter", "The faces on the perimeter of the selection"),
    ('FACE_PATH', "To Face Path", "The faces along the edge rings of the selected edges"),
    ('SHELL_BORDER', "To Shell Border", "The border components of the shells whose border is selected"),
    ('UV_SHELL_BORDER', "To UV Shell Border", "The border components of the UV shells of the selection"),
    ('UVS', "To UVs", "The UVs of the selection (UV Editor, UV Sync Selection off)"),
    ('UV_PERIMETER', "To UV Perimeter", "The UVs on the perimeter of the selection (UV Editor)"),
    ('UV_EDGE_LOOP', "To UV Edge Loop", "The edge loops of the selected edges, up to a UV seam"),
)
# kinds whose result is a UV selection
UV_TARGET = {'UVS', 'UV_PERIMETER'}


# --- reading the selection ---------------------------------------------------------------------------

def mode_kind(select_mode):
    sv, se, sf = select_mode
    return 'FACE' if sf and not (sv or se) else 'EDGE' if se and not sv else 'VERT'


def selection(bm, select_mode, uv=None):
    """(kind, elements): the Maya selection. ``uv`` = the UV layer when UV Sync Selection is off (UV component):
    the selected UVs' vertices, kind 'VERT'."""
    if uv is not None:
        return 'VERT', {lp.vert for f in bm.faces if f.select and not f.hide for lp in f.loops
                        if compat.uv_vert_selected(lp, uv)}
    kind = mode_kind(select_mode)
    seq = {'VERT': bm.verts, 'EDGE': bm.edges, 'FACE': bm.faces}[kind]
    return kind, {x for x in seq if x.select and not x.hide}


def verts_of(kind, elems):
    if kind == 'VERT':
        return set(elems)
    return {v for x in elems for v in x.verts}


# --- loops and rings ---------------------------------------------------------------------------------

def loop_next(e, v):
    """The edge continuing ``e``'s edge loop through ``v``, or None: through an inner vertex with four edges the
    edge sharing no face with ``e``; along an open border through a border vertex with three edges the other border
    edge (Maya / Blender edge loops)."""
    faces = set(e.link_faces)
    others = [x for x in v.link_edges if x is not e]
    if len(v.link_edges) == 4 and not v.is_boundary:
        cand = [x for x in others if not faces & set(x.link_faces)]
        return cand[0] if len(cand) == 1 else None
    if e.is_boundary and len(v.link_edges) == 3:
        cand = [x for x in others if x.is_boundary]
        return cand[0] if len(cand) == 1 else None
    return None


def opposite_edge(f, e):
    """The edge across quad ``f`` from ``e`` (shares no vertex with it), or None."""
    if len(f.edges) != 4:
        return None
    a, b = e.verts
    for x in f.edges:
        if a not in x.verts and b not in x.verts:
            return x
    return None


def across(f, e):
    """The face on the other side of ``e`` from ``f`` (manifold edges), or None."""
    if e is None:
        return None
    other = [g for g in e.link_faces if g is not f]
    return other[0] if len(other) == 1 else None


def edge_ring(e):
    """``e``'s edge ring: across every quad on both sides until a non-quad, an open border or the start again."""
    ring = {e}
    for f0 in e.link_faces:
        cur, f = e, f0
        while f is not None:
            nxt = opposite_edge(f, cur)
            if nxt is None or nxt in ring:
                break
            ring.add(nxt)
            cur, f = nxt, across(f, nxt)
    return ring


# --- grow / shrink along loop ---------------------------------------------------------------------------

def _face_neighbours(f):
    return [(e, g) for e in f.edges for g in e.link_faces if g is not f and not g.hide]


def grow_loop(kind, elems):
    sel = set(elems)
    out = set(sel)
    if kind == 'FACE':
        for f in sel:
            nb = [(e, g) for e, g in _face_neighbours(f) if g in sel]
            if not nb:
                out.update(g for _e, g in _face_neighbours(f))
                continue
            for e, _g in nb:
                g = across(f, opposite_edge(f, e))
                if g is not None and not g.hide:
                    out.add(g)
        return out
    if kind == 'EDGE':
        for e in sel:
            for v in e.verts:
                n = loop_next(e, v)
                if n is not None and not n.hide:
                    out.add(n)
        return out
    inner = {e for v in sel for e in v.link_edges if e.other_vert(v) in sel}
    for e in grow_loop('EDGE', inner):
        out.update(e.verts)
    for v in sel:
        if not any(e in inner for e in v.link_edges):       # an isolated vertex grows to all its neighbours
            out.update(e.other_vert(v) for e in v.link_edges if not e.hide)
    return out


def shrink_loop(kind, elems):
    sel = set(elems)
    if kind == 'FACE':
        out = set()
        for f in sel:
            nb = [g for _e, g in _face_neighbours(f) if g in sel]
            if not nb:
                continue
            end = False
            for e in f.edges:
                o = opposite_edge(f, e)
                if o is None:
                    end = across(f, e) not in sel
                else:
                    end = (across(f, e) in sel) != (across(f, o) in sel)
                if end:
                    break
            if not end:
                out.add(f)
        return out
    if kind == 'EDGE':
        return {e for e in sel if all(loop_next(e, v) in sel for v in e.verts)}
    inner = {e for v in sel for e in v.link_edges if e.other_vert(v) in sel}
    return {v for e in shrink_loop('EDGE', inner) for v in e.verts}


# --- perimeters -------------------------------------------------------------------------------------

def contained_faces(bm, kind, elems):
    if kind == 'EDGE':
        return {f for f in bm.faces if not f.hide and all(e in elems for e in f.edges)}
    vs = verts_of(kind, elems)
    return {f for f in bm.faces if not f.hide and all(v in vs for v in f.verts)}


def region(bm, kind, elems):
    """The face region a perimeter is taken from: the faces, else the contained faces, else the touched faces."""
    if kind == 'FACE':
        return set(elems)
    inside = contained_faces(bm, kind, elems)
    if inside:
        return inside
    if kind == 'EDGE':
        return {f for e in elems for f in e.link_faces if not f.hide}
    return {f for v in elems for f in v.link_faces if not f.hide}


def perimeter_edges(faces):
    return {e for f in faces for e in f.edges if sum(1 for g in e.link_faces if g in faces) == 1}


def perimeter_verts(faces):
    return {v for e in perimeter_edges(faces) for v in e.verts}


def perimeter_faces(faces):
    edges = perimeter_edges(faces)
    return {f for f in faces if any(e in edges for e in f.edges)}


# --- face path / shells -------------------------------------------------------------------------------

def face_path(kind, elems):
    edges = touching_edges(kind, elems)
    ring = set()
    for e in edges:
        if e not in ring:
            ring |= edge_ring(e)
    return {f for e in ring for f in e.link_faces if not f.hide}


def touching_edges(kind, elems):
    if kind == 'EDGE':
        return set(elems)
    if kind == 'FACE':
        return {e for f in elems for e in f.edges}
    return {e for v in elems for e in v.link_edges}


def on_border(kind, x):
    if kind == 'VERT':
        return x.is_boundary
    if kind == 'EDGE':
        return x.is_boundary
    return any(e.is_boundary for e in x.edges)


def shell_faces(seed_faces):
    """Faces connected to ``seed_faces`` through edges (a mesh shell)."""
    seen = set(seed_faces)
    stack = list(seed_faces)
    while stack:
        f = stack.pop()
        for e in f.edges:
            for g in e.link_faces:
                if g not in seen and not g.hide:
                    seen.add(g)
                    stack.append(g)
    return seen


def faces_touching(kind, elems):
    if kind == 'FACE':
        return set(elems)
    return {f for v in verts_of(kind, elems) for f in v.link_faces if not f.hide}


def border_components(kind, faces):
    if kind == 'FACE':
        return {f for f in faces if on_border('FACE', f)}
    edges = {e for f in faces for e in f.edges if e.is_boundary}
    return edges if kind == 'EDGE' else {v for e in edges for v in e.verts}


def shell_border(kind, elems):
    seeds = [x for x in elems if on_border(kind, x)]
    if not seeds:
        return set()
    return border_components(kind, shell_faces(faces_touching(kind, seeds)))


def uv_shell_border(kind, elems):
    """Maya To UV Shell Border on vertices / edges / faces: the open-border components of the shells the selection
    touches. On a cube without its top face the result also has the border face of the other UV piece, so
    the grouping is the mesh shell (the UV shell only counts for UVs, ``uv_border_loops``)."""
    if not elems:
        return set()
    return border_components(kind, shell_faces(faces_touching(kind, elems)))


# --- UV edge loop ------------------------------------------------------------------------------------

def _uv_points(v, uv):
    pts = []
    for lp in v.link_loops:
        if lp.face.hide:
            continue
        p = lp[uv].uv
        if not any(uv_tools._same(p, q) for q in pts):
            pts.append(p.copy())
    return pts


def uv_seam(e, uv):
    """An open edge, or one whose two faces don't share both UVs."""
    if len(e.link_faces) != 2:
        return True
    a, b = e.link_faces
    return not all(uv_tools._same(uv_tools._uv_at(a, v, uv), uv_tools._uv_at(b, v, uv)) for v in e.verts)


def uv_edge_loop(edges, uv):
    """Each edge's loop, walked while it stays inside one UV piece (through vertices with one UV); an edge on a UV
    seam walks the seam instead (Maya "UV edge loop or border")."""
    out = set()
    for e0 in edges:
        out.add(e0)
        seam = uv_seam(e0, uv)
        for v0 in e0.verts:
            e, v = e0, v0
            while True:
                if seam:        # along the seam (a cube's corners end it: three edges)
                    n = loop_next(e, v)
                    if n is not None and not uv_seam(n, uv):
                        n = None
                else:
                    n = loop_next(e, v) if len(_uv_points(v, uv)) == 1 else None
                    if n is not None and uv_seam(n, uv):
                        n = None
                if n is None or n in out or n.hide:
                    break
                out.add(n)
                e, v = n, n.other_vert(v)
    return out


# --- UVs -------------------------------------------------------------------------------------------------

def _key(lp, uv):
    return lp.vert, round(lp[uv].uv.x, 5), round(lp[uv].uv.y, 5)


def uv_loops(kind, elems, uv):
    """The face corners (Blender loops) Maya's To UVs selects: a face's own UVs, an edge's UVs in the faces
    beside it, every UV of a vertex; a UV = every corner sharing its vertex and position."""
    if kind == 'FACE':
        keys = {_key(lp, uv) for f in elems for lp in f.loops}
    elif kind == 'EDGE':
        keys = {_key(lp, uv) for e in elems for f in e.link_faces for lp in f.loops if lp.vert in e.verts}
    else:
        return {lp for v in elems for lp in v.link_loops}
    return {lp for v in {k[0] for k in keys} for lp in v.link_loops if _key(lp, uv) in keys}


def convert(bm, kind_in, elems, what, uv=None):
    """(target kind, elements) or None (keep the selection). Targets: 'VERT' / 'EDGE' / 'FACE' / 'LOOP' (UVs)."""
    if what == 'GROW_LOOP':
        return kind_in, grow_loop(kind_in, elems)
    if what == 'SHRINK_LOOP':
        return kind_in, shrink_loop(kind_in, elems)
    if what == 'VERTEX_PERIMETER':
        return 'VERT', perimeter_verts(region(bm, kind_in, elems))
    if what == 'EDGE_PERIMETER':
        return 'EDGE', perimeter_edges(region(bm, kind_in, elems))
    if what == 'FACE_PERIMETER':
        faces = set(elems) if kind_in == 'FACE' else contained_faces(bm, kind_in, elems)
        return ('FACE', perimeter_faces(faces)) if faces else None
    if what == 'FACE_PATH':
        return 'FACE', face_path(kind_in, elems)
    if what == 'SHELL_BORDER':
        return kind_in, shell_border(kind_in, elems)
    if what == 'UV_SHELL_BORDER':
        return kind_in, uv_shell_border(kind_in, elems)
    if what == 'UVS':
        return 'LOOP', uv_loops(kind_in, elems, uv)
    if what == 'UV_PERIMETER':
        return 'LOOP', uv_loops('VERT', perimeter_verts(region(bm, kind_in, elems)), uv)
    if what == 'UV_EDGE_LOOP':
        return 'EDGE', uv_edge_loop(touching_edges(kind_in, elems), uv)
    raise ValueError(what)


def uv_border_loops(bm, uv, loops):
    """With sync off, Maya's To UV Shell Border on UVs: every UV on the border of the UV shells of ``loops``."""
    shown = [f for f in bm.faces if f.select and not f.hide]
    touched = {lp.face for lp in loops}
    out = set()
    for island in uv_tools.islands(bm, uv, shown):
        if not touched & set(island):
            continue
        inside = set(island)
        for f in island:
            for lp in f.loops:
                e = lp.edge
                share = [g for g in e.link_faces if g is not f and g in inside and all(
                    uv_tools._same(uv_tools._uv_at(f, v, uv), uv_tools._uv_at(g, v, uv)) for v in e.verts)]
                if not share:
                    out.add(lp)
                    out.add(lp.link_loop_next)
    return out


def uv_source(context, bm, uv):
    """Is the selection UVs (the kit's Maya UV component)? Sync off is also Blender's factory state, so
    only in the UV Editor, or in the 3D View when every shown face is selected (how uv_tools.set_component shows
    the UVs) and some but not all UVs are."""
    if uv is None or context.scene.tool_settings.use_uv_select_sync:
        return False
    space = getattr(context, "space_data", None)
    if space is not None and space.type == 'IMAGE_EDITOR':
        return True
    shown = [f for f in bm.faces if not f.hide]
    if not shown or not all(f.select for f in shown):
        return False
    flags = [compat.uv_vert_selected(lp, uv) for f in shown for lp in f.loops]
    return any(flags) and not all(flags)


# --- applying ------------------------------------------------------------------------------------------

def select_loops(bm, uv, loops):
    """UV selection = ``loops`` (vertices; edges whose both corners are in), on the shown faces."""
    for f in bm.faces:
        for lp in f.loops:
            compat.set_uv_vert_selected(lp, uv, lp in loops)
    for f in bm.faces:
        for lp in f.loops:
            compat.set_uv_edge_selected(lp, uv, lp in loops and lp.link_loop_next in loops)


class ALLSET_OT_select_convert(bpy.types.Operator):
    """Maya Select menu conversion (Grow / Shrink Along Loop, perimeters, face path, shell borders, UVs)"""
    bl_idname = "allset.select_convert"
    bl_label = "Convert Selection"
    bl_options = {'REGISTER', 'UNDO'}

    kind: EnumProperty(name="To", items=KINDS, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    @classmethod
    def description(cls, context, props):
        return next(d for k, _l, d in KINDS if k == props.kind)

    def execute(self, context):
        ts = context.scene.tool_settings
        mode = tuple(ts.mesh_select_mode)
        results = []
        from_uvs = False
        for ob in context.objects_in_mode_unique_data:
            if ob.type != 'MESH':
                continue
            bm = bmesh.from_edit_mesh(ob.data)
            uv = bm.loops.layers.uv.active
            if uv is None and (self.kind in UV_TARGET or self.kind.startswith('UV_')):
                continue
            uv_mode = uv_source(context, bm, uv)
            from_uvs = from_uvs or uv_mode
            kind_in, elems = selection(bm, mode, uv if uv_mode else None)
            if uv_mode and self.kind == 'UV_SHELL_BORDER':
                loops = {lp for f in bm.faces if f.select and not f.hide for lp in f.loops
                         if compat.uv_vert_selected(lp, uv)}
                results.append((ob, bm, uv, ('LOOP', uv_border_loops(bm, uv, loops))))
                continue
            res = convert(bm, kind_in, elems, self.kind, uv)
            if res is not None and uv_mode and self.kind in ('GROW_LOOP', 'SHRINK_LOOP'):
                res = ('LOOP', uv_loops('VERT', res[1], uv))      # UVs grow / shrink with their vertices
            results.append((ob, bm, uv, res))
        if not results:
            self.report({'WARNING'}, "Select a mesh with UVs" if self.kind in UV_TARGET else "Select a mesh")
            return {'CANCELLED'}
        if any(r[3] is not None and r[3][0] == 'LOOP' for r in results):
            # a UV selection: Maya's UV component = sync off, every face shown (uv_tools.set_component)
            uv_tools.forget_mesh_selection()      # a conversion: no F12 selection to bring back (#80)
            uv_tools.set_component(context, 'UV')
            ts.uv_select_mode = 'VERTEX'
            for ob, bm, uv, res in results:
                if res is not None:
                    select_loops(bm, uv, res[1])
                bmesh.update_edit_mesh(ob.data)
            if uv_tools.find_uv_editor(context)[1] is None and context.window is not None and not bpy.app.background:
                bpy.ops.allset.open_editor(ui_type='UV')
            return {'FINISHED'}
        targets = {r[3][0] for r in results if r[3] is not None}
        if from_uvs and targets:
            ts.use_uv_select_sync = True
        if len(targets) == 1:
            ts.mesh_select_mode = _MODES[targets.pop()]
        for ob, bm, _uv, res in results:
            if res is not None:
                select_only(bm, res[0], res[1])
            bmesh.update_edit_mesh(ob.data)
        return {'FINISHED'}


classes = (ALLSET_OT_select_convert,)
