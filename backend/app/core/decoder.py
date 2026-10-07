# -*- coding: utf-8 -*-
"""Декодирование DataMatrix из PNG/JPG и PDF (ТЗ §19-28).

Приоритет — точное восстановление исходных байтов, включая 0x1D (§22).
Стратегия предобработки (§26): сначала пробуем исходное изображение,
и только если коды не найдены — градации серого, апскейл, порог, инверсию,
повороты. Для PDF (§27) — рендеринг страниц с нарастающим DPI (200/300/400),
тяжёлая обработка только там, где код не найден с первой попытки.
"""
import io
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageOps

from .dm import decode_dm

PDF_DPI_SCHEDULE = (200, 300, 400)
MAX_DECODE_COUNT = 1000


class DecodeError(Exception):
    """Ошибка декодирования с сообщением на русском языке (ТЗ §29)."""


def _load_image(raw: bytes) -> Image.Image:
    """Загружает изображение, применяет EXIF-поворот (§26)."""
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        raise DecodeError("Не удалось открыть изображение. Файл повреждён или имеет неподдерживаемый формат.")
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("L", "RGB", "CMYK"):
        img = img.convert("RGB")
    return img


def _decode_with_fallbacks(img: Image.Image) -> List[bytes]:
    """Ищет DataMatrix: сначала исходное изображение, затем предобработки.

    Возвращает список найденных последовательностей (без дубликатов подряд).
    """
    # 1. Исходное изображение — не портуем качественные файлы (§26).
    found = decode_dm(img, max_count=MAX_DECODE_COUNT)
    if found:
        return found

    gray = img.convert("L")
    w, h = gray.size

    # 2. Умеренный апскейл (помогает при маленьких кодах и лёгком размытии).
    for scale in (2, 3):
        if w * scale > 8000 or h * scale > 8000:
            break
        up = gray.resize((w * scale, h * scale), Image.NEAREST)
        found = decode_dm(up, max_count=MAX_DECODE_COUNT)
        if found:
            return found

    # 3. Инверсия (чёрно-белые сканы иногда дают инвертированный код).
    found = decode_dm(ImageOps.invert(gray), max_count=MAX_DECODE_COUNT)
    if found:
        return found

    # 4. Адаптивный порог через OpenCV (низкая контрастность, сканы).
    found = _decode_adaptive(gray)
    if found:
        return found

    # 5. Повороты на 90/180/270 (коды под углом кратным 90°).
    for angle in (90, 180, 270):
        found = decode_dm(gray.rotate(angle, expand=True), max_count=MAX_DECODE_COUNT)
        if found:
            return found
        found = _decode_adaptive(gray.rotate(angle, expand=True))
        if found:
            return found

    return []


def _decode_adaptive(gray: Image.Image) -> List[bytes]:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    arr = np.array(gray)
    # Апскейл x2 перед порогом улучшает поиск мелких модулей.
    if arr.shape[0] < 1000:
        arr = cv2.resize(arr, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
    for block in (31, 51, 75):
        if arr.shape[0] < block or arr.shape[1] < block:
            continue
        bin_img = cv2.adaptiveThreshold(arr, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY, block, 10)
        found = decode_dm(Image.fromarray(bin_img), max_count=MAX_DECODE_COUNT)
        if found:
            return found
    return []


def decode_image_bytes(raw: bytes) -> List[bytes]:
    """Декодирует все DataMatrix из изображения (PNG/JPG)."""
    img = _load_image(raw)
    return _decode_with_fallbacks(img)


def decode_pdf_bytes(raw: bytes,
                     progress: Optional[Callable[[str, int, int], None]] = None
                     ) -> Tuple[List[Dict], List[int]]:
    """Декодирует все DataMatrix из всех страниц PDF.

    Возвращает (результаты, страницы_без_кодов):
      результат = {"page": int, "codes": [bytes, ...], "dpi": int}
    Прогресс: (фаза, страница, всего_страниц).
    """
    import fitz  # pymupdf

    try:
        doc = fitz.open(stream=raw, filetype="pdf")
    except Exception:
        raise DecodeError("Не удалось открыть PDF-файл. Файл повреждён или имеет неподдерживаемый формат.")

    results: List[Dict] = []
    empty_pages: List[int] = []
    total = doc.page_count
    try:
        for i in range(total):
            page = doc.load_page(i)
            page_codes: List[bytes] = []
            used_dpi = 0
            # §27: наращиваем DPI только если на текущем коды не найдены.
            for dpi in PDF_DPI_SCHEDULE:
                pix = page.get_pixmap(dpi=dpi)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                page_codes = decode_dm(img, max_count=MAX_DECODE_COUNT)
                if page_codes:
                    used_dpi = dpi
                    break
            if not page_codes:
                # Фолбэк с предобработкой на 300 DPI (§26).
                pix = page.get_pixmap(dpi=300)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                page_codes = _decode_with_fallbacks(img)
                if page_codes:
                    used_dpi = 300
            if page_codes:
                results.append({"page": i + 1, "codes": page_codes, "dpi": used_dpi})
            else:
                empty_pages.append(i + 1)
            if progress:
                progress("page", i + 1, total)
    finally:
        doc.close()
    return results, empty_pages