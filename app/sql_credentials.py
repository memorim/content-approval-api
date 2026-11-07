"""Credential administration in the migrated application database, never plaintext tokens."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import select, update

from app.models import CredentialToken, CredentialUser, utcnow

ALLOWED_ACTIONS = {"approval:read", "approval:create", "approval:decide", "approval:cancel"}


def issue(factory, workspace, user_id, actions, days=30):
    if (
        not workspace or not user_id or len(workspace) > 128 or len(user_id) > 128
        or not 1 <= days <= 365 or not actions or not set(actions) <= ALLOWED_ACTIONS
    ):
        raise ValueError("Use a workspace, user, valid actions and expiry of 1–365 days")
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    with factory.begin() as db:
        dialect = db.bind.dialect.name
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        elif dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
        else:
            raise ValueError("Credential storage supports PostgreSQL or SQLite")
        db.execute(
            insert(CredentialUser)
            .values(workspace_id=workspace, user_id=user_id, active=True)
            .on_conflict_do_nothing(index_elements=["workspace_id", "user_id"])
        )
        # Serialize issuance with disable/enable for this exact user on PostgreSQL.
        user = db.scalar(
            select(CredentialUser)
            .where(CredentialUser.workspace_id == workspace, CredentialUser.user_id == user_id)
            .with_for_update()
        )
        if not user.active:
            raise ValueError("User is disabled")
        db.add(CredentialToken(
            digest=digest, workspace_id=workspace, user_id=user_id,
            actions=sorted(set(actions)), expires_at=utcnow() + timedelta(days=days), revoked=False,
        ))
    return token, digest


def lookup(factory, token):
    # Lookup never creates schema or runs migrations.
    with factory() as db:
        row = db.scalar(
            select(CredentialToken)
            .join(CredentialUser)
            .where(
                CredentialToken.digest == hashlib.sha256(token.encode()).hexdigest(),
                CredentialToken.revoked.is_(False),
                CredentialToken.expires_at > utcnow(),
                CredentialUser.active.is_(True),
            )
        )
        return {"workspace_id": row.workspace_id, "user_id": row.user_id, "actions": row.actions} if row else None


def revoke(factory, digest):
    with factory.begin() as db:
        return db.execute(
            update(CredentialToken).where(CredentialToken.digest == digest).values(revoked=True)
        ).rowcount


def set_user_active(factory, workspace, user_id, active):
    with factory.begin() as db:
        user = db.scalar(
            select(CredentialUser)
            .where(CredentialUser.workspace_id == workspace, CredentialUser.user_id == user_id)
            .with_for_update()
        )
        if user is None:
            return 0
        user.active = active
        if not active:
            db.execute(
                update(CredentialToken)
                .where(CredentialToken.workspace_id == workspace, CredentialToken.user_id == user_id)
                .values(revoked=True)
            )
        return 1


def list_users(factory):
    with factory() as db:
        return [
            {"workspace": row.workspace_id, "user_id": row.user_id, "active": row.active}
            for row in db.scalars(select(CredentialUser).order_by(CredentialUser.workspace_id, CredentialUser.user_id))
        ]
