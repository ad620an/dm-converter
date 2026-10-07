# -*- coding: utf-8 -*-
"""Генерация эталонных тестовых файлов TXT/CSV/XLSX (ТЗ §25, §46).

Запуск:  python tests/make_fixtures.py

Файлы создаются в tests/fixtures/ и используются тестами (test_fixtures.py).
TXT/CSV содержат НАСТОЯЩИЙ байт 0x1D — это главный тестовый артефакт проекта.
"""
import io
import os
import sys

GS = b"\x1d"

CODES = [
    b"010460123456789021ABCDEF123456" + GS + b"910123" + GS
    + b"92ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890",
    b"010460123456789021123456789012" + GS + b"910001" + GS + b"92TEST",
    b"010460123456789021XYZ789",
    b"ABC" + GS + b"DEF",
]

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def make_txt(path):
    lines = [c + b"\n" for c in CODES]
    with open(path, "wb") as f:
        f.writelines(lines)


def make_txt_tab(path):
    lines = [b"code\tarticle\tqty\n"]
    for i, c in enumerate(CODES):
        lines.append(c + b"\tABC-%03d\t%d\n" % (i + 1, (i + 1) * 5))
    with open(path, "wb") as f:
        f.writelines(lines)


def make_csv(path):
    lines = [b"code;article;qty\n"]
    for i, c in enumerate(CODES):
        lines.append(b'"' + c + b'";"ABC-%03d";"%d"\n' % (i + 1, (i + 1) * 5))
    with open(path, "wb") as f:
        f.writelines(lines)


def make_xlsx(path):
    # В XLSX нельзя хранить управляющие символы (XML 1.0) — коды без GS.
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Код", "Артикул", "Количество"])
    plain = [c for c in CODES if GS not in c]
    for i, c in enumerate(plain):
        ws.append([c.decode("ascii"), f"ABC-{i + 1:03d}", (i + 1) * 5])
    ws.append(["04601234567890", "GTIN-текст", 1])  # GTIN с ведущим нулём
    wb.save(path)


def main():
    os.makedirs(FIXTURES, exist_ok=True)
    make_txt(os.path.join(FIXTURES, "codes_gs.txt"))
    make_txt_tab(os.path.join(FIXTURES, "codes_tab.txt"))
    make_csv(os.path.join(FIXTURES, "codes_gs.csv"))
    make_xlsx(os.path.join(FIXTURES, "codes.xlsx"))
    print("Тестовые файлы созданы в", FIXTURES)
    for name in sorted(os.listdir(FIXTURES)):
        print(" -", name)


if __name__ == "__main__":
    sys.exit(main())