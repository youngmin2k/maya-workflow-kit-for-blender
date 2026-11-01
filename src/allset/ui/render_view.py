# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Render View = Blender's Image Editor showing Render Result.

Maya's Render View toolbar has Render, IPR,
Keep Image and Remove Image: kept images stay in a strip to compare with the next render. Blender's Render
Result has render slots (J / Alt+J switch between them), and a render goes into the active slot, so:

- Keep Image = record the shown slot as kept (``allset_kept`` on the Render Result image) and make the first
  slot that isn't kept active (a new slot when all are), so the next render doesn't replace the kept one;
- Remove Image = clear the shown slot and forget it.

The buttons are drawn at the start of the Image Editor header when it shows Render Result (``ui/shelf.py`` already
wraps ``IMAGE_HT_header.draw`` and calls ``draw_header`` first). ``ALLSET_MT_render_using`` = Render > Render Using
(the scene's render engine).
"""

import bpy

from .. import results

KEPT_PROP = "allset_kept"
KEEP_TIP = "Maya Keep Image = Blender Render Slot (J / Alt+J to compare)"


def render_result():
    return next((i for i in bpy.data.images if i.type == 'RENDER_RESULT'), None)


def kept(image):
    return {int(i) for i in image.get(KEPT_PROP, [])}


def keep(image):
    """Keep the active slot; the slot the next render goes into (its index)."""
    slots = image.render_slots
    done = kept(image) | {slots.active_index}
    image[KEPT_PROP] = sorted(done)
    free = next((i for i in range(len(slots)) if i not in done), None)
    if free is None:
        slots.new()
        free = len(slots) - 1
    slots.active_index = free
    return free


def remove(image, image_user=None):
    """Clear the active slot (when the editor's image user is known) and forget that it was kept."""
    slots = image.render_slots
    index = slots.active_index
    if image_user is not None:
        slots[index].clear(image_user)
    done = kept(image) - {index}
    image[KEPT_PROP] = sorted(done)
    return index


class ALLSET_OT_render_keep_image(bpy.types.Operator):
    """Keep this image: the next render goes into a new render slot (Maya Render View Keep Image).
Blender: Render Slots, J / Alt+J to compare"""
    bl_idname = "allset.render_keep_image"
    bl_label = "Keep Image"

    @classmethod
    def poll(cls, context):
        return render_result() is not None

    def execute(self, context):
        image = render_result()
        index = keep(image)
        results.result(self, f"Kept; next render goes to {image.render_slots[index].name}")
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_render_remove_image(bpy.types.Operator):
    """Remove the shown image (clear this render slot) (Maya Render View Remove Image)"""
    bl_idname = "allset.render_remove_image"
    bl_label = "Remove Image"

    @classmethod
    def poll(cls, context):
        return render_result() is not None

    def execute(self, context):
        space = context.space_data
        user = space.image_user if space is not None and space.type == 'IMAGE_EDITOR' else None
        remove(render_result(), user)
        _redraw(context)
        return {'FINISHED'}


def _redraw(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'IMAGE_EDITOR':
                area.tag_redraw()


class ALLSET_MT_render_using(bpy.types.Menu):
    """Render engine of the scene (Maya Render > Render Using)"""
    bl_idname = "ALLSET_MT_render_using"
    bl_label = "Render Using"

    def draw(self, context):
        self.layout.props_enum(context.scene.render, "engine")


TEST_PERCENTAGES = (100, None, 10, 25, 50, 75, None, 110, 125, 150)     # None = a divider


class ALLSET_MT_test_resolution(bpy.types.Menu):
    """Blender's Resolution % of the Output properties (Maya Render > Test Resolution): it sets the size of every
    render"""
    bl_idname = "ALLSET_MT_test_resolution"
    bl_label = "Test Resolution"

    def draw(self, context):
        r = context.scene.render
        for perc in TEST_PERCENTAGES:
            if perc is None:
                self.layout.separator()
                continue
            w, h = r.resolution_x * perc // 100, r.resolution_y * perc // 100
            text = f"Render Settings ({w}x{h})" if perc == 100 else f"{perc}% Settings ({w}x{h})"
            op = self.layout.operator("wm.context_set_int", text=text,
                                      icon='CHECKBOX_HLT' if r.resolution_percentage == perc else 'CHECKBOX_DEHLT')
            op.data_path, op.value = "scene.render.resolution_percentage", perc


def draw_header(layout, context):
    """Maya Render View toolbar buttons for an Image Editor showing Render Result."""
    space = context.space_data
    image = getattr(space, "image", None)
    if image is None or image.type != 'RENDER_RESULT':
        return
    row = layout.row(align=True)
    row.operator("allset.render", text="Render", icon='RENDER_STILL')
    row.operator("allset.render_keep_image", text="Keep Image", icon='PINNED')
    row.operator("allset.render_remove_image", text="Remove Image", icon='X')
    slots = image.render_slots
    done = kept(image)
    row.label(text=f"{slots.active.name}{' (kept)' if slots.active_index in done else ''} · {len(done)} kept")
    layout.separator()


classes = (ALLSET_OT_render_keep_image, ALLSET_OT_render_remove_image, ALLSET_MT_render_using,
           ALLSET_MT_test_resolution)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
