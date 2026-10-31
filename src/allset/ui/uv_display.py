# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya UV Editor display keys and Move UV Shell.

Maya 2022 UV Editor hotkeys (context polyTexturePlacementPanel) and View menu:

- 4 Wireframe / 5 Shaded (Display Mode radio) -> ``SpaceUVEditor.show_faces`` off / on (Shaded also sets
  ``uv_face_opacity`` 1). ``uv_face_opacity`` 0 alone still draws grey face fills (GUI shot): no wireframe.
- 6 UVEditor_ToggleUVTextureImage -> ``SpaceImageEditor.image`` = None / back (Blender has no "hide the image"
  flag; the image is remembered per editor, else the active material's image texture is shown).
- 8 UVEditor_ToggleUVShellBorder = Maya's shell border display toggle: shell
  borders drawn in colour, 3 px wide.
- 9 UVEditor_ToggleTextureBorder = ``ToggleTextureBorderDisplay``: Maya's "texture
  borders" are the UV shell border edges drawn thick (Select > Texture Borders selects the same edges;
  cut_sew.py calls them that too), on by default in the Maya View menu (checked). Drawn 3 px in the
  theme's UV wire colour, i.e. the same edge, thicker.
- Ctrl+1 UVEditor_ToggleUVIsolateViewSelected -> ``allset.uv_isolate``.
- Shaded (5, View > Shaded) also colours each shown face by its UV winding, like Maya's shaded UV display:
  counter-clockwise (front-facing) faces blue, clockwise (flipped) faces red; Wireframe (4) turns it off
  (``WindowManager.allset_uv_face_colors``).

Shell borders follow the step-66 island rule (operators/uv_tools.islands: faces join where their UVs match at both
ends of an edge): an edge is a border on a face's side when no other shown face shares the same UVs across it.
They are drawn by an Image Editor WINDOW POST_PIXEL handler in UV space mapped through ``View2D.view_to_region``;
segments are cached per object and dropped on any depsgraph update of a mesh / object (like cut_sew.py).
"""

import bmesh
import bpy
import gpu
import numpy as np
from bpy.props import BoolProperty, EnumProperty
from gpu_extras.batch import batch_for_shader

from .. import results
from .. import compat
from ..operators import uv_arrays, uv_tools

BORDER_PX = 3.0                        # shell / texture border width
SHELL_RGB = (0.25, 0.75, 1.0)          # Toggle Shell Borders colour (the kit's choice)
FRONT_RGBA = (0.15, 0.35, 1.0, 0.55)   # Shaded: front-facing UV faces (the kit's choice)
FLIPPED_RGBA = (1.0, 0.15, 0.15, 0.55)  # Shaded: flipped UV faces
MOVE_TOOL = "builtin.move"

MODES = (("WIREFRAME", "Wireframe", "Maya 4: UVs as wireframe (no shaded faces)"),
         ("SHADED", "Shaded", "Maya 5: UV faces shaded"),
         ("IMAGE", "Texture Image", "Maya 6: show / hide the texture image"),
         ("SHELL_BORDERS", "Shell Borders", "Maya 8: UV shell borders in colour"),
         ("TEXTURE_BORDERS", "Texture Borders", "Maya 9: UV shell borders drawn thick"))


# --- pure helpers (tests/test_step155_uv_display.py) -----------------------------------------------------

def shown_faces(bm, synced):
    """Faces the UV Editor draws: every unhidden face with UV Sync Selection, else only the selected ones."""
    return [f for f in bm.faces if not f.hide and (synced or f.select)]


def border_segments(bm, uv, faces):
    """UV segments ((u0, v0), (u1, v1)) of every shell border edge side among ``faces``."""
    shown = set(faces)
    out = []
    for f in faces:
        for loop in f.loops:
            e = loop.edge
            joined = False
            for g in e.link_faces:
                if g is f or g not in shown:
                    continue
                if all(uv_tools._same(uv_tools._uv_at(f, v, uv), uv_tools._uv_at(g, v, uv)) for v in e.verts):
                    joined = True
                    break
            if not joined:
                a, b = loop[uv].uv, loop.link_loop_next[uv].uv
                out.append(((a.x, a.y), (b.x, b.y)))
    return out


def face_winding(bm, uv, faces):
    """(front triangles, flipped triangles): UV triangles ((u, v) x 3 each) of ``faces``, split by the sign of each
    face's UV area (counter-clockwise = front-facing). A face with no area counts as front-facing."""
    front, flipped = [], []
    for f in faces:
        pts = [l[uv].uv for l in f.loops]
        area = sum(a.x * b.y - b.x * a.y for a, b in zip(pts, pts[1:] + pts[:1]))
        tris = [(pts[0][:], pts[i][:], pts[i + 1][:]) for i in range(1, len(pts) - 1)]
        (flipped if area < 0.0 else front).extend(tris)
    return front, flipped


def to_region(points, p0, p1):
    """UV points (N x 2) to region pixels, given where UV (0, 0) and (1, 1) land."""
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 2)
    scale = np.array((p1[0] - p0[0], p1[1] - p0[1]), dtype=np.float32)
    return pts * scale + np.array(p0, dtype=np.float32)


# --- drawing ---------------------------------------------------------------------------------------------

_cache = {}          # object pointer -> float32 array (2N x 2) of UV line points
_handle = []


def _edit_meshes(context):
    obs = getattr(context, "objects_in_mode_unique_data", None) or ()
    return [o for o in obs if o.type == 'MESH']


def segments_of(ob, synced):
    key = (ob.as_pointer(), synced)
    pts = _cache.get(key)
    if pts is None:
        bm = bmesh.from_edit_mesh(ob.data)
        uv = bm.loops.layers.uv.active
        if uv is None:
            pts = np.zeros((0, 2), np.float32)
        else:     # numpy (operators/uv_arrays.py): the Python border_segments took ~1.8 s on 48 k faces
            arrays = uv_arrays.read(ob, bm, uv, bpy.context.view_layer.depsgraph, cached=True)
            pts = uv_arrays.border_points(arrays, uv_arrays.shown_faces(arrays, synced))
        _cache[key] = pts
    return pts




def faces_of(ob, synced):
    key = ("faces", ob.as_pointer(), synced)     # in _cache: dropped with the border segments
    tris = _cache.get(key)
    if tris is None:
        bm = bmesh.from_edit_mesh(ob.data)
        uv = bm.loops.layers.uv.active
        if uv is None:
            tris = (np.zeros((0, 2), np.float32),) * 2
        else:
            front, flipped = face_winding(bm, uv, shown_faces(bm, synced))
            tris = tuple(np.asarray(t, np.float32).reshape(-1, 2) for t in (front, flipped))
        _cache[key] = tris
    return tris


def _draw_faces(context, p0, p1):
    synced = context.scene.tool_settings.use_uv_select_sync
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    for i, rgba in enumerate((FRONT_RGBA, FLIPPED_RGBA)):
        pts = [faces_of(ob, synced)[i] for ob in _edit_meshes(context)]
        pts = [t for t in pts if len(t)]
        if not pts:
            continue
        shader.uniform_float("color", rgba)
        batch_for_shader(shader, 'TRIS', {"pos": to_region(np.concatenate(pts), p0, p1).tolist()}).draw(shader)
    gpu.state.blend_set('NONE')


def _draw():
    context = bpy.context
    wm = context.window_manager
    if not (wm.allset_uv_shell_borders or wm.allset_uv_texture_borders or wm.allset_uv_face_colors):
        return
    space = context.space_data
    region = context.region
    try:
        if space is None or space.mode != 'UV' or context.mode != 'EDIT_MESH' or not space.uv_editor.show_uv:
            return
        v2d = region.view2d
        p0 = v2d.view_to_region(0.0, 0.0, clip=False)
        p1 = v2d.view_to_region(1.0, 1.0, clip=False)
        if p0[0] == p1[0] or p0[1] == p1[1]:
            return
        if uv_arrays.editing_now(wm):
            return      # a UV drag runs: the borders come back when it ends (crash fix, operators/uv_arrays.py)
        if wm.allset_uv_face_colors and space.uv_editor.show_faces:
            _draw_faces(context, p0, p1)
        if not (wm.allset_uv_shell_borders or wm.allset_uv_texture_borders):
            return
        synced = context.scene.tool_settings.use_uv_select_sync
        pts = [segments_of(ob, synced) for ob in _edit_meshes(context)]
        pts = [p for p in pts if len(p)]
        if not pts:
            return
        px = to_region(np.concatenate(pts), p0, p1)
        scale = context.preferences.system.ui_scale or 1.0
        shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        if wm.allset_uv_shell_borders:
            rgb = SHELL_RGB
        else:
            rgb = tuple(context.preferences.themes[0].image_editor.wire_edit)[:3]
        gpu.state.blend_set('ALPHA')
        shader.uniform_float("viewportSize", (region.width, region.height))
        shader.uniform_float("lineWidth", BORDER_PX * scale)
        shader.uniform_float("color", (*rgb, 1.0))
        batch_for_shader(shader, 'LINES', {"pos": px.tolist()}).draw(shader)
        gpu.state.blend_set('NONE')
    except (ReferenceError, AttributeError, ValueError):
        _cache.clear()


@bpy.app.handlers.persistent
def _invalidate(_scene=None, depsgraph=None):
    if depsgraph is not None and not any(isinstance(u.id, (bpy.types.Mesh, bpy.types.Object))
                                         for u in depsgraph.updates):
        return
    _cache.clear()
    uv_arrays.invalidate()


def redraw_uv_editors():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'IMAGE_EDITOR':
                area.tag_redraw()


def _redraw(_self, _context):
    redraw_uv_editors()


def _shaded_changed(self, _context):
    """View > Shaded / Wireframe: every UV Editor shows its faces (opaque) or none."""
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            for space in area.spaces:
                if space.type == 'IMAGE_EDITOR' and space.uv_editor.show_faces != self.allset_uv_face_colors:
                    space.uv_editor.show_faces = self.allset_uv_face_colors
                    if self.allset_uv_face_colors:
                        space.uv_editor.uv_face_opacity = 1.0
    redraw_uv_editors()


# --- texture image (6) -----------------------------------------------------------------------------------

_hidden_image = {}   # SpaceImageEditor pointer -> image name it showed before 6 hid it


def material_image(ob):
    """The image of the active material's active (else first) Image Texture node, or None."""
    mat = ob.active_material if ob is not None else None
    tree = mat.node_tree if mat is not None and mat.use_nodes else None
    if tree is None:
        return None
    node = tree.nodes.active
    if node is not None and node.type == 'TEX_IMAGE' and node.image is not None:
        return node.image
    return next((n.image for n in tree.nodes if n.type == 'TEX_IMAGE' and n.image is not None), None)


def toggle_image(space, ob):
    """Maya 6: hide the shown image (remembered), or show the remembered / material image. Returns the shown one."""
    key = space.as_pointer()
    if space.image is not None:
        _hidden_image[key] = space.image.name
        space.image = None
        return None
    img = bpy.data.images.get(_hidden_image.pop(key, "") or "") or material_image(ob)
    if img is not None:
        space.image = img
    return img


# --- operators -------------------------------------------------------------------------------------------

def _in_uv_editor(context):
    space = context.space_data
    return space is not None and space.type == 'IMAGE_EDITOR' and space.mode == 'UV'


class ALLSET_OT_uv_display(bpy.types.Operator):
    """Maya UV Editor display keys: 4 Wireframe, 5 Shaded, 6 texture image, 8 shell borders, 9 texture borders"""
    bl_idname = "allset.uv_display"
    bl_label = "UV Editor Display"
    bl_options = set()          # display only: no undo step, no redo panel

    mode: EnumProperty(items=MODES, name="Mode", default='SHELL_BORDERS', options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return _in_uv_editor(context)

    def execute(self, context):
        space = context.space_data
        wm = context.window_manager
        if self.mode == 'WIREFRAME':
            wm.allset_uv_face_colors = False
            space.uv_editor.show_faces = False
        elif self.mode == 'SHADED':
            wm.allset_uv_face_colors = True
            space.uv_editor.show_faces = True
            space.uv_editor.uv_face_opacity = 1.0
        elif self.mode == 'IMAGE':
            had = space.image is not None
            if toggle_image(space, context.view_layer.objects.active) is None and not had:
                results.result(self, "No texture image to show")
        elif self.mode == 'SHELL_BORDERS':
            wm.allset_uv_shell_borders = not wm.allset_uv_shell_borders
        else:
            wm.allset_uv_texture_borders = not wm.allset_uv_texture_borders
        redraw_uv_editors()
        return {'FINISHED'}


# --- isolate (Ctrl+1, View > Isolate Select, Select > Filter Selection) -------------------------------------
#
# Maya keeps one face set (Maya UV Editor isolate select): Add
# Selected (mode 1) adds the faces the selection touches (polyListComponentConversion -tf: vertices -> their faces,
# edges -> the faces beside them, UVs -> the faces using them), Remove Selected (2) takes them out, Remove All (0)
# empties it for the hilited meshes; the UV Editor shows only the set's faces while the isolate view is on
# (Maya's shader faces mode). Ctrl+1 = Remove All + Add Selected + view on
# (Maya 2026). Kit: the set is
# ``_iso_sets`` (face indices per object); while the view is on, faces outside it are hidden (UV Sync Selection on:
# Blender's hide, the 3D View too) or deselected (sync off: the UV Editor draws only selected faces). Filter Selection
# > Connected / Contained Faces uses the same state with the faces of the selection at the time
# it is turned on (Maya's filter follows later selection changes).

_isolated = {}       # object name -> {synced, gone (face indices the kit hid / deselected), before, count}
_iso_sets = {}       # object name -> (face count, set of face indices): Maya's UV Editor isolate set


def _picked_faces(bm, uv, synced):
    if synced:
        return [f for f in bm.faces if f.select and not f.hide]
    shown = [f for f in bm.faces if f.select and not f.hide]
    full = [f for f in shown if all(compat.uv_vert_selected(l, uv) for l in f.loops)]
    return full or [f for f in shown if any(compat.uv_vert_selected(l, uv) for l in f.loops)]


def _selection(bm):
    return tuple([i for i, el in enumerate(seq) if el.select] for seq in (bm.verts, bm.edges, bm.faces))


def _show_only(bm, rec, keep):
    """Show exactly the faces ``keep`` (indices) of those the kit may touch; the current selection stays."""
    synced = rec["synced"]
    cur = _selection(bm)
    bm.faces.ensure_lookup_table()
    gone = set(rec["gone"])
    back = [i for i in gone if i in keep]
    newly = [f.index for f in bm.faces if not f.hide and f.index not in keep and (synced or f.select)]
    if synced:
        for i in back:
            bm.faces[i].hide_set(False)
        for i in newly:
            bm.faces[i].hide_set(True)
    gone = (gone - set(back)) | set(newly)
    _restore_selection(bm, cur)
    if not synced:
        for i in gone:
            bm.faces[i].select = False
        for i in back:
            bm.faces[i].select = True
    rec["gone"] = sorted(gone)


def isolate(ob, synced, keep=None):
    """Show only ``keep`` (face indices; default: the faces of the selected UVs): with UV Sync Selection the others
    are hidden (Blender's hide, so the 3D View hides them too), without it they are deselected (the UV Editor then
    doesn't draw them). Returns how many faces stay shown (0 = nothing to show, nothing changed)."""
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.active
    if uv is None:
        return 0
    if keep is None:
        keep = {f.index for f in _picked_faces(bm, uv, synced)}
        if keep:
            _iso_sets[ob.name] = (len(bm.faces), set(keep))      # Ctrl+1 = Remove All + Add Selected
    if not keep:
        return 0
    rec = {"synced": synced, "gone": [], "before": _selection(bm), "count": len(bm.faces)}
    _show_only(bm, rec, set(keep))
    _isolated[ob.name] = rec
    bmesh.update_edit_mesh(ob.data)
    return len(keep)


def _restore_selection(bm, before):
    for seq, idx in zip((bm.verts, bm.edges, bm.faces), before):
        on = set(idx)
        for i, el in enumerate(seq):
            el.select = i in on and not el.hide


def unisolate(ob):
    rec = _isolated.pop(ob.name, None)
    if rec is None:
        return False
    bm = bmesh.from_edit_mesh(ob.data)
    if len(bm.faces) != rec["count"]:
        return False
    bm.faces.ensure_lookup_table()
    if rec["synced"]:
        for i in rec["gone"]:
            bm.faces[i].hide_set(False)
    _restore_selection(bm, rec["before"])
    bmesh.update_edit_mesh(ob.data)
    return True


def iso_set(ob):
    """Maya's isolate set of ``ob``: sorted face indices (empty when there is none / the mesh changed)."""
    got = _iso_sets.get(ob.name)
    if got is None or len(ob.data.polygons) != got[0]:
        return []
    return sorted(got[1])


def edit_set(ob, action, faces):
    """View > Isolate Select > Add Selected / Remove Selected / Remove All on ``ob``: ``faces`` = face indices the
    selection touches. Updates the set and, while the view is on, what the UV Editor shows. Returns the set size."""
    bm = bmesh.from_edit_mesh(ob.data)
    got = _iso_sets.get(ob.name)
    cur = set(got[1]) if got is not None and got[0] == len(bm.faces) else set()
    if action == 'ADD':
        cur |= set(faces)
    elif action == 'REMOVE':
        cur -= set(faces)
    else:
        cur = set()
    _iso_sets[ob.name] = (len(bm.faces), cur)
    rec = _isolated.get(ob.name)
    if rec is not None and rec["count"] == len(bm.faces):
        _show_only(bm, rec, cur)
        bmesh.update_edit_mesh(ob.data)
    return len(cur)


def touched_faces(bm, uv, ts):
    from ..operators import uv_select_178
    return {f.index for f in uv_select_178.connected_faces(bm, uv, ts)}


def set_filter(context, kind, rule):
    """Select > Filter Selection > Connected / Contained Faces (check items): on = only the faces ``rule(bm, uv)``
    gives are shown, the same kind again = off. Returns False when turning on found no faces."""
    wm = context.window_manager
    obs = _edit_meshes(context)
    was = wm.allset_uv_filter
    for ob in obs:
        unisolate(ob)
    wm.allset_uv_isolate = False
    wm.allset_uv_filter = 'NONE'
    if was == kind:
        _cache.clear()
        redraw_uv_editors()
        return True
    synced = context.scene.tool_settings.use_uv_select_sync
    shown = 0
    for ob in obs:
        bm = bmesh.from_edit_mesh(ob.data)
        uv = bm.loops.layers.uv.active
        if uv is None:
            continue
        keep = {f.index for f in rule(bm, uv)}
        if keep:
            shown += isolate(ob, synced, keep)
    wm.allset_uv_filter = kind if shown else 'NONE'
    _cache.clear()
    redraw_uv_editors()
    return bool(shown)


class ALLSET_OT_uv_isolate(bpy.types.Operator):
    """Maya Ctrl+1 in the UV Editor: show only the selected UVs' faces; again = show all"""
    bl_idname = "allset.uv_isolate"
    bl_label = "Isolate Select (UV)"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        obs = _edit_meshes(context)
        wm = context.window_manager
        if any(ob.name in _isolated for ob in obs):
            for ob in obs:
                unisolate(ob)
            wm.allset_uv_isolate = False
            wm.allset_uv_filter = 'NONE'
        else:
            synced = context.scene.tool_settings.use_uv_select_sync
            if not sum(isolate(ob, synced) for ob in obs):
                self.report({'WARNING'}, "Select UVs to isolate")
                return {'CANCELLED'}
            wm.allset_uv_isolate = True
        _cache.clear()
        redraw_uv_editors()
        return {'FINISHED'}


ISO_ACTIONS = (('ADD', "Add Selected", "Add the faces of the selected UVs to the isolate select set"),
               ('REMOVE', "Remove Selected", "Remove the faces of the selected UVs from the isolate select set"),
               ('CLEAR', "Remove All", "Remove all faces of the selected meshes from the isolate select set"))


class ALLSET_OT_uv_isolate_edit(bpy.types.Operator):
    """Maya UV Editor View > Isolate Select > Add Selected / Remove Selected / Remove All"""
    bl_idname = "allset.uv_isolate_edit"
    bl_label = "Isolate Select Set (UV)"
    bl_options = {'UNDO'}

    action: EnumProperty(items=ISO_ACTIONS, name="Action", default='ADD', options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    @classmethod
    def description(cls, context, props):
        return next(d for k, _l, d in ISO_ACTIONS if k == props.action)

    def execute(self, context):
        ts = context.scene.tool_settings
        total = 0
        obs = _edit_meshes(context)
        for ob in obs:
            bm = bmesh.from_edit_mesh(ob.data)
            uv = bm.loops.layers.uv.active
            faces = touched_faces(bm, uv, ts) if self.action != 'CLEAR' else set()
            total += edit_set(ob, self.action, faces)
        on = any(ob.name in _isolated for ob in obs)
        results.result(self, "Isolate select set: %d face%s%s" % (
            total, "" if total == 1 else "s", "" if on else " (shown with View > Isolate Select > View Selected)"))
        _cache.clear()
        redraw_uv_editors()
        return {'FINISHED'}


# --- Move UV Shell (Tools menu) ------------------------------------------------------------------------

_shell_tool = {"on": False}


def _uv_tool_ids():
    out = []
    for win in bpy.context.window_manager.windows:
        tool = win.workspace.tools.from_space_image_mode('UV', create=False)
        out.append(tool.idname if tool is not None else "")
    return out


def _watch_shell_tool():
    """While Move UV Shell is on: another UV tool chosen -> back to UV (not shell) selection."""
    if not _shell_tool["on"]:
        return None
    try:
        ids = _uv_tool_ids()
    except (ReferenceError, AttributeError):
        return 0.25
    if ids and MOVE_TOOL not in ids:
        _shell_tool["on"] = False
        ts = bpy.context.scene.tool_settings
        if compat.uv_island_mode(ts):
            compat.set_uv_island_mode(ts, False)
        return None
    return 0.25


class ALLSET_OT_uv_move_shell(bpy.types.Operator):
    """Maya Tools > Move UV Shell: a click on a UV picks its whole shell, a drag moves it
    (Blender: UV shell selection + the Move tool; another UV tool goes back to UV selection)"""
    bl_idname = "allset.uv_move_shell"
    bl_label = "Move UV Shell"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        uv_tools.set_component(context, 'ISLAND')
        if not bpy.app.background:
            bpy.ops.wm.tool_set_by_id(name=MOVE_TOOL, space_type='IMAGE_EDITOR')
            _shell_tool["on"] = True
            if not bpy.app.timers.is_registered(_watch_shell_tool):
                bpy.app.timers.register(_watch_shell_tool, first_interval=0.25)
        return {'FINISHED'}


@bpy.app.handlers.persistent
def _load_pre(*_args):
    _isolated.clear()
    _iso_sets.clear()
    _hidden_image.clear()
    _cache.clear()
    _shell_tool["on"] = False
    try:
        bpy.context.window_manager.allset_uv_isolate = False
        bpy.context.window_manager.allset_uv_filter = 'NONE'
    except (AttributeError, RuntimeError):
        pass


classes = (ALLSET_OT_uv_display, ALLSET_OT_uv_isolate, ALLSET_OT_uv_isolate_edit, ALLSET_OT_uv_move_shell)

FILTER_ITEMS = (('NONE', "None", "All faces shown"),
                ('CONNECTED', "Connected Faces", "Only the faces connected to the UV selection shown"),
                ('CONTAINED', "Contained Faces", "Only the faces whose UVs were all selected shown"))


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    wm = bpy.types.WindowManager
    wm.allset_uv_shell_borders = BoolProperty(name="Shell Borders", default=False, update=_redraw,
                                              description="Maya UV Editor: UV shell borders in colour (8)")
    wm.allset_uv_face_colors = BoolProperty(name="Shaded", default=False, update=_shaded_changed,
                                            description="Maya UV Editor Shaded (5): front-facing UV faces blue, "
                                                        "flipped faces red")
    wm.allset_uv_texture_borders = BoolProperty(name="Texture Borders", default=True, update=_redraw,
                                                description="Maya UV Editor: UV shell borders drawn thick (9)")
    wm.allset_uv_isolate = BoolProperty(name="Isolate Select", default=False,
                                        description="Maya UV Editor: only the selected UVs' faces shown (Ctrl+1)")
    wm.allset_uv_filter = EnumProperty(name="Filter Selection", items=FILTER_ITEMS, default='NONE',
                                       description="Maya UV Editor Select > Filter Selection (Connected / Contained "
                                                   "Faces)")
    _handle.append(bpy.types.SpaceImageEditor.draw_handler_add(_draw, (), 'WINDOW', 'POST_PIXEL'))
    bpy.app.handlers.depsgraph_update_post.append(_invalidate)
    bpy.app.handlers.load_pre.append(_load_pre)


def unregister():
    if bpy.app.timers.is_registered(_watch_shell_tool):
        bpy.app.timers.unregister(_watch_shell_tool)
    _shell_tool["on"] = False
    for h, lst in ((_invalidate, bpy.app.handlers.depsgraph_update_post), (_load_pre, bpy.app.handlers.load_pre)):
        if h in lst:
            lst.remove(h)
    while _handle:
        bpy.types.SpaceImageEditor.draw_handler_remove(_handle.pop(), 'WINDOW')
    wm = bpy.types.WindowManager
    for name in ("allset_uv_filter", "allset_uv_isolate", "allset_uv_texture_borders", "allset_uv_shell_borders",
                 "allset_uv_face_colors"):
        if hasattr(wm, name):
            delattr(wm, name)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    _cache.clear()
    uv_arrays.invalidate()
    _isolated.clear()
    _iso_sets.clear()
    _hidden_image.clear()
