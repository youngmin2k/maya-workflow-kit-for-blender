# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya X/C/V/J hold snapping and D tap-toggle / hold pivot editing.

research/maya/interaction.md §0 (press/release hotkeys), §4 (D hold /
Insert), §5 (X grid, C curve, V point); hotkeys_default.json j =
MoveRotateScaleToolToggleSnapMode press/release. Design and limits:
docs/steps/step_3.md 「계획」 1-4.

``begin``/``end`` are plain functions (headless-testable). The operator
``allset.hold`` wraps them in a modal that waits for the key's RELEASE.
A short, unused D press latches pivot editing until D / Insert is pressed again.
"""

import bpy
import time

from .. import live_refs
from . import keystate


class HoldGroup:
    """Tool settings that several holds share; saved once, restored once."""

    def capture(self, ts):
        raise NotImplementedError

    def apply(self, ts, names):
        raise NotImplementedError

    def restore(self, ts, state):
        raise NotImplementedError


class SnapGroup(HoldGroup):
    # Hold name -> Blender snap elements (step_3.md 「계획」 3).
    ELEMENTS = {"grid": {'GRID'}, "curve": {'EDGE'}, "point": {'VERTEX'}, "step": {'INCREMENT'}}

    def capture(self, ts):
        return (ts.use_snap, set(ts.snap_elements), ts.snap_target, ts.use_snap_translate, ts.use_snap_rotate,
                ts.use_snap_scale)

    def apply(self, ts, names):
        elements = set().union(*(self.ELEMENTS[n] for n in names))
        ts.snap_elements = elements
        ts.use_snap = True
        # a held snap key snaps whatever transform runs (#139: an Affect flag left off ignored X / V)
        ts.use_snap_translate = ts.use_snap_rotate = ts.use_snap_scale = True
        # Maya snaps the manipulator centre (the pivot / the component bbox centre), not the
        # object's closest point (research/maya/workflows/pivot_snap.md S2, S4, S5).
        ts.snap_target = 'CENTER'

    def restore(self, ts, state):
        use_snap, elements, target, *affect = state
        ts.snap_elements = elements
        ts.use_snap = use_snap
        ts.snap_target = target
        if affect:
            ts.use_snap_translate, ts.use_snap_rotate, ts.use_snap_scale = affect


class PivotGroup(HoldGroup):
    """D hold: transform affects only object origins (research/blender/api_limits.md §7) and
    not the children; ``pivot.watch`` rewrites each such transform the Maya way (channels
    stay, docs/steps/step_59.md 「계획」 1)."""

    def capture(self, ts):
        return (ts.use_transform_data_origin, ts.use_transform_skip_children)

    def apply(self, ts, names):
        set_pivot_mode(ts, True)

    def restore(self, ts, state):
        ts.use_transform_data_origin, ts.use_transform_skip_children = state


def set_pivot_mode(ts, on):
    ts.use_transform_data_origin = on
    ts.use_transform_skip_children = on
    if on:
        from . import pivot
        pivot.watch()


_object_toggle_saved = None
PIVOT_TAP_SECONDS = 0.3


def latch_object_pivot(ts):
    """Detach a short D press from its hold, keeping the original flags for D / Insert to restore."""
    global _object_toggle_saved
    state = _state.pop("pivot", None)
    if state is not None:
        _object_toggle_saved = state["saved"]


def toggle_object_pivot(ts):
    global _object_toggle_saved
    if ts.use_transform_data_origin:
        if _object_toggle_saved is not None:
            ts.use_transform_data_origin, ts.use_transform_skip_children = _object_toggle_saved
        else:
            set_pivot_mode(ts, False)
        _object_toggle_saved = None
    else:
        _object_toggle_saved = GROUPS["pivot"].capture(ts)
        set_pivot_mode(ts, True)
    _redraw()


class ComponentPivotGroup(HoldGroup):
    """D in mesh edit mode: the 3D cursor is the temporary or toggled pivot."""

    def capture(self, ts):
        return ts.transform_pivot_point

    def apply(self, ts, names):
        ts.transform_pivot_point = 'CURSOR'

    def restore(self, ts, state):
        ts.transform_pivot_point = state


class PreserveChildrenGroup(HoldGroup):
    """D hold on joints in Edit mode (step 243, #160): Maya moves the joint only, its children stay
    (``cmds.move(preserveChildPosition=True)``, research/maya/re/joint_rig_2026_joint_math.md §3). The picked joints are
    re-selected head-only while held."""

    def capture(self, ts):
        return preserve_children_set(None)

    def apply(self, ts, names):
        preserve_children_set(True)

    def restore(self, ts, state):
        preserve_children_set(state)


def preserve_children_set(value):
    """Set Maya Preserve Children (``None`` = only read it); re-shapes the picked joints. Returns the old value."""
    from . import joint_selection
    context = bpy.context
    ts = context.scene.tool_settings
    old = bool(ts.use_transform_skip_children)    # Blender's Preserve Children = Maya's (joint_edit.preserve_children)
    if value is not None and bool(value) != old:
        ts.use_transform_skip_children = bool(value)
        joint_selection.reshape(context, context.active_object, bool(value))
    return old


def component_pivot_after(saved, moved):
    """Pivot point after releasing D in edit mode: a pivot the user placed (cursor moved)
    stays, like Maya's custom component pivot (research/maya/interaction.md:127-129); a
    plain tap resets it (cursor pivot -> Maya's component manipulator at the bounding-box
    centre, research/maya/workflows/pivot_snap.md P11; otherwise the earlier setting)."""
    if moved:
        return 'CURSOR'
    return 'BOUNDING_BOX_CENTER' if saved == 'CURSOR' else saved


# --- component pivot edit: D hold and Insert toggle in mesh edit mode (docs/steps/step_77.md) ----------

CURSOR_TOOL = "builtin.cursor"
CURSOR_OP = "view3d.cursor3d"
# Maya Move tool snapPivotOri True (pivot_snap.md P13): a click on a component orients the pivot too =
# the cursor tool's "Geometry" orientation (axes along the clicked surface).
PIVOT_CURSOR_ORIENTATION = 'GEOM'
EDIT_MODE = 'EDIT_MESH'


def _active_tool(context):
    tool = context.workspace.tools.from_space_view3d_mode(EDIT_MODE, create=False)
    return tool.idname if tool is not None else None


def _set_cursor_orientation(context, value):
    """Set the edit-mode cursor tool's orientation option; returns the previous value (None if the cursor
    tool isn't the active edit-mode tool)."""
    try:
        tool = context.workspace.tools.from_space_view3d_mode(EDIT_MODE, create=False)
        if tool is None or tool.idname != CURSOR_TOOL:
            return None
        props = tool.operator_properties(CURSOR_OP)
        old = props.orientation
        props.orientation = value
        return old
    except (AttributeError, RuntimeError, TypeError):
        return None


def cursor_orientation(context):
    """The cursor tool orientation for the Maya Snap Pivot Orientation option (step 94; default on = GEOM)."""
    from .pivot_menu import option
    return PIVOT_CURSOR_ORIENTATION if option("SNAP_ORI", context) else 'NONE'


def apply_cursor_options(context):
    """Snap Pivot Orientation / Position -> the active cursor tool's orientation / surface projection (step 94)."""
    from .pivot_menu import option
    _set_cursor_orientation(context, cursor_orientation(context))
    try:
        tool = context.workspace.tools.from_space_view3d_mode(EDIT_MODE, create=False)
        if tool is not None and tool.idname == CURSOR_TOOL:
            tool.operator_properties(CURSOR_OP).use_depth = option("SNAP_POS", context)
    except (AttributeError, RuntimeError, TypeError):
        pass


def selection_signature(context):
    """Cheap edit-mode selection fingerprint: selected counts and the active element per edited mesh."""
    import bmesh
    sig = []
    for ob in getattr(context, "objects_in_mode", None) or ():
        if ob.type != 'MESH':
            continue
        me = ob.data
        try:
            act = bmesh.from_edit_mesh(me).select_history.active
            act = (type(act).__name__, act.index) if act is not None else None
        except (ValueError, ReferenceError):
            act = None
        sig.append((ob.name, me.total_vert_sel, me.total_edge_sel, me.total_face_sel, act))
    return tuple(sig)


def selection_center(context):
    """World centre of the bounding box of the selected vertices (Maya component manipulator, P11) or None."""
    import bmesh
    from mathutils import Vector
    lo = hi = None
    for ob in getattr(context, "objects_in_mode", None) or ():
        if ob.type != 'MESH':
            continue
        mw = ob.matrix_world
        for v in bmesh.from_edit_mesh(ob.data).verts:
            if v.select:
                p = mw @ v.co
                lo = p.copy() if lo is None else Vector(map(min, lo, p))
                hi = p.copy() if hi is None else Vector(map(max, hi, p))
    return None if lo is None else (lo + hi) / 2


def turned(before, after, eps=1e-5):
    """True when the 3D cursor rotation (3x3) changed: the user oriented the pivot."""
    return any(abs(before[i][j] - after[i][j]) > eps for i in range(3) for j in range(3))


class ComponentPivotEdit:
    """One edit-mode pivot edit: the 3D cursor is the pivot, the cursor tool places it (step 18), a
    changed cursor rotation becomes the "Maya Pivot" Move orientation (step 59 P8, now in edit mode)."""

    def __init__(self):
        self.on = False
        self.toggled = False          # started by Insert: stays on until Insert / D / leaving edit mode
        self.pending_tool = None      # tool to bring back on the next mesh edit mode entry
        self.custom = False           # a placed custom pivot is in use (pivot point CURSOR after finish)
        self.sel_sig = None           # the selection it was placed for (Pin Component Pivot off: reset on change)
        self.cursors = set()          # 3D views whose hidden cursor this edit shows (step 134)

    def start(self, context, toggled=False):
        ts = context.scene.tool_settings
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        cursor = context.scene.cursor
        self.area_ptr = live_refs.pointer(context.area)   # a pointer: the timer may run after its window closed (#36)
        self.tool = tool.idname if tool and tool.idname != CURSOR_TOOL else "builtin.select_box"
        self.pivot = ts.transform_pivot_point
        self.previous_cursor = cursor.matrix.copy()
        if self.pivot != 'CURSOR':
            centre = selection_center(context)
            if centre is not None:
                cursor.location = centre
        self.location = cursor.location.copy()
        self.rotation = cursor.matrix.to_3x3()
        self.select_mode = tuple(ts.mesh_select_mode)
        self.on, self.toggled, self.pending_tool = True, toggled, None
        ts.transform_pivot_point = 'CURSOR'
        ts.mesh_select_mode = (True, True, True)
        # the pivot is the 3D cursor: the Maya layout hides it (Maya has none, #59), show it while it is edited
        self.cursors |= show_cursors()
        _tool_set(context, CURSOR_TOOL, self.area_ptr)
        # tool options belong to the tool: set the orientation once the cursor tool is the active one
        self.orientation = _set_cursor_orientation(context, cursor_orientation(context))
        apply_cursor_options(context)
        self.custom = False
        _redraw()

    def finish(self, context):
        if not self.on:
            return
        self.on = self.toggled = False
        hide_cursors(self.cursors)
        self.cursors = set()
        ts = context.scene.tool_settings
        cursor = context.scene.cursor
        moved = (cursor.location - self.location).length > 1e-6
        rot = cursor.matrix.to_3x3()
        rotated = turned(self.rotation, rot)
        ts.mesh_select_mode = self.select_mode
        ts.transform_pivot_point = component_pivot_after(self.pivot, moved or rotated)
        self.custom = ts.transform_pivot_point == 'CURSOR'
        self.sel_sig = selection_signature(context) if self.custom else None
        if self.orientation is not None and _active_tool(context) == CURSOR_TOOL:
            _set_cursor_orientation(context, self.orientation)
        if rotated:
            from . import pivot
            pivot.set_custom_orientation(context, rot)
        if not moved and not rotated:
            cursor.matrix = self.previous_cursor
        if context.mode == EDIT_MODE:
            _tool_set(context, self.tool, self.area_ptr)
        else:
            self.pending_tool = self.tool     # a tool can only be set in its own mode
        _redraw()

    def reset(self, context, position=True, orientation=True):
        """Maya Reset Pivot (Position / Orientation) for components: the pivot back on the selection's bounding-box
        centre with world axes (Maya Reset pivot, research/maya/interaction.md:127)."""
        cursor = context.scene.cursor
        if position:
            centre = selection_center(context)
            if centre is not None:
                cursor.location = centre
        if orientation:
            cursor.rotation_mode = 'XYZ'
            cursor.rotation_euler = (0.0, 0.0, 0.0)
            from . import pivot
            pivot.leave_custom_orientation(context.scene)
        if self.on:                   # releasing D now = no custom pivot (the reset place counts as "not moved")
            if position:
                self.location = cursor.location.copy()
            if orientation:
                self.rotation = cursor.matrix.to_3x3()
        elif position and self.custom:
            context.scene.tool_settings.transform_pivot_point = 'BOUNDING_BOX_CENTER'
            self.custom, self.sel_sig = False, None
        _redraw()

    def tick(self, context):
        """Timer: close a toggled session that left edit mode; restore its tool when edit mode is back; drop an
        unpinned custom pivot when the selection changes (Maya Pin Component Pivot off, step 94)."""
        if self.on and context.mode != EDIT_MODE:
            self.finish(context)
        elif self.pending_tool and context.mode == EDIT_MODE:
            tool, self.pending_tool = self.pending_tool, None
            _tool_set(context, tool, 0)
        if self.custom and not self.on:
            from .pivot_menu import option
            ts = context.scene.tool_settings
            if context.mode != EDIT_MODE or ts.transform_pivot_point != 'CURSOR':
                self.custom, self.sel_sig = False, None
            elif not option("PIN", context) and selection_signature(context) != self.sel_sig:
                ts.transform_pivot_point = 'BOUNDING_BOX_CENTER'
                self.custom, self.sel_sig = False, None
                _redraw()


def _view3d_spaces(screens=None):
    for screen in bpy.data.screens if screens is None else screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    yield space


def show_cursors(screens=None):
    """Show the 3D cursor in every 3D View that hides it (the Maya layout views, step 134 #59); returns their space
    pointers for ``hide_cursors``. Spaces are looked up afresh from ``bpy.data.screens`` (default) every time: no
    reference is kept across a closed window (step 129 #36)."""
    shown = set()
    for space in _view3d_spaces(screens):
        if not space.overlay.show_cursor:
            space.overlay.show_cursor = True
            shown.add(space.as_pointer())
    return shown


def hide_cursors(pointers, screens=None):
    """Hide the cursor again in the views ``show_cursors`` showed (views that showed it before stay as they were)."""
    if not pointers:
        return
    for space in _view3d_spaces(screens):
        if space.as_pointer() in pointers:
            space.overlay.show_cursor = False


def _view3d_area(context):
    screen = getattr(context, "screen", None)
    areas = [a for a in screen.areas if a.type == 'VIEW_3D'] if screen is not None else []
    return max(areas, key=lambda a: a.width * a.height) if areas else None


def _tool_set(context, idname, area_ptr):
    area = live_refs.area(area_ptr)
    if area is None or area.type != 'VIEW_3D':
        area = _view3d_area(context)
    try:
        if area is not None:
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            with context.temp_override(area=area, region=region):
                bpy.ops.wm.tool_set_by_id(name=idname)
        else:
            bpy.ops.wm.tool_set_by_id(name=idname, space_type='VIEW_3D')
    except (RuntimeError, ReferenceError, TypeError):   # area gone or tool unavailable
        pass


COMPONENT = ComponentPivotEdit()
_TICK = 0.25


def _component_tick():
    try:
        COMPONENT.tick(bpy.context)
    except (AttributeError, ReferenceError, RuntimeError):
        pass
    return _TICK if (COMPONENT.on or COMPONENT.pending_tool or COMPONENT.custom) else None


def watch_component():
    if not bpy.app.timers.is_registered(_component_tick):
        bpy.app.timers.register(_component_tick, first_interval=_TICK)


def unregister_component():
    if bpy.app.timers.is_registered(_component_tick):
        bpy.app.timers.unregister(_component_tick)
    if COMPONENT.on:
        try:
            COMPONENT.finish(bpy.context)
        except (AttributeError, ReferenceError, RuntimeError):
            pass
    COMPONENT.on = COMPONENT.toggled = COMPONENT.custom = False
    COMPONENT.pending_tool = COMPONENT.sel_sig = None


GROUPS = {"snap": SnapGroup(), "pivot": PivotGroup(), "component_pivot": ComponentPivotGroup(),
          "preserve_children": PreserveChildrenGroup()}
HOLDS = {"grid": "snap", "curve": "snap", "point": "snap", "step": "snap", "pivot": "pivot",
         "component_pivot": "component_pivot", "preserve_children": "preserve_children"}

# group -> {"saved": state, "active": [hold names in press order]}
_state = {}


def active_holds():
    return {g: list(s["active"]) for g, s in _state.items()}


def begin(ts, name):
    """Start holding ``name``. Saves the group's state on its first hold."""
    group_name = HOLDS[name]
    group = GROUPS[group_name]
    st = _state.get(group_name)
    if st is None:
        st = _state[group_name] = {"saved": group.capture(ts), "active": []}
    if name not in st["active"]:
        st["active"].append(name)
    group.apply(ts, st["active"])
    _redraw()


def _redraw():
    """Status Line snap buttons and the manipulator show the held state at once (pivot_snap.md S6)."""
    wm = getattr(bpy.context, "window_manager", None)
    for window in wm.windows if wm is not None else ():
        for area in window.screen.areas:
            area.tag_redraw()


def end(ts, name):
    """Stop holding ``name``. Restores the saved state when the group empties."""
    group_name = HOLDS[name]
    st = _state.get(group_name)
    if st is None or name not in st["active"]:
        return
    st["active"].remove(name)
    group = GROUPS[group_name]
    if st["active"]:
        group.apply(ts, st["active"])
    else:
        group.restore(ts, st["saved"])
        del _state[group_name]
    _redraw()


def end_all(ts):
    """Restore everything (used on unregister)."""
    for group_name, st in list(_state.items()):
        GROUPS[group_name].restore(ts, st["saved"])
    _state.clear()
    unregister_component()


_HOLD_ITEMS = (
    ("grid", "Grid Snap", "Maya X: snap to grid while held"),
    ("curve", "Curve Snap", "Maya C: snap to curves/edges while held"),
    ("point", "Point Snap", "Maya V: snap to vertices while held"),
    ("step", "Step Snap", "Maya J: incremental snap while held"),
    ("pivot", "Pivot Edit", "Maya D: tap to toggle pivot editing, or hold temporarily"),
    ("component_pivot", "Component Pivot", "Maya D: tap to toggle component pivot editing, or hold temporarily"),
    ("preserve_children", "Preserve Children", "Maya D on joints: move the joint only, its children stay"),
)

class ALLSET_OT_hold(bpy.types.Operator):
    """Enable a Maya hold mode; tap D to toggle custom pivot editing"""
    bl_idname = "allset.hold"
    bl_label = "Maya Hold Key"
    bl_options = {'INTERNAL'}

    name: bpy.props.EnumProperty(items=_HOLD_ITEMS, name="Hold")

    _POLL_INTERVAL = 0.05

    def invoke(self, context, event):
        if event.value != 'PRESS':
            return {'CANCELLED'}
        self._key = event.type
        self._ts = context.scene.tool_settings
        self._pivot_tap = self.name in {"pivot", "component_pivot"}
        self._pressed_at = time.monotonic()
        self._used = False
        if self.name == "component_pivot":
            if COMPONENT.on:          # D while the Insert pivot edit is on: leave it (Maya D tap toggles [I])
                COMPONENT.finish(context)
                return {'FINISHED'}
            COMPONENT.start(context)
        elif self.name == "pivot" and self._ts.use_transform_data_origin:
            toggle_object_pivot(self._ts)
            return {'FINISHED'}
        else:
            begin(self._ts, self.name)
        self._timer = context.window_manager.event_timer_add(self._POLL_INTERVAL, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _finish(self, context):
        if self.name == "component_pivot":
            COMPONENT.finish(context)
        else:
            end(self._ts, self.name)
        context.window_manager.event_timer_remove(self._timer)
        return {'FINISHED'}

    def _latch(self, context):
        if self.name == "component_pivot":
            COMPONENT.toggled = True
            watch_component()
        else:
            latch_object_pivot(self._ts)
        context.window_manager.event_timer_remove(self._timer)
        _redraw()
        return {'FINISHED'}

    def modal(self, context, event):
        if event.type == self._key:
            if event.value == 'RELEASE':
                if (getattr(self, "_pivot_tap", False) and not self._used
                        and time.monotonic() - self._pressed_at < PIVOT_TAP_SECONDS):
                    return self._latch(context)
                return self._finish(context)
            if event.is_repeat:
                # Step 265 (Issue #178): the OS repeats a held key (~30 / s). A *handled* key event cancels the
                # pending LMB CLICK_DRAG (wm_event_system.cc 4.5 :3740-3749 "CLICK_DRAG: canceling (button event
                # was handled)"), so the manipulator's drag — gizmo_tweak is a CLICK_DRAG item — only started when
                # the mouse crossed the drag threshold before the next repeat: D + drag "sometimes" grabbed the
                # pivot. A repeat that nothing handles leaves the drag alone (a repeat never starts one either,
                # :3683, and kit hold items ignore repeats), so pass it on.
                return {'PASS_THROUGH'}
            return {'RUNNING_MODAL'}
        if event.type in {'LEFTMOUSE', 'MIDDLEMOUSE', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._used = True
        if event.type == 'TIMER' and keystate.is_down(self._key) is False:
            # RELEASE was consumed by another modal (e.g. a transform drag). Wait for that
            # transform to end: it writes its snap state back to the tool settings when it
            # finishes, which would undo a restore made during the drag (step 59).
            window = context.window
            if window is not None and any(op.bl_idname.startswith("TRANSFORM_OT_")
                                          for op in window.modal_operators):
                return {'PASS_THROUGH'}
            return self._finish(context)
        return {'PASS_THROUGH'}


class ALLSET_OT_pivot_toggle(bpy.types.Operator):
    """Toggle pivot edit mode (Maya Insert): objects = transform affects only origins; mesh edit mode =
    place the component pivot with the 3D cursor"""
    bl_idname = "allset.pivot_toggle"
    bl_label = "Toggle Pivot Edit"
    bl_options = {'REGISTER'}

    def execute(self, context):
        if context.mode == 'EDIT_ARMATURE':   # step 243: Insert on joints = Preserve Children on / off
            preserve_children_set(not preserve_children_set(None))
            _redraw()
            return {'FINISHED'}
        if context.mode == EDIT_MODE:     # Maya component mode Insert (step 77): the 3D cursor pivot edit
            if COMPONENT.on:
                COMPONENT.finish(context)
            else:
                COMPONENT.start(context, toggled=True)
                watch_component()
            return {'FINISHED'}
        ts = context.scene.tool_settings
        toggle_object_pivot(ts)
        return {'FINISHED'}


classes = (ALLSET_OT_hold, ALLSET_OT_pivot_toggle)


def unregister_cleanup():
    """Restore held states if the add-on is disabled mid-hold."""
    global _object_toggle_saved
    scene = getattr(bpy.context, "scene", None)
    if scene is not None and _state:
        end_all(scene.tool_settings)
    _state.clear()
    if scene is not None and _object_toggle_saved is not None:
        scene.tool_settings.use_transform_data_origin, scene.tool_settings.use_transform_skip_children = _object_toggle_saved
    _object_toggle_saved = None
    unregister_component()
