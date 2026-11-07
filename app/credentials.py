"""Provision and revoke user credentials without storing plaintext access tokens."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(fd)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""CREATE TABLE IF NOT EXISTS auth_users(
        workspace TEXT NOT NULL, user_id TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY(workspace,user_id));
        CREATE TABLE IF NOT EXISTS auth_tokens(
        hash TEXT PRIMARY KEY, workspace TEXT NOT NULL, user_id TEXT NOT NULL,
        actions TEXT NOT NULL, expires_at REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(workspace,user_id) REFERENCES auth_users(workspace,user_id));""")
    path.chmod(0o600)
    return db


def issue(path, workspace, user_id, actions, days=30):
    if not workspace or not user_id or not 1 <= days <= 365 or not actions:
        raise ValueError(
            "Workspace, user, actions and expiry of 1–365 days are required"
        )
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    db = connect(path)
    try:
        with db:
            db.execute(
                "INSERT OR IGNORE INTO auth_users(workspace,user_id) VALUES(?,?)",
                (workspace, user_id),
            )
            if not db.execute(
                "SELECT active FROM auth_users WHERE workspace=? AND user_id=?",
                (workspace, user_id),
            ).fetchone()["active"]:
                raise ValueError("User is disabled")
            db.execute(
                "INSERT INTO auth_tokens(hash,workspace,user_id,actions,expires_at) VALUES(?,?,?,?,?)",
                (
                    digest,
                    workspace,
                    user_id,
                    json.dumps(actions),
                    time.time() + days * 86400,
                ),
            )
    finally:
        db.close()
    return token, digest


def lookup(path, token):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        row = db.execute(
            """SELECT t.* FROM auth_tokens t JOIN auth_users u
            ON u.workspace=t.workspace AND u.user_id=t.user_id
            WHERE t.hash=? AND t.revoked=0 AND u.active=1 AND t.expires_at>?""",
            (hashlib.sha256(token.encode()).hexdigest(), time.time()),
        ).fetchone()
        return (
            {
                "workspace_id": row["workspace"],
                "user_id": row["user_id"],
                "actions": json.loads(row["actions"]),
            }
            if row
            else None
        )
    finally:
        db.close()


def revoke(path, digest):
    db = connect(path)
    try:
        with db:
            return db.execute(
                "UPDATE auth_tokens SET revoked=1 WHERE hash=?", (digest,)
            ).rowcount
    finally:
        db.close()


def set_user_active(path, workspace, user_id, active):
    db = connect(path)
    try:
        with db:
            changed = db.execute(
                "UPDATE auth_users SET active=? WHERE workspace=? AND user_id=?",
                (int(active), workspace, user_id),
            ).rowcount
            if changed and not active:
                db.execute(
                    "UPDATE auth_tokens SET revoked=1 WHERE workspace=? AND user_id=?",
                    (workspace, user_id),
                )
            return changed
    finally:
        db.close()


def list_users(path):
    db = connect(path)
    try:
        return [dict(row) for row in db.execute(
            "SELECT workspace,user_id,active FROM auth_users ORDER BY workspace,user_id"
        )]
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--database", help="Legacy local SQLite credential file")
    target.add_argument("--application-database", action="store_true", help="Use migrated DATABASE_URL; keep its secret out of arguments")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("issue")
    add.add_argument("--workspace", required=True)
    add.add_argument("--user", required=True)
    add.add_argument("--actions", required=True)
    add.add_argument("--days", type=int, default=30)
    delete = sub.add_parser("revoke")
    delete.add_argument("hash")
    sub.add_parser("users")
    for command in ["disable-user", "enable-user"]:
        user = sub.add_parser(command)
        user.add_argument("--workspace", required=True)
        user.add_argument("--user", required=True)
    args = parser.parse_args()
    operations = {"issue": issue, "revoke": revoke, "list_users": list_users, "set_user_active": set_user_active}
    database = args.database
    if args.application_database:
        from . import sql_credentials
        from .database import SessionLocal

        database = SessionLocal
        operations = {name: getattr(sql_credentials, name) for name in operations}
    if args.command == "issue":
        token, digest = operations["issue"](
            database, args.workspace, args.user, args.actions.split(","), args.days
        )
        print(json.dumps({"token": token, "token_hash": digest}))
    elif args.command == "revoke":
        print(json.dumps({"revoked": operations["revoke"](database, args.hash)}))
    elif args.command == "users":
        print(json.dumps({"users": operations["list_users"](database)}))
    else:
        print(json.dumps({"changed": operations["set_user_active"](
            database, args.workspace, args.user, args.command == "enable-user"
        )}))


if __name__ == "__main__":
    main()
