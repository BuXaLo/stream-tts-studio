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


@pytest.mark.parametrize(
    "text, expected",
    [
        ("25%", "двадцать пять процентов"),
        ("1%", "один процент"),
        ("3.5", "три целых пять десятых"),
        ("3,5", "три целых пять десятых"),
        ("1.5", "одна целая пять десятых"),
        ("2.25", "две целых двадцать пять сотых"),
        ("12:30", "двенадцать тридцать"),
        ("12:05", "двенадцать ноль пять"),
        ("1 000", "одна тысяча"),
        ("21 000 рублей", "двадцать одна тысяча рублей"),
        ("1 000 000", "один миллион"),
        ("1-й", "1-й"),
        ("5-го мая", "5-го мая"),
    ],
)
def test_sanitize_text_number_formats(text, expected):
    assert sanitize_text(text) == expected


def test_sanitize_text_keeps_previous_behavior_for_plain_numbers():
    assert sanitize_text("21000 рублей") == "двадцать одна тысяча рублей"
    assert sanitize_text("89001234567") == "восемь девять ноль ноль один два три четыре пять шесть семь"
    assert sanitize_text("5000000000") == "пять ноль ноль ноль ноль ноль ноль ноль ноль ноль"
    assert sanitize_text("100500") == "сто тысяч пятьсот"


def test_sanitize_text_ignores_private_use_characters_in_input():
    assert sanitize_text("1-й \ue005") == "1-й"


def test_sanitize_text_number_formats_before_punctuation():
    assert sanitize_text("бонус 1 000, всего 7.") == "бонус одна тысяча, всего семь."
    assert sanitize_text("цена 3.5.") == "цена три целых пять десятых."


@pytest.mark.parametrize(
    "text, expected",
    [
        ("+7 999 123-45-67", "+семь девятьсот девяносто девять сто двадцать три-сорок пять-шестьдесят семь"),
        ("8 999 123 45 67", "восемь девятьсот девяносто девять сто двадцать три сорок пять шестьдесят семь"),
        ("8 (999) 123-45-67", "восемь (девятьсот девяносто девять) сто двадцать три-сорок пять-шестьдесят семь"),
        ("+7 900", "+семь девятьсот"),
    ],
)
def test_sanitize_text_phone_numbers_keep_previous_behavior(text, expected):
    assert sanitize_text(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("12.05.2024", "двенадцать.пять.две тысячи двадцать четыре"),
        ("12/05/2024", "двенадцать/пять/две тысячи двадцать четыре"),
        ("1.000.000", "один.ноль.ноль"),
        ("24:00", "двадцать четыре:ноль"),
        ("12:60", "двенадцать:шестьдесят"),
        ("007", "ноль ноль семь"),
        ("COVID-19", "COVID-девятнадцать"),
        ("2024-году", "две тысячи двадцать четыре-году"),
        ("10-минутный", "десять-минутный"),
    ],
)
def test_sanitize_text_other_formats_keep_previous_behavior(text, expected):
    assert sanitize_text(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("3.5abc", "три.5abc"),
        ("25%abc", "двадцать пять%abc"),
        ("12:30abc", "двенадцать:30abc"),
        ("1 000abc", "один 000abc"),
    ],
)
def test_sanitize_text_number_glued_to_letters_keeps_previous_behavior(text, expected):
    assert sanitize_text(text) == expected


def test_sanitize_text_compromises_are_pinned():
    assert sanitize_text("5 100") == "пять тысяч сто"
    assert sanitize_text("3,5%") == "три целых пять десятых процента"
    assert sanitize_text("9:00") == "девять ноль ноль"
    assert sanitize_text("3.1234") == "три запятая один два три четыре"


def test_sanitize_text_removes_private_use_boundaries():
    assert sanitize_text("a\ue000b\uf8ffc 1-й") == "abc 1-й"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("007", "ноль ноль семь"),
        ("0007", "ноль ноль ноль семь"),
        ("7", "семь"),
        ("007%", "ноль ноль семь процентов"),
        ("12.05.2024", "двенадцать.пять.две тысячи двадцать четыре"),
        ("+7 900", "+семь девятьсот"),
    ],
)
def test_sanitize_text_preserves_leading_zeros_only_in_general_numbers(text, expected):
    assert sanitize_text(text) == expected


def test_sanitize_text_only_hides_explicit_ordinal_endings():
    assert sanitize_text("1-й и 5-го") == "1-й и 5-го"
    assert sanitize_text("10-минутный таймер") == "десять-минутный таймер"
    assert sanitize_text("в 2024-году") == "в две тысячи двадцать четыре-году"
