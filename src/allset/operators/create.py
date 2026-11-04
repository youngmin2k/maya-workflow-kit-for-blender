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
    # Primitives with a Maya creation node (#11, #12): built from operators/prim_shapes.py by
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
    'PIPE': ("Pipe", "pPipe", None, {}, None),
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
    # #299: the camera plus Maya's aim (and up) nodes in camera1_group (_aim_rig)
    'CAMERA_AIM': ("Camera and Aim", "camera", "object.camera_add", {}, LEVEL),
    'CAMERA_AIM_UP': ("Camera, Aim and Up", "camera", "object.camera_add", {}, LEVEL),
    'LOCATOR': ("Locator", "locator", "object.empty_add",
                {"type": 'PLAIN_AXES', "radius": 1.0}, None),
    'EMPTY_GROUP': ("Empty Group", "null", "object.empty_add",
                    {"type": 'PLAIN_AXES', "radius": 1.0}, None),
    # create paths that used Blender's operators with
    # metre defaults. A joint = a bone in one armature: bone length 1.
    'JOINT': ("Joint", "skeleton", "object.armature_add", {"radius": 1.0}, None),
    'TEXT': ("Type", "typeMesh", "object.text_add", {"radius": 1.0}, None),
    # Maya's Free Image Plane faces the front camera with no image yet: an image empty, no file browser.
    'IMAGE_PLANE': ("Free Image Plane", "imagePlane", "object.empty_add", {"type": 'IMAGE', "radius": 1.0}, LEVEL),
}
# Kinds whose data keeps Blender's name (Maya has no "...Shape" node for them).
NO_SHAPE_NAME = {'JOINT', 'TEXT'}
# A Maya locator (Create > Locator, cmds.spaceLocator): an Empty with this flag; cmds_shim gives it a shape name
# ``locatorShapeN``
LOCATOR_PROP = "allset_locator"
# Lights (operators/lights.py): Maya intensity 1, Decay Rate No Decay. The power follows the Maya unit
# (x maya_unit()^2) and is set so an intensity-1 light at 10 units lights a surface the Maya way;
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
        lights.maya_defaults(data, k)     # intensity 1, No Decay, spot cone 40, area 2 x 2 units


def _maya_naming(context):
    from .. import preferences
    try:
        return preferences.get(context).maya_naming
    except KeyError:
        return True


def create(context, kind, maya_naming=True, overrides=None):
    """Create ``kind`` at the world origin; returns the new object. ``overrides``: for primitives Maya node
    attributes (``{"subdivisionsCaps": 2}``, lengths in Maya units, ``createUVs`` 0 = no UVs), else operator values
    in Maya units (lengths are scaled like the defaults), e.g. from the primitive's option window."""
    _label, base, op, props, rot = KINDS[kind]
    props = {**props, **(overrides or {})}
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    if kind in prim_history.KIND_NODES:
        vals = dict(overrides or {})
        uvs = bool(vals.pop("createUVs", True))
        ob = prim_history.create_object(context, kind, vals, maya_naming, create_uvs=uvs)
        from . import material
        for part in [ob, *ob.children]:   # nurbsCube: each patch joins lambert1
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
    if maya_naming:
        naming.apply_maya_name(ob, base, rename_data=kind not in NO_SHAPE_NAME)
    if kind == 'LOCATOR':
        ob[LOCATOR_PROP] = True
    if kind == 'JOINT':
        _first_joint(ob, maya_naming)
    if kind in ('CAMERA_AIM', 'CAMERA_AIM_UP'):
        _aim_rig(ob, kind == 'CAMERA_AIM_UP', k)
    if maya_naming:
        from . import material
        material.give_default(ob)   # Maya: a new shape joins initialShadingGroup = lambert1
    return ob


def _first_joint(ob, maya_naming):
    """The armature's one bone = Maya's joint1, rotate order XYZ (W1)."""
    bone = ob.data.bones[0]
    if maya_naming:
        bone.name = "joint1"
    pose_bone = ob.pose.bones.get(bone.name)
    if pose_bone is not None:
        pose_bone.rotation_mode = 'XYZ'


def _aim_rig(cam, up, k):
    """Maya's camera1_group holding camera1 and camera1_aim at the centre of interest 5 units ahead, which the camera
    looks at with world up; with ``up``, camera1_up 1 unit above sets the camera's roll."""
    def node(suffix, location, size):
        ob = bpy.data.objects.new(f"{cam.name}_{suffix}", None)
        ob.location, ob.empty_display_size = location, size
        cam.users_collection[0].objects.link(ob)
        return ob

    group = node("group", (0.0, 0.0, 0.0), 0.0)        # a Maya group draws nothing
    nodes = [cam, node("aim", (0.0, 5.0 * k, 0.0), k)]   # LEVEL: the camera looks along +Y
    aim = cam.constraints.new('TRACK_TO')
    aim.target, aim.track_axis, aim.up_axis = nodes[1], 'TRACK_NEGATIVE_Z', 'UP_Y'
    if up:
        nodes.append(node("up", (0.0, 0.0, k), k))
        roll = cam.constraints.new('LOCKED_TRACK')
        roll.target, roll.track_axis, roll.lock_axis = nodes[2], 'TRACK_Y', 'LOCK_Z'
    for ob in nodes:
        ob.parent = group


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


classes = (ALLSET_OT_create,)
