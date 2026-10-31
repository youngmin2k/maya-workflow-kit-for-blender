# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya FX menu items on Blender's own simulation systems (#123).

Each operator only puts a Blender system behind the Maya item a Maya user looks for (no rescaling, no kit nodes):

- nParticles: Fill Object (a particle system emitting from the volume on a grid), Instancer (Render As Object /
  Collection);
- Fluids: Add / Edit Contents > Emitter (the selected meshes become Mantaflow smoke flows), Edit Fluid Resolution;
- nCloth: Rest Shape (the cloth's rest shape key), Paint Vertex Properties (the cloth's vertex-group slots);
- nCache / Fields / Solvers: Create Particle Disk Cache, Volume Curve / Create Curve Flow (Curve Guide field),
  rigid body keys, Break Rigid Body Connections, Create Rigid Body Solver (the scene's Rigid Body World).
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty

from .. import results
from . import fx, naming

FILL_RESOLUTION = 10


def _start_frame(scene):
    return scene.frame_preview_start if scene.use_preview_range else scene.frame_start


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
        start = _start_frame(context.scene)
        names = []
        for ob in fx._meshes(context):
            md = ob.modifiers.new("ParticleSystem", 'PARTICLE_SYSTEM')
            s = md.particle_system.settings
            s.emit_from = 'VOLUME'
            s.distribution = 'GRID'
            s.grid_resolution = self.resolution
            s.frame_start = s.frame_end = start
            s.normal_factor = 0.0
            names.append(f"{ob.name} ({md.particle_system.name})")
        results.result(self, f"Filled {', '.join(names)}")
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

class ALLSET_OT_fluid_add_emitter(bpy.types.Operator):
    """Make the selected meshes emit smoke into a fluid container (Maya Fluids > Add/Edit Contents > Emitter:
    Blender's Fluid modifier of type Flow)"""
    bl_idname = "allset.fluid_add_emitter"
    bl_label = "Emitter"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(fx._meshes(context))

    def execute(self, context):
        made = []
        for ob in fx._meshes(context):
            md = next((m for m in ob.modifiers if m.type == 'FLUID'), None)
            if md is None:
                md = ob.modifiers.new("Fluid", 'FLUID')
            if md.fluid_type != 'NONE':
                continue
            md.fluid_type = 'FLOW'
            md.flow_settings.flow_type = 'SMOKE'
            md.flow_settings.flow_behavior = 'INFLOW'
            made.append(ob.name)
        if not made:
            self.report({'WARNING'}, "Select meshes that aren't fluid containers, emitters or colliders yet")
            return {'CANCELLED'}
        results.result(self, f"Smoke flow: {', '.join(made)}")
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


# --- nCache -------------------------------------------------------------------------------------------------------

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
    Blender's Curve Guide force field on the curve)"""
    bl_idname = "allset.fx_curve_field"
    bl_label = "Curve Field"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(o.type == 'CURVE' for o in context.selected_objects)

    def execute(self, context):
        for cu in [o for o in context.selected_objects if o.type == 'CURVE']:
            if cu.field is None or cu.field.type == 'NONE':
                with context.temp_override(object=cu, active_object=cu):
                    bpy.ops.object.forcefield_toggle()
            cu.field.type = 'GUIDE'
            cu.data.use_path = True
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
    scene)"""
    bl_idname = "allset.fx_rigid_world"
    bl_label = "Create Rigid Body Solver"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if context.scene.rigidbody_world is None:
            bpy.ops.rigidbody.world_add()
        results.result(self, "rigidSolver: the scene's Rigid Body World")
        return {'FINISHED'}


classes = (ALLSET_OT_fx_fill_object, ALLSET_OT_fx_instancer, ALLSET_OT_fluid_add_emitter, ALLSET_OT_fluid_resolution,
           ALLSET_OT_ncloth_rest, ALLSET_OT_ncloth_paint_vertex, ALLSET_OT_particle_disk_cache,
           ALLSET_OT_fx_curve_field, ALLSET_OT_fx_rigid_key, ALLSET_OT_fx_break_rigid, ALLSET_OT_fx_rigid_world)
