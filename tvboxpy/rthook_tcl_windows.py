"""Point the frozen Windows app at the explicitly bundled Tcl/Tk libraries."""
import os
import sys


base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
os.environ["TCL_LIBRARY"] = os.path.join(base, "tcl", "tcl8.6")
os.environ["TK_LIBRARY"] = os.path.join(base, "tcl", "tk8.6")
