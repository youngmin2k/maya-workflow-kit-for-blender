# SPDX-License-Identifier: GPL-3.0-or-later
"""Marking-menu items that had no Blender action (#74 #62).

- RMB list (RMB_MESH): Select Hierarchy (selects the object the menu was opened
  on and everything below it), items run on the object the menu was opened on (Make Live, Actions ▸ Template /
  Untemplate / Unparent / Bounding Box), UV Sets ▸ and Color Sets ▸ as Blender menus listing the mesh's UV maps /
  color attributes.
- Ctrl+RMB (CTRL_CONVERT) "convert, then act" items and Shift+RMB Face Normals ▸ Reverse Propagate
  (SHIFT_FACE: the selected faces' normals reversed, the rest of their shells following): ``allset.mm_poly``; the
  Maya runTimeCommands: PolyConvertToLoopAndDelete = SelectEdgeLoop;
  DeleteEdge, ….
- Select options (OPT_SELECT): Camera-Based Selection = the kit's "marquee selects hidden
  components" preference turned the other way.

The object the RMB menu was opened on is ``WindowManager.allset_mm_target`` (set in object mode), else the active
object.
"""

import bmesh
import bpy
from bpy.props import EnumProperty, StringProperty

from .. import results
from ..ui import menu_map


def target(context):
    """The RMB menu's object: the one under the mouse when it opened, else the active object."""
    name = getattr(context.window_manager, "allset_mm_target", "")
    ob = bpy.data.objects.get(name) if name else None
    return ob or context.active_object


def _select_only(context, obs, active):
    for ob in list(context.selected_objects):
        ob.select_set(False)
    for ob in obs:
        try:
            ob.select_set(True)
        except RuntimeError:      # not in the view layer
            pass
    context.view_layer.objects.active = active


# --- RMB list: object items -------------------------------------------------------------------

class ALLSET_OT_mm_object_item(bpy.types.Operator):
    """Run this Maya menu item on the object the marking menu was opened on, like Maya"""
    bl_idname = "allset.mm_object_item"
    bl_label = "Marking Menu Object Item"
    bl_options = {'INTERNAL'}

    item: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return target(context) is not None

    def execute(self, context):
        ob = target(context)
        if ob is None or self.item not in menu_map.MAP:
            return {'CANCELLED'}
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        before = [o.name for o in context.selected_objects]
        active = context.view_layer.objects.active
        _select_only(context, [ob], ob)
        res = bpy.ops.allset.menu_item(item=self.item)
        # The selection comes back (Maya's command only got the object's name); a templated object stays unselected.
        keep = [o for o in (bpy.data.objects.get(n) for n in before) if o is not None and not o.hide_select]
        _select_only(context, keep, active if active is not None and active.name in bpy.data.objects else ob)
        return res


class ALLSET_OT_mm_select_hierarchy(bpy.types.Operator):
    """Select the object and everything under it (Maya: select -hierarchy)"""
    bl_idname = "allset.mm_select_hierarchy"
    bl_label = "Select Hierarchy"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return target(context) is not None

    def execute(self, context):
        ob = target(context)
        if ob is None:
            return {'CANCELLED'}
        if context.mode != 'OBJECT':      # from component mode: back to objects first
            bpy.ops.object.mode_set(mode='OBJECT')
        _select_only(context, [ob, *ob.children_recursive], ob)
        return {'FINISHED'}


BBOX_OWN = "allset_bbox_own"


class ALLSET_OT_mm_bounding_box(bpy.types.Operator):
    """Toggle bounding-box display of the object (Maya: Actions > Bounding Box)"""
    bl_idname = "allset.mm_bounding_box"
    bl_label = "Bounding Box"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return target(context) is not None

    def execute(self, context):
        ob = target(context)
        if ob is None:
            return {'CANCELLED'}
        if ob.display_type == 'BOUNDS':
            ob.display_type = ob.get(BBOX_OWN) or 'TEXTURED'
            if BBOX_OWN in ob:
                del ob[BBOX_OWN]
        else:
            ob[BBOX_OWN] = ob.display_type
            ob.display_type = 'BOUNDS'
        return {'FINISHED'}


# --- UV Sets / Color Sets ---------------------------------------------------------------------

def _mesh(context):
    ob = target(context)
    return ob.data if ob is not None and ob.type == 'MESH' else None


class ALLSET_OT_mm_uv_set(bpy.types.Operator):
    """Make this UV set the current one (Maya: polyUVSet -currentUVSet)"""
    bl_idname = "allset.mm_uv_set"
    bl_label = "Current UV Set"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    name: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        me = _mesh(context)
        layer = me.uv_layers.get(self.name) if me is not None else None
        if layer is None:
            return {'CANCELLED'}
        me.uv_layers.active = layer
        return {'FINISHED'}


class ALLSET_OT_mm_color_set(bpy.types.Operator):
    """Make this color set the current one (Maya: polyColorSet -currentColorSet)"""
    bl_idname = "allset.mm_color_set"
    bl_label = "Current Color Set"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    name: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        me = _mesh(context)
        if me is None:
            return {'CANCELLED'}
        names = [a.name for a in me.color_attributes]
        if self.name not in names:
            return {'CANCELLED'}
        me.color_attributes.active_color_index = names.index(self.name)
        return {'FINISHED'}


class ALLSET_MT_uv_sets_rmb(bpy.types.Menu):
    """Maya RMB > UV Sets: the UV Set Editor and the mesh's UV sets (the checked one is current)"""
    bl_idname = "ALLSET_MT_uv_sets_rmb"
    bl_label = "UV Sets"

    def draw(self, context):
        layout = self.layout
        layout.operator("allset.menu_item", text="UV Set Editor").item = "UV/UV Set Editor"
        me = _mesh(context)
        if me is None or not me.uv_layers:
            return
        layout.separator()
        active = me.uv_layers.active
        for layer in me.uv_layers:
            on = active is not None and layer.name == active.name
            layout.operator(ALLSET_OT_mm_uv_set.bl_idname, text=layer.name,
                            icon='CHECKBOX_HLT' if on else 'CHECKBOX_DEHLT').name = layer.name


class ALLSET_MT_color_sets_rmb(bpy.types.Menu):
    """Maya RMB > Color Sets: the Color Set Editor and the mesh's color sets (the checked one is current)"""
    bl_idname = "ALLSET_MT_color_sets_rmb"
    bl_label = "Color Sets"

    def draw(self, context):
        layout = self.layout
        layout.operator("allset.menu_item", text="Color Set Editor").item = "Mesh Display/Color Set Editor"
        me = _mesh(context)
        if me is None or not len(me.color_attributes):
            return
        layout.separator()
        current = me.color_attributes.active_color_index
        for i, attr in enumerate(me.color_attributes):
            layout.operator(ALLSET_OT_mm_color_set.bl_idname, text=attr.name,
                            icon='CHECKBOX_HLT' if i == current else 'CHECKBOX_DEHLT').name = attr.name


# --- Ctrl+RMB convert-and-act, Reverse Propagate ----------------------------------------------

POLY_KINDS = (
    ('LOOP_DELETE', "To Edge Loop and Delete", "SelectEdgeLoop; DeleteEdge"),
    ('LOOP_DUPLICATE', "To Edge Loop and Duplicate", "SelectEdgeLoop; polyDuplicateEdge (Blender: Offset Edge Loop)"),
    ('RING_SPLIT', "To Edge Ring and Split", "Edge ring, then one loop through it"),
    ('RING_COLLAPSE', "To Edge Ring and Collapse", "SelectEdgeRing; polyCollapseEdge"),
    ('VERTEX_PERIMETER', "To Vertex Perimeter", "The vertices on the border of the selection"),
    ('SHELL_BORDER', "To Shell Border", "The open border edges of the selected shells"),
    ('REVERSE_PROPAGATE', "Reverse Propagate", "Reverse the selected faces' normals and make the rest of their "
                                               "shells follow them (Maya Mesh Display > Reverse with Propagate)"),
)


def _loops(ring):
    bpy.ops.mesh.select_mode(type='EDGE', use_expand=True)
    bpy.ops.allset.select_loops(ring=ring)


def vertex_perimeter(bm):
    """Vertices on the border of the selection: of a face selection, the verts of edges with one selected face
    (or an open edge); else selected verts with an unselected neighbour or on an open edge."""
    faces = [f for f in bm.faces if f.select]
    if faces:
        out = set()
        for f in faces:
            for e in f.edges:
                if e.is_boundary or sum(1 for g in e.link_faces if g.select) == 1:
                    out.update(e.verts)
        return out
    return {v for v in bm.verts if v.select and (any(not e.other_vert(v).select for e in v.link_edges)
                                                 or any(e.is_boundary for e in v.link_edges))}


def shell_border(bm):
    """Open (boundary) edges of every shell touched by the selection."""
    seeds = [v for v in bm.verts if v.select]
    seen = set(seeds)
    stack = list(seeds)
    while stack:
        v = stack.pop()
        for e in v.link_edges:
            w = e.other_vert(v)
            if w not in seen:
                seen.add(w)
                stack.append(w)
    return {e for v in seen for e in v.link_edges if e.is_boundary}


def reverse_propagate(bm):
    """Flip the selected faces, then walk each shell from them and flip every face whose winding disagrees with
    its already-visited neighbour (manifold edges only). Returns the number of faces flipped."""
    seeds = [f for f in bm.faces if f.select]
    for f in seeds:
        f.normal_flip()
    seen = set(seeds)
    stack = list(seeds)
    flipped = len(seeds)
    while stack:
        f = stack.pop()
        for loop in f.loops:
            e = loop.edge
            if len(e.link_faces) != 2:
                continue
            other = loop.link_loop_radial_next
            g = other.face
            if g in seen:
                continue
            seen.add(g)
            if other.vert == loop.vert:     # same direction along the shared edge = opposite winding
                g.normal_flip()
                flipped += 1
            stack.append(g)
    return flipped


class ALLSET_OT_mm_poly(bpy.types.Operator):
    """Maya polygon command from a marking menu (convert the selection, then act)"""
    bl_idname = "allset.mm_poly"
    bl_label = "Polygon Marking Menu Item"
    bl_options = {'REGISTER', 'UNDO'}

    kind: EnumProperty(items=POLY_KINDS, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    @classmethod
    def description(cls, context, props):
        return next(d for k, _l, d in POLY_KINDS if k == props.kind)

    def execute(self, context):
        kind = self.kind
        if kind == 'LOOP_DELETE':
            _loops(False)
            bpy.ops.mesh.dissolve_edges(use_verts=True)
            return {'FINISHED'}
        if kind == 'LOOP_DUPLICATE':
            _loops(False)      # Maya polyDuplicateEdge on the loops (the kit Offset Edge Loop)
            bpy.ops.allset.offset_edge_loop('EXEC_DEFAULT')
            return {'FINISHED'}
        if kind == 'RING_SPLIT':
            _loops(True)
            bpy.ops.mesh.subdivide(number_cuts=1)
            return {'FINISHED'}
        if kind == 'RING_COLLAPSE':
            _loops(True)
            bpy.ops.mesh.edge_collapse()
            return {'FINISHED'}
        ob = context.edit_object
        bm = bmesh.from_edit_mesh(ob.data)
        bm.verts.index_update()
        bm.edges.index_update()
        if kind == 'REVERSE_PROPAGATE':
            if not any(f.select for f in bm.faces):
                self.report({'WARNING'}, "Select faces to reverse.")
                return {'CANCELLED'}
            reverse_propagate(bm)
            bmesh.update_edit_mesh(ob.data)
            return {'FINISHED'}
        if kind == 'VERTEX_PERIMETER':
            verts = {v.index for v in vertex_perimeter(bm)}     # read before the mode switch re-flushes it
            bpy.ops.mesh.select_mode(type='VERT')
            bm = bmesh.from_edit_mesh(ob.data)
            bm.verts.ensure_lookup_table()
            for v in bm.verts:
                v.select_set(False)
            bm.select_flush(False)
            for i in verts:
                bm.verts[i].select_set(True)
        else:   # SHELL_BORDER
            edges = {e.index for e in shell_border(bm)}
            bpy.ops.mesh.select_mode(type='EDGE')
            bm = bmesh.from_edit_mesh(ob.data)
            bm.edges.ensure_lookup_table()
            for v in bm.verts:
                v.select_set(False)
            bm.select_flush(False)
            for i in edges:
                bm.edges[i].select_set(True)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(ob.data)
        return {'FINISHED'}


# --- Select options ---------------------------------------------------------------------------

class ALLSET_OT_mm_camera_based(bpy.types.Operator):
    """Camera-Based Selection: marquee and lasso select only the components you can see (Maya ``cmds.selectPref(useDepth=...)``;
    the kit preference "Marquee Selects Hidden Components" the other way)"""
    bl_idname = "allset.mm_camera_based"
    bl_label = "Camera-Based Selection"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        from .. import preferences
        prefs = preferences.get(context)
        prefs.select_through = not prefs.select_through
        results.result(self, f"Camera-Based Selection {'off' if prefs.select_through else 'on'}")
        return {'FINISHED'}


classes = (ALLSET_OT_mm_object_item, ALLSET_OT_mm_select_hierarchy, ALLSET_OT_mm_bounding_box,
           ALLSET_OT_mm_uv_set, ALLSET_OT_mm_color_set, ALLSET_MT_uv_sets_rmb, ALLSET_MT_color_sets_rmb,
           ALLSET_OT_mm_poly, ALLSET_OT_mm_camera_based)
