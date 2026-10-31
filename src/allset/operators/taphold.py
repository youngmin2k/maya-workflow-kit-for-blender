# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya "tap = action, hold + click = menu" keys.

Maya hold keys: on press Maya builds a marking menu on
LMB; if no menu was posted before release, the release runs the default
action (``a`` tap = FrameAll).

API (used by the marking-menu step): subclass ``TapHoldBinding``, then
``register_binding(MyBinding())``; bind ``allset.tap_hold`` with
``binding=<name>`` on the key's PRESS.
"""

import bpy

from . import keystate

_BINDINGS = {}


class TapHoldBinding:
    name = ""
    label = ""
    buttons = frozenset({'LEFTMOUSE'})      # mouse buttons whose press while held calls click()

    def tap(self, context):
        """Key released without a click while held."""

    def click(self, context, event):
        """A mouse button of ``buttons`` (LMB by default) pressed while the key is held.

        Return 'DRAG' to receive ``drag()`` for mouse moves and ``drag_end()``
        on that button's release (the release is consumed, not passed on).
        """

    def drag(self, context, event, start):
        """Mouse moved during a drag. ``start`` = (mouse_x, mouse_y) at click."""

    def drag_end(self, context):
        """LMB released after a drag."""

    def drag_cancel(self, context):
        """ESC / RMB during a drag: undo what the drag changed."""


def register_binding(binding):
    _BINDINGS[binding.name] = binding
    return binding


def unregister_binding(name):
    _BINDINGS.pop(name, None)


def get_binding(name):
    return _BINDINGS[name]


def binding_names():
    return sorted(_BINDINGS)


class ALLSET_OT_tap_hold(bpy.types.Operator):
    """Tap for the default action; hold and click for the menu (Maya)"""
    bl_idname = "allset.tap_hold"
    bl_label = "Maya Tap/Hold Key"
    bl_options = {'INTERNAL'}

    binding: bpy.props.StringProperty(name="Binding")

    _POLL_INTERVAL = 0.05

    def invoke(self, context, event):
        if self.binding not in _BINDINGS:
            return {'CANCELLED'}
        if event.value != 'PRESS':
            return {'PASS_THROUGH'}
        self._b = _BINDINGS[self.binding]
        self._key = event.type
        self._used = False
        self._key_released = False
        self._drag_start = None
        self._button = None
        self._timer = context.window_manager.event_timer_add(self._POLL_INTERVAL, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _finish(self, context, released_cleanly):
        context.window_manager.event_timer_remove(self._timer)
        if self._drag_start is not None:
            self._b.drag_end(context)
        elif released_cleanly and not self._used:
            self._b.tap(context)
        return {'FINISHED'}

    def modal(self, context, event):
        # Drag in progress (key may or may not still be held).
        if self._drag_start is not None:
            if event.type == 'MOUSEMOVE':
                self._b.drag(context, event, self._drag_start)
                return {'RUNNING_MODAL'}
            if event.type == self._button and event.value == 'RELEASE':
                self._b.drag_end(context)
                self._drag_start = None
                return self._finish(context, False) if self._key_released else {'RUNNING_MODAL'}
            if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
                self._b.drag_cancel(context)
                self._drag_start = None
                return self._finish(context, False) if self._key_released else {'RUNNING_MODAL'}

        if event.type == self._key:
            if event.value == 'RELEASE':
                if self._drag_start is None:
                    return self._finish(context, released_cleanly=True)
                self._key_released = True  # finish after the drag ends
                return {'RUNNING_MODAL'}
            return {'RUNNING_MODAL'}  # key repeat

        if event.type in self._b.buttons and event.value == 'PRESS' and self._drag_start is None:
            # MMB (soft select) is consumed here, so the 3D View orbit never starts (issue #1).
            self._used = True
            if self._b.click(context, event) == 'DRAG':
                self._drag_start = (event.mouse_x, event.mouse_y)
                self._button = event.type
            return {'RUNNING_MODAL'}

        if event.type == 'TIMER' and keystate.is_down(self._key) is False:
            if self._drag_start is None:
                # RELEASE swallowed elsewhere (e.g. by the menu we opened): no tap.
                return self._finish(context, released_cleanly=False)
        return {'PASS_THROUGH'}


# --- bindings of this step ----------------------------------------------------

# Default soft select radius 5.0 (Maya units). Blender's own default proportional_size is 1.0 BU.
MAYA_SOFT_RADIUS = 5.0
BLENDER_SOFT_RADIUS = 1.0


def maya_soft_radius(context):
    """Turning soft select on with Blender's untouched default radius: use the Maya-style one (x maya_unit)."""
    from . import units
    ts = context.scene.tool_settings
    if abs(ts.proportional_size - BLENDER_SOFT_RADIUS) < 1e-9:
        ts.proportional_size = MAYA_SOFT_RADIUS * units.maya_unit(context.scene)


def radius_from_drag(start_size, dx):
    """B + LMB / MMB drag: doubles the radius every 100 px to the right. Relative, so it feels
    the same at every radius."""
    return max(1e-4, start_size * 2.0 ** (dx / 100.0))


class SoftSelectBinding(TapHoldBinding):
    """B: tap toggles soft select, hold + LMB / MMB drag sets the radius.
    One Maya state for object and component mode (operators/soft_select.py, issue #15)."""
    name = "soft_select"
    label = "Soft Select"
    buttons = frozenset({'LEFTMOUSE', 'MIDDLEMOUSE'})

    def tap(self, context):
        from . import soft_select
        if soft_select.toggle(context):
            from ..ui import view_message
            # Maya's Soft Select message (only when it turns on, topCenter).
            view_message.show(context, "<hl>Soft Select</hl> is <hl>on</hl>. Tap <hl>b</hl> to turn it <hl>off</hl>.",
                              'TOP_CENTER')

    def click(self, context, event):
        from . import soft_select
        soft_select.pull(context.scene)
        self._was_on = soft_select.is_on()
        soft_select.set_on(True, context)
        ts = context.scene.tool_settings
        self._start_size = ts.proportional_size
        self._show(context, event, ts.proportional_size)
        return 'DRAG'

    def drag(self, context, event, start):
        ts = context.scene.tool_settings
        ts.proportional_size = radius_from_drag(self._start_size, event.mouse_x - start[0])
        self._show(context, event, ts.proportional_size)

    def drag_end(self, context):
        self._show(context, None, None)

    def drag_cancel(self, context):
        from . import soft_select
        context.scene.tool_settings.proportional_size = self._start_size
        soft_select.set_on(self._was_on)
        self._show(context, None, None)

    @staticmethod
    def _show(context, event, size):
        """Header text + the radius circle and Maya's 'Falloff Radius' value in the view (ui/soft_overlay.py)."""
        from . import units
        from ..ui import soft_overlay
        text = None if size is None else f"Falloff Radius: {size / units.maya_unit(context.scene):.3f}"
        area = context.area
        if area is not None:
            area.header_text_set(None if text is None else text + " (Maya units)")
        soft_overlay.radius_drag(context, event, text)


class SelectAllBinding(TapHoldBinding):
    """A: tap = frame all; hold + LMB = the Maya marking menu SELECT_ALL
    (delete history, freeze)."""
    name = "select_all"
    label = "Frame All / History Menu"

    def tap(self, context):
        from . import view   # Maya fit (fit factor 0.95, sidebar excluded)
        area, region = context.area, context.region
        if area is not None and area.type == 'VIEW_3D' and region is not None and region.type == 'WINDOW':
            view.frame_region(context, area, region, selected=False)
        else:
            bpy.ops.view3d.view_all(center=False)

    def click(self, context, event):
        # Opened on the LMB press like Q/W/E/R: dragging and releasing LMB picks.
        from ..marking import modal
        modal.open_menu("SELECT_ALL", 'LEFTMOUSE', (event.mouse_region_x, event.mouse_region_y))


def playback_range(scene):
    if scene.use_preview_range:
        return scene.frame_preview_start, scene.frame_preview_end
    return scene.frame_start, scene.frame_end


def frames_per_pixel(scene, width):
    """K drag speed: the editor's width spans the playback range once,
    never slower than 1 frame per 50 px."""
    a, b = playback_range(scene)
    return max((b - a + 1) / max(width, 1), 0.02)


def time_from_drag(start_frame, dx, fpp):
    return int(round(start_frame + dx * fpp))


class TimeDragBinding(TapHoldBinding):
    """K: hold + LMB drag anywhere = move the current time (Maya Time Dragger, TimeDraggerToolActivate).
    LMB is used up, so the selection
    stays; a tap does nothing."""
    name = "time_drag"
    label = "Time Dragger"

    def click(self, context, event):
        scene = context.scene
        self._start = scene.frame_current
        width = context.area.width if context.area is not None else context.window.width
        self._fpp = frames_per_pixel(scene, width)
        self._area = context.area
        self._header(scene.frame_current)
        return 'DRAG'

    def drag(self, context, event, start):
        frame = time_from_drag(self._start, event.mouse_x - start[0], self._fpp)
        if frame != context.scene.frame_current:
            context.scene.frame_current = frame
        self._header(frame)

    def drag_end(self, context):
        self._header(None)

    def drag_cancel(self, context):
        context.scene.frame_current = self._start
        self._header(None)

    def _header(self, frame):
        area = getattr(self, "_area", None)
        if area is not None:
            try:
                area.header_text_set(None if frame is None else f"Time: {frame}  (K + drag, Esc cancel)")
            except ReferenceError:
                self._area = None


classes = (ALLSET_OT_tap_hold,)
_STEP_BINDINGS = (SoftSelectBinding, SelectAllBinding, TimeDragBinding)


def register_bindings():
    for cls in _STEP_BINDINGS:
        register_binding(cls())


def unregister_bindings():
    for cls in _STEP_BINDINGS:
        unregister_binding(cls.name)
