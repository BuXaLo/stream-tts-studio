import json
from contextlib import nullcontext

from fastapi import FastAPI
from fastapi.testclient import TestClient

from studio.routes.characters import create_characters_router


DEFAULT_TEST_PRESET = {
    "name": "Новый персонаж",
    "reference_text": "",
    "speed": 1.0,
    "theme": {
        "border_color": "#6366f1",
        "bg_color": "#0d0b14",
        "text_color": "#fcebeb",
        "name_bg_color": "#6366f1",
        "name_text_color": "#ffffff",
        "text_stroke_color": "#000000",
        "text_stroke_width": 0.0,
        "bg_opacity": 0.9,
        "hide_delay": 2.0,
        "avatar_position": "left",
        "box_shape": "shape-rounded",
        "border_fx": "fx-neon",
        "font_family": "Comfortaa",
        "font_size": 22,
        "entrance_animation": "slide-up",
        "exit_animation": "fade-out",
        "text_animation": "typewriter",
    },
}


def _make_client(tmp_path, initial_presets=None):
    char_dir = tmp_path / "characters"
    char_dir.mkdir()
    state = {"presets": dict(initial_presets or {}), "active": ""}

    def load_presets():
        return dict(state["presets"])

    def save_presets(value):
        state["presets"] = dict(value)

    app = FastAPI()
    app.include_router(
        create_characters_router(
            load_presets,
            save_presets,
            lambda: state["active"],
            lambda value: state.update(active=value),
            DEFAULT_TEST_PRESET,
            lambda value: value,
            str(char_dir),
            str(tmp_path / "presets.json"),
            str(tmp_path / "active.json"),
            lambda path: nullcontext(),
            lambda path, data: None,
            lambda raw: raw,
            {},
        )
    )
    return TestClient(app), state


def test_theme_stroke_fields_are_saved_and_clamped(tmp_path):
    client, state = _make_client(tmp_path)

    resp = client.post(
        "/api/characters/save",
        data={
            "char_id": "mita",
            "name": "Мита",
            "reference_text": "Привет",
            "speed": "1.0",
            "theme_json": json.dumps(
                {"text_stroke_color": "#FF00AA", "text_stroke_width": 7.5}
            ),
        },
    )
    assert resp.status_code == 200
    saved_theme = state["presets"]["mita"]["theme"]
    assert saved_theme["text_stroke_color"] == "#ff00aa"
    assert saved_theme["text_stroke_width"] == 4.0

    resp_bad = client.post(
        "/api/characters/save",
        data={
            "char_id": "mita_bad",
            "name": "Мита 2",
            "reference_text": "Привет",
            "speed": "1.0",
            "theme_json": json.dumps(
                {"text_stroke_color": "not-a-color", "text_stroke_width": -3}
            ),
        },
    )
    assert resp_bad.status_code == 200
    bad_theme = state["presets"]["mita_bad"]["theme"]
    assert bad_theme["text_stroke_color"] == "#000000"
    assert bad_theme["text_stroke_width"] == 0.0


def test_legacy_preset_gets_default_stroke_in_overlay_config(tmp_path):
    legacy = {
        "legacy_char": {
            "name": "Legacy",
            "reference_text": "",
            "speed": 1.0,
            "theme": {"border_color": "#112233"},
        }
    }
    client, _ = _make_client(tmp_path, initial_presets=legacy)
    resp = client.get("/api/active_overlay_config", params={"char_id": "legacy_char"})
    assert resp.status_code == 200
    theme = resp.json()["theme"]
    assert theme["border_color"] == "#112233"
    assert theme["text_stroke_color"] == "#000000"
    assert theme["text_stroke_width"] == 0.0
