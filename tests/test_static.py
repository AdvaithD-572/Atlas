from fastapi.testclient import TestClient

from atlas.database import migrate
from atlas.main import create_app


def test_static_bundle_is_public_but_api_remains_protected(settings, tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>Atlas test</title>")
    (tmp_path / "private.txt").write_text("private-test-sentinel")
    settings.frontend_dir = static
    migrate(settings.database_path)
    with TestClient(create_app(settings)) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "default-src 'self'" in page.headers["content-security-policy"]
        assert "unsafe-inline" not in page.headers["content-security-policy"]
        protected = client.get("/v1/documents")
        assert protected.status_code == 401
        assert "default-src 'none'" in protected.headers["content-security-policy"]
        traversal = client.get("/%2e%2e/private.txt")
        assert traversal.status_code == 404
        assert "private-test-sentinel" not in traversal.text
