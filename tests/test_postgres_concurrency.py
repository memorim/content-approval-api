"""Opt-in checks against an isolated loopback PostgreSQL fixture, never the application URL."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, local
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import service
from app.models import ApprovalRequest, ApprovalStatus, AuditAction, AuditLog, OutboxEvent
from app.schemas import CreateApprovalRequest


@pytest.fixture()
def postgres():
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL is required for the PostgreSQL fixture")
    assert make_url(url).host in {"127.0.0.1", "localhost", "::1"}, "Use a loopback test instance"
    schema = "portfolio_test_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    engine = None
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={"options": f"-c search_path={schema} -c statement_timeout=10000"})
        Base.metadata.create_all(engine)
        yield engine, sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        if engine is not None:
            engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


def payload(title="Fixture review"):
    return CreateApprovalRequest(sourceType="publication", sourceId="s", title=title, reviewerUserIds=["reviewer"])


def test_postgres_competing_decisions_commit_one_status_and_one_event(postgres, monkeypatch):
    _engine, factory = postgres
    with factory() as db:
        item = service.create_request(db, workspace_id="w", actor_user_id="u", payload=payload(), idempotency_key="fixture")
        identifier = item.id
    gate = Barrier(2, timeout=10)
    thread_state = local()
    original = service.get_request_or_404

    def synchronized_read(*args, **kwargs):
        result = original(*args, **kwargs)
        if not getattr(thread_state, "read", False):
            thread_state.read = True
            assert result.status == ApprovalStatus.pending
            gate.wait()
        return result

    monkeypatch.setattr(service, "get_request_or_404", synchronized_read)

    def decide(target):
        with factory() as db:
            try:
                result = service.decide_request(db, workspace_id="w", request_id=identifier, actor_user_id="reviewer", target_status=target, action=AuditAction(target.value), reason="Fixture")
                return 200, result.status
            except HTTPException as error:
                return error.status_code, None

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(decide, [ApprovalStatus.approved, ApprovalStatus.rejected]))
    assert sorted(code for code, _ in results) == [200, 409]
    with factory() as db:
        assert db.get(ApprovalRequest, identifier).status == next(value for code, value in results if code == 200)
        assert db.scalar(select(func.count()).select_from(AuditLog)) == 2
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 2


@pytest.mark.parametrize("same_payload", [True, False])
def test_postgres_idempotent_create_serializes_conflicting_inserts(postgres, same_payload):
    engine, factory = postgres
    gate = Barrier(2, timeout=10)
    thread_state = local()

    @event.listens_for(engine, "after_cursor_execute")
    def synchronize(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().startswith("SELECT approval_requests.") and "approval_requests.idempotency_key =" in statement and not getattr(thread_state, "read", False):
            thread_state.read = True
            gate.wait()

    def create(index):
        with factory() as db:
            try:
                result = service.create_request(db, workspace_id="w", actor_user_id="u", payload=payload("Same" if same_payload else f"Title {index}"), idempotency_key="parallel-key")
                return 201, result.id
            except HTTPException as error:
                return error.status_code, None

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(create, [0, 1]))
    assert sorted(code for code, _ in results) == ([201, 201] if same_payload else [201, 409])
    if same_payload:
        assert results[0][1] == results[1][1]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ApprovalRequest)) == 1
        assert db.scalar(select(func.count()).select_from(AuditLog)) == 1
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 1
