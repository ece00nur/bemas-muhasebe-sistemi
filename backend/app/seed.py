"""Creates tables and seeds the default admin user. Run with: python -m app.seed"""
from app.database import Base, engine, SessionLocal
from app import models
from app.security import hash_password
from app.config import settings


def run():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(models.User).filter(
            models.User.username == settings.seed_admin_username
        ).first()
        if existing is None:
            admin = models.User(
                username=settings.seed_admin_username,
                password_hash=hash_password(settings.seed_admin_password),
                full_name="Bemas Treyler Yönetici",
                role="admin",
                is_active=True,
            )
            db.add(admin)
            db.commit()
            print(f"Seeded admin user '{settings.seed_admin_username}'.")
        else:
            print(f"Admin user '{settings.seed_admin_username}' already exists, skipping.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
