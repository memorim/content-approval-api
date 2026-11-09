"""Validate scheduled delivery before touching the database or claiming events."""

import os
import re
from urllib.parse import urlsplit


def validate_external_delivery(environment=None):
    environment = os.environ if environment is None else environment
    database = urlsplit(environment.get("DATABASE_URL", ""))
    if database.scheme not in {"postgres", "postgresql", "postgresql+psycopg"} or not database.hostname or not database.path.strip("/"):
        raise ValueError("Set DATABASE_URL to the persistent PostgreSQL database")
    topic = environment.get("NTFY_TOPIC", "")
    webhook = environment.get("OUTBOX_WEBHOOK_URL", "")
    if bool(topic) == bool(webhook):
        raise ValueError("Configure exactly one of NTFY_TOPIC or OUTBOX_WEBHOOK_URL")
    if topic and not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", topic):
        raise ValueError("Use a random ntfy topic of 32–128 safe characters")
    if webhook:
        target = urlsplit(webhook)
        if target.scheme != "https" or not target.hostname or target.username or target.password or target.fragment:
            raise ValueError("Configure an HTTPS webhook without embedded credentials")


if __name__ == "__main__":
    try:
        validate_external_delivery()
    except ValueError as error:
        raise SystemExit(str(error)) from None
