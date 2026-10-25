# Content Approval API

Review content within a workspace and deliver resulting events with a durable outbox.


## Implemented

- Create, approve, reject and cancel requests; filtering and audit history.
- Idempotent creation and transactional business changes plus outbox events.
- Leased outbox delivery, retries, dead letters and an idempotent local receiver or configured HTTPS destination.

## Stack and architecture

Python, FastAPI, SQLAlchemy and Alembic; SQLite locally or PostgreSQL via Docker Compose.

## Technical mechanisms and security

- `app/service.py` changes final status with a conditional SQL UPDATE on the pending state. A stale ORM session cannot overwrite an already finalized decision; only the winning decision produces its audit/outbox event.
- An Idempotency-Key is validated without truncation. A retry must match the original actor and immutable request fields; using the same key for a different body returns 409.
- SQLAlchemy transactions commit status, audit and outbox together. Alembic migrations preserve prior records. Lease tokens prevent an old worker from acknowledging a newer delivery lease.
- Stable event IDs support receiver-side deduplication. A crash after the receiver accepts an event but before acknowledgement can cause duplicate delivery. Automatic retries stop after five claimed attempts; dead events require explicit requeue, so eventual successful delivery is not guaranteed.

## Local setup

Python 3.12.14 (see `.python-version`). Activate the virtual environment before the remaining commands.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -c requirements-lock.txt -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Configuration

Use [.env.example](.env.example) for supported configuration and keep secrets outside Git. See [configuration details](docs/TECHNICAL.md) for loading settings and optional services.

## Database and upgrades

Run the migration command above before serving requests. Existing records are retained; tests check upgrading an immutable earlier version.

## Verification

```bash
python -m pytest -q
python tests/check_contract.py
python tests/check_upgrade.py
python -m pip check
```

`tests/test_audit.py` checks stale-session decisions and conflicting idempotent retries. The existing outbox suite covers leases, retry/dead-letter handling and receiver deduplication.

CI installs locked dependencies and runs the configured checks; documentation checks also validate local links/images. Python dependency auditing uses `pip-audit --disable-pip --no-deps --strict -r requirements-lock.txt`. A passing scanner only reports known advisories at the time of the run.

## Limits and next steps

- Identity/action headers are trusted gateway input. The application does not verify a public JWT or authenticate an arbitrary browser user; place it behind a trusted gateway that replaces client-supplied identity headers.
- PostgreSQL 16 CI uses independent sessions for competing decisions and idempotent creation. These are correctness checks, not a production load benchmark; see the PostgreSQL verification section below.
- Webhook destinations are operator-controlled configuration, not user-provided URLs. No email, Slack or Telegram integration is implied.

## Further documentation

[Audit findings and follow-up](docs/AUDIT_2026_10.md) · [Technical reference](docs/TECHNICAL.md) · [Change history](CHANGELOG.md)

[API request/response example](docs/API_EXAMPLE.md)

## PostgreSQL verification

See [PostgreSQL concurrency checks](docs/POSTGRES_CONCURRENCY.md) for isolated test setup, CI and the exact concurrency guarantees.
