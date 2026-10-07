# -*- coding: utf-8 -*-
"""Тесты вкладки «Нанесение»: CSV (код + количество) -> код + 0x1D + 30 + количество."""
import pytest

from app.core import apply as apply_core

from conftest import CHZ_CODE, CHZ_CODE_2, PLAIN_CODE, GS


def _csv(*lines: str) -> bytes:
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_parse_csv_two_columns_with_header():
    raw = _csv(
        "Полный код;Количество",
        CHZ_CODE.decode("utf-8") + ";5",
        PLAIN_CODE.decode("utf-8") + ";100",
    )
    parsed = apply_core.parse_apply_file("codes.csv", raw)
    assert parsed["header"] == ["Полный код", "Количество"]
    rows = apply_core.prepare_rows(parsed)
    assert len(rows) == 2
    assert all(r["status"] == "ok" for r in rows)
    # GS сохранился в исходном коде
    assert rows[0]["hasGS"] is True
    assert "<GS>" in rows[0]["codeDisplay"]


def test_sequence_is_code_plus_gs_plus_30_plus_quantity():
    raw = _csv(CHZ_CODE_2.decode("utf-8") + ";12")
    rows = apply_core.prepare_rows(apply_core.parse_apply_file("c.csv", raw))
    expected = CHZ_CODE_2.decode("utf-8") + "\x1d30" + "12"
    assert rows[0]["sequence"] == expected
    assert rows[0]["sequenceDisplay"] == expected.replace("\x1d", "<GS>")


def _data_lines(out: bytes):
    """Строки выходного CSV без BOM и CRLF-хвостов, в байтах."""
    return [ln.strip(b"\r") for ln in out.replace(b"\xef\xbb\xbf", b"").split(b"\n") if ln]


def test_export_csv_contains_raw_0x1d():
    raw = _csv(
        "код;количество",
        CHZ_CODE.decode("utf-8") + ";7",
        PLAIN_CODE.decode("utf-8") + ";1",
    )
    rows = apply_core.prepare_rows(apply_core.parse_apply_file("c.csv", raw))
    out = apply_core.export_apply_csv(rows)
    line1, line2 = _data_lines(out)
    assert line1 == CHZ_CODE + GS + b"30" + b"7"
    assert line2 == PLAIN_CODE + GS + b"30" + b"1"


def test_export_without_header_row():
    raw = _csv(CHZ_CODE.decode("utf-8") + ";5")
    rows = apply_core.prepare_rows(apply_core.parse_apply_file("c.csv", raw))
    out = apply_core.export_apply_csv(rows)
    assert _data_lines(out) == [CHZ_CODE + GS + b"30" + b"5"]


def test_invalid_quantity_blocks_export():
    raw = _csv(CHZ_CODE.decode("utf-8") + ";5 шт")
    rows = apply_core.prepare_rows(apply_core.parse_apply_file("c.csv", raw))
    assert rows[0]["status"] == "error"
    assert "некорректное количество" in rows[0]["error"]
    with pytest.raises(apply_core.ApplyError):
        apply_core.export_apply_csv(rows)


def test_zero_and_too_long_quantity_are_errors():
    raw = _csv(
        CHZ_CODE.decode("utf-8") + ";0",
        CHZ_CODE.decode("utf-8") + ";123456789",
    )
    rows = apply_core.prepare_rows(apply_core.parse_apply_file("c.csv", raw))
    assert "ожидается целое положительное" in rows[0]["error"]
    assert "более 8 цифр" in rows[1]["error"]


def test_empty_code_is_error():
    raw = _csv(";5")
    rows = apply_core.prepare_rows(apply_core.parse_apply_file("c.csv", raw))
    assert rows[0]["status"] == "error"
    assert "Пустой код" in rows[0]["error"]


def test_quantity_spaces_are_stripped():
    raw = _csv(PLAIN_CODE.decode("utf-8") + "; 3 ")
    rows = apply_core.prepare_rows(apply_core.parse_apply_file("c.csv", raw))
    assert rows[0]["status"] == "ok"
    assert rows[0]["sequence"] == PLAIN_CODE.decode("utf-8") + "\x1d30" + "3"


def test_wrong_column_count_rejected():
    raw = _csv(PLAIN_CODE.decode("utf-8") + ";5;лишнее")
    with pytest.raises(apply_core.ApplyError, match="ровно две"):
        apply_core.parse_apply_file("c.csv", raw)


def test_non_csv_rejected():
    with pytest.raises(apply_core.ApplyError, match="CSV"):
        apply_core.parse_apply_file("codes.txt", b"abc;5")


def test_more_than_max_rows_rejected():
    line = PLAIN_CODE.decode("utf-8") + ";5"
    raw = _csv(*([line] * 1001))
    with pytest.raises(Exception, match="Максимально"):
        apply_core.parse_apply_file("c.csv", raw)