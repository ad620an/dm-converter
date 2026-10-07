import { useState } from 'react';
import ApplyTab from './components/ApplyTab';
import CreateTab from './components/CreateTab';
import DecodeTab from './components/DecodeTab';

type TabId = 'create' | 'decode' | 'apply';

export default function App() {
  // Состояние вкладок: все смонтированы, неактивные скрыты — состояние
  // сохраняется при переключении (ТЗ §3).
  const [tab, setTab] = useState<TabId>('create');

  return (
    <div className="app">
      <header className="header">
        <div className="header__inner">
          <h1>DataMatrix — Честный знак</h1>
          <p className="header__subtitle">Создание и декодирование кодов маркировки</p>
        </div>
      </header>

      <nav className="tabs">
        <div className="tabs__inner">
          <button
            type="button"
            className={`tab${tab === 'create' ? ' tab--active' : ''}`}
            onClick={() => setTab('create')}
          >
            Создать DataMatrix
          </button>
          <button
            type="button"
            className={`tab${tab === 'decode' ? ' tab--active' : ''}`}
            onClick={() => setTab('decode')}
          >
            Декодировать
          </button>
          <button
            type="button"
            className={`tab${tab === 'apply' ? ' tab--active' : ''}`}
            onClick={() => setTab('apply')}
          >
            Нанесение
          </button>
        </div>
      </nav>

      <main className="main">
        <div hidden={tab !== 'create'}>
          <CreateTab />
        </div>
        <div hidden={tab !== 'decode'}>
          <DecodeTab />
        </div>
        <div hidden={tab !== 'apply'}>
          <ApplyTab />
        </div>
      </main>

      <footer className="footer">
        Все операции выполняются локально. Управляющий символ GS (ASCII 29, 0x1D)
        сохраняется в данных без изменений; обозначение &lt;GS&gt; используется
        только для отображения.
      </footer>
    </div>
  );
}