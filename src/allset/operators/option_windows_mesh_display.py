# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya option windows of the Mesh Display menu: Set Vertex Normal, Average, Set to Face, Apply Color.

Fields and default values match the Maya option windows.
"""

import bpy

from .option_windows import F, Window
from .option_windows_display import FColor


def _run_set_normal(context, v):
    x, y, z = v["normal"]
    return bpy.ops.allset.set_vertex_normal('EXEC_DEFAULT', x=x, y=y, z=z)


def _run_average(context, v):
    return bpy.ops.allset.average_normals('EXEC_DEFAULT', distance=v["distance"])


def _run_to_face(context, v):
    return bpy.ops.allset.set_to_face_normal('EXEC_DEFAULT', user_normal=v["user_normal"])


_OPS = {"Replace": 'REPLACE', "Add": 'ADD', "Subtract": 'SUBTRACT', "Remove": 'REMOVE'}


def _run_apply_color(context, v):
    return bpy.ops.allset.apply_color('EXEC_DEFAULT', operation=_OPS[v["operation"]], color=v["color"],
                                      alpha=v["alpha"])


_BLENDS = ("Overwrite", "Add", "Subtract", "Multiply", "Divide", "Average")   # vertexBakeSet colorBlending 0-5


def _run_prelight(context, v):
    return bpy.ops.allset.prelight('EXEC_DEFAULT', use_options=True, bake_color=v["bake_color"],
                                   bake_alpha=v["bake_alpha"], color_blending=_BLENDS.index(v["color_blending"]),
                                   alpha_blending=_BLENDS.index(v["alpha_blending"]), scale_rgba=v["scale_rgba"])


class FApplyColor(FColor):
    """Apply Color's colour: Maya stores the value as is (0.5 grey, any float)."""

    def __init__(self):
        super().__init__("color", "Color value:", (0.5, 0.5, 0.5))


WINDOWS = [
    # Mesh Display > Set Vertex Normal (factory: 1, 0, 0)
    Window("set_vertex_normal", "Set Vertex Normal Options", "Set Normal", ("allset.set_vertex_normal", {}), [
        F("normal", "Vertex normal:", "vec3", (1.0, 0.0, 0.0)),
    ], _run_set_normal, paths=("Mesh Display/Set Vertex Normal",)),
    # Mesh Display > Average (factory: prenormalize, no zero normals, distance 0.1)
    Window("average_normals", "Average Normals Options", "Average", ("allset.average_normals", {}), [
        F("distance", "Distance:", "float", 0.1, lo=0.0, hi=10.0),
    ], _run_average, paths=("Mesh Display/Average",),
        missing=("Normalize: Before / After / Not (Before)", "Allow zero normals / Replace zero normal with (1, 0, 0)")),
    # Mesh Display > Set to Face (factory: user normal off)
    Window("set_to_face", "Set to Face Normal Options", "Set to Face", ("allset.set_to_face_normal", {}), [
        F("user_normal", "", "bool", False, text="Set user normal"),
    ], _run_to_face, paths=("Mesh Display/Set to Face",)),
    # Mesh Display > Apply Color (factory: Replace, all channels, 0.5 grey, alpha 1)
    Window("apply_color", "Apply Color Options", "Apply Color", ("allset.apply_color", {}), [
        F("operation", "Operation:", "enum", "Replace", items=tuple(_OPS)),
        FApplyColor(),
        F("alpha", "Alpha value:", "float", 1.0, lo=0.0, hi=1.0),
    ], _run_apply_color, paths=("Mesh Display/Apply Color",),
        missing=("Individual channels (Red / Green / Blue / Alpha each on its own)",)),
    # Mesh Display > Prelight (Maya) (values = vertexBakeSet factory attributes)
    Window("prelight", "Prelight (Maya) Options", "Prelight", ("allset.prelight", {}), [
        F("bake_color", "", "bool", True, text="Bake shading group lighting"),
        F("bake_alpha", "", "bool", False, text="Bake alpha"),
        F("color_blending", "Color blending:", "enum", "Overwrite", items=_BLENDS),
        F("alpha_blending", "Alpha blending:", "enum", "Overwrite", items=_BLENDS),
        F("scale_rgba", "Scale RGBA:", "float", 1.0, lo=0.0, hi=10.0),
    ], _run_prelight, paths=("Mesh Display/Prelight (Maya)",),
        missing=("Sample by face / Shared vertices / Normal direction", "Ambient occlusion rays / falloff",
                 "Clamp min / max", "Filter size / sample")),
]
