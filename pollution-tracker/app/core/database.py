"""
SQLAlchemy engine + session setup. This is the ONLY file that should
create engines or sessions directly — everywhere else, use the
`get_db` dependency below.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    FastAPI dependency. Use it in routers like:

        @router.get("/reports")
        def list_reports(db: Session = Depends(get_db)):
            ...

    This guarantees the session is closed after every request, even if
    the request raises an exception.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
