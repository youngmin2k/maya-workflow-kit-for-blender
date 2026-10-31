# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya's double-click component selection (issue #22; Maya 2026 rules, #222).

Maya 2026 polygon selection: double-click an edge = its edge loop; double-click a vertex or a face = every
vertex / face of its shell (the connected piece of the mesh). Select a component, then Shift+double-click a
second one on the same loop = the run of components between the two (both kept); for two neighbouring faces
that run is the whole face loop through both. A second component on no common loop gets its whole loop added.

Blender has the loop pick (``mesh.loop_select``: nearest edge decides the direction in every select mode) and
the linked pick (``mesh.select_linked_pick``) but no "between two picks on the loop" — ``mesh.shortest_path_select``
takes any shortest path — so the run is walked here in bmesh: an edge loop continues through a 4-valence vertex
on the edge that shares no face with the current one, a face loop crosses a quad to its opposite edge.

Keymap: "Mesh" LEFTMOUSE DOUBLE_CLICK (Shift = between). A double-click is first offered to every keymap as
DOUBLE_CLICK and re-sent as PRESS only when nothing took it, so the select tool's own press items keep
working; the first click of the pair has already selected (Shift: toggled on) the component under the mouse,
which makes it the last one in the select history.
"""

import bmesh
import bpy
from bpy.props import BoolProperty

from .. import undo_steps


def _continue_edge(edge, vert):
    """The edge after ``edge`` on its loop through ``vert`` (None at a pole / border)."""
    if len(vert.link_edges) != 4:
        return None
    faces = set(edge.link_faces)
    for other in vert.link_edges:
        if other is not edge and not (set(other.link_faces) & faces):
            return other
    return None


def _shortest(paths):
    paths = [p for p in paths if p]
    return min(paths, key=len) if paths else None


def edge_run(a, b):
    """Edges from ``a`` to ``b`` along their common edge loop (both included), or None."""
    if a is b:
        return [a]
    found = []
    for start in a.verts:
        path, cur, at = [a], a, start
        while True:
            nxt = _continue_edge(cur, at)
            if nxt is None or nxt is a:
                break
            path.append(nxt)
            if nxt is b:
                found.append(path)
                break
            at = nxt.other_vert(at)
            cur = nxt
    return _shortest(found)


def vert_run(a, b):
    """(vertices, edges) from ``a`` to ``b`` along an edge loop through both, or None."""
    if a is b:
        return [a], []
    found = []
    for first in a.link_edges:
        verts, edges, cur, at = [a], [first], first, a
        while True:
            nv = cur.other_vert(at)
            verts.append(nv)
            if nv is b:
                found.append((verts, edges))
                break
            nxt = _continue_edge(cur, nv)
            if nxt is None or nxt is first:
                break
            edges.append(nxt)
            at, cur = nv, nxt
    return min(found, key=lambda p: len(p[0])) if found else None


def face_run(a, b):
    """Faces from ``a`` to ``b`` along their common face loop (both included), or None."""
    if a is b:
        return [a]
    if len(a.verts) != 4:
        return None
    found = []
    for across in a.edges:
        path, cur = [a], a
        while True:
            others = [f for f in across.link_faces if f is not cur]
            if not others or others[0] is a:
                break
            nf = others[0]
            path.append(nf)
            if nf is b:
                found.append(path)
                break
            if len(nf.verts) != 4:
                break
            shared = set(across.verts)
            across = next((e for e in nf.edges if not (set(e.verts) & shared)), None)
            if across is None:
                break
            cur = nf
    return _shortest(found)


def face_loop(a, b):
    """The whole face loop through the neighbouring faces ``a`` and ``b`` (across their shared edge), or None."""
    shared = next((e for e in a.edges if b in e.link_faces), None)
    if shared is None:
        return None
    loop = [a]
    for start, across in ((a, shared), (b, None)):
        cur = start
        if across is None:          # walk on from b, away from a
            loop.append(b)
            if len(b.verts) != 4:
                continue
            gone = set(shared.verts)
            across = next((e for e in b.edges if not (set(e.verts) & gone)), None)
            cur = b
        else:                       # walk on from a, away from b
            if len(a.verts) != 4:
                continue
            gone = set(shared.verts)
            across = next((e for e in a.edges if not (set(e.verts) & gone)), None)
        while across is not None:
            others = [f for f in across.link_faces if f is not cur]
            if len(others) != 1 or others[0] in loop:
                break
            nf = others[0]
            loop.append(nf)
            if len(nf.verts) != 4:
                break
            gone = set(across.verts)
            across = next((e for e in nf.edges if not (set(e.verts) & gone)), None)
            cur = nf
    return loop


def select_run(bm):
    """Select the run between the last two components of the select history; count selected, or 0 when they
    are on no common loop (or the history has no such pair)."""
    hist = [h for h in bm.select_history]
    if len(hist) < 2:
        return 0
    a, b = hist[-2], hist[-1]
    if type(a) is not type(b) or not b.select:
        return 0
    if isinstance(a, bmesh.types.BMEdge):
        run = edge_run(a, b)
        elems = run or []
    elif isinstance(a, bmesh.types.BMVert):
        run = vert_run(a, b)
        elems = (run[0] + run[1]) if run else []
    else:
        run = face_run(a, b)
        if run is not None and len(run) == 2:     # neighbours: Maya takes the whole face loop through both
            run = face_loop(a, b)
        elems = run or []
    if not run:
        return 0
    for el in elems:
        el.select_set(True)
    bm.select_history.add(b)     # the second pick stays the active component
    return len(elems)


def shell_mode(select_mode):
    """True when a plain double-click picks the shell: vertex or face select mode without edges."""
    vert, edge, face = select_mode
    return (vert or face) and not edge


def loop_select_args(extend):
    """Keywords for ``mesh.loop_select``: only ones every supported Blender has. 5.1+ dropped ``ring`` (ring pick is
    ``mesh.edgering_select`` there; issue #84: "keyword "ring" unrecognized" on 5.2), and 4.5's default is False."""
    return {"extend": extend, "deselect": False, "toggle": False}


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_loop_pick(bpy.types.Operator):
    """Maya double-click: an edge selects its loop, a vertex or face its shell; Shift: the components between the
    last pick and this one along their loop"""
    bl_idname = "allset.loop_pick"
    bl_label = "Select Loop (Maya Double-Click)"
    bl_options = {'REGISTER', 'UNDO'}

    between: BoolProperty(name="Between", options={'SKIP_SAVE'},
                          description="Select the components between the last two picks along their loop")

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def _between(self, context):
        n = 0
        for ob in context.objects_in_mode_unique_data:
            if ob.type != 'MESH':
                continue
            bm = bmesh.from_edit_mesh(ob.data)
            got = select_run(bm)
            if got:
                bm.select_flush_mode()
                bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
                n += got
        return n

    def execute(self, context):
        return {'FINISHED'} if self.between and self._between(context) else {'CANCELLED'}

    def invoke(self, context, event):
        if self.between and self._between(context):
            return {'FINISHED'}
        # plain double-click on a vertex / face: its shell (Maya 2026); on an edge, or a second pick on no common
        # loop: Blender's loop pick at the mouse (Shift adds the loop to the selection)
        try:
            if not self.between and shell_mode(context.tool_settings.mesh_select_mode):
                return bpy.ops.mesh.select_linked_pick('INVOKE_DEFAULT', deselect=False, delimit=set())
            return bpy.ops.mesh.loop_select('INVOKE_DEFAULT', **loop_select_args(self.between))
        except RuntimeError:
            return {'PASS_THROUGH'}


classes = (ALLSET_OT_loop_pick,)
