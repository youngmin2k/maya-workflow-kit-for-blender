# SPDX-License-Identifier: GPL-3.0-or-later
"""Tidy files saved by older kit versions when they are opened (temporary — remove in 0.11.0).

Older versions added a ``defaultLight`` sun (ID property ``allset_default_light``) while a scene without lights
rendered. Renders no longer add it, so a file that still has one is cleaned once when it is loaded (the kit
``persp`` render camera, ID property ``allset_persp``, is still the render camera of scenes without one and stays):

- every leftover ``defaultLight`` object and its light data are deleted;
- the stored camera Renderable values of the old Render Sequence option are dropped.

Older versions also had Create > Lights > Ambient Light / Volume Light (kit point lights kept in step by handlers,
the ambient light adding "Maya Ambient" nodes to the World), a kit Light Editor whose Isolate kept the other lights'
visibility in the scene, and an Illuminates by Default switch on lights:

- the World's "Maya Ambient" nodes are taken out (the World's own output linked back; a World the kit made for
  them is removed when nothing else uses it);
- a kit Ambient / Volume Light becomes a plain kit point light with the same Maya intensity, No Decay;
- a Light Editor Isolate still on is undone (the other lights' visibility comes back);
- the Illuminates by Default value is dropped (Blender's light linking collections stay as they are).

Older versions also rescaled FX to the Maya unit: a kit nucleus (``Scene.allset_nucleus``) set the scene gravity to
9.8 x the Maya unit (0.098 in a centimetre scene) and every kit nCloth's stiffness and damping by the same factor
(object ID property ``allset_cloth_g``). FX now runs Blender's simulations at real size, so:

- a scene gravity the kit nucleus set (still the value it wrote) goes back to Blender's 9.81 down, and the nucleus
  values are dropped; a gravity changed by hand afterwards stays;
- a kit nCloth's stiffness and damping go back to the values before the rescale;
- ID properties only older FX items read (nConstraint, Curve Flow, rigid body interpenetration and field
  assignment markers, the stored start shape of Initial State) are dropped; the Blender data they belong to (hooks,
  constraints, fields, collections) stays.
"""

import bpy
from bpy.app.handlers import persistent

from .. import compat

DEFAULT_LIGHT = "allset_default_light"
RENDERABLE = "allset_renderable_on"
# Ambient / Volume Light: ID properties on the light data, the volume light's nodes, the World's ambient nodes
LIGHT_KIND = "allset_light_kind"
LIGHT_INTENSITY = "allset_maya_intensity"
LIGHT_PROPS = (LIGHT_KIND, LIGHT_INTENSITY, "allset_ambient_shade")
VOLUME_NODES_ON = "allset_volume_nodes"
VOLUME_NODES = ("Maya Volume Falloff", "Maya Volume Ray Length", "Maya Volume r/R", "Maya Volume 1 - r/R",
                "Maya Volume Strength")
WORLD_ADD = "Maya Ambient Add"
WORLD_NODES = ("Maya Ambient", "Maya Ambient Ray", "Maya Ambient Not Camera", WORLD_ADD)
WORLD_MADE, WORLD_NODES_ON = "allset_ambient_world", "allset_ambient_world_nodes"
LIGHT_ISOLATE = "allset_light_isolate"
ILLUMINATES = "allset_illuminates_by_default"
# FX: the nucleus values (a registered pointer, so the stored values are only visible while it is registered), the
# cloth rescale factor and the ID properties of the old FX items
NUCLEUS = "allset_nucleus"
CLOTH_G = "allset_cloth_g"
CLOTH_SCALED = ("tension_stiffness", "compression_stiffness", "shear_stiffness", "bending_stiffness",
                "tension_damping", "compression_damping", "shear_damping", "bending_damping")
FX_OBJECT_PROPS = ("allset_nconstraint", "allset_nconstraints", "allset_curve_flow", "allset_no_collide",
                   "allset_input_matrix")
FX_COLLECTION_PROPS = ("allset_fields_of",)
FX_MESH_ATTRIBUTE = ".allset_input_co"
BLENDER_GRAVITY = (0.0, 0.0, -9.81)


# the nucleus values older versions stored on the scene (read once by ``clean``, never shown)
class ALLSET_PG_old_nucleus(bpy.types.PropertyGroup):
    exists: bpy.props.BoolProperty()
    gravity: bpy.props.FloatProperty(default=9.8)
    gravity_direction: bpy.props.FloatVectorProperty(size=3, default=(0.0, -1.0, 0.0))
    space_scale: bpy.props.FloatProperty(default=1.0)


def _remove_object(ob):
    data = ob.data
    bpy.data.objects.remove(ob)
    if data is not None and data.users == 0:
        if isinstance(data, bpy.types.Camera):
            bpy.data.cameras.remove(data)
        elif isinstance(data, bpy.types.Light):
            bpy.data.lights.remove(data)


def _clean_world(world):
    """Take the old ambient nodes out of ``world``; True when there were any."""
    tree = world.node_tree
    if tree is None or not any(tree.nodes.get(n) for n in WORLD_NODES):
        return False
    add = tree.nodes.get(WORLD_ADD)
    original = add.inputs[0].links[0].from_socket if add is not None and add.inputs[0].is_linked else None
    targets = [lk.to_socket for lk in add.outputs[0].links] if add is not None else []
    for name in WORLD_NODES:
        node = tree.nodes.get(name)
        if node is not None:
            tree.nodes.remove(node)
    if original is not None:
        for sock in targets:
            tree.links.new(original, sock)
    if world.get(WORLD_NODES_ON):
        compat.release_world_nodes(world)
    return True


def _clean_worlds():
    n = 0
    for world in list(bpy.data.worlds):
        if _clean_world(world):
            n += 1
        made = bool(world.get(WORLD_MADE))
        for key in (WORLD_MADE, WORLD_NODES_ON):
            if key in world.keys():
                del world[key]
        if made:
            for sc in bpy.data.scenes:
                if sc.world == world:
                    sc.world = None
            if world.users == 0:
                bpy.data.worlds.remove(world)
    return n


def _clean_light(light):
    """An old Ambient / Volume Light -> a plain kit point light with its Maya intensity (No Decay)."""
    if LIGHT_KIND not in light.keys():
        return False
    value = light.get(LIGHT_INTENSITY, 1.0)
    intensity = float(value) if isinstance(value, (int, float)) else 1.0
    tree = light.node_tree
    if tree is not None:
        for name in VOLUME_NODES:
            node = tree.nodes.get(name)
            if node is not None:
                tree.nodes.remove(node)
    if light.get(VOLUME_NODES_ON):
        from . import lights
        light[lights.NODES_PROP] = True       # the kit turned the nodes on: the Decay Rate rule may turn them off
    for key in (*LIGHT_PROPS, VOLUME_NODES_ON):
        if key in light.keys():
            del light[key]
    if light.type == 'POINT':
        from . import lights
        lights.apply(light, intensity, 0)
    return True


def _undo_isolate(scene):
    state = scene.get(LIGHT_ISOLATE)
    if state is None:
        return False
    saved = state.to_dict().get("saved", {}) if hasattr(state, "to_dict") else {}
    for name, values in saved.items():
        ob = scene.objects.get(name)
        if ob is not None and len(values) == 2:
            ob.hide_render, ob.hide_viewport = bool(values[0]), bool(values[1])
    del scene[LIGHT_ISOLATE]
    return True


def _old_gravity(scene, nuc):
    """The gravity vector the old kit nucleus wrote (Maya Y-up direction, x Maya unit / Space Scale)."""
    from . import units
    x, y, z = nuc.gravity_direction
    d = (x, -z, y)
    length = sum(c * c for c in d) ** 0.5 or 1.0
    g = nuc.gravity * units.maya_unit(scene) / max(nuc.space_scale, 1e-4)
    return tuple(c / length * g for c in d)


def _restore_gravity(scene):
    """True when the scene had an old kit nucleus (its values are dropped either way)."""
    if not scene.is_property_set(NUCLEUS):
        return False
    nuc = getattr(scene, NUCLEUS, None)
    if nuc is None:
        return False
    had = nuc.exists
    if had and all(abs(a - b) < 1e-5 for a, b in zip(scene.gravity, _old_gravity(scene, nuc))):
        scene.gravity = BLENDER_GRAVITY
    scene.property_unset(NUCLEUS)
    return had


def _restore_cloth(ob):
    """An old kit nCloth: stiffness and damping back to the values before the rescale."""
    if CLOTH_G not in ob.keys():
        return False
    value = ob.get(CLOTH_G)
    g = float(value) if isinstance(value, (int, float)) else 1.0
    del ob[CLOTH_G]
    if g <= 0.0 or abs(g - 1.0) < 1e-12:
        return False
    for md in ob.modifiers:
        if md.type == 'CLOTH':
            st = md.settings
            for attr in CLOTH_SCALED:
                setattr(st, attr, getattr(st, attr) / g)
    return True


def _drop_fx_props():
    n = 0
    for ob in bpy.data.objects:
        for key in FX_OBJECT_PROPS:
            if key in ob.keys():
                del ob[key]
                n += 1
    for coll in bpy.data.collections:
        for key in FX_COLLECTION_PROPS:
            if key in coll.keys():
                del coll[key]
                n += 1
    for me in bpy.data.meshes:
        at = me.attributes.get(FX_MESH_ATTRIBUTE)
        if at is not None:
            me.attributes.remove(at)
            n += 1
    return n


def clean():
    """Clean the open file; returns what was done ({kind: count})."""
    done = {"default_light": 0, "props": 0, "ambient_world": 0, "maya_lights": 0,
            "isolate": 0, "gravity": 0, "cloth": 0}
    for ob in [o for o in bpy.data.objects if o.get(DEFAULT_LIGHT)]:
        _remove_object(ob)
        done["default_light"] += 1
    for data in [d for d in bpy.data.lights if d.get(DEFAULT_LIGHT) and d.users == 0]:
        bpy.data.lights.remove(data)
    for cam in bpy.data.cameras:
        if RENDERABLE in cam.keys():
            del cam[RENDERABLE]
            done["props"] += 1
    done["ambient_world"] = _clean_worlds()
    for light in bpy.data.lights:
        if _clean_light(light):
            done["maya_lights"] += 1
    for sc in bpy.data.scenes:
        if _undo_isolate(sc):
            done["isolate"] += 1
    for ob in bpy.data.objects:
        if ILLUMINATES in ob.keys():
            del ob[ILLUMINATES]
            done["props"] += 1
    for sc in bpy.data.scenes:
        if _restore_gravity(sc):
            done["gravity"] += 1
    for ob in bpy.data.objects:
        if _restore_cloth(ob):
            done["cloth"] += 1
    done["props"] += _drop_fx_props()
    return done


@persistent
def _on_load(*_args):
    try:
        done = clean()
    except (AttributeError, ReferenceError, RuntimeError):
        return
    if any(done[k] for k in ("default_light", "ambient_world", "maya_lights", "isolate",
                             "gravity", "cloth")):
        print(f"Maya Workflow Kit: tidied what an older version left in this file ({done})")


def register():
    bpy.utils.register_class(ALLSET_PG_old_nucleus)
    setattr(bpy.types.Scene, NUCLEUS, bpy.props.PointerProperty(type=ALLSET_PG_old_nucleus))
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)


def unregister():
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    delattr(bpy.types.Scene, NUCLEUS)
    bpy.utils.unregister_class(ALLSET_PG_old_nucleus)
