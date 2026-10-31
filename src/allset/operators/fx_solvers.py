# SPDX-License-Identifier: GPL-3.0-or-later
"""More Maya Fields/Solvers items on Blender's own systems (#123):

- Initial State > Clear Initial State: the cloth / soft body mesh and rigid body transform go back to how they were
  before the first Set for Selected / Set for All Dynamic / Set From Mesh;
- Initial State > Set From Mesh: the cloth starts from the shape of a selected mesh with the same vertex count;
- Set Rigid Body Interpenetration / Collision: the selected rigid bodies (two or more) pass through each other / collide
  again, pair by pair, like Maya. Blender does this with a Generic rigid body constraint that has no limits and
  Disable Collisions on (one small empty per pair);
- Assign to Selected: the selected dynamic objects react only to the selected fields (their Effector Collection);
- Use Selected as Source: the selected object carries the field (Blender's force field on the object itself).
"""

import bpy
from bpy.props import BoolProperty
from mathutils import Matrix

from .. import results
from . import fx_more, naming

NO_COLLIDE = "allset_no_collide"      # object ID property of the kit's no-collision constraint empties
FIELDS = "allset_fields_of"           # collection ID property: the object whose fields it lists
NO_COLLIDE_BASE = "rigidInterpenetrate"


# --- Initial State ----------------------------------------------------------------------------------------------------

def clear_initial_state(context, obs):
    """Bring back the shape / transform kept by ``fx_more.keep_input``. Returns the objects changed."""
    done = []
    for ob in obs:
        if ob.type == 'MESH':
            at = ob.data.attributes.get(fx_more.INPUT_CO)
            if at is not None and len(at.data) == len(ob.data.vertices):
                co = [0.0] * (3 * len(ob.data.vertices))
                at.data.foreach_get("vector", co)
                ob.data.vertices.foreach_set("co", co)
                if ob.data.shape_keys is not None:
                    ob.data.shape_keys.reference_key.data.foreach_set("co", co)
                ob.data.attributes.remove(at)
                ob.data.update()
                for md in ob.modifiers:
                    if md.type in {'CLOTH', 'SOFT_BODY'}:
                        fx_more._reset_cache(md.point_cache)
                done.append(ob)
                continue
        if fx_more.INPUT_MATRIX in ob:
            m = list(ob[fx_more.INPUT_MATRIX])
            ob.matrix_basis = Matrix([m[0:4], m[4:8], m[8:12], m[12:16]])
            del ob[fx_more.INPUT_MATRIX]
            done.append(ob)
    world = context.scene.rigidbody_world
    if world is not None and world.point_cache is not None and any(o.rigid_body for o in done):
        fx_more._reset_cache(world.point_cache)
    return done


class ALLSET_OT_fx_clear_initial_state(bpy.types.Operator):
    """Put the selected cloth, soft body and rigid body objects back to how they were before their initial state was
    set (Maya Initial State > Clear Initial State)"""
    bl_idname = "allset.fx_clear_initial_state"
    bl_label = "Clear Initial State"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        done = clear_initial_state(context, list(context.selected_objects))
        if not done:
            self.report({'WARNING'}, "No selected object has an initial state to clear")
            return {'CANCELLED'}
        results.result(self, f"Initial state cleared for {len(done)} object(s)")
        return {'FINISHED'}


def start_from_mesh(cloth, source):
    """Write ``source``'s vertex positions (world space, then into ``cloth``'s space) as the cloth's start shape.
    False when the vertex counts differ."""
    if cloth.type != 'MESH' or source.type != 'MESH' or len(cloth.data.vertices) != len(source.data.vertices):
        return False
    fx_more.keep_input(cloth)
    to_local = cloth.matrix_world.inverted() @ source.matrix_world
    co = []
    for v in source.data.vertices:
        co.extend(to_local @ v.co)
    cloth.data.vertices.foreach_set("co", co)
    if cloth.data.shape_keys is not None:
        cloth.data.shape_keys.reference_key.data.foreach_set("co", co)
    cloth.data.update()
    for md in cloth.modifiers:
        if md.type in {'CLOTH', 'SOFT_BODY'}:
            fx_more._reset_cache(md.point_cache)
    return True


def _is_cloth(ob):
    return ob.type == 'MESH' and any(md.type in {'CLOTH', 'SOFT_BODY'} for md in ob.modifiers)


class ALLSET_OT_fx_start_from_mesh(bpy.types.Operator):
    """Start the selected nCloth from the shape of the other selected mesh, which needs the same vertex count (Maya
    Initial State > Set From Mesh)"""
    bl_idname = "allset.fx_start_from_mesh"
    bl_label = "Set From Mesh"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        sel = list(context.selected_objects)
        cloths = [o for o in sel if _is_cloth(o)]
        sources = [o for o in sel if o.type == 'MESH' and not _is_cloth(o)]
        if not cloths or not sources:
            self.report({'WARNING'}, "Select an nCloth and a mesh with the same topology")
            return {'CANCELLED'}
        done = [c for c in cloths if start_from_mesh(c, sources[0])]
        if not done:
            self.report({'WARNING'}, "The mesh needs the same number of vertices as the nCloth")
            return {'CANCELLED'}
        results.result(self, f"Start shape of {len(done)} nCloth(s) set from {sources[0].name}")
        return {'FINISHED'}


# --- Rigid body interpenetration --------------------------------------------------------------------------------------

def no_collide_empties(scene):
    return [o for o in scene.objects if o.get(NO_COLLIDE) and o.rigid_body_constraint is not None]


def _pair(o):
    c = o.rigid_body_constraint
    return {c.object1, c.object2}


def set_interpenetrate(context, bodies, on):
    """Pairwise among ``bodies``: ``on`` = add a no-collision constraint where a pair has none, else remove the
    kit's ones between them. Returns the number of pairs changed."""
    scene = context.scene
    existing = no_collide_empties(scene)
    changed = 0
    if not on:
        names = {b.name for b in bodies}
        for o in existing:
            if {x.name for x in _pair(o) if x is not None} <= names:
                bpy.data.objects.remove(o)
                changed += 1
        return changed
    have = [_pair(o) for o in existing]
    taken = {o.name for o in bpy.data.objects}
    for i, a in enumerate(bodies):
        for b in bodies[i + 1:]:
            if {a, b} in have:
                continue
            n = naming.next_number(NO_COLLIDE_BASE, taken)
            name = f"{NO_COLLIDE_BASE}{n}"
            taken.add(name)
            em = bpy.data.objects.new(name, None)
            em.empty_display_size = 0.1 * max(a.dimensions.length, b.dimensions.length, 1e-3)
            em.location = (a.matrix_world.translation + b.matrix_world.translation) / 2.0
            em.hide_render = True
            em[NO_COLLIDE] = True
            scene.collection.objects.link(em)
            with context.temp_override(object=em, active_object=em, selected_objects=[em],
                                       selected_editable_objects=[em]):
                bpy.ops.rigidbody.constraint_add(type='GENERIC')
            c = em.rigid_body_constraint
            c.object1, c.object2 = a, b
            c.disable_collisions = True
            have.append({a, b})
            changed += 1
    return changed


class ALLSET_OT_fx_rigid_interpenetrate(bpy.types.Operator):
    """Let the selected rigid bodies pass through each other, or collide again (Maya Set Rigid Body Interpenetration /
    Set Rigid Body Collision: Blender turns collisions off for each pair with a Generic rigid body constraint that
    has no limits)"""
    bl_idname = "allset.fx_rigid_interpenetrate"
    bl_label = "Set Rigid Body Interpenetration"
    bl_options = {'REGISTER', 'UNDO'}

    on: BoolProperty(name="Interpenetrate", default=True, options={'SKIP_SAVE'})

    def execute(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bodies = sorted((o for o in context.selected_objects if o.rigid_body is not None), key=lambda o: o.name)
        if len(bodies) < 2:
            self.report({'WARNING'}, "Select at least two rigid bodies")
            return {'CANCELLED'}
        if context.scene.rigidbody_world is None:
            bpy.ops.rigidbody.world_add()
        n = set_interpenetrate(context, bodies, self.on)
        what = "pass through each other" if self.on else "collide"
        results.result(self, f"{len(bodies)} rigid bodies {what} ({n} pair(s) changed)")
        return {'FINISHED'}


# --- Fields -----------------------------------------------------------------------------------------------------------

def is_field(ob):
    return ob.field is not None and ob.field.type != 'NONE'


def effector_weights(ob):
    """The effector weights of each simulation on ``ob`` (cloth, soft body, particle systems)."""
    out = []
    for md in ob.modifiers:
        if md.type == 'CLOTH':
            out.append(md.settings.effector_weights)
        elif md.type == 'SOFT_BODY':
            out.append(md.settings.effector_weights)
    for ps in getattr(ob, "particle_systems", ()):
        out.append(ps.settings.effector_weights)
    return out


def fields_collection(ob):
    """The kit collection listing the fields ``ob`` reacts to (made on first use, kept by a fake user)."""
    for coll in bpy.data.collections:
        if coll.get(FIELDS) == ob.name:
            return coll
    coll = bpy.data.collections.new(f"{ob.name}Fields")
    coll[FIELDS] = ob.name
    coll.use_fake_user = True
    return coll


def assign_fields(fields, targets):
    """Each target reacts to ``fields`` (added to what it already listed). Returns the targets changed."""
    done = []
    for ob in targets:
        weights = effector_weights(ob)
        if not weights:
            continue
        coll = fields_collection(ob)
        for f in fields:
            if f.name not in coll.objects:
                coll.objects.link(f)
        for w in weights:
            w.collection = coll
        done.append(ob)
    return done


class ALLSET_OT_fx_assign_fields(bpy.types.Operator):
    """The selected cloth, soft body and particle objects react to the selected fields only (Maya Fields/Solvers >
    Assign to Selected: Blender's Effector Collection of each simulation)"""
    bl_idname = "allset.fx_assign_fields"
    bl_label = "Assign to Selected"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sel = list(context.selected_objects)
        fields = [o for o in sel if is_field(o)]
        targets = [o for o in sel if o not in fields]
        if not fields or not targets:
            self.report({'WARNING'}, "Select fields and the objects they should affect")
            return {'CANCELLED'}
        done = assign_fields(fields, targets)
        if not done:
            self.report({'WARNING'}, "No selected object has a cloth, soft body or particle simulation")
            return {'CANCELLED'}
        results.result(self, f"{len(fields)} field(s) connected to {len(done)} object(s)")
        return {'FINISHED'}


def _copy_field(src, dst):
    dst.type = src.type
    for p in src.bl_rna.properties:
        if p.identifier in {"rna_type", "type"} or p.is_readonly or p.type in {'POINTER', 'COLLECTION'}:
            continue
        try:
            setattr(dst, p.identifier, getattr(src, p.identifier))
        except (AttributeError, TypeError, ValueError):
            pass


class ALLSET_OT_fx_field_source(bpy.types.Operator):
    """The selected object becomes the source of the selected field (Maya Fields/Solvers > Use Selected as Source:
    Blender puts the force field on the object itself; the field's own empty goes away)"""
    bl_idname = "allset.fx_field_source"
    bl_label = "Use Selected as Source"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        sel = list(context.selected_objects)
        fields = [o for o in sel if is_field(o) and o.type == 'EMPTY']
        sources = [o for o in sel if o not in fields and not is_field(o)]
        if len(fields) != 1 or len(sources) != 1:
            self.report({'WARNING'}, "Select one field, then the object to be its source")
            return {'CANCELLED'}
        field, src = fields[0], sources[0]
        if src.field is None:
            with context.temp_override(object=src, active_object=src):
                bpy.ops.object.forcefield_toggle()
        _copy_field(field.field, src.field)
        for coll in list(bpy.data.collections):
            if field.name in coll.objects and coll.get(FIELDS):
                coll.objects.unlink(field)
                if src.name not in coll.objects:
                    coll.objects.link(src)
        name = field.name
        bpy.data.objects.remove(field)
        results.result(self, f"{src.name} is now the source of {name}")
        return {'FINISHED'}


classes = (ALLSET_OT_fx_clear_initial_state, ALLSET_OT_fx_start_from_mesh, ALLSET_OT_fx_rigid_interpenetrate,
           ALLSET_OT_fx_assign_fields, ALLSET_OT_fx_field_source)
