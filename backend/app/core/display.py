# -*- coding: utf-8 -*-
"""Визуализация бинарных данных для UI и HEX-утилиты (ТЗ §9, §15, §37).

Главный принцип (ТЗ §40): исходные данные (rawBytes) — единственный источник
истины; всё здесь — только представления для отображения.
"""
import base64
import binascii
from typing import Optional

# Человекочитаемые обозначения управляющих символов, встречающихся в кодах
# маркировки. Только для UI — в данных всегда остаётся исходный байт.
CONTROL_CHAR_NAMES = {
    0x1D: "<GS>",  # ASCII 29, Group Separator — обязателен по ТЗ
    0x1E: "<RS>",  # Record Separator
    0x04: "<EOT>",  # End of Transmission (встречается в крипто-хвостах)
    0x00: "<NUL>",
    0x01: "<SOH>",
    0x02: "<STX>",
    0x03: "<ETX>",
    0x05: "<ENQ>",
    0x06: "<ACK>",
    0x07: "<BEL>",
    0x08: "<BS>",
    0x09: "<TAB>",
    0x0B: "<VT>",
    0x0C: "<FF>",
    0x0D: "<CR>",
    0x0E: "<SO>",
    0x0F: "<SI>",
    0x10: "<DLE>",
    0x11: "<DC1>",
    0x12: "<DC2>",
    0x13: "<DC3>",
    0x14: "<DC4>",
    0x15: "<NAK>",
    0x16: "<SYN>",
    0x17: "<ETB>",
    0x18: "<CAN>",
    0x19: "<EM>",
    0x1A: "<SUB>",
    0x1B: "<ESC>",
    0x1C: "<FS>",
    0x1F: "<US>",
}


def bytes_to_b64(data: bytes) -> str:
    """Кодирует bytes в base64 — бинарно-безопасный формат передачи в JSON."""
    return base64.b64encode(data).decode("ascii")


def b64_to_bytes(b64: str) -> bytes:
    try:
        return base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("Некорректные base64-данные")


def to_display(data: bytes) -> str:
    """Строка для отображения пользователю: 0x1D -> <GS> и т.д.

    Только представление: байты в rawBytes не изменяются.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    return "".join(CONTROL_CHAR_NAMES.get(ord(ch), ch) for ch in text)


def first_n_display(data: bytes, n: int) -> str:
    """Первые n символов ИСХОДНОЙ последовательности, затем визуализация.

    ТЗ §15: сначала берутся символы исходной последовательности, и только
    потом управляющие символы заменяются обозначениями — визуализированная
    строка может стать длиннее n.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    return to_display(text[:n].encode("utf-8"))


def hex_dump(data: bytes) -> str:
    """HEX-представление для отладки: ABC<GS>DEF -> 41 42 43 1D 44 45 46 (§37)."""
    return " ".join(f"{b:02X}" for b in data)


def contains_gs(data: bytes) -> bool:
    return b"\x1d" in data


def find_gs_positions(data: bytes) -> Optional[str]:
    """Позиции всех 0x1D в виде строки '5,13,22' (для панели деталей)."""
    return ",".join(str(i) for i, b in enumerate(data) if b == 0x1D) or None