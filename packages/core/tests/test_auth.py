from fastapi.testclient import TestClient

from homer_core.auth import SESSION_COOKIE
from homer_core.config import Settings, write_passphrase


def test_login_sets_http_only_cookie(client: TestClient, origin: dict[str, str]) -> None:
    response = client.post("/api/auth/login", json={"passphrase": "test-pass"}, headers=origin)
    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Max-Age=604800" in cookie
    assert "Secure" not in cookie


def test_wrong_passphrase_is_401(client: TestClient, origin: dict[str, str]) -> None:
    response = client.post("/api/auth/login", json={"passphrase": "nope"}, headers=origin)
    assert response.status_code == 401
    assert SESSION_COOKIE not in response.cookies


def test_sixth_failure_is_429_even_with_the_right_passphrase(
    client: TestClient, origin: dict[str, str]
) -> None:
    for _ in range(5):
        assert (
            client.post("/api/auth/login", json={"passphrase": "nope"}, headers=origin).status_code
            == 401
        )
    response = client.post("/api/auth/login", json={"passphrase": "test-pass"}, headers=origin)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"


def test_non_get_without_origin_is_403(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"passphrase": "test-pass"})
    assert response.status_code == 403


def test_non_get_with_foreign_origin_is_403(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"passphrase": "test-pass"},
        headers={"Origin": "http://evil.example"},
    )
    assert response.status_code == 403


def test_protected_route_without_cookie_is_401(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/conversations").status_code == 401


def test_me_returns_the_logged_in_user(logged_in: TestClient) -> None:
    response = logged_in.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json() == {"user_id": 1, "name": "Tester"}


def test_tampered_cookie_is_401(logged_in: TestClient) -> None:
    logged_in.cookies.set(SESSION_COOKIE, "1.bad.signature")
    assert logged_in.get("/api/auth/me").status_code == 401


def test_logout_clears_cookie(logged_in: TestClient, origin: dict[str, str]) -> None:
    response = logged_in.post("/api/auth/logout", headers=origin)
    assert response.status_code == 204
    assert 'homer_session=""' in response.headers["set-cookie"]
    assert logged_in.get("/api/auth/me").status_code == 401


def test_health_is_public(client: TestClient) -> None:
    assert client.get("/api/health").status_code == 200


def test_login_accepts_a_passphrase_changed_in_env_since_start(
    client: TestClient, origin: dict[str, str], settings: Settings
) -> None:
    write_passphrase(settings.homer_home, "changed")
    response = client.post("/api/auth/login", json={"passphrase": "changed"}, headers=origin)
    assert response.status_code == 204
    assert settings.homer_passphrase.get_secret_value() == "changed"
    old = client.post("/api/auth/login", json={"passphrase": "test-pass"}, headers=origin)
    assert old.status_code == 401


def test_login_still_rejects_a_wrong_passphrase_when_env_exists(
    client: TestClient, origin: dict[str, str], settings: Settings
) -> None:
    write_passphrase(settings.homer_home, "changed")
    response = client.post("/api/auth/login", json={"passphrase": "nope"}, headers=origin)
    assert response.status_code == 401
