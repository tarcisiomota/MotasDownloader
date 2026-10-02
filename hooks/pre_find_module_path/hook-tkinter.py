"""Validate installed Tcl resources without opening a GUI during compilation."""
from pathlib import Path
import sys

def pre_find_module_path(hook_api):
    base = Path(sys.base_prefix)
    for file in ('tcl/tcl8.6/init.tcl', 'tcl/tk8.6/tk.tcl'):
        if not (base / file).is_file():
            raise RuntimeError(f'Missing Tcl/Tk build resource: {base / file}')
