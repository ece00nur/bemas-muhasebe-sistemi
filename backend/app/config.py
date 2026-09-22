import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./bemas_muhasebe.db"

    secret_key: str = "change-this-to-a-long-random-string-in-production"
    access_token_expire_minutes: int = 480
    algorithm: str = "HS256"

    seed_admin_username: str = "admin"
    seed_admin_password: str = "change-me-now"

    admin_panel_base_path: str = "/adminpanel"

    tesseract_cmd: str | None = None

    upload_dir: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    export_dir: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "exports")

    class Config:
        env_file = ".env"
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
