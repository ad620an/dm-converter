# -*- coding: utf-8 -*-
"""Экспорт декодированных данных в TXT и CSV (ТЗ §24-25).

Режимы представления управляющих символов:
- "original" — в файле остаётся настоящий ASCII 29 (0x1D);
- "readable" — ASCII 29 заменяется на <GS> (только для удобства просмотра).
"""
import csv
import io
from typing import Dict, List

from .core.display import to_display


def _apply_gs_mode(data: bytes, gs_mode: str) -> bytes:
    if gs_mode == "readable":
        return to_display(data).encode("utf-8")
    return data  # original: байты без изменений, 0x1D остаётся 0x1D


def export_txt(rows: List[Dict], gs_mode: str = "original") -> bytes:
    """TXT: один DataMatrix на строку, 0x1D внутри строки сохраняется (§24).

    Перенос строки — исключительно разделитель между кодами.
    """
    lines = [_apply_gs_mode(row["data"], gs_mode) for row in rows]
    if not lines:
        return b""
    return b"\n".join(lines) + b"\n"


def export_csv(rows: List[Dict], gs_mode: str = "original",
               filename: str = "", include_status: bool = True) -> bytes:
    """CSV: №; Страница; Код; GTIN (+ Файл, Статус). 0x1D сохраняется в поле."""
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    header = ["№", "Страница", "Код", "GTIN"]
    if filename:
        header.append("Файл")
    if include_status:
        header.append("Статус")
    writer.writerow(header)
    for i, row in enumerate(rows, start=1):
        code_str = _apply_gs_mode(row["data"], gs_mode).decode("utf-8")
        cells = [i, row.get("page", ""), code_str, row.get("gtin") or ""]
        if filename:
            cells.append(filename)
        if include_status:
            cells.append(row.get("status", ""))
        writer.writerow(cells)
    # BOM для корректного открытия в Excel; сами данные кода не затрагивает.
    return ("﻿" + buf.getvalue()).encode("utf-8")


def dedup_rows(rows: List[Dict]) -> List[Dict]:
    """Исключает дубликаты по точному совпадению байтов (§21)."""
    seen = set()
    out: List[Dict] = []
    for row in rows:
        key = row["data"]
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out