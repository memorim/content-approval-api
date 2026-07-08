from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.models import ApprovalStatus, SourceType


class CreateApprovalRequest(BaseModel):
    source_type: SourceType = Field(alias="sourceType")
    source_id: str = Field(alias="sourceId", min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=512)
    description: str | None = None
    reviewer_user_ids: list[str] = Field(alias="reviewerUserIds", min_length=1)

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ApproveRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)

    model_config = ConfigDict(extra="forbid")


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)

    model_config = ConfigDict(extra="forbid")


class CancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)

    model_config = ConfigDict(extra="forbid")


class AuditLogResponse(BaseModel):
    id: str
    actor_user_id: str = Field(alias="actorUserId")
    action: str
    before_status: str | None = Field(alias="beforeStatus")
    after_status: str = Field(alias="afterStatus")
    payload: dict
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ApprovalRequestResponse(BaseModel):
    id: str
    workspace_id: str = Field(alias="workspaceId")
    source_type: SourceType = Field(alias="sourceType")
    source_id: str = Field(alias="sourceId")
    title: str
    description: str | None
    reviewer_user_ids: list[str] = Field(alias="reviewerUserIds")
    status: ApprovalStatus
    created_by: str = Field(alias="createdBy")
    decided_by: str | None = Field(alias="decidedBy")
    decision_comment: str | None = Field(alias="decisionComment")
    decision_reason: str | None = Field(alias="decisionReason")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    decided_at: datetime | None = Field(alias="decidedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ApprovalListResponse(BaseModel):
    items: list[ApprovalRequestResponse]
    limit: int
    offset: int
    total: int
