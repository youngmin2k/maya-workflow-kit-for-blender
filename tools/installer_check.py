"""Windows installer helper round trip: install -> Make Blender Maya -> uninstall restores all.

    python tools/installer_check.py [--blender PATH] [--no-build]

Runs tools/installer/allset_setup.ps1 (what the Inno Setup draft allset.iss calls) with Windows
PowerShell 5.1 on a clean sandbox (tmp/release_env_installer; BLENDER_USER_* point there and are
inherited by the Blender processes the script starts) after seeding a "user" setup
(tools/release_probe.py seed). The .exe itself is not built or signed here.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build  # noqa: E402
import release_check  # noqa: E402

SANDBOX = ROOT / "tmp" / "release_env_installer"
SCRIPT = ROOT / "tools" / "installer" / "allset_setup.ps1"
KEYS = ("active_keyconfig", "inputs", "undo_steps", "view", "theme")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--blender", default=os.environ.get("BLENDER", build.DEFAULT_BLENDER))
    ap.add_argument("--no-build", action="store_true")
    args = ap.parse_args(argv)
    zip_path = build.ext_zip()
    if not args.no_build or not zip_path.exists():
        zip_path = build.main(["--blender", args.blender, "--no-legacy"])

    env = release_check.sandbox_env(SANDBOX)
    env["ALLSET_NO_WELCOME"] = "1"
    probe = [args.blender, "-b", "--python", str(ROOT / "tools" / "release_probe.py"), "--"]
    ps = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT)]
    snap, results = {}, []

    def probe_snap(mode, name):
        release_check.run(probe + [mode, str(SANDBOX / f"{name}.json")], env)
        path = SANDBOX / f"{name}.json"
        snap[name] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        return snap[name]

    def setup(*extra):
        r = subprocess.run(ps + list(extra), env=env, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=600)
        print(f"--- allset_setup.ps1 {' '.join(extra[:1])} (exit {r.returncode})\n{(r.stdout + r.stderr).strip()[-1500:]}")
        return r.returncode

    before = probe_snap("seed", "before")
    if not before:
        print("FAIL seed a user setup")
        return 1

    record = SANDBOX / "targets.txt"      # what allset.iss keeps in {app} for the uninstaller
    rc = setup("-Install", "-Zip", str(zip_path), "-Blender", args.blender + ";", "-MakeMaya", "-Record", str(record))
    if rc == 3:
        print("SKIP: this Blender is running (close it to run the installer check)")
        return 1
    s = probe_snap("check", "installed")
    results.append((f"setup -Install -MakeMaya exits 0 (got {rc})", rc == 0))
    results.append(("installed into user_default and enabled", s and s["kit_version"] and
                    "bl_ext.user_default.allset" in s["addons"]))
    results.append((f"active keymap unchanged (got {s and s['active_keyconfig']})",
                    s and s["active_keyconfig"] == before["active_keyconfig"]))
    results.append(("Make Blender Maya applied (theme kept, splash off)", s and s["theme"] == before["theme"]
                    and s["view"]["show_splash"] == "False"))
    results.append(("the user's add-ons are kept", s and set(before["addons"]) < set(s["addons"])))
    recorded = record.read_text(encoding="utf-8-sig").splitlines() if record.exists() else []
    results.append((f"install records its Blender for the uninstaller ({len(recorded)} line)",
                    [os.path.normcase(p) for p in recorded] == [os.path.normcase(args.blender)]))

    rc = setup("-Uninstall", "-TargetsFile", str(record))
    s = probe_snap("check", "removed")
    diff = [k for k in KEYS if not s or s[k] != before[k]]
    results.append((f"setup -Uninstall exits 0 (got {rc})", rc == 0))
    results.append((f"uninstall restores the user's setup ({diff or 'all'})", not diff and s["kit_version"] == ""
                    and set(s["addons"]) == set(before["addons"])))
    rc = setup("-Uninstall", "-Blender", args.blender)
    results.append((f"a second uninstall is harmless (exit {rc})", rc == 0))

    bad = 0
    for name, good in results:
        print("PASS" if good else "FAIL", name)
        bad += not good
    print(f"{len(results) - bad}/{len(results)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
