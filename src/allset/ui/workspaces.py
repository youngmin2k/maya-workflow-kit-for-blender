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
from . import user_workspaces

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
    PATH + "Import Workspace Files...": ("File > Append", "Blender brings workspaces from other files with File > "
                                         "Append > WorkSpace."),
    PATH + "Delete Current Workspace": ("Workspace tabs", "Maya's standard workspaces can't be deleted: they come "
                                        "back with Reset. Workspaces you saved are deleted while they are current."),
    PATH + "Disable Docking/Undocking": ("Area corners", "Blender's areas are split and joined at their corners; "
                                         "there is no docking lock."),
}
ACTIONS_GREYED = ("Import Workspace Files...", "Disable Docking/Undocking")


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


# the main view's display mode that follows a workspace switch: Maya's workspaces share one persp panel
DISPLAY = (("shading", "type"), ("shading", "show_xray"), ("shading", "show_xray_wireframe"),
           ("overlay", "show_xray_bone"), ("overlay", "show_wireframes"))


def display_of(screen):
    """{(struct, prop): value} of the main 3D View of ``screen`` (empty without one)."""
    from .status_line import main_view3d
    area, _region = main_view3d(screen) if screen is not None else (None, None)
    if area is None:
        return {}
    space = area.spaces.active
    return {(part, prop): getattr(getattr(space, part), prop) for part, prop in DISPLAY}


def carry_display(display, ws):
    """Give the main 3D View of workspace ``ws`` the display mode read by ``display_of`` (wireframe stays
    wireframe, X-Ray Joints stays on ...)."""
    from .status_line import main_view3d
    if not display or not ws.screens:
        return
    area, _region = main_view3d(ws.screens[0])
    if area is None:
        return
    space = area.spaces.active
    for (part, prop), value in display.items():
        struct = getattr(space, part)
        if getattr(struct, prop) != value:
            try:
                setattr(struct, prop, value)
            except (AttributeError, TypeError, ValueError):
                pass
    area.tag_redraw()


def activate(context, window, template_name):
    """Show Maya workspace ``template_name`` in ``window`` (appended from the template when the file lacks it); its
    main view keeps the display mode of the view shown before."""
    display = display_of(window.screen)
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
    carry_display(display, ws)
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
    """[(template name / ("user", saved name) / None, workspace or None, label)] in dropdown order: Maya's
    workspaces, the user's saved ones, then the file's other workspaces."""
    out = [(name, find(name), LABELS[name]) for name in IN_TEMPLATE]
    saved = user_workspaces.saved_names()
    out += [(("user", name), user_workspaces.find(name), name) for name in saved]
    out += [(None, ws, ws.name) for ws in bpy.data.workspaces
            if switch.template_of(ws) is None and user_workspaces.user_name(ws) not in saved]
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
            if isinstance(template, tuple):
                user_workspaces.activate(bpy.context, window, template[1])
            else:
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
        if window is not None and user_workspaces.user_name(window.workspace) is not None:
            ws = user_workspaces.reset(window, window.workspace)
            if ws is None:
                self.report({'WARNING'}, "The saved file of this workspace is gone: nothing to reset")
                return {'CANCELLED'}
            window.workspace = ws
            apply_settings(context, ws)
            return {'FINISHED'}
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
        ws = context.window.workspace if context.window else None
        mine = user_workspaces.user_name(ws)
        saved = user_workspaces.saved_names()
        if saved:                       # the user's saved workspaces, after Maya's
            lay.separator()
            for name in saved:
                op = safe_op(lay, user_workspaces.ALLSET_OT_user_workspace.bl_idname, text=name, translate=False,
                             icon='RADIOBUT_ON' if name == mine else 'RADIOBUT_OFF')
                op.name = name
        lay.separator()
        lay.operator(ALLSET_OT_reset_workspace.bl_idname, text=reset_label(ws) if ws else "Reset Current Workspace")
        safe_op(lay, user_workspaces.ALLSET_OT_save_workspace_as.bl_idname, text="Save Current Workspace As...")
        safe_op(lay, ALLSET_OT_menu_unavailable.bl_idname, text="Import Workspace Files...").item =             PATH + "Import Workspace Files..."
        if mine is not None:
            safe_op(lay, user_workspaces.ALLSET_OT_delete_workspace.bl_idname, text="Delete Current Workspace")
        else:
            safe_op(lay, ALLSET_OT_menu_unavailable.bl_idname, text="Delete Current Workspace").item =                 PATH + "Delete Current Workspace"
        safe_op(lay, ALLSET_OT_menu_unavailable.bl_idname, text="Disable Docking/Undocking").item =             PATH + "Disable Docking/Undocking"


classes = (ALLSET_OT_maya_workspace, ALLSET_OT_reset_workspace, ALLSET_MT_maya_workspaces)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    user_workspaces.register()
    from . import notices
    notices.PANEL_NOTICES.update(NOTICES)


def unregister():
    from . import notices
    for k in NOTICES:
        notices.PANEL_NOTICES.pop(k, None)
    user_workspaces.unregister()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    _items.clear()
