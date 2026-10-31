# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya top bar (menu bar) and Status Line.

Maya's menu bar and Status Line groups;
$S\\startup\\bl_ui\\space_topbar.py:14-62.

``TOPBAR_HT_upper_bar.draw_left`` / ``draw_right`` are swapped for Maya
versions while the add-on is enabled and put back on unregister; the
originals still run when the "Maya Menu Bar" preference is off. Maya has the
Status Line on its own row under the menus; one TOPBAR row can't hold both
(at 1600 px), so the Status Line is
drawn first in the tool header of the largest 3D View.
"""

import bpy
from bpy.props import EnumProperty, StringProperty

from . import draw_safe, input_line, menu_sets, own_draw, status_icons

# --- 3D View helpers ----------------------------------------------------------------

def main_view3d(screen=None):
    """(area, WINDOW region) of the largest 3D View in ``screen`` (or the active screen)."""
    screen = screen or bpy.context.screen
    best = None
    for area in (screen.areas if screen else ()):
        if area.type == 'VIEW_3D' and (best is None or area.width * area.height > best.width * best.height):
            best = area
    if best is None:
        return None, None
    return best, next((r for r in best.regions if r.type == 'WINDOW'), None)


def view3d_space(context):
    """The 3D View a Maya Display item reads and sets: the one the menu is drawn in, else the largest of
    the screen (the main menu bar is in the top bar), else the largest of the first window that has one (a kit
    window such as Normals Size has none of its own). Maya keeps polygon display on the meshes; Blender keeps it on
    each 3D View's overlays. None without a 3D View."""
    space = getattr(context, "space_data", None)
    if space is not None and space.type == 'VIEW_3D':
        return space
    area, _region = main_view3d(getattr(context, "screen", None))
    wm = getattr(context, "window_manager", None)
    for window in (wm.windows if wm is not None and area is None else ()):
        area, _region = main_view3d(window.screen)
        if area is not None:
            break
    return area.spaces.active if area is not None else None


def all_view3d_spaces():
    """Every 3D View space in every screen (Maya selection masks are global)."""
    for screen in bpy.data.screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    yield space


# --- selection masks -------------------------------------------

# Maya object mask -> Blender SpaceView3D.show_object_select_<type>; None = no equivalent.
OBJECT_MASKS = (
    ("HANDLES", "Select by handle object type", 'RESTRICT_SELECT_OFF', None),
    ("JOINTS", "Select by joint object type (armatures)", 'OUTLINER_OB_ARMATURE', ("armature",)),
    ("CURVES", "Select by curve object type", 'OUTLINER_OB_CURVE', ("curve", "font", "curves")),
    ("SURFACES", "Select by surface object type (meshes, NURBS)", 'OUTLINER_OB_MESH',
     ("mesh", "surf", "meta", "pointcloud", "volume")),
    ("DEFORMERS", "Select by deformation object type (lattices)", 'OUTLINER_OB_LATTICE', ("lattice",)),
    ("DYNAMICS", "Select by dynamic object type", 'OUTLINER_OB_FORCE_FIELD', None),
    ("RENDERING", "Select by rendering object type (cameras, lights)", 'OUTLINER_OB_LIGHT',
     ("camera", "light")),
    ("MISC", "Select by miscellaneous object type (locators, empties)", 'OUTLINER_OB_EMPTY',
     ("empty", "speaker", "light_probe", "grease_pencil")),
)
_MASK_TYPES = {m[0]: m[3] for m in OBJECT_MASKS}


def mask_on(space, group):
    return all(getattr(space, f"show_object_select_{t}") for t in _MASK_TYPES[group])


def set_mask(group, value):
    for space in all_view3d_spaces():
        for t in _MASK_TYPES[group]:
            setattr(space, f"show_object_select_{t}", value)


class ALLSET_OT_select_mask(bpy.types.Operator):
    """Toggle whether this kind of object can be selected (all 3D Views)"""
    bl_idname = "allset.select_mask"
    bl_label = "Selection Mask"
    bl_options = {'INTERNAL'}

    group: EnumProperty(items=[(m[0], m[0].title(), m[1]) for m in OBJECT_MASKS if m[3]])

    @classmethod
    def description(cls, context, props):
        return next(m[1] for m in OBJECT_MASKS if m[0] == props.group)

    def execute(self, context):
        area, _r = main_view3d(context.screen)
        spaces = [area.spaces.active] if area else list(all_view3d_spaces())[:1]
        if not spaces:
            return {'CANCELLED'}
        set_mask(self.group, not mask_on(spaces[0], self.group))
        return {'FINISHED'}



# Maya keeps its selection masks across File > New / Open (they are session state,
# step 93). Blender keeps the object select filters in each file's screens and the mesh
# select mode in its scene, so a load would replace them: remember them before the load and put them back after.
MASK_FLAGS = tuple(sorted({t for m in OBJECT_MASKS if m[3] for t in m[3]}))
_carried = {}


def session_masks(context=None):
    """The current masks: {type: selectable} of the main 3D View and the mesh select mode (or None)."""
    context = context or bpy.context
    area, _r = main_view3d(context.screen) if context.screen else (None, None)
    space = area.spaces.active if area else next(iter(all_view3d_spaces()), None)
    scene = context.scene
    if space is None and scene is None:
        return None
    return {"objects": {t: getattr(space, f"show_object_select_{t}") for t in MASK_FLAGS} if space else None,
            "mesh": tuple(scene.tool_settings.mesh_select_mode) if scene else None}


def apply_masks(masks):
    if not masks:
        return
    if masks["objects"]:
        for space in all_view3d_spaces():
            for t, value in masks["objects"].items():
                setattr(space, f"show_object_select_{t}", value)
    if masks["mesh"]:
        for scene in bpy.data.scenes:
            scene.tool_settings.mesh_select_mode = masks["mesh"]


@bpy.app.handlers.persistent
def _masks_before_load(*_args):
    try:
        _carried["masks"] = session_masks()
    except (AttributeError, ReferenceError):
        _carried.pop("masks", None)


@bpy.app.handlers.persistent
def _masks_after_load(*_args):
    apply_masks(_carried.pop("masks", None))

# --- selection mode -----------------------------------------------

class ALLSET_OT_select_mode(bpy.types.Operator):
    """Maya selection mode: Object (object mode) or Component (edit mode)"""
    bl_idname = "allset.select_mode"
    bl_label = "Selection Mode"
    bl_options = {'UNDO'}

    mode: EnumProperty(items=(("OBJECT", "Object", "Select by object type (object mode)"),
                              ("COMPONENT", "Component", "Select by component type (edit mode)")))

    @classmethod
    def description(cls, context, props):
        return {"OBJECT": "Select by object type (Object Mode)",
                "COMPONENT": "Select by component type (Edit Mode)"}[props.mode]

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        target = 'OBJECT' if self.mode == "OBJECT" else 'EDIT'
        if context.active_object.mode != target:
            from ..operators import maya_errors
            if target == 'EDIT' and maya_errors.refuse_hidden(self, context.active_object):     # #187
                return {'CANCELLED'}
            bpy.ops.object.mode_set(mode=target)
        return {'FINISHED'}


# --- snapping (hold keys share these settings: operators/hold.py) ----

SNAPS = (
    ("GRID", "Snap to grids (hold X)", 'SNAP_GRID', {'GRID'}),
    ("CURVE", "Snap to curves (hold C)", 'SNAP_EDGE', {'EDGE'}),
    ("POINT", "Snap to points (hold V)", 'SNAP_VERTEX', {'VERTEX'}),
    ("PROJECTED", "Snap to projected center", 'PIVOT_MEDIAN', None),
    ("PLANE", "Snap to view planes", 'VIEW_PERSPECTIVE', None),
    ("LIVE", "Snap to the surface under the cursor (Make Live)", 'SNAP_FACE', {'FACE_PROJECT'}),
)
_SNAP_ELEMENTS = {s[0]: s[3] for s in SNAPS}


def snap_on(ts, name):
    elements = _SNAP_ELEMENTS[name]
    return elements is not None and ts.use_snap and elements <= set(ts.snap_elements)


def toggle_snap(ts, name):
    """Status Line snap button: add/remove its element; snapping off when none is left."""
    current = set(ts.snap_elements) if ts.use_snap else set()
    elements = _SNAP_ELEMENTS[name]
    new = current - elements if snap_on(ts, name) else current | elements
    if new:
        ts.snap_elements = new
        ts.use_snap = True
        # Maya snaps the Move tool whenever a snap button is on: an Affect flag left off (Step Snap Off before
        # step 220, or a file saved that way) would make the button look on while nothing snaps (#139)
        from ..operators import snap_align
        snap_align.settle_affect(ts)
    else:
        ts.use_snap = False


class ALLSET_OT_snap_toggle(bpy.types.Operator):
    """Toggle a Maya snap mode"""
    bl_idname = "allset.snap_toggle"
    bl_label = "Snap Toggle"
    # Maya's snap toggles are not undoable (snapMode pushes no undo step):
    # no undo step here, and undo / redo keep the current snap state (``_keep_snap_pre`` / ``_keep_snap_post``)
    bl_options = {'INTERNAL'}

    snap: EnumProperty(items=[(s[0], s[0].title(), s[1]) for s in SNAPS if s[3]])

    @classmethod
    def description(cls, context, props):
        return next(s[1] for s in SNAPS if s[0] == props.snap)

    def execute(self, context):
        toggle_snap(context.scene.tool_settings, self.snap)
        return {'FINISHED'}


# Blender's memfile undo restores the scene's tool settings with everything else, so an undo after a snap toggle
# would switch the snap back (step 258, Issue #155). The state from before the undo / redo is put back from a 0 s
# timer like the current frame (ui/time_slider.py ``restore_frame``).
_KEEP_SNAP = {}


@bpy.app.handlers.persistent
def _keep_snap_pre(*_args):
    scene = bpy.context.scene
    if scene is not None:
        ts = scene.tool_settings
        _KEEP_SNAP["state"] = (scene.name, ts.use_snap, set(ts.snap_elements))


@bpy.app.handlers.persistent
def _keep_snap_post(*_args):
    if "state" in _KEEP_SNAP and not bpy.app.timers.is_registered(restore_snap):
        bpy.app.timers.register(restore_snap, first_interval=0.0)


def restore_snap():
    """Put the Status Line snap state from before the undo / redo back (None: timer done)."""
    name, on, elements = _KEEP_SNAP.pop("state", (None, None, None))
    scene = bpy.context.scene
    if scene is None or scene.name != name:
        return None
    ts = scene.tool_settings
    if elements and set(ts.snap_elements) != elements:
        ts.snap_elements = elements
    if ts.use_snap != on:
        ts.use_snap = on
    return None


_SNAP_UNDO_HANDLERS = (("undo_pre", _keep_snap_pre), ("redo_pre", _keep_snap_pre),
                       ("undo_post", _keep_snap_post), ("redo_post", _keep_snap_post))


# --- symmetry (operators/symmetry.py) ------

class ALLSET_MT_symmetry(bpy.types.Menu):
    """Maya symmetry modes (Status Line ▾ list)"""
    bl_idname = "ALLSET_MT_symmetry"
    bl_label = "Symmetry"

    def draw(self, context):
        from ..operators import symmetry
        current = symmetry.mode_of(symmetry.state(context.scene))
        layout = self.layout
        for mode, text in symmetry.MODES:
            draw_safe.op(layout, "allset.symmetry", text=text,
                         icon='RADIOBUT_ON' if mode == current else 'RADIOBUT_OFF').mode = mode


def draw_symmetry(layout, context):
    """▾ list with the mode text + a toggle that is blue (pressed) while symmetry is on.

    Maya: LMB ▾ = list, MMB = toggle, the text box turns blue when on (Maya 2022
    Status Line). A Blender menu button has no MMB action, so the toggle is its own button.
    """
    from ..operators import symmetry
    sym = symmetry.state(context.scene)
    row = layout.row(align=True)
    draw_safe.op(row, "allset.symmetry", text="", icon='MOD_MIRROR', depress=sym.on).mode = "TOGGLE"
    sub = row.row(align=True)
    sub.ui_units_x = 6
    sub.menu(ALLSET_MT_symmetry.bl_idname, text=symmetry.label(sym), icon='DOWNARROW_HLT')


TRANSFORM_TOOLS = ("builtin.move", "builtin.rotate", "builtin.scale", "builtin.transform",
                   "builtin.select", "builtin.select_box", "builtin.select_circle", "builtin.select_lasso")


def draw_tool_symmetry(self, context):
    """Maya Move/Rotate/Scale Tool Settings "Symmetry Settings" (edit mesh only)."""
    if context.mode != 'EDIT_MESH':
        return
    tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
    if tool is None or tool.idname not in TRANSFORM_TOOLS:
        return
    layout = self.layout
    layout.separator()
    layout.label(text="Symmetry Settings")
    draw_symmetry(layout, context)


# --- render -----------------------------------------------------------

def _properties_area(screen):
    """A Properties editor of ``screen`` that is not the Tool Settings dock (step 106)."""
    from . import maya_dock, tool_dock
    return next((a for a in (screen.areas if screen else ())
                 if a.type == 'PROPERTIES' and not tool_dock.is_dock(a) and maya_dock.role(a) is None), None)


def show_properties(screen, context_name):
    """Switch a Properties editor to a tab; False if the screen has none."""
    area = _properties_area(screen)
    if area is None:
        return False
    try:
        area.spaces.active.context = context_name
    except TypeError:  # tab not available (no active object etc.)
        return False
    return True


class ALLSET_OT_render_settings(bpy.types.Operator):
    """Open the render settings (Maya Render Settings window)"""
    bl_idname = "allset.render_settings"
    bl_label = "Render Settings"

    def execute(self, context):
        # Maya's Render Settings is a window of its own: a new Properties window on the
        # Render tab, so a Properties editor used as the Attribute Editor keeps its tab
        # (step 67). Without a window (background) switch a
        # Properties editor of the screen instead.
        # Step 105: the kit's Render Settings window (ui/render_settings.py: Maya menus, Render Layer / Render Using,
        # Common | renderer tabs over a Properties editor on the Render tab).
        if context.window is not None:
            from . import render_settings, window_places
            if render_settings.open_window(context) is not None or window_places.deferred():
                return {'FINISHED'}
        return {'FINISHED'} if show_properties(context.screen, 'RENDER') else {'CANCELLED'}


class ALLSET_OT_ipr_toggle(bpy.types.Operator):
    """IPR: interactive render in the main viewport (toggle Rendered shading)"""
    bl_idname = "allset.ipr_toggle"
    bl_label = "IPR Render"

    def execute(self, context):
        area, _r = main_view3d(context.screen)
        if area is None:
            return {'CANCELLED'}
        ipr_toggle(area.spaces.active)
        return {'FINISHED'}


def ipr_toggle(space):
    """IPR on = Rendered shading; off = the shading the view had before (Wireframe stays Wireframe, #24)."""
    from . import panel_menus
    if space.shading.type == 'RENDERED':
        panel_menus.leave_rendered(space)
    else:
        panel_menus.enter_rendered(space)


# --- editor toggles -----------------------------------------------

EDITORS = (
    # Maya order: Modeling Toolkit first (step 63)
    ("MODELING_TOOLKIT", "Show or hide the Modeling Toolkit", 'EDITMODE_HLT'),
    ("ATTRIBUTE", "Show or hide the Attribute Editor", 'PROPERTIES'),
    ("TOOL_SETTINGS", "Show or hide the Tool Settings of the active tool (dock left of the viewport)", 'TOOL_SETTINGS'),
    ("CHANNEL_BOX", "Show or hide the Channel Box / Layer Editor", 'MENU_PANEL'),
)
# Status Line toggle -> Maya panel of the tab stack (ui/maya_dock.py, step 116)
DOCK_KINDS = {"MODELING_TOOLKIT": 'MODELING_TOOLKIT', "ATTRIBUTE": 'ATTRIBUTE_EDITOR', "CHANNEL_BOX": 'CHANNEL_BOX'}


def editor_shown(screen, editor):
    if editor == "TOOL_SETTINGS":    # the dock left of the viewport (ui/tool_dock.py, step 106)
        from . import tool_dock
        return tool_dock.shown(screen)
    from . import maya_dock
    return maya_dock.kind_visible(bpy.context.window_manager, DOCK_KINDS[editor])


class ALLSET_OT_editor_toggle(bpy.types.Operator):
    """Show or hide a Maya editor"""
    bl_idname = "allset.editor_toggle"
    bl_label = "Toggle Editor"
    bl_options = {'INTERNAL'}

    editor: EnumProperty(items=[(e[0], e[0].title(), e[1]) for e in EDITORS])
    show: bpy.props.BoolProperty(options={'SKIP_SAVE'},
                                 description="Only show the editor (Maya toolPropertyWindow), never hide it")

    @classmethod
    def description(cls, context, props):
        return next(e[1] for e in EDITORS if e[0] == props.editor)

    def execute(self, context):
        if self.editor == "TOOL_SETTINGS":
            # Maya ToggleToolSettings: the dock left of the viewport (ui/tool_dock.py, step 106)
            from . import tool_dock
            tool_dock.toggle(context, show_only=self.show)
            return {'FINISHED'}
        # Maya Windows > UI Elements toggles: a panel tabbed behind another is raised,
        # a shown one hidden (ui/maya_dock.py, step 116)
        from . import maya_dock
        maya_dock.toggle(context, DOCK_KINDS[self.editor], show_only=self.show)
        return {'FINISHED'}


# --- drawing --------------------------------------------------------------------

# Maya Status Line groups each start with a collapse handle that hides the group.
# Kept for the
# session only (Maya keeps them in its preferences).
GROUPS = (
    ("FILE", "File: New, Open, Save, Undo, Redo"),
    ("SELECT_MODE", "Selection mode: hierarchy, object, component"),
    ("MASKS", "Selection masks"),
    ("SNAP", "Snap toggles"),
    ("SYMMETRY", "Symmetry"),
    ("HISTORY", "Construction History"),
    ("RENDER", "Render"),
    ("INPUT", "Input line: absolute / relative transform, rename, select by name"),
    ("EDITORS", "Editor toggles"),
)
# Groups Maya 2022 shows collapsed on a factory Status Line (only the bar
# and arrow between selection modes and snaps, after symmetry and after render; step 113).
DEFAULT_COLLAPSED = ("MASKS", "HISTORY", "INPUT")
_collapsed = set(DEFAULT_COLLAPSED)


class ALLSET_OT_status_group(bpy.types.Operator):
    """Show or hide this Status Line group (Maya collapse handle)"""
    bl_idname = "allset.status_group"
    bl_label = "Status Line Group"
    bl_options = {'INTERNAL'}

    group: EnumProperty(items=[(g, g.replace("_", " ").title(), d) for g, d in GROUPS])

    @classmethod
    def description(cls, context, props):
        desc = next(d for g, d in GROUPS if g == props.group)
        return f"{'Show' if props.group in _collapsed else 'Hide'}: {desc}"

    def execute(self, context):
        _collapsed.symmetric_difference_update({self.group})
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        return {'FINISHED'}


# Maya Status Line icons are 20 px on a 23 px pitch; a Blender
# header button draws its icon at 16 px x UI scale unless the button is scaled.
ICON_SCALE = 1.0


def _flat(layout, op, name, depress=False, text=""):
    """A Maya Status Line button: a kit-drawn glyph without a frame; a pressed button gets the frame (Maya's blue
    square behind an active toggle)."""
    sub = layout.row(align=True)
    sub.scale_x = sub.scale_y = ICON_SCALE
    if not depress:
        sub.emboss = 'NONE'
    return draw_safe.op(sub, op, text=text, icon_value=status_icons.icon(name), depress=depress)


def _grey(layout, name, item):
    _flat(layout, menu_sets.ALLSET_OT_menu_unavailable.bl_idname, name).item = item


def _group(layout, group):
    """Maya group start: the bar, then the filled arrow when the group is collapsed. True when its buttons should be
    drawn (``_group_end`` then adds the open collapse arrow)."""
    bar = layout.row(align=True)
    bar.ui_units_x = 0.5
    bar.label(text="", icon_value=status_icons.icon("bar"))
    if group in _collapsed:
        sub = layout.row(align=True)
        sub.ui_units_x = 0.6
        sub.emboss = 'NONE'
        draw_safe.op(sub, ALLSET_OT_status_group.bl_idname, text="", icon_value=status_icons.icon("closed")).group = group
        return False
    return True


def _group_end(layout, group):
    sub = layout.row(align=True)
    sub.ui_units_x = 0.6
    sub.emboss = 'NONE'
    draw_safe.op(sub, ALLSET_OT_status_group.bl_idname, text="", icon_value=status_icons.icon("open")).group = group


def _field(layout, owner, prop, units):
    sub = layout.row(align=True)
    sub.ui_units_x = units
    sub.prop(owner, prop, text="")


def draw_status_line(layout, context, compact=False):
    """The Maya Status Line, left to right (Maya 2022:
    menu set combo, then groups of bar + buttons + collapse arrow, sidebar toggles at the right end). ``compact``
    (the 3D View tool header of other layouts, which overflows): the input line goes after the editor toggles
    (step 75)."""
    from .. import preferences
    screen = context.screen
    ts = context.scene.tool_settings
    area, _r = main_view3d(screen)
    space = area.spaces.active if area else None

    sub = layout.row(align=True)
    sub.ui_units_x = 5                       # 100 px combo
    sub.prop(preferences.get(context), "menu_set", text="")

    if _group(layout, "FILE"):
        row = layout.row(align=True)
        _flat(row, "allset.new_maya_scene", "new")       # new scene in the Maya layout (step 130)
        _flat(row, "allset.open_scene", "open_scene")      # project scenes folder (step 69)
        _flat(row, "allset.save_scene", "save")
        _flat(row, "ed.undo", "undo")
        _flat(row, "ed.redo", "redo")
        _group_end(layout, "FILE")

    if _group(layout, "SELECT_MODE"):
        editing = context.mode != 'OBJECT' and context.mode.startswith('EDIT')
        row = layout.row(align=True)
        _grey(row, "sel_hierarchy", "Status Line/Select by hierarchy")
        _flat(row, ALLSET_OT_select_mode.bl_idname, "sel_object", depress=not editing).mode = "OBJECT"
        _flat(row, ALLSET_OT_select_mode.bl_idname, "sel_component", depress=editing).mode = "COMPONENT"
        _group_end(layout, "SELECT_MODE")

    if _group(layout, "MASKS"):
        row = layout.row(align=True)
        if context.mode == 'EDIT_MESH':
            for i, name in enumerate(("vertex", "edge", "face")):
                sub = row.row(align=True)
                if not ts.mesh_select_mode[i]:
                    sub.emboss = 'NONE'
                sub.prop(ts, "mesh_select_mode", index=i, text="", icon_value=status_icons.icon(name))
        else:
            for group, desc, _icon, types in OBJECT_MASKS:
                if types is None:
                    _grey(row, "mask_" + group, f"Status Line/{desc}")
                else:
                    _flat(row, ALLSET_OT_select_mask.bl_idname, "mask_" + group,
                          depress=bool(space) and mask_on(space, group)).group = group
        _group_end(layout, "MASKS")

    if _group(layout, "SNAP"):
        row = layout.row(align=True)
        for name, desc, _icon, elements in SNAPS:
            if name == 'LIVE':
                from ..operators import live
                _flat(row, 'allset.make_live', 'snap_LIVE', depress=bool(live.objects(context.scene))).toggle = True
            elif elements is None:
                _grey(row, "snap_" + name, f"Status Line/{desc}")
            else:
                _flat(row, ALLSET_OT_snap_toggle.bl_idname, "snap_" + name, depress=snap_on(ts, name)).snap = name
        # Maya's live surface field (step 59): arrow + text field
        row = layout.row(align=True)
        sub = row.row(align=True)
        sub.emboss = 'NONE'
        from ..operators import live
        draw_safe.op(sub, "allset.live_history", text="", icon='DOWNARROW_HLT')
        field = row.row(align=True)
        field.ui_units_x = 6
        draw_safe.op(field, 'allset.live_history', text=live.text(context.scene))
        _group_end(layout, "SNAP")

    if _group(layout, "SYMMETRY"):
        row = layout.row(align=True)
        sub = row.row(align=True)
        sub.emboss = 'NONE'
        sub.menu(ALLSET_MT_symmetry.bl_idname, text="", icon='DOWNARROW_HLT')
        # Maya's symmetry box is a drop-down (Maya 2022 Status Line): a click on the text opens the list, it is
        # never a text field (step 258, Issue #155: the read-only text property took a text cursor)
        box = row.row(align=True)
        box.ui_units_x = 5
        box.menu(ALLSET_MT_symmetry.bl_idname, text=_symmetry_text(None))
        _group_end(layout, "SYMMETRY")

    if _group(layout, "HISTORY"):   # Maya Status Line; toggle since step 189 (input_line.draw_history)
        _flat(layout, input_line.ALLSET_OT_construction_history.bl_idname, "history",
              depress=context.window_manager.allset_construction_history)
        _group_end(layout, "HISTORY")

    if _group(layout, "RENDER"):
        row = layout.row(align=True)
        _flat(row, "render.view_show", "render_view")
        _flat(row, "render.render", "render")
        _flat(row, ALLSET_OT_ipr_toggle.bl_idname, "ipr", depress=bool(space) and space.shading.type == 'RENDERED')
        _flat(row, ALLSET_OT_render_settings.bl_idname, "render_settings")
        _flat(row, "allset.hypershade", "hypershade")       # ui/hypershade.py (step 67)
        _grey(row, "render_setup", "Status Line/Render Setup")
        _flat(row, "allset.light_editor", "light_editor")   # ui/light_editor.py (step 67)
        _grey(row, "pause", "Status Line/Pause Viewport 2.0")
        _group_end(layout, "RENDER")

    if not compact and _group(layout, "INPUT"):     # Maya Status Line input field (step 75)
        input_line.draw(layout, context)
        _group_end(layout, "INPUT")

    if not compact:
        layout.separator_spacer()            # Maya: the sidebar toggles sit at the right end
    row = layout.row(align=True)
    for editor, _desc, _icon in EDITORS:
        if editor == "TOOL_SETTINGS":         # Maya order: toolkit, character controls, AE, tool settings, CB
            _grey(row, "ed_CHARACTER", "Status Line/Show or hide the Character Controls")
        _flat(row, ALLSET_OT_editor_toggle.bl_idname, "ed_" + editor,
              depress=editor_shown(screen, editor)).editor = editor

    if compact and _group(layout, "INPUT"):
        input_line.draw(layout, context)
        _group_end(layout, "INPUT")


def _live_text(self):
    from ..operators import live
    return live.text(self)


def _symmetry_text(self):
    from ..operators import symmetry
    return symmetry.label(symmetry.state(bpy.context.scene))


def _read_only(self, value):
    pass




def _maya_bar(context):
    from .. import preferences
    try:
        return preferences.get(context).maya_top_bar
    except KeyError:
        return False


# Top bars seen while drawing them, by window pointer: global areas aren't in screen.areas, so
# window.screen.areas tag_redraw never reaches them. A window's global
# areas live as long as the window, so only areas of open windows are tagged.
_top_bars = {}


def redraw_top_bars():
    open_windows = {w.as_pointer() for w in bpy.context.window_manager.windows}
    for key in list(_top_bars):
        if key not in open_windows:
            del _top_bars[key]
            continue
        try:
            _top_bars[key].tag_redraw()
        except ReferenceError:
            del _top_bars[key]


# --- menu bar overflow (step 142, #77) -------------------------------------------------------------------------
# Maya hides the menus that don't fit behind a » button at the menu bar's right end; the
# kit's bar ran under the Workspace field instead ("Deform U", GUI shot at UI scale 1.5). Same pattern as the panel
# toolbar's » (step 132 #52, ui/panel_toolbar.py): Blender's header layout can't report where it put an item, so the
# widths follow its layout rules (toolbar_fit.unit; a ``ui_units_x = k`` sub-row is floor(k U) wide, step 132).
MENU_LEAD_UNITS = 0.4    # the header region's left padding
LOGO_UNITS = 1.6         # the Blender logo pulldown (icon only)
MENU_SET_UNITS = 5.5     # the menu set dropdown (= menu_sets.draw_menu_bar)
MENU_MORE_UNITS = 1.5    # the » button
MENU_SLACK_UNITS = 0.5   # kept free before the right-hand region
_menus_shown = {}        # window pointer -> (menu names in bar order, how many the bar shows)


def menu_fit(widths, width, fixed, more):
    """How many leading menus (px ``widths``) the bar shows in ``width`` px after ``fixed`` px; when they don't all
    fit, the » button (``more`` px) takes its place at the end."""
    if fixed + sum(widths) <= width:
        return len(widths)
    x = fixed + more
    n = 0
    for w in widths:
        if x + w > width:
            break
        x += w
        n += 1
    return n


def menu_bar_widths(context, names, menu_set):
    """(px width of each menu of ``names``, fixed px: padding, logo, menu set dropdown, slack, » button)."""
    from .toolbar_fit import unit
    system = context.preferences.system
    u = unit(system.ui_scale or 1.0, system.pixel_size)
    widths = []
    for name in names:
        cls = getattr(bpy.types, menu_sets.menu_idname(name), None)
        label = cls.bl_label if cls is not None else name
        widths.append(int(menu_sets.menu_width_units(label, context) * u))
    fixed = int((MENU_LEAD_UNITS + LOGO_UNITS + MENU_SLACK_UNITS) * u) + (int(MENU_SET_UNITS * u) if menu_set else 0)
    return widths, fixed, int(MENU_MORE_UNITS * u)


def shown_menus(window):
    """(menu names, how many the menu bar of ``window`` showed when it was last drawn)."""
    return _menus_shown.get(window.as_pointer(), ((), 0)) if window is not None else ((), 0)


def _menu_set_field(layout, prefs):
    sub = layout.row()
    sub.ui_units_x = MENU_SET_UNITS
    sub.prop(prefs, "menu_set", text="")


def draw_menu_bar_fit(layout, context, menu_set=True):
    """``menu_sets.draw_menu_bar`` when every menu fits the region, else the menus that fit and Maya's » overflow."""
    from .. import preferences
    prefs = preferences.get(context)
    names = menu_sets.menus_for_set(prefs.menu_set)
    region = getattr(context, "region", None)
    widths, fixed, more = menu_bar_widths(context, names, menu_set)
    n = menu_fit(widths, region.width, fixed, more) if region is not None and region.width > 1 else len(names)
    if context.window is not None:
        _menus_shown[context.window.as_pointer()] = (tuple(names), n)
    if n >= len(names):
        menu_sets.draw_menu_bar(layout, context, menu_set=menu_set)
        return
    layout.menu("TOPBAR_MT_blender", text="", icon='BLENDER')
    common = len(menu_sets._SET_MENUS[menu_sets.COMMON_SET])    # the menu set dropdown follows these
    for i, name in enumerate(names[:n]):
        cls = getattr(bpy.types, menu_sets.menu_idname(name), None)
        sub = layout.row(align=True)
        sub.ui_units_x = menu_sets.menu_width_units(cls.bl_label if cls else name, context)
        sub.menu(menu_sets.menu_idname(name))
        if menu_set and i == common - 1:
            _menu_set_field(layout, prefs)
    if menu_set and n < common:
        _menu_set_field(layout, prefs)
    sub = layout.row(align=True)
    sub.ui_units_x = MENU_MORE_UNITS
    icon = status_icons.icon("pt_more") if "pt_more" in status_icons.EXTRA else 0
    if icon:
        sub.menu(ALLSET_MT_menu_more.bl_idname, text="", icon_value=icon)
    else:
        sub.menu(ALLSET_MT_menu_more.bl_idname, text="\u00bb")


class ALLSET_MT_menu_more(bpy.types.Menu):
    """More Maya menus: the ones that don't fit the menu bar"""
    bl_idname = "ALLSET_MT_menu_more"
    bl_label = "More Menus"

    def draw(self, context):
        names, n = shown_menus(context.window)
        for name in names[n:]:
            self.layout.menu(menu_sets.menu_idname(name))


def draw_left(self, context):
    if context.window is not None and context.area is not None:
        _top_bars[context.window.as_pointer()] = context.area
    if not _maya_bar(context):
        return bpy.types.TOPBAR_HT_upper_bar.draw_left(self, context)
    layout = self.layout
    if context.area.show_menus:
        draw_menu_bar_fit(layout.row(align=True), context, menu_set=not status_line_shown(context))
    else:
        layout.menu(menu_sets.ALLSET_MT_menu_bar.bl_idname, text="", icon='COLLAPSEMENU')
    if context.screen.show_fullscreen:
        layout.separator()
        draw_safe.op(layout, "screen.back_to_previous", icon='SCREEN_BACK', text="Back to Previous")


def draw_right(self, context):
    if not _maya_bar(context):
        return bpy.types.TOPBAR_HT_upper_bar.draw_right(self, context)
    layout = self.layout
    window = context.window
    if not context.screen.show_statusbar:  # as space_topbar.py:46-49
        layout.template_reports_banner()
        layout.template_running_jobs()
    # Maya: "Workspace:" and a dropdown at the far right of the menu bar
    # (label 60 px, combo 194 px), not Blender's ID field
    # (screen icon, name, unlink button; step 113).
    row = layout.row(align=True)
    row.label(text="Workspace:")
    sub = row.row(align=True)
    sub.ui_units_x = 7
    sub.prop(context.window_manager, "allset_workspace", text="")
    if len(bpy.data.scenes) > 1:  # Maya has one scene per file; show only when needed
        row = layout.row()
        row.ui_units_x = 6
        row.template_ID(window, "scene", new="scene.new")


def status_line_shown(context):
    """A Status Line is drawn in this screen: the Maya strip row, or the main 3D View's tool header."""
    from .shelf import strip_area
    screen = context.screen
    if screen is None:
        return False
    if strip_area(screen) is not None:
        return True
    from .. import preferences
    try:
        if not preferences.get(context).show_status_line:
            return False
    except KeyError:
        return False
    area, _r = main_view3d(screen)
    return area is not None and area.spaces.active.show_region_tool_header


# The workspace dropdown (Maya's "Workspace:" combo) lists Maya's workspaces, then the file's others (ui/workspaces.py,
# step 160, #81).


def _workspaces(self, context):
    from . import workspaces
    return workspaces.dropdown_items(self, context)


def _get_workspace(self):
    from . import workspaces
    return workspaces.dropdown_get(self)


def _set_workspace(self, value):
    from . import workspaces
    workspaces.dropdown_set(self, value)


def draw_tool_header(self, context):
    """Status Line at the start of the main 3D View's tool header row."""
    from .. import preferences
    try:
        if not preferences.get(context).show_status_line:
            return
    except KeyError:
        return
    area, _r = main_view3d(context.screen)
    if area is None or context.area != area:  # one Status Line, not one per 3D View
        return
    from .shelf import strip_area
    if strip_area(context.screen) is not None:  # drawn in the Maya strip (step 12)
        return
    draw_status_line(self.layout, context, compact=True)
    self.layout.separator(type='LINE')


def draw_upper_bar(self, context):
    """The top bar's own draw while the kit is on (as space_topbar.py TOPBAR_HT_upper_bar.draw, with the kit's
    left / right): Blender's ``draw_left`` / ``draw_right`` methods stay untouched (step 115)."""
    if context.region.alignment == 'RIGHT':
        draw_right(self, context)
    else:
        draw_left(self, context)


def patch_topbar():
    own_draw.swap("TOPBAR_HT_upper_bar", draw_upper_bar)


def unpatch_topbar():
    own_draw.restore("TOPBAR_HT_upper_bar", draw_upper_bar)


classes = (ALLSET_OT_select_mask, ALLSET_OT_select_mode, ALLSET_OT_snap_toggle, ALLSET_MT_symmetry, ALLSET_MT_menu_more,
           ALLSET_OT_render_settings, ALLSET_OT_ipr_toggle,
           ALLSET_OT_editor_toggle, ALLSET_OT_status_group)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.allset_live_text = StringProperty(
        name="Live Surface", description="The live surface (Make Live); No Live Surface when none",
        get=_live_text, set=_read_only, options={'SKIP_SAVE'})
    bpy.types.Scene.allset_symmetry_text = StringProperty(
        name="Symmetry", description="Symmetric modeling: the current mode (the arrow opens the list)",
        get=_symmetry_text, set=_read_only, options={'SKIP_SAVE'})
    bpy.types.WindowManager.allset_workspace = EnumProperty(
        name="Workspace", description="Maya workspace: switch to another workspace of this file",
        items=_workspaces, get=_get_workspace, set=_set_workspace, options={'SKIP_SAVE'})
    patch_topbar()
    bpy.types.VIEW3D_HT_tool_header.prepend(draw_tool_header)
    bpy.types.VIEW3D_PT_active_tool.append(draw_tool_symmetry)
    bpy.app.handlers.load_pre.append(_masks_before_load)
    bpy.app.handlers.load_post.append(_masks_after_load)
    for name, fn in _SNAP_UNDO_HANDLERS:
        getattr(bpy.app.handlers, name).append(fn)


def unregister():
    for name, fn in _SNAP_UNDO_HANDLERS:
        handlers = getattr(bpy.app.handlers, name)
        if fn in handlers:
            handlers.remove(fn)
    if bpy.app.timers.is_registered(restore_snap):
        bpy.app.timers.unregister(restore_snap)
    _KEEP_SNAP.clear()
    for handlers, fn in ((bpy.app.handlers.load_pre, _masks_before_load),
                         (bpy.app.handlers.load_post, _masks_after_load)):
        if fn in handlers:
            handlers.remove(fn)
    _carried.clear()
    bpy.types.VIEW3D_PT_active_tool.remove(draw_tool_symmetry)
    bpy.types.VIEW3D_HT_tool_header.remove(draw_tool_header)
    unpatch_topbar()
    del bpy.types.WindowManager.allset_workspace
    del bpy.types.Scene.allset_live_text
    del bpy.types.Scene.allset_symmetry_text
    _collapsed.clear()
    _collapsed.update(DEFAULT_COLLAPSED)
    _top_bars.clear()
    _menus_shown.clear()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
