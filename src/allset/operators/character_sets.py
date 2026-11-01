# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Character Sets on Blender Keying Sets.

A Maya character set is a node that owns a list of attributes; one of them can be *current* (Time Slider field), and
then Set Key (S) keys the current character's attributes whatever is selected. Blender's absolute Keying Set is that
concept: a named list of channel paths in the scene, one of them active (Blender's own I key uses it). So:

- every scene Keying Set is a kit character set (its ``bl_label`` = the Maya name); current = ``keying_sets.active``;
- a member = one keying-set path (ID, data path, index), Maya name ``pCube1.translateX`` (``member_name``);
- a subcharacter is a Keying Set whose parent is recorded in the scene ID property ``allset_character_parent``
  ({child: parent}; Blender keying sets don't nest) — keying a character keys its subcharacters' members too;
- Maya's "selected character nodes" (Select Character Set Node, then Add / Remove / Merge / Attribute Editor) =
  ``WindowManager.allset_character_nodes`` (comma list), only while no object is selected (selecting an object in
  Maya deselects the character node).

Rules (the spec's numbers): Create = every keyable channel of each selected node except Scale and
Visibility (1), names ``character1`` / ``subCharacter1`` counting up, the new set becomes current (1); S with a current
character keys all its members (3); Add / Remove = the Channel Box's selected channels (5); Merge = into the last
picked (6).
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from .. import results
from .naming import next_number

PARENT = "allset_character_parent"
PICKED = "allset_character_nodes"
EXCLUDED_KINDS = ("SCALE", "VIS")       # default Create Character Set: All keyable except Scale, Visibility
MAYA_ATTR = {"tx": "translateX", "ty": "translateY", "tz": "translateZ", "rx": "rotateX", "ry": "rotateY",
             "rz": "rotateZ", "sx": "scaleX", "sy": "scaleY", "sz": "scaleZ", "v": "visibility"}
MSG_NEED_CURRENT = "Must have a current character or select a character."
MSG_NO_ATTRS = "No attributes are selected in the Channel Box."
MSG_SUB_NEED = "Must have a current character."
MSG_MERGE = "Select the characters to be merged."


def _cb():
    from ..ui import channel_box
    return channel_box


# --- pure helpers (tests/test_step187_character_sets.py) --------------------------------------------

def next_name(taken, base):
    """Maya's naming: ``<base><N>`` one past the highest, gaps not filled."""
    return f"{base}{next_number(base, set(taken))}"


def merge_target(picked, parents):
    """Maya Merge Character Sets: the top parent among the picked characters when one is a subcharacter of another,
    else the last picked."""
    tops = [c for c in picked if any(parents.get(o) == c for o in picked if o != c)]
    return tops[-1] if tops else picked[-1]


def channel_key_of(data_path, index):
    """Channel Box key of an object channel path, or None (bone / other paths)."""
    from ..ui import channel_box as cb
    if data_path.startswith('["') and data_path.endswith('"]'):
        return cb.CUSTOM_PREFIX + data_path[2:-2]
    for key, _label, path, idx, _kind in cb.MAIN:
        if path == data_path and (idx == index or (idx == -1 and index in (-1, 0))):
            return key
    return None


def maya_attr(data_path, index):
    key = channel_key_of(data_path, index)
    if key is None:
        return f"{data_path}[{index}]" if index >= 0 else data_path
    from ..ui import channel_box as cb
    return key[len(cb.CUSTOM_PREFIX):] if key.startswith(cb.CUSTOM_PREFIX) else MAYA_ATTR[key]


# --- scene state -------------------------------------------------------------------------------------

def characters(scene):
    return list(scene.keying_sets)


def find(scene, name):
    return next((ks for ks in scene.keying_sets if ks.bl_label == name), None)


def current(scene):
    return scene.keying_sets.active


def set_current(scene, ks):
    sets = list(scene.keying_sets)
    scene.keying_sets.active_index = sets.index(ks) if ks is not None else -1


def remove_character(scene, ks):
    """Delete a keying set: Python's KeyingSets has no remove(), Blender's operator removes the active one (the
    current character comes back unless it was the one removed)."""
    keep = current(scene)
    set_current(scene, ks)
    with bpy.context.temp_override(scene=scene):
        bpy.ops.anim.keying_set_remove()
    if keep is not None and keep != ks:
        set_current(scene, find(scene, keep.bl_label))


def parents(scene):
    raw = scene.get(PARENT)
    return {str(k): str(v) for k, v in raw.items()} if raw else {}


def _set_parent(scene, child, parent):
    d = parents(scene)
    if parent is None:
        d.pop(child, None)
    else:
        d[child] = parent
    scene[PARENT] = d


def children(scene, name):
    return [c for c, p in parents(scene).items() if p == name and find(scene, c) is not None]


def member_name(path):
    idb = path.id
    return f"{idb.name if idb is not None else '?'}.{maya_attr(path.data_path, path.array_index)}"


def member_names(scene, ks):
    """Maya ``cmds.character(query=True)``: own attributes, then the subcharacters."""
    return [member_name(p) for p in ks.paths] + children(scene, ks.bl_label)


def all_paths(scene, ks, _seen=None):
    """Every path keyed by Set Key on ``ks``: its own and its subcharacters' (recursively)."""
    seen = _seen if _seen is not None else set()
    if ks.bl_label in seen:
        return []
    seen.add(ks.bl_label)
    out = list(ks.paths)
    for child in children(scene, ks.bl_label):
        out += all_paths(scene, find(scene, child), seen)
    return out


def node_paths(node, keys):
    """(ID, data path, index) of Channel Box ``keys`` on ``node`` (object or pose bone)."""
    cb = _cb()
    for key in keys:
        if cb.is_blend_key(key):        # a blendShape weight: its animation lives on the shape Key
            kb = cb.blend_target(node, key)
            if kb is not None:
                yield kb.id_data, cb.blend_path(kb.name), 0       # keying-set paths keep a scalar at 0
            continue
        path, idx, _kind = cb.channel_path(key)
        full = cb.full_path(node, path)
        if full is not None:
            yield node.id_data, full, idx


def create_keys(node, excluded=EXCLUDED_KINDS):
    """Maya Create Character Set attributes of one node: keyable, not the ``excluded`` kinds (default: Scale /
    Visibility; the option window's All keyable except: LOC / ROT / SCALE / VIS / CUSTOM = Dynamic)."""
    cb = _cb()
    keys = []
    for key in cb._visible_channels(node):
        kind = cb.MAIN_BY_KEY[key][4] if key in cb.MAIN_BY_KEY else "CUSTOM"
        if kind not in excluded and cb.is_keyable(node, key):
            keys.append(key)
    return keys


def unique_name(taken, name, base):
    """Maya node naming for the window's Name: the name itself while free, else its stem counting up from 1
    (``hero`` -> ``hero1``, ``character1`` -> ``character2``)."""
    name = name.strip() or f"{base}1"
    if name not in taken:
        return name
    return next_name(taken, name.rstrip("0123456789") or base)


def _has(ks, idb, data_path, index):
    return any(p.id == idb and p.data_path == data_path and p.array_index == index for p in ks.paths)


def add_members(ks, triples):
    n = 0
    for idb, data_path, index in triples:
        if not _has(ks, idb, data_path, index):
            ks.paths.add(idb, data_path, index=index, group_method='KEYINGSET')
            n += 1
    return n


def remove_members(ks, triples):
    want = {(idb.as_pointer(), dp, i) for idb, dp, i in triples}
    gone = [p for p in ks.paths if p.id is not None and (p.id.as_pointer(), p.data_path, p.array_index) in want]
    for p in gone:
        ks.paths.remove(p)
    return len(gone)


def new_character(scene, base, nodes, name="", keys_of=None):
    """A new character set ``name`` (empty = ``<base>N``) of ``nodes``; ``keys_of(node)`` -> Channel Box keys
    (default: the standard attribute rule)."""
    taken = {ks.bl_label for ks in scene.keying_sets}
    name = unique_name(taken, name, base) if name else next_name(taken, base)
    ks = scene.keying_sets.new(idname="", name=name)
    ks.bl_label = name
    for node in nodes:
        add_members(ks, node_paths(node, (keys_of or create_keys)(node)))
    return ks


def _hierarchy(nodes):
    """Maya Include: Hierarchy below selected node — the nodes and everything under them, each once."""
    out, seen = [], set()
    for node in nodes:
        for n in (node, *getattr(node, "children_recursive", ())):
            if n.as_pointer() not in seen:
                seen.add(n.as_pointer())
                out.append(n)
    return out


def picked(context):
    """Character nodes picked with Select Character Set Node, while no object is selected (Maya: one selection)."""
    if context.selected_objects:
        return []
    raw = getattr(context.window_manager, PICKED, "")
    scene = context.scene
    return [ks for ks in (find(scene, n) for n in raw.split(",") if n) if ks is not None]


def selected_nodes(context):
    """The selected objects / pose bones, lead first (the Maya lead is the active object even when it is not
    selected; Maya's character commands only take the selection)."""
    return [n for n in _cb().targets(context) if not isinstance(n, bpy.types.Object) or n.select_get()]


def targets(context):
    """Maya Key > Character Set edit commands: selected character nodes, else the current character."""
    ks = picked(context)
    if ks:
        return ks
    cur = current(context.scene)
    return [cur] if cur is not None else []


def key_current(context, keytype='KEYFRAME'):
    """Set Key on the current character: every member path, through the kit keyframe for object channels
    (Maya tangents, animation layers). Count of channels keyed."""
    scene = context.scene
    ks = current(scene)
    if ks is None:
        return 0
    cb = _cb()
    n = 0
    for p in all_paths(scene, ks):
        idb = p.id
        if idb is None:
            continue
        key = channel_key_of(p.data_path, p.array_index) if isinstance(idb, bpy.types.Object) else None
        try:
            if key is not None:
                n += bool(cb.keyframe(idb, key, keytype))
            else:
                index = p.array_index
                try:
                    if not hasattr(idb.path_resolve(p.data_path), "__len__"):
                        index = -1          # a scalar (a blendShape weight): its path is kept at 0
                except ValueError:
                    pass
                n += bool(idb.keyframe_insert(p.data_path, index=index, keytype=keytype))
        except (TypeError, RuntimeError):
            pass
    return n


# --- operators ---------------------------------------------------------------------------------------

class ALLSET_OT_character_create(bpy.types.Operator):
    """Make a character set of the selected objects' keyable channels (not Scale / Visibility) and make it current"""
    bl_idname = "allset.character_create"
    bl_label = "Create Character Set"
    bl_options = {'UNDO'}

    sub: BoolProperty(name="Subcharacter", default=False, options={'SKIP_SAVE'})
    # Create (Sub)character Set Options: default values
    character_name: StringProperty(name="Name", default="", options={'SKIP_SAVE'},
                         description="Empty: character1 / subCharacter1, counting up")
    attributes: EnumProperty(name="Include", items=[('ALL', "All keyable", ""),
                                                    ('CHANNEL_BOX', "From Channel Box", ""),
                                                    ('EXCEPT', "All keyable except", "")],
                             default='EXCEPT', options={'SKIP_SAVE'})
    exclude_translate: BoolProperty(name="Translate", default=False, options={'SKIP_SAVE'})
    exclude_rotate: BoolProperty(name="Rotate", default=False, options={'SKIP_SAVE'})
    exclude_scale: BoolProperty(name="Scale", default=True, options={'SKIP_SAVE'})
    exclude_visibility: BoolProperty(name="Visibility", default=True, options={'SKIP_SAVE'})
    exclude_dynamic: BoolProperty(name="Dynamic", default=False, options={'SKIP_SAVE'})
    hierarchy: BoolProperty(name="Hierarchy below selected node", default=False, options={'SKIP_SAVE'})

    def _keys_of(self, context):
        if self.attributes == 'CHANNEL_BOX':
            cb = _cb()
            picked = cb.selected_channels(context)
            return lambda node: [k for k in picked if cb.has_channel(node, k)]
        excluded = ()
        if self.attributes == 'EXCEPT':
            excluded = tuple(kind for kind, on in (("LOC", self.exclude_translate), ("ROT", self.exclude_rotate),
                                                   ("SCALE", self.exclude_scale), ("VIS", self.exclude_visibility),
                                                   ("CUSTOM", self.exclude_dynamic)) if on)
        return lambda node: create_keys(node, excluded)

    def execute(self, context):
        scene = context.scene
        cur = current(scene)
        if self.sub:
            if cur is None:
                self.report({'ERROR'}, MSG_SUB_NEED)
                return {'CANCELLED'}
        nodes = selected_nodes(context)
        if self.hierarchy and self.attributes != 'CHANNEL_BOX':     # Maya: hierarchy is off with From Channel Box
            nodes = _hierarchy(nodes)
        ks = new_character(scene, "subCharacter" if self.sub else "character", nodes, self.character_name,
                           self._keys_of(context))
        if self.sub:
            _set_parent(scene, ks.bl_label, cur.bl_label)
            set_current(scene, cur)          # keying_sets.new() makes the new set active; Maya keeps the current
        else:
            set_current(scene, ks)
        _redraw(context)
        results.result(self, f"Result: {ks.bl_label}")
        return {'FINISHED'}


class ALLSET_OT_character_edit(bpy.types.Operator):
    """Add the Channel Box's selected channels to (or remove them from) the current character set"""
    bl_idname = "allset.character_edit"
    bl_label = "Edit Character Set"
    bl_options = {'UNDO'}

    add: BoolProperty(name="Add", default=True, options={'SKIP_SAVE'})

    def execute(self, context):
        sets = targets(context)
        if not sets:
            self.report({'ERROR'}, MSG_NEED_CURRENT)
            return {'CANCELLED'}
        cb = _cb()
        keys = cb.selected_channels(context)
        triples = [t for node in selected_nodes(context) for t in node_paths(node, [k for k in keys
                                                                              if cb.has_channel(node, k)])]
        if not triples:
            self.report({'ERROR'}, MSG_NO_ATTRS)
            return {'CANCELLED'}
        n = sum((add_members if self.add else remove_members)(ks, triples) for ks in sets)
        _redraw(context)
        results.result(self, f"{'Added' if self.add else 'Removed'} {n} attribute(s)")
        return {'FINISHED'}


class ALLSET_OT_character_merge(bpy.types.Operator):
    """Merge the picked character sets into one (Key > Select Character Set Node first; Ctrl adds)"""
    bl_idname = "allset.character_merge"
    bl_label = "Merge Character Sets"
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        sets = picked(context)
        if len(sets) < 2:
            self.report({'ERROR'}, MSG_MERGE)
            return {'CANCELLED'}
        names = [ks.bl_label for ks in sets]
        into = find(scene, merge_target(names, parents(scene)))
        for ks in sets:
            if ks == into:
                continue
            add_members(into, [(p.id, p.data_path, p.array_index) for p in ks.paths if p.id is not None])
            for child in children(scene, ks.bl_label):
                _set_parent(scene, child, into.bl_label)
            _set_parent(scene, ks.bl_label, None)
            remove_character(scene, ks)
        into = find(scene, merge_target(names, parents(scene)))
        set_current(scene, into)
        setattr(context.window_manager, PICKED, into.bl_label)
        _redraw(context)
        results.result(self, f"Result: {into.bl_label}")
        return {'FINISHED'}


class ALLSET_OT_character_set_current(bpy.types.Operator):
    """Set the current character set (Set Key keys its attributes)"""
    bl_idname = "allset.character_set_current"
    bl_label = "Set Current Character Set"
    bl_options = {'UNDO'}

    name: StringProperty(name="Character Set", options={'SKIP_SAVE'})

    def execute(self, context):
        scene = context.scene
        set_current(scene, find(scene, self.name) if self.name else None)
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_character_select(bpy.types.Operator):
    """Select a character set's member objects, or the character set node itself"""
    bl_idname = "allset.character_select"
    bl_label = "Select Character Set"
    bl_options = {'UNDO'}

    name: StringProperty(name="Character Set", options={'SKIP_SAVE'})
    node: BoolProperty(name="Node", default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        scene = context.scene
        ks = find(scene, self.name)
        if ks is None:
            return {'CANCELLED'}
        for ob in context.view_layer.objects:
            if ob is not None and ob.select_get():
                ob.select_set(False)
        wm = context.window_manager
        if self.node:
            from . import keystate
            add = any(keystate.is_down(k) for k in ("LEFT_CTRL", "RIGHT_CTRL", "LEFT_SHIFT", "RIGHT_SHIFT"))
            old = [n for n in getattr(wm, PICKED, "").split(",") if n and n != self.name] if add else []
            setattr(wm, PICKED, ",".join(old + [self.name]))
            results.result(self, self.name)
        else:
            setattr(wm, PICKED, "")
            obs = []
            for p in all_paths(scene, ks):
                if isinstance(p.id, bpy.types.Object) and p.id not in obs:
                    obs.append(p.id)
            for ob in obs:
                try:
                    ob.select_set(True)
                except RuntimeError:      # not in this view layer
                    pass
            if obs:
                context.view_layer.objects.active = obs[0]
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_character_attributes(bpy.types.Operator):
    """The current (or picked) character set's attributes, like Maya's Attribute Editor of the character node"""
    bl_idname = "allset.character_attributes"
    bl_label = "Character Set Attributes"

    def execute(self, context):
        if not targets(context):
            self.report({'ERROR'}, MSG_NEED_CURRENT)
            return {'CANCELLED'}
        bpy.ops.wm.call_panel(name=ALLSET_PT_character_set.bl_idname, keep_open=True)
        return {'FINISHED'}


class ALLSET_OT_character_remove_member(bpy.types.Operator):
    """Remove this attribute from the character set"""
    bl_idname = "allset.character_remove_member"
    bl_label = "Remove Attribute"
    bl_options = {'UNDO'}

    name: StringProperty(options={'SKIP_SAVE'})
    index: bpy.props.IntProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        ks = find(context.scene, self.name)
        if ks is None or not 0 <= self.index < len(ks.paths):
            return {'CANCELLED'}
        ks.paths.remove(ks.paths[self.index])
        _redraw(context)
        return {'FINISHED'}


class ALLSET_PT_character_set(bpy.types.Panel):
    bl_idname = "ALLSET_PT_character_set"
    bl_label = "Character Set"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_ui_units_x = 14

    def draw(self, context):
        lay = self.layout
        scene = context.scene
        for ks in targets(context):
            box = lay.box()
            box.label(text=ks.bl_label, icon='KEYINGSET')
            col = box.column(align=True)
            for i, p in enumerate(ks.paths):
                row = col.row(align=True)
                row.label(text=member_name(p))
                op = row.operator(ALLSET_OT_character_remove_member.bl_idname, text="", icon='X', emboss=False)
                op.name, op.index = ks.bl_label, i
            for child in children(scene, ks.bl_label):
                col.label(text=child, icon='KEYINGSET')
            if not ks.paths and not children(scene, ks.bl_label):
                col.label(text="(no attributes)")


class ALLSET_PT_character_editor(bpy.types.Panel):
    """Windows > Relationship Editors > Character Sets: Maya's Relationship Editor in character mode
    lists the character sets, highlights the current one and edits its members from the selection — here a popup over
    the kit character sets (= scene Keying Sets)."""
    bl_idname = "ALLSET_PT_character_editor"
    bl_label = "Relationship Editor: Character Sets"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_ui_units_x = 16

    def draw(self, context):
        lay = self.layout
        scene = context.scene
        lay.label(text=self.bl_label)
        sets = characters(scene)
        cur = current(scene)
        if not sets:
            row = lay.row()
            row.enabled = False
            row.label(text=_CharacterList.empty)
        col = lay.column(align=True)
        for ks in sets:
            op = col.operator(ALLSET_OT_character_set_current.bl_idname, text=ks.bl_label, icon='KEYINGSET',
                              depress=ks == cur)
            op.name = ks.bl_label
        row = lay.row(align=True)
        row.operator(ALLSET_OT_character_create.bl_idname, text="Create Character Set")
        if cur is None:
            return
        box = lay.box()
        box.label(text=f"{cur.bl_label} members")
        mcol = box.column(align=True)
        for i, p in enumerate(cur.paths):
            r = mcol.row(align=True)
            r.label(text=member_name(p))
            op = r.operator(ALLSET_OT_character_remove_member.bl_idname, text="", icon='X', emboss=False)
            op.name, op.index = cur.bl_label, i
        if not cur.paths:
            mcol.label(text="(no attributes)")
        r = box.row(align=True)
        r.operator(ALLSET_OT_character_edit.bl_idname, text="Add Selected").add = True
        r.operator(ALLSET_OT_character_edit.bl_idname, text="Remove Selected").add = False


class ALLSET_OT_character_editor(bpy.types.Operator):
    """List the character sets and edit the current one's members (Maya Relationship Editor: Character Sets)"""
    bl_idname = "allset.character_editor"
    bl_label = "Character Sets"

    def execute(self, context):
        bpy.ops.wm.call_panel(name=ALLSET_PT_character_editor.bl_idname, keep_open=True)
        return {'FINISHED'}


class _CharacterList:
    """Shared: one row per character set (Maya: the menu is built when it opens)."""
    op_props = {}
    empty = "No Character Sets Defined"

    def draw(self, context):
        lay = self.layout
        sets = characters(context.scene)
        if not sets:
            row = lay.row()
            row.enabled = False
            row.label(text=self.empty)
            return
        for ks in sets:
            self.item(lay, context, ks)


class ALLSET_MT_character_select_node(_CharacterList, bpy.types.Menu):
    bl_idname = "ALLSET_MT_character_select_node"
    bl_label = "Select Character Set Node"

    def item(self, lay, context, ks):
        op = lay.operator(ALLSET_OT_character_select.bl_idname, text=ks.bl_label)
        op.name, op.node = ks.bl_label, True


class ALLSET_MT_character_select_members(_CharacterList, bpy.types.Menu):
    bl_idname = "ALLSET_MT_character_select_members"
    bl_label = "Select Character Set Members"

    def item(self, lay, context, ks):
        op = lay.operator(ALLSET_OT_character_select.bl_idname, text=ks.bl_label)
        op.name, op.node = ks.bl_label, False


class ALLSET_MT_character_set_current(bpy.types.Menu):
    """Maya Key > Set Current Character Set: a radio row per character set, then None"""
    bl_idname = "ALLSET_MT_character_set_current"
    bl_label = "Set Current Character Set"

    def draw(self, context):
        lay = self.layout
        scene = context.scene
        cur = current(scene)
        for ks in characters(scene):
            on = ks == cur
            lay.operator(ALLSET_OT_character_set_current.bl_idname, text=ks.bl_label,
                         icon='RADIOBUT_ON' if on else 'RADIOBUT_OFF').name = ks.bl_label
        if characters(scene):
            lay.separator()
        lay.operator(ALLSET_OT_character_set_current.bl_idname, text="None",
                     icon='RADIOBUT_ON' if cur is None else 'RADIOBUT_OFF').name = ""


def _redraw(context):
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            area.tag_redraw()
    try:
        from ..ui import status_line
        status_line.redraw_top_bars()
    except Exception:
        pass


classes = (ALLSET_OT_character_create, ALLSET_OT_character_edit, ALLSET_OT_character_merge,
           ALLSET_OT_character_set_current, ALLSET_OT_character_select, ALLSET_OT_character_attributes,
           ALLSET_OT_character_remove_member, ALLSET_PT_character_set, ALLSET_MT_character_select_node,
           ALLSET_MT_character_select_members, ALLSET_MT_character_set_current, ALLSET_PT_character_editor,
           ALLSET_OT_character_editor)


def register_props():
    bpy.types.WindowManager.allset_character_nodes = StringProperty(options={'SKIP_SAVE'})


def unregister_props():
    del bpy.types.WindowManager.allset_character_nodes
