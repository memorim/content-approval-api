import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import OutboxEvent, utcnow
from app.outbox import claim, local_receiver, process_one, webhook_receiver


def factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'outbox.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def add_event(sessions):
    with sessions.begin() as db:
        event = OutboxEvent(
            workspace_id="workspace",
            request_id="request",
            event_type="approved",
            payload={"status": "approved"},
        )
        db.add(event)
        db.flush()
        return event.id


def test_lost_ack_retries_the_same_event_without_a_second_consumer_effect(tmp_path):
    engine, sessions = factory(tmp_path)
    try:
        identifier = add_event(sessions)
        now = utcnow()
        directory = tmp_path / "receiver"
        logs = []

        def lost_ack(event):
            local_receiver(event, directory)
            raise TimeoutError("response lost after successful delivery")

        assert process_one(sessions, lost_ack, now, logs.append)
        assert not process_one(
            sessions, lambda event: local_receiver(event, directory), now, logs.append
        )
        assert process_one(
            sessions,
            lambda event: local_receiver(event, directory),
            now + timedelta(seconds=3),
            logs.append,
        )
        with sessions() as db:
            event = db.get(OutboxEvent, identifier)
            assert event.published and event.attempts == 2 and event.published_at
        assert len(list(directory.glob("*.json"))) == 1
        assert json.loads((directory / (identifier + ".json")).read_text())["id"] == identifier
        assert [json.loads(line)["status"] for line in logs] == ["retry", "delivered"]
    finally:
        engine.dispose()


def test_only_one_worker_claims_an_event_and_a_crashed_lease_can_be_recovered(tmp_path):
    engine, sessions = factory(tmp_path)
    try:
        identifier = add_event(sessions)
        now = utcnow()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: claim(sessions, now), range(4)))
        assert sum(result is not None for result in results) == 1
        assert claim(sessions, now + timedelta(seconds=61))[0]["id"] == identifier
    finally:
        engine.dispose()


def test_attempt_limit_dead_letter_and_webhook_idempotency_header(tmp_path):
    engine, sessions = factory(tmp_path)
    try:
        identifier = add_event(sessions)
        now = utcnow()

        def unavailable(_event):
            raise OSError("private filesystem path must not enter the log")

        logs = []
        for attempt in range(5):
            assert process_one(sessions, unavailable, now + timedelta(minutes=attempt), logs.append)
        assert not process_one(sessions, unavailable, now + timedelta(hours=1), logs.append)
        with sessions() as db:
            event = db.get(OutboxEvent, identifier)
            assert event.dead_at and not event.published and event.attempts == 5
        assert "private filesystem" not in "".join(logs)
        captured = []
        with httpx.Client(
            transport=httpx.MockTransport(
                lambda request: captured.append(request) or httpx.Response(200)
            )
        ) as client:
            send = webhook_receiver("https://receiver.example/events", client, "test-token")
            send({"id": identifier, "payload": {}})
            assert captured[0].headers["Idempotency-Key"] == identifier
            assert captured[0].headers["Authorization"] == "Bearer test-token"
    finally:
        engine.dispose()
