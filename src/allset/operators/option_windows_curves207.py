# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya option windows of Curves > Bend / Curl / Scale Curvature (same spec as operators/option_windows.py).
Titles, labels and default values match Maya's Bend / Curl / Scale Curvature Options windows."""

import bpy

from .option_windows import F, Window


def _run(kind, a, b):
    def run(context, v):
        return bpy.ops.allset.curve_modify('EXEC_DEFAULT', kind=kind, amount=v[a], second=v[b])
    return run


WINDOWS = [
    Window("bend_curves", "Bend Curves Options", "Bend Curves", None, [
        F("amount", "Bend amount:", "float", 0.2, lo=-10.0, hi=10.0),
        F("twist", "Twist:", "float", 0.0, lo=0.0, hi=1.0),
    ], _run('BEND', "amount", "twist"), paths=("Curves/Bend",)),
    Window("curl_curves", "Curl Curves Options", "Curl Curves", None, [
        F("amount", "Curl amount:", "float", 0.3, lo=-10.0, hi=10.0),
        F("frequency", "Curl frequency:", "float", 1.0, lo=0.0, hi=100.0),
    ], _run('CURL', "amount", "frequency"), paths=("Curves/Curl",)),
    Window("scale_curvature", "Scale Curvature Options", "Scale Curvature", None, [
        F("factor", "Scale factor:", "float", 1.1, lo=0.0, hi=10.0),
        F("max_curvature", "Max curvature:", "float", 0.8, lo=0.0, hi=10.0),
    ], _run('CURVATURE', "factor", "max_curvature"), paths=("Curves/Scale Curvature",)),
]
