# SPDX-License-Identifier: GPL-3.0-or-later
"""Global key batch 4: Ctrl+X cut / Ctrl+V paste, Alt+\\ playback range = animation range,
Alt+1 / 2 / 4 show toggles, Ctrl+` / Shift+~ / Ctrl+Shift+~ smooth proxy. Alt+X walk is Blender's view3d.walk.

Maya 2022 behaviour:
- PasteSelected = Edit > Paste: import the clipboard file with every node renamed
  ``pasted__<name>``, grouped under a new ``group``.
- CutSelected = Edit > Cut: export the selection (with its hierarchy) to the clipboard file, then delete it.
- PlaybackRangeAnimStartEnd: playback min / max = animation start / end (Maya runtime command).
- Alt+1 / 2 / 4 flip NURBS Curves / Polygons / Image Planes in the focused panel's Show menu.
- Ctrl+` swaps the proxy (cage) and smooth mesh visibility (both shown -> cage only), Shift+~ shows both;
  Ctrl+Shift+~ = Mesh > Smooth Proxy > Subdiv Proxy.
"""

import re

import bpy

from .. import results
from .. import undo_steps
from . import display
from . import group
from . import naming


# --- Ctrl+X ---------------------------------------------------------------------------------------------

def cut_targets(selected):
    """The selection plus everything below it (Maya exports and deletes the selected DAG hierarchy)."""
    out, seen = [], set()
    for ob in selected:
        for o in (ob, *ob.children_recursive):
            if o.name not in seen:
                seen.add(o.name)
                out.append(o)
    return out


class ALLSET_OT_cut(bpy.types.Operator):
    """Cut the selected objects (Maya Ctrl+X): copy them to the clipboard, then delete them. Ctrl+V pastes them back"""
    bl_idname = "allset.cut"
    bl_label = "Cut"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects)

    def execute(self, context):
        targets = cut_targets(context.selected_objects)
        for ob in targets:
            try:
                ob.select_set(True)
            except RuntimeError:        # not in the view layer
                pass
        names = [ob.name for ob in targets]
        with context.temp_override(selected_objects=targets):
            bpy.ops.view3d.copybuffer()
        datas = {ob.data for ob in targets if ob.data is not None}
        for ob in targets:
            bpy.data.objects.remove(ob)
        # Maya deletes the shape with its transform: drop data left without users, or the paste gets "pCubeShape1.001".
        bpy.data.batch_remove([d for d in datas if d.users == 0])
        results.result(self, f"Cut {len(names)} object(s)")
        return {'FINISHED'}


PASTE_PREFIX = "pasted__"


def pasted_roots(before, objects):
    """The new objects' top nodes (no parent among the new ones), by name for a stable order."""
    new = [o for o in objects if o.name not in before]
    names = {o.name for o in new}
    return sorted((o for o in new if o.parent is None or o.parent.name not in names), key=lambda o: o.name)


def _unsuffixed(name):
    """``pCube1.001`` -> ``pCube1`` (Blender's clash suffix)."""
    return re.sub(r"\.\d{3,}$", "", name)


def pasted_name(orig, taken):
    """Maya Edit > Paste imports with every node renamed by the prefix "pasted_": every node becomes ``pasted__<name>``.
    Maya keeps a clashing short name under another group; Blender names are
    unique, so a taken one counts up like a new node (``pasted__pCube2``)."""
    name = PASTE_PREFIX + orig
    if name not in taken:
        return name
    base = naming.base_name(name)
    return f"{base}{naming.next_number(base, taken)}"


def paste_group_name(taken):
    """Maya's paste puts the pasted nodes under ``group``, then ``group1``, ``group2``."""
    if "group" not in taken:
        return "group"
    return f"group{naming.next_number('group', taken)}"


def rename_pasted(new_objects):
    """Blender's pastebuffer names clashing objects / data ``pCube1.001``: give them Maya's ``pasted__`` names, the
    shape numbered like its transform (``pasted__pCube2`` / ``pasted__pCubeShape2``)."""
    for ob in sorted(new_objects, key=lambda o: o.name):
        orig = _unsuffixed(ob.name)
        ob.name = pasted_name(orig, {o.name for o in bpy.data.objects if o is not ob})
        data = ob.data
        if data is None or data.users != 1 or data.library is not None:
            continue
        coll = naming._collection_for(data)
        if coll is None:
            continue
        dorig = _unsuffixed(data.name)
        dtaken = {d.name for d in coll if d is not data}
        obase, nbase = naming.base_name(orig), naming.base_name(ob.name)
        if orig != obase and dorig == f"{obase}Shape{orig[len(obase):]}":
            want = f"{nbase}Shape{ob.name[len(nbase):]}"      # the shape follows its transform's number
            if want not in dtaken:
                data.name = want
                continue
        data.name = pasted_name(dorig, dtaken)


class ALLSET_OT_paste(bpy.types.Operator):
    """Paste the clipboard objects (Maya Ctrl+V): pasted__ names, under a new group that stays selected"""
    bl_idname = "allset.paste"
    bl_label = "Paste"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        # Maya pasteScene:
        # every node renamed pasted__<name>, the top nodes under a new group at the origin, only the group selected.
        before = set(bpy.data.objects.keys())
        if bpy.ops.view3d.pastebuffer() != {'FINISHED'}:
            return {'CANCELLED'}
        roots = pasted_roots(before, context.scene.objects)
        if not roots:
            return {'FINISHED'}
        rename_pasted([o for o in context.scene.objects if o.name not in before])
        grp = group.make_group(context, roots)
        grp.name = paste_group_name({o.name for o in bpy.data.objects if o is not grp})
        for o in context.scene.objects:
            if o.select_get():
                o.select_set(False)
        grp.select_set(True)
        context.view_layer.objects.active = grp
        return {'FINISHED'}


# --- Alt+\ ----------------------------------------------------------------------------------------------

def playback_to_animation_range(scene):
    """Kit rule: playback range = preview range, animation range = frame_start / end. Turning the preview
    range off makes playback = animation; its values stay, so the Range Slider double-click can bring them back."""
    scene.use_preview_range = False


class ALLSET_OT_playback_range_anim(bpy.types.Operator):
    """Set the playback range to the animation range (Maya Alt+\\)"""
    bl_idname = "allset.playback_range_anim"
    bl_label = "Playback Range = Animation Range"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        playback_to_animation_range(context.scene)
        for win in context.window_manager.windows:
            for area in win.screen.areas:
                if area.type in {'DOPESHEET_EDITOR', 'GRAPH_EDITOR', 'NLA_EDITOR', 'SEQUENCE_EDITOR'}:
                    area.tag_redraw()
        return {'FINISHED'}


# --- Alt+1 / 2 / 4 --------------------------------------------------------------------------------------

SHOW_KINDS = (
    ('CURVES', "NURBS Curves", "Maya Alt+1: curves in this view"),
    ('POLYGONS', "Polygons", "Maya Alt+2: meshes in this view"),
    ('IMAGE_PLANES', "Image Planes", "Maya Alt+4: image planes (image empties, every view)"),
)
SPACE_FILTER = {'CURVES': "show_object_viewport_curve", 'POLYGONS': "show_object_viewport_mesh"}
IMAGE_FLAGS = ("show_empty_image_perspective", "show_empty_image_orthographic")


def image_planes(scene):
    return [o for o in scene.objects if o.type == 'EMPTY' and o.empty_display_type == 'IMAGE']


def toggle_show(space, scene, kind):
    """Flip one Maya Show type. Returns the new state (True = shown). Blender has no view filter for image empties
    only (``empty`` also hides groups and locators), so image planes flip their own display flags in every view."""
    if kind in SPACE_FILTER:
        attr = SPACE_FILTER[kind]
        new = not getattr(space, attr)
        setattr(space, attr, new)
        if kind == 'CURVES':        # curve-shaped bone controls follow (ui/curve_controls.py)
            from ..ui import curve_controls
            curve_controls.sync(space, scene)
        return new
    planes = image_planes(scene)
    new = not any(getattr(o, f) for o in planes for f in IMAGE_FLAGS)
    for o in planes:
        for f in IMAGE_FLAGS:
            setattr(o, f, new)
    return new


class ALLSET_OT_toggle_show(bpy.types.Operator):
    """Show or hide one object type in the view under the mouse (Maya Alt+1 / Alt+2 / Alt+4)"""
    bl_idname = "allset.toggle_show"
    bl_label = "Toggle Show"
    bl_options = {'REGISTER'}

    kind: bpy.props.EnumProperty(items=SHOW_KINDS, name="Type", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.space_data is not None and context.space_data.type == 'VIEW_3D'

    def execute(self, context):
        toggle_show(context.space_data, context.scene, self.kind)
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        return {'FINISHED'}


# --- Ctrl+` / Shift+~ / Ctrl+Shift+~ ----------------------------------------------------------------------
# The kit's Subdiv Proxy is a user Subsurf (ui/menu_map.py "Mesh/Smooth Proxy/Subdiv Proxy"): the cage is the mesh,
# the smooth mesh is the modifier. "Both" draws the cage wire over the smooth surface like smooth preview 2.

PROXY_ACTIONS = (
    ('TOGGLE', "Toggle Proxy Display", "Maya Ctrl+`: cage <-> smooth"),
    ('BOTH', "Both Proxy and Subdiv Display", "Maya Shift+~: cage wire and smooth surface"),
    ('CREATE', "Subdiv Proxy", "Maya Ctrl+Shift+~: add the subdivision"),
)
_BOTH_FLAG = "allset_proxy_wire"   # object custom prop: show_wire turned on by "both"


def proxy_modifier(ob):
    """The object's proxy Subsurf: its last Subsurf that is not the kit's smooth preview."""
    mods = [m for m in ob.modifiers if m.type == 'SUBSURF' and not display.is_preview(m)]
    return mods[-1] if mods else None


def _set_both_wire(ob, on):
    if on:
        if not ob.show_wire:
            ob.show_wire = True
            ob[_BOTH_FLAG] = True
    elif ob.get(_BOTH_FLAG):
        ob.show_wire = False
        del ob[_BOTH_FLAG]


def proxy_action(ob, action):
    """Apply one smooth-proxy key to a mesh object. Returns False when it has no proxy (nothing done)."""
    mod = proxy_modifier(ob)
    if action == 'CREATE':
        if mod is None:
            mod = ob.modifiers.new("Subdivision", 'SUBSURF')
            first_preview = next((i for i, m in enumerate(ob.modifiers) if display.is_preview(m)), None)
            if first_preview is not None:   # the kit's smooth preview stays last in the stack
                with bpy.context.temp_override(object=ob):
                    bpy.ops.object.modifier_move_to_index(modifier=mod.name, index=first_preview)
        mod.show_viewport = True
        return True
    if mod is None:
        return False
    if action == 'BOTH':
        mod.show_viewport = True
        _set_both_wire(ob, True)
    elif ob.get(_BOTH_FLAG):            # both shown -> the cage only
        _set_both_wire(ob, False)
        mod.show_viewport = False
    else:
        mod.show_viewport = not mod.show_viewport
    return True


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_smooth_proxy(bpy.types.Operator):
    """Maya smooth proxy keys: Ctrl+` toggle cage / smooth, Shift+~ show both, Ctrl+Shift+~ create"""
    bl_idname = "allset.smooth_proxy"
    bl_label = "Smooth Proxy"
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.EnumProperty(items=PROXY_ACTIONS, name="Action", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return any(ob.type == 'MESH' for ob in cls._targets(context))

    @staticmethod
    def _targets(context):
        if context.mode == 'EDIT_MESH':
            return list(context.objects_in_mode)
        return list(context.selected_objects)

    def execute(self, context):
        done = [proxy_action(ob, self.action) for ob in self._targets(context) if ob.type == 'MESH']
        if not any(done):
            self.report({'WARNING'}, "No subdiv proxy on the selection (Mesh > Smooth Proxy > Subdiv Proxy, Ctrl+Shift+~)")
            return {'CANCELLED'}
        return {'FINISHED'}


classes = (ALLSET_OT_cut, ALLSET_OT_paste, ALLSET_OT_playback_range_anim, ALLSET_OT_toggle_show, ALLSET_OT_smooth_proxy)
