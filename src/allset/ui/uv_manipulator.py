# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya-style manipulator in the UV Editor.

Maya's UV Editor draws the Move / Rotate / Scale manipulators in UV space at the centre of the selected UVs' box:
Move = a red U arrow, a green V arrow and a centre square (free move); Rotate = one ring; Scale = U / V handles
ending in boxes and a centre box (uniform). Dragging a handle moves the selected UVs along that handle.

The kit swaps the widget of the UV Editor's Move / Rotate / Scale tools (``IMAGE_PT_tools_active._tools['UV']``)
for ``ALLSET_GGT_uv_xform``, the same way the 3D manipulator swaps the 3D View tools. Each handle starts Blender's
own transform (``transform.translate`` / ``rotate`` / ``resize``) with the handle's axis, so snapping, numeric input
and the tool keys (W / E / R, the tool's own keymap) keep working; the handles act on Blender's UV data.
Handles are drawn by the kit (no Maya art) in region pixels and picked by their screen distance.
"""

import math

import bmesh
import bpy
from bpy.types import Gizmo, GizmoGroup
from mathutils import Matrix

from .. import compat

GROUP = "ALLSET_GGT_uv_xform"
GIZMO = "ALLSET_GT_uv_handle"
TOOLS = {"builtin.move": 'TRANSLATE', "builtin.rotate": 'ROTATE', "builtin.scale": 'RESIZE'}
BLENDER_WIDGETS = {"IMAGE_GGT_gizmo2d_translate", "IMAGE_GGT_gizmo2d_rotate", "IMAGE_GGT_gizmo2d_resize"}
LENGTH_PX = 80          # handle length at UI scale 1 (Maya-sized on screen)
PICK_PX = 8             # how near the pointer must be to a handle
HEAD = 0.18             # arrow head / box size, in handle lengths
CENTER = 0.1            # half size of the centre square / box

OPS = {'TRANSLATE': "transform.translate", 'ROTATE': "transform.rotate", 'RESIZE': "transform.resize"}
AXES = {'U': (True, False, False), 'V': (False, True, False), 'UV': (False, False, False)}


# --- selection --------------------------------------------------------------------------------------------------

def _picked_loops(a, bm, uv, shown, sync, ts):
    """Per loop: its UV is selected (the UVs a UV transform moves)."""
    if not sync or getattr(bm, "uv_select_sync_valid", False):
        return a.uv_sel(bm, uv, shown)      # UV Sync on keeps its own UV selection while that is valid
    vert, _edge, face = ts.mesh_select_mode
    if face and not vert:
        return a.face_sel[a.corner_face]    # face mode: the selected faces' UVs
    return a.vert_sel[a.corner_vert]


def selected_uv_bounds(context):
    """(min u, min v, max u, max v) of the selected UVs of every mesh in edit mode, or None."""
    import numpy as np
    from ..operators import uv_arrays
    sync = context.scene.tool_settings.use_uv_select_sync
    lo, hi = None, None
    obs = list(getattr(context, "objects_in_mode_unique_data", None) or [])
    depsgraph = context.view_layer.depsgraph
    for ob in obs:
        if ob.type != 'MESH':
            continue
        try:
            bm = bmesh.from_edit_mesh(ob.data)
        except (ValueError, RuntimeError, ReferenceError):
            continue
        uv = bm.loops.layers.uv.active
        if uv is None:
            continue
        a = uv_arrays.read(ob, bm, uv, depsgraph, cached=True)
        shown = uv_arrays.shown_faces(a, sync)       # sync off: the UV Editor shows only the selected faces' UVs
        picked = _picked_loops(a, bm, uv, shown, sync, context.scene.tool_settings) & shown[a.corner_face]
        if not picked.any():
            continue
        pts = a.uv[picked]
        p_lo, p_hi = pts.min(axis=0), pts.max(axis=0)
        lo = p_lo if lo is None else np.minimum(lo, p_lo)
        hi = p_hi if hi is None else np.maximum(hi, p_hi)
    if lo is None:
        return None
    return float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1])


def center_px(context, bounds):
    """The selection box centre in region pixels (Maya puts the manipulator there)."""
    u = (bounds[0] + bounds[2]) * 0.5
    v = (bounds[1] + bounds[3]) * 0.5
    x, y = context.region.view2d.view_to_region(u, v, clip=False)
    return float(x), float(y)


def length_px(context):
    from . import manipulator
    return LENGTH_PX * context.preferences.view.ui_scale * manipulator.SIZE[0]


# --- shapes (unit = one handle length) ----------------------------------------------------------------------------

def _arrow(axis):
    """Shaft line + head triangle along +U ('U') or +V ('V')."""
    def p(a, b):
        return (a, b, 0.0) if axis == 'U' else (b, a, 0.0)
    lines = [p(CENTER * 1.6, 0.0), p(1.0 - HEAD, 0.0)]
    tris = [p(1.0, 0.0), p(1.0 - HEAD, HEAD * 0.4), p(1.0 - HEAD, -HEAD * 0.4)]
    return [('LINES', lines), ('TRIS', tris)]


def _box_end(axis):
    def p(a, b):
        return (a, b, 0.0) if axis == 'U' else (b, a, 0.0)
    h = HEAD * 0.4
    lines = [p(CENTER * 1.6, 0.0), p(1.0 - 2 * h, 0.0)]
    tris = [p(1.0 - 2 * h, -h), p(1.0, -h), p(1.0, h), p(1.0 - 2 * h, -h), p(1.0, h), p(1.0 - 2 * h, h)]
    return [('LINES', lines), ('TRIS', tris)]


def _square(filled):
    c = CENTER
    if filled:
        return [('TRIS', [(-c, -c, 0), (c, -c, 0), (c, c, 0), (-c, -c, 0), (c, c, 0), (-c, c, 0)])]
    pts = [(-c, -c, 0), (c, -c, 0), (c, c, 0), (-c, c, 0)]
    return [('LINES', [q for i in range(4) for q in (pts[i], pts[(i + 1) % 4])])]


def _ring(n=64):
    pts = [(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n), 0.0) for i in range(n)]
    return [('LINES', [q for i in range(n) for q in (pts[i], pts[(i + 1) % n])])]


def shapes(kind, handle):
    """Draw shapes of one handle: kind TRANSLATE / ROTATE / RESIZE, handle U / V / UV."""
    if kind == 'ROTATE':
        return _ring()
    if handle == 'UV':
        return _square(filled=kind == 'RESIZE')
    return _arrow(handle) if kind == 'TRANSLATE' else _box_end(handle)


def hit(kind, handle, dx, dy, length, pick=PICK_PX):
    """The pointer, (dx, dy) pixels from the manipulator centre, is on this handle."""
    x, y = dx / length, dy / length
    t = pick / length
    if kind == 'ROTATE':
        return abs(math.hypot(x, y) - 1.0) <= t
    if handle == 'UV':
        return abs(x) <= CENTER + t and abs(y) <= CENTER + t
    a, b = (x, y) if handle == 'U' else (y, x)
    return CENTER + t < a <= 1.0 + t and abs(b) <= max(t, HEAD * 0.4)


# --- gizmos -------------------------------------------------------------------------------------------------------

# One UV manipulator handle: kit-drawn, picked by its distance on screen.
class ALLSET_GT_uv_handle(Gizmo):
    bl_idname = GIZMO

    __slots__ = ("kit_shapes", "kit_kind", "kit_handle", "kit_center", "kit_length")

    def build(self, kind, handle):
        self.kit_kind, self.kit_handle = kind, handle
        self.kit_shapes = [self.new_custom_shape(t, v) for t, v in shapes(kind, handle)]
        self.kit_center = (0.0, 0.0)
        self.kit_length = float(LENGTH_PX)

    def draw(self, context):
        for sh in getattr(self, "kit_shapes", ()):
            self.draw_custom_shape(sh)

    def test_select(self, context, location):
        if getattr(self, "kit_kind", None) is None:
            return -1
        cx, cy = self.kit_center
        return 0 if hit(self.kit_kind, self.kit_handle, location[0] - cx, location[1] - cy, self.kit_length) else -1


def active_kind(context):
    """TRANSLATE / ROTATE / RESIZE while the UV Editor's Move / Rotate / Scale tool uses the kit manipulator."""
    try:
        tool = context.workspace.tools.from_space_image_mode('UV', create=False)
    except (TypeError, RuntimeError, AttributeError):
        return None
    if tool is None or tool.widget != GROUP:
        return None
    return TOOLS.get(tool.idname)


class ALLSET_GGT_uv_xform(GizmoGroup):
    bl_idname = GROUP
    bl_label = "Maya UV Manipulator"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT', 'TOOL_FALLBACK_KEYMAP'}     # keep the tool's select fallback (marquee)

    @classmethod
    def setup_keymap(cls, keyconfig):
        return keyconfig.keymaps.new(name="Generic Gizmo Maybe Drag", space_type='EMPTY', region_type='WINDOW')

    @classmethod
    def poll(cls, context):
        space = context.space_data
        if space is None or space.type != 'IMAGE_EDITOR' or space.mode != 'UV' or context.mode != 'EDIT_MESH':
            return False
        if not space.show_gizmo or not getattr(space, "show_gizmo_tool", True):
            return False
        return active_kind(context) is not None

    def setup(self, context):
        self.kit_built = None
        self.kit_handles = []

    def _build(self, kind):
        from . import manipulator
        for gz in self.kit_handles:
            self.gizmos.remove(gz)
        self.kit_handles = []
        colours = manipulator.axis_colours()
        names = ('UV',) if kind == 'ROTATE' else ('U', 'V', 'UV')
        for handle in names:
            gz = self.gizmos.new(GIZMO)
            gz.build(kind, handle)
            props = gz.target_set_operator(OPS[kind])
            if kind != 'ROTATE':
                props.constraint_axis = AXES[handle]
                props.orient_type = 'GLOBAL'
            props.release_confirm = True        # Maya: letting go of the handle ends the drag
            gz.color = {'U': colours['X'], 'V': colours['Y']}.get(handle, colours['Z'] if kind == 'ROTATE'
                                                                  else manipulator.CENTER_IDLE)
            gz.alpha = 1.0
            gz.color_highlight = manipulator.YELLOW
            gz.alpha_highlight = 1.0
            gz.line_width = 2.0
            gz.use_draw_modal = False
            gz.use_draw_scale = False       # matrix_basis is already in region pixels
            gz.use_tooltip = False      # Maya manipulators have no tooltip
            self.kit_handles.append(gz)
        self.kit_built = kind

    def draw_prepare(self, context):
        kind = active_kind(context)
        if kind is None:
            return
        if kind != self.kit_built:
            self._build(kind)
        from ..operators import uv_arrays
        # A transform / UV modal changes the edit mesh: reading it then is unsafe (and the handles would lag),
        # so they hide while it runs and come back at the new centre.
        bounds = None if uv_arrays.editing_now(context.window_manager) else selected_uv_bounds(context)
        hide = bounds is None
        if not hide:
            cx, cy = center_px(context, bounds)
            length = length_px(context)
            m = Matrix.Translation((cx, cy, 0.0)) @ Matrix.Scale(length, 4)
        for gz in self.kit_handles:
            gz.hide = hide
            if hide:
                continue
            gz.kit_center = (cx, cy)
            gz.kit_length = length
            gz.matrix_basis = m


classes = (ALLSET_GT_uv_handle, ALLSET_GGT_uv_xform)


# --- tool widget swap ---------------------------------------------------------------------------------------------

_saved = {}


def _panel():
    from bl_ui.space_toolsystem_toolbar import IMAGE_PT_tools_active
    return IMAGE_PT_tools_active


def _swap_items(items):
    out = []
    for it in items:
        if isinstance(it, tuple) and not hasattr(it, "idname"):
            out.append(tuple(_swap_items(it)))
        elif getattr(it, "idname", None) in TOOLS and getattr(it, "widget", None) in BLENDER_WIDGETS:
            out.append(it._replace(widget=GROUP))
        else:
            out.append(it)
    return out


def _original_widget(idname):
    for it in _flat(_saved.get('UV', ())):
        if getattr(it, "idname", None) == idname:
            return it.widget
    return None


def _flat(items):
    for it in items:
        if isinstance(it, tuple) and not hasattr(it, "idname"):
            yield from _flat(it)
        elif it is not None and hasattr(it, "idname"):
            yield it


def patch_tools():
    cls = _panel()
    if 'UV' in _saved:
        return
    items = cls._tools['UV']
    _saved['UV'] = items
    cls._tools['UV'] = type(items)(_swap_items(items))


def unpatch_tools():
    cls = _panel()
    if 'UV' in _saved:
        cls._tools['UV'] = _saved.pop('UV')


def ensure_tools(patched=True):
    """Every workspace's active UV Move / Rotate / Scale tool uses the kit manipulator (``patched``) or Blender's
    gizmo again. Returns how many tools were set up again."""
    from bl_ui.space_toolsystem_common import ToolSelectPanelHelper
    cls = _panel()
    done = 0
    for ws in bpy.data.workspaces:
        try:
            tool = ws.tools.from_space_image_mode('UV', create=False)
        except (TypeError, RuntimeError, AttributeError):
            continue
        if tool is None or tool.idname not in TOOLS:
            continue
        want = GROUP if patched else (_original_widget(tool.idname) or _blender_widget(tool.idname))
        if tool.widget == want:
            continue
        item = next((it for it, _i in ToolSelectPanelHelper._tools_flatten_with_tool_index(cls._tools['UV'])
                     if it is not None and it.idname == tool.idname), None)
        if item is None:
            continue
        fallback = next((it for it, _i in ToolSelectPanelHelper._tools_flatten_with_tool_index(cls._tools['UV'])
                         if it is not None and it.idname == tool.idname_fallback), None)
        keymap_fallback = (fallback and fallback.keymap and fallback.keymap[0]) or ""
        if keymap_fallback:
            keymap_fallback += " (fallback)"
        try:
            tool.setup(idname=item.idname, keymap=item.keymap[0] if item.keymap else "",
                       cursor=item.cursor or 'DEFAULT', options=item.options or set(), gizmo_group=want,
                       brush_type=item.brush_type or 'ANY', data_block=item.data_block or "",
                       operator=item.operator or "", index=tool.index, idname_fallback=tool.idname_fallback,
                       keymap_fallback=keymap_fallback)
            done += 1
        except (TypeError, RuntimeError, AttributeError) as ex:
            print("allset: UV tool setup failed", tool.idname, ex)
    return done


def _blender_widget(idname):
    return {"builtin.move": "IMAGE_GGT_gizmo2d_translate", "builtin.rotate": "IMAGE_GGT_gizmo2d_rotate",
            "builtin.scale": "IMAGE_GGT_gizmo2d_resize"}[idname]


def wanted():
    """The add-on preference: the kit handles (True) or Blender's UV gizmos."""
    from .. import preferences
    try:
        return bool(preferences.get().maya_uv_manipulator)
    except (KeyError, AttributeError):
        return True


def follow_preference():
    """Give the UV tools the kit handles or Blender's gizmos, as the preference says."""
    if wanted():
        patch_tools()
    else:
        unpatch_tools()
    try:
        ensure_tools(bool(_saved))
    except (ReferenceError, AttributeError):
        pass


def _ensure_timer():
    follow_preference()
    return 0.5


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    if wanted():
        patch_tools()
    bpy.app.timers.register(_ensure_timer, first_interval=0.1, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(_ensure_timer):
        bpy.app.timers.unregister(_ensure_timer)
    unpatch_tools()
    try:
        ensure_tools(False)
    except (ReferenceError, AttributeError):
        pass
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
