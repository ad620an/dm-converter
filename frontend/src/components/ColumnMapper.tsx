import { useState } from 'react';
import type { ColumnInfo, Mapping, ParseRow } from '../types';

interface Props {
  columns: ColumnInfo[];
  initial: Mapping;
  onConfirm: (mapping: Mapping) => void;
  onCancel: () => void;
}

// Окно сопоставления колонок (ТЗ §5): показывается, когда определить
// колонки автоматически не удалось.
export default function ColumnMapper({ columns, initial, onConfirm, onCancel }: Props) {
  const [code, setCode] = useState<number | null>(initial.code);
  const [article, setArticle] = useState<number | null>(initial.article);
  const [quantity, setQuantity] = useState<number | null>(initial.quantity);

  const options = columns.map((c) => (
    <option key={c.index} value={c.index}>
      {`Колонка ${c.index + 1}${c.name ? ` — «${c.name}»` : ''}${c.sample ? ` (пример: ${c.sample.slice(0, 20)}…)` : ''}`}
    </option>
  ));

  return (
    <div className="modal-backdrop">
      <div className="modal">
        <h3>Сопоставление колонок</h3>
        <p className="modal__note">
          Не удалось автоматически определить колонку с кодами DataMatrix. Выберите колонки вручную.
        </p>
        <label className="field">
          Колонка с DataMatrix:
          <select
            value={code ?? ''}
            onChange={(e) => setCode(e.target.value === '' ? null : Number(e.target.value))}
          >
            <option value="">— отсутствует —</option>
            {options}
          </select>
        </label>
        <label className="field">
          Колонка Артикул:
          <select
            value={article ?? ''}
            onChange={(e) => setArticle(e.target.value === '' ? null : Number(e.target.value))}
          >
            <option value="">— отсутствует —</option>
            {options}
          </select>
        </label>
        <label className="field">
          Колонка Количество:
          <select
            value={quantity ?? ''}
            onChange={(e) => setQuantity(e.target.value === '' ? null : Number(e.target.value))}
          >
            <option value="">— отсутствует —</option>
            {options}
          </select>
        </label>
        <div className="modal__actions">
          <button type="button" className="button button--secondary" onClick={onCancel}>
            Отмена
          </button>
          <button
            type="button"
            className="button button--primary"
            disabled={code === null}
            onClick={() => onConfirm({ code, article, quantity })}
          >
            Применить
          </button>
        </div>
      </div>
    </div>
  );
}

interface Cell {
  b64: string;
  display: string;
}

/** Пере-применяет маппинг колонок на клиенте — без повторной загрузки файла. */
export function remapRows(rows: ParseRow[], mapping: Mapping): ParseRow[] {
  return rows.map((row) => {
    const cell = (idx: number | null): Cell | null =>
      idx !== null && row.cells[idx] ? row.cells[idx] : null;
    const codeCell = cell(mapping.code);
    return {
      ...row,
      codeB64: codeCell ? codeCell.b64 : '',
      codeDisplay: codeCell ? codeCell.display : '',
      hasGS: codeCell ? codeCell.display.includes('<GS>') : false,
      article: cell(mapping.article)?.display ?? '',
      quantity: cell(mapping.quantity)?.display ?? '',
      status: codeCell && codeCell.b64 ? 'ok' : 'error',
      error: codeCell && codeCell.b64 ? null : 'Пустой код маркировки',
    };
  });
}