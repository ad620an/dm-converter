# -*- coding: utf-8 -*-
"""Тесты GS1-разбора: GTIN по разметке AI 01 (ТЗ §14), детали кода (§23)."""
from app.core.display import first_n_display, to_display
from app.core.gs1 import code_details, extract_gtin, parse_ais

from conftest import CHZ_CODE, GS, PLAIN_CODE


def test_gtin_extracted_from_ai01():
    """§14: GTIN извлекается по разметке GS1 (AI 01), 14 символов, ведущий ноль на месте."""
    gtin = extract_gtin(CHZ_CODE)
    assert gtin == "04601234567890"
    assert isinstance(gtin, str)
    assert gtin.startswith("0")


def test_gtin_is_string_not_number():
    """§14: GTIN хранится как строка, не как число (критично для Excel/CSV)."""
    gtin = extract_gtin(CHZ_CODE)
    assert not isinstance(gtin, int)
    assert len(gtin) == 14 and gtin.isdigit()


def test_gtin_fallback_pattern():
    """Fallback: строка начинается с 01 + 14 цифр, но строгий разбор не справился."""
    assert extract_gtin(b"0104601234567890") == "04601234567890"


def test_no_gtin_returns_none():
    """При невозможности определить GTIN — None, а не неверное значение."""
    assert extract_gtin(b"21ABCDEF") is None
    assert extract_gtin(b"") is None


def test_symbology_prefix_stripped():
    """Префикс ]d2 от сканеров не мешает разбору."""
    assert extract_gtin(b"]d2" + CHZ_CODE) == "04601234567890"


def test_parse_ais_structure():
    """§30: разбор 01/21/91/92 с учётом GS-разделителей."""
    ais = parse_ais(CHZ_CODE)
    pairs = dict(ais)
    assert pairs["01"] == "04601234567890"
    assert pairs["21"] == "ABCDEF123456"
    assert pairs["91"] == "0123"
    assert pairs["92"] == "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"


def test_code_details():
    details = code_details(CHZ_CODE)
    assert details["gtin"] == "04601234567890"
    assert details["serial"] == "ABCDEF123456"
    assert details["length"] == len(CHZ_CODE)
    assert details["gs_positions"] == [30, 37]


def test_first_38_display_counts_source_symbols():
    """§15: «первые 38 знаков» — по исходной последовательности, GS = 1 символ."""
    src = CHZ_CODE
    assert len(src) >= 38
    shown = first_n_display(src, 38)
    # 38 исходных символов охватывают GS на позициях 30 и 37 → два <GS> на экране.
    assert shown.count("<GS>") == 2
    assert shown.startswith("010460123456789021ABCDEF123456<GS>91")


def test_display_does_not_touch_source():
    """§40: визуализация не изменяет исходные байты."""
    src = b"ABC" + GS + b"DEF"
    assert to_display(src) == "ABC<GS>DEF"
    assert src == b"ABC\x1dDEF"  # байты не изменились


def test_plain_code_gtin():
    assert extract_gtin(PLAIN_CODE) == "04601234567890"