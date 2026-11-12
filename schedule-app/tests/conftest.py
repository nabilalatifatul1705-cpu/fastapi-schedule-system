"""Fixture pytest: database SQLite in-memory + Publisher segar per test."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.database import Base, get_db
from app.main import app
from app.observers import build_default_subject
from app.routers.schedule import get_subject


@pytest.fixture()
def subject():
    return build_default_subject()


@pytest.fixture()
def observers(subject):
    """Peta nama observer -> instance, mis. observers['StudentObserver']."""
    return {type(o).__name__: o for o in subject.observers}


@pytest.fixture()
def client(subject):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_subject] = lambda: subject
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()
