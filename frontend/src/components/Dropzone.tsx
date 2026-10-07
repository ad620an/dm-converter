import { useRef, useState } from 'react';

interface Props {
  accept: string;
  hint: string;          // «TXT, CSV, XLSX — до 1000 строк» или «PDF, JPG, PNG»
  disabled?: boolean;
  onFile: (file: File) => void;
}

// Современная drop-zone (ТЗ §31) с выбором файла кнопкой.
export default function Dropzone({ accept, hint, disabled, onFile }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div
      className={`dropzone${dragOver ? ' dropzone--over' : ''}${disabled ? ' dropzone--disabled' : ''}`}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        if (disabled) return;
        const file = e.dataTransfer.files?.[0];
        if (file) onFile(file);
      }}
    >
      <p className="dropzone__title">Перетащите файл сюда</p>
      <p className="dropzone__hint">{hint}</p>
      <button
        type="button"
        className="button button--secondary"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
      >
        Выберите файл
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = '';
        }}
      />
    </div>
  );
}