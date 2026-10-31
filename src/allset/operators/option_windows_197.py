# SPDX-License-Identifier: GPL-3.0-or-later
"""#104: Maya's Cleanup Options window for Mesh > Cleanup... (operators/poly_cleanup.py).

Title / button / labels / default values match Maya's Cleanup Options window.
"""

from .option_windows import F, Window
from .poly_cleanup import run_window

WINDOWS = [
    Window("poly_cleanup", "Cleanup Options", "Cleanup", None, [
        F("operation", "Operation:", "enum", "Cleanup matching polygons",
          items=("Cleanup matching polygons", "Select matching polygons"), heading="Cleanup Effect"),
        F("scope", "Scope:", "enum", "Apply to selected objects",
          items=("Apply to selected objects", "Apply to all polygonal objects")),
        F("quads", "", "bool", False, text="4-sided faces", heading="Fix by Tesselation"),
        F("nsided", "", "bool", False, text="Faces with more than 4 sides"),
        F("concave", "", "bool", False, text="Concave faces"),
        F("holes", "", "bool", False, text="Faces with holes"),
        F("nonplanar", "", "bool", False, text="Non-planar faces"),
        F("lamina", "", "bool", False, text="Lamina faces (faces sharing all edges)", heading="Remove Geometry"),
        F("nonmanifold", "", "bool", False, text="Nonmanifold geometry"),
        F("nonmanifold_type", "", "enum", "Normals and geometry", items=("Normals and geometry", "Geometry only")),
        F("zero_edge", "", "bool", False, text="Edges with zero length"),
        F("edge_tol", "Length tolerance:", "float", 0.00001, lo=0.0, hi=1.0),
        F("zero_face", "", "bool", False, text="Faces with zero geometry area"),
        F("face_tol", "Area tolerance:", "float", 0.00001, lo=0.0, hi=1.0),
        F("zero_map", "", "bool", False, text="Faces with zero map area"),
        F("map_tol", "Area tolerance:", "float", 0.00001, lo=0.0, hi=1.0),
    ], run_window, paths=("Mesh/Cleanup...",),
        missing=("Keep construction history (Blender keeps no polyCleanup node)", "Invalid Components")),
]
