# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Outliner set rows on Blender's Outliner (step 96).

Maya lists object sets after the DAG nodes, outside the hierarchy; expanding one shows its members.
The Maya Workflow Kit layout's Outliner is Blender's C tree (``maya_outliner``),
which Python can't add rows to, so a WINDOW POST_PIXEL handler draws the set rows under Blender's last
row: that row is found by reading one pixel line through the middle of each candidate row (an empty
row is one flat stripe colour; rows are contiguous, so a binary search). The rows drawn are remembered
per region; the "Outliner" keymap items ``allset.outliner_set_click`` (LMB CLICK) and
``allset.outliner_set_menu`` (RMB) act on them and pass through elsewhere.

Startup rows: a new Maya scene lists the startup cameras persp / top / front / side (hidden, so
greyed) and the sets defaultLightSet / defaultObjectSet
(defaultLightSet = every light, selecting it selects them; defaultObjectSet is empty;
selecting persp selects the hidden camera). The kit has no camera objects behind them (Blender's user views aren't
cameras; real objects would render, export and sort among the user's objects), so they are drawn rows too: the
cameras first, then the default sets, then the kit sets. Blender's rows can't be pushed down, so with objects in
the scene the cameras follow the DAG rows instead of leading them (step 99). Step 211 (#117): a kit new
Maya scene has real hidden startup cameras (operators/startup_cameras.py) that are Blender's first rows
(ui/outliner_order.py); only scenes without them still get drawn camera rows.

Blender row geometry (step 96): row height = UI_UNIT_Y = round(18 x scale) + 2 x pixel size,
row k spans view y [-(k + 1)·U, -k·U]; a depth-0 row draws its disclosure triangle at ~1.6 U, the icon
at ~2.5 U and the name from ~3.25 U (1 U less without the mode column, step 202).
"""

import math

import bpy

from ..operators import sets

_handle = [None]
REGIONS = {}            # region pointer -> [(y0, y1, kind, set name, member name, triangle x1)]
FLAT = 40               # max channel spread of an empty row line (stripes are flat; text / icons spread > 80)


def unit(prefs):
    """Blender's UI_UNIT_Y in pixels."""
    return int(18.0 * prefs.system.ui_scale + 0.5) + 2 * prefs.system.pixel_size


def first_empty(is_empty, lo, hi):
    """Smallest k in [lo, hi] with ``is_empty(k)``, or None; rows lo.. are full then empty (no gaps)."""
    if not is_empty(hi):
        return None
    while lo < hi:
        mid = (lo + hi) // 2
        if is_empty(mid):
            hi = mid
        else:
            lo = mid + 1
    return lo


CAMERAS = ("persp", "top", "front", "side")
DEFAULT_SETS = ("defaultLightSet", "defaultObjectSet")
_picked = {"camera": ""}   # camera row clicked last (highlighted while no object is selected)


def default_entries(scene=None):
    """Maya's startup Outliner rows the kit draws: [(kind, name, "")]. Startup cameras the scene really has (a kit
    new Maya scene, operators/startup_cameras.py) are Blender's own rows at the top instead."""
    real = set()
    if scene is not None:
        from ..operators import startup_cameras
        real = startup_cameras.names(scene)
    return [('CAMERA', n, "") for n in CAMERAS if n not in real] + [('DEFAULT_SET', n, "") for n in DEFAULT_SETS]


def default_set_members(name, scene):
    """defaultLightSet = every light in the scene (step 99); defaultObjectSet is empty in a new scene."""
    if name == "defaultLightSet":
        return [ob for ob in scene.objects if ob.type == 'LIGHT']
    return []


def row_icon(name, cx, cy, prefs, greyed=False):
    """Kit-drawn Maya Outliner icon (``kit_icons`` ``outliner:SET`` / ``outliner:CAMERA``, step 131, #23) centred on
    (cx, cy), drawn unscaled at Blender's icon size (16 px x UI scale)."""
    from . import kit_icons
    n = kit_icons.size_for(name, prefs.system.ui_scale)
    kit_icons.draw_texture(name, math.floor(cx - n / 2), math.floor(cy - n / 2), n, greyed)


def entries(scene):
    """[(kind, set name, member name)] in Maya order: each set, then its members when expanded."""
    out = []
    for coll in sets.all_sets():
        out.append(('SET', coll.name, ""))
        if coll.allset_expanded:
            out.extend(('MEMBER', coll.name, ob.name) for ob in sets.members(coll, scene))
    return out


def _flat_line(fb, region, y):
    from .. import compat
    buf = compat.read_region_row(fb, region, y)
    if buf is None:
        return True     # outside the region: no row there
    line = buf[0]
    lo = [255, 255, 255]
    hi = [0, 0, 0]
    for i in range(region.width):
        px = line[i]
        for c in range(3):
            v = px[c]
            if v < lo[c]:
                lo[c] = v
            if v > hi[c]:
                hi[c] = v
    return max(hi[c] - lo[c] for c in range(3)) <= FLAT


def _theme():
    th = bpy.context.preferences.themes[0]
    sp = th.outliner.space
    return th, tuple(sp.text) if hasattr(sp, "text") else (0.85, 0.85, 0.85)


def _rect(shader, x0, y0, x1, y1, rgba):
    from gpu_extras.batch import batch_for_shader
    batch = batch_for_shader(shader, 'TRIS', {"pos": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]},
                             indices=[(0, 1, 2), (0, 2, 3)])
    shader.uniform_float("color", rgba)
    batch.draw(shader)


def _tri(shader, cx, cy, r, down, rgba):
    from gpu_extras.batch import batch_for_shader
    if down:
        pts = [(cx - r, cy + r * 0.5), (cx + r, cy + r * 0.5), (cx, cy - r * 0.7)]
    else:
        pts = [(cx - r * 0.5, cy + r), (cx - r * 0.5, cy - r), (cx + r * 0.7, cy)]
    batch = batch_for_shader(shader, 'TRIS', {"pos": pts})
    shader.uniform_float("color", rgba)
    batch.draw(shader)


def draw():
    context = bpy.context
    space, region = context.space_data, context.region
    if region is None or not _is_maya(space):
        return
    found = default_entries(context.scene) + entries(context.scene)
    key = region.as_pointer()
    import blf
    import gpu
    prefs = context.preferences
    u = unit(prefs)
    v2d = region.view2d

    def row_y(k):   # region (y0, y1) of tree row k
        top = v2d.view_to_region(0, -k * u, clip=False)[1]
        return top - u, top

    def k_at(y):
        return int(math.floor(-v2d.region_to_view(0, y)[1] / u))

    fb = gpu.state.active_framebuffer_get()
    k_lo, k_hi = max(0, k_at(region.height - 1)), k_at(0)
    empty = first_empty(lambda k: _flat_line(fb, region, (sum(row_y(k)) / 2)), k_lo, k_hi)
    # Native object rows must remain visible and clickable even in a short
    # Outliner / at a large UI scale. Never pin virtual rows over the DAG.
    if empty is None:
        REGIONS[key] = []
        return
    th, text_rgb = _theme()
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    k0 = empty
    selected = set(context.selected_objects) if context.mode == 'OBJECT' else set()
    # Blender keeps one unit for its mode column while it is on (any mode); the Maya Outliner has none (step 202), so
    # the drawn rows line up with Blender's object rows one unit further left
    lead = 0.0 if not getattr(context.space_data, "show_mode_column", True) else u
    blf.size(0, 11.0 * prefs.system.ui_scale)
    rows = []
    for i, (kind, name, member) in enumerate(found):
        y0, y1 = row_y(k0 + i)
        if y0 < 0 or y1 > region.height:
            continue
        cy = (y0 + y1) / 2.0
        indent = u if kind == 'MEMBER' else 0
        if kind in ('CAMERA', 'DEFAULT_SET'):
            if kind == 'CAMERA':
                hl = not selected and _picked["camera"] == name
            else:
                mem = default_set_members(name, context.scene)
                hl = bool(mem) and set(mem) == selected
            if hl:
                _rect(shader, 0, y0, region.width, y1, (*th.outliner.selected_highlight[:3], 1.0))
            # Maya greys hidden nodes: the startup cameras are hidden
            rgb = text_rgb[:3] if kind == 'DEFAULT_SET' or hl else tuple(c * 0.62 for c in text_rgb[:3])
            row_icon("outliner:CAMERA" if kind == 'CAMERA' else "outliner:SET", lead + 1.5 * u, cy, prefs,
                     greyed=kind == 'CAMERA' and not hl)
            blf.color(0, *rgb, 1.0)
            blf.position(0, lead + 2.25 * u, cy - 0.32 * blf.dimensions(0, "Xg")[1] - 1, 0)
            blf.draw(0, name)
            rows.append((y0, y1, kind, name, "", 0))
            continue
        coll = sets.get(name)
        if coll is None:
            continue
        mem = sets.members(coll, context.scene)
        if kind == 'SET':
            hl = bool(mem) and set(mem) == selected
        else:
            ob = bpy.data.objects.get(member)
            hl = ob is not None and ob in selected
        if hl:
            _rect(shader, 0, y0, region.width, y1, (*th.outliner.selected_highlight[:3], 1.0))
        tri_x1 = 0
        if kind == 'SET' and mem:
            _tri(shader, lead + 0.6 * u, cy, u * 0.17, coll.allset_expanded, (*text_rgb[:3], 0.8))
            tri_x1 = lead + 1.05 * u
        if kind == 'SET':
            row_icon("outliner:SET", lead + 1.5 * u, cy, prefs)
        else:
            ix = indent + lead + 1.5 * u
            _rect(shader, ix - u * 0.12, cy - u * 0.12, ix + u * 0.12, cy + u * 0.12, (*text_rgb[:3], 0.7))
        blf.color(0, *text_rgb[:3], 1.0)
        blf.position(0, indent + lead + 2.25 * u, cy - 0.32 * blf.dimensions(0, "Xg")[1] - 1, 0)
        blf.draw(0, name if kind == 'SET' else member)
        rows.append((y0, y1, kind, name, member, tri_x1))
    gpu.state.blend_set('NONE')
    REGIONS[key] = rows


def _is_maya(space):
    from .maya_outliner import is_maya_outliner
    return is_maya_outliner(space)


def row_at(region, y):
    for row in REGIONS.get(region.as_pointer(), ()):
        if row[0] <= y < row[1]:
            return row
    return None


def _redraw(context):
    for area in context.screen.areas if context.screen else ():
        if area.type == 'OUTLINER':
            area.tag_redraw()


class ALLSET_OT_outliner_set_click(bpy.types.Operator):
    """Outliner set row: click = select the set's members (Ctrl toggle, Shift add), triangle = show members"""
    bl_idname = "allset.outliner_set_click"
    bl_label = "Outliner Set Click"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.region is not None and context.region.type == 'WINDOW' and _is_maya(context.space_data)

    def invoke(self, context, event):
        row = row_at(context.region, event.mouse_region_y)
        if row is None:
            return {'PASS_THROUGH'}
        _y0, _y1, kind, name, member, tri_x1 = row
        if kind in ('CAMERA', 'DEFAULT_SET'):
            return self._default_row(context, event, kind, name)
        coll = sets.get(name)
        if coll is None:
            return {'PASS_THROUGH'}
        if kind == 'SET' and event.mouse_region_x < tri_x1:
            coll.allset_expanded = not coll.allset_expanded
        elif kind == 'SET':
            sets.select_members(context, coll, 'TOGGLE' if event.ctrl else 'ADD' if event.shift else 'REPLACE')
        else:
            ob = bpy.data.objects.get(member)
            if ob is not None and sets._selectable(ob):
                if context.mode != 'OBJECT' and context.active_object is not None:
                    bpy.ops.object.mode_set(mode='OBJECT')
                if event.ctrl:
                    ob.select_set(not ob.select_get())
                else:
                    if not event.shift:
                        for o in context.selected_objects:
                            o.select_set(False)
                    ob.select_set(True)
                if ob.select_get():
                    context.view_layer.objects.active = ob
        _redraw(context)
        return {'FINISHED'}


    def _default_row(self, context, event, kind, name):
        """Maya startup rows: a camera row selects the (hidden) camera — the kit has none, so it clears the object
        selection and highlights the row; defaultLightSet selects every light, defaultObjectSet nothing."""
        if context.mode != 'OBJECT' and context.active_object is not None:
            bpy.ops.object.mode_set(mode='OBJECT')
        if kind == 'CAMERA':
            _picked["camera"] = name
            if not (event.shift or event.ctrl):
                for o in context.selected_objects:
                    o.select_set(False)
        else:
            _picked["camera"] = ""
            mem = [o for o in default_set_members(name, context.scene) if sets._selectable(o)]
            if not (event.shift or event.ctrl):
                for o in context.selected_objects:
                    o.select_set(False)
            for o in mem:
                o.select_set(not o.select_get() if event.ctrl else True)
            if mem and mem[-1].select_get():
                context.view_layer.objects.active = mem[-1]
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_outliner_set_menu(bpy.types.Operator):
    """Outliner set row: the Maya set menu (Select Set Members, Show Set Members, ...)"""
    bl_idname = "allset.outliner_set_menu"
    bl_label = "Outliner Set Menu"

    @classmethod
    def poll(cls, context):
        return context.region is not None and context.region.type == 'WINDOW' and _is_maya(context.space_data)

    def invoke(self, context, event):
        row = row_at(context.region, event.mouse_region_y)
        if row is None or row[2] in ('CAMERA', 'DEFAULT_SET'):
            return {'PASS_THROUGH'}
        wm = context.window_manager
        wm.allset_set_target, wm.allset_set_member = row[3], row[4]
        bpy.ops.wm.call_menu(name=ALLSET_MT_outliner_set.bl_idname)
        return {'FINISHED'}


class ALLSET_MT_outliner_set(bpy.types.Menu):
    """Maya Outliner set / set member RMB menu"""
    bl_label = "Set"
    bl_idname = "ALLSET_MT_outliner_set"

    def draw(self, context):
        wm = context.window_manager
        name, member = wm.allset_set_target, wm.allset_set_member
        coll = sets.get(name)
        layout = self.layout
        if coll is None:
            return
        layout.operator("allset.select_set_members", text="Select Set Members").name = name
        if member:
            op = layout.operator("allset.set_edit", text="Remove From Current Set")
            op.name, op.member, op.action = name, member, 'REMOVE_MEMBER'
            return
        op = layout.operator("allset.set_edit", text="Show Set Members", icon='CHECKBOX_HLT' if coll.allset_expanded
                             else 'CHECKBOX_DEHLT')
        op.name, op.action = name, 'EXPAND'
        layout.separator()
        for action, label in (('ADD', "Add Selected Objects"), ('REMOVE', "Remove Selected Objects"),
                              ('RENAME', "Rename..."), ('DELETE', "Delete Set")):
            op = layout.operator("allset.set_edit", text=label)
            op.name, op.action = name, action


classes = (ALLSET_OT_outliner_set_click, ALLSET_OT_outliner_set_menu, ALLSET_MT_outliner_set)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    _handle[0] = bpy.types.SpaceOutliner.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL')


def unregister():
    if _handle[0] is not None:
        bpy.types.SpaceOutliner.draw_handler_remove(_handle[0], 'WINDOW')
        _handle[0] = None
    REGIONS.clear()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
