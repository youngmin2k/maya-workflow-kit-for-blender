# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya 2022 Mesh Display colour commands: Apply Color, Rename / Modify Current Set, Set Keyframe for
Vertex Color, Prelight (Maya), vertex bake sets (Assign New / Existing, Edit Assigned Set), Select Shared Instances.

A Maya colour set = a Blender colour attribute, the current set = the active colour attribute; Maya colours live per
vertex-face, so new sets are CORNER float colours (unclamped, like Maya). Maya corners can have no colour; Blender's
can't [a corner Maya leaves uncoloured is white (1, 1, 1, 1), neutral under the material].
"""

import colorsys
import math

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, StringProperty

from .. import results, undo_steps

NEW_SET = "colorSet1"          # Apply Color on a mesh without a set
UNSET = (1.0, 1.0, 1.0, 1.0)
APPLY_COLOR = (0.5, 0.5, 0.5)  # Apply Color Options default value
APPLY_ALPHA = 1.0
OPERATIONS = (('REPLACE', "Replace", "Replace the colour (default)"), ('ADD', "Add", "Add the colour"),
              ('SUBTRACT', "Subtract", "Subtract the colour"), ('REMOVE', "Remove", "Remove the colour"))
BAKE_SETS = "allset_bake_sets"   # Scene ID property: {vertexBakeSetN: {Maya attribute: value}}
BAKE_SET = "allset_bake_set"     # Object ID property: the assigned bake set's name
BLENDS = ("Overwrite", "Add", "Subtract", "Multiply", "Divide", "Average")   # vertexBakeSet colorBlending 0-5
# vertexBakeSet default attributes the kit uses
BAKE_DEFAULTS = {"bakeColor": True, "bakeAlpha": False, "colorBlending": 0, "alphaBlending": 0, "scaleRgba": 1.0,
                 "clampMin": False, "minColor": (0.0, 0.0, 0.0, 0.0), "clampMax": False, "maxColor": (0.0, 0.0, 0.0, 1.0)}
PRELIGHT_SAMPLES = 16          # Cycles bake samples [Maya's polyGeoSampler samples the shading network once]


# --- pure rules (tests/test_step189_colors.py) ---------------------------------------------------------------

def apply(rgba, color, alpha, operation, channels=(True, True, True, True)):
    """Maya Apply Color on one corner (polyColorPerVertex -r -g -b -a [-rel] / -rem): None = Maya's uncoloured."""
    if operation == 'REMOVE':
        return None
    base = list(rgba) if rgba is not None else list(UNSET)
    value = (*color, alpha)
    sign = {'REPLACE': 0, 'ADD': 1, 'SUBTRACT': -1}[operation]
    for i in range(4):
        if channels[i]:
            base[i] = value[i] if sign == 0 else base[i] + sign * value[i]
    return tuple(base)


def ramp_value(ramp, x):
    """A Maya ramp attribute (redScale ... intensityScale): [(position, value, interp)] — 0 none (step), 1 linear,
    2 smooth ((1 - cos)/2), 3 spline (Catmull-Rom, end points doubled). Outside the points: the end values."""
    pts = sorted(ramp)
    if not pts:
        return x
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for i in range(len(pts) - 1):
        (x0, y0, kind), (x1, y1, _k) = pts[i], pts[i + 1]
        if x0 <= x <= x1:
            u = (x - x0) / (x1 - x0) if x1 > x0 else 0.0
            if kind == 0:
                return y0 if u < 1.0 else y1
            if kind == 1:
                return y0 + (y1 - y0) * u
            if kind == 2:
                return y0 + (y1 - y0) * (1.0 - math.cos(math.pi * u)) / 2.0
            ym = pts[i - 1][1] if i > 0 else y0
            yp = pts[i + 2][1] if i + 2 < len(pts) else y1
            m0, m1 = (y1 - ym) / 2.0, (yp - y0) / 2.0
            u2, u3 = u * u, u * u * u
            return ((2 * u3 - 3 * u2 + 1) * y0 + (u3 - 2 * u2 + u) * m0 + (-2 * u3 + 3 * u2) * y1
                    + (u3 - u2) * m1)
    return pts[-1][1]


IDENTITY = [(0.0, 0.0, 1), (1.0, 1.0, 1)]   # polyColorMod default ramps (linear 0 -> 0, 1 -> 1)


def color_mod(rgba, hue=0.0, saturation=1.0, value=1.0, red=IDENTITY, green=IDENTITY, blue=IDENTITY,
              alpha=IDENTITY, intensity=IDENTITY):
    """Maya polyColorMod on one colour: clamp to [0, 1]; HSV: hue + degrees, saturation and value
    multiplied (saturation not clamped before HSV -> RGB), clamp; channel ramps map r / g / b / a; the colour is
    multiplied by intensityScale(max(r, g, b)) — so the default node darkens every colour by its own value."""
    r, g, b, a = (min(1.0, max(0.0, c)) for c in rgba)
    if hue or saturation != 1.0 or value != 1.0:
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        r, g, b = _hsv_to_rgb((h + hue / 360.0) % 1.0, s * saturation, v * value)
        r, g, b = (min(1.0, max(0.0, c)) for c in (r, g, b))
    r, g, b, a = ramp_value(red, r), ramp_value(green, g), ramp_value(blue, b), ramp_value(alpha, a)
    k = ramp_value(intensity, max(r, g, b))
    return (r * k, g * k, b * k, a)


def _hsv_to_rgb(h, s, v):
    """HSV -> RGB without clamping s (Maya lets saturation > 1 push channels below 0)."""
    i = int(h * 6.0) % 6
    f = h * 6.0 - int(h * 6.0)
    p, q, t = v * (1.0 - s), v * (1.0 - s * f), v * (1.0 - s * (1.0 - f))
    return [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i]


def rename_error(names, new):
    """Maya Color Set Editor rename: an empty name or one already used fails ("Cannot rename color set to an existing
    color set name."); spaces, digits first and dashes are accepted."""
    if not new or new in names:
        return "Cannot rename color set to an existing color set name."
    return None


def next_bake_set(names):
    n = 1
    while f"vertexBakeSet{n}" in names:
        n += 1
    return f"vertexBakeSet{n}"


def blend(old, new, mode):
    """vertexBakeSet colorBlending / alphaBlending (polyGeoSampler colorBlend) of the baked value over the old one."""
    if mode == 1:
        return old + new
    if mode == 2:
        return old - new
    if mode == 3:
        return old * new
    if mode == 4:
        return old / new if abs(new) > 1e-12 else old
    if mode == 5:
        return (old + new) / 2.0
    return new


# --- Blender access --------------------------------------------------------------------------------------------

def _meshes(context):
    if context.mode == 'EDIT_MESH':
        return [o for o in context.objects_in_mode_unique_data if o.type == 'MESH']
    return [o for o in context.selected_objects if o.type == 'MESH']


def current_set(me, create=False):
    """The active colour attribute (Maya current colour set); a new white ``colorSet1`` when asked and there is none."""
    attr = me.color_attributes.active_color
    if attr is None and create:
        attr = me.color_attributes.new(NEW_SET, 'FLOAT_COLOR', 'CORNER')
        for d in attr.data:
            d.color = UNSET
        me.color_attributes.active_color = attr
        me.color_attributes.render_color_index = me.color_attributes.active_color_index
    return attr


class _Picked:
    """Selected corners per mesh (read in Edit Mode, written in Object Mode)."""

    def __init__(self, context):
        self.edit = context.mode == 'EDIT_MESH'
        self.items, self.kind = [], None
        mode = tuple(context.scene.tool_settings.mesh_select_mode)
        for ob in _meshes(context):
            if self.edit:
                bm = bmesh.from_edit_mesh(ob.data)
                if mode[2] and not mode[0]:
                    corners = [l.index for f in bm.faces if f.select for l in f.loops]
                elif mode[0]:
                    corners = [l.index for v in bm.verts if v.select for l in v.link_loops]
                else:
                    corners = None          # edges only: Maya "No vertex or vertex-face components were selected."
                    self.kind = 'EDGE'
            else:
                corners = list(range(len(ob.data.loops)))
            if corners:
                self.items.append((ob, sorted(set(corners))))
        if self.edit:
            bpy.ops.object.mode_set(mode='OBJECT')

    def close(self):
        if self.edit:
            bpy.ops.object.mode_set(mode='EDIT')


def _read(attr, me, corners):
    if attr.domain == 'POINT':
        return {c: tuple(attr.data[me.loops[c].vertex_index].color) for c in corners}
    return {c: tuple(attr.data[c].color) for c in corners}


def _write(attr, me, values):
    """Unclamped like Maya (subtract can go below 0): ``foreach_set`` skips the RNA soft range that ``.color`` = ...
    clamps at 0."""
    flat = [0.0] * (len(attr.data) * 4)
    attr.data.foreach_get("color", flat)
    for c, rgba in values.items():
        i = me.loops[c].vertex_index if attr.domain == 'POINT' else c
        flat[i * 4:i * 4 + 4] = rgba if rgba is not None else UNSET
    attr.data.foreach_set("color", flat)


@undo_steps.no_redo_panel
class ALLSET_OT_apply_color(bpy.types.Operator):
    """Colour the selected vertices / faces (or meshes) in the current colour set (Maya Mesh Display > Apply Color)"""
    bl_idname = "allset.apply_color"
    bl_label = "Apply Color"
    bl_options = {'REGISTER', 'UNDO'}

    operation: EnumProperty(name="Operation", items=OPERATIONS, default='REPLACE', options={'SKIP_SAVE'})
    color: FloatVectorProperty(name="Color", size=3, default=APPLY_COLOR, subtype='COLOR', soft_min=0.0, soft_max=1.0,
                               options={'SKIP_SAVE'})
    alpha: FloatProperty(name="Alpha", default=APPLY_ALPHA, soft_min=0.0, soft_max=1.0, options={'SKIP_SAVE'})

    def execute(self, context):
        picked = _Picked(context)
        try:
            for ob, corners in picked.items:
                me = ob.data
                attr = current_set(me, create=self.operation != 'REMOVE')
                if attr is None:
                    continue
                old = _read(attr, me, corners)
                _write(attr, me, {c: apply(old[c], tuple(self.color), self.alpha, self.operation) for c in corners})
                me.update()
        finally:
            picked.close()
        if not picked.items:
            self.report({'WARNING'}, "No vertex or vertex-face components were selected." if picked.kind == 'EDGE'
                        else "Select vertices, faces or meshes to colour.")
            return {'CANCELLED'}
        results.result(self, "polyColorPerVertex")
        return {'FINISHED'}


class ALLSET_OT_color_set_rename(bpy.types.Operator):
    """Rename the current colour set (Maya Mesh Display > Rename Current Set...)"""
    bl_idname = "allset.color_set_rename"
    bl_label = "Rename Current Set"
    bl_options = {'UNDO'}

    new_name: StringProperty(name="New name", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'MESH' and ob.data.color_attributes.active_color is not None

    def invoke(self, context, event):
        self.new_name = context.active_object.data.color_attributes.active_color.name
        return context.window_manager.invoke_props_dialog(self, title="Rename Color Set")

    def execute(self, context):
        me = context.active_object.data
        attr = me.color_attributes.active_color
        error = rename_error({a.name for a in me.attributes}, self.new_name)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        attr.name = self.new_name
        results.result(self, self.new_name)
        return {'FINISHED'}


def _ramp_prop(label, at, default):
    return FloatProperty(name=f"{label} at {at}", default=default, options={'SKIP_SAVE'},
                         description=f"Maya {label.lower()} ramp: the value at input {at} (linear in between)")


class ALLSET_OT_color_set_modify(bpy.types.Operator):
    """Change the colours of the current colour set: hue, saturation, value and channel curves (Maya Mesh Display >
    Modify Current Set, polyColorMod)"""
    bl_idname = "allset.color_set_modify"
    bl_label = "Modify Current Set"
    bl_options = {'UNDO'}

    hue: FloatProperty(name="Hue", default=0.0, soft_min=-180.0, soft_max=180.0, options={'SKIP_SAVE'})
    saturation: FloatProperty(name="Saturation", default=1.0, min=0.0, soft_max=2.0, options={'SKIP_SAVE'})
    value: FloatProperty(name="Value", default=1.0, min=0.0, soft_max=2.0, options={'SKIP_SAVE'})
    red_0: _ramp_prop("Red", 0, 0.0)
    red_1: _ramp_prop("Red", 1, 1.0)
    green_0: _ramp_prop("Green", 0, 0.0)
    green_1: _ramp_prop("Green", 1, 1.0)
    blue_0: _ramp_prop("Blue", 0, 0.0)
    blue_1: _ramp_prop("Blue", 1, 1.0)
    alpha_0: _ramp_prop("Alpha", 0, 0.0)
    alpha_1: _ramp_prop("Alpha", 1, 1.0)
    intensity_0: _ramp_prop("Intensity", 0, 0.0)
    intensity_1: _ramp_prop("Intensity", 1, 1.0)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, title="Modify Current Set")

    def _ramp(self, name):
        return [(0.0, getattr(self, name + "_0"), 1), (1.0, getattr(self, name + "_1"), 1)]

    def execute(self, context):
        obs = [o for o in _meshes(context) if o.data.color_attributes.active_color is not None]
        if not obs:
            self.report({'WARNING'}, "Select a mesh with a colour set.")
            return {'CANCELLED'}
        edit = context.mode == 'EDIT_MESH'
        if edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        try:
            ramps = {k: self._ramp(k) for k in ("red", "green", "blue", "alpha", "intensity")}
            for ob in obs:
                attr = ob.data.color_attributes.active_color
                _write(attr, ob.data, {i: color_mod(tuple(d.color), self.hue, self.saturation, self.value, **ramps)
                                       for i, d in enumerate(attr.data)} if attr.domain == 'CORNER' else {})
                if attr.domain == 'POINT':
                    for d in attr.data:
                        d.color = color_mod(tuple(d.color), self.hue, self.saturation, self.value, **ramps)
                ob.data.update()
        finally:
            if edit:
                bpy.ops.object.mode_set(mode='EDIT')
        results.result(self, "polyColorMod")
        return {'FINISHED'}


@undo_steps.no_redo_panel
class ALLSET_OT_color_keyframe(bpy.types.Operator):
    """Set keys on the colours of the selected vertices / faces (or meshes) in the current colour set (Maya Mesh
    Display > Set Keyframe for Vertex Color)"""
    bl_idname = "allset.color_keyframe"
    bl_label = "Set Keyframe for Vertex Color"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        picked = _Picked(context)
        keys = 0
        try:
            frame = context.scene.frame_current
            for ob, corners in picked.items:
                me = ob.data
                attr = me.color_attributes.active_color
                if attr is None:
                    continue
                index = sorted({me.loops[c].vertex_index for c in corners}) if attr.domain == 'POINT' else corners
                for i in index:   # element-level keyframe_insert can't make a path to attribute data
                    me.keyframe_insert(f'attributes["{attr.name}"].data[{i}].color', frame=frame, group=attr.name)
                    keys += 1
        finally:
            picked.close()
        if not keys:
            self.report({'WARNING'}, "Select coloured vertices, faces or meshes to key.")
            return {'CANCELLED'}
        results.result(self, keys)
        return {'FINISHED'}


def bake_sets(scene):
    return scene.get(BAKE_SETS) or {}


def bake_settings(scene, ob):
    data = dict(BAKE_DEFAULTS)
    name = ob.get(BAKE_SET)
    if name and name in bake_sets(scene):
        data.update({k: (tuple(v) if hasattr(v, "__len__") and not isinstance(v, str) else v)
                     for k, v in bake_sets(scene)[name].items()})
    return data


def _assign(context, name):
    obs = [o for o in context.selected_objects if o.type == 'MESH']
    for ob in obs:
        ob[BAKE_SET] = name
    return obs


@undo_steps.no_redo_panel
class ALLSET_OT_bake_set_assign_new(bpy.types.Operator):
    """Make a new vertex bake set with the default prelight settings and assign the selected meshes to it (Maya
    Mesh Display > Assign New Set)"""
    bl_idname = "allset.bake_set_assign_new"
    bl_label = "Assign New Bake Set"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not any(o.type == 'MESH' for o in context.selected_objects):
            self.report({'WARNING'}, "Select meshes to assign to a bake set.")
            return {'CANCELLED'}
        sets = dict(bake_sets(context.scene))
        name = next_bake_set(sets)
        sets[name] = dict(BAKE_DEFAULTS)
        context.scene[BAKE_SETS] = sets
        _assign(context, name)
        results.result(self, f"Assigned the selected objects to {name}.")
        return {'FINISHED'}


def _set_items(self, context):
    return [(n, n, "") for n in sorted(bake_sets(context.scene))] or [("", "(no bake sets)", "")]


class ALLSET_OT_bake_set_assign(bpy.types.Operator):
    """Assign the selected meshes to an existing vertex bake set (Maya Mesh Display > Assign Existing Set)"""
    bl_idname = "allset.bake_set_assign"
    bl_label = "Assign Existing Bake Set"
    bl_options = {'UNDO'}

    name: EnumProperty(name="Bake set", items=_set_items)

    def invoke(self, context, event):
        if not bake_sets(context.scene):
            self.report({'WARNING'}, "There is no vertex bake set: use Assign New Set first.")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, title="Assign Existing Set")

    def execute(self, context):
        if self.name not in bake_sets(context.scene) or not _assign(context, self.name):
            self.report({'WARNING'}, "Select meshes and a vertex bake set.")
            return {'CANCELLED'}
        results.result(self, f"Assigned the selected objects to {self.name}.")
        return {'FINISHED'}


class ALLSET_OT_bake_set_edit(bpy.types.Operator):
    """Edit the vertex bake set of the selected mesh: what Prelight bakes and how it mixes (Maya Mesh Display > Edit
    Assigned Set)"""
    bl_idname = "allset.bake_set_edit"
    bl_label = "Edit Assigned Set"
    bl_options = {'UNDO'}

    bake_color: BoolProperty(name="Bake color", options={'SKIP_SAVE'})
    bake_alpha: BoolProperty(name="Bake alpha", options={'SKIP_SAVE'})
    color_blending: EnumProperty(name="Color blending", items=[(b.upper(), b, "") for b in BLENDS],
                                 options={'SKIP_SAVE'})
    alpha_blending: EnumProperty(name="Alpha blending", items=[(b.upper(), b, "") for b in BLENDS],
                                 options={'SKIP_SAVE'})
    scale_rgba: FloatProperty(name="Scale RGBA", default=1.0, options={'SKIP_SAVE'})

    @staticmethod
    def _set(context):
        ob = context.active_object
        name = ob.get(BAKE_SET) if ob is not None else None
        return name if name in bake_sets(context.scene) else None

    def invoke(self, context, event):
        name = self._set(context)
        if name is None:
            self.report({'WARNING'}, "The selected mesh has no vertex bake set: use Assign New Set first.")
            return {'CANCELLED'}
        s = bake_settings(context.scene, context.active_object)
        self.bake_color, self.bake_alpha = bool(s["bakeColor"]), bool(s["bakeAlpha"])
        self.color_blending = BLENDS[int(s["colorBlending"])].upper()
        self.alpha_blending = BLENDS[int(s["alphaBlending"])].upper()
        self.scale_rgba = float(s["scaleRgba"])
        return context.window_manager.invoke_props_dialog(self, title=name)

    def execute(self, context):
        name = self._set(context)
        if name is None:
            self.report({'WARNING'}, "The selected mesh has no vertex bake set.")
            return {'CANCELLED'}
        sets = {k: dict(v) for k, v in bake_sets(context.scene).items()}
        names = [b.upper() for b in BLENDS]
        sets[name].update(bakeColor=self.bake_color, bakeAlpha=self.bake_alpha,
                          colorBlending=names.index(self.color_blending),
                          alphaBlending=names.index(self.alpha_blending), scaleRgba=self.scale_rgba)
        context.scene[BAKE_SETS] = sets
        results.result(self, name)
        return {'FINISHED'}


@undo_steps.no_redo_panel
class ALLSET_OT_prelight(bpy.types.Operator):
    """Bake the scene lighting of the selected meshes into their current colour set (Maya Mesh Display > Prelight;
    Blender: a Cycles diffuse bake)"""
    bl_idname = "allset.prelight"
    bl_label = "Prelight"
    bl_options = {'REGISTER', 'UNDO'}

    # the option window's values (Maya Prelight Options = the vertex bake set attributes); off = the mesh's bake set
    use_options: BoolProperty(default=False, options={'SKIP_SAVE'})
    bake_color: BoolProperty(name="Bake shading group lighting", default=True, options={'SKIP_SAVE'})
    bake_alpha: BoolProperty(name="Bake alpha", default=False, options={'SKIP_SAVE'})
    color_blending: IntProperty(name="Color blending", default=0, min=0, max=5, options={'SKIP_SAVE'})
    alpha_blending: IntProperty(name="Alpha blending", default=0, min=0, max=5, options={'SKIP_SAVE'})
    scale_rgba: FloatProperty(name="Scale RGBA", default=1.0, options={'SKIP_SAVE'})

    def execute(self, context):
        obs = [o for o in context.selected_objects if o.type == 'MESH']
        if not obs:
            self.report({'WARNING'}, "Select meshes to prelight.")
            return {'CANCELLED'}
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        scene = context.scene
        render = scene.render
        saved = (render.engine, scene.cycles.samples, scene.render.bake.target)
        olds = {}
        try:
            render.engine = 'CYCLES'
            scene.cycles.samples = PRELIGHT_SAMPLES
            scene.render.bake.target = 'VERTEX_COLORS'
            for ob in obs:
                attr = current_set(ob.data, create=True)
                olds[ob.name] = [tuple(d.color) for d in attr.data]
            bpy.ops.object.bake(type='DIFFUSE', pass_filter={'DIRECT', 'INDIRECT', 'COLOR'},
                                target='VERTEX_COLORS')
        except RuntimeError as err:
            self.report({'ERROR'}, f"Prelight failed: {err}")
            return {'CANCELLED'}
        finally:
            render.engine, scene.cycles.samples, scene.render.bake.target = saved
        for ob in obs:
            s = bake_settings(scene, ob)
            if self.use_options:
                s.update(bakeColor=self.bake_color, bakeAlpha=self.bake_alpha, colorBlending=self.color_blending,
                         alphaBlending=self.alpha_blending, scaleRgba=self.scale_rgba)
            attr = current_set(ob.data)
            for d, old in zip(attr.data, olds[ob.name]):
                baked = tuple(d.color)
                rgb = [blend(old[i], baked[i] * s["scaleRgba"], int(s["colorBlending"])) if s["bakeColor"]
                       else old[i] for i in range(3)]
                a = blend(old[3], baked[3] * s["scaleRgba"], int(s["alphaBlending"])) if s["bakeAlpha"] else old[3]
                d.color = (*rgb, a)
            ob.data.update()
        results.result(self, "polyGeoSampler")
        return {'FINISHED'}


@undo_steps.no_redo_panel
class ALLSET_OT_select_shared_instances(bpy.types.Operator):
    """Select the other instances of the selected mesh (objects sharing its mesh data) (Maya Mesh Display > Per
    Instance Sharing > Select Shared Instances)"""
    bl_idname = "allset.select_shared_instances"
    bl_label = "Select Shared Instances"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        picked = [o for o in context.selected_objects if o.type == 'MESH']
        if not picked:
            self.report({'WARNING'}, "One instance must be selected.")
            return {'CANCELLED'}
        datas = {o.data for o in picked}
        others = [o for o in context.scene.objects if o.type == 'MESH' and o.data in datas and o not in picked]
        if not others:
            self.report({'WARNING'}, "The selected mesh has no other instances.")
            return {'CANCELLED'}
        for o in picked:
            o.select_set(False)
        for o in others:
            try:
                o.select_set(True)
            except RuntimeError:      # not in the view layer
                pass
        context.view_layer.objects.active = others[0]
        results.result(self, len(others))
        return {'FINISHED'}


classes = (ALLSET_OT_apply_color, ALLSET_OT_color_set_rename, ALLSET_OT_color_set_modify, ALLSET_OT_color_keyframe,
           ALLSET_OT_bake_set_assign_new, ALLSET_OT_bake_set_assign, ALLSET_OT_bake_set_edit, ALLSET_OT_prelight,
           ALLSET_OT_select_shared_instances)
