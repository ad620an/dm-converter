# -*- coding: utf-8 -*-
"""Тесты 4, 6, 7 из ТЗ §35: импорт TXT/CSV/XLSX с сохранением 0x1D и лимит строк."""
import io

import pytest
from openpyxl import Workbook

from app.core import parsers

from conftest import CHZ_CODE, GS


def _apply(parsed, code):
    mapping = parsers.guess_column_mapping(parsed)
    assert mapping is not None and mapping["code"] is not None
    return parsers.apply_mapping(parsed, mapping)


# ---------------------------------------------------------------- TXT

def test_txt_import_preserves_gs():
    """Тест §35-6: после импорта TXT значение побайтово совпадает с файлом."""
    raw = CHZ_CODE + b"\n" + b"ABC" + GS + b"DEF\n"
    parsed = parsers.parse_file("codes.txt", raw)
    rows = _apply(parsed, "код")
    assert rows[0]["code"].encode("utf-8") == CHZ_CODE
    assert rows[1]["code"].encode("utf-8") == b"ABC" + GS + b"DEF"


def test_txt_no_trim_of_control_chars():
    """§6: преждевременный trim() и очистка управляющих символов запрещены."""
    raw = b"ABC" + GS + b"DEF \n"          # пробел в конце — часть значения
    parsed = parsers.parse_txt(raw)
    assert parsed["rows"][0][0] == "ABC\x1dDEF "


def test_txt_tab_variant_with_article_quantity():
    """Вариант Б §6: Код<TAB>Артикул<TAB>Количество с GS внутри кода."""
    raw = (
        b"\xd0\x9a\xd0\xbe\xd0\xb4\t\xd0\x90\xd1\x80\xd1\x82\xd0\xb8\xd0\xba\xd1\x83\xd0\xbb\t\xd0\x9a\xd0\xbe\xd0\xbb\xd0\xb8\xd1\x87\xd0\xb5\xd1\x81\xd1\x82\xd0\xb2\xd0\xbe\n"
        + CHZ_CODE + b"\tABC-001\t5\n"
        + b"010460123456789021XY" + GS + b"91ZZ\tABC-002\t10\n"
    )
    parsed = parsers.parse_file("codes.txt", raw)
    assert parsed["header"] is not None
    rows = _apply(parsed, "код")
    assert rows[0]["code"].encode("utf-8") == CHZ_CODE
    assert rows[0]["article"] == "ABC-001"
    assert rows[0]["quantity"] == "5"
    assert rows[1]["quantity"] == "10"


def test_txt_utf8_bom():
    """UTF-8 BOM корректно распознаётся и не попадает в первую строку."""
    raw = b"\xef\xbb\xbfABC" + GS + b"DEF\n"
    parsed = parsers.parse_txt(raw)
    assert parsed["encoding"] == "utf-8-sig"
    assert parsed["rows"][0][0] == "ABC\x1dDEF"


def test_txt_cp1251():
    """§7: Windows-1251 распознаётся автоматически."""
    raw = "АБВ".encode("cp1251") + GS + b"DEF\n"
    parsed = parsers.parse_txt(raw)
    assert parsed["encoding"] == "cp1251"
    assert parsed["rows"][0][0] == "АБВ\x1dDEF"


# ---------------------------------------------------------------- CSV

@pytest.mark.parametrize("delimiter", [";", ",", "\t"])
def test_csv_import_preserves_gs(delimiter):
    """Тест §35-7: CSV с любым разделителем сохраняет 0x1D (автоопределение)."""
    sep = {";": ";", ",": ",", "\t": "\t"}[delimiter]
    raw = (
        f"Код{sep}Артикул{sep}Количество\n".encode("utf-8")
        + CHZ_CODE + f"{sep}ABC-001{sep}5".encode("utf-8") + b"\n"
    )
    parsed = parsers.parse_file("codes.csv", raw)
    assert parsed["format"] == "csv"
    rows = _apply(parsed, "код")
    assert rows[0]["code"].encode("utf-8") == CHZ_CODE
    assert rows[0]["article"] == "ABC-001"


def test_csv_quoted_fields():
    """Quoted fields разбираются корректно, GS внутри кавычек сохраняется."""
    code = b"010460123456789021AB" + GS + b"91X"
    raw = (
        "Код;Артикул\n".encode("utf-8")
        + b'"' + code + b'";"ABC, 001"\n'
    )
    parsed = parsers.parse_csv(raw)
    rows = _apply(parsed, "код")
    assert rows[0]["code"].encode("utf-8") == code
    assert rows[0]["article"] == "ABC, 001"


def test_csv_without_header_single_column():
    """CSV без заголовка: единственная колонка — код, GS сохраняется."""
    raw = CHZ_CODE + b"\n" + b"ABC" + GS + b"DEF\n"
    parsed = parsers.parse_file("codes.csv", raw)
    rows = _apply(parsed, "код")
    assert rows[0]["code"].encode("utf-8") == CHZ_CODE


# ---------------------------------------------------------------- XLSX
# Важно: сам формат XLSX (XML 1.0) физически не допускает управляющие символы
# вроде 0x1D внутри ячеек — Excel не может их хранить. Поэтому XLSX-тесты
# используют коды без GS; сохранение 0x1D покрывается TXT/CSV-тестами.

PLAIN = "010460123456789021ABCDEF"


def _make_xlsx(rows, header=True):
    wb = Workbook()
    ws = wb.active
    data = list(rows)
    if header:
        ws.append(["Код", "Артикул", "Количество"])
    for r in data:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_xlsx_import_keeps_leading_zero():
    """Тест §35-5 / §8: GTIN с ведущим нулём остаётся строкой '0460...'. """
    raw = _make_xlsx([["04601234567890", "ABC-001", "5"],
                      [PLAIN, "ABC-002", "10"]])
    parsed = parsers.parse_file("codes.xlsx", raw)
    rows = _apply(parsed, "код")
    assert rows[0]["code"] == "04601234567890"  # ведущий ноль сохранён
    assert rows[1]["code"] == PLAIN
    assert rows[0]["quantity"] == "5"


def test_xlsx_numeric_cell_not_scientific():
    """§8: числовая ячейка с количеством не превращается в '5.0' или экспоненту."""
    raw = _make_xlsx([[PLAIN, "A", 5]])
    parsed = parsers.parse_xlsx(raw)
    assert parsed["rows"][0][2] == "5"
    raw2 = _make_xlsx([[PLAIN, "A", 123456789012345]])
    parsed2 = parsers.parse_xlsx(raw2)
    assert "e+" not in parsed2["rows"][0][2].lower()


# ---------------------------------------------------------------- лимиты

def test_1000_rows_allowed():
    """Тест §35-4: 1000 строк импортируются без потерь."""
    lines = [b"010460123456789021ABCDEF%04d" % i for i in range(1000)]
    raw = b"\n".join(lines) + b"\n"
    parsed = parsers.parse_file("codes.txt", raw)
    assert len(parsed["rows"]) == 1000


def test_over_limit_rejected():
    """§29: при 1001 строке — понятная ошибка с текстом на русском."""
    lines = [b"010460123456789021ABCDEF%04d" % i for i in range(1001)]
    raw = b"\n".join(lines) + b"\n"
    with pytest.raises(parsers.ParseError) as e:
        parsers.parse_file("codes.txt", raw)
    assert "1000" in str(e.value)
    assert "1001" in str(e.value)


def test_unknown_format_error():
    with pytest.raises(parsers.ParseError):
        parsers.parse_file("codes.docx", b"xxx")