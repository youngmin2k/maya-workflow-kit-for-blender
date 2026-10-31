# SPDX-License-Identifier: GPL-3.0-or-later
"""Key batch 3: Maya keys that had no or a wrong binding.

Maya commands (meanings from Maya's annotations):
- Ctrl+M ToggleMainMenubar: the main menu bar folds into Blender's top-bar menu button (``area.show_menus`` of the
  top bar, which the kit menu bar already follows: ui/status_line.draw_left).
- Alt+B CycleBackgroundColor: Maya's grey / light grey / gradient / black cycle in every view (see below).
- Alt+C ToggleColorFeedback (skin paint): the weight colours on / off (Weight Paint overlay opacity 1 <-> 0).
- u PaintOperationMarkingMenu: Maya's Artisan paint operations Replace / Add / Scale / Smooth (ui/paint_weights.py
  OPERATIONS) as a menu.
"""

import bpy
from bpy.props import EnumProperty

from .. import results

# Background: the Maya-style Alt+B background cycle is one global state for every viewport -
#   gradient on        -> background 0 0 0, gradient off
#   background == 0    -> 0.36 (default)
#   background <  0.5  -> 0.631
#   else               -> gradient on (backgroundTop #889db3 at the top, backgroundBottom #0d0d0d at the bottom)
# Values are display (sRGB) values: the default viewport pixel is #5c5c5c = 0.36.
#
# The kit never edits the user's theme (Blender's own gradient background is a theme setting), so the gradient is
# drawn by the kit: a view in the gradient state has the flat background colour ``GRADIENT_BASE`` (the middle of
# the ramp, a per-view setting saved with the file), and a POST_VIEW handler paints the ramp over that view's
# empty background (at the far plane with a depth test, before any other kit drawing, so the grid and everything
# else stays on top). Solid and Wireframe shading only, like the flat colours; where Blender keeps no depth for the
# background (the inside of an object in Wireframe without X-ray), the flat base colour shows. The gradient follows
# Tom Pilott's contribution (#224). A view that shows the user's theme background (``THEME``) counts as the default
# grey, so the first Alt+B gives light grey like in Maya.
FLAT, LIGHT, BLACK = 0.36, 0.631, 0.0
CYCLE = ("GREY", "LIGHT", "GRADIENT", "BLACK")
# Maya's gradient, top to bottom: (height from the top, display RGB 0-255)
RAMP = ((0.0, (136, 157, 179)), (0.1, (129, 150, 172)), (0.2, (121, 141, 163)), (0.3, (112, 132, 154)),
        (0.4, (102, 122, 143)), (0.5, (91, 110, 130)), (0.6, (79, 96, 115)), (0.7, (65, 80, 97)),
        (0.8, (51, 62, 75)), (0.9, (35, 41, 49)), (1.0, (13, 13, 13)))
GRADIENT_BASE = (91 / 255, 110 / 255, 130 / 255)    # display value of the flat colour that marks a gradient view


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c):
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def background_state(shading):
    """'GREY' / 'LIGHT' / 'GRADIENT' / 'BLACK' of a 3D View's shading, else the display value of its colour."""
    if is_gradient(shading):
        return "GRADIENT"
    if shading.background_type == 'THEME':
        return "GREY"                                # the user's theme background: the default starting point
    if shading.background_type != 'VIEWPORT':
        return FLAT                                  # world colour: read like Maya's flat background
    v = linear_to_srgb(shading.background_color[0])
    if abs(v - LIGHT) < 1e-3:
        return "LIGHT"
    if abs(v - FLAT) < 1e-3:
        return "GREY"
    if v < 1e-4:
        return "BLACK"
    return v


def is_gradient(shading):
    """True when ``shading`` (a 3D View's) shows the kit's Maya gradient."""
    return (shading.background_type == 'VIEWPORT'
            and all(abs(a - srgb_to_linear(b)) < 1e-4 for a, b in zip(shading.background_color, GRADIENT_BASE)))


def next_state(state):
    """Maya's Alt+B rule on a state or a display value."""
    if state == "GRADIENT":
        return "BLACK"
    value = {"GREY": FLAT, "LIGHT": LIGHT, "BLACK": BLACK}.get(state, state)
    if value == 0:
        return "GREY"
    if value < 0.5:
        return "LIGHT"
    return "GRADIENT"


def set_shading(shading, state, color=None):
    """A view's own flat background (``VIEWPORT``): Maya's grey / light grey / black, or ``color`` (display RGB)."""
    if color is not None:
        rgb = color
    elif state == "GRADIENT":
        rgb = GRADIENT_BASE
    else:
        rgb = ({"GREY": FLAT, "LIGHT": LIGHT}.get(state, BLACK),) * 3
    shading.background_type = 'VIEWPORT'
    shading.background_color = tuple(srgb_to_linear(c) for c in rgb)


def view_spaces():
    """Every 3D View of the file (Maya's background is one global setting), the Tool Box column excepted."""
    from ..ui import toolbox
    for screen in bpy.data.screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type == 'VIEW_3D' and not toolbox.is_toolbox(space):
                    yield area, space


def apply_background(state, color=None):
    """Put every 3D View in a Maya background state ('GREY' / 'LIGHT' / 'GRADIENT' / 'BLACK' / 'CUSTOM' + color)."""
    for area, space in view_spaces():
        set_shading(space.shading, state, color)
        area.tag_redraw()


def cycle_background(shading):
    """Next Maya background (Alt+B) read from ``shading`` (the view under the mouse), applied to every view."""
    state = next_state(background_state(shading))
    apply_background(state)
    set_shading(shading, state)      # also when ``shading`` isn't a view (the scene's display shading in tests)
    return state


def reset_background():
    """the default background (flat 0.36) in every view: promotional / comparison shots use it."""
    apply_background("GREY")


class ALLSET_OT_cycle_background(bpy.types.Operator):
    """Cycle the viewport background (Maya Alt+B): grey, light grey, gradient, black"""
    bl_idname = "allset.cycle_background"
    bl_label = "Cycle Background Color"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space is not None and space.type == 'VIEW_3D'

    def execute(self, context):
        state = cycle_background(context.space_data.shading)
        results.result(self, f"Background: {state.title()}")
        return {'FINISHED'}


def _dialog_values(op):
    shading = next((space.shading for _area, space in view_spaces()), None)
    if shading is not None and shading.background_type == 'VIEWPORT':
        op.background = tuple(linear_to_srgb(c) for c in shading.background_color)
    else:
        op.background = (FLAT,) * 3


class ALLSET_OT_color_settings(bpy.types.Operator):
    """Flat viewport background color (Maya Windows > Settings/Preferences > Color Settings: 3D Views Background)"""
    bl_idname = "allset.color_settings"
    bl_label = "Color Settings"
    bl_options = {'REGISTER'}

    background: bpy.props.FloatVectorProperty(name="Background", subtype='COLOR_GAMMA', size=3, min=0.0, max=1.0,
                                              default=(FLAT,) * 3)

    def invoke(self, context, event):
        _dialog_values(self)
        return context.window_manager.invoke_props_dialog(self, title="Color Settings", confirm_text="Apply")

    def draw(self, context):
        col = self.layout.column()
        col.use_property_split = True
        col.label(text="3D Views")
        col.prop(self, "background")

    def execute(self, context):
        if all(abs(c - FLAT) < 1e-3 for c in self.background):
            apply_background("GREY")
        else:
            apply_background("CUSTOM", color=tuple(self.background))
        return {'FINISHED'}


def top_bar(context):
    """The window's top bar area (a global area, remembered while the kit menu bar draws: ui/status_line)."""
    from ..ui import status_line
    window = context.window
    return status_line._top_bars.get(window.as_pointer()) if window is not None else None


class ALLSET_OT_main_menubar_toggle(bpy.types.Operator):
    """Show or hide the main menu bar (Maya Ctrl+M): the menus fold into the top bar's menu button"""
    bl_idname = "allset.main_menubar_toggle"
    bl_label = "Toggle Main Menu Bar"
    bl_options = {'REGISTER'}

    def execute(self, context):
        area = top_bar(context)
        if area is None:
            return {'CANCELLED'}
        try:
            area.show_menus = not area.show_menus
            area.tag_redraw()
        except ReferenceError:
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_color_feedback(bpy.types.Operator):
    """Show or hide the weight colours while painting skin weights (Maya Alt+C, Toggle Color Feedback)"""
    bl_idname = "allset.color_feedback"
    bl_label = "Toggle Color Feedback"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space is not None and space.type == 'VIEW_3D'

    def execute(self, context):
        overlay = context.space_data.overlay
        overlay.weight_paint_mode_opacity = 0.0 if overlay.weight_paint_mode_opacity > 0.0 else 1.0
        return {'FINISHED'}


PAINT_OPERATIONS = (("MIX", "Replace"), ("ADD", "Add"), ("MUL", "Scale"), ("SMOOTH", "Smooth"))


class ALLSET_OT_paint_operation(bpy.types.Operator):
    """Maya paint operation of the skin weight brush: Replace / Add / Scale (brush blend) or Smooth (Blur tool)"""
    bl_idname = "allset.paint_operation"
    bl_label = "Paint Operation"
    bl_options = {'REGISTER', 'UNDO'}

    operation: EnumProperty(items=[(k, label, "") for k, label in PAINT_OPERATIONS])

    @classmethod
    def poll(cls, context):
        return context.mode == 'PAINT_WEIGHT'

    def execute(self, context):
        if self.operation == "SMOOTH":
            return bpy.ops.wm.tool_set_by_id(name="builtin_brush.Blur")
        brush = context.tool_settings.weight_paint.brush
        if brush is None:
            return {'CANCELLED'}
        brush.blend = self.operation
        return {'FINISHED'}


class ALLSET_MT_paint_operation(bpy.types.Menu):
    """Maya Artisan paint operation marking menu (u)"""
    bl_idname = "ALLSET_MT_paint_operation"
    bl_label = "Paint Operation"

    def draw(self, context):
        brush = getattr(context.tool_settings.weight_paint, "brush", None)
        for key, label in PAINT_OPERATIONS:
            on = brush is not None and brush.blend == key
            self.layout.operator(ALLSET_OT_paint_operation.bl_idname, text=label,
                                 icon='RADIOBUT_ON' if on else 'RADIOBUT_OFF').operation = key


# --- gradient drawing ----------------------------------------------------------------------

_handle = []
_gpu = {}


def ramp_rows():
    """(NDC y, linear RGBA) rows of the gradient from the top (y 1) to the bottom (y -1)."""
    return [(1.0 - 2.0 * h, tuple(srgb_to_linear(v / 255) for v in rgb) + (1.0,)) for h, rgb in RAMP]


def _batch():
    if "batch" not in _gpu:
        import gpu
        from gpu_extras.batch import batch_for_shader
        iface = gpu.types.GPUStageInterfaceInfo("allset_ramp_iface")
        iface.smooth('VEC4', 'ramp_color')
        info = gpu.types.GPUShaderCreateInfo()
        info.vertex_in(0, 'VEC2', 'pos')
        info.vertex_in(1, 'VEC4', 'color')
        info.vertex_out(iface)
        info.fragment_out(0, 'VEC4', 'fragColor')
        # z = w: the far plane, so the depth test keeps the ramp to the empty background
        info.vertex_source("void main() { gl_Position = vec4(pos, 1.0, 1.0); ramp_color = color; }")
        info.fragment_source("void main() { fragColor = ramp_color; }")
        shader = gpu.shader.create_from_info(info)
        pos, col, idx = [], [], []
        for k, (y, c) in enumerate(ramp_rows()):
            pos += [(-1.0, y), (1.0, y)]
            col += [c, c]
            if k:
                a = 2 * (k - 1)
                idx += [(a, a + 1, a + 2), (a + 1, a + 3, a + 2)]
        _gpu.update(shader=shader, batch=batch_for_shader(shader, 'TRIS', {"pos": pos, "color": col}, indices=idx))
    return _gpu["shader"], _gpu["batch"]


def _draw_gradient():
    space = bpy.context.space_data
    if space is None or space.type != 'VIEW_3D':
        return
    shading = space.shading
    if shading.type not in {'SOLID', 'WIREFRAME'} or not is_gradient(shading):
        return
    import gpu
    shader, batch = _batch()
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.depth_mask_set(False)
    gpu.state.blend_set('NONE')
    shader.bind()
    batch.draw(shader)
    gpu.state.depth_test_set('NONE')


def register_handlers():
    """Before the kit's other 3D View POST_VIEW handlers (handlers draw in the order they were added)."""
    if not _handle and not bpy.app.background:
        _handle.append(bpy.types.SpaceView3D.draw_handler_add(_draw_gradient, (), 'WINDOW', 'POST_VIEW'))


def unregister_handlers():
    while _handle:
        bpy.types.SpaceView3D.draw_handler_remove(_handle.pop(), 'WINDOW')
    _gpu.clear()


classes = (ALLSET_OT_cycle_background, ALLSET_OT_color_settings, ALLSET_OT_main_menubar_toggle, ALLSET_OT_color_feedback,
           ALLSET_OT_paint_operation, ALLSET_MT_paint_operation)
