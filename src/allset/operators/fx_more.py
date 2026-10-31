# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya FX menu items on Blender's own simulation systems (#123).

Blender keeps its engines (Cloth modifier, particle systems, Mantaflow, Rigid Body World, force fields); these
operators put them behind the Maya menu items a Maya user looks for, in Maya units (``units.maya_unit``) and with
the kit's simulation scale (``fx.sim_scale``):

- nParticles: Fill Object (grid of particles inside the mesh), Instancer (Render As Object / Collection);
- Fluids: Add / Edit Contents > Emitter (a Mantaflow flow mesh), Edit Fluid Resolution (domain resolution);
- nCloth: Rest Shape (the cloth's rest shape key), Paint Vertex Properties (the cloth's vertex-group slots);
- nConstraint: Transform Constraint (pin group + Hook to an empty), Disable Collision (collision vertex group),
  membership commands, Remove Dynamic Constraint;
- nCache / Fields: Create Particle Disk Cache, Transfer Cache To Input Mesh and Initial State (the simulated shape
  becomes the start shape), Volume Curve / Create Curve Flow (Curve Guide field), rigid body keys / solver.
"""

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty
from mathutils import Vector

from .. import results
from . import fx, naming, units

# --- nParticles: Create Options -----------------------------------------------------------------------------------

STYLES = (('POINT', "Point", "Particles drawn as dots"),
          ('BALLS', "Balls", "Particles drawn as circles"),
          ('CLOUD', "Cloud", "Particles drawn as circles (give them a volume material for a cloud look)"),
          ('THICK_CLOUD', "Thick Cloud", "Particles drawn as circles (give them a volume material for a cloud look)"),
          ('WATER', "Water", "Blender's fluid particles (SPH physics)"))
_DISPLAY = {'POINT': 'DOT', 'BALLS': 'CIRC', 'CLOUD': 'CIRC', 'THICK_CLOUD': 'CIRC', 'WATER': 'DOT'}


def apply_style(settings, style):
    """Draw / physics of a new particle system for the nParticles > Create Options style."""
    settings.display_method = _DISPLAY.get(style, 'DOT')
    if style == 'WATER':
        settings.physics_type = 'FLUID'


def style(context=None):
    wm = (context or bpy.context).window_manager
    return getattr(wm, "allset_nparticle_style", 'POINT')


# --- nParticles ---------------------------------------------------------------------------------------------------

FILL_RESOLUTION = 10


class ALLSET_OT_fx_fill_object(bpy.types.Operator):
    """Fill the selected meshes with particles on a grid (Maya nParticles > Fill Object: a Blender particle system
    emitting from the volume, all at the start frame)"""
    bl_idname = "allset.fx_fill_object"
    bl_label = "Fill Object"
    bl_options = {'REGISTER', 'UNDO'}

    resolution: IntProperty(name="Resolution", default=FILL_RESOLUTION, min=2, max=200,
                            description="Particles along the longest side of the mesh")

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(fx._meshes(context))

    def execute(self, context):
        scene = context.scene
        start, _end = fx._playback(scene)
        names = []
        for ob in fx._meshes(context):
            psys = fx._new_particles(ob, scene, fx._particle_name())
            s = psys.settings
            s.emit_from = 'VOLUME'
            s.distribution = 'GRID'
            s.grid_resolution = self.resolution
            s.frame_start = s.frame_end = start
            s.factor_random = 0.0
            s.normal_factor = 0.0
            names.append(psys.name)
        fx.apply(scene)
        results.result(self, f"Filled with {', '.join(names)}")
        return {'FINISHED'}


class ALLSET_OT_fx_instancer(bpy.types.Operator):
    """Instance the selected objects on the selected particles (Maya nParticles > Instancer: Blender's particle
    Render As Object, or Collection for several objects)"""
    bl_idname = "allset.fx_instancer"
    bl_label = "Instancer"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(o.particle_systems for o in context.selected_objects)

    def execute(self, context):
        owners = [o for o in context.selected_objects if o.particle_systems]
        shapes = [o for o in context.selected_objects if not o.particle_systems and o.type != 'EMPTY']
        if not owners or not shapes:
            self.report({'WARNING'}, "Select the objects to instance and the particle object")
            return {'CANCELLED'}
        name = f"instancer{naming.next_number('instancer', {c.name for c in bpy.data.collections})}"
        coll = None
        if len(shapes) > 1:
            coll = bpy.data.collections.new(name)
            for o in shapes:
                coll.objects.link(o)
        for owner in owners:
            for psys in owner.particle_systems:
                s = psys.settings
                if coll is None:
                    s.render_type = 'OBJECT'
                    s.instance_object = shapes[0]
                else:
                    s.render_type = 'COLLECTION'
                    s.instance_collection = coll
                s.particle_size = 1.0            # instances keep the object's own size
                s.display_method = 'RENDER'
        results.result(self, f"Instanced {', '.join(o.name for o in shapes)}")
        return {'FINISHED'}


# --- Fluids -------------------------------------------------------------------------------------------------------

EMITTER_RADIUS = 1.0


class ALLSET_OT_fluid_add_emitter(bpy.types.Operator):
    """Add a fluid emitter at the centre of the selected fluid container, or at the origin (Maya Fluids > Add/Edit
    Contents > Emitter: a Mantaflow smoke flow mesh, radius 1 unit)"""
    bl_idname = "allset.fluid_add_emitter"
    bl_label = "Emitter"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        domains = fx.fluid_domains(context.selected_objects)
        centre = domains[0].matrix_world.translation.copy() if domains else Vector()
        k = units.maya_unit(context.scene)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=EMITTER_RADIUS * k, location=centre,
                                              align='WORLD')
        em = context.view_layer.objects.active
        naming.apply_maya_name(em, "fluidEmitter")
        md = em.modifiers.new("Fluid", 'FLUID')
        md.fluid_type = 'FLOW'
        md.flow_settings.flow_type = 'SMOKE'
        md.flow_settings.flow_behavior = 'INFLOW'
        em.hide_render = True
        em.display_type = 'WIRE'
        results.result(self, f"Created {em.name}" + (f" in {domains[0].name}" if domains else ""))
        return {'FINISHED'}


def _domains(context):
    return fx.fluid_domains(context.selected_objects) or fx.fluid_domains(context.scene.objects)


class ALLSET_OT_fluid_resolution(bpy.types.Operator):
    """Set the resolution of the selected fluid containers (Maya Fluids > Edit Fluid Resolution: Blender's
    Mantaflow domain Resolution Divisions along the longest side)"""
    bl_idname = "allset.fluid_resolution"
    bl_label = "Edit Fluid Resolution"
    bl_options = {'REGISTER', 'UNDO'}

    resolution: IntProperty(name="Resolution", default=32, min=6, max=10000)

    @classmethod
    def poll(cls, context):
        return bool(_domains(context))

    def invoke(self, context, event):
        self.resolution = _domain_settings(_domains(context)[0]).resolution_max
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        for ob in _domains(context):
            _domain_settings(ob).resolution_max = self.resolution
        return {'FINISHED'}


def _domain_settings(ob):
    return next(md for md in ob.modifiers if md.type == 'FLUID').domain_settings


# --- nCloth: rest shape, vertex maps ------------------------------------------------------------------------------

def cloth_of(ob):
    return next((md for md in ob.modifiers if md.type == 'CLOTH'), None) if ob is not None else None


def _cloth_objects(context):
    obs = list(context.selected_objects)
    if context.active_object is not None and context.active_object not in obs:
        obs.append(context.active_object)
    return [o for o in obs if cloth_of(o) is not None]


class ALLSET_OT_ncloth_rest(bpy.types.Operator):
    """Set the cloth's rest shape (Maya nCloth > Rest Shape: Blender's cloth Shape > Rest Shape Key; no key = the
    input mesh)"""
    bl_idname = "allset.ncloth_rest"
    bl_label = "Rest Shape"
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(items=(('START', "Start Shape", "Rest at the input mesh (no rest shape key)"),
                              ('SELECTED', "Selected Mesh", "The other selected mesh becomes the rest shape key")),
                       name="Rest", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(_cloth_objects(context))

    def execute(self, context):
        if self.mode == 'START':
            for ob in _cloth_objects(context):
                keys = ob.data.shape_keys
                # the Basis key is the input mesh's shape
                cloth_of(ob).settings.rest_shape_key = keys.reference_key if keys is not None else None
            return {'FINISHED'}
        ob = context.active_object
        md = cloth_of(ob)
        others = [o for o in context.selected_objects if o is not ob and o.type == 'MESH']
        if md is None or not others:
            self.report({'WARNING'}, "Select the rest mesh, then the nCloth mesh last")
            return {'CANCELLED'}
        src = others[0]
        if len(src.data.vertices) != len(ob.data.vertices):
            self.report({'WARNING'}, f"{src.name} and {ob.name} need the same vertex count")
            return {'CANCELLED'}
        with context.temp_override(active_object=ob, object=ob, selected_editable_objects=[ob, src],
                                   selected_objects=[ob, src]):
            res = bpy.ops.object.join_shapes()
        if 'FINISHED' not in res:
            return {'CANCELLED'}
        key = ob.data.shape_keys.key_blocks[-1]
        md.settings.rest_shape_key = key
        results.result(self, f"Rest shape of {ob.name}: {key.name}")
        return {'FINISHED'}


# Maya per-vertex property -> (cloth settings attribute holding a vertex group name, group name). Weight 0 keeps the
# cloth's own value, 1 = the matching Max value in Physics > Cloth.
PAINT = {
    'INPUT_ATTRACT': ("vertex_group_mass", "nClothInputAttract"),
    'STRETCH': ("vertex_group_structural_stiffness", "nClothStretch"),
    'COMPRESSION': ("vertex_group_structural_stiffness", "nClothStretch"),
    'BEND': ("vertex_group_bending", "nClothBend"),
    'REST_LENGTH_SCALE': ("vertex_group_shrink", "nClothRestLengthScale"),
}
PAINT_ITEMS = tuple((k, k.replace("_", " ").title(), "") for k in PAINT)


class ALLSET_OT_ncloth_paint_vertex(bpy.types.Operator):
    """Paint an nCloth property per vertex (Maya nCloth > Paint Vertex Properties: the cloth's vertex group for it
    in Weight Paint mode)"""
    bl_idname = "allset.ncloth_paint_vertex"
    bl_label = "Paint Vertex Property"
    bl_options = {'REGISTER', 'UNDO'}

    attr: EnumProperty(items=PAINT_ITEMS, name="Property", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return bool(_cloth_objects(context))

    def execute(self, context):
        obs = _cloth_objects(context)
        ob = context.active_object if context.active_object in obs else obs[0]
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        slot, name = PAINT[self.attr]
        vg = ob.vertex_groups.get(name)
        if vg is None:
            vg = ob.vertex_groups.new(name=name)
            vg.add(range(len(ob.data.vertices)), 0.0, 'REPLACE')
        setattr(cloth_of(ob).settings, slot, name)
        ob.vertex_groups.active_index = vg.index
        for o in context.selected_objects:
            if o is not ob:
                o.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
        results.result(self, f"Paint {name} on {ob.name}")
        return {'FINISHED'}


# --- nConstraint ----------------------------------------------------------------------------------------------------

MARK = "allset_nconstraint"          # on the constraint empty: the cloth object's name
LIST = "allset_nconstraints"         # on the cloth object: its constraint names (= vertex groups, hooks, empties)
PINS = "nConstraintPins"
NO_COLLIDE = "nConstraintNoCollide"


def constraint_names(ob):
    return [str(n) for n in ob.get(LIST, ())]


def _set_names(ob, names):
    if names:
        ob[LIST] = list(names)
    elif LIST in ob:
        del ob[LIST]


def _deform_layer(bm):
    return bm.verts.layers.deform.verify()


def selected_verts(ob):
    """Indices of the selected vertices of a mesh in edit mode (or its stored selection in object mode)."""
    if ob.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(ob.data)
        return [v.index for v in bm.verts if v.select]
    return [v.index for v in ob.data.vertices if v.select]


def members(ob, name):
    """Vertex indices in group ``name``."""
    vg = ob.vertex_groups.get(name)
    if vg is None:
        return set()
    if ob.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(ob.data)
        dl = bm.verts.layers.deform.active
        return {v.index for v in bm.verts if dl is not None and vg.index in v[dl]}
    return {v.index for v in ob.data.vertices if any(g.group == vg.index for g in v.groups)}


def set_members(ob, name, indices, weight=1.0):
    """Group ``name`` holds exactly ``indices`` (made if missing); works in edit and object mode."""
    vg = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
    indices = set(indices)
    if ob.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(ob.data)
        dl = _deform_layer(bm)
        for v in bm.verts:
            if v.index in indices:
                v[dl][vg.index] = weight
            elif vg.index in v[dl]:
                del v[dl][vg.index]
        bmesh.update_edit_mesh(ob.data)
    else:
        vg.remove(range(len(ob.data.vertices)))
        if indices:
            vg.add(sorted(indices), weight, 'REPLACE')
    return vg


def rebuild_pins(ob):
    """The cloth's pin group = every Transform Constraint's vertices (Blender has one pin group per cloth)."""
    md = cloth_of(ob)
    pinned = set()
    for name in constraint_names(ob):
        pinned |= members(ob, name)
    if pinned:
        set_members(ob, PINS, pinned)
        if md is not None:
            md.settings.vertex_group_mass = PINS
    else:
        vg = ob.vertex_groups.get(PINS)
        if vg is not None:
            ob.vertex_groups.remove(vg)
        if md is not None and md.settings.vertex_group_mass == PINS:
            md.settings.vertex_group_mass = ""


def _move_before_cloth(ob, name):
    cloth = next(i for i, m in enumerate(ob.modifiers) if m.type == 'CLOTH')
    if ob.modifiers.find(name) > cloth:
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.object.modifier_move_to_index(modifier=name, index=cloth)


def transform_constraint(context, ob, indices):
    """Pin ``indices`` of cloth ``ob`` to a new empty dynamicConstraintN (Hook before the cloth + pin group)."""
    taken = {o.name for o in bpy.data.objects} | {g.name for g in ob.vertex_groups} | {m.name for m in ob.modifiers}
    name = f"dynamicConstraint{naming.next_number('dynamicConstraint', taken)}"
    set_members(ob, name, indices)
    me = ob.data
    if ob.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(me)
        bm.verts.ensure_lookup_table()
        cos = [bm.verts[i].co.copy() for i in indices]
    else:
        cos = [me.vertices[i].co.copy() for i in indices]
    centre = sum(cos, Vector()) / len(cos)
    empty = bpy.data.objects.new(name, None)
    for coll in ob.users_collection:
        coll.objects.link(empty)
    empty.location = ob.matrix_world @ centre
    empty.empty_display_size = units.maya_unit(context.scene)
    empty[MARK] = ob.name
    context.view_layer.update()
    hook = ob.modifiers.new(name, 'HOOK')
    hook.object = empty
    hook.vertex_group = name
    hook.center = centre
    hook.matrix_inverse = empty.matrix_world.inverted() @ ob.matrix_world
    _move_before_cloth(ob, name)
    _set_names(ob, constraint_names(ob) + [name])
    rebuild_pins(ob)
    return empty


def remove_constraint(ob, name):
    md = ob.modifiers.get(name)
    if md is not None:
        ob.modifiers.remove(md)
    vg = ob.vertex_groups.get(name)
    if vg is not None:
        ob.vertex_groups.remove(vg)
    empty = bpy.data.objects.get(name)
    if empty is not None and empty.get(MARK) == ob.name:
        bpy.data.objects.remove(empty)
    _set_names(ob, [n for n in constraint_names(ob) if n != name])
    rebuild_pins(ob)


def _edit_cloth(context):
    ob = context.edit_object
    return ob if ob is not None and ob.type == 'MESH' and cloth_of(ob) is not None else None


def _picked_constraints(context, ob):
    """The constraints of ``ob`` picked by selecting their empties, else its newest one."""
    names = constraint_names(ob)
    picked = [o.name for o in context.selected_objects if o.get(MARK) == ob.name and o.name in names]
    return picked or names[-1:]


class ALLSET_OT_nconstraint(bpy.types.Operator):
    """Maya nConstraint menu on Blender cloth: Transform Constraint = the selected vertices pinned and hooked to an
    empty, Disable Collision = a collision vertex group, membership commands on those groups"""
    bl_idname = "allset.nconstraint"
    bl_label = "nConstraint"
    bl_options = {'REGISTER', 'UNDO'}

    action: EnumProperty(items=(
        ('TRANSFORM', "Transform Constraint", "Pin the selected vertices to a new empty"),
        ('DISABLE_COLLISION', "Disable Collision", "The selected vertices don't collide"),
        ('REMOVE', "Remove Dynamic Constraint", "Remove the selected constraints (or all of the selected nCloths)"),
        ('SELECT', "Select Members", "Select the constraint's vertices"),
        ('ADD', "Add Members", "Add the selected vertices to the constraint"),
        ('SUBTRACT', "Remove Members", "Take the selected vertices out of the constraint"),
        ('REPLACE', "Replace Members", "The selected vertices become the constraint's"),
    ), name="Action", options={'SKIP_SAVE'})

    def execute(self, context):
        if self.action == 'REMOVE':
            return self._remove(context)
        ob = _edit_cloth(context)
        if ob is None:
            self.report({'WARNING'}, "Select vertices of an nCloth mesh in Edit Mode")
            return {'CANCELLED'}
        picked = selected_verts(ob)
        if self.action == 'TRANSFORM':
            if not picked:
                self.report({'WARNING'}, "Select the vertices to constrain")
                return {'CANCELLED'}
            empty = transform_constraint(context, ob, picked)
            results.result(self, f"Created {empty.name}")
            return {'FINISHED'}
        if self.action == 'DISABLE_COLLISION':
            if not picked:
                self.report({'WARNING'}, "Select the vertices that shouldn't collide")
                return {'CANCELLED'}
            set_members(ob, NO_COLLIDE, members(ob, NO_COLLIDE) | set(picked))
            cs = cloth_of(ob).collision_settings
            cs.vertex_group_object_collisions = NO_COLLIDE
            cs.vertex_group_self_collisions = NO_COLLIDE
            return {'FINISHED'}
        names = _picked_constraints(context, ob)
        if not names:
            self.report({'WARNING'}, f"{ob.name} has no dynamic constraint")
            return {'CANCELLED'}
        if self.action == 'SELECT':
            want = set()
            for n in names:
                want |= members(ob, n)
            bm = bmesh.from_edit_mesh(ob.data)
            for f in bm.faces:
                f.select_set(False)
            for e in bm.edges:
                e.select_set(False)
            for v in bm.verts:
                v.select_set(v.index in want)
            bm.select_flush_mode()
            bmesh.update_edit_mesh(ob.data)
            return {'FINISHED'}
        for n in names:
            cur = members(ob, n)
            new = {'ADD': cur | set(picked), 'SUBTRACT': cur - set(picked), 'REPLACE': set(picked)}[self.action]
            set_members(ob, n, new)
        rebuild_pins(ob)
        return {'FINISHED'}

    def _remove(self, context):
        done = 0
        empties = [o for o in context.selected_objects if MARK in o]
        for e in empties:
            ob = bpy.data.objects.get(e[MARK])
            if ob is not None:
                remove_constraint(ob, e.name)
                done += 1
        if not done:
            for ob in _cloth_objects(context):
                for n in constraint_names(ob):
                    remove_constraint(ob, n)
                    done += 1
                vg = ob.vertex_groups.get(NO_COLLIDE)
                if vg is not None:
                    ob.vertex_groups.remove(vg)
                    cs = cloth_of(ob).collision_settings
                    cs.vertex_group_object_collisions = cs.vertex_group_self_collisions = ""
                    done += 1
        if not done:
            self.report({'WARNING'}, "Select a dynamic constraint or an nCloth with one")
            return {'CANCELLED'}
        return {'FINISHED'}


# --- nCache / Initial State -------------------------------------------------------------------------------------------

def _reset_cache(pc):
    pc.frame_start = pc.frame_start          # a point cache setting change drops the unbaked frames


INPUT_CO = ".allset_input_co"           # mesh point attribute: the shape before the first Initial State
INPUT_MATRIX = "allset_input_matrix"    # object ID property: a rigid body's transform before it


def keep_input(ob):
    """Remember what ``ob`` looked like before its first Initial State, so Clear Initial State can bring it back.
    A later Initial State keeps the first one."""
    if ob.type == 'MESH' and any(md.type in {'CLOTH', 'SOFT_BODY'} for md in ob.modifiers):
        me = ob.data
        if me.attributes.get(INPUT_CO) is None:
            co = [0.0] * (3 * len(me.vertices))
            me.vertices.foreach_get("co", co)
            me.attributes.new(INPUT_CO, 'FLOAT_VECTOR', 'POINT').data.foreach_set("vector", co)
    elif ob.rigid_body is not None and INPUT_MATRIX not in ob:
        ob[INPUT_MATRIX] = [x for row in ob.matrix_basis for x in row]


def set_initial_state(context, obs):
    """The simulated shape / place at the current frame becomes the start: cloth and soft body meshes take their
    simulated vertex positions (the modifier stays), rigid bodies their simulated transform. Returns the objects."""
    depsgraph = context.evaluated_depsgraph_get()
    done = []
    for ob in obs:
        sims = [md for md in ob.modifiers if md.type in {'CLOTH', 'SOFT_BODY'}]
        if ob.type == 'MESH' and sims:
            ev = ob.evaluated_get(depsgraph)
            me = ev.to_mesh()
            if len(me.vertices) == len(ob.data.vertices):
                co = [0.0] * (3 * len(me.vertices))
                me.vertices.foreach_get("co", co)
                ev.to_mesh_clear()
                keep_input(ob)
                ob.data.vertices.foreach_set("co", co)
                if ob.data.shape_keys is not None:
                    ob.data.shape_keys.reference_key.data.foreach_set("co", co)
                ob.data.update()
                for md in sims:
                    _reset_cache(md.point_cache)
                done.append(ob)
            else:
                ev.to_mesh_clear()
        elif ob.rigid_body is not None:
            keep_input(ob)
            ob.matrix_world = ob.matrix_world.copy()        # the simulated (evaluated) transform, kept
            done.append(ob)
    world = context.scene.rigidbody_world
    if world is not None and world.point_cache is not None and any(o.rigid_body for o in done):
        _reset_cache(world.point_cache)
    return done


def dynamic_objects(scene):
    return [o for o in scene.objects
            if o.rigid_body is not None or any(md.type in {'CLOTH', 'SOFT_BODY'} for md in o.modifiers)]


class ALLSET_OT_fx_initial_state(bpy.types.Operator):
    """Make the current simulated shape the start shape (Maya Initial State > Set for Selected / Set for All
    Dynamic, nCache > Transfer Cache To Input Mesh: Blender writes the simulated cloth into the mesh and the
    simulated rigid body places into their transforms)"""
    bl_idname = "allset.fx_initial_state"
    bl_label = "Set Initial State"
    bl_options = {'REGISTER', 'UNDO'}

    all: BoolProperty(name="All Dynamic", options={'SKIP_SAVE'})

    def execute(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        obs = dynamic_objects(context.scene) if self.all else [o for o in context.selected_objects
                                                               if o in dynamic_objects(context.scene)]
        done = set_initial_state(context, obs)
        if not done:
            self.report({'WARNING'}, "No nCloth, soft body or rigid body to set")
            return {'CANCELLED'}
        results.result(self, f"Initial state set for {len(done)} object(s)")
        return {'FINISHED'}


class ALLSET_OT_particle_disk_cache(bpy.types.Operator):
    """Bake the selected particles to disk (Maya nCache > Create Particle Disk Cache: Blender's particle cache with
    Disk Cache on, next to the saved .blend)"""
    bl_idname = "allset.particle_disk_cache"
    bl_label = "Create Particle Disk Cache"
    bl_options = {'REGISTER'}

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({'WARNING'}, "Save the scene first: Blender writes disk caches next to the .blend file")
            return {'CANCELLED'}
        obs = fx.cache_targets(context)
        caches = [p.point_cache for o in obs for p in o.particle_systems]
        for pc in caches:
            pc.use_disk_cache = True
            with context.temp_override(point_cache=pc):
                bpy.ops.ptcache.bake(bake=True)
        if not caches:
            self.report({'WARNING'}, "No particles to cache in the selection")
            return {'CANCELLED'}
        results.result(self, f"Baked {len(caches)} particle cache(s) to disk")
        return {'FINISHED'}


# --- Fields / Solvers ------------------------------------------------------------------------------------------------

class ALLSET_OT_fx_curve_field(bpy.types.Operator):
    """Make the selected curves guide particles (Maya Fields > Volume Curve, Effects > Flow > Create Curve Flow:
    Blender's Curve Guide force field; Curve Flow also adds an emitter at the curve's start)"""
    bl_idname = "allset.fx_curve_field"
    bl_label = "Curve Field"
    bl_options = {'REGISTER', 'UNDO'}

    flow: BoolProperty(name="With Emitter", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(o.type == 'CURVE' for o in context.selected_objects)

    def execute(self, context):
        curves = [o for o in context.selected_objects if o.type == 'CURVE']
        k = units.maya_unit(context.scene)
        for cu in curves:
            if cu.field is None or cu.field.type == 'NONE':
                with context.temp_override(object=cu, active_object=cu):
                    bpy.ops.object.forcefield_toggle()
            cu.field.type = 'GUIDE'
            cu.field.guide_minimum = 0.0
            cu.field.guide_free = 0.0
            cu.data.use_path = True
            if self.flow:
                self._emitter(context, cu, k)
        fx.apply(context.scene)
        return {'FINISHED'}

    @staticmethod
    def _emitter(context, cu, k):
        sp = cu.data.splines[0] if cu.data.splines else None
        if sp is None:
            return
        pts = sp.bezier_points if sp.type == 'BEZIER' else sp.points
        first = pts[0].co
        start = cu.matrix_world @ Vector((first[0], first[1], first[2]))
        name = f"emitter{naming.next_number('emitter', {o.name for o in bpy.data.objects})}"
        me = bpy.data.meshes.new(name.replace("emitter", "emitterShape"))
        me.from_pydata([(0.0, 0.0, 0.0)], [], [])
        em = bpy.data.objects.new(name, me)
        em.location = start
        em.hide_render = True
        context.collection.objects.link(em)
        em[FLOW] = cu.name
        psys = fx._new_particles(em, context.scene, fx._particle_name())
        psys.settings.factor_random = 0.1 * k
        psys.settings.effector_weights.gravity = 0.0


FLOW = "allset_curve_flow"          # on a Create Curve Flow emitter: its curve's name


class ALLSET_OT_fx_delete_flow(bpy.types.Operator):
    """Delete the flow of the selected curves (Maya Effects > Flow > Delete Selected Flow: the curve's Curve Guide
    field off and its flow emitter deleted)"""
    bl_idname = "allset.fx_delete_flow"
    bl_label = "Delete Selected Flow"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects)

    def execute(self, context):
        sel = list(context.selected_objects)
        curves = {o.name for o in sel if o.type == 'CURVE' and o.field is not None and o.field.type == 'GUIDE'}
        curves |= {o[FLOW] for o in sel if FLOW in o}
        if not curves:
            self.report({'WARNING'}, "Select a flow curve or its emitter")
            return {'CANCELLED'}
        for name in curves:
            cu = bpy.data.objects.get(name)
            if cu is not None and cu.field is not None:
                cu.field.type = 'NONE'
        for em in [o for o in bpy.data.objects if o.get(FLOW) in curves]:
            settings = [p.settings for p in em.particle_systems]
            me = em.data
            bpy.data.objects.remove(em)
            if me is not None and me.users == 0:
                bpy.data.meshes.remove(me)
            for s in settings:
                if s.users == 0:
                    bpy.data.particles.remove(s)
        return {'FINISHED'}


class ALLSET_OT_fx_rigid_key(bpy.types.Operator):
    """Key the selected rigid bodies active or passive at the current frame (Maya Set Active Key / Set Passive Key:
    Blender's rigid body Animated checkbox, keyed)"""
    bl_idname = "allset.fx_rigid_key"
    bl_label = "Set Rigid Body Key"
    bl_options = {'REGISTER', 'UNDO'}

    passive: BoolProperty(name="Passive", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return any(o.rigid_body is not None for o in context.selected_objects)

    def execute(self, context):
        frame = context.scene.frame_current
        for ob in context.selected_objects:
            rb = ob.rigid_body
            if rb is None:
                continue
            rb.kinematic = self.passive
            ob.keyframe_insert("rigid_body.kinematic", frame=frame)
            if self.passive:
                ob.keyframe_insert("location", frame=frame)
                ob.keyframe_insert("rotation_euler", frame=frame)
        return {'FINISHED'}


class ALLSET_OT_fx_break_rigid(bpy.types.Operator):
    """Take the selected objects out of the rigid body simulation where they are now (Maya Break Rigid Body
    Connections: Blender keeps the simulated transform and removes the rigid body)"""
    bl_idname = "allset.fx_break_rigid"
    bl_label = "Break Rigid Body Connections"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(o.rigid_body is not None for o in context.selected_objects)

    def execute(self, context):
        obs = [o for o in context.selected_objects if o.rigid_body is not None]
        mats = {o.name: o.matrix_world.copy() for o in obs}
        with context.temp_override(selected_objects=obs, selected_editable_objects=obs, active_object=obs[0],
                                   object=obs[0]):
            bpy.ops.rigidbody.objects_remove()
        for o in obs:
            o.matrix_world = mats[o.name]
        return {'FINISHED'}


class ALLSET_OT_fx_rigid_world(bpy.types.Operator):
    """Create the rigid body solver (Maya Create Rigid Body Solver: Blender's scene Rigid Body World, one per
    scene, with the nucleus substeps)"""
    bl_idname = "allset.fx_rigid_world"
    bl_label = "Create Rigid Body Solver"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        if scene.rigidbody_world is None:
            bpy.ops.rigidbody.world_add()
            start, end = fx._playback(scene)
            pc = scene.rigidbody_world.point_cache
            pc.frame_start, pc.frame_end = start, end
        fx.apply(scene)
        results.result(self, "rigidSolver: the scene's Rigid Body World")
        return {'FINISHED'}


classes = (ALLSET_OT_fx_fill_object, ALLSET_OT_fx_instancer, ALLSET_OT_fluid_add_emitter, ALLSET_OT_fluid_resolution,
           ALLSET_OT_ncloth_rest, ALLSET_OT_ncloth_paint_vertex, ALLSET_OT_nconstraint, ALLSET_OT_fx_initial_state,
           ALLSET_OT_particle_disk_cache, ALLSET_OT_fx_curve_field, ALLSET_OT_fx_delete_flow, ALLSET_OT_fx_rigid_key,
           ALLSET_OT_fx_break_rigid,
           ALLSET_OT_fx_rigid_world)


def register_props():
    bpy.types.WindowManager.allset_nparticle_style = EnumProperty(
        items=STYLES, name="nParticle Style", default='POINT',
        description="How new particle systems are drawn (Maya nParticles > Create Options)")


def unregister_props():
    del bpy.types.WindowManager.allset_nparticle_style
