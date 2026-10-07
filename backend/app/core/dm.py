# -*- coding: utf-8 -*-
"""Обёртки над pylibdmtx: бинарно-безопасная генерация и декодирование DataMatrix ECC 200.

Инвариант проекта (ТЗ §45): source bytes === decoded bytes, в частности 0x1D.
Работаем только с bytes — никакие строки не участвуют в пути данных.
"""
from typing import List, Optional, Tuple

from pylibdmtx.pylibdmtx import PyLibDMTXError, decode as _dmtx_decode, encode as _dmtx_encode
from PIL import Image

# Допустимые размеры символов DataMatrix ECC 200 (порядок возрастания ёмкости).
SYMBOL_SIZES = [
    "10x10", "12x12", "14x14", "16x16", "18x18", "20x20", "22x22",
    "24x24", "26x26", "32x32", "36x36", "40x40", "44x44", "48x48",
    "52x52", "64x64", "72x72", "80x80", "88x88", "96x96",
]

# Схема Ascii: 1 байт = 1 кодворд для байтов < 128, детерминированно.
# (Схемы AutoBest/AutoFast недоступны в pylibdmtx 0.1.10 — известный баг обёртки.)
ENCODING_SCHEME = "Ascii"


class EncodingError(Exception):
    """Не удалось закодировать данные ни в один размер символа."""


def encode_dm(data: bytes) -> Tuple[Image.Image, str, int]:
    """Кодирует bytes в DataMatrix (ECC 200), автоматически подбирая размер символа.

    Возвращает (PIL Image в режиме "L", имя размера, число модулей на стороне).
    Никаких преобразований данных: байты (включая 0x1D) попадают в код как есть.
    """
    if not data:
        raise EncodingError("Пустые данные: нечего кодировать")
    last_error: Optional[Exception] = None
    for size in SYMBOL_SIZES:
        try:
            enc = _dmtx_encode(data, size=size, scheme=ENCODING_SCHEME)
        except PyLibDMTXError as e:  # данные не влезают — пробуем следующий размер
            last_error = e
            continue
        img = Image.frombytes("RGB", (enc.width, enc.height), enc.pixels)
        return img.convert("L"), size, enc.width
    raise EncodingError(
        "Не удалось закодировать данные (слишком длинная последовательность: "
        f"{len(data)} байт). Последняя ошибка libdmtx: {last_error}"
    )


def dm_module_matrix(img: Image.Image) -> List[List[int]]:
    """Преобразует изображение DataMatrix в матрицу модулей: 1 = тёмный, 0 = светлый.

    Нужна для отрисовки модулей целыми пикселями (без интерполяции и сглаживания).
    """
    w, h = img.size
    px = img.load()
    return [[1 if px[x, y] < 128 else 0 for x in range(w)] for y in range(h)]


def dm_symbol_grid(img: Image.Image, symbol_n: int) -> List[List[int]]:
    """Матрица модулей СИМВОЛА размером symbol_n × symbol_n из растра libdmtx.

    Растр pylibdmtx — это пиксельная отрисовка символа с quiet zone, поэтому
    его размер не равен числу модулей. Здесь растр обрезается по граничным
    тёмным модулям (угловые finder-паттерны всегда тёмные), а каждый модуль
    считывается по центру своей ячейки.
    """
    w, h = img.size
    px = img.load()
    dark_rows = [y for y in range(h) if any(px[x, y] < 128 for x in range(w))]
    dark_cols = [x for x in range(w) if any(px[x, y] < 128 for y in range(h))]
    if not dark_rows or not dark_cols:
        raise EncodingError("Растр DataMatrix не содержит тёмных модулей")
    x0, x1 = dark_cols[0], dark_cols[-1]
    y0, y1 = dark_rows[0], dark_rows[-1]
    module_px = (x1 - x0 + 1) / symbol_n
    module_py = (y1 - y0 + 1) / symbol_n
    grid: List[List[int]] = []
    for r in range(symbol_n):
        cy = int(y0 + (r + 0.5) * module_py)
        row = [1 if px[int(x0 + (c + 0.5) * module_px), cy] < 128 else 0
               for c in range(symbol_n)]
        grid.append(row)
    return grid


def decode_dm(img: Image.Image, max_count: int = 1000) -> List[bytes]:
    """Ищет и декодирует все DataMatrix на изображении.

    Возвращает список исходных байтовых последовательностей (0x1D сохраняется
    как настоящий байт 0x1D, без замен).
    """
    results = _dmtx_decode(img, max_count=max_count)
    return [r.data for r in results]