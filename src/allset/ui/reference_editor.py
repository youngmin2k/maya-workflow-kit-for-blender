# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya's Reference Editor window (Issue #116).

Maya 2022: menu
bar File / Reference / Proxy / View / Help, an icon row, File Particulars (Unresolved name, Resolved name with Reload,
Namespace, Read Only, Sharing) and the reference list — a load check box and "<reference node> <file>" per row.

Blender: a new window whose area is a Properties editor on the Tool tab marked by hidden tab flags (the Hypershade
pane mechanism: two of ``maya_dock.ROLE_FLAGS`` + constraints, so neither the Maya dock, Tool Settings nor a
Hypershade pane draws there), drawn by ``ALLSET_PT_reference_editor``. Menus come from ``editor_menu_data``
("Reference Editor"), actions from ``editor_menu_map``; the commands live in ``operators/references.py``.
"""

import bpy
from bpy.props import BoolProperty, StringProperty

from .. import live_refs

EDITOR = "Reference Editor"
MARK = ("show_properties_world", "show_properties_physics", "show_properties_constraints")

# (icon, label, operator, props, tip) — Maya's icon row: create, import, export, reload, unload ... (left to right;
# the kit's subset)
ICONS = (('LINK_BLEND', "allset.create_reference", {}, "Create Reference"),
         ('IMPORT', "allset.reference_cmd", {"action": "IMPORT"}, "Import Objects from Reference"),
         ('EXPORT', "allset.reference_offline", {"mode": "EXPORT"}, "Export to Offline File"),
         "|",
         ('FILE_REFRESH', "allset.reference_cmd", {"action": "RELOAD"}, "Reload Reference"),
         ('HIDE_ON', "allset.reference_cmd", {"action": "UNLOAD"}, "Unload Reference"),
         ('FILE_FOLDER', "allset.reference_replace", {}, "Replace Reference"),
         ('X', "allset.reference_cmd", {"action": "REMOVE"}, "Remove Reference"),
         "|",
         ('LOCKED', "allset.reference_cmd", {"action": "LOCK"}, "Lock Reference"),
         ('RESTRICT_SELECT_OFF', "allset.reference_cmd", {"action": "SELECT"}, "Select File Contents"))


def _refs():
    from ..operators import references
    return references


def _flags(space):
    return [p.identifier for p in space.bl_rna.properties if p.identifier.startswith("show_properties_")]


def is_pane(area):
    if area is None or area.type != 'PROPERTIES':
        return False
    space = area.spaces.active
    if space.show_region_header or not space.show_properties_tool:
        return False
    from .. import compat
    on = {f for f in _flags(space) if getattr(space, f)} - set(compat.LATER_PROPERTIES_TABS)
    return on == {"show_properties_tool", *MARK}


def context_pane(context):
    return is_pane(getattr(context, "area", None))


def set_pane(area, window=None):
    """Mark the Properties editor ``area`` as the Reference Editor; False until its space can take the Tool tab."""
    space = area.spaces.active
    try:
        space.context = 'TOOL'
    except TypeError:
        return False
    for flag in _flags(space):
        setattr(space, flag, flag in ("show_properties_tool", *MARK))
    space.show_region_header = False
    nav = next((r for r in area.regions if r.type == 'NAVIGATION_BAR'), None)
    if nav is not None and nav.width > 1 and window is not None and not bpy.app.background:
        try:
            with bpy.context.temp_override(window=window, area=area):
                bpy.ops.screen.region_toggle(region_type='NAVIGATION_BAR')
        except (RuntimeError, TypeError):
            pass
    area.tag_redraw()
    return True


def set_pane_later(window, area, tries=60):
    win_ptr, key = window.as_pointer(), area.as_pointer()
    state = {"n": tries}

    def tick():
        win, area_ = live_refs.find_area(key, win_ptr)   # looked up each tick (#36)
        if area_ is None:
            return None
        with bpy.context.temp_override(window=win):
            done = set_pane(area_, win)
        state["n"] -= 1
        return None if done or state["n"] <= 0 else 0.05
    bpy.app.timers.register(tick, first_interval=0.0)


def find_window(context):
    for w in context.window_manager.windows:
        if any(is_pane(a) for a in w.screen.areas):
            return w
    return None


def open_window(context):
    """A new window with one Properties area made the Reference Editor (Maya: a floating window)."""
    from ..operators import menu_extras
    area = max(context.window.screen.areas, key=lambda a: a.width * a.height, default=None)
    if area is None:
        return None
    window = menu_extras.open_window(context, area, "reference_editor")
    if window is None:
        return None
    target = window.screen.areas[0]
    target.type = 'PROPERTIES'
    if not set_pane(target, window):
        set_pane_later(window, target)
    return window


class ALLSET_OT_reference_editor(bpy.types.Operator):
    """Open the Reference Editor: the scene's references with load state, Reload / Unload / Replace / Import / Remove
    (Maya File > Reference Editor)"""
    bl_idname = "allset.reference_editor"
    bl_label = "Reference Editor"

    def execute(self, context):
        if context.window is None:
            return {'CANCELLED'}
        if find_window(context) is not None:
            return {'FINISHED'}            # Maya raises the open one
        if open_window(context) is None:
            from . import window_places
            if not window_places.deferred():     # opens on a later tick (#203)
                self.report({'ERROR'}, "Could not open the Reference Editor window")
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_reference_pick(bpy.types.Operator):
    """Select this reference in the Reference Editor"""
    bl_idname = "allset.reference_pick"
    bl_label = "Select Reference"

    reference: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        context.window_manager.allset_ref_current = self.reference
        for w in context.window_manager.windows:
            for a in w.screen.areas:
                if is_pane(a):
                    a.tag_redraw()
        return {'FINISHED'}


# --- File Particulars proxies (Scene: edits push undo steps) -----------------------------------------------------

def _cur():
    return _refs().current(bpy.context)


def _ns_get(_self):
    ref = _cur()
    return ref.name if ref is not None else "N/A"


def _ns_set(_self, value):
    """Maya: the Namespace field renames the reference's namespace (its nodes' ``ns:`` prefix)."""
    ref = _cur()
    value = value.strip().replace(":", "_")
    if ref is None or not value or value == ref.name:
        return
    from ..operators import project
    old = ref.name
    new = project.unique_namespace(value, bpy.context.scene)
    ref.name = new
    for idb in [*ref.children_recursive, *ref.all_objects]:
        if idb.library is None and idb.name.startswith(old + ":"):
            idb.name = new + idb.name[len(old):]
    bpy.context.window_manager.allset_ref_current = ref.name


def _lock_get(_self):
    ref = _cur()
    return ref is not None and _refs().is_locked(ref)


def _lock_set(_self, value):
    ref = _cur()
    if ref is not None:
        _refs().set_locked(ref, value)


# --- the window's panel ---------------------------------------------------------------------------------------------

def _row_label(split, text):
    split.label(text=text)


def draw_icons(layout):
    line = layout.row()
    row = line.row(align=True)
    for it in ICONS:
        if it == "|":
            row = line.row(align=True)
            continue
        icon, idname, props, _tip = it
        op = row.operator(idname, text="", icon=icon)
        for k, v in props.items():
            setattr(op, k, v)


def draw_particulars(layout, context):
    refs = _refs()
    ref = refs.current(context)
    wm = context.window_manager
    box = layout.box()
    head = box.row()
    head.alignment = 'LEFT'
    head.prop(wm, "allset_ref_particulars", text="File Particulars", emboss=False,
              icon='TRIA_DOWN' if wm.allset_ref_particulars else 'TRIA_RIGHT')
    if not wm.allset_ref_particulars:
        return
    col = box.column(align=False)
    col.enabled = ref is not None
    path = refs.path_of(ref) if ref is not None else "N/A"
    resolved = bpy.path.abspath(path) if ref is not None else "N/A"
    for label, value, button in (("Unresolved name:", path, "RELOAD"), ("Resolved name:", resolved, "READ_ONLY")):
        split = col.split(factor=0.24)
        _row_label(split, label)
        row = split.row(align=True)
        field = row.row()
        field.alignment = 'LEFT'
        field.label(text=value)
        if button == "RELOAD":
            op = row.operator("allset.reference_cmd", text="Reload")
            op.action = "RELOAD"
        else:
            row.prop(context.scene, "allset_ref_read_only", text="Read Only")
    split = col.split(factor=0.24)
    _row_label(split, "Namespace:")
    split.prop(context.scene, "allset_ref_namespace", text="")
    split = col.split(factor=0.24)
    _row_label(split, "Sharing:")
    split.label(text="N/A")


def draw_list(layout, context):
    refs = _refs()
    cur = refs.current(context)
    col = layout.column(align=True)
    items = refs.references(context.scene)
    if not items:
        col.label(text="No references: File > Create Reference...", icon='INFO')
        return
    for ref in items:
        row = col.row(align=True)
        loaded = refs.is_loaded(ref)
        op = row.operator("allset.reference_cmd", text="", icon='CHECKBOX_HLT' if loaded else 'CHECKBOX_DEHLT',
                          emboss=False)
        op.action, op.reference = "TOGGLE", ref.name
        lock = " (locked)" if refs.is_locked(ref) else ""
        name = row.row(align=True)
        name.alignment = 'LEFT'           # Maya: "propRN prop_src.ma" from the left
        pick = name.operator("allset.reference_pick", text=f"{refs.node_name(ref)}  {refs.file_label(ref)}{lock}",
                             depress=cur is not None and cur == ref, emboss=cur is not None and cur == ref)
        pick.reference = ref.name


class ALLSET_PT_reference_editor(bpy.types.Panel):
    """Maya's Reference Editor (a marked Properties Tool tab in its own window)"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"            # = drawn by the Properties Tool tab
    bl_label = "Reference Editor"
    bl_options = {'HIDE_HEADER'}
    bl_order = -300

    @classmethod
    def poll(cls, context):
        return context_pane(context)

    def draw(self, context):
        from . import editor_chrome
        layout = self.layout
        bar = layout.row(align=True)
        bar.alignment = 'LEFT'
        bar.emboss = 'PULLDOWN_MENU'          # Maya's flat menu bar titles
        editor_chrome.draw_menu_bar(bar, context, EDITOR)
        draw_icons(layout)
        draw_particulars(layout, context)
        draw_list(layout, context)


classes = (ALLSET_OT_reference_editor, ALLSET_OT_reference_pick, ALLSET_PT_reference_editor)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    wm = bpy.types.WindowManager
    wm.allset_ref_current = StringProperty(name="Selected Reference", description="The Reference Editor's row")
    wm.allset_ref_particulars = BoolProperty(name="File Particulars", default=True)
    sc = bpy.types.Scene
    sc.allset_ref_namespace = StringProperty(name="Namespace", get=_ns_get, set=_ns_set,
                                             description="The selected reference's namespace (renames its ns: nodes)")
    sc.allset_ref_read_only = BoolProperty(name="Read Only", get=_lock_get, set=_lock_set,
                                           description="Lock the selected reference: no edits")


def unregister():
    for name in ("allset_ref_namespace", "allset_ref_read_only"):
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
    for name in ("allset_ref_current", "allset_ref_particulars"):
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
