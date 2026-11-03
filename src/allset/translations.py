# SPDX-License-Identifier: GPL-3.0-or-later
"""The Translations box of the add-on preferences: the user's translation files (``i18n/user_files.py``).

The kit has no language setting of its own: its texts follow Blender's interface language and Translate switches,
like the rest of Blender's interface.
"""

import bpy

from . import i18n
from .i18n import user_files

STATUS = [""]       # the template file written last


def _redraw(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


class ALLSET_OT_translations_folder(bpy.types.Operator):
    """Open the folder for your translation files (<language code>.json, for example de_DE.json) in your system's
    file browser"""
    bl_idname = "allset.translations_folder"
    bl_label = "Open Translations Folder"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        bpy.ops.wm.path_open(filepath=user_files.folder(create=True))
        return {'FINISHED'}


class ALLSET_OT_translations_template(bpy.types.Operator):
    """Write template_en.json, every text of the kit grouped by menu and window, into the translations folder: copy
    it to <language code>.json and replace the English values"""
    bl_idname = "allset.translations_template"
    bl_label = "Write Template"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        try:
            STATUS[0] = user_files.write_template()
        except OSError as exc:
            self.report({'ERROR'}, f"Could not write the template: {exc}")
            return {'CANCELLED'}
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_translations_reload(bpy.types.Operator):
    """Read your translation files again. The kit's texts follow Blender's interface language (Preferences >
    Interface > Language) and its Translate switches"""
    bl_idname = "allset.translations_reload"
    bl_label = "Reload Translations"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        i18n.reload()
        _redraw(context)
        return {'FINISHED'}


NOTES = {user_files.NOT_READ: i18n.mark("could not be read (not valid JSON)"),
         user_files.NOT_LANGUAGE: i18n.mark("the file name is not a Blender language code")}


def draw(layout):
    """The Translations box (add-on preferences)."""
    box = layout.box()
    row = box.row()
    row.label(text="Translations", icon='WORLD')
    row.label(text="Language: Blender's interface language (Preferences > Interface > Language)")
    row = box.row(align=True)
    row.operator("allset.translations_folder", icon='FILE_FOLDER')
    row.operator("allset.translations_template", icon='FILE_TEXT')
    row.operator("allset.translations_reload", icon='FILE_REFRESH')
    col = box.column(align=True)
    if not user_files.LOADED:
        col.label(text="No translation files loaded")
    for name, count, problem in user_files.LOADED:
        if problem:
            col.label(text=f"{name}: {i18n.iface(NOTES[problem])}", icon='ERROR', translate=False)
        else:
            col.label(text=f"{name}: {count} {i18n.iface('translated texts')}", icon='CHECKMARK', translate=False)
    if STATUS[0]:
        col.label(text=STATUS[0], icon='FILE_TICK', translate=False)


classes = (ALLSET_OT_translations_folder, ALLSET_OT_translations_template, ALLSET_OT_translations_reload)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    STATUS[0] = ""
