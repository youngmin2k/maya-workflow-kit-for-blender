# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya FX items on Blender's simulation systems: nCloth removal and display, colliders for fluids, nCache.

Maya FX menus only connect to Blender's own systems (Cloth modifier, particle systems, Mantaflow, Rigid Body World,
point caches). Nothing is rescaled: Blender simulates one unit as one metre, so FX works in metre scenes.
"""

import bpy
from bpy.props import EnumProperty

from .. import results


def _meshes(context):
    return [ob for ob in context.selected_objects if ob.type == 'MESH']


class ALLSET_OT_fx_remove_ncloth(bpy.types.Operator):
    """Remove the cloth from the selected meshes (Maya nCloth > Remove nCloth)"""
    bl_idname = "allset.fx_remove_ncloth"
    bl_label = "Remove nCloth"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(md.type == 'CLOTH' for ob in context.selected_objects for md in ob.modifiers)

    def execute(self, context):
        for ob in context.selected_objects:
            for md in [m for m in ob.modifiers if m.type == 'CLOTH']:
                ob.modifiers.remove(md)
        return {'FINISHED'}


# --- nCache ------------------------------------------------------------------------------------------

def point_caches(ob):
    """(owner, point cache) of an object's cloth / soft body / particle systems."""
    for md in ob.modifiers:
        if md.type in {'CLOTH', 'SOFT_BODY'}:
            yield md, md.point_cache
    for psys in ob.particle_systems:
        yield psys, psys.point_cache


def fluid_domains(obs):
    return [ob for ob in obs for md in ob.modifiers if md.type == 'FLUID' and md.fluid_type == 'DOMAIN']


def _sim_node_objects(obs):
    """Objects with a Geometry Nodes modifier that has a simulation zone."""
    out = []
    for ob in obs:
        for md in ob.modifiers:
            tree = getattr(md, "node_group", None) if md.type == 'NODES' else None
            if tree is not None and any(n.bl_idname == 'GeometryNodeSimulationOutput' for n in tree.nodes):
                out.append(ob)
                break
    return out


def cache_targets(context):
    return list(context.selected_objects) or list(context.scene.objects)


def bake_point_caches(context, obs, bake=True):
    """Bake (or free) the point caches of ``obs`` and, if any of them is a rigid body, the rigid body world's."""
    count = 0
    caches = [pc for ob in obs for _owner, pc in point_caches(ob)]
    world = context.scene.rigidbody_world
    if world is not None and world.point_cache is not None and any(ob.rigid_body for ob in obs):
        caches.append(world.point_cache)
    for pc in caches:
        with context.temp_override(point_cache=pc):
            if bake:
                bpy.ops.ptcache.bake(bake=True)
            else:
                bpy.ops.ptcache.free_bake()
        count += 1
    sims = _sim_node_objects(obs)
    if sims:
        with context.temp_override(selected_objects=sims, active_object=sims[0], object=sims[0]):
            if bake:
                bpy.ops.object.simulation_nodes_cache_bake(selected=True)
            else:
                bpy.ops.object.simulation_nodes_cache_delete(selected=True)
        count += len(sims)
    return count


def bake_fluids(context, obs, bake=True):
    count = 0
    for ob in fluid_domains(obs):
        with context.temp_override(object=ob, active_object=ob):
            if bake:
                bpy.ops.fluid.bake_all()
            else:
                bpy.ops.fluid.free_all()
        count += 1
    return count


class ALLSET_OT_ncache(bpy.types.Operator):
    """Bake or delete the simulation caches of the selection, or of the whole scene when nothing is selected
    (Maya nCache; Blender keeps a cache per object, saved with the file)"""
    bl_idname = "allset.ncache"
    bl_label = "nCache"
    bl_options = {'REGISTER'}

    action: EnumProperty(items=(('CREATE', "Create New Cache", ""), ('DELETE', "Delete Cache", "")), name="Action")
    kind: EnumProperty(items=(('NOBJECT', "nObject", "Cloth, particles, soft and rigid bodies, simulation nodes"),
                              ('FLUID', "Maya Fluid", "Mantaflow domains"),
                              ('ALL', "All", "")), name="Kind", default='NOBJECT')

    def execute(self, context):
        obs = cache_targets(context)
        bake = self.action == 'CREATE'
        n = 0
        if self.kind in {'NOBJECT', 'ALL'}:
            n += bake_point_caches(context, obs, bake)
        if self.kind in {'FLUID', 'ALL'}:
            n += bake_fluids(context, obs, bake)
        if not n:
            self.report({'WARNING'}, "No simulation to cache in the selection")
            return {'CANCELLED'}
        results.result(self, f"{'Baked' if bake else 'Deleted'} {n} cache(s)")
        return {'FINISHED'}


class ALLSET_OT_fluid_collide(bpy.types.Operator):
    """Make the selected meshes collide with fluids (Maya Fluids > Make Collide: a Mantaflow effector)"""
    bl_idname = "allset.fluid_collide"
    bl_label = "Make Collide"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(_meshes(context))

    def execute(self, context):
        for ob in _meshes(context):
            md = next((m for m in ob.modifiers if m.type == 'FLUID'), None)
            if md is None:
                md = ob.modifiers.new("Fluid", 'FLUID')
            if md.fluid_type == 'NONE':
                md.fluid_type = 'EFFECTOR'
        return {'FINISHED'}


def is_fluid(ob):
    return any(md.type == 'FLUID' for md in ob.modifiers)


class ALLSET_OT_fluid_quick_smoke(bpy.types.Operator):
    """Make the selected meshes smoke emitters in a new smoke domain (Blender's Quick Smoke), except fluids"""
    bl_idname = "allset.fluid_quick_smoke"
    bl_label = "Quick Smoke"
    bl_options = {'REGISTER', 'UNDO'}

    style: EnumProperty(name="Smoke Style", items=(('SMOKE', "Smoke", ""), ('FIRE', "Fire", ""),
                                                   ('BOTH', "Smoke & Fire", "")), default='SMOKE')

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        # Blender's Quick Smoke stops with a Python error on a mesh that already has a Fluid modifier
        meshes = _meshes(context)
        fluids = [ob for ob in meshes if is_fluid(ob)]
        if not meshes:
            self.report({'ERROR'}, "Select at least one mesh object")
            return {'CANCELLED'}
        if len(fluids) == len(meshes):
            self.report({'WARNING'}, f"Already a fluid: {', '.join(ob.name for ob in fluids)}")
            return {'CANCELLED'}
        for ob in fluids:
            ob.select_set(False)
        try:
            res = bpy.ops.object.quick_smoke(style=self.style)
        except RuntimeError as ex:
            from . import maya_errors
            maya_errors.report_nested(self, ex)
            return {'CANCELLED'}
        if fluids:
            self.report({'WARNING'}, f"Skipped, already a fluid: {', '.join(ob.name for ob in fluids)}")
        return res


class ALLSET_OT_ncloth_display(bpy.types.Operator):
    """Show the selected cloth objects' input mesh (cloth off in the viewport) or the simulated current mesh
    (Maya nCloth > Display Input Mesh / Display Current Mesh)"""
    bl_idname = "allset.ncloth_display"
    bl_label = "Display nCloth Mesh"
    bl_options = {'REGISTER', 'UNDO'}

    mesh: bpy.props.EnumProperty(items=(('INPUT', "Input Mesh", ""), ('CURRENT', "Current Mesh", "")),
                                 options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return any(md.type == 'CLOTH' for ob in context.selected_objects for md in ob.modifiers)

    def execute(self, context):
        for ob in context.selected_objects:
            for md in ob.modifiers:
                if md.type == 'CLOTH':
                    md.show_viewport = self.mesh == 'CURRENT'
        return {'FINISHED'}


classes = (ALLSET_OT_fx_remove_ncloth, ALLSET_OT_ncache, ALLSET_OT_fluid_collide, ALLSET_OT_fluid_quick_smoke,
           ALLSET_OT_ncloth_display)
