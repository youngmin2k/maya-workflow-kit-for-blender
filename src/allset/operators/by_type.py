# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Select > All by Type / Edit > Delete All by Type for the nodes the kit makes.

Maya selects the transforms of the type (``SelectAllIKHandles`` = every ikHandle, ``SelectAllClusters`` = every
clusterHandle; category "Menu items.Common.Select.All by Type") and deletes the
nodes with them. The kit's counterparts:

- IK handle = the ``ikHandleN`` empty an IK constraint targets (operators/skin.create_ik); a Spline IK handle is the
  ``ikHandleN`` Spline IK constraint itself (operators/rig_maya.py, no object to select).
- cluster = the Hook modifier ``clusterN`` and its ``clusterNHandle`` empty (operators/rig_maya.ALLSET_OT_cluster); a
  plain Blender Hook counts as a cluster too, a soft modification (``softModN``) and the lattice / wrap base hooks
  (``ffd1Base``) don't.
- particles / rigid bodies: objects with a particle system / a rigid body.
"""

import bpy
from bpy.props import EnumProperty

from .. import results
from .. import undo_steps


def _pose_constraints(scene, types):
    for ob in scene.objects:
        if ob.type == 'ARMATURE' and ob.pose is not None:
            for pb in ob.pose.bones:
                for con in pb.constraints:
                    if con.type in types:
                        yield ob, pb, con


def ik_handles(scene):
    """The handle objects of the scene's IK constraints (Maya ikHandle transforms), in scene order."""
    targets = {con.target for _ob, _pb, con in _pose_constraints(scene, {'IK'}) if con.target is not None}
    return [ob for ob in scene.objects if ob in targets]


def is_cluster(md):
    from . import deformers
    if md.type != 'HOOK' or deformers.is_base(md):
        return False
    return deformers.base_of(md) in (None, "cluster")


def cluster_modifiers(scene):
    return [(ob, md) for ob in scene.objects for md in getattr(ob, "modifiers", ()) if is_cluster(md)]


def cluster_handles(scene):
    handles = {md.object for _ob, md in cluster_modifiers(scene) if md.object is not None}
    return [ob for ob in scene.objects if ob in handles]


# --- #109: wires, nCloths, nParticles, nRigids -----------------------------------------
# Maya (SelectAllWires / SelectAllNCloths / SelectAllNParticles /
# SelectAllNRigids, DeleteAllWires / DeleteAllNCloths / DeleteAllNParticles /
# DeleteAllNRigids): select the wire nodes / the nCloth, nParticle, nRigid transforms; delete the wire nodes,
# Remove nCloth / nRigid (nCloth > Remove nCloth: the meshes stay) and the nParticle shapes. The kit's nodes:
# - wire = a kit wire Geometry Nodes modifier (operators/wire_deformer.py); it has no object, so Select picks the
#   wire curves that drive one (the curve is what a Maya user grabs to work the wire), Delete removes the
#   modifiers with their base wires and weights (wire_deformer.remove: the curve stays);
# - nCloth = a Cloth modifier, nRigid = a Collision modifier (nCloth > Create nCloth / Create Passive Collider; the
#   same rule as Modify > Evaluate Nodes, operators/modify_maya.py _set_cloth / _set_nrigid): the meshes carrying one;
# - nParticle = a particle system whose settings are named ``nParticleN`` (files from older versions; modify_maya
#   _is_nparticle). Maya ``-type particle`` includes nParticles, so Particles keeps finding every particle system.

def _modifiers_of(objects, test):
    return [(o, m) for o in objects for m in getattr(o, "modifiers", ()) if test(m)]


def _carriers(scene, test):
    return [o for o in scene.objects if any(test(m) for m in getattr(o, "modifiers", ()))]


def _is_wire(md):
    from . import wire_deformer
    return wire_deformer.is_wire(md)


def is_ncloth(md):
    return md.type == 'CLOTH'


def is_nrigid(md):
    return md.type == 'COLLISION'


def is_nparticle(md):
    ps = getattr(md, "particle_system", None) if md.type == 'PARTICLE_SYSTEM' else None
    return ps is not None and ps.settings is not None and ps.settings.name.startswith("nParticle")


def wire_curves(scene):
    from . import wire_deformer
    curves = {wire_deformer.get(md, "Wire") for _o, md in _modifiers_of(scene.objects, _is_wire)}
    return [ob for ob in scene.objects if ob in curves]


def delete_wires(objects):
    from . import wire_deformer
    pairs = _modifiers_of(list(objects), _is_wire)
    for _ob, md in pairs:
        wire_deformer.remove(md)
    return len(pairs)


def delete_nclothes(objects):
    pairs = _modifiers_of(list(objects), is_ncloth)
    for ob, md in pairs:
        ob.modifiers.remove(md)
    return len(pairs)


def delete_nrigids(objects):
    pairs = _modifiers_of(list(objects), is_nrigid)
    for ob, md in pairs:
        ob.modifiers.remove(md)
    return len(pairs)


def delete_nparticles(objects):
    pairs = _modifiers_of(list(objects), is_nparticle)
    settings = {md.particle_system.settings for _o, md in pairs}
    for ob, md in pairs:
        ob.modifiers.remove(md)
    for s in settings:
        if s.users == 0:
            bpy.data.particles.remove(s)
    return len(pairs)


DELETERS = {'WIRES': delete_wires, 'NCLOTHS': delete_nclothes, 'NPARTICLES': delete_nparticles,
            'NRIGIDS': delete_nrigids}


SELECTORS = {
    'IK_HANDLES': ik_handles,
    'CLUSTERS': cluster_handles,
    'PARTICLES': lambda scene: [o for o in scene.objects
                                if any(m.type == 'PARTICLE_SYSTEM' for m in getattr(o, "modifiers", ()))],
    'RIGID_BODIES': lambda scene: [o for o in scene.objects if o.rigid_body is not None],
    'WIRES': wire_curves,
    'NCLOTHS': lambda scene: _carriers(scene, is_ncloth),
    'NPARTICLES': lambda scene: _carriers(scene, is_nparticle),
    'NRIGIDS': lambda scene: _carriers(scene, is_nrigid),
}
KINDS = (('IK_HANDLES', "IK Handles", "Every IK handle (the empties IK constraints follow)"),
         ('CLUSTERS', "Clusters", "Every cluster handle"),
         ('PARTICLES', "Particles", "Every object with a particle system"),
         ('RIGID_BODIES', "Rigid Bodies", "Every rigid body"),
         ('WIRES', "Wires", "Every curve that drives a wire deformer"),
         ('NCLOTHS', "nCloths", "Every mesh with cloth"),
         ('NPARTICLES', "nParticles", "Every object with an nParticle system"),
         ('NRIGIDS', "nRigids", "Every passive collider"))


def select_all(context, kind):
    """Maya Select All by Type: the selection becomes those objects (the first one the lead). Returns them."""
    found = []
    for ob in SELECTORS[kind](context.scene):
        try:
            ob.select_get(view_layer=context.view_layer)
        except RuntimeError:          # not in this view layer
            continue
        found.append(ob)
    if context.mode != 'OBJECT' and context.active_object is not None:
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(context.selected_objects):
        ob.select_set(False)
    for ob in found:
        ob.select_set(True)
    if found:
        context.view_layer.objects.active = found[0]
    return found


def _unused_empty(ob, scene, ignore=()):
    """``ob`` is an empty nothing but ``ignore`` points at (safe to delete with its node)."""
    if ob is None or ob.type != 'EMPTY' or ob.children:
        return False
    for o in scene.objects:
        for md in getattr(o, "modifiers", ()):
            if md not in ignore and getattr(md, "object", None) == ob:
                return False
        cons = list(getattr(o, "constraints", ()))
        if o.type == 'ARMATURE' and o.pose is not None:
            cons += [c for pb in o.pose.bones for c in pb.constraints]
        for c in cons:
            if c not in ignore and getattr(c, "target", None) == ob:
                return False
    return True


def delete_ik_handles(scene):
    """Remove every IK / Spline IK constraint and the handle empties only they used; the number of handles."""
    found = list(_pose_constraints(scene, {'IK', 'SPLINE_IK'}))
    handles = [con.target for _ob, _pb, con in found if con.type == 'IK' and con.target is not None]
    ignore = [con for _ob, _pb, con in found]
    removable = [h for h in dict.fromkeys(handles) if _unused_empty(h, scene, ignore)]
    for _ob, pb, con in found:
        pb.constraints.remove(con)
    for h in removable:
        bpy.data.objects.remove(h)
    return len(found)


def delete_clusters(scene, objects=None):
    """Remove the cluster Hooks of ``objects`` (None: the scene) and their handles once nothing else uses them."""
    pairs = [(o, m) for o, m in cluster_modifiers(scene) if objects is None or o in objects]
    handles = [m.object for _o, m in pairs if m.object is not None]
    ignore = [m for _o, m in pairs]
    removable = [h for h in dict.fromkeys(handles) if _unused_empty(h, scene, ignore)]
    for ob, md in pairs:
        if md.name in ob.vertex_groups and md.vertex_group == md.name:
            ob.vertex_groups.remove(ob.vertex_groups[md.name])   # the kit cluster's own weights
        ob.modifiers.remove(md)
    for h in removable:
        bpy.data.objects.remove(h)
    return len(pairs)


@undo_steps.no_redo_panel      # Maya has no Adjust Last Operation
class ALLSET_OT_select_all_by_type(bpy.types.Operator):
    """Select every node of this type in the scene (Maya Select > All by Type)"""
    bl_idname = "allset.select_all_by_type"
    bl_label = "Select All by Type"
    bl_options = {'REGISTER', 'UNDO'}

    type: EnumProperty(name="Type", items=KINDS, options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.view_layer is not None

    def execute(self, context):
        found = select_all(context, self.type)
        results.result(self, f"{len(found)} {self.type.replace('_', ' ').lower()} selected")
        return {'FINISHED'}


classes = (ALLSET_OT_select_all_by_type,)
