from __future__ import annotations

from dataclasses import dataclass
from fastapi import Header, HTTPException, Path, status


@dataclass(frozen=True)
class Principal:
    workspace_id: str
    user_id: str
    actions: frozenset[str]


def parse_actions(header: str) -> frozenset[str]:
    return frozenset(action.strip() for action in header.split(",") if action.strip())


def get_principal(
    x_workspace_id: str = Header(..., alias="X-Workspace-Id"),
    x_user_id: str = Header(..., alias="X-User-Id"),
    x_actions: str = Header("", alias="X-Actions"),
) -> Principal:
    if not x_workspace_id or not x_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing auth headers")
    return Principal(workspace_id=x_workspace_id, user_id=x_user_id, actions=parse_actions(x_actions))


def authorize_workspace(
    workspace_id: str = Path(...),
    principal: Principal = None,
) -> None:
    if principal is None:
        return
    if principal.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace mismatch")


def require_action(principal: Principal, action: str) -> None:
    if action not in principal.actions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing action: {action}")
