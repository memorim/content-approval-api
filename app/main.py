from __future__ import annotations

from fastapi import Depends, FastAPI, Header, Query, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import Principal, get_principal, require_action
from app.config import get_settings
from app.database import get_db
from app.models import ApprovalStatus, AuditAction, SourceType
from app.schemas import (
    ApprovalListResponse,
    ApprovalRequestResponse,
    ApproveRequest,
    CancelRequest,
    CreateApprovalRequest,
    RejectRequest,
)
from app.service import create_request, decide_request, get_request_or_404, list_requests, to_response_dict

settings = get_settings()


app = FastAPI(title=settings.app_name, version="1.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.post(
    "/api/v1/workspaces/{workspace_id}/approval-requests",
    response_model=ApprovalRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_approval_request(
    workspace_id: str,
    payload: CreateApprovalRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    if principal.workspace_id != workspace_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace mismatch")
    require_action(principal, "approval:create")
    item = create_request(
        db,
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    # If the item existed due to idempotency, 200 is more precise than 201.
    if item.created_by == principal.user_id and idempotency_key and item.idempotency_key == idempotency_key:
        # We do not store a created-now flag; keeping 201 is acceptable for safe retries.
        pass
    return to_response_dict(item)


@app.get("/api/v1/workspaces/{workspace_id}/approval-requests", response_model=ApprovalListResponse)
def get_approval_requests(
    workspace_id: str,
    status_filter: ApprovalStatus | None = Query(default=None, alias="status"),
    source_type: SourceType | None = Query(default=None, alias="sourceType"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    if principal.workspace_id != workspace_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace mismatch")
    require_action(principal, "approval:read")
    items, total = list_requests(
        db,
        workspace_id=workspace_id,
        status_filter=status_filter,
        source_type=source_type,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [to_response_dict(item) for item in items],
        "limit": limit,
        "offset": offset,
        "total": total,
    }


@app.get(
    "/api/v1/workspaces/{workspace_id}/approval-requests/{request_id}",
    response_model=ApprovalRequestResponse,
)
def get_approval_request(
    workspace_id: str,
    request_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    if principal.workspace_id != workspace_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace mismatch")
    require_action(principal, "approval:read")
    return to_response_dict(get_request_or_404(db, workspace_id=workspace_id, request_id=request_id))


@app.post(
    "/api/v1/workspaces/{workspace_id}/approval-requests/{request_id}/approve",
    response_model=ApprovalRequestResponse,
)
def approve_approval_request(
    workspace_id: str,
    request_id: str,
    payload: ApproveRequest,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    if principal.workspace_id != workspace_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace mismatch")
    require_action(principal, "approval:decide")
    item = decide_request(
        db,
        workspace_id=workspace_id,
        request_id=request_id,
        actor_user_id=principal.user_id,
        target_status=ApprovalStatus.approved,
        action=AuditAction.approved,
        comment=payload.comment,
    )
    return to_response_dict(item)


@app.post(
    "/api/v1/workspaces/{workspace_id}/approval-requests/{request_id}/reject",
    response_model=ApprovalRequestResponse,
)
def reject_approval_request(
    workspace_id: str,
    request_id: str,
    payload: RejectRequest,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    if principal.workspace_id != workspace_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace mismatch")
    require_action(principal, "approval:decide")
    item = decide_request(
        db,
        workspace_id=workspace_id,
        request_id=request_id,
        actor_user_id=principal.user_id,
        target_status=ApprovalStatus.rejected,
        action=AuditAction.rejected,
        reason=payload.reason,
    )
    return to_response_dict(item)


@app.post(
    "/api/v1/workspaces/{workspace_id}/approval-requests/{request_id}/cancel",
    response_model=ApprovalRequestResponse,
)
def cancel_approval_request(
    workspace_id: str,
    request_id: str,
    payload: CancelRequest,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    if principal.workspace_id != workspace_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace mismatch")
    require_action(principal, "approval:cancel")
    item = decide_request(
        db,
        workspace_id=workspace_id,
        request_id=request_id,
        actor_user_id=principal.user_id,
        target_status=ApprovalStatus.cancelled,
        action=AuditAction.cancelled,
        reason=payload.reason,
    )
    return to_response_dict(item)
