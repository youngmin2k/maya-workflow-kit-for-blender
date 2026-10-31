# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya marking menus, first version: Blender pie menus (step 8).

Maya's marking-menu triggers and menus; Blender pies: 8 slots, press-drag-release via pie_tap_timeout.

- ``menus.py``: the menus as data (Maya radial positions).
- ``engine.py`` / ``draw.py`` / ``modal.py``: the step-9 marking menu engine
  (GPU, gestures, in-place submenus, option boxes) and the hotbox; the
  "Marking Menu Style" preference picks the engine (default) or the pies.
- ``user_menus.py``: the user's edited and own menus (Marking Menu
  Editor, ``menu_editor.py``), put into ``menus.MENUS`` at register.
- Here: one pie ``Menu`` class per marking menu and radial submenu (plain
  ``Menu`` for list submenus), ``allset.marking_menu`` (picks the menu for a
  trigger and the context, like Maya's builders), helper operators, and the
  Q/W/E/R "hold + LMB" bindings on the step-3 tap/hold framework; the user's
  menus get their pie classes and hotkeys from ``apply_user_menus``.
"""

import bpy
from bpy.props import EnumProperty, StringProperty

from ..operators import taphold
from ..ui import menu_map, menu_sets
from . import draw, menu_editor, modal, rmb_items, rmb_nodes, user_menus
from . import menus as mm

# Blender fills a pie in this order (UILayout.menu_pie).
PIE_ORDER = ("W", "E", "S", "N", "NW", "NE", "SW", "SE")
TRIGGERS = (("RMB", "RMB", "Object / component marking menu (Maya RMB)"),
            ("SHIFT_RMB", "Shift+RMB", "Context tools (Maya Shift+RMB)"),
            ("CTRL_RMB", "Ctrl+RMB", "Convert selection (Maya Ctrl+RMB)"),
            ("TOOL_OPTIONS", "Ctrl+Shift+RMB", "Options of the active tool (Maya Ctrl+Shift+RMB)"))


# --- classes from the data ------------------------------------------------------------

def idname(menu_name, sub_path=""):
    suffix = sub_path.replace("/", "_")
    return f"ALLSET_MT_mm_{menu_name}{'_' + suffix if suffix else ''}"


_classes = []
_sub_ids = {}  # id(Sub) -> (idname, is_pie)


def _entry_spec(action):
    if isinstance(action, mm.Sub):
        found = _sub_ids.get(id(action))
        if found is None:       # a submenu without a class (never expected): greyed rather than a broken draw
            return None
        name, is_pie = found
        return ("pie" if is_pie else "menu", name, {})
    return menu_map.normalize(action)


def draw_entry(layout, label, action, path):
    if label == mm.OBJECT_TITLE:   # step 52: the RMB list's first row is the object's name
        ob = bpy.context.active_object
        label = f"{getattr(bpy.context.window_manager, 'allset_mm_target', '') or (ob.name if ob else 'Object')}..."
    if mm.is_unavailable(action):  # greyed submenu (step 52)
        return menu_sets.draw_spec(layout, label + " ▸", None, f"Marking menu {path}")
    # Toggles show their state like the engine's check boxes (step 31: pie fallback had none).
    state = draw.checked(action) if not isinstance(action, mm.Sub) else None
    icon = 'NONE' if state is None else ('CHECKBOX_HLT' if state else 'CHECKBOX_DEHLT')
    menu_sets.draw_spec(layout, label, _entry_spec(action), f"Marking menu {path}", icon=icon)


def _draw_list(layout, sub, path):
    for i, entry in enumerate(sub.items):
        if entry == mm.DIVIDER:
            layout.separator()
        else:
            draw_entry(layout, entry[0], entry[1], f"{path}/{entry[0]}")


def draw_pie(pie, sub, path):
    """Maya radial slots in Blender pie order; the linear list goes under S."""
    for pos in PIE_ORDER:
        entry = sub.radial.get(pos)
        if pos == "S" and sub.items:
            col = pie.column()
            if entry:
                draw_entry(col, entry[0], entry[1], f"{path}/{entry[0]}")
                col.separator()
            _draw_list(col.box().column(), sub, path)
        elif entry:
            draw_entry(pie, entry[0], entry[1], f"{path}/{entry[0]}")
        else:
            pie.separator()


def _make(sub, name, label, path, is_pie, out=None, reuse=False):
    """Menu classes for ``sub`` and its submenus into ``out`` (the factory ``_classes``). ``reuse``: a submenu that
    already has a class keeps it (the factory submenus a user menu shares with the kit)."""
    out = _classes if out is None else out
    _sub_ids[id(sub)] = (name, is_pie)
    # Children first so their ids exist when the parent draws.
    for pos, (child_label, action) in sub.radial.items():
        if isinstance(action, mm.Sub) and not (reuse and id(action) in _sub_ids):
            _make(action, f"{name}_{pos}", child_label, f"{path}/{child_label}", True, out, reuse)
    for i, entry in enumerate(sub.items):
        if entry != mm.DIVIDER and isinstance(entry[1], mm.Sub) and not (reuse and id(entry[1]) in _sub_ids):
            _make(entry[1], f"{name}_{i}", entry[0], f"{path}/{entry[0]}", False, out, reuse)

    if is_pie:
        def draw(self, context):
            draw_pie(self.layout.menu_pie(), sub, path)
    elif isinstance(sub, mm.NodeList):
        def draw(self, context):
            # filled from the object now (step 165); a node's own traversal submenu = its first row (Select <node>)
            from . import rmb_nodes
            from . import rmb_items
            data = rmb_nodes.nodes(rmb_items.target(context))
            if not data:
                return
            for entry in mm.fill(sub.kind, data).items:
                if entry == mm.DIVIDER:
                    self.layout.separator()
                    continue
                label, action = entry
                if isinstance(action, mm.Sub):
                    action = action.items[0][1]
                menu_sets.draw_spec(self.layout, label, menu_map.normalize(action), f"Marking menu {path}/{label}")
    else:
        def draw(self, context):
            for pos in mm.RADIALS:  # a list submenu shows radial entries first
                if pos in sub.radial:
                    draw_entry(self.layout, sub.radial[pos][0], sub.radial[pos][1], path)
            _draw_list(self.layout, sub, path)
    out.append(type(name, (bpy.types.Menu,), {
        "bl_idname": name, "bl_label": label, "draw": draw, "__doc__": f"Maya marking menu: {path}"}))


for _m in mm.MENUS.values():
    _make(_m, idname(_m.name), _m.label, _m.label, is_pie=True)
_NAME_BY_ID = {idname(name): name for name in mm.MENUS}


# --- the user's menus (Marking Menu Editor) ---------------------------------------------

_user_classes = []      # Menu classes of the menus user_menus.apply built, registered while those are in MENUS
_user_sub_ids = []      # their _sub_ids keys (the built Subs stay alive in MENUS / the draw closures until dropped)
_USER_IDS = {}          # menu name -> its pie class idname (Blender Pies style)


def user_idname(menu_name, sub_path=""):
    # own prefix: a user menu's name never makes a factory class name (custom names are any identifier)
    return "ALLSET_MT_mmu_" + idname(menu_name, sub_path)[len("ALLSET_MT_mm_"):]


def pie_idname(menu_name):
    """The pie class of ``menu_name`` as it is now (a changed kit menu has its own; step 8 fallback style)."""
    return _USER_IDS.get(menu_name) or idname(menu_name)


def _drop_user_pies():
    for cls in reversed(_user_classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    for key in _user_sub_ids:
        _sub_ids.pop(key, None)
    _user_classes.clear()
    _user_sub_ids.clear()
    _USER_IDS.clear()


def _make_user_pies():
    for name in user_menus.changed_names():
        menu = mm.MENUS.get(name)
        if menu is None or menu is mm.FACTORY.get(name):
            continue
        before = set(_sub_ids)
        made = []
        _make(menu, user_idname(name), menu.label, menu.label, True, made, reuse=True)
        for cls in made:
            bpy.utils.register_class(cls)
        _user_classes.extend(made)
        _user_sub_ids.extend(k for k in _sub_ids if k not in before)
        _USER_IDS[name] = user_idname(name)


class CustomMenuBinding(taphold.TapHoldBinding):
    """A custom marking menu's hotkey, Maya's way: hold the key and press LMB = the menu (drag and release picks);
    a tap does nothing (Maya runs the hotkey's release command, which a marking menu hotkey doesn't have)."""
    menu = ""

    def click(self, context, event):
        modal.open_menu(self.menu, 'LEFTMOUSE', (event.mouse_region_x, event.mouse_region_y))


# 3D View keymaps the hotkey of a custom menu goes into: Blender runs the mode keymaps before "3D View", so the key is
# in each of them, like the Maya keys of that mode (keymap.set_overlay puts it in front of them).
HOTKEY_KEYMAPS = (("Object Mode", 'EMPTY'), ("Mesh", 'EMPTY'), ("Curve", 'EMPTY'), ("Curves", 'EMPTY'),
                  ("Armature", 'EMPTY'), ("Pose", 'EMPTY'), ("Metaball", 'EMPTY'), ("Lattice", 'EMPTY'),
                  ("Font", 'EMPTY'), ("Particle", 'EMPTY'), ("Sculpt", 'EMPTY'), ("Weight Paint", 'EMPTY'),
                  ("Vertex Paint", 'EMPTY'), ("Image Paint", 'EMPTY'), ("3D View", 'VIEW_3D'))
HOTKEY_OWNER = "custom_marking_menus"
_user_bindings = []     # tap/hold binding names of the custom menus' hotkeys


def binding_name(menu_name):
    return f"user_mm_{menu_name}"


def hotkey_items():
    """keymap.set_overlay items for every custom menu with a hotkey (``allset.tap_hold`` on the key's press)."""
    out = []
    for name, hk in user_menus.hotkeys():
        mods = {m: hk[m] for m in user_menus.MODIFIERS}
        for km_name, space in HOTKEY_KEYMAPS:
            out.append((km_name, space, "allset.tap_hold", hk["key"], 'PRESS', mods, {"binding": binding_name(name)}))
    return out


def _set_hotkeys():
    for b in _user_bindings:
        taphold.unregister_binding(b)
    _user_bindings.clear()
    for name, _hk in user_menus.hotkeys():
        cls = type(f"Binding_{binding_name(name)}", (CustomMenuBinding,),
                   {"name": binding_name(name), "label": user_menus.menu_label(name), "menu": name})
        taphold.register_binding(cls())
        _user_bindings.append(cls.name)
    from .. import keymap
    keymap.set_overlay(HOTKEY_OWNER, hotkey_items())


def apply_user_menus():
    """The document (user_menus) into MENUS, the pie classes of the menus it changed and the custom menus' hotkeys.
    Called at register and after every edit in the Marking Menu Editor."""
    _drop_user_pies()
    user_menus.apply()
    _make_user_pies()
    _set_hotkeys()


def _clear_user_menus():
    from .. import keymap
    keymap.set_overlay(HOTKEY_OWNER, [])
    for b in _user_bindings:
        taphold.unregister_binding(b)
    _user_bindings.clear()
    _drop_user_pies()
    user_menus.reset()


# --- choosing the menu (Maya builders, step 8) ---------------------------------------

def resolve(trigger, context, picked=None):
    """("pie" | "menu", Menu idname) for a trigger in this context, or None."""
    mode = context.mode
    ob = picked or context.active_object
    if trigger == "TOOL_OPTIONS":
        tool = context.workspace.tools.from_space_view3d_mode(mode, create=False)
        tid = tool.idname if tool else ""
        name = mm.SELECT_OPTIONS if tid.startswith("builtin.select") else mm.TOOL_OPTIONS.get(tid)
        return ("pie", idname(name)) if name else None
    space = getattr(context, "space_data", None)
    if space is not None and space.type == 'IMAGE_EDITOR':
        # UV Editor (step 66): Maya 2026's UV Editor RMB marking menu, Shift+RMB = UV / UV Shell tools
        if mode != 'EDIT_MESH' or space.mode != 'UV':
            return None
        if trigger == "RMB":
            return ("pie", idname("UV_EDITOR_RMB"))
        if trigger == "SHIFT_RMB":
            ts = context.scene.tool_settings
            from .. import compat
            shell = not ts.use_uv_select_sync and compat.uv_island_mode(ts)
            return ("pie", idname("SHIFT_UV_SHELL" if shell else "SHIFT_UV"))
        return None
    if trigger == "CTRL_RMB":
        # Maya's Ctrl+RMB convert menu picks by the lead's shape type, not the mode: a mesh lead gets CTRL_CONVERT in
        # object mode too (an item then converts the whole object, modal.CONVERT_FROM_OBJECT; step 136)
        if mode == 'EDIT_MESH' or (mode == 'OBJECT' and ob is not None and ob.type == 'MESH'):
            return ("pie", idname("CTRL_CONVERT"))
        trigger = "RMB"  # not a mesh -> object menu
    if trigger == "SHIFT_RMB":
        if mode == 'EDIT_MESH':
            vert, edge, face = context.scene.tool_settings.mesh_select_mode
            name = ("SHIFT_FACE" if face else "SHIFT_EDGE" if edge
                    else "SHIFT_VERTEX")
            return ("pie", idname(name))
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        return ("pie", idname("SHIFT_OBJECT" if meshes else "SHIFT_DEFAULT"))
    # RMB
    from ..operators import pivot_menu
    if pivot_menu.pivot_editing(context):      # D / Insert held or on: the pivot menu (step 94)
        return ("pie", idname("PIVOT_EDIT"))
    if mode == 'EDIT_MESH':
        return ("pie", idname("RMB_MESH"))
    if mode in {'EDIT_CURVE', 'EDIT_SURFACE'}:
        return ("pie", idname("RMB_CURVE"))
    if mode == 'EDIT_LATTICE':
        return ("pie", idname("RMB_LATTICE"))
    if mode == 'OBJECT':
        if ob is None:
            return ("pie", idname("RMB_EMPTY"))
        if ob.type == 'MESH':
            return ("pie", idname("RMB_MESH"))
        if ob.type in {'CURVE', 'SURFACE'}:
            return ("pie", idname("RMB_CURVE"))
        if ob.type == 'LATTICE':
            return ("pie", idname("RMB_LATTICE"))  # step 294 (#227)
        return ("menu", "VIEW3D_MT_object_context_menu")  # no Maya radial for this type
    return None


def pick_object(context, event):
    """Object under the mouse in the 3D View (ray cast), or None."""
    from bpy_extras import view3d_utils
    region, rv3d = context.region, context.region_data
    if region is None or rv3d is None or region.type != 'WINDOW':
        return None
    coord = (event.mouse_region_x, event.mouse_region_y)
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
    hit, _loc, _nor, _idx, ob, _mat = context.scene.ray_cast(
        context.evaluated_depsgraph_get(), origin, direction)
    if not hit or ob is None:
        return None
    return bpy.data.objects.get(ob.name)


class ALLSET_OT_marking_menu(bpy.types.Operator):
    """Open the Maya marking menu for this trigger and context"""
    bl_idname = "allset.marking_menu"
    bl_label = "Marking Menu"
    bl_options = {'INTERNAL'}

    trigger: EnumProperty(items=TRIGGERS)

    def invoke(self, context, event):
        picked = None
        if self.trigger in {"RMB", "CTRL_RMB"} and context.mode == 'OBJECT':
            picked = pick_object(context, event)
        context.window_manager.allset_mm_target = picked.name if picked else ""
        found = resolve(self.trigger, context, picked)
        if found is None:
            return {'PASS_THROUGH'}
        kind, name = found
        if kind == "pie":
            modal.open_menu(_NAME_BY_ID[name], event.type if event.type in modal.MOUSE_BUTTONS
                            else 'RIGHTMOUSE', (event.mouse_region_x, event.mouse_region_y))
        else:
            bpy.ops.wm.call_menu(name=name)
        return {'FINISHED'}


# --- helper operators used by the menus -----------------------------------------------

COMPONENTS = (("VERT", "Vertex", ""), ("EDGE", "Edge", ""), ("FACE", "Face", ""),
              ("MULTI", "Multi", ""), ("CV", "Control Vertex", "Curve edit mode"),
              ("LATTICE", "Lattice Point", "Lattice edit mode"),
              ("NONE", "Select", "Only select the object"))


class ALLSET_OT_mm_component(bpy.types.Operator):
    """Select the object under the marking menu and enter this component mode (Maya RMB menu)"""
    bl_idname = "allset.mm_component"
    bl_label = "Component Mode"
    bl_options = {'UNDO', 'INTERNAL'}

    type: EnumProperty(items=COMPONENTS)

    @classmethod
    def poll(cls, context):
        wm = context.window_manager
        return bool(getattr(wm, "allset_mm_target", "")) or context.active_object is not None

    def execute(self, context):
        target = bpy.data.objects.get(context.window_manager.allset_mm_target)
        if target is not None and context.mode == 'OBJECT':
            vl = context.view_layer
            if target not in context.selected_objects or self.type == "NONE":
                for o in context.selected_objects:
                    o.select_set(False)
            target.select_set(True)
            vl.objects.active = target
        ob = context.view_layer.objects.active
        if self.type == "NONE" or ob is None:
            return {'FINISHED'}
        from ..operators import maya_errors
        if maya_errors.refuse_hidden(self, ob):        # #187
            return {'CANCELLED'}
        if self.type == "CV":
            if ob.type in {'CURVE', 'SURFACE'} and context.mode == 'OBJECT':
                bpy.ops.object.mode_set(mode='EDIT')
            return {'FINISHED'}
        if self.type == "LATTICE":
            # step 294 (#227): Lattice Point on a lattice = its edit mode
            if ob.type == 'LATTICE' and context.mode == 'OBJECT':
                bpy.ops.object.mode_set(mode='EDIT')
            return {'FINISHED'}
        if ob.type != 'MESH':
            return {'CANCELLED'}
        bpy.ops.allset.component_mode(type=self.type)
        return {'FINISHED'}


class ALLSET_OT_mm_python(bpy.types.Operator):
    """Run this marking menu item's Python command (like a shelf button: maya.cmds look-alike available)"""
    bl_idname = user_menus.PYTHON_OP
    bl_label = "Python Command"
    bl_options = {'INTERNAL'}

    code: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        from ..ui import shelf
        ok, msg = shelf.run_script(context, "Marking Menu", self.code)
        if not ok:
            self.report({'ERROR'}, msg)
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_mm_shelf_button(bpy.types.Operator):
    """Run this shelf button, like a click on it (Maya: a shelf button dragged into a marking menu)"""
    bl_idname = user_menus.SHELF_OP
    bl_label = "Shelf Button"
    bl_options = {'INTERNAL'}

    shelf: StringProperty(options={'SKIP_SAVE'})
    button: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        from ..ui import shelf
        index = shelf.button_index(self.shelf, self.button)
        if index is None:
            self.report({'WARNING'}, f"{self.button}: no longer on the {user_menus.shelf_text(self.shelf)} shelf")
            return {'CANCELLED'}
        return bpy.ops.allset.shelf_button(shelf=self.shelf, index=index)


class ALLSET_OT_mm_clear_selection(bpy.types.Operator):
    """Clear the selection (objects or components)"""
    bl_idname = "allset.mm_clear_selection"
    bl_label = "Clear Selection"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if context.mode == 'EDIT_MESH':
            bpy.ops.mesh.select_all(action='DESELECT')
        elif context.mode == 'OBJECT':
            bpy.ops.object.select_all(action='DESELECT')
        else:
            return {'CANCELLED'}
        return {'FINISHED'}


# --- Q/W/E/R hold + LMB (step-3 tap/hold framework) -------------------------------------

HANDLE_KINDS = {"builtin.move": 'TRANSLATE', "builtin.rotate": 'ROTATE', "builtin.scale": 'RESIZE'}


class ToolOptionsBinding(taphold.TapHoldBinding):
    """Key press = this tool (Maya activates it on press); hold + LMB = its options
    marking menu (Maya's tool hold menus)."""
    tool = ""
    menu = ""

    def _set_tool(self):
        # Maya: a tool key ends the Channel Box middle-drag on the picked channels (they stay highlighted)
        from ..ui import channel_box
        channel_box.disarm_slider()
        try:
            bpy.ops.wm.tool_set_by_id(name=self.tool, space_type='VIEW_3D')
        except RuntimeError:  # e.g. the tool doesn't exist in this mode
            pass
        # Maya: a tool key after an extrusion / bevel shows that tool's manipulator instead of the extrude one
        # (issue #80: the hidden Move manipulator left W without a way to move the new faces)
        from ..operators import extrude
        if extrude.dismiss(bpy.context):
            for area in bpy.context.screen.areas if bpy.context.screen else ():
                if area.type == 'VIEW_3D':
                    area.tag_redraw()

    def tap(self, context):
        # Tapping the key of the active tool again goes back to the centre handle (free MMB
        # drag), like Maya; step 28.
        kind = HANDLE_KINDS.get(self.tool)
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        if kind and tool is not None and tool.idname == self.tool:
            from ..operators import manip
            manip.reset_handle(kind)
        from ..operators import hold
        hold.end_pivot_edit(context)
        self._set_tool()

    def click(self, context, event):
        self._set_tool()
        # Opened on the LMB press: dragging and releasing LMB picks (engine or pie).
        modal.open_menu(self.menu, 'LEFTMOUSE', (event.mouse_region_x, event.mouse_region_y))


def _binding(name, label, tool, menu):
    return type(f"Binding_{name}", (ToolOptionsBinding,),
                {"name": name, "label": label, "tool": tool, "menu": menu})


TOOL_BINDINGS = (
    _binding("tool_select", "Select Tool / Options", "builtin.select_box", "OPT_SELECT"),
    _binding("tool_move", "Move Tool / Options", "builtin.move", "OPT_MOVE"),
    _binding("tool_rotate", "Rotate Tool / Options", "builtin.rotate", "OPT_ROTATE"),
    _binding("tool_scale", "Scale Tool / Options", "builtin.scale", "OPT_SCALE"),
)
TOOL_KEYS = (("Q", "tool_select"), ("W", "tool_move"), ("E", "tool_rotate"), ("R", "tool_scale"))


def _tool_later(idname):
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                try:
                    with bpy.context.temp_override(window=window, area=area, region=region):
                        bpy.ops.wm.tool_set_by_id(name=idname)
                except RuntimeError:
                    pass
                return None
    return None


class SelectComponentBinding(ToolOptionsBinding):
    """Shift+Q (Maya hotkey and its hold marking menu): the select tool in component mode;
    hold + LMB = the component pick mask marking menu."""
    name = "select_component"
    label = "Select Tool, Components / Pick Mask"
    tool = "builtin.select_box"
    menu = "SELECT_COMPONENT"

    def _set_tool(self):
        context = bpy.context
        ob = context.active_object
        from ..operators import maya_errors
        if context.mode == 'OBJECT' and maya_errors.is_hidden(ob):
            from ..ui import view_message      # #187: stay in object mode, say why
            view_message.show(context, maya_errors.hidden_text(ob), 'TOP_CENTER')
        elif context.mode == 'OBJECT' and ob is not None and ob.type == 'MESH':
            bpy.ops.object.mode_set(mode='EDIT')     # selectMode -component
            # a tool is set for the mode the call starts in: set the edit-mode tool once in it (step 97)
            bpy.app.timers.register(lambda: _tool_later(self.tool), first_interval=0.0)
        super()._set_tool()

    def tap(self, context):
        self._set_tool()


class SelectPolygonBinding(ToolOptionsBinding):
    """Alt+Q (Maya hotkey and its hold marking menu): the select tool; hold + LMB = Vertices / Edges / Faces /
    UVs."""
    name = "select_polygon"
    label = "Select Tool / Polygon Components"
    tool = "builtin.select_box"
    menu = "SELECT_POLYGON"

    def tap(self, context):
        self._set_tool()


SELECT_BINDINGS = (SelectComponentBinding, SelectPolygonBinding)


classes = (ALLSET_OT_marking_menu, ALLSET_OT_mm_component, ALLSET_OT_mm_python, ALLSET_OT_mm_shelf_button,
           ALLSET_OT_mm_clear_selection, *rmb_items.classes, *rmb_nodes.classes, *modal.classes, *_classes)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.allset_mm_target = StringProperty(
        name="Marking Menu Target", description="Object under the mouse when the RMB menu opened",
        options={'SKIP_SAVE'})
    for cls in (*TOOL_BINDINGS, *SELECT_BINDINGS):
        taphold.register_binding(cls())
    draw.register()
    user_menus.load()
    apply_user_menus()
    menu_editor.register()


def unregister():
    menu_editor.unregister()
    _clear_user_menus()
    draw.unregister()
    for cls in (*TOOL_BINDINGS, *SELECT_BINDINGS):
        taphold.unregister_binding(cls.name)
    del bpy.types.WindowManager.allset_mm_target
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
