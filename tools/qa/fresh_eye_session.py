"""In-Blender part of tools/qa/fresh_eye.py (QA activity H): replay QA_ACTIONS, one action per tick,
a screenshot of the window after each, kit reports / Python errors / an optional state dump into QA_OUT/log.json."""

import io
import json
import os
import sys
from importlib import import_module
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "gui"))
import sim  # noqa: E402
from sim import MODULE, ev, step, view3d, win  # noqa: E402

OUT = Path(os.environ["QA_OUT"])
ACTIONS = json.loads(Path(os.environ["QA_ACTIONS"]).read_text(encoding="utf-8"))
LOG = []
ERR = []


class Tee(io.TextIOBase):
    def __init__(self, base):
        self.base = base

    def write(self, s):
        if any(k in s for k in ("Traceback", "Error", "error:")):
            ERR.append(s.strip()[:300])
        return self.base.write(s)

    def flush(self):
        self.base.flush()


sys.stderr = Tee(sys.stderr)


def point(p):
    if p == "view" or p is None:
        _area, region = view3d()
        return region.x + region.width // 2, region.y + region.height // 2
    return int(p[0]), int(p[1])


def mods(a):
    return {k: True for k in ("shift", "ctrl", "alt") if a.get(k)}


def result_text():
    try:
        return import_module(MODULE + ".command_line")._result["text"]
    except Exception:
        return ""


def state():
    ctx = bpy.context
    ob = ctx.view_layer.objects.active
    s = {"mode": ctx.mode, "frame": ctx.scene.frame_current,
         "selected": [o.name for o in ctx.scene.objects if o.select_get()][:20],
         "active": ob.name if ob else None,
         "objects": [f"{o.name}:{o.type}" for o in ctx.scene.objects][:40],
         "result_field": result_text()}
    if ob:
        k = import_module(MODULE + ".operators.units").maya_unit() or 1.0
        s["translate"] = [round(v / k, 4) for v in ob.location]
        s["rotate_deg"] = [round(v * 57.29578, 3) for v in ob.rotation_euler]
        s["scale"] = [round(v, 4) for v in ob.scale]
    try:
        area, _region = view3d()
        with ctx.temp_override(window=win(), screen=win().screen, area=area):
            s["tool"] = ctx.workspace.tools.from_space_view3d_mode(ctx.mode).idname
    except Exception:
        pass
    return s


def run_action(a):
    rec = {"action": a}
    if "key" in a:
        x, y = point(a.get("at", "view"))
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
        ev(a["key"], 'PRESS', x=x, y=y, **mods(a))
        if not a.get("hold"):
            ev(a["key"], 'RELEASE', x=x, y=y, **mods(a))
    elif "click" in a:
        x, y = point(a["click"])
        b = a.get("button", "LEFTMOUSE")
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
        ev(b, 'PRESS', x=x, y=y, **mods(a))
        ev(b, 'RELEASE', x=x, y=y, **mods(a))
    elif "drag" in a:
        (x0, y0), (x1, y1) = point(a["drag"][0]), point(a["drag"][1])
        b = a.get("button", "LEFTMOUSE")
        ev('MOUSEMOVE', 'NOTHING', x=x0, y=y0)
        ev(b, 'PRESS', x=x0, y=y0, **mods(a))
        for i in range(1, 7):
            ev('MOUSEMOVE', 'NOTHING', x=x0 + (x1 - x0) * i // 6, y=y0 + (y1 - y0) * i // 6, **mods(a))
        ev(b, 'RELEASE', x=x1, y=y1, **mods(a))
    elif "press" in a:
        x, y = point(a["press"])
        ev(a.get("button", "LEFTMOUSE"), 'PRESS', x=x, y=y, **mods(a))
    elif "release" in a:
        x, y = point(a["release"])
        ev(a.get("button", "LEFTMOUSE"), 'RELEASE', x=x, y=y, **mods(a))
    elif "move" in a:
        x, y = point(a["move"])
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y, **mods(a))
    elif "type" in a:
        for ch in a["type"]:
            ev('TEXTINPUT', 'PRESS', unicode=ch)
    elif "menu" in a:
        area, region = view3d()
        with bpy.context.temp_override(window=win(), screen=win().screen, area=area, region=region):
            try:
                bpy.ops.allset.menu_item('INVOKE_DEFAULT', item=a["menu"])
            except Exception as ex:
                rec.setdefault("reports", []).append(str(ex).strip()[:300])
    elif "menus" in a:
        ms = import_module(MODULE + ".ui.menu_sets")
        mm = import_module(MODULE + ".ui.menu_map")
        paths = [p for p, _it in ms.iter_items() if p.startswith(a["menus"] + "/")]
        rec["menus"] = [p + ("" if p in mm.MAP else " (greyed)") for p in paths
                        if not any(q.startswith(p + "/") for q in paths)][:200]
    return rec


def make_step(i, a):
    def s_act():
        n = len(ERR)
        r0 = result_text()
        rec = run_action(a)
        LOG.append(rec)
        for w in win().screen.areas:
            w.tag_redraw()

        def s_after():
            rec["errors"] = ERR[n:]
            if a.get("state"):
                rec["state"] = state()          # after the events were handled
            r1 = result_text()
            if r1 and r1 != r0:
                rec.setdefault("reports", []).append("result field: " + r1)
            label = a.get("shot") or next(iter(a.keys()))
            sim.screenshot(str(OUT / f"{i:02d}_{label}.png"))
            (OUT / "log.json").write_text(json.dumps(LOG, indent=1, default=str), encoding="utf-8")
        _steps_after.append(s_after)
    return s_act


_steps_after = []


@step
def s_start():
    sim.setup()
    import_module(MODULE + ".first_start").new_maya_scene()


@step
def s_settle():
    area, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)
    sim.screenshot(str(OUT / "00_start.png"))


for _i, _a in enumerate(ACTIONS, 1):
    step(make_step(_i, _a))
    for _w in range(1 + int(_a.get("wait", 0))):      # screen.screenshot shows the previous frame: one tick more
        step(lambda: None)

    @step
    def s_flush():
        while _steps_after:
            _steps_after.pop(0)()

sim.run(interval=0.5, first=3.0)
