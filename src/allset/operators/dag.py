# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya DAG rules for a parent: what happens to a node's descendants.

Maya: a node is drawn only while it **and every ancestor** are visible —
hiding group1 (h, Ctrl+H, its Visibility channel, its display layer's V) hides pCube1 without touching pCube1's own
Visibility, and showing group1 again leaves a child that was hidden on its own hidden. Delete, Export Selection and
Isolate Select take the selected nodes with everything below them.

Blender: a parent's ``hide_viewport`` / ``hide_set`` never hides its children and
``object.delete`` leaves the children, unparented. So:

- ``sync``: an object whose ancestor is hidden (own Visibility = ``hide_viewport``, or its display layer's V) gets the
  view-layer flag (``hide_set``) marked ``MARK``; its own ``hide_viewport`` (Maya's Visibility channel) stays as it
  was. Objects the kit did not hide that way are never touched (a layer's or Blender's own ``hide_set`` stays).
  Run from a depsgraph handler (only writes on change, so it settles) and right after kit visibility edits.
- ``hierarchy``: the selection with all descendants, for Delete (``allset.delete``), Export Selection
  (``selected_hierarchy``) and Isolate Select (``allset.isolate``).
"""

import bpy
from bpy.app.handlers import persistent

from .. import depsgraph_filter

MARK = "allset_hidden_by_parent"
# a type filter of the panel Show menu hides only that node, never its children (ui/panel_menus.SHOW_HIDDEN)
SHOW_FILTER = "allset_hidden_by_show"


def hierarchy(objects):
    """``objects`` plus everything below them, each once, parents first."""
    out, seen = [], set()
    for ob in objects:
        for o in (ob, *ob.children_recursive):
            if o.session_uid not in seen:
                seen.add(o.session_uid)
                out.append(o)
    return out


def _layer_hidden(ob, scene):
    from ..ui import layer_editor
    coll = layer_editor.layer_of(ob, scene)
    return coll is not None and not coll.allset_layer.visible


def hidden_self(ob, scene, view_layer=None):
    """Maya: the node's own visibility off, or its display layer hidden (the node's drawOverride). Blender's own hide
    (the Outliner's Ctrl+H, ``hide_set``) counts too, unless this rule set it (``MARK``) or a Show menu type
    filter did (``SHOW_FILTER``)."""
    if ob.hide_viewport or _layer_hidden(ob, scene):
        return True
    if view_layer is None or MARK in ob or SHOW_FILTER in ob:
        return False
    try:
        return ob.hide_get(view_layer=view_layer)
    except RuntimeError:          # not in this view layer
        return False


def hidden_by_ancestor(ob, scene, view_layer=None):
    p = ob.parent
    while p is not None:
        if hidden_self(p, scene, view_layer):
            return True
        p = p.parent
    return False


def sync(scene=None, view_layer=None):
    """Hide / show descendants of hidden nodes (view-layer flag + ``MARK``). Returns the number of changes."""
    scene = scene or bpy.context.scene
    if scene is None:
        return 0
    view_layer = view_layer or bpy.context.view_layer
    if view_layer is None:
        return 0
    changed = 0
    for ob in scene.objects:
        by_parent = hidden_by_ancestor(ob, scene, view_layer)
        if not by_parent and MARK not in ob:
            continue
        want = by_parent or _layer_hidden(ob, scene)
        try:
            if ob.hide_get(view_layer=view_layer) != want:
                ob.hide_set(want, view_layer=view_layer)
                changed += 1
        except RuntimeError:          # not in this view layer
            continue
        if by_parent:
            if MARK not in ob:
                ob[MARK] = True
        elif MARK in ob:
            del ob[MARK]
    return changed


_busy = []


@persistent
def _on_depsgraph(scene, _depsgraph=None):
    # #191: visibility only changes with a hide, a parent change or a new / removed node — never with a
    # move or a mesh edit; sync walks every object's ancestors
    if _busy or depsgraph_filter.only_motion(_depsgraph):
        return
    _busy.append(True)
    try:
        sync(scene)
    except Exception:          # never break the depsgraph update
        pass
    finally:
        _busy.clear()


@persistent
def _on_load(*_args):
    for scene in bpy.data.scenes:
        for vl in scene.view_layers:
            try:
                sync(scene, vl)
            except Exception:
                pass


# --- Delete / Export Selection / Isolate with the hierarchy -----------------------------------------------------

def delete_hierarchy(context, objects):
    """Maya delete of transforms: the nodes and every descendant, with their now unused data. Returns the count."""
    from . import constrain_199, startup_cameras
    # Maya refuses to delete its startup cameras ("Non-deletable node 'persp' cannot be deleted.")
    obs = [ob for ob in hierarchy(objects) if not startup_cameras.is_startup(ob)]
    # Maya's normal / tangent constraint node is a child of the constrained object: its kit helper empty goes too
    # (#109; the helper has no parent — constrain_199.update clears it — so hierarchy() misses it)
    helpers = [h for h in constrain_199.helpers_owned_by(obs) if h not in obs]
    from . import ik_rp
    poles = ik_rp.helpers_of(obs)          # a kit RP handle's pole helper goes with the handle
    from . import spline_twist
    spline_twist.release(obs)              # a kit Spline IK handle takes its twist drivers and constraint
    from . import sweep_mesh
    sweep_mesh.release(context, obs)       # a deleted curve leaves its sweeps as plain meshes, like Maya
    datas = {ob.data for ob in obs if ob.data is not None}
    n = len(obs)
    for ob in reversed(obs):              # children first
        bpy.data.objects.remove(ob, do_unlink=True)
    constrain_199.remove_helpers(helpers)
    ik_rp.drop_orphan_rotations()          # its 3+ bone chain's Copy Rotations and bone helpers too
    for h in poles:
        try:
            bpy.data.objects.remove(h, do_unlink=True)
        except ReferenceError:
            pass
    for data in datas:
        try:
            if data.users == 0:
                getattr(bpy.data, _DATA_COLLECTION.get(type(data).__name__, ""), None).remove(data)
        except (AttributeError, ReferenceError, RuntimeError):
            pass
    return n


_DATA_COLLECTION = {"Mesh": "meshes", "Curve": "curves", "SurfaceCurve": "curves", "TextCurve": "curves",
                    "Lattice": "lattices", "Armature": "armatures", "Camera": "cameras", "Light": "lights",
                    "SpotLight": "lights", "PointLight": "lights", "SunLight": "lights", "AreaLight": "lights",
                    "MetaBall": "metaballs", "GreasePencil": "grease_pencils"}


class selected_hierarchy:
    """``with selected_hierarchy(context):`` the descendants of the selection are selected too (Maya Export
    Selection), and the selection is put back afterwards."""

    def __init__(self, context):
        self.context = context
        self.added = []

    def __enter__(self):
        sel = list(self.context.selected_objects)
        for ob in hierarchy(sel):
            if not ob.select_get():
                try:
                    ob.select_set(True)
                    self.added.append(ob)
                except RuntimeError:      # hidden / not in the view layer
                    pass
        return self

    def __exit__(self, *_exc):
        for ob in self.added:
            try:
                ob.select_set(False)
            except (RuntimeError, ReferenceError):
                pass
        return False


class ALLSET_OT_delete(bpy.types.Operator):
    """Delete the selected objects and everything below them (Maya Edit > Delete)"""
    bl_idname = "allset.delete"
    bl_label = "Delete"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects)

    def execute(self, context):
        from . import startup_cameras
        for ob in context.selected_objects:
            if startup_cameras.is_startup(ob):
                self.report({'WARNING'}, f"Non-deletable node '{ob.name}' cannot be deleted.")
        delete_hierarchy(context, list(context.selected_objects))
        return {'FINISHED'}


class ALLSET_OT_isolate(bpy.types.Operator):
    """Isolate Select: show only the selected objects and everything below them (Maya Ctrl+1); again = back"""
    bl_idname = "allset.isolate"
    bl_label = "Isolate Select"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.space_data is not None and context.space_data.type == 'VIEW_3D'

    def execute(self, context):
        space = context.space_data
        if space.local_view is not None:
            return bpy.ops.view3d.localview(frame_selected=False)
        with selected_hierarchy(context):
            return bpy.ops.view3d.localview(frame_selected=False)


classes = (ALLSET_OT_delete, ALLSET_OT_isolate)


def register_handlers():
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)


def release_all():
    """Disable: show again what only the kit's parent rule hid (the objects' own flags stay)."""
    for scene in bpy.data.scenes:
        for ob in scene.objects:
            if MARK not in ob:
                continue
            for vl in scene.view_layers:
                try:
                    if not _layer_hidden(ob, scene):
                        ob.hide_set(False, view_layer=vl)
                except RuntimeError:
                    pass
            del ob[MARK]


def unregister_handlers():
    for lst, fn in ((bpy.app.handlers.depsgraph_update_post, _on_depsgraph), (bpy.app.handlers.load_post, _on_load)):
        if fn in lst:
            lst.remove(fn)
    try:
        release_all()
    except Exception:          # restricted context while Blender quits
        pass
