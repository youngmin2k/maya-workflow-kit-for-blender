"""QA activity D: seeded monkey in Maya mode, headless (engine; runners qa_monkey*.py).

Action dictionary (built at run time):
  key   - Maya keymap items (``kit.maya_kc()``, non-modal) whose operator is ``allset.*`` or a common Blender op,
          called like a key press but EXEC (``op('EXEC_DEFAULT', True, **kmi props)``; INVOKE would start modals that
          never get events in -b)
  menu  - every ``ui/menu_map.MAP`` path, run like a Maya menu click: ``bpy.ops.allset.menu_item(item=path)``
  mark  - every marking menu leaf (``marking/menus.MENUS``), run like a pick: ``marking.modal.run_action(ctx, action)``
  sel   - change selection / active object / mode (object, edit mesh, pose)
  undo  - every 50 actions 1-3 ed.undo / ed.redo (an undo push follows every action: Blender -b crashes on undo after
          unpushed data changes even without the kit, tools/qa/repro_c_blender_undo_crash.py)
Weight x3 for actions whose id / path mentions a changed area (fbx, joint, anim_layer, four_view, driven_key,
game_export, skin, ik, view). EXCLUDE = destructive / blocking / external-process / file / preference items.

Collected: kit Python tracebacks (from operator RuntimeErrors carrying a Traceback, and from anything written to
sys.stderr — handler exceptions), crashes (the last ``QA_D <i>`` line of the log), poll failures / CANCELLED /
reported errors are counted, not bugs.
"""

import io
import json
import os
import random
import re
import sys
import time
import traceback
from importlib import import_module
from pathlib import Path

import bpy

import kit

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tmp" / "qa240"
OUT.mkdir(parents=True, exist_ok=True)
VERSION = ".".join(map(str, bpy.app.version))
TAG = os.environ.get("ALLSET_SANDBOX", "qa_d")

WEIGHTED = ("fbx", "joint", "anim_layer", "animation layer", "four_view", "four view", "driven", "game_export",
            "game exporter", "skin", "ik", "view")

# Never run: they open / save / quit files, write preferences, open a browser or file dialog, start an external
# process or a render, reload scripts, or switch Maya mode / extensions (the monkey is about the Maya session).
EXCLUDE = (
    r"^File/", r"Help/", r"url_open", r"wm\.quit", r"save_userpref", r"userpref", r"preferences", r"wm\.open_mainfile",
    r"wm\.save", r"read_homefile", r"read_factory", r"new_maya_scene", r"open_scene", r"save_scene", r"increment_save",
    r"render", r"Render", r"playblast", r"Playblast", r"batch", r"play_rendered", r"file_import", r"file_export",
    r"export", r"Export", r"import", r"Import", r"reference", r"Reference", r"project", r"Project", r"script\.",
    r"script_run", r"run_script", r"command_line", r"wm\.link", r"wm\.append", r"addon", r"extension", r"make_maya",
    r"make_blender", r"maya_mode", r"switch", r"revert", r"screenshot", r"image\.save", r"image\.open", r"sound",
    r"wm\.doc", r"console", r"hotkey_editor", r"Hotkey Editor", r"Save Preferences", r"Exit", r"wm\.call_",
    r"fileselect", r"Open", r"Save", r"Recent", r"ed\.undo", r"ed\.redo", r"undo_history", r"wm\.window_",
    r"screen\.animation_play", r"anim\.keyframe_insert_menu", r"wm\.search", r"text\.", r"deformer_weights",
    r"Export Weights", r"Import Weights", r"Batch", r"bake", r"Bake", r"Cache", r"cache", r"Send to", r"Unreal",
    r"Unity", r"Game Exporter", r"game_export", r"wm\.properties_", r"outliner\.orphans_purge",
    # popup menus / pies / marking-menu engines: Blender 4.5 -b crashes in ui_popup_menu_create_impl (no region) on
    # wm.call_menu exec (seen at seed 1 #295 "Windows/UI Elements") - headless-only, a GUI opens the menu
    r"^\('menu'", r"^\('pie'", r"allset\.mm_", r"hotbox", r"popup", r"option_box", r"call_menu", r"call_panel",
    # Blender 4.5 / 5.2 -b crash in initTimeSlide on a scripted transform.transform(mode='TIME_SLIDE') with no
    # Dope Sheet (factory Blender, no kit: tools/qa/repro_c_time_slide.py) - a GUI has the editor
    # 5.2 -b crash in stitch_exit on a scripted UV Stitch (factory Blender; 4.5 survives, the GUI menu path is checked
    # by tests/gui/gui_step271_uv_stitch.py); -b has no tool keymaps, so tool activation raises inside Blender
    r"Stitch Together", r"uv\.stitch", r"Pencil Curve Tool",
    r"TIME_SLIDE", r"BONE_ROLL",     # BONE_ROLL from a script in Object Mode: the same crash (applyBoneRoll)
    # kit editors that open a popover (wm.call_panel inside the operator): 5.2 -b crashes in popover_panel_create
    # (no region), like call_panel above; a GUI opens them (gui_step179_light_linking, gui_step187_character_sets)
    r"Light Linking", r"Relationship Editors/Character Sets", r"camera_attribute_editor", r"character_attributes",
    r"character_editor", r"light_linking_editor", r"cb_channel_drag",
)
EXCLUDE_RE = re.compile("|".join(EXCLUDE))
COMMON = ("object.", "mesh.", "transform.", "anim.", "pose.", "armature.", "wm.context_", "wm.tool_set", "view3d.",
          "screen.", "uv.", "curve.", "graph.", "action.", "nla.", "outliner.", "paint.", "sculpt.")


def m(name):
    return import_module(kit.MODULE + "." + name)


def log(*a):
    print("QA_D", *a, flush=True)


# ---------------------------------------------------------------------------------------- scene

def ensure_scene(force=False):
    sc = bpy.context.scene
    need = ("pCube1", "pSphere1", "pCylinder1", "joint1")
    if not force and all(n in sc.objects for n in need):
        return False
    ob = bpy.context.object
    if ob is not None and ob.mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except RuntimeError:
            pass
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    import bmesh

    def mesh(name, size, loc, segs=False):
        me = bpy.data.meshes.new(name + "Shape")
        bm = bmesh.new()
        if segs:
            bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.5, radius2=0.5, depth=6.0)
            bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 1],
                                      cuts=5, use_grid_fill=False)
        else:
            bmesh.ops.create_cube(bm, size=size)
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new(name, me)
        sc.collection.objects.link(o)
        o.location = loc
        return o

    mesh("pCube1", 2.0, (0, 0, 0))
    sph = mesh("pSphere1", 1.0, (3, 0, 0))
    sph.keyframe_insert("location", frame=1)
    sph.location.z = 2.0
    sph.keyframe_insert("location", frame=12)
    sph.location.z = 0.0
    cyl = mesh("pCylinder1", 1.0, (-3, 0, 3), segs=True)
    arm_data = bpy.data.armatures.new("skeleton1")
    arm = bpy.data.objects.new("joint1", arm_data)
    sc.collection.objects.link(arm)
    arm.location = (-3, 0, 0)
    for o in sc.objects:
        o.select_set(False)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    prev = None
    for i in range(3):
        b = arm_data.edit_bones.new(f"joint{i + 1}")
        b.head = (0, 0, i * 2.0)
        b.tail = (0.2 if i == 1 else 0.0, 0, i * 2.0 + 2.0)
        if prev is not None:
            b.parent, b.use_connect = prev, True
        prev = b
    bpy.ops.object.mode_set(mode='OBJECT')
    # skin: one vertex group per joint by height, armature modifier, parented
    cyl.parent = arm
    cyl.matrix_parent_inverse = arm.matrix_world.inverted()
    for i in range(3):
        vg = cyl.vertex_groups.new(name=f"joint{i + 1}")
        idx = [v.index for v in cyl.data.vertices if i * 2.0 - 0.1 <= (cyl.matrix_world @ v.co).z <= i * 2.0 + 2.1]
        vg.add(idx, 1.0, 'REPLACE')
    md = cyl.modifiers.new("skinCluster1", 'ARMATURE')
    md.object = arm
    arm.pose.bones["joint2"].rotation_mode = 'XYZ'
    arm.pose.bones["joint2"].keyframe_insert("rotation_euler", frame=1)
    for o in sc.objects:
        o.select_set(False)
    sc.objects["pCube1"].select_set(True)
    bpy.context.view_layer.objects.active = sc.objects["pCube1"]
    sc.frame_set(1)
    return True


# ---------------------------------------------------------------------------------------- dictionary

def _props_of(kmi):
    out = {}
    p = kmi.properties
    if p is None:
        return out
    for k in p.keys():
        try:
            v = getattr(p, k)
        except AttributeError:
            continue
        if hasattr(v, "__len__") and not isinstance(v, str):
            try:
                v = list(v)
            except TypeError:
                continue
        if isinstance(v, set):
            v = sorted(v)
        if isinstance(v, (int, float, str, bool, list)):
            out[k] = v
    return out


def _weight(text):
    t = text.lower()
    return 3 if any(w in t for w in WEIGHTED) else 1


def dictionary():
    acts = []
    seen = set()
    for km in kit.maya_kc().keymaps:
        if km.is_modal:
            continue
        for kmi in km.keymap_items:
            idn = kmi.idname
            if not (idn.startswith("allset.") or idn.startswith(COMMON)):
                continue
            props = _props_of(kmi)
            key = ("key", idn, json.dumps(props, sort_keys=True))
            if key in seen or EXCLUDE_RE.search(idn + " " + key[2]):
                continue
            seen.add(key)
            acts.append({"kind": "key", "op": idn, "props": props, "km": km.name, "w": _weight(idn + key[2])})
    menu_map = m("ui.menu_map")
    for path, action in menu_map.MAP.items():
        text = path + " " + repr(action)
        if EXCLUDE_RE.search(text) or EXCLUDE_RE.search(repr(action)):
            continue
        acts.append({"kind": "menu", "path": path, "w": _weight(text)})
    menus = m("marking.menus")
    for name, menu in menus.MENUS.items():
        for path, label, action in _leaves(menu, name):
            text = path + " " + repr(action)
            if EXCLUDE_RE.search(text) or EXCLUDE_RE.search(repr(action)):
                continue
            acts.append({"kind": "mark", "menu": name, "path": path, "w": _weight(text)})
    return acts


def _leaves(sub, prefix):
    menus = m("marking.menus")
    entries = [(pos, e) for pos, e in sub.radial.items()] + [(str(i), e) for i, e in enumerate(sub.items)]
    for pos, e in entries:
        if not isinstance(e, tuple) or len(e) < 2:
            continue
        label, action = e[0], e[1]
        path = f"{prefix}/{pos}:{label}"
        if isinstance(action, menus.Sub):
            yield from _leaves(action, path)
        elif action is not None and not menus.is_unavailable(action):
            yield path, label, action


def find_mark(menu, path):
    menus = m("marking.menus")
    for p, _label, action in _leaves(menus.MENUS[menu], menu):
        if p == path:
            return action
    return None


# ---------------------------------------------------------------------------------------- run

# Blender 4.5 / 5.x -b crash in ui_popup_menu_create_impl / UI_popover_panel_invoke when an operator calls
# wm.call_menu / wm.call_panel with no region (seed 1 #295 Windows/UI Elements, seed 2 #164 Light Linking Editor) - a GUI
# opens the popup. Harness-only shim (this process, never src/): those calls return CANCELLED and are counted.
POPUP_OPS = {"wm.call_menu", "wm.call_panel", "wm.call_menu_pie", "wm.search_menu", "wm.search_operator"}
POPUPS = {"skipped": 0}


def _shim_popups():
    cls = type(bpy.ops.wm.call_menu)
    if getattr(cls, "_qa_shim", False):
        return
    orig = cls.__call__

    def call(self, *args, **kw):
        if self.idname_py() in POPUP_OPS:
            POPUPS["skipped"] += 1
            return {'CANCELLED'}
        return orig(self, *args, **kw)

    try:
        cls.__call__ = call
        cls._qa_shim = True
    except TypeError:
        # Blender 5.x: bpy.ops functions are an immutable C type -> put a proxy in front of bpy.ops.wm instead
        real_wm = bpy.ops.wm

        class _Wm:
            _qa_shim = True

            def __getattr__(self, name):
                if "wm." + name in POPUP_OPS:
                    def skipped(*_a, **_k):
                        POPUPS["skipped"] += 1
                        return {'CANCELLED'}
                    return skipped
                return getattr(real_wm, name)

        if not getattr(bpy.ops.wm, "_qa_shim", False):
            bpy.ops.wm = _Wm()


class StderrTee(io.TextIOBase):
    def __init__(self, real):
        self.real = real
        self.buf = []

    def write(self, s):
        self.buf.append(s)
        return self.real.write(s)

    def flush(self):
        self.real.flush()

    def take(self):
        s = "".join(self.buf)
        self.buf.clear()
        return s


def _kit_frames(text):
    frames = re.findall(r'File "([^"]+)", line (\d+)', text)
    return [f"{Path(f).as_posix().split('allset/', 1)[-1]}:{n}" for f, n in frames
            if re.search(r"[\\/]allset[\\/]", f) and "/qa/" not in Path(f).as_posix()]   # not allset_blenders/


def apply_context(spec):
    """spec = {"sel": [names], "active": name, "mode": 'OBJECT'|'EDIT'|'POSE'}"""
    sc = bpy.context.scene
    ob = bpy.context.object
    if ob is not None and ob.mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except RuntimeError:
            pass
    for o in sc.objects:
        try:
            o.select_set(o.name in spec["sel"])
        except RuntimeError:
            pass
    act = sc.objects.get(spec["active"])
    if act is not None:
        bpy.context.view_layer.objects.active = act
        mode = spec["mode"]
        if mode == 'EDIT' and act.type in ('MESH', 'ARMATURE', 'CURVE'):
            bpy.ops.object.mode_set(mode='EDIT')
        elif mode == 'POSE' and act.type == 'ARMATURE':
            bpy.ops.object.mode_set(mode='POSE')


def run_one(a):
    """Returns 'ok' | 'cancelled' | 'poll' | 'error-report' | ('kit-exc', text)."""
    kind = a["kind"]
    try:
        if kind == "key":
            mod, name = a["op"].split(".", 1)
            fn = getattr(getattr(bpy.ops, mod), name)
            res = fn('EXEC_DEFAULT', True, **a["props"])
        elif kind == "menu":
            res = bpy.ops.allset.menu_item('EXEC_DEFAULT', True, item=a["path"])
        elif kind == "mark":
            action = find_mark(a["menu"], a["path"])
            if action is None:
                return "missing"
            res = m("marking.modal").run_action(bpy.context, action)
        elif kind == "ctx":
            apply_context(a["spec"])
            res = {'FINISHED'}
        elif kind in ("undo", "redo"):
            try:
                getattr(bpy.ops.ed, kind)()
            except RuntimeError:
                return "poll"
            return "ok"
        else:
            return "unknown"
    except RuntimeError as ex:
        text = str(ex)
        if "Traceback" in text and _kit_frames(text):
            return ("kit-exc", text)
        if "poll()" in text or "context is incorrect" in text:
            return "poll"
        return "error-report"
    except TypeError as ex:              # stale keymap property names etc.
        return ("harness-type", str(ex))
    except Exception as ex:              # a kit function raising straight into the caller (run_action)
        text = traceback.format_exc()
        if _kit_frames(text):
            return ("kit-exc", text)
        return ("harness-exc", text)
    if isinstance(res, set):
        return "ok" if 'FINISHED' in res else "cancelled"
    return "ok"


def make_actions(seed, n, pool):
    rng = random.Random(seed)
    weights = [a["w"] for a in pool]
    names = ["pCube1", "pSphere1", "pCylinder1", "joint1"]
    out = []
    for i in range(n):
        if i and i % 50 == 0:
            for _ in range(rng.randint(1, 3)):
                out.append({"kind": rng.choice(("undo", "undo", "redo"))})
        r = rng.random()
        if r < 0.12:
            sel = rng.sample(names, rng.randint(0, 3))
            active = rng.choice(names)
            sel = sorted(set(sel) | {active}) if rng.random() < 0.9 else sel
            mode = rng.choice(("OBJECT", "OBJECT", "EDIT", "POSE"))
            out.append({"kind": "ctx", "spec": {"sel": sel, "active": active, "mode": mode}})
        else:
            out.append(dict(rng.choices(pool, weights)[0]))
    return out


def label(a):
    k = a["kind"]
    if k == "key":
        return f"key {a['op']} {json.dumps(a['props'], sort_keys=True)} [{a.get('km')}]"
    if k == "menu":
        return f"menu {a['path']}"
    if k == "mark":
        return f"mark {a['menu']} {a['path']}"
    if k == "ctx":
        return f"ctx {a['spec']}"
    return k


class Monkey:
    def __init__(self):
        self.stats = {}
        self.failures = []          # (index, signature, text)
        self.tee = StderrTee(sys.stderr)

    def run(self, actions, budget_s=None, stop_sig=None, setup=None):
        _shim_popups()
        t0 = time.time()
        old = sys.stderr
        sys.stderr = self.tee
        done = 0
        try:
            ensure_scene(force=True)
            if setup is not None:
                setup()
            bpy.ops.ed.undo_push(message="qa d start")
            for i, a in enumerate(actions):
                if budget_s is not None and time.time() - t0 > budget_s:
                    break
                if ensure_scene():
                    bpy.ops.ed.undo_push(message="qa d scene")
                log(i, label(a))
                self.tee.take()
                res = run_one(a)
                try:
                    bpy.ops.ed.undo_push(message=f"qa d {i}")
                except RuntimeError:
                    pass
                err = self.tee.take()
                key = res if isinstance(res, str) else res[0]
                self.stats[key] = self.stats.get(key, 0) + 1
                if not isinstance(res, str) and res[0] == "kit-exc":
                    self._fail(i, a, "exc", res[1])
                if not isinstance(res, str) and res[0] == "harness-exc":
                    self._fail(i, a, "harness", res[1])
                if err and ("Traceback" in err or "Error" in err) and _kit_frames(err):
                    self._fail(i, a, "stderr", err)
                done = i + 1
                if stop_sig and any(f[1] == stop_sig for f in self.failures):
                    break
        finally:
            sys.stderr = old
        return done

    def _fail(self, i, a, where, text):
        frames = _kit_frames(text)
        errs = [ln.strip() for ln in text.splitlines() if re.match(r"\s*\w+(Error|Exception|Warning)\b.*:", ln)
                and not ln.strip().startswith(("RuntimeError: Error: Python", "Error: Python"))]
        last = errs[-1] if errs else (text.strip().splitlines()[-1] if text.strip() else "")
        exc = re.sub(r"[-\d.]+", "#", last)[:100]
        sig = f"{where}|{frames[-1] if frames else '?'}|{exc}"
        self.failures.append((i, sig, text, label(a)))
        log("FAIL", i, sig)


def finding(fid, severity, repro, oracle, detail, extra=None):
    rec = {"id": fid, "activity": "D", "severity": severity, "repro": repro, "oracle": oracle,
           "version": VERSION, "detail": detail}
    if extra:
        rec.update(extra)
    with open(OUT / "findings.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


def shrink(actions, sig, budget_s=45.0):
    """Shortest suffix of the failing prefix that still fails (fresh scene each try), then drop single actions."""
    t0 = time.time()
    cur = list(actions)
    for n in (1, 2, 3, 5, 10, 20, 50, 100):
        if time.time() - t0 > budget_s:
            break
        if n >= len(cur):
            break
        cand = cur[-n:]
        mk = Monkey()
        mk.run(cand, stop_sig=sig)
        if any(f[1] == sig for f in mk.failures):
            cur = cand
            break
    i = 0
    while i < len(cur) - 1 and time.time() - t0 < budget_s:
        cand = cur[:i] + cur[i + 1:]
        mk = Monkey()
        mk.run(cand, stop_sig=sig)
        if any(f[1] == sig for f in mk.failures):
            cur = cand
        else:
            i += 1
    return cur


def write_repro(name, actions, sig):
    path = Path(__file__).resolve().parent / f"{name}.py"
    path.write_text(
        '"""QA 240 D repro (generated by tools/qa/qa_d_core.py). Signature: ' + sig.replace('"""', "'") + '\n\n'
        'Run: ALLSET_SANDBOX=qa_d python tests/run.py --no-build -k __none__ --extra tools/qa/' + path.name + '\n"""\n'
        "from importlib.util import module_from_spec, spec_from_file_location\n"
        "from pathlib import Path\n\n"
        "_spec = spec_from_file_location('qa_d_core', Path(__file__).resolve().parent / 'qa_d_core.py')\n"
        "core = module_from_spec(_spec)\n_spec.loader.exec_module(core)\n\n"
        f"ACTIONS = {json.dumps(actions, indent=1)}\nSIGNATURE = {json.dumps(sig)}\n\n\n"
        "def test_repro():\n"
        "    mk = core.Monkey()\n"
        "    mk.run(ACTIONS)\n"
        "    hits = [f for f in mk.failures if f[1] == SIGNATURE]\n"
        "    assert not hits, hits[0][2][-1500:]\n",
        encoding="utf-8")
    return path


def run_seed(seed, n=700, budget_s=200.0):
    t0 = time.time()
    pool = dictionary()
    log("dictionary", len(pool), {k: sum(1 for a in pool if a["kind"] == k) for k in ("key", "menu", "mark")})
    actions = make_actions(seed, n, pool)
    mk = Monkey()
    done = mk.run(actions, budget_s=budget_s)
    seen, recs = set(), []
    for i, sig, text, lab in mk.failures:
        if sig in seen:
            continue
        seen.add(sig)
        left = 280 - (time.time() - t0)
        small = shrink(actions[:i + 1], sig, budget_s=min(40.0, left - 30)) if left > 60 else actions[:i + 1]
        path = write_repro(f"repro_d_{seed}_{i}", small, sig)
        frames = _kit_frames(text)
        sev = "S2" if sig.startswith(("exc", "stderr")) else "S4"
        recs.append(finding(f"D-{TAG}-s{seed}-{i}", sev, f"tools/qa/{path.name}",
                            "kit Python traceback" if sev == "S2" else "harness exception",
                            f"{lab}: {sig.split('|', 2)[-1]}",
                            {"kit_frame": frames[-1] if frames else None, "actions": len(small)}))
    res = {"seed": seed, "popups_skipped": POPUPS["skipped"], "planned": len(actions), "ran": done, "dictionary": len(pool), "stats": mk.stats,
           "failures": len(mk.failures), "unique": len(recs), "findings": recs,
           "seconds": round(time.time() - t0, 1)}
    path = OUT / "qa_d.json"
    try:
        allr = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        allr = {}
    allr.setdefault(f"{TAG} {VERSION}", {})[f"seed{seed}"] = res
    path.write_text(json.dumps(allr, indent=1), encoding="utf-8")
    return res
