"""
Starts the Bemas Muhasebe backend with zero console window - used by the
"BemasMuhasebeBackend" Windows scheduled task (runs at user logon).

Launched directly via pythonw.exe (the windowless Python interpreter), NOT
via powershell.exe/cmd.exe - a console-subsystem process is what was popping
up a visible terminal window on login (some Windows setups don't reliably
honor "-WindowStyle Hidden" and show it anyway). pythonw.exe has no console
subsystem at all, so there is nothing for Windows to display, ever.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

log_path = os.path.join(BASE_DIR, "server.log")
log_file = open(log_path, "a", encoding="utf-8", buffering=1)
sys.stdout = log_file
sys.stderr = log_file

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
