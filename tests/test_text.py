import pytest

from studio.services.text import has_speakable_content, sanitize_overlay_text, sanitize_text


def test_sanitize_text_replaces_urls_and_normalizes_numbers():
    assert sanitize_text("Смотри https://example.test/a 25") == "Смотри ссылка двадцать пять"


def test_sanitize_text_handles_long_isolated_numbers():
    assert sanitize_text("123456789012") == "один два три четыре пять шесть семь восемь девять ноль один два"


@pytest.mark.parametrize("text", ["", "!!!", "😀", "\u200b\u200d"])
def test_has_speakable_content_rejects_non_speech_text(text):
    assert not has_speakable_content(text)


def test_has_speakable_content_accepts_cyrillic_and_latin():
    assert has_speakable_content("Привет 123")
    assert has_speakable_content("Hello")


def test_overlay_text_replaces_urls_without_other_mutation():
    assert sanitize_overlay_text("Ссылка: www.example.test/abc") == "Ссылка: ссылка"
