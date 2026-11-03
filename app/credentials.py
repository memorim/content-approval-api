"""Provision and revoke user credentials without storing plaintext access tokens."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sqlite3
import time
from pathlib import Path


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
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
    db = connect(path)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("issue")
    add.add_argument("--workspace", required=True)
    add.add_argument("--user", required=True)
    add.add_argument("--actions", required=True)
    add.add_argument("--days", type=int, default=30)
    delete = sub.add_parser("revoke")
    delete.add_argument("hash")
    args = parser.parse_args()
    if args.command == "issue":
        token, digest = issue(
            args.database, args.workspace, args.user, args.actions.split(","), args.days
        )
        print(json.dumps({"token": token, "token_hash": digest}))
    else:
        print(json.dumps({"revoked": revoke(args.database, args.hash)}))


if __name__ == "__main__":
    main()
