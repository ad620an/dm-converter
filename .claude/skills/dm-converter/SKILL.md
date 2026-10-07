---
name: dm-converter
description: Гид по репозиторию dm-converter (GS1 DataMatrix для «Честного знака»): структура, локальный запуск, правила внесения изменений, тесты, обновление README, подготовка к публикации. Использовать для любой задачи в этом репозитории.
---

# dm-converter — гид по проекту

## Что это

Веб-сервис для кодов маркировки «Честный знак»: создание GS1 DataMatrix ECC 200
из TXT/CSV/XLSX (до 1000 строк, PDF-наклейки в мм, ZIP с PNG) и декодирование
PDF/JPG/PNG с экспортом в TXT/CSV. Backend — Python 3.9+ / FastAPI,
frontend — React 18 + TypeScript + Vite. Всё локально, файлы не покидают машину.

**Главный инвариант (ТЗ §45), его нельзя ломать:**

```text
source bytes → encode → image/PDF → decode → decoded bytes
source bytes === decoded bytes   # 0x1D (GS, ASCII 29) остаётся 0x1D
```

## Структура

```text
backend/app/main.py        REST API: /api/parse, /api/preview-label, /api/generate,
                           /api/decode, /api/jobs/*, /api/decode/{id}/export
backend/app/jobs.py        фоновые задачи с прогрессом
backend/app/core/dm.py     encode/decode DataMatrix (pylibdmtx, схема Ascii, bytes)
backend/app/core/gs1.py    разбор GS1 (AI 01/21/91/92), GTIN
backend/app/core/parsers.py  импорт TXT/CSV/XLSX (UTF-8, BOM, CP1251; без trim)
backend/app/core/display.py   <GS>/HEX — ТОЛЬКО отображение, исходные байты не меняет
backend/app/core/labels.py    геометрия наклейки, preview, PDF (reportlab)
backend/app/core/decoder.py   декодирование PDF/изображений (PyMuPDF, DPI 200→300→400)
backend/app/exporters.py   экспорт TXT/CSV (original / readable)
backend/tests/             pytest, фикстуры генерируются автоматически
frontend/src/components/  CreateTab, DecodeTab, ApplyTab, ColumnMapper, Dropzone
frontend/src/api.ts        клиент backend API (байты ходят в base64)
samples/                   реальные образцы PDF с кодами для e2e-тестов
```

## Запуск

```powershell
# Backend (терминал 1)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8000

# Frontend dev (терминал 2)
cd frontend
npm install
npm run dev        # http://localhost:5173, /api проксируется на :8000

# Альтернатива без двух терминалов
cd frontend && npm run build    # создаёт dist/, FastAPI отдаёт его на :8000
```

Swagger: http://localhost:8000/docs.

## Внесение изменений — правила пути данных

1. **Только `bytes` в пути данных.** Никаких `str`, `trim()`, регулярок по
   управляющим символам между парсером и энкодером/декодером.
2. **Отображение ≠ данные.** `<GS>`, HEX, base64 — только `display.py` и только
   для UI. Функции отображения не должны менять хранимые байты.
3. **Между frontend и backend байты в base64**; API не принимает коды как текст.
4. **XLSX не может хранить 0x1D** — ограничение формата XML 1.0, не баг.
5. Меняешь API-эндпоинт — проверь `frontend/src/api.ts` и соответствующий
   компонент.
6. После любых изменений backend — прогнать тесты (см. ниже).

## Проверка ошибок

```powershell
cd backend
python -m pytest tests -v     # 47 тестов; всё должно быть зелёным

cd ../frontend
npm run build                  # tsc strict + сборка; ошибки = не публиковать
```

Ключевые тесты инварианта: `test_roundtrip.py` (побайтовый 0x1D round-trip),
`test_e2e.py` (строка ЧЗ → PDF/PNG → декодер → побайтовое совпадение),
`test_import.py`/`test_export.py` (0x1D не теряется при импорте/экспорте).
Упавший тест здесь — регресс инварианта, чинить до всего остального.

## Обновление README

README.md на русском. Разделы: обзор, архитектура, библиотеки, 0x1D,
запуск, production, форматы файлов, API. Обновлять синхронно с кодом при изменении:
эндпоинтов, команд запуска, структуры каталогов, форматов/лимитов (например,
лимит 1000 строк), списка библиотек. После правки перечитай раздел и убедись,
что команды из него реально работают.

## Подготовка к публикации (чек-лист)

1. `python -m pytest tests -v` — все зелёные.
2. `npm run build` — без ошибок TS.
3. README синхронизирован с кодом.
4. В коммите нет: секретов, `scratch/`, логов, тестовых артефактов
   (`apply_out.csv`, `apply_parse.json` и т.п.), файлов с случайными данными.
5. `git status` чист, история коммитов осмысленная.
6. Для деплоя: `npm ci && npm run build`, затем
   `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1` из `backend/`.

## Особенности платформы

- Windows 10, оболочка **PowerShell** (в старых системах — 5.1: без `&&`,
  проверять синтаксис). В командах с кириллическими путями — кавычки.
- `pylibdmtx` тянет бинарник libdmtx — при проблемах установки проверять
  версию Python/сборку колеса.
- Результаты задач — во временном каталоге, удаляются через час; загруженные
  файлы нигде не сохраняются. Это требование приватности (ТЗ §32), не менять.