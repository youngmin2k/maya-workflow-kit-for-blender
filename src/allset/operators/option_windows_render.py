# SPDX-License-Identifier: GPL-3.0-or-later
"""Option boxes of the Render menu.

Render > Render Current Frame / Render Sequence / Batch Render run Blender's own render, so their option boxes have
no kit window (``WINDOWS`` is empty; option_windows._extend appends it). Render Current Frame ❒ / IPR Render Current
Frame ❒ open no window in Maya either: the Help Line reads 'Renderer "<name>" does not provide render options.' —
``NO_OPTIONS`` (option_windows.ALLSET_OT_option_generic).
"""

# Maya's warning for an option box its renderer has no window for; {name} = the render engine
NO_OPTIONS = {"Render/Render Current Frame": 'Renderer "{name}" does not provide render options.',
              "Render/IPR Render Current Frame": 'Renderer "{name}" does not provide IPR options.'}
ENGINE_NAMES = {'BLENDER_EEVEE_NEXT': "EEVEE", 'BLENDER_EEVEE': "EEVEE", 'CYCLES': "Cycles",
                'BLENDER_WORKBENCH': "Workbench"}


def engine_name(scene):
    return ENGINE_NAMES.get(scene.render.engine, scene.render.engine.title())


def no_options_text(path, scene):
    """Maya's Help Line warning for ``path``'s option box, or None when it has a window."""
    text = NO_OPTIONS.get(path)
    return text.format(name=engine_name(scene)) if text else None


WINDOWS = []
