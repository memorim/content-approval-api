from app.models import AuditLog, OutboxEvent
from app.database import get_db


BASE = "/api/v1/workspaces/ws_1/approval-requests"
HEADERS_ALL = {
    "Authorization": "Bearer creator" + "-" * 40,
    "X-Workspace-Id": "ws_1",
    "X-User-Id": "usr_creator",
    "X-Actions": "approval:read,approval:create,approval:decide,approval:cancel",
}


def payload():
    return {
        "sourceType": "publication",
        "sourceId": "pub_123",
        "title": "Instagram reel draft",
        "description": "Needs final approval",
        "reviewerUserIds": ["usr_1", "usr_2"],
    }


def test_health_and_ready(client):
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200


def test_create_get_list_approve(client):
    create = client.post(BASE, json=payload(), headers=HEADERS_ALL | {"Idempotency-Key": "req-1"})
    assert create.status_code == 201, create.text
    data = create.json()
    assert data["status"] == "pending"
    assert data["reviewerUserIds"] == ["usr_1", "usr_2"]

    request_id = data["id"]
    get_one = client.get(f"{BASE}/{request_id}", headers=HEADERS_ALL)
    assert get_one.status_code == 200
    assert get_one.json()["id"] == request_id

    list_response = client.get(BASE, headers=HEADERS_ALL)
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    approve = client.post(f"{BASE}/{request_id}/approve", json={"comment": "Approved"}, headers=HEADERS_ALL)
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"
    assert approve.json()["decisionComment"] == "Approved"


def test_idempotent_create_does_not_duplicate(client):
    headers = HEADERS_ALL | {"Idempotency-Key": "same-key"}
    first = client.post(BASE, json=payload(), headers=headers)
    second = client.post(BASE, json=payload(), headers=headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    list_response = client.get(BASE, headers=HEADERS_ALL)
    assert list_response.json()["total"] == 1


def test_workspace_isolation(client):
    create = client.post(BASE, json=payload(), headers=HEADERS_ALL | {"Idempotency-Key": "isolate-1"})
    request_id = create.json()["id"]

    other_workspace_headers = {
        "Authorization": "Bearer other" + "-" * 40,
        "X-Workspace-Id": "ws_2",
        "X-User-Id": "usr_other",
        "X-Actions": "approval:read",
    }
    response = client.get(f"{BASE}/{request_id}", headers=other_workspace_headers)
    assert response.status_code == 403


def test_final_status_cannot_change(client):
    create = client.post(BASE, json=payload(), headers=HEADERS_ALL | {"Idempotency-Key": "final-1"})
    request_id = create.json()["id"]

    reject = client.post(f"{BASE}/{request_id}/reject", json={"reason": "Brand tone is wrong"}, headers=HEADERS_ALL)
    assert reject.status_code == 200

    approve = client.post(f"{BASE}/{request_id}/approve", json={"comment": "Approved"}, headers=HEADERS_ALL)
    assert approve.status_code == 409


def test_permissions_are_required(client):
    no_create_headers = {
        "Authorization": "Bearer reader" + "-" * 40,
        "X-Workspace-Id": "ws_1",
        "X-User-Id": "usr_1",
        "X-Actions": "approval:read",
    }
    response = client.post(BASE, json=payload(), headers=no_create_headers)
    assert response.status_code == 403


def test_each_change_creates_audit_and_outbox_event(client):
    create = client.post(BASE, json=payload(), headers=HEADERS_ALL | {"Idempotency-Key": "audit-1"})
    request_id = create.json()["id"]
    client.post(f"{BASE}/{request_id}/cancel", json={"reason": "Draft was removed"}, headers=HEADERS_ALL)

    db_override = next(iter(client.app.dependency_overrides.values()))
    db = next(db_override())
    try:
        audit_count = db.query(AuditLog).count()
        event_count = db.query(OutboxEvent).count()
    finally:
        db.close()
    assert audit_count == 2
    assert event_count == 2


def test_identity_and_grants_cannot_be_spoofed(client):
    assert client.get(BASE, headers={"X-Workspace-Id":"ws_1", "X-User-Id":"usr_creator", "X-Actions":"approval:read"}).status_code == 401
    assert client.get(BASE, headers={"Authorization":"Bearer " + "x" * 40}).status_code == 401
    spoofed = HEADERS_ALL | {"Authorization":"Bearer other" + "-" * 40}
    assert client.get(BASE, headers=spoofed).status_code == 403
    spoofed["Authorization"] = "Bearer reader" + "-" * 40
    assert client.post(BASE, headers=spoofed, json=payload()).status_code == 403


def test_misconfigured_registry_fails_closed(client, monkeypatch):
    monkeypatch.setenv("APP_AUTH_TOKENS", "not-json")
    assert client.get(BASE, headers=HEADERS_ALL).status_code == 503
