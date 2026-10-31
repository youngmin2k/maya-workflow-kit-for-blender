# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya 2026 Visualize > Motion Trail Editor on Blender motion paths (Issue #135).

Maya 2026 replaced "Create Editable Motion Trail" with the Motion Trail Editor
(labels and defaults like Maya's Motion Trail Editor): Create
Motion Trail on the selection (time range = Time Slider, increment 1), Delete Selected / Delete All, Settings (Draw
Style Always Draw / Draw When Selected, X-Ray Draw, Draw Mode Constant / Alternating Frames / Past/Future (default) /
Velocity, Anchor World / Object, Path before / before+after (default) / after, Increment 1, Pre / Post Frames 0), Edit
Settings (Local Position Pivot / Custom) and Display Settings (Show Key markers + numbers on, Show Frame markers +
numbers off, Trail Thickness 2, Key / Frame marker size 1, colours). Edit > Reset Settings / Save Settings as Default.

The kit keeps Maya's values (``Scene.allset_motion_trail``) and drives Blender's motion paths with them
(``to_blender``; ``from_blender`` reads them back): Path + Pre / Post Frames -> range type (0 = the whole Time
Slider), Increment -> frame step, Show Key / Numbers -> keyframe highlight / numbers, Frame numbers, Trail Thickness ->
line thickness, Draw Mode Constant / Past/Future -> custom path colour before / after the current frame. Settings
Blender has no counterpart for (Draw When Selected, X-Ray, Alternating Frames / Velocity, Anchor Object, Local
Position, marker sizes and colours, hiding frame markers) are greyed in the window with their reason. Moving a key on
the trail (Maya's editable trail) is not done yet.
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty

from .. import results

PATH_MODES = [('BEFORE', "Before", "Show trail preceding current frame"),
              ('BEFORE_AFTER', "Before and After", "Show trail preceding and following current frame"),
              ('AFTER', "After", "Show trail following current frame")]
DRAW_MODES = [('CONSTANT', "Constant", ""), ('ALTERNATE', "Alternating Frames", ""),
              ('PAST_FUTURE', "Past/Future", ""), ('VELOCITY', "Velocity", "")]

# Default values (like Maya)
FACTORY = {"draw_always": True, "xray": True, "draw_mode": 'PAST_FUTURE', "anchor_object": False,
           "path_mode": 'BEFORE_AFTER', "increment": 1.0, "pre_frames": 0.0, "post_frames": 0.0,
           "show_keys": True, "show_key_numbers": True, "show_frames": False, "show_frame_numbers": False,
           "thickness": 2, "key_size": 1, "frame_size": 1, "key_color": (1.0, 1.0, 1.0),
           "selected_key_color": (1.0, 1.0, 0.0), "frame_color": (0.155, 0.553, 0.111),
           "trail_color": (0.49, 0.098, 0.125), "alt_color": (0.125, 0.098, 0.49),
           "slow_color": (0.565, 0.2, 0.788), "fast_color": (0.686, 0.22, 0.071), "local_custom": False}
# rows Blender can't do (greyed in the window, the reason as the tooltip-like label)
NO_BLENDER = {"draw_always": "Blender draws motion paths whether the object is selected or not",
              "xray": "Blender draws motion paths in front already",
              "anchor_object": "Blender motion paths are in world space (or camera space)",
              "show_frames": "Blender always draws a dot per frame",
              "key_size": "Blender's marker size comes from the theme",
              "frame_size": "Blender's marker size comes from the theme",
              "local_custom": "Blender paths follow the object's origin (bones: head or tail)"}
SAVE_KEY = "motion_trail"


def _color(name, default):
    return FloatVectorProperty(name=name, subtype='COLOR', size=3, min=0.0, max=1.0, default=default,
                               update=_display_update)


def _display_update(self, context):
    apply_display(context)


class ALLSET_PG_motion_trail(bpy.types.PropertyGroup):
    draw_always: BoolProperty(name="Always Draw", default=True)
    xray: BoolProperty(name="X-Ray Draw", default=True)
    draw_mode: EnumProperty(name="Draw Mode", items=DRAW_MODES, default='PAST_FUTURE', update=_display_update)
    anchor_object: BoolProperty(name="Anchor Object", default=False)
    path_mode: EnumProperty(name="Path", items=PATH_MODES, default='BEFORE_AFTER')
    increment: FloatProperty(name="Increment", default=1.0, min=0.01)
    pre_frames: FloatProperty(name="Pre Frames", default=0.0, min=0.0)
    post_frames: FloatProperty(name="Post Frames", default=0.0, min=0.0)
    show_keys: BoolProperty(name="Show Key Markers", default=True, update=_display_update)
    show_key_numbers: BoolProperty(name="Show Key Numbers", default=True, update=_display_update)
    show_frames: BoolProperty(name="Show Frame Markers", default=False)
    show_frame_numbers: BoolProperty(name="Show Frame Numbers", default=False, update=_display_update)
    thickness: IntProperty(name="Trail Thickness", default=2, min=1, max=6, update=_display_update)
    key_size: IntProperty(name="Key Marker Size", default=1, min=1)
    frame_size: IntProperty(name="Frame Marker Size", default=1, min=1)
    key_color: _color("Key Color", (1.0, 1.0, 1.0))
    selected_key_color: _color("Selected Key Color", (1.0, 1.0, 0.0))
    frame_color: _color("Frame Color", (0.155, 0.553, 0.111))
    trail_color: _color("Trail Color", (0.49, 0.098, 0.125))
    alt_color: _color("Alternate Trail Color", (0.125, 0.098, 0.49))
    slow_color: _color("Velocity Slow Color", (0.565, 0.2, 0.788))
    fast_color: _color("Velocity Fast Color", (0.686, 0.22, 0.071))
    local_custom: BoolProperty(name="Local Position Custom", default=False)


def settings(context):
    return context.scene.allset_motion_trail


def values(s):
    return {k: (tuple(round(c, 6) for c in getattr(s, k)) if isinstance(FACTORY[k], tuple) else getattr(s, k))
            for k in FACTORY}


def set_values(s, vals):
    for k, v in vals.items():
        if k in FACTORY:
            setattr(s, k, v)


# --- Maya settings <-> Blender motion paths ----------------------------------------------------------------------

def time_slider(scene):
    if scene.use_preview_range:
        return scene.frame_preview_start, scene.frame_preview_end
    return scene.frame_start, scene.frame_end


def to_blender(vals, scene):
    """Blender AnimVizMotionPaths values for Maya's Path / Pre / Post / Increment / Show settings."""
    start, end = time_slider(scene)
    length = max(1, end - start)
    out = {"frame_step": max(1, int(round(vals["increment"]))), "show_keyframe_highlight": vals["show_keys"],
           "show_keyframe_numbers": vals["show_key_numbers"], "show_frame_numbers": vals["show_frame_numbers"]}
    before = vals["path_mode"] in ('BEFORE', 'BEFORE_AFTER')
    after = vals["path_mode"] in ('AFTER', 'BEFORE_AFTER')
    if vals["path_mode"] == 'BEFORE_AFTER' and not vals["pre_frames"] and not vals["post_frames"]:
        out.update(type='RANGE', range='MANUAL', frame_start=start, frame_end=end)     # Maya: the Time Slider
    else:
        def span(on, n):
            return (int(round(n)) if n > 0 else length) if on else 1
        # Blender keeps at least one frame on each side (frame_before / frame_after >= 1): "no trail after the
        # current frame" is 1 frame there, read back as Maya's Before (from_blender)
        out.update(type='CURRENT_FRAME', frame_before=max(1, span(before, vals["pre_frames"])),
                   frame_after=max(1, span(after, vals["post_frames"])))
    return out


def path_colors(vals):
    """(before, after) path colours of Maya's Draw Mode (Constant = one colour, Past/Future = two)."""
    if vals["draw_mode"] == 'CONSTANT':
        return vals["trail_color"], vals["trail_color"]
    return vals["trail_color"], vals["alt_color"]


def from_blender(viz, scene, colors=None):
    """Maya values read back from Blender's settings (the inverse of ``to_blender`` / ``path_colors``)."""
    start, end = time_slider(scene)
    length = max(1, end - start)
    out = {"increment": float(viz.frame_step), "show_keys": viz.show_keyframe_highlight,
           "show_key_numbers": viz.show_keyframe_numbers, "show_frame_numbers": viz.show_frame_numbers}
    if viz.type == 'RANGE':
        out.update(path_mode='BEFORE_AFTER', pre_frames=0.0, post_frames=0.0)
    else:
        b, a = viz.frame_before, viz.frame_after
        b = 0 if b <= 1 < a else b          # the 1-frame side is Blender's minimum = Maya's "no trail" side
        a = 0 if a <= 1 < b else a
        out["path_mode"] = 'BEFORE_AFTER' if b and a else 'BEFORE' if b else 'AFTER'
        out["pre_frames"] = 0.0 if b >= length or not b else float(b)
        out["post_frames"] = 0.0 if a >= length or not a else float(a)
    if colors is not None:
        before, after = (tuple(round(c, 6) for c in col) for col in colors)
        out["draw_mode"] = 'CONSTANT' if before == after else 'PAST_FUTURE'
        out["trail_color"] = before
        if before != after:
            out["alt_color"] = after
    return out


def _owners(context, selected_only=True):
    """(visualization settings, [(id, motion path owner)]) of the current mode: pose bones in pose mode, objects
    otherwise."""
    ob = context.active_object
    if ob is not None and ob.mode == 'POSE':
        bones = context.selected_pose_bones if selected_only else list(ob.pose.bones)
        return ob.pose.animation_visualization.motion_path, [(ob, pb) for pb in (bones or ())]
    obs = context.selected_objects if selected_only else list(context.scene.objects)
    return None, [(o, o) for o in obs]


def apply_settings(viz, vals, scene):
    for k, v in to_blender(vals, scene).items():
        setattr(viz, k, v)


def apply_display(context):
    """Display settings onto every existing motion path (thickness, colours, numbers)."""
    scene = context.scene
    if not hasattr(scene, "allset_motion_trail"):
        return
    vals = values(scene.allset_motion_trail)
    before, after = path_colors(vals)
    for ob in scene.objects:
        holders = [ob] + (list(ob.pose.bones) if ob.pose else [])
        for h in holders:
            mp = getattr(h, "motion_path", None)
            if mp is None:
                continue
            mp.use_custom_color = True
            mp.color, mp.color_post = before, after
            mp.line_thickness = vals["thickness"]
            mp.lines = True
        vizs = [ob.animation_visualization.motion_path]
        if ob.pose is not None:
            vizs.append(ob.pose.animation_visualization.motion_path)
        for viz in vizs:
            viz.show_keyframe_highlight = vals["show_keys"]
            viz.show_keyframe_numbers = vals["show_key_numbers"]
            viz.show_frame_numbers = vals["show_frame_numbers"]


def _has_keys(ob):
    o = ob
    while o is not None:
        ad = o.animation_data
        if ad is not None and (ad.action is not None or len(ad.nla_tracks)):
            return True
        if any(c.type in {'CHILD_OF', 'FOLLOW_PATH', 'COPY_LOCATION', 'COPY_TRANSFORMS'} for c in o.constraints):
            return True
        o = o.parent
    return False


def create(context):
    """Maya Create Motion Trail on the selection; returns (made, warnings)."""
    scene = context.scene
    vals = values(settings(context))
    viz_bones, owners = _owners(context)
    warnings, made = [], []
    if not owners:
        raise ValueError("Select objects or components to create motion trails")
    if viz_bones is not None:
        apply_settings(viz_bones, vals, scene)
        arm = owners[0][0]
        if not _has_keys(arm):
            warnings.append(f"{arm.name} has no animation: no motion trail")
        else:
            res = bpy.ops.pose.paths_calculate(display_type=viz_bones.type, range=viz_bones.range,
                                               bake_location=viz_bones.bake_location)
            if 'FINISHED' in res:
                made = [pb.name for _a, pb in owners]
    else:
        todo = []
        for ob, _h in owners:
            if ob.motion_path is not None:
                warnings.append(f"{ob.name} already has a motion trail")   # Maya warns and leaves it
            elif not _has_keys(ob):
                warnings.append(f"{ob.name} has no animation: no motion trail")
            else:
                todo.append(ob)
        if todo:
            keep = list(context.selected_objects)
            for ob in keep:
                ob.select_set(ob in todo)
            for ob in todo:
                apply_settings(ob.animation_visualization.motion_path, vals, scene)
            viz = todo[0].animation_visualization.motion_path
            try:
                with context.temp_override(selected_objects=todo, selected_editable_objects=todo,
                                           active_object=todo[0], object=todo[0]):
                    bpy.ops.object.paths_calculate(display_type=viz.type, range=viz.range)
            finally:
                for ob in keep:
                    ob.select_set(True)
            made = [ob.name for ob in todo]
    apply_display(context)
    return made, warnings


def delete(context, selected_only):
    ob = context.active_object
    if ob is not None and ob.mode == 'POSE':
        bpy.ops.pose.paths_clear(only_selected=selected_only)
    else:
        obs = context.selected_objects if selected_only else list(context.scene.objects)
        with context.temp_override(selected_objects=obs, selected_editable_objects=obs):
            bpy.ops.object.paths_clear(only_selected=selected_only)


# --- operators ----------------------------------------------------------------------------------------------------

class ALLSET_OT_motion_trail(bpy.types.Operator):
    """Maya Motion Trail Editor commands"""
    bl_idname = "allset.motion_trail"
    bl_label = "Motion Trail"
    bl_options = {'REGISTER', 'UNDO'}

    action: EnumProperty(items=[('CREATE', "Create Motion Trail", "Create motion trails on the selected objects "
                                 "using the current motion trail settings"),
                                ('DELETE_SELECTED', "Delete Selected", "Removes motion trails from selected objects"),
                                ('DELETE_ALL', "Delete All", "Remove all motion trails from the scene"),
                                ('RANGE', "Update time range to match time slider", ""),
                                ('RESET', "Reset Settings", "Reset all of the values in this editor to their "
                                 "defaults"),
                                ('SAVE_DEFAULT', "Save Settings as Default", "Sets the current settings as default "
                                 "for new motion trails")],
                         options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        s = settings(context)
        if self.action == 'CREATE':
            try:
                made, warnings = create(context)
            except (ValueError, RuntimeError) as ex:
                self.report({'WARNING'}, str(ex))
                return {'CANCELLED'}
            for w in warnings:
                self.report({'WARNING'}, w)
            if made:
                results.result(self, "Motion trail on " + ", ".join(made))
            return {'FINISHED'} if made else {'CANCELLED'}
        if self.action in {'DELETE_SELECTED', 'DELETE_ALL'}:
            delete(context, self.action == 'DELETE_SELECTED')
            return {'FINISHED'}
        if self.action == 'RANGE':
            viz, owners = _owners(context, selected_only=False)
            for ob in context.scene.objects:
                if ob.motion_path is not None:
                    apply_settings(ob.animation_visualization.motion_path, values(s), context.scene)
            if viz is not None:
                apply_settings(viz, values(s), context.scene)
                bpy.ops.pose.paths_update()
            else:
                bpy.ops.object.paths_update()
            return {'FINISHED'}
        if self.action == 'RESET':
            set_values(s, FACTORY)
        elif self.action == 'SAVE_DEFAULT':
            from . import option_windows
            option_windows.store(SAVE_KEY, {k: list(v) if isinstance(v, tuple) else v for k, v in values(s).items()})
        return {'FINISHED'}


class ALLSET_OT_motion_trail_editor(bpy.types.Operator):
    """Maya Motion Trail Editor: create and set up motion trails (Blender motion paths)"""
    bl_idname = "allset.motion_trail_editor"
    bl_label = "Motion Trail Editor"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        from . import option_windows
        saved = option_windows.saved(SAVE_KEY)
        if saved and values(settings(context)) == {k: v for k, v in FACTORY.items()}:   # untouched: Maya's saved defaults
            set_values(settings(context), {k: tuple(v) if isinstance(v, list) else v for k, v in saved.items()})
        return context.window_manager.invoke_props_dialog(self, width=460, title="Motion Trail Editor",
                                                          confirm_text="Close")

    def draw(self, context):
        s = settings(context)
        layout = self.layout
        row = layout.row(align=True)
        row.operator("allset.motion_trail", text="Create Motion Trail").action = 'CREATE'
        row.operator("allset.motion_trail", text="Delete Selected").action = 'DELETE_SELECTED'
        row.operator("allset.motion_trail", text="Delete All").action = 'DELETE_ALL'
        row = layout.row(align=True)
        row.operator("allset.motion_trail", text="Reset Settings").action = 'RESET'
        row.operator("allset.motion_trail", text="Save Settings as Default").action = 'SAVE_DEFAULT'
        box = layout.box()
        box.label(text="Settings")
        _row(box, s, "draw_always", "Draw Style:", "Always Draw")
        _row(box, s, "xray", "", "X-Ray Draw")
        r = box.row()
        r.label(text="Draw Mode:")
        for key, label, _d in DRAW_MODES:
            sub = r.row()
            sub.enabled = key in {'CONSTANT', 'PAST_FUTURE'}
            sub.prop_enum(s, "draw_mode", key, text=label)
        _row(box, s, "anchor_object", "Anchor:", "Object")
        r = box.row()
        r.label(text="Path:")
        r.prop(s, "path_mode", expand=True)
        box.prop(s, "increment")
        r = box.row(align=True)
        r.prop(s, "pre_frames")
        r.prop(s, "post_frames")
        box.operator("allset.motion_trail", text="Update time range to match time slider").action = 'RANGE'
        box = layout.box()
        box.label(text="Edit Settings")
        _row(box, s, "local_custom", "Local Position:", "Custom")
        box = layout.box()
        box.label(text="Display Settings")
        r = box.row()
        r.label(text="Show Key:")
        r.prop(s, "show_keys", text="Markers")
        r.prop(s, "show_key_numbers", text="Numbers")
        r = box.row()
        r.label(text="Show Frame:")
        sub = r.row()
        sub.enabled = False
        sub.prop(s, "show_frames", text="Markers")
        r.prop(s, "show_frame_numbers", text="Numbers")
        box.prop(s, "thickness")
        for name in ("key_size", "frame_size"):
            _row(box, s, name, "", None)
        for name in ("trail_color", "alt_color"):
            box.prop(s, name)
        sub = box.column()
        sub.enabled = False
        for name in ("key_color", "selected_key_color", "frame_color", "slow_color", "fast_color"):
            sub.prop(s, name)
        sub.label(text="Blender's key / frame colours come from the theme.")

    def execute(self, context):
        return {'FINISHED'}


def _row(layout, s, name, label, text):
    r = layout.row()
    if label:
        r.label(text=label)
    sub = r.row()
    sub.enabled = name not in NO_BLENDER
    if text is None:
        sub.prop(s, name)
    else:
        sub.prop(s, name, text=text)
    if name in NO_BLENDER:
        r.label(text="", icon='INFO')


classes = (ALLSET_PG_motion_trail, ALLSET_OT_motion_trail, ALLSET_OT_motion_trail_editor)


def register_props():
    bpy.types.Scene.allset_motion_trail = PointerProperty(type=ALLSET_PG_motion_trail)


def unregister_props():
    del bpy.types.Scene.allset_motion_trail
