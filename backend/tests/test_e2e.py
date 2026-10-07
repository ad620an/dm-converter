# -*- coding: utf-8 -*-
"""End-to-end round-trip тесты (ТЗ §36): PDF/PNG -> декодер -> побайтовое сравнение.

Проверяется не отображаемый текст, а сами байты:
    decodedBytes === sourceBytes, в частности 0x1D === 0x1D (§45).
"""
import io

import pytest

from app.core import decoder, labels

from conftest import CHZ_CODE, CHZ_CODE_2, GS, PLAIN_CODE


def _opts(label_w=40.0, label_h=58.0, variant=1):
    dw, dh = labels.auto_dm_size(label_w, label_h)
    opts = labels.LabelOptions(
        label_w_mm=label_w, label_h_mm=label_h,
        dm_w_mm=dw, dm_h_mm=dh, variant=variant,
    )
    opts.validate()
    return opts


def _rows(codes, article="ABC-001", qty="5"):
    return [{"code_bytes": c, "article": article, "quantity": qty} for c in codes]


@pytest.mark.e2e
def test_pdf_roundtrip_chz_code():
    """§36: эталонная строка ЧЗ — PDF -> декодер -> побайтовое совпадение."""
    pdf = labels.build_pdf(_rows([CHZ_CODE]), _opts())
    page_results, empty = decoder.decode_pdf_bytes(pdf)
    assert not empty
    codes = [c for pr in page_results for c in pr["codes"]]
    assert codes == [CHZ_CODE]


@pytest.mark.e2e
def test_png_roundtrip_gs():
    """PNG -> декодер: ABC + 0x1D + DEF восстанавливается побайтово."""
    src = b"ABC" + GS + b"DEF"
    png = io.BytesIO()
    img = labels.render_label_png(src, "", "", _opts(variant=3), dpi=300)  # только DataMatrix
    img.save(png, format="PNG")
    codes = decoder.decode_image_bytes(png.getvalue())
    assert codes == [src]


@pytest.mark.e2e
def test_pdf_multiple_codes_multiple_pages():
    """Тесты §35-8, §35-9: несколько кодов, несколько страниц, порядок сохранён."""
    srcs = [CHZ_CODE, PLAIN_CODE, CHZ_CODE_2, b"ABC" + GS + b"DEF"]
    pdf = labels.build_pdf(_rows(srcs), _opts())
    page_results, empty = decoder.decode_pdf_bytes(pdf)
    assert len(page_results) == 4  # одна наклейка = одна страница
    assert not empty
    for pr, src in zip(page_results, srcs):
        assert pr["codes"] == [src]
        assert pr["page"] >= 1


@pytest.mark.e2e
def test_pdf_page_numbers_in_result():
    page_results, _ = decoder.decode_pdf_bytes(
        labels.build_pdf(_rows([CHZ_CODE, PLAIN_CODE]), _opts())
    )
    pages = [pr["page"] for pr in page_results]
    assert pages == sorted(pages)  # порядок как в исходном документе


@pytest.mark.e2e
def test_decode_sample_pdf():
    """Декодирование реального пользовательского PDF из samples/ (если есть)."""
    import os

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sample = os.path.join(root, "samples", "order_15bd73b8-832a-4afc-a03f-7dfe565c1897_gtin_04620519012422_quantity_2.pdf")
    if not os.path.exists(sample):
        pytest.skip("образец samples/order_...pdf не найден")
    with open(sample, "rb") as f:
        raw = f.read()
    page_results, empty = decoder.decode_pdf_bytes(raw)
    all_codes = [c for pr in page_results for c in pr["codes"]]
    assert all_codes, "в образце должен найтись хотя бы один DataMatrix"
    # Каждый код — корректная последовательность с GS или стандартный GS1.
    for code in all_codes:
        assert isinstance(code, bytes)
        assert len(code) > 10