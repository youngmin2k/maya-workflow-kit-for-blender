# SPDX-License-Identifier: GPL-3.0-or-later
"""Your own workspaces: Maya's Windows > Workspaces > Save Current Workspace As... / Delete Current Workspace and the
list of saved workspaces after Maya's (#277).

Save Current Workspace As writes the current workspace (its screen: areas, editors, sizes) into its own file in the
extension's user folder (``workspaces/<name>.blend``); only the workspace goes into that file — no scene, objects,
cameras or images. Choosing a saved workspace appends it into the open file (like the Maya workspaces of the
kit's template), Reset Current Workspace brings back its saved state and Delete Current Workspace removes the file.
Nothing is saved without the user asking: new scenes keep starting in the kit's Maya Classic layout.
"""

import os

import bpy
from bpy.props import StringProperty

from .. import switch

FOLDER = "workspaces"
EXT = ".blend"
# characters a file name can't hold on every system (and "%", the escape itself): written as %XX
_UNSAFE = set('<>:"/\\|?*%')


def _package():
    return __package__.rsplit(".", 1)[0]   # the add-on package (``...allset``)


def folder(create=False):
    """``workspaces`` in the extension's user folder (legacy add-on build: a folder inside the add-on's own folder)."""
    try:
        return bpy.utils.extension_path_user(_package(), path=FOLDER, create=create)
    except (ValueError, AttributeError):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_data", FOLDER)
        if create:
            os.makedirs(path, exist_ok=True)
        return path


def file_name(name):
    """``name`` as a file name (reversible: ``name_of``)."""
    out = "".join(f"%{ord(c):02X}" if c in _UNSAFE or ord(c) < 32 else c for c in name)
    if out.endswith((".", " ")):                  # Windows drops a trailing dot / space
        out = out[:-1] + f"%{ord(out[-1]):02X}"
    return out + EXT


def name_of(filename):
    stem = filename[:-len(EXT)] if filename.endswith(EXT) else filename
    out, i = [], 0
    while i < len(stem):
        if stem[i] == "%" and i + 3 <= len(stem):
            try:
                out.append(chr(int(stem[i + 1:i + 3], 16)))
                i += 3
                continue
            except ValueError:
                pass
        out.append(stem[i])
        i += 1
    return "".join(out)


def path_of(name, create=False):
    return os.path.join(folder(create), file_name(name))


def saved_names():
    """Names of the saved workspaces, sorted."""
    base = folder()
    try:
        files = os.listdir(base) if os.path.isdir(base) else []
    except OSError:
        return []
    return sorted((name_of(f) for f in files if f.lower().endswith(EXT)), key=str.casefold)


def user_name(ws):
    """The saved-workspace name of ``ws`` (None: not one of the user's saved workspaces)."""
    if ws is None:
        return None
    name = ws.get(switch.USER_KEY)
    return name if isinstance(name, str) and name else None


def find(name):
    """The open file's copy of saved workspace ``name`` (None: not in the file)."""
    for ws in bpy.data.workspaces:
        if user_name(ws) == name:
            return ws
    return None


# keys of the open file's workspace that must not go into the saved copy (they point at this file's other
# workspaces / data, or mark it as a template workspace)
_LOCAL_KEYS = (switch.TEMPLATE_KEY, switch.PREV_KEY, switch.BLENDER_PREV_KEY, switch.MASK_KEY,
               switch.BLENDER_LAYOUT_KEY)


def save(context, ws, name):
    """Write workspace ``ws`` as saved workspace ``name``; ``ws`` becomes that saved workspace (Maya: the saved
    workspace is the current one). Returns the file path."""
    from ..operators import units
    path = path_of(name, create=True)
    kept = {k: ws[k] for k in _LOCAL_KEYS if k in ws}
    for k in kept:
        del ws[k]
    before = {k: ws.get(k) for k in (switch.USER_KEY, switch.USER_UNIT_KEY)}
    ws[switch.USER_KEY] = name
    ws[switch.USER_UNIT_KEY] = units.maya_unit(context.scene)
    old_name = ws.name
    try:
        ws.name = name
        bpy.data.libraries.write(path, {ws}, fake_user=True)
    except Exception:
        ws.name = old_name
        for k, v in before.items():
            if v is None:
                del ws[k]
            else:
                ws[k] = v
        for k, v in kept.items():
            ws[k] = v
        raise
    for k, v in kept.items():
        if k != switch.TEMPLATE_KEY:          # no longer the template's copy: Maya Classic stays as shipped
            ws[k] = v
    return path


def load(window, name):
    """Append saved workspace ``name`` into the open file and show it in ``window``; None: no such file."""
    path = path_of(name)
    if not os.path.isfile(path):
        return None
    try:
        with bpy.data.libraries.load(path) as (src, _dst):
            names = list(src.workspaces)
    except (OSError, RuntimeError) as ex:
        print("Maya Workflow Kit: workspace not read:", ex)
        return None
    if not names:
        return None
    ws = switch.append_workspace(window, None, filepath=path, idname=names[0])
    if ws is None:
        return None
    ws[switch.USER_KEY] = name
    for k in _LOCAL_KEYS:
        if k in ws:
            del ws[k]
    ws.name = name
    return ws


def activate(context, window, name):
    """Show saved workspace ``name`` in ``window`` (appended from its file when the open file lacks it)."""
    from . import workspaces
    ws = find(name)
    if ws is None:
        prev = window.workspace.name if window.workspace is not None else ""
        ws = load(window, name)
        if ws is None:
            return None
        if prev and switch.PREV_KEY not in ws:
            ws[switch.PREV_KEY] = prev        # the way back to Blender's layout (switch.leave_layout)
    window.workspace = ws
    workspaces.apply_settings(context, ws)
    return ws


def reset(window, ws):
    """Replace the open file's copy of saved workspace ``ws`` by the saved state; returns the new one (None: no
    saved file)."""
    name = user_name(ws)
    if name is None or not os.path.isfile(path_of(name)):
        return None
    prev = ws.get(switch.PREV_KEY)
    ws.name = name + " (old)"
    del ws[switch.USER_KEY]
    new = load(window, name)
    if new is None:
        ws.name = name
        ws[switch.USER_KEY] = name
        return None
    if prev is not None:
        new[switch.PREV_KEY] = prev
    switch.drop_workspace(window, ws)
    return new


def delete(context, window, ws):
    """Maya Delete Current Workspace for a saved workspace: its file goes, the window shows Maya Classic and the
    open file's copy is removed."""
    from . import workspaces
    name = user_name(ws)
    if name is None:
        return False
    path = path_of(name)
    if os.path.isfile(path):
        os.remove(path)
    if window.workspace == ws:
        if workspaces.activate(context, window, switch.TEMPLATE_WORKSPACE) is None:
            return False
    switch.drop_workspace(window, ws)
    return True


# --- operators -------------------------------------------------------------------------------------------------------

class ALLSET_OT_save_workspace_as(bpy.types.Operator):
    """Save the current workspace under a name (Maya Windows > Workspaces > Save Current Workspace As): it is listed
    under Windows > Workspaces in every scene. Only the layout is saved, in the extension's user folder"""
    bl_idname = "allset.save_workspace_as"
    bl_label = "Save Current Workspace As"
    bl_options = {'REGISTER'}

    name: StringProperty(name="Name", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.window is not None and context.window.workspace is not None

    def invoke(self, context, _event):
        from . import workspaces
        ws = context.window.workspace
        self.name = user_name(ws) or ("My " + workspaces.label_of(ws))
        return context.window_manager.invoke_props_dialog(self, title="Save Current Workspace As",
                                                          confirm_text="Save")

    def draw(self, _context):
        lay = self.layout
        lay.prop(self, "name")
        name = self.name.strip()
        if name and name in saved_names():
            lay.label(text="Replaces the saved workspace of this name", icon='INFO')

    def execute(self, context):
        from . import workspaces
        name = self.name.strip()
        if not name:
            self.report({'WARNING'}, "Type a name for the workspace")
            return {'CANCELLED'}
        if name in workspaces.LABELS or name in workspaces.LABELS.values():
            self.report({'WARNING'}, f'"{name}" is one of Maya\'s workspaces: choose another name')
            return {'CANCELLED'}
        try:
            save(context, context.window.workspace, name)
        except (OSError, RuntimeError) as ex:
            self.report({'ERROR'}, f"The workspace could not be saved: {ex}")
            return {'CANCELLED'}
        from .. import results
        results.result(self, f'Saved workspace "{name}"')
        return {'FINISHED'}


class ALLSET_OT_user_workspace(bpy.types.Operator):
    """Switch to this saved workspace (Maya Windows > Workspaces)"""
    bl_idname = "allset.user_workspace"
    bl_label = "Saved Workspace"
    bl_options = {'REGISTER'}

    name: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def description(cls, _context, props):
        return f'Switch to your saved workspace "{props.name}"'

    def execute(self, context):
        if context.window is None or activate(context, context.window, self.name) is None:
            self.report({'WARNING'}, f'The workspace "{self.name}" could not be loaded')
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_delete_workspace(bpy.types.Operator):
    """Delete the current saved workspace (Maya Windows > Workspaces > Delete Current Workspace): its file is removed
    and the window shows Maya Classic"""
    bl_idname = "allset.delete_workspace"
    bl_label = "Delete Current Workspace"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.window is not None and user_name(context.window.workspace) is not None

    def invoke(self, context, _event):
        name = user_name(context.window.workspace)
        return context.window_manager.invoke_confirm(self, _event, title="Delete Current Workspace",
                                                     message=f'Delete the saved workspace "{name}"?',
                                                     confirm_text="Delete")

    def execute(self, context):
        name = user_name(context.window.workspace)
        try:
            ok = delete(context, context.window, context.window.workspace)
        except OSError as ex:
            self.report({'ERROR'}, f"The workspace could not be deleted: {ex}")
            return {'CANCELLED'}
        if not ok:
            return {'CANCELLED'}
        from .. import results
        results.result(self, f'Deleted workspace "{name}"')
        return {'FINISHED'}


classes = (ALLSET_OT_save_workspace_as, ALLSET_OT_user_workspace, ALLSET_OT_delete_workspace)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
