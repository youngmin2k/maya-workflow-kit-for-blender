# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Create menu: primitives at the origin with the default size and names, like Maya.

Maya: interactive creation is off by default, so a
primitive appears at the origin at its default size (polyCube 1x1x1, polySphere
r=1, polyPlane 1x1 with 10x10); names ``pCube1`` / ``pCubeShape1``.
Other default values are Maya behaviour knowledge
and two are unverified.

Size rule: a Maya length of 1
is one scene display unit (``units.maya_unit``), like ``cmds.polyCube()`` and a
Maya FBX import: pCube1 shows 1 cm in the Maya Workflow Kit template (0.01 BU) and with
the "Maya Units" preference (1 BU). Lengths below are in Maya units.
"""

import math

import bpy
from bpy.props import EnumProperty

from .. import results
from . import lights, naming, prim_history, units

HALF_PI = math.pi / 2
# Maya's Y-up "front" (looking down -Z) is Blender's front (+Y): directional lights,
# spots, area lights and cameras start level, not pointing at the floor.
LEVEL = (HALF_PI, 0.0, 0.0)

# kind: (label, Maya base name, operator, props, rotation)
KINDS = {
    # Primitives with a Maya creation node (#11, #12, step 129): built from operators/prim_shapes.py by
    # operators/prim_history.py with Maya's topology, the node shown in Channel Box INPUTS. op = None.
    'CUBE': ("Cube", "pCube", None, {}, None),
    'SPHERE': ("Sphere", "pSphere", None, {}, None),
    'CYLINDER': ("Cylinder", "pCylinder", None, {}, None),
    'CONE': ("Cone", "pCone", None, {}, None),
    'TORUS': ("Torus", "pTorus", None, {}, None),
    'PLANE': ("Plane", "pPlane", None, {}, None),
    'DISC': ("Disc", "pDisc", None, {}, None),
    'PLATONIC': ("Platonic Solid", "pPlatonic", None, {}, None),
    'PYRAMID': ("Pyramid", "pPyramid", None, {}, None),
    'PRISM': ("Prism", "pPrism", None, {}, None),
    'PIPE': ("Pipe", "pPipe", None, {}, None),                      # step 190
    'HELIX': ("Helix", "pHelix", None, {}, None),
    'GEAR': ("Gear", "pGear", None, {}, None),
    'SOCCER_BALL': ("Soccer Ball", "pSolid", None, {}, None),
    'SUPER_ELLIPSE': ("Super Ellipse", "pSuperShape", None, {}, None),
    'SPHERICAL_HARMONICS': ("Spherical Harmonics", "pSuperShape", None, {}, None),
    'ULTRA_SHAPE': ("Ultra Shape", "pSuperShape", None, {}, None),
    'NURBS_SPHERE': ("NURBS Sphere", "nurbsSphere", None, {}, None),
    'NURBS_CYLINDER': ("NURBS Cylinder", "nurbsCylinder", None, {}, None),
    'NURBS_PLANE': ("NURBS Plane", "nurbsPlane", None, {}, None),
    'NURBS_TORUS': ("NURBS Torus", "nurbsTorus", None, {}, None),
    'NURBS_CIRCLE': ("NURBS Circle", "nurbsCircle", None, {}, None),
    'NURBS_SQUARE': ("NURBS Square", "nurbsSquare", None, {}, None),
    'NURBS_CUBE': ("NURBS Cube", "nurbsCube", None, {}, None),
    'NURBS_CONE': ("NURBS Cone", "nurbsCone", None, {}, None),
    # Maya's curve tools draw a curve; Blender adds one to edit (names "curve1" / "bezier1").
    'CV_CURVE': ("CV Curve", "curve", "curve.primitive_nurbs_curve_add", {"radius": 1.0}, None),
    'BEZIER_CURVE': ("Bezier Curve", "bezier", "curve.primitive_bezier_curve_add",
                     {"radius": 1.0}, None),
    'DIRECTIONAL_LIGHT': ("Directional Light", "directionalLight", "object.light_add",
                          {"type": 'SUN'}, LEVEL),
    'POINT_LIGHT': ("Point Light", "pointLight", "object.light_add", {"type": 'POINT'}, None),
    'SPOT_LIGHT': ("Spot Light", "spotLight", "object.light_add", {"type": 'SPOT'}, LEVEL),
    'AREA_LIGHT': ("Area Light", "areaLight", "object.light_add", {"type": 'AREA'}, LEVEL),
    'CAMERA': ("Camera", "camera", "object.camera_add", {}, LEVEL),
    'LOCATOR': ("Locator", "locator", "object.empty_add",
                {"type": 'PLAIN_AXES', "radius": 1.0}, None),
    'EMPTY_GROUP': ("Empty Group", "null", "object.empty_add",
                    {"type": 'PLAIN_AXES', "radius": 1.0}, None),
    # Step 54: create paths that used Blender's operators with
    # metre defaults. A joint = a bone in one armature: bone length 1.
    'JOINT': ("Joint", "skeleton", "object.armature_add", {"radius": 1.0}, None),
    'TEXT': ("Type", "typeMesh", "object.text_add", {"radius": 1.0}, None),
    # Maya's Free Image Plane faces the front camera with no image yet: an image empty, no file browser.
    'IMAGE_PLANE': ("Free Image Plane", "imagePlane", "object.empty_add", {"type": 'IMAGE', "radius": 1.0}, LEVEL),
    # Fields: Blender force fields are empties, display size 1 Maya unit.
    # Blender has no gravity field: a wind blowing down (Maya -Y = Blender -Z); Uniform blows along Maya's +X.
    'FIELD_AIR': ("Air Field", "airField", "object.effector_add", {"type": 'WIND', "radius": 1.0}, None),
    'FIELD_DRAG': ("Drag Field", "dragField", "object.effector_add", {"type": 'DRAG', "radius": 1.0}, None),
    'FIELD_GRAVITY': ("Gravity Field", "gravityField", "object.effector_add", {"type": 'WIND', "radius": 1.0},
                      (math.pi, 0.0, 0.0)),
    'FIELD_NEWTON': ("Newton Field", "newtonField", "object.effector_add", {"type": 'FORCE', "radius": 1.0}, None),
    'FIELD_RADIAL': ("Radial Field", "radialField", "object.effector_add", {"type": 'FORCE', "radius": 1.0}, None),
    'FIELD_TURBULENCE': ("Turbulence Field", "turbulenceField", "object.effector_add",
                         {"type": 'TURBULENCE', "radius": 1.0}, None),
    'FIELD_UNIFORM': ("Uniform Field", "uniformField", "object.effector_add", {"type": 'WIND', "radius": 1.0},
                      (0.0, HALF_PI, 0.0)),
    'FIELD_VORTEX': ("Vortex Field", "vortexField", "object.effector_add", {"type": 'VORTEX', "radius": 1.0}, None),
}
# Fields/Solvers default magnitudes (Gravity / Newton Options):
# Gravity 9.8 along Maya -Y (the Wind above is turned to blow down),
# Newton 5 pulling in (Blender Force: negative strength attracts). An acceleration in Maya units per second squared,
# so it is scaled by the step 68 simulation scale g = maya_unit() / Space Scale like the nucleus gravity (#72).
FIELD_MAGNITUDES = {'FIELD_GRAVITY': 9.8, 'FIELD_NEWTON': -5.0}
# Kinds whose data keeps Blender's name (Maya has no "...Shape" node for them).
NO_SHAPE_NAME = {'JOINT', 'TEXT'}
# A Maya locator (Create > Locator, cmds.spaceLocator): an Empty with this flag; cmds_shim gives it a shape name
# ``locatorShapeN`` (step 208)
LOCATOR_PROP = "allset_locator"
# Lights (step 137, operators/lights.py): Maya intensity 1, Decay Rate No Decay. The power follows the Maya unit
# (x maya_unit()^2, step 54) and is set so an intensity-1 light at 10 units lights a surface the Maya way;
# Cycles renders No Decay / Linear with a Light Falloff node, EEVEE and the viewport keep distance squared.
FALLOFF_LIGHTS = {'POINT', 'SPOT', 'AREA'}
LIGHT_NOTICE = ("Maya Decay Rate No Decay renders in Cycles; EEVEE and the viewport get darker with the square of "
                "the distance (matched to Maya at 10 units).")

MAYA_CAMERA_LENS, MAYA_FILM_MM = 35.0, 36.0

# Operator properties that are lengths (scaled by units.maya_unit).
LENGTHS = {"size", "radius", "depth", "radius1", "radius2", "major_radius", "minor_radius"}


def _scale_data(ob, k):
    """Lengths the add operators don't take: camera (Maya clip 0.1 / 10000),
    Blender's light sizes, kept in proportion to the Maya unit."""
    data = ob.data
    if ob.type == 'CAMERA':
        # Maya camera: focal length 35 on a 1.417 in (36 mm) film back
        # (Blender's camera_add gives 50 mm). Camera from View (Ctrl+Shift+C) overrides the lens with the view's.
        data.lens, data.sensor_width = MAYA_CAMERA_LENS, MAYA_FILM_MM
        data.display_size *= k
        data.clip_start, data.clip_end = units.CLIP["clip_start"] * k, units.CLIP["clip_end"] * k
    elif ob.type == 'LIGHT':
        data.shadow_soft_size *= k
        if data.type == 'AREA':
            data.size_y *= k
        lights.maya_defaults(data, k)     # intensity 1, No Decay, spot cone 40, area 2 x 2 units (step 137)


def _maya_naming(context):
    from .. import preferences
    try:
        return preferences.get(context).maya_naming
    except KeyError:
        return True


def create(context, kind, maya_naming=True, overrides=None):
    """Create ``kind`` at the world origin; returns the new object. ``overrides``: for primitives Maya node
    attributes (``{"subdivisionsCaps": 2}``, lengths in Maya units, ``createUVs`` 0 = no UVs), else operator values
    in Maya units (lengths are scaled like the defaults), e.g. from the primitive's option window (step 103)."""
    _label, base, op, props, rot = KINDS[kind]
    props = {**props, **(overrides or {})}
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    if kind in prim_history.KIND_NODES:
        vals = dict(overrides or {})
        uvs = bool(vals.pop("createUVs", True))
        ob = prim_history.create_object(context, kind, vals, maya_naming, create_uvs=uvs)
        from . import material
        for part in [ob, *ob.children]:   # nurbsCube: each patch joins lambert1 (step 100)
            if part.type in {'MESH', 'SURFACE'}:
                material.give_default(part)
        return ob
    mod, name = op.split(".")
    k = units.maya_unit(context.scene)
    kw = {key: v * k if key in LENGTHS else v for key, v in props.items()}
    kw.update(location=(0.0, 0.0, 0.0), rotation=rot or (0.0, 0.0, 0.0), align='WORLD')
    getattr(getattr(bpy.ops, mod), name)(**kw)
    ob = context.view_layer.objects.active
    _scale_data(ob, k)
    if kind in FIELD_MAGNITUDES and ob.field is not None:
        from . import fx
        g = fx.sim_scale(context.scene) if hasattr(context.scene, "allset_nucleus") else k
        ob.field.strength = FIELD_MAGNITUDES[kind] * g
        ob.field.flow = 0.0     # Blender's Wind starts with Flow 1 (a drag towards the wind speed): Maya gravity has none
    if maya_naming:
        naming.apply_maya_name(ob, base, rename_data=kind not in NO_SHAPE_NAME)
    if kind == 'LOCATOR':
        ob[LOCATOR_PROP] = True
    if kind == 'JOINT':
        _first_joint(ob, maya_naming)
    if maya_naming:
        from . import material
        material.give_default(ob)   # Maya: a new shape joins initialShadingGroup = lambert1 (step 100)
    return ob


def _first_joint(ob, maya_naming):
    """The armature's one bone = Maya's joint1, rotate order XYZ (W1)."""
    bone = ob.data.bones[0]
    if maya_naming:
        bone.name = "joint1"
    pose_bone = ob.pose.bones.get(bone.name)
    if pose_bone is not None:
        pose_bone.rotation_mode = 'XYZ'


class ALLSET_OT_create(bpy.types.Operator):
    """Create a primitive, light, camera or locator at the origin with the default
    size and name, like Maya (Maya Create menu)"""
    bl_idname = "allset.create"
    bl_label = "Create"
    bl_options = {'REGISTER', 'UNDO'}

    kind: EnumProperty(name="Kind", items=[(k, v[0], "") for k, v in KINDS.items()])

    @classmethod
    def description(cls, context, props):
        return f"Create a {KINDS[props.kind][0]} at the origin, default size and name like Maya"

    def execute(self, context):
        from . import interactive_create
        # Create > Polygon Primitives > Interactive Creation: the creation tool draws it in a view
        if interactive_create.wanted(context, self.kind) and interactive_create.start(context, self.kind):
            return {'FINISHED'}
        ob = create(context, self.kind, _maya_naming(context))
        note = LIGHT_NOTICE if ob.type == 'LIGHT' and ob.data.type in FALLOFF_LIGHTS else ""
        results.result(self, f"Created {ob.name}" + (f". {note}" if note else ""))
        return {'FINISHED'}


# Blender's quick smoke (Fluids > 3D Container, Effects > Fire / Smoke) puts a domain around the selection with a
# margin of (1, 1, 2) BU and 1 BU up ($S\startupl_operators\object_quick_effects.py:482-483): 200 x 200 x 400
# Maya units in a cm scene. The margin is redone in Maya units here.
SMOKE_MARGIN = (1.0, 1.0, 2.0)
SMOKE_LIFT = 1.0


def _selection_bounds(objects):
    from mathutils import Vector
    pts = [ob.matrix_world @ Vector(c) for ob in objects for c in ob.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


class ALLSET_OT_quick_smoke(bpy.types.Operator):
    """Smoke or fire from the selected meshes in a Mantaflow domain sized in Maya units
    (Maya Fluids > 3D Container, Effects > Fire / Smoke)"""
    bl_idname = "allset.quick_smoke"
    bl_label = "Quick Smoke"
    bl_options = {'REGISTER', 'UNDO'}

    style: EnumProperty(name="Style", items=(('SMOKE', "Smoke", ""), ('FIRE', "Fire", ""), ('BOTH', "Both", "")))

    @classmethod
    def poll(cls, context):
        return any(ob.type == 'MESH' for ob in context.selected_objects)

    def execute(self, context):
        from mathutils import Vector
        meshes = [ob for ob in context.selected_objects if ob.type == 'MESH']
        # a mesh can hold one fluid modifier: Blender's quick_smoke fails on a selected container / emitter that already
        # has one (the new emitter is the rest of the selection)
        taken = [ob for ob in meshes if any(md.type == 'FLUID' for md in ob.modifiers)]
        if taken:
            meshes = [ob for ob in meshes if ob not in taken]
            if not meshes:
                self.report({'WARNING'}, "Smoke: select a mesh that isn't a fluid container or emitter yet.")
                return {'CANCELLED'}
            for ob in taken:
                ob.select_set(False)
            if context.view_layer.objects.active in taken:
                context.view_layer.objects.active = meshes[0]
        lo, hi = _selection_bounds(meshes)
        before = set(bpy.data.objects)
        if not bpy.ops.object.quick_smoke.poll():
            self.report({'WARNING'}, "Smoke: switch to Object Mode with the emitting meshes selected first.")
            return {'CANCELLED'}
        res = bpy.ops.object.quick_smoke(style=self.style)
        if res != {'FINISHED'}:
            return res
        domain = next((ob for ob in bpy.data.objects if ob not in before), None)
        if domain is None:
            return res
        k = units.maya_unit(context.scene)
        domain.location = (lo + hi) / 2 + Vector((0.0, 0.0, SMOKE_LIFT * k))
        domain.scale = (hi - lo) / 2 + Vector(SMOKE_MARGIN) * k
        return res


classes = (ALLSET_OT_create, ALLSET_OT_quick_smoke)
