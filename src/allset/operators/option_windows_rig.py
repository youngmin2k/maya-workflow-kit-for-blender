# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya option windows: rigging, skinning, deformers and constraints (issue #32, Aim / Pole Vector of #35).

Same spec as operators/option_windows.py (``F`` fields, ``Window`` = one ``allset.opt_<key>`` operator); labels follow
Maya's windows.
option_windows.py appends ``WINDOWS`` to its own list, so this module only imports ``F`` / ``Window`` / helpers from it.

Maya tool boxes (Create Joints, Create IK Handle, Create IK Spline Handle, Paint Skin Weights) open Tool Settings,
not a window: here they are the same kind of window titled with the tool name, whose
button starts the tool with the values. Fields Blender can't honour are only listed
(``missing``), never faked.
"""

import bpy
from bpy.props import StringProperty
from mathutils import Vector

from .option_windows import F, Window, _constraint, _last_constraint  # noqa: F401  (imported by option_windows)
from .option_windows_modify import FString


class FText(F):
    """A Maya text field (``kind`` "text")."""

    def __init__(self, name, label, default=""):
        super().__init__(name, label, "text", default)

    def prop(self):
        return StringProperty(name=self.label.rstrip(":"), default=self.default)


# --- run helpers ------------------------------------------------------------------------------------

_SOLVER = {"Rotate-Plane Solver": "RP", "Single-Chain Solver": "SC"}
_NORMALIZE = {"None": "NONE", "Off": "NONE", "Interactive": "INTERACTIVE", "Post": "POST"}


def _ik_fields(prefix=""):
    # IK Handle Settings: Current solver RP, Solver enable on, Weight 1
    return [F(prefix + "solver", "Current solver:", "enum", "Rotate-Plane Solver",
              items=("Single-Chain Solver", "Rotate-Plane Solver")),
            F(prefix + "solver_enable", "", "bool", True, text="Solver enable"),
            F(prefix + "weight", "Weight:", "float", 1.0, lo=0.01, hi=1.0)]


_IK_MISSING = ("Autopriority", "Snap enable (Blender's handle is a free empty)", "Sticky", "Priority",
               "POWeight")


def joint_tool_props(v):
    """Window values -> ``allset.joint_tool`` properties."""
    return dict(secondary_axis="NONE" if v["secondary_axis"] == "None" else v["secondary_axis"],
                secondary_world=v["secondary_world"], secondary_sign=v["secondary_sign"],
                auto_secondary=v.get("auto_secondary", True), orient_world=v.get("orient_world", False),
                create_ik=v["create_ik"], ik_solver=_SOLVER[v["ik_solver"]],
                ik_solver_enable=v["ik_solver_enable"], ik_weight=v["ik_weight"])


def _run_joint_tool(context, v):
    props = joint_tool_props(v)
    if props["secondary_axis"] == "X":
        raise RuntimeError("Secondary axis must differ from the primary axis (X)")
    return bpy.ops.allset.joint_tool('INVOKE_DEFAULT', **props)


def _run_ik_handle(context, v):
    return bpy.ops.allset.ik_handle('INVOKE_DEFAULT', solver=_SOLVER[v["solver"]], solver_enable=v["solver_enable"],
                                    weight=v["weight"])


def _run_ik_spline(context, v):
    return bpy.ops.allset.ik_spline_handle(
        'INVOKE_DEFAULT', root_on_curve=v.get("root_on_curve", True), parent_curve=v.get("parent_curve", True),
        snap_curve=v.get("snap_curve", False), create_curve=v.get("create_curve", True),
        spans=int(v.get("spans", "1")),
        twist_type=("Linear", "Ease In", "Ease Out", "Ease In Out").index(v.get("twist_type", "Linear")))


_BIND_METHOD = {"Closest distance": "CLOSEST_DISTANCE", "Closest in hierarchy": "CLOSEST_HIERARCHY",
                "Heat Map": "HEAT_MAP"}


def _run_bind(context, v):
    # skinning method, dropoff and Maintain max influences are Bind Skin operator options
    return bpy.ops.allset.bind_skin('EXEC_DEFAULT', bind_to='SELECTED' if v["bind_to"] == "Selected joints" else
                                    'HIERARCHY', max_influences=v["max_influences"],
                                    bind_method=_BIND_METHOD.get(v.get("bind_method"), 'CLOSEST_DISTANCE'),
                                    skinning={"Dual quaternion": 'DUAL_QUATERNION', "Weight blended":
                                              'WEIGHT_BLENDED'}.get(v["skinning"], 'CLASSIC_LINEAR'),
                                    dropoff=v.get("dropoff", 4.0),
                                    maintain_max=v.get("maintain_max", True),
                                    normalize=_NORMALIZE[v["normalize"]], remove_unused=v["remove_unused"],
                                    colorize=v["colorize"])


def _run_unbind(context, v):
    history = {"Delete history": "DELETE", "Keep history": "KEEP", "Bake history": "BAKE"}[v["history"]]
    return bpy.ops.allset.unbind_skin('EXEC_DEFAULT', history=history, remove_colors=v["remove_colors"])


_SURFACE = {"Closest point on surface": "CLOSEST_POINT", "Ray cast": "RAY_CAST",
            "Closest component": "CLOSEST_COMPONENT"}
_INFLUENCE = {"Closest joint": "CLOSEST_JOINT", "Closest bone": "CLOSEST_BONE", "One to one": "ONE_TO_ONE",
              "Name": "NAME", "None": "NONE"}


def _run_copy_weights(context, v):
    return bpy.ops.allset.copy_skin_weights('EXEC_DEFAULT', surface=_SURFACE[v["surface"]],
                                            influence1=_INFLUENCE[v["influence1"]],
                                            influence2=_INFLUENCE[v["influence2"]],
                                            influence3=_INFLUENCE[v["influence3"]], normalize=v["normalize"])


_PAINT_OPS = {"Replace": "REPLACE", "Add": "ADD", "Scale": "SCALE", "Smooth": "SMOOTH"}
_PROFILES = {"Gaussian": "GAUSSIAN", "Soft": "SOFT", "Solid": "SOLID"}


def _run_paint(context, v):
    return bpy.ops.allset.paint_skin_weights(
        'EXEC_DEFAULT', settings=True, operation=_PAINT_OPS[v["operation"]], profile=_PROFILES[v["profile"]],
        normalize=_NORMALIZE[v["normalize"]], opacity=v["opacity"], value=v["value"], radius=v["radius"],
        screen_projection=v["screen_projection"], show_wireframe=v["show_wireframe"], xray_joints=v["xray_joints"])


def _run_blend_shape(context, v):
    return bpy.ops.allset.blend_shape('EXEC_DEFAULT', node_name=v["node_name"].strip(),
                                      origin=v["origin"].upper(), check_topology=v["check_topology"],
                                      delete_targets=v["delete_targets"])


def _run_aim(context, v):
    from . import rig_tools
    world_up = v["world_up_type"]
    bone = context.mode == 'POSE'
    up_object = None
    if world_up in ("Object up", "Object rotation up"):
        name = v.get("world_up_object", "").strip()
        if name:
            up_object = bpy.data.objects.get(name)
            if up_object is None:
                raise RuntimeError(f"World up object: no object named {name}")
    # check the vectors before anything is added (rig_tools.aim raises on vectors Blender can't take)
    a = rig_tools.axis_of(rig_tools.local_axis(v["aim_vector"], bone))
    if a is None:
        raise RuntimeError("Blender aims along an axis: the aim vector must be +-X, +-Y or +-Z")
    if world_up != "None":
        u = rig_tools.axis_of(rig_tools.local_axis(v["up_vector"], bone))
        if u is None or u[0] == a[0] or (u[1] < 0 and world_up != "Object up"):
            raise RuntimeError("Blender turns the up vector along a local axis other than the aim vector's "
                               "(a positive one unless World up type is Object up)")
    res = bpy.ops.allset.constrain('EXEC_DEFAULT', type='TRACK_TO')
    con = _last_constraint(context)
    if res != {'FINISHED'} or con is None:
        return res
    owner = context.active_pose_bone if bone else context.active_object
    cons = owner.constraints
    if (tuple(v["aim_vector"]), tuple(v["up_vector"]), world_up, tuple(v["world_up_vector"])) != (
            rig_tools.AIM_VECTOR, rig_tools.UP_VECTOR, rig_tools.WORLD_UP, (0.0, 1.0, 0.0)):
        # the operator made the default aim (like Maya); redo it with the window's values on a fresh Track To
        target, sub, name = con.target, getattr(con, "subtarget", ""), con.name
        cons.remove(con)
        con = cons.new('TRACK_TO')
        con.name, con.target = name, target
        if sub:
            con.subtarget = sub
        con = rig_tools.aim(cons, con, v["aim_vector"], v["up_vector"], world_up, bone=bone, up_object=up_object,
                            world_up_vector=v["world_up_vector"])
    con.influence = v["weight"]
    companion = cons.get(con.name + rig_tools.UP_SUFFIX)
    if companion is not None:
        companion.influence = v["weight"]
    return res


def _run_scale(context, v):
    res = _constraint('COPY_SCALE')(context, {**v, "maintain_offset": False})
    con = _last_constraint(context)
    if res != {'FINISHED'} or con is None or con.type != 'COPY_SCALE':
        return res
    owner = context.active_pose_bone if context.mode == 'POSE' else context.active_object
    # Maya: driven scale = target scale x offset (Maya Y = Blender Z). Blender's Copy Scale with Offset multiplies
    # the owner's own scale in, so the owner's scale channels become the offset.
    offset = Vector((v["offset"][0], v["offset"][2], v["offset"][1]))
    if v["maintain_offset"]:
        target = con.target
        ts = target.pose.bones[con.subtarget].matrix.to_scale() if con.subtarget else target.matrix_world.to_scale()
        own = owner.scale.copy()
        offset = Vector([own[i] / ts[i] if abs(ts[i]) > 1e-9 else 1.0 for i in range(3)])
    if (offset - Vector((1.0, 1.0, 1.0))).length > 1e-9:
        con.use_offset = True
        owner.scale = offset
    return res


def _run_pole_vector(context, v):
    if abs(v["weight"] - 1.0) > 1e-9:
        raise RuntimeError("Blender's IK pole target has no weight: the pole vector always counts fully (Weight 1)")
    return bpy.ops.allset.pole_vector('EXEC_DEFAULT')


# --- the windows (labels / defaults) --------------------------

_ANIM_LAYER = ("Animation Layer", "Set layer to override")

WINDOWS = [
    # Skeleton > Create Joints: Tool Settings "Joint Tool"
    # Orientation section of Maya 2026: Orient Joint to World, Secondary
    # Axis, its world orientation, Auto orient secondary axis (factory on since 2025)
    Window("joint_tool", "Joint Tool", "Create Joints", None, [
        F("orient_world", "", "bool", False, text="Orient Joint to World"),
        F("secondary_axis", "Secondary Axis:", "enum", "Y", items=("X", "Y", "Z", "None")),
        F("secondary_world", "Secondary Axis World Orientation:", "enum", "Y", items=("X", "Y", "Z")),
        F("secondary_sign", "", "enum", "+", items=("+", "-")),
        F("auto_secondary", "", "bool", True, text="Auto orient secondary axis"),
        F("create_ik", "", "bool", False, text="Create IK handle"),
        *_ik_fields("ik_")], _run_joint_tool, paths=("Skeleton/Create Joints",),
        missing=("Degrees of freedom", "Symmetry", "Scale compensate", "Auto joint limits",
                 "Variable Bone Radius Settings / Bone Radius Settings", "Projected Centering",
                 "Primary Axis (always the bone's Y = Maya X)") + _IK_MISSING),
    # Skeleton > Create IK Handle: Tool Settings "IK Handle Tool"
    Window("ik_handle_tool", "IK Handle Tool", "Create IK Handle", None, _ik_fields(), _run_ik_handle,
           paths=("Skeleton/Create IK Handle",), missing=_IK_MISSING),
    # Skeleton > Create IK Spline Handle: Tool Settings "IK Spline Handle Tool" (Maya
    # 2026 factory values ikSplineHandleCtx)
    Window("ik_spline_tool", "IK Spline Handle Tool", "Create IK Spline Handle", None, [
        F("root_on_curve", "", "bool", True, text="Root on curve"),
        F("parent_curve", "", "bool", True, text="Auto parent curve"),
        F("snap_curve", "", "bool", False, text="Snap curve to root"),
        F("create_curve", "", "bool", True, text="Auto create curve"),
        F("spans", "Number of spans:", "enum", "1", items=("1", "2", "3", "4")),
        # #166: Twist type of the new handle (operators/spline_twist.py)
        F("twist_type", "Twist type:", "enum", "Linear", items=("Linear", "Ease In", "Ease Out", "Ease In Out"))],
        _run_ik_spline, paths=("Skeleton/Create IK Spline Handle",),
        missing=("Auto create root axis", "Auto simplify curve (the kit always fits the curve: on)",
                 "Root twist mode")),
    # Skin > Bind Skin; replaces option_windows "bind_skin"
    Window("bind_skin_maya", "Bind Skin Options", "Apply and Close", ("allset.bind_skin", {}), [
        F("bind_to", "Bind to:", "enum", "Joint hierarchy", items=("Joint hierarchy", "Selected joints")),
        F("bind_method", "Bind method:", "enum", "Closest distance",
          items=("Closest distance", "Closest in hierarchy", "Heat Map")),
        F("skinning", "Skinning method:", "enum", "Classic linear",
          items=("Classic linear", "Dual quaternion", "Weight blended")),
        F("normalize", "Normalize weights:", "enum", "Interactive", items=("None", "Interactive", "Post")),
        F("max_influences", "Max influences:", "int", 5, lo=1, hi=30),
        # defaults like Maya: Maintain max influences on, Dropoff rate 4.0
        F("maintain_max", "", "bool", True, text="Maintain max influences"),
        F("dropoff", "Dropoff rate:", "float", 4.0, lo=0.1, hi=100.0),
        F("remove_unused", "", "bool", True, text="Remove unused influences"),
        F("colorize", "", "bool", True, text="Colorize skeleton")], _run_bind, paths=("Skin/Bind Skin",),
        missing=("Bind to: Object hierarchy", "Bind method: Geodesic Voxel", "Weight distribution", "Allow multiple bind poses", "Include hidden selections on creation",
                 "Deformer node")),
    # Skin > Unbind Skin: "Detach Skin Options"
    Window("unbind_skin", "Detach Skin Options", "Detach", ("allset.unbind_skin", {}), [
        F("history", "History:", "enum", "Delete history", items=("Delete history", "Keep history", "Bake history")),
        F("remove_colors", "Coloring:", "bool", True, text="Remove joint colors")], _run_unbind,
        paths=("Skin/Unbind Skin",)),
    # Skin > Copy Skin Weights
    Window("copy_skin_weights", "Copy Skin Weights Options", "Copy", ("allset.copy_skin_weights", {}), [
        F("surface", "Surface Association:", "enum", "Closest point on surface",
          items=("Closest point on surface", "Ray cast", "Closest component")),
        F("influence1", "Influence Association 1:", "enum", "Closest joint",
          items=("Closest joint", "Closest bone", "One to one", "Name")),
        F("influence2", "Influence Association 2:", "enum", "None",
          items=("None", "Closest joint", "Closest bone", "One to one", "Name")),
        F("influence3", "Influence Association 3:", "enum", "None",
          items=("None", "Closest joint", "Closest bone", "One to one", "Name")),
        F("normalize", "", "bool", False, text="Normalize")], _run_copy_weights, paths=("Skin/Copy Skin Weights",),
        missing=("Surface Association: UV space", "Influence Association: Label")),
    # Skin > Paint Skin Weights: Tool Settings "Paint Skin Weights Tool"
    Window("paint_skin_weights", "Paint Skin Weights Tool", "Paint Skin Weights", None, [
        F("operation", "Paint operation:", "enum", "Replace", items=("Replace", "Add", "Scale", "Smooth")),
        F("profile", "Profile:", "enum", "Soft", items=("Gaussian", "Soft", "Solid")),
        F("normalize", "Normalize Weights:", "enum", "Interactive", items=("Off", "Interactive", "Post")),
        F("opacity", "Opacity:", "float", 1.0, lo=0.0, hi=1.0), F("value", "Value:", "float", 1.0, lo=0.0, hi=1.0),
        F("radius", "Radius(U):", "float", 1.0, lo=0.0001, hi=1000.0),
        F("screen_projection", "", "bool", False, text="Screen projection"),
        F("show_wireframe", "", "bool", True, text="Show wireframe"),
        F("xray_joints", "", "bool", True, text="XRay Joints")], _run_paint, paths=("Skin/Paint Skin Weights",),
        missing=("Influences sort / filter (the vertex group list)", "Mode: Select / Paint Select", "Weight Type",
                 "Min/Max value", "Gradient / color ramp", "Radius(L)", "Reflection", "Stamp spacing / depth",
                 "Stylus pressure", "Other display options")),
    # Deform > Blend Shape
    Window("blend_shape", "Blend Shape Options", "Create", ("allset.blend_shape", {}), [
        FText("node_name", "BlendShape node:"),
        F("origin", "Origin:", "enum", "Local", items=("Local", "World")),
        F("check_topology", "", "bool", True, text="Check topology"),
        F("delete_targets", "", "bool", False, text="Delete targets")], _run_blend_shape,
        paths=("Deform/Blend Shape",), missing=("Envelope (Blender shape keys have no envelope)",
                                                "Target shape options: In-between")),
    # Constrain > Aim: +X at the target, +Y up, world up Vector (0, 1, 0)
    Window("aim_constraint", "Aim Constraint Options", "Add", ("allset.constrain", {"type": 'TRACK_TO'}), [
        F("aim_vector", "Aim vector:", "vec3", (1.0, 0.0, 0.0)), F("up_vector", "Up vector:", "vec3", (0.0, 1.0, 0.0)),
        F("world_up_type", "World up type:", "enum", "Vector",
          items=("Scene up", "Object up", "Object rotation up", "Vector", "None")),
        F("world_up_vector", "World up vector:", "vec3", (0.0, 1.0, 0.0)),
        FString("world_up_object", "World up object:"),
        F("weight", "Weight:", "float", 1.0, lo=0.0, hi=1.0)], _run_aim, paths=("Constrain/Aim",),
        missing=("Maintain offset / Offset (Blender's Track To has none)",) + _ANIM_LAYER +
        ("Constraint axes (always All)",)),
    # Constrain > Pole Vector: only Weight
    Window("pole_vector", "Pole Vector Constraint Options", "Add", ("allset.pole_vector", {}), [
        F("weight", "Weight:", "float", 1.0, lo=0.0, hi=1.0)], _run_pole_vector, paths=("Constrain/Pole Vector",)),
    # Constrain > Scale
    Window("scale_constraint", "Scale Constraint Options", "Add", ("allset.constrain", {"type": 'COPY_SCALE'}), [
        F("maintain_offset", "Maintain offset:", "bool", False), F("offset", "Offset:", "vec3", (1.0, 1.0, 1.0)),
        F("all", "Constraint axes:", "bool", True, text="All"), F("x", "", "bool", False, text="X"),
        F("y", "", "bool", False, text="Y"), F("z", "", "bool", False, text="Z"),
        F("weight", "Weight:", "float", 1.0, lo=0.0, hi=1.0)], _run_scale, paths=("Constrain/Scale",),
        missing=_ANIM_LAYER),
]

