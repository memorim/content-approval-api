"""Durable outbox worker: local receiver by default, optional operator-configured HTTPS webhook."""

from __future__ import annotations

import argparse
import json
import os
import signal
import tempfile
import threading
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
from sqlalchemy import func, or_, select, update

from app.database import SessionLocal
from app.models import OutboxEvent, utcnow

MAX_ATTEMPTS = 5


def claim(factory=SessionLocal, now=None):
    now = now or utcnow()
    expired = or_(OutboxEvent.lease_until.is_(None), OutboxEvent.lease_until <= now)
    with factory.begin() as db:
        db.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.published.is_(False),
                OutboxEvent.dead_at.is_(None),
                expired,
                OutboxEvent.attempts >= MAX_ATTEMPTS,
            )
            .values(dead_at=now, last_error="attempt_limit_after_lease")
        )
        eligible = [
            OutboxEvent.published.is_(False),
            OutboxEvent.dead_at.is_(None),
            expired,
            or_(OutboxEvent.next_attempt_at.is_(None), OutboxEvent.next_attempt_at <= now),
            OutboxEvent.attempts < MAX_ATTEMPTS,
        ]
        identifier = db.scalar(
            select(OutboxEvent.id)
            .where(*eligible)
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .limit(1)
        )
        if identifier is None:
            return None
        token = str(uuid4())
        result = db.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == identifier, *eligible)
            .values(
                lease_token=token,
                lease_until=now + timedelta(seconds=60),
                attempts=OutboxEvent.attempts + 1,
            )
        )
        if result.rowcount != 1:
            return None
        event = db.get(OutboxEvent, identifier)
        db.refresh(event)
        return (
            {
                "id": event.id,
                "workspaceId": event.workspace_id,
                "requestId": event.request_id,
                "type": event.event_type,
                "payload": event.payload,
            },
            token,
            event.attempts,
        )


def local_receiver(event, directory=Path("data/delivered-events")):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = directory / (str(UUID(event["id"])) + ".json")
    encoded = json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".pending-", delete=False) as file:
            temporary = Path(file.name)
            file.write(encoded)
            file.flush()
            os.fsync(file.fileno())
        try:
            # Exclusive atomic link publishes only a complete file; retries never append another effect.
            os.link(temporary, destination)
            if os.name != "nt":
                descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        except FileExistsError:
            if destination.read_bytes() != encoded:
                raise ValueError("event_id_payload_conflict") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def webhook_receiver(url, client, token=""):
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("Configure a fixed HTTPS webhook without embedded credentials")

    def send(event):
        headers = {"Idempotency-Key": event["id"]}
        if token:
            headers["Authorization"] = "Bearer " + token
        response = client.post(url, json=event, headers=headers, follow_redirects=False)
        response.raise_for_status()

    return send


def process_one(factory=SessionLocal, deliver=local_receiver, now=None, log=print):
    now = now or utcnow()
    claimed = claim(factory, now)
    if claimed is None:
        return False
    event, token, attempts = claimed
    failure = None
    try:
        deliver(event)
    except Exception as error:  # noqa: BLE001 - worker boundary persists retry state without payload logs
        failure = type(error).__name__[:80]
    with factory.begin() as db:
        values = {"lease_token": None, "lease_until": None, "last_error": failure}
        if failure:
            values.update(
                next_attempt_at=now + timedelta(seconds=min(300, 2**attempts)),
                dead_at=now if attempts >= MAX_ATTEMPTS else None,
            )
        else:
            values.update(published=True, published_at=now, next_attempt_at=None)
        changed = db.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.id == event["id"],
                OutboxEvent.lease_token == token,
                OutboxEvent.published.is_(False),
            )
            .values(**values)
        ).rowcount
    log(
        json.dumps(
            {
                "event": "outbox_delivery",
                "eventId": event["id"],
                "attempt": attempts,
                "status": "lease_lost"
                if not changed
                else "dead"
                if failure and attempts >= MAX_ATTEMPTS
                else "retry"
                if failure
                else "delivered",
                "error": failure,
            }
        )
    )
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once", action="store_true", help="Process up to 100 currently due events, then exit"
    )
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--retry", metavar="EVENT_ID", help="Explicitly requeue a failed event")
    args = parser.parse_args()
    if args.status:
        with SessionLocal() as db:
            print(
                json.dumps(
                    {
                        "total": db.scalar(select(func.count()).select_from(OutboxEvent)),
                        "published": db.scalar(
                            select(func.count())
                            .select_from(OutboxEvent)
                            .where(OutboxEvent.published.is_(True))
                        ),
                        "dead": db.scalar(
                            select(func.count())
                            .select_from(OutboxEvent)
                            .where(OutboxEvent.dead_at.is_not(None))
                        ),
                    }
                )
            )
        return
    if args.retry:
        identifier = str(UUID(args.retry))
        with SessionLocal.begin() as db:
            changed = db.execute(
                update(OutboxEvent)
                .where(
                    OutboxEvent.id == identifier,
                    OutboxEvent.dead_at.is_not(None),
                    OutboxEvent.published.is_(False),
                )
                .values(
                    attempts=0,
                    dead_at=None,
                    next_attempt_at=None,
                    lease_until=None,
                    lease_token=None,
                    last_error=None,
                )
            ).rowcount
        if not changed:
            parser.error("Failed event not found")
        return
    stopped = threading.Event()
    for name in [signal.SIGINT, signal.SIGTERM]:
        signal.signal(name, lambda *_: stopped.set())
    with httpx.Client(timeout=10) as client:
        url = os.getenv("OUTBOX_WEBHOOK_URL", "")
        deliver = (
            webhook_receiver(url, client, os.getenv("OUTBOX_WEBHOOK_TOKEN", ""))
            if url
            else lambda event: local_receiver(
                event, Path(os.getenv("OUTBOX_DIRECTORY", "data/delivered-events"))
            )
        )
        while not stopped.is_set():
            try:
                for _ in range(100):
                    if stopped.is_set() or not process_one(deliver=deliver):
                        break
            except Exception as error:  # noqa: BLE001 - worker boundary persists retry state without payload logs
                print(
                    json.dumps(
                        {
                            "event": "outbox_worker",
                            "status": "unavailable",
                            "error": type(error).__name__,
                        }
                    )
                )
                if args.once:
                    raise SystemExit(1) from None
                stopped.wait(5)
            if args.once:
                break
            stopped.wait(1)


if __name__ == "__main__":
    main()
