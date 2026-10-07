# -*- coding: utf-8 -*-
"""Тест 10 из ТЗ §35: экспорт TXT/CSV сохраняет 0x1D на исходной позиции."""
import csv
import io

from app.exporters import dedup_rows, export_csv, export_txt

from conftest import CHZ_CODE, GS


def _rows(*datas):
    return [{"data": d, "page": 1, "gtin": "04601234567890", "status": "ok"}
            for d in datas]


def test_export_txt_keeps_gs_byte():
    """Тест §35-10: повторное чтение TXT — 0x1D на исходной позиции."""
    content = export_txt(_rows(CHZ_CODE), gs_mode="original")
    assert GS in content
    lines = content.split(b"\n")
    assert lines[0] == CHZ_CODE
    assert [i for i, b in enumerate(lines[0]) if b == 0x1D] == [
        i for i, b in enumerate(CHZ_CODE) if b == 0x1D
    ]


def test_export_txt_readable_mode():
    """§25: режим readable — 0x1D заменён на <GS> (только для просмотра)."""
    content = export_txt(_rows(CHZ_CODE), gs_mode="readable")
    assert GS not in content
    assert b"<GS>" in content


def test_export_txt_newline_only_as_separator():
    """§24: перенос строки — исключительно разделитель между кодами."""
    content = export_txt(_rows(CHZ_CODE, b"ABC" + GS + b"DEF"))
    lines = content.rstrip(b"\n").split(b"\n")
    assert len(lines) == 2
    assert lines[0] == CHZ_CODE


def test_export_csv_keeps_gs_in_field():
    """§24: CSV корректно экранирует поля, 0x1D внутри поля сохраняется."""
    content = export_csv(_rows(CHZ_CODE), gs_mode="original")
    text = content.decode("utf-8-sig")  # BOM для Excel
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=";")
    rows = list(reader)
    assert rows[0] == ["№", "Страница", "Код", "GTIN", "Статус"]
    assert rows[1][2].encode("utf-8") == CHZ_CODE  # 0x1D внутри поля
    assert rows[1][3] == "04601234567890"


def test_export_csv_readable_mode():
    content = export_csv(_rows(CHZ_CODE), gs_mode="readable")
    text = content.decode("utf-8-sig")
    assert "\x1d" not in text
    assert "<GS>" in text


def test_export_csv_gtin_string_with_leading_zero():
    """Тест §35-5: GTIN с ведущим нулём экспортируется строкой, не числом."""
    content = export_csv(_rows(CHZ_CODE), gs_mode="original")
    text = content.decode("utf-8-sig")
    assert "04601234567890" in text


def test_dedup_rows():
    """§21: дубликаты исключаются только по желанию (dedup=True)."""
    rows = _rows(CHZ_CODE, b"ABC" + GS + b"DEF", CHZ_CODE)
    assert len(rows) == 3
    assert len(dedup_rows(rows)) == 2
    assert len(rows) == 3  # исходный список не изменён