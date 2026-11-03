"""The checks of gui_step134_selection.py on the Vulkan GPU backend: edit-mode vertices keep their size and the
selection colours stay Maya's there too (Vulkan and Metal ignore the point size of the plain uniform-colour shader)."""

import os
import runpy
import sys

import gpu

GUI_ARGS = "--gpu-backend vulkan"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check  # noqa: E402

check(f"Blender runs on the Vulkan backend ({gpu.platform.backend_type_get()})",
      gpu.platform.backend_type_get() == 'VULKAN')
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui_step134_selection.py"), run_name="__main__")
