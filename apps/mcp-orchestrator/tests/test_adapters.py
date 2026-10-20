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


@pytest.mark.asyncio
async def test_bee_sse_parser_handles_heartbeat_and_cursor():
    seen = []

    def handler(request):
        return httpx.Response(
            200,
            text=': heartbeat\n\nid: utterance-1\nevent: new-utterance\ndata: {"utterance":"I will call sister"}\n\n',
            headers={"Content-Type": "text/event-stream"},
        )

    adapter = BeeAdapter("test", httpx.MockTransport(handler))

    async def handle(body, event_id):
        seen.append((body, event_id))

    await adapter.stream_once(handle)
    assert seen == [({"utterance": "I will call sister"}, "utterance-1")]
    assert adapter.cursor == "utterance-1"
    await adapter.client.aclose()


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
