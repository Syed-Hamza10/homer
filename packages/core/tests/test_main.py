from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from homer_core.main import mount_spa


def spa_client(tmp_path: Path) -> TestClient:
    real = tmp_path / "real" / "static"
    (real / "assets").mkdir(parents=True)
    (real / "index.html").write_text("<html>index</html>")
    (real / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("secret")
    linked = tmp_path / "linked"
    linked.symlink_to(tmp_path / "real")
    app = FastAPI()
    mount_spa(app, linked / "static")
    return TestClient(app)


def test_spa_serves_assets_through_a_symlinked_path(tmp_path: Path) -> None:
    response = spa_client(tmp_path).get("/assets/app.js")
    assert response.text == "console.log(1)"
    assert "javascript" in response.headers["content-type"]


def test_spa_falls_back_to_index_and_stays_inside_static(tmp_path: Path) -> None:
    client = spa_client(tmp_path)
    assert client.get("/settings").text == "<html>index</html>"
    assert client.get("/..%2F..%2Fsecret.txt").text == "<html>index</html>"
    assert client.get("/api/nope").status_code == 404
