# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Modify menu commands: Convert > Smooth Mesh Preview to Polygons, Transformation Tools > Default
Object Manipulator / Show Manipulator Tool, Align Tool, Snap Align Objects > Position Along Curve, Convert >
Geometry to Bounding Box and the Evaluate Nodes check items.

Maya 2022 rules. Option window of Geometry to
Bounding Box: operators/option_windows_modify.py.
"""

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatVectorProperty, IntProperty, StringProperty
from mathutils import Matrix, Vector

from .. import results
from .. import undo_steps


# --- Convert > Smooth Mesh Preview to Polygons ------------------------------

WARN_NO_PREVIEW = "No polygonal objects selected were in smooth preview mode."   #
WARN_NO_POLYS = "No polygonal objects selected."


def in_preview(ob):
    """True when the mesh shows the kit's smooth mesh preview (Maya displaySmoothMesh 1 or 2 = keys 2 / 3)."""
    from .display import preview_modifier
    mod = preview_modifier(ob, create=False) if ob.type == 'MESH' else None
    return mod is not None and mod.show_viewport


def smooth_to_polygons(context, obs):
    """Apply only the preview modifiers of ``obs`` (operators/display.py: shading nodes + Subsurf) at their place in
    the stack; every other modifier (Armature = skinCluster, kit deformers, history) stays. Returns (converted,
    problems): problems = (object name, reason) Blender refused."""
    from . import display
    done, problems = [], []
    for ob in obs:
        if not in_preview(ob):
            continue
        if ob.data.users > 1:
            problems.append((ob.name, "its mesh is shared by other objects"))
            continue
        if ob.data.shape_keys is not None:
            problems.append((ob.name, "Blender can't apply a subdivision to a mesh with shape keys"))
            continue
        for name in (display.PREVIEW_SHADE_NAME, display.PREVIEW_MOD_NAME):
            mod = ob.modifiers.get(name)
            if mod is None:
                continue
            mod.show_viewport = True
            # Blender applies a modifier that isn't first to the base mesh (earlier modifiers are not baked in) and
            # carries vertex groups through the Subsurf, so an Armature before it keeps deforming the dense mesh
            # (Maya: polySmoothFace after skinCluster1).
            with context.temp_override(object=ob, active_object=ob, selected_objects=[ob],
                                       selected_editable_objects=[ob]):
                bpy.ops.object.modifier_apply(modifier=name, report=False)
        if ob.get(display._WIRE_FLAG):        # display mode 2 drew the cage as wireframe
            ob.show_wire = False
            del ob[display._WIRE_FLAG]
        done.append(ob)
    return done, problems


@undo_steps.no_redo_panel
class ALLSET_OT_smooth_to_polygons(bpy.types.Operator):
    """Turn the smooth mesh preview of the selected meshes into real polygons; other history stays
    (Maya Modify > Convert > Smooth Mesh Preview to Polygons)"""
    bl_idname = "allset.smooth_to_polygons"
    bl_label = "Smooth Mesh Preview to Polygons"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode in ('OBJECT', 'EDIT_MESH')

    def execute(self, context):
        edit = context.mode == 'EDIT_MESH'
        obs = list(context.objects_in_mode) if edit else list(context.selected_objects)
        meshes = [ob for ob in obs if ob.type == 'MESH']
        if not meshes:
            self.report({'WARNING'}, WARN_NO_POLYS)
            return {'CANCELLED'}
        if not any(in_preview(ob) for ob in meshes):
            self.report({'WARNING'}, WARN_NO_PREVIEW)
            return {'CANCELLED'}
        if edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        try:
            done, problems = smooth_to_polygons(context, meshes)
        finally:
            if edit:
                bpy.ops.object.mode_set(mode='EDIT')
        for name, why in problems:
            self.report({'WARNING'}, f"{name}: not converted, {why}.")
        if not done:
            return {'CANCELLED'}
        results.result(self, " ".join(ob.name for ob in done))
        return {'FINISHED'}


# --- Transformation Tools > Default Object Manipulator / Show Manipulator Tool ----------------

MANIP_PROP = "allset_manip_default"           # Maya showManipDefault: 0 None, 1 Move, 2 Rotate, 3 Scale, 4 Transform
MANIP_TOOLS = {1: "builtin.move", 2: "builtin.rotate", 3: "builtin.scale", 4: "builtin.transform"}
MANIP_ITEMS = (('0', "None", ""), ('1', "Move", ""), ('2', "Rotate", ""), ('3', "Scale", ""), ('4', "Transform", ""))


def manip_default(ob):
    return int(ob.get(MANIP_PROP, 0)) if ob is not None else 0


def show_manip_tool(ob):
    """The tool the Show Manipulator Tool gives ``ob``: its Default Object Manipulator, else Transform (the kit's T:
    Blender has no node-specific manipulators)."""
    return MANIP_TOOLS.get(manip_default(ob), "builtin.transform")


@undo_steps.no_redo_panel
class ALLSET_OT_default_manip(bpy.types.Operator):
    """Set which manipulator the Show Manipulator Tool gives the selected objects
    (Maya Modify > Transformation Tools > Default Object Manipulator)"""
    bl_idname = "allset.default_manip"
    bl_label = "Default Object Manipulator"
    bl_options = {'REGISTER', 'UNDO'}

    value: IntProperty(min=0, max=4, options={'SKIP_SAVE'})

    def execute(self, context):
        obs = list(context.selected_objects)
        if not obs:
            self.report({'WARNING'}, "No objects selected.")     # Maya's warning text
            return {'CANCELLED'}
        for ob in obs:
            if self.value:
                ob[MANIP_PROP] = self.value
            elif MANIP_PROP in ob:
                del ob[MANIP_PROP]
        return {'FINISHED'}


class ALLSET_OT_show_manipulator(bpy.types.Operator):
    """The manipulator of the lead object: its Default Object Manipulator, else the Transform tool
    (Maya Modify > Transformation Tools > Show Manipulator Tool)"""
    bl_idname = "allset.show_manipulator"
    bl_label = "Show Manipulator Tool"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def execute(self, context):
        bpy.ops.wm.tool_set_by_id(name=show_manip_tool(context.view_layer.objects.active))
        return {'FINISHED'}


# --- Align Tool ----------------------------------------------------------------------------

def align_to_lead(context, axis, mode):
    """Line the selected objects up with the lead's world bounding box (min / mid / max) along world ``axis``."""
    from .snap_align import bbox_world
    lead = context.view_layer.objects.active
    others = [ob for ob in context.selected_objects if ob is not lead]
    if lead is None or not others:
        return 0

    def key(bb):
        lo, hi = bb
        return lo[axis] if mode == 'MIN' else hi[axis] if mode == 'MAX' else (lo[axis] + hi[axis]) / 2

    target = key(bbox_world(lead))
    for ob in others:
        d = Vector((0.0, 0.0, 0.0))
        d[axis] = target - key(bbox_world(ob))
        ob.matrix_world = Matrix.Translation(d) @ ob.matrix_world
    return len(others)


@undo_steps.no_redo_panel
class ALLSET_OT_align_to_lead(bpy.types.Operator):
    """Line the selection up with the last selected object along this axis (Maya Align Tool handle)"""
    bl_idname = "allset.align_to_lead"
    bl_label = "Align"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    axis: IntProperty(min=0, max=2, options={'SKIP_SAVE'})
    mode: EnumProperty(items=(('MIN', "Min", ""), ('MID', "Mid", ""), ('MAX', "Max", "")), default='MID',
                       options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        if not align_to_lead(context, self.axis, self.mode):
            self.report({'WARNING'}, "Align Tool: select two or more objects; the last selected one stays.")
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_align_tool(bpy.types.Operator):
    """Align the selected objects to the last selected one: pick an axis and Min / Mid / Max
    (Maya Modify > Align Tool)"""
    bl_idname = "allset.align_tool"
    bl_label = "Align Tool"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        return self.invoke(context, None)

    def invoke(self, context, _event):
        if len(context.selected_objects) < 2:
            self.report({'WARNING'}, "Align Tool: select two or more objects; the last selected one stays.")
            return {'CANCELLED'}
        if bpy.app.background:
            return {'FINISHED'}
        return context.window_manager.invoke_popup(self, width=220)

    def draw(self, context):
        col = self.layout.column()
        col.label(text="Align Tool: to the last selected object")
        for axis, name in enumerate("XYZ"):
            row = col.row(align=True)
            row.label(text=f"{name}")
            for mode, text in (('MIN', "Min"), ('MID', "Mid"), ('MAX', "Max")):
                op = row.operator(ALLSET_OT_align_to_lead.bl_idname, text=text)
                op.axis, op.mode = axis, mode


# --- Snap Align Objects > Position Along Curve ----------------------------------------------

ERR_NO_CURVE = "Position Along Curve: No curve selected to position along"
ERR_SELECTION = "Position Along Curve: Nothing selected. Select a curve and two or more nodes."


def selection_order(context):
    """Selected objects in Maya selection order as far as Blender knows it: Blender keeps no order, the active object
    is the last one picked, the others go by name (operators/curve_tools._curves, mesh_maya._first_selected)."""
    lead = context.view_layer.objects.active
    obs = sorted((ob for ob in context.selected_objects if ob is not lead), key=lambda o: o.name)
    if lead is not None and lead.select_get():
        obs.append(lead)
    return obs


def curve_point(ob, fraction):
    """World point at parameter percentage ``fraction`` of the first spline of curve object ``ob`` (Maya pointOnCurve
    -turnOnPercentage: the parameter, not arc length)."""
    from . import curves_maya, curves_math
    sp = ob.data.splines[0]
    mc = curves_maya.read_spline(sp, ob.matrix_world)
    p = mc.degree
    knots = mc.knots
    full = curves_math.full(knots)
    lo, hi = full[p], full[len(mc.cvs)]
    return Vector(curves_math.evaluate(mc.cvs, knots, mc.degree, lo + (hi - lo) * fraction, mc.weights))


def position_along_curve(objects):
    """objects in selection order; the curve = the last curve object. Returns the moved objects; raises ValueError
    with Maya's message."""
    if len(objects) <= 2:
        raise ValueError(ERR_SELECTION)
    curves = [ob for ob in objects if ob.type == 'CURVE' and ob.data.splines]
    if not curves:
        raise ValueError(ERR_NO_CURVE)
    curve = curves[-1]
    rest = [ob for ob in objects if ob is not curve]
    n = len(rest)
    if n < 2:
        return []
    for i, ob in enumerate(rest):
        mw = ob.matrix_world.copy()
        mw.translation = curve_point(curve, i / (n - 1))   # the Maya pivot (object origin) onto the point
        ob.matrix_world = mw
    return rest


@undo_steps.no_redo_panel
class ALLSET_OT_position_along_curve(bpy.types.Operator):
    """Space the selected objects along the selected curve by its parameter (rebuild the curve for even spacing)
    (Maya Modify > Snap Align Objects > Position Along Curve)"""
    bl_idname = "allset.position_along_curve"
    bl_label = "Position Along Curve"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        try:
            position_along_curve(selection_order(context))
        except ValueError as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        return {'FINISHED'}


# --- Convert > Geometry to Bounding Box ----------------------------------------------------

BBOX_FACES = ((0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0))


def _box_mesh(name, lo, hi):
    """A 6-face box mesh from ``lo`` to ``hi`` (outward normals)."""
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, z)) for (x, y, z) in (
        (lo[0], lo[1], lo[2]), (hi[0], lo[1], lo[2]), (hi[0], hi[1], lo[2]), (lo[0], hi[1], lo[2]),
        (lo[0], lo[1], hi[2]), (hi[0], lo[1], hi[2]), (hi[0], hi[1], hi[2]), (lo[0], hi[1], hi[2]))]
    for f in BBOX_FACES:
        bm.faces.new([vs[i] for i in reversed(f)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def _bbox_material(colour):
    from . import material, naming
    taken = {m.name for m in bpy.data.materials}
    mat = material.new_material('LAMBERT')
    mat.name = f"BBoxLambert{naming.next_number('BBoxLambert', taken)}"
    material.color_socket(mat).default_value = (*colour, 1.0)     # Maya Color; diffuse 0.8 stays
    material._sync_base(mat)
    material.sync_display(mat)
    return mat


def _top_selected(objects):
    chosen = set(objects)
    out = []
    for ob in objects:
        p = ob.parent
        while p is not None and p not in chosen:
            p = p.parent
        if p is None:
            out.append(ob)
    return out


def _meshes_below(ob):
    return [o for o in [ob, *ob.children_recursive] if o.type == 'MESH']


def _world_box(obs):
    from .snap_align import bbox_world
    boxes = [bbox_world(o) for o in obs]
    lo = Vector(tuple(min(b[0][i] for b in boxes) for i in range(3)))
    hi = Vector(tuple(max(b[1][i] for b in boxes) for i in range(3)))
    return lo, hi


def geometry_to_bbox(context, objects, name="", suffix="_BBox", per_shape=False, colour=(0.5, 0.5, 0.5),
                     keep_original=False):
    """Maya geomToBBox: one box per selected hierarchy (``per_shape``: per mesh). A lone mesh keeps its object-space
    box and transform; a hierarchy gets a world-axis box with an identity transform. Returns the new boxes."""
    from . import dag
    tops = [ob for ob in _top_selected(objects) if _meshes_below(ob)]
    if not tops:
        return []
    mat = _bbox_material(colour)
    made = []

    def add(base, lo, hi, matrix, coll):
        label = f"{name or base}{suffix}"
        me = _box_mesh(f"{label}Shape", lo, hi)
        me.materials.append(mat)
        ob = bpy.data.objects.new(label, me)
        ob.matrix_world = matrix
        coll.objects.link(ob)
        made.append(ob)

    for top in tops:
        coll = top.users_collection[0] if top.users_collection else context.scene.collection
        meshes = _meshes_below(top)
        if per_shape:
            for m in meshes:
                bb = m.bound_box
                add(m.name, Vector(bb[0]), Vector(bb[6]), m.matrix_world.copy(), coll)
        elif meshes == [top] and not top.children:
            bb = top.bound_box
            add(top.name, Vector(bb[0]), Vector(bb[6]), top.matrix_world.copy(), coll)
        else:
            lo, hi = _world_box(meshes)
            add(top.name, lo, hi, Matrix.Identity(4), coll)
    if not keep_original:
        dag.delete_hierarchy(context, tops)
    for ob in context.view_layer.objects:
        if ob is not None and ob.select_get():
            ob.select_set(False)
    for ob in made:
        try:
            ob.select_set(True)
        except RuntimeError:
            pass
    context.view_layer.objects.active = made[0]
    return made


@undo_steps.no_redo_panel
class ALLSET_OT_geometry_to_bbox(bpy.types.Operator):
    """Replace the selected geometry with its bounding box (Maya Modify > Convert > Geometry to Bounding Box)"""
    bl_idname = "allset.geometry_to_bbox"
    bl_label = "Geometry to Bounding Box"
    bl_options = {'REGISTER', 'UNDO'}

    name: StringProperty(name="Name", options={'SKIP_SAVE'})
    suffix: StringProperty(name="Name suffix", default="_BBox", options={'SKIP_SAVE'})
    per_shape: BoolProperty(name="One bounding box per shape", options={'SKIP_SAVE'})
    colour: FloatVectorProperty(name="Color", size=3, default=(0.5, 0.5, 0.5), subtype='COLOR', min=0.0, max=1.0,
                                options={'SKIP_SAVE'})
    keep_original: BoolProperty(name="Keep original", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        made = geometry_to_bbox(context, list(context.selected_objects), self.name, self.suffix, self.per_shape,
                                tuple(self.colour), self.keep_original)
        if not made:
            self.report({'WARNING'}, "Geometry to Bounding Box: select geometry first.")
            return {'CANCELLED'}
        results.result(self, " ".join(ob.name for ob in made))
        return {'FINISHED'}


# --- Evaluate Nodes --------------------------------------------------------------------------
# Maya: check items turning every node of that type on / off. Kit: Scene.allset_eval (saved with
# the file), each switch mutes / unmutes the Blender data standing for that Maya node type.

KINDS = ("iksolver", "constraint", "expression", "fluid", "ncloth", "nparticle", "nrigid", "particle", "rigidbody",
         "snapshot")   # snapshot = the kit snapshots' automatic updates (operators/anim_snapshot.evaluating)
_IK_MUTED = "allset_eval_ik_muted"          # scene ID prop: IK constraints the kit muted (IK Solvers off)
_IK_TYPES = {'IK', 'SPLINE_IK'}


def _constraint_owners(scene):
    for ob in scene.objects:
        yield ob, None, ob.constraints
        if ob.type == 'ARMATURE' and ob.pose is not None:
            for pb in ob.pose.bones:
                yield ob, pb.name, pb.constraints


def _set_ik(scene, on):
    if not on:
        muted = []
        for ob, bone, cons in _constraint_owners(scene):
            for con in cons:
                if con.type in _IK_TYPES and not con.mute:
                    con.mute = True
                    muted.append("\x1f".join((ob.name, bone or "", con.name)))
        scene[_IK_MUTED] = muted
        return
    keys = set(scene.get(_IK_MUTED, ()))
    for ob, bone, cons in _constraint_owners(scene):
        for con in cons:
            if con.type in _IK_TYPES and "\x1f".join((ob.name, bone or "", con.name)) in keys:
                con.mute = False
    if _IK_MUTED in scene:
        del scene[_IK_MUTED]


def _set_constraints(scene, on):
    for _ob, _bone, cons in _constraint_owners(scene):
        for con in cons:
            if con.type not in _IK_TYPES:
                con.mute = not on


def _driver_owners():
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.shape_keys, bpy.data.materials, bpy.data.node_groups,
                 bpy.data.armatures, bpy.data.cameras, bpy.data.lights, bpy.data.curves, bpy.data.lattices,
                 bpy.data.worlds, bpy.data.scenes):
        for idb in coll:
            ad = getattr(idb, "animation_data", None)
            if ad is not None:
                yield ad


def _set_expressions(_scene, on):
    from .driven_key import VAR
    for ad in _driver_owners():
        for fc in ad.drivers:
            if any(v.name == VAR for v in fc.driver.variables):    # Set Driven Key: animCurves in Maya
                continue
            fc.mute = not on


def _modifiers(scene, mtype):
    for ob in scene.objects:
        for mod in ob.modifiers:
            if mod.type == mtype:
                yield ob, mod


def _set_fluid(scene, on):
    for _ob, mod in _modifiers(scene, 'FLUID'):
        mod.show_viewport = on


def _set_cloth(scene, on):
    for _ob, mod in _modifiers(scene, 'CLOTH'):
        mod.show_viewport = on
        mod.show_render = on


def _is_nparticle(mod):
    ps = getattr(mod, "particle_system", None)
    return ps is not None and ps.settings is not None and ps.settings.name.startswith("nParticle")


def _set_particles(scene, on, n):
    for _ob, mod in _modifiers(scene, 'PARTICLE_SYSTEM'):
        if _is_nparticle(mod) == n:
            mod.show_viewport = on
            mod.show_render = on


def _set_nrigid(scene, on):
    for ob, _mod in _modifiers(scene, 'COLLISION'):
        if ob.collision is not None:
            ob.collision.use = on


def _set_rigidbody(scene, on):
    world = scene.rigidbody_world
    if world is not None:
        world.enabled = on


APPLY = {"iksolver": _set_ik, "constraint": _set_constraints, "expression": _set_expressions, "fluid": _set_fluid,
         "ncloth": _set_cloth, "nparticle": lambda s, on: _set_particles(s, on, True), "nrigid": _set_nrigid,
         "particle": lambda s, on: _set_particles(s, on, False), "rigidbody": _set_rigidbody,
         "snapshot": lambda s, on: None}   # read by anim_snapshot when a source changes


def _update(kind):
    def update(self, context):
        scene = self.id_data
        APPLY[kind](scene, getattr(self, kind))
        if context is not None and context.view_layer is not None:
            context.view_layer.update()
    return update


class ALLSET_PG_evaluate_nodes(bpy.types.PropertyGroup):
    iksolver: BoolProperty(name="IK Solvers", default=True, update=_update("iksolver"))
    constraint: BoolProperty(name="Constraints", default=True, update=_update("constraint"))
    expression: BoolProperty(name="Expressions", default=True, update=_update("expression"))
    fluid: BoolProperty(name="Fluids", default=True, update=_update("fluid"))
    ncloth: BoolProperty(name="nCloths", default=True, update=_update("ncloth"))
    nparticle: BoolProperty(name="nParticles", default=True, update=_update("nparticle"))
    nrigid: BoolProperty(name="nRigids", default=True, update=_update("nrigid"))
    particle: BoolProperty(name="Particles", default=True, update=_update("particle"))
    rigidbody: BoolProperty(name="Rigid Bodies", default=True, update=_update("rigidbody"))
    snapshot: BoolProperty(name="Snapshots", default=True, update=_update("snapshot"))


def set_all(scene, on):
    """Evaluate All / Ignore All: every switch (each one applies)."""
    ev = scene.allset_eval
    for kind in KINDS:
        if getattr(ev, kind) != on:
            setattr(ev, kind, on)
        else:
            APPLY[kind](scene, on)


@undo_steps.no_redo_panel
class ALLSET_OT_evaluate_all(bpy.types.Operator):
    """Evaluate (on) or ignore (off) every IK solver, constraint, driver and simulation
    (Maya Modify > Evaluate Nodes > Evaluate All / Ignore All)"""
    bl_idname = "allset.evaluate_all"
    bl_label = "Evaluate All"
    bl_options = {'REGISTER', 'UNDO'}

    on: BoolProperty(default=True, options={'SKIP_SAVE'})

    def execute(self, context):
        set_all(context.scene, self.on)
        context.view_layer.update()
        return {'FINISHED'}


# --- Modify > Reorder Rotation... (Maya keeps the orientation, preserve on) -----------------------------------------

# Maya rotateOrder names = Blender's Euler modes of the same names (command_line/cmds_shim.ROTATE_ORDERS).
REORDER_ITEMS = tuple((m, m.lower(), f"Maya rotate order {m.lower()}") for m in ('XYZ', 'YZX', 'ZXY', 'XZY', 'YXZ', 'ZYX'))


def _rotation_matrix(node):
    mode = node.rotation_mode
    if mode == 'QUATERNION':
        return node.rotation_quaternion.normalized().to_matrix()
    if mode == 'AXIS_ANGLE':
        from mathutils import Quaternion
        angle, *axis = node.rotation_axis_angle
        return Quaternion(Vector(axis), angle).to_matrix()
    return node.rotation_euler.to_matrix()


def reorder_rotation(nodes, order):
    """Change the rotate order of objects / pose bones keeping their orientation (Maya's -preserve): setting
    rotation_mode from Python only reinterprets the values, so the Euler angles are recomputed
    from the old rotation, closest to the old angles. Keys are left as they are. Returns how many changed."""
    n = 0
    for node in nodes:
        if node.rotation_mode == order:
            continue
        m = _rotation_matrix(node)
        old = node.rotation_euler.copy()
        node.rotation_mode = order
        node.rotation_euler = m.to_euler(order, old)
        n += 1
    return n


class ALLSET_OT_reorder_rotation(bpy.types.Operator):
    """Change the rotate order of the selected objects / joints, keeping their orientation (Maya Modify > Reorder
    Rotation)"""
    bl_idname = "allset.reorder_rotation"
    bl_label = "Reorder Rotation"
    bl_options = {'REGISTER', 'UNDO'}

    order: EnumProperty(items=REORDER_ITEMS, name="Rotate order", default='XYZ')

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects) or bool(getattr(context, "selected_pose_bones", None))

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, title="Reorder Rotation", confirm_text="Reorder")

    def execute(self, context):
        nodes = list(context.selected_pose_bones or ()) if context.mode == 'POSE' else list(context.selected_objects)
        n = reorder_rotation(nodes, self.order)
        results.result(self, f"Rotate order {self.order.lower()} on {n} node(s)")
        return {'FINISHED'}


classes = (ALLSET_OT_smooth_to_polygons, ALLSET_OT_default_manip, ALLSET_OT_show_manipulator,
           ALLSET_OT_align_to_lead, ALLSET_OT_align_tool, ALLSET_OT_position_along_curve, ALLSET_OT_geometry_to_bbox,
           ALLSET_PG_evaluate_nodes, ALLSET_OT_evaluate_all, ALLSET_OT_reorder_rotation)


def register_props():
    bpy.types.Scene.allset_eval = bpy.props.PointerProperty(type=ALLSET_PG_evaluate_nodes)


def unregister_props():
    del bpy.types.Scene.allset_eval
