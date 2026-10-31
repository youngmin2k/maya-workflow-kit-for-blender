# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya ghosting (Visualize > Ghost Selected / Unghost Selected / Unghost All / Open Ghosting Editor).

Maya 2022 rules:
- Ghost Selected turns ``ghosting`` on for the selection and, with Include Hierarchy (factory on), everything under
  it; Unghost Selected / Unghost All turn it off. Each ghosted node carries its own settings, copied from the
  Ghosting Editor's values when it was ghosted (an editor change applies to every current ghost).
- Factory settings: mode Pre And Post Frames, Pre Frames 3, Post Frames 3, Step: 1 (presets 1s / 2s / 4s / 5s / 10s
  = Step: 1 / 2 / 4 / 5 / 10, Custom = own pre / post / step), Pre Frame Color (0.447, 1, 1), Post Frame Color
  (0.878, 0.678, 0.663), Near Opacity 0.5, Far Opacity 0.15.
- Frames (``cmds.ghosting(query=True, frames=True)``): t − k·step / t + k·step for k = 1 .. pre / post, not clipped to
  the playback range; Pre And Post Keyframes = the pre / post nearest keys before / after t (any key, also outside the
  range); All Keyframes = every key in the playback range; Custom Frames = the listed frames as they are.
- Look: each ghost is the object's mesh at that frame, drawn in the side's colour with opacity
  near + (far − near)·(k − 1)/(n − 1) for the k-th of n ghosts on that side (wireframe alpha 127 / 83 / 38 for
  k = 1 / 2 / 3). Shaded ghosts blend their front and back faces (alpha 191 / 139 / 71 = 1 − (1 − a)²), so the kit
  draws every triangle, both faces, without depth writes. Maya's colours live in its rendering space (ACEScg, colour
  management on by default): the kit converts them to linear Rec.709 and scales by GHOST_GAIN / WIRE_GAIN, fitted
  to look right over the #5c5c5c background.

Kit: ghost settings = ``Object.allset_ghost`` (Maya's per-node attributes); geometry per (object, absolute frame) is
cached in world space — it stays valid when the current frame moves. Missing frames are sampled by a timer with
``scene.frame_set`` (not while playing or dragging a transform); a depsgraph update that moves / reshapes a ghosted
object (or its parents) or edits an Action drops the cache.
"""

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, StringProperty

GEOMETRY = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}
MODES = ("Pre And Post Frames", "Pre Frames", "Post Frames", "Custom Frames", "Pre And Post Keyframes",
         "All Keyframes")                                  # ghostingMode enum
MODE_IDS = ("PRE_POST", "PRE", "POST", "CUSTOM", "KEYS_PRE_POST", "KEYS_ALL")
PRESETS = ("1s", "2s", "4s", "5s", "10s", "Custom")
PRE_COLOR = (0.447, 1.0, 1.0)                              # ghostColorPre factory
POST_COLOR = (0.878, 0.678, 0.663)                         # ghostColorPost factory
NEAR, FAR = 0.5, 0.15                                      # ghostNearOpacity / ghostFarOpacity factory
# Maya's ghosting command error when nothing selected can be ghosted
NOTHING_TO_GHOST = "Nothing selected can be ghosted using the current settings."
FACTORY = {"hierarchy": True, "mode": MODES[0], "preset": "1s", "custom_pre": 3, "custom_post": 3, "custom_step": 1,
           "custom_frames": "", "color_pre": PRE_COLOR, "color_post": POST_COLOR, "near_opacity": NEAR,
           "far_opacity": FAR}
EDITOR_KEY = "ghosting_editor"                             # option_windows key of the Ghosting Editor
# ACEScg (AP1) -> linear Rec.709, Bradford D60 -> D65 (the matrix OCIO's ACES configs use)
AP1_TO_709 = ((1.70505, -0.62179, -0.08326), (-0.13026, 1.14080, -0.01055), (-0.02400, -0.12897, 1.15297))
GHOST_GAIN = 0.34      # shaded: fitted to Maya's ghost colours (front faces)
WIRE_GAIN = 0.78       # wireframe: fitted to Maya's wireframe ghost alpha / colour
DEPTH_BIAS = 2e-5

_geom = {}             # (object session_uid, frame) -> (tri positions, tri normals, edge positions) numpy float32
_batches = {}          # same key -> (tri batch, edge batch)
_handle = []
_shader = []
_wire_shader = []


# --- pure rules ---------------------------------------------------------------------------------------------------

def preset_steps(values):
    """(pre frames, post frames, step) of the editor values: a preset Ns = (3, 3, N), Custom = its own numbers."""
    preset = values.get("preset", "1s")
    if preset == "Custom":
        return int(values.get("custom_pre", 3)), int(values.get("custom_post", 3)), max(1, int(values.get("custom_step", 1)))
    return 3, 3, int(preset[:-1])


def parse_frames(text):
    """'3, 7, 15' -> [3.0, 7.0, 15.0] (Maya's Custom Frames field: frame numbers separated by commas)."""
    out = []
    for part in (text or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(float(part))
        except ValueError:
            pass
    return sorted(set(out))


def ghost_frames(t, mode, pre=3, post=3, step=1, custom=(), keys=(), play_range=(1, 24)):
    """[(frame, side, k, n)]: side 'pre' / 'post', k-th of n ghosts on that side counted from the current frame
    (as Maya). The current frame itself never gets a ghost."""
    step = max(1, step)
    if mode == "Pre And Post Frames":
        before = [t - k * step for k in range(1, pre + 1)]
        after = [t + k * step for k in range(1, post + 1)]
    elif mode == "Pre Frames":
        before, after = [t - k * step for k in range(1, pre + 1)], []
    elif mode == "Post Frames":
        before, after = [], [t + k * step for k in range(1, post + 1)]
    elif mode == "Custom Frames":
        frames = sorted(set(custom))
        before = sorted((f for f in frames if f < t), reverse=True)
        after = [f for f in frames if f > t]
    elif mode == "Pre And Post Keyframes":
        ks = sorted(set(keys))
        before = sorted((f for f in ks if f < t), reverse=True)[:pre]
        after = [f for f in ks if f > t][:post]
    else:  # All Keyframes: every key in the playback range
        ks = sorted(set(f for f in keys if play_range[0] - 1e-6 <= f <= play_range[1] + 1e-6))
        before = sorted((f for f in ks if f < t), reverse=True)
        after = [f for f in ks if f > t]
    out = [(f, "pre", k, len(before)) for k, f in enumerate(before, 1)]
    out += [(f, "post", k, len(after)) for k, f in enumerate(after, 1)]
    return out


def opacity(k, n, near=NEAR, far=FAR):
    """Opacity of the k-th of n ghosts on one side: near for the closest, far for the farthest, linear between."""
    if n <= 1:
        return near
    return near + (far - near) * (k - 1) / (n - 1)


def to_linear(maya_rgb, gain):
    """A Maya ghost colour (rendering space ACEScg) -> linear Rec.709 RGB scaled by the fitted gain."""
    r, g, b = maya_rgb
    return tuple(max(0.0, (m[0] * r + m[1] * g + m[2] * b) * gain) for m in AP1_TO_709)


# --- settings -----------------------------------------------------------------------------------------------------

def editor_values():
    """The Ghosting Editor's saved values over the default ones (like Maya) (Ghost Selected uses them)."""
    from ..operators import option_windows
    values = dict(FACTORY)
    for k, v in (option_windows.saved(EDITOR_KEY) or {}).items():
        if k in values:
            values[k] = tuple(v) if isinstance(values[k], tuple) else v
    return values


class ALLSET_PG_ghost(bpy.types.PropertyGroup):
    """Maya's per-node ghosting attributes (ghosting, ghostingMode, ghostPreFrames ...)."""
    enabled: BoolProperty(name="Ghosting", default=False, update=lambda s, c: _changed())
    mode: EnumProperty(name="Ghosting Mode", items=[(i, n, "") for i, n in zip(MODE_IDS, MODES)], default="PRE_POST",
                       update=lambda s, c: _changed())
    pre_frames: IntProperty(name="Pre Frames", default=3, min=0, soft_max=20, update=lambda s, c: _changed())
    post_frames: IntProperty(name="Post Frames", default=3, min=0, soft_max=20, update=lambda s, c: _changed())
    step: IntProperty(name="Step", default=1, min=1, soft_max=20, update=lambda s, c: _changed())
    custom_frames: StringProperty(name="Custom Frames", default="", update=lambda s, c: _changed())
    color_pre: FloatVectorProperty(name="Pre Frame Color", size=3, subtype='COLOR', min=0.0, max=1.0,
                                   default=PRE_COLOR, update=lambda s, c: _changed())
    color_post: FloatVectorProperty(name="Post Frame Color", size=3, subtype='COLOR', min=0.0, max=1.0,
                                    default=POST_COLOR, update=lambda s, c: _changed())
    near_opacity: FloatProperty(name="Near Opacity", default=NEAR, min=0.0, max=1.0, update=lambda s, c: _changed())
    far_opacity: FloatProperty(name="Far Opacity", default=FAR, min=0.0, max=1.0, update=lambda s, c: _changed())


def apply_values(ob, values, enable=None):
    """Copy Ghosting Editor values onto one object's ghost settings."""
    g = ob.allset_ghost
    pre, post, step = preset_steps(values)
    g.mode = MODE_IDS[MODES.index(values["mode"])] if values["mode"] in MODES else "PRE_POST"
    g.pre_frames, g.post_frames, g.step = pre, post, step
    g.custom_frames = values.get("custom_frames", "")
    g.color_pre, g.color_post = tuple(values["color_pre"]), tuple(values["color_post"])
    g.near_opacity, g.far_opacity = values["near_opacity"], values["far_opacity"]
    if enable is not None:
        g.enabled = enable


def with_hierarchy(objects, hierarchy=True):
    out, seen = [], set()
    for ob in objects:
        for o in [ob] + (list(ob.children_recursive) if hierarchy else []):
            if o.session_uid not in seen:
                seen.add(o.session_uid)
                out.append(o)
    return out


def ghost(objects, values=None):
    """Maya Ghost Selected. Returns the ghosted objects."""
    values = values or editor_values()
    obs = with_hierarchy(objects, values.get("hierarchy", True))
    for ob in obs:
        apply_values(ob, values, enable=True)
    return obs


def unghost(objects, hierarchy=None):
    """Maya Unghost Selected."""
    if hierarchy is None:
        hierarchy = editor_values().get("hierarchy", True)
    obs = with_hierarchy(objects, hierarchy)
    for ob in obs:
        if ob.allset_ghost.enabled:
            ob.allset_ghost.enabled = False
    return obs


def unghost_all():
    out = []
    for ob in bpy.data.objects:
        if ob.allset_ghost.enabled:
            ob.allset_ghost.enabled = False
            out.append(ob)
    return out


def ghosted(scene):
    return [ob for ob in scene.objects if ob.allset_ghost.enabled]


def apply_to_all(scene, values):
    """Ghosting Editor change: every current ghost takes the editor's display values."""
    for ob in ghosted(scene):
        apply_values(ob, values)


def keys_of(ob):
    """Key frames of the object and the DAG hierarchy above it (Maya keyframe modes)."""
    from .. import compat
    out = set()
    o = ob
    while o is not None:
        for fc in compat.id_fcurves(o):
            out.update(round(kp.co[0], 6) for kp in fc.keyframe_points)
        o = o.parent
    return sorted(out)


def frames_for(ob, scene):
    """[(frame, side, k, n)] of one ghosted object at the scene's current frame."""
    from ..operators.playblast import playback_range
    g = ob.allset_ghost
    t = scene.frame_current + scene.frame_subframe
    mode = MODES[MODE_IDS.index(g.mode)]
    keys = keys_of(ob) if mode in ("Pre And Post Keyframes", "All Keyframes") else ()
    return ghost_frames(t, mode, g.pre_frames, g.post_frames, g.step, parse_frames(g.custom_frames), keys,
                        playback_range(scene))


# --- geometry cache -----------------------------------------------------------------------------------------------

def world_geometry(ob, depsgraph):
    """(triangle corner positions (3T, 3), corner normals (3T, 3), edge end positions (2E, 3)), world space."""
    import numpy as np
    ev = ob.evaluated_get(depsgraph)
    if ob.type == 'MESH':
        me, temp = ev.data, False
    else:
        me, temp = ev.to_mesh(), True
    try:
        me.calc_loop_triangles()
        n_v = len(me.vertices)
        co = np.empty(n_v * 3, np.float32)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        tris = np.empty(len(me.loop_triangles) * 3, np.int32)
        me.loop_triangles.foreach_get("vertices", tris)
        nrm = np.empty(len(me.loop_triangles) * 3, np.float32)
        me.loop_triangles.foreach_get("normal", nrm)
        ed = np.empty(len(me.edges) * 2, np.int32)
        me.edges.foreach_get("vertices", ed)
    finally:
        if temp:
            ev.to_mesh_clear()
    mw = np.array(ev.matrix_world, np.float32)
    world = co @ mw[:3, :3].T + mw[:3, 3]
    nmat = np.linalg.inv(mw[:3, :3]).T if abs(np.linalg.det(mw[:3, :3])) > 1e-12 else mw[:3, :3]
    fn = nrm.reshape(-1, 3) @ nmat.T
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    return (world[tris].astype(np.float32), np.repeat(fn, 3, axis=0).astype(np.float32),
            world[ed].astype(np.float32))


def needed(scene):
    """{(uid, frame)} the current frame's ghosts need, and {uid: object}."""
    want, obs = set(), {}
    for ob in ghosted(scene):
        if ob.type not in GEOMETRY:
            continue
        obs[ob.session_uid] = ob
        for f, *_rest in frames_for(ob, scene):
            want.add((ob.session_uid, round(f, 6)))
    return want, obs


def fill(context, want=None):
    """Sample every missing (object, frame) of the current ghosts (frame_set loop, the frame restored)."""
    from ..operators import anim_snapshot
    scene = context.scene
    if want is None:
        want, obs = needed(scene)
    else:
        obs = {ob.session_uid: ob for ob in ghosted(scene)}
    missing = sorted(k for k in want if k not in _geom and k[0] in obs)
    if not missing:
        return 0
    frames = sorted({f for _uid, f in missing})
    keep = (scene.frame_current, scene.frame_subframe)
    anim_snapshot._busy.append(True)
    try:
        for f in frames:
            whole = int(f // 1)
            scene.frame_set(whole, subframe=f - whole)
            dg = context.evaluated_depsgraph_get()
            for uid, ff in missing:
                if ff == f:
                    _geom[(uid, f)] = world_geometry(obs[uid], dg)
    finally:
        scene.frame_set(keep[0], subframe=keep[1])
        anim_snapshot._busy.pop()
    return len(missing)


def drop(uids=None):
    """Forget cached ghosts (of ``uids`` only, else all)."""
    if uids is None:
        _geom.clear()
        _batches.clear()
        return
    for key in [k for k in _geom if k[0] in uids]:
        _geom.pop(key, None)
        _batches.pop(key, None)


# #191: "does any object of this scene ghost?" per scene pointer, so a frame change doesn't walk every
# object; dropped when a ghost setting changes, on undo / redo / load and when objects are added or removed
_any_ghost = {}


def _ghosting_in(scene):
    key = scene.as_pointer()
    v = _any_ghost.get(key)
    if v is None:
        v = _any_ghost[key] = any(ob.allset_ghost.enabled for ob in scene.objects)
    return v


def _changed():
    """A ghost setting changed: redraw, sample what's missing."""
    _any_ghost.clear()
    _schedule()
    _redraw()


def _redraw():
    wm = bpy.context.window_manager
    for win in wm.windows if wm else ():
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _schedule(delay=0.05):
    if not bpy.app.timers.is_registered(_fill_tick):
        bpy.app.timers.register(_fill_tick, first_interval=delay)


def _fill_tick():
    from ..operators.anim_snapshot import _transforming
    context = bpy.context
    scene = getattr(context, "scene", None)
    if scene is None:
        return None
    screen = getattr(context, "screen", None)
    if (screen is not None and screen.is_animation_playing) or _transforming():
        return 0.3
    try:
        if fill(context):
            _redraw()
    except (RuntimeError, ReferenceError):
        pass
    return None


# --- drawing ------------------------------------------------------------------------------------------------------

def _sh():
    if not _shader:
        import gpu
        info = gpu.types.GPUShaderCreateInfo()
        info.push_constant('MAT4', 'vp')
        info.push_constant('VEC4', 'color')
        info.push_constant('VEC3', 'eye')
        info.push_constant('VEC3', 'viewdir')
        info.push_constant('FLOAT', 'ortho')
        info.push_constant('FLOAT', 'bias')
        info.vertex_in(0, 'VEC3', 'pos')
        info.vertex_in(1, 'VEC3', 'nrm')
        iface = gpu.types.GPUStageInterfaceInfo("allset_ghost_iface")
        iface.smooth('FLOAT', 'shade')
        info.vertex_out(iface)
        info.fragment_out(0, 'VEC4', 'fragColor')
        # The default light (like Maya) is a headlight: lambert on |n . v| (both faces lit, the back face too)
        info.vertex_source(
            "void main() {"
            " vec3 v = ortho > 0.5 ? viewdir : normalize(eye - pos);"
            " shade = abs(dot(normalize(nrm), v));"
            " gl_Position = vp * vec4(pos, 1.0); gl_Position.z -= bias * gl_Position.w; }")
        info.fragment_source("void main() { fragColor = vec4(color.rgb * shade, color.a); }")
        _shader.append(gpu.shader.create_from_info(info))
    return _shader[0]


def _wsh():
    if not _wire_shader:
        import gpu
        info = gpu.types.GPUShaderCreateInfo()
        info.push_constant('MAT4', 'vp')
        info.push_constant('VEC4', 'color')
        info.push_constant('FLOAT', 'bias')
        info.vertex_in(0, 'VEC3', 'pos')
        info.fragment_out(0, 'VEC4', 'fragColor')
        info.vertex_source("void main() { gl_Position = vp * vec4(pos, 1.0); gl_Position.z -= bias * gl_Position.w; }")
        info.fragment_source("void main() { fragColor = color; }")
        _wire_shader.append(gpu.shader.create_from_info(info))
    return _wire_shader[0]


def _batch(key):
    hit = _batches.get(key)
    if hit is None:
        from gpu_extras.batch import batch_for_shader
        tris, nrms, edges = _geom[key]
        tb = batch_for_shader(_sh(), 'TRIS', {"pos": tris, "nrm": nrms}) if len(tris) else None
        eb = batch_for_shader(_wsh(), 'LINES', {"pos": edges}) if len(edges) else None
        hit = _batches[key] = (tb, eb)
    return hit


def _draw():
    context = bpy.context
    space, rv3d = context.space_data, context.region_data
    if rv3d is None or space.shading.type == 'RENDERED' or not space.overlay.show_overlays:
        return
    scene = context.scene
    if not _ghosting_in(scene):          # #191: no walk over every object on each redraw
        return
    obs = [ob for ob in ghosted(scene) if ob.type in GEOMETRY and ob.visible_get()]
    if not obs:
        return
    import gpu
    from mathutils import Vector
    wire = space.shading.type == 'WIREFRAME'
    vp = rv3d.perspective_matrix
    inv = rv3d.view_matrix.inverted()
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.depth_mask_set(False)
    gpu.state.face_culling_set('NONE')
    sh = _wsh() if wire else _sh()
    sh.bind()
    sh.uniform_float("vp", vp)
    sh.uniform_float("bias", DEPTH_BIAS)
    if not wire:
        sh.uniform_float("eye", inv.translation)
        sh.uniform_float("viewdir", (inv.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized())
        sh.uniform_float("ortho", 0.0 if rv3d.is_perspective else 1.0)
    missing = False
    for ob in obs:
        g = ob.allset_ghost
        gain = WIRE_GAIN if wire else GHOST_GAIN
        cols = {"pre": to_linear(tuple(g.color_pre), gain), "post": to_linear(tuple(g.color_post), gain)}
        # farthest first, so the nearer ghosts blend over them
        for f, side, k, n in sorted(frames_for(ob, scene), key=lambda r: -r[2]):
            key = (ob.session_uid, round(f, 6))
            if key not in _geom:
                missing = True
                continue
            tb, eb = _batch(key)
            batch = eb if wire else tb
            if batch is None:
                continue
            sh.uniform_float("color", (*cols[side], opacity(k, n, g.near_opacity, g.far_opacity)))
            batch.draw(sh)
    gpu.state.depth_mask_set(False)
    gpu.state.depth_test_set('NONE')
    gpu.state.blend_set('NONE')
    if missing:
        _schedule()


def _callback():
    try:
        _draw()
    except Exception:  # never let a draw error repeat every frame
        import traceback
        traceback.print_exc()
        _remove_handler()


def _remove_handler():
    while _handle:
        bpy.types.SpaceView3D.draw_handler_remove(_handle.pop(), 'WINDOW')


@persistent
def _on_depsgraph(scene, depsgraph):
    """Drop the ghosts of objects that moved / changed shape (and of their ghosted descendants); an Action edit drops
    every ghost (any key change can move any ghost)."""
    from ..operators import anim_snapshot
    if depsgraph is not None and (depsgraph.id_type_updated('SCENE') or depsgraph.id_type_updated('COLLECTION')):
        _any_ghost.clear()
    if anim_snapshot._busy or not _geom:
        return
    uids = set()
    for update in depsgraph.updates:
        idb = update.id
        if isinstance(idb, bpy.types.Action):
            drop()
            _schedule(0.1)
            return
        if isinstance(idb, bpy.types.Object) and (update.is_updated_transform or update.is_updated_geometry):
            ob = idb.original
            uids.add(ob.session_uid)
            uids.update(c.session_uid for c in ob.children_recursive)
    hit = {k[0] for k in _geom} & uids
    if hit:
        drop(hit)
        _schedule(0.1)


@persistent
def _on_frame(scene, _depsgraph=None):
    from ..operators import anim_snapshot
    if anim_snapshot._busy:
        return
    if _ghosting_in(scene):
        _schedule(0.05)


@persistent
def _on_reload(*_args):
    _any_ghost.clear()
    drop()
    _schedule(0.2)


_HANDLERS = (("depsgraph_update_post", _on_depsgraph), ("frame_change_post", _on_frame), ("undo_post", _on_reload),
             ("redo_post", _on_reload), ("load_post", _on_reload))


# --- operators ----------------------------------------------------------------------------------------------------

class ALLSET_OT_ghost(bpy.types.Operator):
    """Maya Visualize ghosting: Ghost Selected / Unghost Selected / Unghost All"""
    bl_idname = "allset.ghost"
    bl_label = "Ghost Selected"
    bl_options = {'UNDO'}

    action: EnumProperty(items=[("GHOST", "Ghost Selected", ""), ("UNGHOST", "Unghost Selected", ""),
                                ("UNGHOST_ALL", "Unghost All", "")], default="GHOST", options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        return {"GHOST": "Ghost selected objects", "UNGHOST": "Remove ghosts from selected objects",
                "UNGHOST_ALL": "All object(s) to be unghosted."}[props.action]   # Maya's messages

    def execute(self, context):
        from .. import results
        if self.action == "GHOST":
            obs = ghost(list(context.selected_objects))
            if not obs:
                self.report({'ERROR'}, NOTHING_TO_GHOST)
                return {'CANCELLED'}
            _schedule()
            _redraw()
            results.result(self, "")    # Maya prints nothing on success
            return {'FINISHED'}
        elif self.action == "UNGHOST":
            obs = unghost(list(context.selected_objects))
        else:
            obs = unghost_all()
        _redraw()
        results.result(self, " ".join(ob.name for ob in obs))
        return {'FINISHED'}


classes = (ALLSET_PG_ghost, ALLSET_OT_ghost)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.allset_ghost = bpy.props.PointerProperty(type=ALLSET_PG_ghost)
    for name, fn in _HANDLERS:
        getattr(bpy.app.handlers, name).append(fn)
    _handle.append(bpy.types.SpaceView3D.draw_handler_add(_callback, (), 'WINDOW', 'POST_VIEW'))


def unregister():
    _remove_handler()
    if bpy.app.timers.is_registered(_fill_tick):
        bpy.app.timers.unregister(_fill_tick)
    for name, fn in _HANDLERS:
        lst = getattr(bpy.app.handlers, name)
        if fn in lst:
            lst.remove(fn)
    del bpy.types.Object.allset_ghost
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    drop()
    _shader.clear()
    _wire_shader.clear()
