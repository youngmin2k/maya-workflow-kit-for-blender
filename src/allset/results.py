# SPDX-License-Identifier: GPL-3.0-or-later
"""Where a kit command's result goes: Maya's Command Line result field, not Blender's status-bar report.

Maya prints a command's result ("// Result: group1") in the Command Line result field at the bottom right and the
Script Editor history; nothing pops up over the Help Line. Blender shows an operator's INFO report as a banner in
the status bar (step-154 dogfood G1: "Grouped 2 object(s) into group1" with Blender's ⓘ). So kit operators report
results through ``result``: the text goes to the result field (``command_line.show_result``). Warnings and errors stay
Blender reports (Maya shows those in the Help Line / Command Line in yellow / red too). Tool usage hints (what the
mouse does in an active tool) stay INFO reports: Maya shows those in the Help Line, which is where Blender's status
bar banner sits in the kit layout (``HINT_REPORTS`` in tests/test_step161_messages.py lists them).
"""


def result(op, text):
    """Show ``text`` as the result of ``op`` (a kit operator) in the Command Line result field."""
    from .command_line import show_result, undo_text
    undo_text.operator_step(op)           # its undo step's name, for Maya's "Undo: <command>"
    show_result(str(text))
