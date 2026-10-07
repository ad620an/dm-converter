# -*- coding: utf-8 -*-
"""Импорт TXT / CSV / XLSX с бинарно-безопасной обработкой (ТЗ §5-8).

Критические правила (ТЗ §6):
- 0x1D (GS) не должен теряться при импорте;
- запрещён преждевременный trim(), удаление управляющих символов и регулярные
  выражения, чистящие непечатаемые символы;
- удаляются только разделители строк CR/LF, относящиеся к структуре файла.
"""
import csv
import io
from typing import Dict, List, Optional

MAX_ROWS = 1000

# Допустимые названия колонки с кодом маркировки (ТЗ §5).
CODE_COLUMN_NAMES = {"код", "datamatrix", "code", "код маркировки", "коды", "гс1", "гс1 код"}
ARTICLE_COLUMN_NAMES = {"артикул", "article", "sku", "артикул товара", "номенклатура"}
QUANTITY_COLUMN_NAMES = {"количество", "кол-во", "колво", "qty", "quantity", "количество шт"}


class ParseError(Exception):
    """Ошибка импорта с сообщением на русском языке (ТЗ §29)."""


def detect_encoding(raw: bytes) -> str:
    """UTF-8 (с BOM и без), при неудаче — Windows-1251 (ТЗ §7)."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "cp1251"


def _is_header_cell(value: str) -> bool:
    v = value.strip().lower()
    return v in CODE_COLUMN_NAMES | ARTICLE_COLUMN_NAMES | QUANTITY_COLUMN_NAMES


def _split_raw_lines(raw: bytes) -> List[bytes]:
    """Разбивает файл на строки, удаляя ТОЛЬКО структурные CR/LF.

    Никакого trim() содержимого строки: 0x1D и прочие байты остаются на месте.
    """
    lines = raw.split(b"\n")
    return [ln[:-1] if ln.endswith(b"\r") else ln for ln in lines]


def parse_txt(raw: bytes) -> Dict:
    """Импорт TXT (ТЗ §6): вариант А — код на строку; вариант Б — табуляция."""
    encoding = detect_encoding(raw)
    raw_lines = [ln for ln in _split_raw_lines(raw) if ln != b""]
    if not raw_lines:
        raise ParseError("Файл пуст или не содержит ни одной непустой строки.")

    # Вариант Б: табуляция. Считаем табы в каждой строке; если есть строка
    # с табами и число табов согласовано (или строка всего одна с табами) —
    # это табличный файл.
    tab_counts = [ln.count(b"\t") for ln in raw_lines]
    has_tabs = tab_counts and max(tab_counts) > 0
    if has_tabs:
        consistent = len(set(tab_counts)) == 1
        # Заголовок: первая строка без 0x1D, все ячейки — известные названия колонок.
        first_cells = raw_lines[0].split(b"\t")
        looks_like_header = (
            b"\x1d" not in raw_lines[0]
            and len(first_cells) > 1
            and all(_is_header_cell(c.decode(encoding, errors="replace")) for c in first_cells if c.strip())
            and all(c.strip() for c in first_cells)
        )
        header = [c.decode(encoding).strip() for c in first_cells] if looks_like_header else None
        data_lines = raw_lines[1:] if looks_like_header else raw_lines
        rows = []
        for ln in data_lines:
            cells = [c.decode(encoding) for c in ln.split(b"\t")]
            rows.append(cells + [""] * (len(first_cells) - len(cells)))
        return {"format": "txt", "encoding": encoding, "header": header, "rows": rows}

    # Вариант А: один код на строку.
    rows = [[ln.decode(encoding)] for ln in raw_lines]
    return {"format": "txt", "encoding": encoding, "header": None, "rows": rows}


def _detect_csv_delimiter(sample: str) -> str:
    """Автоопределение разделителя CSV: ; , или tab (ТЗ §7).

    Считаем только разделители вне кавычек.
    """
    counts = {";": 0, ",": 0, "\t": 0}
    in_quotes = False
    for ch in sample[:100000]:
        if ch == '"':
            in_quotes = not in_quotes
        elif not in_quotes and ch in counts:
            counts[ch] += 1
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ";"


def parse_csv(raw: bytes) -> Dict:
    """Импорт CSV с поддержкой quoted fields и автоопределением разделителя."""
    encoding = detect_encoding(raw)
    text = raw.decode(encoding)
    delimiter = _detect_csv_delimiter(text)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    raw_rows = [row for row in reader]
    raw_rows = [row for row in raw_rows if any(cell.strip() != "" for cell in row)]
    if not raw_rows:
        raise ParseError("Файл пуст или не содержит ни одной непустой строки.")

    # Заголовок: первая строка содержит известные названия колонок и не похожа
    # на код (нет 0x1D и длинной цифро-буквенной последовательности).
    first = raw_rows[0]
    looks_like_header = any(_is_header_cell(c) for c in first if c.strip())
    header = [c.strip() for c in first] if looks_like_header else None
    rows = raw_rows[1:] if looks_like_header else raw_rows
    return {"format": "csv", "encoding": encoding, "header": header, "rows": rows}


def _xlsx_cell_to_str(value) -> str:
    """Значение XLSX максимально близко к исходному строковому представлению.

    ТЗ §8: GTIN не должен превращаться в число, scientific notation или терять
    ведущие нули. Текстовые ячейки Excel остаются текстом; числовые ячейки
    с целым значением форматируются без дробной части и без экспоненты.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        # Формат без scientific notation.
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return format(value, "f")
    if isinstance(value, int):
        return str(value)
    return str(value)


def parse_xlsx(raw: bytes) -> Dict:
    """Импорт XLSX через openpyxl: все значения — как строки (ТЗ §8)."""
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception:
        raise ParseError("Не удалось прочитать XLSX-файл. Убедитесь, что файл не повреждён.")

    ws = None
    for sheet in wb.worksheets:
        if sheet.max_row and sheet.max_row > 0:
            ws = sheet
            break
    if ws is None:
        raise ParseError("XLSX-файл не содержит данных.")

    raw_rows: List[List[str]] = []
    for excel_row in ws.iter_rows(values_only=True):
        cells = [_xlsx_cell_to_str(v) for v in excel_row]
        if any(c.strip() != "" for c in cells):
            raw_rows.append(cells)
    wb.close()
    if not raw_rows:
        raise ParseError("XLSX-файл не содержит данных.")

    first = raw_rows[0]
    looks_like_header = any(_is_header_cell(c) for c in first if c.strip())
    header = [c.strip() for c in first] if looks_like_header else None
    rows = raw_rows[1:] if looks_like_header else raw_rows
    return {"format": "xlsx", "encoding": "utf-8", "header": header, "rows": rows}


def parse_file(filename: str, raw: bytes) -> Dict:
    """Определяет формат по расширению и вызывает нужный парсер."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "txt":
        parsed = parse_txt(raw)
    elif ext == "csv":
        parsed = parse_csv(raw)
    elif ext in ("xlsx", "xlsm"):
        parsed = parse_xlsx(raw)
    elif ext in ("tsv",):
        parsed = parse_txt(raw)
    else:
        raise ParseError(
            f"Неподдерживаемый формат файла «.{ext}». Поддерживаются TXT, CSV и XLSX."
        )
    if len(parsed["rows"]) > MAX_ROWS:
        raise ParseError(
            f"Файл содержит {len(parsed['rows'])} строк. "
            f"Максимально допустимое количество — {MAX_ROWS}."
        )
    return parsed


def _looks_like_code(value: str) -> bool:
    """Эвристика «похоже на код маркировки»: содержит GS или начинается с 01 + 14 цифр."""
    if not value:
        return False
    if "\x1d" in value:
        return True
    v = value.lstrip("]")
    return len(v) >= 16 and v[:2] == "01" and v[2:16].isdigit()


def guess_column_mapping(parsed: Dict) -> Optional[Dict[str, Optional[int]]]:
    """Определяет, какие колонки содержат код/артикул/количество.

    Возвращает mapping или None, если определить не удалось (нужно окно
    сопоставления колонок — ТЗ §5).
    """
    header: Optional[List[str]] = parsed.get("header")
    rows = parsed["rows"]
    ncols = max((len(r) for r in rows), default=0)
    if ncols == 0:
        return None

    code_col: Optional[int] = None
    article_col: Optional[int] = None
    qty_col: Optional[int] = None

    if header:
        for i, name in enumerate(header):
            n = (name or "").strip().lower()
            if n in CODE_COLUMN_NAMES and code_col is None:
                code_col = i
            elif n in ARTICLE_COLUMN_NAMES and article_col is None:
                article_col = i
            elif n in QUANTITY_COLUMN_NAMES and qty_col is None:
                qty_col = i

    # Нет заголовка или колонка кода не найдена — эвристика по содержимому.
    if code_col is None:
        sample = [r for r in rows if any(c.strip() for c in r)][:50]
        # Колонка, где большинство ячеек похожи на код маркировки.
        best_ratio, best_col = 0.0, None
        for c in range(ncols):
            values = [r[c] if c < len(r) else "" for r in sample]
            if not values or not any(v.strip() for v in values):
                continue
            ratio = sum(1 for v in values if _looks_like_code(v)) / len(values)
            if ratio > best_ratio:
                best_ratio, best_col = ratio, c
        if best_ratio >= 0.5:
            code_col = best_col
        elif ncols == 1:
            code_col = 0
        elif ncols == 3:
            code_col = 0  # типовой порядок: Код, Артикул, Количество

    return {"code": code_col, "article": article_col, "quantity": qty_col}


def apply_mapping(parsed: Dict, mapping: Dict[str, Optional[int]]) -> List[Dict]:
    """Применяет сопоставление колонок и формирует строки с кодом/артикулом/количеством.

    Значения ячеек не очищаются: 0x1D и любые другие символы сохраняются.
    """
    rows_out: List[Dict] = []
    code_col = mapping.get("code")
    article_col = mapping.get("article")
    qty_col = mapping.get("quantity")
    for i, r in enumerate(parsed["rows"]):
        def cell(idx):
            if idx is None or idx >= len(r):
                return ""
            return r[idx]
        rows_out.append({
            "index": i + 1,
            "code": cell(code_col),
            "article": cell(article_col),
            "quantity": cell(qty_col),
        })
    return rows_out