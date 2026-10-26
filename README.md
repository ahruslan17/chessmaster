# Chess Master

AI-powered chess game analysis and coaching: Stockfish analysis, LLM commentary, period reports.

---

## UI Design System

Описанная ниже логика дизайна является фиксированной для frontend. При добавлении новых экранов и компонентов соблюдать эти правила.

### Шрифт

- **Основной**: [JetBrains Mono](https://fonts.google.com/specimen/JetBrains+Mono) (400, 500, 600)
- Подключение: Google Fonts, `font-family: "JetBrains Mono", monospace`
- Эффект: техничный, читаемый моноширинный стиль, ассоциируется с шахматной нотацией
- На странице разбора партии интерфейс и объяснения используют системный sans-serif (`font-coach`); шахматная нотация и оценки сохраняют JetBrains Mono (`font-mono`). Остальные страницы не меняются.

### Цветовая палитра

**Базовый фон и поверхности:**

| Token       | Hex       | Назначение                    |
|-------------|-----------|-------------------------------|
| `chess-dark`| `#2d2d2d` | Фон страницы (html body)      |
| `chess-light`| `#3d3d3d`| Карточки, хедер, строки таблицы |
| `stone-100` | —         | Основной текст заголовков     |
| `stone-200` | —         | Основной текст контента       |
| `stone-300` | —         | Второстепенный текст         |
| `stone-400` | —         | Labels, заголовки секций      |
| `stone-500` | —         | Плейсхолдеры, подписи         |
| `stone-600` | —         | Границы, разделители          |

**Акцентные цвета:**

| Token       | Hex       | Назначение                    |
|-------------|-----------|-------------------------------|
| `chess-highlight` | `#4a7c59` | Кнопки, ссылки, focus, активный элемент |

**Семантика качества хода (Move classification):**

| Класс       | Цвет        | Назначение      |
|-------------|-------------|-----------------|
| `chess-best`| `#22c55e`   | Best move       |
| `chess-good`| `#84cc16`   | Good move       |
| `chess-inaccuracy`| `#eab308` | Inaccuracy      |
| `chess-mistake`   | `#f97316` | Mistake         |
| `chess-blunder`   | `#ef4444` | Blunder         |

**Ошибки:** `red-400` для текста ошибок.

### Уровни заголовков

| Элемент        | Tailwind                         | Назначение                      |
|----------------|-----------------------------------|---------------------------------|
| H1 (страница)  | `text-2xl font-semibold text-stone-100` | Заголовок страницы (Game Library, Period Reports) |
| H2 (секция)    | `text-lg font-semibold text-stone-100`  | Заголовок секции (Upload PGN, game title) |
| H3 (подсекция) | `text-sm font-semibold text-stone-400`  | Заголовки панелей (Moves, Commentary) |
| Лого/нав       | `text-xl font-semibold text-stone-100`  | Логотип в хедере               |

### Компоненты

**Кнопки первичные (CTA):**
- `rounded bg-chess-highlight px-4 py-2 font-medium text-stone-100`
- Hover: `hover:bg-chess-highlight/80`
- Disabled: `disabled:opacity-50`

**Кнопки вторичные / ссылки:**
- `text-chess-highlight hover:underline` или `text-stone-400 transition hover:text-stone-100`

**Поля ввода (input, select):**
- `rounded border border-stone-600 bg-chess-dark px-3 py-2 text-stone-200`
- Focus: `focus:border-chess-highlight focus:outline-none`
- Placeholder: `placeholder-stone-500`
- Label: `text-sm text-stone-500` или `text-stone-400`, `mb-1 block`

**Карточки и панели:**
- `rounded-lg border border-stone-600 bg-chess-light/30 p-4` или `p-6`
- Вариант вложенности: `bg-chess-dark/50`, `border-stone-600/50`

**Таблицы:**
- Контейнер: `overflow-hidden rounded-lg border border-stone-600`
- Header: `bg-chess-light/50`, `text-sm font-medium text-stone-400`
- Строка: `border-b border-stone-600/50`, `hover:bg-chess-light/30`
- Ячейка: `px-4 py-3 text-stone-200` (основное), `text-stone-500` (второстепенное)

**Chessboard:**
- Клетки: light `#4a5568`, dark `#2d3748`, last move `#6b7280`
- Обводка: `border border-stone-600`, `rounded-lg`, `shadow-xl`

### Отступы и сетка

- Контейнер контента: `max-w-7xl mx-auto px-6 py-8`
- Вертикальные блоки: `space-y-6` или `space-y-4`
- Горизонтальные группы: `flex gap-4` или `gap-6`

### Общая логика

- **Тема**: тёмная, без «игрового» или броского стиля
- **Читаемость**: достаточный контраст текста (stone-100/200 на dark)
- **Иерархия**: заголовки страниц → секций → подсекций; акцент только на CTA и важных действиях
- **Семантика**: цвета ходов однозначно отражают качество (зелёный = хорошо, красный = плохо)
- **Консистентность**: один акцентный цвет (`chess-highlight`) для интерактивных элементов

---

## Run

```bash
# Docker Compose
docker compose up -d --build

# App: http://localhost
# API: http://localhost:8000
```

Локально: backend `uv run uvicorn app.main:app --reload`, frontend `cd frontend && npm run dev`.
