import tempfile
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def client(monkeypatch):
    identities = {
        "creator": ("ws_1", "usr_creator", ["approval:read", "approval:create", "approval:decide", "approval:cancel"]),
        "other": ("ws_2", "usr_other", ["approval:read"]),
        "reader": ("ws_1", "usr_1", ["approval:read"]),
        "audit": ("w", "u", ["approval:create"]),
        "another": ("w", "another", ["approval:create"]),
    }
    registry = {hashlib.sha256((name + "-" * 40).encode()).hexdigest():
                {"workspace_id": workspace, "user_id": user, "actions": actions}
                for name, (workspace, user, actions) in identities.items()}
    monkeypatch.setenv("APP_AUTH_TOKENS", json.dumps(registry))
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
        Base.metadata.create_all(bind=engine)

        def override_get_db():
            db = TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as c:
                yield c
        finally:
            app.dependency_overrides.clear()
            engine.dispose()
