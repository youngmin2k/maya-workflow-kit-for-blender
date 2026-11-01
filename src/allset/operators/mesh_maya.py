# SPDX-License-Identifier: GPL-3.0-or-later
"""Mesh menu commands with Maya's meaning.

Maya:
- Mesh > Combine = ``cmds.polyUnite(centerPivot=True, name=first)``: a new ``pCube2`` (pCube1 / pSphere1 stay behind as
  empty transforms, so the name skips 1), vertices where they were, pivot at the bounding-box centre, translate 0.
- Mesh > Separate = ``cmds.polySeparate``: ``polySurface1`` / ``polySurface2`` under the original transform (now a
  group).
- Mesh > Mirror options: Cut Geometry on, Mirror Axis Position
  World, Offset 0, Mirror Axis X, Direction -, Combine with Original on, Merge border vertices, threshold Automatic.
The kit applies the result to the mesh (Maya's state after Delete History; no empty transforms are left).
"""

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty
from mathutils import Matrix, Vector

from .. import results
from . import freeze, naming, parenting, units

# Maya Y-up axis -> Blender (axis index, sign): X -> X, Y -> Z, Z -> -Y
MAYA_AXES = {'X': (0, 1.0), 'Y': (2, 1.0), 'Z': (1, -1.0)}


def _mesh_selection(context):
    return [o for o in context.selected_objects if o.type == 'MESH']


def _first_selected(objects, active):
    """Maya's first selected object. Blender keeps no selection order: the active object is the last
    one picked, so the first is a non-active one (by name when there are several)."""
    rest = sorted((o for o in objects if o is not active), key=lambda o: o.name)
    return rest[0] if rest else active


def _maya_rename(ob, base, also_taken=()):
    """``base<N>`` / ``base Shape<N>`` with names in ``also_taken`` counted as used (Maya keeps them)."""
    naming.drop_orphans(bpy.data.objects, base)
    naming.drop_orphans(bpy.data.meshes, f"{base}Shape")
    taken = {o.name for o in bpy.data.objects if o is not ob} | set(also_taken)
    shapes = {m.name for m in bpy.data.meshes if m is not ob.data}
    n = naming.next_number(base, taken, shapes)
    ob.name = f"{base}{n}"
    if ob.data is not None and ob.data.users == 1:
        ob.data.name = f"{base}Shape{n}"
    return ob.name


def _bake_world(ob):
    """Put the object's world transform into its vertices: identity transform at the world root."""
    mw = ob.matrix_world.copy()
    if ob.data.users > 1:
        ob.data = ob.data.copy()
    ob.parent = None
    ob.matrix_parent_inverse = Matrix.Identity(4)
    ob.location = ob.delta_location = (0, 0, 0)
    ob.rotation_mode = 'XYZ'
    ob.rotation_euler = ob.delta_rotation_euler = (0, 0, 0)
    ob.scale = ob.delta_scale = (1, 1, 1)
    ob.data.transform(mw)
    if mw.is_negative:
        ob.data.flip_normals()


def combine(context, objects):
    """Maya Combine: one new mesh named after the first selected, pivot at the bounding-box centre."""
    active = context.view_layer.objects.active
    if active not in objects:
        active = objects[-1]
    first = _first_selected(objects, active)
    base = naming.base_name(first.name)
    sources = [o.name for o in objects]
    for o in context.selected_objects:
        o.select_set(o in objects)
    context.view_layer.objects.active = active
    bpy.ops.object.join()
    ob = context.view_layer.objects.active
    _bake_world(ob)
    context.view_layer.update()
    freeze.center_pivot(context, [ob])
    _maya_rename(ob, base, sources)
    return ob


def separate(context, ob):
    """Maya Separate on one mesh object: shells -> ``polySurfaceN`` under a group with the original name."""
    for o in context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.separate(type='LOOSE')
    bpy.ops.object.mode_set(mode='OBJECT')
    pieces = [ob] + [o for o in context.selected_objects if o is not ob]
    if len(pieces) < 2:
        return None, pieces
    name = ob.name
    for piece in pieces:
        piece.name = "~separate"           # frees the names for Maya numbering
    grp = bpy.data.objects.new(name, None)
    grp.empty_display_type = 'PLAIN_AXES'
    grp.empty_display_size = units.maya_unit(context.scene)
    for coll in ob.users_collection:
        coll.objects.link(grp)
    grp.parent = ob.parent
    grp.matrix_parent_inverse = ob.matrix_parent_inverse.copy()
    grp.rotation_mode = ob.rotation_mode
    for attr in ("location", "rotation_euler", "rotation_quaternion", "scale", "delta_location",
                 "delta_rotation_euler", "delta_scale"):
        setattr(grp, attr, getattr(ob, attr))
    context.view_layer.update()
    # Maya: the pieces have translate 0 and their pivot at the group's own origin, not at its pivot
    # (polySurface1/2 rotatePivot (0, 0, 0) under pCube2). The group carries the pivot
    # offset in delta_location, so each piece's pivot moves back by it (freeze.shift_pivot keeps the data).
    lin = Matrix.LocRotScale(None, grp.matrix_basis.to_quaternion(), grp.matrix_basis.to_scale()).to_3x3()
    back = lin.inverted_safe() @ -Vector(grp.delta_location)
    for piece in pieces:
        world = piece.matrix_world.copy()      # separate copied the original's pivot delta to every piece
        piece.delta_location, piece.delta_rotation_euler, piece.delta_scale = (0, 0, 0), (0, 0, 0), (1, 1, 1)
        piece.matrix_world = world
        parenting.set_parent_maya(piece, grp)
        context.view_layer.update()
        if back.length > 1e-9:
            freeze.shift_pivot(piece, back)
        _maya_rename(piece, "polySurface")
    for o in context.selected_objects:
        o.select_set(False)
    for piece in pieces:
        piece.select_set(True)
    context.view_layer.objects.active = pieces[0]
    return grp, pieces


# --- Mirror ---------------------------------------------------------------------------------------

def mirror_plane(ob, axis, position, offset, direction):
    """(point, receiving-side direction) in world space; ``offset`` in Blender units along the Maya axis."""
    index, sign = MAYA_AXES[axis]
    n = Vector((0.0, 0.0, 0.0))
    n[index] = sign
    d = n if direction == 'POSITIVE' else -n
    if position == 'WORLD':
        p = n * offset
    elif position == 'OBJECT':
        p = ob.matrix_world.translation + n * offset
    else:  # BOUNDING_BOX: the box side the copy goes to
        corners = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        far = max(corners, key=lambda c: c.dot(d))
        p = n * far.dot(n) + n * offset
    return p, d


def mirror_bmesh(bm, p, d, cut=True, combine=True, merge=True, threshold=1e-5):
    """Mirror ``bm`` (world space) across the plane (p, normal d), Maya Mirror semantics:
    Cut removes the receiving side first; the copy is merged at the border when ``merge``.
    Returns the copy's geometry as a new bmesh when not ``combine`` (``bm`` is left as the original)."""
    if cut:
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=p, plane_no=d, clear_outer=True, dist=threshold)
    reflect = Matrix.Translation(p) @ (Matrix.Identity(4) - 2 * _outer(d)) @ Matrix.Translation(-p)
    if not combine:
        copy = bm.copy()
        bmesh.ops.transform(copy, matrix=reflect, verts=copy.verts[:])
        bmesh.ops.reverse_faces(copy, faces=copy.faces[:])
        return copy
    dup = bmesh.ops.duplicate(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:])
    verts = [g for g in dup["geom"] if isinstance(g, bmesh.types.BMVert)]
    faces = [g for g in dup["geom"] if isinstance(g, bmesh.types.BMFace)]
    bmesh.ops.transform(bm, matrix=reflect, verts=verts)
    bmesh.ops.reverse_faces(bm, faces=faces)
    if merge:
        border = [v for v in bm.verts if abs((v.co - p).dot(d)) <= threshold * 2]
        bmesh.ops.remove_doubles(bm, verts=border, dist=threshold)
    return None


def _outer(d):
    m = Matrix(((d.x * d.x, d.x * d.y, d.x * d.z, 0), (d.y * d.x, d.y * d.y, d.y * d.z, 0),
                (d.z * d.x, d.z * d.y, d.z * d.z, 0), (0, 0, 0, 0)))
    return m


class ALLSET_OT_mirror(bpy.types.Operator):
    """Maya Mirror: mirror the selected meshes across a world / object / bounding-box plane (applied to the mesh;
    press and hold the menu item for the Mirror Options)"""
    bl_idname = "allset.mirror"
    bl_label = "Mirror"
    bl_options = {'REGISTER', 'UNDO'}

    cut: BoolProperty(name="Cut Geometry", default=True)
    position: EnumProperty(name="Mirror Axis Position", default='WORLD',
                           items=(('BOUNDING_BOX', "Bounding Box", ""), ('OBJECT', "Object", ""),
                                  ('WORLD', "World", "")))
    offset: FloatProperty(name="Offset", description="Plane offset along the axis (Maya units)", default=0.0,
                          precision=4)
    axis: EnumProperty(name="Mirror Axis", default='X',
                       items=(('X', "X", "Maya X = Blender X"), ('Y', "Y", "Maya Y (up) = Blender Z"),
                              ('Z', "Z", "Maya Z = Blender -Y")))
    direction: EnumProperty(name="Mirror Direction", default='NEGATIVE',
                            items=(('POSITIVE', "+", "The copy goes to the + side"),
                                   ('NEGATIVE', "-", "The copy goes to the - side")))
    combine: BoolProperty(name="Combine with Original", default=True)
    merge: BoolProperty(name="Merge border vertices", default=True)
    auto_threshold: BoolProperty(name="Automatic", default=True)
    threshold: FloatProperty(name="Merge Threshold", description="Custom threshold (Maya units)",
                             default=0.001, min=0.0, precision=4)
    option_box: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(_mesh_selection(context))

    def invoke(self, context, event):
        if self.option_box:   # Maya option box: the Mirror Options window
            return context.window_manager.invoke_props_dialog(self, title="Mirror Options", confirm_text="Mirror",
                                                              width=360)
        return self.execute(context)

    def draw(self, context):
        lay = self.layout
        lay.use_property_split = True
        col = lay.column(heading="Mirror Settings")
        col.prop(self, "cut")
        col.prop(self, "position")
        col.prop(self, "offset")
        col.row().prop(self, "axis", expand=True)
        col.row().prop(self, "direction", expand=True)
        col = lay.column(heading="Merge Settings")
        col.prop(self, "combine")
        sub = col.column()
        sub.active = self.combine
        sub.prop(self, "merge")
        sub.prop(self, "auto_threshold")
        row = sub.row()
        row.active = not self.auto_threshold
        row.prop(self, "threshold")

    def execute(self, context):
        k = units.maya_unit(context.scene)
        threshold = (0.001 if self.auto_threshold else self.threshold) * k
        made = []
        for ob in _mesh_selection(context):
            mw = ob.matrix_world.copy()
            p, d = mirror_plane(ob, self.axis, self.position, self.offset * k, self.direction)
            bm = bmesh.new()
            bm.from_mesh(ob.data)
            bmesh.ops.transform(bm, matrix=mw, verts=bm.verts[:])
            copy = mirror_bmesh(bm, p, d, self.cut, self.combine, self.merge, threshold)
            inv = mw.inverted_safe()
            if ob.data.users > 1:
                ob.data = ob.data.copy()
            bmesh.ops.transform(bm, matrix=inv, verts=bm.verts[:])
            bm.to_mesh(ob.data)
            bm.free()
            ob.data.update()
            if copy is not None:
                bmesh.ops.transform(copy, matrix=inv, verts=copy.verts[:])
                new = ob.copy()
                new.data = ob.data.copy()
                copy.to_mesh(new.data)
                copy.free()
                for coll in ob.users_collection:
                    coll.objects.link(new)
                _maya_rename(new, naming.base_name(ob.name))
                made.append(new.name)
        results.result(self, "Mirror" + (f": new {', '.join(made)}" if made else ""))
        return {'FINISHED'}


# --- Combine / Separate / Boolean ------------------------------------------------------------------

class ALLSET_OT_combine(bpy.types.Operator):
    """Maya Combine: the selected meshes become one new mesh (pivot at its centre)"""
    bl_idname = "allset.combine"
    bl_label = "Combine"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and len(_mesh_selection(context)) >= 2

    def execute(self, context):
        ob = combine(context, _mesh_selection(context))
        results.result(self, f"Combine: {ob.name}")
        return {'FINISHED'}


class ALLSET_OT_separate(bpy.types.Operator):
    """Maya Separate: each piece of the selected meshes becomes its own object (under a group)"""
    bl_idname = "allset.separate"
    bl_label = "Separate"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if context.mode == 'EDIT_MESH':
            return True
        return context.mode == 'OBJECT' and bool(_mesh_selection(context))

    def execute(self, context):
        if context.mode == 'EDIT_MESH':      # components selected: Blender's separate by loose parts
            return bpy.ops.mesh.separate(type='LOOSE')
        made, single = [], []
        for ob in _mesh_selection(context):
            grp, pieces = separate(context, ob)
            (made if grp else single).append(ob.name if grp is None else grp.name)
        if not made:
            self.report({'WARNING'}, "Separate: the mesh has only one piece")
            return {'CANCELLED'}
        results.result(self, f"Separate: {', '.join(made)}")
        return {'FINISHED'}


def _apply_boolean(context, base, operand, op):
    """Apply ``base`` ``op`` ``operand`` on ``base`` (exact solver) and delete ``operand``."""
    if base.data.users > 1:
        base.data = base.data.copy()
    mod = base.modifiers.new("Maya Boolean", 'BOOLEAN')
    mod.operation, mod.object, mod.solver = op, operand, 'EXACT'
    with context.temp_override(object=base, active_object=base):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(operand)


def _boolean_order(context, objs):
    """(first selected, the rest) as far as Blender knows the selection order: the active object is the last
    one picked, the others go by name."""
    active = context.view_layer.objects.active
    lead = active if active in objs else objs[-1]
    rest = sorted((o for o in objs if o is not lead), key=lambda o: o.name)
    order = rest + [lead]
    return order[0], order[1:]


class ALLSET_OT_boolean(bpy.types.Operator):
    """Maya Booleans: select the first object, then the others. Like Maya, the first object meets all the others
    together: Difference (A - B) = first minus the rest, Difference (B - A) = the rest minus the first,
    Intersection = the part of the first inside any of the rest"""
    bl_idname = "allset.boolean"
    bl_label = "Boolean"
    bl_options = {'REGISTER', 'UNDO'}

    operation: EnumProperty(items=(('UNION', "Union", ""), ('DIFFERENCE', "Difference (A - B)", ""),
                                   ('DIFFERENCE_BA', "Difference (B - A)", "Maya 2026: the others minus the first"),
                                   ('INTERSECT', "Intersection", "")), name="Operation", default='UNION')

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and len(_mesh_selection(context)) >= 2

    def execute(self, context):
        first, rest = _boolean_order(context, _mesh_selection(context))
        others = rest[0]
        for ob in rest[1:]:                  # Maya: the first object against the union of the others
            _apply_boolean(context, others, ob, 'UNION')
        if self.operation == 'UNION':
            base, operand, op = first, others, 'UNION'
        elif self.operation == 'DIFFERENCE_BA':
            base, operand, op = others, first, 'DIFFERENCE'
        else:
            base, operand, op = first, others, self.operation
        _apply_boolean(context, base, operand, op)
        base.select_set(True)
        context.view_layer.objects.active = base
        results.result(self, f"Boolean {self.operation.title()}: {base.name}")
        return {'FINISHED'}


classes = (ALLSET_OT_mirror, ALLSET_OT_combine, ALLSET_OT_separate, ALLSET_OT_boolean)
