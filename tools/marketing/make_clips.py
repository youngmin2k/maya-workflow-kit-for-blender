"""Marketing clips: feature clips (MP4 + GIF) and the 30-45 s trailer.

    python tools/marketing/make_clips.py [--blender PATH] [--no-build] [--only a,b] [--no-record] [--no-encode]

1. tools/marketing/fetch_assets.py checks the licensed models (CREDITS.md).
2. The extension is installed in a clean sandbox (tmp/marketing_env; the user's Blender settings are never read or
   written) and, per clip, a GUI Blender (1920 x 1080 window, --enable-event-simulate) runs
   tools/marketing/clips.py: frames + timeline.json in tmp/marketing/clips/<name>/. Only the Blender started here is
   killed on timeout.
3. tools/marketing/clip_compose.py draws cursor / clicks / key chips / caption band and encodes with ffmpeg:
   docs/distribution/marketing/clips/<nn>_<name>.mp4 (store previews), gif/<nn>_<name>.gif (README / social),
   trailer.mp4.
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

HERE = Path(__file__).resolve().parent
SANDBOX = ROOT / "tmp" / "marketing_env"
FRAMES = ROOT / "tmp" / "marketing" / "clips"
TIMEOUT = 900
ORDER = ["hotbox", "marking_menu", "channel_box_keys", "navigation", "pivot_snap", "rigging", "switch"]


def record(blender, name, env):
    result, log = SANDBOX / f"clip_{name}.json", SANDBOX / f"clip_{name}.log"
    result.unlink(missing_ok=True)
    env = dict(env, ALLSET_CLIP=name, ALLSET_CLIP_OUT=str(FRAMES), ALLSET_NO_WELCOME="1")
    cmd = [blender, "--enable-event-simulate", "--window-geometry", "0", "0", "1920", "1080",
           "--python", str(HERE / "clips.py"), "--", str(result)]
    with open(log, "w", encoding="utf-8", errors="replace") as fh:
        proc = subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT)
        try:
            proc.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()  # only the Blender started here
    checks = json.loads(result.read_text(encoding="utf-8")) if result.exists() else \
        [{"name": f"clips.py wrote no results (see {log})", "ok": False}]
    ok = True
    for c in checks:
        print(" ", "PASS" if c["ok"] else "FAIL", c["name"])
        ok &= c["ok"]
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--blender", default=os.environ.get("BLENDER", build.DEFAULT_BLENDER))
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--only", default="", help="comma-separated clip names")
    ap.add_argument("--no-record", action="store_true", help="reuse tmp/marketing/clips")
    ap.add_argument("--no-encode", action="store_true")
    args = ap.parse_args(argv)
    names = [n for n in args.only.split(",") if n] or ORDER
    if subprocess.run([sys.executable, str(HERE / "fetch_assets.py"), "--active"], stdin=subprocess.DEVNULL).returncode:
        return 1
    ok = True
    if not args.no_record:
        zip_path = build.ext_zip()
        if not args.no_build or not zip_path.exists():
            zip_path = build.main(["--blender", args.blender, "--no-legacy"])
        env = release_check.sandbox_env(SANDBOX)
        rc, out = release_check.run([args.blender, "--command", "extension", "install-file", "-r",
                                     release_check.REPO_ID, "--enable", str(zip_path)], env)
        if rc:
            print(out[-3000:])
            return 1
        for name in names:
            print("record", name)
            ok &= record(args.blender, name, env)
    if args.no_encode:
        return 0 if ok else 1
    cmd = [sys.executable, str(HERE / "clip_compose.py")] + (["--only", args.only] if args.only else [])
    return subprocess.run(cmd, stdin=subprocess.DEVNULL).returncode or (0 if ok else 1)


if __name__ == "__main__":
    sys.exit(main())
