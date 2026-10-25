from __future__ import annotations

import hashlib
import json
from typing import Any
from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import (
    ApprovalRequest,
    ApprovalReviewer,
    ApprovalStatus,
    AuditAction,
    AuditLog,
    OutboxEvent,
    SourceType,
    utcnow,
)
from app.schemas import CreateApprovalRequest
from app.security import redact_sensitive

FINAL_STATUSES = {ApprovalStatus.approved, ApprovalStatus.rejected, ApprovalStatus.cancelled}


def normalize_body_for_hash(body: Any) -> str:
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_idempotency_key(workspace_id: str, user_id: str, payload: CreateApprovalRequest, header_key: str | None) -> str:
    if header_key is not None:
        if not 1 <= len(header_key) <= 128:
            raise HTTPException(status_code=400, detail="Idempotency-Key must contain 1 to 128 characters")
        return header_key
    raw = normalize_body_for_hash(payload.model_dump(mode="json", by_alias=True))
    return hashlib.sha256(f"{workspace_id}:{user_id}:{raw}".encode("utf-8")).hexdigest()


def to_response_dict(request: ApprovalRequest) -> dict[str, Any]:
    return {
        "id": request.id,
        "workspaceId": request.workspace_id,
        "sourceType": request.source_type,
        "sourceId": request.source_id,
        "title": request.title,
        "description": request.description,
        "reviewerUserIds": [reviewer.reviewer_user_id for reviewer in request.reviewers],
        "status": request.status,
        "createdBy": request.created_by,
        "decidedBy": request.decided_by,
        "decisionComment": request.decision_comment,
        "decisionReason": request.decision_reason,
        "createdAt": request.created_at,
        "updatedAt": request.updated_at,
        "decidedAt": request.decided_at,
    }


def add_audit_and_event(
    db: Session,
    *,
    request: ApprovalRequest,
    actor_user_id: str,
    action: AuditAction,
    before_status: ApprovalStatus | None,
    payload: dict[str, Any],
) -> None:
    clean_payload = redact_sensitive(payload)
    db.add(
        AuditLog(
            workspace_id=request.workspace_id,
            request_id=request.id,
            actor_user_id=actor_user_id,
            action=action,
            before_status=before_status.value if before_status else None,
            after_status=request.status.value,
            payload=clean_payload,
        )
    )
    db.add(
        OutboxEvent(
            workspace_id=request.workspace_id,
            request_id=request.id,
            event_type=f"approval_request.{action.value}",
            payload=clean_payload | {
                "requestId": request.id,
                "workspaceId": request.workspace_id,
                "status": request.status.value,
            },
        )
    )


def replay_or_conflict(existing, payload, actor_user_id):
    expected = (payload.source_type, payload.source_id, payload.title, payload.description,
                frozenset(payload.reviewer_user_ids))
    actual = (existing.source_type, existing.source_id, existing.title, existing.description,
              frozenset(r.reviewer_user_id for r in existing.reviewers))
    if existing.created_by != actor_user_id or actual != expected:
        raise HTTPException(status_code=409, detail="Idempotency-Key already used for another request")
    return existing


def create_request(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    payload: CreateApprovalRequest,
    idempotency_key: str | None,
) -> ApprovalRequest:
    dedupe_key = build_idempotency_key(workspace_id, actor_user_id, payload, idempotency_key)
    existing = db.scalar(
        select(ApprovalRequest)
        .where(ApprovalRequest.workspace_id == workspace_id, ApprovalRequest.idempotency_key == dedupe_key)
        .options(selectinload(ApprovalRequest.reviewers))
    )
    if existing:
        return replay_or_conflict(existing, payload, actor_user_id)

    reviewer_ids = list(dict.fromkeys(payload.reviewer_user_ids))
    request = ApprovalRequest(
        workspace_id=workspace_id,
        source_type=payload.source_type,
        source_id=payload.source_id,
        title=payload.title,
        description=payload.description,
        idempotency_key=dedupe_key,
        created_by=actor_user_id,
        status=ApprovalStatus.pending,
        reviewers=[ApprovalReviewer(reviewer_user_id=reviewer_id) for reviewer_id in reviewer_ids],
    )
    db.add(request)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(ApprovalRequest)
            .where(ApprovalRequest.workspace_id == workspace_id, ApprovalRequest.idempotency_key == dedupe_key)
            .options(selectinload(ApprovalRequest.reviewers))
        )
        if existing:
            return replay_or_conflict(existing, payload, actor_user_id)
        raise

    add_audit_and_event(
        db,
        request=request,
        actor_user_id=actor_user_id,
        action=AuditAction.created,
        before_status=None,
        payload={"sourceType": payload.source_type.value, "sourceId": payload.source_id},
    )
    db.commit()
    db.refresh(request)
    return get_request_or_404(db, workspace_id=workspace_id, request_id=request.id)


def list_requests(
    db: Session,
    *,
    workspace_id: str,
    status_filter: ApprovalStatus | None,
    source_type: SourceType | None,
    limit: int,
    offset: int,
) -> tuple[list[ApprovalRequest], int]:
    filters = [ApprovalRequest.workspace_id == workspace_id]
    if status_filter:
        filters.append(ApprovalRequest.status == status_filter)
    if source_type:
        filters.append(ApprovalRequest.source_type == source_type)

    total = db.scalar(select(func.count()).select_from(ApprovalRequest).where(*filters)) or 0
    items = list(
        db.scalars(
            select(ApprovalRequest)
            .where(*filters)
            .options(selectinload(ApprovalRequest.reviewers))
            .order_by(ApprovalRequest.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return items, total


def get_request_or_404(db: Session, *, workspace_id: str, request_id: str) -> ApprovalRequest:
    request = db.scalar(
        select(ApprovalRequest)
        .where(ApprovalRequest.workspace_id == workspace_id, ApprovalRequest.id == request_id)
        .options(selectinload(ApprovalRequest.reviewers))
    )
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found")
    return request


def decide_request(
    db: Session,
    *,
    workspace_id: str,
    request_id: str,
    actor_user_id: str,
    target_status: ApprovalStatus,
    action: AuditAction,
    comment: str | None = None,
    reason: str | None = None,
) -> ApprovalRequest:
    request = get_request_or_404(db, workspace_id=workspace_id, request_id=request_id)
    if request.status in FINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Request already has final status: {request.status.value}",
        )

    before = request.status
    now = utcnow()
    changed = db.execute(
        update(ApprovalRequest).where(
            ApprovalRequest.id == request_id,
            ApprovalRequest.workspace_id == workspace_id,
            ApprovalRequest.status == ApprovalStatus.pending,
        ).values(status=target_status, decided_by=actor_user_id, decided_at=now,
                 updated_at=now, decision_comment=comment, decision_reason=reason)
    )
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Request already has a final status")
    db.refresh(request)

    payload: dict[str, Any] = {}
    if comment is not None:
        payload["comment"] = comment
    if reason is not None:
        payload["reason"] = reason

    add_audit_and_event(
        db,
        request=request,
        actor_user_id=actor_user_id,
        action=action,
        before_status=before,
        payload=payload,
    )
    db.commit()
    return get_request_or_404(db, workspace_id=workspace_id, request_id=request_id)
