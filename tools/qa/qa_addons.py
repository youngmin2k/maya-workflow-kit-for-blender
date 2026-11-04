"""QA activity F: the kit next to other add-ons (#79 class of bugs).

    ALLSET_SANDBOX=qa_f python tests/run.py --no-build -k __none__ \
        --extra tools/qa/qa_addons_kit_first.py,tools/qa/qa_addons_others_first.py [--blender <exe>]

Each wrapper runs ``run(order)`` in its own Blender process. Add-ons: bundled rigify, node_wrangler,
copy_global_transform, pose_library (whichever this Blender ships) + two dummies written into the sandbox's user
scripts folder:
  qa_dummy_render (package): Properties > Render panels built on bl_ui.properties_render.RenderButtonsPanel with
    COMPAT_ENGINES, a child panel, a child under a Blender render panel, and a module-valued global ``classes``
    (``from . import classes``, the #79 shape)
  qa_dummy_keys: add-on keymap items on W / Q / E / R in "3D View"
Per order: enable all -> Maya mode on -> smoke (Rigify metarig + generate, Node Wrangler ops, dummy panels / keys) -> Maya mode off ->
disable the kit -> the other add-ons' panels / keymap items / ops still there and work. stderr is teed so Python
tracebacks printed by Blender (handlers, draw, timers) are counted per phase.
LoopTools / Bool Tool are online-only extensions: not covered (no download).
"""

import importlib.util
import io
import os
import sys
import traceback
from importlib import import_module
from pathlib import Path

import addon_utils
import bpy

import kit

AUTO_ENABLE = False

_spec = importlib.util.spec_from_file_location("qa_common", Path(__file__).resolve().parent / "qa_common.py")
qa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qa)

TAG = qa.env_tag()
VERSION = f"Blender {bpy.app.version_string}, kit {qa.git_head()} (working tree, 0.11.0)"
BUNDLED = ("rigify", "node_wrangler", "copy_global_transform", "pose_library")
DUMMY_A, DUMMY_B = "qa_dummy_render", "qa_dummy_keys"

DUMMY_A_INIT = '''bl_info = {"name": "QA Dummy Render Panels", "blender": (4, 2, 0), "category": "Render"}
import bpy
from bl_ui.properties_render import RenderButtonsPanel
from . import classes          # issue #79: the module global "classes" is a submodule


class QA_PT_render_main(RenderButtonsPanel, bpy.types.Panel):
    bl_label = "QA Render Main"
    bl_context = "render"
    COMPAT_ENGINES = {'BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT', 'BLENDER_WORKBENCH', 'CYCLES'}

    def draw(self, context):
        self.layout.label(text="qa main")


class QA_PT_render_child(RenderButtonsPanel, bpy.types.Panel):
    bl_label = "QA Render Child"
    bl_context = "render"
    bl_parent_id = "QA_PT_render_main"
    COMPAT_ENGINES = QA_PT_render_main.COMPAT_ENGINES

    def draw(self, context):
        self.layout.label(text="qa child")


class QA_PT_render_plain(bpy.types.Panel):
    """No RenderButtonsPanel base and no poll of its own (a plain third-party panel on the Render tab)."""
    bl_label = "QA Render Plain"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"

    def draw(self, context):
        self.layout.label(text="qa plain")


class QA_PT_under_blender(bpy.types.Panel):
    bl_label = "QA Under Color Management"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    bl_parent_id = "RENDER_PT_color_management"

    def draw(self, context):
        self.layout.label(text="qa under blender")


_CLASSES = (QA_PT_render_main, QA_PT_render_child, QA_PT_render_plain, QA_PT_under_blender)


def register():
    for c in _CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_CLASSES):
        bpy.utils.unregister_class(c)
'''

DUMMY_B_SRC = '''bl_info = {"name": "QA Dummy Keys", "blender": (4, 2, 0), "category": "3D View"}
import bpy

_items = []


class QA_OT_dummy_key(bpy.types.Operator):
    bl_idname = "qa.dummy_key"
    bl_label = "QA Dummy Key"
    which: bpy.props.StringProperty()

    def execute(self, context):
        bpy.app.driver_namespace["qa_dummy_key"] = self.which
        return {'FINISHED'}


def register():
    bpy.utils.register_class(QA_OT_dummy_key)
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="3D View", space_type='VIEW_3D')
        for key in ("W", "Q", "E", "R"):
            kmi = km.keymap_items.new("qa.dummy_key", key, 'PRESS')
            kmi.properties.which = key
            _items.append((km, kmi))


def unregister():
    for km, kmi in _items:
        km.keymap_items.remove(kmi)
    _items.clear()
    bpy.utils.unregister_class(QA_OT_dummy_key)
'''


class _Tee(io.TextIOBase):
    def __init__(self, real):
        self.real, self.buf = real, []

    def write(self, s):
        self.buf.append(s)
        return self.real.write(s)

    def flush(self):
        self.real.flush()

    def take(self):
        text = "".join(self.buf)
        self.buf.clear()
        return text


RESULTS = {"version": VERSION, "sandbox": TAG, "orders": {}}


def _write_dummies():
    base = bpy.utils.user_resource('SCRIPTS', path="addons", create=True)
    norm = os.path.normcase(base)
    assert os.path.normcase(str(qa.ROOT / "tmp")) in norm, base       # never the real user scripts folder
    pkg = os.path.join(base, DUMMY_A)
    os.makedirs(pkg, exist_ok=True)
    with open(os.path.join(pkg, "__init__.py"), "w", encoding="utf-8") as fh:
        fh.write(DUMMY_A_INIT)
    with open(os.path.join(pkg, "classes.py"), "w", encoding="utf-8") as fh:
        fh.write("# a submodule named classes (issue #79)\n")
    with open(os.path.join(base, DUMMY_B + ".py"), "w", encoding="utf-8") as fh:
        fh.write(DUMMY_B_SRC)
    bpy.utils.refresh_script_paths()


def _available(name):
    return any(m.__name__ == name for m in addon_utils.modules(refresh=False))


def _enable(name):
    err = []
    mod = addon_utils.enable(name, default_set=True, handle_error=lambda ex: err.append(repr(ex)))
    return mod is not None and not err, err


class Run:
    def __init__(self, order):
        self.order = order
        self.checks = []
        self.tee = _Tee(sys.stderr)
        sys.stderr = self.tee
        self.tracebacks = {}

    def check(self, name, ok, detail="", severity="S2"):
        self.checks.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"QA-F {self.order} {'PASS' if ok else 'FAIL'} {name}: {str(detail)[:500]}", flush=True)
        if not ok:
            qa.add_finding(f"F-{TAG}-{self.order}-{name}", "F", severity,
                           f"tools/qa/qa_addons.py order={self.order} (ALLSET_SANDBOX={TAG}): {name}",
                           f"coexistence: {str(detail)[:900]}", VERSION)

    def phase(self, name):
        text = self.tee.take()
        n = text.count("Traceback (most recent call last)")
        self.tracebacks[name] = n
        if n:
            i = text.find("Traceback (most recent call last)")
            self.check(f"no_traceback_{name}", False, text[i:i + 1500], severity="S2")
        return n


def _kit_items():
    kc = bpy.context.window_manager.keyconfigs.addon
    return [(km.name, kmi.type, kmi.idname, kmi.active) for km in kc.keymaps for kmi in km.keymap_items
            if kmi.idname.startswith("allset.")]


def _dummy_items():
    kc = bpy.context.window_manager.keyconfigs.addon
    return [(km.name, kmi.type, kmi.active) for km in kc.keymaps for kmi in km.keymap_items
            if kmi.idname == "qa.dummy_key"]


def _addon_order(key):
    """Add-on keyconfig items on plain ``key`` in "3D View" / "Object Mode" / "Mesh", in effective order (Blender
    merges add-on items at the head one by one, so the last one stored runs first; kit stores its own reversed). Headless the user keyconfig is not populated, so this is read from keyconfigs.addon."""
    kc = bpy.context.window_manager.keyconfigs.addon
    out = {}
    for km in kc.keymaps:
        if km.name not in ("3D View", "Object Mode", "Mesh", "Window", "Screen"):
            continue
        items = [k.idname for k in km.keymap_items if k.active and k.type == key and k.value in ('PRESS', 'ANY')
                 and not (k.shift or k.ctrl or k.alt or k.oskey)]
        if items:
            out[km.name] = list(reversed(items))
    return out


def _first_on_key(key):
    """The first active item for plain ``key`` PRESS in the user (merged) "3D View" keymap — what a press runs."""
    kc = bpy.context.window_manager.keyconfigs.user
    km = kc.keymaps.get("3D View")
    if km is None:
        return None
    for kmi in km.keymap_items:
        if kmi.active and kmi.type == key and kmi.value in ('PRESS', 'ANY') and not (kmi.shift or kmi.ctrl or kmi.alt
                                                                                     or kmi.oskey):
            return kmi.idname
    return None


def _dummy_classes():
    return [getattr(bpy.types, n, None) for n in ("QA_PT_render_main", "QA_PT_render_child", "QA_PT_render_plain",
                                                   "QA_PT_under_blender")]


def _rigify_smoke(r):
    if "rigify" not in bpy.context.preferences.addons:
        r.check("rigify_enabled", False, "rigify not enabled")
        return
    try:
        if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        before = set(bpy.data.objects.keys())
        res = bpy.ops.object.armature_human_metarig_add()
        meta = bpy.context.active_object
        r.check("rigify_metarig_add", res == {'FINISHED'} and meta is not None and meta.type == 'ARMATURE',
                {"res": res, "active": getattr(meta, "name", None), "mode": bpy.context.mode})
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for o in bpy.context.selected_objects:
            o.select_set(False)
        meta.select_set(True)
        bpy.context.view_layer.objects.active = meta
        res = bpy.ops.pose.rigify_generate()
        rig = next((o for o in bpy.data.objects if o.name not in before and o is not meta and o.type == 'ARMATURE'),
                   None)
        r.check("rigify_generate", res == {'FINISHED'} and rig is not None and len(rig.pose.bones) > 200,
                {"res": res, "rig": getattr(rig, "name", None), "bones": len(rig.pose.bones) if rig else 0})
    except Exception:
        r.check("rigify_smoke", False, traceback.format_exc()[-1200:])


def _other_smoke(r, label):
    out = {}
    if "node_wrangler" in bpy.context.preferences.addons:
        ops = [n for n in dir(bpy.ops.node) if n.startswith("nw_")]
        out["nw_ops"] = len(ops)
        r.check(f"node_wrangler_ops_{label}", len(ops) > 10, len(ops))
    if "copy_global_transform" in bpy.context.preferences.addons:
        ops = [n for n in dir(bpy.ops.object) if "global_transform" in n]
        r.check(f"copy_global_transform_ops_{label}", bool(ops), ops)
    cls = _dummy_classes()
    r.check(f"dummy_panels_registered_{label}", all(c is not None and c.is_registered for c in cls),
            [getattr(c, "__name__", None) for c in cls], severity="S1")
    items = _dummy_items()
    r.check(f"dummy_keys_present_active_{label}", len(items) == 4 and all(a for _n, _t, a in items), items)
    try:
        bpy.app.driver_namespace.pop("qa_dummy_key", None)
        bpy.ops.qa.dummy_key(which="W")
        r.check(f"dummy_op_runs_{label}", bpy.app.driver_namespace.get("qa_dummy_key") == "W")
    except Exception as ex:
        r.check(f"dummy_op_runs_{label}", False, repr(ex))
    return out


def run(order):
    r = Run(order)
    res = {"order": order, "bundled": {}, "first_on_key": {}}
    RESULTS["orders"][order] = res
    _write_dummies()
    others = [n for n in BUNDLED if _available(n)] + [DUMMY_A, DUMMY_B]
    res["not_shipped"] = [n for n in BUNDLED if not _available(n)]
    res["not_covered"] = ["looptools", "bool_tool (online-only extensions, no network in QA)"]

    def enable_kit():
        try:
            kit.enable(maya=False)
            r.check("kit_enable", True)
        except Exception:
            r.check("kit_enable", False, traceback.format_exc()[-1200:], severity="S1")

    def enable_others():
        for n in others:
            ok, err = _enable(n)
            res["bundled"][n] = ok
            r.check(f"enable_{n}", ok, err, severity="S1")

    if order == "kit_first":
        enable_kit()
        enable_others()
    else:
        enable_others()
        enable_kit()
    r.phase("enable")
    res["kit_items_before_maya"] = len(_kit_items())
    try:
        kit.maya_mode_on()
        sw = import_module(kit.MODULE + ".switch")
        r.check("maya_mode_on", sw.is_on() and sw._registered[0], {"on": sw.is_on()}, severity="S1")
    except Exception:
        r.check("maya_mode_on", False, traceback.format_exc()[-1500:], severity="S1")
    r.phase("maya_on")
    items = _kit_items()
    res["kit_items_maya_on"] = len(items)
    r.check("kit_keymap_items_present", len(items) > 100 and all(a for *_x, a in items),
            {"n": len(items), "inactive": [i for i in items if not i[3]][:5]})
    for key in ("W", "Q", "E", "R"):
        res["first_on_key"][key] = _first_on_key(key)
        res.setdefault("addon_order", {})[key] = _addon_order(key)
    print(f"QA-F {order} add-on keymap order on W/Q/E/R (Maya on): {res['addon_order']}", flush=True)
    print(f"QA-F {order} 3D View first item per key (Maya on): {res['first_on_key']}", flush=True)
    _rigify_smoke(r)
    r.phase("rigify")
    _other_smoke(r, "maya_on")
    r.phase("smoke_on")
    # a wrapped third-party render add-on goes away while Maya mode is on, then comes back after Maya mode off
    try:
        addon_utils.disable(DUMMY_A, default_set=True, handle_error=lambda ex: (_ for _ in ()).throw(ex))
        r.check("dummy_render_disable_while_maya_on", not any(c is not None and c.is_registered
                                                               for c in _dummy_classes()), [str(c) for c in
                                                                                             _dummy_classes()])
    except Exception:
        r.check("dummy_render_disable_while_maya_on", False, traceback.format_exc()[-1200:], severity="S2")
    r.phase("dummy_off_maya_on")
    try:
        sw = import_module(kit.MODULE + ".switch")
        sw.set_mode(False, layout=False)
        r.check("maya_mode_off", not sw.is_on())
    except Exception:
        r.check("maya_mode_off", False, traceback.format_exc()[-1500:], severity="S1")
    r.phase("maya_off")
    ok, err = _enable(DUMMY_A)
    r.check("dummy_render_reenable_after_maya_off", ok and all(c is not None and c.is_registered
                                                               for c in _dummy_classes()), err, severity="S2")
    r.phase("dummy_reenable")
    # the dummy render panels: original poll back after Maya mode off (no kit wrapper left)
    leftover = [c.__name__ for c in _dummy_classes() if c is not None and
                getattr(c.__dict__.get("poll"), "__func__", None) is not None and
                "_make_poll" in getattr(c.__dict__["poll"].__func__, "__qualname__", "")]
    r.check("dummy_polls_unwrapped", not leftover, leftover)
    try:
        kit.disable()
        r.check("kit_disable", True)
    except Exception:
        r.check("kit_disable", False, traceback.format_exc()[-1200:], severity="S1")
    r.phase("kit_disable")
    for n in others:
        r.check(f"still_enabled_{n}", n in bpy.context.preferences.addons, severity="S1")
    _other_smoke(r, "after_kit_disable")
    res["first_on_key_after"] = {key: _first_on_key(key) for key in ("W", "Q", "E", "R")}
    r.check("no_kit_items_after_disable", not _kit_items(), _kit_items()[:5])
    # Rigify still generates after the kit went away
    _rigify_smoke(r)
    r.phase("after")
    for n in reversed(others):
        try:
            addon_utils.disable(n, default_set=True, handle_error=lambda ex: (_ for _ in ()).throw(ex))
        except Exception:
            r.check(f"disable_{n}", False, traceback.format_exc()[-800:])
    r.phase("cleanup")
    sys.stderr = r.tee.real
    res["checks"] = r.checks
    res["tracebacks"] = r.tracebacks
    res["summary"] = {"checks": len(r.checks), "failed": sum(not c["ok"] for c in r.checks)}
    qa.write_json(f"qa_f_{TAG}_{order}.json", RESULTS)
    print(f"QA-F SUMMARY {order} {res['summary']}", flush=True)
    bad = [c["name"] for c in r.checks if not c["ok"]]
    assert not bad, bad
