# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya workspaces: Windows > Workspaces, the Status Line "Workspace:" dropdown, Reset Current Workspace (#81).

Maya 2022 lists its factory workspaces in this order (Windows > Workspaces;
dividers after General, XGen - Interactive Groom, Animation and Rendering - Expert), then the actions Reset /
Save / Import / Delete Current Workspace and Disable Docking/Undocking. "General" is shown as "Maya Classic".
Choosing one switches the menu set to its ``linkedMenu``. The kit's template (tools/make_startup.MAYA_WORKSPACES) carries eight of them; a file without one gets it
appended from the bundled template (``switch.append_workspace``), Reset replaces the current one with a fresh copy
(``switch.reset_workspace``). Each template workspace keeps its menu set and the raised tab of the right tab stack
in ID properties (``allset_menu_set`` / ``allset_dock_tab``), applied when the kit switches to it.
"""

import bpy
from bpy.props import StringProperty

from .. import switch

# (template name, label); None = divider
FACTORY = (("General", "Maya Classic"), None, ("Modeling - Standard", "Modeling - Standard"),
           ("Modeling - Expert", "Modeling - Expert"), ("Sculpting", "Sculpting"), ("Pose Sculpting", "Pose Sculpting"),
           ("UV Editing", "UV Editing"), ("XGen", "XGen"), ("XGen - Interactive Groom", "XGen - Interactive Groom"),
           None, ("Rigging", "Rigging"), ("Animation", "Animation"), None,
           ("Rendering - Standard", "Rendering - Standard"), ("Rendering - Expert", "Rendering - Expert"), None,
           ("MASH", "MASH"), ("Motion Graphics", "Motion Graphics"))
# the ones the template carries (= tools/make_startup.MAYA_WORKSPACES, checked by tests/test_step160_workspaces.py)
IN_TEMPLATE = ("General", "Modeling - Standard", "Modeling - Expert", "Sculpting", "UV Editing", "Rigging", "Animation",
               "Rendering - Standard")
LABELS = {name: label for name, label in (e for e in FACTORY if e)}
PATH = "Windows/Workspaces/"
NOTICES = {
    PATH + "Pose Sculpting": ("Sculpting", "Blender has no pose space deformation editor: the Sculpting workspace and "
                              "shape keys (Shape Editor) cover sculpted corrections."),
    PATH + "XGen": ("Hair curves", "Blender grooms hair with hair curve objects and their sculpt mode, not XGen."),
    PATH + "XGen - Interactive Groom": ("Hair curves", "Blender grooms hair with hair curve objects and their sculpt "
                                        "mode, not XGen."),
    PATH + "Rendering - Expert": ("Rendering - Standard", "The kit carries Rendering - Standard; Blender's Render "
                                  "properties and Shader Editor are its editors."),
    PATH + "MASH": ("Geometry Nodes", "Blender has no MASH: instancing networks are Geometry Nodes."),
    PATH + "Motion Graphics": ("Geometry Nodes", "Blender has no MASH: instancing networks are Geometry Nodes."),
    PATH + "Save Current Workspace As...": ("Workspace tabs", "Blender saves workspaces with the file: duplicate one "
                                            "from its tab's menu."),
    PATH + "Import Workspace Files...": ("File > Append", "Blender brings workspaces from other files with File > "
                                         "Append > WorkSpace."),
    PATH + "Delete Current Workspace": ("Workspace tabs", "Blender deletes a workspace from its tab's menu; Maya's "
                                        "standard workspaces come back with Reset."),
    PATH + "Disable Docking/Undocking": ("Area corners", "Blender's areas are split and joined at their corners; "
                                         "there is no docking lock."),
}
ACTIONS_GREYED = ("Save Current Workspace As...", "Import Workspace Files...", "Delete Current Workspace",
                  "Disable Docking/Undocking")


def find(template_name):
    """The open file's workspace made from ``template_name`` (None: not in the file)."""
    for ws in bpy.data.workspaces:
        if switch.template_of(ws) == template_name:
            return ws
    return None


def apply_settings(context, ws):
    """Maya's linkedMenu and the tab-stack tab of workspace ``ws``."""
    menu_set = ws.get("allset_menu_set")
    if isinstance(menu_set, str) and menu_set:
        from .. import preferences
        try:
            preferences.get(context).menu_set = menu_set
        except (KeyError, TypeError):
            pass
    tab = ws.get("allset_dock_tab")
    if isinstance(tab, str) and tab:
        try:
            context.window_manager.allset_dock = tab
        except TypeError:
            pass


def activate(context, window, template_name):
    """Show Maya workspace ``template_name`` in ``window`` (appended from the template when the file lacks it)."""
    ws = find(template_name)
    if ws is None:
        prev = window.workspace.name if window.workspace is not None else ""
        ws = switch.append_workspace(window, template_name)
        if ws is None:
            return None
        if prev and switch.PREV_KEY not in ws:
            ws[switch.PREV_KEY] = prev        # the way back to Blender's layout (switch.leave_layout)
    window.workspace = ws
    apply_settings(context, ws)
    return ws


def label_of(ws):
    t = switch.template_of(ws)
    return LABELS.get(t, ws.name) if t else ws.name


def reset_label(ws):
    """Maya's item text for a factory workspace (Windows > Workspaces menu)."""
    return f'Reset "{label_of(ws)}" to Factory Default' if switch.template_of(ws) else "Reset Current Workspace"


# --- Status Line dropdown -------------------------------------------------------------------------------------------
# items = the Maya workspaces (in Maya's order, also those not yet in the file: choosing one appends it), then the
# file's other workspaces. Blender keeps pointers into item strings: one cached list per set of names.

_items = {}


def entries():
    """[(template name or None, workspace or None, label)] in dropdown order."""
    out = [(name, find(name), LABELS[name]) for name in IN_TEMPLATE]
    out += [(None, ws, ws.name) for ws in bpy.data.workspaces if switch.template_of(ws) is None]
    return out


def dropdown_items(_self, _context):
    labels = tuple(label for _t, _w, label in entries())
    items = _items.get(labels)
    if items is None:
        items = [(str(i), label, "Switch to this Maya workspace" if i < len(IN_TEMPLATE) else
                  "Switch to this workspace") for i, label in enumerate(labels)] or [("0", "-", "")]
        _items[labels] = items
    return items


def dropdown_get(_self):
    window = bpy.context.window
    if window is None:
        return 0
    for i, (_t, ws, _label) in enumerate(entries()):
        if ws is not None and ws == window.workspace:
            return i
    return 0


def dropdown_set(_self, value):
    context = bpy.context
    window = context.window
    rows = entries()
    if window is None or not 0 <= value < len(rows):
        return
    template, ws, _label = rows[value]
    if template is not None:
        ptr = window.as_pointer()
        bpy.app.timers.register(lambda: _later(ptr, template), first_interval=0.0)
    elif ws is not None:
        window.workspace = ws


def _later(window_ptr, template):
    # appending runs an operator: not from inside a property setter
    from .. import live_refs
    window = live_refs.window(window_ptr)
    if window is not None:
        with bpy.context.temp_override(window=window):
            activate(bpy.context, window, template)
    return None


# --- operators / menu -----------------------------------------------------------------------------------------------

class ALLSET_OT_maya_workspace(bpy.types.Operator):
    """Switch to this Maya workspace (Maya Windows > Workspaces); a file without it gets the kit's copy"""
    bl_idname = "allset.maya_workspace"
    bl_label = "Maya Workspace"
    bl_options = {'REGISTER'}

    name: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        return f"Switch to the Maya workspace {LABELS.get(props.name, props.name)}"

    def execute(self, context):
        if self.name not in IN_TEMPLATE or context.window is None:
            return {'CANCELLED'}
        if activate(context, context.window, self.name) is None:
            self.report({'WARNING'}, f"The workspace {LABELS[self.name]} could not be loaded")
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_reset_workspace(bpy.types.Operator):
    """Put the current Maya workspace back to its factory layout (Maya Windows > Workspaces > Reset Current
    Workspace): closed, moved or resized panels come back"""
    bl_idname = "allset.reset_workspace"
    bl_label = "Reset Current Workspace"
    bl_options = {'REGISTER'}

    def execute(self, context):
        window = context.window
        ws = switch.reset_workspace(window)
        if ws is None:
            self.report({'WARNING'}, "This isn't one of Maya's workspaces: nothing to reset")
            return {'CANCELLED'}
        apply_settings(context, ws)
        return {'FINISHED'}


class ALLSET_MT_maya_workspaces(bpy.types.Menu):
    """Maya Windows > Workspaces (Maya 2022 order)"""
    bl_label = "Workspaces"

    def draw(self, context):
        from .menu_sets import ALLSET_OT_menu_unavailable
        from .draw_safe import op as safe_op      # an operator missing (half-registered kit) can't empty the menu
        lay = self.layout
        current = switch.template_of(context.window.workspace) if context.window else None
        for entry in FACTORY:
            if entry is None:
                lay.separator()
                continue
            name, label = entry
            if name in IN_TEMPLATE:
                op = safe_op(lay, ALLSET_OT_maya_workspace.bl_idname, text=label,
                             icon='RADIOBUT_ON' if name == current else 'RADIOBUT_OFF')
                op.name = name
            else:
                safe_op(lay, ALLSET_OT_menu_unavailable.bl_idname, text=label, icon='RADIOBUT_OFF').item = PATH + name
        lay.separator()
        ws = context.window.workspace if context.window else None
        lay.operator(ALLSET_OT_reset_workspace.bl_idname, text=reset_label(ws) if ws else "Reset Current Workspace")
        for label in ACTIONS_GREYED:
            safe_op(lay, ALLSET_OT_menu_unavailable.bl_idname, text=label).item = PATH + label


classes = (ALLSET_OT_maya_workspace, ALLSET_OT_reset_workspace, ALLSET_MT_maya_workspaces)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    from . import notices
    notices.PANEL_NOTICES.update(NOTICES)


def unregister():
    from . import notices
    for k in NOTICES:
        notices.PANEL_NOTICES.pop(k, None)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    _items.clear()
