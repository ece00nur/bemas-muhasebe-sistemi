import os
import sys
from pydantic_settings import BaseSettings

# When PyInstaller freezes this into a standalone .exe (bundled inside the
# Electron installer for fully-offline, no-network-setup use on someone
# else's computer), __file__-relative paths point inside the temporary/
# read-only bundle - not a place to keep a growing SQLite database. Detect
# that case and keep all writable data in a normal per-user folder instead,
# which survives app updates/reinstalls.
_FROZEN = getattr(sys, "frozen", False)

if _FROZEN:
    _DATA_DIR = os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
        "BemasMuhasebe",
    )
    _ENV_FILE = os.path.join(_DATA_DIR, ".env")
else:
    _DATA_DIR = os.path.dirname(os.path.dirname(__file__))
    _ENV_FILE = os.path.join(_DATA_DIR, ".env")

os.makedirs(_DATA_DIR, exist_ok=True)


class Settings(BaseSettings):
    database_url: str = f"sqlite:///{os.path.join(_DATA_DIR, 'bemas_muhasebe.db')}"

    secret_key: str = "change-this-to-a-long-random-string-in-production"
    access_token_expire_minutes: int = 480
    algorithm: str = "HS256"

    seed_admin_username: str = "admin"
    seed_admin_password: str = "change-me-now"

    admin_panel_base_path: str = "/adminpanel"

    tesseract_cmd: str | None = None

    upload_dir: str = os.path.join(_DATA_DIR, "uploads")
    export_dir: str = os.path.join(_DATA_DIR, "exports")

    class Config:
        env_file = _ENV_FILE
        extra = "ignore"


settings = Settings()

# Render/Heroku-style hosts hand out "postgres://..." connection strings, but
# SQLAlchemy 2.0 only accepts the "postgresql://" scheme and raises on the
# old one - normalize it so DATABASE_URL can be pasted in as-is.
if settings.database_url.startswith("postgres://"):
    settings.database_url = settings.database_url.replace("postgres://", "postgresql://", 1)

os.makedirs(os.path.join(settings.upload_dir, "excel"), exist_ok=True)
os.makedirs(os.path.join(settings.upload_dir, "receipts"), exist_ok=True)
os.makedirs(settings.export_dir, exist_ok=True)
