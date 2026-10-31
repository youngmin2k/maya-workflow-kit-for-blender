# SPDX-License-Identifier: GPL-3.0-or-later
"""L1: NURBS curve shapes as bone Custom Shapes (Maya ``cmds.parent(shape=True)``)

Maya gives a joint a control shape with ``cmds.parent(curveShape, joint, shape=True, relative=True)``
(case ``L1_parent_shape_relative``): the curve
shape moves under the joint keeping its CV local values, the old transform stays without a shape. Without ``relative``
the CVs keep their world positions and the old transform goes away. A second shape on the same
node is added (two shapes, one control). Every kit
control = a bone Custom Shape — the shape is a copy of the curve data baked into bone space on a curve object in the
hidden collection ``.AllsetControlShapes`` (not linked to any scene, fake user), Custom Shape transform identity and
bone size off.

Joint frame: Maya joint X / Y / Z = bone Y / Z / X and a Blender local point (x, y, z) is Maya (x, z, -y),
so ``-r`` reads the CVs as bone-space (-y, x, z) = +90 deg about Z.
"""

import math

import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

COLLECTION = ".AllsetControlShapes"
MARK = "allset_control_shape"          # on a kit shape object: the bone it was made for ("<armature>/<bone>")
EMPTIED = "allset_shape_moved"         # on the empty transform left behind by -r
RELATIVE_TURN = Matrix.Rotation(math.radians(90.0), 4, 'Z')    # Maya joint frame -> bone space
_DROP_DATA_PROPS = ("allset_history", "allset_nurbs")          # creation node / Maya knots don't follow a baked copy


def warning_text(name):
    return f"Blender can't give {name} a shape: parent the curve to a joint or a curve"


# --- pure helpers ------------------------------------------------------------------------------------------------

def bone_space_matrix(curve_world, bone_world, relative):
    """Matrix taking the curve's data coordinates into the bone's space: ``-r`` = the CV local values read in the
    joint's Maya frame (the curve's own transform ignored), else world kept."""
    if relative:
        return RELATIVE_TURN.copy()
    return bone_world.inverted_safe() @ curve_world


def shape_local_matrix(pb):
    """Blender's Custom Shape display matrix in the bone's space (overlay_armature: translate, rotate, scale by
    custom scale x bone length when ``use_custom_shape_bone_size``)."""
    s = Vector(pb.custom_shape_scale_xyz)
    if pb.use_custom_shape_bone_size:
        s = s * pb.bone.length
    return Matrix.LocRotScale(Vector(pb.custom_shape_translation), Euler(pb.custom_shape_rotation_euler, 'XYZ'), s)


def shape_draw_matrix(arm, pb):
    """World matrix Blender draws ``pb``'s Custom Shape with."""
    src = pb.custom_shape_transform or pb
    return arm.matrix_world @ src.matrix @ shape_local_matrix(pb)


def _mesh_edges(ob, depsgraph):
    """Vertex coordinates (N x 3, object space) and edges (M x 2) of what ``ob`` evaluates to."""
    ev = ob
    if depsgraph is not None:
        try:
            ev = ob.evaluated_get(depsgraph)
        except (RuntimeError, ReferenceError):
            ev = ob
    try:
        me = ev.to_mesh()
    except RuntimeError:
        return np.zeros((0, 3)), np.zeros((0, 2), dtype=np.int64)
    try:
        if me is None:
            return np.zeros((0, 3)), np.zeros((0, 2), dtype=np.int64)
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        ed = np.empty(len(me.edges) * 2, dtype=np.int64)
        me.edges.foreach_get("vertices", ed)
    finally:
        ev.to_mesh_clear()
    return co.reshape(-1, 3), ed.reshape(-1, 2)


def shape_segments(arm, pb, depsgraph):
    """World-space segments (a, b: N x 3) of the Custom Shape wire Blender draws for ``pb``."""
    shape = pb.custom_shape
    if shape is None:
        return np.zeros((0, 3)), np.zeros((0, 3))
    co, ed = _mesh_edges(shape, depsgraph)
    if len(ed) == 0:
        return np.zeros((0, 3)), np.zeros((0, 3))
    m = np.array(shape_draw_matrix(arm, pb), dtype=np.float64)
    co = co @ m[:3, :3].T + m[:3, 3]
    return co[ed[:, 0]], co[ed[:, 1]]


def shows_custom_shapes(arm):
    return getattr(arm.data, "show_bone_custom_shapes", True)


def custom_shape_objects(data=None):
    """Every object used as a pose bone Custom Shape (kit controls, Rigify WGT objects ...)."""
    out = set()
    for ob in (data or bpy.data).objects:
        if ob.type != 'ARMATURE' or ob.pose is None:
            continue
        for pb in ob.pose.bones:
            if pb.custom_shape is not None:
                out.add(pb.custom_shape)
    return out


def is_rig_template(ob):
    """A Rigify metarig: its bones carry Rigify rig types (the template Generate builds the rig from, not a skeleton;
    its bones all deform, so an Export All wrote 159 more joints)."""
    if ob.type != 'ARMATURE' or ob.pose is None or ob.data.get("rig_id"):      # rig_id = a generated rig
        return False
    return any(getattr(pb, "rigify_type", None) or pb.get("rigify_type") for pb in ob.pose.bones)


def rig_templates(data=None):
    return {ob for ob in (data or bpy.data).objects if is_rig_template(ob)}


class excluded:
    """Context manager: every Custom Shape object (kit controls, Rigify WGT objects ...) is out of the scene's
    collections while a kit export runs (controls are not exported), then linked back in the
    same order with the same select / hide state. Rigify metarigs go out too."""

    def __init__(self, scene, view_layer):
        self.scene, self.view_layer = scene, view_layer
        self.colls = []

    def __enter__(self):
        shapes = custom_shape_objects() | rig_templates()
        if not shapes:
            return self
        vl = self.view_layer
        colls = [self.scene.collection] + list(self.scene.collection.children_recursive)
        self.active = vl.objects.active
        for coll in colls:
            hit = [o for o in coll.objects if o in shapes]
            if not hit:
                continue
            objects = list(coll.objects)
            order = objects[min(objects.index(o) for o in hit):]     # only the tail is linked again
            state = {}
            for o in order:
                try:
                    state[o.name] = (o.select_get(view_layer=vl), o.hide_get(view_layer=vl))
                except RuntimeError:
                    pass
            self.colls.append((coll, order, state))
            for o in hit:
                coll.objects.unlink(o)
        return self

    def __exit__(self, *exc):
        vl = self.view_layer
        for coll, order, state in self.colls:
            for o in order:
                if o.name in coll.objects:
                    coll.objects.unlink(o)
            for o in order:
                try:
                    coll.objects.link(o)
                except (RuntimeError, ReferenceError):
                    pass
        if self.colls:
            vl.update()
            for coll, order, state in self.colls:
                for o in order:
                    try:
                        sel, hid = state[o.name]
                        o.hide_set(hid, view_layer=vl)
                        o.select_set(sel, view_layer=vl)
                    except (KeyError, RuntimeError, ReferenceError):
                        pass
            if self.active is not None:
                try:
                    vl.objects.active = self.active
                except (RuntimeError, ReferenceError):
                    pass
        return False


# --- curve data ----------------------------------------------------------------------------------------------------

_SPLINE_ATTRS = ("order_u", "order_v", "resolution_u", "resolution_v", "use_cyclic_u", "use_cyclic_v",
                 "use_endpoint_u", "use_endpoint_v", "use_bezier_u", "use_bezier_v", "use_smooth", "tilt_interpolation",
                 "radius_interpolation", "material_index")


def append_splines(dst, src, matrix=None):
    """Copy every spline of curve ``src`` into curve ``dst`` (points mapped by ``matrix`` when given)."""
    m = matrix if matrix is not None else Matrix.Identity(4)
    for s in src.splines:
        n = dst.splines.new(s.type)
        if s.type == 'BEZIER':
            n.bezier_points.add(len(s.bezier_points) - 1)
            for a, b in zip(n.bezier_points, s.bezier_points):
                a.handle_left_type = a.handle_right_type = 'FREE'
                a.co = m @ b.co
                a.handle_left = m @ b.handle_left
                a.handle_right = m @ b.handle_right
                a.radius, a.tilt = b.radius, b.tilt
            for a, b in zip(n.bezier_points, s.bezier_points):
                a.handle_left_type, a.handle_right_type = b.handle_left_type, b.handle_right_type
        else:
            n.points.add(len(s.points) - 1)
            for a, b in zip(n.points, s.points):
                w = b.co[3]
                p = m @ Vector(b.co[:3])
                a.co = (p.x, p.y, p.z, w)
                a.weight, a.radius, a.tilt = b.weight, b.radius, b.tilt
        for attr in _SPLINE_ATTRS:
            try:
                setattr(n, attr, getattr(s, attr))
            except (AttributeError, TypeError, ValueError):
                pass


def _baked_copy(curve_ob, matrix):
    data = curve_ob.data.copy()
    for key in _DROP_DATA_PROPS:
        if key in data:
            del data[key]
    data.dimensions = '3D'
    data.transform(matrix)
    return data


def shape_collection():
    coll = bpy.data.collections.get(COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(COLLECTION)
    coll.use_fake_user = True
    coll.hide_render = True
    return coll


def kit_shape(pb):
    """``pb``'s Custom Shape when the kit made it (a control the next shape parenting adds to), else None."""
    shape = pb.custom_shape
    return shape if shape is not None and MARK in shape and shape.type == 'CURVE' else None


# --- the source transform afterwards --------------------------------------------------------------------------

def _drop(ob):
    data = ob.data
    bpy.data.objects.remove(ob)
    if data is not None and data.users == 0:
        bpy.data.curves.remove(data)


def _empty_in_place(ob):
    """Maya ``cmds.parent(shape=True, relative=True)``: the old transform stays, without a shape (an Empty with its
    name, channels, parent, children and collections)."""
    from . import units
    name, parent, inv = ob.name, ob.parent, ob.matrix_parent_inverse.copy()
    colls = list(ob.users_collection)
    empty = bpy.data.objects.new(name + ".allset_tmp", None)
    empty.empty_display_type = 'PLAIN_AXES'
    empty.empty_display_size = units.maya_unit()
    for key in ob.keys():
        if not key.startswith("allset_history"):
            empty[key] = ob[key]
    empty[EMPTIED] = True
    for coll in colls:
        coll.objects.link(empty)
    empty.parent = parent
    empty.matrix_parent_inverse = inv
    empty.rotation_mode = ob.rotation_mode
    for attr in ("location", "rotation_euler", "rotation_quaternion", "rotation_axis_angle", "scale",
                 "delta_location", "delta_rotation_euler", "delta_rotation_quaternion", "delta_scale",
                 "hide_viewport", "hide_render", "hide_select"):
        setattr(empty, attr, getattr(ob, attr))
    if ob.animation_data is not None and ob.animation_data.action is not None:
        empty.animation_data_create().action = ob.animation_data.action
    for child in list(ob.children):
        cinv = child.matrix_parent_inverse.copy()
        child.parent = empty
        child.matrix_parent_inverse = cinv
    selected = False
    try:
        selected = ob.select_get()
    except RuntimeError:
        pass
    _drop(ob)
    empty.name = name
    if selected:
        try:
            empty.select_set(True)
        except RuntimeError:
            pass
    return empty


def _finish_source(curve_ob, relative):
    # absolute: Maya deletes the transform it emptied (old_transform None); one with children stays
    if relative or curve_ob.children:
        return _empty_in_place(curve_ob)
    _drop(curve_ob)
    return None


# --- parent -s -----------------------------------------------------------------------------------------------------

def parent_shape(curve_ob, target, relative=True, replace=False):
    """Maya ``cmds.parent(curve, target, shape=True[, relative=True])``. ``target`` = a pose bone (its Custom Shape) or
    a curve object (the splines join it). Returns the shape object (bone) / target curve object; raises ValueError for
    any other target."""
    if curve_ob is None or curve_ob.type != 'CURVE':
        raise ValueError(f"{getattr(curve_ob, 'name', curve_ob)} has no curve shape")
    shape_name = curve_ob.data.name
    if isinstance(target, bpy.types.PoseBone):
        arm = target.id_data
        bone_world = arm.matrix_world @ target.matrix
        matrix = bone_space_matrix(curve_ob.matrix_world, bone_world, relative)
        data = _baked_copy(curve_ob, matrix)
        old = None if replace else kit_shape(target)
        if old is not None:
            append_splines(old.data, data)
            bpy.data.curves.remove(data)
            shape = old
        else:
            shape = bpy.data.objects.new(shape_name + ".allset_tmp", data)
            shape[MARK] = f"{arm.name}/{target.name}"
            shape.use_fake_user = True
            shape_collection().objects.link(shape)
            previous = target.custom_shape
            target.custom_shape = shape
            target.use_custom_shape_bone_size = False
            target.custom_shape_translation = (0.0, 0.0, 0.0)
            target.custom_shape_rotation_euler = (0.0, 0.0, 0.0)
            target.custom_shape_scale_xyz = (1.0, 1.0, 1.0)
            target.custom_shape_transform = None
            if previous is not None and MARK in previous and previous.users <= 2:
                # a replaced kit shape nothing else uses (users: the collection + fake user)
                pdata = previous.data
                bpy.data.objects.remove(previous)
                if pdata is not None and pdata.users == 0:
                    bpy.data.curves.remove(pdata)
        _finish_source(curve_ob, relative)
        if shape is not old:
            # the Maya shape keeps its name (ctrl_circleShape) once the source's data is gone
            left = bpy.data.curves.get(shape_name)
            if left is not None and left is not shape.data and left.users == 0:
                bpy.data.curves.remove(left)
            shape.data.name = shape_name
            shape.name = shape_name
        arm.update_tag()
        return shape
    if isinstance(target, bpy.types.Object) and target.type == 'CURVE':
        if target == curve_ob:
            raise ValueError(f"{target.name} is the curve itself")
        matrix = Matrix.Identity(4) if relative else target.matrix_world.inverted_safe() @ curve_ob.matrix_world
        target.data.dimensions = '3D'
        append_splines(target.data, curve_ob.data, matrix)
        _finish_source(curve_ob, relative)
        target.update_tag()
        return target
    name = target.name if hasattr(target, "name") else str(target)
    raise ValueError(warning_text(name))


def _selected_curves(context, exclude=None):
    return [o for o in context.selected_objects if o.type == 'CURVE' and o is not exclude
            and MARK not in o]


class ALLSET_OT_parent_shape(bpy.types.Operator):
    """Give the active joint (or curve) the selected curves' shapes (Maya parent -s -r): the curve becomes the joint's
    control shape"""
    bl_idname = "allset.parent_shape"
    bl_label = "Parent Shape"
    bl_options = {'REGISTER', 'UNDO'}

    relative: bpy.props.BoolProperty(name="Relative", default=True, options={'HIDDEN', 'SKIP_SAVE'})
    replace: bpy.props.BoolProperty(name="Replace", default=False, options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        from .. import results
        act = context.active_object
        target = None
        if act is not None and act.type == 'ARMATURE' and act.mode == 'POSE':
            target = context.active_pose_bone
            if target is None:
                self.report({'WARNING'}, warning_text(act.name))
                return {'CANCELLED'}
        elif act is not None:
            target = act
        curves = _selected_curves(context, exclude=act)
        if target is None or not curves:
            self.report({'WARNING'}, "Select the curves, then the joint or curve to give their shapes to")
            return {'CANCELLED'}
        if not (isinstance(target, bpy.types.PoseBone) or target.type == 'CURVE'):
            self.report({'WARNING'}, warning_text(target.name))
            return {'CANCELLED'}
        names = []
        for i, curve in enumerate(curves):
            name = curve.data.name
            parent_shape(curve, target, relative=self.relative, replace=self.replace and i == 0)
            names.append(name)
        results.result(self, " ".join(names))
        return {'FINISHED'}


classes = (ALLSET_OT_parent_shape,)


def register_props():
    pass


def unregister_props():
    pass
