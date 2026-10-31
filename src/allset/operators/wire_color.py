# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Wireframe Color / Drawing Overrides colour index (#136).

Maya has two ways to colour a control's wire:

1. Display > Wireframe Color...: an option menu Indexed / RGB, a palette of the 8 user colours
   (userDefined 1-8 = colorIndex 24-31, ``userDefined_gui``), an RGB colour
   slider, Apply / Default / Close. Apply = ``cmds.color(userDefined=N)`` (useObjectColor 1, objectColor N - 1) or
   ``cmds.color(rgbColor=(r, g, b))`` (useObjectColor 2, wireColorRGB) on the selection; Default = ``cmds.color()``
   (useObjectColor 0) (``L2_wireframe_color_command``; window: Maya's Wireframe Color window).
2. Attribute Editor > Display > Drawing Overrides: overrideEnabled, overrideRGBColors (Index / RGB), overrideColor
   (index 0-31, 0 = default) and overrideColorRGB. Factory values all 0 / off (``L2_drawing_override_palette``).

The kit keeps the Maya state as ID properties (``OBJECT_KEY`` / ``OVERRIDE_KEY``) on the object or pose bone and
writes the Blender colour from it:

- object: ``Object.color`` — RNA subtype COLOR = scene linear (``Object.color`` subtype 'COLOR', bone
  ``custom.normal`` 'COLOR_GAMMA'), so Maya's sRGB values are converted. Blender draws an object's wire in
  ``Object.color`` only where the 3D View's ``shading.wireframe_color_type`` is 'OBJECT' (a view setting, not a
  preference): the kit switches it from 'THEME' to 'OBJECT' in the 3D Views of Maya workspaces only
  (``switch.is_maya_workspace``, not the Tool Box column) and marks those screens (``SCREEN_KEY``) so it can switch
  them back when no kit colour is left.
- joint / bone control: ``PoseBone.color`` palette 'CUSTOM', normal = the colour (sRGB, COLOR_GAMMA); select / active
  = the kit's selection colours (other selected white, lead #43ffa3 = ui/selection_wire.py) because Maya draws a
  selected control in the selection colours, not its own.

Which wins when both are set: the drawing override (enabled with an index > 0 or RGB), then the object colour
(a kit choice).
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatVectorProperty, IntProperty

# Maya's colorIndex palette, sRGB 0-1.
# Index 0 = the default colour (no override). Values only.
PALETTE = {
    1: (0.0, 0.0, 0.0), 2: (0.25, 0.25, 0.25), 3: (0.6, 0.6, 0.6), 4: (0.608, 0.0, 0.157),
    5: (0.0, 0.016, 0.376), 6: (0.0, 0.0, 1.0), 7: (0.0, 0.275, 0.098), 8: (0.149, 0.0, 0.263),
    9: (0.784, 0.0, 0.784), 10: (0.541, 0.282, 0.2), 11: (0.247, 0.137, 0.122), 12: (0.6, 0.149, 0.0),
    13: (1.0, 0.0, 0.0), 14: (0.0, 1.0, 0.0), 15: (0.0, 0.255, 0.6), 16: (1.0, 1.0, 1.0),
    17: (1.0, 1.0, 0.0), 18: (0.392, 0.863, 1.0), 19: (0.263, 1.0, 0.639), 20: (1.0, 0.69, 0.69),
    21: (0.894, 0.675, 0.475), 22: (1.0, 1.0, 0.388), 23: (0.0, 0.6, 0.329), 24: (0.8549, 0.5686, 0.4275),
    25: (0.8784, 0.7843, 0.3059), 26: (0.6353, 0.8118, 0.2784), 27: (0.2314, 0.7569, 0.5804),
    28: (0.2549, 0.8196, 0.7255), 29: (0.2274, 0.6157, 0.8078), 30: (0.6118, 0.4196, 0.8078),
    31: (0.8078, 0.349, 0.6549),
}
USER_FIRST = 24          # userDefined 1 = colorIndex 24 (``userDefined_gui`` equals colorIndex 24-31)
USER_COUNT = 8

OBJECT_KEY = "allset_object_color"   # Maya useObjectColor / objectColor / wireColorRGB: {"use", "index", "rgb"}
OVERRIDE_KEY = "allset_override"     # Maya overrideEnabled / overrideColor / overrideRGBColors / overrideColorRGB
SET_KEY = "allset_wire_set"          # the kit wrote this node's Blender colour (restore only those)
SCREEN_KEY = "allset_wire_object"    # the kit switched this screen's views to wireframe colour 'OBJECT'

LEAD = (0x43 / 255.0, 1.0, 0xa3 / 255.0)     # ui/selection_wire.LEAD (Maya lead)
OTHER = (1.0, 1.0, 1.0)                      # ui/selection_wire.OTHER (Maya other selected)
WHITE = (1.0, 1.0, 1.0, 1.0)                 # Object.color factory value


def user_color(n):
    """sRGB of Maya's user palette colour ``n`` (1-8)."""
    return PALETTE[USER_FIRST + n - 1]


def is_bone(node):
    return isinstance(node, bpy.types.PoseBone)


def _get(node, key, defaults):
    raw = node.get(key)
    out = dict(defaults)
    if raw is not None and hasattr(raw, "to_dict"):
        out.update(raw.to_dict())
    return out


def _object_state(node):
    return _get(node, OBJECT_KEY, {"use": 0, "index": 0, "rgb": [0.0, 0.0, 0.0]})


def _override_state(node):
    return _get(node, OVERRIDE_KEY, {"enabled": 0, "index": 0, "rgb": 0, "color": [0.0, 0.0, 0.0]})


def override_color(node):
    """sRGB of the node's drawing override, or None (not enabled / index 0 = default)."""
    st = _override_state(node)
    if not st["enabled"]:
        return None
    if st["rgb"]:
        return tuple(float(c) for c in st["color"])
    return PALETTE.get(int(st["index"]))


def object_color(node):
    """sRGB of the node's Wireframe Color (useObjectColor 1 = user colour objectColor + 1, 2 = RGB), or None."""
    st = _object_state(node)
    if st["use"] == 1:
        return user_color(int(st["index"]) + 1)
    if st["use"] == 2:
        return tuple(float(c) for c in st["rgb"])
    return None


def node_color(node):
    """The colour Maya draws the unselected wire in (sRGB), or None for the default."""
    c = override_color(node)
    return c if c is not None else object_color(node)


def _linear(c):
    from mathutils import Color
    lin = Color(tuple(c)[:3]).from_srgb_to_scene_linear()
    return (lin.r, lin.g, lin.b, 1.0)


def apply(node):
    """Write the Blender colour of ``node`` (object or pose bone) from its Maya state."""
    c = node_color(node)
    if is_bone(node):
        col = node.color
        if c is not None:
            col.palette = 'CUSTOM'
            col.custom.normal = c
            col.custom.select = OTHER
            col.custom.active = LEAD
            node[SET_KEY] = 1
        elif node.get(SET_KEY):
            col.palette = 'DEFAULT'
            del node[SET_KEY]
        return
    if c is not None:
        node.color = _linear(c)
        node[SET_KEY] = 1
    elif node.get(SET_KEY):
        node.color = WHITE
        del node[SET_KEY]


# --- 3D View wireframe colour mode ---------------------------------------------------------------------------

def _maya_view_spaces(screen):
    from ..ui import toolbox
    for area in screen.areas:
        if area.type != 'VIEW_3D':
            continue
        for space in area.spaces:
            if space.type == 'VIEW_3D' and not toolbox.is_toolbox(space):
                yield space


def _maya_screens():
    from .. import switch
    for window in bpy.context.window_manager.windows:
        if switch.is_maya_workspace(window.workspace) and window.screen is not None:
            yield window.screen


def any_object_colored():
    return any(ob.get(SET_KEY) for ob in bpy.data.objects)


def sync_views():
    """Maya layout views draw object wires in ``Object.color`` while a kit colour exists, Blender's theme otherwise
    (only views the kit switched go back)."""
    on = any_object_colored()
    for screen in _maya_screens():
        if on:
            changed = False
            for space in _maya_view_spaces(screen):
                if space.shading.wireframe_color_type == 'THEME':
                    space.shading.wireframe_color_type = 'OBJECT'
                    changed = True
            if changed:
                screen[SCREEN_KEY] = 1
    if on:
        return
    for screen in bpy.data.screens:
        if screen.get(SCREEN_KEY):
            for space in _maya_view_spaces(screen):
                if space.shading.wireframe_color_type == 'OBJECT':
                    space.shading.wireframe_color_type = 'THEME'
            del screen[SCREEN_KEY]


# --- Maya commands ----------------------------------------------------------------------------------------------

def color(nodes, ud=None, rgb=None):
    """Maya ``color [-ud N | -rgb r g b]`` on ``nodes``: user colour N (1-8), RGB, or neither = the default."""
    for node in nodes:
        st = _object_state(node)
        if ud is not None:
            st["use"], st["index"] = 1, int(ud) - 1
        elif rgb is not None:
            st["use"], st["rgb"] = 2, [float(v) for v in rgb[:3]]
        else:
            st["use"] = 0
        node[OBJECT_KEY] = st
        apply(node)
    sync_views()
    return len(nodes)


def set_override(node, enabled=None, index=None, rgb_mode=None, rgb=None):
    """Edit the node's Drawing Overrides (any argument left None keeps its value) and redraw it."""
    st = _override_state(node)
    if enabled is not None:
        st["enabled"] = int(bool(enabled))
    if index is not None:
        st["index"] = max(0, min(31, int(index)))
    if rgb_mode is not None:
        st["rgb"] = int(bool(rgb_mode))
    if rgb is not None:
        st["color"] = [float(v) for v in tuple(rgb)[:3]]
    node[OVERRIDE_KEY] = st
    apply(node)
    if not is_bone(node):
        sync_views()


def selection(context):
    """Maya's selection list: selected pose bones in pose mode, else selected objects (lead first)."""
    from ..ui import channel_box
    return channel_box.targets(context)


# --- Attribute Editor Drawing Overrides (RNA over the ID properties; ui/ae_layout.py rows) -------------------------

def _ov_enabled_get(self):
    return bool(_override_state(self)["enabled"])


def _ov_enabled_set(self, value):
    set_override(self, enabled=value)


def _ov_mode_get(self):
    return 1 if _override_state(self)["rgb"] else 0


def _ov_mode_set(self, value):
    set_override(self, rgb_mode=value == 1)


def _ov_index_get(self):
    return int(_override_state(self)["index"])


def _ov_index_set(self, value):
    set_override(self, index=value)


def _ov_color_get(self):
    st = _override_state(self)
    if st["rgb"]:
        return tuple(float(c) for c in st["color"])
    return PALETTE.get(int(st["index"]), (0.0, 0.0, 0.0))


def _ov_color_set(self, value):
    # Maya's RGB colour slider: editing the colour means RGB colours
    set_override(self, rgb_mode=True, rgb=value)


_OV_PROPS = {
    "allset_override_enabled": lambda: BoolProperty(
        name="Enable Overrides", get=_ov_enabled_get, set=_ov_enabled_set,
        description="Maya Drawing Overrides: draw this node's wire in the override colour"),
    "allset_override_mode": lambda: EnumProperty(
        name="Color", items=(('INDEX', "Index", "Maya colour index 0-31"), ('RGB', "RGB", "Any colour")),
        get=_ov_mode_get, set=_ov_mode_set, description="Maya overrideRGBColors"),
    "allset_override_index": lambda: IntProperty(
        name="Color Index", min=0, max=31, get=_ov_index_get, set=_ov_index_set,
        description="Maya overrideColor: colour index 0-31 (0 = default colour)"),
    "allset_override_color": lambda: FloatVectorProperty(
        name="Color", subtype='COLOR_GAMMA', size=3, min=0.0, max=1.0, get=_ov_color_get, set=_ov_color_set,
        description="The override colour (the index's colour; editing it switches to RGB, Maya overrideColorRGB)"),
}
_OWNERS = (bpy.types.Object, bpy.types.PoseBone)


# --- Display > Wireframe Color... window ------------------------------------------------------------------------

def _swatch_get(n):
    return lambda self: user_color(n)


def _apply_update(self, context):
    if not self.apply_now:
        return
    self.apply_now = False
    _run(self, context, 'APPLY')


def _default_update(self, context):
    if not self.default_now:
        return
    self.default_now = False
    _run(self, context, 'DEFAULT')


def _run(op, context, action):
    nodes = selection(context)
    if not nodes:
        op.report({'WARNING'}, "Select objects to colour")    # Maya: the color command needs a selection
        return 0
    if action == 'DEFAULT':
        n = color(nodes)
    elif op.color_type == 'INDEXED':
        n = color(nodes, ud=int(op.cell))
    else:
        n = color(nodes, rgb=tuple(op.rgb))
    from .. import undo_steps
    undo_steps.push("Wireframe Color")
    for area in context.screen.areas if context.screen else ():
        area.tag_redraw()
    return n


def _annotations():
    ann = {
        "color_type": EnumProperty(name="Color Type", items=(('INDEXED', "Indexed", "One of the 8 user colours"),
                                                             ('RGB', "RGB", "Any colour")), default='INDEXED'),
        "cell": EnumProperty(name="User Color", items=[(str(i), str(i), f"User colour {i}")
                                                       for i in range(1, USER_COUNT + 1)], default='1'),
        "rgb": FloatVectorProperty(name="Color", subtype='COLOR_GAMMA', size=3, min=0.0, max=1.0,
                                   default=(0.0, 0.0, 0.0)),        # Maya's slider starts black (-rgb 0 0 0)
        "action": EnumProperty(items=(('APPLY', "Apply", ""), ('DEFAULT', "Default", ""), ('CLOSE', "Close", "")),
                               default='APPLY', options={'HIDDEN', 'SKIP_SAVE'}),
        "apply_now": BoolProperty(name="Apply", options={'SKIP_SAVE'}, update=_apply_update,
                                  description="Colour the selected objects and keep the window open (Maya Apply)"),
        "default_now": BoolProperty(name="Default", options={'SKIP_SAVE'}, update=_default_update,
                                    description="Back to the default wire colour (like the Default button in Maya)"),
    }
    for i in range(1, USER_COUNT + 1):
        ann[f"swatch_{i}"] = FloatVectorProperty(name=f"User Color {i}", subtype='COLOR_GAMMA', size=3,
                                                 get=_swatch_get(i), options={'SKIP_SAVE'})
    return ann


class ALLSET_OT_wireframe_color(bpy.types.Operator):
    """Maya Wireframe Color: colour the selected objects' wire with a user colour or an RGB colour"""
    bl_idname = "allset.wireframe_color"
    bl_label = "Wireframe Color"
    bl_options = set()      # Apply / Default push their own undo step; Close changes nothing (no redo panel)
    __annotations__ = _annotations()

    def invoke(self, context, event):
        # Maya's window shows the first selected shape's colour
        nodes = selection(context)
        if nodes:
            st = _object_state(nodes[0])
            if st["use"] == 2:
                self.color_type, self.rgb = 'RGB', tuple(st["rgb"])
            else:
                self.color_type = 'INDEXED'
                self.cell = str(min(USER_COUNT, max(1, int(st["index"]) + 1)))
        self.action = 'CLOSE'
        return context.window_manager.invoke_props_dialog(self, width=300, title="Wireframe Color",
                                                          confirm_text="Close")

    def draw(self, context):
        layout = self.layout
        layout.row().prop(self, "color_type", text="")
        if self.color_type == 'INDEXED':
            row = layout.row(align=True)
            for i in range(1, USER_COUNT + 1):
                col = row.column(align=True)
                col.prop(self, f"swatch_{i}", text="")
                col.prop_enum(self, "cell", str(i))
        else:
            layout.prop(self, "rgb", text="")
        layout.separator()
        row = layout.row(align=True)
        row.prop(self, "apply_now", toggle=True)
        row.prop(self, "default_now", toggle=True)

    def execute(self, context):
        if self.action == 'CLOSE':
            return {'FINISHED'}
        return {'FINISHED'} if _run(self, context, self.action) else {'CANCELLED'}


classes = (ALLSET_OT_wireframe_color,)


def register_props():
    for owner in _OWNERS:
        for name, make in _OV_PROPS.items():
            setattr(owner, name, make())


def unregister_props():
    for owner in _OWNERS:
        for name in _OV_PROPS:
            if hasattr(owner, name):
                delattr(owner, name)
