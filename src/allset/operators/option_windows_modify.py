# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya option windows of the Modify menu: Convert > Geometry to Bounding Box ❒.

Same spec as operators/option_windows.py (``F`` fields, ``Window`` = one ``allset.opt_<key>`` operator;
option_windows._extend appends ``WINDOWS``). Title, labels, button and default values match Maya's
Modify > Convert > Geometry to Bounding Box Options window.
"""

import bpy
from bpy.props import StringProperty

from .option_windows import F, Window
from .option_windows_display import FColor

class FString(F):
    """A Maya text field."""

    def __init__(self, name, label, default=""):
        super().__init__(name, label, "string", default)

    def prop(self):
        return StringProperty(name=self.label.rstrip(":"), default=self.default)


HIERARCHY = ("One bounding box", "One bounding box per shape")


def _run_bbox(context, v):
    return bpy.ops.allset.geometry_to_bbox('EXEC_DEFAULT', name=v["name"], suffix=v["suffix"],
                                           per_shape=v["hierarchy"] == HIERARCHY[1], colour=tuple(v["colour"]),
                                           keep_original=v["keep_original"])


WINDOWS = [
    Window("geom_to_bbox", "Convert Geometry to Bounding Box Options", "Convert", ("allset.geometry_to_bbox", {}), [
        FString("name", "Name"),
        FString("suffix", "Name suffix", "_BBox"),
        F("hierarchy", "Represent hierarchy as:", "enum", HIERARCHY[0], items=HIERARCHY),
        FColor("colour", "Color", default=(0.5, 0.5, 0.5)),
        F("keep_original", "", "bool", False, text="Keep original")], _run_bbox,
        paths=("Modify/Convert/Geometry to Bounding Box",),
        missing=("Combine resulting bounding boxes (per shape)", "Bake Animation: Time range, Sample by")),
]
