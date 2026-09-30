from sqlalchemy.orm import Session, sessionmaker

from app.database.engine import make_engine

engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session():
    with SessionLocal() as session:
        yield session
