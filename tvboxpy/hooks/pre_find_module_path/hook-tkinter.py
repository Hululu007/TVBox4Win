"""Keep tkinter discoverable when PyInstaller's Tcl probe is unreliable.

Tcl/Tk itself is collected explicitly by tvboxpy.spec; this override prevents
the built-in probe from dropping the tkinter package before our data is added.
"""


def pre_find_module_path(_hook_api):
    return None
