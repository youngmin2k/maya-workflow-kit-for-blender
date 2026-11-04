# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya's Marking Menu Editor window (Windows > Settings/Preferences > Marking Menu Editor).

Maya 2022's Marking Menu Editor lists the marking menus, edits one in a 3×3 grid of its radial positions (the centre is
the menu itself) plus the list under it, gives each item a label, a command and an option box, makes new menus
(Create Marking Menu) and binds a menu to a hotkey (Settings > Use marking menu in: Hotkey Editor; hold the key, press
LMB). Here the kit's own menus can be edited too (Maya's Restore Default puts one back) and a submenu is opened in
place with the breadcrumb above the grid. Every edit is written at once (``marking/user_menus.py``: one JSON file in
the extension's user folder) and is live in the next menu opened (``marking.apply_user_menus``).

A slot's command is one of: Kit Default (the kit's own item at that place, kept as a reference so kit updates still
reach it), a Blender operator id + properties as JSON, a Maya main-menu item path (run like the menu), Python (like a
shelf button), a shelf button (Maya drags one from the shelf into the editor; here it is picked in a search field),
a submenu, or any kit action value as JSON. The Maya menu item field completes the kit's menu paths as you type.

Window = a ``marked_window`` kind "MARKING_MENU_EDITOR" (Properties Tool tab in its own window), like the Hotkey
Editor; the slot fields live on the WindowManager and are filled by ``refresh`` (selection / edits), never in ``draw``.
"""

import json

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from ..ui import marked_window
from . import menus as mm
from . import user_menus as um

KIND = "MARKING_MENU_EDITOR"
TITLE = "Marking Menu Editor"
GRID = (("NW", "N", "NE"), ("W", None, "E"), ("SW", "S", "SE"))
DIVIDER_TEXT = "──────────"
SHELF_SEP = " / "         # "Polygons / Delete By Type: History" in the Shelf Button field
NEW_LABEL = "New Item"

# Where Maya (and the kit) opens each kit menu: shown in the menu list.
TRIGGERS = {
    "RMB_MESH": "RMB over a mesh", "RMB_CURVE": "RMB over a curve", "RMB_EMPTY": "RMB over nothing",
    "PIVOT_EDIT": "RMB while editing a pivot (D)",
    "SHIFT_OBJECT": "Shift+RMB, object mode", "SHIFT_VERTEX": "Shift+RMB, vertex mode",
    "SHIFT_EDGE": "Shift+RMB, edge mode", "SHIFT_FACE": "Shift+RMB, face mode",
    "SHIFT_DEFAULT": "Shift+RMB, nothing selected", "CTRL_CONVERT": "Ctrl+RMB on a mesh",
    "OPT_MOVE": "W + LMB (Move Tool)", "OPT_ROTATE": "E + LMB (Rotate Tool)", "OPT_SCALE": "R + LMB (Scale Tool)",
    "OPT_SELECT": "Q + LMB (Select Tool)", "OPT_QUAD_DRAW": "Ctrl+Shift+RMB (Quad Draw Tool)", "SELECT_ALL": "A + LMB",
    "HB_NORTH": "Hotbox, north zone", "HB_SOUTH": "Hotbox, south zone", "HB_EAST": "Hotbox, east zone",
    "HB_WEST": "Hotbox, west zone", "HB_CENTER": "Hotbox, centre zone",
    "UV_EDITOR_RMB": "RMB in the UV Editor", "SHIFT_UV": "Shift+RMB in the UV Editor (UVs, edges, vertices)",
    "SHIFT_UV_SHELL": "Shift+RMB in the UV Editor (UV shells)", "SHIFT_UV_FACE": "Shift+RMB in the UV Editor (faces)",
    "KEY_TANGENT": "Shift+S + LMB",
    "SELECT_COMPONENT": "Shift+Q + LMB", "SELECT_POLYGON": "Alt+Q + LMB",
}

TYPE_ITEMS = (
    ("factory", "Kit Default", "The kit's own item at this place (kit updates still reach it)"),
    ("op", "Blender Operator", "A Blender operator id (mesh.bevel) and its properties as JSON"),
    ("item", "Maya Menu Item", "A Maya main-menu item, run like the menu (Edit Mesh/Bevel)"),
    ("python", "Python", "Python run like a shelf button (the maya.cmds look-alike is available)"),
    ("shelf", "Shelf Button", "A shelf button, run like a click on it (Maya: drag it from the shelf)"),
    ("sub", "Submenu", "A submenu of its own (open it to edit its items)"),
    ("kit", "Kit Action", "A kit action value as JSON (ui/menu_map.py forms)"),
)
_IGNORE = {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE", "TIMER", "TIMER_REPORT", "TIMERREGION", "NONE", "WINDOW_DEACTIVATE",
           "LEFT_CTRL", "RIGHT_CTRL", "LEFT_SHIFT", "RIGHT_SHIFT", "LEFT_ALT", "RIGHT_ALT", "OSKEY", "TEXTINPUT"}
_CANCEL = {"ESC", "LEFTMOUSE", "RIGHTMOUSE", "MIDDLEMOUSE"}

_MENU_ITEMS = []        # EnumProperty items (kept referenced: Blender reads the strings later)
_loading = [False]      # refresh is filling the slot fields: their update callbacks do nothing


def _wm(context):
    return context.window_manager


# --- state ------------------------------------------------------------------------------------------------------

def menu_items(self, context):
    _MENU_ITEMS[:] = [(n, ("● " if um.is_changed(n) else "") + f"{um.menu_label(n)}",
                       f"{n}: {TRIGGERS.get(n, 'kit menu')}" + (" (changed)" if um.is_changed(n) else ""), i)
                      for i, n in enumerate(mm.FACTORY)]
    custom = [n for n in um.menu_names() if um.is_custom(n)]
    if custom:
        _MENU_ITEMS.append(None)
    for i, n in enumerate(custom):
        hk = um.document()["custom"][n].get("hotkey")
        _MENU_ITEMS.append((n, um.menu_label(n), f"Your marking menu ({hotkey_text(hk) + ' + LMB' if hk else 'no hotkey'})",
                            len(mm.FACTORY) + 1000 + i))
    return _MENU_ITEMS


def hotkey_text(hk):
    from ..keymap import hotkey_rows
    return hotkey_rows.event_text({"type": hk["key"], **{m: hk.get(m) for m in um.MODIFIERS}})


def current(context):
    """(menu name, submenu path, slot step) shown now."""
    wm = _wm(context)
    return wm.allset_mme_menu, wm.allset_mme_path, wm.allset_mme_slot


def full_path(context):
    _menu, path, slot = current(context)
    return um._join(path, slot) if slot else ""


def node(context):
    """The submenu shown (a read-only tree view)."""
    menu, path, _slot = current(context)
    tree = um.view_tree(menu)
    return um.container(tree, path) if tree is not None else None


def selected_entry(context):
    menu, _path, slot = current(context)
    return um.entry_at(menu, full_path(context)) if slot else None


def factory_here(context):
    """The kit's own entry at the selected place, if the kit menu has one."""
    menu = _wm(context).allset_mme_menu
    return um.factory_entry(menu, full_path(context)) if menu in mm.FACTORY else None


def _set(wm, **values):
    _loading[0] = True
    try:
        for k, v in values.items():
            if getattr(wm, k) != v:
                setattr(wm, k, v)
    finally:
        _loading[0] = False


def refresh(context, message=None):
    """Keep the shown menu / submenu / slot valid and fill the slot fields from the selected entry."""
    wm = _wm(context)
    menu = wm.allset_mme_menu
    if menu not in mm.FACTORY and not um.is_custom(menu):
        _set(wm, allset_mme_menu=next(iter(mm.FACTORY)), allset_mme_path="", allset_mme_slot="")
    if node(context) is None:
        _set(wm, allset_mme_path="", allset_mme_slot="")
    e = selected_entry(context)
    sub = node(context)
    slot = wm.allset_mme_slot
    if e is None and not (slot in mm.RADIALS and sub is not None):
        _set(wm, allset_mme_slot="")
    vals = {"allset_mme_label": "", "allset_mme_op": "", "allset_mme_props": "", "allset_mme_item": "",
            "allset_mme_code": "", "allset_mme_shelf": "", "allset_mme_kit": "", "allset_mme_type": "op"}
    if e is not None:
        vals["allset_mme_label"] = um.entry_label(e)
        vals["allset_mme_type"] = e.get("type", "op")
        if e.get("type") == "op":
            vals["allset_mme_op"] = e.get("op", "")
            vals["allset_mme_props"] = json.dumps(e["props"]) if e.get("props") else ""
        elif e.get("type") == "item":
            vals["allset_mme_item"] = e.get("path", "")
        elif e.get("type") == "python":
            vals["allset_mme_code"] = e.get("code", "")
        elif e.get("type") == "shelf":
            vals["allset_mme_shelf"] = shelf_field(e.get("shelf", ""), e.get("button", ""))
        elif e.get("type") == "kit":
            vals["allset_mme_kit"] = json.dumps(e.get("action"))
    if message is not None:
        vals["allset_mme_message"] = message
    _set(wm, **vals)
    marked_window.redraw(context, KIND)


def changed(context, message=""):
    """An edit was made: write the file, put the menus in place, show the new state."""
    try:
        um.save()
    except OSError as ex:
        message = f"Could not save the marking menus: {ex}"
    from .. import marking
    marking.apply_user_menus()
    refresh(context, message)


# --- search fields ----------------------------------------------------------------------------------------------

def _matches(text, candidates):
    words = text.lower().split()
    return [c for c in candidates if all(w in c.lower() for w in words)]


def item_search(self, context, edit_text):
    """Maya main-menu paths the kit runs (``ui/menu_map.MAP``) containing every typed word."""
    from ..ui import menu_map
    return _matches(edit_text, sorted(menu_map.MAP))


def shelf_choices():
    """"Shelf / Button" texts of every shelf button, in shelf order."""
    from ..ui import shelf
    return [f"{tab}{SHELF_SEP}{label}" for sid, tab in shelf.shelves() for _i, label in shelf.button_labels(sid)]


def shelf_search(self, context, edit_text):
    return _matches(edit_text, shelf_choices())


def shelf_field(shelf_id, button):
    from ..ui import shelf
    tab = next((t for sid, t in shelf.shelves() if sid == shelf_id), um.shelf_text(shelf_id))
    return f"{tab}{SHELF_SEP}{button}" if shelf_id or button else ""


def parse_shelf(text):
    """(shelf id, button label) of a "Shelf / Button" text, or None when no shelf has that button."""
    from ..ui import shelf
    for sid, tab in shelf.shelves():
        prefix = tab + SHELF_SEP
        if text.startswith(prefix) and shelf.button_index(sid, text[len(prefix):]) is not None:
            return sid, text[len(prefix):]
    return None


# --- slot field edits (update callbacks) ------------------------------------------------------------------------

def _new_entry(wm, kind, label, old):
    if kind == "op":
        props, err = _props(wm.allset_mme_props)
        return {"label": label, "type": "op", "op": wm.allset_mme_op.strip(), "props": props or {}}, err
    if kind == "item":
        return {"label": label, "type": "item", "path": wm.allset_mme_item.strip()}, ""
    if kind == "python":
        return {"label": label, "type": "python", "code": wm.allset_mme_code}, ""
    if kind == "shelf":
        found = parse_shelf(wm.allset_mme_shelf) or ("", "")
        return {"label": label, "type": "shelf", "shelf": found[0], "button": found[1]}, ""
    if kind == "kit":
        action = old and um.entry_action(old)
        if isinstance(action, mm.Sub) or action is None:
            return {"label": label, "type": "kit", "action": None}, ""
        return {"label": label, "type": "kit", "action": um.action_to_json(action)}, ""
    return {"label": label, "type": "sub", "radial": {}, "items": [], "options": []}, ""


def _props(text):
    if not text.strip():
        return {}, ""
    try:
        props = json.loads(text)
    except ValueError as ex:
        return None, f"Properties are not JSON: {ex}"
    if not isinstance(props, dict):
        return None, 'Properties must be a JSON object, e.g. {"type": "CENTER"}'
    return props, ""


def _on_label(self, context):
    if _loading[0] or not _wm(context).allset_mme_slot:
        return
    menu, path = _wm(context).allset_mme_menu, full_path(context)
    if um.entry_at(menu, path) is not None and um.update_entry(menu, path, label=_wm(context).allset_mme_label):
        changed(context)


def _on_type(self, context):
    wm = _wm(context)
    if _loading[0] or not wm.allset_mme_slot:
        return
    menu, path = wm.allset_mme_menu, full_path(context)
    old = um.entry_at(menu, path)
    label = wm.allset_mme_label or (old and um.entry_label(old)) or NEW_LABEL
    kind = wm.allset_mme_type
    if kind == "factory":
        if factory_here(context) is None:
            refresh(context, "No kit item at this place: pick another command type")
            return
        um.set_entry(menu, path, um.ref(menu, path))
        changed(context)
        return
    if kind == "sub" and old is not None and old.get("type") == "factory" and um.is_editable_sub(um.entry_action(old)):
        um.container(um.tree_of(menu, create=True), path, create=True)     # the kit submenu, editable in place
        changed(context)
        return
    entry, err = _new_entry(wm, kind, label, old)
    um.set_entry(menu, path, entry)
    changed(context, err)


def _on_field(field):
    def update(self, context):
        wm = _wm(context)
        if _loading[0] or not wm.allset_mme_slot:
            return
        menu, path = wm.allset_mme_menu, full_path(context)
        e = um.entry_at(menu, path)
        if e is None:
            return
        if field == "props":
            props, err = _props(wm.allset_mme_props)
            if props is None:
                refresh(context, err)
                return
            um.update_entry(menu, path, props=props)
        elif field == "op":
            um.update_entry(menu, path, op=wm.allset_mme_op.strip())
        elif field == "item":
            item = wm.allset_mme_item.strip()
            um.update_entry(menu, path, path=item)
            if item and e.get("label") in ("", NEW_LABEL):      # a new item takes the menu item's name
                um.update_entry(menu, path, label=item.split("#")[0].rsplit("/", 1)[-1])
        elif field == "shelf":
            found = parse_shelf(wm.allset_mme_shelf)
            if found is None:
                refresh(context, "Pick a shelf button in the list (type part of its name)")
                return
            um.update_entry(menu, path, shelf=found[0], button=found[1])
            if e.get("label") in ("", NEW_LABEL):              # a new item takes the button's name
                um.update_entry(menu, path, label=found[1])
        elif field == "code":
            um.update_entry(menu, path, code=wm.allset_mme_code)
        elif field == "kit":
            try:
                action = json.loads(wm.allset_mme_kit)
            except ValueError as ex:
                refresh(context, f"Not JSON: {ex}")
                return
            um.update_entry(menu, path, action=action)
        changed(context, "" if um.entry_action(um.entry_at(menu, path)) is not None
                else "This command can't run as it is (shown greyed in the menu)")
    return update


def _on_menu(self, context):
    if _loading[0]:
        return
    _set(_wm(context), allset_mme_path="", allset_mme_slot="")
    refresh(context, "")


# --- hotkey conflicts -------------------------------------------------------------------------------------------

def conflicts(context, menu, hk):
    """[(keymap, command)] of other active 3D View items on ``hk`` (what the custom menu's key takes over)."""
    from .. import marking
    kcs = context.window_manager.keyconfigs
    if kcs.user is None or not hk:
        return []
    own = marking.binding_name(menu)
    out = []
    for km_name, _space in marking.HOTKEY_KEYMAPS:
        km = kcs.user.keymaps.get(km_name)
        for k in km.keymap_items if km is not None else ():
            if not k.active or k.type != hk["key"] or k.value not in {'PRESS', 'CLICK', 'ANY'} or k.any:
                continue
            if any(bool(getattr(k, m)) != bool(hk.get(m)) for m in um.MODIFIERS):
                continue
            binding = getattr(k.properties, "binding", "") if k.idname == "allset.tap_hold" else ""
            if binding == own:
                continue
            if binding:     # a kit hold key: its own name ("Move Tool / Options"), not "Maya Tap/Hold Key"
                from ..operators import taphold
                found = taphold._BINDINGS.get(binding)
                out.append((km_name, found.label if found is not None and found.label else binding))
                continue
            out.append((km_name, k.name or k.idname))
    return out


# --- operators --------------------------------------------------------------------------------------------------

class ALLSET_OT_marking_menu_editor(bpy.types.Operator):
    """Open the Marking Menu Editor: edit the kit's marking menus and make your own (hold a hotkey + LMB)"""
    bl_idname = "allset.marking_menu_editor"
    bl_label = "Marking Menu Editor"

    def execute(self, context):
        if context.window is None:
            return {'CANCELLED'}
        refresh(context, "")
        if marked_window.open_window(context, KIND) is None:
            self.report({'ERROR'}, "Could not open the Marking Menu Editor window")
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_mme_select(bpy.types.Operator):
    """Select this item to edit it"""
    bl_idname = "allset.mme_select"
    bl_label = "Select Item"
    bl_options = {'INTERNAL'}

    slot: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        _set(_wm(context), allset_mme_slot=self.slot)
        refresh(context, "")
        return {'FINISHED'}


class ALLSET_OT_mme_open(bpy.types.Operator):
    """Open this submenu (the breadcrumb goes back)"""
    bl_idname = "allset.mme_open"
    bl_label = "Open Submenu"
    bl_options = {'INTERNAL'}

    path: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        menu = _wm(context).allset_mme_menu
        if self.path and um.container(um.view_tree(menu), self.path) is None:
            self.report({'WARNING'}, "This submenu is filled when the menu opens: it can't be edited")
            return {'CANCELLED'}
        _set(_wm(context), allset_mme_path=self.path, allset_mme_slot="")
        refresh(context, "")
        return {'FINISHED'}


MENU_ACTIONS = (("NEW", "New", "Create a new, empty marking menu (Maya: Create Marking Menu)"),
                ("DUPLICATE", "Duplicate", "A new marking menu made from this one, to bind to a hotkey"),
                ("RENAME", "Rename", "Rename this marking menu"),
                ("DELETE", "Delete", "Delete this marking menu and its hotkey"),
                ("RESTORE", "Restore Default", "Give this kit menu back the kit's items (Maya: Restore Default)"))


class ALLSET_OT_mme_menu(bpy.types.Operator):
    """New / Duplicate / Rename / Delete a marking menu, or Restore Default"""
    bl_idname = "allset.mme_menu"
    bl_label = "Marking Menu"
    bl_options = {'INTERNAL'}

    action: EnumProperty(items=MENU_ACTIONS, options={'SKIP_SAVE'})
    label: StringProperty(name="Name", options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        return next(d for a, _n, d in MENU_ACTIONS if a == props.action)

    def invoke(self, context, event):
        menu = _wm(context).allset_mme_menu
        if self.action in {"NEW", "DUPLICATE", "RENAME"} and not self.label:
            self.label = ("My Marking Menu" if self.action == "NEW" else um.menu_label(menu)
                          + (" Copy" if self.action == "DUPLICATE" else ""))
            return context.window_manager.invoke_props_dialog(self)
        return self.execute(context)

    def execute(self, context):
        wm = _wm(context)
        menu = wm.allset_mme_menu
        label = self.label.strip()
        if self.action in {"NEW", "DUPLICATE"}:
            name = um.new_custom(label or "Marking Menu", from_menu=menu if self.action == "DUPLICATE" else None)
            _set(wm, allset_mme_menu=name, allset_mme_path="", allset_mme_slot="")
            changed(context, f"{um.menu_label(name)}: give it a hotkey to open it (hold the key + LMB)")
        elif self.action == "RENAME":
            if not um.rename_custom(menu, label):
                return {'CANCELLED'}
            changed(context, "")
        elif self.action == "DELETE":
            if not um.is_custom(menu):
                return {'CANCELLED'}
            _set(wm, allset_mme_menu=next(iter(mm.FACTORY)), allset_mme_path="", allset_mme_slot="")
            um.delete_custom(menu)
            changed(context, f"Deleted {menu}")
        elif self.action == "RESTORE":
            if not um.restore(menu):
                return {'CANCELLED'}
            changed(context, f"{um.menu_label(menu)}: the kit's items again")
        return {'FINISHED'}


SLOT_ACTIONS = (("SET", "Add Item", "Put a new item in this empty position"),
                ("CLEAR", "Remove", "Remove this item (a radial position becomes empty)"),
                ("ADD_ITEM", "Add List Item", "Add an item to the list under the radial positions"),
                ("ADD_DIVIDER", "Add Divider", "Add a divider line to the list"),
                ("UP", "Move Up", "Move this list item up"),
                ("DOWN", "Move Down", "Move this list item down"),
                ("OPTION", "Option Box", "Give this item an option box (or take it away)"),
                ("RESTORE", "Kit Default", "Put the kit's own item back at this place"),
                ("SWAP", "Move To", "Move this radial item to another position (swaps with the item there)"))


class ALLSET_OT_mme_slot(bpy.types.Operator):
    """Edit the selected item"""
    bl_idname = "allset.mme_slot"
    bl_label = "Marking Menu Item"
    bl_options = {'INTERNAL'}

    action: EnumProperty(items=SLOT_ACTIONS, options={'SKIP_SAVE'})
    pos: StringProperty(options={'SKIP_SAVE'})      # SWAP: the other radial position

    @classmethod
    def description(cls, context, props):
        return next(d for a, _n, d in SLOT_ACTIONS if a == props.action)

    def execute(self, context):
        wm = _wm(context)
        menu, path, slot = current(context)
        here = full_path(context)
        new = {"label": NEW_LABEL, "type": "op", "op": "", "props": {}}
        done, select = False, slot
        if self.action == "SET" and slot in mm.RADIALS:
            done = um.set_entry(menu, here, new)
        elif self.action == "CLEAR" and slot:
            done = um.set_entry(menu, here, None)
            select = slot if slot in mm.RADIALS else ""
        elif self.action in {"ADD_ITEM", "ADD_DIVIDER"}:
            sel = um._index(slot) if slot else None
            at = um.add_item(menu, path, new if self.action == "ADD_ITEM" else mm.DIVIDER,
                             None if sel is None else sel + 1)
            done, select = at is not None, (at.rsplit("/", 1)[-1] if at else slot)
            if self.action == "ADD_DIVIDER":
                select = ""
        elif self.action in {"UP", "DOWN"} and slot:
            at = um.move_item(menu, here, -1 if self.action == "UP" else 1)
            done, select = at is not None, (at.rsplit("/", 1)[-1] if at else slot)
        elif self.action == "OPTION" and slot:
            done = um.set_option(menu, here, not um.has_option(menu, here))
        elif self.action == "RESTORE" and slot and factory_here(context) is not None:
            done = um.set_entry(menu, here, um.ref(menu, here))
        elif self.action == "SWAP" and slot in mm.RADIALS and self.pos in mm.RADIALS:
            done = um.swap_radial(menu, here, self.pos)
            select = self.pos
        if not done:
            return {'CANCELLED'}
        _set(wm, allset_mme_slot=select)
        changed(context, "")
        return {'FINISHED'}


class ALLSET_OT_mme_hotkey(bpy.types.Operator):
    """Assign the hotkey that opens this marking menu: press the key (with Ctrl / Alt / Shift), Esc cancels.
    Hold it and press LMB to open the menu"""
    bl_idname = "allset.mme_hotkey"
    bl_label = "Assign Hotkey"
    bl_options = {'INTERNAL'}

    key: StringProperty(options={'SKIP_SAVE'})        # event type; empty = capture the next key press
    ctrl: BoolProperty(options={'SKIP_SAVE'})
    alt: BoolProperty(options={'SKIP_SAVE'})
    shift: BoolProperty(options={'SKIP_SAVE'})
    oskey: BoolProperty(options={'SKIP_SAVE'})
    clear: BoolProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        menu = _wm(context).allset_mme_menu
        if not um.is_custom(menu):
            return {'CANCELLED'}
        if self.clear:
            um.set_hotkey(menu, None)
            changed(context, f"{um.menu_label(menu)}: no hotkey")
            return {'FINISHED'}
        if not self.key:
            return {'CANCELLED'}
        hk = {"key": self.key, "ctrl": self.ctrl, "alt": self.alt, "shift": self.shift, "oskey": self.oskey}
        taken = [n for n, h in um.hotkeys() if n != menu and h == um._hotkey(hk)]
        um.set_hotkey(menu, hk)
        changed(context)
        text = hotkey_text(hk)
        clash = conflicts(context, menu, hk)
        if taken:
            msg = f"{text} moved from {', '.join(um.menu_label(n) for n in taken)}"
        elif clash:
            msg = f"{text} was also used by " + ", ".join(f"{c} ({km})" for km, c in clash[:3]) + ": the menu wins"
        else:
            msg = f"{um.menu_label(menu)}: hold {text} and press LMB"
        refresh(context, msg)
        return {'FINISHED'}

    def invoke(self, context, event):
        if self.key or self.clear:
            return self.execute(context)
        if not um.is_custom(_wm(context).allset_mme_menu):
            return {'CANCELLED'}
        _wm(context).allset_mme_capture = True
        marked_window.redraw(context, KIND)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _end(self, context):
        _wm(context).allset_mme_capture = False
        marked_window.redraw(context, KIND)

    def modal(self, context, event):
        from ..keymap import hotkey_rows
        etype = event.type
        if etype in _IGNORE or event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        if etype in _CANCEL:
            self._end(context)
            return {'CANCELLED'}
        if etype not in hotkey_rows.KEYBOARD:
            return {'RUNNING_MODAL'}
        self.key = etype
        self.ctrl, self.alt, self.shift, self.oskey = event.ctrl, event.alt, event.shift, event.oskey
        self._end(context)
        return self.execute(context)


class ALLSET_OT_mme_use_text(bpy.types.Operator):
    """Use the Python of this Text (Text Editor) as the item's command"""
    bl_idname = "allset.mme_use_text"
    bl_label = "Use Text"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        wm = _wm(context)
        text = bpy.data.texts.get(wm.allset_mme_text)
        if text is None or not wm.allset_mme_slot:
            return {'CANCELLED'}
        wm.allset_mme_code = text.as_string()      # its update writes the entry
        return {'FINISHED'}


# --- the window -------------------------------------------------------------------------------------------------

def _slot_text(e, sub_options):
    if e is None:
        return "(empty)"
    label = um.entry_label(e) or "(no label)"
    action = um.entry_action(e)
    if isinstance(action, mm.Sub):
        label += " ▸"
    if e.get("label", "") in sub_options or label in sub_options:
        label += "  □"
    return label


def _draw_menu_bar(layout, context):
    wm = _wm(context)
    menu = wm.allset_mme_menu
    row = layout.row(align=True)
    row.prop(wm, "allset_mme_menu", text="")
    row.operator(ALLSET_OT_mme_menu.bl_idname, text="New", icon='ADD').action = "NEW"
    row.operator(ALLSET_OT_mme_menu.bl_idname, text="Duplicate", icon='DUPLICATE').action = "DUPLICATE"
    if um.is_custom(menu):
        row.operator(ALLSET_OT_mme_menu.bl_idname, text="Rename").action = "RENAME"
        row.operator(ALLSET_OT_mme_menu.bl_idname, text="Delete", icon='TRASH').action = "DELETE"
    else:
        sub = row.row(align=True)
        sub.enabled = um.is_changed(menu)
        sub.operator(ALLSET_OT_mme_menu.bl_idname, text="Restore Default", icon='LOOP_BACK').action = "RESTORE"
    info = layout.row()
    if um.is_custom(menu):
        hk = um.document()["custom"][menu].get("hotkey")
        info.label(text=f"Hotkey: {hotkey_text(hk) + ' + LMB' if hk else 'none'}", icon='EVENT_K' if hk else 'NONE')
        act = info.row(align=True)
        if wm.allset_mme_capture:
            act.alert = True
            act.label(text="Press a key... (Esc cancels)")
        else:
            act.operator(ALLSET_OT_mme_hotkey.bl_idname, text="Assign Hotkey...")
        clr = act.row(align=True)
        clr.enabled = hk is not None
        clr.operator(ALLSET_OT_mme_hotkey.bl_idname, text="", icon='X').clear = True
        if hk:
            clash = conflicts(context, menu, hk)
            if clash:
                layout.label(text="Takes over: " + ", ".join(f"{c} ({km})" for km, c in clash[:3]), icon='ERROR')
    else:
        info.label(text=f"Opens with: {TRIGGERS.get(menu, '—')}" + ("   (changed)" if um.is_changed(menu) else ""))


def _draw_breadcrumb(layout, context):
    menu, path, _slot = current(context)
    row = layout.row(align=True)
    row.alignment = 'LEFT'
    row.operator(ALLSET_OT_mme_open.bl_idname, text=um.menu_label(menu), emboss=bool(path)).path = ""
    steps = um._steps(path)
    for i, step in enumerate(steps):
        sub_path = "/".join(steps[:i + 1])
        e = um.entry_at(menu, sub_path)
        row.label(text="›")
        row.operator(ALLSET_OT_mme_open.bl_idname, text=um.entry_label(e) if e else step,
                     emboss=i < len(steps) - 1).path = sub_path


def _draw_grid(layout, context, sub):
    menu, path, slot = current(context)
    col = layout.column(align=True)
    for line in GRID:
        row = col.row(align=True)
        row.scale_y = 1.6
        for pos in line:
            if pos is None:
                cell = row.row(align=True)
                if path:
                    up = "/".join(um._steps(path)[:-1])
                    cell.operator(ALLSET_OT_mme_open.bl_idname, text="◀ Back", icon='NONE').path = up
                else:
                    cell.enabled = False
                    cell.operator(ALLSET_OT_mme_select.bl_idname, text=f"[ {um.menu_label(menu)} ]").slot = ""
                continue
            e = sub["radial"].get(pos)
            op = row.operator(ALLSET_OT_mme_select.bl_idname, text=f"{pos}: {_slot_text(e, sub['options'])}",
                              depress=slot == pos)
            op.slot = pos


def _draw_list(layout, context, sub):
    _menu, _path, slot = current(context)
    box = layout.box()
    head = box.row(align=True)
    head.label(text="List items")
    head.operator(ALLSET_OT_mme_slot.bl_idname, text="", icon='ADD').action = "ADD_ITEM"
    head.operator(ALLSET_OT_mme_slot.bl_idname, text="", icon='REMOVE').action = "ADD_DIVIDER"
    is_row = um._index(slot) is not None if slot else False
    for a, icon in (("UP", 'TRIA_UP'), ("DOWN", 'TRIA_DOWN')):
        b = head.row(align=True)
        b.enabled = is_row
        b.operator(ALLSET_OT_mme_slot.bl_idname, text="", icon=icon).action = a
    col = box.column(align=True)
    if not sub["items"]:
        col.label(text="(no list items)")
    for i, e in enumerate(sub["items"]):
        step = f"#{i}"
        text = DIVIDER_TEXT if e == mm.DIVIDER else _slot_text(e, sub["options"])
        col.operator(ALLSET_OT_mme_select.bl_idname, text=text, depress=slot == step).slot = step


def _draw_details(layout, context, sub):
    wm = _wm(context)
    menu, path, slot = current(context)
    if not slot:
        layout.label(text="Click a position or a list item to edit it", icon='INFO')
        return
    box = layout.box()
    e = selected_entry(context)
    where = f"Position {slot}" if slot in mm.RADIALS else f"List item {um._index(slot) + 1}"
    top = box.row(align=True)
    top.label(text=where)
    if e is None and slot in mm.RADIALS:
        top.operator(ALLSET_OT_mme_slot.bl_idname, text="Add Item", icon='ADD').action = "SET"
        if factory_here(context) is not None:
            top.operator(ALLSET_OT_mme_slot.bl_idname, text="Kit Default", icon='LOOP_BACK').action = "RESTORE"
        return
    if e is None or e == mm.DIVIDER:
        top.operator(ALLSET_OT_mme_slot.bl_idname, text="Remove", icon='X').action = "CLEAR"
        return
    top.operator(ALLSET_OT_mme_slot.bl_idname, text="Remove", icon='X').action = "CLEAR"
    box.prop(wm, "allset_mme_label", text="Label")
    box.prop(wm, "allset_mme_type", text="Command")
    t = e.get("type")
    if t == "op":
        box.prop(wm, "allset_mme_op", text="Operator")
        box.prop(wm, "allset_mme_props", text="Properties")
    elif t == "item":
        box.prop(wm, "allset_mme_item", text="Menu Item", icon='VIEWZOOM')
    elif t == "python":
        box.prop(wm, "allset_mme_code", text="Python")
        row = box.row(align=True)
        row.prop_search(wm, "allset_mme_text", bpy.data, "texts", text="From Text")
        row.operator(ALLSET_OT_mme_use_text.bl_idname, text="Use")
        if "\n" in wm.allset_mme_code:
            box.label(text=f"{wm.allset_mme_code.count(chr(10)) + 1} lines", icon='TEXT')
    elif t == "shelf":
        box.prop(wm, "allset_mme_shelf", text="Shelf Button", icon='VIEWZOOM')
    elif t == "kit":
        box.prop(wm, "allset_mme_kit", text="Action")
    elif t == "sub":
        box.operator(ALLSET_OT_mme_open.bl_idname, text="Open Submenu", icon='RIGHTARROW').path = full_path(context)
    elif t == "factory":
        action = um.entry_action(e)
        if um.is_editable_sub(action):
            box.operator(ALLSET_OT_mme_open.bl_idname, text="Open Submenu", icon='RIGHTARROW').path = full_path(context)
    if t == "shelf":        # the shelf's tab name, as in the field
        box.label(text="Shelf button: " + (shelf_field(e.get("shelf", ""), e.get("button", "")) or "—"))
    else:
        box.label(text=um.describe(e) or "—")
    row = box.row(align=True)
    row.operator(ALLSET_OT_mme_slot.bl_idname, text="Option Box", icon='CHECKBOX_HLT' if um.has_option(menu, full_path(
        context)) else 'CHECKBOX_DEHLT').action = "OPTION"
    if factory_here(context) is not None and t != "factory":
        row.operator(ALLSET_OT_mme_slot.bl_idname, text="Kit Default", icon='LOOP_BACK').action = "RESTORE"
    if slot in mm.RADIALS:
        move = box.row(align=True)
        move.label(text="Move to:")
        for pos in mm.RADIALS:
            if pos != slot:
                op = move.operator(ALLSET_OT_mme_slot.bl_idname, text=pos)
                op.action, op.pos = "SWAP", pos


class ALLSET_PT_marking_menu_editor(bpy.types.Panel):
    """Maya's Marking Menu Editor (a marked Properties Tool tab in its own window)"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"
    bl_label = TITLE
    bl_options = {'HIDE_HEADER'}
    bl_order = -300

    @classmethod
    def poll(cls, context):
        return marked_window.context_kind(context) == KIND

    def draw(self, context):
        wm = _wm(context)
        layout = self.layout
        _draw_menu_bar(layout, context)
        _draw_breadcrumb(layout, context)
        sub = node(context)
        if sub is None:
            layout.label(text="This submenu can't be edited", icon='ERROR')
            return
        _draw_grid(layout, context, sub)
        _draw_list(layout, context, sub)
        _draw_details(layout, context, sub)
        if wm.allset_mme_message:
            layout.label(text=wm.allset_mme_message, icon='INFO')
        layout.label(text="Changes are saved at once; the next menu opened uses them", icon='FILE_TICK')
        layout.operator("allset.marked_window_close", text="Close")


classes = (ALLSET_OT_marking_menu_editor, ALLSET_OT_mme_select, ALLSET_OT_mme_open, ALLSET_OT_mme_menu,
           ALLSET_OT_mme_slot, ALLSET_OT_mme_hotkey, ALLSET_OT_mme_use_text, ALLSET_PT_marking_menu_editor)

_WM_PROPS = ("allset_mme_menu", "allset_mme_path", "allset_mme_slot", "allset_mme_label", "allset_mme_type",
             "allset_mme_op", "allset_mme_props", "allset_mme_item", "allset_mme_shelf", "allset_mme_code",
             "allset_mme_kit",
             "allset_mme_text", "allset_mme_message", "allset_mme_capture")


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    wm = bpy.types.WindowManager
    wm.allset_mme_menu = EnumProperty(name="Marking Menu", items=menu_items, update=_on_menu,
                                      description="The marking menu to edit")
    wm.allset_mme_path = StringProperty(options={'SKIP_SAVE'})      # the submenu shown ("" = the menu)
    wm.allset_mme_slot = StringProperty(options={'SKIP_SAVE'})      # the selected position / list item in it
    wm.allset_mme_label = StringProperty(name="Label", update=_on_label, description="The text the menu shows")
    wm.allset_mme_type = EnumProperty(name="Command", items=TYPE_ITEMS, update=_on_type,
                                      description="What the item runs")
    wm.allset_mme_op = StringProperty(name="Operator", update=_on_field("op"),
                                      description="A Blender operator id, e.g. mesh.bevel (hover a button with "
                                                  "Python Tooltips on to see one)")
    wm.allset_mme_props = StringProperty(name="Properties", update=_on_field("props"),
                                         description='Operator properties as JSON, e.g. {"type": "CENTER"}')
    wm.allset_mme_item = StringProperty(name="Menu Item", update=_on_field("item"), search=item_search,
                                        description="A Maya main-menu path, e.g. Edit Mesh/Bevel: type words of it "
                                                    "(delete history) and pick one in the list")
    wm.allset_mme_shelf = StringProperty(name="Shelf Button", update=_on_field("shelf"), search=shelf_search,
                                         description="A shelf button: type part of its name and pick it in the list")
    wm.allset_mme_code = StringProperty(name="Python", update=_on_field("code"),
                                        description="Python run like a shelf button (; between statements, or "
                                                    "take a Text)")
    wm.allset_mme_kit = StringProperty(name="Kit Action", update=_on_field("kit"),
                                       description='A kit action as JSON, e.g. ["tool", "builtin.move", true]')
    wm.allset_mme_text = StringProperty(name="Text", description="A Text whose Python becomes the command")
    wm.allset_mme_message = StringProperty(options={'SKIP_SAVE'})
    wm.allset_mme_capture = BoolProperty(name="Capturing a Key", options={'SKIP_SAVE'})


def unregister():
    for name in _WM_PROPS:
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
