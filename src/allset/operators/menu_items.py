# SPDX-License-Identifier: GPL-3.0-or-later
"""Small Maya menu commands Blender has no single operator for.

Each reproduces the Maya result with a few data / bmesh edits: Modify > Naming, Mesh Display > Soften/Harden
Edges, Edit Mesh > Detach / Edit Edge Flow / Wedge, Deform > Nonlinear, Display > Object Display, Mesh Tools >
Sculpting Tools, UV > Assign Checker Shader, the Audio menu, Stereo > Create, and ``menu_note`` for items whose
Maya behaviour already is Blender's (only the notice is shown).
"""

import math

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy_extras.io_utils import ImportHelper
from mathutils import Vector

from .. import results
from .. import undo_steps


def _hierarchy(objects):
    """``objects`` and all their descendants, parents first, each once."""
    out, seen = [], set()

    def walk(ob):
        if ob.name in seen:
            return
        seen.add(ob.name)
        out.append(ob)
        for child in ob.children:
            walk(child)
    for ob in objects:
        walk(ob)
    return out


def _rename(ob, fn):
    """Rename the object and (like Maya renames the shape with its transform) its single-user data."""
    ob.name = fn(ob.name)
    data = ob.data
    if data is not None and data.users == 1 and data.library is None:
        data.name = fn(data.name)


# --- Modify > Naming --------------------------------------------------------------------------

class ALLSET_OT_prefix_hierarchy(bpy.types.Operator):
    """Put a prefix in front of the names of the selected objects and everything under them
    (Maya Modify > Prefix Hierarchy Names)"""
    bl_idname = "allset.prefix_hierarchy"
    bl_label = "Prefix Hierarchy Names"
    bl_options = {'REGISTER', 'UNDO'}

    prefix: StringProperty(name="Prefix", default="prefix_")

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if not self.prefix:
            return {'CANCELLED'}
        obs = _hierarchy(context.selected_objects)
        for ob in obs:
            _rename(ob, lambda name: self.prefix + name)
        results.result(self, f"Prefixed {len(obs)} name(s)")
        return {'FINISHED'}


class ALLSET_OT_search_replace_names(bpy.types.Operator):
    """Replace text in object names: in the selected hierarchies, the selection only, or every object
    (Maya Modify > Search and Replace Names)"""
    bl_idname = "allset.search_replace_names"
    bl_label = "Search and Replace Names"
    bl_options = {'REGISTER', 'UNDO'}

    search: StringProperty(name="Search For")
    replace: StringProperty(name="Replace With")
    scope: EnumProperty(name="Operation", default='HIERARCHY', items=(
        ('HIERARCHY', "Hierarchy", "The selected objects and everything under them"),
        ('SELECTED', "Selected", "Only the selected objects"),
        ('ALL', "All", "Every object in the scene")))

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if not self.search:
            self.report({'WARNING'}, "Nothing to search for")
            return {'CANCELLED'}
        if self.scope == 'ALL':
            obs = list(context.scene.objects)
        elif self.scope == 'SELECTED':
            obs = list(context.selected_objects)
        else:
            obs = _hierarchy(context.selected_objects)
        n = 0
        for ob in obs:
            if self.search in ob.name:
                _rename(ob, lambda name: name.replace(self.search, self.replace))
                n += 1
        results.result(self, f"Renamed {n} object(s)")
        return {'FINISHED'}


# --- Mesh Display > Soften/Harden Edges -------------------------------------------------------

def soften_harden(bm, angle, edges=None):
    """Maya polySoftEdge: an edge whose faces meet at less than ``angle`` degrees is soft, the rest hard;
    the faces shade smooth (Soften/Harden on an object = every edge, angle 30)."""
    limit = math.radians(angle) + 1e-6
    for e in (bm.edges if edges is None else edges):
        e.smooth = len(e.link_faces) != 2 or e.calc_face_angle(0.0) <= limit
    for e in (bm.edges if edges is None else edges):
        for f in e.link_faces:
            f.smooth = True


class ALLSET_OT_soften_harden(bpy.types.Operator):
    """Soften edges whose faces meet at less than the angle, harden the rest: the selected edges in
    component mode, every edge of the selected meshes in object mode (Maya Mesh Display > Soften/Harden)"""
    bl_idname = "allset.soften_harden"
    bl_label = "Soften/Harden Edges"
    bl_options = {'REGISTER', 'UNDO'}

    angle: FloatProperty(name="Angle", default=30.0, min=0.0, max=180.0,
                         description="Default 30: faces at a smaller angle shade smooth across the edge")
    option_box: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})
    # Quad Draw's options menu: every edge of the edited mesh, then nothing stays selected
    whole: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return any(ob.type == 'MESH' for ob in _meshes(context))

    def invoke(self, context, event):
        if self.option_box:
            return context.window_manager.invoke_props_dialog(self)
        return self.execute(context)

    def execute(self, context):
        for ob in _meshes(context):
            if ob.mode == 'EDIT':
                bm = bmesh.from_edit_mesh(ob.data)
                soften_harden(bm, self.angle, None if self.whole else ([e for e in bm.edges if e.select] or None))
                if self.whole:
                    for seq in (bm.verts, bm.edges, bm.faces):
                        for el in seq:
                            el.select = False
                bmesh.update_edit_mesh(ob.data)
            else:
                bm = bmesh.new()
                bm.from_mesh(ob.data)
                soften_harden(bm, self.angle)
                bm.to_mesh(ob.data)
                bm.free()
                ob.data.update()
        return {'FINISHED'}


def _meshes(context):
    if context.mode == 'EDIT_MESH':
        return [ob for ob in context.objects_in_mode if ob.type == 'MESH']
    return [ob for ob in context.selected_objects if ob.type == 'MESH']


# --- Edit Mesh > Detach / Edit Edge Flow / Wedge ----------------------------------------------

def _edit_bm(context):
    ob = context.edit_object
    return ob, bmesh.from_edit_mesh(ob.data)


def detach(bm, mode):
    """Maya Detach of vertices (each face around a selected vertex gets its own vertex) or edges (split
    open). Returns how many elements were detached."""
    if mode == 'VERT':
        verts = [v for v in bm.verts if v.select and len(v.link_faces) > 1]
        for v in verts:
            bmesh.utils.vert_separate(v, list(v.link_edges))
        return len(verts)
    if mode == 'EDGE':
        edges = [e for e in bm.edges if e.select and not e.is_boundary]
        if edges:
            bmesh.ops.split_edges(bm, edges=edges)
        return len(edges)
    return 0


class ALLSET_OT_detach(bpy.types.Operator):
    """Detach the selected components: vertices split per face, edges split open, faces become their own
    shell (Maya Edit Mesh > Detach)"""
    bl_idname = "allset.detach"
    bl_label = "Detach"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        ob, bm = _edit_bm(context)
        mode = context.tool_settings.mesh_select_mode
        if mode[2]:
            if not any(f.select for f in bm.faces):
                self.report({'WARNING'}, "No vertices or edges selected to detach.")
                return {'CANCELLED'}
            bpy.ops.mesh.split()
            return {'FINISHED'}
        n = detach(bm, 'VERT' if mode[0] else 'EDGE')
        if not n:
            self.report({'WARNING'}, "No vertices or edges selected to detach.")   # Maya's warning
            return {'CANCELLED'}
        bmesh.update_edit_mesh(ob.data)
        return {'FINISHED'}


def _across(v, e):
    """The edge of ``v`` opposite ``e`` in a 4-edge vertex (the next edge of the ring), or None."""
    if len(v.link_edges) != 4:
        return None
    faces = set(e.link_faces)
    others = [x for x in v.link_edges if x is not e and not (set(x.link_faces) & faces)]
    return others[0] if len(others) == 1 else None


def _circle_tangent(p_prev, p, p_next):
    """Unit tangent at ``p`` of the circle through three points, pointing from ``p_prev`` towards ``p_next``
    (None when they are in a line)."""
    a, b = p_prev - p, p_next - p
    axb = a.cross(b)
    if axb.length_squared < 1e-18:
        return None
    centre = p + (b * a.length_squared - a * b.length_squared).cross(axb) / (2 * axb.length_squared)
    t = axb.cross(p - centre)
    if t.length_squared < 1e-18:
        return None
    t.normalize()
    return t if t.dot(p_next - p_prev) >= 0 else -t


def edge_flow(bm, edges, flow=1.0):
    """Maya Edit Edge Flow (polyEditEdgeFlow -adjustEdgeFlow): each vertex of the selected edges moves onto a cubic
    Hermite curve between its two ring neighbours a, b, with tangents along the circles through (a's outer
    neighbour, a, b) and (a, b, b's outer neighbour) and length = |ab|, at the vertex's own parameter; flow 0 = the
    straight line (sphere ring: Maya 0.9983, this rule
    0.9971; the step-101 Catmull-Rom gave 0.951). Returns the number of moved vertices."""
    selected = set(edges)
    moves = {}
    for v in {v for e in edges for v in e.verts}:
        ring = [x for x in v.link_edges if x not in selected]
        if len(ring) != 2:
            continue
        pts = []
        for x in ring:
            a = x.other_vert(v)
            nxt = _across(a, x)
            pts.append((a.co.copy(), nxt.other_vert(a).co.copy() if nxt else None))
        (a, a2), (b, b2) = pts
        da, db = (v.co - a).length, (v.co - b).length
        if da + db < 1e-9:
            continue
        t = da / (da + db)
        chord = b - a
        length = chord.length
        ta = _circle_tangent(a2, a, b) if a2 is not None else None
        tb = _circle_tangent(a, b, b2) if b2 is not None else None
        if ta is None and tb is None:
            curve = a.lerp(b, t)
        else:
            u = chord.normalized()
            ta = ta if ta is not None else (u * 2 * u.dot(tb) - tb)    # mirror the other tangent about the chord
            tb = tb if tb is not None else (u * 2 * u.dot(ta) - ta)
            h00, h10 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t
            h01, h11 = -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
            curve = a * h00 + ta * (length * h10) + b * h01 + tb * (length * h11)
        moves[v] = a.lerp(b, t).lerp(curve, flow)
    for v, co in moves.items():
        v.co = co
    return len(moves)


class ALLSET_OT_edge_flow(bpy.types.Operator):
    """Move the selected edges so they follow the curvature of the surrounding surface
    (Maya Edit Mesh > Edit Edge Flow)"""
    bl_idname = "allset.edge_flow"
    bl_label = "Edit Edge Flow"
    bl_options = {'REGISTER', 'UNDO'}

    flow: FloatProperty(name="Edge Flow", default=1.0, soft_min=-1.0, soft_max=2.0,
                        description="Maya adjustEdgeFlow: 1 follows the curvature, 0 is straight")

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        for ob in context.objects_in_mode:
            bm = bmesh.from_edit_mesh(ob.data)
            edge_flow(bm, [e for e in bm.edges if e.select], self.flow)
            bmesh.update_edit_mesh(ob.data)
        return {'FINISHED'}


class ALLSET_OT_wedge(bpy.types.Operator):
    """Sweep the selected faces around one of their edges (the active edge) (Maya Edit Mesh > Wedge)"""
    bl_idname = "allset.wedge"
    bl_label = "Wedge"
    bl_options = {'REGISTER', 'UNDO'}

    angle: FloatProperty(name="Wedge Angle", default=90.0, min=-360.0, max=360.0)
    divisions: IntProperty(name="Divisions", default=4, min=1, max=256)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        ob, bm = _edit_bm(context)
        faces = [f for f in bm.faces if f.select]
        edge = bm.select_history.active
        if not isinstance(edge, bmesh.types.BMEdge):
            edge = next((e for e in bm.edges if e.select and e.is_boundary is False
                         and sum(f.select for f in e.link_faces) == 1), None)
        if not faces or edge is None:
            self.report({'WARNING'}, "No faces selected to wedge. Select faces and one or more edges from the "
                                     "selected faces to wedge about.")   # Maya's warning
            return {'CANCELLED'}
        mw = ob.matrix_world
        p0, p1 = mw @ edge.verts[0].co, mw @ edge.verts[1].co
        axis = (p1 - p0).normalized()
        centre = (p0 + p1) / 2
        # spin so the faces turn away from the rest of the mesh (towards their normal)
        normal = (mw.to_3x3() @ faces[0].normal).normalized()
        side = (mw @ faces[0].calc_center_median()) - centre
        if axis.cross(side).dot(normal) < 0:
            axis = -axis
        bpy.ops.mesh.spin(steps=self.divisions, angle=math.radians(self.angle), center=centre, axis=axis,
                          dupli=False, use_auto_merge=True)
        return {'FINISHED'}


# --- Deform > Nonlinear -----------------------------------------------------------------------

NONLINEAR = (('BEND', "Bend", "Maya bend1: Simple Deform Bend"),
             ('TAPER', "Flare", "Maya flare1: Simple Deform Taper"),
             ('STRETCH', "Squash", "Maya squash1: Simple Deform Stretch"),
             ('TWIST', "Twist", "Maya twist1: Simple Deform Twist"))
_NONLINEAR_NAME = {'BEND': "bend", 'TAPER': "flare", 'STRETCH': "squash", 'TWIST': "twist"}
_DEFORMABLE = {'MESH', 'CURVE', 'SURFACE', 'LATTICE'}


def world_bounds(objects):
    pts = [ob.matrix_world @ Vector(c) for ob in objects for c in ob.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


class ALLSET_OT_nonlinear(bpy.types.Operator):
    """Add a nonlinear deformer to the selected objects: Simple Deform with Maya's neutral start value, deforming
    around the handle ``<type>NHandle`` at the objects' bounding-box centre (Maya Deform > Nonlinear)"""
    bl_idname = "allset.nonlinear"
    bl_label = "Nonlinear Deformer"
    bl_options = {'REGISTER', 'UNDO'}

    method: EnumProperty(items=NONLINEAR, name="Type")

    @classmethod
    def poll(cls, context):
        return any(ob.type in _DEFORMABLE for ob in context.selected_objects)

    def execute(self, context):
        base = _NONLINEAR_NAME[self.method]
        obs = [ob for ob in context.selected_objects if ob.type in _DEFORMABLE]
        names = {md.name for ob in bpy.data.objects for md in ob.modifiers} | {o.name for o in bpy.data.objects}
        n = 1
        while f"{base}{n}" in names or f"{base}{n}Handle" in names:
            n += 1
        # Maya: the handle sits at the bounding-box centre, pointing
        # up (Maya +Y = Blender +Z), scaled to half the height; low / high bound -1 / 1 = the whole object.
        lo, hi = world_bounds(obs)
        handle = bpy.data.objects.new(f"{base}{n}Handle", None)
        context.view_layer.active_layer_collection.collection.objects.link(handle)
        handle.empty_display_type = 'SINGLE_ARROW'
        handle.empty_display_size = 1.0
        handle.location = (lo + hi) / 2
        half = max((hi.z - lo.z) / 2, 1e-6)
        handle.scale = (half, half, half)
        for ob in obs:
            md = ob.modifiers.new(f"{base}{n}", 'SIMPLE_DEFORM')
            md.deform_method = self.method
            md.deform_axis = 'Z'
            md.origin = handle
            md.angle = 0.0
            md.factor = 0.0
        return {'FINISHED'}


# --- Display > Object Display -----------------------------------------------------------------

TEMPLATE_PROP = "allset_template"
DISPLAY = (('TEMPLATE', "Template", "Grey wireframe that can't be selected in the view"),
           ('UNTEMPLATE', "Untemplate", "Undo Template (on the selection, else on every templated object)"),
           ('BBOX', "Bounding Box", "Draw as a bounding box"),
           ('NO_BBOX', "No Bounding Box", "Draw the geometry again"))


class ALLSET_OT_object_display(bpy.types.Operator):
    """Maya Display > Object Display: template / bounding box display of the selected objects"""
    bl_idname = "allset.object_display"
    bl_label = "Object Display"
    bl_options = {'REGISTER', 'UNDO'}

    kind: EnumProperty(items=DISPLAY, name="Display")

    def execute(self, context):
        obs = list(context.selected_objects)
        if self.kind == 'UNTEMPLATE':
            obs = [ob for ob in obs if ob.get(TEMPLATE_PROP)] or \
                [ob for ob in context.scene.objects if ob.get(TEMPLATE_PROP)]
        if not obs:
            self.report({'WARNING'}, "Nothing selected.")
            return {'CANCELLED'}
        for ob in obs:
            if self.kind == 'TEMPLATE':
                ob[TEMPLATE_PROP] = ob.display_type
                ob.display_type = 'WIRE'
                ob.select_set(False)
                ob.hide_select = True
            elif self.kind == 'UNTEMPLATE':
                ob.hide_select = False
                ob.display_type = ob.get(TEMPLATE_PROP) or 'TEXTURED'
                del ob[TEMPLATE_PROP]
            elif self.kind == 'BBOX':
                ob.display_type = 'BOUNDS'
            elif ob.display_type == 'BOUNDS':
                ob.display_type = 'TEXTURED'
        return {'FINISHED'}


# --- Mesh Tools > Sculpting Tools -------------------------------------------------------------

SCULPT_LIBRARY = "brushes/essentials_brushes-mesh_sculpt.blend/Brush/"


class ALLSET_OT_sculpt_tool(bpy.types.Operator):
    """Sculpt the active mesh with this brush (Maya Mesh Tools > Sculpting Tools)"""
    bl_idname = "allset.sculpt_tool"
    bl_label = "Sculpting Tool"
    bl_options = {'REGISTER', 'UNDO'}

    brush: StringProperty(name="Brush", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'MESH'

    def execute(self, context):
        ob = context.active_object
        if context.mode != 'SCULPT' and not ob.visible_get():
            # Maya switches the tool without a check; Blender can't
            # sculpt a hidden object, so the kit says so and stays in object mode
            self.report({'WARNING'}, f"{ob.name} is hidden: show it (Display > Show) to sculpt it.")
            return {'CANCELLED'}
        if context.mode != 'SCULPT':
            bpy.ops.object.mode_set(mode='SCULPT')
        try:
            res = _activate_brush(self.brush)
        except RuntimeError as ex:
            if context.window is None:
                self.report({'WARNING'}, str(ex).strip().splitlines()[-1])
                return {'CANCELLED'}
            # 5.2: right after the switch to sculpt mode the brush operator may still see the old mode
            # ("wrong object mode", GUI): the timer below tries again
            res = {'CANCELLED'}
        if res != {'FINISHED'} and context.window is not None:
            # The essentials library loads in the background on the first use in a session (GUI:
            # the operator cancels with "Asset loading is unfinished"): try again for a few seconds.
            _retry_brush(self.brush)
        return {'FINISHED'}



class ALLSET_OT_paint_hair_follicles(bpy.types.Operator):
    """Paint hair on the selected mesh (Maya nHair > Paint Hair Follicles; Blender: a hair Curves object on that
    surface, groomed in Sculpt mode)"""
    bl_idname = "allset.paint_hair_follicles"
    bl_label = "Paint Hair Follicles"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Maya switches to the Paint Hair Follicles tool for any selection, a mesh included
        # (Maya). Blender grows hair as a Curves object attached to a surface mesh:
        # the mesh's hair (its first Curves object) or a new empty one, then Sculpt mode.
        ob = context.active_object
        if ob is not None and ob.mode != 'OBJECT' and ob.type != 'CURVES':
            bpy.ops.object.mode_set(mode='OBJECT')
        if ob is not None and ob.type == 'MESH':
            hair = next((o for o in context.scene.objects
                         if o.type == 'CURVES' and getattr(o.data, "surface", None) is ob), None)
            if hair is None:
                bpy.ops.object.curves_empty_hair_add(align='WORLD', location=ob.matrix_world.translation)
                hair = context.view_layer.objects.active
            else:
                for o in context.selected_objects:
                    o.select_set(False)
                hair.select_set(True)
                context.view_layer.objects.active = hair
            ob = hair
        if ob is None or ob.type != 'CURVES':
            self.report({'WARNING'}, "Paint Hair Follicles: select a mesh to paint hair on.")
            return {'CANCELLED'}
        if not ob.visible_get():
            self.report({'WARNING'}, f"{ob.name} is hidden: show it (Display > Show) to paint hair.")
            return {'CANCELLED'}
        if ob.mode != 'SCULPT_CURVES':
            bpy.ops.object.mode_set(mode='SCULPT_CURVES')
        results.result(self, f"Paint Hair Follicles on {ob.name}")
        return {'FINISHED'}


BRUSH_RETRY_S, BRUSH_RETRIES = 0.2, 25


def _activate_brush(brush, window=None):
    """``brush.asset_activate`` in a 3D View of the window when there is one: 5.2 checks the mode there and refuses
    from another editor (a shelf button: "Unable to activate brush, wrong object mode", GUI)."""
    window = window or bpy.context.window
    area = next((a for a in window.screen.areas if a.type == 'VIEW_3D'), None) if window else None
    region = next((r for r in area.regions if r.type == 'WINDOW'), None) if area else None
    kwargs = dict(asset_library_type='ESSENTIALS', relative_asset_identifier=SCULPT_LIBRARY + brush)
    if region is None:
        return bpy.ops.brush.asset_activate(**kwargs)
    with bpy.context.temp_override(window=window, area=area, region=region):
        return bpy.ops.brush.asset_activate(**kwargs)


def _retry_brush(brush):
    left = [BRUSH_RETRIES]

    def tick():
        left[0] -= 1
        win = bpy.context.window_manager.windows[0] if bpy.context.window_manager.windows else None
        if win is None or bpy.context.mode != 'SCULPT':
            return None
        try:
            done = _activate_brush(brush, win) == {'FINISHED'}
        except RuntimeError:
            done = False
        return None if done or left[0] <= 0 else BRUSH_RETRY_S
    bpy.app.timers.register(tick, first_interval=BRUSH_RETRY_S)


# --- UV > Assign Checker Shader ---------------------------------------------------------------

CHECKER_IMAGE = "uvChecker"


class ALLSET_OT_checker_shader(bpy.types.Operator):
    """Give the selected objects (or faces) a UV checker material (Maya UV > Assign Checker Shader)"""
    bl_idname = "allset.checker_shader"
    bl_label = "Assign Checker Shader"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from . import material
        obs = [ob for ob in (context.objects_in_mode or context.selected_objects) if ob.type == 'MESH']
        if not obs:
            self.report({'WARNING'}, "Select objects or faces to assign the checker to")
            return {'CANCELLED'}
        img = bpy.data.images.get(CHECKER_IMAGE) or bpy.data.images.new(CHECKER_IMAGE, 1024, 1024)
        img.generated_type = 'UV_GRID'
        mat = material.new_material('LAMBERT')
        tree = mat.node_tree
        node = tree.nodes.new("ShaderNodeTexImage")
        node.image = img
        node.location = (-570, 300)
        # Maya Color (the diffuse node's B): a Maya lambert multiplies its texture by diffuse 0.8
        tree.links.new(node.outputs["Color"], material.color_socket(mat))
        material.assign(context, mat, obs)
        return {'FINISHED'}


# --- UV Editor checker button / Textures > Checker Map (a display toggle, #13) -------------------------------
# Maya: the UV Editor checker button shows / hides a checker map on the objects
# (a check button). Blender has no display-only override, so the kit
# puts a checker material on the objects' slots at object level (``link = 'OBJECT'``: the mesh's own materials are
# untouched) and remembers what was there in the object property CHECKER_PREV; off puts it back.

CHECKER_PREV = "allset_checker_prev"
CHECKER_MAT = "allset_checker_display"


def checker_objects(scene):
    return [ob for ob in scene.objects if CHECKER_PREV in ob]


def checker_on(context):
    return bool(checker_objects(context.scene))


def _checker_material():
    from . import material
    mat = next((m for m in bpy.data.materials if m.get(CHECKER_MAT)), None)
    if mat is not None:
        return mat
    img = bpy.data.images.get(CHECKER_IMAGE) or bpy.data.images.new(CHECKER_IMAGE, 1024, 1024)
    img.generated_type = 'UV_GRID'
    mat = material.new_material('LAMBERT')
    mat.name = "checkerDisplay"
    mat[CHECKER_MAT] = True
    tree = mat.node_tree
    node = tree.nodes.new("ShaderNodeTexImage")
    node.image = img
    node.location = (-570, 300)
    tree.nodes.active = node
    tree.links.new(node.outputs["Color"], material.color_socket(mat))
    # a display aid, not a Maya shader: the checker shows at full brightness (diffuse 1)
    material.ensure_diffuse(mat, 1.0)
    _density_node(mat)
    return mat


# Checker density (Maya UV Editor Ctrl+Up / Ctrl+Down): a whole number from 1, one step per key; the checker
# repeats that many times per UV unit (a Mapping node scale in front of the checker image).
CHECKER_DENSITY = "allset_checker_density"
DENSITY_NODE = "Checker Density"


def _density_node(mat):
    tree = mat.node_tree
    node = tree.nodes.get(DENSITY_NODE)
    if node is not None:
        return node
    tex = next((n for n in tree.nodes if n.type == 'TEX_IMAGE'), None)
    if tex is None:
        return None
    coord = tree.nodes.new("ShaderNodeTexCoord")
    coord.location = tex.location.x - 420, tex.location.y
    node = tree.nodes.new("ShaderNodeMapping")
    node.name = node.label = DENSITY_NODE
    node.location = tex.location.x - 220, tex.location.y
    tree.links.new(coord.outputs["UV"], node.inputs["Vector"])
    tree.links.new(node.outputs["Vector"], tex.inputs["Vector"])
    d = checker_density(mat)
    node.inputs["Scale"].default_value = (d, d, 1.0)
    return node


def checker_density(mat=None):
    if mat is None:
        mat = next((m for m in bpy.data.materials if m.get(CHECKER_MAT)), None)
    return max(1, int(mat.get(CHECKER_DENSITY, 1))) if mat is not None else 1


def set_checker_density(density):
    """Set the checker density (at least 1) on the checker display material; returns the new value."""
    mat = _checker_material()
    d = max(1, int(density))
    mat[CHECKER_DENSITY] = d
    node = _density_node(mat)
    if node is not None:
        node.inputs["Scale"].default_value = (d, d, 1.0)
    return d


def checker_show(obs):
    import json
    mat = _checker_material()
    for ob in obs:
        if CHECKER_PREV in ob:
            continue
        added = not ob.material_slots
        if added:
            ob.data.materials.append(None)
        prev = [(s.link, s.material.name if s.link == 'OBJECT' and s.material else "") for s in ob.material_slots]
        ob[CHECKER_PREV] = json.dumps({"slots": prev, "added": added})
        for slot in ob.material_slots:
            slot.link = 'OBJECT'
            slot.material = mat


def checker_hide(obs):
    import json
    for ob in obs:
        raw = ob.get(CHECKER_PREV)
        if raw is None:
            continue
        data = json.loads(raw)
        for slot, (link, name) in zip(ob.material_slots, data["slots"]):
            slot.link = 'OBJECT'
            slot.material = bpy.data.materials.get(name) if name else None
            slot.link = link
        if data.get("added") and ob.type == 'MESH' and len(ob.data.materials) == 1 and ob.data.materials[0] is None:
            ob.data.materials.clear()
        del ob[CHECKER_PREV]


class ALLSET_OT_checker_toggle(bpy.types.Operator):
    """Show or hide a checker map on the selected objects (Maya UV Editor checker button); a second click puts the
    objects' own materials back"""
    bl_idname = "allset.checker_toggle"
    bl_label = "Checker Map"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        shown = checker_objects(context.scene)
        if shown:
            checker_hide(shown)
            return {'FINISHED'}
        obs = [ob for ob in (context.objects_in_mode or context.selected_objects) if ob.type == 'MESH']
        if not obs:
            self.report({'WARNING'}, "Select objects or faces to show the checker on")
            return {'CANCELLED'}
        checker_show(obs)
        return {'FINISHED'}


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_checker_density(bpy.types.Operator):
    """Make the UV checker finer or coarser (Maya UV Editor Increase / Decrease Checker Density)"""
    bl_idname = "allset.checker_density"
    bl_label = "Checker Density"
    bl_options = {'REGISTER', 'UNDO'}

    step: IntProperty(name="Step", default=1, options={'SKIP_SAVE'})

    def execute(self, context):
        d = set_checker_density(checker_density() + self.step)
        results.result(self, f"Checker density {d}")
        return {'FINISHED'}


# --- Audio ------------------------------------------------------------------------------------

def _strips(scene, create=False):
    if scene.sequence_editor is None:
        if not create:
            return None
        scene.sequence_editor_create()
    from .. import compat
    return compat.strips(scene.sequence_editor)


class ALLSET_OT_import_audio(bpy.types.Operator, ImportHelper):
    """Import a sound at the start of the time slider; it plays with the scene (Maya Audio > Import Audio)"""
    bl_idname = "allset.import_audio"
    bl_label = "Import Audio"
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: StringProperty(default="*.wav;*.mp3;*.ogg;*.flac;*.aif;*.aiff;*.m4a", options={'HIDDEN'})

    def execute(self, context):
        import os
        scene = context.scene
        strips = _strips(scene, create=True)
        try:
            strip = strips.new_sound(os.path.basename(self.filepath), self.filepath, 1, scene.frame_start)
        except RuntimeError as ex:
            self.report({'ERROR'}, str(ex).strip())
            return {'CANCELLED'}
        results.result(self, f"Imported {strip.name}")
        return {'FINISHED'}


class ALLSET_OT_delete_sounds(bpy.types.Operator):
    """Delete the scene's sounds (Maya Audio > Delete Sounds)"""
    bl_idname = "allset.delete_sounds"
    bl_label = "Delete Sounds"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        strips = _strips(context.scene)
        sounds = [s for s in strips if s.type == 'SOUND'] if strips is not None else []
        for s in sounds:
            strips.remove(s)
        results.result(self, f"Deleted {len(sounds)} sound(s)")
        return {'FINISHED'}


# --- Stereo > Create --------------------------------------------------------------------------

class ALLSET_OT_stereo_camera(bpy.types.Operator):
    """Create a stereo camera: a Maya camera with Blender's stereoscopy (Views) turned on
    (Maya Stereo > Create > Stereo Camera)"""
    bl_idname = "allset.stereo_camera"
    bl_label = "Stereo Camera"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from . import create
        ob = create.create(context, 'CAMERA', maya_naming=False)
        from . import naming
        naming.apply_maya_name(ob, "stereoCamera")
        render = context.scene.render
        render.use_multiview = True
        render.views_format = 'STEREO_3D'
        return {'FINISHED'}


# --- notice-only items ------------------------------------------------------------------------

class ALLSET_OT_menu_note(bpy.types.Operator):
    """Maya item whose behaviour already is Blender's: shows the notice"""
    bl_idname = "allset.menu_note"
    bl_label = "Note"
    bl_options = {'INTERNAL'}

    item: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        from ..ui import notices
        n = notices.notice(self.item)
        if n:
            notices.show(f"{self.item.rsplit('/', 1)[-1]}: {n[1]}")
            results.result(self, n[1])
        return {'FINISHED'}


classes = (ALLSET_OT_prefix_hierarchy, ALLSET_OT_search_replace_names, ALLSET_OT_soften_harden,
           ALLSET_OT_detach, ALLSET_OT_edge_flow, ALLSET_OT_wedge, ALLSET_OT_nonlinear,
           ALLSET_OT_object_display, ALLSET_OT_sculpt_tool, ALLSET_OT_checker_shader, ALLSET_OT_checker_toggle, ALLSET_OT_checker_density, ALLSET_OT_import_audio,
           ALLSET_OT_delete_sounds, ALLSET_OT_stereo_camera, ALLSET_OT_menu_note, ALLSET_OT_paint_hair_follicles)
