# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Layer Editor (Display Layers) wrapped on collections.

Maya's Layer Editor.
A display layer is a child collection of a "Display Layers" collection that
is excluded from every view layer, so layers are membership lists that do
not change the scene hierarchy or visibility by themselves. The layer state
is an override on its member objects that never changes their own Maya
attributes (#26; the object's visibility is ``hide_viewport``):
  V (visible)  -> the view-layer flag (``hide_set``)
  T (template) -> unselectable, wireframe; R (reference) -> unselectable
                  (the member's own display type / selectability are kept in ``OWN`` and put back)
  P (playback) -> off: members hidden (view-layer flag) while animation plays
An object belongs to at most one display layer, like Maya.
"""


import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, IntProperty, PointerProperty

from .. import i18n
from . import chrome
from ..operators import naming

ROOT_NAME = "Display Layers"
TYPES = (("NORMAL", "Normal", "Selectable, normal display"),
         ("TEMPLATE", "Template", "Unselectable, wireframe (Maya T)"),
         ("REFERENCE", "Reference", "Unselectable (Maya R)"))
TYPE_LETTER = {"NORMAL": " ", "TEMPLATE": "T", "REFERENCE": "R"}


def _update(self, context):
    coll = self.id_data
    if self.is_layer:
        apply_layer(coll)


class ALLSET_PG_layer(bpy.types.PropertyGroup):
    is_layer: BoolProperty(options={'HIDDEN'})
    visible: BoolProperty(name="Visible", default=True, update=_update,
                          description="Show the layer's objects (Maya V)")
    playback: BoolProperty(name="Playback", default=True, update=_update,
                           description="Show the layer's objects during playback (Maya P)")
    display_type: EnumProperty(name="Display Type", items=TYPES, default="NORMAL", update=_update)
    # list position: Maya lists the newest layer on top and Move Up / Down reorders (Maya 2022 Layer Editor)
    order: IntProperty(options={'HIDDEN'})


# --- data helpers -------------------------------------------------------------------------------

def root(scene, create=False):
    coll = scene.collection.children.get(ROOT_NAME)
    if coll is None and create:
        coll = bpy.data.collections.new(ROOT_NAME)
        scene.collection.children.link(coll)
        for vl in scene.view_layers:
            lc = vl.layer_collection.children.get(coll.name)
            if lc is not None:
                lc.exclude = True
    return coll


def layers(scene):
    r = root(scene)
    return [c for c in r.children if c.allset_layer.is_layer] if r else []


def display_order(scene):
    """Layers top to bottom as Maya lists them: highest ``order`` (newest) first."""
    ls = layers(scene)
    return sorted(ls, key=lambda c: (-c.allset_layer.order, -ls.index(c)))


def move_layer(scene, coll, delta):
    """Move ``coll`` ``delta`` rows down the list (-1 = up)."""
    seq = display_order(scene)
    i = seq.index(coll)
    j = max(0, min(len(seq) - 1, i + delta))
    if i == j:
        return False
    seq.insert(j, seq.pop(i))
    for n, c in enumerate(reversed(seq)):
        c.allset_layer.order = n + 1
    return True


def layer_of(ob, scene):
    for coll in layers(scene):
        if ob.name in coll.objects:
            return coll
    return None


def next_layer_name():
    """Maya ``layer<N>``: one past the highest, gaps not filled."""
    return f"layer{naming.next_number('layer', {c.name for c in bpy.data.collections})}"


OWN = "allset_layer_own"   # the member's own display_type / hide_select while a layer overrides them


def _layer_hide(ob, hidden):
    """The layer's V / P: the view-layer flag, never the object's own visibility (hide_viewport)."""
    for vl in bpy.context.scene.view_layers if bpy.context.scene else ():
        try:
            if ob.hide_get(view_layer=vl) != hidden:
                ob.hide_set(hidden, view_layer=vl)
        except RuntimeError:   # not in this view layer
            pass


def _override_display(ob, display_type, unselectable):
    if OWN not in ob:
        ob[OWN] = {"display_type": ob.display_type, "hide_select": bool(ob.hide_select)}
    ob.display_type = display_type
    ob.hide_select = unselectable


def _restore_display(ob):
    own = ob.get(OWN)
    if own is None:
        return
    ob.display_type = own.get("display_type", 'TEXTURED')
    ob.hide_select = bool(own.get("hide_select", False))
    del ob[OWN]


def apply_object(ob, layer):
    """Apply a layer's state to one member (None = back to the object's own state). Maya: a display layer is an
    override (drawOverride) that never changes the node's own attributes (#26)."""
    if layer is None:
        _layer_hide(ob, False)
        _restore_display(ob)
        return
    st = layer.allset_layer
    _layer_hide(ob, not st.visible)
    if st.display_type == "NORMAL":
        _restore_display(ob)
    else:
        own = ob.get(OWN)
        own_type = own.get("display_type", ob.display_type) if own is not None else ob.display_type
        _override_display(ob, 'WIRE' if st.display_type == "TEMPLATE" else own_type, True)


def apply_layer(coll):
    for ob in coll.objects:
        apply_object(ob, coll)
    from ..operators import dag
    dag.sync()                      # a hidden layer hides its members' children too (Maya)


def new_layer(scene, objects=()):
    top = max((c.allset_layer.order for c in layers(scene)), default=0)
    coll = bpy.data.collections.new(next_layer_name())
    root(scene, create=True).children.link(coll)
    coll.allset_layer.is_layer = True
    coll.allset_layer.order = top + 1
    add_objects(scene, coll, objects)
    return coll


def add_objects(scene, coll, objects):
    for ob in objects:
        old = layer_of(ob, scene)
        if old is not None and old != coll:
            old.objects.unlink(ob)
        if ob.name not in coll.objects:
            coll.objects.link(ob)
        apply_object(ob, coll)


def remove_objects(scene, coll, objects):
    for ob in objects:
        if ob.name in coll.objects:
            coll.objects.unlink(ob)
            apply_object(ob, None)


def delete_layer(scene, coll):
    remove_objects(scene, coll, list(coll.objects))
    bpy.data.collections.remove(coll)


def active_layer(context):
    ls = layers(context.scene)
    i = context.scene.allset_layer_index
    return ls[i] if 0 <= i < len(ls) else None


# --- playback (P) -------------------------------------------------------------------------------

_hidden_for_playback = []


@persistent
def on_playback_pre(scene, *_args):
    _hidden_for_playback.clear()
    for coll in layers(scene):
        st = coll.allset_layer
        if st.visible and not st.playback:
            for ob in coll.objects:
                _layer_hide(ob, True)
                _hidden_for_playback.append(ob.name)


@persistent
def on_playback_post(scene, *_args):
    for name in _hidden_for_playback:
        ob = bpy.data.objects.get(name)
        if ob is not None:
            _layer_hide(ob, False)
    _hidden_for_playback.clear()


# --- operators -----------------------------------------------------------------------------------

class _LayerOp:
    bl_options = {'REGISTER', 'UNDO'}


class ALLSET_OT_layer_new(_LayerOp, bpy.types.Operator):
    """Create a display layer (optionally with the selected objects)"""
    bl_idname = "allset.layer_new"
    bl_label = "New Layer"

    selected: BoolProperty(name="Assign Selected", default=False)

    def execute(self, context):
        objs = list(context.selected_objects) if self.selected else []
        coll = new_layer(context.scene, objs)
        context.scene.allset_layer_index = layers(context.scene).index(coll)
        return {'FINISHED'}


class ALLSET_OT_layer_assign(_LayerOp, bpy.types.Operator):
    """Add (or remove) the selected objects to the active display layer"""
    bl_idname = "allset.layer_assign"
    bl_label = "Add Selected Objects"

    remove: BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        return active_layer(context) is not None

    def execute(self, context):
        coll = active_layer(context)
        fn = remove_objects if self.remove else add_objects
        fn(context.scene, coll, list(context.selected_objects))
        return {'FINISHED'}


class ALLSET_OT_layer_select(_LayerOp, bpy.types.Operator):
    """Select the objects of the active display layer"""
    bl_idname = "allset.layer_select"
    bl_label = "Select Objects"

    @classmethod
    def poll(cls, context):
        return active_layer(context) is not None

    def execute(self, context):
        coll = active_layer(context)
        for ob in context.view_layer.objects:
            ob.select_set(ob.name in coll.objects and not ob.hide_select)
        return {'FINISHED'}


class ALLSET_OT_layer_delete(_LayerOp, bpy.types.Operator):
    """Delete the active display layer (its objects stay, back to normal display)"""
    bl_idname = "allset.layer_delete"
    bl_label = "Delete Layer"

    @classmethod
    def poll(cls, context):
        return active_layer(context) is not None

    def execute(self, context):
        delete_layer(context.scene, active_layer(context))
        context.scene.allset_layer_index = max(0, context.scene.allset_layer_index - 1)
        return {'FINISHED'}


class ALLSET_OT_layer_cycle_type(_LayerOp, bpy.types.Operator):
    """Cycle display type: normal -> template (T) -> reference (R)"""
    bl_idname = "allset.layer_cycle_type"
    bl_label = "Cycle Layer Type"

    layer: bpy.props.StringProperty()

    def execute(self, context):
        coll = bpy.data.collections.get(self.layer)
        if coll is None:
            return {'CANCELLED'}
        order = [t[0] for t in TYPES]
        st = coll.allset_layer
        st.display_type = order[(order.index(st.display_type) + 1) % len(order)]
        return {'FINISHED'}


class ALLSET_OT_layer_toggle(_LayerOp, bpy.types.Operator):
    """Toggle the layer's visibility (V) or playback (P)"""
    bl_idname = "allset.layer_toggle"
    bl_label = "Toggle Layer"

    layer: bpy.props.StringProperty()
    attr: EnumProperty(items=(("visible", "Visible", "Maya V"), ("playback", "Playback", "Maya P")))

    @classmethod
    def description(cls, context, props):
        return ("Visibility (Maya V): show or hide the layer's objects" if props.attr == "visible" else
                "Playback (Maya P): show the layer's objects while animation plays")

    def execute(self, context):
        coll = bpy.data.collections.get(self.layer)
        if coll is None:
            return {'CANCELLED'}
        st = coll.allset_layer
        setattr(st, self.attr, not getattr(st, self.attr))
        return {'FINISHED'}


class ALLSET_OT_layer_move(_LayerOp, bpy.types.Operator):
    """Move the selected layer up or down in the list (Maya Layer Editor arrows)"""
    bl_idname = "allset.layer_move"
    bl_label = "Move Layer"

    direction: EnumProperty(items=(("UP", "Up", "Move selection up in list"),
                                   ("DOWN", "Down", "Move selection down in list")))

    @classmethod
    def description(cls, context, props):
        return f"Move selection {props.direction.lower()} in list"

    @classmethod
    def poll(cls, context):
        return active_layer(context) is not None

    def execute(self, context):
        coll = active_layer(context)
        move_layer(context.scene, coll, -1 if self.direction == "UP" else 1)
        context.scene.allset_layer_index = layers(context.scene).index(coll)
        return {'FINISHED'}


class ALLSET_OT_layer_empty(_LayerOp, bpy.types.Operator):
    """Remove every object from the selected layer (Maya Empty the Layer)"""
    bl_idname = "allset.layer_empty"
    bl_label = "Empty the Layer"

    @classmethod
    def poll(cls, context):
        return active_layer(context) is not None

    def execute(self, context):
        coll = active_layer(context)
        remove_objects(context.scene, coll, list(coll.objects))
        return {'FINISHED'}


class ALLSET_OT_layer_set_type(_LayerOp, bpy.types.Operator):
    """Set the selected layer's display type (Maya Set Selected Layers)"""
    bl_idname = "allset.layer_set_type"
    bl_label = "Set Layer Type"

    display_type: EnumProperty(items=TYPES)

    @classmethod
    def poll(cls, context):
        return active_layer(context) is not None

    def execute(self, context):
        active_layer(context).allset_layer.display_type = self.display_type
        return {'FINISHED'}


# --- UI ------------------------------------------------------------------------------------------

# Maya layer row: three 20x14 boxes V / P / type with 3 px gaps, a 16x14
# colour swatch, then the name as plain text, rows 20 px: boxes one UI unit wide in a left-aligned row (natural
# widths, small gaps).
BOX_UNITS = 1.4
SWATCH_UNITS = 0.9


class ALLSET_UL_layers(bpy.types.UIList):
    """Maya display layer rows: newest on top (``order``), click = select the layer, double-click = rename"""

    def filter_items(self, context, data, propname):
        items = list(getattr(data, propname))
        flags = [self.bitflag_filter_item if c.allset_layer.is_layer else 0 for c in items]
        # neworder[i] = display position of item i: highest order first (Maya lists the newest layer on top)
        ranked = sorted(range(len(items)), key=lambda i: (-items[i].allset_layer.order, -i))
        neworder = [0] * len(items)
        for pos, i in enumerate(ranked):
            neworder[i] = pos
        return flags, neworder

    def draw_filter(self, context, layout):
        pass   # Maya's layer list has no filter / sort options

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        st = item.allset_layer
        row = layout.row(align=False)
        boxes = row.row(align=True)
        boxes.alignment = 'LEFT'           # natural widths: fixed boxes, the name takes the rest
        for attr, letter in (("visible", "V"), ("playback", "P")):
            cell = boxes.row(align=True)
            cell.ui_units_x = BOX_UNITS
            op = cell.operator("allset.layer_toggle", text=letter if getattr(st, attr) else " ")
            op.layer, op.attr = item.name, attr
            boxes.separator(factor=0.3)
        cell = boxes.row(align=True)
        cell.ui_units_x = BOX_UNITS
        cell.operator("allset.layer_cycle_type", text=TYPE_LETTER[st.display_type]).layer = item.name
        sw = boxes.row(align=True)
        sw.ui_units_x = SWATCH_UNITS
        sw.prop(item, "color_tag", text="", icon_only=True, emboss=False)
        row.prop(item, "name", text="", emboss=False)


LAYER_MENU = (   # Maya's layer RMB menu
    ("allset.layer_assign", "Add Selected Objects", {"remove": False}),
    ("allset.layer_assign", "Remove Selected Objects", {"remove": True}),
    ("allset.layer_select", "Select Objects", {}),
    None,
    ("allset.layer_set_type", "Set Normal", {"display_type": "NORMAL"}),
    ("allset.layer_set_type", "Set Template", {"display_type": "TEMPLATE"}),
    ("allset.layer_set_type", "Set Reference", {"display_type": "REFERENCE"}),
    None,
    ("allset.layer_empty", "Empty the Layer", {}),
    ("allset.layer_delete", "Delete Layer", {}),
)


def draw_layer_items(layout):
    for entry in LAYER_MENU:
        if entry is None:
            layout.separator()
            continue
        idname, text, props = entry
        op = layout.operator(idname, text=text)
        for k, v in props.items():
            setattr(op, k, v)


def draw_anim_layer_mode(layout, context):
    """Maya's Override / Additive choice for the selected layer (its layer menu), as two check items."""
    from ..operators import anim_layers
    sel = anim_layers.selected(context.scene)
    if sel is None or sel.name == anim_layers.BASE:
        return
    layout.separator()
    layout.prop(sel, "override", text="Override")
    layout.prop(sel, "override", text="Additive", invert_checkbox=True)


class ALLSET_MT_le_layers(bpy.types.Menu):
    """Maya Layer Editor Layers menu"""
    bl_label = "Layers"

    def draw(self, context):
        lay = self.layout
        if context.window_manager.allset_le_tab == 'ANIM':
            draw_anim_layer_items(lay, context)
            draw_anim_layer_mode(lay, context)
            return
        lay.operator("allset.layer_new", text="Create Empty Layer").selected = False
        lay.operator("allset.layer_new", text="Create Layer from Selected").selected = True
        lay.separator()
        draw_layer_items(lay)


def is_layer_button(context):
    """The button under the mouse belongs to a display layer row (for its RMB menu)."""
    op = getattr(context, "button_operator", None)
    if op is not None and op.bl_rna.identifier in ("ALLSET_OT_layer_toggle", "ALLSET_OT_layer_cycle_type"):
        return True
    ptr = getattr(context, "button_pointer", None)
    return isinstance(ptr, bpy.types.Collection) and getattr(ptr.allset_layer, "is_layer", False)


def draw_button_menu(self, context):
    """Maya's layer RMB menu on top of Blender's button context menu (a C menu, not a keymap item)."""
    row = anim_layer_row(context)
    if row is not None:
        draw_anim_row_menu(self.layout, context, row)
        self.layout.separator()
        return
    if not is_layer_button(context):
        return
    draw_layer_items(self.layout)
    self.layout.separator()


class ALLSET_MT_le_options(bpy.types.Menu):
    """Maya Layer Editor Options menu"""
    bl_label = "Options"

    def draw(self, context):
        for label in ("Make New Layers Current", "Add New Objects to Current Layer", "Auto Overwrite",
                      "Show Namespace"):
            chrome.grey(self.layout, label)


class ALLSET_MT_le_help(bpy.types.Menu):
    bl_label = "Help"

    def draw(self, context):
        self.layout.operator("wm.url_open", text="Help on Display Layers (Blender collections)").url = HELP_URL


HELP_URL = "https://docs.blender.org/manual/en/5.2/scene_layout/collections/collections.html"
# Maya Layer Editor: tabs Display / Anim, menu bar Layers / Options / Help,
# toolbar on the right.
TABS = (('DISPLAY', "Display", "Display layers"), ('ANIM', "Anim", "Animation layers"))
MENU_BAR = (("Layers", "ALLSET_MT_le_layers"), ("Options", "ALLSET_MT_le_options"), ("Help", "ALLSET_MT_le_help"))

# Maya Anim tab Layers menu (Maya order and labels): the items the kit's
# NLA layers carry (operators/anim_layers.py, operators/anim_layers_204.py). Zero Key Layer is a Maya
# toolbar button (also on the kit toolbar), kept here after Merge Layers.
ANIM_LAYER_MENU = (
    ("allset.anim_layer_create", "Create Empty Layer", {"from_selected": False}),
    ("allset.anim_layer_create", "Create Layer from Selected", {"from_selected": True}),
    None,
    ("allset.anim_layer_members", "Add Selected Objects", {"add": True}),
    ("allset.anim_layer_members", "Remove Selected Objects", {"add": False}),
    ("allset.anim_layer_extract", "Extract Selected Objects", {}),
    None,
    ("allset.anim_layer_duplicate", "Duplicate Layer", {"no_animation": False}),
    ("allset.anim_layer_duplicate", "Duplicate Layer (No Animation)", {"no_animation": True}),
    ("allset.anim_layer_merge", "Merge Layers", {}),
    ("allset.anim_layer_zero_key", "Zero Key Layer", {}),
    None,
    ("allset.anim_layer_extract", "Extract Non-Layered Animation for Selected Objects", {"base": True}),
    ("allset.anim_layer_extract", "Extract Non-Layered Animation for All Objects", {"all_objects": True}),
    None,
    ("allset.anim_layer_delete", "Delete", {}),
    ("allset.anim_layer_empty", "Empty", {}),
    ("allset.anim_layer_delete_empty", "Delete Empty Layers", {}),
)
# Maya's Anim tab toolbar, left part (Zero Key / Zero Weight / Full Weight buttons;
# Blender icons until kit glyphs are drawn)
ANIM_TOOLBAR = (
    ("allset.anim_layer_zero_key", 'KEYFRAME', {}),
    ("allset.anim_layer_key_weight", 'KEY_DEHLT', {"weight": 0.0}),
    ("allset.anim_layer_key_weight", 'KEY_HLT', {"weight": 1.0}),
)
# Maya's row buttons, left of the name: Lock, Solo, Mute (24 px pitch,
# BaseAnimation only Lock); icons (off, on) instead of Maya's padlock / rectangle / circle-slash images
ANIM_TOGGLES = (("lock", ('UNLOCKED', 'LOCKED')), ("solo", ('SOLO_OFF', 'SOLO_ON')),
                ("mute", ('MUTE_IPO_OFF', 'MUTE_IPO_ON')))


# Maya greys these Layers menu items while BaseAnimation is among the selected layers
# (Add / Remove Selected Objects, Select Objects, Select Branch / Layer Node,
# Export, Membership, Attribute Editor, Delete, Empty, Delete Empty Layers, Layer Mode). With no layer selected Maya
# enables everything; the kit always has a selected layer.
GREY_WITH_BASE = ("Add Selected Objects", "Remove Selected Objects", "Delete", "Empty", "Delete Empty Layers")
# Layer row right-click menu: the Layers menu without
# the Create / Extract Non-Layered items, plus Lock / Mute / Solo; on BaseAnimation only Extract, Duplicate x2, Merge
# and Lock stay enabled. Exclusive solo, Select Objects / All / Branch / Layer Node, Export, Membership and Attribute
# Editor are not in the kit (remaining).
ANIM_ROW_MENU = (
    ("allset.anim_layer_members", "Add Selected Objects", {"add": True}),
    ("allset.anim_layer_members", "Remove Selected Objects", {"add": False}),
    ("allset.anim_layer_extract", "Extract Selected Objects", {}),
    None,
    ("allset.anim_layer_duplicate", "Duplicate Layer", {"no_animation": False}),
    ("allset.anim_layer_duplicate", "Duplicate Layer (No Animation)", {"no_animation": True}),
    ("allset.anim_layer_merge", "Merge Layers", {}),
    None,
    ("lock", "Lock", None),
    ("mute", "Mute", None),
    ("solo", "Solo", None),
    None,
    ("allset.anim_layer_delete", "Delete", {}),
    ("allset.anim_layer_empty", "Empty", {}),
    ("allset.anim_layer_delete_empty", "Delete Empty Layers", {}),
)
ROW_ON_BASE = ("Extract Selected Objects", "Duplicate Layer", "Duplicate Layer (No Animation)", "Merge Layers", "Lock")


def _base_selected(context):
    from ..operators import anim_layers_204
    return anim_layers_204.base_selected(context.scene)


def draw_anim_layer_items(layout, context=None):
    grey = context is not None and _base_selected(context)
    for entry in ANIM_LAYER_MENU:
        if entry is None:
            layout.separator()
            continue
        idname, text, props = entry
        line = layout
        if grey and text in GREY_WITH_BASE:
            line = layout.row()
            line.enabled = False
        op = line.operator(idname, text=text)
        for k, v in props.items():
            setattr(op, k, v)


def draw_anim_layer_mode(layout, context):
    """Maya's Override / Additive choice for the selected layer (its layer menu), as two check items (greyed while
    BaseAnimation is among the selected layers)."""
    from ..operators import anim_layers
    sel = anim_layers.selected(context.scene)
    if sel is None or sel.name == anim_layers.BASE:
        return
    layout.separator()
    col = layout.column()
    col.enabled = not _base_selected(context)
    col.prop(sel, "override", text="Override")
    col.prop(sel, "override", text="Additive", invert_checkbox=True)


def anim_layer_row(context):
    """The animation layer entry whose Layer Editor row is under the mouse (name button or its Lock / Solo / Mute
    toggle), for the row's right-click menu; None elsewhere."""
    scene = getattr(context, "scene", None)
    ls = getattr(scene, "allset_anim_layers", None)
    if ls is None or not len(ls):
        return None
    op = getattr(context, "button_operator", None)
    if op is not None and op.bl_rna.identifier == "ALLSET_OT_anim_layer_select":
        i = op.index
        return ls[i] if 0 <= i < len(ls) else None
    ptr = getattr(context, "button_pointer", None)
    if ptr is not None and getattr(ptr, "bl_rna", None) is not None and \
            ptr.bl_rna.identifier == "ALLSET_PG_anim_layer":
        return next((e for e in ls if e.name == ptr.name), None)
    return None


def draw_anim_row_menu(layout, context, entry):
    """Maya's layer right-click menu: the selected layers when the clicked row is selected, else that row only."""
    from ..operators import anim_layers
    picked = {e.name for e in anim_layers.selected_layers(context.scene)}
    layer = "" if entry.name in picked else entry.name
    base = entry.name == anim_layers.BASE
    grey_base = anim_layers.BASE in (picked if not layer else {layer})
    for item in ANIM_ROW_MENU:
        if item is None:
            layout.separator()
            continue
        idname, text, props = item
        line = layout.row()
        if (base or grey_base) and text not in ROW_ON_BASE:
            line.enabled = False
        if props is None:                   # Lock / Mute / Solo of the clicked row
            if base and idname != "lock":
                line.enabled = False
            line.prop(entry, idname, text=text)
            continue
        op = line.operator(idname, text=text)
        for k, v in props.items():
            setattr(op, k, v)
        if layer and idname != "allset.anim_layer_delete_empty":
            op.layer = layer
    if not base:
        layout.separator()
        col = layout.column()
        col.enabled = not grey_base
        col.prop(entry, "override", text="Override")
        col.prop(entry, "override", text="Additive", invert_checkbox=True)


def anim_display_order(scene):
    """Indices of ``Scene.allset_anim_layers`` as Maya lists them: top layer first, BaseAnimation last."""
    return list(reversed(range(len(getattr(scene, "allset_anim_layers", ())))))


def draw_anim_tab(layout, context):
    """Maya's Anim tab: toolbar (Create Empty Layer, Create Layer from Selected), the layer rows (name = select,
    M / S / L), then Weight and Additive / Override of the selected layer. Draw only: nothing is written here
    (the list gets BaseAnimation from the operators)."""
    from ..operators import anim_layers
    from .kit_icons import button
    scene = context.scene
    bar = layout.row(align=True)
    left = bar.row(align=True)
    left.alignment = 'LEFT'
    left.emboss = 'NONE'
    for idname, icon, props in ANIM_TOOLBAR:
        op = left.operator(idname, text="", icon=icon)
        for k, v in props.items():
            setattr(op, k, v)
    row = bar.row(align=True)
    row.alignment = 'RIGHT'
    row.emboss = 'NONE'
    button(row, "allset.anim_layer_create", "layer:NEW_EMPTY", 'ADD', text="").from_selected = False
    button(row, "allset.anim_layer_create", "layer:NEW_SELECTED", 'COLLECTION_NEW', text="").from_selected = True
    ls = anim_layers.layers(scene)
    if not len(ls):
        return
    sel = anim_layers.selected(scene)
    picked = {e.name for e in anim_layers.selected_layers(scene)}     # Ctrl / Shift selection
    col = layout.column(align=True)
    for i in anim_display_order(scene):
        e = ls[i]
        line = col.row(align=True)
        base = e.name == anim_layers.BASE
        for attr, icons in ANIM_TOGGLES:
            cell = line.row(align=True)
            if base and attr != "lock":            # Maya: BaseAnimation has only Lock (empty Solo / Mute slots)
                cell.label(text="", icon='BLANK1')
                continue
            cell.prop(e, attr, text="", icon=icons[bool(getattr(e, attr))], toggle=True)
        name = line.row(align=True)
        name.active = not e.mute                 # a muted layer's name reads greyed (#666666)
        name.operator("allset.anim_layer_select", text=e.name, depress=e.name in picked).index = i
    if sel is None:
        return
    layout.separator(factor=0.5)
    # Maya's bottom row: "Weight" field + slider, greyed while BaseAnimation is selected (anim180 state d);
    # Additive / Override is Maya's layer menu choice (Layers menu here)
    # Maya's K is a small square button right of the slider, not half the row
    w = layout.split(factor=0.88, align=True)
    slider = w.row(align=True)
    slider.enabled = sel.name != anim_layers.BASE
    slider.prop(sel, "weight", slider=True)
    w.operator("allset.anim_layer_key_weight", text="K").current = True     # Maya's K: key the weight


class ALLSET_PT_layer_editor(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Channel Box / Layer Editor"   # not registered (ui/maya_dock.py draws it)
    bl_label = "Layer Editor"
    bl_order = 1
    bl_options = {'HIDE_HEADER'}   # Maya: tabs + menu bar, no collapsible panel title

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        wm = context.window_manager
        sdk = getattr(wm, "allset_sdk", None)
        if sdk is not None and sdk.open:
            from . import set_driven_key   # the Set Driven Key window takes the Layer Editor's place
            set_driven_key.draw(layout, context)
            return
        layout.separator(type='LINE')   # Maya's splitter between Channel Box and Layer Editor
        # Maya: slim tabs on the left, not a
        # full-width switch
        tabs = layout.row(align=True)
        tabs.alignment = 'LEFT'
        tabs.scale_y = 0.9
        for ident, label, _tip in TABS:
            tabs.prop_enum(wm, "allset_le_tab", ident, text=f"  {i18n.iface(label)}  ", translate=False)
        chrome.menu_bar(layout, MENU_BAR)
        if wm.allset_le_tab == 'ANIM':
            draw_anim_tab(layout, context)    # Maya animation layers on NLA tracks
            return
        # Maya's toolbar, right-aligned, frameless icon buttons in Maya's order: move up, move down, create
        # empty layer, create layer from selected (Maya 2022 Layer Editor)
        row = layout.row(align=True)
        row.alignment = 'RIGHT'
        row.emboss = 'NONE'
        # kit-drawn Maya icons (#23; Blender's icon until the glyph is made)
        from .kit_icons import button
        for direction, icon in (("UP", 'TRIA_UP_BAR'), ("DOWN", 'TRIA_DOWN_BAR')):
            button(row, "allset.layer_move", f"layer:{direction}", icon, text="").direction = direction
        button(row, "allset.layer_new", "layer:NEW_EMPTY", 'ADD', text="").selected = False
        button(row, "allset.layer_new", "layer:NEW_SELECTED", 'COLLECTION_NEW', text="").selected = True
        # Maya shows the (empty) layer list area even with no layers: an empty
        # list over the scene collection's children (the filter keeps display layers only).
        r = root(scene)
        owner = r if r is not None else scene.collection
        layout.template_list("ALLSET_UL_layers", "", owner, "children", scene, "allset_layer_index",
                             rows=list_rows(context), sort_lock=True)


def list_rows(context):
    """Layer list rows that fill the dock to the bottom (Maya's Layer Editor pane is the dock's lower part,
    channel_box.CB_SHARE)."""
    from .channel_box import _round_half_up, cb_share
    region = context.region
    if region is None or region.type not in {'UI', 'WINDOW'}:   # the dock is a Properties WINDOW
        return 8
    u = _round_half_up(18.0 * context.preferences.system.ui_scale) + 2 * context.preferences.system.pixel_size
    return max(3, int((1.0 - cb_share(region, u)) * region.height / max(u, 1)) - 5)


classes = (ALLSET_PG_layer, ALLSET_OT_layer_new, ALLSET_OT_layer_assign, ALLSET_OT_layer_select,
           ALLSET_OT_layer_delete, ALLSET_OT_layer_cycle_type, ALLSET_OT_layer_toggle, ALLSET_OT_layer_move,
           ALLSET_OT_layer_empty, ALLSET_OT_layer_set_type, ALLSET_UL_layers,
           ALLSET_MT_le_layers, ALLSET_MT_le_options, ALLSET_MT_le_help)
# ALLSET_PT_layer_editor is drawn under the Channel Box by ui/maya_dock.py, not registered as a panel.


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Collection.allset_layer = PointerProperty(type=ALLSET_PG_layer)
    bpy.types.Scene.allset_layer_index = IntProperty(options={'HIDDEN'})
    bpy.types.WindowManager.allset_le_tab = EnumProperty(name="Layer Editor Tab", items=TABS,
                                                           options={'SKIP_SAVE'})
    bpy.app.handlers.animation_playback_pre.append(on_playback_pre)
    bpy.app.handlers.animation_playback_post.append(on_playback_post)
    bpy.types.UI_MT_button_context_menu.prepend(draw_button_menu)


def unregister():
    bpy.types.UI_MT_button_context_menu.remove(draw_button_menu)
    bpy.app.handlers.animation_playback_post.remove(on_playback_post)
    bpy.app.handlers.animation_playback_pre.remove(on_playback_pre)
    del bpy.types.WindowManager.allset_le_tab
    del bpy.types.Scene.allset_layer_index
    del bpy.types.Collection.allset_layer
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
