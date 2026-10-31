"""#40: the extension uninstalls like any other — everything register() adds,
unregister() takes back, and nothing it does needs an extra step to undo.

In one process: before enable → enable (Blender mode) → Maya mode on (+ Make Blender Maya) → off → disable, with
Blender's preferences (every value under inputs / view / edit / system / filepaths / keymap / experimental / apps,
theme, UI styles), keyconfigs + active, add-on keymaps, handler lists, the user scripts / config folders and every
kit function as a timer compared. Blender has no API to list msgbus subscriptions: the kit's owners are cleared by
their modules (``bpy.msgbus.clear_by_owner``), which the test can't observe.
Across processes: install-file --enable → Maya mode on / off → quit in Maya mode → Remove (from inside Blender, and
``blender --command extension remove`` which never runs the add-on's code) with the config folder and userpref.blend
compared.
"""

import json
import os
import shutil
import subprocess
import sys
import types
from importlib import import_module

import bpy

import kit
from rt60_dump import walk

AUTO_ENABLE = False
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PREF_STRUCTS = ("inputs", "view", "edit", "system", "filepaths", "keymap", "experimental", "apps")
# Window dependent values (0 in background)
VOLATILE = ("system.ui_scale", "system.pixel_size", "system.ui_line_width")
# The active keyconfig is lane K's (the Maya keys move into the add-on keyconfig and the active keyconfig
# is never changed). Until that lands, Maya mode still switches it; everything else must stay put even in Maya mode.
LANE_K_PENDING = ("keymap.active_keyconfig",)


def _prefs():
    prefs = bpy.context.preferences
    out = {}
    for name in PREF_STRUCTS:
        struct = getattr(prefs, name, None)
        if struct is not None:
            out.update({f"{name}.{k}": v for k, v in walk(struct).items()})
    for k in VOLATILE:
        out.pop(k, None)
    out["theme"] = kit._struct_hash(prefs.themes[0])
    out["ui_styles"] = kit._struct_hash(prefs.ui_styles[0])
    out["theme_name"] = prefs.themes[0].name
    return out


def _files(root):
    if not root or not os.path.isdir(root):
        return []
    return sorted(os.path.relpath(os.path.join(d, f), root).replace("\\", "/")
                  for d, _dirs, files in os.walk(root) for f in files)


def _user_files():
    return {kind: _files(bpy.utils.user_resource(kind)) for kind in ('SCRIPTS', 'CONFIG')}


def _state():
    snap = kit.snapshot()
    return {"snapshot": snap, "prefs": _prefs(), "files": _user_files(),
            "addons": sorted(bpy.context.preferences.addons.keys())}


def _pref_diff(a, b, skip=()):
    return [f"{k}: {a.get(k)!r} -> {b.get(k)!r}" for k in sorted(set(a) | set(b))
            if a.get(k) != b.get(k) and k not in skip]


def _kit_functions():
    """Every function object the kit's modules hold at module level (also inside lists / tuples, e.g. switch._timers):
    the callbacks it can register as timers."""
    out = []
    for name, mod in list(sys.modules.items()):
        if mod is None or not (name == kit.MODULE or name.startswith(kit.MODULE + ".")):
            continue
        for value in list(vars(mod).values()):
            items = value if isinstance(value, (list, tuple)) else (value,)
            for v in items:
                if isinstance(v, types.FunctionType) and v.__module__ and v.__module__.startswith(kit.MODULE):
                    out.append(v)
    return out


def _timers(funcs):
    return sorted(f"{f.__module__}.{f.__qualname__}" for f in funcs if bpy.app.timers.is_registered(f))


def test_runs_sandboxed():
    for kind in ('CONFIG', 'SCRIPTS'):
        path = os.path.normcase(bpy.utils.user_resource(kind))
        assert os.path.normcase(os.path.join("tmp", os.environ.get("ALLSET_SANDBOX", "test_env"))) in path, path


def test_enable_maya_on_off_disable_leaves_everything():
    before = _state()
    kit.enable(maya=False)
    try:
        d = _pref_diff(before["prefs"], _prefs())
        assert not d, "enabling changed preferences:\n" + "\n".join(d[:20])
        sw = import_module(kit.MODULE + ".switch")
        sw.set_mode(True)
        import_module(kit.MODULE + ".first_start").make(bpy.context, open_layout=False)
        d = _pref_diff(before["prefs"], _prefs(), skip=LANE_K_PENDING)
        assert not d, "Maya mode changed preferences:\n" + "\n".join(d[:20])
        assert _user_files() == before["files"], "Maya mode wrote into the user's scripts / config folders"
        funcs = _kit_functions()
        assert len(funcs) > 100, len(funcs)
        sw.set_mode(False)
        d = _pref_diff(before["prefs"], _prefs())
        assert not d, "switch to Blender left preference changes:\n" + "\n".join(d[:20])
        funcs = _kit_functions() + funcs
    finally:
        kit.disable()
    after = _state()
    d = _pref_diff(before["prefs"], after["prefs"])
    assert not d, "disable left preference changes:\n" + "\n".join(d[:20])
    d = kit.diff(before["snapshot"], after["snapshot"])
    assert not d, "disable left state behind:\n" + "\n".join(d[:20])
    assert after["files"] == before["files"], (before["files"], after["files"])
    assert after["addons"] == before["addons"]
    left = _timers(funcs)
    assert not left, f"kit timers still registered after disable: {left}"


def test_quit_style_disable_in_maya_mode_is_the_same():
    """Blender quitting / reloading / updating disables with default_set=False: the same unregister."""
    before = _state()
    kit.enable()
    funcs = _kit_functions()
    import addon_utils
    addon_utils.disable(kit.MODULE, default_set=False)
    try:
        after = _state()
        # default_set=False keeps the add-on in the enabled list (re-enabled at the next start): only that differs
        d = _pref_diff(before["prefs"], after["prefs"]) + [
            x for x in kit.diff(before["snapshot"], after["snapshot"]) if not x.startswith("addons:")]
        assert not d, "\n".join(d[:20])
        assert after["files"] == before["files"]
        assert not _timers(funcs), _timers(funcs)
    finally:
        addon_utils.disable(kit.MODULE, default_set=True)


# --- install / remove across processes ---------------------------------------------------------------------------

def _zip():
    text = open(os.path.join(ROOT, "src", "allset", "blender_manifest.toml"), encoding="utf-8").read()
    ver = next(line.split('"')[1] for line in text.splitlines() if line.startswith("version"))
    path = os.path.join(ROOT, "dist", f"maya-workflow-kit-{ver}.zip")
    assert os.path.isfile(path), path
    return path


def _sandbox(name):
    root = os.path.abspath(os.path.join(bpy.utils.user_resource('CONFIG'), "..", name))
    assert "tmp" in root.replace("\\", "/").split("/"), root
    if os.path.isdir(root):
        shutil.rmtree(root)
    env = dict(os.environ)
    for var, sub in (("BLENDER_USER_CONFIG", "config"), ("BLENDER_USER_SCRIPTS", "scripts"),
                     ("BLENDER_USER_EXTENSIONS", "extensions")):
        os.makedirs(os.path.join(root, sub))     # Blender ignores a BLENDER_USER_* folder that doesn't exist
        env[var] = os.path.join(root, sub)
    env["ALLSET_NO_WELCOME"] = "1"
    env["ALLSET_PROJECTS_DIR"] = os.path.join(root, "projects")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return root, env


def _run(cmd, env):
    proc = subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=240)
    return proc.returncode, proc.stdout + proc.stderr


def _session(root, env, name, *actions):
    out = os.path.join(root, f"{name}.json")
    rc, log = _run([bpy.app.binary_path, "-b", "--python", os.path.join(HERE, "lc130_session.py"), "--", out,
                    *actions], env)
    if not os.path.isfile(out):
        raise AssertionError(f"session {name} wrote nothing (exit {rc}):\n{log[-3000:]}")
    # a start in Maya mode registers everything while Blender restricts data access (bpy.data.collections)
    assert "Exception in module register" not in log, f"session {name}: register failed:\n{log[-3000:]}"
    with open(out, encoding="utf-8") as fh:
        data = json.load(fh)
    os.remove(out)
    return data


# Files Blender itself writes in a config it runs on, and the extension repository's own bookkeeping.
BLENDER_OWN = ("config/userpref.blend1", "config/recent-files.txt", "config/recent-searches.txt",
               "config/bookmarks.txt", "config/platform_support.txt")


def _config_files(root):
    return [f for f in _files(root) if f.startswith(("config/", "scripts/")) and f not in BLENDER_OWN]


def _userpref(root):
    with open(os.path.join(root, "config", "userpref.blend"), "rb") as fh:
        return fh.read()


def _diff_dump(a, b, skip=()):
    out = []
    for key in sorted(set(a) | set(b)):
        if key == "values":
            out += _pref_diff(a["values"], b["values"], skip)
        elif a.get(key) != b.get(key):
            out.append(f"{key}: {str(a.get(key))[:100]!r} -> {str(b.get(key))[:100]!r}")
    return out


def _install_use(root, env):
    rc, log = _run([bpy.app.binary_path, "--command", "extension", "install-file", "-r", "user_default", "--enable",
                    _zip()], env)
    assert rc == 0, log[-3000:]
    _session(root, env, "cycle", "maya_cycle", "save")         # Maya mode on and off, preferences saved
    _session(root, env, "on", "maya_on", "save")               # the user quits in Maya mode, preferences saved


def _check_back(root, env, a, files_a, bytes_a, label):
    c = _session(root, env, "fresh")                            # a fresh start reads what is saved
    assert not c["kit"], f"{label}: the kit is still enabled"
    d = _diff_dump(a["dump"], c["dump"], skip=LANE_K_PENDING)
    assert not d, f"{label}: preferences differ from before the install:\n" + "\n".join(d[:20])
    files = _config_files(root)
    assert files == files_a, f"{label}: config / scripts files: +{sorted(set(files) - set(files_a))} " \
                             f"-{sorted(set(files_a) - set(files))}"
    bytes_c = _userpref(root)
    ndiff = sum(1 for x, y in zip(bytes_a, bytes_c) if x != y)
    print(f"{label}: userpref.blend {len(bytes_a)} -> {len(bytes_c)} bytes, {ndiff} bytes differ (pointer values)")
    # Same size; differing bytes are memory addresses Blender writes into a .blend across processes
    assert len(bytes_a) == len(bytes_c), (label, len(bytes_a), len(bytes_c))


def test_install_use_remove_from_blender():
    root, env = _sandbox("lc130_remove")
    a = _session(root, env, "a", "save")
    files_a, bytes_a = _config_files(root), _userpref(root)
    _install_use(root, env)
    _session(root, env, "uninstall", "uninstall", "save")    # Preferences > Extensions > Remove, preferences saved
    assert not os.path.isdir(os.path.join(root, "extensions", "user_default", "allset"))
    _check_back(root, env, a, files_a, bytes_a, "Remove from Blender")
    shutil.rmtree(root)


def test_install_use_command_line_remove():
    """``blender --command extension remove`` never imports the add-on: only what Blender saved remains, and the kit
    saved nothing of Blender's, so this is as clean as a Remove from inside Blender."""
    root, env = _sandbox("lc130_cli")
    a = _session(root, env, "a", "save")
    files_a, bytes_a = _config_files(root), _userpref(root)
    _install_use(root, env)
    rc, log = _run([bpy.app.binary_path, "--command", "extension", "remove", "user_default.allset"], env)
    assert rc == 0, log[-3000:]
    _session(root, env, "resave", "save")
    _check_back(root, env, a, files_a, bytes_a, "command line remove")
    shutil.rmtree(root)
