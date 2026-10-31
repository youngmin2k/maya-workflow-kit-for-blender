"""#191: in a real UI: the Maya Workflow Kit layout with a busy scene (a 102k-vertex grid skinned to a
120-bone chain + 600 cubes, the qa_perf scene). For a few seconds one cube is moved every 20 ms while the views
redraw; a profiler records every Python call in that time (timers, draw handlers, depsgraph handlers, panels).
The same is done again after the 600 cubes are deleted. Reported: kit Python time per 3D View redraw and the top kit
functions (``tmp/s286/profile_<tag>.txt``). Checked: the 600 extra objects add less than ``BUDGET_MS`` of kit Python
per 3D View redraw or ``BUDGET_SHARE`` of the few-objects figure when that is larger (time under the profiler, which slows Python down
by about 2x and varies by ~40 % with the machine's load; before the speed-up the 600 objects added 3.6 ms = 51 %)."""

import cProfile
import os
import pstats
import sys
import time
from pathlib import Path

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, setup, step, win  # noqa: E402

GUI_TIMEOUT = 240
ROOT = Path(__file__).resolve().parents[2]
TAG = os.environ.get("ALLSET_PROFILE_TAG", "current")
OUT = ROOT / "tmp" / "s286" / f"profile_{TAG}.txt"
BUDGET_MS = 1.0         # extra kit Python per 3D View redraw for 600 more objects (profiled time)
BUDGET_SHARE = 0.25
MOVES = 150
C = {}


def kit_file(path):
    p = path.replace("\\", "/")
    return "/allset/" in p and "/tests/" not in p


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    sys.path.insert(0, str(ROOT / "tests"))
    sys.path.insert(0, str(ROOT / "tools" / "qa"))
    import qa_perf
    qa_perf.build_scene()
    C["n"] = len(bpy.context.scene.objects)
    check(f"busy scene built ({C['n']} objects)", C["n"] > 600)


def _settle():
    for a in win().screen.areas:
        a.tag_redraw()


def _wait_icons():
    """Menu / shelf icons are made once after start (timers): not part of the timing. Wait until the menu icon
    timer is done (up to 40 ticks), then a few more redraws for the shelf icons."""
    import sim
    from importlib import import_module
    menu_icons = import_module(MODULE + ".ui.menu_icons")
    C["waits"] = C.get("waits", 0) + 1
    _settle()
    if bpy.app.timers.is_registered(menu_icons._tick) and C["waits"] < 40:
        sim._steps.insert(0, _wait_icons)


step(_wait_icons)
for _ in range(5):
    step(_settle)


def _start(phase, name):
    prof = cProfile.Profile()
    rec = C[phase] = {"prof": prof, "i": 0, "t0": time.perf_counter()}
    ob = bpy.data.objects[name]

    def mover():
        i = rec["i"]
        if i >= MOVES:
            rec["t1"] = time.perf_counter()
            prof.disable()
            return None
        ob.location.x = (i % 20) * 0.1
        for a in win().screen.areas:         # like a drag in the view: Blender's notifiers redraw the rest
            if a.type == 'VIEW_3D':
                a.tag_redraw()
        rec["i"] = i + 1
        return 0.02
    prof.enable()
    bpy.app.timers.register(mover, first_interval=0.02)


def _report(phase):
    rec = C[phase]
    if "t1" not in rec:
        rec["prof"].disable()
        rec["t1"] = time.perf_counter()
    wall = rec["t1"] - rec["t0"]
    st = pstats.Stats(rec["prof"])
    kit_total, rows, draws = 0.0, [], 0
    for (fname, line, func), (_cc, nc, tt, ct, _callers) in st.stats.items():
        if kit_file(fname) and fname.replace("\\", "/").endswith("ui/view_furniture.py") and func == "draw":
            draws = max(draws, nc)        # one call per 3D View region redraw (ViewCube / HUD)
        if kit_file(fname):
            kit_total += tt
            rows.append((ct, tt, f"{Path(fname).relative_to(Path(fname).parents[1])}:{line}({func})"))
    rows.sort(reverse=True)
    # per 3D View redraw, not per move: how often Blender redraws during the moves varies with the machine's load
    rec["draws"] = draws
    rec["per_move"] = kit_total * 1000 / max(draws, 1)
    rec["text"] = (f"{phase}: objects {len(bpy.context.scene.objects)} moves {rec['i']} wall {wall:.3f} s kit "
                   f"{kit_total * 1000:.1f} ms / {draws} view redraws = {rec['per_move']:.2f} ms per redraw\n"
                   + "".join(f"{ct * 1000:10.1f} {tt * 1000:9.1f}  {n}\n" for ct, tt, n in rows[:30]))
    check(f"{phase}: {rec['i']} moves done ({wall:.2f} s, kit {rec['per_move']:.2f} ms per view redraw)",
          rec["i"] >= MOVES and draws > 0)


def _wait():
    pass


@step
def s_start_many():
    _start("many", "c0")


for _ in range(12):          # 12 × 0.4 s: enough for 150 moves at 20 ms plus redraws
    step(_wait)


@step
def s_report_many():
    _report("many")
    shots = os.environ.get("ALLSET_GUI_SHOTS", "")
    if shots:
        with bpy.context.temp_override(window=win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(shots, "gui_step286_busy.png"))
    cubes = [o for o in bpy.data.objects if o.name.startswith("c") and o.name[1:].isdigit()]
    bpy.data.batch_remove(cubes)
    bpy.ops.mesh.primitive_cube_add(size=0.2)
    bpy.context.active_object.name = "mover"


for _ in range(5):
    step(_settle)


@step
def s_start_few():
    _start("few", "mover")


for _ in range(12):
    step(_wait)


@step
def s_report_few():
    _report("few")
    extra = C["many"]["per_move"] - C["few"]["per_move"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(f"tag {TAG} blender {bpy.app.version_string}; 600 more objects add {extra:.2f} ms kit Python per "
                 f"view redraw\ncumulative ms  self ms  function\n" + C["many"]["text"] + C["few"]["text"])
    print(f"PROFILE many {C['many']['per_move']:.2f} few {C['few']['per_move']:.2f} ms per view redraw -> {OUT}", flush=True)
    budget = max(BUDGET_MS, BUDGET_SHARE * C["few"]["per_move"])
    check(f"600 more objects add {extra:.2f} ms kit Python per view redraw (budget {budget:.2f} ms)", extra < budget)


run()
