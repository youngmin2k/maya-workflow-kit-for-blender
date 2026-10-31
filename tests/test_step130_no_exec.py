"""#40: the package runs no code of its own and touches no import machinery.

Extension review: no ``exec`` / ``eval`` / ``compile(..., 'exec')``, no ``__import__`` hooks or ``builtins`` changes,
no ``sys.path`` / ``sys.modules`` access, no ``importlib`` loaders. User code (Command Line, Script Editor, shelf
buttons) runs through Blender's own ``text.run_script`` (``command_line/runner.py``).

Comments and docstrings are scanned too: a reviewer greps the whole file.
"""

import os
import re

AUTO_ENABLE = False
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "src", "allset")

PATTERNS = {
    "exec": re.compile(r"\bexec\s*\("),
    "execfile": re.compile(r"\bexecfile\s*\("),
    "eval": re.compile(r"(?<![\w.])eval\s*\("),
    "compile exec/eval": re.compile(r"(?<![\w.])compile\s*\(.*['\"](exec|eval|single)['\"]"),
    "__import__": re.compile(r"__import__"),
    "builtins": re.compile(r"\bimport\s+builtins\b|\bbuiltins\.|__builtins__"),
    "sys.path": re.compile(r"\bsys\.path\b"),
    "sys.modules": re.compile(r"\bsys\.modules\b"),
    "importlib": re.compile(r"\bimportlib\b"),
}

# Files other lanes clean up (keymap = lane K). The main session makes this empty after merging the lanes:
# then every hit fails.
PENDING_OTHER_LANES = {"keymap/ic_data.py"}


def _hits():
    out = []
    for base, dirs, files in os.walk(PKG):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            rel = os.path.relpath(path, PKG).replace(os.sep, "/")
            for i, line in enumerate(open(path, encoding="utf-8"), 1):
                for what, pat in PATTERNS.items():
                    if pat.search(line):
                        out.append((rel, i, what, line.strip()))
    return out


def test_patterns_find_what_they_should():
    samples = {"exec": "exec(code, ns)", "eval": "x = eval(s)", "compile exec/eval": "compile(t, 'f', 'exec')",
               "__import__": "b['__import__'] = f", "builtins": "import builtins", "sys.path": "sys.path.append(p)",
               "sys.modules": "sys.modules.get(n)", "importlib": "import importlib.util", "execfile": "execfile(p)"}
    for what, line in samples.items():
        assert PATTERNS[what].search(line), what
    for ok in ("ast.literal_eval(v)", "re.compile(r'x')", "bpy.ops.allset.command_line_exec(command=c)",
               "class ALLSET_OT_command_line_exec(Op):"):
        assert not any(p.search(ok) for p in PATTERNS.values()), ok


def test_no_code_execution_or_import_machinery():
    hits = _hits()
    own = [h for h in hits if h[0] not in PENDING_OTHER_LANES]
    assert not own, "\n".join(f"{r}:{i}: [{w}] {line}" for r, i, w, line in own)
    pending = [h for h in hits if h[0] in PENDING_OTHER_LANES]
    if pending:
        print("expected to be fixed by another lane (make this test strict after the merge):\n"
              + "\n".join(f"  {r}:{i}: [{w}] {line}" for r, i, w, line in pending))
