# -*- coding: utf-8 -*-
"""Общий conftest: доступ к пакету app и тестовые данные «Честного знака»."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GS = b"\x1d"  # ASCII 29, Group Separator

# Эталонные тестовые последовательности (ТЗ §42).
CHZ_CODE = (
    b"010460123456789021ABCDEF123456" + GS + b"910123" + GS
    + b"92ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
)
CHZ_CODE_2 = b"010460123456789021123456789012" + GS + b"910001" + GS + b"92TEST"
PLAIN_CODE = b"010460123456789021ABCDEF"  # код без GS

# Все строки для round-trip-проверок.
ROUNDTRIP_CASES = [
    b"ABC" + GS + b"DEF",                 # §34: 41 42 43 1D 44 45 46
    b"ABCDEF",                            # §35-1: обычная строка
    PLAIN_CODE,
    CHZ_CODE,
    CHZ_CODE_2,
    GS + b"01" + GS + b"92" + GS + b"93", # §35-3: несколько GS, в т.ч. в начале
    b"0104601234567890",                  # GTIN с ведущим нулём
]


def pytest_configure(config):
    # Чтобы pytest не путал тесты backend с чем-то ещё.
    config.addinivalue_line("markers", "e2e: интеграционные round-trip тесты")