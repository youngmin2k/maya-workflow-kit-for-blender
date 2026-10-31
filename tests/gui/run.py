"""GUI event-simulation tests.

    python tests/gui/run.py [-k PATTERN] [--no-build] [--shots DIR] [--ui-scale 0.8]
    python tests/gui/run.py -k PATTERN --blenders 5.0.1,5.1.2,5.2.3   # the same files on several Blenders

Builds and installs the extension into the same sandbox as tests/run.py,
then runs each tests/gui/gui_*.py in a GUI Blender started with
``--factory-startup --enable-event-simulate`` (real mouse/keyboard input is
ignored, a window appears briefly). Only the Blender process started here is
terminated on timeout. Prints PASS/FAIL per check; exit 1 on any failure.
``--ui-scale`` sets Preferences > Interface > Resolution Scale for every test (also after
a template switch, which reloads factory preferences); 0.8 = the Maya density preset on a
125 % display.
``--blenders`` (step 279, release smoke): one run per portable Blender
(``%LOCALAPPDATA%/allset_blenders/blender-<ver>-windows-x64/blender.exe``, or a path), one after the other, each in
its own sandbox ``<ALLSET_SANDBOX or test_env>_<ver>``; the extension is built once.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
import run as headless  # noqa: E402

PORTABLE = Path(os.environ.get("ALLSET_BLENDERS",
                               os.path.join(os.environ.get("LOCALAPPDATA", ""), "allset_blenders")))


def blender_exe(ver):
    """A version like 5.1.2 -> its portable build's blender.exe; anything with a path separator is a path."""
    if "/" in ver or "\\" in ver:
        return ver
    return str(PORTABLE / f"blender-{ver}-windows-x64" / "blender.exe")


def run_matrix(args):
    """Run this runner once per Blender in ``args.blenders``, one after the other (one Blender at a time)."""
    if not args.no_build:
        headless.build.main(["--blender", args.blender, "--no-legacy"])
    base = os.environ.get("ALLSET_SANDBOX", "test_env")
    summary, worst = [], 0
    for n, ver in enumerate(v.strip() for v in args.blenders.split(",") if v.strip()):
        exe = blender_exe(ver)
        tag = ver if exe != ver else str(n)
        if not Path(exe).exists():
            print(f"MISSING  {ver}: {exe}")
            summary.append((ver, "missing"))
            worst = 1
            continue
        env = dict(os.environ, ALLSET_SANDBOX=f"{base}_{tag}")
        cmd = [sys.executable, str(Path(__file__).resolve()), "--no-build", "--blender", exe, "-k", args.k,
               "--dir", args.dir]
        if args.ui_scale:
            cmd += ["--ui-scale", str(args.ui_scale)]
        if args.include_skipped:
            cmd.append("--include-skipped")
        print(f"\n=== Blender {ver} (sandbox tmp/{env['ALLSET_SANDBOX']}) ===", flush=True)
        code = subprocess.call(cmd, env=env, stdin=subprocess.DEVNULL)
        summary.append((ver, "ok" if code == 0 else "FAILED"))
        worst = worst or code
    print("\nBlender matrix:")
    for ver, text in summary:
        print(f"  {ver}: {text}")
    return 1 if worst else 0


# per-file limit: a hung Blender is killed and reported as TIMEOUT, the run goes on with the next file
TIMEOUT = int(os.environ.get("ALLSET_GUI_TIMEOUT", "180"))


def file_timeout(path):
    """A test file may ask for more time with a top-level ``GUI_TIMEOUT = <seconds>`` line (long sweeps)."""
    m = re.search(r"^GUI_TIMEOUT\s*=\s*(\d+)", path.read_text(encoding="utf-8"), re.M)
    return max(int(m.group(1)), TIMEOUT) if m else TIMEOUT


def skip_reason(path):
    """A quarantined file has a top-level ``GUI_SKIP = "<reason>"`` line (step 141): it hangs or fails only for
    environment reasons; it is left out unless --include-skipped and its checks are done by hand."""
    m = re.search(r"^GUI_SKIP\s*=\s*[\"'](.+)[\"']", path.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else ""


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run Maya Workflow Kit GUI event tests")
    ap.add_argument("-k", default="", help="only files whose name contains this (comma-separated: any)")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--shots", default="", help="directory for screenshots")
    ap.add_argument("--ui-scale", type=float, default=0.0, help="view.ui_scale for all tests")
    ap.add_argument("--dir", default=str(HERE), help="folder of gui_*.py files (audit repro scripts: tests/gui/audit128)")
    ap.add_argument("--blender", default=os.environ.get("BLENDER", headless.build.DEFAULT_BLENDER))
    ap.add_argument("--include-skipped", action="store_true", help="also run files marked GUI_SKIP")
    ap.add_argument("--blenders", default="", help="comma-separated Blender versions (portable builds) or paths: "
                                                   "run the selected files on each, one after the other")
    headless.add_order_args(ap)
    args = ap.parse_args(argv)
    if args.blenders:
        return run_matrix(args)

    if args.zip:
        zip_path = Path(args.zip).resolve()
    elif args.no_build:
        zip_path = headless.build.ext_zip()
    else:
        zip_path = headless.build.main(["--blender", args.blender, "--no-legacy"])
    env = headless.make_sandbox()
    env["ALLSET_NO_WELCOME"] = "1"   # the first-start dialog would eat the simulated events (step 42)
    headless.install(args.blender, zip_path, env)
    if args.ui_scale:
        env["ALLSET_GUI_UI_SCALE"] = str(args.ui_scale)
    if args.shots:
        Path(args.shots).mkdir(parents=True, exist_ok=True)
        env["ALLSET_GUI_SHOTS"] = str(Path(args.shots).resolve())

    env["PYTHONUNBUFFERED"] = "1"     # a Blender killed on timeout keeps what it printed
    passed = failed = skipped = timeouts = 0
    files = headless.order(sorted(p for p in Path(args.dir).resolve().glob("gui_*.py")
                                  if any(k in p.name for k in args.k.split(","))), args)
    for path in files:
        reason = skip_reason(path)
        if reason and not args.include_skipped:
            print(f"SKIP  {path.stem}: {reason}")
            skipped += 1
            continue
        out = headless.SANDBOX / "results" / f"{path.stem}.json"
        log = headless.SANDBOX / "logs" / f"{path.stem}.log"
        cmd = [args.blender, "--factory-startup", "--enable-event-simulate", *os.environ.get("ALLSET_GUI_ARGS", "").split(),
               # ALLSET_GUI_GEOMETRY="2048 0 1600 900": open the window on a second monitor
               "--window-geometry", *os.environ.get("ALLSET_GUI_GEOMETRY", "0 0 1600 900").split(),
               "--python", str(path), "--", str(out)]
        with headless.blender_slots.slot(f"gui {path.stem}"), \
                open(log, "w", encoding="utf-8", errors="replace") as fh:
            proc = subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL,
                                    stdout=fh, stderr=subprocess.STDOUT)
            timed_out = False
            try:
                proc.wait(timeout=file_timeout(path))
            except subprocess.TimeoutExpired:
                proc.kill()  # only the Blender we started
                timed_out = True
        timeouts += timed_out
        results = json.loads(out.read_text(encoding="utf-8")) if out.exists() else \
            [{"name": f"TIMEOUT after {file_timeout(path)} s" if timed_out else "<no result file>", "ok": False}]
        for r in results:
            print(f"{'PASS' if r['ok'] else 'FAIL'}  {path.stem}::{r['name']}")
            passed += r["ok"]
            failed += not r["ok"]
        print(f"      (log: {log.relative_to(ROOT)})")

    print(f"\n{passed} passed, {failed} failed, {len(files)} file(s)"
          + (f", {timeouts} timed out" if timeouts else "") + (f", {skipped} skipped (GUI_SKIP)" if skipped else ""))
    return 1 if failed or not files else 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    import hidden_desktop  # noqa: E402  (test Blenders never show on screen)
    hidden_desktop.ensure_hidden()
    sys.exit(main())
