# SPDX-License-Identifier: GPL-3.0-or-later
"""Run one command-line entry: Python only (MEL is not supported).

Maya's Command Line.

The kit runs no code itself (extension review, issue #40): the entry is written into a Text datablock and run by
Blender's own ``text.run_script`` — the path of the Text Editor's Run Script. Before that the source is rewritten
with plain text edits (``prepare``):

- ``import maya.cmds as cmds`` / ``from maya import cmds`` / ``import maya.cmds`` / ``from maya.cmds import ls`` import
  the kit's ``cmds_shim`` (``maya_stub`` for ``maya``) by its real package path — no import hook, nothing new in the
  module table;
- one line in front hands the run's ``globals()`` to the runner (``bind``), which fills in the session names
  (``bpy``, ``C``, ``D``, ``cmds``, ``mc`` and the variables of earlier entries) and reads the run's variables back
  afterwards — also after an error, like Maya — so they persist between entries;
- a final expression ``x`` becomes ``_allset_result = (x)``: its value is the Maya-style ``# Result: ... #``.

``text.run_script`` runs in a fresh ``__main__`` namespace and reports a Python error as an operator error (a
RuntimeError when called from Python): its last traceback line is the result line.
"""

import ast
import contextlib
import io
import re

import bpy

HISTORY_LIMIT = 20
TEXT_NAME = ".allset_command_line"      # hidden Text the Command Line / Script Editor entry runs from
RESULT = "_allset_result"
RUNNER = "_allset_runner"
_PKG = __package__                      # "<extension package>.command_line"

_namespace = {}
history = []
_runs = []                              # per running entry (nested runs possible): {"names": its globals()}
_last_run = {}                          # the last finished run's details ("kinds", "error")
CONSOLE = "<maya console>"              # Maya's file name of Script Editor / Command Line code


class Result:
    """``text`` = the one line the Command Line result field shows; ``lines`` = what the run writes into the Script
    Editor history, as (kind, text) with kind in ``KINDS``."""
    __slots__ = ("text", "error", "lines")

    def __init__(self, text="", error=False, lines=None):
        self.text = text
        self.error = error
        if lines is None:
            lines = [("ERROR" if error else "RESULT", text)] if text else []
        self.lines = lines

    def __repr__(self):
        return f"Result({self.text!r}, error={self.error})"


def namespace():
    """Session names every run starts with: bpy, C, D, cmds / mc (maya.cmds subset) + earlier entries' variables."""
    if not _namespace:
        from . import cmds_shim
        _namespace.update(bpy=bpy, C=bpy.context, D=bpy.data, cmds=cmds_shim, mc=cmds_shim)
    return _namespace


def bind(names):
    """Called by the first line of a prepared entry with its ``globals()``: give it the session names and keep the
    dictionary, read after the run (Blender doesn't clear a Run Script namespace)."""
    names.update(namespace())
    if _runs:
        _runs[-1]["names"] = names


def _collect(run, persist):
    """(result value, variables) of a finished run; variables go into the session when ``persist``."""
    names = run.get("names") or {}
    value = names.pop(RESULT, None)
    if persist:
        for key, item in names.items():
            if not key.startswith("__") and key != RUNNER:
                _namespace[key] = item
    return value


def reset():
    _namespace.clear()
    history.clear()


def _remember(source):
    if history and history[-1] == source:
        return
    history.append(source)
    del history[:-HISTORY_LIMIT]


# --- source rewriting (plain text edits on the parsed statement positions) ---------------------------------------

def _maya_import(node):
    """Replacement text of an import statement that names ``maya`` / ``maya.cmds``, else None."""
    if isinstance(node, ast.Import):
        if not any(a.name in ("maya", "maya.cmds") for a in node.names):
            return None
        parts = []
        for a in node.names:
            if a.name == "maya.cmds" and a.asname:
                parts.append(f"from {_PKG} import cmds_shim as {a.asname}")
            elif a.name in ("maya", "maya.cmds"):              # binds ``maya`` (with .cmds)
                parts.append(f"from {_PKG} import maya_stub as {a.asname or 'maya'}")
            else:
                parts.append(f"import {a.name}" + (f" as {a.asname}" if a.asname else ""))
        return "; ".join(parts)
    if isinstance(node, ast.ImportFrom) and node.level == 0:
        if node.module == "maya.cmds":
            names = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in node.names)
            return f"from {_PKG}.cmds_shim import {names}"
        if node.module == "maya" and any(a.name == "cmds" for a in node.names):
            names = ", ".join(("cmds_shim as " + (a.asname or "cmds")) if a.name == "cmds"
                              else (a.name + (f" as {a.asname}" if a.asname else "")) for a in node.names)
            return f"from {_PKG}.maya_stub import {names}"
    return None


def prepare(source, tree=None):
    """The text that runs for ``source`` (see the module docstring); ``tree`` = ``ast.parse(source)``."""
    tree = tree if tree is not None else ast.parse(source)
    data = source.encode("utf-8")               # ast column offsets count UTF-8 bytes
    starts = [0]
    for line in data.split(b"\n")[:-1]:
        starts.append(starts[-1] + len(line) + 1)

    def span(node):
        return (starts[node.lineno - 1] + node.col_offset, starts[node.end_lineno - 1] + node.end_col_offset)

    edits = []
    for node in ast.walk(tree):
        text = _maya_import(node)
        if text is not None:
            edits.append((*span(node), text.encode("utf-8")))
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        a, b = span(tree.body[-1])
        edits.append((a, b, f"{RESULT} = (".encode("utf-8") + data[a:b] + b"\n)"))
    for a, b, text in sorted(edits, reverse=True):
        data = data[:a] + text + data[b:]
    head = f"from {_PKG} import runner as {RUNNER}; {RUNNER}.bind(globals())\n"
    return head + data.decode("utf-8") + "\n"


# --- running through Blender's Run Script ------------------------------------------------------------------------

def _error_line(message):
    """Last traceback line of a ``text.run_script`` error report ("ZeroDivisionError: division by zero")."""
    return _parse_error(message)[0]


_FRAME = re.compile(r'^\s*File "(.*)", line (\d+)(?:, in (.*))?$')
_KIT_DIR = __file__.replace("\\", "/").rsplit("/", 2)[0]        # the extension package folder


def _parse_error(message, text_name=None):
    """(last line, line number in the entry or None, Maya traceback lines) of a ``text.run_script`` error report.

    Blender 4.5 reports ``Error: Python: Traceback (most recent call last):`` / ``File "<backslash><text>", line N,
    in <module>`` / ... / ``ZeroDivisionError: division by zero`` / ``Location: ...bpy/ops.py:109`` (step
    216). Frames of the entry Text become Maya's ``<maya console>`` with the line of the entry (the prepared source has one line in
    front); frames inside the kit (the ``cmds`` look-alike) are dropped: Maya's commands are C++ and leave none."""
    lines = [ln for ln in message.splitlines() if ln.strip() and not ln.startswith("Location:")]
    for prefix in ("Error: Python: ", "Error: "):
        if lines and lines[0].startswith(prefix):
            lines[0] = lines[0][len(prefix):]
    last = lines[-1].strip() if lines else message.strip()
    lineno, trace, keep = None, [], True
    for ln in lines[:-1]:
        if ln.startswith("Traceback ("):
            continue
        m = _FRAME.match(ln)
        if m:
            fname, num, where = m.group(1), int(m.group(2)), m.group(3)
            if text_name is not None and fname.lstrip("\\/") == text_name:
                lineno = num - 1
                keep = True
                trace.append(f'  File "{CONSOLE}", line {lineno}' + (f", in {where}" if where else ""))
                continue
            keep = not fname.replace("\\", "/").startswith(_KIT_DIR)
            if keep:
                trace.append(ln.rstrip())
            continue
        if keep:
            trace.append(ln.rstrip())
    if trace or lineno is not None:
        trace.append(last)
    return last, lineno, trace


def run_text(code, name=TEXT_NAME, persist=True):
    """Run prepared ``code`` with Blender's Run Script from a temporary Text ``name``; (result value, error line or
    None, printed text)."""
    text = bpy.data.texts.new(name)
    text_name = text.name
    text.write(code)
    run = {"names": None}
    _runs.append(run)
    out = io.StringIO()
    error = None
    run["kinds"] = {}
    try:
        with contextlib.redirect_stdout(out), bpy.context.temp_override(edit_text=text):
            bpy.ops.text.run_script()
    except RuntimeError as ex:
        run["message"] = str(ex)
        error = _parse_error(str(ex), text_name)
        run["error"] = error
        error = error[0]
    finally:
        _runs.pop()
        leftover = bpy.data.texts.get(text_name)     # the script may have loaded a file or removed it
        if leftover is not None:
            bpy.data.texts.remove(leftover)
    printed = out.getvalue()
    if printed:
        print(printed, end="")              # still reach the system console
    if error is not None:
        # Blender also prints the error report to stdout (BPy_reports_write_stdout): not the script's output
        head = (run.get("message") or "").strip().splitlines()[:1]
        cut = printed.rfind(head[0]) if head else -1
        if cut >= 0:
            printed = printed[:cut]
    value = _collect(run, persist)
    if error is None and run["names"] is None:
        error = "RuntimeError: the script did not run"
    _last_run.clear()
    _last_run.update(run)
    return value, error, printed


def run(source, name=TEXT_NAME, persist=True, remember=True):
    """Run ``source`` (Command Line / Script Editor / shelf button); the value of a final expression is the result."""
    source = source.strip()
    if not source:
        return Result()
    if remember:
        _remember(source)
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as ex:
        hint = mel_to_python(source)
        if hint == "":
            return Result("# Error: MEL is not supported, use Python", True)
        if hint is not None:
            return Result(f"# Error: no MEL, use Python: {hint}", True)
        return Result(f"# Error: {_with_line('SyntaxError: ' + str(ex.msg), ex.lineno)}", True)

    value, error, printed = run_text(prepare(source, tree), name, persist)
    lines = _printed_lines(printed, _last_run.get("kinds") or {})
    if error is not None:
        from . import cmds_shim
        _last, lineno, trace = _last_run.get("error") or (error, None, [])
        text = f"# Error: {_with_line(error, lineno)}"
        m = re.match(r"NameError: name '(\w+)' is not defined", error)
        if m and hasattr(cmds_shim, m.group(1)):
            text += f" (Maya command? use cmds.{m.group(1)}(...))"
        lines.append(("ERROR", text))
        if option("se_stack_trace") and trace:
            lines += [("TRACE", "# " + t) for t in ["Traceback (most recent call last):"] + trace]
        return Result(text, True, lines)
    if value is not None:
        text = f"# Result: {_format(value)} #"
        return Result(text, False, lines + [("RESULT", text)])
    out = printed.strip().splitlines()
    return Result(out[-1] if out else "", False, lines)


def _format(value):
    if isinstance(value, bpy.types.ID):
        return value.name
    return repr(value)


# --- Script Editor History menu: Maya scriptEditorInfo options as add-on preferences -------------------
#
# Kinds of history lines: ECHO (the executed input), OUTPUT (printed text), RESULT ("# Result: ... #"), INFO /
# WARNING / ERROR (messages), TRACE (the traceback after an error, Show Stack Trace). Maya prints a Python error as
# "# Error: <Type>: file <maya console> line <n>: <message>" with Line numbers in errors on, without the
# "file ... line n:" part off; Show Stack Trace adds the traceback lines, each behind "# ".

KINDS = ("ECHO", "OUTPUT", "RESULT", "INFO", "WARNING", "ERROR", "TRACE")
OPTION_DEFAULTS = {         # default states, like Maya (Script Editor History menu check items)
    "se_batch_render_messages": True, "se_echo_all": False, "se_line_numbers": True, "se_stack_trace": False,
    "se_suppress_results": False, "se_suppress_info": False, "se_suppress_warnings": False,
    "se_suppress_errors": False, "se_suppress_stack_window": False, "se_suppress_dup_vars": False,
    "se_history_output": 'BOTH',
}
SUPPRESSED_BY = {"RESULT": "se_suppress_results", "INFO": "se_suppress_info", "WARNING": "se_suppress_warnings",
                 "ERROR": "se_suppress_errors", "TRACE": "se_suppress_errors"}
LOG_LIMIT = 500
log = []                    # (kind, language, text) lines the kit wrote into the Script Editor history
_PREFIXES = (("# Warning:", "WARNING"), ("// Warning:", "WARNING"), ("# Error:", "ERROR"), ("// Error:", "ERROR"),
             ("# Result:", "RESULT"), ("// Result:", "RESULT"))


def option(name):
    """A Script Editor History option (add-on preference ``name``); the default state (like Maya) without the preferences."""
    try:
        from .. import preferences
        return getattr(preferences.get(), name)
    except (KeyError, AttributeError):
        return OPTION_DEFAULTS[name]


def _with_line(error, lineno):
    """``"ZeroDivisionError: division by zero"`` with Maya's "file <maya console> line n:" (Line numbers in errors)."""
    if lineno is None or not option("se_line_numbers"):
        return error
    kind, sep, msg = error.partition(": ")
    return f"{kind}: file {CONSOLE} line {lineno}: {msg}" if sep else f"{kind}: file {CONSOLE} line {lineno}"


def message(kind, text):
    """Print a Maya message line from kit code run inside an entry (``cmds.warning`` -> "# Warning: text #"); the
    history knows its kind (``KINDS``: INFO / WARNING / ERROR), so the Suppress options drop it."""
    line = {"WARNING": f"# Warning: {text} #", "ERROR": f"# Error: {text} #"}.get(kind, str(text))
    if _runs:
        _runs[-1].setdefault("kinds", {})[line] = kind
    print(line)
    return line


def _printed_lines(printed, kinds):
    out = []
    for ln in printed.splitlines():
        kind = kinds.get(ln) or next((k for p, k in _PREFIXES if ln.startswith(p)), "OUTPUT")
        out.append((kind, ln))
    return out


def shown(kind, lang="Python"):
    """Does a history line of ``kind`` from a ``lang`` ("Python" / "MEL") run reach the history?"""
    output = option("se_history_output")
    if (output == 'MEL' and lang != "MEL") or (output == 'PYTHON' and lang != "Python"):
        return False
    key = SUPPRESSED_BY.get(kind)
    return not (key and option(key))


def history_lines(echo, res, lang="Python"):
    """(kind, text) lines a Script Editor run writes into the history: the echoed input, then the run's lines, after
    the History options. Kept in ``log`` too."""
    lines = ([("ECHO", echo.rstrip())] if echo and echo.strip() else []) + list(res.lines)
    out = [(kind, text) for kind, text in lines if text and shown(kind, lang)]
    _log(out, lang)
    return out


def _log(lines, lang):
    log.extend((kind, lang, text) for kind, text in lines)
    del log[:-LOG_LIMIT]


def action_call(kind, target, props):
    """The Python line Echo All Commands prints for a menu action (``menu_map.normalize`` form): the call the kit
    runs, so it can be run again from the Python tab. Maya prints its runtime command (``CreatePolygonCube;``),
    which the kit has no table of."""
    args = ", ".join(f"{k}={v!r}" for k, v in props.items())
    if kind in ("op", "v3d"):
        return f"bpy.ops.{target}({args})"
    if kind == "tool":
        return f"bpy.ops.wm.tool_set_by_id(name={target!r})"
    if kind in ("menu", "pie"):
        return f"bpy.ops.wm.call_menu{'_pie' if kind == 'pie' else ''}(name={target!r})"
    if kind == "prop":
        top = _PKG.rpartition(".")[0]
        path = (f"bpy.context.preferences.addons[{top!r}].preferences.{target[len('addon_prefs.'):]}"
                if target.startswith("addon_prefs.") else f"bpy.context.{target}")
        return f"{path} = {props['value']!r}" if "value" in props else f"{path} = not {path}"
    return f"# {target}"


def echo_command(text):
    """Echo All Commands: write a finished menu / shelf / marking-menu command into the Script Editor history (an
    OPERATOR-type report: Blender's Info editor lists it, the status bar shows no banner). Nothing when off."""
    if not option("se_echo_all") or not shown("ECHO", "Python"):
        return False
    _log([("ECHO", text)], "Python")
    from .. import compat
    if compat.has_op(bpy.ops.allset, "script_echo"):
        try:
            bpy.ops.allset.script_echo(text=text)
        except RuntimeError:
            pass
    return True


def echo_action(action):
    """``echo_command`` for a menu action (``marking/modal.run_action``)."""
    if not option("se_echo_all"):
        return False
    from ..ui import menu_map
    try:
        spec = menu_map.normalize(action)
    except (TypeError, ValueError, IndexError):
        return False
    return echo_command(action_call(*spec)) if spec is not None else False


# --- MEL hint: "polyCube -w 2 -h 3;" -> "cmds.polyCube(w=2, h=3)" -------------------

# A MEL statement: command word, then flags / numbers / names / "strings" only.
_MEL_STATEMENT = re.compile(r'^\s*[A-Za-z_]\w*(\s+("(?:[^"\\]|\\.)*"|-?[\w.|:\[\]]+))*\s*$')
_TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|\S+')


def _value(token):
    if token.startswith('"'):
        return token
    try:
        float(token)
        return token
    except ValueError:
        return repr(token)


def _statement(stmt):
    tokens = _TOKEN.findall(stmt)
    if not tokens:
        return None
    cmd, args, flags = tokens[0], [], []
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if re.match(r"^-[A-Za-z]\w*$", tok):
            values = []
            i += 1
            while i < len(tokens) and not re.match(r"^-[A-Za-z]\w*$", tokens[i]):
                values.append(tokens[i])
                i += 1
            if len(values) == 1:
                flags.append(f"{tok[1:]}={_value(values[0])}")
            else:
                flags.append(f"{tok[1:]}=True")
                args.extend(_value(v) for v in values)
            continue
        args.append(_value(tok))
        i += 1
    return f"cmds.{cmd}({', '.join(args + flags)})"


def mel_to_python(source):
    """Best-effort cmds translation of MEL-looking input; "" = MEL without a
    translation (variables, backquotes); None = doesn't look like MEL."""
    if "$" in source or "`" in source:
        return ""
    parts = [p for p in source.split(";") if p.strip()]
    if not parts or not all(_MEL_STATEMENT.match(p) for p in parts):
        return None
    # Needs a MEL marker, so plain typos ("hello world") stay Python syntax errors.
    if not (source.rstrip().endswith(";") or re.search(r"\s-[A-Za-z]", source) or '"' in source):
        return None
    out = [_statement(p) for p in parts]
    return "; ".join(o for o in out if o)
