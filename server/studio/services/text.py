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

def sanitize_text(text: str) -> str:
    text = re.sub(r'https?://\S+|www\.\S+', 'ссылка', text)
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    
    def replace_isolated_digits(match):
        val_str = match.group(0)
        try:
            if len(val_str) > 9:
                return " ".join(num_to_ru_words(int(d)) for d in val_str)
            return num_to_ru_words(int(val_str))
        except (ValueError, IndexError, OverflowError):
            return val_str

    text = re.sub(r'(?<![A-Za-z0-9_])\d+(?![A-Za-z0-9_])', replace_isolated_digits, text)
    text = re.sub(r'([.!?])\1{2,}', r'\1\1', text)
    return text.strip()

def sanitize_overlay_text(text: str) -> str:
    return re.sub(r'https?://\S+|www\.\S+', 'ссылка', str(text))

def has_speakable_content(text: str) -> bool:
    cleaned = re.sub(r'[\u200B\u200D\uFE0F\u20E3]', '', sanitize_text(text))
    return any(char.isalnum() for char in cleaned)

