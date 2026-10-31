"""Maya Script Editor > History menu options (Echo All Commands, Line numbers in errors, Show Stack Trace,
Suppress ..., History Output) as add-on preferences that change what the kit runner writes into the Script Editor
history. Factory states = Maya 2022's check marks."""

import os
from importlib import import_module

import bpy

import kit

runner = import_module(kit.MODULE + ".command_line.runner")
se = import_module(kit.MODULE + ".ui.script_editor")
preferences = import_module(kit.MODULE + ".preferences")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
notices = import_module(kit.MODULE + ".ui.notices")
data = import_module(kit.MODULE + ".ui.editor_menu_data")
modal = import_module(kit.MODULE + ".marking.modal")

# default states (like Maya) of the Script Editor History menu (check marks)
MAYA_FACTORY = {"se_batch_render_messages": True, "se_echo_all": False, "se_line_numbers": True,
                "se_stack_trace": False, "se_suppress_results": False, "se_suppress_info": False,
                "se_suppress_warnings": False, "se_suppress_errors": False, "se_suppress_dup_vars": False,
                "se_suppress_stack_window": False, "se_history_output": 'BOTH'}
ITEMS = {"Batch Render Messages": "se_batch_render_messages", "Echo All Commands": "se_echo_all",
         "Line numbers in errors": "se_line_numbers", "Show Stack Trace": "se_stack_trace",
         "Suppress Command Results": "se_suppress_results", "Suppress Info Messages": "se_suppress_info",
         "Suppress Warning Messages": "se_suppress_warnings", "Suppress Error Messages": "se_suppress_errors",
         "Suppress Duplicate Variable Messages": "se_suppress_dup_vars",
         "Suppress Stack Window": "se_suppress_stack_window"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RADIO = {"Show Both": 'BOTH', "Show MEL Only": 'MEL', "Show Python Only": 'PYTHON'}


def _prefs():
    return preferences.get()


def _reset():
    p = _prefs()
    for k, v in MAYA_FACTORY.items():
        setattr(p, k, v)


def _history(code, lang="Python"):
    res = runner.run(code, remember=False) if lang == "Python" else runner.Result("// Error: MEL", True)
    return runner.history_lines(code, res, lang), res


def test_menu_items_are_mapped_check_and_radio_items():
    for label, key in ITEMS.items():
        path = f"Script Editor/History/{label}"
        assert menu_map.MAP[path] == ("prop", f"addon_prefs.{key}", {}), path
        assert data.CHECKS[path] == 'check', path
    for label, value in RADIO.items():
        path = f"Script Editor/History/History Output/{label}"
        assert menu_map.MAP[path] == ("prop", "addon_prefs.se_history_output", {"value": value}), path
        assert data.CHECKS[path] == 'radio', path
    assert "Script Editor/History" not in notices.NOTICES and "Script Editor/History" not in notices.CATEGORIES


def test_menu_item_toggles_and_sets_through_allset_menu_item():
    _reset()
    p = _prefs()
    assert bpy.ops.allset.menu_item(item="Script Editor/History/Show Stack Trace") == {'FINISHED'}
    assert p.se_stack_trace is True
    assert bpy.ops.allset.menu_item(item="Script Editor/History/Show Stack Trace") == {'FINISHED'}
    assert p.se_stack_trace is False
    assert bpy.ops.allset.menu_item(item="Script Editor/History/History Output/Show MEL Only") == {'FINISHED'}
    assert p.se_history_output == 'MEL'
    assert bpy.ops.allset.menu_item(item="Script Editor/History/History Output/Show Both") == {'FINISHED'}
    assert p.se_history_output == 'BOTH'
    _reset()


def test_line_numbers_in_errors():
    _reset()
    r = runner.run("x = 1\ny = 2\n1/0", remember=False)
    assert r.error and r.text == "# Error: ZeroDivisionError: file <maya console> line 3: division by zero", r
    r = runner.run("def g():\n    return nope_216\ng()", remember=False)
    assert r.text.startswith("# Error: NameError: file <maya console> line 2: name 'nope_216' is not defined"), r
    r = runner.run("a = (1,\nb = 2", remember=False)        # caught before running: SyntaxError with its line
    assert r.error and r.text.startswith("# Error: SyntaxError: file <maya console> line "), r
    _prefs().se_line_numbers = False
    r = runner.run("x = 1\ny = 2\n1/0", remember=False)
    assert r.text == "# Error: ZeroDivisionError: division by zero", r
    r = runner.run("a = (1,\nb = 2", remember=False)
    assert r.text.startswith("# Error: SyntaxError: ") and "line" not in r.text.split(":", 2)[1], r
    _reset()


def test_show_stack_trace():
    _reset()
    code = "def inner():\n    return 1 / 0\ninner()"
    lines, res = _history(code)
    assert [k for k, _t in lines] == ["ECHO", "ERROR"], lines
    assert lines[1][1] == res.text == "# Error: ZeroDivisionError: file <maya console> line 2: division by zero"
    _prefs().se_stack_trace = True
    lines, res = _history(code)
    texts = [t for _k, t in lines]
    assert texts == [code, "# Error: ZeroDivisionError: file <maya console> line 2: division by zero",
                     "# Traceback (most recent call last):",
                     '#   File "<maya console>", line 3, in <module>',
                     '#   File "<maya console>", line 2, in inner',
                     "# ZeroDivisionError: division by zero"], texts
    assert res.text == texts[1], "the Command Line field keeps the one-line error"
    # a kit (cmds look-alike) frame is not part of the trace (Maya's commands leave none)
    lines, _res = _history("cmds.getAttr('no_such_node_216.tx')")
    trace = [t for k, t in lines if k == "TRACE"]
    assert trace and not any("cmds_" in t or "allset" in t for t in trace), trace
    _reset()


def test_suppress_options():
    _reset()
    code = "print('hello 216')\nprint('# Warning: careful #')\n40 + 2"
    kinds = [k for k, _t in _history(code)[0]]
    assert kinds == ["ECHO", "OUTPUT", "WARNING", "RESULT"], kinds
    p = _prefs()
    p.se_suppress_results = True
    assert [k for k, _t in _history(code)[0]] == ["ECHO", "OUTPUT", "WARNING"]
    p.se_suppress_warnings = True
    assert [k for k, _t in _history(code)[0]] == ["ECHO", "OUTPUT"]
    assert runner.run(code, remember=False).text == "# Result: 42 #", "the Command Line field still shows results"
    p.se_suppress_errors = True
    p.se_stack_trace = True
    assert [k for k, _t in _history("1/0")[0]] == ["ECHO"], "error + its trace suppressed"
    # info messages from kit code (runner.message, e.g. a cmds look-alike's displayInfo)
    _reset()
    import io, contextlib
    run = {"names": None}
    runner._runs.append(run)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            line = runner.message("INFO", "note 216")
            wline = runner.message("WARNING", "w 216")
    finally:
        runner._runs.pop()
    assert wline == "# Warning: w 216 #"
    res = runner.Result("", False, runner._printed_lines(f"{line}\n{wline}\n", run["kinds"]))
    assert [k for k, _t in runner.history_lines("", res)] == ["INFO", "WARNING"]
    p.se_suppress_info = True
    assert [k for k, _t in runner.history_lines("", res)] == ["WARNING"]
    # no effect in Blender, stored only
    for key in ("se_suppress_stack_window", "se_suppress_dup_vars", "se_batch_render_messages"):
        setattr(p, key, not getattr(p, key))
        assert [k for k, _t in _history("1 + 1")[0]] == ["ECHO", "RESULT"], key
    _reset()


def test_history_output_filters_by_language():
    _reset()
    p = _prefs()
    assert [k for k, _t in _history("1 + 1")[0]] == ["ECHO", "RESULT"]
    assert [k for k, _t in _history("polyCube;", "MEL")[0]] == ["ECHO", "ERROR"]
    p.se_history_output = 'MEL'
    assert _history("1 + 1")[0] == []
    assert [k for k, _t in _history("polyCube;", "MEL")[0]] == ["ECHO", "ERROR"]
    p.se_history_output = 'PYTHON'
    assert [k for k, _t in _history("1 + 1")[0]] == ["ECHO", "RESULT"]
    assert _history("polyCube;", "MEL")[0] == []
    _reset()


def test_script_run_operator_writes_filtered_history():
    """allset.script_run reports the filtered lines (the Info editor lists them); runner.log keeps them."""
    _reset()
    reported = []

    class Op:
        def report(self, types, text):
            reported.append((next(iter(types)), text))
    py = se.ensure_texts()
    _prefs().se_stack_trace = True
    lines = se.write_history(Op(), "1/0", runner.run("1/0", remember=False), "Python")
    assert [t for t, _x in reported] == ['INFO', 'ERROR', 'ERROR', 'ERROR', 'ERROR'], reported
    assert runner.log[-len(lines):] == [(k, "Python", t) for k, t in lines]
    assert py.get(se.LANG_PROP) == "Python"
    _reset()


def test_echo_all_commands():
    _reset()
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    n = len(runner.log)
    modal.run_action(bpy.context, ("allset.create", {"kind": 'CUBE'}))
    assert len(runner.log) == n, "factory: Echo All Commands off"
    _prefs().se_echo_all = True
    modal.run_action(bpy.context, ("allset.create", {"kind": 'CUBE'}))
    assert runner.log[-1] == ("ECHO", "Python", "bpy.ops.allset.create(kind='CUBE')"), runner.log[-1:]
    # the echoed line runs again from the Python tab
    count = len(bpy.data.objects)
    assert not runner.run(runner.log[-1][2], remember=False).error
    assert len(bpy.data.objects) == count + 1
    # a check item echoes its preference toggle; Show MEL Only hides the (Python) echo
    modal.run_action(bpy.context, menu_map.MAP["Script Editor/History/Show Stack Trace"])
    assert runner.log[-1][2].endswith(".preferences.se_stack_trace = not "
                                      + runner.log[-1][2].split(" = not ")[1]), runner.log[-1]
    _prefs().se_history_output = 'MEL'
    n = len(runner.log)
    modal.run_action(bpy.context, ("allset.create", {"kind": 'CUBE'}))
    assert len(runner.log) == n
    assert runner.action_call("tool", "builtin.move", {}) == "bpy.ops.wm.tool_set_by_id(name='builtin.move')"
    assert runner.action_call("menu", "ALLSET_MT_x", {}) == "bpy.ops.wm.call_menu(name='ALLSET_MT_x')"
    _reset()


def test_prefs_round_trip_and_disable_enable():
    """The options are this add-on's preferences: what the menu sets is what the runner reads; disable removes the
    echo operator, enable brings back the default states."""
    p = _prefs()
    p.se_stack_trace, p.se_history_output, p.se_line_numbers = True, 'PYTHON', False
    assert runner.option("se_stack_trace") is True and runner.option("se_history_output") == 'PYTHON'
    assert runner.option("se_line_numbers") is False
    kit.disable()
    assert not hasattr(bpy.types, "ALLSET_OT_script_echo"), "unregistered on disable"
    assert runner.option("se_line_numbers") is True, "without the preferences: the default state"
    kit.enable()
    p = _prefs()
    assert {k: getattr(p, k) for k in MAYA_FACTORY} == MAYA_FACTORY
    assert hasattr(bpy.types, "ALLSET_OT_script_echo")
