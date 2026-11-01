import httpx
import pytest

pytestmark = pytest.mark.e2e


def test_login_rules(fresh_server: str, passphrase: str) -> None:
    origin = {"Origin": fresh_server}
    with httpx.Client(base_url=fresh_server, timeout=30.0) as client:
        wrong = client.post("/api/auth/login", json={"passphrase": "nope"}, headers=origin)
        assert wrong.status_code == 401

        no_origin = client.post("/api/auth/login", json={"passphrase": passphrase})
        assert no_origin.status_code == 403

        ok = client.post("/api/auth/login", json={"passphrase": passphrase}, headers=origin)
        assert ok.status_code == 204
        cookie = ok.headers["set-cookie"]
        assert cookie.startswith("homer_session=")
        assert "HttpOnly" in cookie
        assert "samesite=strict" in cookie.lower()

        for _ in range(5):
            attempt = client.post("/api/auth/login", json={"passphrase": "nope"}, headers=origin)
            assert attempt.status_code == 401
        sixth = client.post("/api/auth/login", json={"passphrase": "nope"}, headers=origin)
        assert sixth.status_code == 429
