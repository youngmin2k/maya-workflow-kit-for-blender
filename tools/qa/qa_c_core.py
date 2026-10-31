"""Release QA, activity C: toggle state invariants (UI state == Blender setting == effect), pairwise matrix and
seeded random walk. Engine module (no test_* functions); the runner modules are tools/qa/qa_toggles*.py.

Every toggle is read the way its draw code reads it and changed through the same kit function / operator the
button calls (called like a UI button: ``op('EXEC_DEFAULT', True, ...)`` = undo depth 0).

Oracles (qa_plan_240 3.1-1 internal consistency, 3.1-2 metamorphic):
  I1  ui == rna            after every action (per toggle ``check``)
  I2  click twice == same  (toggle / value back) for the toggle and for every other toggle's UI
  I3  a click changes only its own toggle's UI (model; cross-talk = S3)
  I4  save + reopen keeps every scene-stored toggle; Maya mode off / on keeps them
  I5  undo + redo returns the same scene-stored UI state
  E   effects measurable headless: auto key keys, layer mute / solo changes the evaluated value, Enable IK Solver
      writes the Ik Blend of the selected handle.
Not measurable headless (see tools/qa/qa_probe.py): transform.translate exec ignores grid /
increment snapping, proportional editing and mesh mirror in -b (no region) -> snap / soft select / symmetry effects
are checked through their Blender flags only.
"""

import json
import os
from importlib import import_module
from pathlib import Path

import bpy

import kit

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tmp" / "qa240"
OUT.mkdir(parents=True, exist_ok=True)
VERSION = ".".join(map(str, bpy.app.version))
TAG = os.environ.get("ALLSET_SANDBOX", "qa_c")


def m(name):
    return import_module(kit.MODULE + "." + name)


status_line = m("ui.status_line")
snap_align = m("operators.snap_align")
symmetry = m("operators.symmetry")
soft_select = m("operators.soft_select")
menu_sets = m("ui.menu_sets")
preferences = m("preferences")
ik_fk = m("operators.ik_fk")
anim_layers = m("operators.anim_layers")
auto_key = m("operators.auto_key")
switch = m("switch")

LAYER = "AnimLayer1"
SNAPS = ("GRID", "CURVE", "POINT", "LIVE")
KINDS = ("TRANSLATE", "ROTATE", "RESIZE")
STEP_MODES = ("OFF", "RELATIVE", "ABSOLUTE")
SYM_MODES = [x for x, _l in symmetry.MODES] + [p[0] for p in symmetry.PARTS]
SET_IDS = [s[0] for s in menu_sets.SET_ITEMS]


def C():
    return bpy.context


def ts():
    return C().scene.tool_settings


def op(idname, **kw):
    mod, name = idname.split(".")
    return getattr(getattr(bpy.ops, mod), name)('EXEC_DEFAULT', True, **kw)


# ---------------------------------------------------------------------------------------- scene

def build_scene(layer=True):
    """pCube1 (mesh), skeleton with an IK handle (empty ikHandle1), keyed pSphere1 in AnimLayer1."""
    if C().object is not None and C().object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    sc = C().scene
    sc.frame_set(1)
    me = bpy.data.meshes.new("pCubeShape1")
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    bm.to_mesh(me)
    bm.free()
    cube = bpy.data.objects.new("pCube1", me)
    sc.collection.objects.link(cube)
    # skeleton
    arm_data = bpy.data.armatures.new("skeleton1")
    arm = bpy.data.objects.new("joint1", arm_data)
    sc.collection.objects.link(arm)
    for o in sc.objects:
        o.select_set(False)
    arm.select_set(True)
    C().view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    prev = None
    for i in range(3):
        b = arm_data.edit_bones.new(f"joint{i + 1}")
        b.head = (0, 0, i * 2.0)
        b.tail = (0.3 if i == 1 else 0.0, 0, i * 2.0 + 2.0)
        if prev is not None:
            b.parent = prev
            b.use_connect = True
        prev = b
    bpy.ops.object.mode_set(mode='OBJECT')
    handle = bpy.data.objects.new("ikHandle1", None)
    sc.collection.objects.link(handle)
    handle.location = (0.5, 0, 5.5)
    con = arm.pose.bones["joint3"].constraints.new('IK')
    con.target = handle
    con.chain_count = 2
    # keyed object in a layer
    me2 = bpy.data.meshes.new("pSphereShape1")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(me2)
    bm.free()
    sph = bpy.data.objects.new("pSphere1", me2)
    sc.collection.objects.link(sph)
    sph.keyframe_insert("location", frame=1)
    sph.location.x = 2.0
    sph.keyframe_insert("location", frame=10)
    sph.location.x = 0.0
    for o in sc.objects:
        o.select_set(False)
    sph.select_set(True)
    C().view_layer.objects.active = sph
    if not layer:
        select_object("pCube1")
        return
    ls = anim_layers.layers(sc)
    while len(ls):
        ls.remove(0)
    op("allset.anim_layer_create", from_selected=True)
    e = anim_layers.layers(sc)[-1]
    if e.name != LAYER:
        e.name = LAYER      # names count one past the highest; force the harness name
    # layer adds +3 in x at frame 1 (result = base + layer)
    anim_layers.key(sph, "location", 0, frame=1, value=3.0, scene=sc, layer=e.name)
    sc.frame_set(1)
    select_object("pCube1")


def select_object(name):
    for o in C().scene.objects:
        o.select_set(False)
    ob = C().scene.objects[name]
    ob.select_set(True)
    C().view_layer.objects.active = ob
    return ob


def mode_switch(target):
    """'OBJECT' (pCube1 active), 'EDIT_MESH' (pCube1 edit), 'POSE' (joint1 pose, joint2 picked)."""
    ob = C().object
    if ob is not None and ob.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    if target == 'OBJECT':
        select_object("pCube1")
    elif target == 'EDIT_MESH':
        select_object("pCube1")
        bpy.ops.object.mode_set(mode='EDIT')
    elif target == 'POSE':
        arm = select_object("joint1")
        bpy.ops.object.mode_set(mode='POSE')
        try:
            from importlib import import_module as _im
            cb = _im(kit.MODULE + ".ui.channel_box")
            for pb in arm.pose.bones:
                cb.set_bone_selected(pb, pb.name == "joint2")
        except Exception:
            pass
    elif target == 'HANDLE':
        select_object("ikHandle1")
    C().view_layer.update()


def reset_toggles():
    t = ts()
    t.use_snap = False
    t.snap_elements = {'INCREMENT'}
    t.use_snap_translate = t.use_snap_rotate = t.use_snap_scale = True
    t.use_snap_grid_absolute = False
    C().scene.pop(snap_align.STEP_PROP, None)
    symmetry.set_mode(symmetry.state(C().scene), "OFF")
    symmetry.state(C().scene).last = "OBJECT_X"
    soft_select.set_on(False)
    C().scene.allset_auto_key = False
    preferences.get(C()).menu_set = SET_IDS[0]
    ik_fk._STATE["on"] = False
    for e in anim_layers.layers(C().scene):
        e.mute = e.solo = False


# ---------------------------------------------------------------------------------------- toggles

class Toggle:
    name = ""
    values = (False, True)
    scope = "scene"          # "scene" = saved / undone with the file; "session" = kit / preference state

    def ui(self):
        raise NotImplementedError

    def click(self, value=None):
        """Change through the UI path; ``value`` for multi-value toggles, None = flip."""
        raise NotImplementedError

    def check(self):
        """[] or a list of strings describing ui != Blender setting."""
        return []


class Snap(Toggle):
    def __init__(self, n):
        self.n = n
        self.name = f"snap_{n}"

    def ui(self):
        return status_line.snap_on(ts(), self.n)                  # draw_status_line depress=

    def click(self, value=None):
        if value is None or value != self.ui():
            op("allset.snap_toggle", snap=self.n)

    def check(self):
        t = ts()
        el = status_line._SNAP_ELEMENTS[self.n]
        real = t.use_snap and el <= set(t.snap_elements)
        out = []
        if real != self.ui():
            out.append(f"{self.name}: ui {self.ui()} but Blender use_snap={t.use_snap} elements={sorted(t.snap_elements)}")
        if self.ui() and not t.use_snap_translate:
            out.append(f"{self.name}: icon on but use_snap_translate off -> Move does not snap (#139 class)")
        return out


class Step(Toggle):
    values = STEP_MODES

    def __init__(self, kind):
        self.kind = kind
        self.name = f"step_{kind}"

    def ui(self):
        return snap_align.step_snap_mode(ts(), self.kind)        # tool_settings.py:394

    def click(self, value=None):
        if value is None:
            value = 'TOGGLE'
        op("allset.step_snap", kind=self.kind, mode=value)

    def check(self):
        t = ts()
        aff = getattr(t, snap_align.STEP_FLAGS[self.kind])
        stepping = t.use_snap and 'INCREMENT' in t.snap_elements and aff
        u = self.ui()
        out = []
        if u != 'OFF' and not stepping:
            out.append(f"{self.name}: shows {u} but Blender increment snap is not active for it")
        if u != 'OFF':
            # #153: Relative / Absolute is per tool; Blender's one flag takes this tool's mode when a
            # transform of the tool starts (snap_align.apply_tool) and the other tools keep showing their own
            others = {k: snap_align.step_snap_mode(t, k) for k in snap_align.STEP_FLAGS if k != self.kind}
            saved = t.use_snap_grid_absolute
            snap_align.apply_tool(t, self.kind)
            if t.use_snap_grid_absolute != (u == 'ABSOLUTE'):
                out.append(f"{self.name}: shows {u} but a {self.kind} transform starts with "
                           f"use_snap_grid_absolute={t.use_snap_grid_absolute}")
            changed = {k: v for k, v in others.items() if snap_align.step_snap_mode(t, k) != v}
            if changed:
                out.append(f"{self.name}: starting a {self.kind} transform changed other tools' Step Snap {changed}")
            t.use_snap_grid_absolute = saved
        if u == 'OFF' and stepping and not snap_align.other_snaps_on(t):
            out.append(f"{self.name}: shows Off but Blender steps this transform by the increment "
                       f"(use_snap, INCREMENT, {snap_align.STEP_FLAGS[self.kind]} all on)")
        return out


class Sym(Toggle):
    name = "symmetry"
    values = tuple(SYM_MODES)

    def ui(self):
        s = symmetry.state(C().scene)
        return (symmetry.mode_of(s), s.on, symmetry.label(s))          # draw_symmetry / _symmetry_text

    def click(self, value=None):
        op("allset.symmetry", mode=value or "TOGGLE")

    def check(self):
        s = symmetry.state(C().scene)
        out = []
        mode, on, text = self.ui()
        if (mode == "OFF") == on:
            out.append(f"symmetry: mode {mode} vs on={on}")
        if (text == "Symmetry: Off") != (mode == "OFF"):
            out.append(f"symmetry: text {text!r} vs mode {mode}")
        for ob in symmetry.edit_meshes(C().scene):
            want = symmetry.flags(ob, s)
            have = symmetry._mesh_flags(ob.data)
            if want != have:
                out.append(f"symmetry: {ob.name} in edit mode mirror flags {have} != {want} for {mode}")
        return out


class Soft(Toggle):
    name = "soft_select"
    scope = "session"

    def ui(self):
        return bool(C().scene.allset_soft_select)                 # modeling_toolkit.py:131

    def click(self, value=None):
        if value is not None and value == self.ui():
            return
        C().scene.allset_soft_select = not self.ui()              # checkbox click (Tool Settings / MTK)

    def check(self):
        out = []
        for sc in bpy.data.scenes:
            for f in soft_select.FLAGS:
                if getattr(sc.tool_settings, f) != self.ui():
                    out.append(f"soft_select: ui {self.ui()} but {sc.name}.{f}={getattr(sc.tool_settings, f)}")
        return out


class SoftKey(Soft):
    """The B tap path (taphold -> soft_select.toggle)."""
    name = "soft_select_key"

    def click(self, value=None):
        if value is not None and value == self.ui():
            return
        soft_select.toggle(C())


class AutoKey(Toggle):
    name = "auto_key"

    def ui(self):
        return bool(getattr(C().scene, "allset_auto_key", False))  # time_slider.py:137

    def click(self, value=None):
        if value is not None and value == self.ui():
            return
        C().scene.allset_auto_key = not self.ui()

    def check(self):
        return [] if auto_key.enabled(C().scene) == self.ui() else ["auto_key: enabled() != prop"]


class MenuSet(Toggle):
    name = "menu_set"
    values = tuple(SET_IDS)
    scope = "session"

    def ui(self):
        return preferences.get(C()).menu_set                      # status_line._menu_set_field

    def click(self, value=None):
        if value is None:
            i = SET_IDS.index(self.ui())
            value = SET_IDS[(i + 1) % len(SET_IDS)]
        op("allset.menu_set", set=value)

    def check(self):
        return [] if menu_sets.current_set(C()) == self.ui() else [
            f"menu_set: current_set {menu_sets.current_set(C())} != prefs {self.ui()}"]


class IkSolver(Toggle):
    name = "ik_solver"
    scope = "session"

    def ui(self):
        return bool(C().window_manager.allset_ik_solver)          # menu ("prop", ...) check item

    def click(self, value=None):
        if value is not None and value == self.ui():
            return
        found = ik_fk.ik_constraints(C())
        C().window_manager.allset_ik_solver = not self.ui()
        if found:
            want = 1.0 if self.ui() else 0.0
            for arm, pb, con in found:
                got = ik_fk.blend_of(con)
                if abs(got - want) > 1e-6:
                    raise Violation(f"ik_solver: check {self.ui()} but Ik Blend of {pb.name} = {got}")


class LayerFlag(Toggle):
    def __init__(self, flag):
        self.flag = flag
        self.name = f"layer_{flag}"

    def entry(self):
        return next((e for e in anim_layers.layers(C().scene) if e.name == LAYER), None)

    def ui(self):
        e = self.entry()
        return None if e is None else bool(getattr(e, self.flag))

    def click(self, value=None):
        e = self.entry()
        if e is None:
            return
        if value is not None and value == bool(getattr(e, self.flag)):
            return
        setattr(e, self.flag, not getattr(e, self.flag))

    def check(self):
        sc = C().scene
        ls = anim_layers.layers(sc)
        e = self.entry()
        if e is None:
            return []
        solo = {x.name for x in ls if x.solo and x.name != anim_layers.BASE}
        out = []
        for ob in anim_layers.members(sc, LAYER):
            tr = anim_layers.tracks(ob).get(LAYER)
            want = e.mute or (bool(solo) and LAYER not in solo)
            if tr is not None and tr.mute != want:
                out.append(f"layer: {ob.name} track mute {tr.mute} but layer mute={e.mute} solo={sorted(solo)}")
        return out


class Violation(Exception):
    pass


TOGGLES = [Snap(n) for n in SNAPS] + [Step(k) for k in KINDS] + [Sym(), Soft(), SoftKey(), AutoKey(), MenuSet(),
                                                                 IkSolver(), LayerFlag("mute"), LayerFlag("solo")]
BY_NAME = {t.name: t for t in TOGGLES}
UI_KEYS = [t for t in TOGGLES if t.name != "soft_select_key"]


def ui_state():
    return {t.name: t.ui() for t in UI_KEYS}


def scene_state():
    return {t.name: t.ui() for t in UI_KEYS if t.scope == "scene"}


def effects():
    """Effect checks measurable headless."""
    out = []
    sc = C().scene
    sph = sc.objects.get("pSphere1")
    e = BY_NAME["layer_mute"].entry()
    if sph is not None and e is not None and C().object is not None and C().object.mode == 'OBJECT':
        sc.frame_set(1)
        dg = C().evaluated_depsgraph_get()
        x = sph.evaluated_get(dg).matrix_world.translation.x
        muted = e.mute or (any(l.solo for l in anim_layers.layers(sc) if l.name != anim_layers.BASE) and not e.solo)
        want = 0.0 if muted else 3.0
        if abs(x - want) > 1e-4:
            out.append(f"layer effect: pSphere1 x at frame 1 = {x:.4f}, want {want} (mute={e.mute} solo={e.solo})")
    return out


def all_violations():
    out = []
    for t in UI_KEYS:
        try:
            out += t.check()
        except Exception as ex:
            out.append(f"{t.name}: check raised {ex!r}")
    out += effects()
    return out


# ---------------------------------------------------------------------------------------- actions

def save_reopen():
    path = str(OUT / f"c_{TAG}.blend")
    bpy.ops.wm.save_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)


def maya_off_on():
    switch.set_mode(False, layout=False)
    switch.set_mode(True, layout=False)
    bpy.ops.ed.undo_push(message="qa maya off/on")


def autokey_effect():
    """With Auto Key on, a changed keyed channel gets a key; off: none."""
    sc = C().scene
    sph = sc.objects.get("pSphere1")
    cube = sc.objects.get("pCube1")
    if cube is None or C().object is None or C().object.mode != 'OBJECT':
        return []
    # a plain keyed object (no layers): pCube1 keyed on z
    fc = kit.fcurves(cube).find("location", index=2) if cube.animation_data and cube.animation_data.action else None
    if fc is None:
        cube.keyframe_insert("location", index=2, frame=1)
        fc = kit.fcurves(cube).find("location", index=2)
    frame = 4
    sc.frame_set(frame)
    n0 = len(fc.keyframe_points)
    had = any(abs(k.co.x - frame) < 1e-6 for k in fc.keyframe_points)
    cube.location.z += 0.25
    C().view_layer.update()
    auto_key._flush()
    has = any(abs(k.co.x - frame) < 1e-6 for k in fc.keyframe_points)
    on = BY_NAME["auto_key"].ui()
    out = []
    if on and not has:
        out.append("auto_key effect: on, changed keyed channel got no key")
    if not on and has and not had:
        out.append("auto_key effect: off, but a key was set")
    # clean up
    for k in reversed(list(fc.keyframe_points)):
        if abs(k.co.x - frame) < 1e-6 and not had:
            fc.keyframe_points.remove(k)
    cube.location.z = fc.evaluate(frame)
    sc.frame_set(1)
    auto_key._pending.clear()
    bpy.ops.ed.undo_push(message="qa autokey effect")   # -b undo after unpushed data changes crashes Blender
    return out


def kit_traceback(tb_text):
    return ("allset" in tb_text and "tools\\qa" not in tb_text.splitlines()[-2:][0]) if tb_text else False


# ---------------------------------------------------------------------------------------- recording

def finding(fid, severity, repro, oracle, detail=""):
    rec = {"id": fid, "activity": "C", "severity": severity, "repro": repro, "oracle": oracle,
           "version": VERSION, "detail": detail}
    with open(OUT / "findings.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


def log(*a):
    print("QA_C", *a, flush=True)
