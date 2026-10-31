"""Count the Maya menus the way audit 7 did: leaves per menu set, working
(mapped), greyed with a notice, greyed without one.

    python tools/menu_count.py            # summary
    python tools/menu_count.py --greyed   # list the greyed items without a notice
    python tools/menu_count.py --options  # + what every option box opens (headless Blender)

Shared menus are counted per set (the audit's per-set table, 1417 leaves at the time) and once per path
(the headline 1251). Runs without Blender: ``bpy`` is stubbed, ``ui/menu_data``, ``menu_map`` and ``notices`` are imported from
src/. A leaf = a drawn item that is not a submenu (a mapped submenu entry counts once). Shared menus
(Deform, Constrain) count once per set that shows them, like the audit. Target: working >= 40 %,
greyed without a notice = 0. The Graph Editor / Dope Sheet / UV Editor menu bars are listed after the totals,
then the viewport panel menus, panel toolbar and greyed Status Line widgets (ui/panel_menu_data.py).
"""

import collections
import importlib
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class _Stub:
    def __getattr__(self, key):
        return _Stub()

    def __call__(self, *a, **k):
        return _Stub()

    def __mro_entries__(self, bases):
        return (object,)


def _load():
    bpy = types.ModuleType("bpy")
    bpy.__getattr__ = lambda key: _Stub()
    saved = {n: sys.modules.get(n) for n in ("bpy", "bpy.props", "bpy.types", "mk", "mk.ui")}
    sys.modules["bpy"] = bpy
    for name in ("bpy.props", "bpy.types"):
        mod = types.ModuleType(name)
        mod.__getattr__ = lambda key: _Stub()
        sys.modules[name] = mod
    pkg = types.ModuleType("mk")
    pkg.__path__ = [str(ROOT / "src" / "allset")]
    sys.modules["mk"] = pkg
    ui = types.ModuleType("mk.ui")
    ui.__path__ = [str(ROOT / "src" / "allset" / "ui")]
    sys.modules["mk.ui"] = ui
    try:
        mods = tuple(importlib.import_module(f"mk.ui.{m}") for m in ("menu_data", "menu_map", "notices"))
        mods[0].EDITORS = importlib.import_module("mk.ui.editor_menu_data").EDITORS   # editor menu bars
        mods[0].PANEL = importlib.import_module("mk.ui.panel_menu_data")   # panel menus / toolbar / Status Line
        return mods
    finally:
        for name, mod in saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod


def leaves(md, mm, items, prefix):
    """(path, item) of the drawn leaves below ``items`` (ui/menu_sets.children rules)."""
    seen = {}
    for it in items:
        if it[0] == "-":
            continue
        n = seen[it[0]] = seen.get(it[0], 0) + 1
        path = f"{prefix}/{it[0]}" + (f"#{n}" if n > 1 else "")
        entries = [(path, it)] + [(f"{prefix}/{x[0]}", x) for x in mm.EXTRA.get(path, ()) if x[0] != "-"]
        for p, entry in entries:
            kids = mm.CHILDREN.get(p) or (entry[1] if len(entry) > 1 else None)
            if kids and p not in mm.MAP:
                yield from leaves(md, mm, kids, p)
            else:
                yield p, entry


def count(md=None, mm=None, nt=None):
    """{"sets": {set label: Counter}, "total": Counter, "greyed": [paths without a notice]}."""
    if md is None:
        md, mm, nt = _load()
    labels = {sid: label for sid, label, _menus in md.MENU_SETS}
    menus_by_set = {sid: [m for m in menus if m in md.MENUS] for sid, _label, menus in md.MENU_SETS}
    always = [n for n, m in md.MENUS.items() if m[1] == "(always visible)"]
    sets = collections.OrderedDict()
    for sid, label in labels.items():
        sets[label] = menus_by_set[sid]
    sets["(always visible)"] = always
    out, total, greyed, unique = {}, collections.Counter(), [], {}
    for label, names in sets.items():
        c = collections.Counter()
        for name in names:
            mlabel, _set, _src, items = md.MENUS[name]
            for path, _it in leaves(md, mm, items, mlabel):
                c["leaves"] += 1
                unique[path] = path in mm.MAP
                if path in mm.MAP:
                    c["working"] += 1
                elif nt.greyed_notice(path):
                    c["greyed+notice"] += 1
                else:
                    c["greyed"] += 1
                    greyed.append(path)
        out[label] = c
        total.update(c)
    editors = {}
    for editor, menus in getattr(md, "EDITORS", {}).items():   # Graph Editor / Dope Sheet / UV Editor menu bars
        c = collections.Counter()
        for title, items in menus:
            for path, _it in leaves(md, mm, items, f"{editor}/{title}"):
                c["leaves"] += 1
                if path in mm.MAP:
                    c["working"] += 1
                elif nt.greyed_notice(path):
                    c["greyed+notice"] += 1
                else:
                    c["greyed"] += 1
                    greyed.append(path)
        editors[editor] = c
    panels = collections.OrderedDict()      # viewport panel menus, panel toolbar, Status Line widgets
    if getattr(md, "PANEL", None) is not None:
        for family, path, working in md.PANEL.leaves():
            c = panels.setdefault(family, collections.Counter())
            c["leaves"] += 1
            if working:
                c["working"] += 1
            elif nt.greyed_notice(path):
                c["greyed+notice"] += 1
            else:
                c["greyed"] += 1
                greyed.append(path)
    return {"sets": out, "total": total, "greyed": sorted(set(greyed)), "editors": editors, "panels": panels,
            "unique": (len(unique), sum(unique.values()))}


def options():
    """What every Maya option box opens (window / dialog / tool / redo / generic / dead): runs
    tests/test_step140_option_count.py in its own sandbox (needs Blender) and prints its table."""
    import json
    import os
    import subprocess
    env = dict(os.environ, ALLSET_SANDBOX="option_count")
    subprocess.run([sys.executable, str(ROOT / "tests" / "run.py"), "-k", "step140_option_count"], env=env,
                   check=True, stdout=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    data = json.loads((ROOT / "tmp" / "option_count" / "results" / "option_kinds.json").read_text(encoding="utf-8"))
    kinds = ("window", "dialog", "tool", "redo", "generic", "menu", "dead")
    print(f"\nOption boxes: {data['total']} (kit option windows: {data['windows']})")
    print("  " + "  ".join(f"{k} {data['kinds'].get(k, 0)}" for k in kinds))
    if "--greyed" in sys.argv:
        for k in ("generic", "dead"):
            print(f"\n{k}:")
            print("\n".join("  " + p for p, kind in data["rows"] if kind == k))


def main():
    r = count()
    t = r["total"]
    for label, c in r["sets"].items():
        print(f"{label:18} leaves {c['leaves']:4}  working {c['working']:4} ({100 * c['working'] / max(c['leaves'], 1):.0f} %)"
              f"  greyed+notice {c['greyed+notice']:4}  greyed {c['greyed']:4}")
    print(f"{'total':18} leaves {t['leaves']:4}  working {t['working']:4} ({100 * t['working'] / t['leaves']:.1f} %)"
          f"  greyed+notice {t['greyed+notice']:4}  greyed without notice {len(r['greyed'])}")
    for label, c in r["editors"].items():
        print(f"{label:18} leaves {c['leaves']:4}  working {c['working']:4} ({100 * c['working'] / max(c['leaves'], 1):.0f} %)"
              f"  greyed+notice {c['greyed+notice']:4}  greyed {c['greyed']:4}  (editor menu bar)")
    for label, c in r.get("panels", {}).items():
        print(f"{label:18} leaves {c['leaves']:4}  working {c['working']:4} ({100 * c['working'] / max(c['leaves'], 1):.0f} %)"
              f"  greyed+notice {c['greyed+notice']:4}  greyed {c['greyed']:4}  (viewport panel / Status Line)")
    n, w = r["unique"]
    print(f"{'unique paths':18} leaves {n:4}  working {w:4} ({100 * w / n:.1f} %)")
    if "--greyed" in sys.argv:
        print("\n".join(r["greyed"]))
    if "--options" in sys.argv:
        options()


if __name__ == "__main__":
    main()
