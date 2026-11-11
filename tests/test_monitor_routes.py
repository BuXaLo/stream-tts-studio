from fastapi import FastAPI
from fastapi.testclient import TestClient

from studio.routes.pages import create_pages_router


def test_monitor_page_and_assets_are_served(tmp_path):
    web_dir = tmp_path / "web"
    dashboard_dir = web_dir / "dashboard"
    overlay_dir = web_dir / "overlay"
    monitor_dir = web_dir / "monitor"
    for directory in (dashboard_dir, overlay_dir, monitor_dir):
        directory.mkdir(parents=True)
    (monitor_dir / "index.html").write_text("monitor page", encoding="utf-8")
    (monitor_dir / "app.js").write_text("window.monitorLoaded = true;", encoding="utf-8")
    (monitor_dir / "style.css").write_text("body { color: white; }", encoding="utf-8")
    app = FastAPI()
    app.include_router(create_pages_router(str(dashboard_dir), str(overlay_dir), object(), lambda *args: True))
    with TestClient(app) as client:
        assert client.get("/monitor").text == "monitor page"
        assert client.get("/monitor/app.js").text == "window.monitorLoaded = true;"
        assert client.get("/monitor/style.css").text == "body { color: white; }"
        assert client.get("/monitor/../app.py").status_code == 404
