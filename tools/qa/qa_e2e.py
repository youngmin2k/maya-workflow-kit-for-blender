"""QA activity B: one scene through the whole Maya chain, headless, with metamorphic checkpoints.

    ALLSET_SANDBOX=qa_b python tests/run.py --no-build -k __none__ --extra tools/qa/qa_e2e.py
    ALLSET_SANDBOX=qa_b52 python tests/run.py --no-build -k __none__ --extra tools/qa/qa_e2e.py --blender <5.2 exe>

Stages (kit operators / functions, the way tests/test_step231..239 drive them):
  setup -> model (Create Cylinder, Extrude) -> UV (Automatic) -> rig (Joint Tool chain, Orient Joint, IK Handle,
  Orient constraint on a child joint, Bind Skin) -> anim (S on the IK handle / a control, Animation Layer + key,
  Set Driven Key) -> bake (Bake Simulation of the joints) -> export (Game Exporter 2 clips, kit FBX Export All)
  -> import (kit File > Import into a new file).
After every stage a state fingerprint is taken and these relations are checked:
  (a) ed.undo x k -> each step equals the fingerprint recorded before it; ed.redo x k -> back to the stage's end
  (b) save_mainfile + open_mainfile -> same fingerprint
  (c) Maya mode off -> on (switch.set_mode) -> same scene fingerprint (+ the Maya keymap items back)
  (d) FBX export -> import into a new file -> joint / object world positions within 1e-5 cm per frame
Results: tmp/qa240/qa_b_<sandbox>.json; mismatches -> tmp/qa240/findings.jsonl.
"""

import hashlib
import importlib.util
import math
import traceback
from importlib import import_module
from pathlib import Path

import bmesh
import bpy
from mathutils import Euler, Vector

import kit

_spec = importlib.util.spec_from_file_location("qa_common", Path(__file__).resolve().parent / "qa_common.py")
qa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qa)

units = import_module(kit.MODULE + ".operators.units")
joints = import_module(kit.MODULE + ".operators.joints")
skin = import_module(kit.MODULE + ".operators.skin")
al = import_module(kit.MODULE + ".operators.anim_layers")
driven_key = import_module(kit.MODULE + ".operators.driven_key")
bake_maya = import_module(kit.MODULE + ".operators.bake_maya")
ge = import_module(kit.MODULE + ".operators.game_exporter")
compat = import_module(kit.MODULE + ".compat")
cb = import_module(kit.MODULE + ".ui.channel_box")
switch = import_module(kit.MODULE + ".switch")

TAG = qa.env_tag()
WORK = qa.out_dir() / f"b_{TAG}"
WORK.mkdir(parents=True, exist_ok=True)
VERSION = f"Blender {bpy.app.version_string}, kit {qa.git_head()} (working tree, 0.9.0)"
FRAMES = (1, 7, 10, 15, 20)
NDEC = 4            # cm / radians rounding of fingerprints

RESULTS = {"version": VERSION, "sandbox": TAG, "checkpoints": [], "notes": []}
_chain = []          # fingerprints of the undo steps pushed since the last load: [base, first push, second push, ...]


# --- fingerprint ----------------------------------------------------------------------------------------------

def _r(x, n=NDEC):
    v = round(float(x), n)
    return 0.0 if v == 0 else v


def _vec(v, k=1.0):
    return [_r(c / k) for c in v]


def _mat(m, k):
    return [_vec(m.to_translation(), k), [_r(c, 5) for c in m.to_quaternion()], _vec(m.to_scale())]


def _h(obj):
    return hashlib.sha1(repr(obj).encode()).hexdigest()[:12]


def _idval(v):
    if hasattr(v, "to_dict"):
        return {k: _idval(x) for k, x in v.to_dict().items()}
    if hasattr(v, "to_list"):
        return [_idval(x) for x in v.to_list()]
    if isinstance(v, dict):
        return {k: _idval(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_idval(x) for x in v]
    if isinstance(v, float):
        return round(v, 6)
    if hasattr(v, "name") and hasattr(v, "bl_rna"):
        return f"<{v.bl_rna.identifier} {v.name}>"
    return v if isinstance(v, (int, str, bool, type(None))) else repr(v)


def _kit_props(idb):
    out = {}
    try:
        keys = list(idb.keys())
    except Exception:
        return out
    for key in keys:
        if key.startswith("allset") or key.startswith("_allset"):
            try:
                out[key] = _idval(idb[key])
            except Exception as ex:
                out[key] = f"<unreadable {ex}>"
    return out


def _fcurve(fc):
    return {"keys": [[_r(kp.co[0], 3), _r(kp.co[1], 5)] for kp in fc.keyframe_points],
            "interp": [kp.interpolation for kp in fc.keyframe_points][:3], "mute": fc.mute,
            "mods": [m.type for m in fc.modifiers]}


def _anim(idb):
    ad = getattr(idb, "animation_data", None)
    if ad is None:
        return None
    out = {"action": ad.action.name if ad.action else None, "influence": _r(getattr(ad, "action_influence", 1.0))}
    try:
        out["fcurves"] = {f"{fc.data_path}[{fc.array_index}]": _fcurve(fc) for fc in compat.id_fcurves(idb)}
    except Exception as ex:
        out["fcurves"] = f"<error {ex}>"
    out["drivers"] = {f"{d.data_path}[{d.array_index}]": {
        "expr": d.driver.expression, "type": d.driver.type,
        "vars": [(v.name, v.type, [(t.id.name if t.id else None, t.data_path, getattr(t, "transform_type", ""))
                                    for t in v.targets]) for v in d.driver.variables],
        **_fcurve(d)} for d in ad.drivers}
    out["nla"] = [{"name": t.name, "mute": t.mute, "strips": [
        (s.name, s.action.name if s.action else None, s.blend_type, _r(s.influence), _r(s.frame_start),
         _r(s.frame_end), s.mute) for s in t.strips]} for t in ad.nla_tracks]
    # every action's curves (layer actions not active right now)
    return out


def _mesh(me, k):
    d = {"verts": len(me.vertices), "faces": len(me.polygons),
         "co": _h([_vec(v.co, k) for v in me.vertices]),
         "uv": {uv.name: _h([_vec(l.uv) for l in uv.data]) for uv in me.uv_layers},
         "attrs": sorted(a.name for a in me.attributes if not a.name.startswith(".")),
         "materials": [m.name if m else None for m in me.materials]}
    if me.shape_keys:
        d["shape_keys"] = {kb.name: [_r(kb.value), _h([_vec(p.co, k) for p in kb.data])]
                           for kb in me.shape_keys.key_blocks}
    return d


def _weights(ob):
    names = {vg.index: vg.name for vg in ob.vertex_groups}
    per = {}
    for v in ob.data.vertices:
        for g in v.groups:
            per.setdefault(names.get(g.group, g.group), []).append((v.index, _r(g.weight, 5)))
    return {n: _h(w) for n, w in sorted(per.items())}


def scene_fp(frames=FRAMES):
    sc = bpy.context.scene
    k = units.maya_unit(sc)
    fp = {"scene": {"name": sc.name, "range": [sc.frame_start, sc.frame_end], "frame": sc.frame_current,
                    "units": [sc.unit_settings.system, sc.unit_settings.length_unit,
                              _r(sc.unit_settings.scale_length, 6)],
                    "kit": _kit_props(sc), "camera": sc.camera.name if sc.camera else None,
                    "keying_sets": [ks.bl_label for ks in sc.keying_sets]},
          "objects": {}, "eval": {}, "actions": {}}
    for ob in sorted(sc.objects, key=lambda o: o.name):
        d = {"type": ob.type, "parent": ob.parent.name if ob.parent else None, "parent_type": ob.parent_type,
             "parent_bone": ob.parent_bone, "basis": _mat(ob.matrix_basis, k),
             "delta": [_vec(ob.delta_location, k), _vec(ob.delta_rotation_euler), _vec(ob.delta_scale)],
             "rot_mode": ob.rotation_mode, "hide": [ob.hide_viewport, ob.hide_render, ob.hide_get()],
             "modifiers": [(m.name, m.type, getattr(getattr(m, "object", None), "name", None)) for m in ob.modifiers],
             "constraints": [(c.name, c.type, getattr(getattr(c, "target", None), "name", None),
                              getattr(c, "subtarget", ""), _r(c.influence), c.mute) for c in ob.constraints],
             "kit": _kit_props(ob), "anim": _anim(ob)}
        if ob.type == 'MESH':
            d["mesh"] = _mesh(ob.data, k)
            d["weights"] = _weights(ob)
            d["vgroups"] = [(vg.name, vg.lock_weight) for vg in ob.vertex_groups]
        if ob.type == 'ARMATURE':
            d["bones"] = {b.name: {"head": _vec(b.head_local, k), "tail": _vec(b.tail_local, k), "roll_m": _h(
                [[_r(c, 5) for c in row] for row in b.matrix_local]), "parent": b.parent.name if b.parent else None,
                "connect": b.use_connect, "kit": _kit_props(b)} for b in ob.data.bones}
            d["pose"] = {pb.name: {"basis": _mat(pb.matrix_basis, k), "rot_mode": pb.rotation_mode,
                                   "kit": _kit_props(pb),
                                   "constraints": [(c.name, c.type, getattr(getattr(c, "target", None), "name", None),
                                                    getattr(c, "subtarget", ""), _r(c.influence), c.mute,
                                                    getattr(c, "chain_count", None))
                                                   for c in pb.constraints]} for pb in ob.pose.bones}
            d["data_anim"] = _anim(ob.data)
        if ob.type == 'EMPTY':
            d["empty"] = [ob.empty_display_type, _r(ob.empty_display_size / k)]
        fp["objects"][ob.name] = d
    for act in sorted(bpy.data.actions, key=lambda a: a.name):
        try:
            curves = [fc for owner in compat.fcurve_owners(act) for fc in owner.fcurves]
        except Exception:
            curves = list(getattr(act, "fcurves", []))
        fp["actions"][act.name] = {"users": act.users,
                                   "curves": _h(sorted((fc.data_path, fc.array_index, str(_fcurve(fc)))
                                                       for fc in curves))}
    keep = sc.frame_current
    dg = bpy.context.evaluated_depsgraph_get
    for f in frames:
        sc.frame_set(f)
        ev = {}
        for ob in sorted(sc.objects, key=lambda o: o.name):
            e = {"world": _mat(ob.matrix_world, k)}
            if ob.type == 'ARMATURE':
                e["joints"] = {pb.name: _vec((ob.matrix_world @ pb.matrix).to_translation(), k)
                               for pb in ob.pose.bones}
            if ob.type == 'MESH':
                me = ob.evaluated_get(dg()).data
                e["verts"] = _h([_vec(ob.matrix_world @ v.co, k) for v in me.vertices])
            ev[ob.name] = e
        fp["eval"][str(f)] = ev
    sc.frame_set(keep)
    return fp


def env_fp():
    kcs = bpy.context.window_manager.keyconfigs
    return {"maya_mode": switch.is_on(), "registered": bool(switch._registered[0]),
            "active_keyconfig": kcs.active.name if kcs.active else None,
            "addon_items": sum(len(km.keymap_items) for km in (kcs.addon.keymaps if kcs.addon else ())),
            "addon_ops": sorted({kmi.idname for km in (kcs.addon.keymaps if kcs.addon else ())
                                 for kmi in km.keymap_items}),
            "active_items_off": sum(1 for km in kcs.active.keymaps for kmi in km.keymap_items if not kmi.active)}


def fingerprint():
    return {"scene": scene_fp(), "env": env_fp()}


def _flat(d, path="", out=None):
    out = {} if out is None else out
    if isinstance(d, dict):
        for k_, v in d.items():
            _flat(v, f"{path}/{k_}", out)
    else:
        out[path] = d
    return out


def diff(a, b, limit=25):
    fa, fb = _flat(a), _flat(b)
    keys = sorted(set(fa) | set(fb))
    out = [(k_, fa.get(k_, "<missing>"), fb.get(k_, "<missing>")) for k_ in keys if fa.get(k_, "<missing>")
           != fb.get(k_, "<missing>")]
    return out[:limit], len(out)


# --- checkpoint bookkeeping ------------------------------------------------------------------------------------

def record(stage, relation, ok, detail, severity="S2", by_design=None):
    rec = {"stage": stage, "relation": relation, "ok": ok, "detail": detail}
    if by_design:
        rec["by_design"] = by_design
    RESULTS["checkpoints"].append(rec)
    print(f"QA-B {'PASS' if ok else ('BY-DESIGN' if by_design else 'FAIL')} {stage} {relation}: "
          f"{str(detail)[:600]}", flush=True)
    if not ok and not by_design:
        qa.add_finding(f"B-{TAG}-{stage}-{relation}", "B", severity,
                       f"tools/qa/qa_e2e.py (ALLSET_SANDBOX={TAG}) stage {stage}: {relation}",
                       f"metamorphic {relation}: {str(detail)[:900]}", VERSION)
    qa.write_json(f"qa_b_{TAG}.json", RESULTS)


def push(label):
    bpy.ops.ed.undo_push(message=label)
    _chain.append((label, fingerprint()))


def reset_chain():
    _chain.clear()
    bpy.ops.ed.undo_push(message="base")
    _chain.append(("base", fingerprint()))


def _data_severity(d):
    """S1 when the mismatch is data (keys, weights, mesh, bones) missing, else S2."""
    txt = " ".join(p for p, _a, _b in d)
    return "S1" if any(s in txt for s in ("/fcurves", "/weights", "/mesh/", "/bones/", "<missing>", "/nla",
                                         "/drivers", "/shape_keys")) else "S2"


def check_undo(stage, k):
    """Undo the stage's k steps one at a time (each must equal the fingerprint before it), then redo them."""
    steps = _chain[-(k + 1):]
    if len(steps) < k + 1:
        record(stage, "undo_redo", False, f"only {len(steps)} chain entries for k={k}")
        return
    bad = []
    for i in range(k):
        bpy.ops.ed.undo()
        want_label, want = steps[-(i + 2)]
        got = fingerprint()
        d, n = diff(want["scene"], got["scene"])
        if n:
            bad.append({"after_undo": i + 1, "expected_state": want_label, "n_diff": n, "diff": d[:8]})
    for i in range(k):
        bpy.ops.ed.redo()
        want_label, want = steps[i + 1]
        got = fingerprint()
        d, n = diff(want["scene"], got["scene"])
        if n:
            bad.append({"after_redo": i + 1, "expected_state": want_label, "n_diff": n, "diff": d[:8]})
    sev = "S2"
    if bad:
        sev = _data_severity([x for b in bad for x in b["diff"]])
    record(stage, f"undo_redo_k{k}", not bad, bad or f"{k} undo + {k} redo steps matched", severity=sev)


def check_switch(stage):
    before = fingerprint()
    switch.set_mode(False, layout=False)
    off = fingerprint()
    d_off, n_off = diff(before["scene"], off["scene"])
    switch.set_mode(True, layout=False)
    after = fingerprint()
    d, n = diff(before["scene"], after["scene"])
    de, ne = diff(before["env"], after["env"])
    RESULTS["notes"].append({"stage": stage, "maya_off_env": off["env"], "maya_off_scene_diff": d_off[:10],
                             "maya_off_scene_ndiff": n_off})
    if n_off:
        print(f"QA-B NOTE {stage} Maya mode off changes the scene fingerprint ({n_off}): {d_off[:5]}", flush=True)
    record(stage, "switch_round_trip", not n and not ne,
           {"scene_diff": d[:10], "n": n, "env_diff": de} if (n or ne) else "scene + env equal after off -> on",
           severity=_data_severity(d) if n else "S2")
    core = {"allset.switch_mode", "allset.welcome", "allset.make_maya"}
    left = {o for o in off["env"]["addon_ops"] if o.startswith("allset.")} - core
    if left or off["env"]["maya_mode"]:
        record(stage, "switch_off_clean", False, {"off_env": off["env"]}, severity="S2")
    else:
        record(stage, "switch_off_clean", True, {"core_items_left": off["env"]["addon_ops"],
                                                 "n": off["env"]["addon_items"]})


def check_save_reopen(stage):
    before = fingerprint()
    path = str(WORK / f"{stage}.blend")
    bpy.ops.wm.save_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    after = fingerprint()
    d, n = diff(before["scene"], after["scene"])
    de, ne = diff(before["env"], after["env"])
    record(stage, "save_reopen", not n and not ne,
           {"scene_diff": d[:12], "n": n, "env_diff": de} if (n or ne) else "equal after save + open",
           severity=_data_severity(d) if n else "S2")
    reset_chain()
    return after


def checkpoints(stage, k):
    for fn, args in ((check_undo, (stage, k)), (check_switch, (stage,)), (check_save_reopen, (stage,))):
        try:
            fn(*args)
        except Exception:
            record(stage, fn.__name__, False, traceback.format_exc()[-1500:], severity="S1")
            try:
                if fn is check_switch and not switch.is_on():
                    switch.set_mode(True, layout=False)
            except Exception:
                pass


# --- scene helpers ---------------------------------------------------------------------------------------------

def k_():
    return units.maya_unit(bpy.context.scene)


def bl(p):
    """Maya Y-up cm -> Blender."""
    k = k_()
    return Vector((p[0], -p[2], p[1])) * k


def obj_mode():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def select_only(*obs, active=None):
    obj_mode()
    for o in bpy.context.scene.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = active or (obs[-1] if obs else None)


def O(name):
    return bpy.data.objects[name]


# --- stages ---------------------------------------------------------------------------------------------------

def stage_setup():
    sc = bpy.context.scene
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    sc.unit_settings.system, sc.unit_settings.length_unit = 'METRIC', 'CENTIMETERS'
    sc.unit_settings.scale_length = 0.01
    sc.frame_start, sc.frame_end = 1, 20
    sc.frame_set(1)
    bpy.ops.wm.save_mainfile(filepath=str(WORK / "empty_cm.blend"))     # the "new file" for the import stage
    reset_chain()


def stage_model():
    obj_mode()
    assert bpy.ops.allset.create(kind='CYLINDER') == {'FINISHED'}
    ob = bpy.context.active_object
    obj_mode()
    ob.name = "body"
    ob.scale = (1.0, 1.0, 2.0)            # a taller body to skin (Maya Scale Y 2)
    bpy.context.view_layer.update()
    push("create cylinder")
    select_only(ob)
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    for f in bm.faces:
        f.select_set(f.normal.z > 0.9)
    bmesh.update_edit_mesh(ob.data)
    res = bpy.ops.allset.extrude(local_translate_z=0.5)
    assert res == {'FINISHED'}, res
    obj_mode()
    push("extrude top")
    return 2


def stage_uv():
    select_only(O("body"))
    res = bpy.ops.allset.uv_automatic()
    assert res == {'FINISHED'}, res
    obj_mode()
    push("uv automatic")
    return 1


def stage_rig():
    sc = bpy.context.scene
    k = k_()
    select_only()
    ob = joints.new_skeleton(bpy.context)
    parent = None
    names = []
    for p in ((0, -2, 0), (0.4, 0, 0), (0, 2, 0), (0, 3, 0)):
        parent = joints.add_joint(ob, bl(p), parent, up=Vector((0, 0, 1)), length=0.5 * k)
        names.append(parent)
    joints.orient_new(ob, names)
    joints.finish(bpy.context, ob, names)
    obj_mode()
    arm_name = ob.name
    RESULTS["rig"] = {"armature": arm_name, "joints": names}
    push("joint tool")
    ob = O(arm_name)
    select_only(ob)
    bpy.ops.object.mode_set(mode='POSE')
    joints.orient(ob, [names[0]], "Y+", True)                  # Orient Joint (factory) on the chain
    obj_mode()
    push("orient joint")
    ob = O(arm_name)
    select_only(ob)
    handle = skin.create_ik(bpy.context, ob, (names[0], 'HEAD'), (names[2], 'HEAD'))
    assert handle is not None
    RESULTS["rig"]["ik"] = handle.name
    obj_mode()
    push("ik handle")
    ctrl = bpy.data.objects.new("ctrl1", None)
    sc.collection.objects.link(ctrl)
    ctrl.location = bl((2, 3, 0))
    ctrl.rotation_euler = Euler((0.0, 0.0, math.radians(20)))
    bpy.context.view_layer.update()
    ob = O(arm_name)
    obj_mode()
    for o in sc.objects:
        o.select_set(o in (ctrl, ob))
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='POSE')
    for pb in ob.pose.bones:
        cb.set_bone_selected(pb, pb.name == names[3])
    ob.data.bones.active = ob.data.bones[names[3]]
    res = bpy.ops.allset.constrain('EXEC_DEFAULT', type='COPY_ROTATION', maintain_offset='DEFAULT')
    assert res == {'FINISHED'}, res
    obj_mode()
    push("orient constraint on child joint")
    body, ob = O("body"), O(arm_name)
    select_only(body, ob, active=ob)
    skin.bind_skin(bpy.context, ob, [body])
    obj_mode()
    push("bind skin")
    return 5


def stage_anim():
    sc = bpy.context.scene
    rig = RESULTS["rig"]
    h = O(rig["ik"])
    base = h.location.copy()
    for f, off in ((1, (0, 0, 0)), (10, (1.5, -1.0, 0.5)), (20, (-1.0, -0.5, -0.5))):
        sc.frame_set(f)
        h = O(rig["ik"])
        h.location = base + bl(off)
        select_only(h)
        res = bpy.ops.allset.set_key()
        assert res == {'FINISHED'}, res
    push("S on ik handle")
    for f, deg in ((1, 20.0), (20, -40.0)):
        sc.frame_set(f)
        c = O("ctrl1")
        c.rotation_euler.z = math.radians(deg)
        select_only(c)
        assert bpy.ops.allset.set_key() == {'FINISHED'}
    push("S on ctrl1")
    select_only(O("ctrl1"))
    assert bpy.ops.allset.anim_layer_create(from_selected=True) == {'FINISHED'}
    layer = [e.name for e in al.layers(sc)]
    RESULTS["layers"] = layer
    sc.frame_set(10)
    assert al.key(O("ctrl1"), "rotation_euler", 0, frame=10, value=math.radians(15.0)) is not False
    push("anim layer + key")
    tgt = bpy.data.objects.new("sdkTarget", None)
    sc.collection.objects.link(tgt)
    c = O("ctrl1")
    for x, y in ((0.0, 0.0), (5.0, 3.0)):
        c.location.x = bl((2, 3, 0)).x + x * k_()
        tgt.location.z = y * k_()                 # Maya Translate Y
        driven_key.set_key(tgt, "ty", c, "tx")
    c.location.x = bl((2, 3, 0)).x
    bpy.context.view_layer.update()
    push("set driven key")
    return 4


def stage_bake():
    rig = RESULTS["rig"]
    ob = O(rig["armature"])
    select_only(ob)
    bpy.ops.object.mode_set(mode='POSE')
    for pb in ob.pose.bones:
        cb.set_bone_selected(pb, True)
    res = bake_maya.bake(bpy.context, bones=list(ob.pose.bones), start=1, end=20)
    assert res is not None
    obj_mode()
    push("bake simulation")
    return 1


def _truth():
    sc = bpy.context.scene
    k = k_()
    out = {}
    keep = sc.frame_current
    for f in range(1, 21):
        sc.frame_set(f)
        fr = {}
        for ob in sc.objects:
            if "allset_pole_of" in ob:      # the kit's hidden RP pole helper: no Maya node, not exported
                continue
            fr[ob.name] = list(ob.matrix_world.to_translation() / k)
            if ob.type == 'ARMATURE':
                for pb in ob.pose.bones:
                    fr[f"{ob.name}:{pb.name}"] = list((ob.matrix_world @ pb.matrix).to_translation() / k)
        out[f] = fr
    sc.frame_set(keep)
    return out


def stage_export():
    sc = bpy.context.scene
    obj_mode()
    s = sc.allset_game_exporter
    s.clips.clear()
    for name, a, b in (("idle", 1, 10), ("walk", 11, 20)):
        c = ge.add_clip(sc)
        c.name, c.start, c.end = name, a, b
    push("game exporter clips")
    s = sc.allset_game_exporter
    s.export_type, s.export_path, s.export_filename, s.file_split = 'ANIMATION', str(WORK), "ge240_", 'SINGLE'
    done = ge.export(bpy.context, s)
    takes = [t for _p, t in done]
    RESULTS["game_exporter"] = {"files": [p for p, _t in done], "takes": takes}
    ok = len(done) == 1 and takes[0] == ["idle", "walk"]
    record("export", "game_exporter_takes", ok, RESULTS["game_exporter"])
    select_only()
    path = str(WORK / "all240.fbx")
    res = bpy.ops.allset.file_export_all('EXEC_DEFAULT', filepath=path, export_type='FBX')
    assert res == {'FINISHED'}, res
    RESULTS["fbx"] = path
    truth = _truth()
    qa.write_json(f"qa_b_{TAG}_truth.json", truth)
    return 1, truth


def stage_import(truth):
    bpy.ops.wm.open_mainfile(filepath=str(WORK / "empty_cm.blend"))
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 0, 250
    res = bpy.ops.allset.file_import('EXEC_DEFAULT', filepath=RESULTS["fbx"])
    assert res == {'FINISHED'}, res
    k = k_()
    rng = (sc.frame_start, sc.frame_end)
    worst = {"objects": 0.0, "joints": 0.0}
    missing, where = [], {}
    for f in range(1, 21):
        sc.frame_set(f)
        for key, p in truth[f].items():
            if ":" in key:
                arm_name, bone = key.split(":", 1)
                arm = bpy.data.objects.get(arm_name) or next(
                    (o for o in sc.objects if o.type == 'ARMATURE' and bone in o.pose.bones), None)
                if arm is None or bone not in arm.pose.bones:
                    missing.append(key)
                    continue
                got = (arm.matrix_world @ arm.pose.bones[bone].matrix).to_translation() / k
                kind = "joints"
            else:
                ob = bpy.data.objects.get(key)
                if ob is None:
                    missing.append(key)
                    continue
                got = ob.matrix_world.to_translation() / k
                kind = "objects"
            e = (got - Vector(p)).length
            if e > worst[kind]:
                worst[kind] = e
                where[kind] = (f, key, list(got), p)
    missing = sorted(set(missing))
    RESULTS["fbx_round_trip"] = {"range": rng, "worst_cm": worst, "where": where, "missing": missing,
                                 "imported": sorted(o.name for o in sc.objects)}
    ok_tol = max(worst.values()) <= 1e-5
    sev = "S2" if max(worst.values()) > 1e-3 else "S3"
    record("import", "fbx_round_trip_1e-5cm", ok_tol, RESULTS["fbx_round_trip"], severity=sev)
    record("import", "fbx_range", rng == (1, 20), {"range": rng})
    record("import", "fbx_missing_nodes", not missing, {"missing": missing}, severity="S2")
    reset_chain()
    obj_mode()
    push("after import")
    return 1


# --- the test --------------------------------------------------------------------------------------------------

def _run(stage, fn):
    try:
        out = fn()
    except Exception:
        record(stage, "stage_runs", False, traceback.format_exc()[-2000:], severity="S1")
        raise
    return out


def test_e2e_chain():
    switch.set_mode(True, layout=False)
    _run("setup", stage_setup)
    for stage, fn in (("model", stage_model), ("uv", stage_uv), ("rig", stage_rig), ("anim", stage_anim),
                      ("bake", stage_bake)):
        k = _run(stage, fn)
        checkpoints(stage, k)
    k, truth = _run("export", stage_export)
    checkpoints("export", k)
    k = _run("import", lambda: stage_import(truth))
    checkpoints("import", k)
    fails = [c for c in RESULTS["checkpoints"] if not c["ok"] and not c.get("by_design")]
    RESULTS["summary"] = {"checkpoints": len(RESULTS["checkpoints"]), "failed": len(fails)}
    qa.write_json(f"qa_b_{TAG}.json", RESULTS)
    print(f"QA-B SUMMARY {RESULTS['summary']}", flush=True)
    assert not fails, [(c["stage"], c["relation"]) for c in fails]
