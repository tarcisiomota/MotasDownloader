"""Bundle the installed Windows Tcl/Tk scripts explicitly."""
from pathlib import Path
import sys

base = Path(sys.base_prefix) / 'tcl'
datas = [(str(base / 'tcl8.6'), '_tcl_data'),
         (str(base / 'tk8.6'), '_tk_data'),
         (str(base / 'tcl8'), 'tcl8')]
