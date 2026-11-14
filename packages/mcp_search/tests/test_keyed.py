import json

import httpx
import pytest
import respx

from homer_mcp_search.keyed import BRAVE_URL, TAVILY_URL, keyed_search
from homer_net import OutboundCall

KEY = "test-key-0000abcd"

BRAVE_BODY = {
    "query": {"original": "python"},
    "web": {
        "results": [
            {
                "title": "Welcome to <strong>Python</strong>.org",
                "url": "https://www.python.org/",
                "description": "The home of <strong>Python</strong> &amp; docs.",
                "page_age": "2026-10-01T00:00:00",
            },
            {"title": "Guide", "url": "https://docs.example.test/guide", "description": "A guide."},
            {"title": "No link"},
        ]
    },
}

TAVILY_BODY = {
    "query": "python",
    "results": [
        {
            "title": "Python news",
            "url": "https://news.example.test/python",
            "content": "Python 3.14 is out.",
            "score": 0.9,
            "published_date": "2026-10-02",
        },
        {"title": "Guide", "url": "https://docs.example.test/guide", "content": "A guide."},
    ],
    "response_time": 0.5,
}


@respx.mock
async def test_brave_results_are_normalised_and_the_key_goes_in_the_header() -> None:
    calls: list[OutboundCall] = []
    route = respx.get(BRAVE_URL).mock(return_value=httpx.Response(200, json=BRAVE_BODY))
    found = await keyed_search("brave", "python", 5, KEY, calls.append)
    assert found == {
        "results": [
            {
                "title": "<untrusted>Welcome to Python.org</untrusted>",
                "url": "https://www.python.org/",
                "snippet": "<untrusted>The home of Python & docs.</untrusted>",
                "published": "2026-10-01T00:00:00",
            },
            {
                "title": "<untrusted>Guide</untrusted>",
                "url": "https://docs.example.test/guide",
                "snippet": "<untrusted>A guide.</untrusted>",
            },
        ]
    }
    request = route.calls.last.request
    assert request.headers["X-Subscription-Token"] == KEY
    assert request.url.params["q"] == "python"
    assert request.url.params["count"] == "5"
    assert [(c.method, c.host, c.path, c.status) for c in calls] == [
        ("GET", "api.search.brave.com", "/res/v1/web/search", 200)
    ]


@respx.mock
async def test_tavily_results_are_normalised_and_the_key_is_a_bearer_token() -> None:
    route = respx.post(TAVILY_URL).mock(return_value=httpx.Response(200, json=TAVILY_BODY))
    found = await keyed_search("tavily", "python", 1, KEY, lambda call: None)
    assert found == {
        "results": [
            {
                "title": "<untrusted>Python news</untrusted>",
                "url": "https://news.example.test/python",
                "snippet": "<untrusted>Python 3.14 is out.</untrusted>",
                "published": "2026-10-02",
            }
        ]
    }
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert json.loads(request.content) == {
        "query": "python",
        "max_results": 1,
        "search_depth": "basic",
    }


@pytest.mark.parametrize(
    ("provider", "status", "body", "error"),
    [
        ("brave", 422, '{"error":{"code":"SUBSCRIPTION_TOKEN_INVALID"}}', "search_invalid_key"),
        ("brave", 401, "", "search_invalid_key"),
        ("brave", 429, "", "search_limited"),
        ("tavily", 401, '{"detail":{"error":"Unauthorized"}}', "search_invalid_key"),
        ("tavily", 432, "", "search_limited"),
        ("tavily", 500, "", "search_failed"),
    ],
)
@respx.mock
async def test_provider_errors_map_to_clear_codes(
    provider: str, status: int, body: str, error: str
) -> None:
    respx.route(host=f"api.{'search.brave' if provider == 'brave' else 'tavily'}.com").mock(
        return_value=httpx.Response(status, text=body)
    )
    found = await keyed_search(provider, "python", 5, KEY, lambda call: None)
    assert found == {"error": error, "status": status}
    assert KEY not in json.dumps(found)


@respx.mock
async def test_a_network_failure_is_reported_without_the_key() -> None:
    respx.get(BRAVE_URL).mock(side_effect=httpx.ConnectError(f"boom {KEY}"))
    found = await keyed_search("brave", "python", 5, KEY, lambda call: None)
    assert found == {"error": "search_failed", "detail": "ConnectError"}
