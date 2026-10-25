# PostgreSQL concurrency verification

`tests/test_postgres_concurrency.py` adds opt-in PostgreSQL checks using independent sessions and synchronized reads, without arbitrary sleeps. It verifies final-decision compare-and-swap, one final audit/outbox event, equal-key replay and conflicting-key payloads under concurrent INSERTs. The normal SQLite suite still runs separately.

Set `TEST_POSTGRES_URL=postgresql+psycopg://...@127.0.0.1:<port>/<fixture_db>` for an isolated local test server, then run `.venv/Scripts/python.exe -m pytest tests/test_postgres_concurrency.py -q` (or `python -m pytest ...` on Linux). Only loopback hosts are accepted. The role needs CREATE SCHEMA permissions. Each test creates one UUID-prefixed schema, uses it as search_path and drops only that schema in finally. Never point this variable at a production server.

GitHub CI starts PostgreSQL 16 as an ephemeral service and runs these checks in a separate job. Without the variable, the three tests explicitly skip; a skipped test is not evidence of PostgreSQL correctness. These are database/service integration checks; identity headers still require the trusted upstream contract described by the main README.
