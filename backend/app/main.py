# -*- coding: utf-8 -*-
"""Веб-сервис DataMatrix «Честный знак»: FastAPI-приложение.

Все файлы обрабатываются локально, без внешних API (ТЗ §32). Результаты
хранятся во временном хранилище со случайными именами и удаляются автоматически.
"""
import os
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from . import jobs
from .core import apply as apply_core
from .core import decoder, labels, parsers
from .core.display import (
    b64_to_bytes, bytes_to_b64, contains_gs, find_gs_positions, hex_dump, to_display,
)
from .core.gs1 import code_details, extract_gtin
from .exporters import dedup_rows, export_csv, export_txt

app = FastAPI(title="DataMatrix — Честный знак", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # локальный запуск; доступ только из localhost
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_UPLOAD_BYTES = 30 * 1024 * 1024
MAX_ROWS = parsers.MAX_ROWS
DECODE_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
IMPORT_EXTENSIONS = {"txt", "csv", "xlsx", "xlsm", "tsv"}


class RowIn(BaseModel):
    codeB64: str
    article: str = ""
    quantity: str = ""


class LabelOptionsIn(BaseModel):
    labelWmm: float
    labelHmm: float
    dmWmm: Optional[float] = None   # None — автоматический размер (§11)
    dmHmm: Optional[float] = None
    variant: int = 1


class GenerateIn(BaseModel):
    rows: List[RowIn]
    options: LabelOptionsIn
    format: str = "pdf"  # "pdf" | "pngzip"


class ExportIn(BaseModel):
    format: str = "txt"          # "txt" | "csv"
    gsMode: str = "original"     # "original" | "readable" (§25)
    dedup: bool = False


def _check_upload(file: UploadFile, allowed: set) -> str:
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in allowed:
        raise HTTPException(
            400,
            f"Неподдерживаемый формат файла «{ext or file.filename}». "
            f"Поддерживаются: {', '.join(sorted(allowed))}.",
        )
    return ext


async def _read_upload(file: UploadFile) -> bytes:
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Файл пуст.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            400,
            f"Файл слишком большой ({len(raw) / (1024 * 1024):.1f} МБ). "
            f"Максимальный размер — {MAX_UPLOAD_BYTES // (1024 * 1024)} МБ.",
        )
    return raw


def _row_payload(index: int, code: bytes, article: str, quantity: str,
                 cells: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """Строка для таблицы импорта: исходные байты + представление для UI.

    cells — исходные ячейки строки (b64 + display) для окна сопоставления
    колонок: смена маппинга не требует повторной загрузки файла.
    """
    status, error = "ok", None
    if not code:
        status, error = "error", "Пустой код маркировки"
    return {
        "index": index,
        "codeB64": bytes_to_b64(code),
        "codeDisplay": to_display(code),
        "hex": hex_dump(code),
        "article": article,
        "quantity": quantity,
        "hasGS": contains_gs(code),
        "status": status,
        "error": error,
        "cells": cells or [],
    }


@app.post("/api/parse")
async def api_parse(file: UploadFile):
    """Импорт TXT/CSV/XLSX и предпросмотр строк (ТЗ §4-9)."""
    ext = _check_upload(file, IMPORT_EXTENSIONS)
    raw = await _read_upload(file)
    try:
        parsed = parsers.parse_file(file.filename, raw)
        mapping = parsers.guess_column_mapping(parsed)
    except parsers.ParseError as e:
        raise HTTPException(400, str(e))

    needs_mapping = mapping is None or mapping.get("code") is None
    if mapping is None:
        mapping = {"code": None, "article": None, "quantity": None}

    rows_data = parsers.apply_mapping(parsed, mapping)
    rows = []
    for r in rows_data:
        cells = [
            {"b64": bytes_to_b64(cell.encode("utf-8")), "display": to_display(cell.encode("utf-8"))}
            for cell in parsed["rows"][r["index"] - 1]
        ]
        rows.append(
            _row_payload(
                r["index"],
                r["code"].encode("utf-8"),
                r["article"],
                r["quantity"],
                cells,
            )
        )

    # Ячейки для окна сопоставления колонок (§5).
    columns: List[Dict[str, Any]] = []
    ncols = max((len(r) for r in parsed["rows"]), default=0)
    for c in range(ncols):
        samples = [r[c] for r in parsed["rows"][:5] if c < len(r) and r[c]]
        header_name = (parsed.get("header") or [None] * ncols)[c] if parsed.get("header") else None
        columns.append({
            "index": c,
            "name": header_name,
            "sample": to_display(samples[0].encode("utf-8")) if samples else "",
        })

    total = len(rows)
    ok = sum(1 for r in rows if r["status"] == "ok")
    return {
        "format": parsed["format"],
        "encoding": parsed["encoding"],
        "header": parsed["header"],
        "columns": columns,
        "mapping": mapping,
        "needsMapping": needs_mapping,
        "rows": rows,
        "counts": {"total": total, "ok": ok, "error": total - ok},
        "hasGS": any(r["hasGS"] for r in rows),
        "maxRows": MAX_ROWS,
    }


class PreviewIn(BaseModel):
    codeB64: str
    article: str = ""
    quantity: str = ""
    options: LabelOptionsIn


@app.post("/api/preview-label")
async def api_preview_label(payload: PreviewIn):
    """Live-preview наклейки с реальными пропорциями (§16)."""
    code = b64_to_bytes(payload.codeB64)
    try:
        opts = _make_label_options(payload.options)
        img = labels.render_label_png(
            code, payload.article, payload.quantity, opts, dpi=150,
        )
    except labels.LabelError as e:
        raise HTTPException(400, str(e))
    import io as _io
    from PIL import Image
    buf = _io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


def _make_label_options(options: LabelOptionsIn) -> labels.LabelOptions:
    if options.dmWmm is None or options.dmHmm is None:
        dw, dh = labels.auto_dm_size(options.labelWmm, options.labelHmm)
    else:
        dw, dh = options.dmWmm, options.dmHmm
    opts = labels.LabelOptions(
        label_w_mm=options.labelWmm, label_h_mm=options.labelHmm,
        dm_w_mm=dw, dm_h_mm=dh, variant=options.variant,
    )
    opts.validate()
    return opts


def _run_generate(job: jobs.Job, rows: List[RowIn], options: LabelOptionsIn,
                  fmt: str) -> None:
    try:
        job.status = "running"
        job.phase = "Генерация"
        opts = _make_label_options(options)
        data_rows = [
            {"code_bytes": b64_to_bytes(r.codeB64), "article": r.article,
             "quantity": r.quantity}
            for r in rows if b64_to_bytes(r.codeB64)
        ]
        total = len(data_rows)

        def progress(done: int, total: int) -> None:
            jobs.set_progress(job, done, total,
                              message=f"Создано {done} из {total} кодов")

        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        if fmt == "pngzip":
            pdf_bytes = labels.build_zip_png(data_rows, opts, dpi=600,
                                             progress=progress)
            name, mime = f"datamatrix_{stamp}.zip", "application/zip"
        else:
            pdf_bytes = labels.build_pdf(data_rows, opts, progress=progress)
            name, mime = f"datamatrix_{stamp}.pdf", "application/pdf"
        jobs.store_result_file(job, pdf_bytes, name, mime)
        job.extra = {"count": total, "skipped": len(rows) - total}
        jobs.finish_ok(job)
    except Exception as e:  # noqa: BLE001 — единая обработка с русским сообщением
        jobs.finish_error(job, _friendly_error(e))


def _friendly_error(e: Exception) -> str:
    msg = str(e)
    if "не помещается" in msg or "Недопустимое" in msg:
        return msg
    return f"Внутренняя ошибка обработки: {msg}"


@app.post("/api/generate")
async def api_generate(payload: GenerateIn, background: BackgroundTasks):
    """Запуск генерации PDF (или ZIP с PNG) в фоне (§17, §28)."""
    rows = [r for r in payload.rows if b64_to_bytes(r.codeB64)]
    if not rows:
        raise HTTPException(400, "Нет строк с кодами для генерации.")
    if len(rows) > MAX_ROWS:
        raise HTTPException(
            400, f"Передано {len(rows)} строк. Максимально допустимое количество — {MAX_ROWS}."
        )
    if payload.format not in ("pdf", "pngzip"):
        raise HTTPException(400, "Неизвестный формат результата. Поддерживаются PDF и ZIP с PNG.")
    try:
        _make_label_options(payload.options)
    except labels.LabelError as e:
        raise HTTPException(400, str(e))
    job = jobs.create_job("generate")
    background.add_task(_run_generate, job, payload.rows, payload.options, payload.format)
    return {"jobId": job.id}


def _run_decode(job: jobs.Job, raw: bytes, ext: str, filename: str) -> None:
    try:
        job.status = "running"
        results: List[Dict[str, Any]] = []

        def add_code(page: int, data: bytes) -> None:
            results.append({
                "index": len(results) + 1,
                "page": page,
                "dataB64": bytes_to_b64(data),
                "codeDisplay": to_display(data),
                "hex": hex_dump(data),
                "gtin": extract_gtin(data),
                "hasGS": contains_gs(data),
                "status": "ok",
                "gsPositions": find_gs_positions(data),
                "details": code_details(data),
                "dpi": 0,
            })

        if ext == "pdf":
            def progress(phase: str, page: int, total: int) -> None:
                jobs.set_progress(job, page, total, phase="Обработка PDF",
                                  message=f"Страница {page} из {total}")

            page_results, empty_pages = decoder.decode_pdf_bytes(raw, progress)
            for pr in page_results:
                for code in pr["codes"]:
                    add_code(pr["page"], code)
            job.extra = {"emptyPages": empty_pages, "fileName": filename}
            if empty_pages and not results:
                job.extra["note"] = (
                    "DataMatrix-коды не обнаружены ни на одной странице."
                )
        else:
            jobs.set_progress(job, 1, 2, phase="Обработка изображения",
                              message="Поиск DataMatrix на изображении")
            codes = decoder.decode_image_bytes(raw)
            for code in codes:
                add_code(1, code)
            job.extra = {"fileName": filename}
            if not codes:
                job.extra["note"] = "DataMatrix-коды на изображении не обнаружены."

        job.results = results
        jobs.set_progress(job, 1, 1, message=f"Найдено кодов: {len(results)}")
        jobs.finish_ok(job)
    except Exception as e:  # noqa: BLE001
        jobs.finish_error(job, _friendly_error(e))


@app.post("/api/decode")
async def api_decode(file: UploadFile, background: BackgroundTasks):
    """Запуск декодирования PDF/изображения в фоне (§19-28)."""
    ext = _check_upload(file, DECODE_EXTENSIONS)
    raw = await _read_upload(file)
    job = jobs.create_job("decode")
    background.add_task(_run_decode, job, raw, ext, file.filename)
    return {"jobId": job.id}


@app.get("/api/jobs/{job_id}")
async def api_job_status(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Задача не найдена или уже удалена. Повторите операцию.")
    return job.to_dict()


@app.get("/api/jobs/{job_id}/file")
async def api_job_file(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Задача не найдена или уже удалена.")
    if not job.file_path or not os.path.exists(job.file_path):
        raise HTTPException(404, "Результат ещё не готов или недоступен.")
    return FileResponse(
        job.file_path, media_type=job.mime or "application/octet-stream",
        filename=job.file_name or "result",
    )


@app.post("/api/decode/{job_id}/export")
async def api_decode_export(job_id: str, payload: ExportIn):
    """Экспорт результатов декодирования в TXT или CSV (§24-25)."""
    job = jobs.get_job(job_id)
    if job is None or job.kind != "decode":
        raise HTTPException(404, "Задача не найдена или уже удалена.")
    if not job.results:
        raise HTTPException(400, "Нет результатов для экспорта.")
    if payload.format not in ("txt", "csv"):
        raise HTTPException(400, "Неизвестный формат экспорта. Поддерживаются TXT и CSV.")
    if payload.gsMode not in ("original", "readable"):
        raise HTTPException(400, "Неизвестный режим управляющих символов.")

    rows = [{"data": b64_to_bytes(r["dataB64"]), "page": r["page"],
             "gtin": r["gtin"], "status": "ok"} for r in job.results]
    if payload.dedup:
        rows = dedup_rows(rows)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = (job.extra.get("fileName") or "datamatrix")
    base = filename.rsplit(".", 1)[0]
    if payload.format == "txt":
        content = export_txt(rows, gs_mode=payload.gsMode)
        return Response(
            content=content, media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="decoded_{base}_{stamp}.txt"'},
        )
    content = export_csv(rows, gs_mode=payload.gsMode, filename=filename,
                        include_status=True)
    return Response(
        content=content, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="decoded_{base}_{stamp}.csv"'},
    )


# -------------------------------------------------------------- Вкладка 3: Нанесение

APPLY_EXTENSIONS = {"csv"}


@app.post("/api/apply/parse")
async def api_apply_parse(file: UploadFile):
    """Разбор CSV вкладки «Нанесение»: колонки «полный код» и «количество»
    -> предпросмотр строк и итоговых последовательностей."""
    ext = _check_upload(file, APPLY_EXTENSIONS)
    raw = await _read_upload(file)
    try:
        parsed = apply_core.parse_apply_file(file.filename, raw)
        rows = apply_core.prepare_rows(parsed)
    except (parsers.ParseError, apply_core.ApplyError) as e:
        raise HTTPException(400, str(e))
    ok = sum(1 for r in rows if r["status"] == "ok")
    return {
        "header": parsed.get("header"),
        "encoding": parsed["encoding"],
        "rows": rows,
        "counts": {"total": len(rows), "ok": ok, "error": len(rows) - ok},
        "hasGS": any(r["hasGS"] for r in rows),
        "maxRows": MAX_ROWS,
    }


@app.post("/api/apply/export")
async def api_apply_export(file: UploadFile):
    """Выгрузка последовательностей «код + 0x1D + 30 + количество» в CSV."""
    ext = _check_upload(file, APPLY_EXTENSIONS)
    raw = await _read_upload(file)
    try:
        parsed = apply_core.parse_apply_file(file.filename, raw)
        rows = apply_core.prepare_rows(parsed)
        content = apply_core.export_apply_csv(rows)
    except (parsers.ParseError, apply_core.ApplyError) as e:
        raise HTTPException(400, str(e))
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="apply_{stamp}.csv"'
        },
    )


# В production-сборке отдаём статику frontend/dist, если она собрана.
# ВАЖНО: на Windows mimetypes читает ассоциации из реестра, где тип .js может
# быть переопределён (например, текстовым редактором) в text/plain. Браузер
# откажется выполнять module-скрипт с таким MIME — принудительно чиним типы.
import mimetypes

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")

_DIST = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.isdir(_DIST):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=os.path.abspath(_DIST), html=True), name="static")