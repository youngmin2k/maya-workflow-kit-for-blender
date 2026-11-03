# SPDX-License-Identifier: GPL-3.0-or-later
"""Translation files of the user: ``<language code>.json`` in the ``translations`` folder of the kit's user folder.

A file holds ``{"sections": {section: {English: translation}}}`` (the layout of ``template_en.json``, which lists
every kit string by menu / window / file) or a flat ``{English: translation}``. The file name is Blender's language
code (``de_DE.json``, ``ko_KR.json``); the entries are added over the kit's own table for that language, so a file
can also correct a built-in translation. Empty values and values equal to the English text are skipped. The files are
read as data (JSON) only.
"""

import json
import os
import shutil

import bpy

FOLDER = "translations"
TEMPLATE = "template_en.json"
SUFFIX = ".json"
# Files read at the last (re)load: [(file name, entries used, problem)]; problem = "" / NOT_READ / NOT_LANGUAGE
LOADED = []
NOT_READ = "not read"
NOT_LANGUAGE = "not a language"


def _package():
    return __package__.rsplit(".", 1)[0]       # the add-on package (``...allset``)


def folder(create=False):
    """``translations`` in the extension's user folder (legacy add-on build: a folder inside the add-on's folder)."""
    try:
        return bpy.utils.extension_path_user(_package(), path=FOLDER, create=create)
    except (ValueError, AttributeError):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_data", FOLDER)
        if create:
            os.makedirs(path, exist_ok=True)
        return path


def template_path():
    """The English template shipped with the kit."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), TEMPLATE)


def entries(data):
    """{English: translation} of a parsed translation file: only text values that differ from the English text.
    Where one English text is listed in several sections, the first translation wins."""
    out = {}
    if not isinstance(data, dict):
        return out
    blocks = data.get("sections") if isinstance(data.get("sections"), dict) else {"": data}
    for block in blocks.values():
        if not isinstance(block, dict):
            continue
        for en, tr in block.items():
            if (isinstance(en, str) and isinstance(tr, str) and en.strip() and tr.strip() and tr != en
                    and en not in out):
                out[en] = tr
    return out


def _language_codes():
    try:
        return set(bpy.app.translations.locales)
    except AttributeError:
        return set()


def read_all(path=None):
    """{language code: {English: translation}} of every ``<code>.json`` in ``path`` (default: the translations
    folder); fills ``LOADED``. A file that can't be read is listed with its error and skipped."""
    path = path or folder()
    LOADED.clear()
    out = {}
    try:
        names = sorted(n for n in os.listdir(path) if n.lower().endswith(SUFFIX) and n != TEMPLATE)
    except OSError:
        return out
    codes = _language_codes()
    for name in names:
        code = name[:-len(SUFFIX)]
        try:
            with open(os.path.join(path, name), encoding="utf-8-sig") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            print(f"Maya Workflow Kit: could not read {name}: {exc}")
            LOADED.append((name, 0, NOT_READ))
            continue
        found = entries(data)
        note = "" if not codes or code in codes else NOT_LANGUAGE
        LOADED.append((name, len(found), note))
        if found:
            out.setdefault(code, {}).update(found)
    return out


def write_template(path=None):
    """Copy the English template into ``path`` (default: the translations folder); returns the written file."""
    path = path or folder(create=True)
    os.makedirs(path, exist_ok=True)
    target = os.path.join(path, TEMPLATE)
    shutil.copyfile(template_path(), target)
    return target
