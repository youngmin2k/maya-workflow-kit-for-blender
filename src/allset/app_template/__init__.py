# SPDX-License-Identifier: GPL-3.0-or-later
"""The Maya layout file bundled inside the extension (generator: tools/make_startup.py).

The file is no longer copied into the user's
scripts folder as an application template — nothing is written outside the extension's
folders. It is only read from here: ``switch.enter_layout`` appends its layout workspace into the open file, and
"New Scene in Maya Layout" (``first_start``) loads it as an untitled new file with
``wm.read_homefile(filepath=...)``, which keeps the preferences.
"""

import os

TEMPLATE_ID = "Maya_Workflow_Kit"   # folder of the bundled file (was the app template id)
SOURCE_DIR = os.path.join(os.path.dirname(__file__), TEMPLATE_ID)
STARTUP = os.path.join(SOURCE_DIR, "startup.blend")
