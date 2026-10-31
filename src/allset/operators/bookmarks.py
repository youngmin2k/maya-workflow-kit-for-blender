# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Time Slider bookmarks as Blender timeline markers.

Maya hotkeys: Alt+T makes a Time Slider bookmark from the selected range (a name dialog first), Alt+Shift+T makes
one at once, ' / ; go to the next / previous bookmark, Shift+| fits the playback range to the current bookmark,
Shift+" / Shift+: frame the next / previous one.

A Maya bookmark is a time range; a Blender marker is one frame. The kit bookmark = a marker at the range start; its
end is kept in the scene ID property ``allset_bookmarks`` {marker name: end frame} when the bookmark was made from a
selected Time Slider range (``WindowManager.allset_time_range``), else it ends one frame before the next
marker (or at the scene end).
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from .. import results
from .naming import next_number

ENDS = "allset_bookmarks"


def markers(scene):
    return sorted(scene.timeline_markers, key=lambda m: m.frame)


def next_name(scene):
    """``bookmark<N>`` one past the highest, gaps not filled like Maya's timeSliderBookmark nodes."""
    return f"bookmark{next_number('bookmark', {m.name for m in scene.timeline_markers})}"


def selected_range(context):
    """(start, end) of the Time Slider's Shift-drag range, or None (ui/time_slider)."""
    wm = context.window_manager
    if not getattr(wm, "allset_time_range_on", False):
        return None
    rng = getattr(wm, "allset_time_range", None)
    if rng is None:
        return None
    start, end = int(round(rng[0])), int(round(rng[1]))
    return (min(start, end), max(start, end))


def bookmark_range(scene, marker):
    """(start, end) frames of the bookmark ``marker``."""
    ends = scene.get(ENDS) or {}
    end = ends.get(marker.name)
    if end is None:
        later = [m.frame for m in scene.timeline_markers if m.frame > marker.frame]
        end = (min(later) - 1) if later else scene.frame_end
    return marker.frame, max(int(end), marker.frame)


def current(scene, frame=None):
    """The bookmark containing ``frame`` (the last marker at or before it), or None."""
    frame = scene.frame_current if frame is None else frame
    before = [m for m in markers(scene) if m.frame <= frame]
    return before[-1] if before else None


def create(context, name=""):
    scene = context.scene
    rng = selected_range(context)
    start = rng[0] if rng else scene.frame_current
    marker = scene.timeline_markers.new(name or next_name(scene), frame=start)
    if rng and rng[1] > rng[0]:
        ends = dict(scene.get(ENDS) or {})
        ends[marker.name] = rng[1]
        scene[ENDS] = ends
    return marker


def frame(scene, marker):
    """Playback range = the bookmark's range (Maya FrameTimeSliderBookmark)."""
    start, end = bookmark_range(scene, marker)
    scene.use_preview_range = True
    scene.frame_preview_start, scene.frame_preview_end = start, end
    return start, end


class ALLSET_OT_bookmark_create(bpy.types.Operator):
    """Create a Time Slider bookmark (a timeline marker) at the selected range or the current time"""
    bl_idname = "allset.bookmark_create"
    bl_label = "Create Bookmark"
    bl_options = {'UNDO'}

    name: StringProperty(name="Name", options={'SKIP_SAVE'})
    quick: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'}, description="No dialog (Maya Quick Create)")

    def invoke(self, context, event):
        if self.quick:
            return self.execute(context)
        self.name = next_name(context.scene)
        return context.window_manager.invoke_props_dialog(self, title="Create Bookmark", confirm_text="Create")

    def execute(self, context):
        marker = create(context, self.name.strip())
        results.result(self, f"Bookmark {marker.name} at frame {marker.frame}")
        return {'FINISHED'}


class ALLSET_OT_bookmark_frame(bpy.types.Operator):
    """Set the playback range to a Time Slider bookmark's range (this one, the next or the previous)"""
    bl_idname = "allset.bookmark_frame"
    bl_label = "Frame Bookmark"
    bl_options = {'UNDO'}

    which: EnumProperty(items=(("CURRENT", "Current", ""), ("NEXT", "Next", ""), ("PREVIOUS", "Previous", "")),
                        options={'SKIP_SAVE'})

    def execute(self, context):
        scene = context.scene
        ms = markers(scene)
        if not ms:
            self.report({'WARNING'}, "No bookmarks (timeline markers)")
            return {'CANCELLED'}
        cur = current(scene)
        if self.which == "CURRENT":
            target = cur
        elif self.which == "NEXT":
            target = next((m for m in ms if m.frame > scene.frame_current), None)
        else:
            before = [m for m in ms if cur is not None and m.frame < cur.frame]
            target = before[-1] if before else None
        if target is None:
            return {'CANCELLED'}
        start, _end = frame(scene, target)
        scene.frame_current = start
        return {'FINISHED'}


classes = (ALLSET_OT_bookmark_create, ALLSET_OT_bookmark_frame)
