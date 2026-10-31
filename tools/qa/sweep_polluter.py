"""QA activity A': find which earlier manual-sweep group makes a later sweep check fail (order dependence).

    python tools/qa/sweep_polluter.py --victim m59_4 [--check "[M59-4]"] [--blender PATH] [--max-runs 10]

tests/gui/gui_manual_sweep.py runs ~200 groups (step names "m<step>_<n>_...") in one GUI Blender; ALLSET_SWEEP_ONLY
keeps the setup steps + the listed prefixes. 1) victim alone (3 runs): must pass, 2) all groups before the victim +
the victim: must fail (else: not reproduced), 3) bisect the earlier groups, keeping the half that still fails.
Each run ≈ 20 s + the groups' time, one Blender slot. Results: tmp/qa240/sweep_polluter.json.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SWEEP = ROOT / "tests" / "gui" / "gui_manual_sweep.py"
OUT = ROOT / "tmp" / "qa240" / "sweep_polluter.json"


def groups():
    names = re.findall(r'(?:^def |named\(\s*f?"|drag\(\s*f?")(m\d+_\d+)', SWEEP.read_text(encoding="utf-8"), re.M)
    out = []
    for n in names:
        if n not in out:
            out.append(n)
    return out


def run(prefixes, check, blender):
    """Return (victim checks passed?, failing check names)."""
    env = os.environ.copy()
    env["ALLSET_SWEEP_ONLY"] = ",".join(p + "_" for p in prefixes)
    env["ALLSET_SANDBOX"] = "qa_sweep"
    env["ALLSET_GUI_FULL"] = "1"
    cmd = [sys.executable, str(ROOT / "tests" / "gui" / "run.py"), "--no-build", "-k", "manual_sweep",
           "--blender", blender]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    fails = [ln[6:] for ln in r.stdout.splitlines() if ln.startswith("FAIL")]
    bad = [f for f in fails if check in f or "TIMEOUT" in f or "no result" in f]
    return not bad, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--victim", required=True, help="group prefix, e.g. m59_4")
    ap.add_argument("--check", default="", help="text in the failing check name (default [M<victim>])")
    ap.add_argument("--blender", default=os.environ.get("BLENDER", os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "allset_blenders", "blender-5.2.3-windows-x64", "blender.exe")))
    ap.add_argument("--max-runs", type=int, default=12)
    args = ap.parse_args()
    check = args.check or "[M" + args.victim[1:].replace("_", "-") + "]"
    gs = groups()
    before = gs[:gs.index(args.victim)]
    log = {"victim": args.victim, "check": check, "groups_before": len(before), "runs": []}

    def go(prefixes, why):
        ok, bad = run(prefixes + [args.victim], check, args.blender)
        log["runs"].append({"why": why, "n": len(prefixes), "first": prefixes[:1], "last": prefixes[-1:], "ok": ok,
                            "bad": bad})
        OUT.write_text(json.dumps(log, indent=1), encoding="utf-8")
        print(why, len(prefixes), "groups ->", "PASS" if ok else f"FAIL {bad}", flush=True)
        return ok

    alone = [go([], f"alone {i}") for i in range(3)]
    if not all(alone):
        log["verdict"] = "fails alone too: non-deterministic (NOD), not order-dependent"
    elif go(before, "all before"):
        log["verdict"] = "not reproduced with every earlier group (passes in sweep order now)"
    else:
        cand = before
        runs = 0
        while len(cand) > 1 and runs < args.max_runs:
            half = cand[len(cand) // 2:]          # nearer groups first: state leaks are usually recent
            runs += 1
            if not go(half, "bisect late half"):
                cand = half
                continue
            runs += 1
            if not go(cand[:len(cand) // 2], "bisect early half"):
                cand = cand[:len(cand) // 2]
                continue
            log["verdict"] = f"needs groups from both halves of {len(cand)} (interaction) — {cand[0]} .. {cand[-1]}"
            break
        else:
            log["verdict"] = f"polluter: {cand}" if len(cand) == 1 else f"narrowed to {cand} (run cap)"
        log["candidates"] = cand
    OUT.write_text(json.dumps(log, indent=1), encoding="utf-8")
    print(log["verdict"])


if __name__ == "__main__":
    main()
