from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.main import ClientBuildFiles


def _client(tmp_path):
    (tmp_path / "static" / "js").mkdir(parents=True)
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "manifest.json").write_text("{}")
    (tmp_path / "static" / "js" / "main.abc123.js").write_text("console.log(1)")
    app = FastAPI()
    app.mount("/", ClientBuildFiles(directory=str(tmp_path), html=True))
    return TestClient(app)


def test_app_shell_is_revalidated_every_time(tmp_path):
    client = _client(tmp_path)
    for path in ("/", "/index.html", "/manifest.json"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache", path


def test_hashed_static_files_are_cached_long_term(tmp_path):
    response = _client(tmp_path).get("/static/js/main.abc123.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_conditional_request_still_gets_a_304_with_no_cache(tmp_path):
    client = _client(tmp_path)
    etag = client.get("/").headers["etag"]
    response = client.get("/", headers={"If-None-Match": etag})
    assert response.status_code == 304
    assert response.headers["cache-control"] == "no-cache"


def test_missing_files_are_not_given_cache_headers(tmp_path):
    response = _client(tmp_path).get("/static/js/missing.js")
    assert response.status_code == 404
    assert "cache-control" not in response.headers
