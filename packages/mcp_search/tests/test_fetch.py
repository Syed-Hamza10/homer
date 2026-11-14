import httpx
import pytest
import respx

from homer_mcp_search import fetch
from homer_net import Allowlist, AllowlistedClient, OutboundCall
from homer_net.pinning import PinnedTransport

PUBLIC = "93.184.215.14"
PRIVATE = "10.0.0.7"
PAGE = b"<html><head><title>Pinned</title></head><body><p>pinned page body</p></body></html>"


@pytest.fixture
def lookups(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []
    answers = {"news.example": [[PUBLIC], [PRIVATE]], "inside.example": [[PRIVATE]]}

    async def resolve(hostname: str) -> list[str]:
        seen.append(hostname)
        return answers[hostname].pop(0)

    monkeypatch.setattr(fetch, "resolve", resolve)
    return seen


async def test_connects_to_first_answer_and_never_resolves_again(
    respx_mock: respx.MockRouter, lookups: list[str]
) -> None:
    respx_mock.get(f"https://{PUBLIC}/start").mock(
        return_value=httpx.Response(302, headers={"location": "/page"})
    )
    page = respx_mock.get(f"https://{PUBLIC}/page").mock(
        return_value=httpx.Response(200, content=PAGE, headers={"content-type": "text/html"})
    )
    calls: list[OutboundCall] = []

    result = await fetch.fetch_page("https://news.example/start", calls.append)

    assert lookups == ["news.example"]
    assert result["url"] == "https://news.example/page"
    assert "Pinned" in result["title"]
    request = page.calls.last.request
    assert request.headers["host"] == "news.example"
    assert request.extensions["sni_hostname"] == "news.example"
    assert [(call.host, call.path, call.status) for call in calls] == [
        ("news.example", "/start", 302),
        ("news.example", "/page", 200),
    ]


@pytest.mark.respx(assert_all_called=False)
async def test_redirect_to_another_host_is_refused(
    respx_mock: respx.MockRouter, lookups: list[str]
) -> None:
    respx_mock.get(f"https://{PUBLIC}/start").mock(
        return_value=httpx.Response(302, headers={"location": "https://inside.example/admin"})
    )
    inside = respx_mock.get(f"https://{PRIVATE}/admin").mock(return_value=httpx.Response(200))

    result = await fetch.fetch_page("https://news.example/start", lambda call: None)

    assert result == {"error": "blocked_host", "host": "inside.example"}
    assert lookups == ["news.example"]
    assert not inside.called


@pytest.mark.respx(assert_all_called=False)
async def test_redirect_hop_to_private_address_is_refused_by_the_pin(
    respx_mock: respx.MockRouter, lookups: list[str]
) -> None:
    respx_mock.get(f"https://{PUBLIC}/start").mock(
        return_value=httpx.Response(302, headers={"location": "https://inside.example/admin"})
    )
    inside = respx_mock.get(f"https://{PRIVATE}/admin").mock(return_value=httpx.Response(200))
    allowlist = Allowlist(["news.example", "inside.example"])
    transport = PinnedTransport(fetch.pin_address)

    async with AllowlistedClient(allowlist, transport=transport) as client:
        with pytest.raises(fetch.RefusedAddressError) as excinfo:
            await client.get("https://news.example/start")

    assert excinfo.value.code == "private_address"
    assert lookups == ["news.example", "inside.example"]
    assert not inside.called


async def test_private_first_answer_is_refused_before_any_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def resolve(hostname: str) -> list[str]:
        return [PUBLIC, PRIVATE]

    monkeypatch.setattr(fetch, "resolve", resolve)
    calls: list[OutboundCall] = []

    result = await fetch.fetch_page("https://news.example/", calls.append)

    assert result == {"error": "private_address"}
    assert calls == []
