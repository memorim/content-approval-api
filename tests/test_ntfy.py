from uuid import uuid4

import httpx
import pytest

from app.outbox import ntfy_receiver


def test_ntfy_sends_only_generic_metadata_and_keeps_the_same_event_key():
    identifier = str(uuid4())
    calls = []

    def receive(request):
        assert str(request.url) == "https://ntfy.sh/"
        assert request.headers["Idempotency-Key"] == identifier
        assert b"Private" not in request.content
        assert b"private@example.test" not in request.content
        calls.append(request.content)
        return httpx.Response(200, json={"event": "message"})

    with httpx.Client(transport=httpx.MockTransport(receive)) as client:
        deliver = ntfy_receiver("a" * 48, client)
        event = {"id": identifier, "payload": {"title": "Private", "email": "private@example.test"}}
        deliver(event)
        deliver(event)
        assert calls[0] == calls[1]
        for topic in ["", "short", "https://example.com/", "a" * 129]:
            with pytest.raises(ValueError):
                ntfy_receiver(topic, client)


def test_ntfy_errors_and_redirects_leave_delivery_to_the_existing_retry_queue():
    for status in [302, 429, 503]:
        calls = []

        def receive(request):
            calls.append(str(request.url))
            return httpx.Response(status, headers={"Location": "https://outside.example"})

        with httpx.Client(transport=httpx.MockTransport(receive)) as client:
            with pytest.raises(httpx.HTTPStatusError):
                ntfy_receiver("a" * 48, client)({"id": str(uuid4())})
        assert calls == ["https://ntfy.sh/"]
