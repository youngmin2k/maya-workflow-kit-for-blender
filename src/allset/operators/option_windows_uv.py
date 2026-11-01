# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya option windows of UV Editor > Modify > Straighten UVs and Randomize Shells.

Same spec as operators/option_windows.py (``F`` fields, ``Window`` = one ``allset.opt_<key>`` operator bound to its
menu paths; option_windows._extend appends ``WINDOWS``). Defaults: Straighten UVs straightens along U and V within
30 degrees; Randomize Shells moves shells up to 0.1 along U and V and neither turns nor scales them (22.5 degrees and
10 percent once those are switched on).
"""

import bpy

from .option_windows import F, Window
from . import uv_toolkit_ops as tk


def _run_straighten(context, v):
    return bpy.ops.allset.uv_straighten_uvs('EXEC_DEFAULT', axis=v["direction"], tolerance=v["angle"])


def _run_randomize(context, v):
    return bpy.ops.allset.uv_randomize(
        'EXEC_DEFAULT', translate_u=v["translate_u"], translate_v=v["translate_v"], translate=v["translate"],
        rotate_cw=v["rotate_cw"], rotate_ccw=v["rotate_ccw"], rotate=v["rotate"],
        scale_up=v["scale_up"], scale_down=v["scale_down"], scale=v["scale"])


WINDOWS = [
    Window("straighten_uvs", "Straighten UVs Options", "Straighten UVs", None, [
        F("direction", "Straighten:", "enum", "UV", items=["UV", "U", "V"]),
        F("angle", "Angle tolerance:", "float", tk.STRAIGHTEN_TOLERANCE, lo=0.0, hi=90.0),
    ], _run_straighten, paths=("UV Editor/Modify/Straighten UVs",)),
    Window("randomize_shells", "Randomize Shells Options", "Randomize", None, [
        F("translate_u", "Translate:", "bool", True, text="U"),
        F("translate_v", "", "bool", True, text="V"),
        F("translate", "Units:", "float", tk.RANDOM_TRANSLATE, lo=0.001, hi=1.0),
        F("rotate_cw", "Rotate:", "bool", False, text="Clockwise"),
        F("rotate_ccw", "", "bool", False, text="Counter-clockwise"),
        F("rotate", "Degrees:", "float", tk.RANDOM_ROTATE, lo=1.0, hi=180.0),
        F("scale_up", "Scale:", "bool", False, text="Up"),
        F("scale_down", "", "bool", False, text="Down"),
        F("scale", "Percent:", "float", tk.RANDOM_SCALE, lo=0.1, hi=100.0),
    ], _run_randomize, paths=("UV Editor/Modify/Randomize Shells",)),
]
