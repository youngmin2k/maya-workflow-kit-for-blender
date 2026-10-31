# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya object sets (Create > Sets, Select > Quick Select Sets, Outliner set rows).

Maya behaviour (names set1, set2 …, selection kept,
``select <set>`` = the members, Quick Select Set = a set with text "gCharacterSet").
Blender has no set node, so a kit set is a collection that is not linked to any scene
(fake user, so it is saved) carrying the ID property ``allset_set`` = its creation number
(Outliner order); its objects are the members — an object can be in several collections, so
the scene tree is untouched.
"""


import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from .. import results
from . import naming

PROP = "allset_set"
TEXT = "allset_set_text"
QUICK = "gCharacterSet"     # Maya's text for Quick Select Sets


def is_set(coll):
    return coll is not None and coll.get(PROP) is not None


def all_sets():
    """Kit sets in creation order (Maya's Outliner order)."""
    return sorted((c for c in bpy.data.collections if is_set(c)), key=lambda c: (c.get(PROP), c.name))


def quick_sets():
    return [c for c in all_sets() if c.get(TEXT) == QUICK]


def get(name):
    coll = bpy.data.collections.get(name)
    return coll if is_set(coll) else None


def next_name(base="set"):
    """Maya: ``set<N>`` one past the highest, gaps not filled."""
    return f"{base}{naming.next_number(base, {c.name for c in bpy.data.collections})}"


def create(name="", objects=(), text=""):
    order = max((c.get(PROP) for c in bpy.data.collections if is_set(c)), default=0) + 1
    coll = bpy.data.collections.new(name or next_name())
    coll.use_fake_user = True      # not in any scene: the fake user keeps it in the file
    coll[PROP] = order
    if text:
        coll[TEXT] = text
    for ob in objects:
        if ob.name not in coll.objects:
            coll.objects.link(ob)
    return coll


def members(coll, scene=None):
    """The set's objects that are in ``scene`` (all of them without a scene)."""
    obs = list(coll.objects)
    if scene is None:
        return obs
    in_scene = set(scene.objects)
    return [ob for ob in obs if ob in in_scene]


def _selectable(ob):
    try:
        ob.select_set(ob.select_get())
        return True
    except RuntimeError:       # not in the view layer
        return False


def select_members(context, coll, mode='REPLACE'):
    """Maya ``cmds.select(set, replace / add / toggle=True)``: the members in the view layer; the last one becomes the
    lead."""
    vl = context.view_layer
    obs = [ob for ob in members(coll, context.scene) if _selectable(ob)]
    if context.mode != 'OBJECT' and context.active_object is not None:
        bpy.ops.object.mode_set(mode='OBJECT')
    if mode == 'REPLACE':
        for ob in context.selected_objects:
            ob.select_set(False)
    for ob in obs:
        ob.select_set(not ob.select_get() if mode == 'TOGGLE' else True)
    picked = [ob for ob in obs if ob.select_get()]
    if picked:
        vl.objects.active = picked[-1]
    return obs


def add(coll, objects):
    for ob in objects:
        if ob.name not in coll.objects:
            coll.objects.link(ob)


def remove(coll, objects):
    for ob in objects:
        if ob.name in coll.objects:
            coll.objects.unlink(ob)


def delete(coll):
    bpy.data.collections.remove(coll)


# --- operators -----------------------------------------------------------------------------------

def _selection(context):
    return list(context.selected_objects) if context.mode == 'OBJECT' else []


class ALLSET_OT_create_set(bpy.types.Operator):
    """New set holding the selected objects"""
    bl_idname = "allset.create_set"
    bl_label = "Set"
    bl_options = {'REGISTER', 'UNDO'}

    name: StringProperty(name="Name", description="Set name (empty: set1, set2, ...)", options={'SKIP_SAVE'})
    option_box: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        if self.option_box:   # Maya Create Set Options: the name
            self.name = self.name or next_name()
            return context.window_manager.invoke_props_dialog(self, title="Create Set Options", confirm_text="Create")
        return self.execute(context)

    def execute(self, context):
        coll = create(self.name, _selection(context))
        results.result(self, f"Result: {coll.name}")
        _refresh(context)
        return {'FINISHED'}


class ALLSET_OT_create_quick_select_set(bpy.types.Operator):
    """New set of the selected objects, also listed under Edit > Quick Select Sets"""
    bl_idname = "allset.create_quick_select_set"
    bl_label = "Create Quick Select Set"
    bl_options = {'REGISTER', 'UNDO'}

    name: StringProperty(name="Enter Quick Select Set name", default="Set")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, confirm_text="OK")

    def execute(self, context):
        coll = create(self.name.strip() or "Set", _selection(context), text=QUICK)
        results.result(self, f"Created Quick Select Set {coll.name}")
        _refresh(context)
        return {'FINISHED'}


class ALLSET_OT_select_set_members(bpy.types.Operator):
    """Select the members of the set (Maya: select <set>)"""
    bl_idname = "allset.select_set_members"
    bl_label = "Select Set Members"
    bl_options = {'REGISTER', 'UNDO'}

    name: StringProperty(options={'SKIP_SAVE'})
    mode: EnumProperty(items=(('REPLACE', "Replace", ""), ('ADD', "Add", ""), ('TOGGLE', "Toggle", "")),
                       options={'SKIP_SAVE'})

    def execute(self, context):
        coll = get(self.name or context.window_manager.allset_set_target)
        if coll is None:
            return {'CANCELLED'}
        select_members(context, coll, self.mode)
        return {'FINISHED'}


class ALLSET_OT_set_edit(bpy.types.Operator):
    """Edit a set: add / remove the selected objects, rename, delete, show its members"""
    bl_idname = "allset.set_edit"
    bl_label = "Edit Set"
    bl_options = {'REGISTER', 'UNDO'}

    name: StringProperty(options={'SKIP_SAVE'})
    member: StringProperty(options={'SKIP_SAVE'})
    action: EnumProperty(items=(('ADD', "Add Selected Objects", ""), ('REMOVE', "Remove Selected Objects", ""),
                                ('REMOVE_MEMBER', "Remove From Current Set", ""), ('DELETE', "Delete Set", ""),
                                ('RENAME', "Rename", ""), ('EXPAND', "Show Set Members", "")))
    new_name: StringProperty(name="Name", options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        return {'ADD': "Add the selected objects to the set", 'REMOVE': "Remove the selected objects from the set",
                'REMOVE_MEMBER': "Remove this object from the set", 'DELETE': "Delete the set (its objects stay)",
                'RENAME': "Rename the set", 'EXPAND': "Show the set's members under it"}[props.action]

    def invoke(self, context, event):
        if self.action == 'RENAME':
            coll = get(self.name or context.window_manager.allset_set_target)
            if coll is None:
                return {'CANCELLED'}
            self.name, self.new_name = coll.name, coll.name
            return context.window_manager.invoke_props_dialog(self, title="Rename Set")
        return self.execute(context)

    def draw(self, context):
        self.layout.prop(self, "new_name")

    def execute(self, context):
        coll = get(self.name or context.window_manager.allset_set_target)
        if coll is None:
            return {'CANCELLED'}
        if self.action == 'ADD':
            add(coll, _selection(context))
        elif self.action == 'REMOVE':
            remove(coll, _selection(context))
        elif self.action == 'REMOVE_MEMBER':
            ob = bpy.data.objects.get(self.member or context.window_manager.allset_set_member)
            if ob is not None:
                remove(coll, [ob])
        elif self.action == 'DELETE':
            delete(coll)
        elif self.action == 'RENAME':
            if self.new_name.strip():
                coll.name = self.new_name.strip()
        elif self.action == 'EXPAND':
            coll.allset_expanded = not coll.allset_expanded
        _refresh(context)
        return {'FINISHED'}


class ALLSET_MT_quick_select_sets(bpy.types.Menu):
    """Select > Quick Select Sets"""
    bl_label = "Quick Select Sets"
    bl_idname = "ALLSET_MT_quick_select_sets"

    def draw(self, context):
        layout = self.layout
        found = quick_sets()
        if not found:
            row = layout.row()
            row.enabled = False
            row.label(text="No Quick Select Sets")
            return
        for coll in found:
            layout.operator(ALLSET_OT_select_set_members.bl_idname, text=coll.name).name = coll.name


def _refresh(context):
    """Redraw Outliners and rebuild the sidebar Outliner rows."""
    from ..ui import outliner
    outliner.rebuild(context)
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type in {'OUTLINER', 'VIEW_3D'}:
                area.tag_redraw()


classes = (ALLSET_OT_create_set, ALLSET_OT_create_quick_select_set, ALLSET_OT_select_set_members,
           ALLSET_OT_set_edit, ALLSET_MT_quick_select_sets)


def register_props():
    bpy.types.Collection.allset_expanded = BoolProperty(
        name="Expanded", description="Set expanded in the Maya Outliner (Show Set Members)", options={'HIDDEN'})
    wm = bpy.types.WindowManager
    wm.allset_set_target = StringProperty(options={'SKIP_SAVE', 'HIDDEN'})   # the set row under an RMB menu
    wm.allset_set_member = StringProperty(options={'SKIP_SAVE', 'HIDDEN'})


def unregister_props():
    del bpy.types.WindowManager.allset_set_member
    del bpy.types.WindowManager.allset_set_target
    del bpy.types.Collection.allset_expanded
