"""QA activity J: mutation sample — do the green tests really guard the changed code?

    python tools/qa/qa_mutants.py [--only N,M] [--blender PATH]

Installs the current dist zip once into the sandbox tmp/qa_j (tests/run.py helpers, Blender slots), then for each
mutant edits the *installed* copy of one source line (the repository is never touched), runs the related test files
headless and restores the line. A mutant that survives (every related test passes) marks behaviour no test guards.
Results: tmp/qa240/qa_j.json.
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("ALLSET_SANDBOX", "qa_j")
sys.path.insert(0, str(ROOT / "tests"))
import run as headless  # noqa: E402

PKG = headless.SANDBOX / "extensions" / headless.REPO_ID / headless.PKG_ID

# (file in the package, exact original text, mutated text, test file patterns)
MUTANTS = [
    ("operators/snap_align.py", "        if not getattr(ts, flag):", "        if getattr(ts, flag):", "step220"),
    ("operators/snap_align.py", "    if not other_snaps_on(ts):\n        return 0", "    if other_snaps_on(ts):\n        return 0",
     "step220"),
    ("ui/status_line.py", "    return elements is not None and ts.use_snap and elements <= set(ts.snap_elements)",
     "    return elements is not None and elements <= set(ts.snap_elements)", "step220,status_line,step240"),
    ("operators/bevel_maya.py", "                ent[1] = min(ent[1], sin)", "                ent[1] = max(ent[1], sin)",
     "step239,bevel"),
    ("operators/bevel_maya.py", "s.calc_length() * sin / len(ends)", "s.calc_length() * sin", "step239,bevel"),
    ("operators/anim_layers.py", "            acc = (1.0 - w) * acc + w * x", "            acc = acc + w * x",
     "anim_layer,step234,step240"),
    ("operators/anim_layers.py", "            acc = acc + w * x", "            acc = acc + x", "anim_layer,step234,step240"),
    ("operators/anim_layers.py", "    return Quaternion(axis, angle * w)", "    return Quaternion(axis, angle)",
     "step234,step240"),
    ("operators/control_shapes.py", 'or ob.data.get("rig_id"):', ':', "step236"),
    ("operators/joints.py", "        if not b.use_connect:\n            continue", "        if b.use_connect:\n            continue",
     "step233"),
    ("ui/four_view.py", "        row = 0 if a.y + a.height / 2 > cy else 1", "        row = 0 if a.y + a.height / 2 < cy else 1",
     "step237"),
    ("ui/four_view.py", "    if len(areas) != 4:\n        return {}", "    if len(areas) < 3:\n        return {}", "step237"),
    ("operators/fbx_skeleton.py", "            if p.use_deform:\n                parent = p.name\n                break",
     "            if p.use_deform:\n                parent = None\n                break", "step236"),
    ("operators/fbx_skeleton.py", 'twin = next((n for n in ("DEF-" + base, base) if n in deform and n not in below), None)',
     'twin = None', "step236"),
    ("operators/driven_key.py", "        if seen is None or abs(c.get() - seen) < 1e-9:",
     "        if seen is None or abs(c.get() - seen) >= 1e-9:", "step238,driven"),
    ("operators/skin.py", "        todo[0:0] = list(b.children)", "        todo.extend(b.children)", "step238"),
    ("operators/skin.py", "    todo = [b for b in mod.object.data.bones if b.parent is None]",
     "    todo = list(mod.object.data.bones)[::-1]", "step238"),
    ("operators/history.py", "        rec = extrude.RECORDS.pop(ob.name, None)", "        rec = extrude.RECORDS.get(ob.name, None)",
     "step239,history"),
    ("operators/anim_layers.py", "            acc = acc * (x ** w if x > 0 else 0.0)", "            acc = acc * x",
     "anim_layer,step234,step240"),
    ("operators/bevel_maya.py", "                if s is e or (s in sel and not faces.intersection(s.link_faces)):",
     "                if s is e:", "step239,bevel"),
]


def test_files(patterns):
    pats = patterns.split(",")
    return sorted(p for p in headless.TESTS.glob("test_*.py") if any(k in p.name for k in pats))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--blender", default=os.environ.get("BLENDER", headless.build.DEFAULT_BLENDER))
    args = ap.parse_args()
    env = headless.make_sandbox()
    headless.install(args.blender, headless.build.ext_zip(), env)
    picks = [int(i) for i in args.only.split(",") if i] or range(len(MUTANTS))
    out = []
    for i in picks:
        rel, old, new, pats = MUTANTS[i]
        path = PKG / rel
        src = path.read_text(encoding="utf-8")
        if src.count(old) != 1:
            out.append({"i": i, "file": rel, "status": f"SKIP (original text found {src.count(old)} times)"})
            print(out[-1], flush=True)
            continue
        path.write_text(src.replace(old, new), encoding="utf-8")
        killed_by, ran = [], []
        try:
            for f in test_files(pats):
                results, _log, _dt = headless.run_test_file(args.blender, f, env)
                ran.append(f.stem)
                if not all(r["ok"] for r in results):
                    killed_by.append(f.stem)
                    break
        finally:
            path.write_text(src, encoding="utf-8")
        status = "KILLED" if killed_by else ("NO TESTS" if not ran else "SURVIVED")
        out.append({"i": i, "file": rel, "old": old.strip()[:90], "new": new.strip()[:90], "status": status,
                    "killed_by": killed_by, "tests": ran})
        print(i, status, rel, killed_by or ran, flush=True)
    res = ROOT / "tmp" / "qa240" / "qa_j.json"
    res.parent.mkdir(parents=True, exist_ok=True)
    killed = sum(o["status"] == "KILLED" for o in out)
    res.write_text(json.dumps({"killed": killed, "total": len(out), "mutants": out}, indent=1), encoding="utf-8")
    print(f"mutation score {killed} / {len(out)}")


if __name__ == "__main__":
    main()
