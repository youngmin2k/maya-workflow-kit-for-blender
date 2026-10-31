"""What every Maya option box opens, counted like audit 8
(window / dialog / tool / redo / generic / dead). Writes the table to
tmp/<sandbox>/results/option_kinds.json for ``python tools/menu_count.py --options``.

Baseline (0.2.1): 507 boxes, dead 231, generic 62, window 48."""

import collections
import json
import os
import sys
from importlib import import_module

import kit

menu_data = import_module(kit.MODULE + ".ui.menu_data")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
ow = import_module(kit.MODULE + ".operators.option_windows")

# Daily boxes that must open a Maya window (Maya menu paths)
DAILY = (
    "Skeleton/Create Joints", "Skeleton/Create IK Handle", "Skin/Bind Skin", "Skin/Paint Skin Weights",
    "Edit/Parent", "Key/Delete Keys", "Key/Cut Keys", "Key/Copy Keys", "Key/Paste Keys", "Key/Scale Keys",
    "Edit/Keys/Delete Keys", "Edit/Keys/Cut Keys", "Edit/Keys/Copy Keys", "Edit/Keys/Paste Keys",
    "Deform/Blend Shape", "Edit Mesh/Connect", "Edit Mesh/Circularize", "Mesh Tools/Insert Edge Loop",
    "Edit/Duplicate Special", "Constrain/Aim", "Constrain/Pole Vector",
)


def kinds():
    rows = []
    for p in sorted(menu_data.OPTION_BOXES):
        rows.append((p, menu_sets.option_kind(p) if p in menu_map.MAP else "dead"))
    return rows


def test_count_and_write():
    rows = kinds()
    count = collections.Counter(k for _p, k in rows)
    per_top = collections.defaultdict(collections.Counter)
    for p, k in rows:
        per_top[p.split("/")[0]][k] += 1
    out = os.path.join(os.path.dirname(sys.argv[-1]), "option_kinds.json")   # next to this file's results json
    data = {"total": len(rows), "kinds": dict(count), "per_top": {k: dict(v) for k, v in per_top.items()},
            "rows": rows, "windows": len(ow.WINDOWS)}
    print("OPTION_KINDS", json.dumps({"total": len(rows), "kinds": dict(count), "windows": len(ow.WINDOWS)}))
    try:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
    except OSError:
        pass
