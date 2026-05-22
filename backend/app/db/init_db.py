from sqlmodel import SQLModel
from app.db.session import engine
from app.models.script import Script
from app.scripts.aptly_default_scripts import DEFAULT_SCRIPTS
from sqlmodel import Session, select

def seed_scripts():
    """Insert default scripts if they do not exist"""
    with Session(engine) as session:
        for s in DEFAULT_SCRIPTS:
            stmt = select(Script).where(Script.name == s["name"])
            existing = session.exec(stmt).first()
            if not existing:
                script = Script(**s)
                session.add(script)
        session.commit()

def init_db() -> None:
    """Create all tables and seed default scripts"""
    SQLModel.metadata.create_all(engine)  # ایجاد تمام جداول
    seed_scripts()  # اضافه کردن scriptهای پیش‌فرض