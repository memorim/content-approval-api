from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass

from fastapi import Header, HTTPException, Path, status
from sqlalchemy.exc import SQLAlchemyError


@dataclass(frozen=True)
class Principal:
    workspace_id: str
    user_id: str
    actions: frozenset[str]


def parse_actions(header: str) -> frozenset[str]:
    return frozenset(action.strip() for action in header.split(",") if action.strip())


def get_principal(
    authorization: str | None = Header(None, alias="Authorization"),
) -> Principal:
    # Only operator-configured hashes bind a credential to its identity and grants.
    # Incoming X-User-Id/X-Workspace-Id/X-Actions have no authority.
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer credential required")
    token = authorization[7:]
    if len(token) < 32 or len(token) > 256:
        raise HTTPException(status_code=401, detail="Invalid credential")
    try:
        database = os.getenv("APP_AUTH_DATABASE")
        backend = os.getenv("APP_AUTH_BACKEND", "")
        if backend not in {"", "database"} or (backend == "database" and database):
            raise ValueError("Choose one credential backend")
        if backend == "database":
            from .database import SessionLocal
            from .sql_credentials import lookup

            entry = lookup(SessionLocal, token)
        elif database:
            from .credentials import lookup

            entry = lookup(database, token)
        else:
            entry = None
        if backend == "database" or database:
            if entry is None:
                raise HTTPException(
                    status_code=401, detail="Invalid or expired credential"
                )
            return Principal(
                entry["workspace_id"], entry["user_id"], frozenset(entry["actions"])
            )
        registry = json.loads(os.getenv("APP_AUTH_TOKENS", "{}"))
        if not isinstance(registry, dict):
            raise TypeError("Invalid registry")
        entry = registry.get(hashlib.sha256(token.encode()).hexdigest())
        if entry is None:
            raise HTTPException(status_code=401, detail="Invalid credential")
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("workspace_id"), str)
            or not entry["workspace_id"]
            or not isinstance(entry.get("user_id"), str)
            or not entry["user_id"]
            or not isinstance(entry.get("actions"), list)
            or not all(isinstance(action, str) for action in entry["actions"])
        ):
            raise ValueError("Invalid principal configuration")
        return Principal(
            entry["workspace_id"], entry["user_id"], frozenset(entry["actions"])
        )
    except (ValueError, TypeError, OSError, sqlite3.Error, SQLAlchemyError):
        raise HTTPException(
            status_code=503, detail="Authentication unavailable"
        ) from None


def authorize_workspace(
    workspace_id: str = Path(...),
    principal: Principal = None,
) -> None:
    if principal is None:
        return
    if principal.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Workspace mismatch"
        )


def require_action(principal: Principal, action: str) -> None:
    if action not in principal.actions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing action: {action}"
        )
