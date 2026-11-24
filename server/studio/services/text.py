"""Text normalization and speech validation helpers."""
import re

def num_to_ru_words(n: int) -> str:
    if n == 0:
        return "ноль"
    if n < 0:
        return "минус " + num_to_ru_words(abs(n))

    units_m = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
    units_f = ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
    teens = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", 
             "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
    tens = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
    hundreds = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот"]

    def triplet(val: int, is_female: bool = False) -> str:
        res = []
        h = val // 100
        t = (val % 100) // 10
        u = val % 10
        if h > 0:
            res.append(hundreds[h])
        if t == 1:
            res.append(teens[u])
        else:
            if t > 1:
                res.append(tens[t])
            if u > 0:
                res.append(units_f[u] if is_female else units_m[u])
        return " ".join(res)

    def plural_form(val: int, f1: str, f2: str, f5: str) -> str:
        n100 = val % 100
        n10 = val % 10
        if 11 <= n100 <= 19:
            return f5
        if n10 == 1:
            return f1
        if 2 <= n10 <= 4:
            return f2
        return f5

    parts = []
    millions = n // 1000000
    if millions > 0:
        parts.append(triplet(millions, is_female=False))
        parts.append(plural_form(millions, "миллион", "миллиона", "миллионов"))
        n %= 1000000

    thousands = n // 1000
    if thousands > 0:
        parts.append(triplet(thousands, is_female=True))
        parts.append(plural_form(thousands, "тысяча", "тысячи", "тысяч"))
        n %= 1000

    if n > 0 or not parts:
        parts.append(triplet(n, is_female=False))

    return " ".join([p for p in parts if p]).strip()

def _plural(n: int, f1: str, f2: str, f5: str) -> str:
    n100, n10 = n % 100, n % 10
    if 11 <= n100 <= 19:
        return f5
    if n10 == 1:
        return f1
    if 2 <= n10 <= 4:
        return f2
    return f5


def _int_to_words(
    digits: str,
    feminine: bool = False,
    preserve_leading_zeros: bool = True,
) -> str:
    """Целое число словами; длинные числа и ведущие нули читаются по цифрам."""
    if len(digits) > 9 or (preserve_leading_zeros and len(digits) > 1 and digits.startswith("0")):
        return " ".join(num_to_ru_words(int(d)) for d in digits)
    words = num_to_ru_words(int(digits))
    if feminine:
        # «один» -> «одна», «два» -> «две» только на конце числа (3 -> «три», 21 -> «двадцать одна»)
        words = re.sub(r"\bодин$", "одна", words)
        words = re.sub(r"\bдва$", "две", words)
    return words


def _legacy_digits(text: str, preserve_leading_zeros: bool = False) -> str:
    """Прежняя обработка отдельных групп цифр; ведущие нули сохраняются только в новом общем пути."""
    def replace(match):
        # Не менять прежнее чтение компонентов дат/времени и точечных групп.
        adjacent_separator = (
            (match.start() > 0 and text[match.start() - 1] in ".:")
            or (match.end() < len(text) and text[match.end()] in ".:")
        )
        keep_zeros = preserve_leading_zeros and not adjacent_separator
        return _int_to_words(match.group(0), preserve_leading_zeros=keep_zeros)

    return re.sub(r'(?<![A-Za-z0-9_])\d+(?![A-Za-z0-9_])', replace, text)


_FRACTION_UNITS = {1: ("десятая", "десятые", "десятых"),
                   2: ("сотая", "сотые", "сотых"),
                   3: ("тысячная", "тысячные", "тысячных")}


def _decimal_to_words(whole: str, frac: str) -> str:
    """3.5 -> «три целых пять десятых». Больше трёх знаков после запятой — по цифрам."""
    if len(frac) > 3 or len(whole) > 9:
        return f"{_int_to_words(whole)} запятая {' '.join(num_to_ru_words(int(d)) for d in frac)}"
    w = int(whole)
    whole_part = _int_to_words(whole, feminine=True)
    whole_unit = "целая" if (w % 10 == 1 and w % 100 != 11) else "целых"
    f = int(frac)
    unit = _plural(f, *_FRACTION_UNITS[len(frac)])
    return f"{whole_part} {whole_unit} {_int_to_words(str(f), feminine=True)} {unit}"


# Телефоны и даты не входят в нормализацию: их цифровые группы читаются как раньше.
_PHONE = re.compile(
    r"(?<![\w.,:])(?:"
    r"\+?[78][ \-]?\(?\d{3}\)?[ \-]?\d{3}[ \-]?\d{2}[ \-]?\d{2}"
    r"|\+\d[\d ()\-]{7,}\d"
    r")(?!\w)"
)
_DATE = re.compile(r"(?<![\w.,:])\d{1,2}[./]\d{1,2}[./]\d{2,4}(?!\w)")

# Граница после числового фрагмента такая же, как у прежнего правила: не буква ASCII, не цифра, не «_».
_END = r"(?![A-Za-z0-9_])"
_SPECIAL_NUMBER = re.compile(
    r"(?<![\w.,:+])(?:"
    r"(?P<time>(?:[01]?\d|2[0-3]):[0-5]\d)" + _END +
    r"|(?P<group>\d{1,3}(?:[ \u00a0]\d{3})+)(?![.,]\d)" + _END +
    r"|(?P<dec>\d+[.,]\d+)(?![.,]\d)(?:(?P<pct>%)" + _END + r"|" + _END + r")"
    r"|(?P<int>\d+)(?P<pct2>%)" + _END +
    r")"
)

# Только явные окончания порядковых числительных. Не скрываем, например,
# «10-минутный» или «2024-году»: для них сохраняется прежняя обработка числа.
_ORDINAL = re.compile(r"(?<![\w.,:])\d+-(?:й|я|е|го|му|м|х|ым|ом|ой|ей|ю|ью)(?![^\W\d_])")


def _replace_special(m: "re.Match") -> str:
    if m.group("time"):
        h, mi = m.group("time").split(":")
        if mi == "00":
            minutes = "ноль ноль"
        elif mi.startswith("0"):
            minutes = "ноль " + num_to_ru_words(int(mi))
        else:
            minutes = num_to_ru_words(int(mi))
        return f"{num_to_ru_words(int(h))} {minutes}"
    if m.group("group"):
        return _int_to_words(re.sub(r"\D", "", m.group("group")))
    if m.group("dec"):
        whole, frac = re.split(r"[.,]", m.group("dec"))
        text = _decimal_to_words(whole, frac)
        return text + " процента" if m.group("pct") else text
    n = m.group("int")
    words = _int_to_words(n)
    if len(n) <= 9:
        return f"{words} {_plural(int(n), 'процент', 'процента', 'процентов')}"
    return f"{words} процентов"


def sanitize_text(text: str) -> str:
    text = re.sub(r'https?://\S+|www\.\S+', 'ссылка', text)
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)

    # Телефоны и даты: прежняя пошаговая обработка цифровых групп, без новых правил.
    text = _PHONE.sub(lambda m: _legacy_digits(m.group(0)), text)
    text = _DATE.sub(lambda m: _legacy_digits(m.group(0)), text)

    # Порядковые (1-й, 5-го) оставляем как есть: правильное склонение зависит от падежа и рода.
    # Прячем их за маркерами из Private Use Area (их в исходном тексте предварительно удаляем).
    text = re.sub("[\uE000-\uF8FF]", "", text)
    ordinals: list = []

    def _hide(m):
        ordinals.append(m.group(0))
        return chr(0xE000 + len(ordinals) - 1)

    text = _ORDINAL.sub(_hide, text)
    text = _SPECIAL_NUMBER.sub(_replace_special, text)
    text = _legacy_digits(text, preserve_leading_zeros=True)
    text = re.sub("[\uE000-\uF8FF]", lambda m: ordinals[ord(m.group(0)) - 0xE000], text)
    text = re.sub(r'([.!?])\1{2,}', r'\1\1', text)
    return text.strip()

def sanitize_overlay_text(text: str) -> str:
    return re.sub(r'https?://\S+|www\.\S+', 'ссылка', str(text))

def has_speakable_content(text: str) -> bool:
    cleaned = re.sub(r'[\u200B\u200D\uFE0F\u20E3]', '', sanitize_text(text))
    return any(char.isalnum() for char in cleaned)
