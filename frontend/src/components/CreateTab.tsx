import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as api from '../api';
import type { Job, LabelOptions, Mapping, ParseResult, ParseRow } from '../types';
import ColumnMapper, { remapRows } from './ColumnMapper';
import Dropzone from './Dropzone';

const LABEL_PRESETS: [string, number, number][] = [
  ['20 × 30 мм', 20, 30],
  ['20 × 40 мм', 20, 40],
  ['25 × 43 мм', 25, 43],
  ['30 × 50 мм', 30, 50],
  ['30 × 58 мм', 30, 58],
  ['40 × 58 мм', 40, 58],
  ['40 × 60 мм', 40, 60],
  ['пользовательский', 0, 0],
];

const DM_PRESETS: [string, number | null][] = [
  ['автоматический', null],
  ['12 × 12 мм', 12],
  ['15 × 15 мм', 15],
  ['18 × 18 мм', 18],
  ['20 × 20 мм', 20],
  ['22 × 22 мм', 22],
  ['25 × 25 мм', 25],
  ['пользовательский', -1],
];

export default function CreateTab() {
  const [rows, setRows] = useState<ParseRow[] | null>(null);
  const [meta, setMeta] = useState<ParseResult | null>(null);
  const [fileName, setFileName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [manualText, setManualText] = useState('');
  const [showMapper, setShowMapper] = useState(false);

  // Параметры этикетки
  const [labelPreset, setLabelPreset] = useState('40 × 58 мм');
  const [labelW, setLabelW] = useState(40);
  const [labelH, setLabelH] = useState(58);
  const [dmPreset, setDmPreset] = useState('автоматический');
  const [dmW, setDmW] = useState(18);
  const [dmH, setDmH] = useState(18);
  const [variant, setVariant] = useState<1 | 2 | 3>(1);

  // Прогресс генерации
  const [job, setJob] = useState<Job | null>(null);
  const [format, setFormat] = useState<'pdf' | 'pngzip'>('pdf');
  const pollRef = useRef<number | null>(null);

  const options: LabelOptions = useMemo(
    () => ({
      labelWmm: labelW,
      labelHmm: labelH,
      dmWmm: dmPreset === 'автоматический' ? null : dmPreset === 'пользовательский' ? dmW : presetDmSize(dmPreset),
      dmHmm: dmPreset === 'автоматический' ? null : dmPreset === 'пользовательский' ? dmH : presetDmSize(dmPreset),
      variant,
    }),
    [labelW, labelH, dmPreset, dmW, dmH, variant],
  );

  const okRows = useMemo(() => (rows ?? []).filter((r) => r.status === 'ok'), [rows]);

  // ---- Live-preview наклейки (§16)
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewError, setPreviewError] = useState('');
  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      const first = okRows[0];
      if (!first) {
        if (!cancelled) setPreviewUrl('');
        return;
      }
      try {
        const url = await api.previewLabel(first.codeB64, first.article, first.quantity, options);
        if (!cancelled) {
          setPreviewUrl((old) => {
            if (old) URL.revokeObjectURL(old);
            return url;
          });
          setPreviewError('');
        } else {
          URL.revokeObjectURL(url);
        }
      } catch (e) {
        if (!cancelled) setPreviewError(e instanceof Error ? e.message : 'Ошибка предпросмотра');
      }
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [okRows, options]);

  useEffect(
    () => () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      if (pollRef.current) window.clearInterval(pollRef.current);
    },
    [previewUrl],
  );

  const handleFile = useCallback(async (file: File) => {
    setError('');
    setLoading(true);
    try {
      const result = await api.parseFile(file);
      setRows(result.rows);
      setMeta(result);
      setFileName(file.name);
      if (result.needsMapping) setShowMapper(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось прочитать файл');
    } finally {
      setLoading(false);
    }
  }, []);

  // Ручной ввод (§4.2): textarea — только источник символов; данные
  // переводятся в байты (UTF-8, b64) без какой-либо очистки.
  const handleManual = () => {
    setError('');
    if (!manualText.trim()) {
      setError('Вставьте хотя бы одну символьную последовательность.');
      return;
    }
    const lines = manualText.split(/\r\n|\n/).filter((l) => l !== '');
    if (lines.length > 1000) {
      setError(`Вставлено ${lines.length} строк. Максимально допустимое количество — 1000.`);
      return;
    }
    const parsed: ParseRow[] = lines.map((line, i) => {
      const parts = line.includes('\t') ? line.split('\t') : [line];
      const code = parts[0] ?? '';
      const article = parts[1] ?? '';
      const quantity = parts[2] ?? '';
      const codeB64 = api.utf8ToB64(code);
      return {
        index: i + 1,
        codeB64,
        codeDisplay: visualize(code),
        hex: api.bytesToHex(api.b64ToBytes(codeB64)),
        article: visualize(article),
        quantity,
        hasGS: code.includes('\u001d'),
        status: code ? 'ok' : 'error',
        error: code ? null : 'Пустой код маркировки',
        cells: [],
      };
    });
    setRows(parsed);
    setMeta({
      format: 'txt',
      encoding: 'utf-8',
      header: null,
      columns: [],
      mapping: { code: 0, article: null, quantity: null },
      needsMapping: false,
      rows: parsed,
      counts: {
        total: parsed.length,
        ok: parsed.filter((r) => r.status === 'ok').length,
        error: parsed.filter((r) => r.status === 'error').length,
      },
      hasGS: parsed.some((r) => r.hasGS),
      maxRows: 1000,
    });
    setFileName('ручной ввод');
  };

  const startGenerate = async () => {
    if (!okRows.length) return;
    setError('');
    try {
      const jobId = await api.startGenerate(
        okRows.map((r) => ({ codeB64: r.codeB64, article: r.article, quantity: r.quantity })),
        options,
        format,
      );
      setJob({
        id: jobId, kind: 'generate', status: 'queued', phase: '', done: 0,
        total: okRows.length, message: '', results: [], extra: {}, error: null,
        fileReady: false, fileName: null,
      });
      if (pollRef.current) window.clearInterval(pollRef.current);
      pollRef.current = window.setInterval(async () => {
        try {
          const j = await api.getJob(jobId);
          setJob(j);
          if (j.status === 'done' || j.status === 'error') {
            if (pollRef.current) window.clearInterval(pollRef.current);
            pollRef.current = null;
          }
        } catch {
          /* продолжаем опрос */
        }
      }, 600);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось запустить генерацию');
    }
  };

  const busy = job?.status === 'queued' || job?.status === 'running' || loading;

  return (
    <div className="tab-content">
      <div className="layout-two-col">
        <div className="col-left">
          <h2 className="section-title">Данные для маркировки</h2>
          <Dropzone
            accept=".txt,.csv,.xlsx"
            hint="TXT, CSV, XLSX — до 1000 строк"
            disabled={busy}
            onFile={handleFile}
          />

          <details className="manual-input">
            <summary>Или вставьте последовательности вручную</summary>
            <textarea
              rows={4}
              placeholder={'Одна последовательность на строку. Управляющий символ GS (ASCII 29) можно вставить из буфера обмена.\nФормат с табуляцией: Код⇥Артикул⇥Количество'}
              value={manualText}
              onChange={(e) => setManualText(e.target.value)}
            />
            <button type="button" className="button button--secondary" disabled={busy} onClick={handleManual}>
              Обработать текст
            </button>
          </details>

          {error && <div className="alert alert--error">{error}</div>}

          {meta?.hasGS && (
            <div className="alert alert--info">
              Обнаружены управляющие символы GS (ASCII 29). Они будут сохранены при
              генерации и экспорте. В таблице они отображаются как &lt;GS&gt;.
            </div>
          )}

          <h2 className="section-title">Размер DataMatrix</h2>
          <div className="option-group">
            {DM_PRESETS.map(([name]) => (
              <label key={name} className="radio">
                <input
                  type="radio"
                  name="dmsize"
                  checked={dmPreset === name}
                  onChange={() => setDmPreset(name)}
                />
                {name}
              </label>
            ))}
          </div>
          {dmPreset === 'пользовательский' && (
            <div className="custom-size">
              <label>
                Ширина DataMatrix, мм
                <input type="number" min={5} max={200} step={0.5} value={dmW}
                  onChange={(e) => setDmW(Number(e.target.value))} />
              </label>
              <label>
                Высота DataMatrix, мм
                <input type="number" min={5} max={200} step={0.5} value={dmH}
                  onChange={(e) => setDmH(Number(e.target.value))} />
              </label>
            </div>
          )}

          <h2 className="section-title">Размер наклейки</h2>
          <div className="option-group">
            {LABEL_PRESETS.map(([name, w, h]) => (
              <label key={name} className="radio">
                <input
                  type="radio"
                  name="labelsize"
                  checked={labelPreset === name}
                  onChange={() => {
                    setLabelPreset(name);
                    if (w > 0) {
                      setLabelW(w);
                      setLabelH(h);
                    }
                  }}
                />
                {name}
              </label>
            ))}
          </div>
          {labelPreset === 'пользовательский' && (
            <div className="custom-size">
              <label>
                Ширина наклейки, мм
                <input type="number" min={10} max={300} step={0.5} value={labelW}
                  onChange={(e) => setLabelW(Number(e.target.value))} />
              </label>
              <label>
                Высота наклейки, мм
                <input type="number" min={10} max={300} step={0.5} value={labelH}
                  onChange={(e) => setLabelH(Number(e.target.value))} />
              </label>
            </div>
          )}

          <h2 className="section-title">Дополнительная информация на наклейке</h2>
          <div className="option-group option-group--stack">
            <label className="radio">
              <input type="radio" name="variant" checked={variant === 1} onChange={() => setVariant(1)} />
              Артикул + Количество + GTIN + первые 38 знаков DataMatrix
            </label>
            <label className="radio">
              <input type="radio" name="variant" checked={variant === 2} onChange={() => setVariant(2)} />
              GTIN + первые 38 знаков DataMatrix
            </label>
            <label className="radio">
              <input type="radio" name="variant" checked={variant === 3} onChange={() => setVariant(3)} />
              Только DataMatrix
            </label>
          </div>
        </div>

        <div className="col-right">
          <h2 className="section-title">Предпросмотр наклейки</h2>
          <div className="preview-box">
            {previewUrl ? (
              <img
                src={previewUrl}
                alt="Предпросмотр наклейки"
                style={{ maxWidth: `${Math.min(labelW * 6, 420)}px`, width: `${labelW * 6}px` }}
              />
            ) : (
              <div className="preview-empty">
                {previewError || 'Загрузите данные, чтобы увидеть предпросмотр наклейки.'}
              </div>
            )}
          </div>
          <p className="muted">
            Пропорции соответствуют наклейке {labelW} × {labelH} мм. DataMatrix —{' '}
            {dmPreset === 'автоматический'
              ? 'автоматический размер'
              : `${options.dmWmm} × ${options.dmHmm} мм`}
            . Точные физические размеры соблюдаются в PDF.
          </p>
        </div>
      </div>

      {rows && meta && (
        <div className="table-section">
          <div className="table-header">
            <h2 className="section-title">
              Импортированные строки{fileName && ` — ${fileName}`}
            </h2>
            <span className="counts">
              Загружено: {meta.counts.total} · корректных: {meta.counts.ok} · ошибочных:{' '}
              {meta.counts.error}
              {meta.format && ` · формат: ${meta.format.toUpperCase()} (${meta.encoding})`}
            </span>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>№</th>
                  <th>Код</th>
                  <th>Артикул</th>
                  <th>Количество</th>
                  <th>Статус</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.index} className={r.status === 'error' ? 'row-error' : ''}>
                    <td>{r.index}</td>
                    <td className="code-cell">{r.codeDisplay || '—'}</td>
                    <td>{r.article || '—'}</td>
                    <td>{r.quantity || '—'}</td>
                    <td>
                      {r.status === 'ok' ? (
                        <span className="badge badge--ok">OK</span>
                      ) : (
                        <span className="badge badge--error">{r.error ?? 'Ошибка'}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted">
            &lt;GS&gt; — управляющий символ ASCII 29 (Group Separator). При генерации
            DataMatrix используется исходный символ 0x1D.
          </p>

          <div className="generate-bar">
            <label className="radio inline">
              <input type="radio" name="fmt" checked={format === 'pdf'} onChange={() => setFormat('pdf')} />
              PDF (одна наклейка = одна страница)
            </label>
            <label className="radio inline">
              <input type="radio" name="fmt" checked={format === 'pngzip'} onChange={() => setFormat('pngzip')} />
              ZIP с PNG
            </label>
            <button
              type="button"
              className="button button--primary"
              disabled={busy || !okRows.length}
              onClick={startGenerate}
            >
              Сгенерировать DataMatrix ({okRows.length})
            </button>
          </div>

          {job && (job.status === 'running' || job.status === 'queued') && (
            <div className="progress-wrap">
              <div className="progress">
                <div className="progress__bar" style={{ width: `${job.total ? (job.done / job.total) * 100 : 0}%` }} />
              </div>
              <span>{job.message || 'Подготовка…'}</span>
            </div>
          )}
          {job?.status === 'error' && <div className="alert alert--error">{job.error}</div>}
          {job?.status === 'done' && job.fileReady && (
            <div className="alert alert--success">
              Готово: {job.extra?.count ?? job.total} кодов сгенерировано.{' '}
              {job.extra?.skipped ? `Пропущено пустых строк: ${job.extra.skipped}. ` : ''}
              <a className="download-link" href={`/api/jobs/${job.id}/file`}>
                Скачать {job.fileName}
              </a>
            </div>
          )}
        </div>
      )}

      {showMapper && meta && (
        <ColumnMapper
          columns={meta.columns}
          initial={meta.mapping}
          onConfirm={(m: Mapping) => {
            setRows(remapRows(meta.rows, m));
            setMeta({ ...meta, mapping: m, needsMapping: false });
            setShowMapper(false);
          }}
          onCancel={() => setShowMapper(false)}
        />
      )}
    </div>
  );
}

function presetDmSize(name: string): number {
  const m = /(\d+(?:[.,]\d+)?)/.exec(name);
  return m ? parseFloat(m[1].replace(',', '.')) : 0;
}

/** Визуализация управляющих символов для UI (0x1D -> <GS>) — только отображение. */
function visualize(s: string): string {
  return s
    .replace(/\u001d/g, '<GS>')
    .replace(/\u001e/g, '<RS>')
    .replace(/\u0004/g, '<EOT>');
}