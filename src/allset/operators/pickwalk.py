# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya arrow-key pick-walk (object mode).

Maya arrow keys: Up = parent, Down = child,
Left/Right = sibling (Maya-style hotkeys). Siblings are in Maya's
creation order (a re-parented node last; the kit's ``outliner_order.ORDER`` numbers) and wrap around —
locators made b, a, c walk b -> a -> c -> b, Down = the first made.
Edit mode:
component pick-walk at the end of this file.
"""

import bpy

from .. import undo_steps

DIRECTIONS = (
    ("UP", "Up", "Select the parent"),
    ("DOWN", "Down", "Select the first child"),
    ("LEFT", "Left", "Select the previous sibling"),
    ("RIGHT", "Right", "Select the next sibling"),
)


def _in_layer(view_layer, objs):
    from ..ui.outliner_order import ORDER
    names = view_layer.objects
    link = {o.name: i for i, o in enumerate(view_layer.objects) if o is not None}   # link order = creation order
    return sorted((o for o in objs if o.name in names),
                  key=lambda o: (o.get(ORDER, 10 ** 9 + link.get(o.name, 0)), link.get(o.name, 0)))


def siblings(view_layer, ob):
    if ob.parent is not None:
        return _in_layer(view_layer, ob.parent.children)
    return _in_layer(view_layer, (o for o in view_layer.objects if o.parent is None))


def walk(view_layer, ob, direction):
    """Object reached from ``ob`` (``ob`` itself when there is nowhere to go)."""
    if direction == "UP":
        return ob.parent if ob.parent is not None and ob.parent.name in view_layer.objects else ob
    if direction == "DOWN":
        kids = _in_layer(view_layer, ob.children)
        return kids[0] if kids else ob
    sibs = siblings(view_layer, ob)
    if len(sibs) < 2:
        return ob
    i = sibs.index(ob)
    return sibs[(i + (1 if direction == "RIGHT" else -1)) % len(sibs)]


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_pick_walk(bpy.types.Operator):
    """Walk the selection through the hierarchy (Maya arrow keys)"""
    bl_idname = "allset.pick_walk"
    bl_label = "Pick Walk"
    bl_options = {'REGISTER', 'UNDO'}

    direction: bpy.props.EnumProperty(items=DIRECTIONS, name="Direction")

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects)

    def execute(self, context):
        vl = context.view_layer
        active = vl.objects.active
        targets = []
        for ob in context.selected_objects:
            t = walk(vl, ob, self.direction)
            if t not in targets:
                targets.append(t)
        for ob in context.selected_objects:
            ob.select_set(False)
        for t in targets:
            t.select_set(True)
        if active is not None:
            vl.objects.active = walk(vl, active, self.direction)
        return {'FINISHED'}




# --- component pick-walk ----------------------------------------------------
# Maya pick-walk: edges walk the edge ring (Up/Down)
# and the edge loop (Left/Right); faces/vertices (Maya: face loop / index order) walk to the
# neighbour whose screen direction is closest to the arrow.

SCREEN_DIR = {"UP": (0.0, 1.0), "DOWN": (0.0, -1.0), "LEFT": (-1.0, 0.0), "RIGHT": (1.0, 0.0)}
MIN_ALIGN = 0.3   # vertices / faces: no neighbour within ~72 degrees of the arrow = stay


def centre(elem):
    import bmesh
    if isinstance(elem, bmesh.types.BMVert):
        return elem.co.copy()
    if isinstance(elem, bmesh.types.BMEdge):
        return (elem.verts[0].co + elem.verts[1].co) / 2
    return elem.calc_center_median()


def edge_loop_next(edge):
    """Edges continuing ``edge``'s loop at either end: the edge at the vertex that shares no
    face with ``edge`` (only where that is unambiguous, i.e. a 4-edge vertex)."""
    faces = set(edge.link_faces)
    out = []
    for v in edge.verts:
        if len(v.link_edges) != 4:
            continue
        cand = [e for e in v.link_edges if e is not edge and not (set(e.link_faces) & faces)]
        if len(cand) == 1:
            out.append(cand[0])
    return out


def edge_ring_next(edge):
    """The opposite edge of each quad beside ``edge``."""
    out = []
    verts = set(edge.verts)
    for f in edge.link_faces:
        if len(f.edges) == 4:
            out.extend(e for e in f.edges if not (set(e.verts) & verts))
    return out


def neighbours(elem, direction):
    import bmesh
    if isinstance(elem, bmesh.types.BMEdge):
        return edge_loop_next(elem) if direction in ("LEFT", "RIGHT") else edge_ring_next(elem)
    if isinstance(elem, bmesh.types.BMVert):
        return [e.other_vert(elem) for e in elem.link_edges]
    return [f for e in elem.edges for f in e.link_faces if f is not elem]


def step_component(elem, direction, project):
    """The element an arrow key walks to from ``elem`` (``elem`` when there is none).

    ``project``: world point -> screen (x, y)."""
    import bmesh
    cands = neighbours(elem, direction)
    if not cands:
        return elem
    dx, dy = SCREEN_DIR[direction]
    x0, y0 = project(centre(elem))
    best, best_score = None, -2.0
    for c in cands:
        x, y = project(centre(c))
        vx, vy = x - x0, y - y0
        n = (vx * vx + vy * vy) ** 0.5
        if n < 1e-9:
            continue
        score = (vx * dx + vy * dy) / n
        if score > best_score:
            best, best_score = c, score
    if best is None:
        return elem
    # Edges follow their loop / ring (Maya) unless the only way on points against the arrow (a
    # border); vertices and faces go only roughly in the arrow's direction.
    limit = -MIN_ALIGN if isinstance(elem, bmesh.types.BMEdge) else MIN_ALIGN
    if best_score < limit:
        return elem
    return best


def component_kind(bm):
    mode = bm.select_mode
    return 'FACE' if 'FACE' in mode else 'EDGE' if 'EDGE' in mode else 'VERT'


def walk_components(bm, direction, project):
    """Walk every selected element of the current select mode; returns the new selection."""
    kind = component_kind(bm)
    seq = {'VERT': bm.verts, 'EDGE': bm.edges, 'FACE': bm.faces}[kind]
    selected = [e for e in seq if e.select]
    if not selected:
        return []
    active = bm.select_history.active
    targets = []
    for e in selected:
        t = step_component(e, direction, project)
        if t not in targets:
            targets.append(t)
    new_active = step_component(active, direction, project) if active in selected else targets[0]
    for e in list(bm.verts) + list(bm.edges) + list(bm.faces):
        e.select = False
    for t in targets:
        t.select_set(True)
    bm.select_history.clear()
    bm.select_history.add(new_active)
    bm.select_flush_mode()
    return targets


def view_projector(context, ob):
    """World point (object space ``ob``) -> screen-ish (x, y) of this 3D View; front view
    (x, z) without one (headless)."""
    rv3d = context.region_data
    if rv3d is None and context.space_data is not None and context.space_data.type == 'VIEW_3D':
        rv3d = context.space_data.region_3d
    mw = ob.matrix_world
    if rv3d is None:
        return lambda p: ((mw @ p).x, (mw @ p).z)
    pm = rv3d.perspective_matrix

    def project(p):
        v = pm @ (mw @ p).to_4d()
        w = v.w if abs(v.w) > 1e-9 else 1e-9
        return v.x / w, v.y / w
    return project


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_pick_walk_component(bpy.types.Operator):
    """Walk the component selection to the next vertex / edge / face (Maya arrow keys)"""
    bl_idname = "allset.pick_walk_component"
    bl_label = "Pick Walk Components"
    bl_options = {'REGISTER', 'UNDO'}

    direction: bpy.props.EnumProperty(items=DIRECTIONS, name="Direction")

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        import bmesh
        moved = 0
        for ob in context.objects_in_mode_unique_data:
            if ob.type != 'MESH':
                continue
            bm = bmesh.from_edit_mesh(ob.data)
            moved += len(walk_components(bm, self.direction, view_projector(context, ob)))
            bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
        return {'FINISHED'} if moved else {'CANCELLED'}


classes = (ALLSET_OT_pick_walk, ALLSET_OT_pick_walk_component)
