import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ApprovalStatus, AuditAction, OutboxEvent
from app.schemas import CreateApprovalRequest
from app.service import create_request, decide_request, get_request_or_404


def test_stale_decision_cannot_overwrite_an_already_committed_final_status(tmp_path):
    engine = create_engine('sqlite:///' + (tmp_path / 'decisions.sqlite').as_posix())
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with factory() as first, factory() as second:
            item = create_request(first, workspace_id='w', actor_user_id='u',
                payload=CreateApprovalRequest(sourceType='publication', sourceId='s',
                    title='Review', reviewerUserIds=['r']), idempotency_key='decision')
            stale = get_request_or_404(second, workspace_id='w', request_id=item.id)
            assert stale.status == ApprovalStatus.pending
            decide_request(first, workspace_id='w', request_id=item.id, actor_user_id='r',
                target_status=ApprovalStatus.approved, action=AuditAction.approved)
            with pytest.raises(HTTPException) as error:
                decide_request(second, workspace_id='w', request_id=item.id, actor_user_id='r',
                    target_status=ApprovalStatus.rejected, action=AuditAction.rejected, reason='Late')
            assert error.value.status_code == 409
        with factory() as verify:
            assert get_request_or_404(verify, workspace_id='w', request_id=item.id).status == ApprovalStatus.approved
            assert len(list(verify.scalars(select(OutboxEvent)))) == 2
    finally:
        engine.dispose()


def test_same_idempotency_key_rejects_a_different_request_or_actor(client):
    path='/api/v1/workspaces/w/approval-requests'
    headers={'X-Workspace-Id':'w','X-User-Id':'u','X-Actions':'approval:create','Idempotency-Key':'shared'}
    body={'sourceType':'publication','sourceId':'s','title':'Original','reviewerUserIds':['r']}
    assert client.post(path,headers=headers,json=body).status_code == 201
    assert client.post(path,headers=headers,json=body | {'title':'Changed'}).status_code == 409
    assert client.post(path,headers=headers | {'X-User-Id':'another'},json=body).status_code == 409
    assert client.post(path,headers=headers | {'Idempotency-Key':'x'*129},json=body).status_code == 400
