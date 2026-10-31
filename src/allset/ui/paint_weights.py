# SPDX-License-Identifier: GPL-3.0-or-later
"""An influence-first skin-paint workspace with native Blender paint capabilities."""
import fnmatch
import re
from types import SimpleNamespace

import bpy
from bl_ui import properties_paint_common as paint_common

from .. import compat
from ..operators import skin, weight_paint as model
from . import status_icons

OPERATIONS = (("MIX", "Replace"), ("ADD", "Add"), ("MUL", "Scale"))
FLOOD_OP = 'allset.flood_weights'


def active(context):
    return model.active(context)


def _prop(layout, owner, name, **kw):
    if owner is not None and hasattr(owner, name):
        layout.prop(owner, name, **kw)


def _muted(layout, text, icon='NONE'):
    row = layout.row()
    row.active = False
    row.label(text=text, icon=icon)


def _card(layout, title, icon='NONE', setting=None, context=None):
    layout.separator(factor=0.35)
    box = layout.box()
    head = box.row(align=True)
    head.alignment = 'LEFT'
    if setting:
        s = model.state(context)
        head.prop(s, setting, text='',
                  icon='TRIA_DOWN' if getattr(s, setting) else 'TRIA_RIGHT', emboss=False)
        head.label(text=title)
        if not getattr(s, setting):
            return None
    else:
        head.label(text=title, icon=icon)
    col = box.column()
    col.use_property_split = False
    col.use_property_decorate = False
    return col


def _native(layout, context, cls):
    # These native paint panels support Properties docks as well as 3D Views.
    # Keep the draw context intact; only interactive viewport actions are routed.
    holder = SimpleNamespace(layout=_BrushLayout(layout), is_popover=False, bl_label=cls.bl_label,
                             paint_settings=lambda ctx: ctx.tool_settings.weight_paint,
                             get_brush_mode=lambda ctx: 'PAINT_WEIGHT')
    cls.draw(holder, context)


class _BrushLayout:
    """Route native Paint Curve's viewport action correctly when drawn in a dock."""
    def __init__(self, layout):
        object.__setattr__(self, '_layout', layout)

    def __setattr__(self, name, value):
        setattr(self._layout, name, value)

    def __getattr__(self, name):
        value = getattr(self._layout, name)
        if not callable(value):
            return value
        def call(*args, **kwargs):
            if name == 'operator' and args and args[0] == 'paintcurve.draw':
                args = ('allset.weight_curve', *args[1:])
            result = value(*args, **kwargs)
            return _BrushLayout(result) if isinstance(result, bpy.types.UILayout) else result
        return call


def _tool(layout, label, kind, blend='', selected=False, icon='NONE'):
    op = layout.operator('allset.weight_tool', text=label, icon=icon, depress=selected)
    op.kind, op.blend = kind, blend
    return op


def _weight_icon(cv):
    colors = [(0.22, 0.42, 0.68), (0.22, 0.62, 0.68), (0.46, 0.82, 0.72)]
    for i, color in enumerate(colors):
        x = 0.12 + i * 0.27
        cv.rect(x, 0.74 - i * 0.19, x + 0.19, 0.88, color)
    cv.line(0.16, 0.29, 0.42, 0.12, 0.06, status_icons.LIGHT)
    cv.line(0.42, 0.12, 0.73, 0.19, 0.06, status_icons.LIGHT)


# Maya 2026 Influences list RMB, labels and order exactly as Maya's;
# the kit's extras come below a separator
MAYA_RMB = (('Lock Selected', 'allset.weight_influence', 'action', 'LOCK_SELECTED'),
            ('Unlock Selected', 'allset.weight_influence', 'action', 'UNLOCK_SELECTED'),
            ('Lock Inverse Selection', 'allset.weight_influence', 'action', 'LOCK_OTHERS'),
            ('Unlock Inverse Selection', 'allset.weight_influence', 'action', 'UNLOCK_OTHERS'),
            ('Select Vertices', 'allset.weight_influence_verts', 'mode', 'SET'),
            ('Add Affected Vertices', 'allset.weight_influence_verts', 'mode', 'ADD'),
            ('Remove Affected Vertices', 'allset.weight_influence_verts', 'mode', 'REMOVE'))


def draw_influence_menu(layout, context):
    for label, op, prop, value in MAYA_RMB:
        setattr(layout.operator(op, text=label), prop, value)
    layout.separator()
    s = model.state(context)
    for action, label, icon in [('LOCK', 'Lock all influences', 'LOCKED'),
                                ('UNLOCK', 'Unlock all influences', 'UNLOCKED'),
                                ('INVERT', 'Invert locks', 'ARROW_LEFTRIGHT')]:
        layout.operator('allset.weight_influence', text=label, icon=icon).action = action
    layout.separator()
    layout.prop(s, 'show_all')
    layout.prop(s, 'locked_only')


class ALLSET_MT_weight_influences(bpy.types.Menu):
    bl_label = 'Influences'
    bl_idname = 'ALLSET_MT_weight_influences'

    def draw(self, context):
        draw_influence_menu(self.layout, context)


def draw_list_item_menu(self, context):
    """RMB on a row of the influence list (Blender's list item context menu) = Maya's Influences RMB."""
    ui_list = getattr(context, 'ui_list', None)
    if ui_list is None or getattr(ui_list, 'bl_idname', '') != 'ALLSET_UL_influences' or not active(context):
        return
    draw_influence_menu(self.layout, context)


def natural_key(name):
    """Maya 2026 Alphabetically = natural order (joint2 before joint10)."""
    return [(0, int(part), '') if part.isdigit() else (1, 0, part) for part in re.split(r'(\d+)', name.casefold())
            if part]


def influence_order(mesh, sort='HIERARCHY'):
    groups = list(mesh.vertex_groups)
    if sort == 'NAME':
        order = sorted(range(len(groups)), key=lambda i: natural_key(groups[i].name))
    elif sort == 'HIERARCHY' and skin.armature_modifier(mesh):
        arm = skin.armature_modifier(mesh).object
        rank = {name: i for i, name in enumerate(skin._hierarchy_order(arm))}
        order = sorted(range(len(groups)), key=lambda i: (rank.get(groups[i].name, len(rank)), i))
    else:
        order = list(range(len(groups)))
    inverse = [0] * len(order)
    for position, index in enumerate(order):
        inverse[index] = position
    return inverse


def chosen_cluster(context, mesh):
    """The Armature modifier picked in the Skin Clusters list (Maya: the first bound one on entry)."""
    mods = skin.armature_modifiers(mesh)
    if not mods:
        return None
    return mods[min(model.state(context).skin_cluster, len(mods) - 1)]


def influence_filter(mesh, flag, search='', sort='NAME', show_all=False, locked_only=False, mod=None):
    names = {g.name for g in skin.influences(mesh, mod)}
    pattern = '*' + search.casefold() + '*'
    flags = [flag if (show_all or g.name in names) and fnmatch.fnmatchcase(g.name.casefold(), pattern)
             and (not locked_only or g.lock_weight) else 0 for g in mesh.vertex_groups]
    return flags, influence_order(mesh, sort)


class ALLSET_UL_influences(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0):
        row = layout.row(align=True)
        mod = skin.armature_modifier(data)
        bone = mod.object.data.bones.get(item.name) if mod else None
        depth = len(bone.parent_recursive) if bone is not None else 0
        indent = '  ' * min(depth, 4) if model.state(context).sort == 'HIERARCHY' else ''
        row.label(text=indent + item.name, icon='BONE_DATA' if bone else 'GROUP_VERTEX')
        row.prop(item, 'lock_weight', text='', emboss=False,
                 icon='LOCKED' if item.lock_weight else 'UNLOCKED')

    def filter_items(self, context, data, propname):
        s = model.state(context)
        return influence_filter(data, self.bitflag_filter_item, s.search, s.sort, s.show_all, s.locked_only,
                                chosen_cluster(context, data))

    def draw_filter(self, context, layout):
        pass  # Dedicated, always-visible search above the list.


def _skin_clusters(layout, context):
    """Maya 2024+ "Skin Clusters": every skin of the mesh in chain order (shown read-only — the kit binds
    one skin per mesh, FBX / engines keep one), the picked one filters the Influences list."""
    s, mesh = model.state(context), context.active_object
    col = _card(layout, 'Skin Clusters', setting='show_skin_clusters', context=context)
    if col is None:
        return
    mods = skin.armature_modifiers(mesh)
    chosen = chosen_cluster(context, mesh)
    if not mods:
        _muted(col, 'No skin cluster: Skin > Bind Skin first.', 'INFO')
    for i, mod in enumerate(mods):
        row = col.split(factor=0.8, align=True)
        op = row.operator('allset.weight_skin_cluster', text=mod.name, icon='MOD_ARMATURE', depress=mod == chosen)
        op.index = i
        row.label(text=str(len(skin.influences(mesh, mod))), icon='BONE_DATA')
    if len(mods) > 1:
        _muted(col, 'Several skin clusters: FBX and game engines keep one skin per mesh.', 'ERROR')
    row = col.row(align=True)
    row.prop(context.tool_settings, 'use_lock_relative', text='Lock-relative', toggle=True)
    if mods:
        col.operator('allset.skin_tools', text='Skin Tools (layers)', icon='RENDERLAYERS')


def _influences(layout, context):
    s, mesh = model.state(context), context.active_object
    col = _card(layout, 'Influences', setting='show_influences', context=context)
    if col is None:
        return
    row = col.row(align=True)
    row.label(text='Sort:')
    row.prop(s, 'sort', expand=True)
    row = col.row(align=True)
    row.prop(s, 'search', text='', icon='VIEWZOOM', placeholder='Find a joint…')
    row.menu('ALLSET_MT_weight_influences', text='', icon='DOWNARROW_HLT')
    col.template_list('ALLSET_UL_influences', '', mesh, 'vertex_groups', mesh.vertex_groups,
                      'active_index', rows=5, maxrows=8, sort_lock=True)
    row = col.row(align=True)
    row.operator('allset.weight_influence', text='Lock others', icon='LOCKED').action = 'OTHERS'
    row.operator('allset.weight_influence', text='Unlock all', icon='UNLOCKED').action = 'UNLOCK'
    vg = mesh.vertex_groups.active
    if vg:
        footer = col.row(align=True)
        footer.label(text=vg.name, icon='LOCKED' if vg.lock_weight else 'BONE_DATA')
        footer.operator('allset.weight_influence', text='', icon='RESTRICT_SELECT_OFF').action = 'JOINT'
    elif not skin.influences(mesh) and not s.show_all:
        _muted(col, 'No joint groups. Include non-joint groups in Filter.', 'INFO')


def _unified(layout, context, name, label, pressure=None):
    ts = context.tool_settings
    brush = ts.weight_paint.brush
    ups = compat.unified_paint_settings(ts)
    unified = {'weight': 'use_unified_weight', 'strength': 'use_unified_strength', 'size': 'use_unified_size'}[name]
    owner = ups if getattr(ups, unified) or brush is None else brush
    prop = name
    if name == 'size' and getattr(owner, 'use_locked_size', 'VIEW') == 'SCENE':
        prop = 'unprojected_size'
    row = layout.row(align=True)
    row.prop(owner, prop, text=label, slider=name != 'size')
    if pressure:
        _prop(row, brush, pressure, text='')
    row.prop(ups, unified, text='', icon='BRUSHES_ALL')
    return row


def s_state(context):
    return model.state(context)


# Maya Profile buttons (Gaussian / Soft (default) / Solid / Square / image)
PROFILES = (('GAUSSIAN', 'Gaussian'), ('SOFT', 'Soft'), ('SOLID', 'Solid'), ('SQUARE', 'Square'))


def current_profile(brush):
    if brush is None:
        return 'SOFT'
    preset = getattr(brush, compat.brush_falloff_props(brush)[0], '')
    return next((k for k, v in skin.PROFILE_CURVE.items() if v == preset), '')


def _maya_brush_fields(col, context, brush):
    """Maya 2026 Brush frame rows the kit adds: Profile, Weight Type, Normalize Weights."""
    s = model.state(context)
    col.separator(factor=0.35)
    row = col.row(align=True)
    row.label(text='Profile:')
    now = current_profile(brush)
    for key, label in PROFILES:
        sub = row.row(align=True)
        sub.enabled = key in skin.PROFILE_CURVE and brush is not None
        sub.operator('allset.weight_profile', text=label, depress=key == now).profile = key
    row = col.row(align=True)
    row.label(text='Weight Type:')
    row.prop_enum(s, 'weight_type', 'SKIN')
    sub = row.row(align=True)
    sub.enabled = False                        # Blender: one dual quaternion switch per skin (Armature modifier)
    sub.prop_enum(s, 'weight_type', 'DQ')
    row = col.row(align=True)
    row.label(text='Normalize Weights:')
    for key, label in (('NONE', 'Off'), ('INTERACTIVE', 'Interactive'), ('POST', 'Post')):
        row.prop_enum(s, 'normalize_mode', key, text=label)


def _brush(layout, context):
    """Maya "Brush" + paint operation: operation, Value / Opacity / Radius, Flood, profile (falloff)."""
    ts, mesh = context.tool_settings, context.active_object
    brush = ts.weight_paint.brush
    kind = model.brush_kind(brush)
    col = _card(layout, 'Brush', setting='show_brush', context=context)
    if col is None:
        return
    # Maya 2026 Brush frame: Mode (Paint / Select / Paint Select, Ctrl+. / Ctrl+,) and Select Geometry
    mode = model.paint_mode(context)
    row = col.row(align=True)
    row.label(text='Mode:')
    for key in model.PAINT_MODES:
        row.operator('allset.skin_paint_mode', text=model.MODE_LABELS[key], depress=mode == key).mode = key
    col.operator('allset.select_geometry')
    col.separator(factor=0.35)
    assets = col.row(align=True)
    _tool(assets, brush.name if brush else 'Choose a brush', 'ASSETS', icon='ASSET_MANAGER')
    assets.menu('VIEW3D_MT_brush_context_menu', text='', icon='DOWNARROW_HLT')
    col.separator(factor=0.35)
    # Maya's paint operations first (Replace / Add / Scale / Smooth, Maya Paint Skin Weights Tool Settings), Blender's
    # extra blends on a second row
    for operations in ((('Replace', 'DRAW', 'MIX'), ('Add', 'DRAW', 'ADD'), ('Scale', 'DRAW', 'MUL'),
                        ('Smooth', 'BLUR', '')),
                       (('Subtract', 'DRAW', 'SUB'), ('Average', 'AVERAGE', ''), ('Smear', 'SMEAR', ''))):
        row = col.row(align=True)
        row.scale_y = 1.15
        for label, target, blend in operations:
            chosen = kind == target and (not blend or (brush and brush.blend == blend))
            _tool(row, label, target, blend, chosen)
    _maya_brush_fields(col, context, brush)
    col.separator(factor=0.5)
    values = col.column(align=True)
    values.scale_y = 1.12
    _unified(values, context, 'strength', 'Opacity', 'use_pressure_strength')
    _unified(values, context, 'weight', 'Value').enabled = kind not in {'BLUR', 'AVERAGE', 'SMEAR'}
    _unified(values, context, 'size', 'Radius', 'use_pressure_size')
    row = col.row(align=True)
    row.label(text='Min/Max value:')
    row.prop(s_state(context), 'min_value', text='')
    row.prop(s_state(context), 'max_value', text='')
    col.separator(factor=0.35)
    presets = col.row(align=True)
    presets.enabled = kind not in {'BLUR', 'AVERAGE', 'SMEAR'}
    for value, label in [(0, '0'), (.25, '0.25'), (.5, '0.5'), (.75, '0.75'), (1, '1')]:
        presets.operator('allset.weight_value', text=label).value = value
    col.separator(factor=0.5)
    row = col.row(align=True)
    row.scale_y = 1.4
    flood = row.row(align=True)
    flood.enabled = (mesh.vertex_groups.active is not None and not mesh.vertex_groups.active.lock_weight
                     and kind != 'SMEAR')
    flood.operator(FLOOD_OP, text='Flood', icon='COLOR')
    _tool(row, 'Sample', 'SAMPLE', icon='EYEDROPPER')
    if mesh.vertex_groups.active and mesh.vertex_groups.active.lock_weight:
        _muted(col, 'Unlock this influence to paint or flood.', 'LOCKED')
    if brush is None:
        _muted(col, 'Choose a brush above to start painting.', 'INFO')
        return
    row = col.row(align=True)
    _tool(row, 'Pick joint', 'SAMPLE_GROUP', icon='EYEDROPPER')
    _tool(row, 'Linear gradient', 'LINEAR')
    _tool(row, 'Radial gradient', 'RADIAL')
    preset, curve = compat.brush_falloff_props(brush)
    current = context.workspace.tools.from_space_view3d_mode('PAINT_WEIGHT', create=False)
    if current and current.idname == 'builtin.gradient':
        _prop(col, brush, preset, text='Gradient falloff')
        if getattr(brush, preset, '') == 'CUSTOM':
            col.template_curve_mapping(brush, curve, brush=True, show_presets=True)
    # Maya "Profile" = the brush falloff
    col.separator(factor=0.5)
    _native(col, context, paint_common.FalloffPanel)
    _prop(col, brush, 'falloff_shape', text='Shape')
    _prop(col, brush, 'use_frontface', text='Front faces only')
    _prop(col, brush, 'use_frontface_falloff', text='Front-face falloff')
    sub = col.column()
    sub.active = getattr(brush, 'use_frontface_falloff', False)
    _prop(sub, brush, 'falloff_angle', text='Falloff angle')
    _prop(col, brush, 'blend', text='Blend mode')
    _prop(col, brush, 'use_accumulate', text='Accumulate strokes')
    ups = compat.unified_paint_settings(ts)
    _prop(col, ups if ups.use_unified_size else brush, 'use_locked_size', text='Size units')
    _prop(col, ts, 'use_multipaint', text='Multi-paint selected joints')
    _prop(col, ts.weight_paint, 'use_group_restrict', text='Existing weights only')


def _visualization(layout, context):
    """Maya 2024+ "Visualization": Geometry Color (Blender's weight colours / colour ramp) and Numeric (kit-drawn
    numbers)."""
    from .status_line import main_view3d
    col = _card(layout, 'Visualization', setting='show_visualization', context=context)
    if col is None:
        return
    area, _region = main_view3d(context.screen)
    view = area.spaces.active if area else None
    if view:
        _prop(col, view.overlay, 'weight_paint_mode_opacity', text='Weight opacity', slider=True)
        _prop(col, view.overlay, 'show_wpaint_contours', text='Weight contours')
    _prop(col, context.tool_settings, 'vertex_group_user', text='Zero weights')
    prefs = context.preferences.view
    col.prop(prefs, 'use_weight_color_range', text='Color ramp')
    sub = col.column()
    sub.enabled = prefs.use_weight_color_range
    sub.template_color_ramp(prefs, 'weight_color_range', expand=True)
    _muted(col, 'This color ramp is shared across Blender.', 'INFO')
    # Maya 2024+ Numeric (Show Numbers, Decimal Places, Number Color, Color Ramp; ui/weight_numbers.py)
    s = model.state(context)
    col.separator(factor=0.5)
    col.label(text='Numeric')
    col.prop(s, 'show_numbers')
    sub = col.column()
    sub.active = s.show_numbers
    sub.prop(s, 'number_places')
    sub.prop(s, 'number_color')
    sub.prop(s, 'number_color_ramp')
    ramp = sub.row(align=True)
    ramp.active = s.number_color_ramp
    ramp.prop(s, 'number_min_color')
    ramp.prop(s, 'number_max_color')


def _stroke(layout, context):
    """Maya "Stroke": stroke method, spacing, stabilizer and reflection."""
    brush = context.tool_settings.weight_paint.brush
    col = _card(layout, 'Stroke', setting='show_stroke', context=context)
    if col is None:
        return
    if brush is not None:
        _native(col, context, paint_common.StrokePanel)
        _prop(col, brush, 'use_smooth_stroke', text='Stabilize stroke')
        sub = col.column()
        sub.enabled = brush.use_smooth_stroke
        _prop(sub, brush, 'smooth_stroke_radius', text='Stabilizer radius')
        _prop(sub, brush, 'smooth_stroke_factor', text='Stabilizer strength')
    mesh = context.active_object.data
    col.prop(mesh, 'use_mirror_vertex_groups', text='Mirror influence names')
    row = col.row(align=True)
    row.label(text='Reflection')
    for axis in ('x', 'y', 'z'):
        row.prop(context.active_object, 'use_mesh_mirror_' + axis, text=axis.upper(), toggle=True)
    radial = col.column()
    radial.active = not mesh.use_mirror_vertex_groups
    radial.prop(mesh, 'radial_symmetry', text='Radial copies')
    topology = col.column()
    topology.active = mesh.use_mirror_vertex_groups
    topology.prop(mesh, 'use_mirror_topology', text='Topology matching')


def _pressure(layout, context):
    """Maya "Stylus Pressure"."""
    brush = context.tool_settings.weight_paint.brush
    col = _card(layout, 'Stylus Pressure', setting='show_pressure', context=context)
    if col is None or brush is None:
        return
    for enabled, curve, title in [('use_pressure_size', 'curve_size', 'Radius pressure'),
                                  ('use_pressure_strength', 'curve_strength', 'Opacity pressure'),
                                  ('use_pressure_jitter', 'curve_jitter', 'Jitter pressure')]:
        _prop(col, brush, enabled, text=title)
        if getattr(brush, enabled, False) and hasattr(brush, curve):
            col.template_curve_mapping(brush, curve, brush=True, show_presets=True)


def _display(layout, context):
    """Maya "Display": brush outline, wireframe, joints in front."""
    from .status_line import main_view3d
    col = _card(layout, 'Display', setting='show_display', context=context)
    if col is None:
        return
    wp = context.tool_settings.weight_paint
    _prop(col, wp, 'show_brush', text='Show brush')
    _prop(col, wp, 'show_brush_on_surface', text='Brush follows surface')
    if wp.brush:
        _native(col, context, paint_common.DisplayPanel)
    area, _region = main_view3d(context.screen)
    view = area.spaces.active if area else None
    if view:
        _prop(col, view.overlay, 'show_paint_wire', text='Show wireframe')
        _prop(col, view.overlay, 'show_overlays', text='Viewport overlays')
    mod = skin.armature_modifier(context.active_object)
    if mod and mod.object:
        _prop(col, mod.object, 'show_in_front', text='Joints in front')


def _mask(layout, context):
    mesh = context.active_object.data
    col = _card(layout, 'Selection masking', setting='show_mask', context=context)
    if col is None:
        return
    row = col.row(align=True)
    row.prop(mesh, 'use_paint_mask_vertex', text='Vertices', toggle=True, icon='VERTEXSEL')
    row.prop(mesh, 'use_paint_mask', text='Faces', toggle=True, icon='FACESEL')
    if not (mesh.use_paint_mask or mesh.use_paint_mask_vertex):
        _muted(col, 'Paint the whole mesh, or enable a mask.')
    for choices in [[('ALL', 'All'), ('NONE', 'None'), ('INVERT', 'Invert')],
                    [('BOX', 'Box'), ('LASSO', 'Lasso'), ('CIRCLE', 'Paint select')],
                    [('GROW', 'Grow'), ('SHRINK', 'Shrink'), ('LINKED', 'Linked')],
                    [('HIDE', 'Hide'), ('HIDE_OTHER', 'Hide others'), ('REVEAL', 'Show all')]]:
        row = col.row(align=True)
        for action, label in choices:
            row.operator('allset.weight_mask', text=label).action = action
    if mesh.use_paint_mask_vertex:
        col.operator('allset.weight_mask', text='Select unweighted vertices').action = 'UNGROUPED'


def _action(layout, key, text=None, icon='NONE'):
    layout.operator('allset.weight_action', text=text or model.ACTIONS[key][0], icon=icon).action = key


def _commands(layout, context):
    """Blender extra: Maya keeps these in the Skin menu (Normalize, Mirror, Prune ...), not in Tool Settings."""
    col = _card(layout, 'Skin Commands', setting='show_commands', context=context)
    if col is None:
        return
    _action(col, 'SET', 'Set current Value', icon='COLOR')
    row = col.row(align=True)
    _action(row, 'NORMALIZE_ALL', 'Normalize all')
    _action(row, 'NORMALIZE', 'Normalize active')
    row = col.row(align=True)
    _action(row, 'SMOOTH', 'Smooth')
    _action(row, 'LEVELS', 'Levels')
    _action(col, 'MIRROR', icon='MOD_MIRROR')
    row = col.row(align=True)
    _action(row, 'CLEAN', 'Prune')
    _action(row, 'LIMIT', 'Limit influences')
    row = col.row(align=True)
    _action(row, 'QUANTIZE', 'Quantize')
    _action(row, 'INVERT', 'Invert')
    _action(col, 'TRANSFER', 'Transfer from another mesh', icon='MOD_DATA_TRANSFER')
    row = col.row(align=True)
    _action(row, 'AUTO', 'Automatic weights')
    _action(row, 'ENVELOPE', 'Bone envelopes')
    _muted(col, 'Locked influences stay protected.', 'LOCKED')


# Maya 2024+ Tool Settings frames in order, then Blender extras (PR #125 follow-up; Maya 2022
# had Influences / Gradient / Stroke / Stylus Pressure / Display)
SECTIONS = (("Skin Clusters", _skin_clusters), ("Influences", _influences), ("Brush", _brush),
            ("Visualization", _visualization), ("Stroke", _stroke), ("Stylus Pressure", _pressure),
            ("Display", _display), ("Skin Commands", _commands), ("Selection Masking", _mask))
MAYA_SECTIONS = ("Skin Clusters", "Influences", "Brush", "Visualization", "Stroke", "Stylus Pressure", "Display")


def draw(layout, context):
    """The Paint Skin Weights Tool Settings: drawn in the Tool Settings dock only (no Maya version turns the
    Channel Box into paint UI)."""
    layout.use_property_decorate = False
    s = model.state(context)
    title = layout.split(factor=0.86, align=True)
    title.scale_y = 1.35
    title.label(text='Paint Skin Weights Tool', icon_value=status_icons.icon('skin_weights'))
    title.operator('allset.weight_paint_exit', text='', icon='CHECKMARK')
    for _name, fn in SECTIONS:
        fn(layout, context)
    layout.separator(factor=0.6)
    if s.status:
        _muted(layout, s.status, 'CHECKMARK')
    footer = layout.box()
    _muted(footer, 'Q  Select    W / E / R  Transform')
    _muted(footer, 'Ctrl-click a joint to choose its influence')


classes = (ALLSET_MT_weight_influences, ALLSET_UL_influences)


def register():
    status_icons.EXTRA['skin_weights'] = _weight_icon
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.UI_MT_list_item_context_menu.append(draw_list_item_menu)


def unregister():
    bpy.types.UI_MT_list_item_context_menu.remove(draw_list_item_menu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    status_icons.EXTRA.pop('skin_weights', None)
