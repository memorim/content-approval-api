"""Persistent credential lifecycle and API authorization use independent database sessions."""

from datetime import timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import sql_credentials as credentials
from app.database import Base
from app.models import CredentialToken, utcnow


@pytest.fixture()
def registry(tmp_path):
    path = tmp_path / "application.db"
    engine = create_engine("sqlite:///" + str(path), connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield path, sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def test_credentials_persist_and_expire_without_storing_raw_tokens(registry):
    path, factory = registry
    token, digest = credentials.issue(factory, "workspace", "alice", ["approval:read"])
    factory.kw["bind"].dispose()  # A new connection must read persisted state.
    assert credentials.lookup(factory, token)["user_id"] == "alice"
    assert credentials.lookup(factory, "unknown") is None
    assert token.encode() not in path.read_bytes()
    with factory.begin() as db:
        row = db.get(CredentialToken, digest)
        assert row.digest == digest and row.actions == ["approval:read"]
        row.expires_at = utcnow() - timedelta(seconds=1)
    assert credentials.lookup(factory, token) is None


def test_disable_is_scoped_and_enable_requires_new_tokens(registry):
    _path, factory = registry
    first, digest = credentials.issue(factory, "one", "alice", ["approval:read"])
    second, _ = credentials.issue(factory, "one", "alice", ["approval:decide"])
    other, _ = credentials.issue(factory, "two", "alice", ["approval:read"])
    assert credentials.revoke(factory, digest) == 1
    assert credentials.lookup(factory, first) is None
    assert credentials.set_user_active(factory, "one", "alice", False) == 1
    assert credentials.lookup(factory, second) is None
    assert credentials.lookup(factory, other) is not None
    with pytest.raises(ValueError, match="disabled"):
        credentials.issue(factory, "one", "alice", ["approval:read"])
    assert credentials.set_user_active(factory, "one", "alice", True) == 1
    assert credentials.lookup(factory, first) is None
    assert credentials.lookup(factory, second) is None
    fresh, _ = credentials.issue(factory, "one", "alice", ["approval:read"])
    assert credentials.lookup(factory, fresh) is not None
    assert credentials.list_users(factory) == [
        {"workspace": "one", "user_id": "alice", "active": True},
        {"workspace": "two", "user_id": "alice", "active": True},
    ]


def test_api_reads_shared_registry_and_applies_revocation_on_next_request(client, registry, monkeypatch):
    from app import database

    _path, factory = registry
    token, digest = credentials.issue(factory, "ws_1", "reader", ["approval:read"])
    monkeypatch.setenv("APP_AUTH_BACKEND", "database")
    monkeypatch.setattr(database, "SessionLocal", factory)
    headers = {"Authorization": "Bearer " + token}
    url = "/api/v1/workspaces/ws_1/approval-requests"
    assert client.get(url, headers=headers).status_code == 200
    assert client.get(url.replace("ws_1", "ws_2"), headers=headers).status_code == 403
    assert client.post(url, headers=headers, json={
        "sourceType": "publication", "sourceId": "fixture", "title": "Fixture",
        "reviewerUserIds": ["reviewer"],
    }).status_code == 403
    credentials.revoke(factory, digest)
    assert client.get(url, headers=headers).status_code == 401


def test_unmigrated_registry_fails_closed_without_creating_tables(tmp_path, client, monkeypatch):
    from app import database
    from sqlalchemy import inspect

    engine = create_engine("sqlite:///" + str(tmp_path / "unmigrated.db"))
    try:
        monkeypatch.setenv("APP_AUTH_BACKEND", "database")
        monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
        response = client.get("/api/v1/workspaces/ws_1/approval-requests", headers={
            "Authorization": "Bearer " + "fixture-token-" * 4,
        })
        assert response.status_code == 503
        assert response.json() == {"detail": "Authentication unavailable"}
        assert inspect(engine).get_table_names() == []
    finally:
        engine.dispose()


def test_cli_issues_into_migrated_application_database(tmp_path):
    import json
    import os
    import subprocess
    import sys

    environment = {**os.environ, "DATABASE_URL": "sqlite:///" + str(tmp_path / "cli.db")}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=environment, check=True, capture_output=True)
    result = subprocess.run([
        sys.executable, "-m", "app.credentials", "--application-database", "issue",
        "--workspace", "fixture", "--user", "owner", "--actions", "approval:read",
    ], env=environment, check=True, capture_output=True, text=True)
    issued = json.loads(result.stdout)
    engine = create_engine(environment["DATABASE_URL"])
    try:
        factory = sessionmaker(bind=engine)
        assert credentials.lookup(factory, issued["token"])["workspace_id"] == "fixture"
        with factory() as db:
            assert db.scalar(select(CredentialToken.digest)) == issued["token_hash"]
    finally:
        engine.dispose()
