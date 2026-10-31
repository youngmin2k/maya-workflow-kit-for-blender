# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya animation layer commands, part 4 (Issue #111).

Maya 2022 Layer Editor Anim tab (its menus and labels),
re-implemented on the kit's NLA layers (operators/anim_layers.py):

- Extract Selected Objects: per selected layer L a new layer
  ``L_extract`` with L's settings, right above L, takes the selected objects' membership and curves out of L
  (``cmds.animLayer(extractAnimation=...)``); with BaseAnimation selected (and Extract Non-Layered Animation for
  Selected / All Objects) a new Override layer ``BaseAnimation_extract`` right above BaseAnimation takes the objects'
  base curves. The result doesn't change.
- Duplicate Layer / Duplicate Layer (No Animation) (``cmds.animLayer("L_copy", copy="L")`` +
  ``moveLayerAfter="L"``): a copy right above L with the same members, settings and (or without) curves.
- Empty (``cmds.animLayer(removeAllAttributes=True)``) / Delete Empty Layers (every layer but
  BaseAnimation without attributes; the others are named in a warning).
- Zero Weight and Key Layer / Set Weight to 1.0 and Key Layer: weight 0 / 1
  on the selected layers, then a key on ``<layer>.weight`` at the current time. The kit's weight is each member's
  strip influence, so the key goes on every member's influence curve.
- Layer Editor Ctrl / Shift click (Qt tree view): several selected layers (``picked`` flags); the last picked one stays
  ``allset_anim_layer_index`` (keys and the Graph Editor's editable curves), ui/graph_layers.py draws the
  other selected layers' curves.

Maya 2022:
new layers (extract / copy) get weight 1.0 whatever L's weight (so an extract from a layer of weight != 1 changes the
result, like Maya), go directly above L and are not selected; an Override copy without animation holds L's value at
the current time; Delete Empty Layers deletes the layers without member attributes (keys don't count).
"""

import bpy
from bpy.props import BoolProperty, FloatProperty, StringProperty

from . import anim_layers as al

EXTRACT = "_extract"
COPY = "_copy"
NOT_EMPTY = "Layer was not deleted because it was not empty: {}"     # Maya's warning text


# --- selection (Layer Editor Ctrl / Shift click) --------------------------------------------------------------

def pick(scene, index, toggle=False, extend=False):
    """Maya's tree view click on layer ``index``: plain = only it, Ctrl = add / remove it, Shift = the range from the
    last picked one (list order = Maya's stack order). The last picked layer becomes ``allset_anim_layer_index``; a
    Ctrl click on the last selected layer keeps it (the kit always has one selected layer)."""
    ls = al.layers(scene)
    n = len(ls)
    if not 0 <= index < n:
        return
    cur = scene.allset_anim_layer_index
    have = {i for i, e in enumerate(ls) if e.picked} if 0 <= cur < n and ls[cur].picked else \
        ({cur} if 0 <= cur < n else set())
    new = index
    if toggle:
        if index in have:
            if len(have) > 1:
                have.discard(index)
                new = cur if cur in have else max(have)
        else:
            have.add(index)
    elif extend and 0 <= cur < n:
        lo, hi = sorted((cur, index))
        have = set(range(lo, hi + 1))
    else:
        have = {index}
    for i, e in enumerate(ls):
        if e.picked != (i in have):
            e.picked = i in have
    if scene.allset_anim_layer_index != new:
        scene.allset_anim_layer_index = new       # its update shows the layer (anim_layers.show)
    else:
        al.show(scene)


def activate(scene, name):
    """Make the selected layer ``name`` the last picked one (Graph Editor row / curve pick), keeping the selection."""
    ls = al.layers(scene)
    i = next((k for k, e in enumerate(ls) if e.name == name), None)
    if i is None:
        return False
    keep = {e.name for e in al.selected_layers(scene)}
    if name not in keep:
        return False
    for e in ls:
        e.picked = e.name in keep
    if scene.allset_anim_layer_index != i:
        scene.allset_anim_layer_index = i
    return True


def redraw(context):
    wm = getattr(context, "window_manager", None)
    for win in (wm.windows if wm is not None else ()):
        for area in win.screen.areas:
            if area.type in {'GRAPH_EDITOR', 'DOPESHEET_EDITOR', 'VIEW_3D', 'PROPERTIES'}:
                area.tag_redraw()


# --- helpers ------------------------------------------------------------------------------------------------

def maya_name(scene, base):
    """Maya node naming: ``base`` when free, else ``base`` + 1, 2, ... (the clash suffix)."""
    names = {e.name for e in al.layers(scene)}
    if base not in names:
        return base
    n = 1
    while f"{base}{n}" in names:
        n += 1
    return f"{base}{n}"


def _index_of(scene, name):
    return next((i for i, e in enumerate(al.layers(scene)) if e.name == name), None)


def _keep_selection(scene, name, picked):
    """Point the selected index at ``name`` again after list edits (the ``picked`` flags move with their entries)."""
    i = _index_of(scene, name)
    if i is None:
        i = 0
        for e in al.layers(scene):
            e.picked = False
    if scene.allset_anim_layer_index != i:
        scene.allset_anim_layer_index = i
    for e in al.layers(scene):
        if e.name in picked and not e.picked:
            e.picked = True


SETTINGS = ("mute", "solo", "lock", "override")   # not weight: a copy / extract layer has weight 1.0


def insert_layer(scene, name, above, like=None):
    """A new list entry ``name`` right above entry ``above`` (Maya ``-moveLayerAfter``), settings copied from
    ``like`` (``-copy`` / ``-copyNoAnimation`` keep Additive / Override, weight 1.0)."""
    ls = al.ensure_list(scene)
    cur = al.selected(scene)
    keep, picked = (cur.name if cur is not None else al.BASE), {e.name for e in ls if e.picked}
    e = ls.add()
    e.name = name
    ls.move(len(ls) - 1, above + 1)
    e = ls[above + 1]
    if like is not None:
        for attr in SETTINGS:
            v = getattr(like, attr)
            if getattr(e, attr) != v:
                setattr(e, attr, v)
    _keep_selection(scene, keep, picked)
    return e


def _rename_action(act, layer, ob):
    act[al.MARK] = layer
    act.name = f"{layer}_{ob.name}"


def move_track(scene, ob, src, dst):
    """``ob``'s curves on ``src`` go to a new ``dst`` track (Maya -extractAnimation: the same curves, keys and
    tangents), the attribute list too; the weight and its keys stay with ``src`` (the new layer has weight 1.0);
    BaseAnimation gets a new empty action."""
    tr = al.tracks(ob)[src]
    act = al._strip(tr).action
    ad = ob.animation_data
    if ad.action is not None and ad.action == act:
        ad.action = None
    ad.nla_tracks.remove(tr)
    _rename_action(act, dst, ob)
    al._add_track(ob, dst, act)
    if src == al.BASE:
        al._add_track(ob, al.BASE, al._new_action(ob, al.BASE))
    rec = al._attr_record(ob).get(src)
    if rec is not None:
        al._set_attr_record(ob, src, None)
        al._set_attr_record(ob, dst, rec)


def copy_track(scene, ob, src, dst, with_curves=True, hold=None):
    """``ob``'s ``src`` track copied to a new ``dst`` track (Maya ``cmds.animLayer(copy=...)``: copies of the curves,
    same members; weight 1.0 without weight keys). ``with_curves`` False = ``copyNoAnimation=True``; ``hold`` = a
    frame: every curve of ``src`` becomes a static value = its value at that frame (Override copy without animation)."""
    tr = al.tracks(ob)[src]
    st = al._strip(tr)
    if with_curves:
        act = st.action.copy()
        _rename_action(act, dst, ob)
    else:
        act = al._new_action(ob, dst)
    al._add_track(ob, dst, act)
    if not with_curves and hold is not None:
        for fc in al.layer_curves(ob, src):
            if len(fc.keyframe_points):
                static(ob, act, fc.data_path, fc.array_index, hold, fc.evaluate(hold))
    rec = al._attr_record(ob).get(src)
    if rec is not None:
        al._set_attr_record(ob, dst, rec)


def static(ob, act, path, index, frame, value):
    """Maya's static (unkeyed) layer value of a member attribute. NLA has no per-strip constant, so the kit writes it
    as one CONSTANT key (a one-key curve where Maya has no curve; the result is the same at every frame)."""
    fc = al._fcurve(act, path, index) or al._new_fcurve(ob, act, path, index)
    if fc is None:
        return None
    fc.keyframe_points.clear()
    kp = fc.keyframe_points.insert(frame, value, options={'FAST'})
    kp.interpolation = 'CONSTANT'
    fc.update()
    return fc


def _copy_keys(src, dst):
    pts = src.keyframe_points
    dst.keyframe_points.clear()
    dst.keyframe_points.add(len(pts))
    for a, b in zip(dst.keyframe_points, pts):
        a.co = b.co
        a.interpolation = b.interpolation
        a.handle_left_type, a.handle_right_type = b.handle_left_type, b.handle_right_type
        a.handle_left, a.handle_right = b.handle_left, b.handle_right
        a.easing = b.easing
    dst.extrapolation = src.extrapolation
    dst.update()


def copy_base(scene):
    """Maya Duplicate Layer on BaseAnimation (``copy_base``): an Override layer
    ``BaseAnimation_copy`` on top of the stack; members = the layered attributes only (those in some layer above
    BaseAnimation), curves = copies of their base curves; a member without a base curve holds its base value (the
    property default NLA starts from, see anim_layers.key) — so the copy overrides every layer below."""
    from ..ui import channel_box as cb
    ls = al.layers(scene)
    new = insert_layer(scene, maya_name(scene, al.BASE + COPY), len(ls) - 1)
    new.override = True
    obs = []
    for ob in list(scene.objects):
        have = al.tracks(ob)
        if al.BASE not in have:
            continue
        keys = list(dict.fromkeys(k for name in have if name not in (al.BASE, new.name)
                                  for k in al.member_keys(ob, name)))
        keys = [k for k in keys if not isinstance(_value_of(ob, k), bool)]   # visibility isn't NLA-layered
        if not keys:
            continue
        act = al._new_action(ob, new.name)
        al._add_track(ob, new.name, act)
        for k in keys:
            path, idx, _kind = cb.channel_path(k)
            idx = max(idx, 0)
            base = al.base_curve(ob, path, idx)
            if base is not None and len(base.keyframe_points):
                fc = al._new_fcurve(ob, act, path, idx)
                if fc is not None:
                    _copy_keys(base, fc)
            else:
                static(ob, act, path, idx, scene.frame_current, al._identity(path))
        al._set_attr_record(ob, new.name, keys)
        obs.append(ob)
    _finish(scene, obs)
    return new.name


def _value_of(ob, key):
    from ..ui import channel_box as cb
    path, idx, _kind = cb.channel_path(key)
    try:
        v = ob.path_resolve(path)
        return v[idx] if idx >= 0 else v
    except (ValueError, TypeError, IndexError, KeyError):
        return None


def _finish(scene, obs):
    names = [e.name for e in al.layers(scene)]
    for ob in obs:
        al.order_tracks(ob, names)
        ob.update_tag(refresh={'TIME'})
    al.sync(scene)


# --- commands ------------------------------------------------------------------------------------------------

def extract(scene, objects, layer):
    """Maya Extract Selected Objects from ``layer`` (BaseAnimation: Extract Non-Layered Animation). Returns the new
    layer's name. Maya makes the layer even when no object is a member."""
    if layer == al.BASE:
        new = insert_layer(scene, maya_name(scene, al.BASE + EXTRACT), 0)
        new.override = True              # Maya: an Override layer from the selection
        obs = list(objects)
        for ob in obs:
            al.ensure_base(ob)
            move_track(scene, ob, al.BASE, new.name)
    else:
        src = al.layers(scene)[_index_of(scene, layer)]
        new = insert_layer(scene, maya_name(scene, layer + EXTRACT), _index_of(scene, layer), like=src)
        obs = [ob for ob in objects if layer in al.tracks(ob)]
        for ob in obs:
            move_track(scene, ob, layer, new.name)
    _finish(scene, obs)
    return new.name


def duplicate(scene, layer, with_curves=True):
    """Maya Duplicate Layer / Duplicate Layer (No Animation): ``L_copy``
    directly above L (a second copy ``L_copy1`` also directly above L, i.e. below the first), weight 1.0."""
    if layer == al.BASE:
        if not with_curves:
            return None      # Duplicate Layer (No Animation) on BaseAnimation is unknown: nothing happens
        return copy_base(scene)
    src = al.layers(scene)[_index_of(scene, layer)]
    new = insert_layer(scene, maya_name(scene, layer + COPY), _index_of(scene, layer), like=src)
    obs = al.members(scene, layer)
    hold = scene.frame_current if src.override and not with_curves else None
    for ob in obs:
        copy_track(scene, ob, layer, new.name, with_curves, hold)
    _finish(scene, obs)
    return new.name


def empty(scene, layer):
    """Maya Layers > Empty: no members, no curves; the layer stays."""
    for ob in al.members(scene, layer):
        al._set_attr_record(ob, layer, None)
        al.remove_object(scene, ob, layer)
        ob.update_tag(refresh={'TIME'})
    al.sync(scene)


def delete_empty(scene):
    """Maya Delete Empty Layers: every layer but BaseAnimation without attributes (kit: without member objects).
    Returns (deleted, kept) names."""
    ls = al.layers(scene)
    cur = al.selected(scene)
    keep, picked = (cur.name if cur is not None else al.BASE), {e.name for e in ls if e.picked}
    gone = [e.name for e in ls if e.name != al.BASE and not al.members(scene, e.name)]
    kept = [e.name for e in ls if e.name != al.BASE and e.name not in gone]
    for name in gone:
        ls.remove(_index_of(scene, name))
    _keep_selection(scene, keep, picked)
    al.sync(scene)
    return gone, kept


def key_weight(scene, names, weight, frame=None):
    """Maya Zero Weight and Key Layer / Set Weight to 1.0 and Key Layer (``weight`` 0 / 1) and the Weight row's K
    button (``weight`` None = the current weight), each layer's weight set, then
    ``setKeyframe <layer>.weight`` at ``frame``. The kit's weight is each member's strip influence, so the key goes on
    every member strip's influence curve (Maya auto tangents = Blender Auto Clamped, as for every kit key).
    BaseAnimation's weight is not changed but still keyed; the kit's BaseAnimation weight is always 1.0 (strip
    influence 1), so it gets a key of 1.0 (no effect, like Maya's). Returns the keyed layers."""
    frame = scene.frame_current if frame is None else frame
    done = []
    for name in names:
        i = _index_of(scene, name)
        if i is None:
            continue
        e = al.layers(scene)[i]
        value = 1.0 if name == al.BASE else (e.weight if weight is None else weight)
        if name != al.BASE and abs(e.weight - value) > 1e-9:
            e.weight = value                     # its update writes the strips (anim_layers.sync)
        for ob in al.members(scene, name):
            st = al._strip(al.tracks(ob)[name])
            fc = al.weight_curve(st)
            if fc is None:
                continue
            kp = fc.keyframe_points.insert(frame, value)
            kp.interpolation = 'BEZIER'
            kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'
            fc.update()
            ob.update_tag(refresh={'TIME'})
        done.append(name)
    return done


# --- operators -------------------------------------------------------------------------------------------------

def _names(scene, layer=""):
    """The layers a command acts on: Maya's selected layers in stack order, or one ``layer``
    (the layer row's right-click menu on a row that isn't selected acts on that row only)."""
    if layer:
        return [layer] if _index_of(scene, layer) is not None else []
    return [e.name for e in al.selected_layers(scene)]


def base_selected(scene):
    """BaseAnimation is among the selected layers: Maya greys the Layers menu items listed in GREY_WITH_BASE."""
    return al.BASE in _names(scene)


LAYER_PROP = dict(options={'SKIP_SAVE', 'HIDDEN'}, description="Act on this layer only (layer right-click menu)")


class ALLSET_OT_anim_layer_extract(bpy.types.Operator):
    """Move the selected objects' animation out of the selected layers into new layers (Maya Extract Selected
    Objects; from BaseAnimation: Extract Non-Layered Animation)"""
    bl_idname = "allset.anim_layer_extract"
    bl_label = "Extract Selected Objects"
    bl_options = {'UNDO'}

    base: BoolProperty(options={'SKIP_SAVE'}, description="Extract the non-layered (BaseAnimation) animation")
    all_objects: BoolProperty(options={'SKIP_SAVE'}, description="Every animated object, not the selection")
    layer: StringProperty(**LAYER_PROP)

    def execute(self, context):
        scene = context.scene
        al.ensure_list(scene)
        if self.all_objects:
            obs = [ob for ob in scene.objects if ob.animation_data is not None and
                   (ob.animation_data.action is not None or al.has_layers(ob))]
        else:
            obs = al._layer_objects(context)
        if not obs and (self.base or self.all_objects):
            self.report({'WARNING'}, "Select objects to extract")
            return {'CANCELLED'}
        for name in ([al.BASE] if self.base or self.all_objects else _names(scene, self.layer)):
            extract(scene, obs, name)
        return {'FINISHED'}


class ALLSET_OT_anim_layer_duplicate(bpy.types.Operator):
    """Copy the selected layers with their members and keys, right above them (Maya Duplicate Layer)"""
    bl_idname = "allset.anim_layer_duplicate"
    bl_label = "Duplicate Layer"
    bl_options = {'UNDO'}

    no_animation: BoolProperty(options={'SKIP_SAVE'}, description="Copy members and settings, not the keys")
    layer: StringProperty(**LAYER_PROP)

    def execute(self, context):
        scene = context.scene
        for name in _names(scene, self.layer):
            duplicate(scene, name, with_curves=not self.no_animation)
        return {'FINISHED'}


class ALLSET_OT_anim_layer_empty(bpy.types.Operator):
    """Remove every attribute (member) and its keys from the selected layers (Maya Layers > Empty)"""
    bl_idname = "allset.anim_layer_empty"
    bl_label = "Empty"
    bl_options = {'UNDO'}

    layer: StringProperty(**LAYER_PROP)

    def execute(self, context):
        names = [n for n in _names(context.scene, self.layer) if n != al.BASE]
        if not names:
            self.report({'WARNING'}, "Select an animation layer")
            return {'CANCELLED'}
        for name in names:
            empty(context.scene, name)
        return {'FINISHED'}


class ALLSET_OT_anim_layer_delete_empty(bpy.types.Operator):
    """Delete every animation layer without members (Maya Delete Empty Layers)"""
    bl_idname = "allset.anim_layer_delete_empty"
    bl_label = "Delete Empty Layers"
    bl_options = {'UNDO'}

    def execute(self, context):
        gone, kept = delete_empty(context.scene)
        if kept and gone:          # Maya prints the kept ones when some layer was deleted
            self.report({'WARNING'}, "; ".join(NOT_EMPTY.format(n) for n in kept))
        return {'FINISHED'}


class ALLSET_OT_anim_layer_key_weight(bpy.types.Operator):
    """Set the selected layers' weight and key it at the current time (Maya Zero Weight and Key Layer / Set Weight
    to 1.0 and Key Layer; the Weight row's K button keys the current weight)"""
    bl_idname = "allset.anim_layer_key_weight"
    bl_label = "Key Layer Weight"
    bl_options = {'UNDO'}

    weight: FloatProperty(default=0.0, min=0.0, max=1.0, options={'SKIP_SAVE'})
    current: BoolProperty(options={'SKIP_SAVE'}, description="Key the current weight (Maya's K button)")
    layer: StringProperty(**LAYER_PROP)

    @classmethod
    def description(cls, context, props):
        if props.current:
            return "Key the layer weight"
        return "Set Weight to 1.0 and Key Layer" if props.weight >= 1.0 else "Zero Weight and Key Layer"

    def execute(self, context):
        # Maya: no layer selected = nothing; the kit always has a selected layer
        key_weight(context.scene, _names(context.scene, self.layer), None if self.current else self.weight)
        return {'FINISHED'}


classes = (ALLSET_OT_anim_layer_extract, ALLSET_OT_anim_layer_duplicate, ALLSET_OT_anim_layer_empty,
           ALLSET_OT_anim_layer_delete_empty, ALLSET_OT_anim_layer_key_weight)
