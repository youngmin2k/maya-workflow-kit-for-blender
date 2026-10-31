"""Distribution round trip through a self-hosted extension repository.

    python tools/repo_check.py [--blender PATH] [--no-build]

Everything runs in a clean sandbox (tmp/release_env_repo: empty user config, scripts and
extensions) with a "user" setup seeded first (tools/release_probe.py seed: an add-on of
their own, changed navigation, undo steps and theme). The repository is a folder in the sandbox
served as ``file:///.../index.json`` — the same listing a static web host would serve
(tools/build_repo.py):

 1. repo-add + sync + ``extension install allset --enable`` (what "Add Remote Repository" +
    Install does in Preferences > Get Extensions)
 2. Make Blender Maya, then disable -> the user's setup is back
 3. enable, then a new version (same source, version + patch 1) is published to the repository:
    sync + ``extension update`` -> the installed version is the new one, still enabled, Maya keymap
 4. Remove in Maya mode from inside Blender (Preferences > Extensions > Remove) -> the user's setup is
    back, the package folder is gone; repo-remove -> no repository left
Only Blender processes started here run; nothing is uploaded.
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build  # noqa: E402
import build_repo  # noqa: E402
import release_check  # noqa: E402

SANDBOX = ROOT / "tmp" / "release_env_repo"
REPO_ID = "mayakit"      # repository module: the kit becomes bl_ext.mayakit.allset
KEYS = ("active_keyconfig", "inputs", "undo_steps", "view", "theme")


def next_version(version):
    major, minor, patch = (int(x) for x in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


def build_next(blender, out_dir):
    """The same source with the next patch version (what a release would publish)."""
    src = out_dir / "src_next" / "allset"
    if src.parent.exists():
        shutil.rmtree(src.parent)
    shutil.copytree(build.SRC, src, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    manifest = src / "blender_manifest.toml"
    version = next_version(build.manifest_value("version"))
    text = re.sub(r'^version\s*=\s*"[^"]+"', f'version = "{version}"', manifest.read_text(encoding="utf-8"),
                  count=1, flags=re.M)
    manifest.write_text(text, encoding="utf-8")
    out = build.ext_zip(version, out_dir)
    cmd = [blender, "--factory-startup", "--command", "extension", "build",
           "--source-dir", str(src), "--output-filepath", str(out)]
    rc, log = release_check.run(cmd, build.sandbox_env())
    if rc != 0 or not out.exists():
        raise SystemExit("building the next version failed:\n" + log[-2000:])
    return out, version


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--blender", default=os.environ.get("BLENDER", build.DEFAULT_BLENDER))
    ap.add_argument("--no-build", action="store_true")
    args = ap.parse_args(argv)
    blender = args.blender

    version = build.manifest_value("version")
    zip_path = build.ext_zip(version)
    if not args.no_build or not zip_path.exists():
        zip_path = build.main(["--blender", blender, "--no-legacy"])

    env = release_check.sandbox_env(SANDBOX)
    env["ALLSET_REPO"] = REPO_ID
    env["ALLSET_NO_WELCOME"] = "1"
    server = SANDBOX / "server"
    index = build_repo.main(["--blender", blender, "--out", str(server), "--zip", str(zip_path)])
    url = build_repo.file_url(index)
    # Repository sync needs online access even for file:// (bpy.app.online_access, else the sync poll fails).
    ext = [blender, "--online-mode", "--command", "extension"]
    probe = [blender, "-b", "--python", str(ROOT / "tools" / "release_probe.py"), "--"]
    snap = {}
    results = []

    def step(name, cmd, out_name=None):
        rc, log = release_check.run(cmd, env)
        if rc != 0:
            print(f"--- {name} (exit {rc})\n{log[-2500:]}")
        if out_name:
            path = SANDBOX / f"{out_name}.json"
            snap[out_name] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        return rc == 0

    def check(name, ok):
        results.append((name, bool(ok)))

    def same_as_before(name):
        s = snap.get(name)
        diff = [k for k in KEYS if not s or s[k] != snap["before"][k]]
        return diff, s

    step("seed", probe + ["seed", str(SANDBOX / "before.json")], "before")
    if not snap["before"]:
        print("FAIL seed a user setup")
        return 1

    step("offline_org", probe + ["offline_org", str(SANDBOX / "offline.json")], "offline")
    # 1. add the repository, install + enable from it
    ok = step("repo-add", ext + ["repo-add", REPO_ID, "--name", "Maya Workflow Kit (test repository)", "--url", url])
    ok &= step("sync", ext + ["sync"])
    ok &= step("install", ext + ["install", "allset", "--enable"])
    step("check", probe + ["check", str(SANDBOX / "installed.json")], "installed")
    s = snap["installed"]
    kit = f"bl_ext.{REPO_ID}.allset"
    check(f"add the repository ({url}) and install from it", ok and s and REPO_ID in s["repos"])
    check(f"installed version {s and s['kit_version']} == {version}, enabled", s and s["kit_version"] == version
          and kit in s["addons"])
    check("the user's add-ons and theme are kept", s and set(snap["before"]["addons"]) < set(s["addons"])
          and s["theme"] == snap["before"]["theme"])
    # installing + enabling changes nothing until the user opts in
    check(f"keymap untouched before the opt-in (got {s and s['active_keyconfig']})",
          s and s["active_keyconfig"] == snap["before"]["active_keyconfig"])

    # 2. Make Blender feel like Maya (the opt-in), then disable
    step("make", probe + ["make", str(SANDBOX / "made.json")], "made")
    check("Make Blender Maya keeps the user's theme",
          snap["made"] and snap["made"]["theme"] == snap["before"]["theme"])
    check(f"active keymap unchanged by the opt-in (got {snap['made'] and snap['made']['active_keyconfig']})",
          snap["made"] and snap["made"]["active_keyconfig"] == snap["before"]["active_keyconfig"])
    step("disable", probe + ["disable", str(SANDBOX / "disabled.json")], "disabled")
    diff, s = same_as_before("disabled")
    check(f"disable after Make Blender Maya restores the user's setup ({diff or 'all'})",
          not diff and kit not in s["addons"])

    # 3. enable again, publish the next version, update
    step("enable", probe + ["enable", str(SANDBOX / "enabled.json")], "enabled")
    nxt, nxt_version = build_next(blender, SANDBOX)
    build_repo.main(["--blender", blender, "--out", str(server), "--zip", str(nxt)])
    ok = step("sync", ext + ["sync"])
    ok &= step("update", ext + ["update"])
    step("check", probe + ["check", str(SANDBOX / "updated.json")], "updated")
    s = snap["updated"]
    check(f"update from the repository: {version} -> {s and s['kit_version']} (expected {nxt_version})",
          ok and s and s["kit_version"] == nxt_version)
    check("after the update the kit is still enabled (Maya mode as before the update: off after the re-enable)",
          s and kit in s["addons"] and s["active_keyconfig"] == snap["before"]["active_keyconfig"])

    # 4. Remove in Maya mode (inside Blender), then remove the repository
    step("make", probe + ["make", str(SANDBOX / "made2.json")], "made2")
    step("remove", probe + ["remove", str(SANDBOX / "removing.json")], "removing")
    step("check", probe + ["check", str(SANDBOX / "removed.json")], "removed")
    diff, s = same_as_before("removed")
    check(f"Remove in Maya mode restores the user's setup ({diff or 'all'})",
          not diff and snap["made2"] and snap["made2"]["kit_version"] and s["kit_version"] == "" and set(s["addons"]) == set(snap["before"]["addons"]))
    ok = step("repo-remove", ext + ["repo-remove", REPO_ID])
    step("check", probe + ["check", str(SANDBOX / "final.json")], "final")
    s = snap["final"]
    check("repo-remove leaves the repositories as before", ok and s and s["repos"] == snap["before"]["repos"])

    bad = 0
    for name, good in results:
        print("PASS" if good else "FAIL", name)
        bad += not good
    print(f"{len(results) - bad}/{len(results)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
