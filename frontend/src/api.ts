// API-клиент. Все бинарные данные передаются в base64 — управляющие
// символы (0x1D) не могут потеряться при транспортировке (ТЗ §40).

import type { ApplyResult, Job, LabelOptions, ParseResult } from './types';

export class ApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function readError(res: Response): Promise<never> {
  let message = `Ошибка сервера (${res.status})`;
  try {
    const data = await res.json();
    if (data && typeof data.detail === 'string') message = data.detail;
  } catch {
    /* оставляем стандартное сообщение */
  }
  throw new ApiError(message);
}

export function utf8ToB64(s: string): string {
  const bytes = new TextEncoder().encode(s);
  let bin = '';
  bytes.forEach((b) => {
    bin += String.fromCharCode(b);
  });
  return btoa(bin);
}

export async function parseFile(file: File): Promise<ParseResult> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch('/api/parse', { method: 'POST', body: form });
  if (!res.ok) await readError(res);
  return (await res.json()) as ParseResult;
}

export async function previewLabel(
  codeB64: string,
  article: string,
  quantity: string,
  options: LabelOptions,
): Promise<string> {
  const res = await fetch('/api/preview-label', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ codeB64, article, quantity, options }),
  });
  if (!res.ok) await readError(res);
  return URL.createObjectURL(await res.blob());
}

export async function startGenerate(
  rows: { codeB64: string; article: string; quantity: string }[],
  options: LabelOptions,
  format: 'pdf' | 'pngzip',
): Promise<string> {
  const res = await fetch('/api/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rows, options, format }),
  });
  if (!res.ok) await readError(res);
  const data = await res.json();
  return data.jobId as string;
}

export async function startDecode(file: File): Promise<string> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch('/api/decode', { method: 'POST', body: form });
  if (!res.ok) await readError(res);
  const data = await res.json();
  return data.jobId as string;
}

export async function getJob(jobId: string): Promise<Job> {
  const res = await fetch(`/api/jobs/${jobId}`);
  if (!res.ok) await readError(res);
  return (await res.json()) as Job;
}

export async function exportDecoded(
  jobId: string,
  format: 'txt' | 'csv',
  gsMode: 'original' | 'readable',
  dedup: boolean,
): Promise<{ blob: Blob; filename: string }> {
  const res = await fetch(`/api/decode/${jobId}/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ format, gsMode, dedup }),
  });
  if (!res.ok) await readError(res);
  const cd = res.headers.get('Content-Disposition') || '';
  const m = /filename="?([^";]+)"?/.exec(cd);
  return { blob: await res.blob(), filename: m ? m[1] : `decoded.${format}` };
}

// ---------------------------------------------------------------- Нанесение

/** Разбор CSV «полный код + количество» для вкладки «Нанесение». */
export async function applyParse(file: File): Promise<ApplyResult> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch('/api/apply/parse', { method: 'POST', body: form });
  if (!res.ok) await readError(res);
  return (await res.json()) as ApplyResult;
}

/** Выгрузка CSV: одна колонка — «код + 0x1D + 30 + количество». */
export async function applyExport(
  file: File,
): Promise<{ blob: Blob; filename: string }> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch('/api/apply/export', { method: 'POST', body: form });
  if (!res.ok) await readError(res);
  const cd = res.headers.get('Content-Disposition') || '';
  const m = /filename="?([^";]+)"?/.exec(cd);
  return { blob: await res.blob(), filename: m ? m[1] : 'apply.csv' };
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Побайтовое декодирование b64 — для HEX-подсказки и отладки. */
export function b64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) out[i] = bin.charCodeAt(i);
  return out;
}

export function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes, (b) => b.toString(16).toUpperCase().padStart(2, '0')).join(' ');
}