# -*- coding: utf-8 -*-
"""Разбор GS1-структуры кодов «Честного знака»: GTIN, серийный номер, криптохвост.

Реализация по ТЗ §14: GTIN извлекается по разметке GS1 (AI 01), а не как
«первые 14 символов любой строки».
"""
import re
from typing import Dict, List, Optional

GS = b"\x1d"  # ASCII 29, Group Separator

# Application Identifiers с фиксированной длиной (значение + AI, в символах).
FIXED_LENGTH_AIS = {
    "00": 18,  # SSCC
    "01": 14,  # GTIN
    "02": 14,  # GTIN содержимого
    "11": 6,   # дата производства
    "12": 6,   # дата срока годности
    "13": 6,   # дата упаковки
    "15": 6,   # дата минимального срока годности
    "17": 6,   # дата окончания срока годности
    "20": 2,   # вариант
}

# Переменные AI, встречающиеся в кодах «Честного знака».
VARIABLE_AIS = ["10", "21", "22", "240", "241", "91", "92", "93", "94", "95", "96", "97", "98", "99"]

# Префикс символьного идентификатора для DataMatrix (ECM/AIM: ]d2), может
# возвращаться некоторыми сканерами/библиотеками — при разборе отбрасываем.
SYMBOLOGY_PREFIXES = (b"]d2", b"]Q3", b"]C1")


def _strip_symbology_prefix(data: bytes) -> bytes:
    for p in SYMBOLOGY_PREFIXES:
        if data.startswith(p):
            return data[len(p):]
    return data


def parse_ais(data: bytes) -> List[tuple]:
    """Разбирает последовательность GS1 на список (ai, value).

    Понимает фиксированные AI (следующий AI идёт вплотную) и переменные AI
    (значение до разделителя GS). Незнакомые AI пропускает максимально
    консервативно: фиксируем позицию и прекращаем строгий разбор.
    """
    raw = _strip_symbology_prefix(data)
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    out: List[tuple] = []
    pos = 0
    while pos < len(text):
        matched = False
        for ai_len in (2, 3):
            ai = text[pos:pos + ai_len]
            if ai in FIXED_LENGTH_AIS:
                value = text[pos + ai_len:pos + ai_len + FIXED_LENGTH_AIS[ai]]
                if len(value) < FIXED_LENGTH_AIS[ai]:
                    out.append((ai, value))
                    pos = len(text)
                    matched = True
                    break
                out.append((ai, value))
                pos += ai_len + FIXED_LENGTH_AIS[ai]
                matched = True
                break
            if ai in VARIABLE_AIS:
                gs = text.find("\x1d", pos + ai_len)
                value = text[pos + ai_len:] if gs == -1 else text[pos + ai_len:gs]
                out.append((ai, value))
                pos = len(text) if gs == -1 else gs + 1
                matched = True
                break
        if not matched:
            # AI не распознан — дальнейший строгий разбор невозможен.
            out.append(("", text[pos:]))
            break
    return out


def extract_gtin(data: bytes) -> Optional[str]:
    """Извлекает GTIN-14 из кода маркировки по разметке GS1 (AI 01).

    Возвращает 14-символьную строку (с ведущими нулями) или None.
    Fallback: если строгий разбор не нашёл AI 01, ищем шаблон
    «01» + 14 цифр в начале последовательности.
    """
    raw = _strip_symbology_prefix(data)
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        return None

    for ai, value in parse_ais(raw):
        if ai == "01" and len(value) == 14 and value.isdigit():
            return value

    m = re.match(r"^01(\d{14})", text)
    return m.group(1) if m else None


def code_details(data: bytes) -> Dict:
    """Расширенная информация о коде для панели деталей (ТЗ §23).

    Дополнительные поля не заменяют исходную строку — она хранится отдельно.
    """
    raw = _strip_symbology_prefix(data)
    ais = parse_ais(raw)
    details: Dict = {
        "gtin": extract_gtin(raw),
        "length": len(raw),
        "gs_positions": [i for i, b in enumerate(raw) if b == 0x1D],
        "ai_pairs": [{"ai": ai, "value": value} for ai, value in ais if ai],
        "ai01": None,
        "serial": None,
        "crypto_tail": None,
    }
    crypto_parts: List[str] = []
    for ai, value in ais:
        if ai == "01" and details["ai01"] is None:
            details["ai01"] = value
        elif ai == "21" and details["serial"] is None:
            details["serial"] = value
        elif ai in ("91", "92", "93"):
            crypto_parts.append(value)
    if crypto_parts:
        # Криптохвост может состоять из нескольких AI (91, 92, ...),
        # разделённых GS — в деталях показываем их через обозначение <GS>.
        details["crypto_tail"] = "<GS>".join(crypto_parts)
    return details