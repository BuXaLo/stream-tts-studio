import re
from pathlib import Path


EXPECTED_ROUTES = {
    "DELETE /api/characters/{char_id}",
    "GET /", "GET /api/active_overlay_config", "GET /api/da/auth_url",
    "GET /api/da/callback", "GET /api/da/config", "GET /api/fonts",
    "GET /api/presets", "GET /api/system_config", "GET /favicon.ico",
    "GET /overlay", "GET /overlay/", "POST /api/characters/save",
    "POST /api/convert_to_telegram_ogg", "POST /api/da/config",
    "POST /api/da/test_donation", "POST /api/isolate_vocal",
    "POST /api/normalize_audio", "POST /api/presets/set_active",
    "POST /api/system_config", "POST /api/test_draft_tts",
    "POST /api/trigger_overlay_preview", "POST /api/trim_and_transcribe",
    "POST /api/upload_font", "POST /speak", "WEBSOCKET /ws/overlay",
}


def test_refactor_preserves_all_http_and_websocket_route_paths():
    source_files = [Path("server/app.py"), *Path("server/studio/routes").glob("*.py")]
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_files)
    found = {
        f"{method.upper()} {path}"
        for method, path in re.findall(
            r"@router\.(get|post|put|patch|delete|websocket)\([\"']([^\"']+)[\"']", source
        )
    }
    assert found == EXPECTED_ROUTES
