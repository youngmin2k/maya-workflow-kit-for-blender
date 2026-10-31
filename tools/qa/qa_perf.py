"""QA activity G: relative performance budget on a heavy scene, kit off / on (Maya mode) / off again.

Headless test module (tests/_bootstrap.py runs it; it enables the kit itself):

    python tests/run.py --no-build -k __none__ --extra tools/qa/qa_perf.py                     # current build
    ALLSET_SANDBOX=qa_g050 QA_TAG=0.5.0 python tests/run.py -k __none__ --zip dist/maya-workflow-kit-0.5.0.zip \
        --extra tools/qa/qa_perf.py                                                          # previous release
    python tools/qa/qa_perf_compare.py                                                       # verdict

Scene: a 102k-vertex grid skinned to a 120-bone chain keyed over 250 frames, plus 600 linked cubes. Timed: frame
changes (playback without drawing), depsgraph updates from a moved object, selection changes, edit mode in / out,
save + open. The kit's own handlers are wrapped while it is on: cumulative time per handler (top 10).
Budget (#191: update / select tightened from +5 ms to +2 ms): on / off ratio —
frame ≤ 1 / 0.85 (or ≤ +2 ms), update handlers ≤ +2 ms median, selection change ≤ +2 ms median, open ≤ 1.3× (or
≤ +250 ms).
"""

import ctypes
import json
import os
import statistics
import time
from pathlib import Path

import bpy

import kit

AUTO_ENABLE = False
ROOT = Path(__file__).resolve().parents[2]
TAG = os.environ.get("QA_TAG", "current")
OUT = ROOT / "tmp" / "qa240" / f"qa_g_{TAG}_{bpy.app.version_string.split()[0]}.json"
GRID = 319          # (GRID + 1)^2 = 102 400 vertices
BONES = 120
CUBES = 600
RESULT = {"tag": TAG, "blender": bpy.app.version_string, "phases": {}}


def working_set_mb():
    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + \
                   [(n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                                   "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                                   "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    try:
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        k32.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(PMC), ctypes.c_ulong]
        if not k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
            return None
        return round(pmc.WorkingSetSize / 2 ** 20, 1)
    except Exception:
        return None


def build_scene():
    # not read_factory_settings: it reloads preferences and would switch the kit off
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.armatures, bpy.data.actions):
        bpy.data.batch_remove(list(coll))
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=GRID, y_subdivisions=GRID, size=20)
    grid = bpy.context.active_object
    grid.name = "heavy"
    arm_data = bpy.data.armatures.new("rig")
    arm = bpy.data.objects.new("rig", arm_data)
    scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    prev = None
    for i in range(BONES):
        b = arm_data.edit_bones.new(f"b{i}")
        x = -10 + 20 * i / BONES
        b.head, b.tail = (x, 0, 0), (x + 20 / BONES, 0, 0)
        if prev:
            b.parent, b.use_connect = prev, True
        prev = b
    bpy.ops.object.mode_set(mode='OBJECT')
    import numpy as np
    co = np.empty(len(grid.data.vertices) * 3)
    grid.data.vertices.foreach_get("co", co)
    xs = co[0::3]
    band = np.clip(((xs + 10) / 20 * BONES).astype(int), 0, BONES - 1)
    for i in range(BONES):
        vg = grid.vertex_groups.new(name=f"b{i}")
        idx = np.nonzero(band == i)[0].tolist()
        if idx:
            vg.add(idx, 1.0, 'REPLACE')
    md = grid.modifiers.new("skin", 'ARMATURE')
    md.object = arm
    for i, pb in enumerate(arm.pose.bones):
        pb.rotation_mode = 'XYZ'
        for f, a in ((1, 0.0), (125, 0.05), (250, 0.0)):
            pb.rotation_euler.z = a * ((i % 5) - 2)
            pb.keyframe_insert("rotation_euler", frame=f)
    cube = bpy.data.meshes.new("c")
    cube.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
    for i in range(CUBES):
        o = bpy.data.objects.new(f"c{i}", cube)
        o.location = (i % 30, i // 30, 5)
        scene.collection.objects.link(o)
    scene.frame_start, scene.frame_end = 1, 250
    bpy.context.view_layer.objects.active = grid
    grid.select_set(True)
    bpy.context.view_layer.update()
    return grid


HTIMES = {}


def wrap_kit_handlers():
    wrapped = []
    for name in dir(bpy.app.handlers):
        lst = getattr(bpy.app.handlers, name)
        if not isinstance(lst, list):
            continue
        for i, fn in enumerate(list(lst)):
            if not getattr(fn, "__module__", "").startswith(kit.MODULE):
                continue
            key = f"{name}:{fn.__module__.rsplit('.', 1)[-1]}.{fn.__name__}"

            def w(*a, _fn=fn, _key=key):
                t = time.perf_counter()
                try:
                    return _fn(*a)
                finally:
                    rec = HTIMES.setdefault(_key, [0.0, 0])
                    rec[0] += time.perf_counter() - t
                    rec[1] += 1
            if hasattr(fn, "_bpy_persistent"):
                w = bpy.app.handlers.persistent(w)
            lst[i] = w
            wrapped.append((lst, i, fn))
    return wrapped


def unwrap(wrapped):
    for lst, i, fn in wrapped:
        if i < len(lst):
            lst[i] = fn


def kit_handler_count():
    n = 0
    for name in dir(bpy.app.handlers):
        lst = getattr(bpy.app.handlers, name)
        if isinstance(lst, list):
            n += sum(1 for f in lst if getattr(f, "__module__", "").startswith(kit.MODULE))
    return n


def measure(phase):
    grid = build_scene()
    scene = bpy.context.scene
    r = {"kit_handlers": kit_handler_count(), "mem_before_mb": working_set_mb()}
    wrapped = wrap_kit_handlers() if phase == "on" else []
    HTIMES.clear()

    frames = []
    for f in range(1, 121):
        t = time.perf_counter()
        scene.frame_set(f)
        frames.append(time.perf_counter() - t)
    r["frame_ms_median"] = round(statistics.median(frames) * 1000, 2)

    ups = []
    cube = bpy.data.objects["c0"]
    for i in range(150):
        cube.location.x = i * 0.01
        t = time.perf_counter()
        bpy.context.view_layer.update()
        ups.append(time.perf_counter() - t)
    r["update_ms_median"] = round(statistics.median(ups) * 1000, 3)

    sels = []
    objs = [bpy.data.objects[f"c{i}"] for i in range(200)]
    for o in objs:
        t = time.perf_counter()
        o.select_set(not o.select_get())
        bpy.context.view_layer.update()
        sels.append(time.perf_counter() - t)
    r["select_ms_median"] = round(statistics.median(sels) * 1000, 3)

    bpy.context.view_layer.objects.active = grid
    edits = []
    for _ in range(3):
        t = time.perf_counter()
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.object.mode_set(mode='OBJECT')
        edits.append(time.perf_counter() - t)
    r["edit_toggle_ms_median"] = round(statistics.median(edits) * 1000, 1)

    handler_top = sorted(((k, round(v[0] * 1000, 2), v[1]) for k, v in HTIMES.items()), key=lambda x: -x[1])[:10]
    r["kit_handler_top_ms"] = handler_top
    unwrap(wrapped)

    path = ROOT / "tmp" / "qa240" / f"perf_{TAG}_{phase}.blend"
    path.parent.mkdir(parents=True, exist_ok=True)
    t = time.perf_counter()
    bpy.ops.wm.save_mainfile(filepath=str(path))
    r["save_ms"] = round((time.perf_counter() - t) * 1000, 1)
    t = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(path))
    r["open_ms"] = round((time.perf_counter() - t) * 1000, 1)
    r["mem_after_mb"] = working_set_mb()
    RESULT["phases"][phase] = r
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(RESULT, indent=1), encoding="utf-8")
    print(phase, json.dumps(r), flush=True)


def test_off_before():
    measure("off")


def test_on_maya_mode():
    kit.enable(maya=True)
    measure("on")


def test_off_after_disable():
    kit.disable()
    measure("off2")
    assert kit_handler_count() == 0, "kit handlers left after disable"


def test_budget():
    p = RESULT["phases"]
    off = {k: min(p["off"][k], p["off2"][k]) for k in ("frame_ms_median", "update_ms_median", "select_ms_median",
                                                       "open_ms")}
    on = p["on"]
    RESULT["ratios"] = {k: round(on[k] / off[k], 2) if off[k] else None for k in off}
    OUT.write_text(json.dumps(RESULT, indent=1), encoding="utf-8")
    print("ratios", RESULT["ratios"], flush=True)
    problems = []
    # ratios of ~2 ms numbers are mostly noise: a budget fails only past an absolute floor too
    if on["frame_ms_median"] > off["frame_ms_median"] / 0.85 and on["frame_ms_median"] - off["frame_ms_median"] > 2:
        problems.append(f"frame {on['frame_ms_median']} ms vs {off['frame_ms_median']} ms off (budget 1/0.85)")
    if on["update_ms_median"] - off["update_ms_median"] > 2:
        problems.append(f"update +{on['update_ms_median'] - off['update_ms_median']:.2f} ms (budget 2 ms)")
    if on["select_ms_median"] - off["select_ms_median"] > 2:
        problems.append(f"select +{on['select_ms_median'] - off['select_ms_median']:.2f} ms (budget 2 ms)")
    if on["open_ms"] > 1.3 * off["open_ms"] and on["open_ms"] - off["open_ms"] > 250:
        problems.append(f"open {on['open_ms']} ms vs {off['open_ms']} ms off (budget 1.3x)")
    assert not problems, "; ".join(problems)
