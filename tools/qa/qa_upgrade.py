"""QA activity E (upgrade): install 0.5.0 -> use -> upgrade to 0.10.0 -> disable / remove, in a clean sandbox.

    python tools/qa/qa_upgrade.py [--blender EXE] [--old ZIP] [--new ZIP]

Sandbox tmp/qa_upg/{config,scripts,extensions} (created before any Blender starts; every probe asserts
bpy.utils.user_resource('CONFIG') is inside it). Old zip default = the published 0.5.0 on the Desktop
(MayaWorkflowKit_upload/maya-workflow-kit-0.5.0.zip); new = dist/maya-workflow-kit-0.10.0.zip.
 0 factory snapshot (before anything is installed)
 1 `blender --factory-startup --command extension install-file -r user_default --enable <old zip>`
 2 session with 0.5.0: Maya mode on (welcome.opt_in), 3 add-on prefs, a user shelf button (shelves.json), a hotkey
   change (Hotkey Editor, keyconfigs.user), save_userpref, a .blend with a small rig + keys + skin
 3 install the new zip over it (same command)
 4 session with 0.10.0: prefs / shelf / hotkey / Maya mode kept? the 0.5.0 .blend opens without tracebacks and its
   joint positions / key values / weights equal the 0.5.0 truth
 5 Disable -> Enable (0.10.0) snapshot, then Remove from inside Blender (disable(default_set) + package_uninstall)
 6 final snapshot == factory snapshot taken first (keyconfig, inputs / view / edit prefs, add-ons, handlers, types)
Output tmp/qa240/qa_e.json; mismatches -> tmp/qa240/findings.jsonl.
The script runs itself inside Blender as the probe (``-- <mode> OUT.json``).
"""

import json
import os
import sys

try:
    import bpy  # noqa: F401
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False


# =============================================================================================================
# probe (inside Blender)
# =============================================================================================================

if IN_BLENDER:
    import hashlib
    import io
    import traceback
    from importlib import import_module

    import addon_utils
    import bpy

    KIT = "bl_ext.user_default.allset"
    BLEND = os.environ["QA_UPG_BLEND"]

    class _Tee(io.TextIOBase):
        def __init__(self, real):
            self.real, self.buf = real, []

        def write(self, s):
            self.buf.append(s)
            return self.real.write(s)

        def flush(self):
            self.real.flush()

    TEE = _Tee(sys.stderr)
    sys.stderr = TEE

    def _assert_sandbox():
        config = bpy.utils.user_resource('CONFIG')
        assert os.path.normcase(os.path.join("tmp", "qa_upg")) in os.path.normcase(config), config

    def _rna_values(struct):
        out = {}
        for p in struct.bl_rna.properties:
            if p.identifier in ("rna_type",) or p.type in ('POINTER', 'COLLECTION'):
                continue
            try:
                v = getattr(struct, p.identifier)
            except Exception:
                continue
            if isinstance(v, (set, frozenset)):
                v = sorted(v)
            elif hasattr(v, "__len__") and not isinstance(v, str):
                v = [round(x, 5) if isinstance(x, float) else x for x in v]
            elif isinstance(v, float):
                v = round(v, 5)
            out[p.identifier] = repr(v)
        return out

    def _kit_version():
        import re
        for repo in bpy.context.preferences.extensions.repos:
            path = os.path.join(repo.directory, "allset", "blender_manifest.toml")
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as fh:
                    m = re.search(r'^version\s*=\s*"([^"]+)"', fh.read(), re.M)
                return m.group(1) if m else "?"
        return ""

    def _user_dir():
        ext = bpy.utils.user_resource('EXTENSIONS')
        return os.path.join(ext, ".user", "user_default", "allset")

    def _user_files():
        d = _user_dir()
        out = {}
        for root, _dirs, files in os.walk(d):
            for f in files:
                p = os.path.join(root, f)
                with open(p, "rb") as fh:
                    out[os.path.relpath(p, d)] = hashlib.sha1(fh.read()).hexdigest()[:12]
        return out

    def _shelves_json():
        p = os.path.join(_user_dir(), "shelves.json")
        if not os.path.isfile(p):
            return None
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)

    def _user_key_edits():
        out = []
        for km in bpy.context.window_manager.keyconfigs.user.keymaps:
            for kmi in km.keymap_items:
                if kmi.idname.startswith("allset.") and kmi.is_user_modified:
                    out.append([km.name, kmi.idname, kmi.type, kmi.value, kmi.ctrl, kmi.alt, kmi.shift, kmi.active])
        return sorted(out)

    def _items_on(km_name, key, ctrl=False):
        km = bpy.context.window_manager.keyconfigs.user.keymaps.get(km_name)
        if km is None:
            return None
        return [k.idname for k in km.keymap_items if k.active and k.type == key and bool(k.ctrl) == ctrl
                and not k.alt and not k.shift]

    PREFS = ("select_through", "cb_speed", "curve_color_rules")

    def _kit_prefs():
        a = bpy.context.preferences.addons.get(KIT)
        if a is None or a.preferences is None:
            return None
        p = a.preferences
        return {n: repr(getattr(p, n, "<missing>")) for n in PREFS + ("maya_mode", "welcome_done")}

    def snapshot():
        prefs = bpy.context.preferences
        wm = bpy.context.window_manager
        handlers = {}
        for name in dir(bpy.app.handlers):
            lst = getattr(bpy.app.handlers, name)
            if isinstance(lst, list):
                kit_h = [f"{getattr(f, '__module__', '')}.{getattr(f, '__qualname__', repr(f))}" for f in lst
                         if "allset" in (getattr(f, "__module__", "") or "")]
                if kit_h:
                    handlers[name] = kit_h
        return {
            "blender": bpy.app.version_string,
            "kit_version": _kit_version(),
            "addons": sorted(a.module for a in prefs.addons),
            "active_keyconfig": [prefs.keymap.active_keyconfig, wm.keyconfigs.active.name if wm.keyconfigs.active
                                 else None],
            "keyconfigs": sorted(k.name for k in wm.keyconfigs),
            "inputs": _rna_values(prefs.inputs),
            "view": _rna_values(prefs.view),
            "edit": _rna_values(prefs.edit),
            "kit_prefs": _kit_prefs(),
            "user_files": _user_files(),
            "shelves_json": _shelves_json(),
            "user_key_edits": _user_key_edits(),
            "kit_handlers": handlers,
            "kit_types": sorted(n for n in dir(bpy.types) if n.startswith("ALLSET_")),
            "kit_ops": sorted(n for n in dir(bpy.ops) if n == "allset"),
            "addon_kit_items": sum(1 for km in wm.keyconfigs.addon.keymaps for k in km.keymap_items
                                   if k.idname.startswith("allset.")),
            "f8_object": _items_on("Object Non-modal", "F8"),
            "ctrl_f6_object": _items_on("Object Non-modal", "F6", ctrl=True),
        }

    def _rig_truth():
        sc = bpy.context.scene
        arm = bpy.data.objects.get("skeleton1")
        body = bpy.data.objects.get("pCube1")
        out = {"objects": sorted(o.name for o in sc.objects), "frames": {}}
        if arm is None:
            return out
        keep = sc.frame_current
        for f in (1, 5, 10, 15, 20):
            sc.frame_set(f)
            fr = {pb.name: [round(c, 5) for c in (arm.matrix_world @ pb.matrix).to_translation()]
                  for pb in arm.pose.bones}
            if body is not None:
                ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
                fr["_body_verts"] = hashlib.sha1(repr([tuple(round(c, 5) for c in (body.matrix_world @ v.co))
                                                       for v in ev.vertices]).encode()).hexdigest()[:12]
            out["frames"][str(f)] = fr
        sc.frame_set(keep)
        keys = {}
        compat = import_module(KIT + ".compat")
        for ob in (arm, body):
            if ob is not None and ob.animation_data:
                for fc in compat.id_fcurves(ob):
                    keys[f"{ob.name}:{fc.data_path}[{fc.array_index}]"] = [[round(k.co[0], 3), round(k.co[1], 5)]
                                                                         for k in fc.keyframe_points]
        out["keys"] = keys
        if body is not None:
            names = {g.index: g.name for g in body.vertex_groups}
            out["weights"] = hashlib.sha1(repr([[(names[g.group], round(g.weight, 5)) for g in v.groups]
                                                for v in body.data.vertices]).encode()).hexdigest()[:12]
            out["modifiers"] = [(m.name, m.type) for m in body.modifiers]
            out["kit_props"] = sorted(k for k in body.keys() if k.startswith("allset"))
        out["scene_kit_props"] = sorted(k for k in sc.keys() if k.startswith("allset"))
        return out

    def use_old(log):
        if KIT not in bpy.context.preferences.addons:
            log["enabled_by_probe"] = True
            addon_utils.enable(KIT, default_set=True)
        welcome = import_module(KIT + ".welcome")
        welcome.opt_in(open_layout=False)
        populate()                     # the user keyconfig again, now with the kit's Maya items merged in
        p = bpy.context.preferences.addons[KIT].preferences
        log["prefs_before"] = {n: repr(getattr(p, n)) for n in PREFS}
        p.select_through = not p.select_through
        items = [i.identifier for i in p.bl_rna.properties["cb_speed"].enum_items]
        p.cb_speed = next(i for i in items if i != p.cb_speed)
        p.curve_color_rules = "qa240 upgrade marker"
        log["prefs_set"] = {n: repr(getattr(p, n)) for n in PREFS}
        shelf = import_module(KIT + ".ui.shelf")
        log["shelf_added"] = repr(shelf.add_menu_item(bpy.context, "Mesh/Combine"))
        he = import_module(KIT + ".ui.hotkey_editor")
        row = next(r for r in he.rows() if r["command"] == "SelectToggleMode" and r["context"] == "global")
        log["hotkey_assign"] = list(bpy.ops.allset.hotkey_assign(row=row["index"], key="F6", ctrl=True))
        bpy.ops.wm.save_userpref()
        # a scene made by this version: skeleton + keys + a skinned cube (kit functions of 0.5.0)
        joints = import_module(KIT + ".operators.joints")
        skin = import_module(KIT + ".operators.skin")
        units = import_module(KIT + ".operators.units")
        from mathutils import Vector
        sc = bpy.context.scene
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob)
        sc.unit_settings.system, sc.unit_settings.length_unit, sc.unit_settings.scale_length = 'METRIC', \
            'CENTIMETERS', 0.01
        sc.frame_start, sc.frame_end = 1, 20
        k = units.maya_unit(sc)
        bpy.ops.allset.create(kind='CUBE')
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        body = bpy.context.active_object
        body.scale = (1, 1, 4)
        ob = joints.new_skeleton(bpy.context)
        parent, names = None, []
        for p_ in ((0, 0, -2), (0.3, 0, 0), (0, 0, 2)):
            parent = joints.add_joint(ob, Vector(p_) * k, parent, up=Vector((0, 0, 1)), length=0.5 * k)
            names.append(parent)
        joints.orient_new(ob, names)
        joints.finish(bpy.context, ob, names)
        bpy.ops.object.mode_set(mode='OBJECT')
        skin.bind_skin(bpy.context, ob, [body])
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='POSE')
        pb = ob.pose.bones[names[1]]
        for f, deg in ((1, 0.0), (10, 35.0), (20, -15.0)):
            sc.frame_set(f)
            pb.rotation_euler = (0.0, 0.0, deg * 3.14159265 / 180)
            pb.keyframe_insert("rotation_euler", frame=f)
        bpy.ops.object.mode_set(mode='OBJECT')
        log["truth"] = _rig_truth()
        bpy.ops.wm.save_mainfile(filepath=BLEND)

    def open_old(log):
        TEE.buf.clear()
        try:
            bpy.ops.wm.open_mainfile(filepath=BLEND)
            log["open_ok"] = True
        except Exception:
            log["open_ok"] = False
            log["open_error"] = traceback.format_exc()[-1500:]
        log["truth"] = _rig_truth()
        text = "".join(TEE.buf)
        log["tracebacks"] = text.count("Traceback (most recent call last)")
        i = text.find("Traceback")
        log["traceback_text"] = text[i:i + 2000] if i >= 0 else ""

    def populate():
        """-b leaves the default keyconfig empty: fill it from Blender's keymap data so keyconfigs.user exists like
        in the UI (tests/rt60_dump.populate)."""
        kcs = bpy.context.window_manager.keyconfigs
        km = kcs.default.keymaps.get("Object Mode")
        if km is None or len(km.keymap_items) == 0:
            from bl_keymap_utils.io import keyconfig_init_from_data
            path = bpy.utils.system_resource('SCRIPTS', path="presets/keyconfig/keymap_data")
            if path not in sys.path:
                sys.path.insert(0, path)
            import blender_default
            keyconfig_init_from_data(kcs.default, blender_default.generate_keymaps(blender_default.Params()))
        kcs.update()

    def probe_main():
        _assert_sandbox()
        populate()
        mode, out = sys.argv[sys.argv.index("--") + 1:][:2]
        log = {"mode": mode}
        try:
            if mode == "use_old":
                use_old(log)
            elif mode == "after":
                open_old(log)
            elif mode == "disable_enable":
                addon_utils.disable(KIT, default_set=True)
                log["after_disable"] = snapshot()
                addon_utils.enable(KIT, default_set=True)
                bpy.ops.wm.save_userpref()
            elif mode == "maya_on":
                import_module(KIT + ".switch").set_mode(True, layout=False)
                populate()
            elif mode == "remove":
                from bl_pkg.bl_extension_ops import extension_repos_read
                repo_index = next(i for i, r in enumerate(extension_repos_read()) if r.module == "user_default")
                log["uninstall"] = list(bpy.ops.extensions.package_uninstall(repo_index=repo_index, pkg_id="allset"))
                bpy.ops.wm.save_userpref()
        except Exception:
            log["error"] = traceback.format_exc()[-2500:]
        log["snapshot"] = snapshot()
        text = "".join(TEE.buf)
        log["session_tracebacks"] = text.count("Traceback (most recent call last)")
        i = text.find("Traceback")
        log["session_traceback_text"] = text[i:i + 2000] if i >= 0 else ""
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(log, fh, indent=1, default=str)

    probe_main()


# =============================================================================================================
# driver (plain Python)
# =============================================================================================================

else:
    import argparse
    import importlib.util
    import shutil
    import subprocess
    from pathlib import Path

    HERE = Path(__file__).resolve().parent
    ROOT = HERE.parents[1]
    sys.path.insert(0, str(ROOT / "tools"))          # driver process only (not the add-on)
    import blender_slots  # noqa: E402
    import build  # noqa: E402

    _spec = importlib.util.spec_from_file_location("qa_common", HERE / "qa_common.py")
    qa = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(qa)

    SANDBOX = ROOT / "tmp" / "qa_upg"
    OLD = Path(os.path.expanduser("~")) / "Desktop" / "MayaWorkflowKit_upload" / "maya-workflow-kit-0.5.0.zip"
    NEW = ROOT / "dist" / "maya-workflow-kit-0.10.0.zip"

    def sandbox_env():
        assert SANDBOX.resolve().is_relative_to(ROOT / "tmp"), SANDBOX
        if SANDBOX.exists():
            shutil.rmtree(SANDBOX)
        env = os.environ.copy()
        for var, sub in (("BLENDER_USER_CONFIG", "config"), ("BLENDER_USER_SCRIPTS", "scripts"),
                         ("BLENDER_USER_EXTENSIONS", "extensions")):
            d = SANDBOX / sub
            d.mkdir(parents=True)           # must exist, else Blender silently uses the real folder
            env[var] = str(d)
        (SANDBOX / "out").mkdir()
        env["ALLSET_PROJECTS_DIR"] = str(SANDBOX / "projects")
        env["ALLSET_NO_WELCOME"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        env["QA_UPG_BLEND"] = str(SANDBOX / "out" / "made_by_050.blend")
        env.pop("ALLSET_NO_SLOTS", None)
        return env

    def run(cmd, env, label, timeout=600):
        with blender_slots.slot(f"qa upgrade {label}"):
            r = subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout)
        log = r.stdout + r.stderr
        (SANDBOX / "out" / f"{label}.log").write_text(log, encoding="utf-8")
        return r.returncode, log

    def main(argv=None):
        ap = argparse.ArgumentParser()
        ap.add_argument("--blender", default=os.environ.get("BLENDER", build.DEFAULT_BLENDER))
        ap.add_argument("--old", default=str(OLD))
        ap.add_argument("--new", default=str(NEW))
        args = ap.parse_args(argv)
        env = sandbox_env()
        bl = args.blender
        probe = [bl, "-b", "--python", str(Path(__file__).resolve()), "--"]
        install = [bl, "--factory-startup", "--command", "extension", "install-file", "-r", "user_default",
                   "--enable"]
        # the upgrade runs on the user's own preferences (a real user installs the new zip from their Blender);
        # --factory-startup here would save factory preferences over the user's
        upgrade = [a for a in install if a != "--factory-startup"]
        if os.environ.get("QA_UPG_FACTORY_UPGRADE"):
            upgrade = install
        out = SANDBOX / "out"
        res = {"blender": bl, "old_zip": args.old, "new_zip": args.new, "steps": {}, "checks": []}
        version = f"upgrade {Path(args.old).name} -> {Path(args.new).name}, {Path(bl).parent.name}"

        def snap(label, mode):
            path = out / f"{label}.json"
            rc, log = run(probe + [mode, str(path)], env, label)
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
            res["steps"][label] = {"rc": rc, "data": data,
                                   "log_tracebacks": log.count("Traceback (most recent call last)")}
            return data, log

        def check(name, ok, detail="", severity="S2"):
            res["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
            print(f"QA-E {'PASS' if ok else 'FAIL'} {name}: {str(detail)[:400]}", flush=True)
            if not ok:
                qa.add_finding(f"E-{name}", "E", severity, f"python tools/qa/qa_upgrade.py: {name}",
                               f"upgrade path: {str(detail)[:900]}", version)
            qa.write_json("qa_e.json", res)

        before = snap("s0_factory", "snapshot")[0]["snapshot"]
        rc, log = run(install + [args.old], env, "s1_install_old")
        check("install_old_zip", rc == 0, log[-600:], severity="S1")
        installed = (snap("s1b_after_install", "snapshot")[0] or {}).get("snapshot")
        check("old_enabled_after_install_file", installed and "bl_ext.user_default.allset" in installed["addons"],
              installed and installed["addons"], severity="S3")
        check("install_does_not_touch_keyconfig_or_prefs",
              installed and installed["active_keyconfig"] == before["active_keyconfig"]
              and installed["inputs"] == before["inputs"] and installed["view"] == before["view"],
              installed and {"kc": installed["active_keyconfig"]})
        used, log = snap("s2_use_old", "use_old")
        check("use_old_session", used and not used.get("error"), used and used.get("error"), severity="S1")
        s = used["snapshot"] if used else {}
        check("old_hotkey_changed", s.get("ctrl_f6_object") and "allset.toggle_sel_mode" in s["ctrl_f6_object"],
              {"f8": s.get("f8_object"), "ctrl_f6": s.get("ctrl_f6_object"), "edits": s.get("user_key_edits")})
        check("old_shelf_saved", bool(s.get("shelves_json")), s.get("shelves_json"))
        check("old_session_no_traceback", used and used.get("session_tracebacks", 0) == 0,
              used and used.get("session_traceback_text", "")[:1200])
        rc, log = run(upgrade + [args.new], env, "s3_install_new")
        check("install_new_over_old", rc == 0, log[-800:], severity="S1")
        after, log = snap("s4_after_upgrade", "after")
        a = after["snapshot"] if after else {}
        check("new_version_installed", a.get("kit_version") == build.manifest_value("version"),
              a.get("kit_version"), severity="S1")
        check("new_enabled", "bl_ext.user_default.allset" in a.get("addons", []), a.get("addons"), severity="S1")
        check("prefs_kept", a.get("kit_prefs") and s.get("kit_prefs") and
              all(a["kit_prefs"][n] == s["kit_prefs"][n] for n in ("select_through", "cb_speed",
                                                                     "curve_color_rules", "maya_mode")),
              {"old": s.get("kit_prefs"), "new": a.get("kit_prefs")}, severity="S1")
        check("shelf_kept", a.get("shelves_json") == s.get("shelves_json") and a.get("shelves_json"),
              {"old": s.get("shelves_json"), "new": a.get("shelves_json")}, severity="S1")
        check("hotkey_kept", a.get("user_key_edits") == s.get("user_key_edits") and a.get("user_key_edits")
              and a.get("ctrl_f6_object") and "allset.toggle_sel_mode" in a["ctrl_f6_object"],
              {"old": s.get("user_key_edits"), "new": a.get("user_key_edits"), "ctrl_f6": a.get("ctrl_f6_object"),
               "f8": a.get("f8_object")}, severity="S1")
        check("maya_mode_kept_after_upgrade", a.get("addon_kit_items", 0) > 100,
              {"addon_kit_items": a.get("addon_kit_items")}, severity="S2")
        check("old_blend_opens", after and after.get("open_ok"), after and after.get("open_error"), severity="S1")
        check("old_blend_no_traceback", after and after.get("tracebacks") == 0,
              after and after.get("traceback_text", "")[:1500], severity="S2")
        t_old, t_new = (used or {}).get("truth"), (after or {}).get("truth")
        diffs = [k for k in (t_old or {}) if (t_new or {}).get(k) != t_old[k]]
        if "scene_kit_props" in diffs and set(t_old["scene_kit_props"]) <= set(t_new.get("scene_kit_props", [])):
            diffs.remove("scene_kit_props")     # by design: load_post scene_carry adds kit scene settings
            res["by_design"] = {"scene_kit_props_added_on_load": sorted(set(t_new["scene_kit_props"])
                                                                        - set(t_old["scene_kit_props"]))}
        check("old_blend_rig_and_keys_equal", t_old and t_new and not diffs,
              {"keys_differ": diffs, "old": {k: t_old.get(k) for k in diffs} if t_old else None,
               "new": {k: (t_new or {}).get(k) for k in diffs}}, severity="S1")
        de, _l = snap("s5_disable_enable", "disable_enable")
        d = de["snapshot"] if de else {}
        check("disable_enable_keeps_shelf_and_hotkey", d.get("shelves_json") == s.get("shelves_json")
              and d.get("user_key_edits") == s.get("user_key_edits"),
              {"shelf": d.get("shelves_json"), "keys": d.get("user_key_edits")})
        res["disable_enable_prefs"] = {"before": a.get("kit_prefs"), "after": d.get("kit_prefs")}
        dis = (de or {}).get("after_disable") or {}
        check("disable_clean", not dis.get("kit_handlers") and not dis.get("kit_types")
              and dis.get("addon_kit_items") == 0 and dis.get("active_keyconfig") == before["active_keyconfig"]
              and dis.get("inputs") == before["inputs"] and dis.get("view") == before["view"],
              {"handlers": dis.get("kit_handlers"), "types": (dis.get("kit_types") or [])[:5],
               "items": dis.get("addon_kit_items"), "kc": dis.get("active_keyconfig"),
               "inputs_diff": {k: (before["inputs"].get(k), v) for k, v in (dis.get("inputs") or {}).items()
                               if before["inputs"].get(k) != v},
               "view_diff": {k: (before["view"].get(k), v) for k, v in (dis.get("view") or {}).items()
                             if before["view"].get(k) != v}}, severity="S2")
        mo, _l = snap("s5b_maya_on_again", "maya_on")
        m_ = (mo or {}).get("snapshot") or {}
        check("hotkey_back_when_maya_mode_on_again", m_.get("user_key_edits") == s.get("user_key_edits")
              and m_.get("ctrl_f6_object") and "allset.toggle_sel_mode" in m_["ctrl_f6_object"],
              {"keys": m_.get("user_key_edits"), "ctrl_f6": m_.get("ctrl_f6_object"), "f8": m_.get("f8_object")},
              severity="S2")
        check("addon_prefs_survive_disable_enable", d.get("kit_prefs") and all(
            d["kit_prefs"][n] == s["kit_prefs"][n] for n in ("select_through", "cb_speed", "curve_color_rules")),
            {"before": s.get("kit_prefs"), "after": d.get("kit_prefs")}, severity="S3")
        rm, _l = snap("s6_remove", "remove")
        check("remove_runs", rm and not rm.get("error"), rm and (rm.get("error") or rm.get("uninstall")), "S2")
        final = snap("s7_final", "snapshot")[0]["snapshot"]
        diff = {k: (before[k], final[k]) for k in ("addons", "active_keyconfig", "keyconfigs", "inputs", "view",
                                                   "edit", "kit_handlers", "kit_types", "kit_ops")
                if before[k] != final[k]}
        for k in ("inputs", "view", "edit"):
            if k in diff:
                diff[k] = {n: (before[k].get(n), final[k].get(n)) for n in set(before[k]) | set(final[k])
                           if before[k].get(n) != final[k].get(n)}
        check("removed_back_to_factory", not diff and final["kit_version"] == "", {"diff": diff,
              "kit_version": final["kit_version"]}, severity="S2")
        res["leftover_user_files"] = final.get("user_files")
        res["summary"] = {"checks": len(res["checks"]), "failed": sum(not c["ok"] for c in res["checks"])}
        qa.write_json("qa_e.json", res)
        print("QA-E SUMMARY", res["summary"])
        return 1 if res["summary"]["failed"] else 0

    if __name__ == "__main__":
        sys.exit(main())
