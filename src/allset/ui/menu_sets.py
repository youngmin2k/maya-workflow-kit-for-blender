# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya main menu bar and menu sets (Modeling/Rigging/Animation/FX/Rendering).

Maya's menu sets: the common menus are always shown,
the menu set dropdown swaps the menus after them. Structure from
``menu_data`` (Maya's menu structure), Blender actions from
``menu_map``; unmapped items are drawn greyed out.

One ``Menu`` class per Maya menu and submenu is built from the data at import
time. ``menu_idname(maya_name)`` is the public name for other UI (hotbox).
"""

import json

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from .. import i18n, results
from .. import compat, undo_steps
from . import draw_safe, editor_menu_data, menu_data, menu_hotkeys, menu_icons, menu_map, notices, option_click

COMMON_SET = "commonMenuSet"
ALWAYS = "(always visible)"
DEFAULT_SET = "modelingMenuSet"

# Menu set dropdown items.
SET_ITEMS = tuple((sid, label, f"Maya {label} menu set")
                  for sid, label, _menus in menu_data.MENU_SETS if sid != COMMON_SET)
# Plugin menus (MASH, Bifrost, Boss) are listed in the sets but have no data: skipped.
_SET_MENUS = {sid: tuple(m for m in menus if m in menu_data.MENUS)
              for sid, _label, menus in menu_data.MENU_SETS}
_ALWAYS_MENUS = tuple(n for n, m in menu_data.MENUS.items() if m[1] == ALWAYS)
# Main menu bar option boxes + the editor menu bars'
OPTION_BOXES = menu_data.OPTION_BOXES | editor_menu_data.OPTION_BOXES


def menu_idname(maya_name):
    return f"ALLSET_MT_{maya_name}"


def menus_for_set(set_id):
    """Maya menu names shown in the menu bar for ``set_id``, left to right."""
    return _SET_MENUS[COMMON_SET] + _SET_MENUS.get(set_id, ()) + _ALWAYS_MENUS


def iter_items(items=None, prefix=""):
    """Yield (label path, item) for every entry below ``items`` (all menus if None)."""
    if items is None:
        for label, _set, _src, its in menu_data.MENUS.values():
            yield from iter_items(its, label)
        for editor, menus in editor_menu_data.EDITORS.items():
            for title, its in menus:
                yield from iter_items(its, f"{editor}/{title}")
        return
    for path, it in children(items, prefix):
        if path is None:
            continue
        yield path, it
        kids = sub_items(path, it)
        if kids:
            yield from iter_items(kids, path)


def sub_items(path, it):
    """Children of a menu entry: Maya's run-time ones (``menu_map.CHILDREN``), else the data's."""
    return menu_map.CHILDREN.get(path) or (it[1] if len(it) > 1 else None)


def children(items, prefix):
    """(path, item) per direct entry; path None for dividers. A label repeated
    among siblings gets "#2", "#3" (Select > Components for polygons, curves,
    surfaces). ``menu_map.EXTRA`` items follow the entry they are attached to."""
    seen = {}
    for it in items:
        if it[0] == "-":
            yield None, it
            continue
        n = seen[it[0]] = seen.get(it[0], 0) + 1
        path = f"{prefix}/{it[0]}" + (f"#{n}" if n > 1 else "")
        yield path, it
        for extra in menu_map.EXTRA.get(path, ()):
            yield (None if extra[0] == "-" else f"{prefix}/{extra[0]}"), extra


def current_set(context=None):
    from .. import preferences
    try:
        return preferences.get(context).menu_set
    except KeyError:  # add-on preferences not registered (disable in progress)
        return DEFAULT_SET


# --- items ---------------------------------------------------------------------

def draw_item(layout, path, label, icon_value=0, translate=True):
    """Draw one Maya menu item: its Blender action, or greyed out. An item with a "not in Blender" notice and an
    operator substitute runs through ``allset.menu_item``, whose tooltip carries the notice. So does a
    mapped item Blender's poll would grey out (component commands in object mode): Maya keeps its menu items
    enabled and runs or warns (``menu_map.OBJECT_MODE``). ``icon_value``: the item's kit icon
    (``menu_icons``), 0 = none. ``translate=False``: ``label`` is already in the interface language."""
    s = menu_map.spec(path)
    # Blender draws, right-aligned, a shortcut it finds in the keymaps for the very operator + properties of an
    # item (Increment and Save "Ctrl Alt S", Exit "Ctrl Q"): operator items go through ``allset.menu_item``, which
    # no key runs, so only the Maya hotkey drawn into the label shows.
    if s is not None and s[0] == "op" and path in menu_map.GREY_ON_POLL and not op_polls(s[1]):
        draw_spec(layout, label, s, path, icon_value=icon_value, translate=translate)  # Maya greys it here
        return
    if s is not None and (s[0] == "op" or s[0] in ("v3d", "tool") and (
            notices.notice(path) or not runs_directly(path, s) or _has_saved_options(path))):
        op = draw_safe.op(layout, ALLSET_OT_menu_item.bl_idname, text=label, icon_value=icon_value,
                          translate=translate)
        op.item, op.clicked = path, True
        return
    draw_spec(layout, label, s, path, icon_value=icon_value, translate=translate)


def _has_saved_options(path):
    from ..operators import option_windows
    w = option_windows.find_path(path)
    return w is not None and w.click_saved and option_windows.saved(w.key) is not None


def op_polls(target):
    """Blender's poll of operator ``target`` in the current context (True if it can't be asked)."""
    mod, name = target.split(".")
    try:
        return getattr(getattr(bpy.ops, mod), name).poll()
    except (AttributeError, KeyError, RuntimeError, TypeError):
        return True


def runs_directly(path, s):
    """False if the item must go through ``allset.menu_item`` to stay enabled the Maya way."""
    if path in menu_map.OBJECT_MODE and bpy.context.mode == 'OBJECT':
        return False
    if path in menu_map.EDIT_MODE and bpy.context.mode == 'EDIT_MESH':
        return False
    return s[0] != "op" or op_polls(s[1])


_WHAT = {"mesh": "mesh components (vertices, edges or faces)", "curve": "curve points (CVs)",
         "armature": "joints (skeleton edit mode)", "pose": "joints (pose mode)", "uv": "UVs (UV Editor)",
         "object": "objects", "anim": "objects to key", "paint": "a mesh", "sculpt": "a mesh"}


def maya_warning(path, target):
    """Maya-style warning for an item Blender can't run on this selection."""
    label = path.rsplit("/", 1)[-1]
    what = _WHAT.get(target.split(".")[0], "what it works on")
    return f"{label}: select {what} first."


def draw_spec(layout, label, s, path, icon='NONE', icon_value=0, translate=True):
    """Draw a normalised action (``menu_map.normalize``); None = greyed out with
    ``path`` (the Maya menu path) in the tooltip. ``icon_value`` (a kit icon) wins over ``icon``.
    ``translate=False``: ``label`` is already in the interface language (Blender doesn't look it up again)."""
    iv = {"icon_value": icon_value} if icon_value else {"icon": icon}
    if not translate:
        iv["translate"] = False
    if s is None:
        draw_safe.op(layout, ALLSET_OT_menu_unavailable.bl_idname, text=label, **iv).item = path
        return
    kind, target, props = s
    if kind == "prop":
        draw_prop(layout, label, target, props, path, translate=translate)
    elif kind == "menu":
        layout.menu(proxy_menu(target), text=label, **iv)
    elif kind == "pie":
        draw_safe.op(layout, "wm.call_menu_pie", text=label + " ▸", **iv).name = target
    elif kind == "tool":
        op = draw_safe.op(layout, ALLSET_OT_menu_tool.bl_idname, text=label, **iv)
        op.tool = target
        op.edit = props["edit"]
        op.item = path              # Ctrl+Shift+click: to the shelf
    elif kind == "v3d":
        op = draw_safe.op(layout, ALLSET_OT_menu_run.bl_idname, text=label, **iv)
        op.op = target
        op.props = json.dumps(props)
        op.item = path
    else:
        op = draw_safe.op(layout, target, text=label, **iv)
        for key, value in props.items():
            setattr(op, key, value)


def prop_owner(context, target):
    """(owner, attribute) of a ``("prop", target)`` mapping: a path from the context ("space_data.show_handles"),
    "addon_prefs.<name>" = this add-on's preferences, "view3d.<path>" = the 3D View the Display menu acts on
    (``status_line.view3d_space``; the main menu bar is in the top bar, whose space has no overlays).
    Blender's own preferences are never a target (store review, #40 / #43): such a path has no owner."""
    *parents, attr = target.split(".")
    if parents and parents[0] == "preferences":
        return None, attr
    if parents and parents[0] == "addon_prefs":
        from .. import preferences
        owner, parents = preferences.get(context), parents[1:]
    elif parents and parents[0] == "view3d":
        from .status_line import view3d_space
        owner, parents = view3d_space(context), parents[1:]
    else:
        owner = context
    for name in parents:
        owner = getattr(owner, name, None)
        if owner is None:
            return None, attr
    return (owner, attr) if hasattr(owner, attr) else (None, attr)


def draw_prop(layout, label, target, props, path="", translate=True):
    """A Maya check item = Blender's check box; a radio choice = ``prop_enum`` for enums, else a radio-marked
    button that sets the value (``allset.menu_set_value``). Greyed with the notice when the property isn't
    there in this context (e.g. a Graph Editor setting drawn from another editor)."""
    owner, attr = prop_owner(bpy.context, target)
    tr = {} if translate else {"translate": False}
    if owner is None:
        draw_safe.op(layout, ALLSET_OT_menu_unavailable.bl_idname, text=label, **tr).item = path
        return
    if "value" not in props:
        from . import maya_dock
        current = getattr(owner, attr)
        if maya_dock.drawing_torn() and isinstance(current, bool):
            # a torn-off menu is a panel with menu emboss, where Blender drops a check box (Blender 5.2):
            # the check mark is drawn as the item's icon
            layout.prop(owner, attr, text=label, **tr, icon='CHECKBOX_HLT' if current else 'CHECKBOX_DEHLT')
            return
        layout.prop(owner, attr, text=label, **tr)
        return
    value = props["value"]
    rna = owner.bl_rna.properties.get(attr)
    if rna is not None and rna.type == 'ENUM':
        layout.prop_enum(owner, attr, value, text=label, **tr)
        return
    current = getattr(owner, attr)
    on = abs(current - value) < 1e-6 if isinstance(value, float) else current == value
    op = draw_safe.op(layout, ALLSET_OT_menu_set_value.bl_idname, text=label, **tr,
                      icon='RADIOBUT_ON' if on else 'RADIOBUT_OFF')
    op.target, op.value = target, repr(value)


def set_prop(context, target, props):
    """Run a ``("prop", ...)`` mapping: toggle the check box or set the radio value."""
    owner, attr = prop_owner(context, target)
    if owner is None:
        return {'CANCELLED'}
    setattr(owner, attr, props["value"] if "value" in props else not getattr(owner, attr))
    return {'FINISHED'}


class ALLSET_OT_menu_set_value(bpy.types.Operator):
    """Maya radio menu item: set this choice"""
    bl_idname = "allset.menu_set_value"
    bl_label = "Set"
    bl_options = {'INTERNAL', 'UNDO'}

    target: StringProperty(options={'SKIP_SAVE'})
    value: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        import ast
        return set_prop(context, self.target, {"value": ast.literal_eval(self.value)})


# Maya's option box is a small square at the right end of the item's line.
# A second button on a Blender menu line breaks consecutive lines into a staircase (checked again in step
# 103 with row / split / column / grid_flow lines), so the item stays one button:
# its label ends with Maya's box mark, click = the command, press and hold = "Option Box" = the option window
# (``operators/option_windows.py``) or the command's own settings. Since #82 the hold needs no drag:
# the pointer is put on the hold menu's "Option Box" row, so letting go runs it.
BOX_MARK = "  ❒"
BOX_TIP = i18n.mark("❒ Option box: click the box, or press and hold the item (or Shift / Ctrl+click)")


def _draw_boxed(layout, path, text, icon_value=0):
    """An item with a Maya option box; ``text`` already ends with the box mark (``item_texts``) and is in the
    interface language."""
    s = menu_map.spec(path)
    if s is None or s[0] in ("menu", "pie"):
        draw_spec(layout, text, s, path, icon_value=icon_value, translate=False)
        return
    op = draw_safe.op_hold(layout, ALLSET_OT_menu_item.bl_idname, text=text, icon_value=icon_value, translate=False,
                           menu=ALLSET_MT_option_box.bl_idname)
    op.item, op.clicked = path, True


# --- Maya hotkey column ------------------------------------------------------------------------
# Maya prints an item's hotkey right-aligned (File > New Scene "Ctrl+N",
# Edit Mesh > Bevel "Ctrl+B"), the option box after it. Blender takes no such text for a Python button,
# so the label carries it: label + filler + "Ctrl+N  ❒", the filler sized with the menu font so the tails line
# up on the right.
HAIR = "\u200a"          # a hair space: fine filler steps (plain spaces only if the UI font lacks it)
MIN_GAP = 3              # spaces between the longest label and its tail


def hotkey(path):
    """The Maya hotkey shown beside a menu item ("" without one): ui/menu_hotkeys.py (tools/gen_menu_hotkeys.py)."""
    return menu_hotkeys.HOTKEYS.get(path, "")


def font_size(context=None):
    """The menu text size in px: the UI style's widget points x the effective UI scale (0 in background -> 1)."""
    prefs = (context or bpy.context).preferences
    scale = prefs.system.ui_scale or 1.0
    try:
        points = prefs.ui_styles[0].widget.points
    except (IndexError, AttributeError):
        points = 11
    return points * scale


def text_width(text, size):
    import blf
    blf.size(0, size)
    return blf.dimensions(0, text)[0]


def filler(width, size, space=None, hair=None):
    """Blank text about ``width`` px wide: spaces, then hair spaces for the rest (if the UI font has them)."""
    space = space or (text_width(" ", size) or 1.0)
    if hair is None:
        hair = text_width(HAIR, size)
        if not 0.0 < hair < space:
            hair = 0.0
    n = int(max(width, 0.0) // space)
    hairs = int(round((width - n * space) / hair)) if hair else 0
    return " " * n + HAIR * hairs


def aligned(entries, size=None):
    """[(label, tail)] -> texts with the tails right-aligned on one column (rows without a tail stay as they are)."""
    if not any(tail for _label, tail in entries):
        return [label for label, _tail in entries]
    size = size or font_size()
    space = text_width(" ", size) or 1.0
    hair = text_width(HAIR, size)
    if not 0.0 < hair < space:
        hair = 0.0
    widths = [(text_width(label, size), text_width(tail, size) if tail else 0.0) for label, tail in entries]
    total = max(lw + MIN_GAP * space + tw for (lw, tw), (_l, tail) in zip(widths, entries) if tail)
    out = []
    for (label, tail), (lw, tw) in zip(entries, widths):
        if not tail:
            out.append(label)
            continue
        out.append(label + filler(max(total - lw - tw, space), size, space, hair) + tail)
    return out


def item_texts(rows, size=None):
    """{path: drawn text} for a menu's (path, label, boxed) rows: label + Maya hotkey + option box, aligned. In a
    menu with option boxes a hotkey without a box keeps the box column empty, so every hotkey ends on one line
    (Maya: Increment and Save "Ctrl+Alt+S" under "Ctrl+S" of Save Scene)."""
    size = size or font_size()
    any_box = any(boxed for _p, _l, boxed in rows)
    box_gap = filler(text_width(BOX_MARK, size), size) if any_box else ""
    entries = []
    for path, label, boxed in rows:
        key = hotkey(path)
        if key:
            tail = key + (BOX_MARK if boxed else box_gap)
        else:
            tail = BOX_MARK.strip() if boxed else ""
        entries.append((label, tail))
    return {row[0]: text for row, text in zip(rows, aligned(entries, size))}


def _dynamic_label(path, label):
    """The label a menu row shows, in the interface language. Maya labels built when the menu opens:
    Edit > Repeat = 'Repeat "<last command>"' (Maya 2022 Edit menu)."""
    if path == "Edit/Repeat":
        from ..operators import repeat_maya
        try:
            return repeat_maya.label(bpy.context)
        except (AttributeError, ReferenceError):
            pass
    return i18n.iface(label)


def menu_rows(items, prefix):
    """(path, item) rows of a Maya menu with each item's label as shown (``_dynamic_label``); separators as they
    are. Shared with ``option_click``, which models the drawn widths."""
    return [(path, ((_dynamic_label(path, it[0]),) + tuple(it[1:])) if path is not None else it)
            for path, it in children(items, prefix)]


def _draw_items(layout, items, prefix, submenus):
    kids = menu_rows(items, prefix)
    texts = item_texts([(path, it[0], path in OPTION_BOXES) for path, it in kids
                        if path is not None and not (sub_items(path, it) and path not in menu_map.MAP)])
    for path, it in kids:
        if path is None:
            layout.separator()
            if it[1]:
                # Maya section titles are small; a lower row also keeps File inside a
                # 900 px window at 125 %
                _section_label(layout, it[1])
            continue
        iv = menu_icons.icon_value(path)
        if sub_items(path, it) and path not in menu_map.MAP:
            layout.menu(submenus[path], text=it[0] + (BOX_MARK if path in OPTION_BOXES else ""), icon_value=iv,
                        translate=False)
        elif path in OPTION_BOXES:
            _draw_boxed(layout, path, texts[path], iv)
        else:
            draw_item(layout, path, texts[path], iv, translate=False)


def _section_label(layout, text):
    """A Maya section title, on a lower row than an item (Maya draws them small)."""
    row = layout.row()
    if row is None:      # a minimal stand-in layout (tests)
        layout.label(text=text)
        return
    row.scale_y = 0.8
    row.label(text=text)


# Blender menus a Maya item opens (Recent Files = TOPBAR_MT_file_open_recent) are drawn through a kit subclass:
# for the original Blender prints the keymap shortcut of ``wm.call_menu`` ("Shift Ctrl O").
_proxies = {}          # Blender menu idname -> kit subclass idname
_PROXY_CLASSES = []


def proxy_menu(target):
    return _proxies.get(target, target)


def _menu_targets():
    out = set()
    for path in menu_map.MAP:
        s = menu_map.spec(path)
        if s is not None and s[0] == "menu" and not s[1].startswith("ALLSET_"):
            out.add(s[1])
    return sorted(out)


def register_proxies():
    for target in _menu_targets():
        base = getattr(bpy.types, target, None)
        if not (isinstance(base, type) and issubclass(base, bpy.types.Menu) and "draw" in base.__dict__):
            continue
        idname = "ALLSET_MT_proxy_" + target
        cls = type(idname, (base,), {"bl_idname": idname, "__doc__": base.__doc__ or base.bl_label})
        try:
            bpy.utils.register_class(cls)
        except (RuntimeError, ValueError):
            continue
        _proxies[target] = idname
        _PROXY_CLASSES.append(cls)


def unregister_proxies():
    for cls in reversed(_PROXY_CLASSES):
        if cls.is_registered:
            bpy.utils.unregister_class(cls)
    _PROXY_CLASSES.clear()
    _proxies.clear()


# Menu class of every Maya submenu path (e.g. "Graph Editor/Tangents/Default In Tangent"), for buttons that open one
SUBMENU_IDS = {}


def _make_menu(idname, label, prefix, items, top_label=None):
    submenus = {}
    classes = []
    for path, it in iter_items(items, prefix):
        if sub_items(path, it) and path not in submenus and path not in menu_map.MAP:
            submenus[path] = f"{idname}_{len(submenus)}"
    # Build the submenu classes (each draws its own children).
    SUBMENU_IDS.update(submenus)
    for path, sub_id in submenus.items():
        node = _find(items, prefix, path)
        classes.append(_menu_class(sub_id, node[0], path, sub_items(path, node), submenus))
    classes.insert(0, _menu_class(idname, label, prefix, items, submenus, top_label))
    return classes


def _find(items, prefix, path):
    for p, it in iter_items(items, prefix):
        if p == path:
            return it
    raise KeyError(path)


def _menu_class(idname, label, prefix, items, submenus, top_label=None):
    blender = menu_map.BLENDER_MENU.get(top_label) if top_label else None

    def draw(self, context):
        layout = self.layout
        from . import maya_dock
        maya_dock.draw_tear_line(layout, idname)    # Maya's dotted tear-off line
        if top_label:
            option_click.note_draw(context, top_label)    # opened from the Maya menu bar?
        _draw_items(layout, items, prefix, submenus)
        if blender:
            layout.separator()
            layout.menu(blender[0], text=blender[1], icon='BLENDER')

    return type(idname, (bpy.types.Menu,), {
        "bl_idname": idname, "bl_label": label, "draw": draw,
        "__doc__": f"Maya menu: {prefix}"})


# --- operators -----------------------------------------------------------------

class ALLSET_OT_menu_unavailable(bpy.types.Operator):
    """Maya menu item without a Blender equivalent in Maya Workflow Kit (always greyed out)"""
    bl_idname = "allset.menu_unavailable"
    bl_label = "Not Available"
    bl_options = {'INTERNAL'}

    item: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return False

    @classmethod
    def description(cls, context, props):
        return notices.tooltip(props.item, mapped=False) or _no_equivalent(props.item)

    def execute(self, context):
        return {'CANCELLED'}


class ALLSET_OT_menu_item(bpy.types.Operator):
    """Maya menu item with an option box (press and hold: Option Box)"""
    bl_idname = "allset.menu_item"
    bl_label = "Menu Item"
    bl_options = {'INTERNAL'}

    item: StringProperty(options={'SKIP_SAVE'})
    # drawn in a Maya menu (not run from Python / a marking menu): Ctrl+Shift+click adds it to the shelf
    clicked: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return True

    @classmethod
    def description(cls, context, props):
        if props.item not in menu_map.MAP:
            return notices.tooltip(props.item, mapped=False) or _no_equivalent(props.item)
        text = notices.tooltip(props.item, mapped=True) or _op_description(props.item)
        if props.item in OPTION_BOXES:
            text += "\n" + i18n.tip(BOX_TIP)
        return text

    def execute(self, context):
        action = menu_map.MAP.get(self.item)
        if action is None:
            results.result(self, f"Maya: {self.item} has no Blender equivalent in Maya Workflow Kit yet")
            return {'CANCELLED'}
        if self.clicked and add_to_shelf_if_asked(self, context, self.item):     # before Shift / Ctrl alone
            return {'FINISHED'}
        if self.item in OPTION_BOXES and modifier_held():      # Shift / Ctrl+click = the option box
            return bpy.ops.allset.menu_option_box('INVOKE_DEFAULT', item=self.item)
        if self.clicked and self.item in OPTION_BOXES and option_click.on_box(context, self.item):
            return bpy.ops.allset.menu_option_box('INVOKE_DEFAULT', item=self.item)    # a click on ❒
        if context.mode == 'EDIT_MESH' and self.item in menu_map.EDIT_MODE:     # component mode
            try:
                return bpy.ops.allset.component_command('EXEC_DEFAULT', True, item=self.item)
            except RuntimeError as ex:      # Blender's own refusal (Select > Similar with nothing selected ...)
                from ..operators import maya_errors
                maya_errors.report_nested(self, ex)
                return {'CANCELLED'}
        rule = menu_map.OBJECT_MODE.get(self.item) if context.mode == 'OBJECT' else None
        if isinstance(rule, str):     # Maya warns and does nothing
            self.report({'WARNING'}, rule)
            return {'CANCELLED'}
        if rule:
            return bpy.ops.allset.menu_whole_mesh('EXEC_DEFAULT', True, item=self.item)
        s = menu_map.spec(self.item)
        if s[0] == "op" and not op_polls(s[1]):
            self.report({'WARNING'}, maya_warning(self.item, s[1]))
            return {'CANCELLED'}
        from ..marking.modal import run_action
        try:
            run_action(context, action, path=self.item)
        except RuntimeError as ex:
            from ..operators import maya_errors
            maya_errors.report_nested(self, ex)       # a Maya Error stays an Error (#152)
            return {'CANCELLED'}
        return {'FINISHED'}


def _no_equivalent(path):
    """Tooltip of a greyed Maya item without a notice, in the tooltip language."""
    return f"Maya: {i18n.path(path, i18n.tip)}\n" + i18n.tip("No Blender equivalent in Maya Workflow Kit yet")


def _op_description(path):
    """Tooltip of a mapped item: its Blender operator's description, else the item's label (tooltip language)."""
    s = menu_map.spec(path)
    if s is not None and s[0] in ("op", "v3d"):
        try:
            mod, name = s[1].split(".")
            text = getattr(getattr(bpy.ops, mod), name).get_rna_type().description
            if text:
                return i18n.tip(text)
        except (AttributeError, KeyError, ValueError):
            pass
    return i18n.tip(path.rsplit('/', 1)[-1])


# Values for commands run on a whole object:
# Bevel fraction 0.5, Chamfer Vertices 0.25 (Blender: percent of the adjacent edge).
WHOLE_MESH_PROPS = {
    "Edit Mesh/Chamfer Vertices": {"offset_type": 'PERCENT', "offset_pct": 25.0, "affect": 'VERTICES'},
    "Edit Mesh/Average Vertices": {"repeat": 10},
    # Circularize: allset.circularize's own defaults apply; the old LoopTools "value" key made every
    # object-mode Circularize raise TypeError
}


class ALLSET_OT_menu_whole_mesh(bpy.types.Operator):
    """Run a component command on every component of the selected meshes (Maya does that for an object
    selection) and come back to object mode, as one undo step"""
    bl_idname = "allset.menu_whole_mesh"
    bl_label = "Menu Item on Whole Mesh"
    bl_options = {'INTERNAL', 'REGISTER', 'UNDO'}

    item: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        rule = menu_map.OBJECT_MODE.get(self.item)
        s = menu_map.spec(self.item)
        meshes = [ob for ob in context.selected_objects if ob.type == 'MESH']
        if not isinstance(rule, tuple) or s is None or s[0] not in ("op", "v3d"):
            return {'CANCELLED'}
        if not meshes:
            self.report({'WARNING'}, "Nothing selected.")
            return {'CANCELLED'}
        view_layer = context.view_layer
        if view_layer.objects.active not in meshes:
            view_layer.objects.active = meshes[0]
        mod, name = s[1].split(".")
        props = {**s[2], **WHOLE_MESH_PROPS.get(self.item, {})}
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            bpy.ops.mesh.select_mode(type=rule[1])
            bpy.ops.mesh.select_all(action='SELECT')
            getattr(getattr(bpy.ops, mod), name)('EXEC_DEFAULT', **props)
        except (RuntimeError, TypeError) as ex:
            self.report({'WARNING'}, str(ex).strip().splitlines()[-1])
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
        return {'FINISHED'}


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_component_command(bpy.types.Operator):
    """A Maya Edit / Select / Modify command in component mode, run the way Maya runs it there
    (``menu_map.EDIT_MODE``)"""
    bl_idname = "allset.component_command"
    bl_label = "Maya Command in Component Mode"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    item: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    @classmethod
    def description(cls, context, props):
        return _op_description(props.item)

    def execute(self, context):
        rule = menu_map.EDIT_MODE.get(self.item)
        if rule is None:
            return {'CANCELLED'}
        kind, label = rule[0], self.item.rsplit("/", 1)[-1]
        if kind == "warn":
            self.report({'WARNING'}, rule[1])
            return {'CANCELLED'}
        if kind == "none":
            results.result(self, f"{label}: works on objects; in component mode Maya leaves it alone "
                                  "(F8 = object mode)")
            return {'CANCELLED'}
        from ..marking.modal import run_action
        try:
            with undo_steps.nested():          # this operator is the undo step (UNDO)
                if kind == "run":
                    run_action(context, rule[1], path=self.item)
                elif kind == "object":
                    bpy.ops.object.mode_set(mode='OBJECT')
                    run_action(context, rule[1], path=self.item)
                elif kind == "owner":
                    _run_on_owners(context, rule[1], self.item)
        except RuntimeError as ex:
            from ..operators import maya_errors
            maya_errors.report_nested(self, ex)
            return {'CANCELLED'}
        return {'FINISHED'}


def _select_only(context, objects):
    for ob in context.scene.objects:
        try:
            ob.select_set(ob in objects)
        except RuntimeError:          # not in the view layer
            pass


def _run_on_owners(context, action, path):
    """Run ``action`` in object mode on the objects whose components are being edited, then come back to component
    mode on the same objects with their components still selected (Maya keeps the component selection)."""
    from ..marking.modal import run_action
    owners = list(context.objects_in_mode)
    active = context.view_layer.objects.active
    bpy.ops.object.mode_set(mode='OBJECT')
    _select_only(context, owners)
    try:
        run_action(context, action, path=path)
    finally:
        _select_only(context, owners)
        context.view_layer.objects.active = active
        bpy.ops.object.mode_set(mode='EDIT')


# --- opening the option box by holding (#82) ----------------------------------------------------------
# Blender 4.5 (interface_handlers.cc / interface_layout.cc ui_item_menu_hold): a held
# ``operator_menu_hold`` button opens its hold menu after BUTTON_AUTO_OPEN_THRESH (0.2 s) *below* the button, as a
# popup of its own; letting go outside it cancels it, so before #82 the user had to drag onto its row. Python
# can't tell where on the item a click landed, Shift / Ctrl / Alt+click run nothing in event simulation, and an
# option window opened from a timer while the menus are open leaves them open under it. So:
# 1. when the hold menu opens, the pointer goes onto its (taller) "Option Box" row: letting go runs it;
# 2. the Maya menu the item was in is still open then (Blender closes only the hold menu), so the option box first
#    moves the pointer to the far side of the window (Blender closes a menu the mouse left, UI_BLOCK_MOVEMOUSE_QUIT;
#    checked in a normal GUI Blender: event simulation gets no event from a warp), then after AWAY_TICK puts it back
#    and opens the option window there.
HOLD_ROW_SCALE = 1.5        # the hold menu's row height in menu rows: room for where the pointer sat on the item
HOLD_WARP_PX = 28           # pointer move at UI scale 1: item row centre -> hold row centre (23 px + half the taller row)
HOLD_ROOM_PX = 60           # less room than this under the pointer: Blender opens the hold menu above the item
AWAY_TICK = 0.05            # s the pointer stays away while Blender closes the menu
LAST_WARP = []              # the pointer moves of the last hold / close: (move, window x, y), for tests
_hold = {"t": -1.0, "back": None}


def modifier_held():
    """Shift or Ctrl physically down (the OS key state; Blender gives a menu item no event)."""
    from ..operators import keystate
    return any(keystate.is_down(k) for k in ("LEFT_SHIFT", "RIGHT_SHIFT", "LEFT_CTRL", "RIGHT_CTRL"))


# --- Ctrl+Shift+click: the item to the current shelf -------------------------------------------------
# Maya: Shift+Ctrl+click on a menu item adds it to the current shelf; Maya's
# Maya appends a shelf button with the item's label / annotation / image (running the item's command)
# to the shelf tab shown, factory tabs included, and prints nothing. The kit button runs
# the path like the menu (``shelf.add_menu_item``, ``marking.modal.run_action(("item", path))``).

def ctrl_shift_held():
    """Ctrl and Shift both physically down (OS key state; unknown = not held)."""
    from ..operators import keystate

    def down(keys):
        return any(keystate.is_down(k) for k in keys)
    return down(("LEFT_SHIFT", "RIGHT_SHIFT")) and down(("LEFT_CTRL", "RIGHT_CTRL"))


def add_to_shelf_if_asked(op, context, path):
    """With Ctrl+Shift held, put a button for Maya menu item ``path`` on the current shelf instead of running it;
    True if it did. Only mapped Maya menu paths (marking-menu pies pass their own labels)."""
    if not path or path not in menu_map.MAP or not ctrl_shift_held():
        return False
    from . import shelf
    _shelf_id, tab, button = shelf.add_menu_item(context, path)
    results.result(op, f"{button['label']} added to the {tab} shelf")
    return True


def _point_at_hold_row_later(context):
    """After the hold menu opened, put the pointer on its Option Box row (once per hold: a refresh redraws it)."""
    import time
    from .. import live_refs
    win = context.window
    now = time.monotonic()
    if win is None or now - _hold["t"] < 0.5:
        return
    _hold["t"] = now
    ptr = win.as_pointer()

    def later():
        from ..operators import keystate
        w = live_refs.window(ptr)
        if w is None or keystate.is_down('LEFTMOUSE') is False:      # already let go: the hold menu is gone
            return None
        with bpy.context.temp_override(window=w):
            bpy.ops.allset.option_box_point('INVOKE_DEFAULT', move='HOLD_ROW')
        return None
    bpy.app.timers.register(later, first_interval=0.0)


def _close_menu_then_open(context, item):
    """Close the Maya menu still open under the hold menu, then open ``item``'s option box where the pointer was."""
    from .. import live_refs
    if context.window is None:
        return
    wp = context.window.as_pointer()
    ap = context.area.as_pointer() if context.area else 0
    rp = context.region.as_pointer() if context.region else 0
    # away right now: Blender queues a mouse move after closing the hold menu, built from the pointer position, and
    # where the pointer was is the Maya menu's next row - a submenu there opens, and Blender never mouse-outs a menu
    # while a newer one is open (interface_handlers.cc ui_mouse_motion_towards_check "annoying fix").
    # Blender 5.x (menu_close_leave off, its default) closes menus only on a click: no warp, the option window
    # opens over the Maya menu (compat.menus_close_on_leave).
    away = compat.menus_close_on_leave(context.preferences)
    if away:
        with bpy.context.temp_override(window=context.window):
            bpy.ops.allset.option_box_point('INVOKE_DEFAULT', move='AWAY')

    def later():
        w = live_refs.window(wp)
        if w is None:
            return None
        if away:
            with bpy.context.temp_override(window=w):
                bpy.ops.allset.option_box_point('INVOKE_DEFAULT', move='BACK')
        area = live_refs.area(ap, w)
        region = live_refs.region(area, rp)
        with bpy.context.temp_override(window=w, area=area, region=region):
            bpy.ops.allset.menu_option_box('INVOKE_DEFAULT', item=item)
        return None
    bpy.app.timers.register(later, first_interval=AWAY_TICK)


class ALLSET_OT_option_box_point(bpy.types.Operator):
    """Move the pointer for a held option box: onto the hold menu's row, away (closes the menu) and back"""
    bl_idname = "allset.option_box_point"
    bl_label = "Point for Option Box"
    bl_options = {'INTERNAL'}

    move: EnumProperty(items=[('HOLD_ROW', "Hold Row", ""), ('AWAY', "Away", ""), ('BACK', "Back", "")],
                       options={'SKIP_SAVE'})

    def invoke(self, context, event):      # called from a timer: the event is the window's latest state
        win = context.window
        scale = context.preferences.system.ui_scale or 1.0
        x, y = event.mouse_x, event.mouse_y
        if self.move == 'HOLD_ROW':
            step = round(HOLD_WARP_PX * scale)
            y = y - step if y >= HOLD_ROOM_PX * scale else y + step
            LAST_WARP[:] = []
        elif self.move == 'AWAY':
            _hold["back"] = (x, y)
            x = 2 if x > win.width // 2 else win.width - 3     # the far side: outside the menu and its safety margin
        else:
            if _hold["back"] is None:
                return {'CANCELLED'}
            x, y = _hold["back"]
            _hold["back"] = None
        win.cursor_warp(x, y)
        LAST_WARP.append((self.move, x, y))
        return {'FINISHED'}


class ALLSET_MT_option_box(bpy.types.Menu):
    """The option box of the Maya menu item that was held"""
    bl_idname = "ALLSET_MT_option_box"
    bl_label = "Option Box"

    def draw(self, context):
        props = getattr(context, "button_operator", None)
        layout = self.layout
        layout.scale_y = HOLD_ROW_SCALE
        op = draw_safe.op(layout, ALLSET_OT_menu_option_box.bl_idname, text="Option Box" + BOX_MARK)
        op.item = getattr(props, "item", "")
        op.from_hold = True
        _point_at_hold_row_later(context)


class ALLSET_OT_menu_option_box(bpy.types.Operator):
    """Maya option box: the command's option window"""
    bl_idname = "allset.menu_option_box"
    bl_label = "Option Box"
    bl_options = {'INTERNAL'}

    item: StringProperty(options={'SKIP_SAVE'})
    from_hold: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})     # run from a hold menu: close the Maya menu first

    @classmethod
    def description(cls, context, props):
        from ..operators import option_windows
        label = props.item.rsplit('/', 1)[-1]
        if props.item not in menu_map.MAP:
            return f"{label} options (greyed: no Blender equivalent in Maya Workflow Kit)"
        w = option_windows.find_path(props.item)
        if w is not None:
            return w.title
        kind = option_kind(props.item)
        if kind == "tool":
            return f"{label}: the tool and its Tool Settings"
        return f"{label} Options: run, then its settings (Adjust Last Operation)"

    def execute(self, context):
        action = menu_map.MAP.get(self.item)
        if action is None:
            results.result(self, f"Maya: {self.item} has no Blender equivalent in Maya Workflow Kit yet")
            return {'CANCELLED'}
        if self.from_hold and not bpy.app.background:
            _close_menu_then_open(context, self.item)
            return {'FINISHED'}
        if option_kind(self.item) == "generic":
            return bpy.ops.allset.option_generic('INVOKE_DEFAULT', item=self.item)
        from ..marking.modal import run_action
        try:
            run_action(context, action, option=True, path=self.item)
        except RuntimeError as ex:
            from ..operators import maya_errors
            maya_errors.report_nested(self, ex)
            return {'CANCELLED'}
        return {'FINISHED'}


def option_kind(path):
    """What a mapped item's option box opens: "window" (a kit / Maya option window), "dialog" (the operator's own
    options window or file dialog), "tool" (tool + Tool Settings), "redo" (run + Adjust Last Operation with the
    operator's settings), "generic" (a window saying Blender has no settings for it), "menu"; "none" = unmapped."""
    from ..operators import option_windows
    s = menu_map.spec(path)
    if s is None:
        return "none"
    if option_windows.find_path(path) is not None:
        return "window"
    kind, target, _props = s
    if kind == "tool":
        return "tool"
    if kind in ("menu", "pie"):
        return "menu"
    if target in ("render.render", "allset.render"):
        return "generic"          # Blender's render reads Render Settings; it has no options of its own to adjust
    mod, name = target.split(".")
    try:
        rna = getattr(getattr(bpy.ops, mod), name).get_rna_type()
    except (AttributeError, KeyError):
        return "none"
    if "option_box" in rna.properties or "filepath" in rna.properties:
        return "dialog"
    shown = [p for p in rna.properties if p.identifier != "rna_type" and not p.is_hidden]
    return "redo" if shown else "generic"     # allset.option_generic: a window that says Blender has none


def _call(op_id, props):
    mod, name = op_id.split(".")
    return getattr(getattr(bpy.ops, mod), name)('INVOKE_DEFAULT', **props)


class ALLSET_OT_menu_run(bpy.types.Operator):
    """Run a Blender operator in the largest 3D View (for Maya menu items)"""
    bl_idname = "allset.menu_run"
    bl_label = "Run in 3D View"
    bl_options = {'INTERNAL'}

    op: StringProperty(options={'SKIP_SAVE'})
    props: StringProperty(default="{}", options={'SKIP_SAVE'})
    item: StringProperty(options={'SKIP_SAVE', 'HIDDEN'})       # the Maya menu path (drawn in a menu)

    @classmethod
    def description(cls, context, props):
        try:
            mod, name = props.op.split(".")
            return getattr(getattr(bpy.ops, mod), name).get_rna_type().description
        except (ValueError, AttributeError, KeyError):
            return ""

    def execute(self, context):
        if add_to_shelf_if_asked(self, context, self.item):
            return {'FINISHED'}
        from .status_line import main_view3d
        area, region = main_view3d(context.window.screen if context.window else None)
        if area is None:
            self.report({'ERROR'}, "No 3D View to run this in")
            return {'CANCELLED'}
        try:
            with context.temp_override(window=context.window, area=area, region=region):
                _call(self.op, json.loads(self.props))
        except RuntimeError as ex:  # poll failed etc.
            text = str(ex).strip()
            # a Maya-style line instead of Blender's "poll() failed, context is incorrect"
            self.report({'WARNING'}, maya_warning(self.op, self.op) if "poll()" in text else text)
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_menu_tool(bpy.types.Operator):
    """Switch the 3D View tool (for Maya menu items that pick a tool)"""
    bl_idname = "allset.menu_tool"
    bl_label = "Set Tool"
    bl_options = {'INTERNAL'}

    tool: StringProperty(options={'SKIP_SAVE'})
    edit: BoolProperty(description="Enter mesh edit (component) mode first", options={'SKIP_SAVE'})
    item: StringProperty(options={'SKIP_SAVE', 'HIDDEN'})       # the Maya menu path (drawn in a menu)

    def execute(self, context):
        if add_to_shelf_if_asked(self, context, self.item):
            return {'FINISHED'}
        ob = context.active_object
        if self.edit:
            if ob is None or ob.type != 'MESH':
                self.report({'ERROR'}, "Select a mesh first")
                return {'CANCELLED'}
            if context.mode != 'EDIT_MESH' and not ob.visible_get():
                self.report({'WARNING'}, f"{ob.name} is hidden: show it first")
                return {'CANCELLED'}
            if context.mode != 'EDIT_MESH':
                # its own undo step: Ctrl+Z after the tool's first edit must stay in edit mode
                bpy.ops.object.mode_set('EXEC_DEFAULT', True, mode='EDIT')
        try:
            bpy.ops.wm.tool_set_by_id(name=self.tool, space_type='VIEW_3D')
        except RuntimeError as ex:
            self.report({'ERROR'}, str(ex).strip())
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_MT_ui_elements(bpy.types.Menu):
    """Maya Windows > UI Elements"""
    bl_idname = "ALLSET_MT_ui_elements"
    bl_label = "UI Elements"

    def draw(self, context):
        from .. import preferences
        prefs = preferences.get(context)
        layout = self.layout
        layout.prop(prefs, "maya_top_bar")
        layout.prop(prefs, "maya_panel_menus")
        layout.prop(prefs, "show_status_line")
        from .shelf import strip_area
        draw_safe.op(layout, "allset.shelf_strip_toggle", text="Shelf",
                     icon='CHECKBOX_HLT' if strip_area(context.screen) else 'CHECKBOX_DEHLT')
        layout.prop(prefs, "show_command_line")
        layout.prop(prefs, "show_help_line")


class ALLSET_MT_addon_menus(bpy.types.Menu):
    """Menus other add-ons put in Blender's top bar"""
    bl_idname = "ALLSET_MT_addon_menus"
    bl_label = "Add-on Menus"

    def draw(self, context):
        for func in addon_menu_funcs(context):
            try:     # one broken add-on must not stop the rest, as in Blender's own menus
                func(self, context)
            except Exception:
                import traceback
                traceback.print_exc()


# Other add-ons append their own menus to Blender's top bar menu (TOPBAR_MT_editor_menus), where they follow Help.
# The Maya menu bar replaces that menu, so those entries follow the Maya menus instead (or sit at the end of the
# overflow menu when the bar is full). Their width is unknown: each keeps this much room when the bar is fitted.
ADDON_MENU_UNITS = 5.0
_KIT = __package__.rpartition(".")[0]


def addon_menu_funcs(context=None):
    """Draw functions other add-ons added to ``TOPBAR_MT_editor_menus`` (not Blender's own, not the kit's), with
    the workspace's add-on filter applied like Blender does."""
    draw = getattr(bpy.types, "TOPBAR_MT_editor_menus", None)
    funcs = getattr(getattr(draw, "draw", None), "_draw_funcs", None) or ()
    workspace = getattr(context, "workspace", None) if context is not None else None
    owners = None
    if workspace is not None and getattr(workspace, "use_filter_by_owner", False):
        owners = {o.name for o in workspace.owner_ids}
    out = []
    for func in funcs:
        if getattr(func, "__qualname__", "") == "TOPBAR_MT_editor_menus.draw":
            continue
        module = getattr(func, "__module__", "") or ""
        if module == _KIT or module.startswith(_KIT + "."):
            continue
        owner = getattr(func, "_owner", None)
        if owners is not None and owner is not None and owner not in owners:
            continue
        out.append(func)
    return out


def draw_addon_menus(layout, context):
    """Other add-ons' top-bar menus, in line (a header row or a menu)."""
    if addon_menu_funcs(context):
        layout.menu_contents(ALLSET_MT_addon_menus.bl_idname)


class ALLSET_MT_menu_bar(bpy.types.Menu):
    """The Maya menu bar folded into one menu (header menus collapsed)"""
    bl_idname = "ALLSET_MT_menu_bar"
    bl_label = "Menus"

    def draw(self, context):
        draw_menu_bar(self.layout, context, collapsed=True)


# Maya-style menu bar items are their text plus a small padding; Blender's header pulldowns add about a UI unit, so
# the bar overflowed a 1600 px window at 125 %. Each item gets its blf text width plus this padding.
MENU_PAD_PX = 11


def menu_width_units(text, context):
    """``ui_units_x`` of a header pulldown showing ``text`` at Maya's spacing. ``text`` is the English label; it is
    taken as the interface shows it, so translated labels (Japanese, #249) are not cut off."""
    import blf
    prefs = context.preferences
    scale = prefs.system.ui_scale or 1.0
    blf.size(0, prefs.ui_styles[0].widget.points * scale)
    w = blf.dimensions(0, bpy.app.translations.pgettext_iface(text))[0]
    return (w + MENU_PAD_PX * scale) / (20.0 * scale)


def _menu(layout, context, idname, collapsed):
    if collapsed:
        layout.menu(idname)
        return
    label = getattr(bpy.types, idname).bl_label
    sub = layout.row(align=True)
    sub.ui_units_x = menu_width_units(label, context)
    sub.menu(idname)


def draw_menu_bar(layout, context, collapsed=False, menu_set=True):
    """Blender logo menu, Maya common menus, set menus, Cache, Help. ``menu_set``: the menu set dropdown after the
    common menus (only when no Status Line shows it: Maya keeps it at the Status Line's left end)."""
    from .. import preferences
    prefs = preferences.get(context)
    if collapsed:
        layout.menu("TOPBAR_MT_blender", text="Blender")
    else:
        layout.menu("TOPBAR_MT_blender", text="", icon='BLENDER')
    set_id = prefs.menu_set
    for name in _SET_MENUS[COMMON_SET]:
        _menu(layout, context, menu_idname(name), collapsed)
    if collapsed:
        layout.separator()
        layout.prop(prefs, "menu_set", text="")
    elif menu_set:
        sub = layout.row()
        sub.ui_units_x = 5.5
        sub.prop(prefs, "menu_set", text="")
    for name in _SET_MENUS.get(set_id, ()) + _ALWAYS_MENUS:
        _menu(layout, context, menu_idname(name), collapsed)
    draw_addon_menus(layout, context)


def editor_menu_idname(editor, index):
    """Menu class of the ``index``-th menu of a Maya editor menu bar (``editor_menu_data.EDITORS``)."""
    return "ALLSET_MT_ed_" + "".join(ch for ch in editor.title() if ch.isalnum()) + f"_{index}"


_menu_classes = []
for _name, (_label, _set, _src, _items) in menu_data.MENUS.items():
    _menu_classes.extend(_make_menu(menu_idname(_name), _label, _label, _items, top_label=_label))
for _editor, _menus in editor_menu_data.EDITORS.items():
    for _i, (_title, _items) in enumerate(_menus):
        _menu_classes.extend(_make_menu(editor_menu_idname(_editor, _i), _title, f"{_editor}/{_title}", _items))

classes = (ALLSET_OT_menu_unavailable, ALLSET_OT_menu_set_value, ALLSET_OT_menu_item, ALLSET_OT_menu_whole_mesh,
           ALLSET_OT_component_command, ALLSET_MT_option_box, ALLSET_OT_option_box_point,
           ALLSET_OT_menu_option_box, ALLSET_OT_menu_run, ALLSET_OT_menu_tool,
           ALLSET_MT_ui_elements, ALLSET_MT_addon_menus, ALLSET_MT_menu_bar, *option_click.classes, *_menu_classes)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    register_proxies()
    menu_icons.register()


def unregister():
    menu_icons.unregister()
    unregister_proxies()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
