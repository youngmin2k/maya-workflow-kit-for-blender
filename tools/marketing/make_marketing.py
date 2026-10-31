"""Marketing images: captioned feature screens, key visuals, icon.

    python tools/marketing/make_marketing.py [--blender PATH] [--no-build] [--no-shots] [--compose-only]

1. tools/marketing/fetch_assets.py checks the licensed models and the Inter font in the local assets folder
   (downloads what is missing; tools/marketing/assets.json, docs/distribution/marketing/CREDITS.md).
2. The extension zip is installed and enabled in a clean sandbox (tmp/marketing_env: the user's Blender settings are
   never read or written) and a GUI Blender (1920 x 1080 window) runs tools/marketing/shots.py:
   raw shots + meta.json in tmp/marketing/raw/. Only the Blender started here is killed on timeout.
3. tools/marketing/compose.py composites docs/distribution/marketing/screens/*.png, key_visual*.png, icon_256.png.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import build  # noqa: E402
import release_check  # noqa: E402

SANDBOX = ROOT / "tmp" / "marketing_env"
RAW = ROOT / "tmp" / "marketing" / "raw"
TIMEOUT = 1500


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--blender", default=os.environ.get("BLENDER", build.DEFAULT_BLENDER))
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--no-shots", action="store_true", help="reuse tmp/marketing/raw")
    args = ap.parse_args(argv)
    here = Path(__file__).resolve().parent
    if subprocess.run([sys.executable, str(here / "fetch_assets.py"), "--active"], stdin=subprocess.DEVNULL).returncode:
        return 1
    if not args.no_shots:
        zip_path = build.ext_zip()
        if not args.no_build or not zip_path.exists():
            zip_path = build.main(["--blender", args.blender, "--no-legacy"])
        env = release_check.sandbox_env(SANDBOX)
        rc, out = release_check.run([args.blender, "--command", "extension", "install-file", "-r",
                                     release_check.REPO_ID, "--enable", str(zip_path)], env)
        if rc:
            print(out[-3000:])
            return 1
        RAW.mkdir(parents=True, exist_ok=True)
        result, log = SANDBOX / "shots.json", SANDBOX / "shots.log"
        env["ALLSET_SHOTS"] = str(RAW)
        env["ALLSET_NO_WELCOME"] = "1"
        cmd = [args.blender, "--enable-event-simulate", "--window-geometry", "0", "0", "1920", "1080",
               "--python", str(here / "shots.py"), "--", str(result)]
        with open(log, "w", encoding="utf-8", errors="replace") as fh:
            proc = subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT)
            try:
                proc.wait(timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                proc.kill()  # only the Blender started here
        checks = json.loads(result.read_text(encoding="utf-8")) if result.exists() else \
            [{"name": f"shots.py wrote no results (see {log})", "ok": False}]
        ok = True
        for c in checks:
            print("PASS" if c["ok"] else "FAIL", c["name"])
            ok &= c["ok"]
        if not ok:
            return 1
    return subprocess.run([sys.executable, str(here / "compose.py")], stdin=subprocess.DEVNULL).returncode


if __name__ == "__main__":
    sys.exit(main())
