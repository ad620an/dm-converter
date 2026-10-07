# -*- coding: utf-8 -*-
"""Тесты 1-3 из ТЗ §35: побайтовый round-trip encode -> DataMatrix -> decode.

Главный инвариант проекта (ТЗ §45):
    source bytes === decoded bytes, в частности 0x1D === 0x1D.
"""
from app.core.dm import decode_dm, encode_dm

from conftest import GS, ROUNDTRIP_CASES, CHZ_CODE


def _roundtrip(data: bytes) -> bytes:
    img, size, modules = encode_dm(data)
    found = decode_dm(img)
    assert found, f"decode ничего не нашёл (size={size})"
    return found[0]


def test_plain_string_roundtrip():
    """Тест §35-1: обычная строка совпадает после encode/decode."""
    src = b"010460123456789021ABCDEF"
    assert _roundtrip(src) == src


def test_gs_roundtrip_byte_for_byte():
    """Тест §35-2 / §34: ABC + 0x1D + DEF — побайтовое совпадение 41 42 43 1D 44 45 46."""
    src = b"ABC" + GS + b"DEF"
    out = _roundtrip(src)
    assert out == src
    assert out == bytes([0x41, 0x42, 0x43, 0x1D, 0x44, 0x45, 0x46])


def test_multiple_gs_positions_preserved():
    """Тест §35-3: несколько 0x1D — количество и позиции совпадают."""
    src = b"010460123456789021ABCDEF" + GS + b"910123" + GS + b"92ABCDEFG"
    out = _roundtrip(src)
    assert out == src
    assert out.count(GS) == 2
    assert out.index(GS) == src.index(GS)
    assert [i for i, b in enumerate(out) if b == 0x1D] == [
        i for i, b in enumerate(src) if b == 0x1D
    ]


def test_real_chz_code_roundtrip():
    """Тест §42: эталонная строка ЧЗ с GS проходит полный цикл без потерь."""
    out = _roundtrip(CHZ_CODE)
    assert out == CHZ_CODE
    assert len(out) == len(CHZ_CODE)


def test_length_and_bytes_equal():
    """Тест §35 (инвариант): length(original) == length(decoded) и байты равны."""
    for src in ROUNDTRIP_CASES:
        out = _roundtrip(src)
        assert len(out) == len(src), f"длина изменилась: {src!r}"
        assert out == src, f"байты изменились: {src!r}"


def test_gs_not_replaced_by_text():
    """0x1D не превращается в '?', ' ', '~', '[GS]' или '<GS>'."""
    out = _roundtrip(b"ABC" + GS + b"DEF")
    assert GS in out
    assert b"?" not in out
    assert b"[GS]" not in out
    assert b"<GS>" not in out
    assert b"~" not in out