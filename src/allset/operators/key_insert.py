# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Insert Key (Alt+I, Ctrl+Shift+W/E/R), Nudge Keys (Shift+( / )) and Select Previous / Next Key (Ctrl+Alt+, / .).

Maya runtime commands:
InsertKeyTranslate / Rotate / Scale = ``cmds.setKeyframe(insert=True, attribute="translate" / ...)``, InsertKey =
Insert Key (curves with selected Graph Editor keys, else the Graph Editor's curves, else the selection's),
Nudge = ``cmds.keyframe(animation="keys", relative=True, option="over", timeChange=±1)``, SelectNext/PreviousKey
(from the last selected key: find the next / previous key, select only it, go there).

An insert keeps the curve's shape. Blender 4.5's ``keyframe_points.insert`` already subdivides a segment between two
auto-handle keys and keeps the handles auto (= Maya Auto tangents, which follow later edits); with
free / aligned handles it misses, so those segments are split
here (de Casteljau) with the touched handles pinned.
"""

import bpy
from bpy.props import EnumProperty, IntProperty

from .. import results
from .. import undo_steps
from . import time_keys

CHANNELS = {"TRANSLATE": ("location",),
            "ROTATE": ("rotation_euler", "rotation_quaternion", "rotation_axis_angle"),
            "SCALE": ("scale",)}
_PIN = {'AUTO': 'ALIGNED', 'AUTO_CLAMPED': 'ALIGNED', 'VECTOR': 'FREE'}
AUTO = {'AUTO', 'AUTO_CLAMPED'}
EPS = 1e-4


# --- shape-keeping insert ---------------------------------------------------------------------------

def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def bezier_x(p0, p1, p2, p3, t):
    s = 1.0 - t
    return s * s * s * p0[0] + 3 * s * s * t * p1[0] + 3 * s * t * t * p2[0] + t * t * t * p3[0]


def solve_t(p0, p1, p2, p3, x):
    """Bezier parameter whose x is ``x`` (x(t) is monotonic for a valid F-curve segment): bisection."""
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) * 0.5
        if bezier_x(p0, p1, p2, p3, mid) < x:
            lo = mid
        else:
            hi = mid
    return (lo + hi) * 0.5


def split(p0, p1, p2, p3, t):
    """de Casteljau: (left handle of p0's next ... ) -> (p01, p012, p0123, p123, p23)."""
    p01, p12, p23 = _lerp(p0, p1, t), _lerp(p1, p2, t), _lerp(p2, p3, t)
    p012, p123 = _lerp(p01, p12, t), _lerp(p12, p23, t)
    return p01, p012, _lerp(p012, p123, t), p123, p23


def _pin(kp):
    kp.handle_left_type = _PIN.get(kp.handle_left_type, kp.handle_left_type)
    kp.handle_right_type = _PIN.get(kp.handle_right_type, kp.handle_right_type)


def _at(fc, x):
    return next((kp for kp in fc.keyframe_points if abs(kp.co.x - x) < EPS), None)


def insert_keep_shape(fc, frame):
    """Insert a key at ``frame`` on its current curve value without changing the curve. Returns True if added."""
    pts = fc.keyframe_points
    if _at(fc, frame) is not None:
        return False
    value = fc.evaluate(frame)
    before = [kp for kp in pts if kp.co.x < frame]
    after = [kp for kp in pts if kp.co.x > frame]
    prev = max(before, key=lambda k: k.co.x) if before else None
    nxt = min(after, key=lambda k: k.co.x) if after else None
    if (prev is not None and nxt is not None and prev.interpolation == 'BEZIER'
            and prev.handle_right_type in AUTO and nxt.handle_left_type in AUTO
            and prev.handle_left_type in AUTO and nxt.handle_right_type in AUTO):
        pts.insert(frame, value)                          # Blender subdivides auto segments itself
        fc.update()
        return True
    for kp in (prev, nxt):
        if kp is not None:
            _pin(kp)
    plan = None
    if prev is not None and nxt is not None and prev.interpolation == 'BEZIER':
        p0, p1 = tuple(prev.co), tuple(prev.handle_right)
        p2, p3 = tuple(nxt.handle_left), tuple(nxt.co)
        p01, p012, mid, p123, p23 = split(p0, p1, p2, p3, solve_t(p0, p1, p2, p3, frame))
        value = mid[1]
        plan = (p01, p012, p123, p23)
    interp = (prev or nxt).interpolation if (prev or nxt) else 'BEZIER'
    ref = (prev.co.x if prev else None, nxt.co.x if nxt else None)
    pts.insert(frame, value, options={'FAST'})          # invalidates the old KeyframePoint references
    kp = _at(fc, frame)
    kp.interpolation = interp
    kp.handle_left_type = kp.handle_right_type = 'ALIGNED'
    if plan is not None:
        p01, p012, p123, p23 = plan
        prev, nxt = _at(fc, ref[0]), _at(fc, ref[1])
        prev.handle_right = p01
        nxt.handle_left = p23
        kp.handle_left, kp.handle_right = p012, p123
    else:
        # linear / constant segment or outside the keys: flat handles a third of the way to the neighbours
        dl = (frame - ref[0]) / 3.0 if ref[0] is not None else 1.0
        dr = (ref[1] - frame) / 3.0 if ref[1] is not None else 1.0
        kp.handle_left = (frame - dl, value)
        kp.handle_right = (frame + dr, value)
        if ref[0] is not None and ref[1] is None:            # past the last key: keep that key's right side flat
            last = _at(fc, ref[0])
            last.handle_right = (last.co.x + dl, last.co.y)
        if ref[1] is not None and ref[0] is None:            # before the first key
            first = _at(fc, ref[1])
            first.handle_left = (first.co.x - dr, first.co.y)
    fc.update()
    return True


# --- which curves -------------------------------------------------------------------------------------

def _graph(context):
    sp = getattr(context, "space_data", None)
    return sp is not None and sp.type == 'GRAPH_EDITOR'


def _key_editor(context):
    """Graph Editor or a Dope Sheet that isn't the Time Slider: keys are selected there."""
    sp = getattr(context, "space_data", None)
    if sp is None:
        return False
    return sp.type == 'GRAPH_EDITOR' or (sp.type == 'DOPESHEET_EDITOR' and sp.ui_mode != 'TIMELINE')


def channel_curves(node, channels):
    """The node's existing curves for Maya translate / rotate / scale (bones: their own pose.bones paths)."""
    pre = time_keys.prefix(node)
    props = CHANNELS[channels]
    out = []
    for fc in time_keys.node_fcurves(node):
        path = fc.data_path[len(pre) + 1:] if pre else fc.data_path
        if path in props:
            out.append(fc)
    return out


def node_curves(context):
    return [fc for node in time_keys.nodes(context) for fc in time_keys.node_fcurves(node)]


def insert_curves(context, channels):
    if channels != 'ALL':
        return [fc for node in time_keys.nodes(context) for fc in channel_curves(node, channels)]
    if _graph(context):
        editable = list(getattr(context, "editable_fcurves", None) or ())
        chosen = [fc for fc in editable if any(kp.select_control_point for kp in fc.keyframe_points)]
        return chosen or list(getattr(context, "visible_fcurves", None) or editable)
    return node_curves(context)


def insert_keys(context, channels='ALL'):
    frame = context.scene.frame_current
    curves = insert_curves(context, channels)
    added = sum(insert_keep_shape(fc, frame) for fc in curves if not fc.lock)
    return curves, added


# --- nudge --------------------------------------------------------------------------------------------

def _matches(x, xs):
    return any(abs(x - v) < EPS for v in xs)


def move_keys(fc, xs, dx):
    """Move the keys at frames ``xs`` by dx; other keys where they land are removed first (Maya -option over).
    Keys are found by frame: removing a point invalidates the references to the later ones."""
    dest = [x + dx for x in xs]
    clash = [kp.co.x for kp in fc.keyframe_points
             if not _matches(kp.co.x, xs) and any(abs(kp.co.x - d) < 0.5 for d in dest)]
    for cx in clash:
        fc.keyframe_points.remove(next(kp for kp in fc.keyframe_points if abs(kp.co.x - cx) < EPS))
    for kp in [kp for kp in fc.keyframe_points if _matches(kp.co.x, xs)]:
        time_keys._move(kp, dx)
    fc.update()


def nudge(context, dx):
    """Move the selected keys (Graph Editor / Dope Sheet), else the Channel Box nodes' Time Slider keys
    (Shift range or current frame; the range / frame moves with them). Returns the number of keys moved."""
    n = 0
    if _key_editor(context):
        for fc in getattr(context, "editable_fcurves", None) or ():
            xs = [kp.co.x for kp in fc.keyframe_points if kp.select_control_point]
            if xs:
                n += len(xs)
                move_keys(fc, xs, dx)
        return n
    a, b = time_keys.time_range(context)
    for node in time_keys.nodes(context):
        for fc, keys in time_keys.keys_in(node, a, b):
            n += len(keys)
            move_keys(fc, [kp.co.x for kp in keys], dx)
    if n:
        wm = context.window_manager
        if getattr(wm, "allset_time_range_on", False):
            r0, r1 = wm.allset_time_range
            wm.allset_time_range = (r0 + dx, r1 + dx)
        else:
            context.scene.frame_current = int(round(context.scene.frame_current + dx))
    return n


# --- select previous / next key -------------------------------------------------------------------------

def select_curves(context):
    if _key_editor(context):
        return list(getattr(context, "visible_fcurves", None) or getattr(context, "editable_fcurves", None) or ())
    return node_curves(context)


def neighbour_time(times, ref, direction):
    if direction == 'NEXT':
        later = [t for t in times if t > ref + EPS]
        return min(later) if later else None
    earlier = [t for t in times if t < ref - EPS]
    return max(earlier) if earlier else None


def select_key(context, direction):
    """Go to the next / previous key and select only it. Reference time = the selected keys in a Graph Editor /
    Dope Sheet (Maya: the last selected key), else the current frame: elsewhere the key selection isn't visible
    and Blender selects every key it inserts; Maya moves the time to the key it selects, so repeats agree."""
    curves = select_curves(context)
    sel = [kp.co.x for fc in curves for kp in fc.keyframe_points if kp.select_control_point]         if _key_editor(context) else []
    if sel:
        ref = max(sel) if direction == 'NEXT' else min(sel)
    else:
        ref = context.scene.frame_current
    t = neighbour_time([kp.co.x for fc in curves for kp in fc.keyframe_points], ref, direction)
    if t is None:
        return None
    for fc in curves:
        for kp in fc.keyframe_points:
            on = abs(kp.co.x - t) < EPS
            kp.select_control_point = kp.select_left_handle = kp.select_right_handle = on
    context.scene.frame_current = int(round(t))
    return t


# --- operators ----------------------------------------------------------------------------------------

def _redraw(context):
    for area in context.screen.areas if context.screen else ():
        area.tag_redraw()


INSERT_ITEMS = (("ALL", "Insert Key", "Insert a key on the selected curves without changing their shape (Maya Alt+I)"),
                ("TRANSLATE", "Insert Key on Translate", "Insert a key on the translate curves, keeping their shape "
                 "(Maya Ctrl+Shift+W)"),
                ("ROTATE", "Insert Key on Rotate", "Insert a key on the rotate curves, keeping their shape (Maya Ctrl+Shift+E)"),
                ("SCALE", "Insert Key on Scale", "Insert a key on the scale curves, keeping their shape (Maya Ctrl+Shift+R)"))


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_insert_key(bpy.types.Operator):
    """Insert a key at the current time on existing curves without changing their shape (Maya Insert Key)"""
    bl_idname = "allset.insert_key"
    bl_label = "Insert Key"
    bl_options = {'REGISTER', 'UNDO'}

    channels: EnumProperty(items=INSERT_ITEMS, name="Channels", options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        return next(d for k, _l, d in INSERT_ITEMS if k == props.channels)

    def execute(self, context):
        curves, added = insert_keys(context, self.channels)
        if not curves:
            self.report({'WARNING'}, "No animation curves to insert a key on")
            return {'CANCELLED'}
        results.result(self, f"Insert Key: {added} key(s)")
        _redraw(context)
        return {'FINISHED'}


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_nudge_keys(bpy.types.Operator):
    """Move the selected keys one frame (Graph Editor / Dope Sheet), else the selection's keys at the current time
    or in the Time Slider range (Maya Shift+( / Shift+))"""
    bl_idname = "allset.nudge_keys"
    bl_label = "Nudge Keys"
    bl_options = {'REGISTER', 'UNDO'}

    delta: IntProperty(name="Frames", default=1, options={'SKIP_SAVE'})

    def execute(self, context):
        if not nudge(context, self.delta):
            self.report({'WARNING'}, "No keys selected" if _key_editor(context) else "No keys at this time")
            return {'CANCELLED'}
        _redraw(context)
        return {'FINISHED'}


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_select_key(bpy.types.Operator):
    """Go to the next / previous key and select it (Maya Ctrl+Alt+. / Ctrl+Alt+,)"""
    bl_idname = "allset.select_key"
    bl_label = "Select Next / Previous Key"
    bl_options = {'REGISTER', 'UNDO'}

    direction: EnumProperty(items=(("NEXT", "Next", "Go to the next key and select it"),
                                   ("PREVIOUS", "Previous", "Go to the previous key and select it")),
                            name="Direction", options={'SKIP_SAVE'})

    def execute(self, context):
        if select_key(context, self.direction) is None:
            results.result(self, "No more keys")
            return {'CANCELLED'}
        _redraw(context)
        return {'FINISHED'}


classes = (ALLSET_OT_insert_key, ALLSET_OT_nudge_keys, ALLSET_OT_select_key)
