import httpx
import pytest
from done_irl.adapters import BeeAdapter, RingAdapter, NotificationAdapter
from done_irl.models import ApiError


@pytest.mark.asyncio
async def test_ring_expired_token_does_not_become_live_or_simulated():
    adapter = RingAdapter("private-test-token", httpx.MockTransport(lambda r: httpx.Response(401)))
    with pytest.raises(ApiError) as error:
        await adapter.devices()
    assert error.value.code == "RING_ACCESS_REJECTED"
    assert "private-test-token" not in error.value.message
    await adapter.client.aclose()


@pytest.mark.asyncio
async def test_ring_session_budget_and_cleanup():
    calls = []

    def handler(request):
        calls.append((request.method, str(request.url)))
        return httpx.Response(
            201, headers={"Location": "https://api.amazonvision.com/sessions/test"}, text="v=0\r\n"
        )

    adapter = RingAdapter("test", httpx.MockTransport(handler))
    result = await adapter.whep("test-device", "v=0\r\n", battery=True)
    assert result["max_seconds"] == 30
    adapter.sessions[result["location"]] = 0
    await adapter.cleanup()
    assert not adapter.sessions
    assert calls[-1][0] == "DELETE"
    await adapter.client.aclose()


@pytest.mark.asyncio
async def test_ring_rejects_untrusted_session_url():
    adapter = RingAdapter(
        "test",
        httpx.MockTransport(
            lambda r: httpx.Response(
                201, headers={"Location": "https://attacker.example/collect-token"}, text="sdp"
            )
        ),
    )
    with pytest.raises(ApiError) as error:
        await adapter.whep("test", "sdp")
    assert error.value.code == "UNTRUSTED_SESSION_URL"
    await adapter.client.aclose()


# Event shapes mirror the official bee-cli stream formatter (bee-computer/bee-cli,
# sources/commands/stream/index.ts); they are not captured from a live account.
BEE_STREAM = (
    ": heartbeat\n\n"
    "id: 41\nevent: new-utterance\n"
    'data: {"conversation_uuid":"c-1","utterance":{"id":7,"text":"I will call my sister at 6 pm",'
    '"speaker":"speaker_1","spoken_at":1792488600000}}\n\n'
    "id: 42\nevent: todo-created\n"
    'data: {"todo":{"id":99,"text":"Renew passport","completed":false,"alarmAt":1792575000000}}\n\n'
    "id: 43\nevent: update-conversation-summary\n"
    'data: {"conversation_id":5,"short_summary":"Chat"}\n\n'
)


@pytest.mark.asyncio
async def test_bee_sse_parser_handles_heartbeat_and_cursor():
    seen = []

    def handler(request):
        assert "new-utterance" in request.url.query.decode() and "todo-created" in request.url.query.decode()
        return httpx.Response(200, text=BEE_STREAM, headers={"Content-Type": "text/event-stream"})

    adapter = BeeAdapter("test", httpx.MockTransport(handler))

    async def handle(body, event_id):
        seen.append((body, event_id))

    await adapter.stream_once(handle)
    (utt, utt_id), (todo, todo_id) = seen
    assert utt_id == "bee:utt:c-1:7" and utt["utterance"] == "I will call my sister at 6 pm"
    assert utt["speaker"] == "UNKNOWN"  # wearer label not configured -> owner must confirm
    assert utt["occurred_at"].startswith("2026-10-20T")
    assert todo_id == "bee:todo:99" and todo["source_kind"] == "BEE_TODO" and todo["due_at"]
    assert adapter.cursor == "43" and adapter.ignored == 1
    await adapter.client.aclose()


def test_bee_normalizer_wearer_label_and_rejects_unknown_shapes():
    from done_irl.adapters import normalize_bee_event

    data = {"conversation_uuid": "c", "utterance": {"id": 1, "text": "I'll pay rent", "speaker": "Me"}}
    assert normalize_bee_event("new-utterance", data, self_speakers="me")["speaker"] == "SELF"
    assert normalize_bee_event("new-utterance", {"utterance": "flat string"}) is None
    assert normalize_bee_event("new-utterance", {"utterance": {"text": "no id"}}) is None
    assert normalize_bee_event("todo-created", {"todo": {"id": 3, "text": "x", "completed": True}}) is None
    assert normalize_bee_event("journal-text", {"text": "hello"}) is None


@pytest.mark.asyncio
async def test_bee_401_redacted():
    adapter = BeeAdapter("do-not-leak", httpx.MockTransport(lambda r: httpx.Response(401)))
    with pytest.raises(ApiError) as error:
        await adapter.stream_once(None)
    assert "do-not-leak" not in error.value.message
    await adapter.client.aclose()


@pytest.mark.parametrize("provider", ["alexa", "bee-haptic"])
def test_unavailable_notification_adapters_do_not_fake_success(provider):
    adapter = NotificationAdapter(provider)
    assert not adapter.capabilities()["available"]
    assert adapter.send("test")["status"] == "UNAVAILABLE"
