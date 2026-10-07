# -*- coding: utf-8 -*-
"""Генерация этикеток: раскладка, PNG-рендер и векторный PDF (ТЗ §11-13, §16-18).

Инварианты:
- PDF-страница имеет точный физический размер наклейки в мм;
- модули DataMatrix рисуются целыми прямоугольниками (вектор в PDF, целые
  пиксели в PNG) — без масштабирования, размытия и anti-aliasing;
- quiet zone не меньше одного модуля; запрошенный размер DataMatrix включает
  поле отступа (код занимает область без учёта quiet zone полностью);
- раскладка вертикальная: DataMatrix сверху по центру, текст под ним;
- текст бёрется из исходных байтов: GTIN по разметке GS1, первые 38 символов
  исходной последовательности с последующей визуализацией <GS> (§15).
"""
import io
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdf_canvas

from .dm import dm_symbol_grid, encode_dm
from .display import first_n_display
from .gs1 import extract_gtin

MM_PER_INCH = 25.4

# Пресеты размеров наклейки (мм) — вертикальная ориентация (ширина × высота).
LABEL_PRESETS = [
    ("20 × 30 мм", 20, 30),
    ("20 × 40 мм", 20, 40),
    ("25 × 43 мм", 25, 43),
    ("30 × 50 мм", 30, 50),
    ("30 × 58 мм", 30, 58),
    ("40 × 58 мм", 40, 58),
    ("40 × 60 мм", 40, 60),
]

# Пресеты размеров DataMatrix (мм) — ТЗ §11. None = автоматический.
DM_PRESETS_MM = [None, 12, 15, 18, 20, 22, 25]

MIN_LABEL_MM = 10.0
MAX_LABEL_MM = 300.0
MIN_DM_MM = 5.0
MAX_DM_MM = 200.0
MARGIN_MM = 1.5       # поле наклейки
DM_TEXT_GAP_MM = 1.0  # зазор между кодом и текстом
FIRST_N_CHARS = 38    # ТЗ §13, §15
QUIET_ZONE_MODULES = 1  # quiet zone вокруг символа, в модулях (ISO 16022: >= 1X)

# Варианты дополнительной информации (ТЗ §13).
VARIANT_ARTICLE_QTY_GTIN = 1  # Артикул + Количество + GTIN + 38 знаков
VARIANT_GTIN_38 = 2           # GTIN + 38 знаков
VARIANT_DM_ONLY = 3           # только DataMatrix
VARIANTS = (VARIANT_ARTICLE_QTY_GTIN, VARIANT_GTIN_38, VARIANT_DM_ONLY)

_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


class LabelError(Exception):
    """Ошибка параметров этикетки с сообщением на русском языке."""


def _find_font() -> Optional[str]:
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def _register_pdf_font() -> str:
    """Регистрирует шрифт с поддержкой кириллицы; fallback на Helvetica."""
    path = _find_font()
    if path:
        try:
            pdfmetrics.registerFont(TTFont("LabelFont", path))
            return "LabelFont"
        except Exception:
            pass
    return "Helvetica"


@dataclass
class LabelOptions:
    label_w_mm: float
    label_h_mm: float
    dm_w_mm: float  # квадрат по умолчанию (ТЗ §11)
    dm_h_mm: float
    variant: int = VARIANT_ARTICLE_QTY_GTIN

    def validate(self) -> None:
        for name, v, lo, hi in [
            ("ширина наклейки", self.label_w_mm, MIN_LABEL_MM, MAX_LABEL_MM),
            ("высота наклейки", self.label_h_mm, MIN_LABEL_MM, MAX_LABEL_MM),
            ("ширина DataMatrix", self.dm_w_mm, MIN_DM_MM, MAX_DM_MM),
            ("высота DataMatrix", self.dm_h_mm, MIN_DM_MM, MAX_DM_MM),
        ]:
            if not (lo <= v <= hi):
                raise LabelError(
                    f"Недопустимое значение: {name} = {v:g} мм. "
                    f"Допустимый диапазон — от {lo:g} до {hi:g} мм."
                )
        margin = min(MARGIN_MM, self.label_w_mm / 8, self.label_h_mm / 8)
        if (self.dm_w_mm > self.label_w_mm - 2 * margin
                or self.dm_h_mm > self.label_h_mm - 2 * margin):
            raise LabelError(
                f"DataMatrix {self.dm_w_mm:g} × {self.dm_h_mm:g} мм не помещается "
                f"на наклейку {self.label_w_mm:g} × {self.label_h_mm:g} мм. "
                "Уменьшите размер кода или увеличьте наклейку."
            )
        if self.variant not in VARIANTS:
            raise LabelError("Неизвестный вариант дополнительной информации.")


def auto_dm_size(label_w_mm: float, label_h_mm: float) -> Tuple[float, float]:
    """Автоматический размер DataMatrix: ограничен шириной наклейки,
    под текст оставляется не меньше половины высоты (код сверху, текст снизу)."""
    margin = min(MARGIN_MM, label_w_mm / 8, label_h_mm / 8)
    side = min(label_w_mm - 2 * margin, (label_h_mm - 3 * margin) / 2, 25.0)
    return round(max(side, MIN_DM_MM), 1), round(max(side, MIN_DM_MM), 1)


@dataclass
class _Layout:
    """Геометрия этикетки в мм; начало координат — левый ВЕРХНИЙ угол.

    dm_cols/dm_rows — размер сетки отрисовки вместе с quiet zone
    (символ n × n плюс по QUIET_ZONE_MODULES модулей с каждой стороны).
    """
    label_w_mm: float
    label_h_mm: float
    dm_x: float
    dm_y: float
    dm_w: float
    dm_h: float
    dm_cols: int
    dm_rows: int
    module_mm: float
    dm_matrix: List[List[int]] = None  # матрица модулей символа n × n
    text_x: Optional[float] = None
    text_y: Optional[float] = None
    text_w: Optional[float] = None
    text_h: Optional[float] = None


def label_text_lines(code: bytes, article: str, quantity: str, variant: int) -> List[str]:
    """Строки дополнительной информации по выбранному варианту (ТЗ §13).

    Первые 38 знаков: сначала берутся символы исходной последовательности,
    затем выполняется визуализация <GS> (ТЗ §15).
    """
    gtin = extract_gtin(code)
    first38 = first_n_display(code, FIRST_N_CHARS)
    if variant == VARIANT_ARTICLE_QTY_GTIN:
        lines = []
        if article.strip():
            lines.append(f"Артикул: {article.strip()}")
        if quantity.strip():
            lines.append(f"Количество: {quantity.strip()}")
        if gtin:
            lines.append(f"GTIN: {gtin}")
        lines.append(first38)
        return lines
    if variant == VARIANT_GTIN_38:
        lines = []
        if gtin:
            lines.append(f"GTIN: {gtin}")
        lines.append(first38)
        return lines
    return []  # только DataMatrix


def _wrap_by_measure(lines: List[str], measure, max_width_mm: float) -> List[str]:
    """Переносит длинные строки по ширине текстового блока. measure(s) -> мм."""
    wrapped: List[str] = []
    for line in lines:
        if measure(line) <= max_width_mm:
            wrapped.append(line)
            continue
        out = ""
        for ch in line:
            if out and measure(out + ch) > max_width_mm:
                wrapped.append(out)
                out = ch
            else:
                out += ch
        wrapped.append(out)
    return wrapped


def _padded_matrix(matrix: List[List[int]], quiet: int) -> List[List[int]]:
    """Матрица символа, обрамлённая quiet zone из `quiet` светлых модулей."""
    n = len(matrix)
    row_pad = [0] * (n + 2 * quiet)
    rows_out = [list(row_pad) for _ in range(quiet)]
    rows_out += [[0] * quiet + list(row) + [0] * quiet for row in matrix]
    rows_out += [list(row_pad) for _ in range(quiet)]
    return rows_out


def compute_layout(code: bytes, options: LabelOptions) -> _Layout:
    """Чистая геометрия этикетки (без текста и подгонки шрифта)."""
    options.validate()
    dm_img, size, _w = encode_dm(code)  # проверка кодируемости + размер символа
    n_cols, n_rows = (int(v) for v in size.split("x"))
    symbol = dm_symbol_grid(dm_img, n_rows)

    W, H = options.label_w_mm, options.label_h_mm
    dm_w, dm_h = options.dm_w_mm, options.dm_h_mm
    margin = min(MARGIN_MM, W / 8, H / 8)
    # Запрошенный размер DataMatrix включает поле отступа (quiet zone).
    cols = n_cols + 2 * QUIET_ZONE_MODULES
    rows = n_rows + 2 * QUIET_ZONE_MODULES
    module_mm = min(dm_w / cols, dm_h / rows)

    return _Layout(
        label_w_mm=W, label_h_mm=H, dm_x=0, dm_y=0,
        dm_w=dm_w, dm_h=dm_h, dm_cols=cols, dm_rows=rows, module_mm=module_mm,
        dm_matrix=symbol,
    )


def place_elements(layout: _Layout, has_text: bool) -> None:
    """Размещает код и текстовый блок на наклейке (мутирует layout).

    Вертикальная раскладка: DataMatrix сверху по центру, текст под ним.
    """
    W, H = layout.label_w_mm, layout.label_h_mm
    margin = min(MARGIN_MM, W / 8, H / 8)
    if not has_text:
        # Только DataMatrix — по центру.
        layout.dm_x = (W - layout.dm_w) / 2
        layout.dm_y = (H - layout.dm_h) / 2
        return
    # Код сверху по центру, текст снизу на всю ширину.
    layout.dm_x = (W - layout.dm_w) / 2
    layout.dm_y = margin
    layout.text_x = margin
    layout.text_w = W - 2 * margin
    layout.text_y = margin + layout.dm_h + DM_TEXT_GAP_MM
    layout.text_h = H - margin - layout.text_y


def _fit_text(lines: List[str], text_w_mm: float, text_h: float,
              make_font, measure_font, min_size: float, max_size: float,
              size_step: float, line_factor: float) -> Tuple[object, float, List[str]]:
    """Подбирает наибольший размер шрифта, при котором текст влезает в блок.

    make_font(size) -> объект шрифта; measure_font(font, s) -> ширина s в мм;
    text_h и размер шрифта — в ОДНИХ единицах (px для PNG, pt для PDF);
    line_factor — высота строки в единицах размера шрифта.
    Возвращает (шрифт, размер, строки с переносами).
    """
    size = max_size
    while size >= min_size:
        font = make_font(size)
        wrapped = _wrap_by_measure(
            lines, lambda s: measure_font(font, s), text_w_mm
        )
        if wrapped and len(wrapped) * line_factor * size <= text_h:
            return font, size, wrapped
        size -= size_step
    font = make_font(min_size)
    wrapped = _wrap_by_measure(lines, lambda s: measure_font(font, s), text_w_mm)
    return font, min_size, wrapped


# ---------------------------------------------------------------- PNG-рендер

def render_label_png(code: bytes, article: str, quantity: str,
                     options: LabelOptions, dpi: int = 300) -> Image.Image:
    """Рендерит этикетку в PNG: модули — целые пиксели, без сглаживания (§18)."""
    font_path = _find_font()
    px_per_mm = dpi / MM_PER_INCH

    layout = compute_layout(code, options)
    lines = label_text_lines(code, article, quantity, options.variant)
    place_elements(layout, bool(lines))

    def px(mm_value: float) -> int:
        return max(0, round(mm_value * px_per_mm))

    img = Image.new("1", (px(layout.label_w_mm), px(layout.label_h_mm)), 1)
    draw = ImageDraw.Draw(img)

    # --- DataMatrix: сетка модулей целыми пикселями (с quiet zone)
    matrix = _padded_matrix(layout.dm_matrix, QUIET_ZONE_MODULES)
    mod_px = max(1, min(
        px(layout.dm_w) // layout.dm_cols,
        px(layout.dm_h) // layout.dm_rows,
    ))
    grid_w, grid_h = mod_px * layout.dm_cols, mod_px * layout.dm_rows
    gx = px(layout.dm_x) + (px(layout.dm_w) - grid_w) // 2
    gy = px(layout.dm_y) + (px(layout.dm_h) - grid_h) // 2
    for r, row_mods in enumerate(matrix):
        for c, dark in enumerate(row_mods):
            if dark:
                draw.rectangle(
                    [gx + c * mod_px, gy + r * mod_px,
                     gx + (c + 1) * mod_px - 1, gy + (r + 1) * mod_px - 1],
                    fill=0,
                )

    # --- Текст
    if lines and layout.text_w and px(layout.text_w) > 4 and px(layout.text_h) > 4:
        def make_font(size_px: int):
            return ImageFont.truetype(font_path, size_px) if font_path else ImageFont.load_default()

        def font_width_mm(font, s: str) -> float:
            try:
                w = font.getlength(s)
            except AttributeError:
                w = font.getsize(s)[0]
            return w / px_per_mm

        text_h_px = px(layout.text_h)
        font, size_px, wrapped = _fit_text(
            lines, layout.text_w, text_h_px,
            make_font, font_width_mm,
            min_size=4, max_size=max(6, int(text_h_px / max(1, len(lines)) / 1.25)),
            size_step=1, line_factor=1.25,
        )
        line_h = round(size_px * 1.25)
        y = px(layout.text_y)
        for line in wrapped:
            draw.text((px(layout.text_x), y), line, font=font, fill=0)
            y += line_h
    return img


# ---------------------------------------------------------------- PDF-рендер

def _draw_dm_vector(c: pdf_canvas.Canvas, layout: _Layout,
                    matrix: List[List[int]]) -> None:
    """Рисует DataMatrix прямоугольниками в точных мм — без растровых артефактов.

    matrix включает окантовку quiet zone (светлые модули не рисуются).
    """
    cols, rows = layout.dm_cols, layout.dm_rows
    module_mm = min(layout.dm_w / cols, layout.dm_h / rows)
    grid_w, grid_h = module_mm * cols, module_mm * rows
    gx = layout.dm_x + (layout.dm_w - grid_w) / 2
    # PDF: начало координат — левый НИЖНИЙ угол; инвертируем вертикаль.
    gy = (layout.label_h_mm - layout.dm_y - layout.dm_h) + (layout.dm_h - grid_h) / 2
    for r, row_mods in enumerate(matrix):
        for col, dark in enumerate(row_mods):
            if dark:
                c.rect(
                    (gx + col * module_mm) * mm,
                    (gy + (rows - 1 - r) * module_mm) * mm,
                    module_mm * mm, module_mm * mm,
                    stroke=0, fill=1,
                )


def _draw_label_pdf_page(c: pdf_canvas.Canvas, code: bytes, article: str,
                         quantity: str, options: LabelOptions,
                         font_name: str) -> None:
    layout = compute_layout(code, options)
    lines = label_text_lines(code, article, quantity, options.variant)
    place_elements(layout, bool(lines))

    page_w, page_h = layout.label_w_mm * mm, layout.label_h_mm * mm
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, page_w, page_h, stroke=0, fill=1)

    c.setFillColorRGB(0, 0, 0)
    _draw_dm_vector(
        c, layout, _padded_matrix(layout.dm_matrix, QUIET_ZONE_MODULES)
    )

    if lines and layout.text_w and layout.text_h > 0:
        def width_mm(font_size: float, s: str) -> float:
            return pdfmetrics.stringWidth(s, font_name, font_size) / mm

        pt_per_mm = 72 / 25.4
        text_h_pt = layout.text_h * pt_per_mm
        _font, font_size, wrapped = _fit_text(
            lines, layout.text_w, text_h_pt,
            lambda size_pt: size_pt, width_mm,
            min_size=3.0, max_size=max(4.0, text_h_pt / max(1, len(lines)) / 1.25),
            size_step=0.5, line_factor=1.25,
        )
        line_h = font_size * 1.25
        c.setFont(font_name, font_size)
        y_top_pt = (layout.label_h_mm - layout.text_y) * mm
        for line in wrapped:
            c.drawString(layout.text_x * mm, y_top_pt - line_h, line)
            y_top_pt -= line_h


def build_pdf(rows: List[Dict], options: LabelOptions,
              progress: Optional[Callable[[int, int], None]] = None) -> bytes:
    """Собирает PDF: одна наклейка = одна страница точного физического размера (§17-18)."""
    font_name = _register_pdf_font()
    buf = io.BytesIO()
    page_size = (options.label_w_mm * mm, options.label_h_mm * mm)
    c = pdf_canvas.Canvas(buf, pagesize=page_size)
    total = len(rows)
    for i, row in enumerate(rows):
        _draw_label_pdf_page(
            c, row["code_bytes"],
            row.get("article") or "", row.get("quantity") or "",
            options, font_name,
        )
        c.showPage()
        if progress:
            progress(i + 1, total)
    c.save()
    return buf.getvalue()


def build_zip_png(rows: List[Dict], options: LabelOptions, dpi: int = 600,
                  progress: Optional[Callable[[int, int], None]] = None) -> bytes:
    """ZIP с PNG-файлами этикеток (§17). Имена предсказуемые: label_0001.png."""
    buf = io.BytesIO()
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    total = len(rows)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, row in enumerate(rows):
            img = render_label_png(
                row["code_bytes"], row.get("article") or "",
                row.get("quantity") or "", options, dpi=dpi,
            )
            png = io.BytesIO()
            img.save(png, format="PNG")
            zf.writestr(f"datamatrix_{stamp}/label_{i + 1:04d}.png", png.getvalue())
            if progress:
                progress(i + 1, total)
    return buf.getvalue()