# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Light Editor = a kit light list in a 3D View window's sidebar (step 67).

Maya: a floating window with a toolbar (create lights),
a list (Name / Color / Intensity / Exposure, enable and solo per row) and the Property Editor of the picked light.
Blender has no Light Editor and Python can't make an editor type, so ``allset.light_editor`` duplicates the main
3D View into a new window and shows its sidebar's "Light Editor" tab, which polls only in such windows
(``_SPACES``: window + space pointers, valid while that window holds that one area — freed pointers get reused).

- Enable = ``hide_render`` and ``hide_viewport`` together (Maya: the light's visibility, which also stops it lighting);
- Isolate = every other light off; their previous values are kept in the scene ID property ``allset_light_isolate``
  and come back when Isolate is pressed again (lights deleted meanwhile are skipped);
- Intensity = Maya intensity ``Light.allset_intensity`` (read from and written to ``energy``, operators/lights.py, step 137);
  Maya's Exposure has no separate value in Blender.
"""

import bpy
from bpy.props import StringProperty

from ..operators import menu_extras
from . import ae_layout

CATEGORY = "Light Editor"
NOTICE = "Light Editor (kit): Blender has no Light Editor, Maya Workflow Kit lists the scene lights. Exposure is part of Intensity."
ISOLATE_PROP = "allset_light_isolate"
# Maya Light Editor toolbar order: create light buttons
CREATE = (("AMBIENT_LIGHT", 'WORLD'), ("DIRECTIONAL_LIGHT", 'LIGHT_SUN'), ("POINT_LIGHT", 'LIGHT_POINT'),
          ("SPOT_LIGHT", 'LIGHT_SPOT'), ("AREA_LIGHT", 'LIGHT_AREA'), ("VOLUME_LIGHT", 'MESH_UVSPHERE'))

_SPACES = set()     # (window pointer, space pointer) of Light Editor windows


def mark(window):
    _SPACES.add((window.as_pointer(), window.screen.areas[0].spaces.active.as_pointer()))


def is_light_editor(context):
    space, window = context.space_data, context.window
    if space is None or window is None or space.type != 'VIEW_3D':
        return False
    if (window.as_pointer(), space.as_pointer()) not in _SPACES:
        return False
    return len(window.screen.areas) == 1


def lights(context):
    # scene.objects: view_layer.objects lags behind objects linked since the last depsgraph sync (step 11)
    return sorted((o for o in context.scene.objects if o.type == 'LIGHT'), key=lambda o: o.name.lower())


def enabled(ob):
    return not (ob.hide_render or ob.hide_viewport)


def set_enabled(ob, on):
    ob.hide_render = ob.hide_viewport = not on


def isolated(scene):
    state = scene.get(ISOLATE_PROP)
    return state.get("light", "") if state is not None else ""


def isolate(scene, name):
    """Maya Isolate: only ``name`` lights; pressing it again (or isolating another light) restores the rest."""
    previous = isolated(scene)
    unisolate(scene)
    if previous == name:
        return False
    saved = {}
    for ob in scene.objects:
        if ob.type != 'LIGHT':
            continue
        saved[ob.name] = [ob.hide_render, ob.hide_viewport]
        set_enabled(ob, ob.name == name)
    scene[ISOLATE_PROP] = {"light": name, "saved": saved}
    return True


def unisolate(scene):
    state = scene.get(ISOLATE_PROP)
    if state is None:
        return
    for name, (render, viewport) in state.to_dict().get("saved", {}).items():
        ob = scene.objects.get(name)
        if ob is not None:
            ob.hide_render, ob.hide_viewport = bool(render), bool(viewport)
    del scene[ISOLATE_PROP]


def lead(context):
    ob = context.active_object
    if ob is not None and ob.type == 'LIGHT':
        return ob
    return next((o for o in context.selected_objects if o.type == 'LIGHT'), None)


class ALLSET_OT_light_editor(bpy.types.Operator):
    """Light Editor: the scene's lights in a new window (kit list: Blender has no Light Editor)"""
    bl_idname = "allset.light_editor"
    bl_label = "Light Editor"

    def execute(self, context):
        from .status_line import main_view3d
        if context.window is None:
            return {'CANCELLED'}
        area, _r = main_view3d(context.window.screen)
        if area is None:
            area = max(context.window.screen.areas, key=lambda a: a.width * a.height, default=None)
        if area is None:
            return {'CANCELLED'}
        window = menu_extras.open_window(context, area, "light_editor")
        if window is None:
            from . import window_places
            if not window_places.deferred():     # opens on a later tick (#203)
                self.report({'ERROR'}, "Could not open a new window")
            return {'CANCELLED'}
        target = window.screen.areas[0]
        if target.type != 'VIEW_3D':
            target.ui_type = 'VIEW_3D'
        mark(window)
        menu_extras.sidebar_tab_later(window, CATEGORY)
        return {'FINISHED'}


_NAME = StringProperty(name="Light", options={'SKIP_SAVE'})


class ALLSET_OT_light_select(bpy.types.Operator):
    """Select this light (Shift: add to the selection)"""
    bl_idname = "allset.light_select"
    bl_label = "Select Light"
    bl_options = {'REGISTER', 'UNDO'}

    light: _NAME
    extend: bpy.props.BoolProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        self.extend = event.shift
        return self.execute(context)

    def execute(self, context):
        ob = context.scene.objects.get(self.light)
        if ob is None:
            return {'CANCELLED'}
        if not self.extend:
            for o in context.selected_objects:
                o.select_set(False)
        try:
            ob.select_set(True)
        except RuntimeError:    # disabled (hide_viewport): Maya still picks it in the editor
            pass
        context.view_layer.objects.active = ob
        return {'FINISHED'}


class ALLSET_OT_light_enable(bpy.types.Operator):
    """Turn this light on or off (render and viewport)"""
    bl_idname = "allset.light_enable"
    bl_label = "Enable Light"
    bl_options = {'REGISTER', 'UNDO'}

    light: _NAME

    def execute(self, context):
        ob = context.scene.objects.get(self.light)
        if ob is None:
            return {'CANCELLED'}
        set_enabled(ob, not enabled(ob))
        return {'FINISHED'}


class ALLSET_OT_light_isolate(bpy.types.Operator):
    """Light only with this light; press again to bring the others back (Maya Isolate)"""
    bl_idname = "allset.light_isolate"
    bl_label = "Isolate Light"
    bl_options = {'REGISTER', 'UNDO'}

    light: _NAME

    def execute(self, context):
        if context.scene.objects.get(self.light) is None:
            return {'CANCELLED'}
        isolate(context.scene, self.light)
        return {'FINISHED'}


def draw_list(layout, context):
    obs = lights(context)
    toolbar = layout.row(align=True)
    for kind, icon in CREATE:
        toolbar.operator("allset.create", text="", icon=icon).kind = kind
    if not obs:
        layout.label(text="No lights in the scene")
        return
    head = layout.row(align=True)
    split = head.split(factor=0.45)
    split.label(text="Name")
    rest = split.row(align=True)
    rest.label(text="Color")
    rest.label(text="Intensity")
    rest.label(text="On / Solo")
    solo = isolated(context.scene)
    col = layout.column(align=True)
    for ob in obs:
        row = col.row(align=True)
        split = row.split(factor=0.45, align=True)
        icon = {"ambientLight": 'WORLD', "volumeLight": 'MESH_UVSPHERE'}.get(
            ae_layout.light_kind(ob.data), 'LIGHT_' + {'POINT': 'POINT', 'SUN': 'SUN', 'SPOT': 'SPOT', 'AREA': 'AREA'}[ob.data.type])
        op = split.operator("allset.light_select", text=ob.name, icon=icon, depress=ob.select_get())
        op.light = ob.name
        rest = split.row(align=True)
        rest.prop(ob.data, "color", text="")
        rest.prop(ob.data, "allset_intensity", text="")
        on = enabled(ob)
        rest.operator("allset.light_enable", text="", icon='CHECKBOX_HLT' if on else 'CHECKBOX_DEHLT').light = ob.name
        rest.operator("allset.light_isolate", text="", icon='SOLO_ON' if solo == ob.name else 'SOLO_OFF',
                      depress=(solo == ob.name)).light = ob.name


def draw_property_editor(layout, context):
    from . import attribute_editor
    ob = lead(context)
    if ob is None:
        layout.label(text="Select a light")
        return
    head = layout.row(align=True)
    head.label(text=f"{ae_layout.light_type(ob.data)}:")
    head.prop(ob, "name", text="")
    row = layout.row(align=True)
    row.operator("allset.light_enable", text="Enable", depress=enabled(ob)).light = ob.name
    row.operator("allset.light_isolate", text="Isolate", depress=isolated(context.scene) == ob.name).light = ob.name
    sub = ae_layout.light_kind(ob.data) or ob.data.type
    sections = ae_layout.BY_KIND.get(sub, ([], None))[0]
    attribute_editor.draw_sections(layout, context, ob, ob.data, sections, f"le_{sub.lower()}")
    attribute_editor.draw_transform_channels(layout.column(), context, ob)


class _Panel:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CATEGORY

    @classmethod
    def poll(cls, context):
        return is_light_editor(context)


class ALLSET_PT_light_editor(_Panel, bpy.types.Panel):
    bl_label = "Light Editor"
    bl_order = 0

    def draw(self, context):
        from . import chrome
        chrome.paragraph(self.layout, context, NOTICE)
        draw_list(self.layout, context)


class ALLSET_PT_light_property_editor(_Panel, bpy.types.Panel):
    bl_label = "Property Editor - Light Editor"
    bl_order = 1

    def draw(self, context):
        draw_property_editor(self.layout, context)


classes = (ALLSET_OT_light_editor, ALLSET_OT_light_select, ALLSET_OT_light_enable, ALLSET_OT_light_isolate,
           ALLSET_PT_light_editor, ALLSET_PT_light_property_editor)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    _SPACES.clear()
