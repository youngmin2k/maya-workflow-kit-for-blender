# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya option windows (the □ option box of a menu item).

Maya opens a window per command with its fields (labels right-aligned, field + slider), an Edit menu (Save Settings /
Reset Settings) and three buttons: the command ("Create", "Extrude", ...), Apply (run, keep the window) and Close; the
values are kept between sessions. Fields, labels and defaults below follow Maya's windows.

Each ``Window`` becomes one operator ``allset.opt_<key>`` drawn with ``invoke_props_dialog`` (confirm = the
command's button, Blender's cancel = Close); Apply / Save Settings / Reset Settings are toggle buttons inside the
dialog whose update callbacks act at once and spring back. ``Window.run`` maps the Maya values onto the kit or
Blender operator. ``find(action)`` ties a window to a menu / marking menu / shelf action, so every option box of
that action opens it, and a plain click uses the saved values once the user has applied or saved them (Maya runs a
menu item with its option values).
"""

import json

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty
from mathutils import Matrix, Vector

from . import units

# --- spec -------------------------------------------------------------------------------------------


class F:
    """One Maya field: ``kind`` float / length (× maya_unit) / int / bool / enum / vec3 / vec3len / angle3."""

    def __init__(self, name, label, kind, default, items=None, lo=None, hi=None, text=None, heading=None):
        self.name, self.label, self.kind, self.default = name, label, kind, default
        self.items, self.lo, self.hi, self.text, self.heading = items, lo, hi, text, heading

    def prop(self):
        kw = {"name": self.label.rstrip(":"), "default": self.default}
        if self.kind in ("float", "length"):
            kw.update(soft_min=self.lo if self.lo is not None else -1e6, soft_max=self.hi if self.hi is not None else 1e6,
                      precision=4, step=10)
            return FloatProperty(**kw)
        if self.kind == "int":
            return IntProperty(min=self.lo if self.lo is not None else 0, soft_max=self.hi or 100, **kw)
        if self.kind == "bool":
            return BoolProperty(**kw)
        if self.kind == "enum":
            return EnumProperty(items=[(i, i, "") for i in self.items], **kw)
        return FloatVectorProperty(size=3, precision=4, **kw)


class Window:
    def __init__(self, key, title, action, match, fields, run, paths=(), missing=(), width=440, apply_text="Apply",
                 click_saved=True):
        self.key, self.title, self.action = key, title, action
        # a plain menu click runs the window's command with the saved values (Maya); False = the click keeps running
        # the menu's own action (Display > Grid toggles the grid, its window only sets how it looks)
        self.click_saved = click_saved
        self.apply_text = apply_text  # Maya's middle button (Offset Edge Loop: "Enter Tool")
        self.match = match            # (operator id, props subset) of the menu action this window belongs to
        self.fields, self.run, self.paths = fields, run, tuple(paths)
        self.missing = tuple(missing)   # Maya fields Blender has no equivalent for (drawn greyed, one line)
        self.width = width

    @property
    def idname(self):
        return f"allset.opt_{self.key}"

    def defaults(self):
        return {f.name: f.default for f in self.fields}


# --- shared run helpers -----------------------------------------------------------------------------

def _k(context):
    return units.maya_unit(context.scene)


_AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}
# option window field -> Maya creation node attribute (the window fills the node, operators/prim_history.py)
_NODE_FIELDS = {
    'CUBE': {"width": "width", "height": "height", "depth": "depth", "width_div": "subdivisionsWidth",
             "height_div": "subdivisionsHeight", "depth_div": "subdivisionsDepth"},
    'SPHERE': {"radius": "radius", "axis_div": "subdivisionsAxis", "height_div": "subdivisionsHeight"},
    'CYLINDER': {"radius": "radius", "height": "height", "axis_div": "subdivisionsAxis",
                 "height_div": "subdivisionsHeight", "cap_div": "subdivisionsCaps", "round_cap": "roundCap"},
    'CONE': {"radius": "radius", "height": "height", "axis_div": "subdivisionsAxis", "height_div": "subdivisionsHeight",
             "cap_div": "subdivisionsCap", "round_cap": "roundCap"},
    'TORUS': {"radius": "radius", "section_radius": "sectionRadius", "twist": "twist", "axis_div": "subdivisionsAxis",
              "height_div": "subdivisionsHeight"},
    'PLANE': {"width": "width", "height": "height", "width_div": "subdivisionsWidth",
              "height_div": "subdivisionsHeight"},
}


def _primitive(kind):
    def run(context, v):
        from .option_windows_prims import _create
        over = {node: v[field] for field, node in _NODE_FIELDS[kind].items() if field in v}
        ax = _AXES.get(v.get("axis", "Y"), _AXES["Y"])
        over.update(axisX=ax[0], axisY=ax[1], axisZ=ax[2], createUVs=int(bool(v.get("create_uvs", True))))
        return _create(context, kind, over)     # at the origin, or drawn with Interactive Creation
    return run


def _op(op_id, **kw):
    mod, name = op_id.split(".")
    return getattr(getattr(bpy.ops, mod), name)('EXEC_DEFAULT', **kw)


def _components(context, op_id, select_mode, **kw):
    """Run an edit-mode mesh command; from object mode on every component of the selected meshes (Maya)."""
    if context.mode == 'EDIT_MESH':
        return _op(op_id, **kw)
    meshes = [o for o in context.selected_objects if o.type == 'MESH']
    if not meshes:
        raise RuntimeError("Select a mesh first.")
    if context.view_layer.objects.active not in meshes:
        context.view_layer.objects.active = meshes[0]
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        bpy.ops.mesh.select_mode(type=select_mode)
        bpy.ops.mesh.select_all(action='SELECT')
        return _op(op_id, **kw)
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')


def _with_hierarchy(context, below, fn):
    """Maya Hierarchy: Selected / Below (the selection plus everything under it while ``fn`` runs)."""
    if not below:
        return fn()
    from .freeze import hierarchy
    extra = [o for o in hierarchy(context.selected_objects) if not o.select_get()]
    for o in extra:
        o.select_set(True)
    try:
        return fn()
    finally:
        for o in extra:
            o.select_set(False)


def _last_constraint(context):
    pb = context.active_pose_bone if context.mode == 'POSE' else None
    owner = pb if pb is not None else context.active_object
    return owner.constraints[-1] if owner is not None and owner.constraints else None


def _group_axes(cons, ctype, v):
    """Constraint axes on every Blender constraint of a kit multi-target group: the parent group's Copy
    Location members take Translate, its Copy Rotation members Rotate (Maya Z = Blender -Y, Maya Y = Blender Z)."""
    for con in cons:
        if ctype == 'CHILD_OF':
            pre = "all_t" if con.type == 'COPY_LOCATION' else "all_r"
            keys = ("tx", "tz", "ty") if con.type == 'COPY_LOCATION' else ("rx", "rz", "ry")
            con.use_x, con.use_y, con.use_z = (v[pre] or v[k] for k in keys)
        else:
            con.use_x = v["all"] or v["x"]
            con.use_y = v["all"] or v["z"]
            con.use_z = v["all"] or v["y"]


def _constraint(ctype):
    def run(context, v):
        from . import constrain_multi
        res = bpy.ops.allset.constrain('EXEC_DEFAULT', type=ctype, weight=v["weight"],
                                       maintain_offset='ON' if v["maintain_offset"] else 'OFF')
        con = _last_constraint(context)
        if res != {'FINISHED'} or con is None:
            return res
        mb = constrain_multi.member(con)
        if mb is not None:
            # a multi-target node: Maintain offset and Weight were applied when it was built (weights = W0, W1 ...)
            _group_axes(constrain_multi.members(mb.owner, mb.group), ctype, v)
            return res
        con.influence = v["weight"]
        if ctype == 'CHILD_OF':
            if not v["maintain_offset"]:
                con.inverse_matrix = Matrix.Identity(4)      # snap like Maya without Maintain offset
            con.use_location_x = v["all_t"] or v["tx"]
            con.use_location_y = v["all_t"] or v["tz"]   # Maya Z = Blender -Y, Maya Y = Blender Z
            con.use_location_z = v["all_t"] or v["ty"]
            con.use_rotation_x = v["all_r"] or v["rx"]
            con.use_rotation_y = v["all_r"] or v["rz"]
            con.use_rotation_z = v["all_r"] or v["ry"]
        else:
            con.use_x = v["all"] or v["x"]
            con.use_y = v["all"] or v["z"]
            con.use_z = v["all"] or v["y"]
            if v["maintain_offset"]:
                if ctype == 'COPY_LOCATION':
                    con.use_offset = True
                else:
                    con.mix_mode = 'OFFSET'
        return res
    return run


def _run_group(context, v):
    res = bpy.ops.allset.group('EXEC_DEFAULT')
    grp = context.view_layer.objects.active
    if res == {'FINISHED'} and grp is not None:
        if v["group_under"] == "World" and grp.parent is not None:
            world = grp.matrix_world.copy()
            grp.parent = None
            grp.matrix_world = world
        if v["pivot"] == "Center":
            from .freeze import center_pivot
            center_pivot(context, [grp])
    return res


def _run_combine(context, v):
    objects = [o for o in context.selected_objects if o.type == 'MESH']
    last = context.view_layer.objects.active
    point = last.matrix_world.translation.copy() if last is not None else Vector()
    res = bpy.ops.allset.combine('EXEC_DEFAULT')
    ob = context.view_layer.objects.active
    if res == {'FINISHED'} and ob is not None and v["pivot"] != "Center" and objects:
        from .pivot import match_pivot
        match_pivot(ob, point if v["pivot"] == "Last object" else Vector())
    return res


def _run_smooth(context, v):
    """Maya Smooth with the window's values: real Catmull-Clark geometry (operators/poly_maya.py)."""
    if context.mode != 'EDIT_MESH' and not any(o.type == 'MESH' for o in context.selected_objects):
        raise RuntimeError("Select a mesh first.")
    return bpy.ops.allset.smooth('EXEC_DEFAULT', divisions=v["levels"])


def _run_bevel(context, v):
    # Maya polyBevel3 with the window's values (allset.bevel, editable afterwards like Ctrl+B)
    fraction = v["offset_type"].startswith("Fractional")
    kw = dict(segments=v["segments"], depth=max(-1.0, min(1.0, v["depth"])), offset_as_fraction=fraction)
    if fraction:
        kw["fraction"] = max(0.0, min(1.0, v["width"]))
    else:
        kw["offset"] = max(0.0, v["width"])
    if context.mode == 'EDIT_MESH' and tuple(context.scene.tool_settings.mesh_select_mode) == (True, False, False):
        bpy.ops.mesh.select_mode(type='EDGE')       # the window bevels edges (Maya: polyBevel3, not Chamfer)
    return _components(context, "allset.bevel", 'EDGE', **kw)


def _run_extrude(context, v):
    def go():
        return bpy.ops.allset.extrude('EXEC_DEFAULT', thickness=v["thickness"], offset=v["offset"],
                                        divisions=v["divisions"])
    if context.mode == 'EDIT_MESH':
        return go()
    meshes = [o for o in context.selected_objects if o.type == 'MESH']
    if not meshes:
        raise RuntimeError("Select faces (or a mesh) to extrude.")
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        bpy.ops.mesh.select_mode(type='FACE')
        bpy.ops.mesh.select_all(action='SELECT')
        return go()
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')


def _run_set_key(context, v):
    return _with_hierarchy(context, v["hierarchy"] == "Below", lambda: bpy.ops.allset.set_key('EXEC_DEFAULT'))


def _run_bake(context, v):
    # Maya's bakeResults rules (operators/bake_maya.py). Keep unbaked keys = keys outside the range,
    # never constraint deletion
    return bpy.ops.allset.bake_simulation(
        'EXEC_DEFAULT', hierarchy_below=v["hierarchy"] == "Below", use_time_slider=v["time_range"] == "Time Slider",
        start=int(round(v["start"])), end=int(round(v["end"])), sample_by=max(1, int(round(v["sample_by"]))),
        keep_unbaked=bool(v["keep_unbaked"]), disable_implicit=bool(v["disable_implicit"]))


def _run_uv_planar(context, v):
    from .menu_extras import planar_uvs
    axis = {"X axis": Vector((1, 0, 0)), "Y axis": Vector((0, 0, 1)), "Z axis": Vector((0, -1, 0))}
    if v["fit"] == "Best plane" or v["project_from"] == "Camera":
        return bpy.ops.allset.uv_planar('EXEC_DEFAULT')
    normal = axis[v["project_from"]]
    obs = [o for o in (context.objects_in_mode if context.mode == 'EDIT_MESH' else context.selected_objects)
           if o.type == 'MESH']
    if not obs:
        raise RuntimeError("Select faces (or a mesh) to project.")
    for ob in obs:
        edit = ob.mode == 'EDIT'
        bm = bmesh.from_edit_mesh(ob.data) if edit else bmesh.new()
        if not edit:
            bm.from_mesh(ob.data)
        faces = [f for f in bm.faces if f.select] if edit else list(bm.faces)
        layer = bm.loops.layers.uv.active or bm.loops.layers.uv.new("UVMap")
        loops = [lp for f in faces for lp in f.loops]
        for lp, uv in zip(loops, planar_uvs([lp.vert.co for lp in loops], normal)):
            lp[layer].uv = uv
        if edit:
            bmesh.update_edit_mesh(ob.data)
        else:
            bm.to_mesh(ob.data)
            bm.free()
    return {'FINISHED'}


def _run_uv_auto(context, v):
    # Maya polyAutoProjection in bmesh (operators/uv_tools.auto_project); handles object mode itself.
    return bpy.ops.allset.uv_automatic('EXEC_DEFAULT', planes=v["planes"], spacing=v["spacing"])


def _run_new_scene(context, v):
    values = dict(v)

    def later():
        from .. import first_start
        first_start.new_maya_scene()     # the Maya layout file bundled in the extension
        scene = bpy.context.scene
        us = scene.unit_settings
        if not values["keep_units"]:
            us.length_unit = {"millimeter": 'MILLIMETERS', "centimeter": 'CENTIMETERS', "meter": 'METERS',
                              "inch": 'INCHES', "foot": 'FEET', "yard": 'YARDS'}[values["linear"]]
            if values["linear"] in ("inch", "foot", "yard"):
                us.system = 'IMPERIAL'
            us.system_rotation = 'DEGREES' if values["angular"] == "degrees" else 'RADIANS'
            fps = float(values["fps"].split()[0])
            scene.render.fps, scene.render.fps_base = (round(fps), round(fps) / fps)
        scene.frame_start, scene.frame_end = int(values["anim_start"]), int(values["anim_end"])
        scene.use_preview_range = True
        scene.frame_preview_start, scene.frame_preview_end = int(values["play_start"]), int(values["play_end"])
        scene.frame_current = int(values["play_start"])
        return None
    # Maya's Save Changes prompt first (#57); never load a file inside a running operator
    #: save_prompt runs it from a timer
    from ..ui import save_prompt
    save_prompt.ask(context, later)
    return {'FINISHED'}


def _run_save(context, v):
    if v["incremental"] and bpy.data.filepath:
        return bpy.ops.allset.increment_save('EXEC_DEFAULT')
    if not bpy.data.filepath:
        return bpy.ops.allset.save_scene_as('INVOKE_DEFAULT')
    return bpy.ops.wm.save_mainfile('EXEC_DEFAULT', compress=v["compressed"])


# --- the windows (labels / defaults) ------------------------------

AXIS = F("axis", "Axis:", "enum", "Y", items=("X", "Y", "Z"))
UVS = F("create_uvs", "Texture mapping:", "bool", True, text="Create UVs")
_FREEZE_RESET = lambda kind: [F("translate", f"{kind}:", "bool", True, text="Translate"),   # noqa: E731
                              F("rotate", "", "bool", True, text="Rotate"), F("scale", "", "bool", True, text="Scale")]
_CON_AXES = [F("all", "Constraint axes:", "bool", True, text="All"), F("x", "", "bool", False, text="X"),
             F("y", "", "bool", False, text="Y"), F("z", "", "bool", False, text="Z"),
             F("weight", "Weight:", "float", 1.0, lo=0.0, hi=1.0)]

WINDOWS = [
    Window("poly_cube", "Polygon Cube Options", "Create", ("allset.create", {"kind": 'CUBE'}), [
        F("width", "Width:", "length", 1.0, lo=0.0001, hi=100), F("height", "Height:", "length", 1.0, lo=0.0001, hi=100),
        F("depth", "Depth:", "length", 1.0, lo=0.0001, hi=100),
        F("width_div", "Width divisions:", "int", 1, lo=1, hi=50), F("height_div", "Height divisions:", "int", 1, lo=1, hi=50),
        F("depth_div", "Depth divisions:", "int", 1, lo=1, hi=50), AXIS, UVS], _primitive('CUBE'),
        missing=("Normalize", "Collectively / Each face separately", "Preserve aspect ratio")),
    Window("poly_sphere", "Polygon Sphere Options", "Create", ("allset.create", {"kind": 'SPHERE'}), [
        F("radius", "Radius:", "length", 1.0, lo=0.0001, hi=100), F("axis_div", "Axis divisions:", "int", 20, lo=3, hi=200),
        F("height_div", "Height divisions:", "int", 20, lo=3, hi=200), AXIS, UVS], _primitive('SPHERE'),
        missing=("Pinched / Sawtooth at poles",)),
    Window("poly_cylinder", "Polygon Cylinder Options", "Create", ("allset.create", {"kind": 'CYLINDER'}), [
        F("radius", "Radius:", "length", 1.0, lo=0.0001, hi=100), F("height", "Height:", "length", 2.0, lo=0.0001, hi=100),
        F("axis_div", "Axis divisions:", "int", 20, lo=3, hi=200), F("height_div", "Height divisions:", "int", 1, lo=1, hi=100),
        F("cap_div", "Cap divisions:", "int", 1, lo=0, hi=100), F("round_cap", "", "bool", False, text="Round cap"),
        AXIS, UVS], _primitive('CYLINDER'), missing=("Normalize", "Preserve aspect ratio")),
    Window("poly_cone", "Polygon Cone Options", "Create", ("allset.create", {"kind": 'CONE'}), [
        F("radius", "Radius:", "length", 1.0, lo=0.0001, hi=100), F("height", "Height:", "length", 2.0, lo=0.0001, hi=100),
        F("axis_div", "Axis divisions:", "int", 20, lo=3, hi=200), F("height_div", "Height divisions:", "int", 1, lo=1, hi=100),
        F("cap_div", "Cap divisions:", "int", 0, lo=0, hi=100), F("round_cap", "", "bool", False, text="Round cap"),
        AXIS, UVS], _primitive('CONE'), missing=("Normalize", "Preserve aspect ratio")),
    Window("poly_torus", "Polygon Torus Options", "Create", ("allset.create", {"kind": 'TORUS'}), [
        F("radius", "Radius:", "length", 1.0, lo=0.0001, hi=100),
        F("section_radius", "Section Radius:", "length", 0.5, lo=0.0001, hi=100),
        F("twist", "Twist:", "float", 0.0, lo=-360, hi=360),
        F("axis_div", "Axis divisions:", "int", 20, lo=3, hi=200), F("height_div", "Height divisions:", "int", 20, lo=3, hi=200),
        AXIS, UVS], _primitive('TORUS')),
    Window("poly_plane", "Polygon Plane Options", "Create", ("allset.create", {"kind": 'PLANE'}), [
        F("width", "Width:", "length", 1.0, lo=0.0001, hi=100), F("height", "Height:", "length", 1.0, lo=0.0001, hi=100),
        F("width_div", "Width divisions:", "int", 10, lo=1, hi=200), F("height_div", "Height divisions:", "int", 10, lo=1, hi=200),
        AXIS, UVS], _primitive('PLANE'), missing=("Preserve aspect ratio",)),
    Window("group", "Group Options", "Group", ("allset.group", {}), [
        F("group_under", "Group under:", "enum", "Parent", items=("Parent", "World")),
        F("pivot", "Group pivot:", "enum", "Origin", items=("Center", "Origin"))], _run_group),
    Window("freeze", "Freeze Transformations Options", "Freeze Transform", ("allset.freeze_transform", {}),
           _FREEZE_RESET("Freeze"),
           lambda c, v: bpy.ops.allset.freeze_transform('EXEC_DEFAULT', translate=v["translate"],
                                                          rotate=v["rotate"], scale=v["scale"]),
           missing=("Joint orient", "Lock normals", "Preserve normals")),
    Window("reset", "Reset Transformations Options", "Reset Transform", ("allset.reset_transform", {}),
           _FREEZE_RESET("Reset"),
           lambda c, v: bpy.ops.allset.reset_transform('EXEC_DEFAULT', translate=v["translate"],
                                                         rotate=v["rotate"], scale=v["scale"])),
    Window("combine", "Combine Options", "Combine", ("allset.combine", {}), [
        F("pivot", "Pivot Position:", "enum", "Center", items=("Center", "Last object", "World origin"))],
        _run_combine, missing=("Merge UV Sets", "Combine Skinning")),
    Window("smooth", "Smooth Options", "Smooth", None, [
        F("levels", "Division levels:", "int", 1, lo=0, hi=6)], _run_smooth,
        # the kit always smooths with the default options, like Maya: sharp edges and corners, selection border kept
        paths=("Mesh/Smooth",), missing=("Exponentially / Linearly", "Maya Catmull-Clark", "Propagate Edge Hardness",
                                        "Vertex Boundary: Sharp edges", "Smooth UVs: off", "Map borders",
                                        "Preserve: Geometry / Selection borders")),
    Window("extrude", "Extrude Face Options", "Extrude", ("allset.extrude", {}), [
        F("divisions", "Divisions:", "int", 1, lo=1, hi=50), F("offset", "Offset:", "float", 0.0),
        F("thickness", "Thickness:", "float", 0.0)], _run_extrude,
        missing=("Smoothing angle", "Curve", "Taper", "Twist")),
    Window("bevel", "Bevel Options", "Bevel", None, [
        F("offset_type", "Offset type:", "enum", "Fractional (prevents inside out bevels)",
          items=("Fractional (prevents inside out bevels)", "Absolute")),
        F("width", "Width:", "float", 0.5, lo=0.0, hi=1.0), F("segments", "Segments:", "int", 1, lo=1, hi=50),
        F("depth", "Depth:", "float", 1.0, lo=-1.0, hi=1.0)], _run_bevel,
        paths=("Edit Mesh/Bevel",), missing=("Offset space", "Mitering / Miter Along", "Chamfer", "Smoothing Angle",
                                            "Automatically fit bevel to object")),
    Window("bridge", "Bridge Options", "Bridge", None, [
        F("divisions", "Divisions:", "int", 5, lo=0, hi=100), F("twist", "Twist:", "int", 0, lo=-100, hi=100)],
        lambda c, v: _components(c, "mesh.bridge_edge_loops", 'EDGE', number_cuts=v["divisions"],
                                 twist_offset=v["twist"]),
        paths=("Edit Mesh/Bridge",), missing=("Bridge type: Smooth path / curve", "Taper", "Smoothing angle")),
    Window("merge", "Merge Vertices Options", "Merge", None, [
        F("threshold", "Threshold:", "length", 0.01, lo=0.0, hi=1.0),
        F("always_two", "", "bool", True, text="Always merge for two vertices")],
        lambda c, v: _components(c, "allset.merge", 'VERT', threshold=v["threshold"], always_two=v["always_two"]),
        paths=("Edit Mesh/Merge",)),
    Window("parent_constraint", "Parent Constraint Options", "Add", ("allset.constrain", {"type": 'CHILD_OF'}), [
        F("maintain_offset", "Maintain offset:", "bool", True),
        F("all_t", "Translate:", "bool", True, text="All"), F("tx", "", "bool", False, text="X"),
        F("ty", "", "bool", False, text="Y"), F("tz", "", "bool", False, text="Z"),
        F("all_r", "Rotate:", "bool", True, text="All"), F("rx", "", "bool", False, text="X"),
        F("ry", "", "bool", False, text="Y"), F("rz", "", "bool", False, text="Z"),
        F("weight", "Weight:", "float", 1.0, lo=0.0, hi=1.0)], _constraint('CHILD_OF'),
        missing=("Decompose near object", "Animation Layer")),
    Window("point_constraint", "Point Constraint Options", "Add", ("allset.constrain", {"type": 'COPY_LOCATION'}),
           [F("maintain_offset", "Maintain offset:", "bool", False)] + _CON_AXES, _constraint('COPY_LOCATION'),
           missing=("Offset", "Animation Layer")),
    Window("orient_constraint", "Orient Constraint Options", "Add", ("allset.constrain", {"type": 'COPY_ROTATION'}),
           [F("maintain_offset", "Maintain offset:", "bool", False)] + _CON_AXES, _constraint('COPY_ROTATION'),
           missing=("Offset", "Animation Layer")),
    Window("set_key", "Set Key Options", "Set Key", ("allset.set_key", {}), [
        F("hierarchy", "Hierarchy:", "enum", "Selected", items=("Selected", "Below"))], _run_set_key,
        missing=("Set keys on: manipulator handles", "Set keys at: Prompt", "Set IK/FK keys", "Channels: From Channel Box",
                 "Control points", "Shapes")),
    Window("bake_simulation", "Bake Simulation Options", "Bake", ("allset.bake_simulation", {}), [
        F("hierarchy", "Hierarchy:", "enum", "Selected", items=("Selected", "Below")),
        F("time_range", "Time range:", "enum", "Time Slider", items=("Time Slider", "Start/End")),
        F("start", "Start time:", "float", 0.0), F("end", "End time:", "float", 10.0),
        F("sample_by", "Sample by:", "float", 1.0, lo=1.0, hi=100.0),
        F("keep_unbaked", "Keep unbaked keys:", "bool", True),
        F("disable_implicit", "Disable implicit control:", "bool", True)], _run_bake,
        missing=("Channels: From Channel Box", "Bake To: New Layer", "Smart Bake", "Sparse curve bake")),
    Window("uv_planar", "Planar Mapping Options", "Project", ("allset.uv_planar", {}), [
        F("fit", "Fit projection to:", "enum", "Bounding box", items=("Best plane", "Bounding box")),
        F("project_from", "Project from:", "enum", "X axis", items=("X axis", "Y axis", "Z axis", "Camera"))],
        _run_uv_planar, paths=("UV/Planar",), missing=("Keep image width/height ratio", "Insert projection before deformers",
                                                       "Create new UV Set")),
    Window("uv_automatic", "Polygon Automatic Mapping Options", "Project", ("allset.uv_automatic", {}), [
        F("planes", "Planes:", "enum", "6", items=("3", "4", "5", "6", "8", "12")),
        F("spacing", "Percentage space:", "float", 0.2, lo=0.0, hi=5.0)], _run_uv_auto, paths=("UV/Automatic",),
        missing=("Optimize for", "Shell layout / Scale mode / Shell stacking", "Create new UV set")),
    Window("new_scene", "New Scene Options", "New", None, [
        F("keep_units", "", "bool", False, text="Do not reset working units"),
        F("linear", "Linear:", "enum", "centimeter", items=("millimeter", "centimeter", "meter", "inch", "foot", "yard")),
        F("angular", "Angular:", "enum", "degrees", items=("degrees", "radians")),
        F("fps", "Time:", "enum", "24 fps", items=("12 fps", "15 fps", "23.976 fps", "24 fps", "25 fps",
                                                   "29.97 fps", "30 fps", "48 fps", "50 fps", "60 fps")),
        F("play_start", "Playback start:", "int", 1, lo=-100000), F("play_end", "Playback end:", "int", 120, lo=-100000),
        F("anim_start", "Animation start:", "int", 1, lo=-100000), F("anim_end", "Animation end:", "int", 200, lo=-100000)],
        _run_new_scene, paths=("File/New Scene",), missing=("Enable default scene", "Show the Compass", "Color Management enabled")),
    Window("save_scene", "Save Scene Options", "Save Scene", None, [
        F("incremental", "", "bool", False, text="Incremental save"),
        F("compressed", "", "bool", False, text="Compressed save")], _run_save, paths=("File/Save Scene",),
        missing=("Limit incremental saves", "Save Thumbnail/Playblast", "USD edits")),
]


def _extend():
    # more windows live in their own modules (they import F / Window from here); Bind Skin and Duplicate
    # Special moved there with every Maya field (option_windows_rig.bind_skin_maya / option_windows_edit)
    from . import (option_windows_curves, option_windows_deform, option_windows_display, option_windows_edit,
                   option_windows_modify, option_windows_render, option_windows_rig, option_windows_surfaces,
                   option_windows_visualize, option_windows_mesh_display)
    WINDOWS.extend(option_windows_rig.WINDOWS + option_windows_edit.WINDOWS + option_windows_deform.WINDOWS
                   + option_windows_display.WINDOWS + option_windows_render.WINDOWS + option_windows_curves.WINDOWS
                   + option_windows_modify.WINDOWS
                   + option_windows_visualize.WINDOWS
                   + option_windows_surfaces.WINDOWS
                   + option_windows_mesh_display.WINDOWS)
    from . import option_windows_misc196, option_windows_prims
    WINDOWS.extend(option_windows_prims.WINDOWS + option_windows_misc196.WINDOWS)
    from . import option_windows_197
    WINDOWS.extend(option_windows_197.WINDOWS)      # Mesh > Cleanup...
    from . import deformers_205a, deformers_205b, pins_205
    WINDOWS.extend(deformers_205a.windows() + deformers_205b.windows() + pins_205.windows())
    from . import option_windows_199
    WINDOWS.extend(option_windows_199.WINDOWS)      # Skin / Constrain tools 2
    from . import option_windows_curves207
    WINDOWS.extend(option_windows_curves207.WINDOWS)    # Bend / Curl / Scale Curvature
    from . import motion_path_228
    WINDOWS.extend(motion_path_228.windows())    # Attach to Motion Path
    from . import option_windows_uv
    WINDOWS.extend(option_windows_uv.WINDOWS)    # UV Editor Straighten UVs / Randomize Shells


_extend()
_BY_KEY = {w.key: w for w in WINDOWS}


def find(action):
    """The option window of a menu / marking-menu / shelf action (raw ``menu_map`` value or normalised), or None."""
    from ..ui import menu_map
    if isinstance(action, tuple) and len(action) == 3 and action[0] in ("op", "v3d") and isinstance(action[2], dict):
        s = action
    else:
        s = menu_map.normalize(action)
    if s is None or s[0] not in ("op", "v3d"):
        return None
    target, props = s[1], s[2]
    for w in WINDOWS:
        if w.match is None:
            continue
        op, want = w.match
        if op == target and all(props.get(k) == val for k, val in want.items()):
            return w
    return None


def find_path(path):
    """The option window of a Maya menu path (explicit ``paths`` first, then its menu twin's, then its action). A twin
    (``menu_map.TWINS``) runs the same Maya command, so its box opens the same window (nHair > Modify Curves
    Bend / Curl / Scale Curvature = the Curves windows, audit 16 quant)."""
    from ..ui import menu_map
    source = menu_map.TWINS.get(path)
    for w in WINDOWS:
        if path in w.paths:
            return w
    for w in WINDOWS:
        if source is not None and source in w.paths:
            return w
    return find(menu_map.MAP.get(path)) if path in menu_map.MAP else None


# --- saved settings (Maya's saved option values -> add-on preferences) ------------------------------

def _prefs():
    from .. import preferences
    try:
        return preferences.get()
    except KeyError:
        return None


def saved(key):
    prefs = _prefs()
    try:
        return json.loads(prefs.option_settings).get(key) if prefs is not None and prefs.option_settings else None
    except ValueError:
        return None


def store(key, values):
    prefs = _prefs()
    if prefs is None:
        return
    try:
        data = json.loads(prefs.option_settings) if prefs.option_settings else {}
    except ValueError:
        data = {}
    if values is None:
        data.pop(key, None)
    else:
        data[key] = values
    prefs.option_settings = json.dumps(data)


def values_of(window, holder):
    out = {}
    for f in window.fields:
        val = getattr(holder, f.name)
        out[f.name] = tuple(val) if f.kind.startswith("vec") else val
    return out


def run(window, context, values):
    """Run ``window``'s command with ``values`` (Maya values, defaults filled in)."""
    v = {**window.defaults(), **(values or {})}
    try:
        res = window.run(context, v)
    except RuntimeError as ex:
        return str(ex).strip().splitlines()[-1]
    return res


def run_saved(window, context):
    return run(window, context, saved(window.key))


# --- the operators --------------------------------------------------------------------------------

_PATHS = {}


def _menu_path(window):
    """The first main-menu path whose action opens ``window`` (windows bound by action, not by path)."""
    if window.key not in _PATHS:
        from ..ui import menu_map
        _PATHS[window.key] = next((p for p, a in menu_map.MAP.items()
                                   if not p.startswith(("Graph Editor/", "Dope Sheet/", "UV Editor/"))
                                   and find(a) is window), None)
    return _PATHS[window.key]


def _record(window, context, res):
    """A window command that ran is Maya's last command (G repeats it with the saved values)."""
    if not window.click_saved or isinstance(res, str) or not (isinstance(res, set) and 'FINISHED' in res):
        return
    from ..ui import menu_map
    path = window.paths[0] if window.paths else _menu_path(window)
    action = menu_map.MAP.get(path) if path else window.match
    if action is None:
        return
    from . import repeat_maya
    repeat_maya.record(path.rsplit("/", 1)[-1] if path else window.title, action, path, context)


def _apply_update(window):
    def update(self, context):
        if not self.apply_now:
            return
        apply_run = getattr(window, "apply_run", None)   # a window whose Apply isn't its command
        if apply_run is not None:
            res = apply_run(context, {**window.defaults(), **values_of(window, self)})
        else:
            res = run(window, context, values_of(window, self))
        store(window.key, values_of(window, self))
        if apply_run is None:
            _record(window, context, res)
        self.apply_now = False
        if isinstance(res, str):
            from ..ui import notices
            notices.show(f"{window.title}: {res}")
    return update


def _save_update(window):
    def update(self, context):
        if self.save_now:
            store(window.key, values_of(window, self))
            self.save_now = False
    return update


def _reset_update(window):
    def update(self, context):
        if self.reset_now:
            for f in window.fields:
                setattr(self, f.name, f.default)
            store(window.key, None)
            self.reset_now = False
    return update


def _make(window):
    ann = {f.name: f.prop() for f in window.fields}
    ann["apply_now"] = BoolProperty(name="Apply", options={'SKIP_SAVE'}, update=_apply_update(window),
                                    description="Run with these settings and keep the window open (Maya Apply)")
    ann["save_now"] = BoolProperty(name="Save Settings", options={'SKIP_SAVE'}, update=_save_update(window),
                                   description="Keep these settings for next time (Maya Edit > Save Settings)")
    ann["reset_now"] = BoolProperty(name="Reset Settings", options={'SKIP_SAVE'}, update=_reset_update(window),
                                    description="Back to the default settings (like Maya's Edit > Reset Settings)")

    def invoke(self, context, event):
        if window.key == "paint_skin_weights":
            return bpy.ops.allset.weight_workspace('INVOKE_DEFAULT')
        for name, val in (saved(window.key) or {}).items():
            if name in ann:
                try:
                    setattr(self, name, val)
                except (TypeError, ValueError):
                    pass
        return context.window_manager.invoke_props_dialog(self, width=window.width, title=window.title,
                                                          confirm_text=window.action)

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.prop(self, "save_now", toggle=True)
        row.prop(self, "reset_now", toggle=True)
        layout.separator()
        col = layout.column()
        col.use_property_split = True
        col.use_property_decorate = False
        fields = list(window.fields)
        i = 0
        while i < len(fields):
            f = fields[i]
            if f.kind == "bool" and f.text in ("X", "Y", "Z"):
                # Maya puts the X / Y / Z check boxes of a constraint on one line
                split = col.split(factor=0.4)       # Blender's property split: label column 40 %
                split.label(text="")
                row = split.row()
                row.use_property_split = False
                while i < len(fields) and fields[i].kind == "bool" and fields[i].text in ("X", "Y", "Z"):
                    row.prop(self, fields[i].name, text=fields[i].text)
                    i += 1
                continue
            i += 1
            if f.kind == "bool":
                col.column(heading=f.label.rstrip(":")).prop(self, f.name, text=f.text or "")
                continue
            elif f.kind == "enum":
                # an enum without a label is Maya's combo beside the row above (Joint Tool " + "): a drop-down, as
                # expanded buttons without a label Blender stacks it as empty bars
                col.row().prop(self, f.name, text=f.label.rstrip(":") or " ",
                               expand=bool(f.label) and len(f.items) <= 4)
            else:
                col.prop(self, f.name, text=f.label.rstrip(":"))
        if window.missing:
            sub = layout.column(align=True)
            sub.enabled = False
            sub.label(text="Not in Blender:")
            for name in window.missing:
                sub.label(text="    " + name)
        layout.separator()
        layout.prop(self, "apply_now", toggle=True, text=window.apply_text)

    def execute(self, context):
        values = values_of(window, self)
        store(window.key, values)        # Maya keeps the option values of a command that ran
        res = run(window, context, values)
        if isinstance(res, str):
            self.report({'WARNING'}, res)
            return {'CANCELLED'}
        _record(window, context, res)
        return {'FINISHED'} if res is None or 'FINISHED' in res else {'CANCELLED'}

    return type(f"ALLSET_OT_opt_{window.key}", (bpy.types.Operator,), {
        "__annotations__": ann, "bl_idname": window.idname, "bl_label": window.title,
        "bl_description": f"Maya {window.title}", "bl_options": {'UNDO'},    # no redo panel
        "invoke": invoke, "draw": draw, "execute": execute})


class ALLSET_OT_option_generic(bpy.types.Operator):
    """Option box of a Maya command whose settings Blender has no equivalent for: the window says so and runs
    the command (Maya: every option box opens a window)"""
    bl_idname = "allset.option_generic"
    bl_label = "Options"
    bl_options = {'INTERNAL'}

    item: bpy.props.StringProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        from .option_windows_render import no_options_text
        text = no_options_text(self.item, context.scene)
        if text:                    # Maya opens no window for these: its Help Line warning
            self.report({'WARNING'}, text)
            return {'CANCELLED'}
        label = self.item.rsplit("/", 1)[-1].rstrip(".").split("#")[0]
        return context.window_manager.invoke_props_dialog(self, width=400, title=f"{label} Options",
                                                          confirm_text=label)

    def draw(self, context):
        from ..ui import chrome, notices
        n = notices.notice(self.item)
        text = ("Maya's settings for this command have no Blender equivalent: it runs with Blender's own."
                + (f" {n[1]}" if n else ""))
        chrome.paragraph(self.layout, context, text, width=380)

    def execute(self, context):
        from ..ui import menu_map
        from ..marking.modal import run_action
        action = menu_map.MAP.get(self.item)
        if action is None:
            return {'CANCELLED'}
        try:
            run_action(context, action, path=self.item)
        except RuntimeError as ex:
            from . import maya_errors
            maya_errors.report_nested(self, ex)       # a Maya Error stays an Error
            return {'CANCELLED'}
        return {'FINISHED'}


classes = tuple(_make(w) for w in WINDOWS) + (ALLSET_OT_option_generic,)
