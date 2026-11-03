# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya option windows of the Trax Editor: Create > Animation Clip (Create Clip Options).

Same spec as operators/option_windows.py. Defaults like Maya: Name clip1, keys leave the timeline, the clip goes on
the Trax tracks and into the library, time range = the animation curves' key range (Start / End 0 / 10), the
hierarchy below the selection and the subcharacters are included. The clip keeps its absolute values: Maya's
Offset Relative (a clip continuing from the previous clip's last value) and the time warp curve have no field.
"""

import bpy

from .option_windows import F, Window
from .option_windows_modify import FString
from . import trax_clips as tc


def _run_create_clip(context, v):
    return bpy.ops.allset.trax_create_clip(
        'EXEC_DEFAULT', clip_name=v["name"], leave_keys=v["leave_keys"], visor_only=v["clip"] == tc.SCHEDULE[1],
        time_range=v["time_range"], start=v["start"], end=v["end"], hierarchy=v["hierarchy"],
        subcharacters=v["subcharacters"])


WINDOWS = [
    Window("create_clip", "Create Clip Options", "Create Clip", ("allset.trax_create_clip", {}), [
        FString("name", "Name:", "clip1"),
        F("leave_keys", "Keys:", "bool", False, text="Leave keys in timeline"),
        F("clip", "Clip:", "enum", tc.SCHEDULE[0], items=list(tc.SCHEDULE)),
        F("time_range", "Time range:", "enum", "Animation curve", items=list(tc.RANGES)),
        F("start", "Start time:", "float", 0.0),
        F("end", "End time:", "float", 10.0),
        F("hierarchy", "", "bool", True, text="Include Hierarchy"),
        F("subcharacters", "Subcharacters:", "bool", True, text="Include subcharacters in clip"),
    ], _run_create_clip, paths=("Trax Editor/Create/Animation Clip",),
        missing=("Offset: Relative", "Time warp")),
]
