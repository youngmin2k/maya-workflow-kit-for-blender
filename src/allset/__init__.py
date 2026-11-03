# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Workflow Kit: make Blender feel like Maya (keymap, interaction, UI, concepts).

Shipped as one Blender 4.2+ extension; Blender reads ``blender_manifest.toml``. The
legacy add-on zip gets its ``bl_info`` from ``tools/build.py`` (the extension build carries none, as the
extension guidelines recommend).

Each feature area is a sub-package with its own ``register()`` /
``unregister()``. Order matters: preferences first (others may read them),
keymap last (keymap items reference operators registered before it). ``CORE``
stays registered; ``MODE`` is Maya mode, switched on and off at run time by
``switch``.

Opt-in: Maya mode is off after install, so enabling registers only CORE. Nothing persistent:
no module writes Blender's preferences or files outside the extension's folders, and
``unregister()`` takes back everything ``register()`` added — there is nothing to restore on disable or Remove.
"""

from . import i18n, preferences, translations, settings_io, switch, welcome, operators, ui, command_line, marking, first_start, keymap

# Always registered: the translations, the preferences (with the translation files box), settings export / import,
# the Maya / Blender switch and the opt-in.
CORE = (i18n, preferences, translations, settings_io, switch, welcome)
# "Maya mode": registered while the add-on preference ``maya_mode`` is on; switching to
# Blender unregisters them, which takes back everything they registered.
MODE = (operators, ui, command_line, marking, first_start, keymap)


def register():
    for mod in CORE:
        mod.register()
    if switch.is_on():
        # A failed Maya mode start (rolled back by ``register_mode``) must not take the add-on down with it: CORE
        # stays, so the user still has the Maya / Blender switch and can disable the kit (#199).
        try:
            switch.register_mode()
        except Exception as ex:
            switch.preferences_off()
            switch._report_failure(ex)


def unregister():
    preferences.save_backup()     # before any module runs: Blender may delete the preferences after this
    switch.unregister_mode()      # whatever Maya mode modules are registered (none after a failed start)
    for mod in reversed(CORE):
        mod.unregister()
