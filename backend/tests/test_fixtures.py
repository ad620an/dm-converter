# -*- coding: utf-8 -*-
"""Тесты на эталонных файлах из tests/fixtures (ТЗ §25, §46).

Фикстуры генерируются tests/make_fixtures.py; если их нет — создаются
автоматически при первом запуске.
"""
import os
import subprocess
import sys

import pytest

from app.core import parsers

from conftest import CHZ_CODE, GS

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


@pytest.fixture(scope="module", autouse=True)
def _ensure_fixtures():
    if not os.path.isdir(FIXTURES) or not os.listdir(FIXTURES):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "make_fixtures.py")
        subprocess.run([sys.executable, script], check=True)


def _read(name):
    path = os.path.join(FIXTURES, name)
    if not os.path.exists(path):
        pytest.skip(f"фикстура {name} не создана")
    with open(path, "rb") as f:
        return f.read()


def _rows_from_file(filename):
    parsed = parsers.parse_file(filename, _read(filename))
    mapping = parsers.guess_column_mapping(parsed)
    assert mapping is not None and mapping["code"] is not None
    return parsed, parsers.apply_mapping(parsed, mapping)


def test_fixture_txt_gs_preserved():
    """Эталонный TXT с настоящим 0x1D импортируется без потерь."""
    parsed, rows = _rows_from_file("codes_gs.txt")
    assert len(rows) == 4
    assert rows[0]["code"].encode("utf-8") == CHZ_CODE
    assert rows[3]["code"].encode("utf-8") == b"ABC" + GS + b"DEF"


def test_fixture_txt_tab_mapping():
    """Таб-TXT: код/артикул/количество сопоставляются автоматически."""
    parsed, rows = _rows_from_file("codes_tab.txt")
    assert rows[0]["article"] == "ABC-001"
    assert rows[0]["quantity"] == "5"
    assert rows[2]["quantity"] == "15"
    assert "\x1d" in rows[0]["code"]


def test_fixture_csv_gs_preserved():
    """Эталонный CSV с 0x1D в quoted-полях."""
    parsed, rows = _rows_from_file("codes_gs.csv")
    assert rows[0]["code"].encode("utf-8") == CHZ_CODE
    assert rows[1]["article"] == "ABC-002"
    assert "\x1d" in rows[0]["code"]


def test_fixture_xlsx_plain_and_gtin():
    """Эталонный XLSX: коды без GS + GTIN с ведущим нулём как текст."""
    parsed, rows = _rows_from_file("codes.xlsx")
    assert rows[-1]["code"] == "04601234567890"  # ведущий ноль сохранён
    assert all("\x1d" not in r["code"] for r in rows)  # XML не хранит GS