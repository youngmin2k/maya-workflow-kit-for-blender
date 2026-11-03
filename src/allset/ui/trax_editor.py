# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Trax Editor on Blender's NLA Editor.

- The NLA Editor header draws Maya's Trax menu bar (File / Edit / View / Modify / Create / Library / List / Help,
  structure ``editor_menu_data``, actions ``editor_menu_map``) and then Blender's own filters / snapping; Blender's
  NLA menus stay in a "Blender" menu at the end of the bar. Only the class's own draw is swapped (restored on
  unregister, ``tests/kit.py`` snapshots it), and only while the Maya editor menus are on.
- Library > Insert Clip lists the source clips; the sidebar tab "Trax" is the clip library (Maya's Visor): rename a
  source clip, place it at the current time, delete it with its instances.

Clips themselves: operators/trax_clips.py.
"""

import bpy
from bpy.props import IntProperty

from . import editor_chrome

TX = "Trax Editor"
_orig = {}


def _header(self, context):
    if not editor_chrome.enabled(context):
        return _orig["nla"](self, context)
    from bl_ui.space_dopesheet import dopesheet_filter
    layout = self.layout
    layout.template_header()
    editor_chrome.draw_menus(layout, context, TX)
    layout.separator_spacer()
    dopesheet_filter(layout, context)
    layout.popover(panel="NLA_PT_filters", text="", icon='FILTER')
    row = layout.row(align=True)
    row.prop(context.tool_settings, "use_snap_anim", text="")
    row.row(align=True).popover(panel="NLA_PT_snapping", text="")


def patch():
    funcs = bpy.types.NLA_HT_header._dyn_ui_initialize()
    if "nla" not in _orig:
        _orig["nla"] = funcs[0]
    funcs[0] = _header


def unpatch():
    if "nla" in _orig:
        bpy.types.NLA_HT_header._dyn_ui_initialize()[0] = _orig.pop("nla")


def _sources():
    from ..operators import trax_clips
    return trax_clips.sources()


class ALLSET_MT_trax_insert_clip(bpy.types.Menu):
    """Maya Trax Library > Insert Clip: the source clips"""
    bl_idname = "ALLSET_MT_trax_insert_clip"
    bl_label = "Insert Clip"

    def draw(self, context):
        layout = self.layout
        acts = _sources()
        if not acts:
            row = layout.row()
            row.enabled = False
            row.label(text="No clips on characters loaded in Trax")
            return
        for act in acts:
            layout.operator("allset.trax_insert_clip", text=act.name, translate=False).source = act.name


class ALLSET_UL_trax_clips(bpy.types.UIList):
    """Source clips (Maya's Visor clips)"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        from ..operators import trax_clips
        n = len({st.name for _o, _t, st in trax_clips.clip_strips(context.scene) if st.action == item})
        row = layout.row(align=True)
        row.prop(item, "name", text="", emboss=False, icon='ACTION')
        row.label(text=str(item.get(trax_clips.CHARACTER, "")), translate=False)
        row.label(text=f"{n}")

    def filter_items(self, context, data, propname):
        from ..operators import trax_clips
        items = getattr(data, propname)
        flags = [self.bitflag_filter_item if trax_clips.is_source(a) else 0 for a in items]
        return flags, []


class ALLSET_PT_trax_library(bpy.types.Panel):
    bl_space_type = 'NLA_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Trax"
    bl_label = "Clip Library"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        layout.label(text="Source clips (name, character, instances)")
        layout.template_list("ALLSET_UL_trax_clips", "", bpy.data, "actions", wm, "allset_trax_clip_index", rows=4)
        acts = bpy.data.actions
        i = wm.allset_trax_clip_index
        act = acts[i] if 0 <= i < len(acts) else None
        from ..operators import trax_clips
        row = layout.row(align=True)
        row.enabled = trax_clips.is_source(act)
        name = act.name if act is not None else ""
        row.operator("allset.trax_insert_clip", text="Insert at Current Time").source = name
        row.operator("allset.trax_delete_source", text="", icon='TRASH').source = name
        col = layout.column(align=True)
        col.operator("allset.trax_create_clip", text="Create Clip", icon='ADD')
        col.operator("allset.trax_clip_edit", text="Duplicate").action = 'DUPLICATE'
        col.operator("allset.trax_clip_edit", text="Blend").action = 'BLEND'
        col.operator("allset.trax_clip_edit", text="Delete Selected Clips").action = 'DELETE'


classes = (ALLSET_MT_trax_insert_clip, ALLSET_UL_trax_clips, ALLSET_PT_trax_library)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.allset_trax_clip_index = IntProperty(name="Clip", default=0, options={'SKIP_SAVE'})
    patch()


def unregister():
    unpatch()
    del bpy.types.WindowManager.allset_trax_clip_index
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
