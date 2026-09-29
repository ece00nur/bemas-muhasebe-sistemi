"""
Entry point for the standalone, PyInstaller-frozen backend that ships inside
the Electron installer (see desktop/main.js: it spawns this exe when no
backend is already reachable, so someone on a completely different computer
just runs the one installer - no separate Python install, no server address
to type in).

Binds to 127.0.0.1 only (not 0.0.0.0): this build is for a single person's
own machine, not for sharing over a LAN, so there is no reason to accept
connections from other computers.
"""
import uvicorn

# Import the app object directly (not the "app.main:app" string form) -
# PyInstaller's static import analysis can't follow uvicorn's runtime
# string-based module loader, so the whole `app` package would otherwise be
# silently left out of the bundle ("ModuleNotFoundError: No module named 'app'"
# at first run, even though the build itself succeeds with no warnings).
from app.main import app as fastapi_app

if __name__ == "__main__":
    uvicorn.run(fastapi_app, host="127.0.0.1", port=8000, log_level="info")
