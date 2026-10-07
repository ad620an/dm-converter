import { useState } from 'react';
import * as api from '../api';
import type { ApplyResult } from '../types';
import Dropzone from './Dropzone';

export default function ApplyTab() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ApplyResult | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);

  const handleFile = async (f: File) => {
    setError('');
    setResult(null);
    setFile(null);
    setBusy(true);
    try {
      const parsed = await api.applyParse(f);
      setFile(f);
      setResult(parsed);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось прочитать файл');
    } finally {
      setBusy(false);
    }
  };

  const doExport = async () => {
    if (!file) return;
    setExporting(true);
    setError('');
    try {
      const { blob, filename } = await api.applyExport(file);
      api.downloadBlob(blob, filename);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сформировать файл');
    } finally {
      setExporting(false);
    }
  };

  const hasErrors = (result?.counts.error ?? 0) > 0;
  const firstError = result?.rows.find((r) => r.status === 'error');

  return (
    <div className="tab-content">
      <div className="alert alert--info">
        Файл CSV с <strong>двумя колонками</strong>: 1 — полный код маркировки
        (включая нечитаемые символы; GS отображается как &lt;GS&gt; и сохраняется
        в данных байтом 0x1D), 2 — количество. Каждая строка результата —
        символьная последовательность
        <strong> код + GS (ASCII 29) + 30 + количество</strong> без пробелов и
        дополнительных знаков.
      </div>

      <Dropzone
        accept=".csv"
        hint="CSV с двумя колонками — до 1000 строк"
        disabled={busy}
        onFile={handleFile}
      />

      {error && <div className="alert alert--error">{error}</div>}

      {result && (
        <>
          <div className="table-header">
            <h2 className="section-title">
              Строки{file && ` — ${file.name}`}
            </h2>
            <span className="counts">
              Загружено: {result.counts.total} · корректных: {result.counts.ok} ·
              ошибочных: {result.counts.error}
              {` · кодировка: ${result.encoding.toUpperCase()}`}
            </span>
          </div>

          {firstError && (
            <div className="alert alert--error">
              Некорректные строки: {result.counts.error}. Первая — №
              {firstError.index}: {firstError.error}. Файл сформировать нельзя,
              исправьте данные и загрузите заново.
            </div>
          )}

          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>№</th>
                  <th>Полный код</th>
                  <th>Количество</th>
                  <th>Итоговая последовательность</th>
                  <th>Статус</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r) => (
                  <tr key={r.index} className={r.status === 'error' ? 'row-error' : ''}>
                    <td>{r.index}</td>
                    <td className="code-cell">{r.codeDisplay || '—'}</td>
                    <td>{r.status === 'ok' ? r.quantity : (r.quantity || '—')}</td>
                    <td className="code-cell">{r.sequenceDisplay || '—'}</td>
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

          <div className="generate-bar">
            <button
              type="button"
              className="button button--primary"
              disabled={exporting || hasErrors || !result.counts.ok}
              onClick={doExport}
            >
              Сформировать файл ({result.counts.ok})
            </button>
          </div>
        </>
      )}
    </div>
  );
}