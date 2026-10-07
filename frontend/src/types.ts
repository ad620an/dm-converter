// Типы, зеркалящие API бэкенда. Источник истины для кода — b64-поля
// (rawBytes, ТЗ §40); display-поля используются только в интерфейсе.

export interface Cell {
  b64: string;      // base64 от UTF-8 байтов ячейки
  display: string;  // визуализация: 0x1D -> <GS>
}

export interface ParseRow {
  index: number;
  codeB64: string;
  codeDisplay: string;
  hex: string;
  article: string;
  quantity: string;
  hasGS: boolean;
  status: 'ok' | 'error';
  error: string | null;
  cells: Cell[];
}

export interface ColumnInfo {
  index: number;
  name: string | null;
  sample: string;
}

export interface ParseResult {
  format: string;
  encoding: string;
  header: string[] | null;
  columns: ColumnInfo[];
  mapping: Mapping;
  needsMapping: boolean;
  rows: ParseRow[];
  counts: { total: number; ok: number; error: number };
  hasGS: boolean;
  maxRows: number;
}

export interface Mapping {
  code: number | null;
  article: number | null;
  quantity: number | null;
}

export interface LabelOptions {
  labelWmm: number;
  labelHmm: number;
  dmWmm: number | null; // null = автоматический размер
  dmHmm: number | null;
  variant: 1 | 2 | 3;
}

export interface DecodeRow {
  index: number;
  page: number;
  dataB64: string;
  codeDisplay: string;
  hex: string;
  gtin: string | null;
  hasGS: boolean;
  status: string;
  gsPositions: string | null;
  details: {
    gtin: string | null;
    length: number;
    gs_positions: number[];
    ai_pairs: { ai: string; value: string }[];
    ai01: string | null;
    serial: string | null;
    crypto_tail: string | null;
  };
}

export interface ApplyRow {
  index: number;
  code: string;
  codeDisplay: string;
  hex: string;
  quantity: string;
  sequence: string | null;
  sequenceDisplay: string;
  hasGS: boolean;
  status: 'ok' | 'error';
  error: string | null;
}

export interface ApplyResult {
  header: string[] | null;
  encoding: string;
  rows: ApplyRow[];
  counts: { total: number; ok: number; error: number };
  hasGS: boolean;
  maxRows: number;
}

export type JobStatus = 'queued' | 'running' | 'done' | 'error';

export interface Job {
  id: string;
  kind: 'generate' | 'decode';
  status: JobStatus;
  phase: string;
  done: number;
  total: number;
  message: string;
  results: DecodeRow[];
  extra: {
    emptyPages?: number[];
    fileName?: string;
    note?: string;
    count?: number;
    skipped?: number;
  };
  error: string | null;
  fileReady: boolean;
  fileName: string | null;
}