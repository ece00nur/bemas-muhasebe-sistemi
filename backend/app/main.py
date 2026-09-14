import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.config import settings
from app.routers import auth, companies, invoices, uploads, receipts, ledger
from app import seed as seed_module

Base.metadata.create_all(bind=engine)
seed_module.run()

app = FastAPI(title="Bemas Treyler - Cari Hesap ve Muhasebe Takip Sistemi")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # desktop-only usage: app and API always share http://localhost
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(invoices.router)
app.include_router(uploads.router)
app.include_router(receipts.router)
app.include_router(ledger.router)


@app.middleware("http")
async def no_cache_admin_panel(request, call_next):
    # The desktop app's Chromium session otherwise caches /adminpanel/*.js|css
    # aggressively (no explicit Cache-Control was set), so a UI update can sit
    # invisible behind a stale cached app.js even after a full reinstall - the
    # installer only replaces main.js, the UI is always fetched live from here.
    response = await call_next(request)
    if request.url.path.startswith(settings.admin_panel_base_path):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serves the admin panel UI (static SPA) that the Electron desktop app opens
# locally at http://localhost:8000/adminpanel/ - not exposed publicly.
_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "frontend")
_frontend_dir = os.path.abspath(_frontend_dir)
if os.path.isdir(_frontend_dir):
    app.mount(
        settings.admin_panel_base_path,
        StaticFiles(directory=_frontend_dir, html=True),
        name="adminpanel",
    )
