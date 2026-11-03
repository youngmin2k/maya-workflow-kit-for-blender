# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Time Slider + Range Slider in the Timeline header, and a timeline view that
follows the playback range.

Maya's Time Slider (transport buttons, current time
field, auto key) and Range Slider (animation start, playback start, [range], playback end,
animation end). Blender form:
- the timeline header's ``draw_header`` (``DOPESHEET_HT_editor_buttons`` in Timeline mode, a plain class, not in
  bpy.types) is wrapped to draw ``draw_header`` below and restored on unregister.
- Maya's animation range = scene frame_start/end; its playback range = the preview range
  (``use_preview_range`` off: playback = animation range, inner fields greyed).
- Maya's time slider always shows the playback range: after a file load and whenever the
  range changes, every Timeline runs ``anim.scene_range_frame`` (a msgbus subscription and
  a load_post handler defer it to a timer).
- LMB on the timeline = time (Shift = red range), RMB = Maya's
  Time Slider menu, MMB = move the time without updating the scene (Maya's MMB drag).
- The
  header is the Range Slider row in Maya's order; Blender's Playback / Keying / View / Marker menus move
  into the animation preferences menu at its right end (``DOPESHEET_MT_editor_menus.draw_collapsible`` is
  overridden on the class for Timeline mode, deleted on unregister). A timeline with its sidebar shown (the Maya Workflow Kit
  layout) draws the current frame field and the 8 transport buttons there, at the right end of the
  Time Slider row like Maya (``ALLSET_PT_time_slider``); other timelines keep them in the header.
"""

import bpy

from .. import results
from .. import compat, i18n
from bpy.app.handlers import persistent

# Blender 5.x: the Timeline is a Dope Sheet mode; compat names the header classes.
header_classes = compat.timeline_header_classes


def _is_timeline(context):
    space = getattr(context, "space_data", None)
    return space is not None and getattr(space, "mode", None) == 'TIMELINE'

_ORIGINAL = {}
_OWNER = object()
_RANGE_PROPS = ("frame_start", "frame_end", "frame_preview_start", "frame_preview_end",
                "use_preview_range")


def draw_transport(layout, context):
    """Current frame field + the 8 Maya transport buttons."""
    scene, screen = context.scene, context.screen
    row = layout.row()
    row.ui_units_x = 4.5    # current time field width 90 px
    row.prop(scene, "frame_current", text="")
    row = layout.row(align=True)
    row.operator("screen.frame_jump", text="", icon='REW').end = False
    row.operator("screen.frame_offset", text="", icon='TRIA_LEFT_BAR').delta = -1
    row.operator("screen.keyframe_jump", text="", icon='PREV_KEYFRAME').next = False
    if screen.is_animation_playing:
        row.scale_x = 2
        row.operator("screen.animation_play", text="", icon='PAUSE')
        row.scale_x = 1
    else:
        row.operator("screen.animation_play", text="", icon='PLAY_REVERSE').reverse = True
        row.operator("screen.animation_play", text="", icon='PLAY')
    row.operator("screen.keyframe_jump", text="", icon='NEXT_KEYFRAME').next = True
    row.operator("screen.frame_offset", text="", icon='TRIA_RIGHT_BAR').delta = 1
    row.operator("screen.frame_jump", text="", icon='FF').end = True


def has_slider_panel(space, area=None):
    """The timeline shows the Time Slider buttons in its sidebar (the Maya Workflow Kit layout). With ``area``, the
    sidebar must also have room: Blender 5.x loads the 4.5 template's timeline sidebar 1 px wide,
    and then the buttons stay in the header."""
    if space is None or space.type != 'DOPESHEET_EDITOR' or not space.show_region_ui:
        return False
    if area is None:
        return True
    ui = next((r for r in area.regions if r.type == 'UI'), None)
    return ui is not None and ui.width > 20


# Range Slider row, Maya order.
RANGE_ITEMS = ("start", "playback start", "range", "playback end", "end", "auto key", "No Character Set",
               "No Anim Layer", "fps", "loop", "sound", "animation preferences")


def draw_header(context, layout):
    space, area = context.space_data, context.area
    if has_slider_panel(space) and not has_slider_panel(space, area):
        # Maya Workflow Kit layout whose sidebar can't open (Blender 5.x: the Timeline mode keeps its sidebar 1 px, even in a
        # factory file): one row, Range Slider first, the Time Slider buttons at the right end
        draw_range_slider(layout, context)
        layout.separator_spacer()
        draw_transport(layout, context)
        return
    if not has_slider_panel(space, area):
        layout.separator_spacer()
        draw_transport(layout, context)
        layout.separator_spacer()
    draw_range_slider(layout, context)   # Maya: the range fields start at the left edge


def draw_range_slider(layout, context):
    scene = context.scene
    # animation start | playback start [range bar] playback end | animation end
    row = layout.row(align=True)
    row.ui_units_x = 4.5
    row.prop(scene, "frame_start", text="")
    row = layout.row(align=True)
    row.ui_units_x = 4.5
    row.active = scene.use_preview_range
    row.prop(scene, "frame_preview_start", text="")
    # Maya's range bar. In the Maya Workflow Kit layout an empty label holds its place and
    # ui/range_bar.py draws the draggable bar there. Elsewhere Blender has no such
    # widget: the toggle = use the playback range (off = the whole animation range), the button frames it.
    from . import range_bar
    bar = layout.row(align=True)
    bar.ui_units_x = range_bar.BAR_UNITS
    if range_bar.active(context):
        bar.label(text="")
    else:
        a, b = (scene.frame_preview_start, scene.frame_preview_end) if scene.use_preview_range else \
            (scene.frame_start, scene.frame_end)
        bar.prop(scene, "use_preview_range", text="", toggle=True, icon='PREVIEW_RANGE')
        bar.operator("anim.scene_range_frame", text=f"{a}" + " " * 40 + f"{b}")
    row = layout.row(align=True)
    row.ui_units_x = 4.5
    row.active = scene.use_preview_range
    row.prop(scene, "frame_preview_end", text="")
    row = layout.row(align=True)
    row.ui_units_x = 4.5
    row.prop(scene, "frame_end", text="")

    layout.separator_spacer()
    row = layout.row(align=True)
    # Maya auto key (:585): Maya's key button, red while on (issue #37: Blender's record circle wasn't recognised)
    # The kit's own Maya Auto Key (operators/auto_key.py): keys only already keyed channels without
    # Blender's "Only Insert Available" preference.
    on = getattr(scene, "allset_auto_key", False)
    key = row.row(align=True)
    key.alert = on
    key.prop(scene, "allset_auto_key", text="", toggle=True, icon='KEY_HLT' if on else 'KEY_DEHLT')
    # Maya: the current character set and the current animation layer (the selected
    # layer of operators/anim_layers; "No Anim Layer" while the scene has only BaseAnimation)
    from ..operators import anim_layers
    ls = getattr(context.scene, "allset_anim_layers", ())
    sel = anim_layers.selected(context.scene) if len(ls) > 1 else None
    # Maya's current character field (kit character sets = Keying Sets, operators/character_sets.py)
    ks = scene.keying_sets.active
    sub = layout.row()
    sub.ui_units_x = 6
    sub.menu("ALLSET_MT_character_set_current", text=ks.bl_label if ks is not None else i18n.mark("No Character Set"),
             icon='DOWNARROW_HLT')
    for text, on in ((sel.name if sel is not None else i18n.mark("No Anim Layer"), sel is not None),):
        sub = layout.row()
        sub.enabled = on
        sub.ui_units_x = 6
        sub.label(text=text, icon='DOWNARROW_HLT')
    row = layout.row()
    row.ui_units_x = 5
    fps = scene.render.fps / scene.render.fps_base
    row.menu("RENDER_MT_framerate_presets", text=f"{fps:g} fps")
    row = layout.row(align=True)
    sub = row.row(align=True)
    sub.enabled = False   # Maya loop / once / oscillate: Blender always loops
    sub.label(text="", icon='FILE_REFRESH')
    row.prop(scene, "use_audio", text="", icon='SPEAKER', invert_checkbox=True)
    row.menu("ALLSET_MT_anim_preferences", text="", icon='PREFERENCES')


class ALLSET_MT_anim_preferences(bpy.types.Menu):
    """Animation preferences (Maya's button at the right end of the Range Slider): Blender's
    timeline Playback, Keying, View and Marker menus"""
    bl_label = "Animation Preferences"

    def draw(self, context):
        lay = self.layout
        lay.popover(panel="TIME_PT_playback", text="Playback")
        lay.popover(panel="TIME_PT_keyframing_settings", text="Keying")
        lay.separator()
        lay.menu("TIME_MT_view", text="View")
        lay.menu(compat.timeline_marker_menu(), text="Marker")


class ALLSET_PT_time_slider(bpy.types.Panel):
    """Current time field and transport buttons at the right of Maya's Time Slider."""
    bl_space_type = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_label = "Time Slider"
    bl_options = {'HIDE_HEADER'}

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space is not None and space.mode == 'TIMELINE'

    def draw(self, context):
        draw_transport(self.layout.row(align=False), context)


# --- Time Slider hand feel ---------------------------------------------------------------
# Maya: LMB anywhere on the Time Slider moves the time, Shift+LMB drag highlights a range, RMB = the
# Time Slider menu (Maya 2022 labels).
# Blender's timeline is a Dope Sheet mode, so these sit first in the "Dopesheet" keymap and pass
# through in the Dope Sheet itself (keys are clicked there in Maya too).

RANGE_COLOR = (0.78, 0.16, 0.16, 0.35)   # red range highlight
RANGE_ARROW_COLOR = (1.0, 1.0, 1.0, 0.9)
# Time Slider items with no Blender equivalent: (label, Help Line text)
TIME_NOTICES = {
    "Paste Connect": "Blender pastes keys as they were copied: no connect (offset) paste.",
    "Play Every Frame, Free": "Blender never plays faster than the scene frame rate.",
    "Once": "Blender playback always loops.",
    "Oscillate": "Blender playback always loops.",
    "Enabled Clips": "Blender has no Time Editor clips (NLA strips instead).",
    "Sound Length": "Use the sound strip's length in the Video Sequencer.",
}


def frame_at(region, x):
    """Whole frame under window x in a timeline WINDOW region."""
    return int(round(region.view2d.region_to_view(x - region.x, 0)[0]))


def set_range(wm, a, b, on=True):
    wm.allset_time_range = (int(a), int(b))
    wm.allset_time_range_on = on


class ALLSET_OT_time_scrub(bpy.types.Operator):
    """Maya Time Slider: click or drag to move the time (Shift: highlight a range, middle mouse: keep the pose)"""
    bl_idname = "allset.time_scrub"
    bl_label = "Time Slider Scrub"
    bl_options = {'INTERNAL'}

    range: bpy.props.BoolProperty(name="Range", description="Shift-drag: highlight a time range",
                                  options={'SKIP_SAVE'})
    hold: bpy.props.BoolProperty(name="Hold", description="Move the time without updating the scene, so the "
                                 "current pose can be keyed at another frame", options={'SKIP_SAVE'})

    def invoke(self, context, event):
        region = context.region
        if not _is_timeline(context) or region is None or region.type != 'WINDOW':
            return {'PASS_THROUGH'}
        self._region = region
        self._button = event.type
        self._held = None
        if self.hold:
            # Maya MMB: every animated channel keeps the value it has now while the time moves
            from ..operators import time_hold
            self._held = time_hold.snapshot()
        wm, scene = context.window_manager, context.scene
        self._old = (scene.frame_current, tuple(wm.allset_time_range), wm.allset_time_range_on)
        f = frame_at(region, event.mouse_x)
        if self.range:
            self._anchor = f
            set_range(wm, f, f)
        else:
            wm.allset_time_range_on = False   # a plain click drops the highlighted range (Maya)
            self._set_frame(scene, f)
        _tag(context)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _set_frame(self, scene, f):
        if self._held is None:
            scene.frame_current = f
        else:
            from ..operators import time_hold
            time_hold.move_time(scene, f, self._held)

    def modal(self, context, event):
        wm, scene = context.window_manager, context.scene
        if event.type == 'MOUSEMOVE':
            f = frame_at(self._region, event.mouse_x)
            if self.range:
                set_range(wm, self._anchor, f)
            elif f != scene.frame_current:
                self._set_frame(scene, f)
            _tag(context)
            return {'RUNNING_MODAL'}
        if event.type == self._button and event.value == 'RELEASE':
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._set_frame(scene, self._old[0])
            set_range(wm, *self._old[1], on=self._old[2])
            _tag(context)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


RANGE_EDGE_PX = 8          # end-arrow zone of a highlighted range (x UI scale)


def range_zone(context, region, x):
    """'LEFT' / 'RIGHT' / 'MOVE' when window x is on the highlighted range of this timeline, else None."""
    from ..operators import time_range
    wm = context.window_manager
    if not getattr(wm, "allset_time_range_on", False):
        return None
    x0, x1 = range_rect(region, *wm.allset_time_range)
    edge = RANGE_EDGE_PX * (context.preferences.system.ui_scale or 1.0)
    return time_range.zone(x - region.x, x0, x1, edge)


class ALLSET_OT_time_range_drag(bpy.types.Operator):
    """Maya Time Slider range: drag the middle to move its keys, an end arrow to scale them"""
    bl_idname = "allset.time_range_drag"
    bl_label = "Move / Scale Range Keys"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    def invoke(self, context, event):
        from ..operators import time_keys, time_range
        region = context.region
        if not _is_timeline(context) or region is None or region.type != 'WINDOW':
            return {'PASS_THROUGH'}
        mode = range_zone(context, region, event.mouse_x)
        if mode is None:
            return {'PASS_THROUGH'}
        wm = context.window_manager
        a, b = sorted(wm.allset_time_range)
        curves, seen = [], set()
        for node in time_keys.nodes(context):
            for fc in time_keys.node_fcurves(node):
                if fc.as_pointer() in seen:
                    continue
                seen.add(fc.as_pointer())
                idx = [i for i, kp in enumerate(fc.keyframe_points) if time_keys._in(kp, a, b)]
                if idx:
                    curves.append((fc, idx))
        self._drag = time_range.Drag(curves, a, b)
        self._region, self._mode, self._range = region, ('MOVE' if a == b else mode), (a, b)
        self._f0 = frame_at(region, event.mouse_x)
        self._f, self._moved = self._f0, False
        self._x0 = event.mouse_x
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _update(self, context, f):
        from ..operators import time_range
        wm = context.window_manager
        self._f = f
        self._drag.apply(self._mode, self._f0, f)
        set_range(wm, *time_range.new_range(*self._range, self._mode, self._f0, f))
        _tag(context)
        for area in context.screen.areas:
            if area.type in {'GRAPH_EDITOR', 'VIEW_3D'}:
                area.tag_redraw()

    def modal(self, context, event):
        wm, scene = context.window_manager, context.scene
        if event.type == 'MOUSEMOVE':
            f = frame_at(self._region, event.mouse_x)
            if abs(event.mouse_x - self._x0) >= 3:
                self._moved = True
            if self._moved and f != self._f:
                self._update(context, f)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if not self._moved:
                # a click on the range = a plain Time Slider click: drop the range, go to that frame (no undo step)
                wm.allset_time_range_on = False
                scene.frame_current = self._f0
                _tag(context)
                return {'CANCELLED'}
            n = self._drag.finish(self._mode, self._f0, self._f)
            scene.frame_set(scene.frame_current)          # re-evaluate at the current time
            results.result(self, f"{'Moved' if self._mode == 'MOVE' else 'Scaled'} {n} key(s)")
            _tag(context)
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._drag.cancel()
            set_range(wm, *self._range)
            _tag(context)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


def _tag(context):
    for area in context.screen.areas if context.screen else ():
        if area.type == 'DOPESHEET_EDITOR':
            area.tag_redraw()


class ALLSET_OT_time_slider_menu(bpy.types.Operator):
    """Maya Time Slider menu (RMB on the Time Slider)"""
    bl_idname = "allset.time_slider_menu"
    bl_label = "Time Slider Menu"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        if not _is_timeline(context):
            return {'PASS_THROUGH'}
        bpy.ops.wm.call_menu(name=ALLSET_MT_time_slider.__name__)
        return {'FINISHED'}


class ALLSET_OT_time_slider_unavailable(bpy.types.Operator):
    """Time Slider item with no Blender equivalent (greyed)"""
    bl_idname = "allset.time_slider_unavailable"
    bl_label = "Not Available"
    bl_options = {'INTERNAL'}

    item: bpy.props.StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return False

    @classmethod
    def description(cls, context, props):
        line = TIME_NOTICES.get(props.item, "")
        if line:
            from . import notices
            notices.show(f"{props.item}: {line}")
        return f"Maya: Time Slider > {props.item}\n{line}"

    def execute(self, context):
        return {'CANCELLED'}


def _keys(layout, action, text=None, **props):
    op = layout.operator("allset.time_keys", text=text)
    op.action = action
    for k, v in props.items():
        setattr(op, k, v)
    return op


def _grey(layout, label):
    layout.operator(ALLSET_OT_time_slider_unavailable.bl_idname, text=label).item = label


class ALLSET_MT_time_slider(bpy.types.Menu):
    """Maya Time Slider menu, in Maya's order"""
    bl_label = "Time Slider"

    def draw(self, context):
        lay = self.layout
        _keys(lay, "CUT", "Cut")
        _keys(lay, "COPY", "Copy")
        lay.menu("ALLSET_MT_time_slider_paste", text="Paste")
        _keys(lay, "DELETE", "Delete")
        _keys(lay, "SNAP", "Snap")
        lay.menu("ALLSET_MT_time_slider_keys", text="Keys")
        lay.menu("ALLSET_MT_time_slider_tangents", text="Tangents")
        lay.separator()
        lay.menu("ALLSET_MT_time_slider_speed", text="Playback Speed")
        lay.menu("ALLSET_MT_time_slider_looping", text="Playback Looping")
        lay.menu("ALLSET_MT_time_slider_range", text="Set Range to")
        lay.separator()
        op = lay.operator("allset.menu_run", text="Playblast...")
        op.op, op.props = "render.opengl", '{"animation": true}'


class ALLSET_MT_time_slider_paste(bpy.types.Menu):
    bl_label = "Paste"

    def draw(self, context):
        _keys(self.layout, "PASTE", "Paste")
        _grey(self.layout, "Paste Connect")


class ALLSET_MT_time_slider_keys(bpy.types.Menu):
    bl_label = "Keys"

    def draw(self, context):
        for action, label in (("TO_KEY", "Convert to Key"), ("TO_BREAKDOWN", "Convert to Breakdown"),
                              ("ADD_INBETWEEN", "Add Inbetween"), ("REMOVE_INBETWEEN", "Remove Inbetween")):
            _keys(self.layout, action, label)


class ALLSET_MT_time_slider_tangents(bpy.types.Menu):
    bl_label = "Tangents"

    def draw(self, context):
        for kind in ("SPLINE", "LINEAR", "CLAMPED", "STEPPED", "FLAT", "PLATEAU", "AUTO"):
            _keys(self.layout, "TANGENT", kind.title(), tangent=kind)


class ALLSET_MT_time_slider_speed(bpy.types.Menu):
    bl_label = "Playback Speed"

    def draw(self, context):
        lay = self.layout
        lay.prop_enum(context.scene, "sync_mode", 'FRAME_DROP', text="Real-time")
        _grey(lay, "Play Every Frame, Free")
        lay.prop_enum(context.scene, "sync_mode", 'NONE', text="Play Every Frame, Max Real-time")


class ALLSET_MT_time_slider_looping(bpy.types.Menu):
    bl_label = "Playback Looping"

    def draw(self, context):
        lay = self.layout
        _grey(lay, "Once")
        _grey(lay, "Oscillate")
        lay.label(text="Continuous", icon='CHECKMARK')


class ALLSET_MT_time_slider_range(bpy.types.Menu):
    bl_label = "Set Range to"

    def draw(self, context):
        lay = self.layout
        for mode, label in (("START_END", "Start/End"), ("MIN_MAX", "Min/Max"), ("SELECTED", "Selected")):
            lay.operator("allset.time_set_range", text=label).mode = mode
        _grey(lay, "Enabled Clips")
        _grey(lay, "Sound Length")


TIME_SLIDER_MENUS = (ALLSET_MT_time_slider, ALLSET_MT_time_slider_paste, ALLSET_MT_time_slider_keys,
                     ALLSET_MT_time_slider_tangents, ALLSET_MT_time_slider_speed,
                     ALLSET_MT_time_slider_looping, ALLSET_MT_time_slider_range)


# --- the red range highlight -----------------------------------------------------------------------

_draw_handle = []


def range_rect(region, a, b):
    """Window-region x0, x1 of frames a..b (whole frames: half a frame either side)."""
    lo, hi = min(a, b) - 0.5, max(a, b) + 0.5
    x0 = region.view2d.view_to_region(lo, 0, clip=False)[0]
    x1 = region.view2d.view_to_region(hi, 0, clip=False)[0]
    return x0, x1


def _draw_range():
    context = bpy.context
    wm = context.window_manager
    if not _is_timeline(context):
        return
    region = context.region
    maya = has_slider_panel(context.space_data)
    if maya:
        _draw_ruler(context, region)
    _draw_keys(context, region, maya)
    if not getattr(wm, "allset_time_range_on", False):
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    x0, x1 = range_rect(region, *wm.allset_time_range)
    h = region.height
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {"pos": ((x0, 0), (x1, 0), (x1, h), (x0, 0), (x1, h), (x0, h))})
    gpu.state.blend_set('ALPHA')
    shader.uniform_float("color", RANGE_COLOR)
    batch.draw(shader)
    # Maya's arrows on a highlighted range: ◀ / ▶ in the end zones (scale), ◀▶ in the middle (move)
    edge = RANGE_EDGE_PX * (context.preferences.system.ui_scale or 1.0)
    k = min(edge * 0.6, h * 0.25)
    y = h * 0.5
    tris = []

    def arrow(cx, d):
        tris.extend(((cx - d * k * 0.5, y), (cx + d * k * 0.5, y + k * 0.6), (cx + d * k * 0.5, y - k * 0.6)))
    cx = (x0 + x1) * 0.5
    if x1 - x0 >= 3 * edge:
        arrow(x0 + edge * 0.5, 1)       # tip left
        arrow(x1 - edge * 0.5, -1)      # tip right
    arrow(cx - k * 0.55, 1)
    arrow(cx + k * 0.55, -1)
    batch = batch_for_shader(shader, 'TRIS', {"pos": tris})
    shader.uniform_float("color", RANGE_ARROW_COLOR)
    batch.draw(shader)
    gpu.state.blend_set('NONE')


# --- Maya ruler -------------------------------------------
# The Maya Workflow Kit layout's Time Slider is painted over Blender's timeline drawing: a dark background, one 2 px
# tick + label per step (the smallest step whose spacing fits the labels, like Maya), the bottom band and the
# translucent current-time block with its white frame number. At UI scale 1.0 (a 32 px tall ruler): rows 1-8 labels
# #757575, ticks rows 13-27 #7c7c7c, rows 29-31 #373737, background #2b2b2b, current time = white at 18.4 % over the
# frame's cell, its number white in rows 16-23.
# Blender draws its own current-frame box in the region overlay after every Python handler (a full-region
# POST_PIXEL fill hides everything else of Blender's) and no RNA / theme-free switch hides it, so that box stays on
# top.
MAYA_RULER_H = 32.0
RULER_BG = (0x2b / 255, 0x2b / 255, 0x2b / 255, 1.0)
RULER_BAND = (0x37 / 255, 0x37 / 255, 0x37 / 255, 1.0)
RULER_TICK = (0x7c / 255, 0x7c / 255, 0x7c / 255, 1.0)
RULER_LABEL = (0x75 / 255, 0x75 / 255, 0x75 / 255, 1.0)
# the current-time block is #525252 over the #2b2b2b ruler = white at (0x52 - 0x2b) / (0xff - 0x2b) = 18.4 %
RULER_CURRENT = (1.0, 1.0, 1.0, (0x52 - 0x2b) / (0xff - 0x2b))
RULER_CURRENT_LABEL = (1.0, 1.0, 1.0, 1.0)
# (top row, bottom row) of the 32 px ruler. With Time Slider bookmarks
# (kit: timeline markers, operators/bookmarks.py) the ruler gets a strip on top and moves labels / ticks down:
# strip #454545 rows 0-8, each bookmark's colour at 80 % over
# it in rows 0-4 with a solid 1 px left edge over the strip height.
ROWS = {"label": (1, 8), "tick": (13, 27), "current_label": (16, 23), "band": (29, 31)}
ROWS_BOOKMARKS = {"label": (11, 18), "tick": (23, 27), "current_label": (19, 26), "band": (29, 31),
                  "strip": (0, 8), "bookmark": (0, 4)}
BOOKMARK_STRIP = (0x45 / 255, 0x45 / 255, 0x45 / 255, 1.0)
BOOKMARK_RGB = (204 / 255, 92 / 255, 92 / 255)   # bookmark colour (Maya picks one per bookmark)
TICK_PX = 2.0
# Eight-pixel label row in the 32 px ruler, converted to BLF size.
RULER_FONT_SIZE = 8.0 / 0.72
NICE_STEPS = tuple(m * 10 ** e for e in range(8) for m in (1, 2, 5))


# Cases (widget px, first, last frame) where this model picks another step than Maya (tests/test_step186_time_slider.py;
# the default 1-120 and the short ranges match): Maya's threshold also moves with the widget width and the step, and
# it uses steps of 4 / 400 / 4000 with wide labels. "max(a, b x digits)" thresholds with 1-2-4 steps drew 1-120 every
# 4 frames: not taken.
STEP_MATCHES = 32
STEP_DEVIATIONS = ((1292, 1, 10000), (692, 1, 120), (1592, 1, 120), (1592, 1, 60), (1292, 1, 215), (1292, 1, 230),
                   (1292, 1, 250), (1292, 1001, 1100), (1292, 1, 100000), (692, 1, 130), (692, 1, 110))


def label_digits(frame):
    return len(str(abs(int(frame)))) + (1 if frame < 0 else 0)


def label_need_px(digits):
    """Spacing (px at UI scale 1) between two labels of ``digits`` characters (at a 1292 px wide
    ruler: <= 3 digits fit at 25.6 px but not 24.7, 4 digits need more than 25.6 and fit at 32, 5 digits
    need more than 32)."""
    return max(25.0, 7.0 * digits + 3.0)


def _multiples(step, lo, hi):
    import math
    first = math.ceil(lo / step) * step
    return range(int(first), int(hi) + 1, int(step))


def tick_step(start, end, px_per_frame, scale=1.0):
    """Maya Time Slider step (frames between ticks / labels) for the playback range start..end shown at
    ``px_per_frame``: the smallest of 1, 2, 5, 10, 20, 50 ... whose spacing fits the widest label below the end."""
    for step in NICE_STEPS:
        labels = _multiples(step, start, max(start, end - 1))
        widest = max((label_digits(f) for f in (labels[0], labels[-1])), default=1) if len(labels) else 1
        if step * px_per_frame >= label_need_px(widest) * scale:
            return step
    return NICE_STEPS[-1]


def ruler_ticks(step, lo, hi):
    """Frames with a tick and a label in the visible frame range lo..hi."""
    return list(_multiples(step, lo - 1, hi + 1))


# A taller Time Slider (Maya 2026 behaviour, #190): the frame numbers stay at the top in
# their size, the current frame number stays at the bottom, and the ticks keep their bottom end and normal length
# until half the room between the numbers and that end (less this many px) is longer; then they take that half.
TICK_HALF_PAD = 2.33


def _rows(name, h, rows=None, scale=1.0):
    """(y0, y1) region rows (bottom-up) of a ruler row band at region height ``h``, UI-scaled: the label rows keep
    their place under the top edge, the band and the current frame number theirs above the bottom edge, and the
    ticks grow Maya's way (``TICK_HALF_PAD``)."""
    rows = rows or ROWS
    top, bottom = rows[name]
    k = min(h / MAYA_RULER_H, scale)
    if name == "tick":
        y0 = (MAYA_RULER_H - bottom - 1) * k                     # the bottom end, above the band
        normal = (bottom + 1 - top) * k
        label_low = h - (rows["label"][1] + 1) * k              # the frame numbers' lowest row
        half = (label_low - y0) / 2 - TICK_HALF_PAD * k
        return y0, y0 + max(normal, half)
    if name in ("band", "current_label"):
        return (MAYA_RULER_H - bottom - 1) * k, (MAYA_RULER_H - top) * k
    return h - (bottom + 1) * k, h - top * k


def _draw_ruler(context, region):
    import blf
    import gpu
    from gpu_extras.batch import batch_for_shader
    scene = context.scene
    s = context.preferences.system.ui_scale or 1.0
    w, h = region.width, region.height
    v2d = region.view2d

    def x_of(f):
        return v2d.view_to_region(f, 0, clip=False)[0]
    pxf = x_of(1.0) - x_of(0.0)
    if pxf <= 0:
        return
    start, end = playback_range(scene)
    step = tick_step(start, end, pxf, s)
    lo, hi = v2d.region_to_view(0, 0)[0], v2d.region_to_view(w, 0)[0]
    frames = ruler_ticks(step, lo, hi)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')

    def rects(rs, colour):
        tris = []
        for x0, y0, x1, y1 in rs:
            tris += [(x0, y0), (x1, y0), (x1, y1), (x0, y0), (x1, y1), (x0, y1)]
        if tris:
            shader.uniform_float("color", colour)
            batch_for_shader(shader, 'TRIS', {"pos": tris}).draw(shader)
    from ..operators import bookmarks
    marks = bookmarks.markers(scene)
    rows = ROWS_BOOKMARKS if marks else ROWS
    gpu.state.blend_set('ALPHA')
    rects([(0, 0, w, h)], RULER_BG)
    b0, b1 = _rows("band", h, rows, s)
    rects([(0, b0, w, b1)], RULER_BAND)
    if marks:
        s0, s1 = _rows("strip", h, rows, s)
        rects([(0, s0, w, s1)], BOOKMARK_STRIP)
        m0, m1 = _rows("bookmark", h, rows, s)
        bars, edges = [], []
        for m in marks:
            a, b = bookmarks.bookmark_range(scene, m)
            x0, x1 = round(x_of(a - 0.5)), round(x_of(b + 0.5))
            bars.append((x0, m0, x1, m1))
            edges.append((x0, s0, x0 + max(1.0, round(s)), s1))
        rects(bars, (*BOOKMARK_RGB, 0.8))
        rects(edges, (*BOOKMARK_RGB, 1.0))
    tw = max(1.0, round(TICK_PX * s))
    t0, t1 = _rows("tick", h, rows, s)
    lefts = {f: round(x_of(f - 0.5)) for f in frames}
    rects([(x, t0, x + tw, t1) for x in lefts.values()], RULER_TICK)
    cur = scene.frame_current
    cx0, cx1 = x_of(cur - 0.5), x_of(cur + 0.5)
    rects([(round(cx0), 0, max(round(cx0) + 1, round(cx1)), h)], RULER_CURRENT)
    # labels: 2 px + a fifth of a frame right of the tick
    l0, _l1 = _rows("label", h, rows, s)
    # The same UI-scaled font is used for the current-frame number.
    blf.size(0, RULER_FONT_SIZE * s)
    off = 2 * s + 0.2 * pxf
    blf.color(0, *RULER_LABEL)
    for f, x in lefts.items():
        blf.position(0, x + off, l0, 0)
        blf.draw(0, str(f))
    c0, _c1 = _rows("current_label", h, rows, s)
    blf.color(0, *RULER_CURRENT_LABEL)
    blf.position(0, round(cx0) + off, c0, 0)
    blf.draw(0, str(cur))
    gpu.state.blend_set('NONE')


def playback_range(scene):
    """Maya playback range = the preview range when on, else the scene range (module docstring)."""
    if scene.use_preview_range:
        return scene.frame_preview_start, scene.frame_preview_end
    return scene.frame_start, scene.frame_end


# --- key ticks -----------------------------------------------------------------------------
# Maya draws the keys of the selected nodes as 1 px lines over the whole Time Slider height: keys red,
# breakdowns green.
KEY_RGB = (1.0, 0.0, 0.0, 1.0)
BREAKDOWN_RGB = (0.0, 1.0, 0.0, 1.0)


def key_frames(nodes):
    """Sorted [(frame, is_breakdown)] of the nodes' keys; a frame with any regular key is a regular key."""
    from ..operators import time_keys
    from . import cb_channels
    frames = {}
    for node in nodes:
        # Channel Box Sync Timeline Display: only the selected channels' keys
        curves = cb_channels.timeline_curves(bpy.context, node)
        if curves is None:
            curves = time_keys.node_fcurves(node)
            if isinstance(node, bpy.types.Object):
                # the shown layer's keys + BaseAnimation keys of channels not in that layer (Maya)
                from ..operators import anim_layers
                curves = list(curves) + anim_layers.hidden_base_curves(node, bpy.context.scene)
                curves += blend_weight_curves(node)
                # component mode: the keys of the selected points (vertices / CVs / lattice points)
                from ..operators import point_keys
                curves += point_keys.selected_point_curves(node)
        for fc in curves:
            for kp in fc.keyframe_points:
                f = round(kp.co.x, 3)
                frames[f] = frames.get(f, True) and kp.type == 'BREAKDOWN'
    return sorted(frames.items())


def blend_weight_curves(ob):
    """Curves of the mesh's blendShape target weights (they live on its Key datablock, which the Channel Box lists
    under INPUTS): their keys are part of the object's ticks."""
    from . import channel_box
    from .. import compat
    bs = channel_box.blend_shape_key(ob)
    if bs is None:
        return []
    paths = {channel_box.blend_path(kb.name) for kb in channel_box.blend_shape_targets(bs)}
    return [fc for fc in compat.id_fcurves(bs) if fc.data_path in paths]


def key_x(region, frame, maya):
    """Region x of a key tick: Maya draws it on the frame's tick, the left edge of the frame's cell;
    other timelines keep Blender's frame centre."""
    return region.view2d.view_to_region(frame - 0.5 if maya else frame, 0, clip=False)[0]


def _shows_keys(node):
    if not isinstance(node, bpy.types.Object):
        return True     # pose bones: only selected ones are listed
    if node.mode != 'OBJECT':
        return True     # edit / paint modes: the object whose components are being worked on
    try:
        return node.select_get()
    except RuntimeError:    # not in the view layer
        return False


def tick_nodes(context):
    """Nodes whose keys the Time Slider shows: the selected ones, like Maya (nothing selected = no ticks). Blender
    keeps an active object after it is deselected; its keys are not shown."""
    from . import channel_box
    return [n for n in channel_box.targets(context) if _shows_keys(n)]


def _draw_keys(context, region, maya=False):
    keys = key_frames(tick_nodes(context))
    if not keys:
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    w = max(1.0, round(context.preferences.system.ui_scale or 1.0))
    h = region.height
    if maya:
        from ..operators import bookmarks
        if bookmarks.markers(context.scene):     # Maya: keys stay under the bookmark strip
            h = _rows("strip", h, ROWS_BOOKMARKS, context.preferences.system.ui_scale or 1.0)[0]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    current = context.scene.frame_current
    for colour, breakdown in ((KEY_RGB, False), (BREAKDOWN_RGB, True)):
        tris = []
        for f, bd in keys:
            if bd != breakdown:
                continue
            x = key_x(region, f, maya)
            if x < -w or x > region.width + w:
                continue
            x0, x1 = int(x), int(x) + w
            if abs(f - current) < 0.5:
                # Blender draws its current-frame box over add-on drawing (the region's draw_overlay runs after
                # POST_PIXEL), and in the Maya layout that box fills the Time Slider: a key at the current frame
                # was invisible (issue #38). Maya shows it through its current-time block, one frame wide. Here the
                # key fills the current frame's cell: the box hides its middle and the rows above and below the
                # box stay red, while the ticks of the neighbouring frames stay visible.
                left, right = (region.view2d.view_to_region(f + d, 0, clip=False)[0] for d in (-0.5, 0.5))
                x0 = int(left)
                x1 = max(x0 + w, int(right))
            tris += [(x0, 0), (x1, 0), (x1, h), (x0, 0), (x1, h), (x0, h)]
        if tris:
            shader.uniform_float("color", colour)
            batch_for_shader(shader, 'TRIS', {"pos": tris}).draw(shader)


# --- timeline view = playback range -------------------------------------------------------

def timeline_areas(wm):
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type == 'DOPESHEET_EDITOR' and area.spaces.active.mode == 'TIMELINE':
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                if region is not None:
                    yield win, area, region


def fit_timelines():
    wm = bpy.context.window_manager
    n = 0
    for win, area, region in list(timeline_areas(wm)):
        with bpy.context.temp_override(window=win, screen=win.screen, area=area, region=region):
            if bpy.ops.anim.scene_range_frame.poll():
                bpy.ops.anim.scene_range_frame()
                n += 1
    return n


def _deferred_fit():
    try:
        fit_timelines()
    except Exception:   # never break file loading / editing over a view nicety
        import traceback
        traceback.print_exc()
    return None


def _schedule():
    if not bpy.app.timers.is_registered(_deferred_fit):
        bpy.app.timers.register(_deferred_fit, first_interval=0.0)


def _subscribe():
    bpy.msgbus.clear_by_owner(_OWNER)
    for prop in _RANGE_PROPS:
        bpy.msgbus.subscribe_rna(key=(bpy.types.Scene, prop), owner=_OWNER, args=(), notify=_schedule)


@persistent
def _on_load(_dummy=None):
    _subscribe()   # file loading clears msgbus subscriptions
    if not bpy.app.background:
        _schedule()


classes = (ALLSET_MT_anim_preferences, ALLSET_PT_time_slider, ALLSET_OT_time_scrub, ALLSET_OT_time_range_drag, ALLSET_OT_time_slider_menu,
           ALLSET_OT_time_slider_unavailable, *TIME_SLIDER_MENUS)


# Maya's undo never moves the current time (a time change isn't an undo step there); Blender's memfile undo restores
# the scene's frame_current with everything else, so Ctrl+Z after scrubbing jumped back. The frame
# is put back from a 0 s timer, not inside undo_post (data written there before the next push is unsafe for redo).
_KEEP = {}


@persistent
def _keep_frame_pre(*_args):
    scene = bpy.context.scene
    if scene is not None:
        _KEEP["frame"] = (scene.name, scene.frame_current)


@persistent
def _keep_frame_post(*_args):
    if "frame" in _KEEP and not bpy.app.timers.is_registered(restore_frame):
        bpy.app.timers.register(restore_frame, first_interval=0.0)


def restore_frame():
    """Put the frame from before the undo / redo back (None: timer done)."""
    name, frame = _KEEP.pop("frame", (None, None))
    scene = bpy.context.scene
    if scene is not None and scene.name == name and scene.frame_current != frame:
        scene.frame_current = frame
    return None


_UNDO_HANDLERS = (("undo_pre", _keep_frame_pre), ("redo_pre", _keep_frame_pre),
                  ("undo_post", _keep_frame_post), ("redo_post", _keep_frame_post))


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    for name, fn in _UNDO_HANDLERS:
        getattr(bpy.app.handlers, name).append(fn)
    wm = bpy.types.WindowManager
    wm.allset_time_range_on = bpy.props.BoolProperty(
        name="Time Range", description="A Shift-dragged Time Slider range is highlighted", options={'SKIP_SAVE'})
    wm.allset_time_range = bpy.props.IntVectorProperty(name="Time Range", size=2, options={'SKIP_SAVE'})
    _draw_handle.append(bpy.types.SpaceDopeSheetEditor.draw_handler_add(_draw_range, (), 'WINDOW', 'POST_PIXEL'))
    buttons, menus = header_classes()
    orig_menus, orig_header = menus.draw_collapsible, buttons.draw_header   # bound class methods
    _ORIGINAL["draw_header"] = buttons.__dict__["draw_header"]

    def _menus_5(cls, context, layout):
        # Timeline mode: the menus live in ALLSET_MT_anim_preferences (Maya has no menus in the Range Slider)
        if not _is_timeline(context):
            return orig_menus(context, layout)

    def _header_5(cls, context, layout):
        if _is_timeline(context):
            return draw_header(context, layout)
        return orig_header(context, layout)
    menus.draw_collapsible = classmethod(_menus_5)
    buttons.draw_header = classmethod(_header_5)
    _subscribe()
    bpy.app.handlers.load_post.append(_on_load)


def unregister():
    for name, fn in _UNDO_HANDLERS:
        if fn in getattr(bpy.app.handlers, name):
            getattr(bpy.app.handlers, name).remove(fn)
    if bpy.app.timers.is_registered(restore_frame):
        bpy.app.timers.unregister(restore_frame)
    _KEEP.clear()
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    bpy.msgbus.clear_by_owner(_OWNER)
    if bpy.app.timers.is_registered(_deferred_fit):
        bpy.app.timers.unregister(_deferred_fit)
    buttons, menus = header_classes()
    if "draw_header" in _ORIGINAL:
        orig = _ORIGINAL.pop("draw_header")
        buttons.draw_header = orig
    if "draw_collapsible" in menus.__dict__:
        del menus.draw_collapsible
    while _draw_handle:
        bpy.types.SpaceDopeSheetEditor.draw_handler_remove(_draw_handle.pop(), 'WINDOW')
    wm = bpy.types.WindowManager
    del wm.allset_time_range
    del wm.allset_time_range_on
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
