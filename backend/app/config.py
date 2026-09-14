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

os.makedirs(os.path.join(settings.upload_dir, "excel"), exist_ok=True)
os.makedirs(os.path.join(settings.upload_dir, "receipts"), exist_ok=True)
os.makedirs(settings.export_dir, exist_ok=True)
