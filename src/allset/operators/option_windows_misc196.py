# SPDX-License-Identifier: GPL-3.0-or-later
"""Issue #103: Maya option windows that were Blender's Adjust Last Operation ("redo") or the generic
"no settings" window — Create Character Set / Subcharacter Set, Curves Cut / Detach / Reverse Direction / Smooth (both)
/ Straighten, the circular arc tools, UV Merge UVs / Contour Stretch, Set / Assume Preferred Angle, Add Influence.

Same spec as operators/option_windows.py (``F`` fields, ``Window`` = one ``allset.opt_<key>`` operator, bound to its
menu paths; option_windows._extend appends ``WINDOWS``). Titles, buttons, labels and default values match the Maya
option windows; fields the kit
can't honour are only listed (``missing``), never faked. Every window run with its defaults does what the plain menu
item does; Merge UVs / Smooth (Modify section) run the kit's Maya operators, like their plain menu items
(menu_map).
"""

import bpy

from .option_windows import F, Window, _op
from .option_windows_rig import FText

# --- run helpers ---------------------------------------------------------------------------------------

_ATTRS = {"All keyable": 'ALL', "From Channel Box": 'CHANNEL_BOX', "All keyable except:": 'EXCEPT'}


def _character(sub):
    def run(context, v):
        return bpy.ops.allset.character_create(
            'EXEC_DEFAULT', sub=sub, character_name=v["name"], attributes=_ATTRS[v["attributes"]],
            exclude_translate=v["no_translate"], exclude_rotate=v["no_rotate"], exclude_scale=v["no_scale"],
            exclude_visibility=v["no_visibility"], exclude_dynamic=v["no_dynamic"],
            hierarchy=v.get("hierarchy", False))
    return run


def _run_cut(context, v):
    return bpy.ops.allset.curve_cut('EXEC_DEFAULT', last_only=v["cut"] == "Using last curve",
                                    keep_longest=v["keep"] == "Longest segments")


def _run_detach(context, v):
    return bpy.ops.allset.curve_detach('EXEC_DEFAULT')


def _keep_copies(context, suffix):
    """Maya Keep original (object mode): the selected curves are duplicated, the copies — named
    ``<curve><suffix>N`` (``curveAreversedCurve1``, ``curveAsmoothCurve1``) — become the selection and get the
    command; the originals stay unchanged."""
    from . import naming
    if context.mode != 'OBJECT':
        return
    originals = [o for o in context.selected_objects if o.type == 'CURVE']
    for o in context.selected_objects:
        if o.type != 'CURVE':
            o.select_set(False)
    copies = []
    for o in originals:
        c = o.copy()
        c.data = o.data.copy()
        for coll in o.users_collection:
            coll.objects.link(c)
        naming.apply_maya_name(c, f"{o.name}{suffix}")
        o.select_set(False)
        c.select_set(True)
        copies.append(c)
    if copies:
        context.view_layer.objects.active = copies[-1]


def _run_reverse(context, v):
    """Curves > Reverse Direction: Blender's Switch Direction in edit mode (the plain item); in object mode every
    selected curve is reversed whole (CVs reversed, knots mirrored)."""
    if v["keep_original"]:
        _keep_copies(context, "reversedCurve")
    if context.mode == 'EDIT_CURVE':
        return _op("curve.switch_direction")
    from . import curves_maya as cmaya
    from . import curves_math as cm
    obs = [o for o in context.selected_objects if o.type == 'CURVE']
    if not obs:
        raise RuntimeError("Select curves to reverse")
    for ob in obs:
        out = []
        for sp in ob.data.splines:
            c = cmaya.read_spline(sp)
            if sp.type != 'BEZIER':
                res = cm.reverse(c.cvs, c.knots, c.weights)
                c = cmaya.MCurve(res[0], res[1], c.degree, res[2] if len(res) > 2 else None, c.periodic)
            out.append(c)
        cmaya._replace_splines(ob, out)
    return {'FINISHED'}


def _run_smooth_curves(context, v):
    return bpy.ops.allset.curve_smooth_curves('EXEC_DEFAULT', factor=v["factor"])


def _run_smooth_curve(context, v):
    """Curves > Smooth (Edit section): Blender's curve Smooth on the selected points (the plain item); Keep original
    smooths copies (all their points)."""
    if not v["keep_original"] or context.mode != 'OBJECT':
        return _op("curve.smooth")
    _keep_copies(context, "smoothCurve")
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        bpy.ops.curve.select_all(action='SELECT')
        return _op("curve.smooth")
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')


def _run_straighten(context, v):
    return bpy.ops.allset.curve_straighten('EXEC_DEFAULT', straightness=v["straightness"],
                                           preserve_length=v["preserve_length"])


def _arc(op_name):
    def run(context, v):
        op = getattr(bpy.ops.allset, op_name)
        return op('INVOKE_DEFAULT', degree=1 if v["degree"].startswith("1") else 3, sections=v["sections"])
    return run


def _run_merge_uvs(context, v):
    return bpy.ops.allset.uv_merge('EXEC_DEFAULT', distance=v["threshold"])


def _run_contour(context, v):
    return bpy.ops.allset.uv_contour('EXEC_DEFAULT')


def _preferred(op_name):
    def run(context, v):
        return getattr(bpy.ops.allset, op_name)('EXEC_DEFAULT', hierarchy=v["options"] == "Hierarchy")
    return run


def _run_add_influence(context, v):
    return bpy.ops.allset.add_influence('EXEC_DEFAULT', lock_weights=v["lock_weights"],
                                        default_weight=v["default_weight"])


# --- windows -------------------------------------------------------------------------------------------

_INCLUDE = ("All keyable", "From Channel Box", "All keyable except:")
_KEEP_ORIGINAL = "Keep original (Maya keeps the input curve and makes new ones)"

WINDOWS = [
    # Create Character Set Options (factory values, window)
    Window("character_set", "Create Character Set Options", "Create Character Set", None, [
        FText("name", "Name:", "character1"),
        F("hierarchy", "Include:", "bool", False, text="Hierarchy below selected node"),
        F("attributes", "Include:", "enum", "All keyable except:", items=_INCLUDE),
        F("no_translate", "", "bool", False, text="Translate"),
        F("no_rotate", "", "bool", False, text="Rotate"),
        F("no_scale", "", "bool", True, text="Scale"),
        F("no_visibility", "", "bool", True, text="Visibility"),
        F("no_dynamic", "", "bool", False, text="Dynamic"),
    ], _character(False), paths=("Control/Create Character Set", "Key/Create Character Set"),
        missing=("Redirection: Redirect character (Rotation and translation / Rotation only / Translation only)",)),
    # Create Subcharacter Set Options (no hierarchy, no redirection)
    Window("subcharacter_set", "Create Subcharacter Set Options", "Create Subcharacter Set", None, [
        FText("name", "Name:", "subCharacter1"),
        F("attributes", "Subcharacter set attributes:", "enum", "All keyable except:", items=_INCLUDE),
        F("no_translate", "", "bool", False, text="No translate"),
        F("no_rotate", "", "bool", False, text="No rotate"),
        F("no_scale", "", "bool", True, text="No scale"),
        F("no_visibility", "", "bool", True, text="No visibility"),
        F("no_dynamic", "", "bool", False, text="No dynamic"),
    ], _character(True), paths=("Control/Create Subcharacter Set", "Key/Create Subcharacter Set")),
    # Cut Curve Options (factory 1 / 2, Cut / Keep radios, title)
    Window("cut_curve", "Cut Curve Options", "Cut", None, [
        F("cut", "Cut:", "enum", "At all intersections", items=("At all intersections", "Using last curve")),
        F("keep", "Keep:", "enum", "All curve segments", items=("Longest segments", "All curve segments")),
    ], _run_cut, paths=("Curves/Cut",),
        missing=("Find intersections: In 2D and 3D / In 3D only / Use direction (the kit finds 3D crossings)",
                 "Keep: Segments with curve points", "Use tolerance: Global / Local, Tolerance 0.0001",
                 _KEEP_ORIGINAL)),
    # Detach Curves Options
    Window("detach_curves", "Detach Curves Options", "Detach", None, [], _run_detach, paths=("Curves/Detach",),
           missing=(_KEEP_ORIGINAL,)),
    # Reverse Curve Options
    Window("reverse_curve", "Reverse Curve Options", "Reverse", None, [
        F("keep_original", "", "bool", False, text="Keep original"),
    ], _run_reverse, paths=("Curves/Reverse Direction",)),
    # Smooth Curves Options (factor 4)
    Window("smooth_curves", "Smooth Curves Options", "Smooth Curves", None, [
        F("factor", "Smooth factor:", "int", 4, lo=1, hi=100),
    ], _run_smooth_curves, paths=("Curves/Smooth", "nHair/Modify Curves/Smooth")),
    # Smooth Curve Options (Edit section Smooth = smoothCurve)
    Window("smooth_curve", "Smooth Curve Options", "Smooth", None, [
        F("keep_original", "", "bool", False, text="Keep original"),
    ], _run_smooth_curve, paths=("Curves/Smooth#2",),
        missing=("Smoothness: 10.0 (Maya's smoothCurve; the kit runs Blender's curve Smooth)",)),
    # Straighten Curves Options
    Window("straighten_curves", "Straighten Curves Options", "Straighten Curves", None, [
        F("straightness", "Straightness:", "float", 1.0, lo=0.0, hi=2.0),
        F("preserve_length", "", "bool", True, text="Preserve length"),
    ], _run_straighten, paths=("Curves/Straighten", "nHair/Modify Curves/Straighten")),
    # Tool Settings "Three / Two Point Arc Settings" (window = tool name,
    # its button starts the tool, like the other tool boxes)
    Window("arc3_tool", "Three Point Arc Settings", "Create Arc", None, [
        F("degree", "Circular arc degree:", "enum", "3", items=("1 Linear", "3")),
        F("sections", "Sections:", "int", 8, lo=4, hi=200),
    ], _arc("arc3_tool"), paths=("Create/Curve Tools/Three Point Circular Arc",)),
    Window("arc2_tool", "Two Point Arc Settings", "Create Arc", None, [
        F("degree", "Circular arc degree:", "enum", "3", items=("1 Linear", "3")),
        F("sections", "Sections:", "int", 8, lo=4, hi=200),
    ], _arc("arc2_tool"), paths=("Create/Curve Tools/Two Point Circular Arc",)),
    # Merge UVs Options (factory 0.01)
    Window("merge_uvs", "Merge UVs Options", "Merge UVs", None, [
        F("threshold", "Threshold:", "float", 0.01, lo=0.0, hi=1.0),
    ], _run_merge_uvs, paths=("UV/Merge UVs",)),
    # Contour Stretch Mapping Options
    Window("contour_stretch", "Contour Stretch Mapping Options", "Project", None, [], _run_contour,
           paths=("UV/Contour Stretch",),
           missing=("Method: Walk Contours / NURBS Projection (the kit follows the quad grid)",
                    "Smoothness 0-3, Offset 0-3", "User defined corner vertices",
                    "Insert projection before deformers", "Create new UV Set")),
    # Set Preferred Angle Options (factory Hierarchy)
    Window("set_preferred_angle", "Set Preferred Angle Options", "Set", None, [
        F("options", "Options:", "enum", "Hierarchy", items=("Selected joint", "Hierarchy")),
    ], _preferred("set_preferred_angle"), paths=("Skeleton/Set Preferred Angle",)),
    Window("assume_preferred_angle", "Assume Preferred Angle Options", "Assume", None, [
        F("options", "Options:", "enum", "Hierarchy", items=("Selected joint", "Hierarchy")),
    ], _preferred("assume_preferred_angle"), paths=("Skeleton/Assume Preferred Angle",)),
    # Add Influence Options
    Window("add_influence", "Add Influence Options", "Add", None, [
        F("lock_weights", "Weight locking:", "bool", False, text="Lock weights"),
        F("default_weight", "Default weight:", "float", 0.0, lo=0.0, hi=1.0),
    ], _run_add_influence, paths=("Skin/Edit Influences/Add Influence",),
        missing=("Geometry: Use geometry", "Dropoff: 4.0 (Maya weighs an unlocked influence by distance; the kit adds "
                 "it at 0)", "Polygon smoothness: 0.0", "NURBS samples: 10")),
]
