"""Maya ⇄ Blender switch, without any snapshot.

In one process: factory → the user's own changes (a key edit, theme colour, navigation, splash,
another add-on) → Maya Workflow Kit on → Make Blender Maya → Blender's preferences unchanged even in Maya mode
(nothing to restore) → switch to Blender → everything as before → Maya again → Blender again → as
before → disable → as before.
Across processes (saved preferences re-read by a new Blender): the same round trip, the saved
userpref.blend compared, and the extension disabled in Maya mode.
"""

import json
import os
import shutil
import subprocess
from importlib import import_module

import bpy

import kit
from rt60_dump import dump, edit_user_key, populate

AUTO_ENABLE = False
HERE = os.path.dirname(os.path.abspath(__file__))


def _diff(a, b):
    out = []
    for key in sorted(set(a) | set(b)):
        if a.get(key) == b.get(key):
            continue
        if isinstance(a.get(key), dict) and isinstance(b.get(key), dict):
            for k in sorted(set(a[key]) | set(b[key])):
                if a[key].get(k) != b[key].get(k):
                    out.append(f"{key}.{k}: {a[key].get(k)!r} -> {b[key].get(k)!r}")
        elif isinstance(a.get(key), list) and isinstance(b.get(key), list):
            sa, sb = set(a[key]), set(b[key])
            out.append(f"{key}: +{sorted(sb - sa)[:5]} -{sorted(sa - sb)[:5]}")
        else:
            out.append(f"{key}: {str(a.get(key))[:80]!r} -> {str(b.get(key))[:80]!r}")
    return out


def _mod(name):
    return import_module(f"{kit.MODULE}.{name}")


def _user_setup():
    import addon_utils
    prefs = bpy.context.preferences
    edit_user_key()
    prefs.themes[0].view_3d.space.gradients.high_gradient = (0.5, 0.1, 0.1)
    prefs.inputs.view_rotate_method = 'TRACKBALL'
    prefs.view.show_splash = True
    addon_utils.enable("node_wrangler", default_set=True)


# The Maya keys live in the add-on keyconfig, so not even the stored keyconfig name changes:
# no preference may change while Maya mode is on.
KEYMAP_KEYS = ()


def _unchanged_in_maya_mode(before, maya):
    d = [k for k in set(before["values"]) | set(maya["values"])
         if before["values"].get(k) != maya["values"].get(k) and k not in KEYMAP_KEYS]
    assert not d, "Maya mode changed preferences: " + ", ".join(
        f"{k}: {before['values'].get(k)} -> {maya['values'].get(k)}" for k in sorted(d)[:20])
    # user_keymaps differ on purpose while Maya mode is on (add-on items first, the active keyconfig's items off in
    # memory); the keyconfigs themselves and which one is active don't
    for key in ("theme_xml", "theme_filepath", "theme_name", "addons", "active_keyconfig", "keyconfigs"):
        assert before[key] == maya[key], f"Maya mode changed {key}"


def test_round_trip_in_one_session():
    _user_setup()
    before = dump()
    kit.enable()
    sw = _mod("switch")
    assert sw.is_on()
    _mod("first_start").make(bpy.context, open_layout=False)   # Make Blender Maya
    _unchanged_in_maya_mode(before, dump())
    for n in (1, 2):
        sw.set_mode(False)
        after = dump()
        d = _diff(before, after)
        assert not d, f"switch {n} to Blender left differences:\n" + "\n".join(d[:20])
        assert not sw.is_on()
        assert "draw_topbar_switch" in [getattr(f, "__name__", "") for f in
                                        bpy.types.TOPBAR_HT_upper_bar.draw._draw_funcs], "switch gone in Blender mode"
        assert not hasattr(bpy.types.Scene, "allset_cb"), "Maya mode classes still registered"
        sw.set_mode(True)
        _unchanged_in_maya_mode(before, dump())
    kit.disable()
    d = _diff(before, dump())
    assert not d, "disable in Maya mode left differences:\n" + "\n".join(d[:20])


def test_user_key_edit_and_other_keyconfig_kept():
    """A user who uses Industry Compatible with their own key edit gets exactly that back."""
    populate()
    kcs = bpy.context.window_manager.keyconfigs
    km = kcs.user.keymaps["Object Mode"]
    kmi = next(k for k in km.keymap_items if k.idname == "object.delete")
    assert kmi.type == 'F9' and kmi.is_user_modified, "the user's key edit survived the first test"
    before = dump()
    kit.enable()
    sw = _mod("switch")
    sw.set_mode(True)
    sw.set_mode(False)
    d = _diff(before, dump())
    assert not d, "\n".join(d[:20])
    kit.disable()


# --- across processes ------------------------------------------------------------------------------

def _session(cfg, name, *actions):
    out = os.path.join(cfg, "..", f"{name}.json")
    env = dict(os.environ)
    env["BLENDER_USER_CONFIG"] = cfg
    env["ALLSET_NO_WELCOME"] = "1"
    cmd = [bpy.app.binary_path, "-b", "--python", os.path.join(HERE, "rt60_session.py"), "--", out, *actions]
    proc = subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=180)
    if not os.path.isfile(out):
        raise AssertionError(f"session {name} wrote nothing:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
    with open(out, encoding="utf-8") as fh:
        data = json.load(fh)
    os.remove(out)
    return data


def _sandbox():
    root = os.path.abspath(os.path.join(bpy.utils.user_resource('CONFIG'), "..", "rt60"))
    assert "tmp" in root.replace("\\", "/").split("/"), root
    if os.path.isdir(root):
        shutil.rmtree(root)
    cfg = os.path.join(root, "config")
    os.makedirs(cfg)          # Blender ignores a BLENDER_USER_CONFIG that doesn't exist
    return cfg


def _userpref(cfg):
    with open(os.path.join(cfg, "userpref.blend"), "rb") as fh:
        return fh.read()


def test_round_trip_across_restarts():
    cfg = _sandbox()
    a = _session(cfg, "a", "user_setup", "save")
    b = _session(cfg, "b", "enable", "make_maya", "save")
    assert b["state"]["maya_mode"], b["state"]
    c = _session(cfg, "c", "maya_off", "save")            # Blender starts in Maya mode, switch off
    assert not c["state"]["maya_mode"], c["state"]
    d = _diff(a["dump"], c["dump"])
    assert not d, "after restart + switch off:\n" + "\n".join(d[:20])
    bytes_c = _userpref(cfg)
    _session(cfg, "d", "maya_on", "save")                  # Maya again, quit in Maya mode
    e = _session(cfg, "e", "maya_off", "save")
    d = _diff(a["dump"], e["dump"])
    assert not d, "second round trip:\n" + "\n".join(d[:20])
    bytes_e = _userpref(cfg)
    ndiff = sum(1 for x, y in zip(bytes_c, bytes_e) if x != y)
    # Same size; the differing bytes are memory addresses Blender writes into a .blend (two saves
    # in one process are byte-identical, across processes the addresses change).
    print(f"userpref.blend after both switches to Blender: {len(bytes_c)} / {len(bytes_e)} bytes, "
          f"{ndiff} bytes differ (pointer values)")
    assert len(bytes_c) == len(bytes_e), (len(bytes_c), len(bytes_e))
    # values re-read by a fresh session are equal too
    f = _session(cfg, "f")
    assert not _diff(a["dump"], f["dump"]), "re-read after save differs"


def test_disable_after_quitting_in_maya_mode():
    cfg = _sandbox()
    a = _session(cfg, "a", "user_setup", "save")
    _session(cfg, "b", "enable", "make_maya", "save")       # quit in Maya mode
    c = _session(cfg, "c", "disable", "save")               # extension disabled (or removed) in Maya mode
    d = _diff(a["dump"], c["dump"])
    assert not d, "disable in Maya mode:\n" + "\n".join(d[:20])
    shutil.rmtree(os.path.dirname(cfg))
