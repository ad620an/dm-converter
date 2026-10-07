# -*- coding: utf-8 -*-
"""Вкладка «Нанесение»: CSV (код + количество) -> файл с последовательностями
для оборудования нанесения.

Формат входного CSV — две колонки:
- колонка 1: полный код маркировки, включая нечитаемые символы (0x1D и др.);
- колонка 2: количество.

Формат выходного CSV — одна колонка; каждая строка:
    <полный код> + GS (ASCII 29, байт 0x1D) + "30" + <количество>
Без пробелов и дополнительных знаков внутри последовательности.
«30» — Application Identifier (30) количества по GS1.
"""
import csv
import io
from typing import Dict, List

from . import parsers
from .display import to_display

# Признак количества в GS1: AI 30 (количество единиц), максимум 8 цифр.
QUANTITY_AI = "30"
QUANTITY_MAX_DIGITS = 8


class ApplyError(Exception):
    """Ошибка обработки файла «Нанесения» с сообщением на русском языке."""


def parse_apply_file(filename: str, raw: bytes) -> Dict:
    """Разбор CSV с двумя колонками: полный код и количество.

    Используется общий бинарно-безопасный импорт (0x1D сохраняется);
    структура проверяется: ровно две колонки.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext != "csv":
        raise ApplyError(
            "Для вкладки «Нанесение» нужен CSV-файл с двумя колонками: "
            "полный код (включая нечитаемые символы) и количество."
        )
    parsed = parsers.parse_file(filename, raw)
    ncols = max((len(r) for r in parsed["rows"]), default=0)
    if ncols != 2:
        raise ApplyError(
            f"В файле {ncols} колонок. Ожидается ровно две: "
            "полный код и количество."
        )
    return parsed


def _clean_quantity(value: str) -> str:
    """Убирает пробелы (включая неразрывный) и BOM — только цифры."""
    for ch in (" ", " ", "﻿"):
        value = value.replace(ch, "")
    return value.strip()


def _parse_quantity(value: str, index: int) -> str:
    """Количество: целое без пробелов, 1-8 цифр (ограничение AI 30)."""
    v = _clean_quantity(value)
    if not v.isdigit() or int(v) < 1:
        raise ApplyError(
            f"строка {index}: некорректное количество «{value.strip() or 'пусто'}» — "
            "ожидается целое положительное число"
        )
    if len(v) > QUANTITY_MAX_DIGITS:
        raise ApplyError(
            f"строка {index}: количество {v} содержит более "
            f"{QUANTITY_MAX_DIGITS} цифр (ограничение AI 30)"
        )
    return v


def prepare_rows(parsed: Dict) -> List[Dict]:
    """Строки для UI: код (исходный + display), количество, итоговая
    последовательность. Некорректные строки не прерывают обработку — их статус
    и причина возвращаются в полях status/error; файл формируется только когда
    ошибок нет."""
    rows_out: List[Dict] = []
    for r in parsed["rows"]:
        code = r[0] if len(r) > 0 else ""
        qty_raw = r[1] if len(r) > 1 else ""
        code_bytes = code.encode("utf-8")
        status, error, quantity, sequence = "ok", None, "", None
        if not code.strip():
            status, error = "error", "Пустой код маркировки"
        else:
            try:
                quantity = _parse_quantity(qty_raw, len(rows_out) + 1)
                # Итоговая последовательность: код + GS (ASCII 29) + AI 30 + количество.
                sequence = code + "\x1d" + QUANTITY_AI + quantity
            except ApplyError as e:
                status, error = "error", str(e)
        rows_out.append({
            "index": len(rows_out) + 1,
            "code": code,
            "codeDisplay": to_display(code_bytes),
            "hex": " ".join(f"{b:02X}" for b in code_bytes),
            "quantity": _clean_quantity(qty_raw) if status == "ok" else qty_raw.strip(),
            "sequence": sequence,
            "sequenceDisplay": to_display(sequence.encode("utf-8")) if sequence else "",
            "hasGS": "\x1d" in code,
            "status": status,
            "error": error,
        })
    return rows_out


def export_apply_csv(prepared: List[Dict]) -> bytes:
    """Выгрузка последовательностей в CSV: одна колонка, 0x1D остаётся байтом.

    Вызывается после проверки prepare_rows: строк с ошибками быть не должно.
    Кавычки добавляются CSV-механизмом только при необходимости; сама
    последовательность не изменяется.
    """
    bad = [r for r in prepared if r["status"] != "ok" or not r["sequence"]]
    if bad:
        raise ApplyError(
            f"Нельзя сформировать файл: некорректных строк {len(bad)} "
            f"(первая — №{bad[0]['index']}: {bad[0]['error']}). "
            "Исправьте их и загрузите файл заново."
        )
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    for row in prepared:
        writer.writerow([row["sequence"]])
    # BOM для корректного открытия в Excel; 0x1D внутри данных не затрагивает.
    return ("﻿" + buf.getvalue()).encode("utf-8")