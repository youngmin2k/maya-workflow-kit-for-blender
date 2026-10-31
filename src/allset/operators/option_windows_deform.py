# SPDX-License-Identifier: GPL-3.0-or-later
"""#34: Maya option windows of the Deform menu: same spec as operators/option_windows.py (``F`` fields,
``Window`` = one ``allset.opt_<key>`` operator; option_windows._extend appends ``WINDOWS``).

Titles, buttons, Basic tab fields in screen order and default values match Maya's Deform
option windows. Every Python-built deformer box also has an
Advanced tab (Deformation order / Exclusive / Partition): Blender's modifier stack
has none of them, so they and every Basic field Blender can't honour are listed as ``missing``, never faked.
The deformers themselves: operators/deformers.py.
"""

import bpy
from bpy.props import IntVectorProperty

from .option_windows import F, Window
from .option_windows_modify import FString


class FDivisions(F):
    """Maya's three-int field (Lattice Divisions S T U)."""

    def __init__(self, name, label, default):
        super().__init__(name, label, "vec3int", default)

    def prop(self):
        return IntVectorProperty(name=self.label.rstrip(":"), default=self.default, size=3, min=2, soft_max=50)


ADVANCED = ("Deformation order (Advanced tab; the modifier stack order)",
            "Exclusive / Partition to use / Partition name (Advanced tab)")
ENVELOPE = "Envelope (the modifier has no strength)"


def _create(kind):
    def run(context, v):
        from . import deformers
        deformers.create(context, kind, v)
        return {'FINISHED'}
    return run


def _cluster(context, v):
    return bpy.ops.allset.cluster('EXEC_DEFAULT', envelope=float(v["envelope"]))


def _soft_mod(context, v):
    return bpy.ops.allset.soft_mod('EXEC_DEFAULT', radius=float(v["radius"]))


def _match(kind):
    return ("allset.deformer", {"kind": kind})


def _bounds():
    return [F("low", "Low bound:", "float", -1.0, lo=-10.0, hi=0.0),
            F("high", "High bound:", "float", 1.0, lo=0.0, hi=10.0)]


def _wire_edit(action):
    def run(context, v):
        return bpy.ops.allset.wire_edit('EXEC_DEFAULT', action=action, node=v["node"] if v["specify"] else "")
    return run


def _dropoff_locator(context, v):
    return bpy.ops.allset.wire_dropoff_locator('EXEC_DEFAULT', node=v["node"], envelope=float(v["envelope"]),
                                               percent=float(v["percent"]))


def _point_on_curve(context, v):
    return bpy.ops.allset.point_on_curve('EXEC_DEFAULT', weight=float(v["weight"]))


def PAINT_FIELDS():                                         # noqa: N802  (a field list, like _bounds())
    return [F("operation", "Paint operation:", "enum", "Replace", items=("Replace", "Add", "Scale", "Smooth")),
            F("profile", "Profile:", "enum", "Soft", items=("Gaussian", "Soft", "Solid")),
            F("opacity", "Opacity:", "float", 1.0, lo=0.0, hi=1.0), F("value", "Value:", "float", 1.0, lo=0.0, hi=1.0),
            F("radius", "Radius(U):", "float", 1.0, lo=0.0001, hi=1000.0)]


PAINT_MISSING = ("Radius(L) 0.001", "Min/Max value 0 / 1", "Rotate to stroke", "Vector index",
                 "Stamp spacing / depth", "Stylus pressure")


def _paint(kind):
    """Start painting this deformer's weights (Set Membership: Blender's Weight Paint toggle) with the window's
    Maya tool values (operators/skin.apply_paint_settings; deformer weights are never normalized)."""
    def run(context, v):
        from . import option_windows_rig, skin
        if kind:
            res = bpy.ops.allset.paint_deformer_weights('EXEC_DEFAULT', kind=kind)
        else:
            res = bpy.ops.paint.weight_paint_toggle('EXEC_DEFAULT') if context.mode != 'PAINT_WEIGHT' else {'FINISHED'}
        if res != {'FINISHED'}:
            return res
        values = {"operation": option_windows_rig._PAINT_OPS[v["operation"]],
                  "profile": option_windows_rig._PROFILES[v["profile"]], "normalize": None,
                  "opacity": v["opacity"], "value": v["value"], "radius": v["radius"], "screen_projection": False,
                  "show_wireframe": True, "xray_joints": False}
        refused = skin.apply_paint_settings(context, context.active_object, None, values)
        if refused:
            raise RuntimeError("Blender kept its brush for: " + ", ".join(refused))
        return res
    return run


_BOUNDS_NOTE = "Bounds beyond the object (Blender limits stop at its ends)"

WINDOWS = [
    # Lattice Options (Lattice row): Divisions 2 5 2, Center around selection on
    Window("deform_lattice", "Lattice Options", "Create", _match('LATTICE'), [
        FDivisions("divisions", "Divisions:", (2, 5, 2)),
        F("center", "", "bool", True, text="Center around selection"),
        F("auto_parent", "", "bool", False, text="Auto parent to selection")], _create('LATTICE'),
        paths=("Deform/Lattice",),
        missing=("Use local mode / Local divisions (B-spline over all points)",
                 "Group base and lattice (ffd1Base is a Hook modifier)",
                 "Freeze geometry", "Bind original geometry",
                 "Outside lattice / Falloff distance (all group points move)") + ADVANCED),
    # Delta Mush Options: Smoothing iterations 10, Smoothing Step = 0.5, Pin border vertices on
    Window("deform_delta_mush", "Delta Mush Options", "Create", _match('DELTA_MUSH'), [
        F("iterations", "Smoothing iterations:", "int", 10, lo=0, hi=50),
        F("step", "Smoothing step:", "float", 0.5, lo=0.0, hi=1.0),
        F("pin_border", "", "bool", True, text="Pin border vertices")], _create('DELTA_MUSH'),
        paths=("Deform/Delta Mush",),
        missing=("Displacement 1.0", "Inward constraint / Outward constraint", "Distance weight", ENVELOPE)
        + ADVANCED),
    # Wrap Options (no tabs): Render influence objects off
    Window("deform_wrap", "Wrap Options", "Create", _match('WRAP'), [
        F("render_influence", "", "bool", False, text="Render influence objects")], _create('WRAP'),
        paths=("Deform/Wrap",),
        missing=("Exclusive bind", "Auto weight threshold / Weight threshold", "Use max distance / Max distance",
                 "Falloff mode Volume (Surface Deform binds to the surface)",
                 "pCube2Base (the modifier keeps the bound shape)")),
    # Proximity Wrap Options: Wrap mode Surface = Surface Deform; the rest has no Blender setting
    Window("deform_proximity_wrap", "Proximity Wrap Options", "Create", _match('PROXIMITY_WRAP'), [],
           _create('PROXIMITY_WRAP'), paths=("Deform/Proximity Wrap",),
           missing=("Wrap mode (always Surface: Blender's Surface Deform)", "Max drivers 5 (one driver)",
                    "Falloff scale", "Smooth influences / Smooth normals") + ADVANCED),
    # ShrinkWrap Options: Projection Toward Inner Object ...
    Window("deform_shrink_wrap", "ShrinkWrap Options", "Create", _match('SHRINK_WRAP'), [
        F("projection", "Projection:", "enum", "Toward Inner Object",
          items=("Toward Inner Object", "Toward Center", "Parallel To Axes", "Vertex Normals", "Closest")),
        F("bidirectional", "", "bool", False, text="Bidirectional"),
        F("reverse", "", "bool", False, text="Reverse"),
        F("offset", "Offset:", "float", 0.0, lo=-10.0, hi=10.0),
        F("along_x", "", "bool", False, text="Along X"), F("along_y", "", "bool", False, text="Along Y"),
        F("along_z", "", "bool", False, text="Along Z")], _create('SHRINK_WRAP'), paths=("Deform/ShrinkWrap",),
        missing=("Closest If No Intersection", "Target Inflation", "Bounding Box Center", "Axis Reference",
                 "Single ShrinkWrap Node (one modifier per object)", "Toward Center (Blender: closest point)",
                 ENVELOPE)),
    # Cluster Options: Relative mode off, Envelope 1
    Window("deform_cluster", "Cluster Options", "Create", ("allset.cluster", {}), [
        F("envelope", "Envelope:", "float", 1.0, lo=0.0, hi=1.0)], _cluster, paths=("Deform/Cluster",),
        missing=("Relative mode (the Hook follows the handle's world position)",) + ADVANCED),
    # Soft Modification Options (button "Soft Modification"): Falloff radius 5
    Window("deform_soft_mod", "Soft Modification Options", "Soft Modification", ("allset.soft_mod", {}), [
        F("radius", "Falloff radius:", "float", 5.0, lo=0.0, hi=100.0)], _soft_mod,
        paths=("Deform/Soft Modification Tool",),
        missing=("Falloff curve (fixed: Maya's smooth curve)", "Falloff mode Surface (Blender: Volume)",
                 "Color Feedback", "Preserve history", "Mask unselected", "Falloff around selection",
                 "Falloff based on X / Y / Z")),
    # Nonlinear: Bend / Flare / Sine / Squash / Twist / Wave Options
    Window("deform_bend", "Bend Options", "Create", _match('BEND'), _bounds() + [
        F("curvature", "Curvature:", "float", 0.0, lo=-4.0, hi=4.0)], _create('BEND'),
        paths=("Deform/Nonlinear/Bend",), missing=(_BOUNDS_NOTE, ENVELOPE) + ADVANCED),
    Window("deform_flare", "Flare Options", "Create", _match('FLARE'), _bounds() + [
        F("end_flare", "End flare X:", "float", 1.0, lo=0.0, hi=10.0)], _create('FLARE'),
        paths=("Deform/Nonlinear/Flare",),
        missing=("Start flare X / Z (Blender tapers from 1 at the low end)",
                 "End flare Z (Blender tapers X and Z together: End flare X)", "Curve", _BOUNDS_NOTE, ENVELOPE)
        + ADVANCED),
    Window("deform_sine", "Sine Options", "Create", _match('SINE'), [
        F("amplitude", "Amplitude:", "float", 0.0, lo=-5.0, hi=5.0),
        F("wavelength", "Wavelength:", "float", 2.0, lo=0.1, hi=10.0)], _create('SINE'),
        paths=("Deform/Nonlinear/Sine",),
        missing=("Low bound / High bound (Blender's Wave has none)", "Dropoff", "Offset",
                 "A true sine shape (Blender's Wave modifier ripples)", ENVELOPE) + ADVANCED),
    Window("deform_squash", "Squash Options", "Create", _match('SQUASH'), _bounds() + [
        F("factor", "Factor:", "float", 0.0, lo=-10.0, hi=10.0)], _create('SQUASH'),
        paths=("Deform/Nonlinear/Squash",),
        missing=("Start smoothness / End smoothness", "Max expand position / Expand (Blender keeps the volume)",
                 _BOUNDS_NOTE, ENVELOPE) + ADVANCED),
    Window("deform_twist", "Twist Options", "Create", _match('TWIST'), _bounds() + [
        F("end_angle", "End angle:", "float", 0.0, lo=-360.0, hi=360.0)], _create('TWIST'),
        paths=("Deform/Nonlinear/Twist",),
        missing=("Start angle (Blender twists from 0 at the handle)", _BOUNDS_NOTE, ENVELOPE) + ADVANCED),
    Window("deform_wave", "Wave Options", "Create", _match('WAVE'), [
        F("max_radius", "Max radius:", "float", 1.0, lo=0.0, hi=10.0),
        F("amplitude", "Amplitude:", "float", 0.0, lo=-5.0, hi=5.0),
        F("wavelength", "Wavelength:", "float", 1.0, lo=0.1, hi=10.0)], _create('WAVE'),
        paths=("Deform/Nonlinear/Wave",),
        missing=("Min radius", "Dropoff", "Offset", ENVELOPE) + ADVANCED),
    # Texture Options (Advanced tab empty)
    Window("deform_texture", "Texture Options", "Create", _match('TEXTURE'), [
        F("point_space", "Point Space:", "enum", "UV", items=("World", "Local", "UV")),
        F("direction", "Direction:", "enum", "Handle", items=("Normal", "Handle", "Vector")),
        F("vector_space", "Vector Space:", "enum", "Object", items=("Object", "World", "Tangent")),
        F("strength", "Strength:", "float", 1.0, lo=-10.0, hi=10.0),
        F("offset", "Offset:", "float", 0.0, lo=-10.0, hi=10.0)], _create('TEXTURE'), paths=("Deform/Texture",),
        missing=("Vector Strength / Vector Offset", "Vector Space Tangent", ENVELOPE,
                 "textureDeformerHandle1 (Handle = the object's up axis)")),
    # Wire Tool settings = a window titled with
    # the tool name whose button makes the wire (select the objects, then the curve)
    Window("deform_wire", "Wire Tool", "Create", _match('WIRE'), [
        F("envelope", "Envelope:", "float", 1.0, lo=0.0, hi=1.0),
        F("dropoff", "Dropoff distance:", "float", 1.0, lo=0.0, hi=100.0)], _create('WIRE'), paths=("Deform/Wire",),
        missing=("Holders (Deform > Wire > Add Holder)", "Crossing effect 0 / Local influence 0 (the factory "
                 "values: no effect)", "Grouping: Group wire(s) and base wire(s) (Wire > Parent Base Wire)")
        + ADVANCED[:1]),
    *[Window(f"wire_{key.lower()}", title, "Apply and Close", None, [
        F("specify", "Specify node:", "bool", False, text=""),
        FString("node", "Wire node:")], _wire_edit(key), paths=(f"Deform/Wire#2/{label}",),
        missing=("Existing nodes: (type the wire node's name)",))
      for key, label, title in (("ADD", "Add", "Add Wire Options"), ("REMOVE", "Remove", "Remove Wire Options"),
                                ("RESET", "Reset", "Reset Wire Options"),
                                ("PARENT_BASE", "Parent Base Wire", "Parent Base Wire Options"))],
    Window("wire_dropoff_locator", "Wire Dropoff Locator Options", "Apply and Close",
           ("allset.wire_dropoff_locator", {}), [
               FString("node", "Wire node:"),
               F("envelope", "Envelope:", "float", 1.0, lo=0.0, hi=1.0),
               F("percent", "Percent:", "float", 1.0, lo=0.0, hi=10.0)], _dropoff_locator,
           paths=("Deform/Wire#2/Wire Dropoff Locator",), missing=("Existing wire nodes: (type the name)",)),
    # Point On Curve Options: Keep original off, Point weight 1
    Window("point_on_curve", "Point On Curve Options", "Create", ("allset.point_on_curve", {}), [
        F("weight", "Point weight:", "float", 1.0, lo=0.0, hi=1.0)], _point_on_curve,
        paths=("Deform/Point On Curve",),
        missing=("Keep original (the curve is always the original)",
                 "Least-squares fit through the point (Blender hooks the selected control point)")),
    # Paint Weights > <deformer> boxes = the Paint Attributes Tool settings ("Paint tool factory
    # brush"; Blend Shape: Paint Blend Shape Weights Tool), the button starts painting with them
    *[Window(f"paint_weights_{(kind or 'membership').lower()}", "Paint Blend Shape Weights Tool" if kind == "blendShape" else
             "Paint Attributes Tool", "Paint", None, PAINT_FIELDS(), _paint(kind),
             # Maya 2026 moved Paint Weights > Set Membership to Deform > Paint Membership
             paths=("Deform/Paint Membership",) if not kind else (f"Deform/Paint Weights/{label}",),
             missing=PAINT_MISSING)
      for label, kind in (("Blend Shape", "blendShape"), ("Cluster", "cluster"), ("Delta Mush", "deltaMush"),
                          ("Proximity Wrap", "proximityWrap"), ("Lattice", "ffd"), ("ShrinkWrap", "shrinkWrap"),
                          ("Wire", "wire"), ("Nonlinear", "nonLinear"), ("Texture Deformer", "textureDeformer"),
                          ("Set Membership", ""))],
]
