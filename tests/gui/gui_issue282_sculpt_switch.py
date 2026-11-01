"""#282 in a real UI: Blender's Sculpting workspace after a round trip through Maya mode.
1. Sculpting, Maya on, Blender: the workspace looks as before (regions, tool header, toolbar tools, panels, header
   draws, asset shelf).
2. Maya on, Windows > Workspaces > Sculpting (Maya's), Blender: no Maya workspace is left in the file.
3. A Maya Workflow Kit scene, Blender: the "Sculpting" tab is Blender's own; Maya's is "Sculpting (Maya)"."""

import json
import os
import sys
from importlib import import_module

import addon_utils
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, step, screenshot, tap, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
DUMP = os.environ.get("ALLSET_282_DUMP", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def sw():
    return import_module(MODULE + ".switch")


def view():
    for area in win().screen.areas:
        if area.type == 'VIEW_3D':
            return area
    return None


def _panels(area, region_type):
    """bl_idnames of the 3D View panels of ``region_type`` whose poll passes in that region now."""
    region = next((r for r in area.regions if r.type == region_type), None)
    if region is None:
        return []
    out = []
    with bpy.context.temp_override(window=win(), area=area, region=region):
        ctx = bpy.context
        for cls in bpy.types.Panel.__subclasses__() + [c for b in bpy.types.Panel.__subclasses__()
                                                        for c in b.__subclasses__()]:
            if getattr(cls, "bl_space_type", None) != 'VIEW_3D' or getattr(cls, "bl_region_type", None) != region_type:
                continue
            if not getattr(cls, "is_registered", False):
                continue
            poll = getattr(cls, "poll", None)
            try:
                ok = poll(ctx) if poll is not None else True
            except Exception as ex:      # noqa: BLE001 — record, a probe
                ok = f"raised {ex!r}"
            if ok:
                out.append(f"{getattr(cls, 'bl_idname', cls.__name__)}|{getattr(cls, 'bl_category', '')}|{getattr(cls, 'bl_parent_id', '')}")
    return sorted(set(out))


def _draws(cls_name):
    cls = getattr(bpy.types, cls_name, None)
    if cls is None:
        return None
    try:
        funcs = cls._dyn_ui_initialize()
    except Exception:            # noqa: BLE001
        funcs = [cls.draw]
    return [f"{getattr(f, '__module__', '')}.{getattr(f, '__qualname__', repr(f))}" for f in funcs]


def state():
    area = view()
    space = area.spaces.active
    out = {"workspace": win().workspace.name, "mode": bpy.context.mode}
    out["space"] = {k: getattr(space, k) for k in dir(space)
                    if k.startswith("show_region") or k in ("show_gizmo", "show_gizmo_navigate")}
    out["regions"] = sorted(f"{r.type}:{r.width}x{r.height}" for r in area.regions)
    for rt in ("UI", "TOOLS", "HEADER", "TOOL_HEADER", "WINDOW"):
        out["panels_" + rt] = _panels(area, rt)
    for name in ("VIEW3D_HT_header", "VIEW3D_HT_tool_header", "VIEW3D_MT_editor_menus", "VIEW3D_PT_tools_active",
                 "TOPBAR_HT_upper_bar", "STATUSBAR_HT_header"):
        out["draw_" + name] = _draws(name)
    tools = bpy.types.VIEW3D_PT_tools_active
    with bpy.context.temp_override(window=win(), area=area,
                                   region=next(r for r in area.regions if r.type == 'WINDOW')):
        ctx = bpy.context
        try:
            out["tools"] = [getattr(t, "idname", str(t)) for t in tools.tools_from_context(ctx)]
        except Exception as ex:          # noqa: BLE001
            out["tools"] = repr(ex)
        out["tool"] = ctx.workspace.tools.from_space_view3d_mode(ctx.mode).idname
    out["asset_shelves"] = sorted(getattr(c, "bl_idname", c.__name__) for c in bpy.types.AssetShelf.__subclasses__()
                                  if getattr(c, "is_registered", False))
    out["categories"] = {r.type: getattr(r, "active_panel_category", None) for r in area.regions}
    return out


def diff(a, b):
    out = {}
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            if isinstance(a.get(k), list) and isinstance(b.get(k), list):
                out[k] = {"lost": sorted(set(map(str, a[k])) - set(map(str, b[k]))),
                          "added": sorted(set(map(str, b[k])) - set(map(str, a[k])))}
            elif isinstance(a.get(k), dict) and isinstance(b.get(k), dict):
                out[k] = {kk: (a[k].get(kk), b[k].get(kk)) for kk in set(a[k]) | set(b[k])
                          if a[k].get(kk) != b[k].get(kk)}
            else:
                out[k] = (a.get(k), b.get(k))
    return out


@step
def s_setup():
    tap('ESC')
    addon_utils.enable(MODULE, default_set=True)        # Blender mode: enabling alone changes nothing
    win().workspace = bpy.data.workspaces["Sculpting"]


@step
def s_wait():
    pass


@step
def s_before():
    C["a"] = state()
    check(f"Blender's Sculpting workspace in sculpt mode ({C['a']['workspace']}, {C['a']['mode']})",
          C["a"]["workspace"] == "Sculpting" and C["a"]["mode"] == 'SCULPT')
    shot("gui_issue282_before.png")
    sw().set_mode(True)


@step
def s_maya():
    check(f"Maya mode shows the Maya layout ({win().workspace.name})", sw().is_maya_workspace(win().workspace))


@step
def s_maya_wait():
    shot("gui_issue282_maya.png")


@step
def s_blender():
    sw().set_mode(False)


@step
def s_blender_wait():
    pass


# UI panels whose poll reads the selection (Maya mode selects the lead)
SELECTION_PANELS = ("VIEW3D_PT_context_properties",)


@step
def s_after():
    C["b"] = state()
    shot("gui_issue282_after.png")
    for k in ("a", "b"):
        C[k]["panels_UI"] = [p for p in C[k]["panels_UI"] if p.split("|")[0] not in SELECTION_PANELS]
    d = diff(C["a"], C["b"])
    if DUMP:
        with open(DUMP, "w", encoding="utf-8") as fh:
            json.dump({"before": C["a"], "after": C["b"], "diff": d}, fh, indent=1, default=str)
    check(f"back in Blender's Sculpting workspace ({C['b']['workspace']}, {C['b']['mode']})",
          C["b"]["workspace"] == "Sculpting" and C["b"]["mode"] == 'SCULPT')
    check(f"the Sculpting workspace looks as before ({json.dumps(d, default=str)[:1500]})", not d)
    C["names"] = sorted(w.name for w in bpy.data.workspaces)
    sw().set_mode(True)


def maya_names():
    return sorted(w.name for w in bpy.data.workspaces if sw().is_maya_workspace(w))


@step
def s_pick_maya_sculpting():
    ws = import_module(MODULE + ".ui.workspaces")
    ws.activate(bpy.context, win(), "Sculpting")


@step
def s_maya_sculpting():
    check(f"Maya's Sculpting workspace shown ({win().workspace.name})",
          sw().template_of(win().workspace) == "Sculpting")
    sw().set_mode(False)


@step
def s_maya_sculpting_wait():
    pass


@step
def s_back_from_maya_sculpting():
    check(f"Blender mode shows a Blender workspace ({win().workspace.name})",
          not sw().is_maya_workspace(win().workspace))
    names = sorted(w.name for w in bpy.data.workspaces)
    check(f"no Maya workspace left ({maya_names()}), the file's workspaces as before ({names})",
          not maya_names() and names == C["names"])


@step
def s_template():
    sw().set_mode(True, layout=False)
    load_maya_layout()


@step
def s_template_wait():
    pass


@step
def s_template_blender():
    check(f"a Maya Workflow Kit scene ({win().workspace.name})", sw().is_maya_workspace(win().workspace))
    sw().set_mode(False)


@step
def s_template_blender_wait():
    pass


@step
def s_template_tabs():
    sculpt = bpy.data.workspaces.get("Sculpting")
    maya = bpy.data.workspaces.get("Sculpting (Maya)")
    check(f"Blender mode shows Blender's Layout ({win().workspace.name})", win().workspace.name == "Layout")
    check("the Sculpting tab is Blender's own", sculpt is not None and not sw().is_maya_workspace(sculpt))
    check("Maya's Sculpting workspace is kept as Sculpting (Maya)",
          maya is not None and sw().template_of(maya) == "Sculpting")
    clash = [w.name for w in bpy.data.workspaces if sw().is_maya_workspace(w) and w.name in sw().BLENDER_WORKSPACES]
    check(f"no Maya workspace under a Blender name ({clash})", not clash)
    C["n"] = len(bpy.data.workspaces)
    win().workspace = sculpt


@step
def s_template_sculpt_wait():
    pass


@step
def s_template_sculpt():
    shot("gui_issue282_template_sculpting.png")
    area = view()
    space = area.spaces.active if area is not None else None
    check(f"Blender's Sculpting workspace shown ({win().workspace.name})", win().workspace.name == "Sculpting")
    check("its 3D View has Blender's toolbar and asset shelf, no Maya strip",
          space is not None and space.show_region_toolbar
          and not any(a.type == 'IMAGE_EDITOR' for a in win().screen.areas))
    sw().set_mode(True)


@step
def s_template_maya_again():
    check(f"Maya mode shows the Maya layout again ({win().workspace.name})", sw().is_maya_workspace(win().workspace))
    sw().set_mode(False)


@step
def s_template_blender_again():
    pass


@step
def s_template_again():
    check(f"a second round trip appends nothing ({C['n']} -> {len(bpy.data.workspaces)}, "
          f"{sorted(w.name for w in bpy.data.workspaces)})", len(bpy.data.workspaces) == C["n"])


run()
