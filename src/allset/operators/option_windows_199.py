# SPDX-License-Identifier: GPL-3.0-or-later
"""#106: Maya option windows of the new Skin / Constrain commands.

Titles, buttons, labels and default values match the Maya option windows.
Fields the kit can't honour
are listed (``missing``), never faked.
"""

import bpy
from mathutils import Vector

from .option_windows import F, Window

WORLD_UP = ("Scene up", "Vector", "None")


def _aim_like(op_name):
    def run(context, v):
        up = Vector(v["world_up_vector"])
        if v["world_up_type"] == "Vector" and (up.length < 1e-9 or (up.normalized() - Vector((0, 1, 0))).length > 1e-6):
            raise RuntimeError("The kit turns the up vector towards the scene up only: World up vector must be 0 1 0 "
                               "(Maya Y)")
        return getattr(bpy.ops.allset, op_name)(
            'EXEC_DEFAULT', weight=v["weight"], aim_vector=v["aim_vector"], up_vector=v["up_vector"],
            world_up_type=v["world_up_type"])
    return run


def _aim_fields():
    return [F("aim_vector", "Aim vector:", "vec3", (1.0, 0.0, 0.0)),
            F("up_vector", "Up vector:", "vec3", (0.0, 1.0, 0.0)),
            F("world_up_type", "World up type:", "enum", "Vector", items=WORLD_UP),
            F("world_up_vector", "World up vector:", "vec3", (0.0, 1.0, 0.0)),
            F("weight", "Weight:", "float", 1.0, lo=0.0, hi=1.0)]


_AIM_MISSING = ("World up type: Object up / Object rotation up", "World up object")

REMOVE_TYPES = (("point", "Point constraint"), ("orient", "Orient constraint"), ("aim", "Aim constraint"),
                ("scale", "Scale constraint"), ("parent", "Parent constraint"), ("geometry", "Geometry constraint"),
                ("normal", "Normal constraint"), ("tangent", "Tangent constraint"),
                ("pole_vector", "Pole vector constraint"))


def _run_remove(context, v):
    kw = {k: v[k] for k, _l in REMOVE_TYPES}
    return bpy.ops.allset.remove_constraint_target('EXEC_DEFAULT', remove_all=v["remove_all"], **kw)


def _run_axes(context, v):
    return bpy.ops.allset.modify_constraint_axes('EXEC_DEFAULT', x=v["x"], y=v["y"], z=v["z"],
                                                maintain_offset=v["maintain_offset"])


def _run_substitute(context, v):
    return bpy.ops.allset.substitute_geometry('EXEC_DEFAULT', reweight_distance=v["reweight_distance"],
                                             retain_old=v["retain_old"], disable_non_skin=v["disable_non_skin"])


WINDOWS = [
    # Normal Constraint Options (factory aim 1 0 0, up 0 1 0, world up Vector 0 1 0, weight 1)
    Window("normal_constraint", "Normal Constraint Options", "Add", ("allset.normal_constraint", {}), _aim_fields(),
           _aim_like("normal_constraint"), paths=("Constrain/Normal",), missing=_AIM_MISSING),
    Window("tangent_constraint", "Tangent Constraint Options", "Add", ("allset.tangent_constraint", {}),
           _aim_fields(), _aim_like("tangent_constraint"), paths=("Constrain/Tangent",), missing=_AIM_MISSING),
    # Remove Target Options: all targets, every type, Maintain offset off
    Window("remove_constraint_target", "Remove Target Options", "Remove", ("allset.remove_constraint_target", {}),
           [F("remove_all", "Constraint type:", "bool", True, text="All")]
           + [F(k, "", "bool", True, text=label) for k, label in REMOVE_TYPES],
           _run_remove, paths=("Constrain/Remove Target",),
           missing=("Point on poly constraint (the kit's is a Shrinkwrap = Geometry)", "Maintain offset")),
    # Modify Constrained Axis Options: X / Y / Z on, Maintain offset off
    Window("modify_constraint_axes", "Modify Constrained Axis Options", "Modify",
           ("allset.modify_constraint_axes", {}),
           [F("x", "Constrain:", "bool", True, text="X"), F("y", "", "bool", True, text="Y"),
            F("z", "", "bool", True, text="Z"), F("maintain_offset", "", "bool", False, text="Maintain offset")],
           _run_axes, paths=("Constrain/Modify Constrained Axis...",)),
    # Substitute Geometry Options
    Window("substitute_geometry", "Substitute Geometry Options", "Substitute Geometry",
           ("allset.substitute_geometry", {}),
           [F("reweight_distance", "Re-weighting distance tolerance:", "float", 1.0, lo=0.0, hi=10.0),
            F("disable_non_skin", "", "bool", False, text="Disable non-skin deformers"),
            F("retain_old", "", "bool", False, text="Retain old geometry")],
           _run_substitute, paths=("Skin/Substitute Geometry",),
           missing=("Move new geometry to a layer", "Move old geometry to a layer")),
]
