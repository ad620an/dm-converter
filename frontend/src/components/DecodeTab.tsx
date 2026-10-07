import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import * as api from '../api';
import type { DecodeRow, Job } from '../types';
import Dropzone from './Dropzone';

export default function DecodeTab() {
  const [job, setJob] = useState<Job | null>(null);
  const [fileName, setFileName] = useState('');
  const [error, setError] = useState('');
  const [dedup, setDedup] = useState(false);
  const [gsMode, setGsMode] = useState<'original' | 'readable'>('original');
  const [expanded, setExpanded] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);
  const pollRef = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    },
    [],
  );

  const busy = job?.status === 'queued' || job?.status === 'running';

  const handleFile = async (file: File) => {
    setError('');
    if (pollRef.current) window.clearInterval(pollRef.current);
    setJob(null);
    try {
      const jobId = await api.startDecode(file);
      setFileName(file.name);
      setJob({
        id: jobId, kind: 'decode', status: 'queued', phase: '', done: 0,
        total: 0, message: '', results: [], extra: {}, error: null,
        fileReady: false, fileName: null,
      });
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
      }, 700);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось начать декодирование');
    }
  };

  const rows: DecodeRow[] = useMemo(() => {
    if (!job?.results) return [];
    if (!dedup) return job.results;
    const seen = new Set<string>();
    return job.results.filter((r) => {
      if (seen.has(r.dataB64)) return false;
      seen.add(r.dataB64);
      return true;
    });
  }, [job, dedup]);

  const anyGS = rows.some((r) => r.hasGS);
  const okCount = rows.filter((r) => r.status === 'ok').length;
  const emptyPages = job?.extra?.emptyPages ?? [];

  const doExport = async (format: 'txt' | 'csv') => {
    if (!job) return;
    setExporting(true);
    setError('');
    try {
      const { blob, filename } = await api.exportDecoded(job.id, format, gsMode, dedup);
      api.downloadBlob(blob, filename);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось выполнить экспорт');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="tab-content">
      <Dropzone
        accept=".pdf,.jpg,.jpeg,.png"
        hint="PDF, JPG, PNG — все страницы PDF обрабатываются"
        disabled={busy}
        onFile={handleFile}
      />

      {error && <div className="alert alert--error">{error}</div>}

      {job && (job.status === 'running' || job.status === 'queued') && (
        <div className="progress-wrap">
          <div className="progress">
            <div
              className="progress__bar"
              style={{
                width: job.total
                  ? `${Math.round((job.done / job.total) * 100)}%`
                  : '10%',
              }}
            />
          </div>
          <span>{job.message || 'Подготовка…'}</span>
        </div>
      )}

      {job?.status === 'error' && (
        <div className="alert alert--error">{job.error ?? 'Ошибка декодирования'}</div>
      )}

      {job?.status === 'done' && (
        <>
          <div className="table-header">
            <h2 className="section-title">
              Результаты декодирования{fileName && ` — ${fileName}`}
            </h2>
            <span className="counts">
              Найдено кодов: {job.results.length}
              {dedup && ` · без дубликатов: ${rows.length}`}
              {' · '}декодировано: {okCount}
            </span>
          </div>

          {job.extra?.note && <div className="alert alert--error">{job.extra.note}</div>}
          {emptyPages.length > 0 && (
            <div className="alert alert--info">
              На страницах {emptyPages.join(', ')} DataMatrix-коды не обнаружены.
            </div>
          )}
          {anyGS && (
            <div className="alert alert--info">
              Обнаружены управляющие символы GS (ASCII 29). В таблице они отображаются
              как &lt;GS&gt;. При экспорте в режиме «Исходные символы» в файле
              сохраняется настоящий байт 0x1D.
            </div>
          )}

          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>№</th>
                  <th>Страница</th>
                  <th>Найденный код</th>
                  <th>GTIN</th>
                  <th>Статус</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <Fragment key={r.index}>
                    <tr
                      className="row-clickable"
                      onClick={() => setExpanded(expanded === r.index ? null : r.index)}
                    >
                      <td>{r.index}</td>
                      <td>{r.page}</td>
                      <td className="code-cell">{r.codeDisplay}</td>
                      <td>{r.gtin ?? '—'}</td>
                      <td>
                        <span className="badge badge--ok">OK</span>
                      </td>
                    </tr>
                    {expanded === r.index && (
                      <tr className="row-details">
                        <td colSpan={5}>
                          <dl className="details">
                            <div>
                              <dt>GTIN (AI 01)</dt>
                              <dd>{r.details?.ai01 ?? '—'}</dd>
                            </div>
                            <div>
                              <dt>Серийный номер (AI 21)</dt>
                              <dd>{r.details?.serial ?? '—'}</dd>
                            </div>
                            <div>
                              <dt>Криптохвост (AI 91/92/93)</dt>
                              <dd>{r.details?.crypto_tail ?? '—'}</dd>
                            </div>
                            <div>
                              <dt>Позиции GS</dt>
                              <dd>{r.gsPositions ?? '—'}</dd>
                            </div>
                            <div>
                              <dt>Длина последовательности</dt>
                              <dd>{r.details?.length ?? '—'} байт</dd>
                            </div>
                            <div className="details__hex">
                              <dt>HEX</dt>
                              <dd className="mono">{r.hex}</dd>
                            </div>
                          </dl>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>

          <div className="export-bar">
            <div className="export-mode">
              <span className="export-mode__title">Представление управляющих символов:</span>
              <label className="radio inline">
                <input
                  type="radio"
                  name="gsmode"
                  checked={gsMode === 'original'}
                  onChange={() => setGsMode('original')}
                />
                Исходные символы (настоящий 0x1D)
              </label>
              <label className="radio inline">
                <input
                  type="radio"
                  name="gsmode"
                  checked={gsMode === 'readable'}
                  onChange={() => setGsMode('readable')}
                />
                Читаемое представление (&lt;GS&gt;)
              </label>
            </div>
            <label className="checkbox">
              <input type="checkbox" checked={dedup} onChange={(e) => setDedup(e.target.checked)} />
              Исключить дубликаты
            </label>
            <button
              type="button"
              className="button button--secondary"
              disabled={exporting || !rows.length}
              onClick={() => doExport('txt')}
            >
              Скачать TXT
            </button>
            <button
              type="button"
              className="button button--secondary"
              disabled={exporting || !rows.length}
              onClick={() => doExport('csv')}
            >
              Скачать CSV
            </button>
          </div>
        </>
      )}
    </div>
  );
}